"""F2, lote D2: desde PDF con Docling (A.9), con Docling, LibreOffice, pandoc y Tesseract reales.

Si Docling no está instalado (solo va en la imagen `worker-convert` y en la CI con el extra `convert`), se omiten.
"""
from __future__ import annotations

import csv
import dataclasses
import io
import json
import shutil
import zipfile
from pathlib import Path

import pikepdf
import pytest

from core.errors import ToolError
from core.registry import load_registry
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida

pytest.importorskip("docling")
needs_soffice = pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice no instalado")

needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no instalado")


def table_pdf(path: Path) -> Path:
    """Informe con título, párrafo y una tabla con rejilla, como los que llegan a pdf-a-excel."""
    rows = [["Producto", "Unidades", "Precio"], ["Manzanas", "12", "3,50"], ["Peras", "7", "2,10"], ["Naranjas", "1.230", "15,00"]]
    ops = ["BT /F1 18 Tf 72 760 Td (Informe de ventas) Tj ET", "BT /F1 11 Tf 72 730 Td (Resumen del primer trimestre por producto.) Tj ET",
           "0.8 w"]
    x0, y0, cw, rh = 72, 680, 150, 28
    for r in range(len(rows) + 1):
        ops.append(f"{x0} {y0 - r * rh} m {x0 + cw * 3} {y0 - r * rh} l S")
    for c in range(4):
        ops.append(f"{x0 + c * cw} {y0} m {x0 + c * cw} {y0 - rh * len(rows)} l S")
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            ops.append(f"BT /{'F2' if r == 0 else 'F1'} 11 Tf {x0 + c * cw + 8} {y0 - r * rh - 18} Td ({cell}) Tj ET")
    ops.append("BT /F1 11 Tf 72 520 Td (Fin del informe.) Tj ET")
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(595, 842))
    page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(
        F1=pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica),
        F2=pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name("/Helvetica-Bold"))))
    page.Contents = pdf.make_stream("\n".join(ops).encode("latin-1"))
    pdf.save(path)
    return path


def picture_pdf(path: Path) -> Path:
    """Página con título, párrafos y un gráfico de barras como imagen, con su pie."""
    import zlib

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (600, 400), (235, 242, 250))
    draw = ImageDraw.Draw(img)
    for k, (h, color) in enumerate(((60, (30, 90, 200)), (160, (200, 60, 40)), (240, (40, 160, 80)), (300, (220, 160, 30)))):
        draw.rectangle((40 + k * 140, 360 - h, 140 + k * 140, 360), fill=color)
    draw.line((30, 365, 580, 365), fill=(0, 0, 0), width=3)
    draw.line((30, 20, 30, 365), fill=(0, 0, 0), width=3)
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(595, 842))
    image = pdf.make_stream(zlib.compress(img.tobytes()), Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image, Width=600, Height=400,
                            ColorSpace=pikepdf.Name.DeviceRGB, BitsPerComponent=8, Filter=pikepdf.Name.FlateDecode)
    page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im1=image), Font=pikepdf.Dictionary(
        F1=pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)))
    page.Contents = pdf.make_stream("\n".join([
        "BT /F1 20 Tf 72 770 Td (Ventas por trimestre) Tj ET",
        "BT /F1 11 Tf 72 740 Td (El grafico muestra la evolucion de las ventas durante el ano.) Tj ET",
        "q 450 0 0 300 72 400 cm /Im1 Do Q", "BT /F1 10 Tf 72 380 Td (Figura 1. Ventas por trimestre.) Tj ET",
        "BT /F1 11 Tf 72 340 Td (Las ventas crecen cada trimestre gracias a la nueva tienda.) Tj ET"]).encode())
    pdf.save(path)
    return path


@pytest.fixture(scope="module")
def tabla(tmp_path_factory) -> Path:
    return table_pdf(tmp_path_factory.mktemp("d2") / "tabla.pdf")


@pytest.fixture(scope="module")
def grafico(tmp_path_factory) -> Path:
    return picture_pdf(tmp_path_factory.mktemp("d2g") / "grafico.pdf")


# --- Excel, ODS, CSV y JSON ---------------------------------------------------------------------------------------


def test_excel_one_sheet_per_table_with_real_numbers(make_ctx, tabla):
    from openpyxl import load_workbook

    out = run("pdf-a-excel", make_ctx("pdf-a-excel", [tabla]))
    wb = load_workbook(out[0]["path"])
    assert wb.sheetnames == ["Tabla 1 (p. 1)"] and out[0]["note"] is None
    ws = wb.active
    assert [c.value for c in ws[1]] == ["Producto", "Unidades", "Precio"] and ws["A1"].font.bold
    assert ws["B2"].value == 12 and ws["C2"].value == 3.5 and ws["B4"].value == 1230 and ws["C4"].value == 15.0
    english = run("pdf-a-excel", dataclasses.replace(make_ctx("pdf-a-excel", [tabla], {"hojas": "todas_en_una"}), locale="en"))
    ws = load_workbook(english[0]["path"]).active
    assert ws.title == "Tables" and ws["A1"].value == "Table 1 (p. 1)" and ws["C3"].value == "3,50"  # «3,50» no es un número en inglés


def test_excel_without_tables_lists_the_text(make_ctx, fixtures_dir):
    from openpyxl import load_workbook

    out = run("pdf-a-excel", make_ctx("pdf-a-excel", [fixtures_dir / "texto.pdf"], {"paginas": "1"}))
    ws = load_workbook(out[0]["path"]).active
    assert ws.title == "Texto" and "Hola mundo" in str(ws["A1"].value) and out[0]["note"].startswith("No se han encontrado tablas")


@needs_soffice
def test_ods_through_libreoffice(make_ctx, tabla):
    out = run("pdf-a-ods", make_ctx("pdf-a-ods", [tabla]))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        assert zf.read("mimetype") == b"application/vnd.oasis.opendocument.spreadsheet"
        assert "Manzanas" in zf.read("content.xml").decode()


def test_csv_per_table_with_delimiter_and_bom(make_ctx, tabla, fixtures_dir):
    out = run("pdf-a-csv", make_ctx("pdf-a-csv", [tabla], {"delimitador": "punto_y_coma"}))
    assert out[0]["name"] == "tabla-tabla-1-p1.csv"
    data = Path(out[0]["path"]).read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
    assert rows[0] == ["Producto", "Unidades", "Precio"] and rows[1] == ["Manzanas", "12", "3,50"]
    with pytest.raises(ToolError) as err:
        run("pdf-a-csv", make_ctx("pdf-a-csv", [fixtures_dir / "texto.pdf"], {"paginas": "1"}))
    assert err.value.code == "NO_TABLES"


def test_json_tables_or_whole_document(make_ctx, tabla):
    out = run("pdf-a-json", make_ctx("pdf-a-json", [tabla]))
    data = json.loads(Path(out[0]["path"]).read_text(encoding="utf-8"))
    assert data["source"] == "tabla.pdf" and len(data["tables"]) == 1
    table = data["tables"][0]
    assert table["page"] == 1 and table["header"] == ["Producto", "Unidades", "Precio"] and table["rows"][2] == ["Naranjas", "1.230", "15,00"]
    out = run("pdf-a-json", make_ctx("pdf-a-json", [tabla], {"contenido": "documento"}))
    doc = json.loads(Path(out[0]["path"]).read_text(encoding="utf-8"))
    assert doc["schema_name"] == "DoclingDocument" and any("Informe de ventas" in t.get("text", "") for t in doc["texts"])


# --- Markdown, HTML y EPUB ----------------------------------------------------------------------------------------


def test_markdown_with_gfm_table_and_images_in_zip(make_ctx, tabla, grafico):
    out = run("pdf-a-markdown", make_ctx("pdf-a-markdown", [tabla]))
    md = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert out[0]["name"] == "tabla.md" and "Informe de ventas" in md and "| Producto" in md and "|---" in md.replace(" ", "")
    out = run("pdf-a-markdown", make_ctx("pdf-a-markdown", [grafico]))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        names = zf.namelist()
        assert out[0]["name"] == "grafico-markdown.zip" and "grafico.md" in names
        assert any(n.startswith("grafico-imagenes/") and n.endswith(".png") for n in names)
        assert "](grafico-imagenes/" in zf.read("grafico.md").decode()
    out = run("pdf-a-markdown", make_ctx("pdf-a-markdown", [grafico], {"imagenes": "sin"}))
    md = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert out[0]["name"] == "grafico.md" and "<!-- image -->" not in md and "Figura 1" in md


def test_html_flowing_fixed_and_automatic(make_ctx, tabla, fixtures_dir):
    out = run("pdf-a-html", make_ctx("pdf-a-html", [tabla], {"diseno": "fluido"}))
    page = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert "<table" in page and "Manzanas" in page and 'lang="es"' in page
    out = run("pdf-a-html", make_ctx("pdf-a-html", [tabla], {"diseno": "fijo"}))
    page = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert "data:image/svg+xml;base64," in page and 'lengthAdjust="spacingAndGlyphs">Informe de ventas</text>' in page
    out = run("pdf-a-html", make_ctx("pdf-a-html", [fixtures_dir / "escaneado.pdf"], {"ocr_si_no_hay_texto": False}))
    assert out[0]["note"].startswith("Diseño fijo") and "data:image/svg+xml" in Path(out[0]["path"]).read_text(encoding="utf-8")



def test_epub_flowing_and_fixed_layout(make_ctx, tabla, grafico):
    from lxml import etree

    out = run("pdf-a-epub", make_ctx("pdf-a-epub", [tabla], {"diseno": "fluido"}))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        assert zf.namelist()[0] == "mimetype" and zf.read("mimetype") == b"application/epub+zip"
        chapters = [n for n in zf.namelist() if n.startswith("OEBPS/capitulo-")]
        for name in chapters:
            etree.fromstring(zf.read(name))  # XHTML bien formado
        text = "".join(zf.read(n).decode("utf-8") for n in chapters)
        assert "Informe de ventas" in text and "<td>Manzanas</td>" in text
        assert "Informe de ventas</a>" in zf.read("OEBPS/nav.xhtml").decode()
    out = run("pdf-a-epub", make_ctx("pdf-a-epub", [grafico], {"diseno": "fluido"}))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        images = [n for n in zf.namelist() if n.startswith("OEBPS/imagenes/")]
        assert images and "data:image" not in "".join(zf.read(n).decode() for n in zf.namelist() if n.endswith(".xhtml"))
        assert 'media-type="image/png"' in zf.read("OEBPS/content.opf").decode()
    out = run("pdf-a-epub", make_ctx("pdf-a-epub", [tabla], {"diseno": "fijo"}))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        assert zf.namelist()[0] == "mimetype" and zf.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        opf = zf.read("OEBPS/content.opf").decode()
        assert "pre-paginated" in opf and 'properties="nav"' in opf
        page = zf.read("OEBPS/pagina-1.xhtml").decode()
        assert 'name="viewport" content="width=793, height=1123"' in page and "Informe de ventas" in page
        assert zf.read("OEBPS/pagina-1.svg").lstrip().startswith(b"<?xml")


# --- PowerPoint, ODP, ODT, RTF y Word -----------------------------------------------------------------------------


def _slide_texts(path: str) -> tuple[list, list[str]]:
    from pptx import Presentation

    prs = Presentation(path)
    shapes = list(prs.slides[0].shapes)
    texts = [s.text_frame.text for s in shapes if s.has_text_frame and s.text_frame.text]
    return shapes, texts


def test_ppt_editable_places_text_and_tables(make_ctx, tabla):
    from pptx import Presentation
    from pptx.util import Emu

    out = run("pdf-a-ppt", make_ctx("pdf-a-ppt", [tabla]))
    prs = Presentation(out[0]["path"])
    assert len(prs.slides) == 1 and prs.slide_width == Emu(595 * 12700) and prs.slide_height == Emu(842 * 12700)
    shapes, texts = _slide_texts(out[0]["path"])
    assert "Informe de ventas" in texts
    title = next(s for s in shapes if s.has_text_frame and s.text_frame.text == "Informe de ventas")
    assert abs(title.text_frame.paragraphs[0].runs[0].font.size.pt - 18) < 1.5  # tamaño leído del PDF
    assert abs(title.left / 12700 - 72) < 6 and abs(title.top / 12700 - (842 - 773)) < 8  # en su sitio
    tables = [s for s in shapes if s.has_table]
    assert tables and tables[0].table.cell(1, 0).text == "Manzanas"


def test_ppt_with_textless_page_as_background(make_ctx, tabla):
    shapes, texts = _slide_texts(run("pdf-a-ppt", make_ctx("pdf-a-ppt", [tabla], {"modo": "editable_imagenes"}))[0]["path"])
    assert shapes[0].shape_type == 13 and shapes[0].width == shapes[0].part.package.presentation_part.presentation.slide_width
    assert "Manzanas" in texts and not any(s.has_table for s in shapes)  # las celdas van como texto sobre la rejilla del fondo


@needs_soffice
def test_ppt_faithful_and_odp(make_ctx, tabla):
    out = run("pdf-a-ppt", make_ctx("pdf-a-ppt", [tabla], {"modo": "fiel"}))
    assert out[0]["note"].startswith("Modo fiel")
    with zipfile.ZipFile(out[0]["path"]) as zf:
        assert "Manzanas" in zf.read("ppt/slides/slide1.xml").decode()
    out = run("pdf-a-odp", make_ctx("pdf-a-odp", [tabla]))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        assert zf.read("mimetype") == b"application/vnd.oasis.opendocument.presentation" and "Manzanas" in zf.read("content.xml").decode()


@needs_soffice
def test_odt_and_rtf_editable_and_faithful(make_ctx, tabla):
    out = run("pdf-a-odt", make_ctx("pdf-a-odt", [tabla]))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        content = zf.read("content.xml").decode()
        assert zf.read("mimetype") == b"application/vnd.oasis.opendocument.text" and "Informe de ventas" in content and "table:table" in content
    out = run("pdf-a-rtf", make_ctx("pdf-a-rtf", [tabla]))
    rtf = Path(out[0]["path"]).read_bytes()
    assert rtf.startswith(b"{\\rtf") and b"Manzanas" in rtf
    out = run("pdf-a-rtf", make_ctx("pdf-a-rtf", [tabla], {"modo": "fiel"}))
    assert Path(out[0]["path"]).read_bytes().startswith(b"{\\rtf") and out[0]["note"].startswith("Modo fiel")


@needs_tesseract
def test_word_with_docling_ocr_on_a_scan(make_ctx, fixtures_dir):
    from docx import Document

    out = run("pdf-a-word", make_ctx("pdf-a-word", [fixtures_dir / "escaneado.pdf"], {"idiomas": ["spa"]}))
    text = "\n".join(p.text for p in Document(out[0]["path"]).paragraphs)
    assert "Factura" in text or "Madrid" in text


# --- convertir-desde-pdf ------------------------------------------------------------------------------------------


def test_hub_routes_and_costs_by_format():
    hub = load_registry().require("convertir-desde-pdf")
    assert hub.target({"formato": "jpg"}) == ("pdf", "pdf") and hub.cost_for({"formato": "jpg"}) == "light"
    assert hub.target({"formato": "docx", "modo": "fiel"}) == ("office", "office.heavy")
    assert hub.target({"formato": "docx"}) == ("convert", "convert") and hub.cost_for({"formato": "docx"}) == "heavy"
    assert hub.target({"formato": "pdfa"}) == ("ocr", "ocr") and hub.cost_for({"formato": "pdfa"}) == "heavy"
    assert hub.target({"formato": "txt", "ocr_si_no_hay_texto": False}) == ("pdf", "pdf")
    assert hub.cost_for({"formato": "txt", "ocr_si_no_hay_texto": False}) == "light"
    props = hub.to_public()["options_schema"]["properties"]
    assert props["calidad"]["x-show-if"] == {"formato": ["jpg", "webp"]}
    assert props["compresion_bn"]["x-show-if"] == {"color": ["bn"], "formato": ["tiff"]}
    assert props["color"]["x-labels"]["cmyk"]["es"] == "CMYK, 32 bits (JPG y TIFF)"


def test_hub_delegates_with_the_same_options(make_ctx, tabla):
    from openpyxl import load_workbook

    out = run("convertir-desde-pdf", make_ctx("convertir-desde-pdf", [tabla], {"formato": "xlsx", "hojas": "todas_en_una"}))
    assert out[0]["name"] == "tabla.xlsx" and load_workbook(out[0]["path"]).active.title == "Tablas"
    out = run("convertir-desde-pdf", make_ctx("convertir-desde-pdf", [tabla], {"formato": "png", "dpi": 72}))
    assert out[0]["name"] == "tabla-1.png"
    with pytest.raises(Exception):
        make_ctx("convertir-desde-pdf", [tabla], {"formato": "doc"})


# --- copiar-de-pdf (A.4) ------------------------------------------------------------------------------------------


def list_pdf(path: Path) -> Path:
    items = ["Revisar el contrato", "Firmar las dos copias", "Enviar una al cliente"]
    ops = ["BT /F1 18 Tf 72 760 Td (Tareas pendientes) Tj ET", "BT /F1 11 Tf 72 730 Td (Antes del viernes hay que hacer lo siguiente:) Tj ET"]
    for k, item in enumerate(items):
        ops.append(f"BT /F1 11 Tf 80 {700 - k * 20} Td (\\225) Tj ET")
        ops.append(f"BT /F1 11 Tf 96 {700 - k * 20} Td ({item}) Tj ET")
    ops.append("BT /F1 11 Tf 72 600 Td (Gracias por tu ayuda.) Tj ET")
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(595, 842))
    page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pikepdf.Dictionary(
        Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica, Encoding=pikepdf.Name.WinAnsiEncoding)))
    page.Contents = pdf.make_stream("\n".join(ops).encode("latin-1"))
    pdf.save(path)
    return path


def test_copy_blocks_with_boxes_markdown_and_tables(make_ctx, tabla):
    out = run("copiar-de-pdf", make_ctx("copiar-de-pdf", [tabla]))
    assert [o["name"] for o in out] == ["bloques.json", "tabla.md", "tabla-tablas.xlsx"] and out[0]["note"] is None
    data = json.loads(Path(out[0]["path"]).read_text(encoding="utf-8"))
    assert data["version"] == 1 and data["pages"] == [{"number": 1, "width": 595.0, "height": 842.0}]
    kinds = [b["type"] for b in data["blocks"]]
    assert kinds == ["titulo", "parrafo", "tabla", "parrafo"] and [b["id"] for b in data["blocks"]] == ["b1", "b2", "b3", "b4"]
    title, _, table, _ = data["blocks"]
    assert title["html"] == "<h2>Informe de ventas</h2>" and title["markdown"] == "## Informe de ventas"
    x0, y0, x1, y1 = title["bbox"]
    assert abs(x0 - 72) < 4 and abs(y0 - (842 - 773)) < 6 and x1 > x0 and y1 > y0  # origen arriba a la izquierda
    assert table["header"] == ["Producto", "Unidades", "Precio"] and table["rows"][0] == ["Manzanas", "12", "3,50"]
    assert table["text"].splitlines()[1] == "Manzanas\t12\t3,50" and "<th>Producto</th>" in table["html"]
    assert table["markdown"].splitlines()[:2] == ["| Producto | Unidades | Precio |", "|---|---|---|"]
    assert "| Manzanas" in Path(out[1]["path"]).read_text(encoding="utf-8")


def test_copy_groups_list_items_and_keeps_pictures(make_ctx, tmp_path, grafico):
    out = run("copiar-de-pdf", make_ctx("copiar-de-pdf", [list_pdf(tmp_path / "lista.pdf")]))
    blocks = json.loads(Path(out[0]["path"]).read_text(encoding="utf-8"))["blocks"]
    lists = [b for b in blocks if b["type"] == "lista"]
    assert len(lists) == 1 and len(out) == 2  # sin tablas no hay XLSX
    assert lists[0]["text"].splitlines() == ["Revisar el contrato", "Firmar las dos copias", "Enviar una al cliente"]
    assert lists[0]["html"].startswith("<ul><li>Revisar el contrato</li>") and lists[0]["markdown"].startswith("- Revisar el contrato")
    blocks = json.loads(Path(run("copiar-de-pdf", make_ctx("copiar-de-pdf", [grafico]))[0]["path"]).read_text(encoding="utf-8"))["blocks"]
    picture = next(b for b in blocks if b["type"] == "imagen")
    assert picture["text"] == "Figura 1. Ventas por trimestre." and picture["bbox"][2] - picture["bbox"][0] > 300


def test_copy_on_a_scan_suggests_ocr(make_ctx, fixtures_dir):
    out = run("copiar-de-pdf", make_ctx("copiar-de-pdf", [fixtures_dir / "escaneado.pdf"]))
    assert out[0]["note"].startswith("El PDF no tiene texto que reconocer")
    assert load_registry().require("copiar-de-pdf").where == "hybrid"
