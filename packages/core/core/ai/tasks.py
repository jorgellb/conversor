"""Tareas periódicas de IA en `workerai`, el único con la clave y con salida a OpenRouter (6.2 y 6.3).

- `refresh_models`: al arrancar el worker y cada `LLM_MODELS_REFRESH_HOURS` horas, `GET /models`.
- `reconcile`: cada 10 minutos, `GET /key`; si OpenRouter cuenta más peticiones gratuitas que nosotros, el contador
  propio sube, y si le quedan menos de 20, solo Pro usa IA.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from celery.signals import worker_ready

from core.ai import budget, catalog
from core.ai.provider import LLMError, get_provider
from core.celeryapp import celery_app
from core.db import session_scope
from core.settings import get_settings
from core.valkey import get_valkey

log = logging.getLogger("ai")


@celery_app.task(name="core.ai.tasks.refresh_models", ignore_result=True)
def refresh_models() -> int:
    settings = get_settings()
    try:
        data = get_provider(settings).list_models()
    except LLMError as exc:
        log.warning("descubrimiento de modelos fallido: %s", exc.kind)
        return -1
    models = catalog.parse_models(data)
    with session_scope() as s:
        n = catalog.upsert_models(s, models)
        catalog.update_success_rates(s)
    log.info("modelos gratuitos descubiertos: %d", n)
    return n


@celery_app.task(name="core.ai.tasks.reconcile", ignore_result=True)
def reconcile() -> dict | None:
    settings = get_settings()
    r = get_valkey()
    try:
        info = get_provider(settings).key_info()
    except LLMError as exc:
        log.warning("reconciliación con /key fallida: %s", exc.kind)
        return None
    free = info.get("free_model_daily_requests") or {}
    delta = 0
    if isinstance(free.get("used"), int):
        delta = budget.reconcile(r, settings, int(free["used"]), free.get("remaining") if isinstance(free.get("remaining"), int) else None)
    snapshot = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "free_model_daily_requests": free or None,
        "usage": info.get("usage"),
        "usage_daily": info.get("usage_daily"),
        "limit": info.get("limit"),
        "limit_remaining": info.get("limit_remaining"),
        "is_free_tier": info.get("is_free_tier"),
        "raised_by": delta,
    }
    budget.save_key_snapshot(r, snapshot)
    with session_scope() as s:
        catalog.update_success_rates(s)
    if delta:
        log.warning("OpenRouter cuenta %d peticiones gratuitas más que el contador propio", delta)
    return snapshot


@worker_ready.connect
def _on_start(sender=None, **_kwargs) -> None:
    """6.2: descubrimiento al arrancar `workerai`."""
    if os.environ.get("SERVICE_ROLE") == "worker-ai":
        refresh_models.apply_async(queue="ai")
