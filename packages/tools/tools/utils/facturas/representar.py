"""Representación legible de una factura electrónica (F4-D2, A.2 y 7.14): datos completos y plantilla HTML.

Se usa en factura-electronica-a-pdf y en sus páginas propias (facturae-a-pdf, ubl-a-pdf y cii-a-pdf): el HTML se
imprime con el Chromium de `gotenberg` (sin red) y el XML original se incrusta sin cambiar un byte. Los importes se
copian del XML sin recalcular. En Facturae se navega por rutas explícitas de hijos directos (una búsqueda por todo el
subárbol confunde la dirección de un centro administrativo con la del cliente, o el IRPF de una línea con su IVA; D-194).
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from tools.utils.facturas import lectura

NS = lectura.NS
MAX_LINES = 500
MAX_TAXES = 50


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
    kind: str = "factura"  # factura, abono (UBL CreditNote y CII 381) o rectificativa (Facturae OR y CR)
    number: str = ""
    date: str = ""
    due: str = ""
    currency: str = ""
    language: str = ""
    seller: Party = field(default_factory=Party)
    buyer: Party = field(default_factory=Party)
    lines: list[dict] = field(default_factory=list)  # descripcion, cantidad, unidad, precio, importe, iva
    line_count: int = 0  # todas las líneas del XML (se representan como mucho MAX_LINES)
    taxes: list[dict] = field(default_factory=list)  # categoria, tipo, base, cuota
    withheld: list[dict] = field(default_factory=list)  # retenciones de Facturae (IRPF), mismas claves
    net: str = ""
    allowances: str = ""
    charges: str = ""
    tax: str = ""
    withheld_total: str = ""
    total: str = ""
    prepaid: str = ""
    payable: str = ""
    iban: str = ""
    payment_terms: str = ""
    notes: list[str] = field(default_factory=list)
    reference: str = ""
    corrected: str = ""  # factura que rectifica
    invoice_count: int = 1  # Facturae en lote: se representa la primera


def _t(node, path: str) -> str:
    return lectura._t(node, path)


def _kids(node, name: str) -> list:
    if node is None:
        return []
    return [c for c in node if isinstance(c.tag, str) and c.tag.rsplit("}", 1)[-1] == name]


def _p(node, path: str):
    """Primer nodo por una ruta de hijos directos por nombre local (`Invoices/Invoice`; `A|B` es uno u otro), sin bajar a
    otros subárboles."""
    for part in path.split("/"):
        if node is None:
            return None
        options = []
        for alt in part.split("|"):
            options = _kids(node, alt)
            if options:
                break
        node = options[0] if options else None
    return node


def _pt(node, path: str) -> str:
    found = _p(node, path)
    return (found.text or "").strip() if found is not None and found.text else ""


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
    lines = root.findall(tag, NS)
    d.line_count = len(lines)
    for line in lines[:MAX_LINES]:
        q = line.find(qty, NS)
        d.lines.append({"descripcion": _t(line, "cac:Item/cbc:Name"), "cantidad": _t(line, qty), "unidad": q.get("unitCode", "") if q is not None else "",
                        "precio": _t(line, "cac:Price/cbc:PriceAmount"), "importe": _t(line, "cbc:LineExtensionAmount"),
                        "iva": _t(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent")})
    for sub in root.findall("cac:TaxTotal/cac:TaxSubtotal", NS)[:MAX_TAXES]:
        d.taxes.append({"categoria": _t(sub, "cac:TaxCategory/cbc:ID"), "tipo": _t(sub, "cac:TaxCategory/cbc:Percent"),
                        "base": _t(sub, "cbc:TaxableAmount"), "cuota": _t(sub, "cbc:TaxAmount")})
    total = "cac:LegalMonetaryTotal"
    d.net = _t(root, f"{total}/cbc:TaxExclusiveAmount")
    d.allowances, d.charges = _t(root, f"{total}/cbc:AllowanceTotalAmount"), _t(root, f"{total}/cbc:ChargeTotalAmount")
    d.tax = _t(root, "cac:TaxTotal/cbc:TaxAmount")
    d.total = _t(root, f"{total}/cbc:TaxInclusiveAmount")
    d.prepaid = _t(root, f"{total}/cbc:PrepaidAmount")
    d.payable = _t(root, f"{total}/cbc:PayableAmount")
    d.iban = _t(root, "cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID")
    d.payment_terms = _t(root, "cac:PaymentTerms/cbc:Note")
    d.notes = [n.text.strip() for n in root.findall("cbc:Note", NS)[:10] if n.text and n.text.strip()]
    d.reference = _t(root, "cbc:BuyerReference")
    d.corrected = _t(root, "cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID")
    return d


def _cii_party(party) -> Party:
    if party is None:
        return Party()
    addr = party.find("ram:PostalTradeAddress", NS)
    lines = [_t(addr, "ram:LineOne"), _t(addr, "ram:LineTwo"),
             " ".join(x for x in (_t(addr, "ram:PostcodeCode"), _t(addr, "ram:CityName")) if x), _t(addr, "ram:CountryID")]
    # Correo de contacto; si no lo hay, la dirección electrónica (BT-34/BT-49), que en la práctica suele ser un correo.
    email = _t(party, "ram:DefinedTradeContact/ram:EmailURIUniversalCommunication/ram:URIID") or _t(party, "ram:URIUniversalCommunication/ram:URIID")
    return Party(name=_t(party, "ram:Name"), vat=_t(party, "ram:SpecifiedTaxRegistration/ram:ID"), address=[x for x in lines if x], email=email)


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
    lines = tx.findall("ram:IncludedSupplyChainTradeLineItem", NS) if tx is not None else []
    d.line_count = len(lines)
    for line in lines[:MAX_LINES]:
        q = line.find("ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", NS)
        d.lines.append({"descripcion": _t(line, "ram:SpecifiedTradeProduct/ram:Name"), "cantidad": (q.text or "").strip() if q is not None else "",
                        "unidad": q.get("unitCode", "") if q is not None else "",
                        "precio": _t(line, "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount"),
                        "importe": _t(line, "ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount"),
                        "iva": _t(line, "ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/ram:RateApplicablePercent")})
    for tax in (settlement.findall("ram:ApplicableTradeTax", NS)[:MAX_TAXES] if settlement is not None else []):
        d.taxes.append({"categoria": _t(tax, "ram:CategoryCode"), "tipo": _t(tax, "ram:RateApplicablePercent"),
                        "base": _t(tax, "ram:BasisAmount"), "cuota": _t(tax, "ram:CalculatedAmount")})
    summary = "ram:SpecifiedTradeSettlementHeaderMonetarySummation"
    d.net = _t(settlement, f"{summary}/ram:TaxBasisTotalAmount")
    d.allowances, d.charges = _t(settlement, f"{summary}/ram:AllowanceTotalAmount"), _t(settlement, f"{summary}/ram:ChargeTotalAmount")
    d.tax = _t(settlement, f"{summary}/ram:TaxTotalAmount")
    d.total = _t(settlement, f"{summary}/ram:GrandTotalAmount")
    d.prepaid = _t(settlement, f"{summary}/ram:TotalPrepaidAmount")
    d.payable = _t(settlement, f"{summary}/ram:DuePayableAmount")
    d.iban = _t(settlement, "ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeePartyCreditorFinancialAccount/ram:IBANID")
    d.payment_terms = _t(settlement, "ram:SpecifiedTradePaymentTerms/ram:Description")
    d.notes = [(n.text or "").strip() for n in root.findall("rsm:ExchangedDocument/ram:IncludedNote/ram:Content", NS)[:10] if (n.text or "").strip()]
    d.reference = _t(agreement, "ram:BuyerReference")
    d.corrected = _t(settlement, "ram:InvoiceReferencedDocument/ram:IssuerAssignedID")
    return d


def _facturae_tax(tax) -> dict:
    return {"categoria": _pt(tax, "TaxTypeCode"), "tipo": _pt(tax, "TaxRate"), "base": _pt(tax, "TaxableBase/TotalAmount"),
            "cuota": _pt(tax, "TaxAmount/TotalAmount")}


def _facturae_party(node) -> Party:
    """SellerParty o BuyerParty: TaxIdentification y LegalEntity o Individual (nunca sus AdministrativeCentres)."""
    if node is None:
        return Party()
    entity = _p(node, "LegalEntity|Individual")
    if entity is None:
        return Party(vat=_pt(node, "TaxIdentification/TaxIdentificationNumber"))
    if entity.tag.rsplit("}", 1)[-1] == "Individual":
        name = " ".join(x for x in (_pt(entity, "Name"), _pt(entity, "FirstSurname"), _pt(entity, "SecondSurname")) if x)
    else:
        name = _pt(entity, "CorporateName") or _pt(entity, "TradeName")
    addr = _p(entity, "AddressInSpain|OverseasAddress")
    lines = [_pt(addr, "Address"), " ".join(x for x in (_pt(addr, "PostCode") or _pt(addr, "PostCodeAndTown"), _pt(addr, "Town")) if x),
             _pt(addr, "Province"), _pt(addr, "CountryCode")] if addr is not None else []
    return Party(name=name, vat=_pt(node, "TaxIdentification/TaxIdentificationNumber"), address=[x for x in lines if x],
                 email=_pt(entity, "ContactDetails/ElectronicMail"))


def _facturae(root, version: str) -> Detail:
    inv = lectura._facturae(root, version)
    invoices = _kids(_p(root, "Invoices"), "Invoice")
    invoice = invoices[0] if invoices else None
    header = _p(invoice, "InvoiceHeader")
    kind = "rectificativa" if _pt(header, "InvoiceClass") in ("OR", "CR") else "factura"
    d = Detail("facturae", inv.spec, kind, (_pt(header, "InvoiceSeriesCode") + _pt(header, "InvoiceNumber")).strip(),
               _pt(invoice, "InvoiceIssueData/IssueDate"), "", _pt(invoice, "InvoiceIssueData/InvoiceCurrencyCode"),
               _pt(invoice, "InvoiceIssueData/LanguageName"))
    d.invoice_count = max(1, len(invoices))
    parties = _p(root, "Parties")
    d.seller, d.buyer = _facturae_party(_p(parties, "SellerParty")), _facturae_party(_p(parties, "BuyerParty"))
    lines = _kids(_p(invoice, "Items"), "InvoiceLine")
    d.line_count = len(lines)
    for line in lines[:MAX_LINES]:
        d.lines.append({"descripcion": _pt(line, "ItemDescription"), "cantidad": _pt(line, "Quantity"), "unidad": _pt(line, "UnitOfMeasure"),
                        "precio": _pt(line, "UnitPriceWithoutTax"), "importe": _pt(line, "TotalCost"),
                        "iva": _pt(line, "TaxesOutputs/Tax/TaxRate")})  # el IVA, no el IRPF de TaxesWithheld
    d.taxes = [_facturae_tax(t) for t in _kids(_p(invoice, "TaxesOutputs"), "Tax")[:MAX_TAXES]]
    d.withheld = [_facturae_tax(t) for t in _kids(_p(invoice, "TaxesWithheld"), "Tax")[:MAX_TAXES]]
    totals = _p(invoice, "InvoiceTotals")
    d.net, d.tax = _pt(totals, "TotalGrossAmountBeforeTaxes"), _pt(totals, "TotalTaxOutputs")
    d.allowances, d.charges = _pt(totals, "TotalGeneralDiscounts"), _pt(totals, "TotalGeneralSurcharges")
    withheld = _pt(totals, "TotalTaxesWithheld")
    d.withheld_total = withheld if re.sub(r"[0.,\s-]", "", withheld) else ""  # «0.00» no se enseña
    d.total, d.payable = _pt(totals, "InvoiceTotal"), _pt(totals, "TotalExecutableAmount")
    d.prepaid = _pt(totals, "TotalPaymentsOnAccount")
    installment = _p(invoice, "PaymentDetails/Installment")
    d.due = _pt(installment, "InstallmentDueDate")
    d.iban = _pt(installment, "AccountToBeCredited/IBAN")
    corrective = _p(header, "Corrective")
    d.corrected = (_pt(corrective, "InvoiceSeriesCode") + _pt(corrective, "InvoiceNumber")).strip()
    return d


def detail(data: bytes) -> Detail:
    root, inv = lectura.read_invoice(data)
    return detail_of(root, inv)


def detail_of(root, inv) -> Detail:
    if inv.syntax == "ubl":
        return _ubl(root)
    if inv.syntax == "cii":
        return _cii(root)
    return _facturae(root, lectura.facturae_version(root))


LABELS = {
    "es": {"factura": "Factura", "abono": "Factura rectificativa (abono)", "rectificativa": "Factura rectificativa", "number": "Número",
           "date": "Fecha", "due": "Vencimiento", "seller": "Emisor", "buyer": "Cliente", "vat": "NIF", "desc": "Concepto", "qty": "Cantidad",
           "unit": "Unidad", "price": "Precio", "amount": "Importe", "rate": "IVA %", "taxes": "Desglose de impuestos", "withheld": "Retenciones",
           "category": "Categoría", "base": "Base", "quota": "Cuota", "net": "Total sin impuestos", "allowances": "Descuentos",
           "charges": "Recargos", "tax": "Impuestos", "withheld_total": "Retenciones", "total": "Total", "prepaid": "Anticipos",
           "payable": "Importe a pagar", "iban": "IBAN", "terms": "Condiciones de pago", "notes": "Notas", "reference": "Referencia del cliente",
           "corrected": "Rectifica la factura", "spec": "Formato",
           "truncated": "Se muestran {shown} de {total} líneas; el XML incrustado las tiene todas.",
           "batch": "Este archivo contiene {n} facturas; se representa la primera.",
           "footer": "Representación legible de una factura electrónica. El documento con validez es el XML original, incrustado en este PDF sin cambios."},
    "en": {"factura": "Invoice", "abono": "Credit note", "rectificativa": "Corrective invoice", "number": "Number", "date": "Date",
           "due": "Due date", "seller": "Seller", "buyer": "Customer", "vat": "VAT ID", "desc": "Item", "qty": "Quantity", "unit": "Unit",
           "price": "Price", "amount": "Amount", "rate": "VAT %", "taxes": "Tax breakdown", "withheld": "Withholdings", "category": "Category",
           "base": "Taxable amount", "quota": "Tax", "net": "Total without tax", "allowances": "Allowances", "charges": "Charges",
           "tax": "Taxes", "withheld_total": "Withholdings", "total": "Total", "prepaid": "Prepaid", "payable": "Amount due", "iban": "IBAN",
           "terms": "Payment terms", "notes": "Notes", "reference": "Customer reference", "corrected": "Corrects invoice", "spec": "Format",
           "truncated": "Showing {shown} of {total} lines; the embedded XML has all of them.",
           "batch": "This file contains {n} invoices; the first one is represented.",
           "footer": "Human-readable representation of an e-invoice. The legally valid document is the original XML, embedded in this PDF unchanged."},
}


def language_of(d: Detail, locale: str, option: str) -> str:
    """«[El de la factura]» (A.2): Facturae declara su idioma; UBL y CII no, y se usa el de la página."""
    if option in ("es", "en"):
        return option
    lang = (d.language or "").lower()[:2]
    return lang if lang in ("es", "en") else ("en" if locale == "en" else "es")


def warnings(d: Detail, lang: str) -> list[str]:
    """Lo que la representación no enseña entero (también va en la nota del archivo)."""
    t = LABELS[lang]
    out = []
    if d.line_count > len(d.lines):
        out.append(t["truncated"].format(shown=len(d.lines), total=d.line_count))
    if d.invoice_count > 1:
        out.append(t["batch"].format(n=d.invoice_count))
    return out


def render(d: Detail, lang: str, spec_label: str, embedded_name: str) -> str:
    t = LABELS[lang]
    e = html.escape
    cur = f" {e(d.currency)}" if d.currency else ""

    def party(p: Party, label: str) -> str:
        rows = "".join(f"<div>{e(x)}</div>" for x in p.address)
        vat = f"<div>{e(t['vat'])}: {e(p.vat)}</div>" if p.vat else ""
        mail = f"<div>{e(p.email)}</div>" if p.email else ""
        return f"<div class=\"p\"><h3>{e(label)}</h3><div class=\"n\">{e(p.name or '—')}</div>{vat}{rows}{mail}</div>"

    def tax_table(title: str, rows: list[dict]) -> str:
        if not rows:
            return ""
        body = "".join(f"<tr><td>{e(x['categoria'])}</td><td class=\"r\">{e(x['tipo'])}</td><td class=\"r\">{e(x['base'])}</td>"
                       f"<td class=\"r\">{e(x['cuota'])}</td></tr>" for x in rows)
        return (f"<h2>{e(title)}</h2><table class=\"l\"><thead><tr><th>{e(t['category'])}</th><th class=\"r\">%</th>"
                f"<th class=\"r\">{e(t['base'])}</th><th class=\"r\">{e(t['quota'])}</th></tr></thead><tbody>{body}</tbody></table>")

    lines = "".join(
        f"<tr><td>{e(x['descripcion'])}</td><td class=\"r\">{e(x['cantidad'])}</td><td>{e(x['unidad'])}</td>"
        f"<td class=\"r\">{e(x['precio'])}</td><td class=\"r\">{e(x['iva'])}</td><td class=\"r\">{e(x['importe'])}</td></tr>" for x in d.lines)
    meta = [(t["number"], d.number), (t["date"], d.date), (t["due"], d.due), (t["reference"], d.reference), (t["corrected"], d.corrected),
            (t["spec"], spec_label)]
    meta_html = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in meta if v)
    totals = [("net", d.net), ("allowances", d.allowances), ("charges", d.charges), ("tax", d.tax), ("withheld_total", d.withheld_total),
              ("total", d.total), ("prepaid", d.prepaid), ("payable", d.payable)]
    totals_html = "".join(f"<tr{' class=\"g\"' if k == 'payable' else ''}><th>{e(t[k])}</th><td class=\"r\">{e(v)}{cur}</td></tr>"
                          for k, v in totals if v)
    pay = "".join(f"<p><b>{e(k)}:</b> {e(v)}</p>" for k, v in ((t["iban"], d.iban), (t["terms"], d.payment_terms)) if v)
    notes = "".join(f"<p>{e(n)}</p>" for n in d.notes)
    warn = "".join(f"<p class=\"w\">{e(w)}</p>" for w in warnings(d, lang))
    return (f"<!doctype html><html lang=\"{lang}\"><head><meta charset=\"utf-8\"><title>{e(t[d.kind])} {e(d.number)}</title><style>"
            "@page{size:A4;margin:16mm}body{font:10pt/1.45 'Noto Sans','DejaVu Sans',sans-serif;color:#111}"
            "h1{font-size:20pt;margin:0 0 4mm}h2{font-size:12pt;margin:6mm 0 2mm}h3{font-size:9pt;text-transform:uppercase;color:#555;margin:0 0 1mm}"
            ".top{display:flex;justify-content:space-between;gap:8mm}.parties{display:flex;gap:8mm;margin:6mm 0}.p{flex:1;border:1px solid #ccc;"
            "border-radius:2mm;padding:3mm}.n{font-weight:bold}table{border-collapse:collapse;width:100%}th,td{padding:1.5mm 2mm;text-align:left;"
            "vertical-align:top}.l th{background:#f0f0f0;border-bottom:1px solid #999}.l td{border-bottom:1px solid #ddd}.r{text-align:right}"
            ".meta th{color:#555;font-weight:normal;padding-left:0}.tot{width:45%;margin-left:auto;margin-top:4mm}.tot th{font-weight:normal}"
            ".tot .g th,.tot .g td{font-weight:bold;border-top:1px solid #111}footer{margin-top:10mm;color:#666;font-size:8pt}"
            ".w{border:1px solid #bf8700;background:#fff8c5;padding:2mm 3mm}"
            "</style></head><body>"
            f"<div class=\"top\"><div><h1>{e(t[d.kind])}</h1></div><table class=\"meta\" style=\"width:auto\">{meta_html}</table></div>{warn}"
            f"<div class=\"parties\">{party(d.seller, t['seller'])}{party(d.buyer, t['buyer'])}</div>"
            f"<table class=\"l\"><thead><tr><th>{e(t['desc'])}</th><th class=\"r\">{e(t['qty'])}</th><th>{e(t['unit'])}</th>"
            f"<th class=\"r\">{e(t['price'])}</th><th class=\"r\">{e(t['rate'])}</th><th class=\"r\">{e(t['amount'])}</th></tr></thead><tbody>{lines}</tbody></table>"
            + tax_table(t["taxes"], d.taxes) + tax_table(t["withheld"], d.withheld)
            + f"<table class=\"tot\">{totals_html}</table>{pay}"
            + (f"<h2>{e(t['notes'])}</h2>{notes}" if notes else "")
            + f"<footer>{e(t['footer'])} ({e(embedded_name)})</footer></body></html>")
