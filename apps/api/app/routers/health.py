"""Vida y preparación (9.1). /readyz devuelve 503 si algo crítico falla."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.deps import registry_dep, settings_dep, valkey_dep
from core import disk, queueguard
from core.db import get_engine
from core.envguard import violations
from core.registry import Registry
from core.settings import Settings

router = APIRouter(tags=["salud"])


@router.get("/healthz")
def healthz():
    return {"ok": True}


def pg_dump_matches(settings: Settings) -> bool | None:
    """Comprueba que `pg_dump` es de la misma versión mayor que el servidor (4.6). None si no aplica."""
    if settings.SERVICE_ROLE != "apiint" or not shutil.which("pg_dump"):
        return None
    out = subprocess.run(["pg_dump", "--version"], capture_output=True, text=True, timeout=10).stdout
    client_major = out.strip().split()[-1].split(".")[0]
    with get_engine().connect() as conn:
        server_major = str(conn.execute(text("SHOW server_version_num")).scalar())[:2]
    return client_major == server_major


def readiness(settings: Settings, r, registry: Registry) -> tuple[bool, dict]:
    checks: dict = {}
    ok = True
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {type(exc).__name__}"
        ok = False
    try:
        r.ping()
        checks["valkey"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["valkey"] = f"error: {type(exc).__name__}"
        ok = False
    if ok:
        st = disk.status(r, Path(settings.FILESTORE_PATH), settings.DISK_MAX_USAGE_PERCENT, settings.DISK_MIN_FREE_GB)
        checks["disk"] = st.as_dict()
        queues = sorted({s.queue for s in registry.server_tools() if s.queue})
        checks["queues"] = {q: int(queueguard.estimated_wait(r, q, q.split(".")[0])) for q in queues}
    bad_env = violations(settings.SERVICE_ROLE)
    checks["secrets"] = "ok" if not bad_env else {"no_permitidas": bad_env}
    # En desarrollo todos los servicios leen .env.example: se informa, pero solo bloquea en producción.
    ok = ok and (not bad_env or settings.is_dev)
    if settings.SERVICE_ROLE in ("api", "apiint"):
        try:
            resp = httpx.get(f"{settings.GOTENBERG_URL.rstrip('/')}/health", timeout=3)
            checks["gotenberg"] = "ok" if resp.status_code == 200 else f"http {resp.status_code}"
        except httpx.HTTPError:
            checks["gotenberg"] = "no disponible"
    match = pg_dump_matches(settings)
    if match is not None:
        checks["pg_dump"] = "ok" if match else "versión distinta del servidor"
        ok = ok and match
    return ok, checks


@router.get("/readyz")
def readyz(settings: Settings = Depends(settings_dep), r=Depends(valkey_dep), registry: Registry = Depends(registry_dep)):
    ok, checks = readiness(settings, r, registry)
    return JSONResponse({"ok": ok, "checks": checks}, status_code=200 if ok else 503)
