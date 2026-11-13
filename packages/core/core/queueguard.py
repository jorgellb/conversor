"""Guarda de colas (4.5): estima la espera y rechaza con QUEUE_FULL por encima del umbral."""
from __future__ import annotations

import os

from core.errors import AppError, ErrorCode

DEFAULT_CONCURRENCY = {
    "pdf": 3, "ocr": 1, "office": 2, "convert": 1, "media": 2, "ai": 4,
    "sign": 1, "av": 2, "utils": 2, "mesh": 1, "cad": 1,
}
DEFAULT_AVG_SECONDS = {"pdf": 5.0, "ocr": 40.0, "office": 8.0, "convert": 40.0, "av": 20.0}


def concurrency(group: str) -> int:
    value = os.environ.get(f"CONCURRENCY_{group.upper()}")
    return max(1, int(value)) if value else DEFAULT_CONCURRENCY.get(group, 1)


def _pending_key(queue: str) -> str:
    return f"q:{queue}:pending"


def _avg_key(queue: str) -> str:
    return f"q:{queue}:avg"


def on_enqueue(r, queue: str) -> None:
    r.incr(_pending_key(queue))


def on_start(r, queue: str) -> None:
    if int(r.decr(_pending_key(queue))) < 0:
        r.set(_pending_key(queue), 0)


def on_finish(r, queue: str, seconds: float) -> None:
    old = r.get(_avg_key(queue))
    new = seconds if old is None else float(old) * 0.8 + seconds * 0.2
    r.set(_avg_key(queue), f"{new:.3f}", ex=1800)


def estimated_wait(r, queue: str, group: str) -> float:
    pending = int(r.get(_pending_key(queue)) or 0)
    avg = float(r.get(_avg_key(queue)) or DEFAULT_AVG_SECONDS.get(group, 10.0))
    return pending * avg / concurrency(group)


def check(r, queue: str, group: str, limit_seconds: int, is_pro: bool) -> float:
    wait = estimated_wait(r, queue, group)
    threshold = limit_seconds * (2 if is_pro else 1)
    if wait > threshold:
        raise AppError(ErrorCode.QUEUE_FULL, status=503, extra={"wait_seconds": int(wait)})
    return wait
