"""Representación legible de una factura electrónica (F4-D2, A.2 y 7.14): datos completos y plantilla HTML.

Se usa en factura-electronica-a-pdf y en sus páginas propias (facturae-a-pdf, ubl-a-pdf y cii-a-pdf): el HTML se
imprime con el Chromium de `gotenberg` (sin red) y el XML original se incrusta sin cambiar un byte.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from tools.utils.facturas import lectura

NS = lectura.NS


@dataclass
class Party:
    name: str = ""
    vat: str = ""
    address: list[str] = field(default_factory=list)
    email: str = ""


@dataclass
class Detail:
    syntax: str
    spec: str = ""
    kind: str = "factura"
    number: str = ""
    date: str = ""
    due: str = ""
    currency: str = ""
    language: str = ""
    seller: Party = field(default_factory=Party)
    buyer: Party = field(default_factory=Party)
    lines: list[dict] = field(default_factory=list)  # descripcion, cantidad, unidad, precio, importe, iva
    taxes: list[dict] = field(default_factory=list)  # categoria, tipo, base, cuota
    net: str = ""
    tax: str = ""
    total: str = ""
    payable: str = ""
    iban: str = ""
    payment_terms: str = ""
    notes: list[str] = field(default_factory=list)
    reference: str = ""


def _t(node, path: str) -> str:
    return lectura._t(node, path)


def _ubl_party(party) -> Party:
    if party is None:
        return Party()
    addr = party.find("cac:PostalAddress", NS)
    lines = [_t(addr, "cbc:StreetName"), _t(addr, "cbc:AdditionalStreetName"),
             " ".join(x for x in (_t(addr, "cbc:PostalZone"), _t(addr, "cbc:CityName")) if x), _t(addr, "cac:Country/cbc:IdentificationCode")]
    return Party(name=_t(party, "cac:PartyLegalEntity/cbc:RegistrationName") or _t(party, "cac:PartyName/cbc:Name"),
                 vat=_t(party, "cac:PartyTaxScheme/cbc:CompanyID"), address=[x for x in lines if x],
                 email=_t(party, "cac:Contact/cbc:ElectronicMail"))


def _ubl(root) -> Detail:
    inv = lectura._ubl(root)
    d = Detail("ubl", inv.spec, inv.kind, inv.number, inv.date, _t(root, "cbc:DueDate") or _t(root, "cac:PaymentMeans/cbc:PaymentDueDate"),
               inv.currency)
    d.seller = _ubl_party(root.find("cac:AccountingSupplierParty/cac:Party", NS))
    d.buyer = _ubl_party(root.find("cac:AccountingCustomerParty/cac:Party", NS))
    credit = inv.kind == "abono"
    tag, qty = ("cac:CreditNoteLine", "cbc:CreditedQuantity") if credit else ("cac:InvoiceLine", "cbc:InvoicedQuantity")
    for line in root.findall(tag, NS)[:500]:
        q = line.find(qty, NS)
        d.lines.append({"descripcion": _t(line, "cac:Item/cbc:Name"), "cantidad": _t(line, qty), "unidad": q.get("unitCode", "") if q is not None else "",
                        "precio": _t(line, "cac:Price/cbc:PriceAmount"), "importe": _t(line, "cbc:LineExtensionAmount"),
                        "iva": _t(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent")})
    for sub in root.findall("cac:TaxTotal/cac:TaxSubtotal", NS)[:50]:
        d.taxes.append({"categoria": _t(sub, "cac:TaxCategory/cbc:ID"), "tipo": _t(sub, "cac:TaxCategory/cbc:Percent"),
                        "base": _t(sub, "cbc:TaxableAmount"), "cuota": _t(sub, "cbc:TaxAmount")})
    d.net = _t(root, "cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount")
    d.tax = _t(root, "cac:TaxTotal/cbc:TaxAmount")
    d.total = _t(root, "cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount")
    d.payable = _t(root, "cac:LegalMonetaryTotal/cbc:PayableAmount")
    d.iban = _t(root, "cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID")
    d.payment_terms = _t(root, "cac:PaymentTerms/cbc:Note")
    d.notes = [n.text.strip() for n in root.findall("cbc:Note", NS)[:10] if n.text and n.text.strip()]
    d.reference = _t(root, "cbc:BuyerReference")
    return d


def _cii_party(party) -> Party:
    if party is None:
        return Party()
    addr = party.find("ram:PostalTradeAddress", NS)
    lines = [_t(addr, "ram:LineOne"), _t(addr, "ram:LineTwo"),
             " ".join(x for x in (_t(addr, "ram:PostcodeCode"), _t(addr, "ram:CityName")) if x), _t(addr, "ram:CountryID")]
    return Party(name=_t(party, "ram:Name"), vat=_t(party, "ram:SpecifiedTaxRegistration/ram:ID"), address=[x for x in lines if x],
                 email=_t(party, "ram:URIUniversalCommunication/ram:URIID"))


def _date(raw: str) -> str:
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}" if re.fullmatch(r"\d{8}", raw or "") else raw


def _cii(root) -> Detail:
    inv = lectura._cii(root)
    tx = root.find("rsm:SupplyChainTradeTransaction", NS)
    agreement = tx.find("ram:ApplicableHeaderTradeAgreement", NS) if tx is not None else None
    settlement = tx.find("ram:ApplicableHeaderTradeSettlement", NS) if tx is not None else None
    d = Detail("cii", inv.spec, inv.kind, inv.number, inv.date,
               _date(_t(settlement, "ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime/udt:DateTimeString")), inv.currency)
    d.seller = _cii_party(agreement.find("ram:SellerTradeParty", NS) if agreement is not None else None)
    d.buyer = _cii_party(agreement.find("ram:BuyerTradeParty", NS) if agreement is not None else None)
    for line in (tx.findall("ram:IncludedSupplyChainTradeLineItem", NS)[:500] if tx is not None else []):
        q = line.find("ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", NS)
        d.lines.append({"descripcion": _t(line, "ram:SpecifiedTradeProduct/ram:Name"), "cantidad": (q.text or "").strip() if q is not None else "",
                        "unidad": q.get("unitCode", "") if q is not None else "",
                        "precio": _t(line, "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount"),
                        "importe": _t(line, "ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount"),
                        "iva": _t(line, "ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/ram:RateApplicablePercent")})
    for tax in (settlement.findall("ram:ApplicableTradeTax", NS)[:50] if settlement is not None else []):
        d.taxes.append({"categoria": _t(tax, "ram:CategoryCode"), "tipo": _t(tax, "ram:RateApplicablePercent"),
                        "base": _t(tax, "ram:BasisAmount"), "cuota": _t(tax, "ram:CalculatedAmount")})
    summary = "ram:SpecifiedTradeSettlementHeaderMonetarySummation"
    d.net = _t(settlement, f"{summary}/ram:TaxBasisTotalAmount")
    d.tax = _t(settlement, f"{summary}/ram:TaxTotalAmount")
    d.total = _t(settlement, f"{summary}/ram:GrandTotalAmount")
    d.payable = _t(settlement, f"{summary}/ram:DuePayableAmount")
    d.iban = _t(settlement, "ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeePartyCreditorFinancialAccount/ram:IBANID")
    d.payment_terms = _t(settlement, "ram:SpecifiedTradePaymentTerms/ram:Description")
    d.notes = [(n.text or "").strip() for n in root.findall("rsm:ExchangedDocument/ram:IncludedNote/ram:Content", NS)[:10] if (n.text or "").strip()]
    d.reference = _t(agreement, "ram:BuyerReference")
    return d


def _facturae(root, version: str) -> Detail:
    inv = lectura._facturae(root, version)
    L = lectura._ltext  # noqa: N806
    invoice = lectura._local(root, "Invoice")
    d = Detail("facturae", inv.spec, inv.kind, inv.number, inv.date, "", inv.currency, L(invoice, "LanguageName"))

    def party(node) -> Party:
        if node is None:
            return Party()
        addr = lectura._local(node, "AddressInSpain")
        if addr is None:
            addr = lectura._local(node, "OverseasAddress")
        lines = [L(addr, "Address"), " ".join(x for x in (L(addr, "PostCode", "PostCodeAndTown"), L(addr, "Town")) if x),
                 L(addr, "Province"), L(addr, "CountryCode")] if addr is not None else []
        return Party(name=L(node, "CorporateName", "Name"), vat=L(node, "TaxIdentificationNumber"), address=[x for x in lines if x],
                     email=L(node, "ElectronicMail"))

    d.seller, d.buyer = party(lectura._local(root, "SellerParty")), party(lectura._local(root, "BuyerParty"))
    for line in [e for e in (invoice.iter() if invoice is not None else []) if isinstance(e.tag, str) and e.tag.rsplit("}", 1)[-1] == "InvoiceLine"][:500]:
        d.lines.append({"descripcion": L(line, "ItemDescription"), "cantidad": L(line, "Quantity"), "unidad": L(line, "UnitOfMeasure"),
                        "precio": L(line, "UnitPriceWithoutTax"), "importe": L(line, "TotalCost"), "iva": L(line, "TaxRate")})
    outputs = lectura._local(invoice, "TaxesOutputs") if invoice is not None else None
    for tax in ([e for e in outputs if isinstance(e.tag, str) and e.tag.rsplit("}", 1)[-1] == "Tax"] if outputs is not None else [])[:50]:
        d.taxes.append({"categoria": L(tax, "TaxTypeCode"), "tipo": L(tax, "TaxRate"),
                        "base": L(lectura._local(tax, "TaxableBase"), "TotalAmount"), "cuota": L(lectura._local(tax, "TaxAmount"), "TotalAmount")})
    totals = lectura._local(invoice, "InvoiceTotals") if invoice is not None else None
    d.net, d.tax = L(totals, "TotalGrossAmountBeforeTaxes"), L(totals, "TotalTaxOutputs")
    d.total, d.payable = L(totals, "InvoiceTotal"), L(totals, "TotalExecutableAmount")
    installment = lectura._local(invoice, "Installment") if invoice is not None else None
    d.due = L(installment, "InstallmentDueDate")
    d.iban = L(installment, "IBAN")
    return d


def detail(data: bytes) -> Detail:
    root, inv = lectura.read_invoice(data)
    if inv.syntax == "ubl":
        return _ubl(root)
    if inv.syntax == "cii":
        return _cii(root)
    return _facturae(root, lectura.facturae_version(root))


LABELS = {
    "es": {"factura": "Factura", "abono": "Factura rectificativa (abono)", "number": "Número", "date": "Fecha", "due": "Vencimiento",
           "seller": "Emisor", "buyer": "Cliente", "vat": "NIF", "desc": "Concepto", "qty": "Cantidad", "unit": "Unidad", "price": "Precio",
           "amount": "Importe", "rate": "IVA %", "taxes": "Desglose de impuestos", "category": "Categoría", "base": "Base", "quota": "Cuota",
           "net": "Total sin impuestos", "tax": "Impuestos", "total": "Total", "payable": "Importe a pagar", "iban": "IBAN",
           "terms": "Condiciones de pago", "notes": "Notas", "reference": "Referencia del cliente", "spec": "Formato",
           "footer": "Representación legible de una factura electrónica. El documento con validez es el XML original, incrustado en este PDF sin cambios."},
    "en": {"factura": "Invoice", "abono": "Credit note", "number": "Number", "date": "Date", "due": "Due date",
           "seller": "Seller", "buyer": "Customer", "vat": "VAT ID", "desc": "Item", "qty": "Quantity", "unit": "Unit", "price": "Price",
           "amount": "Amount", "rate": "VAT %", "taxes": "Tax breakdown", "category": "Category", "base": "Taxable amount", "quota": "Tax",
           "net": "Total without tax", "tax": "Taxes", "total": "Total", "payable": "Amount due", "iban": "IBAN",
           "terms": "Payment terms", "notes": "Notes", "reference": "Customer reference", "spec": "Format",
           "footer": "Human-readable representation of an e-invoice. The legally valid document is the original XML, embedded in this PDF unchanged."},
}


def language_of(d: Detail, locale: str, option: str) -> str:
    """«[El de la factura]» (A.2): Facturae declara su idioma; UBL y CII no, y se usa el de la página."""
    if option in ("es", "en"):
        return option
    lang = (d.language or "").lower()[:2]
    return lang if lang in ("es", "en") else ("en" if locale == "en" else "es")


def render(d: Detail, lang: str, spec_label: str, embedded_name: str) -> str:
    t = LABELS[lang]
    e = html.escape
    cur = f" {e(d.currency)}" if d.currency else ""

    def party(p: Party, label: str) -> str:
        rows = "".join(f"<div>{e(x)}</div>" for x in p.address)
        vat = f"<div>{e(t['vat'])}: {e(p.vat)}</div>" if p.vat else ""
        mail = f"<div>{e(p.email)}</div>" if p.email else ""
        return f"<div class=\"p\"><h3>{e(label)}</h3><div class=\"n\">{e(p.name or '—')}</div>{vat}{rows}{mail}</div>"

    lines = "".join(
        f"<tr><td>{e(x['descripcion'])}</td><td class=\"r\">{e(x['cantidad'])}</td><td>{e(x['unidad'])}</td>"
        f"<td class=\"r\">{e(x['precio'])}</td><td class=\"r\">{e(x['iva'])}</td><td class=\"r\">{e(x['importe'])}</td></tr>" for x in d.lines)
    taxes = "".join(f"<tr><td>{e(x['categoria'])}</td><td class=\"r\">{e(x['tipo'])}</td><td class=\"r\">{e(x['base'])}</td>"
                    f"<td class=\"r\">{e(x['cuota'])}</td></tr>" for x in d.taxes)
    meta = [(t["number"], d.number), (t["date"], d.date), (t["due"], d.due), (t["reference"], d.reference), (t["spec"], spec_label)]
    meta_html = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in meta if v)
    totals = [(t["net"], d.net), (t["tax"], d.tax), (t["total"], d.total), (t["payable"], d.payable)]
    totals_html = "".join(f"<tr{' class=\"g\"' if k == t['payable'] else ''}><th>{e(k)}</th><td class=\"r\">{e(v)}{cur}</td></tr>" for k, v in totals if v)
    pay = "".join(f"<p><b>{e(k)}:</b> {e(v)}</p>" for k, v in ((t["iban"], d.iban), (t["terms"], d.payment_terms)) if v)
    notes = "".join(f"<p>{e(n)}</p>" for n in d.notes)
    return (f"<!doctype html><html lang=\"{lang}\"><head><meta charset=\"utf-8\"><title>{e(t[d.kind])} {e(d.number)}</title><style>"
            "@page{size:A4;margin:16mm}body{font:10pt/1.45 'Noto Sans','DejaVu Sans',sans-serif;color:#111}"
            "h1{font-size:20pt;margin:0 0 4mm}h2{font-size:12pt;margin:6mm 0 2mm}h3{font-size:9pt;text-transform:uppercase;color:#555;margin:0 0 1mm}"
            ".top{display:flex;justify-content:space-between;gap:8mm}.parties{display:flex;gap:8mm;margin:6mm 0}.p{flex:1;border:1px solid #ccc;"
            "border-radius:2mm;padding:3mm}.n{font-weight:bold}table{border-collapse:collapse;width:100%}th,td{padding:1.5mm 2mm;text-align:left;"
            "vertical-align:top}.l th{background:#f0f0f0;border-bottom:1px solid #999}.l td{border-bottom:1px solid #ddd}.r{text-align:right}"
            ".meta th{color:#555;font-weight:normal;padding-left:0}.tot{width:45%;margin-left:auto;margin-top:4mm}.tot th{font-weight:normal}"
            ".tot .g th,.tot .g td{font-weight:bold;border-top:1px solid #111}footer{margin-top:10mm;color:#666;font-size:8pt}"
            "</style></head><body>"
            f"<div class=\"top\"><div><h1>{e(t[d.kind])}</h1></div><table class=\"meta\" style=\"width:auto\">{meta_html}</table></div>"
            f"<div class=\"parties\">{party(d.seller, t['seller'])}{party(d.buyer, t['buyer'])}</div>"
            f"<table class=\"l\"><thead><tr><th>{e(t['desc'])}</th><th class=\"r\">{e(t['qty'])}</th><th>{e(t['unit'])}</th>"
            f"<th class=\"r\">{e(t['price'])}</th><th class=\"r\">{e(t['rate'])}</th><th class=\"r\">{e(t['amount'])}</th></tr></thead><tbody>{lines}</tbody></table>"
            + (f"<h2>{e(t['taxes'])}</h2><table class=\"l\"><thead><tr><th>{e(t['category'])}</th><th class=\"r\">%</th><th class=\"r\">{e(t['base'])}</th>"
               f"<th class=\"r\">{e(t['quota'])}</th></tr></thead><tbody>{taxes}</tbody></table>" if taxes else "")
            + f"<table class=\"tot\">{totals_html}</table>{pay}"
            + (f"<h2>{e(t['notes'])}</h2>{notes}" if notes else "")
            + f"<footer>{e(t['footer'])} ({e(embedded_name)})</footer></body></html>")
