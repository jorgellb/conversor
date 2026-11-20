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

NOTES = {
    "es": {"ok": "Compilado con Tectonic (XeTeX).", "failed": "No se ha podido compilar: {error} Te dejamos el registro para que veas el detalle.",
           "main": "Documento principal: {name}."},
    "en": {"ok": "Compiled with Tectonic (XeTeX).", "failed": "It could not be compiled: {error} Here is the log so you can see the details.",
           "main": "Main document: {name}."},
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
                head = dst.read_bytes()[:200_000]
                if rb"\documentclass" in head:
                    candidates.append(str(dst.relative_to(folder)))
    if not candidates:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "latex_no_main")
    main = min(candidates, key=lambda c: (Path(c).name.lower() not in ("main.tex", "documento.tex", "paper.tex", "tesis.tex"),
                                          c.count("/"), c))
    return folder, main


def first_error(log: str, line_word: str = "línea") -> str:
    """La primera línea «! …» del registro con su número de línea, sin rutas del servidor."""
    m = re.search(r"^! (.+?)$(?:.*?^l\.(\d+))?", log, re.M | re.S)
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
        result = run_engine([str(exe), "-X", "compile", "--untrusted", "--only-cached", "--keep-logs", main],
                            cwd=folder, timeout=600, mem_mb=2048, extra_env={"TECTONIC_CACHE_DIR": str(cache)},
                            ok_codes=tuple(range(256)),
                            landlock=[(folder, "rw"), (cache, "r"), (exe.parent, "rx"), *((d, "r") for d in FONT_DIRS)])
        pdf = folder / Path(main).with_suffix(".pdf")
        if result.returncode == 0 and pdf.exists():
            name = derived_name(inp.name, "", "pdf")
            dst = ctx.output(name)
            shutil.move(pdf, dst)
            notes = [t["ok"]] + ([t["main"].format(name=main)] if (inp.ext or "").lower() == "zip" else [])
            outputs.append({"path": str(dst), "name": name, "note": " ".join(notes)})
            continue
        log_path = folder / Path(main).with_suffix(".log")
        log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else result.stderr.decode("utf-8", "replace")
        error = first_error(log + "\n" + result.stderr.decode("utf-8", "replace"), "línea" if ctx.locale == "es" else "line") or "?"
        name = derived_name(inp.name, "-registro", "log")
        dst = ctx.output(name)
        dst.write_text(log[-500_000:], encoding="utf-8")
        outputs.append({"path": str(dst), "name": name, "note": t["failed"].format(error=error)})
    return with_batch_zip(ctx, outputs, "latex-pdf.zip")
