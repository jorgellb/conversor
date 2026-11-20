"""Lectura de subtítulos SRT, WebVTT y ASS/SSA con pysubs2 (MIT), compartida por traducir-subtitulos (F3-E) y las
conversiones de F6-E. Sin dependencias de IA: la importan `workerai` y `workerutils`."""
from __future__ import annotations

import re
import warnings
from pathlib import Path

from core.errors import ErrorCode, ToolError

MAX_BYTES = 8 * 1024 * 1024  # un ASS con fuentes incrustadas puede pasar de 1 MB; una película en SRT ocupa unos 100 KB
MAX_EVENTS = 30_000
VTT_SETTINGS = re.compile(r"-->[ \t]*\S+[ \t]+\S", re.MULTILINE)
VTT_VOICE = re.compile(r"<v[ .]")


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


VTT_INLINE_TIME = re.compile(r"<\d{1,2}:\d{2}(?::\d{2})?\.\d{3}>")
VTT_CLASS = re.compile(r"</?c(?:\.[\w.-]+)?>")


def clean_vtt(text: str) -> str:
    """Sin los bloques NOTE, STYLE y REGION de WebVTT, que pysubs2 pegaría al subtítulo anterior, ni las marcas de tiempo
    por palabra y las clases `<c>` de los subtítulos automáticos de YouTube (pysubs2 tomaría `<00:00:00.539>` por una línea
    de tiempos y perdería frases)."""
    blocks = re.split(r"\n[ \t]*\n", text.replace("\r\n", "\n").replace("\r", "\n"))
    keep = [b for b in blocks if not re.match(r"\s*(NOTE|STYLE|REGION)\b", b)]
    cleaned = []
    for block in keep:
        lines = block.split("\n")
        cleaned.append("\n".join(VTT_CLASS.sub("", VTT_INLINE_TIME.sub("", line)) if "-->" not in line else line for line in lines))
    return "\n\n".join(cleaned)


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
