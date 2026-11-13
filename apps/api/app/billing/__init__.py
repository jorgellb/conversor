"""Pagos detrás de la interfaz PaymentProvider (decisión 6: Stripe en modo test)."""
from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.models import Profile, StripeEvent, Subscription
from core.settings import Settings


@dataclass
class CheckoutResult:
    url: str
    session_id: str


class PaymentProvider(ABC):
    name = "abstract"

    @abstractmethod
    def checkout(self, user_id: str, email: str | None, interval: str, locale: str) -> CheckoutResult: ...

    @abstractmethod
    def portal(self, user_id: str, locale: str) -> str: ...

    @abstractmethod
    def handle_webhook(self, session: Session, payload: bytes, signature: str) -> str: ...


def set_plan(session: Session, user_id: str, plan_id: str, status: str, customer: str | None = None,
             subscription: str | None = None, period_end: datetime | None = None, provider: str = "stripe") -> None:
    profile = session.get(Profile, user_id) or Profile(user_id=user_id, plan_id="free", locale="es")
    profile.plan_id = plan_id
    session.add(profile)
    sub = session.get(Subscription, user_id) or Subscription(user_id=user_id)
    sub.provider = provider
    sub.status = status
    sub.stripe_customer_id = customer or sub.stripe_customer_id
    sub.stripe_subscription_id = subscription or sub.stripe_subscription_id
    sub.current_period_end = period_end
    session.add(sub)


class FakePaymentProvider(PaymentProvider):
    """Doble de desarrollo y CI (0.1): el pago se completa con una URL local, sin red."""

    name = "fake"

    def __init__(self, settings: Settings):
        self.settings = settings

    def _r(self):
        from core.valkey import get_valkey

        return get_valkey()

    def checkout(self, user_id, email, interval, locale):
        sid = "fake_" + uuid.uuid4().hex
        self._r().set(f"fakepay:{sid}", user_id, ex=3600)
        url = f"{self.settings.PUBLIC_API_URL.rstrip('/')}/v1/billing/fake/complete?session={sid}&locale={locale}"
        return CheckoutResult(url=url, session_id=sid)

    def complete(self, session: Session, sid: str) -> str | None:
        user_id = self._r().getdel(f"fakepay:{sid}")
        if user_id:
            set_plan(session, user_id, "pro", "active", customer="fake_customer", subscription=sid, provider="fake")
        return user_id

    def portal(self, user_id, locale):
        return f"{self.settings.PUBLIC_WEB_URL.rstrip('/')}/{locale}/cuenta"

    def handle_webhook(self, session, payload, signature):
        return "ignorado"


class StripePaymentProvider(PaymentProvider):
    name = "stripe"

    def __init__(self, settings: Settings):
        import stripe

        self.settings = settings
        self.stripe = stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY

    def checkout(self, user_id, email, interval, locale):
        price = self.settings.STRIPE_PRICE_PRO_YEARLY if interval == "yearly" else self.settings.STRIPE_PRICE_PRO_MONTHLY
        base = self.settings.PUBLIC_WEB_URL.rstrip("/")
        sub = None
        params = dict(
            mode="subscription",
            line_items=[{"price": price, "quantity": 1}],
            client_reference_id=user_id,
            success_url=f"{base}/{locale}/cuenta?pago=ok",
            cancel_url=f"{base}/{locale}/precios?pago=cancelado",
            automatic_tax={"enabled": True},
            allow_promotion_codes=True,
            locale="es" if locale == "es" else "en",
            metadata={"user_id": user_id},
        )
        if email:
            params["customer_email"] = email
        sub = self.stripe.checkout.Session.create(**params)
        return CheckoutResult(url=sub.url, session_id=sub.id)

    def portal(self, user_id, locale):
        from core.db import session_scope

        with session_scope() as s:
            sub = s.get(Subscription, user_id)
            customer = sub.stripe_customer_id if sub else None
        if not customer:
            return f"{self.settings.PUBLIC_WEB_URL.rstrip('/')}/{locale}/precios"
        portal = self.stripe.billing_portal.Session.create(customer=customer, return_url=f"{self.settings.PUBLIC_WEB_URL.rstrip('/')}/{locale}/cuenta")
        return portal.url

    def handle_webhook(self, session, payload, signature):
        # Verifica la firma con la librería y trabaja sobre el JSON plano (los StripeObject no son dict).
        self.stripe.Webhook.construct_event(payload, signature, self.settings.STRIPE_WEBHOOK_SECRET)
        event = json.loads(payload)
        if session.get(StripeEvent, event["id"]) is not None:
            return "duplicado"
        record = StripeEvent(id=event["id"], type=event["type"])
        session.add(record)
        obj = event["data"]["object"]
        if event["type"] == "checkout.session.completed":
            user_id = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("user_id")
            if user_id:
                set_plan(session, user_id, "pro", "active", customer=obj.get("customer"), subscription=obj.get("subscription"))
        elif event["type"] in ("customer.subscription.updated", "customer.subscription.deleted"):
            sub = session.query(Subscription).filter(Subscription.stripe_subscription_id == obj.get("id")).one_or_none()
            if sub is not None:
                status = obj.get("status", "canceled")
                active = status in ("active", "trialing", "past_due") and event["type"] != "customer.subscription.deleted"
                # Desde la API 2025-03-31 el fin de periodo está en cada elemento de la suscripción.
                items = (obj.get("items") or {}).get("data") or [{}]
                end = obj.get("current_period_end") or items[0].get("current_period_end")
                set_plan(session, sub.user_id, "pro" if active else "free", status,
                         period_end=datetime.fromtimestamp(end, timezone.utc) if end else None)
        record.processed_at = datetime.now(timezone.utc)
        return event["type"]


_FAKE: dict[str, FakePaymentProvider] = {}


def get_provider(settings: Settings) -> PaymentProvider:
    if settings.PAYMENT_PROVIDER == "stripe" and settings.STRIPE_SECRET_KEY:
        return StripePaymentProvider(settings)
    if not settings.is_dev and settings.PAYMENT_PROVIDER != "fake":
        raise RuntimeError("Falta configurar Stripe")
    _FAKE.setdefault("fake", FakePaymentProvider(settings))
    return _FAKE["fake"]
