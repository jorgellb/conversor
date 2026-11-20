"""F4, lote D2: factura-electronica-a-pdf, facturae-a-pdf, ubl-a-pdf y cii-a-pdf (A.2 y 7.14).

Gotenberg se simula con respx (devuelve un PDF en blanco; el PDF/A-3b real lo hace su Chromium en e2e-compose) y
veraPDF con el informe MRR de `test_desde_pdf.mrr`; lo que se comprueba aquí es lo que hace el código: la plantilla, la
petición a Gotenberg, el XML incrustado byte a byte como archivo asociado y el paso a `ocr`.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pikepdf
import pytest
import respx
from httpx import Response

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fixtures"))

import facturas  # noqa: E402
from test_desde_pdf import fake_verapdf, mrr  # noqa: E402,F401 - fixture compartida
from test_tools import make_ctx, run  # noqa: E402,F401 - fixture compartida

CHROMIUM = "/forms/chromium/convert/html"


LOCAL_KOSIT = Path.home() / ".cache" / "conversor-motores" / "kosit" / "root"


@pytest.fixture(autouse=True)
def facturae_xsd(monkeypatch):
    """XSD de Facturae del repositorio y de UBL y CII de la configuración de KoSIT (KOSIT_HOME en la CI, la caché local
    de motores aquí)."""
    import os

    from core.settings import get_settings

    monkeypatch.setattr(get_settings(), "FACTURAE_XSD_DIR", ROOT / "infra" / "facturae")
    home = Path(os.environ.get("KOSIT_HOME") or LOCAL_KOSIT)
    if not (home / "xrechnung" / "resources" / "ubl").exists():
        pytest.skip("sin los XSD de UBL y CII de KoSIT (KOSIT_HOME)")
    monkeypatch.setattr(get_settings(), "KOSIT_HOME", home)


def _blank() -> bytes:
    pdf = pikepdf.new()
    pdf.add_blank_page()
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def _gotenberg():
    from core.settings import get_settings

    return respx.post(f"{get_settings().GOTENBERG_URL.rstrip('/')}{CHROMIUM}").mock(return_value=Response(200, content=_blank()))


def _file(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _html_sent(route) -> str:
    body = route.calls.last.request.content
    start = body.index(b"<!doctype html>")
    return body[start:body.index(b"</html>", start) + 7].decode()


def _first_stage(make_ctx, tool: str, files, options=None, locale="es"):
    from tools.base import Handoff

    ctx = make_ctx(tool, files, options or {})
    ctx.locale = locale
    with pytest.raises(Handoff) as step:
        run(tool, ctx)
    return ctx, step.value


@respx.mock
def test_pdfa3_embeds_the_original_xml_byte_for_byte_and_hands_off_to_verapdf(make_ctx, tmp_path, fake_verapdf):
    route = _gotenberg()
    xml = facturas.ubl_invoice(facturas.UBL_PEPPOL)
    ctx, step = _first_stage(make_ctx, "factura-electronica-a-pdf", [_file(tmp_path, "F-42.xml", xml)])
    body = route.calls.last.request.content.decode("latin-1")
    assert 'name="pdfa"\r\n\r\nPDF/A-3b' in body
    assert (step.group, step.queue, step.stage) == ("ocr", "ocr", "verapdf")
    staged = ctx.store.job_dir(ctx.job_id) / "stage" / "0.pdf"
    with pikepdf.open(staged) as pdf:
        assert pdf.attachments["F-42.xml"].get_file().read_bytes() == xml  # sin cambiar un byte
        spec = pdf.attachments["F-42.xml"].obj
        assert spec.AFRelationship == pikepdf.Name.Source and spec.EF.F.Subtype == pikepdf.Name("/application/xml")
        assert spec.objgen in [f.objgen for f in pdf.Root.AF]
    ctx.stage = step.stage
    out = run("factura-electronica-a-pdf", ctx)
    assert fake_verapdf[0] == [("F-42.pdf", "3b")]
    assert out[0]["name"] == "F-42.pdf" and out[0]["note"] == ("PDF/A-3 con el XML original incrustado sin cambios (F-42.xml). "
                                                              "Cumple: PDF/A-3b.")


@respx.mock
def test_plain_pdf_needs_no_verapdf_and_carries_no_xml(make_ctx, tmp_path):
    route = _gotenberg()
    out = run("cii-a-pdf", make_ctx("cii-a-pdf", [_file(tmp_path, "f.xml", facturas.cii_invoice())], {"salida": "pdf"}))
    assert 'name="pdfa"' not in route.calls.last.request.content.decode("latin-1")
    with pikepdf.open(out[0]["path"]) as pdf:
        assert not pdf.attachments and "/AF" not in pdf.Root
    assert out[0]["note"] == "PDF sin el XML incrustado."


@respx.mock
def test_representation_content_language_and_escaping(make_ctx, tmp_path):
    route = _gotenberg()
    hostile = facturas.ubl_invoice().replace(b"Cliente Pruebas SA", b"Cliente &lt;script&gt;alert(1)&lt;/script&gt;")
    _first_stage(make_ctx, "ubl-a-pdf", [_file(tmp_path, "f.xml", hostile)])
    page = _html_sent(route)
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "Factura" in page and "Importe a pagar" in page and "2002.55 EUR" in page and "Licencia anual del portal" in page
    assert "ES9121000418450200051332" in page and "Desglose de impuestos" in page
    _first_stage(make_ctx, "ubl-a-pdf", [_file(tmp_path, "g.xml", facturas.ubl_invoice())], {"idioma": "en"})
    assert '<html lang="en">' in _html_sent(route) and "Amount due" in _html_sent(route)
    # Facturae declara su idioma: con «el de la factura» manda el de la factura aunque la página esté en inglés.
    _first_stage(make_ctx, "facturae-a-pdf", [_file(tmp_path, "h.xml", facturas.facturae())], locale="en")
    assert '<html lang="es">' in _html_sent(route)


@respx.mock
def test_wrong_syntax_invalid_facturae_and_not_an_invoice(make_ctx, tmp_path):
    from core.errors import ToolError

    _gotenberg()
    with pytest.raises(ToolError) as err:
        run("facturae-a-pdf", make_ctx("facturae-a-pdf", [_file(tmp_path, "u.xml", facturas.ubl_invoice())]))
    assert (err.value.code, err.value.detail) == ("UNSUPPORTED_FORMAT", "invoice_syntax:ubl>facturae")
    broken = facturas.facturae().replace(b"<Modality>I</Modality>", b"<Modality>X</Modality>")
    with pytest.raises(ToolError) as err:
        run("facturae-a-pdf", make_ctx("facturae-a-pdf", [_file(tmp_path, "m.xml", broken)]))
    assert err.value.detail == "facturae_xsd_invalid"
    with pytest.raises(ToolError) as err:
        run("factura-electronica-a-pdf", make_ctx("factura-electronica-a-pdf", [_file(tmp_path, "n.xml", b"<pedido/>")]))
    assert err.value.code == "UNSUPPORTED_FORMAT"
    with pytest.raises(ToolError) as err:
        run("factura-electronica-a-pdf", make_ctx("factura-electronica-a-pdf", [_file(tmp_path, "x.xml",
            b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/hostname">]><x>&e;</x>')]))
    assert err.value.code == "CORRUPT_FILE"


@respx.mock
def test_batch_produces_a_zip(make_ctx, tmp_path, fake_verapdf):
    _gotenberg()
    ctx, step = _first_stage(make_ctx, "factura-electronica-a-pdf",
                             [_file(tmp_path, "a.xml", facturas.ubl_invoice()), _file(tmp_path, "b.xml", facturas.cii_invoice())])
    ctx.stage = step.stage
    out = run("factura-electronica-a-pdf", ctx)
    assert [o["name"] for o in out] == ["a.pdf", "b.pdf", "facturas-pdf.zip"]


# --- Revisión de F4-D2 (D-194) ---------------------------------------------------------------------------------------


def _facturae_tree(data: bytes):
    from lxml import etree

    return etree.fromstring(data)


def _el(tag: str, text: str | None = None, *children):
    from lxml import etree

    el = etree.Element(tag)
    el.text = text
    el.extend(children)
    return el


def _withheld(rate: str, base: str, amount: str):
    return _el("TaxesWithheld", None, _el("Tax", None, _el("TaxTypeCode", "04"), _el("TaxRate", rate),
                                         _el("TaxableBase", None, _el("TotalAmount", base)), _el("TaxAmount", None, _el("TotalAmount", amount))))


def _irpf_facturae() -> bytes:
    """Facturae de un profesional con IRPF del 15 %: TaxesWithheld en cada línea (antes de TaxesOutputs) y en la
    factura (después), y TotalTaxesWithheld."""
    from lxml import etree

    root = _facturae_tree(facturas.facturae())
    for line in root.iter("InvoiceLine"):
        line.find("TaxesOutputs").addprevious(_withheld("15.00", line.findtext("TotalCost"), "0.00"))
    invoice = root.find("Invoices/Invoice")
    invoice.find("TaxesOutputs").addnext(_withheld("15.00", "1655.00", "248.25"))
    invoice.find("InvoiceTotals/TotalTaxesWithheld").text = "248.25"
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def test_facturae_irpf_is_not_taken_for_vat_and_withholdings_are_shown():
    from tools.utils.facturas import representar

    data = _irpf_facturae()
    d = representar.detail(data)
    assert {line["iva"] for line in d.lines} == {"21.00"}
    assert d.withheld == [{"categoria": "04", "tipo": "15.00", "base": "1655.00", "cuota": "248.25"}]
    assert d.withheld_total == "248.25"
    page = representar.render(d, "es", "Facturae 3.2.2", "f.xml")
    assert "<h2>Retenciones</h2>" in page and "<th>Retenciones</th><td class=\"r\">248.25 EUR</td>" in page
    assert "Retenciones" not in representar.render(representar.detail(facturas.facturae()), "es", "", "f.xml")  # 0.00 no se enseña


def test_facturae_parties_ignore_administrative_centres_and_join_surnames():
    from lxml import etree

    from tools.utils.facturas import representar

    root = _facturae_tree(facturas.facturae())
    buyer = root.find("Parties/BuyerParty")
    centre = _el("AdministrativeCentres", None, _el("AdministrativeCentre", None, _el("CentreCode", "L01"), _el("RoleTypeCode", "01"),
                                                         _el("Name", "Oficina contable"),
                                                         _el("AddressInSpain", None, _el("Address", "Plaza Oficina 9"), _el("PostCode", "41001"),
                                                             _el("Town", "Sevilla"), _el("Province", "Sevilla"), _el("CountryCode", "ESP"))))
    buyer.find("LegalEntity").addprevious(centre)
    seller = root.find("Parties/SellerParty")
    legal = seller.find("LegalEntity")
    address = legal.find("AddressInSpain")
    person = _el("Individual", None, _el("Name", "Juan"), _el("FirstSurname", "Pérez"), _el("SecondSurname", "García"), address)
    legal.addprevious(person)
    seller.remove(legal)
    seller.find("TaxIdentification/PersonTypeCode").text = "F"
    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
    d = representar.detail(data)
    assert d.seller.name == "Juan Pérez García" and d.seller.address[0] == "Calle Mayor 1"
    assert d.buyer.name == "Cliente Pruebas SA" and "Plaza Oficina 9" not in d.buyer.address


def test_truncated_lines_and_facturae_batch_are_said():
    import re

    from lxml import etree

    from tools.utils.facturas import representar

    base = facturas.ubl_invoice()
    line = re.search(rb"<cac:InvoiceLine>.*?</cac:InvoiceLine>", base, re.S).group(0)
    many = base.replace(line, line * 600, 1)  # 2 líneas de muestra: 600 copias de la primera + la segunda = 601
    d = representar.detail(many)
    assert len(d.lines) == 500 and representar.warnings(d, "es") == ["Se muestran 500 de 601 líneas; el XML incrustado las tiene todas."]
    root = _facturae_tree(facturas.facturae())
    invoices = root.find("Invoices")
    invoices.append(etree.fromstring(etree.tostring(invoices.find("Invoice"))))
    d = representar.detail(etree.tostring(root))
    assert representar.warnings(d, "en") == ["This file contains 2 invoices; the first one is represented."]


@respx.mock
def test_one_bad_file_does_not_stop_the_batch(make_ctx, tmp_path, fake_verapdf):
    _gotenberg()
    files = [_file(tmp_path, "buena.xml", facturas.facturae()), _file(tmp_path, "ubl.xml", facturas.ubl_invoice()),
             _file(tmp_path, "nada.xml", b"<pedido/>")]
    ctx, step = _first_stage(make_ctx, "facturae-a-pdf", files)
    ctx.stage = step.stage
    out = run("facturae-a-pdf", ctx)
    names = [o["name"] for o in out]
    assert names == ["buena.pdf", "no-convertidas.txt", "facturas-pdf.zip"]
    text = Path(out[1]["path"]).read_text(encoding="utf-8")
    assert "- ubl.xml: Esta página convierte otra sintaxis" in text and "- nada.xml: El archivo no es una factura" in text
    assert out[1]["note"] == "2 archivo(s) no se han convertido: mira el motivo en este archivo."


@respx.mock
def test_ubl_and_cii_are_checked_against_their_xsd(make_ctx, tmp_path):
    from core.errors import ToolError

    _gotenberg()
    bad = facturas.ubl_invoice().replace(b"<cbc:IssueDate>", b"<cbc:Basura>x</cbc:Basura><cbc:IssueDate>", 1)
    with pytest.raises(ToolError) as err:
        run("ubl-a-pdf", make_ctx("ubl-a-pdf", [_file(tmp_path, "mal.xml", bad)], {"salida": "pdf"}))
    assert (err.value.code, err.value.detail) == ("CORRUPT_FILE", "invoice_xsd_invalid")
    out = run("cii-a-pdf", make_ctx("cii-a-pdf", [_file(tmp_path, "c.xml", facturas.cii_invoice(facturas.CII_MINIMUM))], {"salida": "pdf"}))
    assert out[0]["name"] == "c.pdf"


@respx.mock
def test_verapdf_failure_still_delivers_the_pdf_and_a_failed_check_brings_the_report(make_ctx, tmp_path, fake_verapdf, monkeypatch):
    from core.errors import ErrorCode, ToolError
    from test_desde_pdf import mrr as make_mrr

    _gotenberg()
    ctx, step = _first_stage(make_ctx, "factura-electronica-a-pdf", [_file(tmp_path, "a.xml", facturas.ubl_invoice())])
    ctx.stage = step.stage

    def broken(*_a, **_k):
        raise ToolError(ErrorCode.ENGINE_FAILED, "veraPDF")

    with monkeypatch.context() as m:
        m.setattr("tools.ocr.verapdf.run_verapdf", broken)
        out = run("factura-electronica-a-pdf", ctx)
    assert [o["name"] for o in out] == ["a.pdf"] and out[0]["note"].endswith("No se ha podido comprobar con veraPDF.")
    ctx, step = _first_stage(make_ctx, "factura-electronica-a-pdf", [_file(tmp_path, "b.xml", facturas.ubl_invoice())])
    ctx.stage = step.stage
    fake_verapdf[1]["xml"] = make_mrr(False)
    out = run("factura-electronica-a-pdf", ctx)
    assert out[0]["note"].startswith("PDF/A-3 con el XML original") and "No cumple" in out[0]["note"]
    assert any(o["name"].endswith(".html") for o in out)
