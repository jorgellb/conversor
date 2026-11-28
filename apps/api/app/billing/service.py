"""Pedidos, pases y devoluciones (D-273). Todo lo que cambia el estado de un pedido bloquea antes su fila: el navegador
(captura) y el aviso de PayPal (webhook) pueden llegar a la vez y el pase y la factura se dan una sola vez."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.errors import AppError, ErrorCode
from core.jobs import Owner
from core.models import Invoice, Order, Pass, PaymentEvent, Profile
from core.settings import Settings

from . import Capture, PaymentProvider, price
from . import invoices as inv

log = logging.getLogger("conversor.billing")
ORDERS_PER_HOUR = 20


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def describe(hours: int, locale: str) -> str:
    return f"{hours}-hour pass" if locale == "en" else f"Pase de {hours} horas"


def create_order(session: Session, settings: Settings, provider: PaymentProvider, owner: Owner, locale: str) -> Order:
    if not owner.email_verified:
        raise AppError(ErrorCode.FORBIDDEN, status=403, detail="email_unverified")
    if settings.APP_ENV == "production" and not settings.INVOICE_ISSUER_TAX_ID:
        # Sin emisor no hay factura válida: no se cobra.
        raise AppError(ErrorCode.PAYMENT_FAILED, status=503, detail="issuer_not_configured")
    recent = session.scalar(select(func.count()).select_from(Order).where(
        Order.user_id == owner.id, Order.created_at > utcnow() - timedelta(hours=1)))
    if recent >= ORDERS_PER_HOUR:
        raise AppError(ErrorCode.RATE_LIMITED, status=429)
    p = price(settings)
    order = Order(id=uuid.uuid4(), user_id=owner.id, email=owner.email or "", hours=p.hours, currency=p.currency,
                  total_cents=p.total_cents, base_cents=p.base_cents, vat_cents=p.vat_cents, vat_rate_bp=p.vat_rate_bp,
                  provider=provider.name, locale=locale, waiver_at=utcnow())
    session.add(order)
    session.flush()
    order.provider_order_id = provider.create_order(str(order.id), p, describe(p.hours, locale), locale)
    session.flush()
    return order


def _lock(session: Session, **where) -> Order | None:
    q = select(Order).with_for_update()
    for key, value in where.items():
        q = q.where(getattr(Order, key) == value)
    return session.execute(q).scalar_one_or_none()


def grant_pass(session: Session, order: Order) -> Pass:
    profile = session.execute(select(Profile).where(Profile.user_id == order.user_id).with_for_update()).scalar_one_or_none()
    if profile is None:
        profile = Profile(user_id=order.user_id, plan_id="free", locale=order.locale)
        session.add(profile)
        session.flush()
    now = utcnow()
    # Un pase comprado con otro activo empieza cuando acaba el anterior: no se pierden horas.
    start = profile.pass_until if profile.pass_until and profile.pass_until > now else now
    p = Pass(user_id=order.user_id, order_id=order.id, starts_at=start, expires_at=start + timedelta(hours=order.hours))
    session.add(p)
    profile.pass_until = p.expires_at
    session.flush()
    return p


def _recompute_pass(session: Session, user_id: str) -> None:
    profile = session.execute(select(Profile).where(Profile.user_id == user_id).with_for_update()).scalar_one_or_none()
    if profile is None:
        return
    # Los pases que quedan se vuelven a encadenar sin el devuelto: el que está en curso sigue igual y los siguientes
    # empiezan al acabar el anterior, con su misma duración.
    now = utcnow()
    passes = session.scalars(select(Pass).where(Pass.user_id == user_id, Pass.revoked_at.is_(None),
                                                Pass.expires_at > now).order_by(Pass.starts_at)).all()
    cursor = now
    for p in passes:
        if p.starts_at <= now:
            cursor = max(cursor, p.expires_at)
            continue
        length = p.expires_at - p.starts_at
        p.starts_at = cursor
        p.expires_at = cursor + length
        cursor = p.expires_at
    profile.pass_until = cursor if passes else None
    session.flush()


def fulfill(session: Session, settings: Settings, order: Order, capture: Capture) -> str:
    """Da el pase y emite la factura si PayPal confirma el cobro del importe exacto. Devuelve el estado del pedido."""
    if order.status in ("paid", "refunded"):
        return order.status
    if capture.status != "COMPLETED":
        if capture.status in ("DECLINED", "FAILED"):
            order.status = "failed"
        if capture.capture_id:
            order.provider_capture_id = capture.capture_id
        return "pending" if order.status == "created" else order.status
    if capture.amount_cents != order.total_cents or capture.currency != order.currency or (
            capture.custom_id and capture.custom_id != str(order.id)):
        log.error("Cobro que no cuadra con el pedido %s: %s %s", order.id, capture.amount_cents, capture.currency)
        raise AppError(ErrorCode.PAYMENT_FAILED, status=409, detail="amount_mismatch")
    order.status = "paid"
    order.paid_at = utcnow()
    order.provider_capture_id = capture.capture_id
    order.payer_email = capture.payer_email
    session.flush()
    grant_pass(session, order)
    inv.issue(session, settings, order)
    return "paid"


def capture_order(session: Session, settings: Settings, provider: PaymentProvider, owner: Owner, order_id: str) -> Order:
    try:
        oid = uuid.UUID(order_id)
    except ValueError as exc:
        raise AppError(ErrorCode.NOT_FOUND, status=404) from exc
    order = _lock(session, id=oid)
    if order is None or order.user_id != owner.id:
        raise AppError(ErrorCode.NOT_FOUND, status=404)
    if order.status == "created" and order.provider_order_id:
        fulfill(session, settings, order, provider.capture(order.provider_order_id, str(order.id)))
    return order


def refund(session: Session, settings: Settings, provider: PaymentProvider | None, order: Order) -> Invoice | None:
    """Devolución completa: PayPal devuelve el dinero (si `provider`), el pase se retira y se emite la rectificativa."""
    if order.status != "paid":
        return None
    if provider is not None and order.provider_capture_id:
        provider.refund(order.provider_capture_id, str(order.id), price(settings))
    order.status = "refunded"
    order.refunded_at = utcnow()
    p = session.scalar(select(Pass).where(Pass.order_id == order.id))
    if p is not None and p.revoked_at is None:
        p.revoked_at = utcnow()
        session.flush()
        _recompute_pass(session, order.user_id)
    original = session.scalar(select(Invoice).where(Invoice.order_id == order.id, Invoice.rectifies_id.is_(None)))
    if original is None:
        return None
    already = session.scalar(select(Invoice).where(Invoice.rectifies_id == original.id))
    return already or inv.issue(session, settings, order, rectifies=original)


def _capture_id_of(resource: dict) -> str | None:
    for link in resource.get("links") or []:
        if link.get("rel") == "up" and "/captures/" in link.get("href", ""):
            return link["href"].rstrip("/").rsplit("/", 1)[-1]
    return None


def _is_partial(resource: dict, order: Order) -> bool:
    from . import _cents

    value = (resource.get("amount") or {}).get("value")
    return value is not None and abs(_cents(value)) < order.total_cents


def _unmatched(session: Session, kind: str) -> None:
    """Una devolución que no encuentra su pedido. Si hay un cobro en curso (la captura aún no ha guardado su id), se
    responde 503 para que PayPal la repita y no quede apuntada como procesada; si no, se registra y se ignora."""
    recent = utcnow() - timedelta(hours=24)
    if session.scalar(select(Order.id).where(Order.status == "created", Order.provider_order_id.is_not(None),
                                             Order.created_at >= recent).limit(1)) is not None:
        raise AppError(ErrorCode.INTERNAL, status=503, detail="order_not_ready")
    log.warning("Aviso %s de PayPal sin pedido", kind)


def handle_event(session: Session, settings: Settings, provider: PaymentProvider, event: dict) -> str:
    """Aviso de PayPal ya verificado. Idempotente por el id del evento."""
    event_id, kind = str(event.get("id", "")), str(event.get("event_type", ""))
    if not event_id:
        raise AppError(ErrorCode.INVALID_OPTIONS, status=400)
    if session.get(PaymentEvent, event_id) is not None:
        return "duplicado"
    record = PaymentEvent(id=event_id, provider=provider.name, type=kind)
    session.add(record)
    session.flush()
    res = event.get("resource") or {}
    if kind == "PAYMENT.CAPTURE.COMPLETED":
        custom = res.get("custom_id")
        order = None
        if custom:
            try:
                order = _lock(session, id=uuid.UUID(custom))
            except ValueError:
                order = None
        if order is None and res.get("id"):
            order = _lock(session, provider_capture_id=res["id"])
        if order is not None:
            amount = res.get("amount") or {}
            from . import _cents

            fulfill(session, settings, order, Capture(status="COMPLETED", capture_id=res.get("id"),
                                                      amount_cents=_cents(amount.get("value")),
                                                      currency=amount.get("currency_code", ""), custom_id=custom))
    elif kind in ("PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED"):
        # Los dos traen una devolución cuyo enlace «up» es la captura; por si alguna vez trae la captura, su id.
        capture_id = _capture_id_of(res) or res.get("id")
        order = _lock(session, provider_capture_id=capture_id) if capture_id else None
        if order is None:
            _unmatched(session, kind)
        elif kind == "PAYMENT.CAPTURE.REFUNDED" and _is_partial(res, order):
            # Una devolución parcial desde el panel de PayPal no retira el pase ni emite una rectificativa por el total:
            # el titular la tiene que regularizar a mano (OPERATIONS.md). Las devoluciones se hacen desde /admin.
            log.error("Devolución parcial en PayPal del pedido %s: revisar a mano", order.id)
        else:
            refund(session, settings, None, order)
    elif kind == "PAYMENT.CAPTURE.DENIED":
        order = _lock(session, provider_capture_id=res.get("id")) if res.get("id") else None
        if order is not None and order.status == "created":
            order.status = "failed"
    record.processed_at = utcnow()
    return kind


def order_json(o: Order) -> dict:
    return {"id": str(o.id), "status": o.status, "product": o.product, "hours": o.hours, "total_cents": o.total_cents,
            "currency": o.currency, "created_at": o.created_at.isoformat() if o.created_at else None,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            "refunded_at": o.refunded_at.isoformat() if o.refunded_at else None}


def invoice_json(i: Invoice) -> dict:
    return {"id": str(i.id), "number": i.number, "kind": i.kind, "order_id": str(i.order_id),
            "issued_at": i.issued_at.isoformat(), "total_cents": i.total_cents, "base_cents": i.base_cents,
            "vat_cents": i.vat_cents, "currency": i.currency, "rectifies_id": str(i.rectifies_id) if i.rectifies_id else None}


def receipt_mail(settings: Settings, order: Order) -> None:
    """Correo de confirmación con el enlace a las facturas de la cuenta. Si falla, el pago sigue siendo válido."""
    from core.external import send_mail

    to = order.email or order.payer_email
    if not to:
        return
    base = settings.PUBLIC_WEB_URL.rstrip("/")
    if order.locale == "en":
        subject = f"{settings.APP_NAME}: your {order.hours}-hour pass is active"
        body = (f"Thank you. Your pass is active: all the advanced tools for {order.hours} hours.\n\n"
                f"Your invoice is in your account: {base}/en/account#invoices\n")
    else:
        subject = f"{settings.APP_NAME}: tu pase de {order.hours} horas está activo"
        body = (f"Gracias. Tu pase ya está activo: todas las herramientas avanzadas durante {order.hours} horas.\n\n"
                f"Tienes la factura en tu cuenta: {base}/es/cuenta#facturas\n")
    try:
        send_mail(settings.SMTP_URL, settings.MAIL_FROM, [to], subject, body)
    except Exception:  # noqa: BLE001 — el correo es una cortesía
        log.warning("No se pudo enviar el recibo del pedido %s", order.id)


def parse_event(body: bytes) -> dict:
    try:
        event = json.loads(body)
    except ValueError as exc:
        raise AppError(ErrorCode.INVALID_OPTIONS, status=400) from exc
    if not isinstance(event, dict):
        raise AppError(ErrorCode.INVALID_OPTIONS, status=400)
    return event
