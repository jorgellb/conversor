"""Tareas de `sign.verify`: refresco de la lista de confianza de la UE (7.23). Beat la pide cada hora y solo se
descarga si no hay ninguna versión, está dañada o tiene más de EUTL_REFRESH_HOURS; así una primera descarga fallida (o
`egressweb` mal configurado) se reintenta a la hora siguiente y no al día siguiente. El worker también la pide al
arrancar."""
from __future__ import annotations

import logging
import os

from celery.signals import worker_ready

from core.celeryapp import celery_app
from core.settings import get_settings

log = logging.getLogger("worker")


@celery_app.task(name="tools.sign.tasks.refresh_eutl", ignore_result=True, soft_time_limit=1500, time_limit=1800)
def refresh_eutl(force: bool = False) -> dict | None:
    from tools.sign import confianza

    settings = get_settings()
    if not force and not confianza.due(settings):
        return None
    try:
        return confianza.refresh(settings)
    except Exception:  # noqa: BLE001 - sin red o con una LOTL que no valida se conserva la versión anterior (7.23 y 14)
        log.exception("no se ha podido actualizar la lista de confianza de la UE")
        return None


@worker_ready.connect
def _first_download(sender=None, **_kwargs) -> None:
    if os.environ.get("WORKER_NAME") == "sign-verify":
        refresh_eutl.apply_async(queue="sign.verify")
