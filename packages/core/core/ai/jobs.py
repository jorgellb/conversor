"""Lo que la API comprueba y reserva antes de encolar un trabajo de IA (6.3 y 6.6). La API no sale a internet."""
from __future__ import annotations

from sqlalchemy.orm import Session

from core.ai import CONSENT_VERSION, budget, catalog, quota
from core.ai.store import record_consent
from core.errors import AppError, ErrorCode
from core.plans import PlanLimits
from core.registry import ToolSpec
from core.settings import Settings


def needs_of(spec: ToolSpec) -> catalog.Needs:
    ai = spec.ai
    return catalog.Needs(ai.min_context, ai.min_output, ai.json, ai.images) if ai else catalog.Needs()


def prepare(session: Session, r, settings: Settings, spec: ToolSpec, owner_type: str, owner_id: str, plan: PlanLimits,
            options: dict, consent: bool | None) -> int:
    """Consentimiento, disponibilidad y reserva. Devuelve las peticiones reservadas (Valkey va lo último)."""
    if plan.ai_requests_day <= 0:
        # Anónimos: la IA necesita una cuenta (9.3: 0 peticiones al día).
        raise AppError(ErrorCode.UNAUTHORIZED if owner_type == "anon" else ErrorCode.QUOTA_EXCEEDED,
                       status=401 if owner_type == "anon" else 429, detail="ai_account", extra={"cost_class": "ai"})
    if settings.ai_consent_required and not consent:
        raise AppError(ErrorCode.AI_CONSENT_REQUIRED, status=400, extra={"consent_version": CONSENT_VERSION})
    if consent:
        record_consent(session, owner_type, owner_id, CONSENT_VERSION, quota.ai_day(settings))
    if not catalog.available(session, settings, needs_of(spec)):
        raise AppError(ErrorCode.AI_UNAVAILABLE, status=503)
    n = spec.ai.requests_for(options) if spec.ai else 1
    top = quota.per_task_limit(plan, settings)
    if n > top:
        raise AppError(ErrorCode.LIMIT_EXCEEDED, status=400, detail=f"ai_task:{n}>{top}", extra={"ai_requests": n, "max": top})
    quota.reserve(session, settings, owner_type, owner_id, plan, n)
    if not budget.reserve(r, settings, n, plan.id == "pro"):
        raise AppError(ErrorCode.AI_BUDGET_EXHAUSTED, status=429, extra={"reset": budget.reset_local(settings),
                                                                           "reset_at": budget.reset_at(settings).isoformat()})
    return n


def summary(session: Session, r, settings: Settings, owner_type: str, owner_id: str, plan: PlanLimits, specs: list[ToolSpec]) -> dict:
    """`GET /v1/ai/budget`: lo que le queda hoy al usuario, la disponibilidad global y qué herramientas tienen modelo."""
    state = budget.status(r, settings)
    pro = plan.id == "pro"
    used = quota.used_today(session, settings, owner_type, owner_id) if plan.ai_requests_day > 0 else 0
    mine = max(0, plan.ai_requests_day - used)
    global_left = state["remaining_pro"] if pro else state["remaining_free"]
    return {
        "user": {"used": used, "limit": plan.ai_requests_day, "remaining": min(mine, global_left)},
        "per_task": quota.per_task_limit(plan, settings) if plan.ai_requests_day > 0 else 0,
        "pages_per_task": plan.ai_pages_task,
        "available": global_left > 0,
        "pro_only": state["pro_only"],
        "reset_at": state["reset_at"],
        "reset_local": state["reset_local"],
        "consent_required": settings.ai_consent_required,
        "consent_version": CONSENT_VERSION,
        "tools": {s.slug_es: catalog.available(session, settings, needs_of(s)) for s in specs if s.ai is not None},
    }
