"""latex-a-pdf (7.13, F6-K, D-227): Tectonic 0.17 (MIT) con XeTeX, aislado con Landlock.

Un .tex puede leer cualquier archivo con `\\input{/etc/hostname}` y `--untrusted` de Tectonic no lo impide (solo quita
`\\write18`): el motor corre con Landlock (tools/sandbox.py) y solo ve el directorio del trabajo (lectura y escritura), su
caché de paquetes (lectura), su propio binario y las fuentes del sistema; sin TCP con Linux 6.7 o posterior. Además
`--only-cached`: los paquetes vienen de la caché que se llena al construir la imagen, nunca de la red (16.4).
Si no compila, se entrega el registro con el primer error en la nota.
"""
from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.zipguard import check_zip
from tools.base import ToolContext, derived_name, run_engine
from tools.pdf.common import with_batch_zip

MAX_TEX_BYTES = 5 * 1024 * 1024
MAX_PROJECT_BYTES = 200 * 1024 * 1024
FONT_DIRS = (Path("/usr/share/fonts"), Path("/etc/fonts"), Path("/usr/share/fontconfig"), Path("/var/cache/fontconfig"))

MAX_LOG_BYTES = 500_000
DOCCLASS = re.compile(rb"^[^%\n]*\\documentclass", re.M)
NOTES = {
    "es": {"ok": "Compilado con Tectonic (XeTeX).", "failed": "No se ha podido compilar: {error} Te dejamos el registro para que veas el detalle.",
           "main": "Documento principal: {name}.", "cites": "Hay citas sin resolver ({keys}): revisa las claves y el archivo .bib.",
           "bibtex": "BibTeX ha avisado de problemas en la bibliografía: «{msg}».", "refs": "Hay referencias cruzadas sin resolver.",
           "denied": "«el documento intenta leer o escribir un archivo fuera del proyecto»", "unknown": "«error de LaTeX sin detalle»"},
    "en": {"ok": "Compiled with Tectonic (XeTeX).", "failed": "It could not be compiled: {error} Here is the log so you can see the details.",
           "main": "Main document: {name}.", "cites": "There are unresolved citations ({keys}): check the keys and the .bib file.",
           "bibtex": "BibTeX reported problems in the bibliography: «{msg}».", "refs": "There are unresolved cross-references.",
           "denied": "«the document tries to read or write a file outside the project»", "unknown": "«LaTeX error without details»"},
}


def _project(ctx: ToolContext, inp, n: int) -> tuple[Path, str]:
    """El directorio del proyecto en el trabajo y el nombre del .tex principal (el de \\documentclass, mejor main.tex)."""
    folder = ctx.work / f"tex-{n}"
    folder.mkdir(parents=True, exist_ok=True)
    ext = (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()
    if ext != "zip":
        if inp.path.stat().st_size > MAX_TEX_BYTES:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Archivo .tex de más de 5 MB")
        shutil.copyfile(inp.path, folder / "documento.tex")
        return folder, "documento.tex"
    check_zip(inp.path, max_uncompressed=MAX_PROJECT_BYTES)
    candidates = []
    try:
        with zipfile.ZipFile(inp.path) as zf:
            for info in zf.infolist():
                parts = [p for p in info.filename.replace("\\", "/").split("/") if p not in ("", ".")]
                if info.is_dir() or not parts or ".." in parts or parts[0] == "__MACOSX" or any(p.startswith(".") for p in parts):
                    continue
                dst = folder.joinpath(*parts)
                dst.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(dst, "wb") as out:
                    shutil.copyfileobj(src, out)
                if dst.suffix.lower() == ".tex" and dst.stat().st_size <= MAX_TEX_BYTES:
                    if DOCCLASS.search(dst.read_bytes()[:200_000]):  # un \documentclass comentado no cuenta
                        candidates.append(str(dst.relative_to(folder)))
    except (zipfile.BadZipFile, OSError, EOFError) as exc:
        # CRC erróneo o un archivo y una carpeta con el mismo nombre («a.tex» y «a.tex/b»).
        raise ToolError(ErrorCode.CORRUPT_FILE, "ZIP del proyecto dañado o con rutas que chocan") from exc
    if not candidates:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "latex_no_main")
    # Primero el menos profundo (un «old/main.tex» antiguo no gana al documento de la raíz) y, a igual profundidad,
    # los nombres habituales.
    main = min(candidates, key=lambda c: (c.count("/"), Path(c).name.lower() not in ("main.tex", "documento.tex", "paper.tex", "tesis.tex"), c))
    return folder, main


def _tail(path: Path, limit: int = MAX_LOG_BYTES) -> str:
    """El final de un registro sin leerlo entero (el documento puede escribir cientos de MB con \\message)."""
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - limit))
        return f.read().decode("utf-8", "replace")


def warnings(folder: Path, main: str, t: dict) -> list[str]:
    """Citas y referencias sin resolver y avisos de BibTeX: Tectonic termina bien aunque la bibliografía falle."""
    notes = []
    log_path = folder / Path(main).with_suffix(".log")
    log = _tail(log_path) if log_path.exists() else ""
    keys = list(dict.fromkeys(re.findall(r"Citation `([^']{1,80})' (?:on page \d+ )?undefined", log)))
    if keys:
        notes.append(t["cites"].format(keys=", ".join(keys[:5]) + ("…" if len(keys) > 5 else "")))
    elif "There were undefined references" in log:
        notes.append(t["refs"])
    blg = folder / Path(main).with_suffix(".blg")
    if blg.exists() and not keys:
        text = _tail(blg, 100_000)
        m = re.search(r"^(?:Warning--|I couldn't open|I found no)(.{1,150})$", text, re.M)
        if m:
            notes.append(t["bibtex"].format(msg=re.sub(r"/[\w./-]+/", "", m.group(0)).strip()))
    return notes


def first_error(log: str, line_word: str = "línea") -> str:
    """La primera línea «! …» del registro con su número de línea, sin rutas del servidor."""
    m = re.search(r"^! (.+?)$(?:.{0,4000}?^l\.(\d+))?", log, re.M | re.S)
    if not m:
        return ""
    text = re.sub(r"/[\w./-]+/", "", m.group(1)).strip()[:200]
    return f"«{text}»" + (f" ({line_word} {m.group(2)})" if m.group(2) else "")


def run(ctx: ToolContext) -> list[dict]:
    t = NOTES.get(ctx.locale, NOTES["es"])
    exe = Path(ctx.settings.TECTONIC_BIN)
    cache = Path(ctx.settings.TECTONIC_CACHE)
    if not exe.is_file() or not cache.is_dir():
        raise ToolError(ErrorCode.ENGINE_FAILED, "tectonic no está instalado")
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        folder, main = _project(ctx, inp, n)
        result = run_engine([str(exe), "-X", "compile", "--untrusted", "--only-cached", "--keep-logs", "--keep-intermediates", main],
                            cwd=folder, timeout=600, mem_mb=2048, extra_env={"TECTONIC_CACHE_DIR": str(cache)},
                            ok_codes=tuple(range(256)), max_file_mb=512,
                            landlock=[(folder, "rw"), (cache, "r"), (exe.parent, "rx"), *((d, "r") for d in FONT_DIRS)])
        pdf = folder / Path(main).with_suffix(".pdf")
        if result.returncode == 0 and pdf.exists():
            from tools.office.office_a_pdf import select_pages

            name = derived_name(inp.name, "", "pdf")
            dst = ctx.output(name)
            shutil.move(pdf, dst)
            select_pages(dst, "todas", ctx.plan.pdf_pages)  # el límite de páginas del plan también aquí
            notes = [t["ok"]] + ([t["main"].format(name=main)] if (inp.ext or "").lower() == "zip" else [])
            notes += warnings(folder, Path(main).as_posix(), t)
            outputs.append({"path": str(dst), "name": name, "note": " ".join(notes)})
            continue
        log_path = folder / Path(main).with_suffix(".log")
        stderr = re.sub(r"(?<![\w])/(?:[\w.+-]+/)+", "", result.stderr.decode("utf-8", "replace"))  # sin rutas del servidor
        log = _tail(log_path) if log_path.exists() else stderr
        error = first_error(log + "\n" + stderr, "línea" if ctx.locale == "es" else "line")
        if not error:
            error = t["denied"] if "Permission denied" in stderr or "os error 13" in stderr else t["unknown"]
        name = derived_name(inp.name, "-registro", "log")
        dst = ctx.output(name)
        dst.write_text(log[-MAX_LOG_BYTES:], encoding="utf-8")
        outputs.append({"path": str(dst), "name": name, "note": t["failed"].format(error=error)})
    return with_batch_zip(ctx, outputs, "latex-pdf.zip")
