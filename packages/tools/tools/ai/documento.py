"""Texto de un PDF para las herramientas de IA y para pdf-a-audio (6.4): pypdfium2 en `workerai` (o en `workerav`) y,
para las páginas escaneadas, OCR con Tesseract en `workerocr`. El texto se guarda en `document_texts` (del propietario,
con la caducidad de sus archivos) y las siguientes herramientas lo reutilizan sin volver a leer el PDF."""
from __future__ import annotations

from core.ai.store import texts_get, texts_put
from core.db import session_scope
from core.errors import ErrorCode, ToolError
from core.options import parse_page_ranges
from tools.av import lectura
from tools.base import InputFile, ToolContext
from tools.pdf.common import open_pdf

MIN_CHARS = 3  # menos caracteres visibles que esto: página escaneada (como en pdf-a-txt)
OCR_LANGS = {"auto": ["spa", "eng"], "es": ["spa"], "en": ["eng"], "fr": ["fra"], "de": ["deu"], "it": ["ita"],
             "pt": ["por"], "ca": ["cat"]}
MESSAGES = {"es": "Leyendo con OCR las páginas escaneadas…", "en": "Reading scanned pages with OCR…"}


def _extract(ctx: ToolContext, inp: InputFile) -> list[str | None]:
    import pypdfium2 as pdfium

    with open_pdf(inp.path, None, ctx.plan.pdf_pages):
        pass
    doc = pdfium.PdfDocument(str(inp.path))
    pages: list[str | None] = []
    try:
        for i in range(len(doc)):
            page = doc[i]
            textpage = page.get_textpage()
            try:
                text = lectura.page_text(textpage)
            finally:
                textpage.close()
                page.close()
            pages.append(text if len("".join(text.split())) >= MIN_CHARS else None)
    finally:
        doc.close()
    return pages


def load(ctx: ToolContext, inp: InputFile) -> list[str | None]:
    """Páginas del documento: `None` es una página sin capa de texto que aún no ha pasado por el OCR."""
    owner_type, owner_id = ctx.owner
    with session_scope() as s:
        row = texts_get(s, owner_type, owner_id, inp.sha256, ctx.now())
        if row is not None:
            return list(row.pages)
    pages = _extract(ctx, inp)
    with session_scope() as s:
        texts_put(s, owner_type, owner_id, inp.sha256, pages, "pdfium", ctx.expires_at)
    return pages


def selection(ctx: ToolContext, total: int, ai_pages: bool = True) -> list[int]:
    try:
        selected = parse_page_ranges(ctx.options.paginas, total)
    except ValueError as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, str(exc)) from exc
    limit = ctx.plan.ai_pages_task
    if ai_pages and len(selected) > limit:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"ai_pages:{len(selected)}>{limit}")
    return selected


def text_of(ctx: ToolContext, inp: InputFile, ai_pages: bool = True, ocr_langs: list[str] | None = None) -> tuple[list[int], list[str]]:
    """Páginas elegidas y su texto. Si faltan escaneos y el OCR está activado, el trabajo pasa a `ocr` y vuelve a la
    cola de la herramienta (`ai`, o `av.heavy` en pdf-a-audio). `ai_pages=False` no aplica el límite de páginas por
    tarea de IA (pdf-a-audio tiene el suyo de caracteres, 9.3); `ocr_langs` fija los idiomas del OCR."""
    pages = load(ctx, inp)
    selected = selection(ctx, len(pages), ai_pages)
    missing = [i for i in selected if pages[i] is None]
    if missing and ctx.stage == "ocr":
        from tools.pdf.texto import ocr_pages

        langs = ocr_langs or OCR_LANGS.get(ctx.options.idioma_documento, ["spa", "eng"])
        found = ocr_pages(ctx, inp.path, missing, langs)
        for i in missing:
            pages[i] = (found.get(i) or "").strip()
        with session_scope() as s:
            texts_put(s, ctx.owner[0], ctx.owner[1], inp.sha256, pages, "pdfium+tesseract", ctx.expires_at)
        home = ctx.home_queue or "ai"
        ctx.handoff(home.split(".")[0], home.split(".")[0], None, queue=home)
    if missing:
        if not ctx.options.ocr:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "ai_scanned:" + ", ".join(str(i + 1) for i in missing[:20]))
        ctx.charge("heavy")
        ctx.handoff("ocr", "ocr", MESSAGES.get(ctx.locale, MESSAGES["es"]))
    return selected, [pages[i] or "" for i in selected]
