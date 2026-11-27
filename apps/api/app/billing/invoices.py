"""Facturas del pase (D-273): numeración correlativa por serie y año, huella encadenada y PDF.

Series: «S» simplificadas (F2, sin datos fiscales del comprador; hasta 400 € el Reglamento de facturación lo permite),
«F» completas (F1, con nombre, NIF y dirección del comprador) y «R» rectificativas (R5 de una simplificada, R1 de una
completa). Número: `<prefijo><serie><año>-<6 cifras>`, p. ej. «S2026-000001».

La huella sigue el registro de alta del Reglamento de sistemas informáticos de facturación (Orden HAC/1177/2024): SHA-256
en hexadecimal y mayúsculas de
`IDEmisorFactura=…&NumSerieFactura=…&FechaExpedicionFactura=dd-mm-aaaa&TipoFactura=…&CuotaTotal=…&ImporteTotal=…&Huella=…&FechaHoraHusoGenRegistro=…`
con la huella del registro anterior del mismo emisor. Falta el envío de los registros a la AEAT (VERI*FACTU), que para un
autónomo es obligatorio desde julio de 2027 (DEPLOY-CHECKLIST).
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core.models import BillingProfile, Invoice, InvoiceCounter, Order
from core.settings import Settings

from . import money

MADRID = ZoneInfo("Europe/Madrid")
# Clave fija del bloqueo que serializa la emisión: la cadena de huellas es una sola por emisor.
CHAIN_LOCK = 727_300_001


def issuer_of(settings: Settings) -> dict:
    return {"name": settings.INVOICE_ISSUER_NAME, "tax_id": settings.INVOICE_ISSUER_TAX_ID.upper().replace(" ", ""),
            "address": settings.INVOICE_ISSUER_ADDRESS, "email": settings.INVOICE_ISSUER_EMAIL}


def buyer_of(session: Session, order: Order) -> tuple[dict, bool]:
    """Datos del comprador y si bastan para una factura completa (nombre, NIF y dirección)."""
    bp = session.get(BillingProfile, order.user_id)
    buyer = {"email": order.email or order.payer_email or ""}
    if bp is not None:
        buyer.update({"name": bp.name, "tax_id": bp.tax_id, "address": bp.address, "postal_code": bp.postal_code,
                      "city": bp.city, "country": bp.country})
    complete = bool(bp and bp.name.strip() and bp.tax_id.strip() and bp.address.strip())
    return buyer, complete


def record_hash(nif: str, number: str, issued: datetime, kind: str, vat_cents: int, total_cents: int, prev: str,
                record_at: str) -> str:
    chain = (f"IDEmisorFactura={nif}&NumSerieFactura={number}&FechaExpedicionFactura={issued.astimezone(MADRID):%d-%m-%Y}"
             f"&TipoFactura={kind}&CuotaTotal={money(vat_cents)}&ImporteTotal={money(total_cents)}&Huella={prev}"
             f"&FechaHoraHusoGenRegistro={record_at}")
    return hashlib.sha256(chain.encode("utf-8")).hexdigest().upper()


def _next_number(session: Session, series: str) -> int:
    counter = session.execute(select(InvoiceCounter).where(InvoiceCounter.series == series).with_for_update()).scalar_one_or_none()
    if counter is None:
        session.execute(text("INSERT INTO invoice_counters (series, last) VALUES (:s, 0) ON CONFLICT DO NOTHING"), {"s": series})
        counter = session.execute(select(InvoiceCounter).where(InvoiceCounter.series == series).with_for_update()).scalar_one()
    counter.last += 1
    session.flush()
    return counter.last


def issue(session: Session, settings: Settings, order: Order, rectifies: Invoice | None = None) -> Invoice:
    """Emite la factura de un pedido pagado, o la rectificativa (importes en negativo) de una factura."""
    session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": CHAIN_LOCK})
    now = datetime.now(MADRID).replace(microsecond=0)
    if rectifies is not None:
        kind = "R1" if rectifies.kind == "F1" else "R5"
        letter, buyer = "R", rectifies.buyer
        lines = [{**line, "base_cents": -line["base_cents"], "vat_cents": -line["vat_cents"],
                  "total_cents": -line["total_cents"]} for line in rectifies.lines]
        base, vat, total, rate = -rectifies.base_cents, -rectifies.vat_cents, -rectifies.total_cents, rectifies.vat_rate_bp
    else:
        buyer, complete = buyer_of(session, order)
        kind, letter = ("F1", "F") if complete else ("F2", "S")
        description = {"es": f"Pase de {order.hours} horas: herramientas avanzadas", "en": f"{order.hours}-hour pass: advanced tools"}
        lines = [{"description": description["en" if order.locale == "en" else "es"], "quantity": 1,
                  "base_cents": order.base_cents, "vat_cents": order.vat_cents, "total_cents": order.total_cents}]
        base, vat, total, rate = order.base_cents, order.vat_cents, order.total_cents, order.vat_rate_bp
    series = f"{settings.INVOICE_SERIES_PREFIX}{letter}{now.year}"
    number = f"{series}-{_next_number(session, series):06d}"
    issuer = issuer_of(settings)
    prev = session.scalar(select(Invoice.record_hash).order_by(Invoice.seq.desc()).limit(1)) or ""
    record_at = now.isoformat()
    inv = Invoice(
        number=number, series=series, kind=kind, order_id=order.id, rectifies_id=rectifies.id if rectifies else None,
        user_id=order.user_id, issued_at=now, issuer=issuer, buyer=buyer, lines=lines, base_cents=base, vat_rate_bp=rate,
        vat_cents=vat, total_cents=total, currency=order.currency, prev_hash=prev,
        record_hash=record_hash(issuer["tax_id"], number, now, kind, vat, total, prev, record_at), record_at=record_at,
        locale=order.locale,
    )
    session.add(inv)
    session.flush()
    return inv


def qr_url(settings: Settings, inv: Invoice) -> str | None:
    if not settings.VERIFACTU_QR_URL:
        return None
    query = urlencode({"nif": inv.issuer.get("tax_id", ""), "numserie": inv.number,
                       "fecha": f"{inv.issued_at.astimezone(MADRID):%d-%m-%Y}", "importe": money(inv.total_cents)})
    return f"{settings.VERIFACTU_QR_URL}?{query}"


T = {
    "es": {"F1": "Factura", "F2": "Factura simplificada", "R1": "Factura rectificativa", "R5": "Factura rectificativa simplificada",
           "number": "Número", "date": "Fecha de expedición", "issuer": "Emisor", "buyer": "Cliente", "concept": "Concepto",
           "qty": "Cant.", "base": "Base imponible", "vat": "IVA", "total": "Total", "paid": "Pagado con PayPal",
           "rectifies": "Rectifica la factura", "reason": "Motivo: devolución del importe del pase.",
           "hash": "Huella del registro", "qr": "QR tributario", "order": "Pedido"},
    "en": {"F1": "Invoice", "F2": "Simplified invoice", "R1": "Corrective invoice", "R5": "Simplified corrective invoice",
           "number": "Number", "date": "Issue date", "issuer": "Issuer", "buyer": "Customer", "concept": "Description",
           "qty": "Qty", "base": "Taxable base", "vat": "VAT", "total": "Total", "paid": "Paid with PayPal",
           "rectifies": "Corrects invoice", "reason": "Reason: refund of the pass amount.",
           "hash": "Record hash", "qr": "Tax QR code", "order": "Order"},
}


def _eur(cents: int, locale: str) -> str:
    value = money(cents)
    return f"{value.replace('.', ',')} €" if locale == "es" else f"€{value}"


def render_pdf(settings: Settings, inv: Invoice, rectified_number: str | None = None) -> bytes:
    """PDF A4 de la factura con reportlab (BSD): sobrio, con la tabla de conceptos, el desglose y la huella."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    loc = "en" if inv.locale == "en" else "es"
    t = T[loc]
    ink, muted, line = HexColor("#14161a"), HexColor("#5b616b"), HexColor("#d9dce1")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, pageCompression=1)
    c.setTitle(f"{t[inv.kind]} {inv.number}")
    c.setAuthor(inv.issuer.get("name") or settings.APP_NAME)
    w, h = A4
    x0, x1 = 20 * mm, w - 20 * mm
    y = h - 24 * mm

    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(x0, y, t[inv.kind])
    c.setFont("Helvetica", 10)
    c.setFillColor(muted)
    c.drawRightString(x1, y + 4, settings.APP_NAME)
    y -= 9 * mm
    c.setFillColor(ink)
    c.setFont("Helvetica", 9.5)
    for label, value in ((t["number"], inv.number), (t["date"], f"{inv.issued_at.astimezone(MADRID):%d/%m/%Y}"),
                         (t["order"], str(inv.order_id))):
        c.setFillColor(muted)
        c.drawString(x0, y, label)
        c.setFillColor(ink)
        c.drawString(x0 + 38 * mm, y, value)
        y -= 5 * mm
    if rectified_number:
        c.setFillColor(muted)
        c.drawString(x0, y, t["rectifies"])
        c.setFillColor(ink)
        c.drawString(x0 + 38 * mm, y, rectified_number)
        y -= 5 * mm
        c.drawString(x0, y, t["reason"])
        y -= 5 * mm

    y -= 5 * mm
    col = (x1 - x0) / 2
    for i, (title, party) in enumerate(((t["issuer"], inv.issuer), (t["buyer"], inv.buyer))):
        x = x0 + i * col
        yy = y
        c.setFillColor(muted)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x, yy, title.upper())
        yy -= 5 * mm
        c.setFillColor(ink)
        c.setFont("Helvetica", 9.5)
        rows = [party.get("name"), party.get("tax_id"), party.get("address"),
                " ".join(v for v in (party.get("postal_code"), party.get("city")) if v), party.get("email")]
        for row in rows:
            if row:
                c.drawString(x, yy, str(row)[:70])
                yy -= 4.6 * mm
    y -= 34 * mm

    c.setStrokeColor(line)
    c.setLineWidth(0.6)
    c.line(x0, y, x1, y)
    y -= 5.5 * mm
    c.setFillColor(muted)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0, y, t["concept"].upper())
    c.drawRightString(x1 - 66 * mm, y, t["qty"].upper())
    c.drawRightString(x1 - 25 * mm, y, t["base"].upper())
    c.drawRightString(x1, y, t["total"].upper())
    y -= 3 * mm
    c.line(x0, y, x1, y)
    c.setFillColor(ink)
    c.setFont("Helvetica", 9.5)
    for item in inv.lines:
        y -= 6 * mm
        c.drawString(x0, y, str(item["description"])[:70])
        c.drawRightString(x1 - 66 * mm, y, str(item.get("quantity", 1)))
        c.drawRightString(x1 - 25 * mm, y, _eur(item["base_cents"], loc))
        c.drawRightString(x1, y, _eur(item["total_cents"], loc))
    y -= 4 * mm
    c.line(x0, y, x1, y)

    rate = f"{inv.vat_rate_bp / 100:g} %"
    y -= 7 * mm
    for label, cents, bold in ((t["base"], inv.base_cents, False), (f"{t['vat']} ({rate})", inv.vat_cents, False),
                               (t["total"], inv.total_cents, True)):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 9.5)
        c.setFillColor(ink if bold else muted)
        c.drawRightString(x1 - 30 * mm, y, label)
        c.setFillColor(ink)
        c.drawRightString(x1, y, _eur(cents, loc))
        y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(muted)
    c.drawString(x0, y + 6 * mm, t["paid"])

    url = qr_url(settings, inv)
    if url:
        from reportlab.graphics import renderPDF
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics.shapes import Drawing

        widget = QrCodeWidget(url, barLevel="M")
        bx0, by0, bx1, by1 = widget.getBounds()
        size = 30 * mm
        d = Drawing(size, size, transform=[size / (bx1 - bx0), 0, 0, size / (by1 - by0), 0, 0])
        d.add(widget)
        renderPDF.draw(d, c, x0, 34 * mm)
        c.setFont("Helvetica", 7.5)
        c.drawString(x0, 31 * mm, t["qr"])

    c.setFont("Helvetica", 7)
    c.setFillColor(muted)
    c.drawString(x0, 22 * mm, f"{t['hash']}: {inv.record_hash}")
    c.drawString(x0, 18 * mm, f"{inv.issuer.get('name', '')} · {inv.issuer.get('tax_id', '')} · {inv.issuer.get('address', '')}"[:150])
    c.showPage()
    c.save()
    return buf.getvalue()
