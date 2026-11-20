"""crear-factura-electronica (A.2 y 7.23, F4-E2, D-205): XML de la factura a partir del formulario EN 16931.

- CII D16B: Factur-X/ZUGFeRD por perfil (MINIMUM, BASIC WL, BASIC, EN 16931, EXTENDED, XRECHNUNG) y XRechnung CII.
- UBL 2.1: EN 16931 (la sintaxis de la solución pública española), Peppol BIS Billing 3.0 y XRechnung UBL.
- Facturae 3.2.2, sin firmar (la firma XAdES-EPES se hace en el navegador, con el certificado del usuario).

Los importes son los de crear-factura (`calcular`, igual que `client-tools/src/invoice-calc.ts`): cada importe a céntimos
y la cuota de cada tipo sobre la suma de sus bases (EN 16931). El recargo de equivalencia y la retención de IRPF no
existen en EN 16931: solo se admiten en Facturae. Se generan con lxml sin plantillas ni bibliotecas nuevas; el resultado
pasa por el mismo motor que validar-factura-electronica (XSD y KoSIT, o el XSD de Facturae) antes de entregarse.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from lxml import etree

from core.errors import ErrorCode, ToolError

RSM = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
UDT = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"
QDT = "urn:un:unece:uncefact:data:standard:QualifiedDataType:100"
UBL = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
FE = "http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_2.xml"
DS = "http://www.w3.org/2000/09/xmldsig#"

XRECHNUNG = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
PEPPOL = "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
PEPPOL_PROFILE = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
GUIDELINES = {
    "minimum": "urn:factur-x.eu:1p0:minimum",
    "basicwl": "urn:factur-x.eu:1p0:basicwl",
    "basic": "urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic",
    "en16931": "urn:cen.eu:en16931:2017",
    "extended": "urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended",
    "xrechnung": XRECHNUNG,
}
# Unidades (UN/ECE Rec. 20) y su código de Facturae.
UNITS = {"ud": ("C62", "01"), "u": ("C62", "01"), "unidad": ("C62", "01"), "unidades": ("C62", "01"), "pcs": ("C62", "01"),
         "h": ("HUR", "02"), "hora": ("HUR", "02"), "horas": ("HUR", "02"), "kg": ("KGM", "03"), "l": ("LTR", "04"),
         "litro": ("LTR", "04"), "m": ("MTR", "05"), "m2": ("MTK", "05"), "día": ("DAY", "05"), "dia": ("DAY", "05"),
         "días": ("DAY", "05"), "mes": ("MON", "05"), "meses": ("MON", "05"), "caja": ("XBX", "06"), "km": ("KMT", "05")}
# UNTDID 4461 → Facturae (PaymentMeans).
PAYMENT_FACTURAE = {"10": "01", "30": "04", "58": "04", "59": "02", "48": "19", "54": "19", "55": "19", "49": "02", "1": "05"}
ISO3 = {"ES": "ESP", "PT": "PRT", "FR": "FRA", "DE": "DEU", "IT": "ITA", "NL": "NLD", "BE": "BEL", "AT": "AUT", "IE": "IRL",
        "LU": "LUX", "GB": "GBR", "CH": "CHE", "AD": "AND", "US": "USA", "MX": "MEX", "AR": "ARG", "CO": "COL", "CL": "CHL",
        "PL": "POL", "SE": "SWE", "DK": "DNK", "FI": "FIN", "NO": "NOR", "CZ": "CZE", "GR": "GRC", "RO": "ROU", "HU": "HUN"}


def d2(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(value) -> str:
    return f"{d2(value):.2f}"


def qty(value) -> str:
    q = Decimal(str(value)).normalize()
    return format(q, "f")


def price(value) -> str:
    p = Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP).normalize()
    text = format(p, "f")
    return text if "." in text else text + ".00"


@dataclass
class Group:
    rate: Decimal
    category: str
    base: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    surcharge_rate: Decimal = Decimal("0")
    surcharge: Decimal = Decimal("0")


@dataclass
class Totals:
    lines: list[tuple[Decimal, Decimal, Decimal]] = field(default_factory=list)  # bruto, descuento, neto
    groups: list[Group] = field(default_factory=list)
    net: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    surcharge: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    irpf: Decimal = Decimal("0")
    payable: Decimal = Decimal("0")


SURCHARGE = {Decimal("21"): Decimal("5.2"), Decimal("10"): Decimal("1.4"), Decimal("5"): Decimal("0.62"), Decimal("4"): Decimal("0.5"),
             Decimal("2"): Decimal("0.26"), Decimal("0"): Decimal("0")}


def calcular(f) -> Totals:
    """Los mismos totales que crear-factura (EN 16931), con Decimal."""
    t = Totals()
    groups: dict[Decimal, Group] = {}
    for line in f.lineas:
        gross = d2(Decimal(str(line.cantidad)) * Decimal(str(line.precio)))
        disc = d2(gross * Decimal(str(line.descuento)) / 100)
        net = d2(gross - disc)
        t.lines.append((gross, disc, net))
        rate = Decimal(str(line.iva))
        if rate == rate.to_integral_value():
            rate = rate.quantize(Decimal(1))  # 21.0 → 21
        g = groups.setdefault(rate, Group(rate=rate, category="S" if rate > 0 else "E"))
        g.base = d2(g.base + net)
    for rate in sorted(groups, reverse=True):
        g = groups[rate]
        g.tax = d2(g.base * rate / 100)
        if f.recargo:
            g.surcharge_rate = SURCHARGE.get(rate, Decimal("0"))
            g.surcharge = d2(g.base * g.surcharge_rate / 100)
        t.groups.append(g)
    t.net = d2(sum((n for _, _, n in t.lines), Decimal("0")))
    t.tax = d2(sum((g.tax for g in t.groups), Decimal("0")))
    t.surcharge = d2(sum((g.surcharge for g in t.groups), Decimal("0")))
    t.total = d2(t.net + t.tax + t.surcharge)
    t.irpf = d2(t.net * Decimal(str(f.irpf)) / 100)
    t.payable = d2(t.total - t.irpf)
    return t


def unit_codes(unit: str) -> tuple[str, str]:
    """Código UN/ECE Rec. 20 y de Facturae de la unidad («h» → HUR y 02); un código de Rec. 20 escrito tal cual vale."""
    u = (unit or "").strip().rstrip(".")
    by_code = {code: fc for code, fc in UNITS.values()}
    if u.upper() in by_code and len(u) == 3 and u.isupper():
        return u, by_code[u]
    return UNITS.get(u.lower(), ("C62", "01"))


def vat_id(country: str, tax_id: str) -> str:
    tid = "".join(tax_id.split()).upper()
    return tid if tid[:2].isalpha() and tid[:2] == country.upper() else f"{country.upper()}{tid}"


def problems(f, fmt: str, profile: str) -> list[str]:
    """Lo que el formato necesita y el formulario no trae (los textos, en la página y en errors.py)."""
    out: list[str] = []
    if not f.numero.strip():
        out.append("einvoice_number")
    if not f.lineas or any(not line.descripcion.strip() for line in f.lineas):
        out.append("einvoice_lines")
    eu = fmt != "facturae"
    if eu and f.recargo:
        out.append("einvoice_surcharge")
    if eu and f.irpf:
        out.append("einvoice_irpf")
    xr = fmt in ("xrechnung_cii", "xrechnung_ubl") or (fmt == "facturx" and profile == "xrechnung")
    if xr:
        if not f.referencia_comprador.strip():
            out.append("einvoice_buyer_reference")
        if not (f.emisor.contacto.strip() and f.emisor.telefono.strip() and f.emisor.correo.strip()):
            out.append("einvoice_seller_contact")
        for p in (f.emisor, f.cliente):
            if not (p.ciudad.strip() and p.cp.strip()):
                out.append("einvoice_address")
                break
    if xr or fmt == "peppol":
        if not (f.emisor.endpoint_id.strip() and f.cliente.endpoint_id.strip()):
            out.append("einvoice_endpoint")
    if fmt == "peppol" and any(p.endpoint_esquema.strip().upper() == "EM" for p in (f.emisor, f.cliente)):
        out.append("einvoice_endpoint_scheme")  # Peppol no admite el correo como dirección electrónica
    if fmt == "peppol" and not (f.referencia_comprador.strip() or f.pedido.strip()):
        out.append("einvoice_buyer_reference")
    if any(line.iva == 0 for line in f.lineas) and not f.motivo_exencion.strip():
        out.append("einvoice_exemption")
    if fmt == "facturae":
        if not f.emisor.nif.strip() or not f.cliente.nif.strip():
            out.append("einvoice_facturae_nif")
        if f.moneda != "EUR":
            out.append("einvoice_facturae_currency")
    if not f.emisor.nif.strip():
        out.append("einvoice_seller_vat")
    return sorted(set(out))


def _e(parent, ns: str, tag: str, text=None, **attrs):
    el = etree.SubElement(parent, f"{{{ns}}}{tag}", {k: v for k, v in attrs.items() if v is not None})
    if text is not None:
        el.text = str(text)
    return el


def _date102(iso: str) -> str:
    return iso.replace("-", "")


# --- CII ------------------------------------------------------------------------------------------------------------


def _cii_party(parent, tag: str, p, seller: bool, profile: str):
    party = _e(parent, RAM, tag)
    _e(party, RAM, "Name", p.nombre.strip())
    minimum = profile == "minimum"
    # El contacto del vendedor (BG-6) no existe en MINIMUM, BASIC WL ni BASIC.
    if profile not in ("minimum", "basicwl", "basic") and (p.contacto.strip() or p.telefono.strip() or p.correo.strip()) and seller:
        contact = _e(party, RAM, "DefinedTradeContact")
        if p.contacto.strip():
            _e(contact, RAM, "PersonName", p.contacto.strip())
        if p.telefono.strip():
            _e(_e(contact, RAM, "TelephoneUniversalCommunication"), RAM, "CompleteNumber", p.telefono.strip())
        if p.correo.strip():
            _e(_e(contact, RAM, "EmailURIUniversalCommunication"), RAM, "URIID", p.correo.strip())
    if seller or not minimum:
        addr = _e(party, RAM, "PostalTradeAddress")
        if not minimum:
            if p.cp.strip():
                _e(addr, RAM, "PostcodeCode", p.cp.strip())
            if p.direccion.strip():
                _e(addr, RAM, "LineOne", p.direccion.strip())
            if p.ciudad.strip():
                _e(addr, RAM, "CityName", p.ciudad.strip())
        _e(addr, RAM, "CountryID", p.pais.upper())
    if not minimum and p.endpoint_id.strip():
        _e(_e(party, RAM, "URIUniversalCommunication"), RAM, "URIID", p.endpoint_id.strip(), schemeID=p.endpoint_esquema.strip() or "EM")
    if p.nif.strip() and (seller or not minimum):
        _e(_e(party, RAM, "SpecifiedTaxRegistration"), RAM, "ID", vat_id(p.pais, p.nif), schemeID="VA")
    return party


def cii(f, profile: str) -> bytes:
    t = calcular(f)
    root = etree.Element(f"{{{RSM}}}CrossIndustryInvoice", nsmap={"rsm": RSM, "ram": RAM, "udt": UDT, "qdt": QDT})
    ctx = _e(root, RSM, "ExchangedDocumentContext")
    if profile == "xrechnung":
        _e(_e(ctx, RAM, "BusinessProcessSpecifiedDocumentContextParameter"), RAM, "ID", PEPPOL_PROFILE)
    _e(_e(ctx, RAM, "GuidelineSpecifiedDocumentContextParameter"), RAM, "ID", GUIDELINES[profile])
    doc = _e(root, RSM, "ExchangedDocument")
    _e(doc, RAM, "ID", f.numero.strip())
    _e(doc, RAM, "TypeCode", "380")
    _e(_e(doc, RAM, "IssueDateTime"), UDT, "DateTimeString", _date102(f.fecha), format="102")
    if f.notas.strip() and profile not in ("minimum",):
        _e(_e(doc, RAM, "IncludedNote"), RAM, "Content", f.notas.strip())
    tx = _e(root, RSM, "SupplyChainTradeTransaction")
    with_lines = profile not in ("minimum", "basicwl")
    if with_lines:
        for i, (line, (gross, disc, net)) in enumerate(zip(f.lineas, t.lines), 1):
            item = _e(tx, RAM, "IncludedSupplyChainTradeLineItem")
            _e(_e(item, RAM, "AssociatedDocumentLineDocument"), RAM, "LineID", str(i))
            _e(_e(item, RAM, "SpecifiedTradeProduct"), RAM, "Name", line.descripcion.strip())
            agreement = _e(item, RAM, "SpecifiedLineTradeAgreement")
            _e(_e(agreement, RAM, "NetPriceProductTradePrice"), RAM, "ChargeAmount", price(line.precio))
            _e(_e(item, RAM, "SpecifiedLineTradeDelivery"), RAM, "BilledQuantity", qty(line.cantidad), unitCode=unit_codes(line.unidad)[0])
            settle = _e(item, RAM, "SpecifiedLineTradeSettlement")
            tax = _e(settle, RAM, "ApplicableTradeTax")
            _e(tax, RAM, "TypeCode", "VAT")
            _e(tax, RAM, "CategoryCode", "S" if line.iva > 0 else "E")
            _e(tax, RAM, "RateApplicablePercent", qty(line.iva))
            if disc:
                ac = _e(settle, RAM, "SpecifiedTradeAllowanceCharge")
                _e(_e(ac, RAM, "ChargeIndicator"), UDT, "Indicator", "false")
                _e(ac, RAM, "ActualAmount", money(disc))
                _e(ac, RAM, "Reason", f.texto_descuento)
            _e(_e(settle, RAM, "SpecifiedTradeSettlementLineMonetarySummation"), RAM, "LineTotalAmount", money(net))
    agreement = _e(tx, RAM, "ApplicableHeaderTradeAgreement")
    if f.referencia_comprador.strip():
        _e(agreement, RAM, "BuyerReference", f.referencia_comprador.strip())
    _cii_party(agreement, "SellerTradeParty", f.emisor, True, profile)
    _cii_party(agreement, "BuyerTradeParty", f.cliente, False, profile)
    if f.pedido.strip() and profile != "minimum":
        _e(_e(agreement, RAM, "BuyerOrderReferencedDocument"), RAM, "IssuerAssignedID", f.pedido.strip())
    delivery = _e(tx, RAM, "ApplicableHeaderTradeDelivery")
    if f.fecha_operacion and profile != "minimum":  # BT-72; sin ella el bloque va vacío (aviso del Schematron)
        event = _e(delivery, RAM, "ActualDeliverySupplyChainEvent")
        _e(_e(event, RAM, "OccurrenceDateTime"), UDT, "DateTimeString", _date102(f.fecha_operacion), format="102")
    settle = _e(tx, RAM, "ApplicableHeaderTradeSettlement")
    _e(settle, RAM, "InvoiceCurrencyCode", f.moneda)
    if profile != "minimum":
        if f.forma_pago:
            means = _e(settle, RAM, "SpecifiedTradeSettlementPaymentMeans")
            _e(means, RAM, "TypeCode", f.forma_pago)
            if f.iban.strip() and f.forma_pago in ("30", "58"):
                _e(_e(means, RAM, "PayeePartyCreditorFinancialAccount"), RAM, "IBANID", "".join(f.iban.split()).upper())
        for g in t.groups:
            tax = _e(settle, RAM, "ApplicableTradeTax")
            _e(tax, RAM, "CalculatedAmount", money(g.tax))
            _e(tax, RAM, "TypeCode", "VAT")
            if g.category == "E":
                _e(tax, RAM, "ExemptionReason", f.motivo_exencion.strip())
            _e(tax, RAM, "BasisAmount", money(g.base))
            _e(tax, RAM, "CategoryCode", g.category)
            _e(tax, RAM, "RateApplicablePercent", qty(g.rate))
        if f.vencimiento or f.condiciones_pago.strip():
            terms = _e(settle, RAM, "SpecifiedTradePaymentTerms")
            if f.condiciones_pago.strip():
                _e(terms, RAM, "Description", f.condiciones_pago.strip())
            if f.vencimiento:
                _e(_e(terms, RAM, "DueDateDateTime"), UDT, "DateTimeString", _date102(f.vencimiento), format="102")
    sums = _e(settle, RAM, "SpecifiedTradeSettlementHeaderMonetarySummation")
    if profile != "minimum":
        _e(sums, RAM, "LineTotalAmount", money(t.net))
    _e(sums, RAM, "TaxBasisTotalAmount", money(t.net))
    _e(sums, RAM, "TaxTotalAmount", money(t.tax), currencyID=f.moneda)
    _e(sums, RAM, "GrandTotalAmount", money(t.total))
    _e(sums, RAM, "DuePayableAmount", money(t.payable))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# --- UBL ------------------------------------------------------------------------------------------------------------


def _ubl_party(parent, tag: str, p, seller: bool):
    party = _e(_e(parent, CAC, tag), CAC, "Party")
    if p.endpoint_id.strip():
        _e(party, CBC, "EndpointID", p.endpoint_id.strip(), schemeID=p.endpoint_esquema.strip() or "EM")
    addr = _e(party, CAC, "PostalAddress")
    if p.direccion.strip():
        _e(addr, CBC, "StreetName", p.direccion.strip())
    if p.ciudad.strip():
        _e(addr, CBC, "CityName", p.ciudad.strip())
    if p.cp.strip():
        _e(addr, CBC, "PostalZone", p.cp.strip())
    _e(_e(addr, CAC, "Country"), CBC, "IdentificationCode", p.pais.upper())
    if p.nif.strip():
        scheme = _e(party, CAC, "PartyTaxScheme")
        _e(scheme, CBC, "CompanyID", vat_id(p.pais, p.nif))
        _e(_e(scheme, CAC, "TaxScheme"), CBC, "ID", "VAT")
    _e(_e(party, CAC, "PartyLegalEntity"), CBC, "RegistrationName", p.nombre.strip())
    if seller and (p.contacto.strip() or p.telefono.strip() or p.correo.strip()):
        contact = _e(party, CAC, "Contact")
        for tag2, value in (("Name", p.contacto), ("Telephone", p.telefono), ("ElectronicMail", p.correo)):
            if value.strip():
                _e(contact, CBC, tag2, value.strip())


def ubl(f, customization: str, profile_id: str | None) -> bytes:
    t = calcular(f)
    root = etree.Element(f"{{{UBL}}}Invoice", nsmap={None: UBL, "cac": CAC, "cbc": CBC})
    _e(root, CBC, "CustomizationID", customization)
    if profile_id:
        _e(root, CBC, "ProfileID", profile_id)
    _e(root, CBC, "ID", f.numero.strip())
    _e(root, CBC, "IssueDate", f.fecha)
    if f.vencimiento:
        _e(root, CBC, "DueDate", f.vencimiento)
    _e(root, CBC, "InvoiceTypeCode", "380")
    if f.notas.strip():
        _e(root, CBC, "Note", f.notas.strip())
    _e(root, CBC, "DocumentCurrencyCode", f.moneda)
    if f.referencia_comprador.strip():
        _e(root, CBC, "BuyerReference", f.referencia_comprador.strip())
    if f.pedido.strip():
        _e(_e(root, CAC, "OrderReference"), CBC, "ID", f.pedido.strip())
    _ubl_party(root, "AccountingSupplierParty", f.emisor, True)
    _ubl_party(root, "AccountingCustomerParty", f.cliente, False)
    if f.fecha_operacion:
        _e(_e(root, CAC, "Delivery"), CBC, "ActualDeliveryDate", f.fecha_operacion)
    if f.forma_pago:
        means = _e(root, CAC, "PaymentMeans")
        _e(means, CBC, "PaymentMeansCode", f.forma_pago)
        if f.iban.strip() and f.forma_pago in ("30", "58"):
            _e(_e(means, CAC, "PayeeFinancialAccount"), CBC, "ID", "".join(f.iban.split()).upper())
    if f.condiciones_pago.strip():
        _e(_e(root, CAC, "PaymentTerms"), CBC, "Note", f.condiciones_pago.strip())
    total = _e(root, CAC, "TaxTotal")
    _e(total, CBC, "TaxAmount", money(t.tax), currencyID=f.moneda)
    for g in t.groups:
        sub = _e(total, CAC, "TaxSubtotal")
        _e(sub, CBC, "TaxableAmount", money(g.base), currencyID=f.moneda)
        _e(sub, CBC, "TaxAmount", money(g.tax), currencyID=f.moneda)
        cat = _e(sub, CAC, "TaxCategory")
        _e(cat, CBC, "ID", g.category)
        _e(cat, CBC, "Percent", qty(g.rate))
        if g.category == "E":
            _e(cat, CBC, "TaxExemptionReason", f.motivo_exencion.strip())
        _e(_e(cat, CAC, "TaxScheme"), CBC, "ID", "VAT")
    sums = _e(root, CAC, "LegalMonetaryTotal")
    _e(sums, CBC, "LineExtensionAmount", money(t.net), currencyID=f.moneda)
    _e(sums, CBC, "TaxExclusiveAmount", money(t.net), currencyID=f.moneda)
    _e(sums, CBC, "TaxInclusiveAmount", money(t.total), currencyID=f.moneda)
    _e(sums, CBC, "PayableAmount", money(t.payable), currencyID=f.moneda)
    for i, (line, (gross, disc, net)) in enumerate(zip(f.lineas, t.lines), 1):
        el = _e(root, CAC, "InvoiceLine")
        _e(el, CBC, "ID", str(i))
        _e(el, CBC, "InvoicedQuantity", qty(line.cantidad), unitCode=unit_codes(line.unidad)[0])
        _e(el, CBC, "LineExtensionAmount", money(net), currencyID=f.moneda)
        if disc:
            ac = _e(el, CAC, "AllowanceCharge")
            _e(ac, CBC, "ChargeIndicator", "false")
            _e(ac, CBC, "AllowanceChargeReason", f.texto_descuento)
            _e(ac, CBC, "Amount", money(disc), currencyID=f.moneda)
        item = _e(el, CAC, "Item")
        _e(item, CBC, "Name", line.descripcion.strip())
        cat = _e(item, CAC, "ClassifiedTaxCategory")
        _e(cat, CBC, "ID", "S" if line.iva > 0 else "E")
        _e(cat, CBC, "Percent", qty(line.iva))
        _e(_e(cat, CAC, "TaxScheme"), CBC, "ID", "VAT")
        _e(_e(el, CAC, "Price"), CBC, "PriceAmount", price(line.precio), currencyID=f.moneda)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# --- Facturae 3.2.2 ---------------------------------------------------------------------------------------------------


def _is_company(tax_id: str) -> bool:
    tid = "".join(tax_id.split()).upper()
    if tid.startswith("ES") and len(tid) == 11:
        tid = tid[2:]
    return bool(tid) and tid[0] in "ABCDEFGHJNPQRSUVW"


def _facturae_party(parent, tag: str, p):
    party = etree.SubElement(parent, tag)
    tax = etree.SubElement(party, "TaxIdentification")
    company = _is_company(p.nif)
    etree.SubElement(tax, "PersonTypeCode").text = "J" if company else "F"
    etree.SubElement(tax, "ResidenceTypeCode").text = "R" if p.pais.upper() == "ES" else ("U" if p.pais.upper() in ISO3 and p.pais.upper() not in ("US", "MX", "AR", "CO", "CL", "CH", "NO", "GB", "AD") else "E")
    etree.SubElement(tax, "TaxIdentificationNumber").text = vat_id(p.pais, p.nif)[:30]
    if company:
        holder = etree.SubElement(party, "LegalEntity")
        etree.SubElement(holder, "CorporateName").text = p.nombre.strip()[:80]
    else:
        holder = etree.SubElement(party, "Individual")
        parts = p.nombre.split()
        etree.SubElement(holder, "Name").text = (parts[0] if parts else p.nombre)[:40]
        etree.SubElement(holder, "FirstSurname").text = (" ".join(parts[1:2]) or "-")[:40]
        if len(parts) > 2:
            etree.SubElement(holder, "SecondSurname").text = " ".join(parts[2:])[:40]
    if p.pais.upper() == "ES":
        addr = etree.SubElement(holder, "AddressInSpain")
        etree.SubElement(addr, "Address").text = (p.direccion.strip() or "-")[:80]
        etree.SubElement(addr, "PostCode").text = (p.cp.strip() or "00000")[:5]
        etree.SubElement(addr, "Town").text = (p.ciudad.strip() or "-")[:50]
        etree.SubElement(addr, "Province").text = (p.provincia.strip() or p.ciudad.strip() or "-")[:20]
        etree.SubElement(addr, "CountryCode").text = "ESP"
    else:
        addr = etree.SubElement(holder, "OverseasAddress")
        etree.SubElement(addr, "Address").text = (p.direccion.strip() or "-")[:80]
        etree.SubElement(addr, "PostCodeAndTown").text = (f"{p.cp} {p.ciudad}".strip() or "-")[:50]
        etree.SubElement(addr, "Province").text = (p.provincia.strip() or p.ciudad.strip() or "-")[:20]
        etree.SubElement(addr, "CountryCode").text = ISO3.get(p.pais.upper(), "ESP")
    if p.correo.strip():
        contact = etree.SubElement(holder, "ContactDetails")
        if p.telefono.strip():
            etree.SubElement(contact, "Telephone").text = p.telefono.strip()[:15]
        etree.SubElement(contact, "ElectronicMail").text = p.correo.strip()[:60]


def _amount(parent, tag: str, value):
    el = etree.SubElement(parent, tag)
    etree.SubElement(el, "TotalAmount").text = money(value)
    return el


def facturae(f) -> bytes:
    t = calcular(f)
    root = etree.Element(f"{{{FE}}}Facturae", nsmap={"fe": FE, "ds": DS})
    header = etree.SubElement(root, "FileHeader")
    etree.SubElement(header, "SchemaVersion").text = "3.2.2"
    etree.SubElement(header, "Modality").text = "I"
    etree.SubElement(header, "InvoiceIssuerType").text = "EM"
    batch = etree.SubElement(header, "Batch")
    etree.SubElement(batch, "BatchIdentifier").text = (vat_id(f.emisor.pais, f.emisor.nif) + f.numero.strip())[:70]
    etree.SubElement(batch, "InvoicesCount").text = "1"
    for tag in ("TotalInvoicesAmount", "TotalOutstandingAmount", "TotalExecutableAmount"):
        _amount(batch, tag, t.total if tag == "TotalInvoicesAmount" else t.payable)
    etree.SubElement(batch, "InvoiceCurrencyCode").text = "EUR"
    parties = etree.SubElement(root, "Parties")
    _facturae_party(parties, "SellerParty", f.emisor)
    _facturae_party(parties, "BuyerParty", f.cliente)
    inv = etree.SubElement(etree.SubElement(root, "Invoices"), "Invoice")
    ih = etree.SubElement(inv, "InvoiceHeader")
    number = f.numero.strip()
    series = ""
    if "/" in number:
        series, number = number.rsplit("/", 1)
    etree.SubElement(ih, "InvoiceNumber").text = number[:20]
    if series:
        etree.SubElement(ih, "InvoiceSeriesCode").text = series[:20]
    etree.SubElement(ih, "InvoiceDocumentType").text = "FC"
    etree.SubElement(ih, "InvoiceClass").text = "OO"
    data = etree.SubElement(inv, "InvoiceIssueData")
    etree.SubElement(data, "IssueDate").text = f.fecha
    if f.fecha_operacion:
        etree.SubElement(data, "OperationDate").text = f.fecha_operacion
    etree.SubElement(data, "InvoiceCurrencyCode").text = "EUR"
    etree.SubElement(data, "TaxCurrencyCode").text = "EUR"
    etree.SubElement(data, "LanguageName").text = f.idioma
    outputs = etree.SubElement(inv, "TaxesOutputs")
    for g in t.groups:
        tax = etree.SubElement(outputs, "Tax")
        etree.SubElement(tax, "TaxTypeCode").text = "01"
        etree.SubElement(tax, "TaxRate").text = money(g.rate)
        _amount(tax, "TaxableBase", g.base)
        _amount(tax, "TaxAmount", g.tax)
        if g.surcharge_rate:
            etree.SubElement(tax, "EquivalenceSurcharge").text = money(g.surcharge_rate)
            _amount(tax, "EquivalenceSurchargeAmount", g.surcharge)
    if t.irpf:
        withheld = etree.SubElement(etree.SubElement(inv, "TaxesWithheld"), "Tax")
        etree.SubElement(withheld, "TaxTypeCode").text = "04"
        etree.SubElement(withheld, "TaxRate").text = money(f.irpf)
        _amount(withheld, "TaxableBase", t.net)
        _amount(withheld, "TaxAmount", t.irpf)
    totals = etree.SubElement(inv, "InvoiceTotals")
    etree.SubElement(totals, "TotalGrossAmount").text = money(t.net)
    etree.SubElement(totals, "TotalGrossAmountBeforeTaxes").text = money(t.net)
    etree.SubElement(totals, "TotalTaxOutputs").text = money(t.tax + t.surcharge)
    etree.SubElement(totals, "TotalTaxesWithheld").text = money(t.irpf)
    etree.SubElement(totals, "InvoiceTotal").text = money(t.payable)
    etree.SubElement(totals, "TotalOutstandingAmount").text = money(t.payable)
    etree.SubElement(totals, "TotalExecutableAmount").text = money(t.payable)
    items = etree.SubElement(inv, "Items")
    for line, (gross, disc, net) in zip(f.lineas, t.lines):
        el = etree.SubElement(items, "InvoiceLine")
        etree.SubElement(el, "ItemDescription").text = line.descripcion.strip()[:2500]
        etree.SubElement(el, "Quantity").text = qty(line.cantidad)
        etree.SubElement(el, "UnitOfMeasure").text = unit_codes(line.unidad)[1]
        etree.SubElement(el, "UnitPriceWithoutTax").text = f"{Decimal(str(line.precio)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP):.6f}"
        etree.SubElement(el, "TotalCost").text = f"{gross:.6f}"
        if disc:
            d = etree.SubElement(etree.SubElement(el, "DiscountsAndRebates"), "Discount")
            etree.SubElement(d, "DiscountReason").text = f.texto_descuento[:2500]
            etree.SubElement(d, "DiscountRate").text = f"{Decimal(str(line.descuento)):.4f}"
            etree.SubElement(d, "DiscountAmount").text = f"{disc:.6f}"
        etree.SubElement(el, "GrossAmount").text = f"{net:.6f}"
        lt = etree.SubElement(etree.SubElement(el, "TaxesOutputs"), "Tax")
        etree.SubElement(lt, "TaxTypeCode").text = "01"
        etree.SubElement(lt, "TaxRate").text = money(line.iva)
        _amount(lt, "TaxableBase", net)
        rate = Decimal(str(line.iva))
        if f.recargo and SURCHARGE.get(rate):
            etree.SubElement(lt, "EquivalenceSurcharge").text = money(SURCHARGE[rate])
    if f.forma_pago and (f.vencimiento or f.iban.strip()):
        inst = etree.SubElement(etree.SubElement(inv, "PaymentDetails"), "Installment")
        etree.SubElement(inst, "InstallmentDueDate").text = f.vencimiento or f.fecha
        etree.SubElement(inst, "InstallmentAmount").text = money(t.payable)
        etree.SubElement(inst, "PaymentMeans").text = PAYMENT_FACTURAE.get(f.forma_pago, "13")
        if f.iban.strip() and f.forma_pago in ("30", "58"):
            etree.SubElement(etree.SubElement(inst, "AccountToBeCredited"), "IBAN").text = "".join(f.iban.split()).upper()
    note = " ".join(x for x in (f.notas.strip(), f.motivo_exencion.strip() if any(line.iva == 0 for line in f.lineas) else "") if x)
    if note:
        etree.SubElement(etree.SubElement(inv, "AdditionalData"), "InvoiceAdditionalInformation").text = note[:2500]
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def build(f, fmt: str, profile: str) -> tuple[bytes, str]:
    """El XML y la sintaxis («cii», «ubl» o «facturae»)."""
    issues = problems(f, fmt, profile)
    if issues:
        raise ToolError(ErrorCode.INVALID_OPTIONS, issues[0])
    if fmt == "facturx":
        return cii(f, profile), "cii"
    if fmt == "xrechnung_cii":
        return cii(f, "xrechnung"), "cii"
    if fmt == "xrechnung_ubl":
        return ubl(f, XRECHNUNG, PEPPOL_PROFILE), "ubl"
    if fmt == "peppol":
        return ubl(f, PEPPOL, PEPPOL_PROFILE), "ubl"
    if fmt == "ubl":
        return ubl(f, GUIDELINES["en16931"], None), "ubl"
    if fmt == "facturae":
        return facturae(f), "facturae"
    raise ToolError(ErrorCode.INVALID_OPTIONS, f"formato:{fmt}")
