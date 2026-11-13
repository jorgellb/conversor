"""pdf-a-word (7.4 y A.9).

- Modos «editable»: Docling (backend pypdfium2) reconstruye títulos, párrafos, listas, tablas e imágenes
  con python-docx. El resultado es editable y recompone el flujo; no copia el diseño exacto.
- Modo «fiel»: importación de PDF de LibreOffice (cajas posicionadas), en `workeroffice`.
"""
from __future__ import annotations

import io
import shutil
from pathlib import Path

from tools.base import ToolContext, derived_name
from tools.convert.docling_util import convert, libreoffice, subset_pdf, table_rows
from tools.pdf.common import with_batch_zip


def faithful_with_libreoffice(ctx: ToolContext, src: Path, out_name: str) -> Path:
    local = ctx.work / "entrada.pdf"
    shutil.copyfile(src, local)
    produced = libreoffice(ctx, local, "docx:MS Word 2007 XML", "writer_pdf_import")
    dst = ctx.output(out_name)
    shutil.move(produced, dst)
    return dst


def docx_from_document(doc, dst: Path) -> Path:
    """Títulos, párrafos, listas, tablas e imágenes de Docling en un DOCX que recompone el flujo."""
    from docling_core.types.doc import DocItemLabel, PictureItem, TableItem, TextItem
    from docx import Document
    from docx.shared import Inches

    out = Document()
    for item, level in doc.iterate_items():
        if isinstance(item, TableItem):
            rows = table_rows(item, doc)
            if not rows:
                continue
            table = out.add_table(rows=len(rows), cols=max(1, max(len(r) for r in rows)))
            table.style = "Table Grid"
            for r_i, row in enumerate(rows):
                for c, value in enumerate(row):
                    table.cell(r_i, c).text = value
        elif isinstance(item, PictureItem):
            image = item.get_image(doc)
            if image is not None:
                buf = io.BytesIO()
                image.save(buf, format="PNG")
                buf.seek(0)
                out.add_picture(buf, width=Inches(min(6.0, image.width / 96)))
        elif isinstance(item, TextItem):
            text = item.text.strip()
            if not text:
                continue
            if item.label == DocItemLabel.TITLE:
                out.add_heading(text, level=0)
            elif item.label == DocItemLabel.SECTION_HEADER:
                out.add_heading(text, level=min(max(level, 1), 6))
            elif item.label == DocItemLabel.LIST_ITEM:
                out.add_paragraph(text, style="List Bullet")
            elif item.label in (DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER):
                continue
            else:
                out.add_paragraph(text)
    out.save(dst)
    return dst


def editable_with_docling(ctx: ToolContext, src: Path, out_name: str, images_for_vectors: bool, ocr: bool) -> Path:
    doc = convert(src, ocr, getattr(ctx.options, "idiomas", None), pictures=True, scale=2.0 if images_for_vectors else 1.0)
    return docx_from_document(doc, ctx.output(out_name))


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        src, _ = subset_pdf(ctx, inp.path, o.paginas, n)
        name = derived_name(inp.name, "", "docx")
        if o.modo == "fiel":
            dst = faithful_with_libreoffice(ctx, src, name)
        else:
            dst = editable_with_docling(ctx, src, name, o.modo == "editable_imagenes", o.ocr_si_no_hay_texto)
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "documentos-word.zip")
