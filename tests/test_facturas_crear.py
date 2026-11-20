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
        (_options("facturae", moneda="USD"), "einvoice_facturae_currency"),
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
