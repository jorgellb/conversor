"""Buzones de correo (7.13, F6-J, D-225): mbox-a-eml, mbox-a-pdf, pst-a-mbox y pst-a-pdf.

En `workermedia`, junto a eml-a-pdf, para reutilizar su lectura y su maquetación (tools/media/correo.py: cabeceras, HTML
saneado con nh3 y Chromium de `gotenberg` sin red). mbox con `mailbox` de la biblioteca estándar, leyendo cada mensaje
tal cual (`get_bytes`); PST con `readpst` de libpst (GPL), siempre como programa externo (11), que deja un mbox por
carpeta. Categoría `data` con «mbox» o «pst» en el nombre: nunca IA (6.6 y 16.3).
"""
from __future__ import annotations

import mailbox
import re
import shutil
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name, run_engine, zip_files

MAX_MESSAGES = 20_000
MAX_PDF_MESSAGES = 200
MAX_PST_BYTES = 2 * 1024**3

NOTES = {
    "es": {"messages": "{n} mensaje(s).", "folders": "{n} carpeta(s).", "cut": "El PDF incluye los {n} primeros mensajes (de {total}); para el buzón entero, usa MBOX a EML.",
           "bad": "{n} mensaje(s) dañados no se han podido leer."},
    "en": {"messages": "{n} message(s).", "folders": "{n} folder(s).", "cut": "The PDF includes the first {n} messages (of {total}); for the whole mailbox, use MBOX to EML.",
           "bad": "{n} damaged message(s) could not be read."},
}


def _t(ctx: ToolContext) -> dict:
    return NOTES.get(ctx.locale, NOTES["es"])


class Box:
    """Un mbox abierto: solo guarda la posición de cada mensaje y lo lee cuando hace falta (D-230: un buzón de 1 GB no
    se carga entero en memoria)."""

    def __init__(self, path: Path) -> None:
        try:
            self.box = mailbox.mbox(str(path), create=False)
            self.keys = list(self.box.iterkeys())
        except (mailbox.Error, OSError, UnicodeDecodeError) as exc:
            raise ToolError(ErrorCode.CORRUPT_FILE, "mbox") from exc

    def read(self, key) -> bytes:
        return self.box.get_bytes(key)

    def head(self, key) -> bytes:
        with self.box.get_file(key) as f:
            return f.read(16384)

    def close(self) -> None:
        self.box.close()


def messages(path: Path, limit: int = MAX_MESSAGES) -> list[tuple[Box, object]]:
    """Referencias a los mensajes de un mbox (cada uno se lee con sus bytes originales, sin la línea «From »)."""
    box = Box(path)
    if len(box.keys) > limit:
        box.close()
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "mail_too_many")
    if not box.keys:
        box.close()
        raise ToolError(ErrorCode.CORRUPT_FILE, "mail_empty")
    return [(box, key) for key in box.keys]


def _close(refs) -> None:
    for box in {id(b): b for b, _ in refs}.values():
        box.close()


def _subject_name(data: bytes, n: int, used: set[str]) -> str:
    import email
    import email.policy

    try:
        subject = str(email.message_from_bytes(data, policy=email.policy.default).get("subject") or "")
    except Exception:  # noqa: BLE001 - una cabecera mal codificada no impide guardar el mensaje
        subject = ""
    clean = re.sub(r"[^\w .,()-]+", "_", subject, flags=re.UNICODE).strip(" ._")[:80] or "mensaje"
    name = f"{n:05d} - {clean}.eml"  # cinco cifras: el orden se mantiene hasta MAX_MESSAGES
    while name.lower() in used:
        name = f"{n:05d} - {clean} ({len(used)}).eml"
    used.add(name.lower())
    return name


def _date_of(data: bytes) -> datetime:
    m = re.search(rb"^Date:\s*(.+?)\r?$", data[:8192], re.MULTILINE | re.IGNORECASE)
    try:
        value = parsedate_to_datetime(m.group(1).decode("ascii", "replace")) if m else None
    except (TypeError, ValueError, IndexError):
        value = None
    if value is None:
        return datetime.max.replace(tzinfo=timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def to_eml_zip(ctx: ToolContext, msgs, stem: str, folder: str = "") -> tuple[Path, int]:
    work = ctx.work / f"eml-{stem}"
    work.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    files = []
    n = 0
    for box, key in msgs:
        data = box.read(key)
        if not data.strip():
            continue
        n += 1
        name = _subject_name(data, n, used)
        path = work / f"{n:05d}.eml"
        path.write_bytes(data)
        files.append((path, f"{folder}/{name}" if folder else name))
    if not files:
        raise ToolError(ErrorCode.CORRUPT_FILE, "mail_empty")
    dst = ctx.work / f"{stem}-eml.zip"
    zip_files(files, dst)
    return dst, len(files)


def to_pdf(ctx: ToolContext, msgs, stem: str) -> tuple[Path, list[str]]:
    """Cada mensaje como en eml-a-pdf (cabeceras, cuerpo e imágenes incrustadas), ordenados por fecha, en un PDF con un
    marcador por mensaje; los adjuntos solo si se piden."""
    from tools.media import correo
    from tools.office import gotenberg
    from tools.office.anyto import merge_with_bookmarks
    from tools.office.anyto import to_pdf as office_to_pdf

    t, o = _t(ctx), ctx.options
    labels = correo.LABELS.get(ctx.locale, correo.LABELS["es"])
    notes = []
    # Para ordenar basta la cabecera de cada mensaje; el mensaje entero solo se lee si entra en el PDF.
    ordered = sorted(msgs, key=lambda ref: _date_of(ref[0].head(ref[1]))) if o.orden == "fecha" else list(msgs)
    if len(ordered) > MAX_PDF_MESSAGES:
        notes.append(t["cut"].format(n=MAX_PDF_MESSAGES, total=len(ordered)))
        ordered = ordered[:MAX_PDF_MESSAGES]
    parts, bad = [], 0
    for n, (box, key) in enumerate(ordered):
        ctx.report(n / len(ordered), None)
        data = box.read(key)
        if not data.strip():
            continue
        try:
            mail = correo.parse_eml(data)
        except ToolError:
            bad += 1
            continue
        cited = {c.strip("<>") for c in re.findall(r"cid:([^\"'\s>)]+)", mail.html or "", flags=re.IGNORECASE)}
        attachments = [a for a in mail.attachments if not (a.cid and a.cid in cited)][: correo.MAX_ATTACHMENTS]
        files = correo.render(mail, labels, [a.name for a in attachments])
        page = ctx.work / f"mensaje-{n}.pdf"
        page.write_bytes(gotenberg.chromium_html_files(ctx.settings.GOTENBERG_URL, files,
                                                       gotenberg.page_fields(o.papel, "vertical", 15, True, False, "print")))
        parts.append((mail.subject or labels["message"], page))
        if o.adjuntos:
            for k, att in enumerate(attachments):
                folder = ctx.work / f"adj-{n}-{k}"
                folder.mkdir(parents=True, exist_ok=True)
                src = folder / (re.sub(r"[^A-Za-z0-9._-]+", "_", att.name).strip("._") or "adjunto")
                src.write_bytes(att.data)
                try:
                    pdf = office_to_pdf(ctx, src, att.name, f"{n}-{k}")
                except ToolError as exc:
                    if exc.transient:
                        raise
                    pdf = None
                if pdf is not None:
                    parts.append((f"  {att.name}", pdf))
    if not parts:
        raise ToolError(ErrorCode.CORRUPT_FILE, "mail_empty")
    if bad:
        notes.append(t["bad"].format(n=bad))
    dst = ctx.work / f"{stem}.pdf"
    merge_with_bookmarks(parts, dst, ctx.plan.pdf_pages)
    return dst, notes


def readpst(ctx: ToolContext, path: Path) -> list[tuple[str, Path]]:
    """Las carpetas de un PST como mbox, con `readpst` (libpst) aparte: entorno vacío, tiempo y memoria limitados."""
    if path.stat().st_size > MAX_PST_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "PST de más de 2 GB")
    exe = shutil.which("readpst", path="/usr/bin:/usr/local/bin") or ctx.settings.READPST_BIN
    if not exe or not Path(exe).is_file():
        raise ToolError(ErrorCode.ENGINE_FAILED, "readpst no está instalado")
    out = ctx.work / "pst"
    out.mkdir(parents=True, exist_ok=True)
    src = ctx.work / "buzon.pst"
    shutil.copyfile(path, src)
    # -r: una carpeta del sistema de archivos por carpeta del PST, con su mbox; -b: sin los cuerpos RTF aparte; -q: sin ruido.
    # readpst (C, GPL) lee un binario del usuario y crea carpetas con los nombres del PST («..» incluido): con Landlock
    # solo puede escribir dentro del trabajo y leer su programa y las bibliotecas (D-230); cada archivo, como mucho 2 GB.
    exe_path = Path(exe).resolve()
    libs = [(Path(d), "rx") for d in ("/lib", "/lib64", "/usr/lib", "/usr/lib64", "/usr/local/lib")]
    result = run_engine([str(exe_path), "-q", "-r", "-b", "-j", "0", "-o", str(out.relative_to(ctx.work)), src.name], cwd=ctx.work,
                        timeout=1500, mem_mb=2048, ok_codes=tuple(range(256)), max_file_mb=2048,
                        landlock=[(ctx.work, "rw"), (exe_path, "rx"), (Path("/etc/ld.so.cache"), "r"), *libs])
    boxes = sorted(p for p in out.rglob("*") if p.is_file() and not p.is_symlink() and p.stat().st_size and p.name == "mbox")
    if not boxes:
        raise ToolError(ErrorCode.CORRUPT_FILE, f"pst (readpst {result.returncode})")
    named = []
    for p in boxes:
        rel = p.parent.relative_to(out)
        named.append((rel.as_posix() if rel != Path(".") else "Buzón", p))
    return named


def run(ctx: ToolContext) -> list[dict]:
    t = _t(ctx)
    outputs = []
    for inp in ctx.inputs:
        stem = Path(inp.name).stem or "buzon"
        if ctx.tool == "mbox-a-eml":
            msgs = messages(inp.path)
            try:
                packed, count = to_eml_zip(ctx, msgs, stem)
            finally:
                _close(msgs)
            name = derived_name(inp.name, "-eml", "zip")
            note = t["messages"].format(n=count)
        elif ctx.tool == "mbox-a-pdf":
            msgs = messages(inp.path)
            try:
                pdf, notes = to_pdf(ctx, msgs, stem)
            finally:
                _close(msgs)
            packed, name, note = pdf, derived_name(inp.name, "", "pdf"), " ".join([t["messages"].format(n=len(msgs)), *notes])
        elif ctx.tool == "pst-a-mbox":
            boxes = readpst(ctx, inp.path)
            packed = ctx.work / f"{stem}-mbox.zip"
            zip_files([(p, f"{folder}.mbox") for folder, p in boxes], packed)
            name = derived_name(inp.name, "-mbox", "zip")
            note = t["folders"].format(n=len(boxes))
        else:  # pst-a-pdf
            # Todas las carpetas juntas, con el límite de mensajes para el PST entero; una carpeta vacía no lo corta.
            msgs = []
            try:
                for _folder, p in readpst(ctx, inp.path):
                    try:
                        msgs += messages(p, MAX_MESSAGES - len(msgs))
                    except ToolError as exc:
                        if exc.detail != "mail_empty" and exc.code != ErrorCode.CORRUPT_FILE:
                            raise
                if not msgs:
                    raise ToolError(ErrorCode.CORRUPT_FILE, "mail_empty")
                pdf, notes = to_pdf(ctx, msgs, stem)
            finally:
                _close(msgs)
            packed, name, note = pdf, derived_name(inp.name, "", "pdf"), " ".join([t["messages"].format(n=len(msgs)), *notes])
        dst = ctx.output(name)
        shutil.move(packed, dst)
        outputs.append({"path": str(dst), "name": name, "note": note})
    return outputs
