"""Subtítulos (7.13, F6-E, D-217): srt-a-vtt, vtt-a-srt y ass-a-srt.

pysubs2 (MIT) solo lee (tools/subs.py, la misma lectura que traducir-subtitulos); la salida se escribe aquí para que salga
ordenada por tiempo y con las etiquetas de estilo bien pasadas: negrita, cursiva, subrayado y tachado de ASS
(`{\\b1}…{\\b0}`, también los del estilo de la línea) se convierten en `<b>`, `<i>`, `<u>` y `<s>`; el resto de etiquetas
(posición, color, karaoke) se quita. Los comentarios y los dibujos vectoriales de ASS (`{\\p1}`) no son texto y no salen.
"""
from __future__ import annotations

import html
import re

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.pdf.common import with_batch_zip
from tools.subs import parse, read, vtt_extras

TARGET = {"srt-a-vtt": ("srt", "vtt"), "vtt-a-srt": ("vtt", "srt"), "ass-a-srt": ("ass", "srt")}
OVERRIDE = re.compile(r"\{([^}]*)\}")
TOGGLE = re.compile(r"\\([biusp])(\d+)")
TAG_FOR = {"b": "b", "i": "i", "u": "u", "s": "s"}

NOTES = {
    "es": {"vtt": "Los ajustes de posición de WebVTT (align, position, line) y los nombres de quien habla (<v>) no existen en "
                  "SRT y no se conservan.",
           "ass": "La posición, los colores, las fuentes y los efectos de ASS no existen en SRT: se conservan el texto, los tiempos, "
                  "la negrita, la cursiva, el subrayado y el tachado.",
           "skipped": "{n} comentario(s) o dibujo(s) de ASS no se han incluido.", "count": "{n} subtítulos."},
    "en": {"vtt": "WebVTT position settings (align, position, line) and speaker names (<v>) do not exist in SRT and are not kept.",
           "ass": "ASS position, colours, fonts and effects do not exist in SRT: text, timings, bold, italics, underline and "
                  "strikethrough are kept.",
           "skipped": "{n} ASS comment(s) or drawing(s) were not included.", "count": "{n} subtitles."},
}


def _stamp(ms: int, sep: str) -> str:
    ms = max(0, int(ms))
    h, rest = divmod(ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def cue_text(event, style, keep_tags: bool, escape: bool = False) -> str:
    """El texto de un evento de pysubs2 con las etiquetas de estilo pasadas a HTML (o quitadas) y sus saltos de línea."""
    state = {k: bool(getattr(style, attr, False)) for k, attr in (("b", "bold"), ("i", "italic"), ("u", "underline"), ("s", "strikeout"))}
    opened: list[str] = []
    out: list[str] = []

    def sync(target: dict) -> None:
        # Cierra lo que deja de valer (y lo que se abrió después, para que el HTML quede bien anidado) y abre lo nuevo.
        while opened and not all(target[t] for t in opened):
            out.append(f"</{opened.pop()}>")
        for tag in "bius":
            if target[tag] and tag not in opened:
                out.append(f"<{tag}>")
                opened.append(tag)

    if keep_tags:
        sync(state)
    pos = 0
    text = event.text
    for m in OVERRIDE.finditer(text):
        out.append(_plain(text[pos:m.start()], escape))
        pos = m.end()
        for name, value in TOGGLE.findall(m.group(1)):
            if name in TAG_FOR:
                state[name] = int(value) > 0  # \b700 también es negrita
        if keep_tags:
            sync(state)
    out.append(_plain(text[pos:], escape))
    while keep_tags and opened:
        out.append(f"</{opened.pop()}>")
    result = "".join(out)
    result = re.sub(r"<(\w)></\1>", "", result)
    lines = [line.strip() for line in result.split("\n")]
    return "\n".join(line for line in lines if line)


def _plain(fragment: str, escape: bool) -> str:
    """Saltos de línea de ASS a reales; en WebVTT, «&», «<» y «>» como entidades (lo exige el formato; en SRT, no: muchos
    reproductores enseñarían «&amp;» tal cual)."""
    text = fragment.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", "\u00a0")
    return html.escape(text, quote=False) if escape else text


def _is_drawing(event) -> bool:
    return bool(re.search(r"\\p[1-9]", event.text))


def write(subs, target: str, keep_tags: bool) -> tuple[str, int, int]:
    events = [e for e in subs.events if not e.is_comment and not _is_drawing(e)]
    skipped = len(subs.events) - len(events)
    events.sort(key=lambda e: (e.start, e.end))
    blocks = []
    sep = "," if target == "srt" else "."
    for event in events:
        text = cue_text(event, subs.styles.get(event.style), keep_tags, escape=target == "vtt")
        if not text:
            continue
        end = max(event.end, event.start + 1)
        blocks.append((_stamp(event.start, sep), _stamp(end, sep), text))
    if target == "srt":
        body = "\n".join(f"{n}\n{a} --> {b}\n{t}\n" for n, (a, b, t) in enumerate(blocks, 1))
    else:
        body = "WEBVTT\n\n" + "\n".join(f"{n}\n{a} --> {b}\n{t}\n" for n, (a, b, t) in enumerate(blocks, 1))
    return body, len(blocks), skipped


def run(ctx: ToolContext) -> list[dict]:
    t = NOTES.get(ctx.locale, NOTES["es"])
    source, target = TARGET[ctx.tool]
    keep = ctx.options.etiquetas == "conservar"
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        text = read(inp.path)
        subs = parse(inp.path, source)
        body, count, skipped = write(subs, target, keep)
        if not count:
            raise ToolError(ErrorCode.CORRUPT_FILE, "subtítulos no válidos")
        notes = [t["count"].format(n=count)]
        if source == "vtt" and vtt_extras(text):
            notes.append(t["vtt"])
        if source == "ass":
            notes.append(t["ass"])
            if skipped:
                notes.append(t["skipped"].format(n=skipped))
        name = derived_name(inp.name, "", target)
        dst = ctx.output(name)
        dst.write_text(body, encoding="utf-8", newline="\r\n" if target == "srt" else "\n")
        outputs.append({"path": str(dst), "name": name, "note": " ".join(notes)})
    return with_batch_zip(ctx, outputs, f"{ctx.tool}.zip")
