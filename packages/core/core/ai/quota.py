"""Peticiones de IA de cada usuario al día (9.3), en `usage_daily` (clase `ai`, columna `ai_requests`).

Se reservan al crear el trabajo y se devuelven las que no se usan al terminar; cuentan también los fallos y reintentos.
El día es el del presupuesto global (`AI_BUDGET_RESET_TZ`), para que los dos se reinicien a la vez.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.errors import AppError, ErrorCode
from core.plans import PlanLimits
from core.settings import Settings
from core.ai.budget import budget_day


def ai_day(settings: Settings) -> date:
    return date.fromisoformat(budget_day(settings))


def per_task_limit(plan: PlanLimits, settings: Settings) -> int:
    return min(plan.ai_requests_task, settings.AI_TASK_MAX_REQUESTS)


def reserve(session: Session, settings: Settings, owner_type: str, owner_id: str, plan: PlanLimits, n: int) -> int:
    """Suma `n` peticiones al día del usuario y lanza QUOTA_EXCEEDED si pasa de su plan (la transacción se deshace)."""
    row = session.execute(
        text(
            """
            INSERT INTO usage_daily (owner_type, owner_id, date, cost_class, tasks, ai_requests, mail_shares)
            VALUES (:t, :o, :d, 'ai', 0, :n, 0)
            ON CONFLICT (owner_type, owner_id, date, cost_class)
            DO UPDATE SET ai_requests = usage_daily.ai_requests + :n
            RETURNING ai_requests
            """
        ),
        {"t": owner_type, "o": owner_id, "d": ai_day(settings), "n": n},
    ).one()
    if row.ai_requests > plan.ai_requests_day:
        raise AppError(ErrorCode.QUOTA_EXCEEDED, status=429, extra={"limit": plan.ai_requests_day, "cost_class": "ai"})
    return row.ai_requests


def release(session: Session, settings: Settings, owner_type: str, owner_id: str, n: int, day: date | None = None) -> None:
    if n <= 0:
        return
    session.execute(
        text(
            """
            UPDATE usage_daily SET ai_requests = GREATEST(0, ai_requests - :n)
            WHERE owner_type = :t AND owner_id = :o AND date = :d AND cost_class = 'ai'
            """
        ),
        {"t": owner_type, "o": owner_id, "d": day or ai_day(settings), "n": n},
    )


def used_today(session: Session, settings: Settings, owner_type: str, owner_id: str) -> int:
    value = session.execute(
        text("SELECT ai_requests FROM usage_daily WHERE owner_type=:t AND owner_id=:o AND date=:d AND cost_class='ai'"),
        {"t": owner_type, "o": owner_id, "d": ai_day(settings)},
    ).scalar()
    return int(value or 0)
