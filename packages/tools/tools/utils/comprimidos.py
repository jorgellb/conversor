"""Comprimidos (7.13, F6-E, D-217): rar-a-zip, 7z-a-zip, tar-a-zip y extraer-archivo-online con libarchive.

libarchive (BSD-2-Clause, con libarchive-c) lee RAR 4 y 5, 7z, ZIP, tar y tar comprimido con gzip, bzip2, xz o zstd; nunca
unrar ni p7zip (11). Cada entrada se copia por bloques con límites de bombas (12.3): 10 000 entradas, 2 GB descomprimidos y
una relación de 1000 a 1 sobre el archivo subido. Rutas seguras (16.4): sin `..`, sin raíz, sin letra de unidad y sin
barras invertidas; los enlaces simbólicos, los duros y los dispositivos no se extraen.
"""
from __future__ import annotations

import posixpath
import re
import time
import zipfile
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.zipguard import MAX_MEMBERS, MAX_UNCOMPRESSED
from tools.base import ToolContext, derived_name
from tools.pdf.common import with_batch_zip

MAX_RATIO = 1000
RATIO_FLOOR = 200 * 1024 * 1024  # la relación solo cuenta por encima de 200 MB descomprimidos
MAX_LISTED = 50  # extraer-archivo-online: hasta 50 archivos sueltos; más, solo el ZIP

NOTES = {
    "es": {"summary": "{files} archivo(s) en {dirs} carpeta(s).", "links": "{n} enlace(s) o archivo(s) especiales no se han extraído.",
           "renamed": "{n} ruta(s) peligrosas (con «..» o absolutas) se han guardado dentro de la carpeta del archivo.",
           "only_zip": "Tiene más de {n} archivos: descarga el ZIP con todos.", "empty": "El archivo comprimido está vacío."},
    "en": {"summary": "{files} file(s) in {dirs} folder(s).", "links": "{n} link(s) or special file(s) were not extracted.",
           "renamed": "{n} unsafe path(s) (with “..” or absolute) were stored inside the archive's folder.",
           "only_zip": "It has more than {n} files: download the ZIP with all of them.", "empty": "The archive is empty."},
}


def safe_name(raw: str) -> tuple[str, bool]:
    """Ruta relativa segura y si ha habido que cambiarla («../../etc/passwd» → «etc/passwd»)."""
    name = raw.replace("\\", "/")
    name = re.sub(r"^[A-Za-z]:", "", name)
    parts = [p for p in name.split("/") if p not in ("", ".")]
    clean = [p for p in parts if p != ".."]
    changed = name.startswith("/") or len(clean) != len(parts) or name != raw.replace("\\", "/")
    return "/".join(clean), changed


def _zip_time(mtime) -> tuple[int, ...]:
    try:
        t = time.gmtime(int(mtime or 0))
    except (OverflowError, OSError, ValueError):
        t = time.gmtime(0)
    return (1980, 1, 1, 0, 0, 0) if t.tm_year < 1980 else tuple(t)[:6] if t.tm_year <= 2107 else (2107, 12, 31, 23, 59, 58)


def extract(ctx: ToolContext, path: Path, zf: zipfile.ZipFile, password: str | None) -> dict[str, int | list[str]]:
    """Copia cada archivo del comprimido al ZIP abierto. Devuelve los recuentos y los nombres escritos."""
    import libarchive

    limit = min(MAX_UNCOMPRESSED, max(RATIO_FLOOR, path.stat().st_size * MAX_RATIO))
    counts: dict = {"files": 0, "links": 0, "renamed": 0, "names": [], "dirs": set()}
    total = seen = 0
    used: set[str] = set()
    try:
        with libarchive.file_reader(str(path), passphrase=password or None) as archive:
            for entry in archive:
                seen += 1
                if seen > MAX_MEMBERS:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"Más de {MAX_MEMBERS} entradas")
                try:
                    raw = entry.pathname or ""
                except UnicodeDecodeError:
                    raw = f"archivo-{seen}"
                name, changed = safe_name(raw)
                if entry.isdir:
                    if name:
                        counts["dirs"].add(name)
                    continue
                if not entry.isreg or entry.issym or entry.islnk:
                    counts["links"] += 1
                    continue
                if not name:
                    name, changed = f"archivo-{seen}", True
                counts["renamed"] += changed
                base, n = name, 2
                while name.lower() in used:
                    stem, dot, ext = base.rpartition(".")
                    name = f"{stem} ({n}).{ext}" if dot and stem else f"{base} ({n})"
                    n += 1
                used.add(name.lower())
                if "/" in name:
                    counts["dirs"].add(posixpath.dirname(name))
                info = zipfile.ZipInfo(name, date_time=_zip_time(entry.mtime))
                info.compress_type = zipfile.ZIP_DEFLATED
                with zf.open(info, "w", force_zip64=True) as out:
                    for block in entry.get_blocks():
                        total += len(block)
                        if total > limit:
                            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Archivo descomprimido demasiado grande")
                        out.write(block)
                counts["files"] += 1
                counts["names"].append(name)
    except libarchive.ArchiveError as exc:
        message = str(exc).lower()
        if ("encrypt" in message or "crypt" in message) and "unsupported" in message:
            # libarchive no descifra RAR ni 7z (solo ZIP): pedir la contraseña no serviría de nada.
            raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "archive_encrypted_unsupported") from exc
        if "passphrase" in message or "encrypt" in message or "password" in message or "decrypt" in message:
            if password:
                raise ToolError(ErrorCode.WRONG_PASSWORD, "archive_password_or_cipher") from exc
            raise ToolError(ErrorCode.PASSWORD_REQUIRED, "archive_password") from exc
        raise ToolError(ErrorCode.CORRUPT_FILE, "Comprimido ilegible") from exc
    if seen == 0:  # libarchive no protesta con un 7z o un RAR roto: simplemente no ve entradas
        raise ToolError(ErrorCode.CORRUPT_FILE, "archive_empty")
    counts["dirs"] = len({d for name in counts["dirs"] for d in _parents(name)})
    return counts


def _parents(name: str) -> list[str]:
    parts = name.split("/")
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def _notes(ctx: ToolContext, counts: dict) -> list[str]:
    t = NOTES.get(ctx.locale, NOTES["es"])
    notes = [t["summary"].format(files=counts["files"], dirs=counts["dirs"])] if counts["files"] else [t["empty"]]
    if counts["links"]:
        notes.append(t["links"].format(n=counts["links"]))
    if counts["renamed"]:
        notes.append(t["renamed"].format(n=counts["renamed"]))
    return notes


def run_to_zip(ctx: ToolContext) -> list[dict]:
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        stem = re.sub(r"\.tar$", "", Path(inp.name).stem, flags=re.I)
        name = f"{stem or 'archivo'}.zip"
        dst = ctx.output(name)
        with zipfile.ZipFile(dst, "w", allowZip64=True) as zf:
            counts = extract(ctx, inp.path, zf, ctx.secrets.get("contrasena"))
        outputs.append({"path": str(dst), "name": name, "note": " ".join(_notes(ctx, counts))})
    return with_batch_zip(ctx, outputs, f"{ctx.tool}.zip")


def run_extract(ctx: ToolContext) -> list[dict]:
    """Los archivos sueltos para descargarlos uno a uno (hasta 50) y un ZIP con todos, con sus carpetas."""
    t = NOTES.get(ctx.locale, NOTES["es"])
    inp = ctx.inputs[0]
    stem = re.sub(r"\.tar$", "", Path(inp.name).stem, flags=re.I) or "archivo"
    packed = ctx.work / "todo.zip"
    packed.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(packed, "w", allowZip64=True) as zf:
        counts = extract(ctx, inp.path, zf, ctx.secrets.get("contrasena"))
    notes = _notes(ctx, counts)
    outputs: list[dict] = []
    if 0 < counts["files"] <= MAX_LISTED:
        bases = [posixpath.basename(m).lower() for m in counts["names"]]
        with zipfile.ZipFile(packed) as zf:
            for member in counts["names"]:
                # El nombre del archivo; si se repite en otra carpeta, con la carpeta delante («fotos_portada.jpg»).
                shown = posixpath.basename(member) if bases.count(posixpath.basename(member).lower()) == 1 else member.replace("/", "_")
                dst = ctx.output(shown)
                with zf.open(member) as src, open(dst, "wb") as out:
                    while chunk := src.read(1 << 20):
                        out.write(chunk)
                outputs.append({"path": str(dst), "name": shown, "note": None})
    elif counts["files"] > MAX_LISTED:
        notes.append(t["only_zip"].format(n=MAX_LISTED))
    if counts["files"] != 1:
        name = derived_name(stem, "-extraido", "zip")
        dst = ctx.output(name)
        packed.replace(dst)
        outputs.append({"path": str(dst), "name": name, "note": "zip"})
    if outputs:
        outputs[0]["note"] = " ".join(notes)
    else:
        outputs.append({"path": str(packed), "name": derived_name(stem, "-extraido", "zip"), "note": " ".join(notes)})
    return outputs


def run(ctx: ToolContext) -> list[dict]:
    return run_extract(ctx) if ctx.tool == "extraer-archivo-online" else run_to_zip(ctx)
