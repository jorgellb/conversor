"""pdf-a-fichas (7.6 y 6.3): fichas de estudio (término y definición, o pregunta y respuesta) para Anki o Quizlet
(texto con tabuladores), CSV o Word para imprimir y recortar. Una petición si el documento cabe; si no, una por bloque."""
from __future__ import annotations

import csv
import io
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.ai import comun
from tools.base import ToolContext, derived_name

KINDS = {"concepto": "Anverso: un término o concepto clave. Reverso: su definición o explicación breve (una o dos frases).",
         "pregunta": "Anverso: una pregunta concreta. Reverso: su respuesta breve (una o dos frases)."}
TEXTS = {
    "es": {"title": "Fichas de {name}", "front": "Anverso", "back": "Reverso", "page": "Página", "suffix": "-fichas"},
    "en": {"title": "Flashcards from {name}", "front": "Front", "back": "Back", "page": "Page", "suffix": "-flashcards"},
}
SCHEMA = {
    "type": "object",
    "properties": {"fichas": {"type": "array", "items": {
        "type": "object",
        "properties": {"anverso": {"type": "string"}, "reverso": {"type": "string"}, "pagina": {"type": "integer"}},
        "required": ["anverso", "reverso", "pagina"], "additionalProperties": False}}},
    "required": ["fichas"], "additionalProperties": False,
}


def clean(data, pages: set[int]) -> list[dict]:
    items = data.get("fichas") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("falta «fichas»")
    out, seen = [], set()
    for c in items:
        if not isinstance(c, dict):
            continue
        front, back = " ".join(str(c.get("anverso", "")).split()), " ".join(str(c.get("reverso", "")).split())
        if not front or not back or front.lower() in seen:
            continue
        seen.add(front.lower())
        page = c.get("pagina") if isinstance(c.get("pagina"), int) and c.get("pagina") in pages else None
        out.append({"anverso": front, "reverso": back, "pagina": page})
    if not out or len(out) * 2 < len(items):
        raise ValueError("demasiadas fichas no válidas")
    return out


def make(ctx: ToolContext, selected: list[int], body: str) -> dict:
    o = ctx.options
    parts, cap = comun.blocks(ctx, body, 90 * o.numero + 200)
    work = comun.batches(parts, o.numero, 90, cap)
    ctx.ai.budget.ensure(len(work))
    pages = {i + 1 for i in selected}
    cards: list[dict] = []
    for n, (part, count) in enumerate(work):
        ctx.report(0.1 + 0.8 * n / len(work), None)
        system = (f"Preparas fichas de estudio a partir de un documento. {comun.GUARD} {comun.language_rule(o.idioma)} "
                  f"Escribe exactamente {count} fichas sobre lo más importante, sin repetir ideas. {KINDS[o.tipo]} "
                  "`pagina`: la página («[Página n]») de donde sale.")
        if cards:
            system += " Ya hay estas fichas; haz otras distintas: " + " | ".join(c["anverso"][:80] for c in cards[-60:])
        data, _ = ctx.ai.complete_json(
            [{"role": "system", "content": system}, {"role": "user", "content": f"Documento:\n<<<\n{part}\n>>>"}],
            needs=comun.needs_for(part, 90 * count + 200), max_tokens=min(90 * count + 200, cap), schema=SCHEMA,
            check=lambda d: clean(d, pages))
        cards.extend(data[:count])
    if not cards:
        raise ToolError(ErrorCode.AI_UNAVAILABLE, "sin fichas")
    return {"fichas": cards, "model": (ctx.ai.models_used or [""])[-1]}


def tsv(cards: list[dict]) -> str:
    """Anverso y reverso separados por un tabulador, una ficha por línea: lo importan Anki y Quizlet."""
    flat = lambda s: s.replace("\t", " ").replace("\r", " ").replace("\n", " ")  # noqa: E731
    return "".join(f"{flat(c['anverso'])}\t{flat(c['reverso'])}\n" for c in cards)


def csv_text(cards: list[dict], t: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow([t["front"], t["back"], t["page"]])
    for c in cards:
        writer.writerow([c["anverso"], c["reverso"], c["pagina"] or ""])
    return "﻿" + buf.getvalue()  # con BOM: Excel lo abre con las tildes bien


def docx(dst: Path, cards: list[dict], t: dict, title: str, language: str, note: str) -> None:
    """Tabla de dos columnas (anverso y reverso) con bordes para recortar."""
    from docx import Document
    from docx.shared import Pt, RGBColor

    from tools.ai.salida import set_language

    doc = Document()
    doc.core_properties.title = title
    doc.core_properties.author = ""
    set_language(doc, language)
    doc.add_heading(title, level=1)
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    head = table.rows[0].cells
    head[0].text, head[1].text = t["front"], t["back"]
    for cell in head:
        cell.paragraphs[0].runs[0].bold = True
    for c in cards:
        row = table.add_row().cells
        row[0].text = c["anverso"]
        row[1].text = c["reverso"] + (f" ({t['page'].lower()} {c['pagina']})" if c["pagina"] else "")
    run = doc.add_paragraph().add_run(note)
    run.italic = True
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    doc.save(str(dst))


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    t = TEXTS.get(ctx.locale, TEXTS["es"])
    inp = ctx.inputs[0]
    selected, body = comun.document(ctx)
    options = {"numero": o.numero, "tipo": o.tipo, "idioma": o.idioma, "paginas": selected}
    result, hit = comun.with_cache(ctx, "pdf-a-fichas", options, lambda: make(ctx, selected, body))
    cards = result["fichas"]
    note = comun.note(ctx, hit)
    made = comun.texts(ctx)["made"].format(model=result.get("model") or "IA")
    ext = {"tsv": "txt", "csv": "csv"}.get(o.formato, "docx")
    name = derived_name(inp.name, t["suffix"], ext)
    dst = ctx.output(name)  # una sola vez: cada llamada da un nombre libre nuevo
    if o.formato == "tsv":
        dst.write_text(tsv(cards), encoding="utf-8")
    elif o.formato == "csv":
        dst.write_text(csv_text(cards, t), encoding="utf-8")
    else:
        docx(dst, cards, t, t["title"].format(name=Path(inp.name).stem), comun.output_language(o.idioma, ctx.locale), made)
    return [{"path": str(dst), "name": name, "note": note}]
