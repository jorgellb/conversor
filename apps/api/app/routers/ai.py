"""IA (6.3 y 9.1): peticiones que quedan hoy y, para administración, modelos, presupuesto y lo que dice OpenRouter."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import current_admin, current_owner, db, locale_of, registry_dep, settings_dep, valkey_dep
from core.ai import budget
from core.ai.jobs import summary
from core.jobs import Owner, load_plan, utcnow
from core.models import AiRequest, AuditLog, LlmModel
from core.registry import Registry
from core.settings import Settings

router = APIRouter(prefix="/v1", tags=["ia"])

# Sustituible en pruebas: ejecuta la respuesta en el mismo proceso en lugar de encolarla en `workerai`.
CHAT_ENQUEUE = {"fn": None}
CHAT_IDLE_SECONDS = 180  # sin ningún evento del worker en este tiempo, el mensaje se da por perdido


@router.get("/ai/budget")
def ai_budget(owner: Owner = Depends(current_owner), session: Session = Depends(db, scope="function"), r=Depends(valkey_dep),
              settings: Settings = Depends(settings_dep), registry: Registry = Depends(registry_dep)):
    plan = load_plan(session, owner.plan_id, settings)
    return summary(session, r, settings, owner.type, owner.id, plan, registry.specs)


def _model_view(m: LlmModel, now: datetime) -> dict:
    return {
        "id": m.id, "context_length": m.context_length, "max_completion_tokens": m.max_completion_tokens,
        "supports_json": m.supports_json, "supports_images": m.supports_images, "enabled": m.enabled,
        "paused_until": m.disabled_until.isoformat() if m.disabled_until and m.disabled_until > now else None,
        "priority": m.priority, "success_rate_7d": m.success_rate_7d,
        "last_seen_at": m.last_seen_at.isoformat() if m.last_seen_at else None,
    }


@router.get("/admin/ai")
def admin_ai(_: Owner = Depends(current_admin), session: Session = Depends(db, scope="function"), r=Depends(valkey_dep),
             settings: Settings = Depends(settings_dep)):
    """6.2 y 6.3: modelos descubiertos, presupuesto del día, lo último de `/key` y peticiones por estado (24 h)."""
    now = utcnow()
    models = session.scalars(select(LlmModel).order_by(LlmModel.priority.nulls_last(), LlmModel.id)).all()
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    by_status = dict(session.execute(select(AiRequest.status, func.count()).where(AiRequest.created_at >= since)
                                     .group_by(AiRequest.status)).all())
    return {
        "models": [_model_view(m, now) for m in models],
        "preferred": settings.preferred_models,
        "fallback_router": settings.LLM_FALLBACK_ROUTER,
        "budget": budget.status(r, settings),
        "openrouter": budget.key_snapshot(r),
        "requests_today": by_status,
        "fake": settings.ai_fake,
    }


class ModelIn(BaseModel):
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    clear_priority: bool = False


@router.put("/admin/ai/models/{model_id:path}")
def admin_model(model_id: str, body: ModelIn, admin: Owner = Depends(current_admin), session: Session = Depends(db, scope="function")):
    """Desactivar o volver a activar un modelo y fijar su preferencia (menor, antes)."""
    from core.errors import AppError, ErrorCode

    row = session.get(LlmModel, model_id)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, status=404)
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.clear_priority:
        row.priority = None
    elif body.priority is not None:
        row.priority = body.priority
    session.add(AuditLog(actor=admin.email or admin.id, action="ai_model",
                         target=f"{model_id} enabled={row.enabled} priority={row.priority}"))
    return _model_view(row, utcnow())


# --- chat-pdf (9.1): la API no sale a internet; encola en workerai y retransmite lo que este publica en Valkey ---


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    job_id: str = Field(max_length=40)
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)
    ai_consent: bool | None = None


def _chat_job(session: Session, owner: Owner, job_id: str):
    from core.errors import AppError, ErrorCode
    from core.models import Job

    try:
        uuid.UUID(job_id)
    except ValueError as exc:
        raise AppError(ErrorCode.NOT_FOUND, status=404) from exc
    job = session.get(Job, job_id)
    if job is None or job.owner_type != owner.type or job.owner_id != owner.id or job.tool != "chat-pdf":
        raise AppError(ErrorCode.NOT_FOUND, status=404)
    if job.status != "succeeded" or job.expires_at <= utcnow():
        raise AppError(ErrorCode.NOT_FOUND, status=409, detail="chat_not_ready" if job.status in ("queued", "running") else "chat_expired")
    return job


def _doc_info(session: Session, owner: Owner, job_id: str) -> dict:
    from core.ai.store import cache_get, chat_doc_key
    from core.errors import AppError, ErrorCode

    info = cache_get(session, chat_doc_key(owner.type, owner.id, job_id), owner.type, owner.id, utcnow())
    if not info:
        raise AppError(ErrorCode.NOT_FOUND, status=409, detail="chat_expired")
    return info


@router.get("/ai/chat/{job_id}")
def chat_document(job_id: str, owner: Owner = Depends(current_owner), session: Session = Depends(db, scope="function")):
    """Documento preparado para el chat: páginas, si va entero o con búsqueda, y fragmentos."""
    job = _chat_job(session, owner, job_id)
    info = _doc_info(session, owner, job_id)
    return {"job_id": job_id, "name": info["name"], "pages": [p + 1 for p in info["pages"]], "tokens": info["tokens"],
            "chunks": info["chunks"], "expires_at": job.expires_at.isoformat()}


@router.post("/ai/chat")
async def chat(body: ChatIn, request: Request, owner: Owner = Depends(current_owner), session: Session = Depends(db, scope="function"),
               r=Depends(valkey_dep), settings: Settings = Depends(settings_dep), registry: Registry = Depends(registry_dep)):
    """Una pregunta = una petición (6.3). Reserva antes de encolar; el worker devuelve lo que no use."""
    from core.ai import CONSENT_VERSION, catalog, quota
    from core.ai.jobs import needs_of
    from core.ai.store import record_consent
    from core.ai.store import chat_stream_key
    from core.errors import AppError, ErrorCode

    def reserve() -> tuple[str, str]:
        plan = load_plan(session, owner.plan_id, settings)
        if plan.ai_requests_day <= 0:
            raise AppError(ErrorCode.UNAUTHORIZED if owner.type == "anon" else ErrorCode.QUOTA_EXCEEDED,
                           status=401 if owner.type == "anon" else 429, detail="ai_account", extra={"cost_class": "ai"})
        _chat_job(session, owner, body.job_id)
        info = _doc_info(session, owner, body.job_id)
        if settings.ai_consent_required and not body.ai_consent:
            raise AppError(ErrorCode.AI_CONSENT_REQUIRED, status=400, extra={"consent_version": CONSENT_VERSION})
        if body.ai_consent:
            record_consent(session, owner.type, owner.id, CONSENT_VERSION, quota.ai_day(settings))
        if not catalog.available(session, settings, needs_of(registry.require("chat-pdf"))):
            raise AppError(ErrorCode.AI_UNAVAILABLE, status=503)
        quota.reserve(session, settings, owner.type, owner.id, plan, 1)
        if not budget.reserve(r, settings, 1, plan.id == "pro"):
            raise AppError(ErrorCode.AI_BUDGET_EXHAUSTED, status=429, extra={"reset": budget.reset_local(settings),
                                                                               "reset_at": budget.reset_at(settings).isoformat()})
        session.commit()  # la respuesta va por eventos: la reserva queda guardada antes de empezar
        return plan.id, str(uuid.uuid4()), bool(info.get("chunks"))

    plan_id, message_id, searched = await run_in_threadpool(reserve)
    locale = locale_of(request)
    args = [message_id, body.job_id, owner.type, owner.id, plan_id, body.message,
            [t.model_dump() for t in body.history], locale]
    # Un documento con fragmentos pasa antes por `workeraiembed` (búsqueda con el modelo de embeddings); uno corto va
    # entero y directo a `workerai`.
    name, queue = ("tools.ai.chat.retrieve", "ai.embed") if searched else ("tools.ai.chat.answer", "ai")
    try:
        if CHAT_ENQUEUE["fn"] is not None:
            await run_in_threadpool(CHAT_ENQUEUE["fn"], name, args, queue)
        else:
            from core.celeryapp import celery_app

            celery_app.send_task(name, args=args, queue=queue, priority=0 if plan_id == "pro" else 5)
    except Exception:
        def undo() -> None:
            quota.release(session, settings, owner.type, owner.id, 1)
            session.commit()
            budget.release(r, settings, 1)

        await run_in_threadpool(undo)
        raise
    key = chat_stream_key(message_id)

    async def events():
        last = "0-0"
        idle = 0.0
        yield f"event: start\ndata: {json.dumps({'id': message_id})}\n\n"
        while True:
            if await request.is_disconnected():
                return
            batch = await run_in_threadpool(r.xread, {key: last}, 50, 1000)
            if not batch:
                idle += 1.0
                if idle >= CHAT_IDLE_SECONDS:
                    from core.errors import message as err_message

                    yield ("event: error\ndata: " + json.dumps({"type": "error", "code": "TIMEOUT",
                                                               "message": err_message("TIMEOUT", locale)}) + "\n\n")
                    return
                if idle % 15 == 0:
                    yield ": latido\n\n"
                continue
            idle = 0.0
            for _stream, entries in batch:
                for entry_id, fields in entries:
                    last = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                    raw = fields.get(b"e") or fields.get("e")
                    event = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event["type"] in ("done", "error"):
                        return
            await asyncio.sleep(0)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
