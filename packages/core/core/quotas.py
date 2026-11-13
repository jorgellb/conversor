"""Cuotas diarias por clase de coste (9.3). Anónimos: por token y por IP; manda la más restrictiva."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.errors import AppError, ErrorCode
from core.plans import PlanLimits


def today() -> date:
    return datetime.now(timezone.utc).date()


def count_task(session: Session, owners: list[tuple[str, str]], plan: PlanLimits, cost_class: str, day: date | None = None) -> None:
    """Suma una tarea a cada propietario y falla si alguno supera el límite.

    Usa una inserción con conflicto que incrementa de forma atómica; si se supera el límite,
    la excepción hace que la transacción del llamador se deshaga.
    """
    day = day or today()
    limit = plan.tasks_for(cost_class)
    for owner_type, owner_id in owners:
        row = session.execute(
            text(
                """
                INSERT INTO usage_daily (owner_type, owner_id, date, cost_class, tasks, ai_requests, mail_shares)
                VALUES (:t, :o, :d, :c, 1, 0, 0)
                ON CONFLICT (owner_type, owner_id, date, cost_class)
                DO UPDATE SET tasks = usage_daily.tasks + 1
                RETURNING tasks
                """
            ),
            {"t": owner_type, "o": owner_id, "d": day, "c": cost_class},
        ).one()
        if row.tasks > limit:
            raise AppError(ErrorCode.QUOTA_EXCEEDED, status=429, extra={"limit": limit, "cost_class": cost_class})


def usage(session: Session, owner_type: str, owner_id: str, day: date | None = None) -> dict[str, int]:
    day = day or today()
    rows = session.execute(
        text("SELECT cost_class, tasks FROM usage_daily WHERE owner_type=:t AND owner_id=:o AND date=:d"),
        {"t": owner_type, "o": owner_id, "d": day},
    ).all()
    return {r.cost_class: r.tasks for r in rows}


def count_mail_share(session: Session, owner_id: str, limit: int, day: date | None = None) -> int:
    """Suma un envío por correo (8.2.4) del usuario y falla si supera `MAIL_SHARE_DAILY_LIMIT`."""
    row = session.execute(
        text(
            """
            INSERT INTO usage_daily (owner_type, owner_id, date, cost_class, tasks, ai_requests, mail_shares)
            VALUES ('user', :o, :d, 'mail', 0, 0, 1)
            ON CONFLICT (owner_type, owner_id, date, cost_class)
            DO UPDATE SET mail_shares = usage_daily.mail_shares + 1
            RETURNING mail_shares
            """
        ),
        {"o": owner_id, "d": day or today()},
    ).one()
    if row.mail_shares > limit:
        raise AppError(ErrorCode.QUOTA_EXCEEDED, status=429, extra={"limit": limit, "cost_class": "mail"})
    return row.mail_shares
