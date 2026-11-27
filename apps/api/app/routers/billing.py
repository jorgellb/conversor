"""Pagos (D-273): pase de 24 h con PayPal, pedidos, facturas y datos fiscales de la cuenta."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing import get_provider, price
from app.billing import invoices as inv
from app.billing import service
from app.deps import current_user, db, settings_dep
from core.errors import AppError, ErrorCode
from core.jobs import Owner
from core.models import BillingProfile, Invoice, Order, Profile
from core.settings import Settings
from core.taxid import nif_ok, normalize

router = APIRouter(prefix="/v1/billing", tags=["pagos"])


@router.get("/config")
def config(settings: Settings = Depends(settings_dep)):
    """Lo que necesita la página de pago: proveedor, cliente público de PayPal y precio."""
    p = price(settings)
    return {"provider": "paypal" if settings.PAYMENT_PROVIDER == "paypal" else "fake",
            "client_id": settings.PAYPAL_CLIENT_ID if settings.PAYMENT_PROVIDER == "paypal" else "",
            "env": settings.PAYPAL_ENV, "currency": p.currency, "price_cents": p.total_cents, "base_cents": p.base_cents,
            "vat_cents": p.vat_cents, "vat_rate_bp": p.vat_rate_bp, "hours": p.hours, "required": settings.PASS_REQUIRED}


@router.get("/pass")
def my_pass(owner: Owner = Depends(current_user), session: Session = Depends(db, scope="function")):
    profile = session.get(Profile, owner.id)
    until = profile.pass_until if profile else None
    active = bool(until and until > datetime.now(timezone.utc))
    return {"active": active or owner.is_pro, "expires_at": until.isoformat() if active else None,
            "unlimited": owner.is_pro and not active}


class OrderIn(BaseModel):
    locale: str = "es"
    # Contenido digital con ejecución inmediata: el comprador consiente y pierde el desistimiento (art. 103.m TRLGDCU).
    waiver: bool = False


@router.post("/orders")
def create_order(body: OrderIn, owner: Owner = Depends(current_user), session: Session = Depends(db, scope="function"),
                 settings: Settings = Depends(settings_dep)):
    if not body.waiver:
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422, detail="waiver_required")
    order = service.create_order(session, settings, get_provider(settings), owner, "en" if body.locale == "en" else "es")
    return {"order_id": str(order.id), "provider_order_id": order.provider_order_id}


@router.post("/orders/{order_id}/capture")
def capture(order_id: str, owner: Owner = Depends(current_user), session: Session = Depends(db, scope="function"),
            settings: Settings = Depends(settings_dep)):
    order = service.capture_order(session, settings, get_provider(settings), owner, order_id)
    profile = session.get(Profile, owner.id)
    if order.status == "paid":
        session.commit()  # el pase queda guardado antes del correo
        service.receipt_mail(settings, order)
    return {"status": order.status if order.status != "created" else "pending",
            "pass_until": profile.pass_until.isoformat() if profile and profile.pass_until else None}


@router.get("/orders")
def my_orders(owner: Owner = Depends(current_user), session: Session = Depends(db, scope="function")):
    rows = session.scalars(select(Order).where(Order.user_id == owner.id, Order.status != "created")
                           .order_by(Order.created_at.desc()).limit(200)).all()
    return {"orders": [service.order_json(o) for o in rows]}


@router.get("/invoices")
def my_invoices(owner: Owner = Depends(current_user), session: Session = Depends(db, scope="function")):
    rows = session.scalars(select(Invoice).where(Invoice.user_id == owner.id).order_by(Invoice.seq.desc()).limit(200)).all()
    return {"invoices": [service.invoice_json(i) for i in rows]}


@router.get("/invoices/{invoice_id}/pdf")
def invoice_pdf(invoice_id: str, owner: Owner = Depends(current_user), session: Session = Depends(db, scope="function"),
                settings: Settings = Depends(settings_dep)):
    try:
        iid = uuid.UUID(invoice_id)
    except ValueError as exc:
        raise AppError(ErrorCode.NOT_FOUND, status=404) from exc
    row = session.get(Invoice, iid)
    if row is None or (row.user_id != owner.id and not owner.is_admin):
        raise AppError(ErrorCode.NOT_FOUND, status=404)
    rectified = session.get(Invoice, row.rectifies_id).number if row.rectifies_id else None
    pdf = inv.render_pdf(settings, row, rectified)
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{row.number}.pdf"', "Cache-Control": "private, no-store"})


class BillingProfileIn(BaseModel):
    name: str = Field(default="", max_length=200)
    tax_id: str = Field(default="", max_length=32)
    address: str = Field(default="", max_length=300)
    postal_code: str = Field(default="", max_length=16)
    city: str = Field(default="", max_length=120)
    country: str = Field(default="ES", min_length=2, max_length=2)


def _profile_json(bp: BillingProfile | None) -> dict:
    if bp is None:
        return {"name": "", "tax_id": "", "address": "", "postal_code": "", "city": "", "country": "ES", "complete": False}
    return {"name": bp.name, "tax_id": bp.tax_id, "address": bp.address, "postal_code": bp.postal_code, "city": bp.city,
            "country": bp.country, "complete": bool(bp.name.strip() and bp.tax_id.strip() and bp.address.strip())}


@router.get("/profile")
def get_profile(owner: Owner = Depends(current_user), session: Session = Depends(db, scope="function")):
    return _profile_json(session.get(BillingProfile, owner.id))


@router.put("/profile")
def put_profile(body: BillingProfileIn, owner: Owner = Depends(current_user), session: Session = Depends(db, scope="function")):
    country = body.country.upper()
    tax_id = normalize(body.tax_id)
    if tax_id and country == "ES" and not nif_ok(tax_id):
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422, detail="tax_id")
    bp = session.get(BillingProfile, owner.id) or BillingProfile(user_id=owner.id)
    bp.name, bp.tax_id, bp.address = body.name.strip(), tax_id, body.address.strip()
    bp.postal_code, bp.city, bp.country = body.postal_code.strip(), body.city.strip(), country
    session.add(bp)
    session.flush()
    return _profile_json(bp)


@router.post("/webhook")
async def webhook(request: Request, session: Session = Depends(db, scope="function"), settings: Settings = Depends(settings_dep)):
    from starlette.concurrency import run_in_threadpool

    body = await request.body()
    provider = get_provider(settings)
    headers = dict(request.headers)
    if not await run_in_threadpool(provider.verify_webhook, headers, body):
        raise AppError(ErrorCode.FORBIDDEN, status=400, detail="Webhook no válido")
    event = service.parse_event(body)
    result = await run_in_threadpool(service.handle_event, session, settings, provider, event)
    return {"received": result}
