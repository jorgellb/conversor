"""crear-factura-electronica (A.2 y 7.23, F4-E2, D-205 y D-209): XML de la factura a partir del formulario EN 16931.

- CII D16B: Factur-X/ZUGFeRD por perfil (MINIMUM, BASIC WL, BASIC, EN 16931, EXTENDED, XRECHNUNG) y XRechnung CII.
- UBL 2.1: EN 16931 (la sintaxis de la solución pública española), Peppol BIS Billing 3.0 y XRechnung UBL.
- Facturae 3.2.2, sin firmar (la firma XAdES-EPES se hace en el navegador, con el certificado del usuario).

Los importes son los de crear-factura (`calcular`, igual que `client-tools/src/invoice-calc.ts`): cada importe a céntimos
y la cuota de cada tipo sobre la suma de sus bases (EN 16931). El recargo de equivalencia y la retención de IRPF no
existen en EN 16931: solo se admiten en Facturae. `problems` dice antes de generar lo que cada formato exige, con textos
propios (`einvoice_*`), para que el usuario no reciba la regla del validador en inglés o en alemán; nada se recorta ni se
inventa en silencio. El resultado pasa por el mismo motor que validar-factura-electronica antes de entregarse.
"""
from __future__ import annotations

import re
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
# Unidades: código UN/ECE Rec. 20 y el de Facturae (01 unidades, 02 horas, 03 kg, 04 litros, 05 otros, 16 cm, 21 g,
# 22 km, 25 metros, 26 mm, 36 kWh...).
UNITS = {"ud": ("C62", "01"), "u": ("C62", "01"), "unidad": ("C62", "01"), "unidades": ("C62", "01"), "pcs": ("C62", "01"),
         "h": ("HUR", "02"), "hora": ("HUR", "02"), "horas": ("HUR", "02"), "kg": ("KGM", "03"), "l": ("LTR", "04"),
         "litro": ("LTR", "04"), "litros": ("LTR", "04"), "m": ("MTR", "25"), "metro": ("MTR", "25"), "metros": ("MTR", "25"),
         "km": ("KMT", "22"), "cm": ("CMT", "16"), "mm": ("MMT", "26"), "g": ("GRM", "21"), "kwh": ("KWH", "36"),
         "m2": ("MTK", "05"), "m3": ("MTQ", "33"), "día": ("DAY", "05"), "dia": ("DAY", "05"), "días": ("DAY", "05"),
         "mes": ("MON", "05"), "meses": ("MON", "05"), "caja": ("XBX", "06"), "docena": ("DZN", "18")}
# UNTDID 4461 → Facturae (PaymentMeans).
PAYMENT_FACTURAE = {"10": "01", "30": "04", "58": "04", "48": "19"}
EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL",
      "PT", "RO", "SK", "SI", "ES", "SE"}
ISO3 = {"ES": "ESP", "PT": "PRT", "FR": "FRA", "DE": "DEU", "IT": "ITA", "NL": "NLD", "BE": "BEL", "AT": "AUT", "IE": "IRL",
        "LU": "LUX", "GB": "GBR", "CH": "CHE", "AD": "AND", "US": "USA", "MX": "MEX", "AR": "ARG", "CO": "COL", "CL": "CHL",
        "PL": "POL", "SE": "SWE", "DK": "DNK", "FI": "FIN", "NO": "NOR", "CZ": "CZE", "GR": "GRC", "RO": "ROU", "HU": "HUN",
        "BG": "BGR", "HR": "HRV", "CY": "CYP", "EE": "EST", "LV": "LVA", "LT": "LTU", "MT": "MLT", "SK": "SVK", "SI": "SVN",
        "IS": "ISL", "LI": "LIE", "MC": "MCO", "SM": "SMR", "GI": "GIB", "MA": "MAR", "PE": "PER", "VE": "VEN", "UY": "URY",
        "EC": "ECU", "BR": "BRA", "CA": "CAN", "CN": "CHN", "JP": "JPN", "IN": "IND", "AU": "AUS", "TR": "TUR", "AE": "ARE"}
# Causa del IVA 0 % → categoría EN 16931 (UNCL 5305) y código VATEX (BT-121); en Facturae, SpecialTaxableEvent.
EXEMPTION = {"": ("E", "", "01"), "art20": ("E", "", "01"), "art21": ("G", "VATEX-EU-G", "01"),
             "art25": ("K", "VATEX-EU-IC", "01"), "isp": ("AE", "VATEX-EU-AE", "02"), "nosujeta": ("O", "VATEX-EU-O", "02")}
XML_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def d2(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def p6(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def money(value) -> str:
    return f"{d2(value):.2f}"


def qty(value) -> str:
    q = Decimal(str(value)).normalize()
    return format(q, "f")


def price(value) -> str:
    text = format(p6(value).normalize(), "f")
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


def _rate(value) -> Decimal:
    rate = Decimal(str(value))
    return rate.quantize(Decimal(1)) if rate == rate.to_integral_value() else rate


def category_of(f, vat) -> str:
    return "S" if _rate(vat) > 0 else EXEMPTION[f.causa_exencion][0]


def calcular(f) -> Totals:
    """Los mismos totales que crear-factura (EN 16931), con Decimal; el bruto, con el precio que va en el XML (6 decimales)."""
    t = Totals()
    groups: dict[tuple[str, Decimal], Group] = {}
    for line in f.lineas:
        gross = d2(Decimal(str(line.cantidad)) * p6(line.precio))
        disc = d2(gross * Decimal(str(line.descuento)) / 100)
        net = d2(gross - disc)
        t.lines.append((gross, disc, net))
        rate = _rate(line.iva)
        cat = category_of(f, line.iva)
        g = groups.setdefault((cat, rate), Group(rate=rate, category=cat))
        g.base = d2(g.base + net)
    for key in sorted(groups, key=lambda k: (-k[1], k[0])):
        g = groups[key]
        g.tax = d2(g.base * g.rate / 100)
        if f.recargo:
            g.surcharge_rate = SURCHARGE.get(g.rate, Decimal("0"))
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


def clean_id(value: str) -> str:
    return re.sub(r"[\s.\-]", "", value or "").upper()


def vat_id(country: str, tax_id: str) -> str:
    """Identificador de IVA con el prefijo del país (Grecia, EL); si ya lleva un prefijo de la UE, tal cual."""
    tid = clean_id(tax_id)
    prefix = "EL" if country.upper() == "GR" else country.upper()
    if tid[:2] == prefix or (tid[:2].isalpha() and (tid[:2] in EU or tid[:2] == "EL")):
        return tid
    return prefix + tid


def domestic_id(tax_id: str) -> str:
    tid = clean_id(tax_id)
    return tid[2:] if tid.startswith("ES") and len(tid) == 11 else tid


def _series(numero: str) -> tuple[str, str]:
    number = numero.strip()
    if "/" in number:
        series, number = number.rsplit("/", 1)
        return series.strip(), number.strip()
    return "", number


def person_type(p) -> str:
    if p.tipo_persona:
        return p.tipo_persona
    if p.pais.upper() != "ES":
        return "J"
    tid = domestic_id(p.nif)
    return "J" if tid and tid[0] in "ABCDEFGHJNPQRSUVW" else "F"


def split_name(name: str) -> tuple[str, str, str] | None:
    """Nombre y apellidos de una persona física (Facturae): los dos últimos términos son los apellidos («María José García
    López»); con dos términos, un apellido. Uno solo no basta."""
    parts = name.split()
    if len(parts) < 2:
        return None
    if len(parts) == 2:
        return parts[0], parts[1], ""
    return " ".join(parts[:-2]), parts[-2], parts[-1]


def problems(f, fmt: str, profile: str) -> list[str]:
    """Lo que el formato necesita y el formulario no trae (los textos, en errors.py). El primero va al usuario."""
    out: list[str] = []
    zero = any(_rate(line.iva) == 0 for line in f.lineas)
    cause = f.causa_exencion
    if not f.numero.strip():
        out.append("einvoice_number")
    if not f.lineas or any(not line.descripcion.strip() for line in f.lineas):
        out.append("einvoice_lines")
    if any(line.cantidad == 0 for line in f.lineas):
        out.append("einvoice_quantity")
    if not (f.emisor.nombre.strip() and f.cliente.nombre.strip()):
        out.append("einvoice_names")
    for p in (f.emisor, f.cliente):
        if p.pais.upper() not in ISO3:
            out.append(f"einvoice_country:{p.pais}")
            break
    if not f.emisor.nif.strip():
        out.append("einvoice_seller_vat")
    eu = fmt != "facturae"
    xr = fmt in ("xrechnung_cii", "xrechnung_ubl") or (fmt == "facturx" and profile == "xrechnung")
    if eu and f.recargo:
        out.append("einvoice_surcharge")
    if eu and f.irpf:
        out.append("einvoice_irpf")
    if f.moneda != "EUR" and f.emisor.pais.upper() == "ES" and not f.tipo_cambio:
        out.append("einvoice_exchange_rate")  # la cuota de IVA también en euros (RD 1619/2012, art. 12.1)
    # Forma de pago: la transferencia necesita la cuenta; adeudos y tarjeta piden datos que el formulario no tiene.
    if f.forma_pago in ("30", "58") and not f.iban.strip() and not (fmt == "facturx" and profile == "minimum"):
        out.append("einvoice_iban")
    if xr and not f.forma_pago:
        out.append("einvoice_payment")
    if f.forma_pago in ("49", "59") or (xr and f.forma_pago == "48"):
        out.append("einvoice_payment_unsupported")
    if zero:
        if not (f.motivo_exencion.strip() or cause):
            out.append("einvoice_exemption")
        if cause in ("isp", "art25") and not f.cliente.nif.strip():
            out.append("einvoice_buyer_vat")
        if cause == "art25" and not f.fecha_operacion:
            out.append("einvoice_delivery_date")
        if cause == "nosujeta" and any(_rate(line.iva) > 0 for line in f.lineas):
            out.append("einvoice_mixed_o")
    if xr:
        if not f.referencia_comprador.strip():
            out.append("einvoice_buyer_reference")
        if not (f.emisor.contacto.strip() and f.emisor.telefono.strip() and f.emisor.correo.strip()):
            out.append("einvoice_seller_contact")
        if any(not (p.ciudad.strip() and p.cp.strip()) for p in (f.emisor, f.cliente)):
            out.append("einvoice_address")
    if xr or fmt == "peppol":
        if not (f.emisor.endpoint_id.strip() and f.cliente.endpoint_id.strip()):
            out.append("einvoice_endpoint")
    if fmt == "peppol":
        if any(p.endpoint_esquema.strip().upper() == "EM" for p in (f.emisor, f.cliente)):
            out.append("einvoice_endpoint_scheme")
        if not (f.referencia_comprador.strip() or f.pedido.strip()):
            out.append("einvoice_buyer_reference")
    if fmt == "facturae":
        out += _facturae_problems(f)
    order = {"einvoice_number": 0, "einvoice_names": 1, "einvoice_lines": 2}
    return sorted(dict.fromkeys(out), key=lambda k: (order.get(k, 9), out.index(k)))


def _facturae_problems(f) -> list[str]:
    """Las longitudes del XSD de Facturae: nada se recorta en silencio (un número de factura cambiado sería otra)."""
    out: list[str] = []
    if not f.emisor.nif.strip() or not f.cliente.nif.strip():
        out.append("einvoice_facturae_nif")
    if f.moneda != "EUR":
        out.append("einvoice_facturae_currency")
    series, number = _series(f.numero)
    if not number or len(number) > 20 or len(series) > 20:
        out.append("einvoice_facturae_field:numero")
    for p in (f.emisor, f.cliente):
        if person_type(p) == "J":
            if len(p.nombre.strip()) > 80:
                out.append("einvoice_facturae_field:nombre")
        else:
            parts = split_name(p.nombre)
            if parts is None:
                out.append("einvoice_facturae_field:apellidos")
            elif any(len(x) > 40 for x in parts):
                out.append("einvoice_facturae_field:nombre")
        spain = p.pais.upper() == "ES"
        if not p.direccion.strip() or len(p.direccion) > 80:
            out.append("einvoice_facturae_field:direccion")
        if spain and not re.fullmatch(r"\d{5}", p.cp.strip()):
            out.append("einvoice_facturae_field:cp")
        if not p.ciudad.strip() or len(p.ciudad) > 50 or (not spain and len(f"{p.cp} {p.ciudad}".strip()) > 50):
            out.append("einvoice_facturae_field:ciudad")
        if len((p.provincia or p.ciudad).strip()) > 20:
            out.append("einvoice_facturae_field:provincia")
        if len(p.telefono.strip()) > 15:
            out.append("einvoice_facturae_field:telefono")
        if len(p.correo.strip()) > 60:
            out.append("einvoice_facturae_field:correo")
    dir3 = [f.oficina_contable.strip(), f.organo_gestor.strip(), f.unidad_tramitadora.strip()]
    if any(dir3) and not all(dir3):
        out.append("einvoice_dir3")
    return out


def _e(parent, ns: str, tag: str, text=None, **attrs):
    el = etree.SubElement(parent, f"{{{ns}}}{tag}", {k: v for k, v in attrs.items() if v is not None})
    if text is not None:
        el.text = str(text)
    return el


def _date102(iso: str) -> str:
    return iso.replace("-", "")


# --- CII ------------------------------------------------------------------------------------------------------------


def _cii_party(parent, tag: str, p, seller: bool, profile: str, cat_o: bool):
    party = _e(parent, RAM, tag)
    _e(party, RAM, "Name", p.nombre.strip())
    minimum = profile == "minimum"
    if cat_o and seller and p.nif.strip() and not minimum:
        # Operación no sujeta (O): sin NIF-IVA (BR-O-2); el NIF va como registro legal (BT-30).
        _e(_e(party, RAM, "SpecifiedLegalOrganization"), RAM, "ID", clean_id(p.nif))
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
    if p.nif.strip() and (seller or not minimum) and not cat_o:
        _e(_e(party, RAM, "SpecifiedTaxRegistration"), RAM, "ID", vat_id(p.pais, p.nif), schemeID="VA")
    return party


def _cii_tax(parent, f, category: str, rate: Decimal, header: bool, g: Group | None = None):
    tax = _e(parent, RAM, "ApplicableTradeTax")
    if header:
        _e(tax, RAM, "CalculatedAmount", money(g.tax))
    _e(tax, RAM, "TypeCode", "VAT")
    if header and category != "S":
        _e(tax, RAM, "ExemptionReason", f.motivo_exencion.strip() or EXEMPTION[f.causa_exencion][1] or "Exenta")
    if header:
        _e(tax, RAM, "BasisAmount", money(g.base))
    _e(tax, RAM, "CategoryCode", category)
    if header and category != "S" and EXEMPTION[f.causa_exencion][1]:
        _e(tax, RAM, "ExemptionReasonCode", EXEMPTION[f.causa_exencion][1])
    if category != "O" or header:  # en el desglose, también con O (0 %; BR-DE-14)
        _e(tax, RAM, "RateApplicablePercent", qty(rate))
    return tax


def cii(f, profile: str) -> bytes:
    t = calcular(f)
    cat_o = any(g.category == "O" for g in t.groups)
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
    if profile not in ("minimum", "basicwl"):
        for i, (line, (gross, disc, net)) in enumerate(zip(f.lineas, t.lines), 1):
            item = _e(tx, RAM, "IncludedSupplyChainTradeLineItem")
            _e(_e(item, RAM, "AssociatedDocumentLineDocument"), RAM, "LineID", str(i))
            _e(_e(item, RAM, "SpecifiedTradeProduct"), RAM, "Name", line.descripcion.strip())
            agreement = _e(item, RAM, "SpecifiedLineTradeAgreement")
            _e(_e(agreement, RAM, "NetPriceProductTradePrice"), RAM, "ChargeAmount", price(line.precio))
            _e(_e(item, RAM, "SpecifiedLineTradeDelivery"), RAM, "BilledQuantity", qty(line.cantidad), unitCode=unit_codes(line.unidad)[0])
            settle = _e(item, RAM, "SpecifiedLineTradeSettlement")
            _cii_tax(settle, f, category_of(f, line.iva), _rate(line.iva), header=False)
            if disc:
                ac = _e(settle, RAM, "SpecifiedTradeAllowanceCharge")
                _e(_e(ac, RAM, "ChargeIndicator"), UDT, "Indicator", "false")
                _e(ac, RAM, "ActualAmount", money(disc))
                _e(ac, RAM, "Reason", f.texto_descuento.strip() or "Descuento")
            _e(_e(settle, RAM, "SpecifiedTradeSettlementLineMonetarySummation"), RAM, "LineTotalAmount", money(net))
    agreement = _e(tx, RAM, "ApplicableHeaderTradeAgreement")
    if f.referencia_comprador.strip():
        _e(agreement, RAM, "BuyerReference", f.referencia_comprador.strip())
    _cii_party(agreement, "SellerTradeParty", f.emisor, True, profile, cat_o)
    _cii_party(agreement, "BuyerTradeParty", f.cliente, False, profile, cat_o)
    if f.pedido.strip() and profile != "minimum":
        _e(_e(agreement, RAM, "BuyerOrderReferencedDocument"), RAM, "IssuerAssignedID", f.pedido.strip())
    delivery = _e(tx, RAM, "ApplicableHeaderTradeDelivery")
    intra = any(g.category == "K" for g in t.groups)
    if intra and profile != "minimum":  # BR-IC-12: país de entrega (con su población y C. P., BR-DE-10 y 11)
        ship = _e(delivery, RAM, "ShipToTradeParty")
        addr = _e(ship, RAM, "PostalTradeAddress")
        if f.cliente.cp.strip():
            _e(addr, RAM, "PostcodeCode", f.cliente.cp.strip())
        if f.cliente.ciudad.strip():
            _e(addr, RAM, "CityName", f.cliente.ciudad.strip())
        _e(addr, RAM, "CountryID", f.cliente.pais.upper())
    if f.fecha_operacion and profile != "minimum":  # BT-72; sin ella el bloque va vacío (aviso del Schematron)
        event = _e(delivery, RAM, "ActualDeliverySupplyChainEvent")
        _e(_e(event, RAM, "OccurrenceDateTime"), UDT, "DateTimeString", _date102(f.fecha_operacion), format="102")
    settle = _e(tx, RAM, "ApplicableHeaderTradeSettlement")
    other = f.moneda != "EUR" and f.tipo_cambio
    if other:
        _e(settle, RAM, "TaxCurrencyCode", "EUR")
    _e(settle, RAM, "InvoiceCurrencyCode", f.moneda)
    if profile != "minimum":
        if f.forma_pago:
            means = _e(settle, RAM, "SpecifiedTradeSettlementPaymentMeans")
            _e(means, RAM, "TypeCode", f.forma_pago)
            if f.iban.strip() and f.forma_pago in ("30", "58"):
                _e(_e(means, RAM, "PayeePartyCreditorFinancialAccount"), RAM, "IBANID", clean_id(f.iban))
        for g in t.groups:
            _cii_tax(settle, f, g.category, g.rate, header=True, g=g)
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
    if other:  # BT-111: la cuota en la moneda de los impuestos
        _e(sums, RAM, "TaxTotalAmount", money(t.tax * Decimal(str(f.tipo_cambio))), currencyID="EUR")
    _e(sums, RAM, "GrandTotalAmount", money(t.total))
    _e(sums, RAM, "DuePayableAmount", money(t.payable))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# --- UBL ------------------------------------------------------------------------------------------------------------


def _ubl_party(parent, tag: str, p, seller: bool, cat_o: bool):
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
    if p.nif.strip() and not cat_o:
        scheme = _e(party, CAC, "PartyTaxScheme")
        _e(scheme, CBC, "CompanyID", vat_id(p.pais, p.nif))
        _e(_e(scheme, CAC, "TaxScheme"), CBC, "ID", "VAT")
    legal = _e(party, CAC, "PartyLegalEntity")
    _e(legal, CBC, "RegistrationName", p.nombre.strip())
    if cat_o and seller and p.nif.strip():
        _e(legal, CBC, "CompanyID", clean_id(p.nif))  # BT-30 en lugar del NIF-IVA (BR-O-2)
    if seller and (p.contacto.strip() or p.telefono.strip() or p.correo.strip()):
        contact = _e(party, CAC, "Contact")
        for tag2, value in (("Name", p.contacto), ("Telephone", p.telefono), ("ElectronicMail", p.correo)):
            if value.strip():
                _e(contact, CBC, tag2, value.strip())


def _ubl_category(parent, tag: str, f, category: str, rate: Decimal, reason: bool):
    cat = _e(parent, CAC, tag)
    _e(cat, CBC, "ID", category)
    if category != "O" or reason:  # en el desglose (reason), también con O (0 %; BR-DE-14)
        _e(cat, CBC, "Percent", qty(rate))
    if reason and category != "S":
        code = EXEMPTION[f.causa_exencion][1]
        if code:
            _e(cat, CBC, "TaxExemptionReasonCode", code)
        _e(cat, CBC, "TaxExemptionReason", f.motivo_exencion.strip() or code or "Exenta")
    _e(_e(cat, CAC, "TaxScheme"), CBC, "ID", "VAT")


def ubl(f, customization: str, profile_id: str | None) -> bytes:
    t = calcular(f)
    cat_o = any(g.category == "O" for g in t.groups)
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
    other = f.moneda != "EUR" and f.tipo_cambio
    if other:
        _e(root, CBC, "TaxCurrencyCode", "EUR")
    if f.referencia_comprador.strip():
        _e(root, CBC, "BuyerReference", f.referencia_comprador.strip())
    if f.pedido.strip():
        _e(_e(root, CAC, "OrderReference"), CBC, "ID", f.pedido.strip())
    _ubl_party(root, "AccountingSupplierParty", f.emisor, True, cat_o)
    _ubl_party(root, "AccountingCustomerParty", f.cliente, False, cat_o)
    intra = any(g.category == "K" for g in t.groups)
    if f.fecha_operacion or intra:
        delivery = _e(root, CAC, "Delivery")
        if f.fecha_operacion:
            _e(delivery, CBC, "ActualDeliveryDate", f.fecha_operacion)
        if intra:
            address = _e(_e(delivery, CAC, "DeliveryLocation"), CAC, "Address")
            if f.cliente.ciudad.strip():
                _e(address, CBC, "CityName", f.cliente.ciudad.strip())
            if f.cliente.cp.strip():
                _e(address, CBC, "PostalZone", f.cliente.cp.strip())
            _e(_e(address, CAC, "Country"), CBC, "IdentificationCode", f.cliente.pais.upper())
    if f.forma_pago:
        means = _e(root, CAC, "PaymentMeans")
        _e(means, CBC, "PaymentMeansCode", f.forma_pago)
        if f.iban.strip() and f.forma_pago in ("30", "58"):
            _e(_e(means, CAC, "PayeeFinancialAccount"), CBC, "ID", clean_id(f.iban))
    if f.condiciones_pago.strip():
        _e(_e(root, CAC, "PaymentTerms"), CBC, "Note", f.condiciones_pago.strip())
    total = _e(root, CAC, "TaxTotal")
    _e(total, CBC, "TaxAmount", money(t.tax), currencyID=f.moneda)
    for g in t.groups:
        sub = _e(total, CAC, "TaxSubtotal")
        _e(sub, CBC, "TaxableAmount", money(g.base), currencyID=f.moneda)
        _e(sub, CBC, "TaxAmount", money(g.tax), currencyID=f.moneda)
        _ubl_category(sub, "TaxCategory", f, g.category, g.rate, reason=True)
    if other:  # BT-111
        _e(_e(root, CAC, "TaxTotal"), CBC, "TaxAmount", money(t.tax * Decimal(str(f.tipo_cambio))), currencyID="EUR")
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
            _e(ac, CBC, "AllowanceChargeReason", f.texto_descuento.strip() or "Descuento")
            _e(ac, CBC, "Amount", money(disc), currencyID=f.moneda)
        item = _e(el, CAC, "Item")
        _e(item, CBC, "Name", line.descripcion.strip())
        _ubl_category(item, "ClassifiedTaxCategory", f, category_of(f, line.iva), _rate(line.iva), reason=False)
        _e(_e(el, CAC, "Price"), CBC, "PriceAmount", price(line.precio), currencyID=f.moneda)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# --- Facturae 3.2.2 ---------------------------------------------------------------------------------------------------


def _sub(parent, tag: str, text=None):
    el = etree.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def _address(holder, p):
    if p.pais.upper() == "ES":
        addr = _sub(holder, "AddressInSpain")
        _sub(addr, "Address", p.direccion.strip())
        _sub(addr, "PostCode", p.cp.strip())
        _sub(addr, "Town", p.ciudad.strip())
        _sub(addr, "Province", (p.provincia.strip() or p.ciudad.strip()))
        _sub(addr, "CountryCode", "ESP")
    else:
        addr = _sub(holder, "OverseasAddress")
        _sub(addr, "Address", p.direccion.strip())
        _sub(addr, "PostCodeAndTown", f"{p.cp} {p.ciudad}".strip())
        _sub(addr, "Province", (p.provincia.strip() or p.ciudad.strip()))
        _sub(addr, "CountryCode", ISO3[p.pais.upper()])


def _facturae_party(parent, tag: str, p, dir3: list[tuple[str, str]] | None = None):
    party = _sub(parent, tag)
    tax = _sub(party, "TaxIdentification")
    kind = person_type(p)
    country = p.pais.upper()
    residence = "R" if country == "ES" else ("U" if country in EU else "E")
    _sub(tax, "PersonTypeCode", kind)
    _sub(tax, "ResidenceTypeCode", residence)
    # Sin prefijo de país en un NIF español; con el suyo en el resto (XSD, TaxIdentificationNumber).
    _sub(tax, "TaxIdentificationNumber", domestic_id(p.nif) if residence == "R" else vat_id(country, p.nif) if residence == "U" else clean_id(p.nif))
    if dir3:
        centres = _sub(party, "AdministrativeCentres")
        for code, role in dir3:
            centre = _sub(centres, "AdministrativeCentre")
            _sub(centre, "CentreCode", code)
            _sub(centre, "RoleTypeCode", role)
            _address(centre, p)
    if kind == "J":
        holder = _sub(party, "LegalEntity")
        _sub(holder, "CorporateName", p.nombre.strip())
    else:
        holder = _sub(party, "Individual")
        name, first, second = split_name(p.nombre)
        _sub(holder, "Name", name)
        _sub(holder, "FirstSurname", first)
        if second:
            _sub(holder, "SecondSurname", second)
    _address(holder, p)
    if p.correo.strip() or p.telefono.strip():
        contact = _sub(holder, "ContactDetails")
        if p.telefono.strip():
            _sub(contact, "Telephone", p.telefono.strip())
        if p.correo.strip():
            _sub(contact, "ElectronicMail", p.correo.strip())


def _amount(parent, tag: str, value):
    el = _sub(parent, tag)
    _sub(el, "TotalAmount", money(value))
    return el


def facturae(f) -> bytes:
    t = calcular(f)
    root = etree.Element(f"{{{FE}}}Facturae", nsmap={"fe": FE, "ds": DS})
    header = _sub(root, "FileHeader")
    _sub(header, "SchemaVersion", "3.2.2")
    _sub(header, "Modality", "I")
    _sub(header, "InvoiceIssuerType", "EM")
    batch = _sub(header, "Batch")
    _sub(batch, "BatchIdentifier", (domestic_id(f.emisor.nif) + f.numero.strip())[:70])
    _sub(batch, "InvoicesCount", "1")
    for tag in ("TotalInvoicesAmount", "TotalOutstandingAmount", "TotalExecutableAmount"):
        _amount(batch, tag, t.payable)  # la suma de InvoiceTotal, que ya descuenta las retenciones
    _sub(batch, "InvoiceCurrencyCode", "EUR")
    parties = _sub(root, "Parties")
    _facturae_party(parties, "SellerParty", f.emisor)
    dir3 = [(f.oficina_contable.strip(), "01"), (f.organo_gestor.strip(), "02"), (f.unidad_tramitadora.strip(), "03")]
    _facturae_party(parties, "BuyerParty", f.cliente, dir3 if all(c for c, _ in dir3) else None)
    inv = _sub(_sub(root, "Invoices"), "Invoice")
    ih = _sub(inv, "InvoiceHeader")
    series, number = _series(f.numero)
    _sub(ih, "InvoiceNumber", number)
    if series:
        _sub(ih, "InvoiceSeriesCode", series)
    _sub(ih, "InvoiceDocumentType", "FC")
    _sub(ih, "InvoiceClass", "OO")
    data = _sub(inv, "InvoiceIssueData")
    _sub(data, "IssueDate", f.fecha)
    if f.fecha_operacion:
        _sub(data, "OperationDate", f.fecha_operacion)
    _sub(data, "InvoiceCurrencyCode", "EUR")
    _sub(data, "TaxCurrencyCode", "EUR")
    _sub(data, "LanguageName", f.idioma)
    outputs = _sub(inv, "TaxesOutputs")
    for g in t.groups:
        tax = _sub(outputs, "Tax")
        _sub(tax, "TaxTypeCode", "01")
        _sub(tax, "TaxRate", money(g.rate))
        _amount(tax, "TaxableBase", g.base)
        _amount(tax, "TaxAmount", g.tax)
        if g.surcharge_rate:
            _sub(tax, "EquivalenceSurcharge", money(g.surcharge_rate))
            _amount(tax, "EquivalenceSurchargeAmount", g.surcharge)
    if t.irpf:
        withheld = _sub(_sub(inv, "TaxesWithheld"), "Tax")
        _sub(withheld, "TaxTypeCode", "04")
        _sub(withheld, "TaxRate", money(f.irpf))
        _amount(withheld, "TaxableBase", t.net)
        _amount(withheld, "TaxAmount", t.irpf)
    totals = _sub(inv, "InvoiceTotals")
    _sub(totals, "TotalGrossAmount", money(t.net))
    _sub(totals, "TotalGrossAmountBeforeTaxes", money(t.net))
    _sub(totals, "TotalTaxOutputs", money(t.tax + t.surcharge))
    _sub(totals, "TotalTaxesWithheld", money(t.irpf))
    _sub(totals, "InvoiceTotal", money(t.payable))
    _sub(totals, "TotalOutstandingAmount", money(t.payable))
    _sub(totals, "TotalExecutableAmount", money(t.payable))
    items = _sub(inv, "Items")
    reason = f.motivo_exencion.strip()
    for line, (gross, disc, net) in zip(f.lineas, t.lines):
        el = _sub(items, "InvoiceLine")
        _sub(el, "ItemDescription", line.descripcion.strip())
        _sub(el, "Quantity", qty(line.cantidad))
        _sub(el, "UnitOfMeasure", unit_codes(line.unidad)[1])
        _sub(el, "UnitPriceWithoutTax", f"{p6(line.precio):.6f}")
        _sub(el, "TotalCost", f"{gross:.6f}")
        if disc:
            d = _sub(_sub(el, "DiscountsAndRebates"), "Discount")
            _sub(d, "DiscountReason", f.texto_descuento.strip() or "Descuento")
            _sub(d, "DiscountRate", f"{Decimal(str(line.descuento)):.4f}")
            _sub(d, "DiscountAmount", f"{disc:.6f}")
        _sub(el, "GrossAmount", f"{net:.6f}")
        lt = _sub(_sub(el, "TaxesOutputs"), "Tax")
        _sub(lt, "TaxTypeCode", "01")
        _sub(lt, "TaxRate", money(line.iva))
        _amount(lt, "TaxableBase", net)
        rate = _rate(line.iva)
        if f.recargo and SURCHARGE.get(rate):
            _sub(lt, "EquivalenceSurcharge", money(SURCHARGE[rate]))
        if rate == 0:
            event = _sub(el, "SpecialTaxableEvent")
            _sub(event, "SpecialTaxableEventCode", EXEMPTION[f.causa_exencion][2])
            _sub(event, "SpecialTaxableEventReason", reason or "Exenta")
    if f.forma_pago in PAYMENT_FACTURAE:
        inst = _sub(_sub(inv, "PaymentDetails"), "Installment")
        _sub(inst, "InstallmentDueDate", f.vencimiento or f.fecha)
        _sub(inst, "InstallmentAmount", money(t.payable))
        _sub(inst, "PaymentMeans", PAYMENT_FACTURAE[f.forma_pago])
        if f.forma_pago in ("30", "58"):
            _sub(_sub(inst, "AccountToBeCredited"), "IBAN", clean_id(f.iban))
    if f.notas.strip():
        _sub(_sub(inv, "AdditionalData"), "InvoiceAdditionalInformation", f.notas.strip())
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def sanitized(f):
    """Sin caracteres de control que XML no admite (lxml los rechaza con un error interno)."""
    def clean(value):
        if isinstance(value, str):
            return XML_BAD.sub("", value)
        if isinstance(value, list):
            return [clean(v) for v in value]
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        return value

    return type(f).model_validate(clean(f.model_dump()))


def build(f, fmt: str, profile: str) -> tuple[bytes, str]:
    """El XML y la sintaxis («cii», «ubl» o «facturae»)."""
    f = sanitized(f)
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
