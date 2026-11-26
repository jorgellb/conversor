"""Pagos (9.1): checkout, portal y webhook idempotente."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.billing import FakePaymentProvider, get_provider
from app.deps import current_user, db, settings_dep
from core.errors import AppError, ErrorCode
from core.jobs import Owner
from core.settings import Settings

router = APIRouter(prefix="/v1/billing", tags=["pagos"])


class CheckoutIn(BaseModel):
    interval: str = "monthly"
    locale: str = "es"


@router.post("/checkout")
def checkout(body: CheckoutIn, owner: Owner = Depends(current_user), settings: Settings = Depends(settings_dep)):
    if body.interval not in ("monthly", "yearly"):
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422)
    result = get_provider(settings).checkout(owner.id, owner.email, body.interval, "en" if body.locale == "en" else "es")
    return {"url": result.url}


@router.post("/portal")
def portal(owner: Owner = Depends(current_user), settings: Settings = Depends(settings_dep)):
    return {"url": get_provider(settings).portal(owner.id, "es")}


@router.post("/webhook")
async def webhook(request: Request, session: Session = Depends(db, scope="function"), settings: Settings = Depends(settings_dep)):
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    provider = get_provider(settings)
    try:
        result = provider.handle_webhook(session, payload, signature)
    except Exception as exc:  # firma inválida o evento mal formado
        raise AppError(ErrorCode.FORBIDDEN, status=400, detail="Webhook no válido") from exc
    return {"received": result}


@router.get("/fake/complete")
def fake_complete(session: str, locale: str = "es", s: Session = Depends(db, scope="function"), settings: Settings = Depends(settings_dep)):
    provider = get_provider(settings)
    if not isinstance(provider, FakePaymentProvider):
        raise AppError(ErrorCode.NOT_FOUND, status=404)
    provider.complete(s, session)
    return RedirectResponse(f"{settings.PUBLIC_WEB_URL.rstrip('/')}/{'en' if locale == 'en' else 'es'}/cuenta?pago=ok", status_code=303)
