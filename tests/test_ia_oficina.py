"""F6-D (7.6, 6.3, D-239): traducir-word, traducir-excel y traducir-powerpoint conservando el formato, y manuscrito-a-texto
con un modelo que admite imágenes, de extremo a extremo con el proveedor falso (traduce poniendo «[inglés] » delante)."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from helpers import auth
from test_ia import _model, _models, ai  # noqa: F401 - fixture compartida
from test_ia_documentos import _out, _run

pytestmark = pytest.mark.integration


def _docx(tmp_path: Path) -> Path:
    from docx import Document
    from docx.shared import Inches
    from PIL import Image

    doc = Document()
    doc.add_heading("Informe anual", level=1)
    p = doc.add_paragraph("El resultado fue ")
    p.add_run("muy bueno").bold = True
    p.add_run(" este año.")
    doc.add_paragraph("12.345,67")  # sin letras: no se manda
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Ventas"
    table.cell(0, 1).text = "Gastos"
    img = tmp_path / "logo.png"
    Image.new("RGB", (30, 20), "red").save(img)
    doc.add_picture(str(img), width=Inches(1))
    doc.sections[0].header.paragraphs[0].text = "Confidencial"
    path = tmp_path / "informe.docx"
    doc.save(str(path))
    return path


def test_runs_are_grouped_by_format_and_put_back():
    from lxml import etree

    from tools.ai.oficina import KINDS, apply, paragraphs_of

    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml = (f'<w:document xmlns:w="{w}"><w:body><w:p><w:r><w:t>Hola </w:t></w:r><w:r><w:t>a </w:t></w:r>'
           '<w:r><w:rPr><w:b/></w:rPr><w:t>todos</w:t></w:r><w:r><w:tab/><w:t>fin</w:t></w:r>'
           '<w:r><w:drawing><w:txbxContent><w:p><w:r><w:t>Caja</w:t></w:r></w:p></w:txbxContent></w:drawing></w:r></w:p></w:body></w:document>')
    root = etree.fromstring(xml)
    paras = paragraphs_of(root, KINDS["traducir-word"])
    assert [p.texts() for p in paras] == [["Hola a ", "todos", "fin"], ["Caja"]]
    assert paras[0].source() == "<0>Hola a </0><1>todos</1><2>fin</2>"
    apply(paras[0], "<1>everyone</1> <0>Hello </0><2>end</2>")
    assert paras[0].texts() == ["Hello ", "everyone", "end"]
    apply(paras[0], "Tags lost entirely")
    assert paras[0].texts() == ["Tags lost entirely", "", ""]


def test_translate_word_keeps_runs_tables_header_and_image(api, ai, user_token, tus_upload, services, tmp_path):
    from docx import Document

    src = _docx(tmp_path)
    token, job = _run(api, user_token, tus_upload, src, "ia-word", "traducir-word", {"destino": "en"})
    assert job["status"] == "succeeded", job
    assert job["outputs"][0]["name"] == "informe-traducido-en.docx" and "Traducción hecha con IA" in job["outputs"][0]["note"]
    out = _out(services, job)
    doc = Document(str(out))
    texts = [p.text for p in doc.paragraphs]
    assert texts[0].startswith("[inglés] Informe anual")
    para = doc.paragraphs[1]
    assert [r.bold for r in para.runs] == [None, True, None]
    assert para.runs[0].text.startswith("[inglés] El resultado fue") and para.runs[1].text == "muy bueno"
    assert "12.345,67" in texts
    assert doc.tables[0].cell(0, 0).text.startswith("[inglés] Ventas")
    assert doc.sections[0].header.paragraphs[0].text.startswith("[inglés] Confidencial")
    with zipfile.ZipFile(src) as a, zipfile.ZipFile(out) as b:
        media = [n for n in a.namelist() if n.startswith("word/media/")]
        assert media and all(a.read(n) == b.read(n) for n in media)
    # Un solo lote: los textos repetidos o sin letras no se mandan.
    sent = ai.calls[-1]["messages"][1]["content"]
    assert "12.345,67" not in sent and "<0>El resultado fue </0><1>muy bueno</1>" in sent
    assert "conserva todas las etiquetas" in ai.calls[-1]["messages"][0]["content"]


def test_translate_excel_strings_only(api, ai, user_token, tus_upload, services, tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ventas"
    ws.append(["Producto", "Precio", "Total"])
    ws.append(["Manzanas", 3, "=B2*2"])
    ws.append(["Peras", 4, "=B3*2"])
    path = tmp_path / "ventas.xlsx"
    wb.save(path)
    token, job = _run(api, user_token, tus_upload, path, "ia-excel", "traducir-excel", {"destino": "en"})
    assert job["status"] == "succeeded", job
    out = openpyxl.load_workbook(_out(services, job))
    ws = out["Ventas"]  # el nombre de la hoja no cambia: las fórmulas lo usan
    assert ws["A1"].value.startswith("[inglés] Producto") and ws["A2"].value.startswith("[inglés] Manzanas")
    assert ws["B2"].value == 3 and ws["C2"].value == "=B2*2"


def test_translate_powerpoint_with_notes(api, ai, user_token, tus_upload, services, tmp_path):
    from pptx import Presentation

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Plan de ventas"
    body = slide.placeholders[1].text_frame
    body.text = "Primer objetivo"
    run = body.add_paragraph().add_run()
    run.text = "Crecer un diez por ciento"
    run.font.bold = True
    slide.notes_slide.notes_text_frame.text = "Recordar los datos"
    path = tmp_path / "plan.pptx"
    prs.save(path)
    token, job = _run(api, user_token, tus_upload, path, "ia-pptx", "traducir-powerpoint", {"destino": "en"})
    assert job["status"] == "succeeded", job
    out = Presentation(str(_out(services, job)))
    s = out.slides[0]
    assert s.shapes.title.text.startswith("[inglés] Plan de ventas")
    paragraphs = s.placeholders[1].text_frame.paragraphs
    assert paragraphs[1].runs[0].font.bold and paragraphs[1].runs[0].text.startswith("[inglés]")
    assert s.notes_slide.notes_text_frame.text.startswith("[inglés] Recordar")


def test_handwriting_needs_an_image_model(api, ai, user_token, tus_upload, services, tmp_path):
    from PIL import Image

    img = tmp_path / "nota.jpg"
    Image.new("RGB", (800, 600), "white").save(img)
    # Sin ningún modelo gratuito que admita imágenes, la API no encola el trabajo (la herramienta se apaga sola, 6.2).
    _models([_model("texto/solo:free", 32768, 4096, images=False)])
    token = user_token(user_id="ia-manuscrito")
    api.get("/v1/me", headers=auth(token))
    uid, _ = tus_upload(token, "manuscrito-a-texto", img)
    res = api.post("/v1/jobs", json={"tool": "manuscrito-a-texto", "upload_ids": [uid], "ai_consent": True, "options": {}}, headers=auth(token))
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_UNAVAILABLE"
    budget = api.get("/v1/ai/budget", headers=auth(token)).json()
    assert budget["tools"]["manuscrito-a-texto"] is False and budget["tools"]["traducir-word"] is True
    _models([_model("vision/lector:free", 32768, 4096, images=True)])
    token, job = _run(api, user_token, tus_upload, img, "ia-manuscrito-2", "manuscrito-a-texto", {"formato": "txt", "idioma": "es"})
    assert job["status"] == "succeeded", job
    assert job["outputs"][0]["name"] == "nota-transcripcion.txt"
    sent = ai.calls[-1]["messages"]
    assert sent[1]["content"][1]["type"] == "image_url" and sent[1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "Transcribe exactamente" in sent[0]["content"] and "español" in sent[0]["content"]
    text = _out(services, job).read_text(encoding="utf-8")
    assert text.startswith("Transcripción de nota") and "Transcripción hecha con IA" in text


# ——— D-243: correcciones de la revisión de F6-D ———

def _word(body: str):
    from lxml import etree

    from tools.ai.oficina import KINDS, paragraphs_of

    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    root = etree.fromstring(f'<w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>')
    return paragraphs_of(root, KINDS["traducir-word"])


def test_word_fields_are_not_translated_and_split_segments():
    paras = _word('<w:p><w:r><w:t xml:space="preserve">Ver la página </w:t></w:r>'
                  '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText>PAGEREF _Ref1</w:instrText></w:r>'
                  '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>7</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
                  '<w:r><w:t xml:space="preserve"> para más detalles</w:t></w:r>'
                  '<w:fldSimple w:instr="SEQ Figura"><w:r><w:t>3</w:t></w:r></w:fldSimple></w:p>')
    assert paras[0].texts() == ["Ver la página ", " para más detalles"]


def test_powerpoint_breaks_and_fields_split_segments():
    from lxml import etree

    from tools.ai.oficina import KINDS, paragraphs_of

    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    root = etree.fromstring(f'<p:sld xmlns:p="x" xmlns:a="{a}"><a:p><a:r><a:t>Primera línea</a:t></a:r><a:br/>'
                            '<a:r><a:t>Segunda línea</a:t></a:r></a:p>'
                            '<a:p><a:r><a:t>Diapositiva </a:t></a:r><a:fld type="slidenum"><a:t>3</a:t></a:fld>'
                            '<a:r><a:t> de 20</a:t></a:r></a:p></p:sld>')
    paras = paragraphs_of(root, KINDS["traducir-powerpoint"])
    assert [p.texts() for p in paras] == [["Primera línea", "Segunda línea"], ["Diapositiva ", " de 20"]]


@pytest.mark.parametrize("model_output", [
    "<0>Hola <1>negrita</1></0><2>mundo</2>",     # anidadas
    "<0>Hola </0><1>negrita<2>mundo</2>",           # sin cerrar
    "<0>Hola</0><0>otra</0><1>negrita</1><2>mundo</2>",  # repetida
])
def test_broken_tags_never_reach_the_document(model_output):
    paras = _word('<w:p><w:r><w:t xml:space="preserve">Hola </w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>negrita</w:t></w:r>'
                  '<w:r><w:t xml:space="preserve"> mundo</w:t></w:r></w:p>')
    from tools.ai.oficina import apply

    apply(paras[0], model_output)
    texts = paras[0].texts()
    assert "<" not in "".join(texts) and texts[1:] == ["", ""]


def test_spaces_between_segments_are_restored_and_control_chars_dropped():
    from tools.ai.oficina import apply

    paras = _word('<w:p><w:r><w:t xml:space="preserve">Hola </w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>negrita</w:t></w:r>'
                  '<w:r><w:t xml:space="preserve"> mundo</w:t></w:r></w:p>')
    apply(paras[0], "<0>Hello</0><1>bold\x07</1><2>world</2>")
    assert "".join(paras[0].texts()) == "Hello bold world"


def test_excel_table_headers_stay_and_sheets_without_inline_strings_are_skipped(tmp_path):
    import openpyxl
    from openpyxl.worksheet.table import Table

    from tools.ai.oficina import KINDS, read

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Nombre", "Ciudad"])
    ws.append(["Ana", "Madrid"])
    ws.add_table(Table(displayName="Personas", ref="A1:B2"))
    path = tmp_path / "tabla.xlsx"
    wb.save(path)
    doc = read(path, KINDS["traducir-excel"])
    assert {"Nombre", "Ciudad"} <= doc.fixed
    # Una hoja que solo usa cadenas compartidas (como las que guarda Excel) ni se analiza.
    numbers = openpyxl.Workbook()
    numbers.active.append([1, 2, 3])
    shared = tmp_path / "compartidas.xlsx"
    numbers.save(shared)
    sst = ('<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
           'count="1" uniqueCount="1"><si><t>Hola</t></si></sst>')
    with zipfile.ZipFile(shared, "a") as z:
        z.writestr("xl/sharedStrings.xml", sst)
    other = read(shared, KINDS["traducir-excel"])
    assert list(other.parts) == ["xl/sharedStrings.xml"] and other.paragraphs[0].texts() == ["Hola"]
    from tools.ai.oficina import sources

    items, _ = sources(doc, 10000)
    assert "Nombre" not in items and "Madrid" in items


def test_doctype_anywhere_is_rejected(tmp_path):
    from core.errors import ToolError
    from tools.ai.oficina import KINDS, read

    src = _docx(tmp_path)
    bad = tmp_path / "malo.docx"
    with zipfile.ZipFile(src) as a, zipfile.ZipFile(bad, "w") as b:
        for info in a.infolist():
            data = a.read(info)
            if info.filename == "word/document.xml":
                data = b'<?xml version="1.0"?>' + b"<!-- " + b"x" * 5000 + b" -->" + b'<!DOCTYPE d [<!ENTITY e "x">]>' + data.split(b"?>", 1)[1]
            b.writestr(info, data)
    with pytest.raises(ToolError):
        read(bad, KINDS["traducir-word"])


def test_word_default_language_and_streamed_members(api, ai, user_token, tus_upload, services, tmp_path):
    src = _docx(tmp_path)
    token, job = _run(api, user_token, tus_upload, src, "ia-word-idioma", "traducir-word", {"destino": "en"})
    assert job["status"] == "succeeded", job
    out = _out(services, job)
    with zipfile.ZipFile(out) as z:
        styles = z.read("word/styles.xml").decode()
        assert 'w:lang w:val="en' in styles or "w:lang w:val=\"en" in styles
        assert z.testzip() is None


def test_handwriting_huge_jpeg_is_reduced_and_exif_rotation_kept(tmp_path):
    from types import SimpleNamespace

    from PIL import Image

    from tools.ai.manuscrito import pages_of

    img = Image.new("RGB", (6000, 3000), "white")
    exif = Image.Exif()
    exif[0x0112] = 6  # girada 90°
    path = tmp_path / "nota.jpg"
    img.save(path, "JPEG", exif=exif.tobytes())
    ctx = SimpleNamespace(settings=SimpleNamespace(IMAGE_MAX_PIXELS=200_000_000))
    data = pages_of(ctx, path, "jpg")[0]
    import base64
    import io as _io

    with Image.open(_io.BytesIO(base64.b64decode(data.split(",", 1)[1]))) as out:
        assert out.size[1] == 2000 and out.size[0] == 1000  # vertical tras el giro y reducida


def test_image_requests_never_use_the_text_router(monkeypatch):
    import inspect

    from core.ai import client

    assert "not needs.images" in inspect.getsource(client.AiClient._with_retries if hasattr(client, "AiClient") else client)
