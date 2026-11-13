"""Troceado por tokens del modelo elegido (6.3) y lectura tolerante de JSON (6.5)."""
from __future__ import annotations

import json
import math
import re

# Estimación prudente de tokens por carácter para español e inglés (los tokenizadores dan de 3,5 a 4,5 caracteres por
# token en prosa): con 3 por token, un bloque no se pasa del contexto aunque el texto tenga cifras o palabras raras.
CHARS_PER_TOKEN = 3.0


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN) + 1


def input_budget(context_length: int, max_output: int, overhead: int = 600) -> int:
    """Tokens de documento que caben en una petición: el contexto menos la salida y las instrucciones."""
    return max(500, context_length - max_output - overhead)


def split_tokens(text: str, budget: int) -> list[str]:
    """Bloques de como mucho `budget` tokens, cortados por párrafos y, si hace falta, por frases."""
    limit = max(200, int(budget * CHARS_PER_TOKEN))
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        if len(para) <= limit:
            pieces.append(para)
            continue
        sentences = re.split(r"(?<=[.!?…])\s+", para)
        buf = ""
        for s in sentences:
            while len(s) > limit:  # una «frase» sin puntos (tablas, listas): se corta a la fuerza
                pieces.append(s[:limit])
                s = s[limit:]
            if len(buf) + len(s) + 1 > limit and buf:
                pieces.append(buf)
                buf = s
            else:
                buf = f"{buf} {s}".strip()
        if buf:
            pieces.append(buf)
    blocks: list[str] = []
    buf = ""
    for p in pieces:
        if buf and len(buf) + len(p) + 2 > limit:
            blocks.append(buf)
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        blocks.append(buf)
    return blocks


def parse_json(text: str):
    """JSON de una respuesta: tal cual, dentro de ```json … ``` o el primer objeto o lista que aparezca."""
    text = text.strip()
    for candidate in (text, *re.findall(r"```(?:json)?\s*(.*?)```", text, re.S)):
        try:
            return json.loads(candidate)
        except (ValueError, TypeError):
            pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if 0 <= start < end:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                continue
    raise ValueError("la respuesta no contiene JSON válido")
