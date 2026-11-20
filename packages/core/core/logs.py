"""Logs en JSON sin nombres de archivo ni contenido (12.4)."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("job_id", "tool", "sha256", "size", "duration_ms", "error_code", "queue"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


SIGN_TOKEN_RE = re.compile(r"(/v1/sign/)[A-Za-z0-9_-]+")


class RedactSignTokens(logging.Filter):
    """El token del firmante de solicitar-firmas va en la ruta (/v1/sign/{token}, 9.1): fuera de los logs de acceso."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(SIGN_TOKEN_RE.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.msg, str):
            record.msg = SIGN_TOKEN_RE.sub(r"\1***", record.msg)
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Celery registra los argumentos de las tareas en DEBUG; nunca deben salir en producción.
    logging.getLogger("celery.app.trace").setLevel(logging.WARNING)
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactSignTokens) for f in access.filters):
        access.addFilter(RedactSignTokens())
