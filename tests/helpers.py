"""Ayudas compartidas por las pruebas."""
from __future__ import annotations

from urllib.parse import urlsplit


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def download_path(url: str) -> str:
    """Convierte la URL pública de descarga en la URI que Caddy reenvía a /files/authorize."""
    parts = urlsplit(url)
    return f"{parts.path}?{parts.query}"


def local_file(services, url: str):
    from pathlib import Path

    parts = urlsplit(url).path.split("/")
    job_id, filename = parts[2], parts[3]
    return Path(services["files"]) / "jobs" / job_id / "out" / filename
