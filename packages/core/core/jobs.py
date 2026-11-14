"""Ciclo de vida de los trabajos (5.1 y 5.3): creación, intentos, latidos y vista pública."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from core import disk, queueguard, quotas
from core.errors import AppError, ErrorCode
from core.filetype import Detected, family_of, matches
from core.flags import is_tool_enabled
from core.models import FeatureFlag, Job, JobInput, JobOutput, Plan, Upload
from core.plans import PlanLimits, load_plans_file
from core.registry import Registry, ToolSpec
from core.secretbox import seal
from core.settings import Settings
from core.storage import Store
from core.tokens import owner_key, sign_download

LIVE_STATUSES = ("queued", "running", "succeeded")
MAX_ATTEMPTS = 3


@dataclass
class Owner:
    type: str
    id: str
    plan_id: str
    is_admin: bool = False
    ip_hash: str | None = None
    email: str | None = None
    email_verified: bool = False

    @property
    def key(self) -> str:
        return owner_key(self.type, self.id)

    @property
    def is_pro(self) -> bool:
        return self.plan_id == "pro"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_plan(session: Session, plan_id: str, settings: Settings) -> PlanLimits:
    row = session.get(Plan, plan_id)
    if row is not None:
        return PlanLimits(name=row.name, id=plan_id, **{k: v for k, v in row.limits.items() if k not in ("name", "id")})
    return load_plans_file(settings.PLANS_FILE)[plan_id]


def db_flags(session: Session) -> dict[str, bool]:
    return {f.slug: f.enabled for f in session.scalars(select(FeatureFlag)).all()}


def ensure_enabled(session: Session, spec: ToolSpec) -> None:
    if not is_tool_enabled(spec.slug_es, db_flags(session), default=spec.default_enabled):
        raise AppError(ErrorCode.TOOL_DISABLED, status=403)


def canonical_options(options: dict) -> str:
    return json.dumps(options, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def idempotency_key(owner: Owner, tool: str, options: dict, input_hashes: list[str]) -> str:
    material = "|".join([owner.key, tool, canonical_options(options), *sorted(input_hashes)])
    return hashlib.sha256(material.encode()).hexdigest()


def validate_options(spec: ToolSpec, raw: dict | None) -> tuple[dict, dict]:
    """Valida contra el options_schema y separa los secretos (nunca se guardan en claro)."""
    try:
        model = spec.options.model_validate(raw or {})
    except ValidationError as exc:
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422, extra={"errors": json.loads(exc.json(include_url=False))}) from exc
    data = model.model_dump(mode="json")
    secrets = {k: data.pop(k) for k in spec.secret_fields if data.get(k)}
    for k in spec.secret_fields:
        data.pop(k, None)
    return data, secrets


def create_job(
    session: Session,
    r,
    settings: Settings,
    registry: Registry,
    owner: Owner,
    tool_slug: str,
    upload_ids: list[str],
    raw_options: dict | None,
    locale: str = "es",
    ai_consent: bool | None = None,
) -> tuple[Job, str, bool]:
    """Crea y deja listo para encolar un trabajo. Devuelve (trabajo, secretos sellados, reutilizado)."""
    spec = registry.require(tool_slug)
    if not spec.runs_on_server:
        raise AppError(ErrorCode.INVALID_OPTIONS, status=400, detail="Esta herramienta funciona en el navegador")
    ensure_enabled(session, spec)
    options, secrets = validate_options(spec, raw_options)
    plan = load_plan(session, owner.plan_id, settings)

    if spec.inputs and not upload_ids:
        raise AppError(ErrorCode.INVALID_OPTIONS, status=400, detail="Faltan archivos")
    if not spec.inputs and upload_ids:
        raise AppError(ErrorCode.INVALID_OPTIONS, status=400, detail="Esta herramienta no recibe archivos")
    max_files = min(plan.files_per_task, spec.max_files or plan.files_per_task)
    if len(upload_ids) > max_files:
        raise AppError(ErrorCode.TOO_MANY_FILES, status=400, extra={"max": max_files})

    uploads = session.scalars(select(Upload).where(Upload.id.in_(upload_ids)).with_for_update()).all()
    by_id = {u.id: u for u in uploads}
    ordered: list[Upload] = []
    for uid in upload_ids:
        up = by_id.get(uid)
        if up is None or up.owner_type != owner.type or up.owner_id != owner.id:
            raise AppError(ErrorCode.NOT_FOUND, status=404, detail="Subida no encontrada")
        if up.state == "rejected":
            raise AppError(ErrorCode.UNSUPPORTED_FORMAT, status=415)
        if up.state != "ready":
            raise AppError(ErrorCode.NOT_FOUND, status=409, detail="La subida no ha terminado")
        declared = Path(up.original_name).suffix
        detected = Detected(up.detected_ext or "", family_of(up.detected_ext or ""))
        if not matches(detected, declared, spec.inputs):
            raise AppError(ErrorCode.UNSUPPORTED_FORMAT, status=415)
        if up.size > plan.max_file_bytes:
            raise AppError(ErrorCode.FILE_TOO_LARGE, status=413)
        ordered.append(up)
    if sum(u.size for u in ordered) > plan.max_task_bytes:
        raise AppError(ErrorCode.FILE_TOO_LARGE, status=413, detail="Tamaño total por tarea")

    key = idempotency_key(owner, spec.slug_es, options, [u.sha256 or "" for u in ordered])
    existing = session.scalars(
        select(Job).where(Job.idempotency_key == key, Job.status.in_(LIVE_STATUSES), Job.expires_at > utcnow())
    ).first()
    store = Store(settings.FILESTORE_PATH)
    if existing is not None and (existing.status != "succeeded" or all(Path(o.path).exists() for o in existing.outputs)):
        for up in ordered:
            store.remove_upload(up.id)
            disk.release(r, up.id)
            session.delete(up)
        return existing, "", True
    if existing is not None:
        # Resultado borrado del disco: el trabajo antiguo deja de ocupar la clave de idempotencia.
        existing.status = "expired"
        session.flush()

    owners = [(owner.type, owner.id)]
    if owner.type == "anon" and owner.ip_hash:
        owners.append(("ip", owner.ip_hash))
    cost_class = spec.cost_for(options)
    quotas.count_task(session, owners, plan, cost_class)
    group, queue = spec.target(options)
    queueguard.check(r, queue, group, settings.queue_wait_limit(group), owner.is_pro)
    ai_reserved = 0
    if spec.ai is not None and spec.ai.used_by(options):
        from core.ai.jobs import prepare

        # Lo último antes de crear el trabajo: la reserva en Valkey no se deshace con la transacción (6.3).
        ai_reserved = prepare(session, r, settings, spec, owner.type, owner.id, plan, options, ai_consent, files=len(ordered))

    job = Job(
        id=uuid.uuid4(),
        owner_type=owner.type,
        owner_id=owner.id,
        tool=spec.slug_es,
        options=options,
        status="queued",
        worker_group=group,
        queue=queue,
        priority=plan.priority,
        cost_class=cost_class,
        idempotency_key=key,
        attempts=0,
        has_secrets=bool(secrets),
        locale="en" if locale == "en" else "es",
        expires_at=utcnow() + timedelta(hours=plan.retention_hours),
        ai_reserved=ai_reserved,
        ai_used=0,
    )
    session.add(job)
    session.flush()
    for i, up in enumerate(ordered):
        dst = store.move_upload_to_job(up.id, str(job.id), i, up.original_name)
        session.add(JobInput(job_id=job.id, position=i, name=up.original_name, path=str(dst), size=up.size,
                             mime=up.detected_mime or "application/octet-stream", ext=up.detected_ext or "",
                             sha256=up.sha256 or ""))
        up.state = "consumed"
    job.reserved_bytes = disk.transfer(r, [u.id for u in ordered], f"job:{job.id}")
    sealed = seal(settings.JOB_SECRETS_KEY, secrets) if secrets else ""
    return job, sealed, False


def enqueue(celery_app, r, job: Job, sealed: str, spec: ToolSpec) -> None:
    celery_app.send_task(
        "tools.tasks.run_job",
        args=[str(job.id), job.attempts + 1, sealed],
        queue=job.queue,
        priority=job.priority,
        soft_time_limit=spec.time_limit,
        time_limit=spec.time_limit + 60,
    )
    queueguard.on_enqueue(r, job.queue)


def start_attempt(session: Session, job_id: str, attempt: int) -> bool:
    """Marca el intento como en curso. Devuelve False si es un duplicado o un intento antiguo."""
    res = session.execute(
        text(
            """
            UPDATE jobs SET attempts = :a, status = 'running', heartbeat_at = now(),
                   started_at = COALESCE(started_at, now()), message = NULL
            WHERE id = :id AND attempts = :a - 1 AND status IN ('queued', 'running')
            """
        ),
        {"id": job_id, "a": attempt},
    )
    return res.rowcount == 1


def heartbeat(session: Session, job_id: str, progress: float | None = None, message: str | None = None) -> None:
    values: dict = {"heartbeat_at": utcnow()}
    if progress is not None:
        values["progress"] = max(0.0, min(1.0, progress))
    if message is not None:
        values["message"] = message[:300]
    session.execute(update(Job).where(Job.id == job_id, Job.status == "running").values(**values))


def complete(session: Session, job_id: str, outputs: list[dict]) -> None:
    job = session.get(Job, job_id)
    for i, o in enumerate(outputs):
        session.add(JobOutput(job_id=job.id, position=i, name=o["name"], filename=Path(o["path"]).name, path=str(o["path"]),
                              size=o["size"], mime=o["mime"], sha256=o["sha256"], note=o.get("note")))
    job.status = "succeeded"
    job.progress = 1.0
    job.finished_at = utcnow()


def fail(session: Session, job_id: str, code: str, message: str | None = None) -> None:
    session.execute(
        update(Job).where(Job.id == job_id).values(status="failed", error_code=code, finished_at=utcnow(), message=(message or "")[:300] or None)
    )


def _reset(code: str | None, settings: Settings) -> str | None:
    if code != ErrorCode.AI_BUDGET_EXHAUSTED:
        return None
    from core.ai.budget import reset_local

    return reset_local(settings)


def public_view(job: Job, settings: Settings, locale: str = "es") -> dict:
    from core.errors import message as err_message

    owner = owner_key(job.owner_type, job.owner_id)
    ttl = settings.DOWNLOAD_TOKEN_MINUTES * 60
    outputs = []
    if job.status == "succeeded":
        for o in job.outputs:
            token = sign_download(settings.FILE_TOKEN_SECRET, str(job.id), o.filename, owner, ttl)
            outputs.append({
                "name": o.name,
                "size": o.size,
                "mime": o.mime,
                "note": o.note,
                "url": f"{settings.PUBLIC_FILES_URL.rstrip('/')}/d/{job.id}/{o.filename}?t={token}",
                "url_expires_in": ttl,
            })
    return {
        "id": str(job.id),
        "tool": job.tool,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "error": {"code": job.error_code, "message": err_message(job.error_code, locale, job.message, _reset(job.error_code, settings))}
        if job.error_code else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
        "inputs": [{"name": i.name, "size": i.size} for i in job.inputs],
        "outputs": outputs,
    }
