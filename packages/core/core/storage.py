"""Almacenamiento propio en disco (sección 4): rutas, nombres seguros y movimientos atómicos."""
from __future__ import annotations

import os
import re
import shutil
import stat
import unicodedata
from pathlib import Path

SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]+")
MAX_NAME = 120


def sanitize_filename(name: str, default: str = "archivo") -> str:
    """Solo [A-Za-z0-9._-], sin rutas y como máximo 120 caracteres; conserva la extensión."""
    base = os.path.basename((name or "").replace("\\", "/"))
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = SAFE_CHARS_RE.sub("-", base).strip(".-_")
    if not base:
        base = default
    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""
    ext = ext[:10]
    room = MAX_NAME - (len(ext) + 1 if ext else 0)
    stem = (stem or default)[:room].strip(".-_") or default
    return f"{stem}.{ext}" if ext else stem


def is_regular_file(path: Path) -> bool:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    return stat.S_ISREG(st.st_mode)


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)

    @property
    def uploads(self) -> Path:
        return self.root / "uploads"

    def job_dir(self, job_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f-]{36}", str(job_id)):
            raise ValueError("Identificador de trabajo no válido")
        return self.root / "jobs" / str(job_id)

    def in_dir(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "in"

    def work_dir(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "work"

    def out_dir(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "out"

    def share_dir(self, share_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f-]{36}", str(share_id)):
            raise ValueError("Identificador de compartición no válido")
        return self.root / "shares" / str(share_id)

    def request_dir(self, request_id: str) -> Path:
        """solicitar-firmas (F4-C2): el documento vive aquí mientras dura la solicitud, fuera de la retención de 24 h
        de los trabajos (desviación de 4.1, D-202)."""
        if not re.fullmatch(r"[0-9a-f-]{36}", str(request_id)):
            raise ValueError("Identificador de solicitud no válido")
        return self.root / "requests" / str(request_id)

    def ensure_layout(self) -> None:
        for sub in ("uploads", "jobs", "shares", "requests"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    def ensure_job_dirs(self, job_id: str) -> None:
        for d in (self.in_dir(job_id), self.work_dir(job_id), self.out_dir(job_id)):
            d.mkdir(parents=True, exist_ok=True)

    def upload_path(self, upload_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", upload_id):
            raise ValueError("Identificador de subida no válido")
        return self.uploads / upload_id

    def move_upload_to_job(self, upload_id: str, job_id: str, index: int, original_name: str) -> Path:
        """Mueve con rename atómico (mismo sistema de archivos) la subida a jobs/<id>/in."""
        src = self.upload_path(upload_id)
        if not is_regular_file(src):
            raise FileNotFoundError(upload_id)
        self.ensure_job_dirs(job_id)
        dst = self.in_dir(job_id) / f"{index:03d}-{sanitize_filename(original_name)}"
        os.rename(src, dst)
        info = src.with_name(src.name + ".info")
        if info.exists():
            info.unlink(missing_ok=True)
        return dst

    def remove_job(self, job_id: str) -> None:
        shutil.rmtree(self.job_dir(job_id), ignore_errors=True)

    def remove_upload(self, upload_id: str) -> None:
        p = self.upload_path(upload_id)
        p.unlink(missing_ok=True)
        p.with_name(p.name + ".info").unlink(missing_ok=True)

    def safe_output(self, job_id: str, name: str) -> Path:
        """Ruta de salida dentro de out/, con nombre saneado y sin colisiones."""
        out = self.out_dir(job_id)
        candidate = out / sanitize_filename(name)
        stem, suffix = candidate.stem, candidate.suffix
        n = 2
        while candidate.exists():
            candidate = out / f"{stem}-{n}{suffix}"
            n += 1
        return candidate
