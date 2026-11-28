"""Los workers y beat escriben logs en JSON como la API (12.4): Celery no debe dejar el logger raíz sin manejador."""
from __future__ import annotations

import io
import json
import logging

from celery.signals import setup_logging as celery_setup_logging

from core.celeryapp import _json_logs
from core.logs import JsonFormatter


def test_celery_logging_signal_installs_json_handler(monkeypatch):
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        root.handlers[:] = []
        assert _json_logs in [r() for _, r in celery_setup_logging.receivers]
        celery_setup_logging.send(sender=None, loglevel="WARNING", logfile=None, format="", colorize=False)
        assert len(root.handlers) == 1 and isinstance(root.handlers[0].formatter, JsonFormatter)
        assert root.level == logging.INFO
        buf = io.StringIO()
        root.handlers[0].setStream(buf)
        logging.getLogger("celery.beat").info("beat: Starting...")
        logging.getLogger("maintenance").info("cleanup_expired: %s", {"jobs": 0})
        # La traza de Celery (con los argumentos de las tareas en DEBUG) se queda en WARNING.
        logging.getLogger("celery.app.trace").info("Task x succeeded")
        lines = [json.loads(line) for line in buf.getvalue().splitlines()]
        assert [line["msg"] for line in lines] == ["beat: Starting...", "cleanup_expired: {'jobs': 0}"]
        assert lines[0]["level"] == "INFO" and lines[0]["logger"] == "celery.beat"
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
