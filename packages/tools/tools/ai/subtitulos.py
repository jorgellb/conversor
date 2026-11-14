"""traducir-subtitulos (7.10 y 6.3): traduce subtítulos SRT, WebVTT o ASS conservando los tiempos (D-174).

- Los subtítulos se leen y se escriben con pysubs2 (MIT). Cada subtítulo («cue») es un elemento de la lista JSON que
  se pide al modelo (`LLMTranslator`, D-132): exactamente un elemento traducido por cada uno de entrada, así que la
  traducción queda alineada con los tiempos, que no se tocan. Las líneas se vuelven a partir al ancho elegido.
- Lo que no es texto se conserva: las etiquetas de estilo del principio y del final de cada subtítulo (posición, cursiva
  de toda la línea), los comentarios y los dibujos de ASS, y los estilos de la cabecera de un ASS. Las etiquetas de en
  medio de una línea (una palabra en negrita) no se pueden llevar a la traducción y se quitan.
- Un subtítulo sin letras («♪», «...») no se manda; los repetidos se mandan una vez.
- Un audio o un vídeo pasa antes por `av.heavy`: faster-whisper hace los subtítulos con el ancho de línea elegido y
  vuelve a `ai` para traducirlos (`tools.ai.grabacion`). La transcripción cuenta como tarea pesada (como el OCR, D-124).
- Con «Desde» y «Hasta», solo se traducen los subtítulos que empiezan en ese tramo; el resto queda como estaba, así que
  unos subtítulos muy largos se pueden traducir en dos tareas pasando el resultado de la primera a la segunda.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import warnings
from dataclasses import dataclass
from pathlib import Path

from core.ai.text import CHARS_PER_TOKEN
from core.ai.translate import LLMTranslator
from core.errors import ErrorCode, ToolError
from tools.ai import comun, grabacion
from tools.base import InputFile, ToolContext, derived_name

TOOL = "traducir-subtitulos"
MAX_BYTES = 8 * 1024 * 1024  # un ASS con fuentes incrustadas puede pasar de 1 MB; una película en SRT ocupa unos 100 KB
MAX_EVENTS = 30_000
CHARS_PER_CUE = 60  # para estimar cuántos subtítulos salen de un audio antes de transcribirlo
TAG = re.compile(r"\{[^}]*\}")
LEADING = re.compile(r"^(?:\{[^}]*\})+")
TRAILING = re.compile(r"(?:\{[^}]*\})+$")
BREAK = re.compile(r"\\[Nn]|\n")
LANG_SUFFIX = re.compile(r"\.[a-z]{2,3}(?:[-_][A-Za-z]{2})?$")
DASHES = ("-", "–", "—")
TEXTS = {
    "es": {"made": "Traducción hecha con IA ({model}). Puede tener errores: revísala antes de usarla.",
           "tags": "Las etiquetas de estilo de dentro de las líneas (una palabra en cursiva o en negrita) no se conservan.",
           "kept": "Subtítulos fuera del tramo elegido sin traducir: {n}.",
           "media": "{name}: {lang}{detected}, {duration}. Cuenta como una tarea pesada por la transcripción.",
           "detected": " (detectado, {p:.0%})"},
    "en": {"made": "Translated with AI ({model}). It may contain errors: review it before using it.",
           "tags": "Style tags inside lines (a word in italics or bold) are not kept.",
           "kept": "Subtitles outside the chosen section left untranslated: {n}.",
           "media": "{name}: {lang}{detected}, {duration}. Counts as a heavy task because of the transcription.",
           "detected": " (detected, {p:.0%})"},
}


def _texts(ctx: ToolContext) -> dict[str, str]:
    return TEXTS.get(ctx.locale, TEXTS["es"])


# ——— Lectura ———

def decode(raw: bytes) -> str:
    """UTF-8 (con o sin BOM), UTF-16 con BOM o, si no, Windows-1252, la de muchos SRT antiguos en español."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def clean_vtt(text: str) -> str:
    """Sin los bloques NOTE, STYLE y REGION de WebVTT, que pysubs2 pegaría al subtítulo anterior."""
    blocks = re.split(r"\n[ \t]*\n", text.replace("\r\n", "\n").replace("\r", "\n"))
    keep = [b for b in blocks if not re.match(r"\s*(NOTE|STYLE|REGION)\b", b)]
    return "\n\n".join(keep)


def parse_text(text: str, ext: str):
    """Subtítulos de un texto, siempre con el formato de su extensión (ASS lee también SSA, su versión anterior): nunca
    se deja a pysubs2 adivinar otro formato por el contenido."""
    import pysubs2

    if ext == "vtt":
        text = clean_vtt(text)
    try:
        with warnings.catch_warnings():  # un campo mal escrito (la capa de un SSA antiguo) toma su valor por defecto
            warnings.simplefilter("ignore")
            subs = pysubs2.SSAFile.from_string(text, format_={"srt": "srt", "vtt": "vtt", "ass": "ass"}[ext])
    except Exception as exc:  # noqa: BLE001 - pysubs2 lanza varios tipos con un archivo mal formado
        raise ToolError(ErrorCode.CORRUPT_FILE, "subtítulos no válidos") from exc
    if len(subs.events) > MAX_EVENTS:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{len(subs.events)} subtítulos")
    return subs


def parse(path: Path, ext: str):
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{size} bytes")
    return parse_text(decode(path.read_bytes()), ext)


def from_cues(cues: list) -> object:
    """Subtítulos hechos a partir de la transcripción: [inicio, fin, líneas] en segundos."""
    import pysubs2

    subs = pysubs2.SSAFile()
    for start, end, lines in cues:
        subs.append(pysubs2.SSAEvent(start=int(round(start * 1000)), end=int(round(end * 1000)), text="\\N".join(lines)))
    return subs


# ——— Texto de cada subtítulo ———

@dataclass
class Item:
    index: int
    prefix: str
    inner: str
    suffix: str
    source: str
    dialogue: bool
    inner_tags: bool


def split_markup(text: str) -> tuple[str, str, str]:
    lead = LEADING.match(text)
    prefix = lead.group(0) if lead else ""
    rest = text[len(prefix):]
    trail = TRAILING.search(rest)
    suffix = trail.group(0) if trail else ""
    return prefix, rest[:len(rest) - len(suffix)], suffix


def plain_lines(inner: str) -> list[str]:
    text = TAG.sub("", inner).replace("\\h", " ")
    return [" ".join(line.split()) for line in BREAK.split(text) if line.strip()]


def items_of(subs, start_ms: int = 0, end_ms: int | None = None) -> tuple[list[Item], int]:
    """Los subtítulos que hay que traducir (con letras y dentro del tramo) y cuántos con texto quedan fuera del tramo."""
    out: list[Item] = []
    outside = 0
    for i, ev in enumerate(subs.events):
        if ev.is_comment or ev.is_drawing:
            continue
        prefix, inner, suffix = split_markup(ev.text)
        lines = plain_lines(inner)
        if not lines or not any(ch.isalpha() for ch in "".join(lines)):
            continue
        if ev.start < start_ms or (end_ms is not None and ev.start >= end_ms):
            outside += 1
            continue
        dialogue = len(lines) > 1 and all(line.startswith(DASHES) for line in lines)
        out.append(Item(i, prefix, inner, suffix, "\n".join(lines) if dialogue else " ".join(lines), dialogue,
                        bool(TAG.search(inner))))
    return out, outside


def _balance(words: list[str], width: int) -> list[str] | None:
    best: tuple[int, int] | None = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if len(a) <= width and len(b) <= width and (best is None or abs(len(a) - len(b)) < best[0]):
            best = (abs(len(a) - len(b)), i)
    return None if best is None else [" ".join(words[:best[1]]), " ".join(words[best[1]:])]


def wrap(text: str, width: int) -> list[str]:
    """Una línea si cabe; si no, dos equilibradas; si una traducción larga no cabe en dos, las que hagan falta (nunca
    se corta texto ni se cambian los tiempos)."""
    words = text.split()
    if not words:
        return []
    joined = " ".join(words)
    if len(joined) <= width:
        return [joined]
    two = _balance(words, width)
    if two:
        return two
    lines, current = [], ""
    for w in words:
        if current and len(current) + 1 + len(w) > width:
            lines.append(current)
            current = w
        else:
            current = f"{current} {w}".strip()
    if current:
        lines.append(current)
    return lines


def safe(text: str) -> str:
    """Sin llaves ni barras invertidas, que ASS leería como etiquetas o saltos."""
    return text.replace("{", "(").replace("}", ")").replace("\\", "/")


def render(translation: str, dialogue: bool, width: int) -> list[str]:
    text = safe(translation).strip()
    if dialogue:
        parts = [p.strip() for p in text.split("\n") if p.strip()]
        if len(parts) > 1:
            return [line for part in parts for line in wrap(part, width)]
    return wrap(" ".join(text.split()), width)


def apply(subs, items: list[Item], translated: dict[str, str], width: int, bilingual: bool) -> None:
    for item in items:
        ev = subs.events[item.index]
        lines = render(translated.get(item.source) or item.source, item.dialogue, width)
        body = "\\N".join(lines)
        if bilingual:
            original = item.inner.strip() or "\\N".join(wrap(item.source, width))
            body = f"{original}\\N{body}"
        ev.text = f"{item.prefix}{body}{item.suffix}"


# ——— Peticiones ———

def estimate_requests(ctx: ToolContext, chars: int) -> int:
    """Peticiones para traducir unos subtítulos de `chars` caracteres (antes de transcribir un audio)."""
    translator = LLMTranslator(ctx.ai)
    tokens = chars / CHARS_PER_TOKEN + 5 * (chars / CHARS_PER_CUE)
    return max(1, math.ceil(tokens / translator.batch_tokens))


def make(ctx: ToolContext, sources: list[str], source_lang: str | None) -> dict:
    o = ctx.options
    translator = LLMTranslator(ctx.ai)
    grabacion.check_requests(ctx, len(translator.plan(sources)))
    keep = [line.strip() for line in (o.glosario or "").splitlines() if line.strip()][:50]
    out = translator.translate(sources, o.destino, source_lang, keep, progress=lambda f: ctx.report(0.8 + 0.18 * f, None))
    return {"traducciones": out, "model": (ctx.ai.models_used or [""])[-1]}


# ——— Etapas ———

def transcript_params(ctx: ToolContext) -> dict:
    o = ctx.options
    return {"idioma": o.origen, "precision": o.precision, "desde": o.desde, "hasta": o.hasta, "ancho": o.caracteres_por_linea}


def _transcribe(ctx: ToolContext) -> None:
    from tools.av import transcribe as tr

    o = ctx.options

    def build(result) -> dict:
        return {"cues": [[c.start, c.end, c.lines] for c in tr.cues(result.segments, max_chars=o.caracteres_por_linea)]}

    grabacion.transcribe_stage(ctx, TOOL, transcript_params(ctx), lambda chars: estimate_requests(ctx, chars), build, words=True)


def output_name(inp: InputFile, destino: str, ext: str) -> str:
    stem = Path(inp.name).stem
    stem = LANG_SUFFIX.sub("", stem) or stem
    return derived_name(f"{stem}.x", f".{destino}", ext)


def _translate(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    t = _texts(ctx)
    inp = ctx.inputs[0]
    notes: list[str] = []
    source_lang = None if o.origen == "auto" else o.origen
    if grabacion.is_media(inp):
        payload = grabacion.load(ctx, inp, TOOL, transcript_params(ctx))
        if payload is None:
            raise ToolError(ErrorCode.INTERNAL, "transcripción no encontrada")
        detected = payload.get("language") or ""
        if o.origen == "auto" and detected == o.destino:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "ai_same_language")
        source_lang = source_lang or (detected or None)
        subs = from_cues(payload["cues"])
        items, outside = items_of(subs)
        fmt = "srt" if o.salida == "mismo" else o.salida
        lang = grabacion.language_label(detected, ctx.locale)
        notes += [*payload.get("notes", []), t["media"].format(
            name=inp.name, lang=lang, duration=grabacion.clock(payload.get("duration", 0)),
            detected=t["detected"].format(p=payload.get("probability", 0)) if o.origen == "auto" else "")]
    else:
        start, end = grabacion.span_of(o)
        subs = parse(inp.path, inp.ext)
        items, outside = items_of(subs, int(start * 1000), int(end * 1000) if end is not None else None)
        fmt = inp.ext if o.salida == "mismo" else o.salida
        if outside:
            notes.append(t["kept"].format(n=outside))
    if not items:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "subs_empty")
    if any(item.inner_tags for item in items):
        notes.append(t["tags"])
    sources = list(dict.fromkeys(item.source for item in items))
    digest = hashlib.sha256(json.dumps(sources, ensure_ascii=False).encode()).hexdigest()
    options = {"destino": o.destino, "origen": source_lang or "auto", "glosario": (o.glosario or "").strip(), "textos": digest}
    result, hit = comun.with_cache(ctx, TOOL, options, lambda: make(ctx, sources, source_lang))
    translated = dict(zip(sources, result["traducciones"]))
    apply(subs, items, translated, o.caracteres_por_linea, o.bilingue)
    name = output_name(inp, o.destino, fmt)
    dst = ctx.output(name)
    dst.write_text(subs.to_string(fmt), encoding="utf-8")
    note = " ".join([comun.note(ctx, hit), t["made"].format(model=result.get("model") or "IA"), *notes])
    return [{"path": str(dst), "name": name, "note": note}]


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    if o.origen != "auto" and o.origen == o.destino:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "ai_same_language")
    inp = ctx.inputs[0]
    if ctx.stage == "transcribir":
        _transcribe(ctx)
    if ctx.stage is None and grabacion.is_media(inp) and grabacion.load(ctx, inp, TOOL, transcript_params(ctx)) is None:
        ctx.charge("heavy")
        ctx.handoff("av", "transcribir", grabacion.message("transcribe", ctx.locale), queue="av.heavy")
    return _translate(ctx)
