"""Base común de las implementaciones de servidor."""
from __future__ import annotations

from contextlib import contextmanager

import hashlib
import mimetypes
import os
import resource
import selectors
import signal
import subprocess
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel

from core.errors import ErrorCode, ToolError
from core.filetype import MIME
from core.plans import PlanLimits
from core.settings import Settings
from core.storage import Store, sanitize_filename

SAFE_PATH = "/usr/local/bin:/usr/bin:/bin"


@dataclass
class InputFile:
    path: Path
    name: str
    ext: str
    size: int
    sha256: str


class Handoff(Exception):
    """El trabajo sigue en otra cola (F3: el OCR de un escaneo en `ocr` y la IA en `ai`). Lo trata `tools.tasks`."""

    def __init__(self, group: str, queue: str, stage: str, message: str | None = None, keep_secrets: bool = True):
        super().__init__(f"{group}/{stage}")
        self.group = group
        self.queue = queue
        self.stage = stage
        self.message = message
        # False si la etapa siguiente no los necesita: el sobre cifrado no viaja a una cola sin JOB_SECRETS_KEY (12.1).
        self.keep_secrets = keep_secrets


@dataclass
class ToolContext:
    job_id: str
    tool: str
    inputs: list[InputFile]
    work: Path
    out: Path
    options: BaseModel
    secrets: dict[str, str]
    plan: PlanLimits
    settings: Settings
    store: Store
    threads: int = 1
    locale: str = "es"  # idioma de la página que creó el trabajo: textos que van dentro del resultado
    report: Callable[[float, str | None], None] = field(default=lambda p, m=None: None)
    # Cuenta una tarea más de esa clase al dueño del trabajo, por ejemplo cuando pdf-a-txt tiene que hacer OCR
    # (A.9: «cuenta como tarea de OCR»). Lanza QUOTA_EXCEEDED si ya no le quedan.
    charge: Callable[[str], None] = field(default=lambda cost_class: None)
    # Dueño del trabajo (tipo, id): lo que se guarda de sus documentos es solo suyo (6.5).
    owner: tuple[str, str] = ("", "")
    # Caducidad de los archivos del trabajo: la del texto extraído y la caché de IA (9.4).
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=1))
    # Etapa en la que sigue un trabajo que ha cambiado de cola (None la primera vez).
    stage: str | None = None
    # Cliente de IA (core.ai.client.AIClient) en las herramientas de IA; None en el resto.
    ai: object | None = None
    # Cola propia de la herramienta (a la que vuelve un trabajo tras pasar por otra, p. ej., `ai.embed` tras el OCR).
    home_queue: str | None = None

    def output(self, display_name: str) -> Path:
        return self.store.safe_output(self.job_id, display_name)

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def handoff(self, group: str, stage: str, message: str | None = None, queue: str | None = None,
                keep_secrets: bool = True) -> None:
        raise Handoff(group, queue or group, stage, message, keep_secrets)

    def stage_dir(self) -> Path:
        """Carpeta del trabajo que sobrevive al cambio de cola (`work/` se borra al acabar cada etapa)."""
        path = self.store.job_dir(self.job_id) / "stage"
        path.mkdir(parents=True, exist_ok=True)
        return path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def guess_mime(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return MIME.get(ext) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def describe_output(path: Path, display_name: str | None = None, note: str | None = None) -> dict:
    return {
        "path": str(path),
        "name": display_name or path.name,
        "size": path.stat().st_size,
        "mime": guess_mime(path),
        "sha256": sha256_file(path),
        "note": note,
    }


def derived_name(original: str, suffix: str, ext: str) -> str:
    """«Informe final.docx» + «-comprimido» + «pdf» → «Informe final-comprimido.pdf» (nombre visible)."""
    stem = Path(original).stem or "archivo"
    return f"{stem}{suffix}.{ext}"


def zip_files(files: list[tuple[Path, str]], zip_path: Path) -> Path:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        used: set[str] = set()
        for path, arcname in files:
            name = sanitize_filename(arcname) if "/" not in arcname else "/".join(sanitize_filename(p) for p in arcname.split("/"))
            base, n = name, 2
            while name in used:
                stem, dot, ext = base.rpartition(".")
                name = f"{stem}-{n}.{ext}" if dot else f"{base}-{n}"
                n += 1
            used.add(name)
            zf.write(path, name)
    return zip_path


@contextmanager
def open_image(src, max_pixels: int):
    """Abre una imagen sin descomprimirla y corta las bombas de píxeles (12.3)."""
    from PIL import Image, UnidentifiedImageError

    try:
        img = Image.open(src)
    except Image.DecompressionBombError as exc:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Imagen demasiado grande") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "Imagen no válida") from exc
    try:
        if img.width * img.height > max_pixels:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Imagen demasiado grande")
        yield img
    finally:
        img.close()


def regular_output(path: Path, root: Path) -> Path:
    """Un archivo que entrega un motor aislado (D-256): regular, no un enlace, y dentro de su carpeta. Si no, el motor se ha
    salido de lo previsto y no se entrega nada."""
    import stat as _stat

    path = Path(path)
    try:
        info = os.lstat(path)
        inside = os.path.realpath(path).startswith(os.path.realpath(root) + os.sep)
    except OSError as exc:
        raise ToolError(ErrorCode.ENGINE_FAILED, "engine_output") from exc
    if not _stat.S_ISREG(info.st_mode) or not inside:
        raise ToolError(ErrorCode.ENGINE_FAILED, "engine_output")
    return path


PR_SET_PDEATHSIG = 1
MAX_STDOUT = 256 * 1024 * 1024
STDERR_KEEP = 2 * 1024 * 1024  # del registro de error se guardan el principio y el final


def _limits(mem_mb: int | None, data_only: bool = False, landlock: list[tuple[Path, str]] | None = None,
            cpu_s: int | None = None, max_file_mb: int | None = None):
    # Todo lo que no es una llamada al sistema se prepara en el padre (después del fork solo se llama, D-230).
    restrict = None
    if landlock is not None:
        from tools.sandbox import prepare

        restrict = prepare(landlock)
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)

    def apply() -> None:
        os.setsid()
        # Si muere el worker (límite duro de Celery, OOM), el motor muere con él en lugar de quedarse huérfano.
        libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0)
        if mem_mb:
            limit = mem_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_DATA if data_only else resource.RLIMIT_AS, (limit, limit))
        if cpu_s:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        if max_file_mb:
            size = max_file_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_FSIZE, (size, size))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if restrict is not None:
            restrict()  # si no se puede, el hijo no llega a ejecutar el motor

    return apply


def _kill(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


class _TooMuchOutput(Exception):
    pass


def _collect(proc: subprocess.Popen, timeout: float, max_stdout: int) -> tuple[bytes, bytes]:
    """Lee stdout y stderr a la vez, con plazo: stdout hasta `max_stdout`; de stderr, el principio y el final (D-230)."""
    deadline = time.monotonic() + timeout
    out = bytearray()
    head = bytearray()
    tail = bytearray()
    cut = False
    with selectors.DefaultSelector() as sel:
        sel.register(proc.stdout, selectors.EVENT_READ, "out")
        sel.register(proc.stderr, selectors.EVENT_READ, "err")
        while sel.get_map():
            left = deadline - time.monotonic()
            if left <= 0:
                raise subprocess.TimeoutExpired(proc.args, timeout)
            for key, _ in sel.select(min(left, 1.0)):
                chunk = os.read(key.fd, 1 << 16)
                if not chunk:
                    sel.unregister(key.fileobj)
                    continue
                if key.data == "out":
                    out += chunk
                    if len(out) > max_stdout:
                        raise _TooMuchOutput
                elif len(head) < STDERR_KEEP:
                    head += chunk
                else:
                    tail += chunk
                    if len(tail) > 2 * STDERR_KEEP:
                        del tail[: len(tail) - STDERR_KEEP]
                        cut = True
    proc.stdout.close()
    proc.stderr.close()
    left = deadline - time.monotonic()
    if left <= 0:
        raise subprocess.TimeoutExpired(proc.args, timeout)
    proc.wait(timeout=left)
    if cut:
        tail = tail[-STDERR_KEEP:]
        return bytes(out), bytes(head) + b"\n[...]\n" + bytes(tail)
    return bytes(out), bytes(head) + bytes(tail)


def run_engine(
    args: list[str],
    cwd: Path,
    timeout: int,
    mem_mb: int | None = None,
    extra_env: dict[str, str] | None = None,
    limit_data: bool = False,
    ok_codes: tuple[int, ...] = (0,),
    landlock: list[tuple[Path, str]] | None = None,
    max_file_mb: int | None = None,
    max_stdout: int = MAX_STDOUT,
) -> subprocess.CompletedProcess:
    """Ejecuta un motor externo con entorno vacío (12.1): solo PATH, HOME y TMPDIR del trabajo.

    Ningún secreto del worker llega al subproceso. Si se pasa del tiempo, si llega el límite blando de Celery o si
    falla cualquier cosa mientras se espera, se mata el grupo entero (D-230); y si muere el worker, el motor recibe
    SIGKILL. El tiempo de CPU se limita a `timeout` por núcleo, la salida estándar a `max_stdout` y, con
    `max_file_mb`, el tamaño de cada archivo que escriba.
    Los mensajes de error del motor no se devuelven literalmente al usuario. `limit_data` limita la memoria de datos
    (RLIMIT_DATA) en lugar de la virtual: es para motores con Chromium, como Calibre, que reservan mucho espacio de
    direcciones sin usarlo y con RLIMIT_AS no arrancan (D-52). `ok_codes`: códigos de salida que no son un fallo (veraPDF
    devuelve 1 cuando el archivo no cumple).
    """
    env = {"PATH": SAFE_PATH, "HOME": str(cwd), "TMPDIR": str(cwd), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    if extra_env:
        env.update(extra_env)
    cpu_s = int(timeout) * max(1, os.cpu_count() or 1) + 30
    try:
        preexec = _limits(mem_mb, limit_data, landlock, cpu_s, max_file_mb)
    except Exception as exc:
        raise ToolError(ErrorCode.ENGINE_FAILED, "sandbox") from exc
    try:
        proc = subprocess.Popen(args, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, preexec_fn=preexec)
    except subprocess.SubprocessError as exc:
        # Landlock (tools/sandbox.py, D-227): si el núcleo no lo permite, error claro en lugar de ejecutar sin él.
        if landlock is not None:
            raise ToolError(ErrorCode.ENGINE_FAILED, "sandbox") from exc
        raise
    try:
        out, err = _collect(proc, timeout, max_stdout)
    except subprocess.TimeoutExpired:
        _kill(proc)
        raise ToolError(ErrorCode.TIMEOUT, f"{Path(args[0]).name} superó {timeout} s") from None
    except _TooMuchOutput:
        _kill(proc)
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{Path(args[0]).name} produjo demasiada salida") from None
    except BaseException:
        _kill(proc)  # SoftTimeLimitExceeded, KeyboardInterrupt…: el motor no sigue solo
        raise
    result = subprocess.CompletedProcess(args, proc.returncode, out, err)
    if proc.returncode not in ok_codes:
        raise ToolError(ErrorCode.ENGINE_FAILED, f"{Path(args[0]).name} terminó con código {proc.returncode}")
    return result
