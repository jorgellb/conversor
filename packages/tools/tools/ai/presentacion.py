"""pdf-a-presentacion (7.6 y 6.3): dos peticiones, como pide 6.3. La primera saca el esquema del documento (una por
bloque si no cabe) y la segunda convierte ese esquema en diapositivas con notas del orador. El PowerPoint (16:9) lo
dibuja python-pptx con cuadros de texto propios, así se ve igual en PowerPoint, LibreOffice y Keynote."""
from __future__ import annotations

from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.ai import comun
from tools.base import ToolContext, derived_name

OUTLINE = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string"},
        "secciones": {"type": "array", "items": {
            "type": "object",
            "properties": {"titulo": {"type": "string"}, "ideas": {"type": "array", "items": {"type": "string"}},
                           "paginas": {"type": "array", "items": {"type": "integer"}}},
            "required": ["titulo", "ideas", "paginas"], "additionalProperties": False}},
    },
    "required": ["titulo", "secciones"], "additionalProperties": False,
}
SLIDES = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string"},
        "subtitulo": {"type": "string"},
        "diapositivas": {"type": "array", "items": {
            "type": "object",
            "properties": {"titulo": {"type": "string"}, "puntos": {"type": "array", "items": {"type": "string"}},
                           "notas": {"type": "string"}, "paginas": {"type": "array", "items": {"type": "integer"}}},
            "required": ["titulo", "puntos", "notas", "paginas"], "additionalProperties": False}},
    },
    "required": ["titulo", "subtitulo", "diapositivas"], "additionalProperties": False,
}
THEMES = {
    "claro": {"bg": "FFFFFF", "title": "1F3A5F", "text": "222222", "accent": "2F6FDF", "muted": "6B7280"},
    "oscuro": {"bg": "1E2430", "title": "FFFFFF", "text": "E6E9EF", "accent": "5AA9FF", "muted": "9AA3B2"},
    "color": {"bg": "F6F1E7", "title": "7A2E2E", "text": "333333", "accent": "D9822B", "muted": "7C6F64"},
}
TEXTS = {"es": {"pages": "Págs.", "page": "Pág.", "based": "Basada en «{name}»", "suffix": "-presentacion"},
         "en": {"pages": "Pp.", "page": "P.", "based": "Based on “{name}”", "suffix": "-presentation"}}


def _outline_check(data, pages: set[int]) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("secciones"), list) or not data["secciones"]:
        raise ValueError("falta «secciones»")
    sections = []
    for s in data["secciones"]:
        if isinstance(s, dict) and str(s.get("titulo", "")).strip():
            ideas = [str(i).strip() for i in (s.get("ideas") or []) if str(i).strip()][:8]
            sections.append({"titulo": str(s["titulo"]).strip(), "ideas": ideas,
                             "paginas": sorted({p for p in (s.get("paginas") or []) if isinstance(p, int) and p in pages})})
    if not sections:
        raise ValueError("sin secciones válidas")
    return {"titulo": str(data.get("titulo") or "").strip(), "secciones": sections}


def _slides_check(data, count: int, pages: set[int]) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("diapositivas"), list):
        raise ValueError("falta «diapositivas»")
    slides = []
    for s in data["diapositivas"]:
        if not isinstance(s, dict) or not str(s.get("titulo", "")).strip():
            continue
        points = [" ".join(str(p).split()) for p in (s.get("puntos") or []) if str(p).strip()][:6]
        slides.append({"titulo": " ".join(str(s["titulo"]).split()), "puntos": points, "notas": str(s.get("notas") or "").strip(),
                       "paginas": sorted({p for p in (s.get("paginas") or []) if isinstance(p, int) and p in pages})})
    if len(slides) < max(2, count // 2):
        raise ValueError("demasiadas diapositivas no válidas")
    return {"titulo": str(data.get("titulo") or "").strip(), "subtitulo": str(data.get("subtitulo") or "").strip(),
            "diapositivas": slides[:count]}


def make(ctx: ToolContext, selected: list[int], body: str) -> dict:
    o = ctx.options
    content = o.diapositivas - 1  # la primera es la portada
    parts, cap = comun.blocks(ctx, body, 2500)
    ctx.ai.budget.ensure(len(parts) + 1)
    pages = {i + 1 for i in selected}
    outlines = []
    for n, part in enumerate(parts, start=1):
        ctx.report(0.1 + 0.6 * (n - 1) / len(parts), None)
        where = f" Es la parte {n} de {len(parts)} del documento." if len(parts) > 1 else ""
        system = (f"Haces el esquema de un documento para preparar una presentación. {comun.GUARD}{where} "
                  f"{comun.language_rule(o.idioma)} Da su título y sus secciones principales, en orden, cada una con sus "
                  "ideas clave (frases cortas) y las páginas («[Página n]») de donde salen.")
        data, _ = ctx.ai.complete_json(
            [{"role": "system", "content": system}, {"role": "user", "content": f"Documento:\n<<<\n{part}\n>>>"}],
            needs=comun.needs_for(part, 2500), max_tokens=min(2500, cap), schema=OUTLINE, check=lambda d: _outline_check(d, pages))
        outlines.append(data)
    title = next((x["titulo"] for x in outlines if x["titulo"]), "")
    sections = [s for x in outlines for s in x["secciones"]]
    import json

    outline_text = json.dumps({"titulo": title, "secciones": sections}, ensure_ascii=False)
    notes = ("Cada diapositiva lleva en `notas` lo que diría el orador (2 a 4 frases)." if o.notas
             else "Deja `notas` vacío.")
    system = (f"Conviertes el esquema de un documento en una presentación. {comun.language_rule(o.idioma)} Escribe "
              f"exactamente {content} diapositivas de contenido (sin portada), en un orden que cuente el documento de "
              "principio a fin. Cada una: un título corto y de 3 a 6 puntos de menos de 15 palabras, sin repetir el título. "
              f"{notes} `paginas`: las páginas del documento en las que se basa. Además, `titulo` y `subtitulo` de la "
              "portada. Usa solo lo que dice el esquema.")
    ctx.report(0.75, None)
    deck, _ = ctx.ai.complete_json(
        [{"role": "system", "content": system}, {"role": "user", "content": f"Esquema:\n<<<\n{outline_text}\n>>>"}],
        needs=comun.needs_for(outline_text, 250 * content + 300), max_tokens=min(250 * content + 300, cap),
        schema=SLIDES, check=lambda d: _slides_check(d, content, pages))
    if not deck["titulo"]:
        deck["titulo"] = title
    deck["model"] = (ctx.ai.models_used or [""])[-1]
    return deck


def _range(pages: list[int], t: dict) -> str:
    if not pages:
        return ""
    if len(pages) == 1:
        return f"{t['page']} {pages[0]}"
    return f"{t['pages']} {pages[0]}–{pages[-1]}" if pages[-1] - pages[0] == len(pages) - 1 else f"{t['pages']} {', '.join(map(str, pages))}"


def render(dst: Path, deck: dict, theme_name: str, t: dict, source_name: str, with_notes: bool) -> None:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Emu, Inches, Pt

    theme = THEMES.get(theme_name, THEMES["claro"])
    color = lambda h: RGBColor.from_string(h)  # noqa: E731
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    prs.core_properties.title = deck["titulo"]
    prs.core_properties.author = ""
    blank = prs.slide_layouts[6]
    W, H = prs.slide_width, prs.slide_height

    def background(slide) -> None:
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = color(theme["bg"])

    def text(slide, x, y, w, h, value: str, size: int, rgb: str, bold: bool = False, align=PP_ALIGN.LEFT):
        box = slide.shapes.add_textbox(x, y, w, h)
        frame = box.text_frame
        frame.word_wrap = True
        para = frame.paragraphs[0]
        para.alignment = align
        run = para.add_run()
        run.text = value
        run.font.size, run.font.bold, run.font.color.rgb = Pt(size), bold, color(rgb)
        return frame

    def bar(slide, x, y, w, h) -> None:
        from pptx.enum.shapes import MSO_SHAPE

        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
        shape.fill.solid()
        shape.fill.fore_color.rgb = color(theme["accent"])
        shape.line.fill.background()

    cover = prs.slides.add_slide(blank)
    background(cover)
    bar(cover, Inches(0.9), Inches(3.05), Inches(1.6), Emu(Inches(0.09)))
    text(cover, Inches(0.9), Inches(1.4), W - Inches(1.8), Inches(1.6), deck["titulo"], 40, theme["title"], bold=True)
    if deck.get("subtitulo"):
        text(cover, Inches(0.9), Inches(3.3), W - Inches(1.8), Inches(1.2), deck["subtitulo"], 20, theme["text"])
    text(cover, Inches(0.9), H - Inches(1.0), W - Inches(1.8), Inches(0.5), t["based"].format(name=source_name), 12, theme["muted"])

    total = len(deck["diapositivas"]) + 1
    for n, s in enumerate(deck["diapositivas"], start=2):
        slide = prs.slides.add_slide(blank)
        background(slide)
        bar(slide, Inches(0.6), Inches(0.55), Emu(Inches(0.09)), Inches(0.75))
        text(slide, Inches(0.85), Inches(0.45), W - Inches(1.7), Inches(1.0), s["titulo"], 30, theme["title"], bold=True)
        chars = sum(len(p) for p in s["puntos"])
        size = 20 if chars < 300 else 18 if chars < 420 else 16
        frame = slide.shapes.add_textbox(Inches(0.85), Inches(1.75), W - Inches(1.7), H - Inches(2.7)).text_frame
        frame.word_wrap = True
        for k, point in enumerate(s["puntos"]):
            para = frame.paragraphs[0] if k == 0 else frame.add_paragraph()
            para.space_after = Pt(10)
            run = para.add_run()
            run.text = f"•  {point}"
            run.font.size, run.font.color.rgb = Pt(size), color(theme["text"])
        text(slide, Inches(0.85), H - Inches(0.7), Inches(6), Inches(0.4), _range(s["paginas"], t), 11, theme["muted"])
        text(slide, W - Inches(1.85), H - Inches(0.7), Inches(1.0), Inches(0.4), f"{n} / {total}", 11, theme["muted"], align=PP_ALIGN.RIGHT)
        if with_notes and s["notas"]:
            slide.notes_slide.notes_text_frame.text = s["notas"]
    prs.save(str(dst))


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    t = TEXTS.get(ctx.locale, TEXTS["es"])
    inp = ctx.inputs[0]
    selected, body = comun.document(ctx)
    options = {"diapositivas": o.diapositivas, "notas": o.notas, "idioma": o.idioma, "paginas": selected}
    deck, hit = comun.with_cache(ctx, "pdf-a-presentacion", options, lambda: make(ctx, selected, body))
    if not deck.get("diapositivas"):
        raise ToolError(ErrorCode.AI_UNAVAILABLE, "sin diapositivas")
    name = derived_name(inp.name, t["suffix"], "pptx")
    dst = ctx.output(name)
    render(dst, deck, o.estilo, t, inp.name, o.notas)
    made = comun.texts(ctx)["made"].format(model=deck.get("model") or "IA")
    return [{"path": str(dst), "name": name, "note": f"{comun.note(ctx, hit)} {made}"}]
