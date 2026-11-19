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


@pytest.fixture(autouse=True)
def facturae_xsd(monkeypatch):
    from core.settings import get_settings

    monkeypatch.setattr(get_settings(), "FACTURAE_XSD_DIR", ROOT / "infra" / "facturae")


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
