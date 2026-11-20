"""Tareas periódicas de Celery beat (4.5 y 5.3)."""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select, text

from core import disk
from core.celeryapp import celery_app
from core.db import session_scope
from core.errors import ErrorCode
from core.external import send_mail
from core.jobs import MAX_ATTEMPTS, utcnow
from core.models import Job, Share, Upload
from core.settings import get_settings
from core.storage import Store
from core.valkey import get_valkey

log = logging.getLogger("maintenance")
STALE_SECONDS = 180


@celery_app.task(name="core.maintenance.cleanup_expired")
def cleanup_expired() -> dict:
    settings = get_settings()
    store = Store(settings.FILESTORE_PATH)
    r = get_valkey()
    now = utcnow()
    counts = {"jobs": 0, "uploads": 0, "shares": 0}
    with session_scope() as s:
        for job in s.scalars(select(Job).where(Job.expires_at < now, Job.status != "expired")).all():
            store.remove_job(str(job.id))
            disk.release(r, f"job:{job.id}")
            job.status = "expired"
            counts["jobs"] += 1
        stale_uploads = s.scalars(
            select(Upload).where(
                (Upload.expires_at < now)
                | ((Upload.state == "uploading") & (Upload.created_at < now - timedelta(hours=24)))
                | (Upload.state == "rejected")
            )
        ).all()
        for up in stale_uploads:
            store.remove_upload(up.id)
            disk.release(r, up.id)
            s.delete(up)
            counts["uploads"] += 1
        # 9.4 y 12.5: el texto de los documentos y la caché de IA caducan con los archivos; `ai_requests`, a los 90 días.
        from core.models import AiCache, AiRequest, DocumentText

        counts["ai"] = (s.execute(delete(DocumentText).where(DocumentText.expires_at < now)).rowcount
                        + s.execute(delete(AiCache).where(AiCache.expires_at < now)).rowcount
                        + s.execute(delete(AiRequest).where(AiRequest.created_at < now - timedelta(days=90))).rowcount
                        + s.execute(text("DELETE FROM document_chunks WHERE expires_at < :now"), {"now": now}).rowcount)
        for share in s.scalars(select(Share).where(Share.expires_at < now)).all():
            try:
                import shutil

                shutil.rmtree(store.share_dir(str(share.id)), ignore_errors=True)
            except ValueError:
                pass
            s.delete(share)
            counts["shares"] += 1
    return counts


@celery_app.task(name="core.maintenance.signature_requests")
def signature_requests() -> dict:
    """solicitar-firmas (F4-C2, D-202): pasa los resultados de los trabajos a cada solicitud, avisa al siguiente
    firmante, crea el sellado final, caduca las solicitudes y borra los archivos de las terminadas hace 30 días."""
    from core import signreq
    from core.registry import load_registry

    return signreq.tick(get_settings(), load_registry())


@celery_app.task(name="core.maintenance.requeue_stale")
def requeue_stale() -> int:
    """Reencola (intento nuevo) los trabajos `running` sin latido; al tercer intento, WORKER_LOST."""
    from core.registry import load_registry

    r = get_valkey()
    registry = load_registry()
    n = 0
    limit = utcnow() - timedelta(seconds=STALE_SECONDS)
    with session_scope() as s:
        for job in s.scalars(select(Job).where(Job.status == "running", Job.heartbeat_at < limit).with_for_update(skip_locked=True)).all():
            if job.attempts >= MAX_ATTEMPTS:
                job.status = "failed"
                job.error_code = ErrorCode.WORKER_LOST
                job.finished_at = utcnow()
                disk.release(r, f"job:{job.id}")
                _settle_ai(s, r, job)
                continue
            job.status = "queued"
            spec = registry.get(job.tool)
            if spec is None:
                continue
            # Los secretos no se guardan: un trabajo que llevaba contraseña y muere se marca como fallido.
            if job.has_secrets:
                job.status = "failed"
                job.error_code = ErrorCode.WORKER_LOST
                job.finished_at = utcnow()
                _settle_ai(s, r, job)
                continue
            celery_app.send_task(
                "tools.tasks.run_job",
                args=[str(job.id), job.attempts + 1, ""],
                queue=job.queue,
                priority=job.priority,
                soft_time_limit=spec.time_limit,
                time_limit=spec.time_limit + 60,
            )
            n += 1
    return n


@celery_app.task(name="core.maintenance.disk_alert")
def disk_alert() -> bool:
    settings = get_settings()
    r = get_valkey()
    st = disk.status(r, Path(settings.FILESTORE_PATH), settings.DISK_MAX_USAGE_PERCENT, settings.DISK_MIN_FREE_GB)
    if st.guard_active and r.set("alert:disk", "1", nx=True, ex=3600):
        send_mail(settings.SMTP_URL, settings.MAIL_FROM, settings.admin_emails,
                  f"[{settings.APP_NAME}] Guarda de disco activa",
                  f"Uso {st.usage_percent:.1f} %, libre {st.free / disk.GB:.1f} GB, reservado {st.reserved / disk.GB:.2f} GB.")
    return st.guard_active


@celery_app.task(name="core.maintenance.find_orphans")
def find_orphans() -> dict:
    """Directorios de trabajos sin fila y filas vivas sin directorio."""
    settings = get_settings()
    store = Store(settings.FILESTORE_PATH)
    jobs_root = Path(settings.FILESTORE_PATH) / "jobs"
    removed_dirs = 0
    with session_scope() as s:
        live = {str(j) for j in s.scalars(select(Job.id).where(Job.status.in_(("queued", "running", "succeeded")))).all()}
        if jobs_root.exists():
            for d in jobs_root.iterdir():
                if d.is_dir() and d.name not in live and time.time() - d.stat().st_mtime > 3600:
                    store.remove_job(d.name)
                    removed_dirs += 1
        missing = 0
        for job in s.scalars(select(Job).where(Job.status == "succeeded")).all():
            if not store.job_dir(str(job.id)).exists():
                job.status = "expired"
                missing += 1
    return {"removed_dirs": removed_dirs, "expired_without_files": missing}


def _settle_ai(session, r, job: Job) -> None:
    # Por la reserva y no por la clase de coste: imagen-a-excel reserva una petición y cuenta como tarea pesada (D-161).
    if (job.ai_reserved or 0) > (job.ai_used or 0):
        from core.ai.client import settle_job

        settle_job(session, r, get_settings(), job)
