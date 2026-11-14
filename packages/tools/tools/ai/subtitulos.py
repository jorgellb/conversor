"""traducir-subtitulos (7.10 y 6.3): traduce subtítulos SRT, WebVTT o ASS conservando los tiempos (D-174).

- Los subtítulos se leen y se escriben con pysubs2 (MIT). Cada subtítulo («cue») es un elemento de la lista JSON que
  se pide al modelo (`LLMTranslator`, D-132): exactamente un elemento traducido por cada uno de entrada, así que la
  traducción queda alineada con los tiempos, que no se tocan. Las líneas se vuelven a partir al ancho elegido.
- Lo que no es texto se conserva: las etiquetas de estilo del principio y del final de cada subtítulo (posición, cursiva
  de toda la línea), los comentarios y los dibujos de ASS, y los estilos de la cabecera de un ASS. Las etiquetas de en
  medio de una línea (una palabra en negrita) no se pueden llevar a la traducción y se quitan, y con ellas las del
  principio que esas cierran o cambian (`<i>Titanic</i> es…` no pasa a ser una línea entera en cursiva). Los ajustes
  de posición de WebVTT y las voces (`<v Ana>`) no se conservan (pysubs2 no los lee) y el resultado lo avisa.
- Las etiquetas se recorren sin expresiones regulares con retroceso (un subtítulo con miles de `{}` no bloquea el
  trabajador) y un subtítulo no puede pasar de 2.000 caracteres de texto.
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
MAX_CUE_CHARS = 2_000  # texto de un subtítulo sin etiquetas: uno normal tiene menos de 100
CHARS_PER_CUE = 60  # para estimar cuántos subtítulos salen de un audio antes de transcribirlo
# Etiquetas ASS que solo colocan el subtítulo: se conservan aunque se quiten las de estilo.
POSITIONAL = ("an", "a", "pos", "move", "org", "fad", "fade", "clip", "iclip", "q")
# Nombres de las etiquetas ASS, los más largos primero (`\fscx` antes que `\fs`, `\fs` antes que `\f…`).
TAG_NAMES = tuple(sorted(("pos", "move", "org", "fade", "fad", "iclip", "clip", "an", "a", "alpha", "fscx", "fscy", "fsp", "fs",
                          "fn", "frx", "fry", "frz", "fr", "fax", "fay", "fe", "blur", "bord", "xbord", "ybord", "shad",
                          "xshad", "yshad", "be", "kf", "ko", "k", "K", "q", "r", "p", "pbo", "i", "b", "u", "s", "t", "c",
                          "1c", "2c", "3c", "4c", "1a", "2a", "3a", "4a"), key=len, reverse=True))
VTT_SETTINGS = re.compile(r"-->[ \t]*\S+[ \t]+\S", re.MULTILINE)
VTT_VOICE = re.compile(r"<v[ .]")
BREAK = re.compile(r"\\[Nn]|\n")
LANG_SUFFIX = re.compile(r"\.[a-z]{2,3}(?:[-_][A-Za-z]{2})?$")
DASHES = ("-", "–", "—")
TEXTS = {
    "es": {"made": "Traducción hecha con IA ({model}). Puede tener errores: revísala antes de usarla.",
           "tags": "Las etiquetas de estilo de dentro de las líneas (una palabra en cursiva o en negrita) no se conservan.",
           "vtt": "Los ajustes de posición de WebVTT (align, position, line) y los nombres de quien habla (<v>) no se conservan.",
           "kept": "Subtítulos fuera del tramo elegido sin traducir: {n}.",
           "media": "{name}: {lang}{detected}, {duration}. Cuenta como una tarea pesada por la transcripción.",
           "detected": " (detectado, {p:.0%})"},
    "en": {"made": "Translated with AI ({model}). It may contain errors: review it before using it.",
           "tags": "Style tags inside lines (a word in italics or bold) are not kept.",
           "vtt": "WebVTT position settings (align, position, line) and speaker names (<v>) are not kept.",
           "kept": "Subtitles outside the chosen section left untranslated: {n}.",
           "media": "{name}: {lang}{detected}, {duration}. Counts as a heavy task because of the transcription.",
           "detected": " (detected, {p:.0%})"},
}


def _texts(ctx: ToolContext) -> dict[str, str]:
    return TEXTS.get(ctx.locale, TEXTS["es"])


# ——— Lectura ———

def decode(raw: bytes) -> str:
    """UTF-8 (con o sin BOM), UTF-16 o UTF-32 con BOM o, si no, Windows-1252, la de muchos SRT antiguos en español."""
    if raw.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return raw.decode("utf-32", errors="replace")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
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


def read(path: Path) -> str:
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{size} bytes")
    return decode(path.read_bytes())


def parse(path: Path, ext: str):
    return parse_text(read(path), ext)


def vtt_extras(text: str) -> bool:
    """Un WebVTT con ajustes de posición en la línea de tiempos o con voces (`<v Ana>`), que pysubs2 descarta."""
    return bool(VTT_SETTINGS.search(text) or VTT_VOICE.search(text))


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
    raw_prefix: str = ""  # las del original sin quitar nada (la versión bilingüe conserva la línea original tal cual)
    raw_suffix: str = ""


def blocks(text: str) -> list[tuple[int, int]]:
    """Posiciones [inicio, fin) de los bloques `{…}`, en tiempo lineal (como libass: el bloque acaba en la primera `}`;
    una `{` sin cerrar es texto, y entonces ninguna de las siguientes se cierra)."""
    out: list[tuple[int, int]] = []
    pos = 0
    while True:
        start = text.find("{", pos)
        if start < 0:
            return out
        end = text.find("}", start + 1)
        if end < 0:
            return out
        out.append((start, end + 1))
        pos = end + 1


def strip_tags(text: str) -> str:
    parts, pos = [], 0
    for a, b in blocks(text):
        parts.append(text[pos:a])
        pos = b
    parts.append(text[pos:])
    return "".join(parts)


def _leading_end(text: str) -> int:
    pos = 0
    while pos < len(text) and text[pos] == "{":
        end = text.find("}", pos + 1)
        if end < 0:
            break
        pos = end + 1
    return pos


def _trailing_start(text: str, floor: int) -> int:
    """Inicio de los bloques `{…}` seguidos con los que acaba el texto (sin pasar de `floor`), recorriendo hacia atrás."""
    end = len(text)
    while end > floor and text[end - 1] == "}":
        start = text.rfind("{", floor, end - 1)
        if start < 0 or text.find("}", start + 1, end - 1) >= 0:
            break
        end = start
    return end


def tag_names(block: str) -> list[tuple[str, str]]:
    """Las etiquetas de un bloque `{\\an8\\i1}` como (nombre, etiqueta entera). Las barras dentro de paréntesis son
    de la misma etiqueta (`\\t(0,500,\\fs20)`); el texto antes de la primera barra es un comentario y no cuenta."""
    body = block[1:-1]
    starts: list[int] = []
    depth = 0
    for k, ch in enumerate(body):
        if ch == "\\" and depth == 0:
            starts.append(k + 1)
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
    raws = [body[a:(starts[n + 1] - 1 if n + 1 < len(starts) else len(body))] for n, a in enumerate(starts)]
    out = []
    for raw in raws:
        name = next((n for n in TAG_NAMES if raw.startswith(n)), raw[:1])
        out.append((name, "\\" + raw))
    return out


def _keep_tags(markup: str, inner_names: set[str]) -> str:
    """Los bloques del principio o del final sin las etiquetas que las de dentro de la línea cierran o cambian: así
    `{\\i1}Titanic{\\i0} es…` no deja en cursiva toda la traducción. Las de posición se quedan siempre."""
    if not inner_names:
        return markup
    kept = []
    for a, b in blocks(markup):
        block = markup[a:b]
        tags = tag_names(block)
        if not tags:  # un comentario `{nota}`
            kept.append(block)
            continue
        keep = [t for n, t in tags if n in POSITIONAL or (n not in inner_names and "r" not in inner_names)]
        if keep:
            kept.append("{" + "".join(keep) + "}")
    return "".join(kept)


def split_markup(text: str) -> tuple[str, str, str]:
    """(etiquetas del principio, texto, etiquetas del final) tal como están, en tiempo lineal."""
    head = _leading_end(text)
    tail = _trailing_start(text, head)
    return text[:head], text[head:tail], text[tail:]


def kept_markup(prefix: str, inner: str, suffix: str) -> tuple[str, str]:
    """Las etiquetas del principio y del final que siguen valiendo para la traducción, que no lleva las de dentro."""
    names = {n for a, b in blocks(inner) for n, _ in tag_names(inner[a:b])}
    return _keep_tags(prefix, names), _keep_tags(suffix, names)


def plain_lines(inner: str) -> list[str]:
    text = strip_tags(inner).replace("\\h", " ")
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
        size = sum(len(line) for line in lines)
        if size > MAX_CUE_CHARS:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"subs_cue:{size}>{MAX_CUE_CHARS}")
        if ev.start < start_ms or (end_ms is not None and ev.start >= end_ms):
            outside += 1
            continue
        dialogue = len(lines) > 1 and all(line.startswith(DASHES) for line in lines)
        kept_prefix, kept_suffix = kept_markup(prefix, inner, suffix)
        out.append(Item(i, kept_prefix, inner, kept_suffix, "\n".join(lines) if dialogue else " ".join(lines), dialogue,
                        bool(blocks(inner)), prefix, suffix))
    return out, outside


def _balance(words: list[str], width: int) -> list[str] | None:
    """Dos líneas lo más parecidas posible que quepan en el ancho (en tiempo lineal: longitudes acumuladas)."""
    total = sum(len(w) for w in words) + len(words) - 1
    best: tuple[int, int] | None = None
    a = -1
    for i in range(1, len(words)):
        a += len(words[i - 1]) + 1  # longitud de las i primeras palabras unidas por espacios
        b = total - a - 1
        if a <= width and b <= width and (best is None or abs(a - b) < best[0]):
            best = (abs(a - b), i)
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
            # El original con todas sus etiquetas; `\r` vuelve al estilo de la línea para que una negrita sin cerrar
            # no pase a la traducción, que lleva las suyas (la posición, `\an` o `\pos`, vale para el subtítulo entero).
            ev.text = f"{item.raw_prefix}{original}{item.raw_suffix}\\N{{\\r}}{item.prefix}{body}{item.suffix}"
        else:
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
        text = read(inp.path)
        subs = parse_text(text, inp.ext)
        if inp.ext == "vtt" and vtt_extras(text):
            notes.append(t["vtt"])
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
