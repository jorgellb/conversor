"""Lo que se guarda de los documentos y de las respuestas, siempre de un solo propietario (6.5 y 9.4)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.models import AiCache, AiConsent, DocumentText

PROMPT_VERSION = "1"  # cambia si cambian las instrucciones: una respuesta guardada con otras ya no vale


def cache_key(owner_type: str, owner_id: str, tool: str, document: str, options: dict, locale: str, extra: str = "") -> str:
    material = json.dumps([owner_type, owner_id, tool, document, options, locale, extra, PROMPT_VERSION],
                          sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()


def cache_get(session: Session, key: str, owner_type: str, owner_id: str, now: datetime) -> dict | None:
    row = session.get(AiCache, key)
    # La clave ya incluye al propietario; se comprueba también la fila por si acaso.
    if row is None or row.owner_type != owner_type or row.owner_id != owner_id or row.expires_at <= now:
        return None
    return row.result


def cache_put(session: Session, key: str, owner_type: str, owner_id: str, result: dict, expires_at: datetime) -> None:
    stmt = insert(AiCache).values(key=key, owner_type=owner_type, owner_id=owner_id, result=result, expires_at=expires_at)
    session.execute(stmt.on_conflict_do_update(index_elements=["key"], set_={"result": result, "expires_at": expires_at}))


def texts_get(session: Session, owner_type: str, owner_id: str, sha256: str, now: datetime) -> DocumentText | None:
    row = session.get(DocumentText, (owner_type, owner_id, sha256))
    return row if row is not None and row.expires_at > now else None


def texts_put(session: Session, owner_type: str, owner_id: str, sha256: str, pages: list, extractor: str, expires_at: datetime) -> None:
    stmt = insert(DocumentText).values(owner_type=owner_type, owner_id=owner_id, sha256=sha256, pages=pages,
                                       extractor=extractor, expires_at=expires_at)
    session.execute(stmt.on_conflict_do_update(
        index_elements=["owner_type", "owner_id", "sha256"],
        set_={"pages": pages, "extractor": extractor, "expires_at": expires_at},
    ))


def record_consent(session: Session, owner_type: str, owner_id: str, version: str, day) -> None:
    """6.6: un registro por usuario, versión del texto y día (la web lo pide una vez por sesión)."""
    stmt = insert(AiConsent).values(owner_type=owner_type, owner_id=owner_id, text_version=version, day=day)
    session.execute(stmt.on_conflict_do_nothing(index_elements=["owner_type", "owner_id", "text_version", "day"]))


def chat_doc_key(owner_type: str, owner_id: str, job_id: str) -> str:
    """Clave en `ai_cache` del documento preparado por un trabajo de chat-pdf."""
    return cache_key(owner_type, owner_id, "chat-pdf:documento", job_id, {}, "")


def chat_stream_key(message_id: str) -> str:
    """Stream de Valkey con los trozos de la respuesta de un mensaje del chat (9.1)."""
    return f"ai:chat:{message_id}"
