"""Aplicación Celery con Valkey como broker (5.3)."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging as celery_setup_logging

from core.registry import load_registry
from core.settings import get_settings


def _max_time_limit() -> int:
    tools = load_registry().server_tools()
    return max([t.time_limit for t in tools] + [3600])


def make_celery() -> Celery:
    settings = get_settings()
    app = Celery("conversor", broker=settings.VALKEY_URL, include=["tools.tasks", "core.maintenance", "core.ai.tasks", "tools.ai.chat", "tools.sign.tasks"])
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_reject_on_worker_lost=False,
        task_ignore_result=True,
        task_store_errors_even_if_ignored=False,
        broker_connection_retry_on_startup=True,
        worker_hijack_root_logger=False,
        worker_send_task_events=False,
        timezone="UTC",
        broker_transport_options={
            # Mayor que el time_limit más largo + 10 minutos: si no, Valkey reentrega trabajos largos.
            "visibility_timeout": _max_time_limit() + 600,
            "priority_steps": list(range(10)),
            "sep": ":",
            "queue_order_strategy": "priority",
        },
        task_default_queue="pdf",
        # Las tareas de IA necesitan la clave y la salida a OpenRouter: solo las ejecuta `workerai` (12.1 y 12.2).
        # El mantenimiento lo ejecuta el propio contenedor de beat (`worker -B -Q maintenance`): borra filas de `uploads`
        # y `shares`, que el usuario de base de datos de los workers no puede tocar, y avisa por SMTP (D-181).
        task_routes={"core.ai.tasks.*": {"queue": "ai"}, "tools.ai.chat.answer": {"queue": "ai"},
                     "tools.ai.chat.retrieve": {"queue": "ai.embed"}, "core.maintenance.*": {"queue": "maintenance"},
                     "tools.sign.tasks.*": {"queue": "sign.verify"}},
        beat_schedule={
            "cleanup-expired": {"task": "core.maintenance.cleanup_expired", "schedule": 300.0},
            "requeue-stale": {"task": "core.maintenance.requeue_stale", "schedule": 60.0},
            # solicitar-firmas (F4-C2): la API también avanza cada solicitud al consultarla; esto es lo que no espera a nadie.
            "signature-requests": {"task": "core.maintenance.signature_requests", "schedule": 60.0, "options": {"expires": 55}},
            "disk-alert": {"task": "core.maintenance.disk_alert", "schedule": 300.0},
            "find-orphans": {"task": "core.maintenance.find_orphans", "schedule": crontab(hour=4, minute=17)},
            "ai-models": {"task": "core.ai.tasks.refresh_models", "schedule": max(1, settings.LLM_MODELS_REFRESH_HOURS) * 3600.0},
            "ai-reconcile": {"task": "core.ai.tasks.reconcile", "schedule": 600.0},
            # Lista de confianza de la UE (7.23): la descarga workersignverify por egressweb cuando toca (EUTL_REFRESH_HOURS).
            # Caduca antes de la siguiente: sin workersignverify no se acumulan en la cola.
            "eutl-refresh": {"task": "tools.sign.tasks.refresh_eutl", "schedule": 3600.0, "options": {"expires": 3300}},
        },
    )
    return app


celery_app = make_celery()


@celery_setup_logging.connect
def _json_logs(**_kwargs) -> None:
    """Los workers y beat escriben los mismos logs en JSON que la API (12.4). Con un receptor en esta señal Celery no
    configura el logging; sin él, y con `worker_hijack_root_logger=False`, el logger raíz se quedaba sin manejador y se
    perdían todos los INFO (arranque de beat, limpiezas, lista de confianza de la UE) y los errores salían sin JSON."""
    from core.logs import setup_logging

    setup_logging(get_settings().LOG_LEVEL)
