"""pdf-a-txt (A.9): texto con pypdfium2 y OCR de OCRmyPDF solo en las páginas que no tienen texto.

Con «OCR automático» el trabajo va a la cola `ocr`; si hace falta OCR, cuenta como tarea de OCR (`ctx.charge`). Si al
dueño ya no le quedan tareas de OCR, se entrega el texto que hay y se avisa (D-61).
"""
from __future__ import annotations

from pathlib import Path

import pikepdf
import pypdfium2 as pdfium

from core.errors import ErrorCode, ToolError
from core.options import parse_page_ranges
from tools.base import ToolContext, derived_name
from tools.pdf.common import open_pdf, with_batch_zip

MIN_CHARS = 3  # menos caracteres visibles que esto: la página se trata como escaneada
NOTES = {
    "es": {"ocr": "Páginas leídas con OCR: {pages}.", "quota": "Sin OCR en las páginas {pages}: has llegado al límite diario de tareas de OCR.",
           "empty": "Páginas sin texto: {pages}. Activa el OCR automático o pasa antes ocr-pdf.", "page": "Página {n}"},
    "en": {"ocr": "Pages read with OCR: {pages}.", "quota": "No OCR on pages {pages}: you reached the daily limit of OCR tasks.",
           "empty": "Pages without text: {pages}. Turn on automatic OCR or run ocr-pdf first.", "page": "Page {n}"},
}


def _pages_list(indexes: list[int]) -> str:
    return ", ".join(str(i + 1) for i in indexes)


def ocr_pages(ctx: ToolContext, src: Path, indexes: list[int], languages: list[str]) -> dict[int, str]:
    """Texto de esas páginas con OCRmyPDF (rasterizador pypdfium2, sin Ghostscript) y su archivo de texto lateral."""
    import ocrmypdf
    from ocrmypdf import exceptions as ocr_exc

    subset = ctx.work / f"ocr-{src.stem}.pdf"
    with open_pdf(src, None, ctx.plan.pdf_pages) as pdf:
        new = pikepdf.Pdf.new()
        for i in indexes:
            new.pages.append(pdf.pages[i])
        new.save(subset)
        new.close()
    sidecar = subset.with_suffix(".txt")
    try:
        # Solo interesa el texto lateral: con output_type «none» la salida tiene que ser «-» (OCRmyPDF no escribe nada).
        ocrmypdf.ocr(str(subset), "-", language=languages, mode="force",
                     output_type="none", sidecar=str(sidecar), rasterizer="pypdfium", jobs=max(1, ctx.threads), progress_bar=False,
                     max_image_mpixels=ctx.settings.IMAGE_MAX_PIXELS / 1_000_000)
    except ocr_exc.ExitCodeException as exc:
        raise ToolError(ErrorCode.ENGINE_FAILED, type(exc).__name__) from exc
    chunks = sidecar.read_text(encoding="utf-8", errors="replace").split("\f")
    return {idx: (chunks[k] if k < len(chunks) else "") for k, idx in enumerate(indexes)}


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    labels = NOTES.get(ctx.locale, NOTES["es"])
    charged = False
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        with open_pdf(inp.path, None, ctx.plan.pdf_pages):
            pass
        doc = pdfium.PdfDocument(str(inp.path))
        try:
            try:
                pages = parse_page_ranges(o.paginas, len(doc))
            except ValueError as exc:
                raise ToolError(ErrorCode.INVALID_OPTIONS, str(exc)) from exc
            texts: dict[int, str] = {}
            empty: list[int] = []
            for k, idx in enumerate(pages):
                page = doc[idx]
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_range().replace("\r\n", "\n").replace("\r", "\n")
                finally:
                    textpage.close()
                    page.close()
                texts[idx] = text
                if len("".join(text.split())) < MIN_CHARS:
                    empty.append(idx)
                ctx.report((n + (k + 1) / len(pages) / 2) / len(ctx.inputs), None)
        finally:
            doc.close()
        notes = []
        if empty and o.ocr_si_no_hay_texto:
            try:
                if not charged:
                    ctx.charge("heavy")
                    charged = True
                texts.update(ocr_pages(ctx, inp.path, empty, o.idiomas))
                notes.append(labels["ocr"].format(pages=_pages_list(empty)))
            except ToolError as exc:
                if exc.code != ErrorCode.QUOTA_EXCEEDED:
                    raise
                notes.append(labels["quota"].format(pages=_pages_list(empty)))
        elif empty:
            notes.append(labels["empty"].format(pages=_pages_list(empty)))
        parts = []
        for idx in pages:
            body = texts[idx].rstrip()
            if o.separador == "linea":
                parts.append(f"--- {labels['page'].format(n=idx + 1)} ---\n{body}")
            else:
                parts.append(body)
        joiner = "\n\f\n" if o.separador == "salto" else "\n\n"
        name = derived_name(inp.name, "", "txt")
        dst = ctx.output(name)
        dst.write_text(joiner.join(parts) + "\n", encoding="utf-8")
        outputs.append({"path": str(dst), "name": name, "note": " ".join(notes) or None})
    return with_batch_zip(ctx, outputs, "pdf-txt.zip")
