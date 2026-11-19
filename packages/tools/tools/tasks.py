"""Tarea genérica de los workers: ejecuta una herramienta sobre un trabajo (5.3)."""
from __future__ import annotations

import logging
import os
import shutil
from datetime import date
import threading
import time
from pathlib import Path

from billiard.exceptions import SoftTimeLimitExceeded
from celery.signals import worker_init, worker_process_init

from core import disk, queueguard, quotas
from core.celeryapp import celery_app
from core.db import session_scope
from core.envguard import harden_process
from core.errors import AppError, ErrorCode, ToolError
from core.jobs import MAX_ATTEMPTS, complete, fail, heartbeat, load_plan, start_attempt
from core.models import Job
from core.registry import load_impl, load_registry
from core.secretbox import open_sealed
from core.settings import get_settings
from core.storage import Store
from core.valkey import get_valkey
from tools.base import Handoff, InputFile, ToolContext, describe_output

log = logging.getLogger("worker")
HEARTBEAT_SECONDS = 30


@worker_process_init.connect
def _harden(**_kwargs) -> None:
    harden_process()


class _Heartbeat(threading.Thread):
    def __init__(self, job_id: str):
        super().__init__(daemon=True)
        self.job_id = job_id
        self.stop_event = threading.Event()
        self.progress: float | None = None
        self.message: str | None = None

    def run(self) -> None:
        while not self.stop_event.wait(HEARTBEAT_SECONDS):
            self.flush()

    def flush(self) -> None:
        try:
            with session_scope() as s:
                heartbeat(s, self.job_id, self.progress, self.message)
        except Exception:  # noqa: BLE001 - un latido fallido no debe tumbar el trabajo
            log.warning("latido fallido", extra={"job_id": self.job_id})


def execute(job_id: str, attempt: int, sealed: str = "") -> str:
    """Lógica del trabajo, separada de Celery para poder probarla de forma síncrona."""
    settings = get_settings()
    r = get_valkey()
    registry = load_registry()
    with session_scope() as s:
        if not start_attempt(s, job_id, attempt):
            return "descartado"
        job = s.get(Job, job_id)
        spec = registry.require(job.tool)
        plan = load_plan(s, "anon" if job.owner_type == "anon" else _plan_of(s, job), settings)
        inputs = [InputFile(Path(i.path), i.name, i.ext, i.size, i.sha256) for i in job.inputs]
        options = spec.options.model_validate(job.options)
        queue = job.queue
        locale = job.locale or "es"
        owner = (job.owner_type, job.owner_id)
        stage = job.stage
        expires_at = job.expires_at
        ai_state = (job.ai_reserved or 0, job.ai_used or 0, job.created_at)
        priority = job.priority
    queueguard.on_start(r, queue)
    store = Store(settings.FILESTORE_PATH)
    store.ensure_job_dirs(job_id)
    work = store.work_dir(job_id)
    hb = _Heartbeat(job_id)
    hb.start()

    def report(progress: float, message: str | None = None) -> None:
        hb.progress, hb.message = progress, message

    def charge(cost_class: str) -> None:
        """Tarea extra para el dueño cuando la herramienta descubre que hace un trabajo más caro (A.9)."""
        try:
            with session_scope() as s:
                quotas.count_task(s, [owner], plan, cost_class)
        except AppError as exc:
            raise ToolError(ErrorCode.QUOTA_EXCEEDED, f"sin tareas {cost_class}") from exc

    ctx = ToolContext(
        job_id=job_id, tool=spec.slug_es, inputs=inputs, work=work, out=store.out_dir(job_id),
        options=options, secrets=open_sealed(settings.JOB_SECRETS_KEY, sealed) if sealed else {},
        plan=plan, settings=settings, store=store, threads=int(os.environ.get("THREADS", settings.THREADS)), locale=locale,
        report=report, charge=charge, owner=owner, expires_at=expires_at, stage=stage, home_queue=spec.queue,
    )
    ai_budget = None
    if spec.ai is not None and spec.ai.used_by(options.model_dump()):
        ai_budget, ctx.ai = _ai_client(settings, r, spec, owner, plan, job_id, ai_state)
    started = time.monotonic()
    result = "ok"
    try:
        outputs = load_impl(spec)(ctx)
        described = [describe_output(Path(o["path"]), o.get("name"), o.get("note")) for o in outputs]
        with session_scope() as s:
            complete(s, job_id, described)
    except Handoff as step:
        # Sigue en otra cola con un intento nuevo: el intento no se pierde por cambiar de etapa.
        with session_scope() as s:
            s.query(Job).filter(Job.id == job_id, Job.status == "running").update({
                "status": "queued", "attempts": 0, "queue": step.queue, "worker_group": step.group, "stage": step.stage,
                "message": step.message}, synchronize_session=False)
        celery_app.send_task("tools.tasks.run_job", args=[job_id, 1, sealed if step.keep_secrets else ""], queue=step.queue,
                             priority=priority,
                             soft_time_limit=spec.time_limit, time_limit=spec.time_limit + 60)
        queueguard.on_enqueue(r, step.queue)
        result = "etapa"
    except SoftTimeLimitExceeded:
        with session_scope() as s:
            fail(s, job_id, ErrorCode.TIMEOUT)
        result = "timeout"
    except ToolError as exc:
        if exc.transient and attempt < MAX_ATTEMPTS:
            with session_scope() as s:
                s.query(Job).filter(Job.id == job_id).update({"status": "queued"})
            # El sobre cifrado viaja igual que en el primer envío: nunca hay secretos en claro en Valkey.
            celery_app.send_task("tools.tasks.run_job", args=[job_id, attempt + 1, sealed], queue=queue,
                                 countdown=10 * attempt, soft_time_limit=spec.time_limit, time_limit=spec.time_limit + 60)
            result = "reintento"
        else:
            with session_scope() as s:
                fail(s, job_id, exc.code, exc.detail)
            result = exc.code
    except Exception:  # noqa: BLE001
        log.exception("fallo inesperado", extra={"job_id": job_id, "tool": spec.slug_es})
        with session_scope() as s:
            fail(s, job_id, ErrorCode.INTERNAL)
        result = "error"
    finally:
        hb.stop_event.set()
        shutil.rmtree(work, ignore_errors=True)
        if result != "etapa":
            disk.release(r, f"job:{job_id}")
        if ai_budget is not None and result not in ("etapa", "reintento"):
            try:
                ai_budget.settle()
            except Exception:  # noqa: BLE001 - devolver la reserva no debe tapar el resultado
                log.exception("no se ha podido devolver la reserva de IA", extra={"job_id": job_id})
        queueguard.on_finish(r, queue, time.monotonic() - started)
    return result


def _ai_client(settings, r, spec, owner, plan, job_id: str, state):
    """Presupuesto del trabajo y cliente de IA (6.3): sigue la reserva hecha al encolar."""
    from core.ai.budget import budget_day
    from core.ai.client import AIClient, JobBudget

    reserved, used, created = state
    day = budget_day(settings, created) if created else None
    budget = JobBudget(settings=settings, r=r, owner_type=owner[0], owner_id=owner[1], plan=plan, reserved=reserved,
                       used=used, job_id=job_id, day=date.fromisoformat(day) if day else None)
    return budget, AIClient(settings=settings, r=r, tool=spec.slug_es, category=spec.category, budget=budget)


def _plan_of(session, job: Job) -> str:
    from core.models import Profile

    profile = session.get(Profile, job.owner_id)
    return profile.plan_id if profile else "free"


@celery_app.task(name="tools.tasks.run_job", acks_late=True)
def run_job(job_id: str, attempt: int, sealed: str = "") -> str:
    return execute(job_id, attempt, sealed)


@worker_init.connect
def _check_secrets(**_kwargs) -> None:
    """Matriz de secretos (12.1): un worker que ve variables que no le tocan no arranca."""
    import sys

    from core.envguard import violations

    role = os.environ.get("SERVICE_ROLE", "")
    extra = violations(role) if role else []
    if extra and os.environ.get("APP_ENV", "production") != "development":
        log.critical("variables no permitidas en %s: %s", role, ", ".join(extra))
        sys.exit(78)
