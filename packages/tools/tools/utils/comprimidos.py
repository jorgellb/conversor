"""Comprimidos (7.13, F6-E, D-217): rar-a-zip, 7z-a-zip, tar-a-zip y extraer-archivo-online con libarchive.

libarchive (BSD-2-Clause, con libarchive-c) lee RAR 4 y 5, 7z, ZIP, tar y tar comprimido con gzip, bzip2, xz o zstd; nunca
unrar ni p7zip (11). Cada entrada se copia por bloques con límites de bombas (12.3): 10 000 entradas, 2 GB descomprimidos y
una relación de 1000 a 1 sobre el archivo subido. Rutas seguras (16.4): sin `..`, sin raíz, sin letra de unidad y sin
barras invertidas; los enlaces simbólicos, los duros y los dispositivos no se extraen.
"""
from __future__ import annotations

import posixpath
from collections import Counter
import re
import time
import zipfile
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.zipguard import MAX_MEMBERS, MAX_UNCOMPRESSED
from tools.base import ToolContext, derived_name
from tools.pdf.common import with_batch_zip

MAX_RATIO = 100  # 12.3
RATIO_FLOOR = 100 * 1024 * 1024  # la relación solo cuenta por encima de 100 MB descomprimidos
MAX_PART_BYTES = 255  # lo que admiten los sistemas de archivos en cada nombre
MAX_PATH_BYTES = 1024
# Formatos que acepta cada herramienta según libarchive (`format_name`): ni mtree, ni cpio, ni ISO, ni un .gz suelto, que
# libarchive también leería (un mtree puede pedir archivos del propio servidor).
FORMATS = {"rar-a-zip": ("rar",), "7z-a-zip": ("7-zip",), "tar-a-zip": ("tar", "ustar", "pax"),
           "extraer-archivo-online": ("zip", "rar", "7-zip", "tar", "ustar", "pax")}
MAX_LISTED = 50  # extraer-archivo-online: hasta 50 archivos sueltos; más, solo el ZIP

NOTES = {
    "es": {"summary": "{files} archivo(s) en {dirs} carpeta(s).", "links": "{n} enlace(s) o archivo(s) especiales no se han extraído.",
           "renamed": "{n} ruta(s) peligrosas (con «..» o absolutas) se han guardado dentro de la carpeta del archivo.",
           "only_zip": "Tiene más de {n} archivos: descarga el ZIP con todos.", "empty": "El archivo comprimido está vacío."},
    "en": {"summary": "{files} file(s) in {dirs} folder(s).", "links": "{n} link(s) or special file(s) were not extracted.",
           "renamed": "{n} unsafe path(s) (with “..” or absolute) were stored inside the archive's folder.",
           "only_zip": "It has more than {n} files: download the ZIP with all of them.", "empty": "The archive is empty."},
}


def _short(part: str, limit: int) -> str:
    """Un nombre recortado a `limit` bytes en UTF-8, conservando la extensión."""
    if len(part.encode("utf-8")) <= limit:
        return part
    stem, dot, ext = part.rpartition(".")
    ext = ext if dot and len(ext) <= 10 else ""
    stem = part if not ext else stem
    keep = limit - len(ext.encode()) - 1 - 2
    cut = stem.encode("utf-8")[:keep].decode("utf-8", errors="ignore")
    return f"{cut}~" + (f".{ext}" if ext else "")


def safe_name(raw: str) -> tuple[str, bool]:
    """Ruta relativa segura y si ha habido que cambiarla («../../etc/passwd» → «etc/passwd»; nombres de más de 255
    bytes o rutas de más de 1024, recortados)."""
    name = raw.replace("\\", "/")
    name = re.sub(r"^[A-Za-z]:/", "/", name)  # solo una letra de unidad seguida de barra («a:b.txt» es un nombre)
    parts = [p for p in name.split("/") if p not in ("", ".")]
    clean = [_short(p.replace("\x00", ""), MAX_PART_BYTES) for p in parts if p != ".." and p.strip(".")]
    while clean and len("/".join(clean).encode("utf-8")) > MAX_PATH_BYTES:
        clean = clean[1:] if len(clean) > 1 else [_short(clean[0], MAX_PATH_BYTES)]
    joined = "/".join(clean)
    changed = name.startswith("/") or joined != "/".join(parts)
    return joined, changed


def _entry_name(entry, zip_like: bool, n: int) -> str:
    """El nombre de la entrada; libarchive-c devuelve bytes si no es UTF-8 (CP437 en los ZIP antiguos de Windows,
    Windows-1252 o Latin-1 en tar y RAR)."""
    try:
        raw = entry.pathname
    except UnicodeError:
        raw = None
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            raw = raw.decode("cp437" if zip_like else "cp1252", errors="replace")
    return raw if isinstance(raw, str) and raw else f"archivo-{n}"


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
    used: dict[str, int] = {}  # nombre en minúsculas → siguiente número para las copias
    allowed = FORMATS.get(ctx.tool, FORMATS["extraer-archivo-online"])
    try:
        with libarchive.file_reader(str(path), passphrase=password or None) as archive:
            for entry in archive:
                seen += 1
                if seen == 1:
                    fmt = (archive.format_name or b"").decode("ascii", "replace").lower() if isinstance(archive.format_name, bytes) \
                        else str(archive.format_name or "").lower()
                    if not any(f in fmt for f in allowed):
                        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "archive_format")
                    zip_like = "zip" in fmt and "7-zip" not in fmt
                if seen > MAX_MEMBERS:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"Más de {MAX_MEMBERS} entradas")
                if not zip_like and libarchive.ffi.libarchive.archive_entry_is_encrypted(entry._entry_p):
                    # libarchive no descifra RAR ni 7z: con datos cifrados entregaría el texto cifrado como si fuera bueno.
                    raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "archive_encrypted_unsupported")
                name, changed = safe_name(_entry_name(entry, zip_like, seen))
                total += len(name.encode("utf-8")) + 64  # los nombres también ocupan (y pesan en memoria)
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
                base = name
                while name.lower() in used:
                    n = used[base.lower()] = used.get(base.lower(), 1) + 1
                    stem, dot, ext = base.rpartition(".")
                    name = f"{stem} ({n}).{ext}" if dot and stem and "/" not in ext else f"{base} ({n})"
                used.setdefault(name.lower(), 1)
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
        if "crypt" in message and any(w in message for w in ("unsupported", "not supported", "unavailable")):
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
        bases = Counter(posixpath.basename(m).lower() for m in counts["names"])
        shown_used: set[str] = set()
        with zipfile.ZipFile(packed) as zf:
            for member in counts["names"]:
                # El nombre del archivo; si se repite en otra carpeta, con la carpeta delante («fotos_portada.jpg»), y
                # con un número si aun así coincide con otro.
                shown = posixpath.basename(member) if bases[posixpath.basename(member).lower()] == 1 else member.replace("/", "_")
                candidate, k = shown, 2
                while candidate.lower() in shown_used:
                    stem, dot, ext = shown.rpartition(".")
                    candidate, k = (f"{stem} ({k}).{ext}" if dot and stem else f"{shown} ({k})"), k + 1
                shown = candidate
                shown_used.add(shown.lower())
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
