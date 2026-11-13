"""generador-de-preguntas (7.6 y 6.3): preguntas de test, verdadero o falso o respuesta corta sobre el documento, con
soluciones, en Word, Moodle (GIFT) o texto. Una petición si el documento cabe; si no, una por bloque con las preguntas
repartidas según su tamaño. Salida JSON con esquema (6.5)."""
from __future__ import annotations

import re
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.ai import comun
from tools.base import ToolContext, derived_name

TYPES = {"test": "de test con una sola respuesta correcta", "verdadero_falso": "de verdadero o falso",
         "corta": "de respuesta corta (una palabra o una frase)"}
LEVEL = {"facil": "fáciles (datos que aparecen tal cual en el texto)", "media": "de dificultad media",
         "dificil": "difíciles (que exigen relacionar ideas o razonar)"}
TEXTS = {
    "es": {"title": "Preguntas sobre {name}", "solutions": "Soluciones", "answer": "Respuesta", "true": "Verdadero",
           "false": "Falso", "page": "pág.", "suffix": "-preguntas", "sol_suffix": "-soluciones", "name": "Nombre:", "line": "_" * 50},
    "en": {"title": "Questions about {name}", "solutions": "Answers", "answer": "Answer", "true": "True", "false": "False",
           "page": "p.", "suffix": "-questions", "sol_suffix": "-answers", "name": "Name:", "line": "_" * 50},
}
LETTERS = "abcdefghij"


def schema(options: int) -> dict:
    question = {
        "type": "object",
        "properties": {
            "tipo": {"type": "string", "enum": ["test", "verdadero_falso", "corta"]},
            "enunciado": {"type": "string"},
            "opciones": {"type": "array", "items": {"type": "string"}},
            "correcta": {"type": "integer"},
            "respuesta": {"type": "string"},
            "explicacion": {"type": "string"},
            "pagina": {"type": "integer"},
        },
        "required": ["tipo", "enunciado", "opciones", "correcta", "respuesta", "explicacion", "pagina"],
        "additionalProperties": False,
    }
    return {"type": "object", "properties": {"preguntas": {"type": "array", "items": question}},
            "required": ["preguntas"], "additionalProperties": False}


def clean(data, n_options: int, allowed: set[str], pages: set[int]) -> list[dict]:
    """Preguntas válidas (las que no lo son se descartan); si queda menos de la mitad, se pide reparar."""
    items = data.get("preguntas") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("falta «preguntas»")
    out = []
    for q in items:
        if not isinstance(q, dict) or not str(q.get("enunciado", "")).strip():
            continue
        kind = q.get("tipo") if q.get("tipo") in allowed else next(iter(allowed))
        options = [str(o).strip() for o in (q.get("opciones") or []) if str(o).strip()]
        correct = q.get("correcta") if isinstance(q.get("correcta"), int) else -1
        answer = str(q.get("respuesta") or "").strip()
        if kind == "test":
            options = options[:n_options]
            if len(options) < 2 or not 0 <= correct < len(options):
                continue
        elif kind == "verdadero_falso":
            if correct not in (0, 1):
                low = answer.lower()
                correct = 0 if low.startswith(("v", "t", "s", "y")) else 1 if low else -1
            if correct not in (0, 1):
                continue
            options = []
        else:
            if not answer:
                continue
            options, correct = [], -1
        page = q.get("pagina") if isinstance(q.get("pagina"), int) and q.get("pagina") in pages else None
        out.append({"tipo": kind, "enunciado": str(q["enunciado"]).strip(), "opciones": options, "correcta": correct,
                    "respuesta": answer, "explicacion": str(q.get("explicacion") or "").strip(), "pagina": page})
    if len(out) * 2 < len(items) or not out:
        raise ValueError("demasiadas preguntas no válidas")
    return out


def ask(ctx: ToolContext, block: str, count: int, pages: set[int], avoid: list[str] | None = None, cap: int = 8000) -> list[dict]:
    o = ctx.options
    allowed = {"test", "verdadero_falso", "corta"} if o.tipo == "mezcla" else {o.tipo}
    kinds = "una mezcla de preguntas de test, de verdadero o falso y de respuesta corta" if o.tipo == "mezcla" else f"preguntas {TYPES[o.tipo]}"
    system = (f"Eres un profesor que prepara preguntas de examen a partir de un documento. {comun.GUARD} "
              f"{comun.language_rule(o.idioma)} Escribe exactamente {count} {kinds}, {LEVEL[o.dificultad]}, sobre ideas distintas "
              f"y repartidas por todo el texto. En las de test, {o.opciones} opciones con una sola correcta (`correcta` es su "
              "índice, empezando en 0) y distractores creíbles; en las de verdadero o falso, `correcta` es 0 si es verdadera y "
              "1 si es falsa, y `opciones` va vacía; en las de respuesta corta, `opciones` va vacía, `correcta` es -1 y "
              "`respuesta` es la respuesta. `explicacion`: una frase con el porqué. `pagina`: la página («[Página n]») de "
              "donde sale.")
    if avoid:
        system += " Ya hay estas preguntas; haz otras distintas: " + " | ".join(a[:120] for a in avoid[-40:])
    data, _ = ctx.ai.complete_json(
        [{"role": "system", "content": system}, {"role": "user", "content": f"Documento:\n<<<\n{block}\n>>>"}],
        needs=comun.needs_for(block, 250 * count + 200), max_tokens=min(250 * count + 200, cap), schema=schema(o.opciones),
        check=lambda d: clean(d, o.opciones, allowed, pages))
    return data[:count]


def make(ctx: ToolContext, selected: list[int], body: str) -> dict:
    o = ctx.options
    parts, cap = comun.blocks(ctx, body, 250 * o.numero + 200)
    work = comun.batches(parts, o.numero, 250, cap)
    ctx.ai.budget.ensure(len(work))
    pages = {i + 1 for i in selected}
    questions: list[dict] = []
    for n, (part, count) in enumerate(work):
        ctx.report(0.1 + 0.8 * n / len(work), None)
        questions.extend(ask(ctx, part, count, pages, [q["enunciado"] for q in questions], cap))
    if not questions:
        raise ToolError(ErrorCode.AI_UNAVAILABLE, "sin preguntas")
    return {"preguntas": questions, "model": (ctx.ai.models_used or [""])[-1]}


# --- salidas ---


def _gift_escape(text: str) -> str:
    return re.sub(r"([~=#{}:\\])", r"\\\1", text.replace("\n", " "))


def gift(questions: list[dict]) -> str:
    """Formato GIFT de Moodle: test (= correcta, ~ incorrectas), verdadero o falso ({T} o {F}) y respuesta corta."""
    out = []
    for i, q in enumerate(questions, start=1):
        head = f"::P{i}:: {_gift_escape(q['enunciado'])}"
        fb = f"#{_gift_escape(q['explicacion'])}" if q["explicacion"] else ""
        if q["tipo"] == "test":
            opts = "\n".join(("=" if k == q["correcta"] else "~") + _gift_escape(o) for k, o in enumerate(q["opciones"]))
            out.append(f"{head} {{\n{opts}\n{fb}\n}}" if fb else f"{head} {{\n{opts}\n}}")
        elif q["tipo"] == "verdadero_falso":
            out.append(f"{head} {{{'T' if q['correcta'] == 0 else 'F'}{fb}}}")
        else:
            out.append(f"{head} {{={_gift_escape(q['respuesta'])}{fb}}}")
    return "\n\n".join(out) + "\n"


def _solution(q: dict, t: dict) -> str:
    if q["tipo"] == "test":
        text = f"{LETTERS[q['correcta']]}) {q['opciones'][q['correcta']]}"
    elif q["tipo"] == "verdadero_falso":
        text = t["true"] if q["correcta"] == 0 else t["false"]
    else:
        text = q["respuesta"]
    extra = f" — {q['explicacion']}" if q["explicacion"] else ""
    page = f" ({t['page']} {q['pagina']})" if q["pagina"] else ""
    return f"{text}{extra}{page}"


def plain(questions: list[dict], t: dict, title: str, with_solutions: bool) -> str:
    lines = [title, ""]
    for i, q in enumerate(questions, start=1):
        lines.append(f"{i}. {q['enunciado']}")
        if q["tipo"] == "test":
            lines += [f"   {LETTERS[k]}) {o}" for k, o in enumerate(q["opciones"])]
        elif q["tipo"] == "verdadero_falso":
            lines.append(f"   {t['true']} / {t['false']}")
        else:
            lines.append(f"   {t['answer']}: {t['line']}")
        lines.append("")
    if with_solutions:
        lines += [t["solutions"], ""] + [f"{i}. {_solution(q, t)}" for i, q in enumerate(questions, start=1)]
    return "\n".join(lines).rstrip() + "\n"


def docx(dst: Path, questions: list[dict], t: dict, title: str, language: str, exam: bool, solutions: bool, note: str) -> None:
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()
    doc.core_properties.title = title
    doc.core_properties.author = ""
    doc.styles["Normal"].font.size = Pt(11)
    from tools.ai.salida import set_language

    set_language(doc, language)
    doc.add_heading(title, level=1)
    if exam:
        doc.add_paragraph(f"{t['name']} {t['line']}")
        for i, q in enumerate(questions, start=1):
            p = doc.add_paragraph()
            p.add_run(f"{i}. ").bold = True
            p.add_run(q["enunciado"])
            if q["tipo"] == "test":
                for k, o in enumerate(q["opciones"]):
                    doc.add_paragraph(f"{LETTERS[k]}) {o}").paragraph_format.left_indent = Pt(18)
            elif q["tipo"] == "verdadero_falso":
                doc.add_paragraph(f"☐ {t['true']}    ☐ {t['false']}").paragraph_format.left_indent = Pt(18)
            else:
                doc.add_paragraph(f"{t['answer']}: {t['line']}").paragraph_format.left_indent = Pt(18)
    if solutions:
        if exam:
            doc.add_page_break()
        doc.add_heading(t["solutions"], level=2)
        for i, q in enumerate(questions, start=1):
            doc.add_paragraph(f"{i}. {_solution(q, t)}")
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
    options = {k: getattr(o, k) for k in ("numero", "tipo", "opciones", "dificultad", "idioma")} | {"paginas": selected}
    result, hit = comun.with_cache(ctx, "generador-de-preguntas", options, lambda: make(ctx, selected, body))
    questions = result["preguntas"]
    title = t["title"].format(name=Path(inp.name).stem)
    made = comun.texts(ctx)["made"].format(model=result.get("model") or "IA")
    note = comun.note(ctx, hit)
    language = comun.output_language(o.idioma, ctx.locale)
    outputs = []
    if o.formato == "gift":
        name = derived_name(inp.name, t["suffix"], "gift.txt")
        dst = ctx.output(name)
        dst.write_text(gift(questions), encoding="utf-8")
        outputs.append({"path": str(dst), "name": name, "note": note})
        return outputs
    separate = o.soluciones == "aparte"
    if o.formato == "docx":
        name = derived_name(inp.name, t["suffix"], "docx")
        dst = ctx.output(name)
        docx(dst, questions, t, title, language, True, o.soluciones == "final", made)
        outputs.append({"path": str(dst), "name": name, "note": note})
        if separate:
            sname = derived_name(inp.name, t["sol_suffix"], "docx")
            sdst = ctx.output(sname)
            docx(sdst, questions, t, title, language, False, True, made)
            outputs.append({"path": str(sdst), "name": sname, "note": None})
    else:
        name = derived_name(inp.name, t["suffix"], "txt")
        dst = ctx.output(name)
        dst.write_text(plain(questions, t, title, o.soluciones == "final") + f"\n{made}\n", encoding="utf-8")
        outputs.append({"path": str(dst), "name": name, "note": note})
        if separate:
            sname = derived_name(inp.name, t["sol_suffix"], "txt")
            sdst = ctx.output(sname)
            sdst.write_text(t["solutions"] + "\n\n" + "\n".join(f"{i}. {_solution(q, t)}" for i, q in enumerate(questions, 1)) + "\n",
                            encoding="utf-8")
            outputs.append({"path": str(sdst), "name": sname, "note": None})
    return outputs
