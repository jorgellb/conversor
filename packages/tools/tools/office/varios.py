"""svg-a-pdf (A.8), formatos con importación parcial de LibreOffice (7.3) y solicitud-de-empleo-pdf (A.1)."""
from __future__ import annotations

import html
import re
from pathlib import Path

from defusedxml import ElementTree as SafeET

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.office import gotenberg
from tools.office.anyto import merge_with_bookmarks, to_pdf
from tools.office.office_a_pdf import run as office_run
from tools.office.office_a_pdf import select_pages
from tools.pdf.common import with_batch_zip

UNIT_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72, "pc": 25.4 / 6, "px": 25.4 / 96, "": 25.4 / 96}
MAX_SVG_MM = 5000


def _length_mm(value: str | None) -> float | None:
    if not value:
        return None
    m = re.fullmatch(r"\s*([\d.]+)\s*([a-z%]*)\s*", value)
    if not m or m.group(2) == "%" or m.group(2) not in UNIT_MM:
        return None
    return float(m.group(1)) * UNIT_MM[m.group(2)]


def svg_size_mm(data: bytes) -> tuple[float, float]:
    """Tamaño del SVG en mm (width y height, o el viewBox a 96 ppp), leído sin entidades externas."""
    try:
        root = SafeET.fromstring(data)
    except Exception as exc:  # noqa: BLE001 - XML mal formado o con entidades
        raise ToolError(ErrorCode.CORRUPT_FILE, "SVG no válido") from exc
    w, h = _length_mm(root.get("width")), _length_mm(root.get("height"))
    box = [float(v) for v in re.split(r"[\s,]+", root.get("viewBox", "").strip()) if v] if root.get("viewBox") else []
    if (w is None or h is None) and len(box) == 4:
        ratio = box[3] / box[2] if box[2] else 1
        if w is None and h is None:
            w, h = box[2] * UNIT_MM["px"], box[3] * UNIT_MM["px"]
        elif w is None:
            w = h / ratio
        else:
            h = w * ratio
    w, h = w or 210.0, h or 297.0
    return min(max(w, 1), MAX_SVG_MM), min(max(h, 1), MAX_SVG_MM)


def run_svg(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        data = inp.path.read_bytes()
        w, h = svg_size_mm(data)
        if o.tamano == "svg":
            page_w, page_h, margin, img_w, img_h = w, h, 0.0, w, h
        else:
            page_w, page_h, margin = (297.0, 210.0, 10.0) if w > h else (210.0, 297.0, 10.0)
            scale = min((page_w - 2 * margin) / w, (page_h - 2 * margin) / h)
            img_w, img_h = w * scale, h * scale
        page = (f"<!doctype html><html><head><meta charset=\"utf-8\"><style>@page{{size:{page_w:.2f}mm {page_h:.2f}mm;margin:{margin}mm}}"
                f"html,body{{margin:0}}img{{display:block;margin:auto;width:{img_w:.2f}mm;height:{img_h:.2f}mm}}</style></head>"
                f"<body><img src=\"dibujo.svg\" alt=\"\"></body></html>")
        files = [("index.html", page.encode("utf-8"), "text/html"), ("dibujo.svg", data, "image/svg+xml")]
        pdf = gotenberg.chromium_html_files(ctx.settings.GOTENBERG_URL, files,
                                            gotenberg.page_fields("A4", "vertical", 0, True, False, "print", tamano_css=True))
        name = derived_name(inp.name, "", "pdf")
        dst = ctx.output(name)
        dst.write_bytes(pdf)
        select_pages(dst, "todas", ctx.plan.pdf_pages)
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "svg-pdf.zip")


PARTIAL_NOTE = {
    "es": "LibreOffice importa este formato solo en parte: revisa el resultado (fuentes, efectos y diseño pueden cambiar).",
    "en": "LibreOffice imports this format only in part: check the result (fonts, effects and layout may change).",
}


def run_partial(ctx: ToolContext) -> list[dict]:
    """pages, keynote, numbers, visio y publisher a PDF con LibreOffice, avisando de la calidad (7.3)."""
    outputs = office_run(ctx)
    for o in outputs:
        if not str(o["name"]).endswith(".zip"):
            o["note"] = PARTIAL_NOTE.get(ctx.locale, PARTIAL_NOTE["es"])
    return outputs


# --- solicitud-de-empleo-pdf ----------------------------------------------------------------------------------------


JOB_LABELS = {
    "es": {"letter": "Carta de presentación", "cv": "Currículum", "index": "Índice", "compressed": "Comprimida porque superaba {mb:g} MB."},
    "en": {"letter": "Cover letter", "cv": "CV", "index": "Contents", "compressed": "Compressed because it was over {mb:g} MB."},
}


def _index_page(ctx: ToolContext, title: str, entries: list[tuple[str, int]], dst: Path) -> None:
    rows = "".join(f"<tr><td>{html.escape(t)}</td><td class=\"p\">{p}</td></tr>" for t, p in entries)
    page = (f"<!doctype html><html lang=\"{ctx.locale}\"><head><meta charset=\"utf-8\"><style>body{{font-family:{gotenberg.SANS};font-size:12pt}}"
            "h1{font-size:18pt;margin-bottom:16px}table{width:100%;border-collapse:collapse}td{padding:6px 0;border-bottom:1px dotted #999}"
            f".p{{text-align:right;width:4em}}</style></head><body><h1>{html.escape(title)}</h1><table>{rows}</table></body></html>")
    dst.write_bytes(gotenberg.chromium_html_files(ctx.settings.GOTENBERG_URL, [("index.html", page.encode("utf-8"), "text/html")],
                                                  gotenberg.page_fields("A4", "vertical", 20, True, False, "print")))


def run_job_application(ctx: ToolContext) -> list[dict]:
    """Carta (opcional), CV y adjuntos convertidos con Gotenberg y unidos con pikepdf, con un marcador por documento."""
    import pikepdf

    o = ctx.options
    labels = JOB_LABELS.get(ctx.locale, JOB_LABELS["es"])
    if not ctx.inputs:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "Falta el CV")
    roles: list[str] = []
    for i, inp in enumerate(ctx.inputs):
        if o.primera_es_carta and len(ctx.inputs) > 1 and i == 0:
            roles.append(labels["letter"])
        elif labels["cv"] not in roles:
            roles.append(labels["cv"])
        else:
            roles.append(Path(inp.name).stem)
    parts: list[tuple[str, Path]] = []
    for i, (inp, role) in enumerate(zip(ctx.inputs, roles)):
        ctx.report(i / len(ctx.inputs), None)
        pdf = to_pdf(ctx, inp.path, inp.name, f"sol-{i}")
        if pdf is None:
            raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, inp.name)
        parts.append((role, pdf))
    cv_name = ctx.inputs[1].name if (o.primera_es_carta and len(ctx.inputs) > 1) else ctx.inputs[0].name
    name = f"solicitud-{Path(cv_name).stem}.pdf"
    dst = ctx.output(name)
    merged = ctx.work / "solicitud.pdf"
    merge_with_bookmarks(parts, merged, ctx.plan.pdf_pages)
    if o.indice:
        counts = []
        for _, p in parts:
            with pikepdf.open(p) as pdf:
                counts.append(len(pdf.pages))
        index = ctx.work / "indice.pdf"
        index_pages = 1
        for _ in range(3):  # se rehace si el índice ocupa más de lo previsto
            entries, start = [], index_pages + 1
            for (title, _), count in zip(parts, counts):
                entries.append((title, start))
                start += count
            _index_page(ctx, labels["index"], entries, index)
            with pikepdf.open(index) as pdf:
                real = len(pdf.pages)
            if real == index_pages:
                break
            index_pages = real
        merge_with_bookmarks([(labels["index"], index), *parts], merged, ctx.plan.pdf_pages)
    if not o.marcadores:
        with pikepdf.open(merged, allow_overwriting_input=True) as pdf:
            if "/Outlines" in pdf.Root:
                del pdf.Root["/Outlines"]
            pdf.save(merged)
    note = None
    if o.comprimir and merged.stat().st_size > o.umbral_mb * 1024 * 1024:
        from tools.pdf.comprimir_pdf import compress_one
        from tools.pdf.specs import ComprimirOptions

        smaller = ctx.work / "solicitud-comprimida.pdf"
        compress_one(merged, smaller, ComprimirOptions(), None, ctx.plan.pdf_pages)
        if smaller.exists() and smaller.stat().st_size < merged.stat().st_size:
            merged = smaller
            note = labels["compressed"].format(mb=o.umbral_mb)
    dst.write_bytes(merged.read_bytes())
    return [{"path": str(dst), "name": name, "note": note}]
