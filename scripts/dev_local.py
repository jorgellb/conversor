"""Arranque local sin Docker (solo desarrollo): `python scripts/dev_local.py start | stop | status`.

Levanta el portal entero en esta máquina con lo que haya instalado: PostgreSQL (con pgvector), Redis (en lugar de
Valkey), las migraciones de Better Auth y de la API, la API pública (8000) y la interna (8001), un worker de Celery con
todas las colas más el de mantenimiento, los sustitutos mínimos de tusd (8080, `scripts/dev/tus_local.py`) y de Caddy
(8090, `scripts/dev/files_local.py`) y la web ya compilada (`npm run build`) en http://localhost:3000.

Los datos van a `~/.local/share/conversor-dev` (base de datos, archivos, registros y los PID). Gotenberg se sustituye por
`scripts/dev/gotenberg_local.py` (las rutas de Chromium con el Chromium de Playwright; las de LibreOffice, con el `soffice`
de la máquina si puede abrir el archivo). Lo que necesite un motor que no esté instalado (Calibre, OpenSCAD, LibreDWG, el
sello con SoftHSM…) falla con su error, igual que en un worker sin ese motor. Los
correos (enlaces de inicio de sesión, solicitudes de firma) se ven en http://localhost:8025 (`scripts/dev/mail_local.py`,
en lugar de Mailpit). Para el despliegue de verdad, `docker compose up` (README) y Coolify (docs/DEPLOY.md).
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("CONVERSOR_DEV_DIR", Path.home() / ".local/share/conversor-dev"))
PIDS = DATA / "pids.json"
LOGS = DATA / "logs"
PG_PORT, REDIS_PORT = 5544, 6390
PORTS = {"web": 3000, "api": 8000, "apiint": 8001, "tus": 8080, "files": 8090, "mail": 8025}
VENV = ROOT / ".venv/bin"
ENGINES = Path.home() / ".cache/conversor-motores"


def _pg_bin() -> Path:
    found = sorted(Path("/usr/lib/postgresql").glob("*/bin/initdb"), key=lambda p: int(p.parts[-3]))
    if not found:
        sys.exit("Falta PostgreSQL (initdb): instálalo con pgvector.")
    return found[-1].parent


def _env() -> dict[str, str]:
    env = dict(os.environ)
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env.setdefault(key.strip(), value.strip())
    db = f"postgresql+psycopg://conversor:conversor@127.0.0.1:{PG_PORT}/conversor"
    env.update({
        "APP_ENV": "development",
        "DATABASE_URL": db,
        "VALKEY_URL": f"redis://127.0.0.1:{REDIS_PORT}/0",
        "AUTH_JWKS_URL": f"http://127.0.0.1:{PORTS['web']}/api/auth/jwks",
        "PUBLIC_WEB_URL": f"http://localhost:{PORTS['web']}",
        "BETTER_AUTH_URL": f"http://localhost:{PORTS['web']}",
        "PUBLIC_API_URL": f"http://localhost:{PORTS['api']}",
        "PUBLIC_UPLOAD_URL": f"http://localhost:{PORTS['tus']}/files/",
        "PUBLIC_FILES_URL": f"http://localhost:{PORTS['files']}",
        "FILESTORE_PATH": str(DATA / "files"),
        "BACKUP_PATH": str(DATA / "backups"),
        "GOTENBERG_URL": "http://127.0.0.1:3999",  # scripts/dev/gotenberg_local.py: Chromium de Playwright y el soffice local
        "GOTENBERG_WEB_URL": "http://127.0.0.1:3999",
        "SMTP_URL": "smtp://127.0.0.1:1025",
        "PYTHONPATH": os.pathsep.join(str(ROOT / p) for p in ("packages/core", "packages/tools", "apps/api")),
        "PYTHONUTF8": "1",
        "WORKER_DB_PASSWORD": "worker-desarrollo",
    })
    # Motores que las pruebas encuentran en la caché local (pandoc, tectonic, fluidsynth, MuseScore, Whisper, Kokoro…).
    engines = {"PANDOC_BIN": "pandoc/bin/pandoc", "TECTONIC_BIN": "tectonic/bin/tectonic", "TECTONIC_CACHE": "tectonic/cache",
               "DRAWIO_VIEWER": "drawio/viewer-static.min.js", "FLUIDSYNTH_BIN": "debs/root/usr/bin/fluidsynth",
               "SOUNDFONT": "debs/root/usr/share/sounds/sf2/FluidR3_GM.sf2", "MSCORE_BIN": "debs/root/usr/bin/mscore3",
               "WHISPER_HOME": "whisper", "KOKORO_HOME": "kokoro",
               # chat-pdf: `sh infra/embeddings/fetch-model.sh ~/.cache/conversor-motores/embeddings` (revisión y SHA-256 fijados)
               "EMBEDDINGS_HOME": "embeddings"}
    for key, rel in engines.items():
        if (ENGINES / rel).exists():
            env.setdefault(key, str(ENGINES / rel))
    libs = [ENGINES / "debs/root/usr/lib/x86_64-linux-gnu", ENGINES / "debs/root/usr/lib"]
    if all(p.exists() for p in libs):
        env.setdefault("ENGINES_LIBRARY_PATH", os.pathsep.join(map(str, libs)))
    return env


def _pids() -> dict[str, int]:
    return json.loads(PIDS.read_text()) if PIDS.exists() else {}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _spawn(name: str, args: list[str], env: dict, cwd: Path = ROOT) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = open(LOGS / f"{name}.log", "ab")
    proc = subprocess.Popen(args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    pids = _pids()
    pids[name] = proc.pid
    PIDS.write_text(json.dumps(pids))
    print(f"  {name}: pid {proc.pid} (registro en {LOGS / (name + '.log')})")


def _wait_port(port: int, name: str, seconds: int = 60) -> None:
    for _ in range(seconds * 2):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.5)
    sys.exit(f"{name} no responde en el puerto {port}: mira {LOGS / (name + '.log')}")


def _run(args: list[str], env: dict, cwd: Path = ROOT) -> None:
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"Falló {' '.join(args[:3])}…:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}")


def start() -> None:
    env = _env()
    if any(_alive(p) for p in _pids().values()):
        sys.exit("Ya está en marcha: `python scripts/dev_local.py stop` antes.")
    for sub in ("files/uploads", "files/jobs", "files/shares", "files/requests", "backups/postgres", "logs"):
        (DATA / sub).mkdir(parents=True, exist_ok=True)
    pg = _pg_bin()
    pgdata = DATA / "postgres"
    if not (pgdata / "PG_VERSION").exists():
        print("Creando la base de datos…")
        _run([str(pg / "initdb"), "-D", str(pgdata), "-U", "postgres", "--auth=trust", "-E", "UTF8"], env)
    print("Arrancando PostgreSQL y Redis…")
    _run([str(pg / "pg_ctl"), "-D", str(pgdata), "-l", str(LOGS / "postgres.log"), "-w", "-o",
          f"-p {PG_PORT} -k {DATA} -c listen_addresses=127.0.0.1", "start"], env)
    psql = [str(pg / "psql"), "-h", "127.0.0.1", "-p", str(PG_PORT), "-U", "postgres", "-tAc"]
    exists = subprocess.run([*psql, "SELECT 1 FROM pg_roles WHERE rolname='conversor'"], env=env, capture_output=True, text=True)
    if exists.stdout.strip() != "1":
        _run([*psql, "CREATE ROLE conversor LOGIN SUPERUSER PASSWORD 'conversor'"], env)
        _run([*psql, "CREATE DATABASE conversor OWNER conversor"], env)
    _spawn("redis", ["redis-server", "--port", str(REDIS_PORT), "--bind", "127.0.0.1", "--save", "", "--appendonly", "no",
                     "--dir", str(DATA)], env)
    _wait_port(REDIS_PORT, "redis")
    print("Migraciones…")
    web_env = {**env, "AUTH_DATABASE_URL": f"postgresql://conversor:conversor@127.0.0.1:{PG_PORT}/conversor",
               "AUTH_SECRET": "desarrollo-solo-local-cambiar-0123456789abcdef"}
    _run(["node", "scripts/migrate-auth.mjs"], web_env, ROOT / "apps/web")
    _run([str(VENV / "alembic"), "-c", "apps/api/alembic.ini", "upgrade", "head"], {**env, "SERVICE_ROLE": "migrate"})
    print("Servicios…")
    uvicorn = str(VENV / "uvicorn")
    _spawn("api", [uvicorn, "app.main:app", "--host", "127.0.0.1", "--port", str(PORTS["api"])], {**env, "SERVICE_ROLE": "api"})
    _spawn("apiint", [uvicorn, "app.internal.app:app", "--host", "127.0.0.1", "--port", str(PORTS["apiint"])],
           {**env, "SERVICE_ROLE": "apiint"})
    _wait_port(PORTS["apiint"], "apiint")
    _spawn("gotenberg", [str(VENV / "python"), "scripts/dev/gotenberg_local.py"], {**env, "GOTENBERG_PORT": "3999"})
    _wait_port(3999, "gotenberg")
    queues = _queues(env)
    celery = str(VENV / "celery")
    _spawn("worker", [celery, "-A", "core.celeryapp", "worker", "-Q", ",".join(queues), "-n", "local@%h", "-c", "2",
                      "--prefetch-multiplier", "1", "-O", "fair", "--without-gossip", "--without-mingle"],
           {**env, "SERVICE_ROLE": "worker-local", "THREADS": "2"})
    _spawn("beat", [celery, "-A", "core.celeryapp", "worker", "-B", "-Q", "maintenance", "--pool", "solo", "-n", "beat@%h",
                    "-s", str(DATA / "celerybeat-schedule")], {**env, "SERVICE_ROLE": "beat"})
    # El catálogo de modelos de la IA (con el proveedor falso, sin clave) se pide ya, sin esperar a la hora de beat.
    _run([celery, "-A", "core.celeryapp", "call", "core.ai.tasks.refresh_models"], env)
    py = str(VENV / "python")
    _spawn("tus", [py, "scripts/dev/tus_local.py"], {**env, "TUS_PORT": str(PORTS["tus"])})
    _spawn("files", [py, "scripts/dev/files_local.py"], {**env, "FILES_PORT": str(PORTS["files"])})
    _spawn("mail", [py, "scripts/dev/mail_local.py"], env)
    if not (ROOT / "apps/web/.next/BUILD_ID").exists():
        print("Compilando la web (unos minutos)…")
        _run(["npm", "run", "build", "-w", "@conversor/web"], env)
    _spawn("web", ["npx", "next", "start", "-p", str(PORTS["web"])], {**web_env, "PORT": str(PORTS["web"])}, ROOT / "apps/web")
    for name in ("api", "tus", "files", "mail", "web"):
        _wait_port(PORTS[name], name, 120)
    print(f"\nListo: abre http://localhost:{PORTS['web']}/es  (correos en http://localhost:{PORTS['mail']}, datos en {DATA})")


def _queues(env: dict) -> list[str]:
    out = subprocess.run([str(VENV / "python"), "-c", "from core.registry import load_registry; "
                          "print(','.join(sorted({t.queue for t in load_registry().specs if t.runs_on_server})))"],
                         env=env, capture_output=True, text=True, cwd=ROOT)
    if out.returncode != 0:
        sys.exit(out.stderr[-2000:])
    return out.stdout.strip().split(",")


def stop() -> None:
    for name, pid in _pids().items():
        if _alive(pid):
            try:
                os.killpg(pid, signal.SIGTERM)  # el grupo que creó _spawn (start_new_session), nada más
            except OSError:
                os.kill(pid, signal.SIGTERM)
            print(f"  {name}: parado (pid {pid})")
    PIDS.unlink(missing_ok=True)
    pgdata = DATA / "postgres"
    if (pgdata / "postmaster.pid").exists():
        subprocess.run([str(_pg_bin() / "pg_ctl"), "-D", str(pgdata), "-m", "fast", "stop"], capture_output=True)
        print("  postgres: parado")


def status() -> None:
    pids = _pids()
    if not pids:
        print("Parado.")
    for name, pid in pids.items():
        print(f"  {name}: {'en marcha' if _alive(pid) else 'caído'} (pid {pid})")


if __name__ == "__main__":
    {"start": start, "stop": stop, "status": status}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
