"""Fragmentos de un documento para la búsqueda de chat-pdf (6.5), en `document_chunks` con pgvector.

Los fragmentos son cortos (el modelo de embeddings solo mira unos 128 tokens) y van por frases dentro de cada página;
al responder se añaden los vecinos de cada fragmento encontrado para dar más contexto al modelo.
"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.ai.embeddings import literal

TARGET = 450  # caracteres por fragmento (unos 110-130 tokens del modelo de embeddings)
LIMIT = 700


def passages(pages: dict[int, str]) -> list[tuple[int, str]]:
    """(página, texto) en orden; cada fragmento queda dentro de su página."""
    out: list[tuple[int, str]] = []
    for page, body in sorted(pages.items()):
        clean = re.sub(r"[ \t]+", " ", body).strip()
        if not clean:
            continue
        sentences = [s for s in re.split(r"(?<=[.!?…:;])\s+|\n{2,}", clean) if s.strip()]
        buf = ""
        for s in sentences:
            s = s.strip()
            while len(s) > LIMIT:  # sin puntos (tablas, listas): se corta a la fuerza
                if buf:
                    out.append((page, buf))
                    buf = ""
                out.append((page, s[:LIMIT]))
                s = s[LIMIT:]
            if buf and len(buf) + len(s) + 1 > TARGET:
                out.append((page, buf))
                buf = s
            else:
                buf = f"{buf} {s}".strip()
        if buf:
            out.append((page, buf))
    return out


PER_PAGE = 1000  # chunk_index = página × 1000 + orden dentro de la página


def present_pages(session: Session, owner_type: str, owner_id: str, sha256: str) -> set[int]:
    return set(session.execute(text("SELECT DISTINCT page FROM document_chunks WHERE owner_type=:t AND owner_id=:o AND sha256=:s"),
                               {"t": owner_type, "o": owner_id, "s": sha256}).scalars().all())


def add(session: Session, owner_type: str, owner_id: str, sha256: str, items: list[tuple[int, str]],
        vectors: list[list[float]], expires_at: datetime) -> int:
    """Añade los fragmentos de páginas que aún no estaban (otra preparación del mismo documento con otro rango)."""
    seen: dict[int, int] = {}
    rows = []
    for (page, body), vec in zip(items, vectors):
        n = seen.get(page, 0)
        seen[page] = n + 1
        rows.append({"t": owner_type, "o": owner_id, "s": sha256, "p": page, "i": page * PER_PAGE + min(n, PER_PAGE - 1),
                     "x": body, "e": literal(vec), "exp": expires_at})
    if rows:
        session.execute(text(
            "INSERT INTO document_chunks (owner_type, owner_id, sha256, page, chunk_index, text, embedding, expires_at) "
            "VALUES (:t, :o, :s, :p, :i, :x, CAST(:e AS vector), :exp)"), rows)
        session.execute(text("UPDATE document_chunks SET expires_at = GREATEST(expires_at, :exp) "
                             "WHERE owner_type=:t AND owner_id=:o AND sha256=:s"),
                        {"t": owner_type, "o": owner_id, "s": sha256, "exp": expires_at})
    return len(rows)


def count(session: Session, owner_type: str, owner_id: str, sha256: str, pages: list[int] | None = None) -> int:
    filt = " AND page = ANY(:pages)" if pages else ""
    return int(session.execute(text("SELECT count(*) FROM document_chunks WHERE owner_type=:t AND owner_id=:o AND sha256=:s" + filt),
                               {"t": owner_type, "o": owner_id, "s": sha256, "pages": pages or []}).scalar() or 0)


def search(session: Session, owner_type: str, owner_id: str, sha256: str, vector: list[float], k: int = 8,
           pages: list[int] | None = None) -> list[dict]:
    """Los `k` fragmentos más cercanos (distancia del coseno) y sus vecinos, en el orden del documento."""
    filt = " AND page = ANY(:pages)" if pages else ""
    params = {"t": owner_type, "o": owner_id, "s": sha256, "q": literal(vector), "k": k, "pages": pages or []}
    hits = session.execute(text(
        "SELECT chunk_index FROM document_chunks WHERE owner_type=:t AND owner_id=:o AND sha256=:s" + filt +
        " ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"), params).scalars().all()
    if not hits:
        return []
    wanted = sorted({j for i in hits for j in (i - 1, i, i + 1) if j >= 0})
    rows = session.execute(text(
        "SELECT chunk_index, page, text FROM document_chunks WHERE owner_type=:t AND owner_id=:o AND sha256=:s "
        "AND chunk_index = ANY(:w) ORDER BY chunk_index"), {**params, "w": wanted}).all()
    return [{"index": r.chunk_index, "page": r.page, "text": r.text, "hit": r.chunk_index in hits} for r in rows]
