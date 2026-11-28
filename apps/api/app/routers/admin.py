"""Panel de administración básico (8.1): colas, disco, flags, errores y purga."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import String, func, select
from sqlalchemy.orm import Session

from app.deps import current_admin, db, registry_dep, settings_dep, valkey_dep
from core import disk, queueguard
from core.flags import is_tool_enabled
from core.jobs import Owner, db_flags
from core.models import AuditLog, FeatureFlag, Job
from core.registry import Registry
from core.settings import Settings

router = APIRouter(prefix="/v1/admin", tags=["administración"])


def _cell(value: object) -> str:
    """Datos del cliente en el CSV: una celda que empieza por = + - @ o un tabulador se abre como fórmula en Excel."""
    text = str(value or "")
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def overview_data(session: Session, r, settings: Settings, registry: Registry) -> dict:
    from datetime import timedelta

    from core.jobs import utcnow

    st = disk.status(r, Path(settings.FILESTORE_PATH), settings.DISK_MAX_USAGE_PERCENT, settings.DISK_MIN_FREE_GB)
    queues = sorted({s.queue for s in registry.server_tools() if s.queue})
    by_status = dict(session.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    since = utcnow() - timedelta(hours=24)
    rows = session.execute(
        select(Job.tool, func.count(), func.count().filter(Job.status == "failed"))
        .where(Job.created_at >= since).group_by(Job.tool)
    ).all()
    errors = {tool: {"failed": failed, "total": total, "rate": round(failed / total, 3) if total else 0.0}
              for tool, total, failed in rows if failed}
    return {
        "disk": st.as_dict(),
        "queues": {q: {"wait_seconds": int(queueguard.estimated_wait(r, q, q.split(".")[0])),
                       "pending": int(r.get(f"q:{q}:pending") or 0)} for q in queues},
        "jobs_by_status": by_status,
        "errors_by_tool": dict(sorted(errors.items(), key=lambda kv: -kv[1]["rate"])),
        "flags": db_flags(session),
        # Apagadas por el entorno, un flag temático o `default_enabled=False` (D-134): una fila de feature_flags no las
        # enciende, así que el panel no ofrece encenderlas.
        "locked_off": sorted(s.slug_es for s in registry.specs
                             if not is_tool_enabled(s.slug_es, {s.slug_es: True}, default=s.default_enabled)),
        # Encendidas por TOOL_<SLUG>_ENABLED=true: el entorno gana a la fila, así que tampoco se pueden apagar desde aquí.
        "locked_on": sorted(s.slug_es for s in registry.specs
                            if is_tool_enabled(s.slug_es, {s.slug_es: False}, default=s.default_enabled)),
    }


@router.get("/overview")
def overview(_: Owner = Depends(current_admin), session: Session = Depends(db, scope="function"), r=Depends(valkey_dep),
             settings: Settings = Depends(settings_dep), registry: Registry = Depends(registry_dep)):
    return overview_data(session, r, settings, registry)


class FlagIn(BaseModel):
    enabled: bool


@router.put("/flags/{slug}")
def set_flag(slug: str, body: FlagIn, admin: Owner = Depends(current_admin), session: Session = Depends(db, scope="function"),
             registry: Registry = Depends(registry_dep)):
    spec = registry.require(slug)
    flag = session.get(FeatureFlag, spec.slug_es) or FeatureFlag(slug=spec.slug_es, plans=[])
    flag.enabled = body.enabled
    session.add(flag)
    session.add(AuditLog(actor=admin.email or admin.id, action="flag", target=f"{spec.slug_es}={body.enabled}"))
    return {"slug": spec.slug_es, "enabled": body.enabled}


@router.post("/purge")
def purge(admin: Owner = Depends(current_admin), session: Session = Depends(db, scope="function")):
    from core.maintenance import cleanup_expired

    session.add(AuditLog(actor=admin.email or admin.id, action="purge", target=None))
    return cleanup_expired()


# Pagos (D-273): ventas, pedidos, devoluciones y libro registro de facturas expedidas.
@router.get("/billing/summary")
def billing_summary(_: Owner = Depends(current_admin), session: Session = Depends(db, scope="function")):
    from datetime import datetime, timedelta, timezone

    from core.models import Invoice, Order, Profile

    now = datetime.now(timezone.utc)

    def sales(since: datetime) -> dict:
        paid = session.execute(select(func.count(), func.coalesce(func.sum(Order.total_cents), 0))
                               .where(Order.paid_at >= since, Order.status.in_(("paid", "refunded")))).one()
        refunded = session.execute(select(func.count(), func.coalesce(func.sum(Order.total_cents), 0))
                                   .where(Order.refunded_at >= since, Order.status == "refunded")).one()
        return {"orders": paid[0], "gross_cents": int(paid[1]), "refunds": refunded[0], "refunded_cents": int(refunded[1]),
                "net_cents": int(paid[1]) - int(refunded[1])}

    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "today": sales(day0), "last_7_days": sales(now - timedelta(days=7)), "last_30_days": sales(now - timedelta(days=30)),
        "active_passes": session.scalar(select(func.count()).select_from(Profile).where(Profile.pass_until > now)),
        "invoices": session.scalar(select(func.count()).select_from(Invoice)),
        "pending_orders": session.scalar(select(func.count()).select_from(Order).where(Order.status == "created",
                                                                                     Order.created_at > now - timedelta(days=1))),
    }


@router.get("/billing/orders")
def billing_orders(status: str | None = None, q: str | None = None, limit: int = 100,
                   _: Owner = Depends(current_admin), session: Session = Depends(db, scope="function")):
    from app.billing.service import order_json
    from core.models import Invoice, Order

    query = select(Order).order_by(Order.created_at.desc()).limit(max(1, min(limit, 500)))
    if status:
        query = query.where(Order.status == status)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.where(func.lower(Order.email).like(like) | func.lower(func.coalesce(Order.payer_email, "")).like(like)
                            | (func.cast(Order.id, String) == q.strip()) | (Order.provider_order_id == q.strip()))
    rows = session.scalars(query).all()
    numbers = {}
    if rows:
        for inv in session.scalars(select(Invoice).where(Invoice.order_id.in_([o.id for o in rows]))).all():
            numbers.setdefault(str(inv.order_id), []).append({"id": str(inv.id), "number": inv.number, "kind": inv.kind})
    return {"orders": [{**order_json(o), "email": o.email, "payer_email": o.payer_email, "user_id": o.user_id,
                        "provider_order_id": o.provider_order_id, "provider_capture_id": o.provider_capture_id,
                        "invoices": numbers.get(str(o.id), [])} for o in rows]}


@router.post("/billing/orders/{order_id}/refund")
def billing_refund(order_id: str, admin: Owner = Depends(current_admin), session: Session = Depends(db, scope="function"),
                   settings: Settings = Depends(settings_dep)):
    import uuid

    from app.billing import get_provider
    from app.billing import service
    from core.errors import AppError, ErrorCode
    from core.models import Order

    try:
        oid = uuid.UUID(order_id)
    except ValueError as exc:
        raise AppError(ErrorCode.NOT_FOUND, status=404) from exc
    order = session.execute(select(Order).where(Order.id == oid).with_for_update()).scalar_one_or_none()
    if order is None:
        raise AppError(ErrorCode.NOT_FOUND, status=404)
    if order.status != "paid":
        raise AppError(ErrorCode.INVALID_OPTIONS, status=409, detail="not_paid")
    rect = service.refund(session, settings, get_provider(settings), order)
    session.add(AuditLog(actor=admin.email or admin.id, action="refund", target=str(order.id)))
    return {"status": order.status, "rectifying_invoice": rect.number if rect else None}


@router.get("/billing/invoices.csv")
def billing_invoices_csv(start: str | None = None, end: str | None = None, _: Owner = Depends(current_admin),
                         session: Session = Depends(db, scope="function")):
    """Libro registro de facturas expedidas (para el modelo 303 y la gestoría): una fila por factura."""
    import csv
    import io
    from datetime import date, datetime, time, timezone
    from zoneinfo import ZoneInfo

    from fastapi.responses import Response

    from app.billing import money
    from core.errors import AppError, ErrorCode
    from core.models import Invoice

    tz = ZoneInfo("Europe/Madrid")
    query = select(Invoice).order_by(Invoice.seq)
    try:
        if start:
            query = query.where(Invoice.issued_at >= datetime.combine(date.fromisoformat(start), time.min, tz))
        if end:
            query = query.where(Invoice.issued_at <= datetime.combine(date.fromisoformat(end), time.max, tz))
    except ValueError as exc:
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422, detail="date") from exc
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Número", "Tipo", "Fecha", "Rectifica", "Cliente", "NIF cliente", "País", "Base", "Tipo IVA", "Cuota IVA",
                "Total", "Huella"])
    by_id = {}
    rows = session.scalars(query).all()
    for i in rows:
        by_id[i.id] = i.number
    for i in rows:
        rect = by_id.get(i.rectifies_id) or (session.get(Invoice, i.rectifies_id).number if i.rectifies_id else "")
        w.writerow([i.number, i.kind, f"{i.issued_at.astimezone(tz):%d/%m/%Y}", rect, _cell(i.buyer.get("name", "")),
                    _cell(i.buyer.get("tax_id", "")), _cell(i.buyer.get("country", "")), money(i.base_cents).replace(".", ","),
                    f"{i.vat_rate_bp / 100:g}".replace(".", ","), money(i.vat_cents).replace(".", ","),
                    money(i.total_cents).replace(".", ","), i.record_hash])
    data = "﻿" + out.getvalue()
    return Response(data, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="facturas-expedidas.csv"', "Cache-Control": "no-store"})
