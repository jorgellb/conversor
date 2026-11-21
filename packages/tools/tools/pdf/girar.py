"""girar-pdf en el servidor (A.4, D-261): el mismo giro que en el navegador y, con «autoorientar», cada página elegida
se gira según la orientación que detecta Tesseract (`--psm 0`) en una imagen de la página a 150 ppp. Si Tesseract no
está seguro (confianza menor de 2), la página se deja como está. La web manda aquí el trabajo cuando se pide
autoorientar o el archivo es demasiado grande para el navegador.
"""
from __future__ import annotations

from core.errors import ErrorCode, ToolError
from core.options import parse_page_ranges
from tools.base import ToolContext, derived_name
from tools.pdf.common import open_pdf, with_batch_zip

DPI = 150
TEXTS = {
    "es": {"auto": "Autoorientar: {n} de {total} páginas giradas ({pages}).", "none": "Autoorientar: todas las páginas ya estaban derechas."},
    "en": {"auto": "Auto-orient: {n} of {total} pages rotated ({pages}).", "none": "Auto-orient: every page was already upright."},
}


def _pages_text(pages: list[int]) -> str:
    shown = ", ".join(str(p + 1) for p in pages[:20])
    return shown + ("…" if len(pages) > 20 else "")


def detect_turns(ctx: ToolContext, path, pages: list[int]) -> dict[int, int]:
    """Grados en sentido horario que hay que girar cada página (solo las que no están derechas)."""
    import pypdfium2 as pdfium

    from tools.ocr.imagen import osd_rotation

    turns: dict[int, int] = {}
    doc = pdfium.PdfDocument(str(path))
    try:
        for k, idx in enumerate(pages):
            page = doc[idx]
            try:
                image = page.render(scale=DPI / 72).to_pil().convert("L")
            finally:
                page.close()
            png = ctx.work / f"orientacion-{idx}.png"
            image.save(png, format="PNG")
            turn = osd_rotation(ctx, png)
            png.unlink(missing_ok=True)
            if turn:
                turns[idx] = turn
            ctx.report((k + 1) / len(pages) * 0.9, None)
    finally:
        doc.close()
    return turns


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    t = TEXTS.get(ctx.locale, TEXTS["es"])
    outputs = []
    for inp in ctx.inputs:
        with open_pdf(inp.path, ctx.secrets.get("contrasena"), ctx.plan.pdf_pages) as pdf:
            total = len(pdf.pages)
            try:
                selected = parse_page_ranges(o.paginas, total)
            except ValueError as exc:
                raise ToolError(ErrorCode.INVALID_OPTIONS, str(exc)) from exc
            turns = detect_turns(ctx, inp.path, selected) if o.autoorientar else {}
            for i, page in enumerate(pdf.pages):
                extra = o.por_pagina.get(str(i + 1))
                if extra is not None:
                    delta = extra
                elif o.autoorientar:
                    delta = turns.get(i, 0)
                else:
                    delta = o.angulo if i in selected else 0
                if delta % 90:
                    raise ToolError(ErrorCode.INVALID_OPTIONS, "El giro debe ser múltiplo de 90°")
                if delta:
                    page.rotate(delta, relative=True)
            name = derived_name(inp.name, "", "pdf")
            dst = ctx.output(name)
            pdf.save(dst)
        note = None
        if o.autoorientar:
            note = t["auto"].format(n=len(turns), total=len(selected), pages=_pages_text(sorted(turns))) if turns else t["none"]
        outputs.append({"path": str(dst), "name": name, "note": note})
    return with_batch_zip(ctx, outputs, "pdf-girados.zip")
