"""traducir-pdf (7.6 y 6.3): traduce el texto del PDF y lo regenera en Word y PDF con maquetación simplificada: títulos
y párrafos de cada página, una página nueva por cada página del original. Detrás de `TranslationProvider` (sin
BabelDOC, que es AGPL). Una petición por lote de párrafos que cabe en la salida máxima del modelo."""
from __future__ import annotations

import html
from pathlib import Path

from core.ai.translate import NAMES, LLMTranslator
from core.errors import ErrorCode, ToolError
from tools.ai import comun, documento
from tools.ai.parrafos import paragraphs
from tools.base import ToolContext, derived_name

TEXTS = {
    "es": {"title": "{name} (traducción al {lang})", "page": "Página {n} del original",
           "made": "Traducción hecha con IA ({model}). Puede tener errores: revísala antes de usarla."},
    "en": {"title": "{name} (translated into {lang})", "page": "Page {n} of the original",
           "made": "Translated with AI ({model}). It may contain errors: review it before using it."},
}
LANG_EN = {"es": "Spanish", "en": "English", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese",
           "ca": "Catalan", "nl": "Dutch", "pl": "Polish", "ro": "Romanian", "gl": "Galician", "eu": "Basque"}
SUFFIX = {"es": "-traducido-{code}", "en": "-translated-{code}"}


def structure(ctx: ToolContext) -> list[tuple[int, list[tuple[str, str]]]]:
    selected, texts = documento.text_of(ctx, ctx.inputs[0])
    pages = [(i + 1, paragraphs(t)) for i, t in zip(selected, texts)]
    if not any(items for _, items in pages):
        raise ToolError(ErrorCode.INVALID_OPTIONS, "ai_empty")
    return pages


def make(ctx: ToolContext, flat: list[str]) -> dict:
    o = ctx.options
    translator = LLMTranslator(ctx.ai)
    ctx.ai.budget.ensure(len(translator.plan(flat)))
    keep = [line.strip() for line in (o.glosario or "").splitlines() if line.strip()][:50]
    out = translator.translate(flat, o.destino, None if o.origen == "auto" else o.origen, keep,
                               progress=lambda f: ctx.report(0.1 + 0.8 * f, None))
    return {"traducciones": out, "model": (ctx.ai.models_used or [""])[-1]}


def write_docx(dst: Path, title: str, pages, language: str, t: dict, note: str) -> None:
    from docx import Document
    from docx.shared import Pt, RGBColor

    from tools.ai.salida import set_language

    doc = Document()
    doc.core_properties.title = title
    doc.core_properties.author = ""
    doc.styles["Normal"].font.size = Pt(11)
    set_language(doc, language)
    doc.add_heading(title, level=1)
    for n, (page, items) in enumerate(pages):
        if n:
            doc.add_page_break()
        mark = doc.add_paragraph().add_run(t["page"].format(n=page))
        mark.font.size, mark.font.color.rgb = Pt(8), RGBColor(0x77, 0x77, 0x77)
        for kind, text in items:
            if kind == "t":
                doc.add_heading(text, level=2)
            else:
                doc.add_paragraph(text)
    run = doc.add_paragraph().add_run(note)
    run.italic = True
    run.font.size, run.font.color.rgb = Pt(9), RGBColor(0x55, 0x55, 0x55)
    doc.save(str(dst))


def html_of(title: str, pages, language: str, t: dict, note: str) -> str:
    from tools.office.gotenberg import SANS

    esc = html.escape
    body = []
    for page, items in pages:
        parts = [f'<p class="marca">{esc(t["page"].format(n=page))}</p>']
        parts += [f"<h2>{esc(text)}</h2>" if kind == "t" else f"<p>{esc(text)}</p>" for kind, text in items]
        body.append(f'<section class="pagina">{"".join(parts)}</section>')
    style = (f"body{{font-family:{SANS};font-size:11pt;line-height:1.45;color:#111}}h1{{font-size:18pt;margin:0 0 12pt}}"
             "h2{font-size:13pt;margin:14pt 0 6pt}p{margin:0 0 8pt;text-align:justify;hyphens:auto}"
             ".pagina{break-after:page}.pagina:last-of-type{break-after:auto}.marca{color:#777;font-size:8pt;margin-bottom:6pt}"
             ".nota{color:#555;font-size:9pt;font-style:italic;margin-top:16pt}")
    return (f'<!doctype html><html lang="{esc(language)}"><head><meta charset="utf-8"><title>{esc(title)}</title>'
            f"<style>{style}</style></head><body><h1>{esc(title)}</h1>{''.join(body)}<p class=\"nota\">{esc(note)}</p></body></html>")


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    if o.origen != "auto" and o.origen == o.destino:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "ai_same_language")
    t = TEXTS.get(ctx.locale, TEXTS["es"])
    inp = ctx.inputs[0]
    pages = structure(ctx)
    flat = [text for _, items in pages for _, text in items]
    options = {"destino": o.destino, "origen": o.origen, "glosario": (o.glosario or "").strip(), "paginas": [p for p, _ in pages]}
    result, hit = comun.with_cache(ctx, "traducir-pdf", options, lambda: make(ctx, flat))
    out = iter(result["traducciones"])
    translated = [(page, [(kind, next(out, "")) for kind, _ in items]) for page, items in pages]
    lang_name = NAMES[o.destino] if ctx.locale != "en" else LANG_EN[o.destino]
    title = t["title"].format(name=Path(inp.name).stem, lang=lang_name)
    note = t["made"].format(model=result.get("model") or "IA")
    language = comun.output_language(o.destino, ctx.locale)
    stem_suffix = SUFFIX.get(ctx.locale, SUFFIX["es"]).format(code=o.destino)
    used = comun.note(ctx, hit)
    outputs = []
    if o.formato in ("docx_pdf", "docx"):
        name = derived_name(inp.name, stem_suffix, "docx")
        dst = ctx.output(name)
        write_docx(dst, title, translated, language, t, note)
        outputs.append({"path": str(dst), "name": name, "note": used})
    if o.formato in ("docx_pdf", "pdf"):
        from tools.office.gotenberg import chromium_html, page_fields

        page = ctx.work / "traduccion.html"
        page.write_text(html_of(title, translated, language, t, note), encoding="utf-8")
        name = derived_name(inp.name, stem_suffix, "pdf")
        dst = ctx.output(name)
        dst.write_bytes(chromium_html(ctx.settings.GOTENBERG_URL, page, page_fields("A4", "vertical", 20)))
        outputs.append({"path": str(dst), "name": name, "note": None if outputs else used})
    return outputs
