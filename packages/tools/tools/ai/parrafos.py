"""Párrafos y títulos a partir del texto de una página de PDF (pypdfium2 da líneas sueltas): la «maquetación
simplificada» de traducir-pdf (7.6). Une las líneas de un mismo párrafo (también las palabras partidas con guion) y marca
como título una línea corta, sola y sin punto final que va en mayúsculas o numerada."""
from __future__ import annotations

import re
import statistics

END = re.compile(r"[.!?…:;»”\")]\s*$")
BULLET = re.compile(r"^\s*(?:[-•–·*]|\d+[.)]|[a-z][.)])\s+")
NUMBERED_TITLE = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?|[IVXLC]+\.|cap[ií]tulo\s+\w+|chapter\s+\w+)\s+\S", re.I)


def _is_title(line: str) -> bool:
    words = line.split()
    if not words or len(line) > 80 or END.search(line) or line.endswith(","):
        return False
    letters = [c for c in line if c.isalpha()]
    upper = bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8 and len(letters) > 3
    return upper or bool(NUMBERED_TITLE.match(line)) and len(words) <= 12


def paragraphs(text: str) -> list[tuple[str, str]]:
    """[(«t» título o «p» párrafo, texto)] en orden."""
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    long_lines = [len(ln) for ln in lines if len(ln) > 30]
    width = statistics.median(long_lines) if long_lines else 80
    out: list[tuple[str, str]] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            joined = ""
            for part in buf:
                if joined.endswith("-") and part[:1].islower():
                    joined = joined[:-1] + part  # palabra partida al final de la línea
                else:
                    joined = f"{joined} {part}".strip()
            out.append(("p", joined))
            buf.clear()

    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            flush()
            continue
        if _is_title(line) and (not buf or END.search(buf[-1]) or len(buf[-1]) < 0.85 * width):
            flush()
            out.append(("t", line))
            continue
        if BULLET.match(line):
            flush()
        elif buf and END.search(buf[-1]) and len(buf[-1]) < 0.85 * width:
            flush()
        buf.append(line)
    flush()
    return out
