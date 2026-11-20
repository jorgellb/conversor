"""F4-E2: crear-factura-electronica (A.2, D-205). Cada formato y perfil se genera y pasa el mismo motor que
validar-factura-electronica: KoSIT (aquí, el de la caché local en KOSIT_URL; en la CI, el del job python) y los XSD
oficiales; Facturae, su XSD. Factur-X sale en PDF/A-3b con `factur-x.xml` y sus metadatos, y pasa a veraPDF."""
from __future__ import annotations

import sys
from pathlib import Path

import pikepdf
import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fixtures"))

from test_desde_pdf import fake_verapdf, mrr  # noqa: E402,F401
from test_facturas import needs_kosit  # noqa: E402
from test_facturas_pdf import _gotenberg, facturae_xsd  # noqa: E402,F401 - XSD de Facturae, UBL y CII
from test_tools import make_ctx, run  # noqa: E402,F401

TOOL = "crear-factura-electronica"
BASE = {
    "numero": "2026/0042", "fecha": "2026-11-20", "vencimiento": "2026-12-20", "fecha_operacion": "2026-11-15", "moneda": "EUR",
    "idioma": "es", "referencia_comprador": "04011000-12345-34", "pedido": "PO-77",
    "emisor": {"nombre": "Estudio Pérez S.L.", "nif": "B12345674", "direccion": "Calle Mayor 1", "cp": "28013", "ciudad": "Madrid",
               "provincia": "Madrid", "pais": "ES", "correo": "hola@estudio.test", "telefono": "+34 600 000 000", "contacto": "Ana Pérez",
               "endpoint_esquema": "9920", "endpoint_id": "ESB12345674"},
    "cliente": {"nombre": "Cliente GmbH", "nif": "DE123456789", "direccion": "Hauptstr. 1", "cp": "10115", "ciudad": "Berlin", "pais": "DE",
                "correo": "ap@cliente.test", "endpoint_esquema": "9930", "endpoint_id": "DE123456789"},
    "lineas": [{"descripcion": "Diseño", "cantidad": 1, "unidad": "ud", "precio": 450, "descuento": 0, "iva": 21},
               {"descripcion": "Horas", "cantidad": 3.5, "unidad": "h", "precio": 40.33, "descuento": 10, "iva": 21},
               {"descripcion": "Libro", "cantidad": 2, "unidad": "ud", "precio": 19.95, "descuento": 0, "iva": 4}],
    "forma_pago": "58", "iban": "ES9121000418450200051332", "condiciones_pago": "30 días", "notas": "Gracias",
}
CASES = [("facturx", p) for p in ("minimum", "basicwl", "basic", "en16931", "extended", "xrechnung")] + \
        [(f, "en16931") for f in ("xrechnung_cii", "xrechnung_ubl", "peppol", "ubl", "facturae")]


def _options(fmt="ubl", profile="en16931", **over):
    from tools.utils.specs import CrearFacturaElectronicaOptions

    return CrearFacturaElectronicaOptions.model_validate({"formato": fmt, "perfil": profile, "factura": {**BASE, **over}})


def test_totals_match_crear_factura():
    """Los mismos importes que client-tools/test/invoice.test.ts (EN 16931), también con recargo e IRPF."""
    from tools.utils.facturas.generar import calcular

    t = calcular(_options().factura)
    assert [str(n) for _, _, n in t.lines] == ["450.00", "127.04", "39.90"]
    assert [(str(g.rate), str(g.base), str(g.tax)) for g in t.groups] == [("21", "577.04", "121.18"), ("4", "39.90", "1.60")]
    assert (str(t.net), str(t.tax), str(t.total), str(t.payable)) == ("616.94", "122.78", "739.72", "739.72")
    t = calcular(_options(recargo=True, irpf=15).factura)
    assert (str(t.surcharge), str(t.total), str(t.irpf), str(t.payable)) == ("30.21", "769.93", "92.54", "677.39")


@needs_kosit
@pytest.mark.parametrize("fmt,profile", CASES)
def test_every_format_passes_the_validator(fmt, profile, make_ctx):
    """16.6: el XML generado pasa KoSIT en cada perfil (y el XSD; Facturae, el suyo)."""
    from tools.utils.facturas import crear, generar

    o = _options(fmt, profile)
    data, syntax = generar.build(o.factura, fmt, profile)
    ctx = make_ctx(TOOL, [], {"formato": fmt, "perfil": profile, "factura": BASE})
    spec, warnings = crear.validate(ctx, data, syntax)
    assert warnings == 0, (fmt, profile)
    if fmt == "facturae":
        assert spec.startswith("Facturae")


@needs_kosit
def test_facturae_with_surcharge_withholding_exemption_and_individual(make_ctx):
    from lxml import etree

    from tools.utils.facturas import crear, generar

    o = _options("facturae", recargo=True, irpf=15, motivo_exencion="Exenta por el artículo 20 de la Ley 37/1992",
                 cliente={"nombre": "Ana García López", "nif": "12345678Z", "direccion": "Av. del Mar 3", "cp": "46001",
                          "ciudad": "Valencia", "provincia": "Valencia", "pais": "ES"},
                 lineas=BASE["lineas"] + [{"descripcion": "Formación", "cantidad": 1, "unidad": "h", "precio": 100, "descuento": 0, "iva": 0}])
    data, syntax = generar.build(o.factura, "facturae", "en16931")
    crear.validate(make_ctx(TOOL, [], {"formato": "facturae"}), data, syntax)
    root = etree.fromstring(data)
    assert root.findtext(".//BuyerParty//PersonTypeCode") == "F" and root.findtext(".//BuyerParty//FirstSurname") == "García"
    assert root.findtext(".//TaxesWithheld/Tax/TaxAmount/TotalAmount") == "107.54"  # 15 % de 716,94
    assert root.findtext(".//InvoiceTotals/InvoiceTotal") == "762.39"
    assert root.findtext(".//InvoiceHeader/InvoiceSeriesCode") == "2026" and root.findtext(".//InvoiceHeader/InvoiceNumber") == "0042"


def test_format_requirements_are_explained():
    from core.errors import ToolError
    from tools.utils.facturas import generar

    cases = [
        (_options("ubl", recargo=True), "einvoice_surcharge"),
        (_options("facturx", irpf=7), "einvoice_irpf"),
        (_options("xrechnung_ubl", referencia_comprador=""), "einvoice_buyer_reference"),
        (_options("xrechnung_cii", emisor={**BASE["emisor"], "telefono": ""}), "einvoice_seller_contact"),
        (_options("peppol", cliente={**BASE["cliente"], "endpoint_esquema": "EM", "endpoint_id": "a@b.test"}), "einvoice_endpoint_scheme"),
        (_options("peppol", cliente={**BASE["cliente"], "endpoint_id": ""}), "einvoice_endpoint"),
        (_options("ubl", lineas=[{**BASE["lineas"][0], "iva": 0}]), "einvoice_exemption"),
        (_options("facturae", moneda="USD", tipo_cambio=0.9), "einvoice_facturae_currency"),
        (_options("ubl", moneda="USD"), "einvoice_exchange_rate"),
        (_options("ubl", iban=""), "einvoice_iban"),
        (_options("xrechnung_cii", forma_pago=""), "einvoice_payment"),
        (_options("peppol", forma_pago="59"), "einvoice_payment_unsupported"),
        (_options("ubl", causa_exencion="isp", lineas=[{**BASE["lineas"][0], "iva": 0}], cliente={**BASE["cliente"], "nif": ""}), "einvoice_buyer_vat"),
        (_options("ubl", causa_exencion="art25", fecha_operacion="", lineas=[{**BASE["lineas"][0], "iva": 0}]), "einvoice_delivery_date"),
        (_options("ubl", causa_exencion="nosujeta", lineas=[{**BASE["lineas"][0], "iva": 0}, BASE["lineas"][1]]), "einvoice_mixed_o"),
        (_options("facturae", numero="FACTURA-2026-000000123"), "einvoice_facturae_field:numero"),
        (_options("facturae", numero="2026/"), "einvoice_facturae_field:numero"),
        (_options("facturae", emisor={**BASE["emisor"], "provincia": "Santa Cruz de Tenerife"}), "einvoice_facturae_field:provincia"),
        (_options("facturae", cliente={**BASE["cliente"], "pais": "ES", "cp": "", "nif": "12345678Z", "nombre": "Ana García"}), "einvoice_facturae_field:cp"),
        (_options("facturae", cliente={**BASE["cliente"], "pais": "ES", "cp": "46001", "nif": "12345678Z", "nombre": "Ana"}), "einvoice_facturae_field:apellidos"),
        (_options("facturae", oficina_contable="EA0000001"), "einvoice_dir3"),
        (_options("ubl", cliente={**BASE["cliente"], "pais": "UK"}), "einvoice_country:UK"),
        (_options("ubl", emisor={**BASE["emisor"], "nombre": ""}), "einvoice_names"),
        (_options("ubl", lineas=[{**BASE["lineas"][0], "cantidad": 0}]), "einvoice_quantity"),
    ]
    for o, detail in cases:
        with pytest.raises(ToolError) as err:
            generar.build(o.factura, o.formato, o.perfil)
        assert err.value.detail == detail, detail


@needs_kosit
def test_job_delivers_validated_xml(make_ctx):
    out = run(TOOL, make_ctx(TOOL, [], {"formato": "xrechnung_ubl", "factura": BASE}))
    assert [o["name"] for o in out] == ["factura-2026-0042.xml"]
    assert out[0]["note"].startswith("Validada con KoSIT (XRechnung")
    assert b"urn:xeinkauf.de:kosit:xrechnung_3.0" in Path(out[0]["path"]).read_bytes()


@needs_kosit
def test_invalid_result_is_never_delivered(make_ctx, monkeypatch):
    """Si el validador rechaza lo generado, el trabajo falla con la regla y no hay salida."""
    from core.errors import ToolError
    from tools.utils.facturas import generar

    real = generar.ubl
    monkeypatch.setattr(generar, "ubl", lambda f, c, p: real(f, c, p).replace(b"<cbc:PayableAmount currencyID=\"EUR\">739.72", b"<cbc:PayableAmount currencyID=\"EUR\">1.00"))
    with pytest.raises(ToolError) as err:
        run(TOOL, make_ctx(TOOL, [], {"formato": "ubl", "factura": BASE}))
    assert err.value.code == "INVALID_OPTIONS" and err.value.detail.startswith("einvoice_invalid:BR-CO-16")


@needs_kosit
@respx.mock
def test_facturx_pdf_has_the_xml_and_metadata_and_goes_to_verapdf(make_ctx, fake_verapdf):
    from tools.base import Handoff

    from core.settings import get_settings

    _gotenberg()
    respx.route(url__startswith=get_settings().KOSIT_URL.rstrip("/")).pass_through()  # KoSIT de verdad
    ctx = make_ctx(TOOL, [], {"formato": "facturx", "perfil": "en16931", "factura": BASE})
    with pytest.raises(Handoff) as step:
        run(TOOL, ctx)
    assert (step.value.group, step.value.stage) == ("ocr", "verapdf")
    staged = ctx.store.job_dir(ctx.job_id) / "stage" / "0.pdf"
    with pikepdf.open(staged) as pdf:
        xml = pdf.attachments["factur-x.xml"].get_file().read_bytes()
        assert b"urn:cen.eu:en16931:2017" in xml
        assert pdf.attachments["factur-x.xml"].obj.AFRelationship == pikepdf.Name.Alternative
        xmp = pdf.Root.Metadata.read_bytes()
        assert b"EN 16931" in xmp and b"factur-x.xml" in xmp and b"<pdfaid:part>3</pdfaid:part>" in xmp
    ctx.stage = step.value.stage
    out = run(TOOL, ctx)
    assert [o["name"] for o in out] == ["factura-2026-0042.pdf", "factura-2026-0042.xml"]
    assert fake_verapdf[0] == [("factura-2026-0042.pdf", "3b")]


def test_facturae_signed_in_the_browser_passes_the_server_check():
    """F4-E2b (D-207): apps/web/test/xades.test.ts firma facturae.xml con xadesjs y la clave de rsa.p12 (FACTURAE_FIXTURE=1
    vuelve a escribir facturae-firmada.xml); aquí la comprueba el mismo motor que validar-factura-electronica (XSD y
    XAdES con signxml), y cualquier cambio posterior la invalida."""
    from core.settings import get_settings
    from tools.utils.facturas import lectura, motores

    data = (ROOT / "apps" / "web" / "test" / "fixtures" / "facturae-firmada.xml").read_bytes()
    root, _inv = lectura.read_invoice(data)
    result = motores.facturae(get_settings(), root, data, lectura.facturae_version(root), check_signature=True)
    assert result.accepted and not result.findings
    assert b"politica_de_firma_formato_facturae_v3_1.pdf" in data and b"<xades:ClaimedRole>emisor</xades:ClaimedRole>" in data
    tampered = data.replace(b"<InvoiceTotal>", b"<InvoiceTotal>1", 1)
    root, _inv = lectura.read_invoice(tampered)
    result = motores.facturae(get_settings(), root, tampered, lectura.facturae_version(root), check_signature=True)
    assert not result.accepted and [f.code for f in result.findings] == ["FIRMA"]



@needs_kosit
@pytest.mark.parametrize("cause,category,code", [("art20", "E", ""), ("art21", "G", "VATEX-EU-G"), ("art25", "K", "VATEX-EU-IC"),
                                                 ("isp", "AE", "VATEX-EU-AE"), ("nosujeta", "O", "VATEX-EU-O")])
@pytest.mark.parametrize("fmt", ["facturx", "xrechnung_ubl", "peppol", "ubl", "facturae"])
def test_zero_vat_uses_the_category_of_its_cause(cause, category, code, fmt, make_ctx):
    """Revisión de F4-E2: el IVA 0 % ya no es siempre E; cada causa lleva su categoría y su código VATEX (BT-121), y en
    Facturae su SpecialTaxableEvent, y todo pasa el validador."""
    from tools.utils.facturas import crear, generar

    zero = {"descripcion": "Exento", "cantidad": 1, "unidad": "ud", "precio": 100, "descuento": 0, "iva": 0}
    o = _options(fmt, causa_exencion=cause, motivo_exencion="Motivo legal",
                 lineas=[zero] if cause == "nosujeta" else BASE["lineas"] + [zero])
    data, syntax = generar.build(o.factura, fmt, "en16931")
    crear.validate(make_ctx(TOOL, [], {"formato": fmt}), data, syntax)
    if fmt == "facturae":
        assert b"<SpecialTaxableEventCode>" + (b"02" if cause in ("isp", "nosujeta") else b"01") in data
    else:
        assert f">{category}<".encode() in data
        if code:
            assert code.encode() in data
    if cause == "nosujeta" and fmt != "facturae":
        assert b'schemeID="VA"' not in data and b"<cac:PartyTaxScheme>" not in data  # BR-O-2: sin NIF-IVA


def test_facturae_ids_people_countries_and_batch_total():
    from lxml import etree

    from tools.utils.facturas import generar

    o = _options("facturae", irpf=15, recargo=True,
                 cliente={"nombre": "María José García López", "nif": "12345678-Z", "direccion": "Av. del Mar 3", "cp": "46001",
                          "ciudad": "Valencia", "pais": "ES"})
    root = etree.fromstring(generar.build(o.factura, "facturae", "en16931")[0])
    assert root.findtext(".//SellerParty//TaxIdentificationNumber") == "B12345674"  # sin «ES» en un NIF español
    assert [root.findtext(f".//BuyerParty//{t}") for t in ("Name", "FirstSurname", "SecondSurname")] == ["María José", "García", "López"]
    assert root.findtext(".//Batch/TotalInvoicesAmount/TotalAmount") == root.findtext(".//InvoiceTotals/InvoiceTotal") == "677.39"
    o = _options("facturae", cliente={"nombre": "Rossi S.p.A.", "nif": "IT12345678901", "direccion": "Via Roma 1", "cp": "00100",
                                      "ciudad": "Roma", "pais": "IT"})
    root = etree.fromstring(generar.build(o.factura, "facturae", "en16931")[0])
    assert root.findtext(".//BuyerParty//PersonTypeCode") == "J" and root.findtext(".//BuyerParty//ResidenceTypeCode") == "U"
    assert root.findtext(".//BuyerParty//CorporateName") == "Rossi S.p.A." and root.findtext(".//BuyerParty//CountryCode") == "ITA"
    o = _options("facturae", oficina_contable="EA0000001", organo_gestor="EA0000002", unidad_tramitadora="EA0000003")
    root = etree.fromstring(generar.build(o.factura, "facturae", "en16931")[0])
    assert [c.findtext("RoleTypeCode") for c in root.iter("AdministrativeCentre")] == ["01", "02", "03"]
    assert generar.vat_id("GR", "123456789") == "EL123456789" and generar.vat_id("ES", "B-12345674") == "ESB12345674"
    # Caracteres de control: fuera, en lugar de un error interno de lxml.
    assert b"ab" in generar.build(_options("ubl", notas="a\x0bb").factura, "ubl", "en16931")[0]


@needs_kosit
@respx.mock
def test_facturx_xrechnung_profile_names_its_file(make_ctx, fake_verapdf):
    from core.settings import get_settings
    from tools.base import Handoff

    _gotenberg()
    respx.route(url__startswith=get_settings().KOSIT_URL.rstrip("/")).pass_through()
    ctx = make_ctx(TOOL, [], {"formato": "facturx", "perfil": "xrechnung", "factura": BASE})
    with pytest.raises(Handoff):
        run(TOOL, ctx)
    with pikepdf.open(ctx.store.job_dir(ctx.job_id) / "stage" / "0.pdf") as pdf:
        assert list(pdf.attachments) == ["xrechnung.xml"]
        xmp = pdf.Root.Metadata.read_bytes()
        assert b"XRECHNUNG" in xmp and b"xrechnung.xml" in xmp
