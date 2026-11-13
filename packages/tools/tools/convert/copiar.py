"""Parte de servidor de copiar-de-pdf (A.4, híbrida): bloques reconocidos con Docling para resaltarlos y copiarlos en
el navegador, el documento entero en Markdown y todas las tablas en un XLSX (una hoja por tabla).

Cada bloque lleva su página, su caja en puntos (origen arriba a la izquierda), su tipo (título, párrafo, lista, tabla,
imagen, índice, código o fórmula) y el contenido listo para copiar como texto, HTML y Markdown; las tablas, además, sus
filas. Los escaneos pasan antes por ocr-pdf desde la web (enderezado y más de 100 idiomas; D-75).
"""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext
from tools.convert.docling_util import convert, subset_pdf, table_data
from tools.convert.oficina import NOTES as SHEET_LABELS
from tools.convert.oficina import workbook_from_document

VERSION = 1
NOTES = {
    "es": {"no_text": "El PDF no tiene texto que reconocer: si es un escaneo, pasa antes por el OCR."},
    "en": {"no_text": "The PDF has no text to recognise: if it is a scan, run OCR first."},
}


def _box(prov, page_heights: dict[int, float]) -> list[float]:
    b = prov.bbox.to_top_left_origin(page_height=page_heights[prov.page_no])
    return [round(b.l, 2), round(b.t, 2), round(b.r, 2), round(b.b, 2)]


def _union(boxes: list[list[float]]) -> list[float]:
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def table_block(header: list[str] | None, rows: list[list[str]]) -> tuple[str, str, str]:
    """Texto (TSV), HTML y Markdown (GFM) de una tabla."""
    all_rows = ([header] if header else []) + rows
    width = max((len(r) for r in all_rows), default=0)
    padded = [r + [""] * (width - len(r)) for r in all_rows]
    text = "\n".join("\t".join(c.replace("\t", " ").replace("\n", " ") for c in r) for r in padded)
    e = html.escape
    head = f"<thead><tr>{''.join(f'<th>{e(c)}</th>' for c in padded[0])}</tr></thead>" if header and padded else ""
    body_rows = padded[1:] if header else padded
    body = "".join(f"<tr>{''.join(f'<td>{e(c)}</td>' for c in r)}</tr>" for r in body_rows)
    table_html = f"<table>{head}<tbody>{body}</tbody></table>"
    md_head = padded[0] if header and padded else [""] * width
    md = "\n".join([f"| {' | '.join(_md_cell(c) for c in md_head)} |", f"|{'|'.join(['---'] * width)}|",
                    *(f"| {' | '.join(_md_cell(c) for c in r)} |" for r in body_rows)]) if width else ""
    return text, table_html, md


def blocks_from_document(doc) -> list[dict]:
    from docling_core.types.doc import DocItemLabel, ListItem, PictureItem, TableItem, TextItem

    heights = {no: p.size.height for no, p in doc.pages.items()}
    blocks: list[dict] = []
    pending_list: dict | None = None

    def flush() -> None:
        nonlocal pending_list
        if pending_list:
            items = pending_list["items"]
            tag = "ol" if pending_list["ordered"] else "ul"
            blocks.append({
                "type": "lista", "page": pending_list["page"], "bbox": _union(pending_list["boxes"]),
                "text": "\n".join(items),
                "html": f"<{tag}>{''.join(f'<li>{html.escape(i)}</li>' for i in items)}</{tag}>",
                "markdown": "\n".join(f"{k}. {i}" if pending_list["ordered"] else f"- {i}" for k, i in enumerate(items, start=1)),
            })
        pending_list = None

    for item, level in doc.iterate_items():
        prov = item.prov[0] if getattr(item, "prov", None) else None
        if prov is None:
            continue
        box = _box(prov, heights)
        if isinstance(item, ListItem):
            parent = item.parent.cref if item.parent else ""
            text = item.text.strip()
            if pending_list and (pending_list["parent"] != parent or pending_list["page"] != prov.page_no):
                flush()
            if pending_list is None:
                pending_list = {"parent": parent, "page": prov.page_no, "items": [], "boxes": [], "ordered": bool(item.enumerated)}
            if text:
                pending_list["items"].append(text)
                pending_list["boxes"].append(box)
            continue
        flush()
        if isinstance(item, TableItem):
            header, rows = table_data(item, doc)
            text, table_html, md = table_block(header, rows)
            blocks.append({"type": "indice" if item.label == DocItemLabel.DOCUMENT_INDEX else "tabla", "page": prov.page_no,
                           "bbox": box, "text": text, "html": table_html, "markdown": md, "header": header, "rows": rows})
        elif isinstance(item, PictureItem):
            caption = item.caption_text(doc).strip() if hasattr(item, "caption_text") else ""
            blocks.append({"type": "imagen", "page": prov.page_no, "bbox": box, "text": caption,
                           "html": f"<p>{html.escape(caption)}</p>" if caption else "", "markdown": f"![{caption}]()"})
        elif isinstance(item, TextItem):
            text = item.text.strip()
            if not text:
                continue
            e = html.escape(text)
            if item.label in (DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER):
                n = 1 if item.label == DocItemLabel.TITLE else min(6, max(2, level + 1))
                blocks.append({"type": "titulo", "page": prov.page_no, "bbox": box, "text": text, "html": f"<h{n}>{e}</h{n}>",
                               "markdown": f"{'#' * n} {text}"})
            elif item.label == DocItemLabel.CODE:
                blocks.append({"type": "codigo", "page": prov.page_no, "bbox": box, "text": text,
                               "html": f"<pre><code>{e}</code></pre>", "markdown": f"```\n{text}\n```"})
            elif item.label == DocItemLabel.FORMULA:
                blocks.append({"type": "formula", "page": prov.page_no, "bbox": box, "text": text, "html": f"<p>{e}</p>",
                               "markdown": f"$${text}$$"})
            else:
                blocks.append({"type": "parrafo", "page": prov.page_no, "bbox": box, "text": text, "html": f"<p>{e}</p>",
                               "markdown": text})
    flush()
    for k, block in enumerate(blocks, start=1):
        block["id"] = f"b{k}"
    return blocks


def run(ctx: ToolContext) -> list[dict]:
    from docling_core.types.doc import ImageRefMode

    o = ctx.options
    if len(ctx.inputs) != 1:
        raise ToolError(ErrorCode.TOO_MANY_FILES)
    inp = ctx.inputs[0]
    src, pages = subset_pdf(ctx, inp.path, "todas", 0)
    ctx.report(0.05, None)
    doc = convert(src, o.ocr_si_no_hay_texto, o.idiomas, pictures=False)
    ctx.report(0.8, None)
    blocks = blocks_from_document(doc)
    stem = Path(inp.name).stem or "documento"
    data = {"version": VERSION, "source": inp.name,
            "pages": [{"number": no, "width": round(p.size.width, 2), "height": round(p.size.height, 2)} for no, p in sorted(doc.pages.items())],
            "blocks": blocks}
    outputs = []
    dst = ctx.output("bloques.json")
    dst.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    note = None if any(b["type"] != "imagen" for b in blocks) else NOTES.get(ctx.locale, NOTES["es"])["no_text"]
    outputs.append({"path": str(dst), "name": "bloques.json", "note": note})
    md = ctx.output(f"{stem}.md")
    md.write_text(doc.export_to_markdown(image_mode=ImageRefMode.PLACEHOLDER, image_placeholder=""), encoding="utf-8")
    outputs.append({"path": str(md), "name": md.name})
    if any(b["type"] in ("tabla", "indice") for b in blocks):
        xlsx = ctx.work / "tablas.xlsx"
        workbook_from_document(doc, xlsx, pages, False, True, ctx.locale, SHEET_LABELS.get(ctx.locale, SHEET_LABELS["es"]))
        final = ctx.output(f"{stem}-tablas.xlsx")
        shutil.move(xlsx, final)
        outputs.append({"path": str(final), "name": final.name})
    return outputs
