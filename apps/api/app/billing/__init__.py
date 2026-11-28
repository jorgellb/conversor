"""Cobro del pase de 24 h con PayPal (D-273): cuenta PayPal o tarjeta a través de PayPal, nada más.

El navegador muestra los botones de PayPal (JS SDK) y la API crea y captura el pedido con la API REST Orders v2: el importe
y lo que se vende los decide siempre el servidor. Un aviso de PayPal (webhook) completa el pedido si el navegador se cerró
antes de capturar, y avisa de devoluciones y retrocesiones.
"""
from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from core.errors import AppError, ErrorCode
from core.settings import Settings


@dataclass
class Price:
    total_cents: int
    base_cents: int
    vat_cents: int
    vat_rate_bp: int
    currency: str = "EUR"
    hours: int = 24


def price(settings: Settings) -> Price:
    """Precio con IVA incluido: la base es el total entre (1 + tipo), redondeada al céntimo; el IVA, la diferencia."""
    total = settings.PASS_PRICE_CENTS
    div = 10000 + settings.VAT_RATE_BP
    base = (total * 10000 * 2 + div) // (2 * div)  # redondeo al céntimo más cercano, en enteros
    return Price(total_cents=total, base_cents=base, vat_cents=total - base, vat_rate_bp=settings.VAT_RATE_BP,
                 hours=settings.PASS_HOURS)


def _issue(resp) -> str:
    """El primer `details[].issue` de un error de PayPal."""
    try:
        return str((resp.json().get("details") or [{}])[0].get("issue", ""))
    except (ValueError, AttributeError, IndexError):
        return ""


def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


@dataclass
class Capture:
    """Lo que dice PayPal de un pedido tras capturarlo (o al consultarlo)."""

    status: str  # COMPLETED, PENDING, DECLINED, FAILED…
    capture_id: str | None
    amount_cents: int
    currency: str
    custom_id: str | None = None
    payer_email: str | None = None
    raw: dict = field(default_factory=dict)


class PaymentProvider(ABC):
    name = "abstract"

    @abstractmethod
    def create_order(self, order_id: str, p: Price, description: str, locale: str) -> str: ...

    @abstractmethod
    def capture(self, provider_order_id: str, order_id: str) -> Capture: ...

    @abstractmethod
    def refund(self, capture_id: str, order_id: str, p: Price) -> str: ...

    @abstractmethod
    def verify_webhook(self, headers: dict[str, str], body: bytes) -> bool: ...


def _cents(value: str | None) -> int:
    whole, _, frac = (value or "0").partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


class PayPalProvider(PaymentProvider):
    name = "paypal"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.base = "https://api-m.paypal.com" if settings.PAYPAL_ENV == "live" else "https://api-m.sandbox.paypal.com"
        self.http = httpx.Client(base_url=self.base, timeout=20, transport=transport)

    # La ficha de acceso dura unas 9 horas; se guarda en Valkey para no pedirla en cada cobro.
    def _token(self) -> str:
        from core.valkey import get_valkey

        r = get_valkey()
        cached = r.get("paypal:token")
        if cached:
            return cached.decode() if isinstance(cached, bytes) else cached
        resp = self.http.post("/v1/oauth2/token", data={"grant_type": "client_credentials"},
                              auth=(self.settings.PAYPAL_CLIENT_ID, self.settings.PAYPAL_CLIENT_SECRET))
        if resp.status_code != 200:
            raise AppError(ErrorCode.PAYMENT_FAILED, status=502, detail="paypal_auth")
        data = resp.json()
        r.set("paypal:token", data["access_token"], ex=max(60, int(data.get("expires_in", 3600)) - 120))
        return data["access_token"]

    def _call(self, method: str, path: str, request_id: str | None = None, body: dict | None = None) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json",
                   "Prefer": "return=representation"}
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        resp = self.http.request(method, path, headers=headers, content=json.dumps(body) if body is not None else None)
        if resp.status_code == 401:
            from core.valkey import get_valkey

            get_valkey().delete("paypal:token")
        return resp

    def create_order(self, order_id, p, description, locale):
        unit = {"currency_code": p.currency, "value": money(p.base_cents)}
        tax = {"currency_code": p.currency, "value": money(p.vat_cents)}
        body = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": order_id,
                "custom_id": order_id,
                "invoice_id": order_id,
                "description": description,
                "soft_descriptor": self.settings.APP_NAME[:22],
                "amount": {"currency_code": p.currency, "value": money(p.total_cents),
                           "breakdown": {"item_total": unit, "tax_total": tax}},
                "items": [{"name": description, "quantity": "1", "category": "DIGITAL_GOODS",
                           "unit_amount": unit, "tax": tax}],
            }],
            "application_context": {
                "brand_name": self.settings.APP_NAME[:127],
                "locale": "es-ES" if locale == "es" else "en-GB",
                "shipping_preference": "NO_SHIPPING",
                "user_action": "PAY_NOW",
            },
        }
        resp = self._call("POST", "/v2/checkout/orders", request_id=f"crear-{order_id}", body=body)
        if resp.status_code not in (200, 201):
            raise AppError(ErrorCode.PAYMENT_FAILED, status=502, detail="paypal_create")
        return resp.json()["id"]

    @staticmethod
    def _parse(data: dict) -> Capture:
        unit = (data.get("purchase_units") or [{}])[0]
        caps = ((unit.get("payments") or {}).get("captures")) or []
        cap = caps[0] if caps else {}
        amount = cap.get("amount") or unit.get("amount") or {}
        # Sin captura no hay cobro: un pedido COMPLETED sin captura no da el pase.
        status = cap.get("status", "") if cap else ("PENDING" if data.get("status") == "COMPLETED" else data.get("status", ""))
        return Capture(status=status, capture_id=cap.get("id"),
                       amount_cents=_cents(amount.get("value")), currency=amount.get("currency_code", ""),
                       custom_id=cap.get("custom_id") or unit.get("custom_id"),
                       payer_email=(data.get("payer") or {}).get("email_address"), raw=data)

    def capture(self, provider_order_id, order_id):
        resp = self._call("POST", f"/v2/checkout/orders/{provider_order_id}/capture", request_id=f"capturar-{order_id}", body={})
        if resp.status_code in (200, 201):
            return self._parse(resp.json())
        issue = _issue(resp)
        if issue == "ORDER_ALREADY_CAPTURED":
            got = self._call("GET", f"/v2/checkout/orders/{provider_order_id}")
            if got.status_code == 200:
                return self._parse(got.json())
        if issue in ("INSTRUMENT_DECLINED", "PAYER_ACTION_REQUIRED"):
            # El comprador puede elegir otra tarjeta o cuenta en la misma ventana de PayPal.
            raise AppError(ErrorCode.PAYMENT_FAILED, status=402, detail=issue.lower())
        raise AppError(ErrorCode.PAYMENT_FAILED, status=502, detail="paypal_capture")

    def refund(self, capture_id, order_id, p):
        resp = self._call("POST", f"/v2/payments/captures/{capture_id}/refund", request_id=f"devolver-{order_id}", body={})
        if resp.status_code not in (200, 201) and _issue(resp) == "CAPTURE_FULLY_REFUNDED":
            # Un reintento tras un fallo de la base de datos: PayPal ya devolvió el dinero.
            return ""
        if resp.status_code not in (200, 201):
            raise AppError(ErrorCode.PAYMENT_FAILED, status=502, detail="paypal_refund")
        return resp.json().get("id", "")

    def verify_webhook(self, headers, body):
        if not self.settings.PAYPAL_WEBHOOK_ID:
            return False
        h = {k.lower(): v for k, v in headers.items()}
        try:
            event = json.loads(body)
        except ValueError:
            return False
        payload = {
            "auth_algo": h.get("paypal-auth-algo", ""), "cert_url": h.get("paypal-cert-url", ""),
            "transmission_id": h.get("paypal-transmission-id", ""), "transmission_sig": h.get("paypal-transmission-sig", ""),
            "transmission_time": h.get("paypal-transmission-time", ""), "webhook_id": self.settings.PAYPAL_WEBHOOK_ID,
            "webhook_event": event,
        }
        if not all(payload[k] for k in ("auth_algo", "cert_url", "transmission_id", "transmission_sig", "transmission_time")):
            return False
        resp = self._call("POST", "/v1/notifications/verify-webhook-signature", body=payload)
        return resp.status_code == 200 and resp.json().get("verification_status") == "SUCCESS"


class FakePaymentProvider(PaymentProvider):
    """Doble de desarrollo y CI: pedidos y capturas en memoria de Valkey, sin red. Nunca en producción."""

    name = "fake"

    def __init__(self, settings: Settings):
        self.settings = settings

    def _r(self):
        from core.valkey import get_valkey

        return get_valkey()

    def create_order(self, order_id, p, description, locale):
        pid = f"FAKE-{uuid.uuid4().hex[:16].upper()}"
        self._r().set(f"fakepay:{pid}", json.dumps({"order": order_id, "cents": p.total_cents, "currency": p.currency}), ex=86400)
        return pid

    def capture(self, provider_order_id, order_id):
        raw = self._r().get(f"fakepay:{provider_order_id}")
        if not raw:
            raise AppError(ErrorCode.PAYMENT_FAILED, status=404, detail="paypal_capture")
        data = json.loads(raw)
        cap = data.get("capture") or f"FAKECAP-{uuid.uuid4().hex[:12].upper()}"
        data["capture"] = cap
        self._r().set(f"fakepay:{provider_order_id}", json.dumps(data), ex=86400)
        return Capture(status="COMPLETED", capture_id=cap, amount_cents=data["cents"], currency=data["currency"],
                       custom_id=data["order"], payer_email="comprador@ejemplo.test")

    def refund(self, capture_id, order_id, p):
        return f"FAKEREF-{uuid.uuid4().hex[:12].upper()}"

    def verify_webhook(self, headers, body):
        return {k.lower(): v for k, v in headers.items()}.get("x-fake-webhook") == "ok"


_FAKE: dict[str, FakePaymentProvider] = {}
TRANSPORT: dict[str, httpx.BaseTransport | None] = {"paypal": None}  # las pruebas sustituyen la red de PayPal


def get_provider(settings: Settings) -> PaymentProvider:
    if settings.PAYMENT_PROVIDER == "paypal":
        if not (settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET):
            raise AppError(ErrorCode.PAYMENT_FAILED, status=503, detail="paypal_not_configured")
        return PayPalProvider(settings, transport=TRANSPORT["paypal"])
    # El doble que cobra sin cobrar solo existe en desarrollo y pruebas: en producción, PayPal o nada.
    if settings.PAYMENT_PROVIDER != "fake" or settings.APP_ENV not in ("development", "test"):
        raise AppError(ErrorCode.PAYMENT_FAILED, status=503, detail="paypal_not_configured")
    _FAKE.setdefault("fake", FakePaymentProvider(settings))
    return _FAKE["fake"]
