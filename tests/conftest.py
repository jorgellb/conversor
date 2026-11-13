"""Entorno de pruebas: PostgreSQL y Redis/Valkey reales (locales o de la CI), migraciones y clientes."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core"), str(ROOT / "packages/tools"), str(ROOT / "apps/api"), str(ROOT / "scripts/fixtures")]

def _pg_bin() -> Path:
    # PostgreSQL 16 en producción y en la CI; en local vale la versión que traiga la distribución (Debian 13: 17).
    found = sorted(Path("/usr/lib/postgresql").glob("*/bin/initdb"), key=lambda p: int(p.parts[-3]))
    return found[0].parent if found else Path("/usr/lib/postgresql/16/bin")


PG_BIN = _pg_bin()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_postgres() -> tuple[str, callable]:
    # Directorio propio fuera del temporal de pytest (0700 de root): si se ejecuta como root,
    # PostgreSQL arranca con el usuario postgres y necesita poder recorrer la ruta.
    base = Path(tempfile.mkdtemp(prefix="conversor-pg-"))
    data = base / "pgdata"
    data.mkdir()
    port = _free_port()
    prefix: list[str] = []
    if os.geteuid() == 0:
        shutil.chown(base, user="postgres")
        shutil.chown(data, user="postgres")
        prefix = ["runuser", "-u", "postgres", "--"]
    subprocess.run([*prefix, str(PG_BIN / "initdb"), "-D", str(data), "-U", "postgres", "--auth=trust", "-E", "UTF8"],
                   check=True, capture_output=True)
    subprocess.run([*prefix, str(PG_BIN / "pg_ctl"), "-D", str(data), "-o", f"-p {port} -k {base} -c listen_addresses=127.0.0.1",
                    "-l", str(base / "pg.log"), "-w", "start"], check=True, capture_output=True)
    subprocess.run([*prefix, str(PG_BIN / "createdb"), "-h", "127.0.0.1", "-p", str(port), "-U", "postgres", "conversor"],
                   check=True, capture_output=True)

    def stop():
        subprocess.run([*prefix, str(PG_BIN / "pg_ctl"), "-D", str(data), "-m", "immediate", "stop"], capture_output=True)
        shutil.rmtree(base, ignore_errors=True)

    return f"postgresql+psycopg://postgres@127.0.0.1:{port}/conversor", stop


def _start_redis(base: Path) -> tuple[str, callable]:
    port = _free_port()
    proc = subprocess.Popen(["redis-server", "--port", str(port), "--save", "", "--appendonly", "no", "--dir", str(base)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    return f"redis://127.0.0.1:{port}/0", proc.terminate


@pytest.fixture(scope="session")
def services(tmp_path_factory):
    base = tmp_path_factory.mktemp("servicios")
    stops = []
    db_url = os.environ.get("TEST_DATABASE_URL")
    if not db_url:
        db_url, stop = _start_postgres()
        stops.append(stop)
    valkey_url = os.environ.get("TEST_VALKEY_URL")
    if not valkey_url:
        valkey_url, stop = _start_redis(base)
        stops.append(stop)
    files = base / "files"
    env = {
        "APP_ENV": "development", "SERVICE_ROLE": "test", "DATABASE_URL": db_url, "VALKEY_URL": valkey_url,
        "FILESTORE_PATH": str(files), "BACKUP_PATH": str(base / "backups"), "FILE_TOKEN_SECRET": "prueba-descargas",
        "ANON_TOKEN_SECRET": "prueba-anonimos", "JOB_SECRETS_KEY": "prueba-secretos", "BETTER_AUTH_URL": "https://ejemplo.test",
        "PUBLIC_WEB_URL": "https://ejemplo.test", "PUBLIC_FILES_URL": "https://files.ejemplo.test",
        "PUBLIC_API_URL": "https://api.ejemplo.test", "RATE_LIMIT_PER_MINUTE": "100000", "ANON_TOKENS_PER_IP_DAY": "100000",
        "DISK_MIN_FREE_GB": "0.01", "DISK_MAX_USAGE_PERCENT": "99.9", "GOTENBERG_URL": "http://gotenberg.test",
        "TURNSTILE_SECRET_KEY": "1x0000000000000000000000000000000AA", "PAYMENT_PROVIDER": "fake", "THREADS": "2",
    }
    os.environ.update(env)
    from core.db import reset_caches
    from core.settings import get_settings
    from core.valkey import get_valkey

    get_settings.cache_clear()
    reset_caches()
    get_valkey.cache_clear()
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "apps/api/alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "apps/api/migrations"))
    command.upgrade(cfg, "head")
    from core.storage import Store

    Store(files).ensure_layout()
    yield {"db_url": db_url, "valkey_url": valkey_url, "files": files, "base": base}
    for stop in stops:
        stop()


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory):
    from generate import generate

    out = tmp_path_factory.mktemp("muestras")
    generate(out)
    return out


@pytest.fixture(scope="session")
def jwt_keys():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    return private, private.public_key()


@pytest.fixture()
def api(services, jwt_keys):
    from fastapi.testclient import TestClient

    from app import deps
    from app.main import create_app
    from app.routers import jobs, session
    from tools.tasks import execute

    deps.KEY_RESOLVER["fn"] = lambda token, settings: jwt_keys[1]
    session.VERIFY["fn"] = lambda secret, token, ip: token == "ok"
    jobs.ENQUEUE["fn"] = lambda job, sealed, spec: execute(str(job.id), job.attempts + 1, sealed)
    with TestClient(create_app()) as client:
        yield client
    jobs.ENQUEUE["fn"] = None


@pytest.fixture()
def internal(services, jwt_keys):
    from fastapi.testclient import TestClient

    from app import deps
    from app.internal.app import create_internal_app

    deps.KEY_RESOLVER["fn"] = lambda token, settings: jwt_keys[1]
    with TestClient(create_internal_app()) as client:
        yield client


@pytest.fixture()
def user_token(jwt_keys):
    import jwt

    def make(user_id: str | None = None, role: str | None = None, email: str | None = None) -> str:
        now = datetime.now(timezone.utc)
        claims = {"sub": user_id or f"usuario-{uuid.uuid4().hex[:12]}", "iss": "https://ejemplo.test", "aud": "https://ejemplo.test",
                  "iat": now, "exp": now + timedelta(minutes=15), "email": email or "persona@ejemplo.test"}
        if role:
            claims["role"] = role
        return jwt.encode(claims, jwt_keys[0], algorithm="EdDSA")

    return make


@pytest.fixture()
def anon_token(api):
    def make() -> str:
        resp = api.post("/v1/session/anon", json={"turnstile_token": "ok"})
        assert resp.status_code == 200, resp.text
        return resp.json()["token"]

    return make


@pytest.fixture()
def tus_upload(internal, services):
    """Simula el flujo de tusd: pre-create, escritura del archivo y pre-finish."""

    def upload(token: str, tool: str, path: Path, filename: str | None = None, size: int | None = None) -> tuple[str | None, dict]:
        name = filename or path.name
        payload = {"Type": "pre-create", "Event": {
            "Upload": {"Size": size if size is not None else path.stat().st_size, "SizeIsDeferred": False,
                       "MetaData": {"filename": name, "tool": tool}},
            "HTTPRequest": {"Method": "POST", "URI": "/files/", "Header": {"Authorization": [f"Bearer {token}"]}}}}
        resp = internal.post("/tusd-hooks", json=payload).json()
        if resp.get("RejectUpload"):
            return None, resp
        upload_id = resp["ChangeFileInfo"]["ID"]
        dst = Path(services["files"]) / "uploads" / upload_id
        shutil.copyfile(path, dst)
        fin = internal.post("/tusd-hooks", json={"Type": "pre-finish", "Event": {"Upload": {"ID": upload_id}}}).json()
        return upload_id, fin

    return upload


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
