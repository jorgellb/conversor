"""Texto leído con OCR de una imagen que pasa de una cola a otra (F3, lote C): `workerocr` o `workerconvert` lo leen,
lo guardan en `document_texts` (del propietario y con la caducidad de sus archivos, 6.4 y 9.4) y `workerai` lo usa sin
volver a leer la imagen (D-162).

La clave no es solo el SHA-256 de la imagen: incluye la herramienta y los idiomas del OCR, para que el texto que ha
leído una herramienta con unos idiomas no lo reutilice otra con otros.
"""
from __future__ import annotations

import hashlib

from core.ai.store import texts_get, texts_put
from core.db import session_scope
from tools.base import InputFile, ToolContext

EXTRACTOR = "tesseract-imagen"
MIN_CHARS = 8  # letras o cifras: con menos, el OCR solo ha visto ruido y no se gasta ninguna petición


def meaningful(text: str) -> bool:
    return sum(ch.isalnum() for ch in text) >= MIN_CHARS


def key(inp: InputFile, tool: str, languages: list[str]) -> str:
    return hashlib.sha256(f"{inp.sha256}|{tool}|{'+'.join(languages)}".encode()).hexdigest()


def load(ctx: ToolContext, inp: InputFile, tool: str, languages: list[str]) -> str | None:
    with session_scope() as s:
        row = texts_get(s, ctx.owner[0], ctx.owner[1], key(inp, tool, languages), ctx.now())
        return "\n\n".join(row.pages) if row is not None else None


def save(ctx: ToolContext, inp: InputFile, tool: str, languages: list[str], text: str) -> None:
    with session_scope() as s:
        texts_put(s, ctx.owner[0], ctx.owner[1], key(inp, tool, languages), [text], EXTRACTOR, ctx.expires_at)
