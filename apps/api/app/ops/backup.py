"""Copia de la base de datos (4.6): `python -m app.ops.backup`, cada 6 horas desde una tarea de Coolify en `apiint`."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from core.external import send_mail
from core.logs import setup_logging
from core.settings import get_settings

log = logging.getLogger("backup")


def pg_env(url) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    if url.password:
        env["PGPASSWORD"] = url.password
    return env


def pg_args(url) -> list[str]:
    return ["-h", url.host or "localhost", "-p", str(url.port or 5432), "-U", url.username or "postgres", "-d", url.database]


def dump(database_url: str, out_dir: Path) -> Path:
    url = make_url(database_url)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = out_dir / f"{stamp}.dump"
    tmp = target.with_suffix(".tmp")
    subprocess.run(["pg_dump", "-Fc", "--no-owner", *pg_args(url), "-f", str(tmp)], env=pg_env(url), check=True, timeout=3600)
    tmp.rename(target)
    return target


def prune(out_dir: Path, days: int) -> int:
    limit = time.time() - days * 86400
    removed = 0
    for f in out_dir.glob("*.dump"):
        if f.stat().st_mtime < limit:
            f.unlink()
            removed += 1
    return removed


def restic(repo: str, password: str, paths: list[Path]) -> None:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "RESTIC_REPOSITORY": repo, "RESTIC_PASSWORD": password,
           "HOME": os.environ.get("HOME", "/tmp")}
    if subprocess.run(["restic", "snapshots", "--latest", "1"], env=env, capture_output=True, timeout=600).returncode != 0:
        subprocess.run(["restic", "init"], env=env, check=True, timeout=600)
    subprocess.run(["restic", "backup", *[str(p) for p in paths if p.exists()]], env=env, check=True, timeout=7200)
    subprocess.run(["restic", "forget", "--keep-daily", "7", "--keep-weekly", "4", "--keep-monthly", "6", "--prune"],
                   env=env, check=True, timeout=7200)


def main() -> int:
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    out_dir = Path(settings.BACKUP_PATH) / "postgres"
    try:
        target = dump(settings.DATABASE_URL, out_dir)
        prune(out_dir, settings.BACKUP_RETENTION_DAYS)
        if settings.BACKUP_RESTIC_REPOSITORY:
            extra = [Path(p) for p in os.environ.get("BACKUP_EXTRA_PATHS", "").split(":") if p]
            restic(settings.BACKUP_RESTIC_REPOSITORY, settings.BACKUP_RESTIC_PASSWORD, [out_dir, *extra])
        log.info("copia correcta: %s", target.name)
        _failures(reset=True)
        return 0
    except (subprocess.SubprocessError, OSError) as exc:
        log.error("copia fallida: %s", type(exc).__name__)
        if _failures() >= 2:
            send_mail(settings.SMTP_URL, settings.MAIL_FROM, settings.admin_emails,
                      f"[{settings.APP_NAME}] La copia de seguridad ha fallado dos veces seguidas",
                      "Revisa la tarea programada de copias en Coolify y el repositorio de restic.")
        return 1


def _failures(reset: bool = False) -> int:
    try:
        from core.valkey import get_valkey

        r = get_valkey()
        if reset:
            r.delete("backup:failures")
            return 0
        return int(r.incr("backup:failures"))
    except Exception:  # noqa: BLE001
        return 0


if __name__ == "__main__":
    sys.exit(main())
