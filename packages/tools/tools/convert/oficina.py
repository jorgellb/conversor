"""pdf-a-odt, pdf-a-rtf, pdf-a-excel, pdf-a-ods, pdf-a-ppt y pdf-a-odp (A.9) en `workerconvert`.

- Editable: Docling reconstruye el contenido; DOCX con python-docx, XLSX con openpyxl y PPTX con python-pptx (una
  diapositiva por página, cajas en su sitio). ODT, RTF, ODS y ODP salen de esos archivos con LibreOffice (D-67).
- Editable con gráficos como imágenes: en PPTX, cada diapositiva lleva de fondo la página sin texto y el texto encima.
- Fiel al diseño: importación de PDF de LibreOffice (Writer o Impress), que se edita peor.
"""
from __future__ import annotations

import io
import re
import shutil
import statistics
from pathlib import Path

import pikepdf

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.convert.docling_util import convert, libreoffice, page_of, subset_pdf, table_rows
from tools.numeros import parse_number
from tools.convert.pdf_a_word import docx_from_document
from tools.pdf.common import with_batch_zip

TARGET = {"pdf-a-odt": "odt", "pdf-a-rtf": "rtf", "pdf-a-excel": "xlsx", "pdf-a-ods": "ods", "pdf-a-ppt": "pptx", "pdf-a-odp": "odp"}
LO_FILTER = {"odt": "odt", "rtf": "rtf", "ods": "ods", "odp": "odp", "pptx": "pptx:Impress MS PowerPoint 2007 XML",
             "docx": "docx:MS Word 2007 XML"}
NOTES = {
    "es": {"faithful": "Modo fiel al diseño: cajas posicionadas, se edita peor que el modo editable.",
           "no_tables": "No se han encontrado tablas: van los párrafos del documento, uno por fila.",
           "table": "Tabla {n} (p. {page})", "tables": "Tablas", "text": "Texto", "page": "Página {n}", "images": "Imágenes",
           "image": "Imagen {n} (p. {page})", "with_images": "{n} imágenes en la hoja «Imágenes».", "no_images": "El PDF no tiene imágenes ni gráficos que añadir.",
           "faithful_sheet": "Modo fiel al diseño: una hoja por página con cada texto en su fila y su columna; se edita peor que el modo editable.",
           "faithful_empty": "{n} páginas sin texto (escaneadas): pásalas antes por ocr-pdf."},
    "en": {"faithful": "Faithful layout mode: positioned boxes, harder to edit than editable mode.",
           "no_tables": "No tables were found: the document paragraphs are listed, one per row.",
           "table": "Table {n} (p. {page})", "tables": "Tables", "text": "Text", "page": "Page {n}", "images": "Images",
           "image": "Image {n} (p. {page})", "with_images": "{n} images on the “Images” sheet.", "no_images": "The PDF has no images or charts to add.",
           "faithful_sheet": "Faithful layout mode: one sheet per page with each text in its row and column; harder to edit than editable mode.",
           "faithful_empty": "{n} pages without text (scanned): run them through ocr-pdf first."},
}


def _target(ctx: ToolContext) -> str:
    try:
        return TARGET[ctx.tool]
    except KeyError as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, ctx.tool) from exc


def _labels(ctx: ToolContext) -> dict[str, str]:
    return NOTES.get(ctx.locale, NOTES["es"])


def _deliver(ctx: ToolContext, produced: Path, name: str) -> dict:
    dst = ctx.output(name)
    shutil.move(produced, dst)
    return {"path": str(dst), "name": name}


def _document(ctx: ToolContext, src: Path, pictures: bool = True, scale: float = 1.0):
    o = ctx.options
    return convert(src, o.ocr_si_no_hay_texto, getattr(o, "idiomas", None), pictures=pictures, scale=scale)


# --- ODT y RTF ----------------------------------------------------------------------------------------------------


def run_text(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    target = _target(ctx)
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        src, _ = subset_pdf(ctx, inp.path, o.paginas, n)
        name = derived_name(inp.name, "", target)
        note = None
        if o.modo == "fiel":
            local = ctx.work / f"entrada-{n}.pdf"
            shutil.copyfile(src, local)
            produced = libreoffice(ctx, local, LO_FILTER[target], "writer_pdf_import")
            note = _labels(ctx)["faithful"]
        else:
            doc = _document(ctx, src, scale=2.0 if o.modo == "editable_imagenes" else 1.0)
            docx = docx_from_document(doc, ctx.work / f"documento-{n}.docx")
            produced = libreoffice(ctx, docx, LO_FILTER[target])
        out = _deliver(ctx, produced, name)
        out["note"] = note
        outputs.append(out)
    return with_batch_zip(ctx, outputs, f"pdf-{target}.zip")


# --- XLSX y ODS ---------------------------------------------------------------------------------------------------


def _sheet_title(text: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", "", text)[:31] or "Hoja"
    title, k = base, 2
    while title.lower() in used:
        suffix = f" {k}"
        title = base[: 31 - len(suffix)] + suffix
        k += 1
    used.add(title.lower())
    return title


def _write_rows(ws, rows: list[list[str]], start: int, numbers: bool, locale: str, header: bool) -> int:
    from openpyxl.styles import Font

    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            parsed = parse_number(value, locale) if numbers and not (header and r == 0) else None
            cell = ws.cell(row=start + r, column=c + 1, value=parsed if parsed is not None else value)
            if header and r == 0:
                cell.font = Font(bold=True)
    return start + len(rows)


def _autosize(ws) -> None:
    from openpyxl.utils import get_column_letter

    widths: dict[int, int] = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None:
                widths[cell.column] = max(widths.get(cell.column, 0), len(str(cell.value)))
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = min(60, max(8, width + 2))


def workbook_from_document(doc, dst: Path, pages: list[int], one_sheet: bool, numbers: bool, locale: str, labels: dict) -> str | None:
    """Una hoja por tabla (o todas en una); sin tablas, los párrafos. Devuelve la nota para el usuario, si hace falta."""
    from docling_core.types.doc import TableItem, TextItem
    from openpyxl import Workbook

    tables = [(item, page_of(item)) for item, _ in doc.iterate_items() if isinstance(item, TableItem)]
    wb = Workbook()
    used: set[str] = set()
    note = None
    if not tables:
        ws = wb.active
        ws.title = _sheet_title(labels["text"], used)
        texts = [[item.text.strip()] for item, _ in doc.iterate_items() if isinstance(item, TextItem) and item.text.strip()]
        _write_rows(ws, texts, 1, False, locale, header=False)
        note = labels["no_tables"]
    elif one_sheet:
        ws = wb.active
        ws.title = _sheet_title(labels["tables"], used)
        row = 1
        for k, (table, page) in enumerate(tables, start=1):
            original = pages[page - 1] if page and page <= len(pages) else page
            ws.cell(row=row, column=1, value=labels["table"].format(n=k, page=original))
            row = _write_rows(ws, table_rows(table, doc), row + 1, numbers, locale, header=True) + 1
    else:
        wb.remove(wb.active)
        for k, (table, page) in enumerate(tables, start=1):
            original = pages[page - 1] if page and page <= len(pages) else page
            ws = wb.create_sheet(_sheet_title(labels["table"].format(n=k, page=original), used))
            _write_rows(ws, table_rows(table, doc), 1, numbers, locale, header=True)
    for ws in wb.worksheets:
        _autosize(ws)
    wb.save(dst)
    return note


def workbook_faithful(src: Path, dst: Path, pages: list[int], numbers: bool, locale: str, labels: dict) -> str:
    """Fiel al diseño (D-261): una hoja por página, cada trozo de texto en la celda de su línea y de su columna."""
    import pypdfium2 as pdfium
    from openpyxl import Workbook

    from tools.pdf.disposicion import layout_grid, page_layout

    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    doc = pdfium.PdfDocument(str(src))
    empty = 0
    try:
        for k in range(len(doc)):
            page = doc[k]
            try:
                grid = layout_grid(page_layout(page))
            finally:
                page.close()
            original = pages[k] if k < len(pages) else k + 1  # subset_pdf da los números de página desde 1
            ws = wb.create_sheet(_sheet_title(labels["page"].format(n=original), used))
            if not grid:
                empty += 1
            _write_rows(ws, grid, 1, numbers, locale, header=False)
            _autosize(ws)
    finally:
        doc.close()
    wb.save(dst)
    return labels["faithful_sheet"] + (" " + labels["faithful_empty"].format(n=empty) if empty else "")


def add_pictures(doc, dst: Path, labels: dict) -> int:
    """Editable con imágenes (D-261): las imágenes y gráficos que reconoce Docling, en una hoja «Imágenes» una debajo de otra."""
    from docling_core.types.doc import PictureItem
    from openpyxl import load_workbook
    from openpyxl.drawing.image import Image as XlImage

    pictures = []
    for item, _ in doc.iterate_items():
        if isinstance(item, PictureItem):
            image = item.get_image(doc)
            if image is not None:
                pictures.append((image, page_of(item)))
    if not pictures:
        return 0
    wb = load_workbook(dst)
    ws = wb.create_sheet(_sheet_title(labels["images"], {w.title.lower() for w in wb.worksheets}))
    row = 1
    for k, (image, page) in enumerate(pictures[:200], start=1):
        image = image.convert("RGB")
        image.thumbnail((900, 900))
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        ws.cell(row=row, column=1, value=labels["image"].format(n=k, page=page))
        xl = XlImage(io.BytesIO(buf.getvalue()))
        ws.add_image(xl, f"A{row + 1}")
        row += 2 + int(image.height / 20)  # unas 20 px por fila
    wb.save(dst)
    return len(pictures)


def run_sheet(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    target = _target(ctx)
    labels = _labels(ctx)
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        src, pages = subset_pdf(ctx, inp.path, o.paginas, n)
        xlsx = ctx.work / f"tablas-{n}.xlsx"
        if o.modo == "fiel":
            note = workbook_faithful(src, xlsx, pages, o.numeros, ctx.locale, labels)
            produced = xlsx if target == "xlsx" else libreoffice(ctx, xlsx, LO_FILTER[target])
            out = _deliver(ctx, produced, derived_name(inp.name, "", target))
            out["note"] = note
            outputs.append(out)
            continue
        doc = _document(ctx, src, pictures=o.modo == "editable_imagenes")
        note = workbook_from_document(doc, xlsx, pages, o.hojas == "todas_en_una", o.numeros, ctx.locale, labels)
        if o.modo == "editable_imagenes":
            count = add_pictures(doc, xlsx, labels)
            note = " ".join(x for x in (note, labels["with_images"].format(n=count) if count else labels["no_images"]) if x)
        produced = xlsx if target == "xlsx" else libreoffice(ctx, xlsx, LO_FILTER[target])
        out = _deliver(ctx, produced, derived_name(inp.name, "", target))
        out["note"] = note
        outputs.append(out)
    return with_batch_zip(ctx, outputs, f"pdf-{target}.zip")


# --- PPTX y ODP ---------------------------------------------------------------------------------------------------

EMU_PER_PT = 12700
TEXT_OPS = {"Tj", "TJ", "'", '"'}


def _strip_text(pdf: pikepdf.Pdf, owner, seen: set) -> None:
    """Quita los operadores que pintan texto (y nada más: el estado gráfico se conserva) de la página y sus formularios."""
    ops = [(operands, op) for operands, op in pikepdf.parse_content_stream(owner) if str(op) not in TEXT_OPS]
    data = pikepdf.unparse_content_stream(ops)
    if isinstance(owner, pikepdf.Page):
        owner.Contents = pdf.make_stream(data)
        resources = owner.obj.get("/Resources")
    else:
        owner.write(data)
        resources = owner.get("/Resources")
    xobjects = resources.get("/XObject") if resources is not None else None
    for _, xobj in (xobjects.items() if xobjects is not None else []):
        if xobj.get("/Subtype") == pikepdf.Name.Form and xobj.objgen not in seen:
            seen.add(xobj.objgen)
            _strip_text(pdf, xobj, seen)


def textless_backgrounds(src: Path, dpi: int, work: Path) -> list[bytes]:
    """Cada página sin su texto, renderizada en PNG: el fondo de las diapositivas «con gráficos como imágenes»."""
    import pypdfium2 as pdfium

    stripped = work / "sin-texto.pdf"
    with pikepdf.open(src) as pdf:
        seen: set = set()
        for page in pdf.pages:
            _strip_text(pdf, page, seen)
        pdf.save(stripped)
    out = []
    doc = pdfium.PdfDocument(str(stripped))
    try:
        for i in range(len(doc)):
            buf = io.BytesIO()
            doc[i].render(scale=dpi / 72).to_pil().convert("RGB").save(buf, format="PNG", optimize=True)
            out.append(buf.getvalue())
    finally:
        doc.close()
    return out


def char_sizes(src: Path) -> dict[int, list[tuple[float, float, float]]]:
    """Centro (origen arriba a la izquierda) y tamaño de letra de cada carácter, por página (desde 1)."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    sizes: dict[int, list[tuple[float, float, float]]] = {}
    doc = pdfium.PdfDocument(str(src))
    try:
        for i in range(len(doc)):
            page = doc[i]
            height = page.get_height()
            tp = page.get_textpage()
            chars = []
            for k in range(tp.count_chars()):
                left, bottom, right, top = tp.get_charbox(k)
                if right <= left or top <= bottom:
                    continue
                size = pdfium_c.FPDFText_GetFontSize(tp.raw, k)
                if size < 4:  # tamaño 1 con la escala en la matriz de texto
                    size = (top - bottom) * 1.3
                chars.append(((left + right) / 2, height - (bottom + top) / 2, size))
            sizes[i + 1] = chars
            tp.close()
            page.close()
    finally:
        doc.close()
    return sizes


def _font_size(chars: list[tuple[float, float, float]], box: tuple[float, float, float, float], text: str) -> float:
    left, top, width, height = box
    inside = [s for x, y, s in chars if left - 1 <= x <= left + width + 1 and top - 1 <= y <= top + height + 1]
    if inside:
        return max(5.0, min(96.0, statistics.median(inside)))
    estimate = (width * height / (0.6 * max(1, len(text)))) ** 0.5  # sin capa de texto (OCR): por superficie
    return max(5.0, min(height, 48.0, estimate))


def _bbox(bbox, page_height: float) -> tuple[float, float, float, float]:
    """Izquierda, arriba, ancho y alto en puntos, con el origen arriba a la izquierda."""
    b = bbox.to_top_left_origin(page_height=page_height)
    return b.l, b.t, b.r - b.l, b.b - b.t


def presentation_from_document(doc, src: Path, dst: Path, mode: str, work: Path) -> Path:
    from docling_core.types.doc import DocItemLabel, PictureItem, TableItem, TextItem
    from pptx import Presentation
    from pptx.enum.text import MSO_AUTO_SIZE
    from pptx.util import Emu, Pt

    sizes = {no: (p.size.width, p.size.height) for no, p in doc.pages.items()}
    if not sizes:
        raise ToolError(ErrorCode.CORRUPT_FILE, "PDF sin páginas")
    first_w, first_h = sizes[min(sizes)]
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(int(first_w * EMU_PER_PT)), Emu(int(first_h * EMU_PER_PT))
    blank = prs.slide_layouts[6]
    backgrounds = textless_backgrounds(src, 150, work) if mode == "editable_imagenes" else []
    chars = char_sizes(src)
    slides = {}
    for no in sorted(sizes):
        slide = prs.slides.add_slide(blank)
        slides[no] = slide
        if backgrounds and no - 1 < len(backgrounds):
            slide.shapes.add_picture(io.BytesIO(backgrounds[no - 1]), 0, 0, prs.slide_width, prs.slide_height)

    def emu(page_no: int, box: tuple[float, float, float, float]) -> tuple[Emu, Emu, Emu, Emu]:
        w, h = sizes[page_no]
        sx, sy = first_w / w, first_h / h
        left, top, width, height = box
        return (Emu(int(left * sx * EMU_PER_PT)), Emu(int(top * sy * EMU_PER_PT)), Emu(max(1, int(width * sx * EMU_PER_PT))),
                Emu(max(1, int(height * sy * EMU_PER_PT))))

    def text_box(page_no: int, box: tuple[float, float, float, float], text: str, size: float, bold: bool = False) -> None:
        left, top, width, height = box
        shape = slides[page_no].shapes.add_textbox(*emu(page_no, (left, top, width * 1.06 + 2, height)))
        frame = shape.text_frame
        frame.word_wrap = True
        frame.auto_size = MSO_AUTO_SIZE.NONE
        frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
        run = frame.paragraphs[0].add_run()
        run.text = text
        run.font.size = Pt(round(size, 1))
        run.font.bold = bold

    for item, _ in doc.iterate_items():
        if not getattr(item, "prov", None):
            continue
        prov = item.prov[0]
        page_no = prov.page_no
        if page_no not in slides:
            continue
        box = _bbox(prov.bbox, sizes[page_no][1])
        if isinstance(item, TableItem):
            if mode == "editable_imagenes":
                for cell in item.data.table_cells:
                    if cell.bbox is not None and cell.text.strip():
                        cbox = _bbox(cell.bbox, sizes[page_no][1])
                        text_box(page_no, cbox, cell.text.strip(), _font_size(chars.get(page_no, []), cbox, cell.text))
                continue
            rows = table_rows(item, doc)
            if not rows:
                continue
            cols = max(len(r) for r in rows)
            table = slides[page_no].shapes.add_table(len(rows), cols, *emu(page_no, box)).table
            cell_size = max(6.0, min(14.0, box[3] / max(1, len(rows)) * 0.55))
            for r, row in enumerate(rows):
                for c in range(cols):
                    frame = table.cell(r, c).text_frame
                    frame.text = row[c] if c < len(row) else ""
                    for paragraph in frame.paragraphs:
                        for run in paragraph.runs:
                            run.font.size = Pt(round(cell_size, 1))
        elif isinstance(item, PictureItem):
            if mode == "editable_imagenes":
                continue  # ya está en el fondo
            image = item.get_image(doc)
            if image is not None:
                buf = io.BytesIO()
                image.save(buf, format="PNG")
                buf.seek(0)
                slides[page_no].shapes.add_picture(buf, *emu(page_no, box))
        elif isinstance(item, TextItem):
            text = item.text.strip()
            if not text:
                continue
            heading = item.label in (DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER)
            text_box(page_no, box, text, _font_size(chars.get(page_no, []), box, text), bold=heading)
    prs.save(dst)
    return dst


def run_slides(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    target = _target(ctx)
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        src, _ = subset_pdf(ctx, inp.path, o.paginas, n)
        local = ctx.work / f"entrada-{n}.pdf"
        shutil.copyfile(src, local)
        note = None
        if o.modo == "fiel":
            produced = libreoffice(ctx, local, LO_FILTER[target], "impress_pdf_import")
            note = _labels(ctx)["faithful"]
        else:
            doc = _document(ctx, local, scale=2.0)
            pptx = presentation_from_document(doc, local, ctx.work / f"presentacion-{n}.pptx", o.modo, ctx.work)
            produced = pptx if target == "pptx" else libreoffice(ctx, pptx, LO_FILTER[target])
        out = _deliver(ctx, produced, derived_name(inp.name, "", target))
        out["note"] = note
        outputs.append(out)
    return with_batch_zip(ctx, outputs, f"pdf-{target}.zip")
