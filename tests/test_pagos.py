"""Pagos con PayPal, pase de 24 h, pedidos y facturas (D-273)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from helpers import auth


@pytest.fixture()
def pase(monkeypatch, services):
    from core.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "PASS_REQUIRED", True)
    monkeypatch.setattr(settings, "INVOICE_ISSUER_NAME", "Persona Autónoma")
    monkeypatch.setattr(settings, "INVOICE_ISSUER_TAX_ID", "12345678Z")
    monkeypatch.setattr(settings, "INVOICE_ISSUER_ADDRESS", "Calle Mayor 1, 28001 Madrid")
    return settings


def _user(user_token):
    uid = f"cliente-{uuid.uuid4().hex[:10]}"
    return uid, auth(user_token(user_id=uid, email=f"{uid}@ejemplo.test"))


def _buy(api, headers) -> dict:
    created = api.post("/v1/billing/orders", json={"locale": "es", "waiver": True}, headers=headers)
    assert created.status_code == 200, created.text
    order = created.json()
    captured = api.post(f"/v1/billing/orders/{order['order_id']}/capture", headers=headers)
    assert captured.status_code == 200, captured.text
    return {**order, **captured.json()}


def test_price_splits_vat_from_one_euro(pase):
    from app.billing import money, price

    p = price(pase)
    assert (p.total_cents, p.base_cents, p.vat_cents) == (100, 83, 17)
    assert money(p.base_cents) == "0.83" and money(-100) == "-1.00"


def test_config_is_public(api, pase):
    data = api.get("/v1/billing/config").json()
    assert data["price_cents"] == 100 and data["hours"] == 24 and data["provider"] == "fake" and data["required"] is True


def test_heavy_tool_needs_pass_but_light_is_free(api, pase, user_token):
    _, headers = _user(user_token)
    heavy = api.post("/v1/jobs", json={"tool": "ocr-pdf", "upload_ids": []}, headers=headers)
    assert heavy.status_code == 402
    body = heavy.json()
    assert body["error"]["code"] == "PASS_REQUIRED" and body["error"]["price_cents"] == 100
    light = api.post("/v1/jobs", json={"tool": "comprimir-pdf", "upload_ids": []}, headers=headers)
    assert light.status_code == 400  # pasa el pase y se queja de que faltan archivos


def test_order_needs_withdrawal_waiver_and_account(api, pase, user_token):
    _, headers = _user(user_token)
    assert api.post("/v1/billing/orders", json={"locale": "es"}, headers=headers).status_code == 422
    assert api.post("/v1/billing/orders", json={"waiver": True}).status_code == 401


def test_purchase_grants_pass_issues_invoice_and_unlocks_heavy(api, pase, user_token):
    uid, headers = _user(user_token)
    result = _buy(api, headers)
    assert result["status"] == "paid"
    until = datetime.fromisoformat(result["pass_until"])
    assert timedelta(hours=23, minutes=59) < until - datetime.now(timezone.utc) <= timedelta(hours=24)
    assert api.get("/v1/me", headers=headers).json()["plan"] == "pro"
    state = api.get("/v1/billing/pass", headers=headers).json()
    assert state["active"] is True and state["expires_at"]

    orders = api.get("/v1/billing/orders", headers=headers).json()["orders"]
    assert [o["status"] for o in orders] == ["paid"]
    invoices = api.get("/v1/billing/invoices", headers=headers).json()["invoices"]
    assert len(invoices) == 1 and invoices[0]["kind"] == "F2" and invoices[0]["number"].startswith(f"S{datetime.now().year}-")
    pdf = api.get(f"/v1/billing/invoices/{invoices[0]['id']}/pdf", headers=headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and pdf.headers["content-type"] == "application/pdf"
    # Otra cuenta no ve la factura.
    _, other = _user(user_token)
    assert api.get(f"/v1/billing/invoices/{invoices[0]['id']}/pdf", headers=other).status_code == 404

    heavy = api.post("/v1/jobs", json={"tool": "ocr-pdf", "upload_ids": []}, headers=headers)
    assert heavy.status_code == 400  # ya no es 402: falta el archivo

    # Capturar otra vez no da otro pase ni otra factura.
    again = api.post(f"/v1/billing/orders/{result['order_id']}/capture", headers=headers).json()
    assert again["status"] == "paid" and again["pass_until"] == result["pass_until"]
    assert len(api.get("/v1/billing/invoices", headers=headers).json()["invoices"]) == 1


def test_second_pass_starts_when_first_ends(api, pase, user_token):
    _, headers = _user(user_token)
    first = datetime.fromisoformat(_buy(api, headers)["pass_until"])
    second = datetime.fromisoformat(_buy(api, headers)["pass_until"])
    assert second - first == timedelta(hours=24)


def test_billing_profile_makes_full_invoice(api, pase, user_token):
    _, headers = _user(user_token)
    bad = api.put("/v1/billing/profile", json={"name": "Ana", "tax_id": "12345678A", "address": "Calle 1"}, headers=headers)
    assert bad.status_code == 422
    ok = api.put("/v1/billing/profile", json={"name": "Ana Pérez", "tax_id": "12.345.678-z", "address": "Calle Luna 3",
                                              "postal_code": "28004", "city": "Madrid"}, headers=headers)
    assert ok.status_code == 200 and ok.json()["tax_id"] == "12345678Z" and ok.json()["complete"] is True
    _buy(api, headers)
    invoice = api.get("/v1/billing/invoices", headers=headers).json()["invoices"][0]
    assert invoice["kind"] == "F1" and invoice["number"].startswith(f"F{datetime.now().year}-")


def test_invoice_chain_hash_and_immutability(api, pase, user_token, services):
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.orm import Session

    from app.billing.invoices import record_hash
    from core.models import Invoice

    _, h1 = _user(user_token)
    _, h2 = _user(user_token)
    admin = auth(user_token(role="admin"))
    # Compra, devolución en el mismo segundo (S… y luego R…) y otra compra: la cadena sigue el orden de emisión,
    # no el de la fecha al segundo ni el del número de las distintas series.
    first = _buy(api, h1)
    assert api.post(f"/v1/admin/billing/orders/{first['order_id']}/refund", headers=admin).status_code == 200
    _buy(api, h2)
    engine = create_engine(services["db_url"])
    with Session(engine) as s:
        chain = s.scalars(select(Invoice).order_by(Invoice.seq)).all()
        assert [i.kind for i in chain[-3:]] == ["F2", "R5", "F2"]
        for older, newer in zip(chain, chain[1:]):
            assert newer.prev_hash == older.record_hash
            assert newer.record_hash == record_hash(newer.issuer["tax_id"], newer.number, newer.issued_at, newer.kind,
                                                    newer.vat_cents, newer.total_cents, newer.prev_hash, newer.record_at)
            if older.series == newer.series:
                assert int(newer.number.rsplit("-", 1)[1]) == int(older.number.rsplit("-", 1)[1]) + 1
        assert len(newer.record_hash) == 64 and newer.record_hash == newer.record_hash.upper()
    with engine.connect() as conn, pytest.raises(Exception, match="no se modifican"):
        conn.execute(text("UPDATE invoices SET total_cents = 0 WHERE id = :i"), {"i": newer.id})
    engine.dispose()


def test_admin_refund_revokes_pass_and_issues_rectifying(api, pase, user_token):
    uid, headers = _user(user_token)
    order = _buy(api, headers)
    admin = auth(user_token(role="admin"))
    assert api.post(f"/v1/admin/billing/orders/{order['order_id']}/refund", headers=headers).status_code == 403
    done = api.post(f"/v1/admin/billing/orders/{order['order_id']}/refund", headers=admin)
    assert done.status_code == 200 and done.json()["status"] == "refunded" and done.json()["rectifying_invoice"].startswith("R")
    assert api.post(f"/v1/admin/billing/orders/{order['order_id']}/refund", headers=admin).status_code == 409
    assert api.get("/v1/me", headers=headers).json()["plan"] == "free"
    invoices = api.get("/v1/billing/invoices", headers=headers).json()["invoices"]
    rect = next(i for i in invoices if i["rectifies_id"])
    assert rect["kind"] == "R5" and rect["total_cents"] == -100 and rect["vat_cents"] == -17
    pdf = api.get(f"/v1/billing/invoices/{rect['id']}/pdf", headers=headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    summary = api.get("/v1/admin/billing/summary", headers=admin).json()
    assert summary["today"]["refunds"] >= 1 and summary["invoices"] >= 2
    listed = api.get("/v1/admin/billing/orders", params={"q": f"{uid}@ejemplo.test"}, headers=admin).json()["orders"]
    assert listed[0]["status"] == "refunded" and len(listed[0]["invoices"]) == 2
    csv = api.get("/v1/admin/billing/invoices.csv", headers=admin)
    assert csv.status_code == 200 and rect["number"] in csv.text and "-1,00" in csv.text


def test_refund_keeps_later_pass_and_moves_it_forward(api, pase, user_token):
    _, headers = _user(user_token)
    first = _buy(api, headers)
    second = _buy(api, headers)
    admin = auth(user_token(role="admin"))
    api.post(f"/v1/admin/billing/orders/{first['order_id']}/refund", headers=admin)
    state = api.get("/v1/billing/pass", headers=headers).json()
    left = datetime.fromisoformat(state["expires_at"]) - datetime.now(timezone.utc)
    assert state["active"] and timedelta(hours=23, minutes=59) < left <= timedelta(hours=24)
    assert second["status"] == "paid"


def test_fake_provider_is_refused_in_production(api, pase, user_token, monkeypatch):
    monkeypatch.setattr(pase, "APP_ENV", "production")
    _, headers = _user(user_token)
    res = api.post("/v1/billing/orders", json={"waiver": True}, headers=headers)
    assert res.status_code == 503 and res.json()["error"]["code"] == "PAYMENT_FAILED"


def test_account_deletion_keeps_invoices(api, pase, user_token, services):
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from core.models import Invoice

    uid, headers = _user(user_token)
    _buy(api, headers)
    export = api.get("/v1/me/export", headers=headers).json()
    assert export["orders"] and export["invoices"] and export["pass_until"]
    assert api.delete("/v1/me", headers=headers).status_code == 200
    engine = create_engine(services["db_url"])
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Invoice).where(Invoice.user_id == uid)) == 1
    engine.dispose()


# PayPal de verdad, con la red sustituida: lo que se manda y cómo se lee la respuesta.
class FakePayPal:
    def __init__(self):
        self.calls: list[tuple[str, str, dict, dict]] = []
        self.orders: dict[str, dict] = {}
        self.verify = "SUCCESS"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content and request.headers.get("content-type") == "application/json" else {}
        self.calls.append((request.method, request.url.path, dict(request.headers), body))
        path = request.url.path
        if path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "A21AA-prueba", "expires_in": 32400})
        if path == "/v2/checkout/orders":
            oid = f"PP{uuid.uuid4().hex[:15].upper()}"
            self.orders[oid] = body
            return httpx.Response(201, json={"id": oid, "status": "CREATED"})
        if path.endswith("/capture"):
            oid = path.split("/")[-2]
            unit = self.orders[oid]["purchase_units"][0]
            return httpx.Response(201, json={
                "id": oid, "status": "COMPLETED", "payer": {"email_address": "pagador@ejemplo.test"},
                "purchase_units": [{"reference_id": unit["reference_id"], "payments": {"captures": [{
                    "id": f"CAP{oid}", "status": "COMPLETED", "custom_id": unit["custom_id"], "amount": unit["amount"]}]}}]})
        if path.endswith("/refund"):
            return httpx.Response(201, json={"id": "REF1", "status": "COMPLETED"})
        if path == "/v1/notifications/verify-webhook-signature":
            return httpx.Response(200, json={"verification_status": self.verify})
        return httpx.Response(404, json={})


@pytest.fixture()
def paypal(pase, monkeypatch):
    from app import billing
    from core.valkey import get_valkey

    fake = FakePayPal()
    monkeypatch.setattr(pase, "PAYMENT_PROVIDER", "paypal")
    monkeypatch.setattr(pase, "PAYPAL_CLIENT_ID", "cliente-prueba")
    monkeypatch.setattr(pase, "PAYPAL_CLIENT_SECRET", "secreto-prueba")
    monkeypatch.setattr(pase, "PAYPAL_WEBHOOK_ID", "WH-PRUEBA")
    monkeypatch.setitem(billing.TRANSPORT, "paypal", httpx.MockTransport(fake))
    get_valkey().delete("paypal:token")
    yield fake
    get_valkey().delete("paypal:token")


def test_paypal_order_amounts_and_capture(api, paypal, user_token):
    _, headers = _user(user_token)
    assert api.get("/v1/billing/config").json()["client_id"] == "cliente-prueba"
    result = _buy(api, headers)
    assert result["status"] == "paid"
    create = next(c for c in paypal.calls if c[1] == "/v2/checkout/orders")
    unit = create[3]["purchase_units"][0]
    assert unit["amount"] == {"currency_code": "EUR", "value": "1.00", "breakdown": {
        "item_total": {"currency_code": "EUR", "value": "0.83"}, "tax_total": {"currency_code": "EUR", "value": "0.17"}}}
    assert unit["custom_id"] == result["order_id"] and unit["items"][0]["category"] == "DIGITAL_GOODS"
    assert create[2]["paypal-request-id"] == f"crear-{result['order_id']}"
    assert create[3]["application_context"]["shipping_preference"] == "NO_SHIPPING"
    # La ficha de acceso se reutiliza.
    assert sum(1 for c in paypal.calls if c[1] == "/v1/oauth2/token") == 1


def _event(kind: str, resource: dict) -> bytes:
    return json.dumps({"id": f"WH-{uuid.uuid4().hex}", "event_type": kind, "resource": resource}).encode()


SIGNED = {"paypal-auth-algo": "SHA256withRSA", "paypal-cert-url": "https://api.paypal.com/cert", "paypal-transmission-id": "t1",
          "paypal-transmission-sig": "firma", "paypal-transmission-time": "2026-11-27T10:00:00Z"}


def test_paypal_webhook_completes_order_when_browser_closed(api, paypal, user_token):
    _, headers = _user(user_token)
    order = api.post("/v1/billing/orders", json={"waiver": True}, headers=headers).json()
    event = _event("PAYMENT.CAPTURE.COMPLETED", {"id": "CAP-WH-1", "status": "COMPLETED", "custom_id": order["order_id"],
                                                 "amount": {"currency_code": "EUR", "value": "1.00"}})
    assert api.post("/v1/billing/webhook", content=event, headers={"content-type": "application/json"}).status_code == 400
    paypal.verify = "FAILURE"
    assert api.post("/v1/billing/webhook", content=event, headers=SIGNED).status_code == 400
    paypal.verify = "SUCCESS"
    ok = api.post("/v1/billing/webhook", content=event, headers=SIGNED)
    assert ok.status_code == 200 and ok.json()["received"] == "PAYMENT.CAPTURE.COMPLETED"
    assert api.post("/v1/billing/webhook", content=event, headers=SIGNED).json()["received"] == "duplicado"
    assert api.get("/v1/billing/pass", headers=headers).json()["active"] is True
    assert len(api.get("/v1/billing/invoices", headers=headers).json()["invoices"]) == 1

    refunded = _event("PAYMENT.CAPTURE.REFUNDED", {"id": "REF-WH", "status": "COMPLETED", "links": [
        {"rel": "up", "href": "https://api.paypal.com/v2/payments/captures/CAP-WH-1", "method": "GET"}]})
    assert api.post("/v1/billing/webhook", content=refunded, headers=SIGNED).status_code == 200
    assert api.get("/v1/billing/pass", headers=headers).json()["active"] is False
    kinds = sorted(i["kind"] for i in api.get("/v1/billing/invoices", headers=headers).json()["invoices"])
    assert kinds == ["F2", "R5"]


def test_paypal_amount_mismatch_gives_nothing(api, paypal, user_token):
    _, headers = _user(user_token)
    order = api.post("/v1/billing/orders", json={"waiver": True}, headers=headers).json()
    event = _event("PAYMENT.CAPTURE.COMPLETED", {"id": "CAP-MAL", "status": "COMPLETED", "custom_id": order["order_id"],
                                                 "amount": {"currency_code": "EUR", "value": "0.01"}})
    assert api.post("/v1/billing/webhook", content=event, headers=SIGNED).status_code == 409
    assert api.get("/v1/billing/pass", headers=headers).json()["active"] is False


def test_price_rounds_in_integers(pase, monkeypatch):
    from app.billing import price

    for total, bp, base in ((100, 2100, 83), (1000, 2100, 826), (121, 2100, 100), (500, 1000, 455), (100, 0, 100)):
        monkeypatch.setattr(pase, "PASS_PRICE_CENTS", total)
        monkeypatch.setattr(pase, "VAT_RATE_BP", bp)
        p = price(pase)
        assert (p.base_cents, p.vat_cents) == (base, total - base)


def test_paypal_completed_order_without_capture_is_not_paid():
    from app.billing import PayPalProvider

    got = PayPalProvider._parse({"id": "PP1", "status": "COMPLETED", "purchase_units": [{"amount": {"currency_code": "EUR", "value": "1.00"}}]})
    assert got.status == "PENDING" and got.capture_id is None


def test_csv_cells_cannot_be_formulas():
    from app.routers.admin import _cell

    assert _cell('=HYPERLINK("http://x")') == "'=HYPERLINK(\"http://x\")"
    assert [_cell(v) for v in ("+34", "-1", "@SUM(A1)", "\tx", "Ana", "", None)] == ["'+34", "'-1", "'@SUM(A1)", "'\tx", "Ana", "", ""]


def _paid_by_webhook(api, headers, capture_id: str) -> dict:
    order = api.post("/v1/billing/orders", json={"waiver": True}, headers=headers).json()
    event = _event("PAYMENT.CAPTURE.COMPLETED", {"id": capture_id, "status": "COMPLETED", "custom_id": order["order_id"],
                                                 "amount": {"currency_code": "EUR", "value": "1.00"}})
    assert api.post("/v1/billing/webhook", content=event, headers=SIGNED).status_code == 200
    return order


def _refund_event(kind: str, capture_id: str, value: str = "1.00") -> bytes:
    return _event(kind, {"id": f"REF-{uuid.uuid4().hex[:8]}", "status": "COMPLETED",
                         "amount": {"currency_code": "EUR", "value": value},
                         "links": [{"rel": "up", "href": f"https://api.paypal.com/v2/payments/captures/{capture_id}", "method": "GET"}]})


def test_paypal_partial_refund_keeps_pass_and_reversal_revokes_it(api, paypal, user_token):
    _, headers = _user(user_token)
    cap = f"CAP-{uuid.uuid4().hex[:8]}"
    _paid_by_webhook(api, headers, cap)
    partial = api.post("/v1/billing/webhook", content=_refund_event("PAYMENT.CAPTURE.REFUNDED", cap, "0.50"), headers=SIGNED)
    assert partial.status_code == 200
    assert api.get("/v1/billing/pass", headers=headers).json()["active"] is True
    assert [i["kind"] for i in api.get("/v1/billing/invoices", headers=headers).json()["invoices"]] == ["F2"]
    # Contracargo: PayPal manda una devolución cuyo enlace «up» es la captura.
    reversed_ = api.post("/v1/billing/webhook", content=_refund_event("PAYMENT.CAPTURE.REVERSED", cap), headers=SIGNED)
    assert reversed_.status_code == 200
    assert api.get("/v1/billing/pass", headers=headers).json()["active"] is False
    assert sorted(i["kind"] for i in api.get("/v1/billing/invoices", headers=headers).json()["invoices"]) == ["F2", "R5"]


def test_paypal_refund_before_capture_is_saved_is_retried(api, paypal, user_token):
    _, headers = _user(user_token)
    # Un pedido en curso (creado en PayPal y sin capturar) y una devolución de una captura que aún no tiene pedido.
    api.post("/v1/billing/orders", json={"waiver": True}, headers=headers)
    cap = f"CAP-{uuid.uuid4().hex[:8]}"
    early = _refund_event("PAYMENT.CAPTURE.REFUNDED", cap)
    assert api.post("/v1/billing/webhook", content=early, headers=SIGNED).status_code == 503
    _paid_by_webhook(api, headers, cap)
    # La repetición de PayPal (mismo id de evento) no está apuntada como procesada y retira el pase.
    again = api.post("/v1/billing/webhook", content=early, headers=SIGNED)
    assert again.status_code == 200 and again.json()["received"] == "PAYMENT.CAPTURE.REFUNDED"
    assert api.get("/v1/billing/pass", headers=headers).json()["active"] is False


def test_paypal_refund_retry_after_full_refund_is_success(api, paypal, user_token, monkeypatch):
    _, headers = _user(user_token)
    order = _buy(api, headers)
    original = paypal.__call__

    def already(request):
        if request.url.path.endswith("/refund"):
            return httpx.Response(422, json={"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "CAPTURE_FULLY_REFUNDED"}]})
        return original(request)

    from app import billing

    monkeypatch.setitem(billing.TRANSPORT, "paypal", httpx.MockTransport(already))
    admin = auth(user_token(role="admin"))
    done = api.post(f"/v1/admin/billing/orders/{order['order_id']}/refund", headers=admin)
    assert done.status_code == 200 and done.json()["status"] == "refunded"


def test_order_needs_verified_email_claim(api, pase, user_token):
    for verified in (None, False):
        headers = auth(user_token(email_verified=verified))
        got = api.post("/v1/billing/orders", json={"locale": "es", "waiver": True}, headers=headers)
        assert got.status_code == 403, (verified, got.text)
