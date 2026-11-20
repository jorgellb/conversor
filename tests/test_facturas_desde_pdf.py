"""F4-E3: pdf-a-factura-electronica (A.2, D-208). Extracción (XML que ya trae el PDF, reglas sobre el texto y una
petición de IA con un cliente falso) y generación del Factur-X EN 16931 (KoSIT, OCRmyPDF a PDF/A-3b con las páginas del
original, `factur-x.xml` y veraPDF simulado)."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pikepdf
import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fixtures"))

from test_desde_pdf import fake_verapdf, mrr, no_ghostscript  # noqa: E402,F401
from test_facturas import needs_kosit  # noqa: E402
from test_facturas_crear import BASE  # noqa: E402
from test_facturas_pdf import _gotenberg, facturae_xsd  # noqa: E402,F401
from test_tools import make_ctx, run  # noqa: E402,F401

TOOL = "pdf-a-factura-electronica"
TEXT = ["FACTURA Nº 2026/0099", "Fecha: 20/11/2026   Vencimiento: 20/12/2026", "Estudio Pérez S.L.  NIF B12345674",
        "Cliente S.A.  CIF A58818501", "Diseño de logotipo   1   450,00", "Base imponible 450,00  IVA 21% 94,50",
        "TOTAL FACTURA 544,50 EUR", "IBAN ES91 2100 0418 4502 0005 1332"]


def _text_pdf(tmp_path: Path, lines=TEXT, name="factura.pdf") -> Path:
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(595, 842))
    font = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica,
                              Encoding=pikepdf.Name.WinAnsiEncoding)
    page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
    ops = [b"BT /F1 11 Tf 50 780 Td 16 TL"]
    for line in lines:
        ops.append(b"(" + line.encode("cp1252").replace(b"(", b"\\(").replace(b")", b"\\)") + b") Tj T*")
    ops.append(b"ET")
    page.obj.Contents = pdf.make_stream(b"\n".join(ops))
    path = tmp_path / name
    pdf.save(path)
    return path


def _embedded_pdf(tmp_path: Path, lines=TEXT, name="factura.pdf") -> Path:
    """Como una factura de verdad: el texto con DejaVu Sans incrustada (TrueType, WinAnsi), que se puede pasar a PDF/A."""
    from fontTools.ttLib import TTFont

    ttf = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    tt = TTFont(ttf)
    scale = 1000 / tt["head"].unitsPerEm
    cmap, hmtx = tt.getBestCmap(), tt["hmtx"]
    widths = []
    for code in range(32, 256):
        ch = bytes([code]).decode("cp1252", "replace")
        glyph = cmap.get(ord(ch))
        widths.append(round(hmtx[glyph][0] * scale) if glyph else 0)
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(595, 842))
    descriptor = pikepdf.Dictionary(Type=pikepdf.Name.FontDescriptor, FontName=pikepdf.Name("/DejaVuSans"), Flags=32,
                                    FontBBox=[-1021, -463, 1793, 1232], ItalicAngle=0, Ascent=928, Descent=-236, CapHeight=729,
                                    StemV=80, FontFile2=pdf.make_stream(Path(ttf).read_bytes()))
    font = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.TrueType, BaseFont=pikepdf.Name("/DejaVuSans"),
                              FirstChar=32, LastChar=255, Widths=widths, FontDescriptor=pdf.make_indirect(descriptor),
                              Encoding=pikepdf.Name.WinAnsiEncoding)
    page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pdf.make_indirect(font)))
    ops = [b"BT /F1 11 Tf 50 780 Td 16 TL"]
    for line in lines:
        ops.append(b"(" + line.encode("cp1252").replace(b"(", b"\\(").replace(b")", b"\\)") + b") Tj T*")
    ops.append(b"ET")
    page.obj.Contents = pdf.make_stream(b"\n".join(ops))
    path = tmp_path / name
    pdf.save(path)
    return path


def _data(out) -> dict:
    [o] = out
    assert o["name"] == "datos-factura.json"
    return json.loads(Path(o["path"]).read_text(encoding="utf-8"))


def test_rules_find_number_dates_tax_ids_iban_and_total(make_ctx, tmp_path):
    from tools.utils.facturas.desde_pdf import rules

    data, warnings = rules("\n".join(TEXT))
    assert data["numero"] == "2026/0099" and data["fecha"] == "2026-11-20" and data["vencimiento"] == "2026-12-20"
    assert (data["emisor"]["nif"], data["cliente"]["nif"]) == ("B12345674", "A58818501")
    assert data["iban"] == "ES9121000418450200051332" and data["forma_pago"] == "58"
    assert warnings == ["total:544.5"]
    out = _data(run(TOOL, make_ctx(TOOL, [_text_pdf(tmp_path)], {"fase": "extraer"})))
    assert out["origen"] == "reglas" and out["factura"]["numero"] == "2026/0099"


def test_scanned_pdf_says_so(make_ctx, tmp_path):
    out = _data(run(TOOL, make_ctx(TOOL, [_text_pdf(tmp_path, lines=["x"])], {"fase": "extraer"})))
    assert out["origen"] == "vacio" and out["avisos"] == ["scanned"]


def test_ai_fills_the_form_with_one_request(make_ctx, tmp_path, monkeypatch):
    from tools.base import Handoff

    ctx = make_ctx(TOOL, [_text_pdf(tmp_path)], {"fase": "extraer", "ia": True})
    with pytest.raises(Handoff) as step:
        run(TOOL, ctx)
    assert (step.value.group, step.value.stage) == ("ai", "ai")
    calls = []
    answer = {"es_factura": True, "numero": "2026/0099", "fecha": "2026-11-20", "vencimiento": "", "moneda": "EUR",
              "emisor": {"nombre": "Estudio Pérez S.L.", "nif": "B12345674", "direccion": "", "cp": "", "ciudad": "Madrid", "provincia": "",
                         "pais": "ES", "correo": ""},
              "cliente": {"nombre": "Cliente S.A.", "nif": "", "direccion": "", "cp": "", "ciudad": "", "provincia": "", "pais": "ES", "correo": ""},
              "lineas": [{"descripcion": "Diseño de logotipo", "cantidad": 1, "unidad": "ud", "precio": 450, "descuento": None, "iva": 21}],
              "iban": "", "total": 544.5}

    def complete_json(messages, **kw):
        calls.append(messages)
        return answer, None

    ctx.ai = SimpleNamespace(complete_json=complete_json, budget=SimpleNamespace(ensure=lambda n: calls.append(("ensure", n)), used=1),
                             models_used=["falso/modelo:free"])
    ctx.stage = "ai"
    out = _data(run(TOOL, ctx))
    assert out["origen"] == "ia" and calls[0] == ("ensure", 1) and len(calls) == 2
    f = out["factura"]
    assert f["emisor"]["ciudad"] == "Madrid" and f["cliente"]["nif"] == "A58818501"  # lo de las reglas se conserva
    assert f["iban"] == "ES9121000418450200051332" and f["lineas"][0]["descuento"] == 0
    assert "<<<" in calls[1][1]["content"] and "FACTURA" in calls[1][1]["content"]


@needs_kosit
@respx.mock
def test_embedded_xml_is_read_instead_of_the_text(make_ctx, tmp_path, fake_verapdf):
    """Un Factur-X que ya trae su XML: los datos salen de él, sin reglas ni IA."""
    from core.settings import get_settings
    from tools.base import Handoff

    _gotenberg()
    respx.route(url__startswith=get_settings().KOSIT_URL.rstrip("/")).pass_through()
    ctx = make_ctx("crear-factura-electronica", [], {"formato": "facturx", "perfil": "en16931", "factura": BASE})
    with pytest.raises(Handoff):
        run("crear-factura-electronica", ctx)
    facturx = tmp_path / "con-xml.pdf"
    facturx.write_bytes((ctx.store.job_dir(ctx.job_id) / "stage" / "0.pdf").read_bytes())
    out = _data(run(TOOL, make_ctx(TOOL, [facturx], {"fase": "extraer", "ia": True})))
    assert out["origen"] == "xml"
    f = out["factura"]
    assert f["numero"] == "2026/0042" and f["fecha"] == "2026-11-20" and f["emisor"]["nombre"] == "Estudio Pérez S.L."
    assert len(f["lineas"]) == 3 and f["lineas"][1]["iva"] == 21


@needs_kosit
@respx.mock
def test_generate_keeps_the_original_pages_and_embeds_the_xml(make_ctx, tmp_path, fixtures_dir, fake_verapdf, no_ghostscript):
    from core.settings import get_settings
    from tools.base import Handoff

    respx.route(url__startswith=get_settings().KOSIT_URL.rstrip("/")).pass_through()
    src = _embedded_pdf(tmp_path)
    ctx = make_ctx(TOOL, [src], {"fase": "generar", "factura": BASE})
    with pytest.raises(Handoff) as step:
        run(TOOL, ctx)
    assert (step.value.group, step.value.stage) == ("ocr", "pdfa")
    ctx.stage = step.value.stage
    out = run(TOOL, ctx)
    assert [o["name"] for o in out] == ["factura-facturx.pdf", "factura-facturx.xml"]
    assert "Cumple: PDF/A-3b" in out[0]["note"]
    import pypdfium2 as pdfium

    with pikepdf.open(src) as original:
        pages = len(original.pages)
    doc = pdfium.PdfDocument(out[0]["path"])
    assert len(doc) == pages and "FACTURA Nº 2026/0099" in doc[0].get_textpage().get_text_range()  # las páginas del original
    doc.close()
    with pikepdf.open(out[0]["path"]) as pdf:
        xml = pdf.attachments["factur-x.xml"].get_file().read_bytes()
        assert b"urn:cen.eu:en16931:2017" in xml and xml == Path(out[1]["path"]).read_bytes()
        meta = pdf.Root.Metadata.read_bytes()
        assert b"<pdfaid:part>3</pdfaid:part>" in meta and b"factur-x.xml" in meta
    assert fake_verapdf[0] == [("factura-facturx.pdf", "3b")]


@needs_kosit
def test_generate_refuses_what_the_validator_rejects(make_ctx, tmp_path):
    from core.errors import ToolError

    with pytest.raises(ToolError) as err:
        run(TOOL, make_ctx(TOOL, [_text_pdf(tmp_path)], {"fase": "generar", "factura": {**BASE, "recargo": True}}))
    assert err.value.detail == "einvoice_surcharge"


@needs_kosit
@respx.mock
def test_fonts_not_embedded_need_ghostscript(make_ctx, tmp_path, no_ghostscript):
    """Sin Ghostscript (7.5) no se puede incrustar una fuente que el PDF no trae: error propio, no un PDF/A falso."""
    from core.errors import ToolError
    from core.settings import get_settings
    from tools.base import Handoff

    respx.route(url__startswith=get_settings().KOSIT_URL.rstrip("/")).pass_through()
    ctx = make_ctx(TOOL, [_text_pdf(tmp_path)], {"fase": "generar", "factura": BASE})
    with pytest.raises(Handoff) as step:
        run(TOOL, ctx)
    ctx.stage = step.value.stage
    with pytest.raises(ToolError) as err:
        run(TOOL, ctx)
    assert err.value.code == "PDFA_NEEDS_GHOSTSCRIPT"


# --- Revisión de F4-E3 (D-211) ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("text,number", [
    ("FACTURA SIMPLIFICADA Nº 123", "123"), ("Factura rectificativa nº R-12", "R-12"), ("Factura Numero 55", "55"),
    ("Invoice date 12/03/2026\nInvoice no. INV-7", "INV-7"), ("Datos de facturación\nFactura: 2026/12", "2026/12"),
])
def test_rules_number_needs_a_digit_and_skips_words(text, number):
    from tools.utils.facturas.desde_pdf import rules

    assert rules(text)[0].get("numero") == number


def test_rules_totals_nifs_dates_and_iban_edge_cases():
    from tools.utils.facturas.desde_pdf import rules

    data, warnings = rules("Subtotal 100,00\nTOTAL 1.234 €\nCIF: B-12345674 y cliente 12.345.678-Z\nPedido 12345678A\n"
                           "Pedido del 01/01/2026\nFecha factura: 15/02/2026\nVencimiento 15/03/2026\n"
                           "IBAN ES91 2100 0418 4502 0005 1332 BIC CAIXESBBXXX")
    assert warnings == ["total:1234.0"]
    assert (data["emisor"]["nif"], data["cliente"]["nif"]) == ("B12345674", "12345678Z")  # 12345678A no cuadra
    assert (data["fecha"], data["vencimiento"]) == ("2026-02-15", "2026-03-15")
    assert data["iban"] == "ES9121000418450200051332"
    assert "iban" not in rules("IBAN ES91 2100 0418 4502 0005 1333")[0]  # mod 97


def test_ai_answer_is_normalised_before_use():
    from tools.utils.facturas.desde_pdf import clean

    out = clean({"es_factura": True, "numero": "7", "fecha": "20/11/2026", "vencimiento": "", "moneda": "eur", "iban": "x",
                 "emisor": {"nombre": "A", "nif": "B-12345674", "pais": "España"}, "cliente": {},
                 "lineas": [{"descripcion": "X", "cantidad": "2", "unidad": "ud", "precio": "450,00", "descuento": None, "iva": "21%"}],
                 "total": "1.089,00 €"})
    assert out["fecha"] == "2026-11-20" and out["moneda"] == "EUR" and out["iban"] == ""
    assert out["emisor"]["nif"] == "B12345674" and out["emisor"]["pais"] == ""
    assert out["lineas"][0] == {"descripcion": "X", "cantidad": 2.0, "unidad": "ud", "precio": 450.0, "descuento": 0, "iva": 21.0}
    assert out["total"] == 1089.0
    for bad in ({"lineas": "x"}, {"lineas": [], "emisor": "ACME"}, {"lineas": ["texto"]}):
        with pytest.raises(ValueError):
            clean(bad)


def test_generar_never_reserves_ai():
    from tools.utils.specs import PdfAFacturaOptions

    assert PdfAFacturaOptions.model_validate({"fase": "generar", "ia": True}).ia is False


@needs_kosit
@respx.mock
def test_embedded_xml_keeps_the_total_and_can_be_regenerated(make_ctx, tmp_path, fake_verapdf, no_ghostscript):
    """El XML del PDF da el mismo total al regenerar (el descuento de línea va en el precio) y su IBAN y su forma de
    pago; y un Factur-X ya hecho (con /PageMode /UseAttachments) se puede volver a generar."""
    from core.settings import get_settings
    from tools.base import Handoff
    from tools.utils.facturas import generar
    from tools.utils.specs import FacturaE

    _gotenberg()
    respx.route(url__startswith=get_settings().KOSIT_URL.rstrip("/")).pass_through()
    ctx = make_ctx("crear-factura-electronica", [], {"formato": "facturx", "perfil": "en16931", "factura": BASE})
    with pytest.raises(Handoff):
        run("crear-factura-electronica", ctx)
    facturx = tmp_path / "con-xml.pdf"
    with pikepdf.open(ctx.store.job_dir(ctx.job_id) / "stage" / "0.pdf") as pdf:
        pdf.Root.PageMode = pikepdf.Name.UseAttachments
        pdf.save(facturx)
    out = _data(run(TOOL, make_ctx(TOOL, [facturx], {"fase": "extraer"})))
    f = out["factura"]
    assert out["origen"] == "xml" and "total:739.72" in out["avisos"]
    assert f["iban"] == "ES9121000418450200051332" and f["forma_pago"] == "58" and f["emisor"]["direccion"] == "Calle Mayor 1"
    rebuilt = FacturaE.model_validate({**BASE, **{k: v for k, v in f.items() if k in ("numero", "fecha", "lineas", "iban", "forma_pago")}})
    assert str(generar.calcular(rebuilt).payable) == "739.72"
    gen = make_ctx(TOOL, [facturx], {"fase": "generar", "factura": BASE})
    with pytest.raises(Handoff) as step:
        run(TOOL, gen)
    gen.stage = step.value.stage
    result = run(TOOL, gen)
    with pikepdf.open(result[0]["path"]) as pdf:
        assert list(pdf.attachments) == ["factur-x.xml"]


@needs_kosit
@respx.mock
def test_page_limit_and_signed_pdf_in_generar(make_ctx, tmp_path, no_ghostscript):
    from core.errors import ToolError
    from core.settings import get_settings
    from tools.base import Handoff

    respx.route(url__startswith=get_settings().KOSIT_URL.rstrip("/")).pass_through()
    big = pikepdf.new()
    for _ in range(140):
        big.add_blank_page()
    path = tmp_path / "grande.pdf"
    big.save(path)
    with pytest.raises(ToolError) as err:
        run(TOOL, make_ctx(TOOL, [path], {"fase": "generar", "factura": BASE}, plan="anon"))
    assert err.value.code == "LIMIT_EXCEEDED"
    signed = _embedded_pdf(tmp_path, name="firmado.pdf")
    with pikepdf.open(signed, allow_overwriting_input=True) as pdf:
        sig = pdf.make_indirect(pikepdf.Dictionary(FT=pikepdf.Name.Sig, T=pikepdf.String("Firma1"), V=pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name.Sig, Filter=pikepdf.Name("/Adobe.PPKLite"), Contents=pikepdf.String("0" * 16)))))
        pdf.Root.AcroForm = pikepdf.Dictionary(Fields=[sig], SigFlags=3)
        pdf.save(signed)
    ctx = make_ctx(TOOL, [signed], {"fase": "generar", "factura": BASE})
    with pytest.raises(Handoff) as step:
        run(TOOL, ctx)
    ctx.stage = step.value.stage
    with pytest.raises(ToolError) as err:
        run(TOOL, ctx)
    assert err.value.detail == "einvoice_signed_pdf"
