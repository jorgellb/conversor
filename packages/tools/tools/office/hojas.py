"""ods-a-xlsx y xlsx-a-ods (7.12, F6-B1, D-213): LibreOffice Calc local de `workeroffice`.

Perfil propio dentro del trabajo, entorno vacío, sin red (la red de workeroffice no sale) y sin macros: el modo sin
interfaz no las ejecuta al convertir. Los ZIP de xlsx y ods se comprueban antes (bomba, rutas).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.zipguard import check_zip
from tools.base import ToolContext, derived_name, run_engine
from tools.pdf.common import with_batch_zip

TARGETS = {"ods-a-xlsx": ("xlsx", "xlsx:Calc MS Excel 2007 XML"), "xlsx-a-ods": ("ods", "ods:calc8")}


def libreoffice(ctx: ToolContext, src: Path, target: str) -> Path:
    profile = ctx.work / "lo-perfil"
    outdir = ctx.work / f"lo-{src.stem}"
    outdir.mkdir(parents=True, exist_ok=True)
    soffice = shutil.which("soffice") or "soffice"
    run_engine([soffice, f"-env:UserInstallation=file://{profile}", "--headless", "--norestore", "--nologo",
                "--convert-to", target, "--outdir", str(outdir), str(src)], cwd=ctx.work, timeout=600, mem_mb=3072)
    produced = outdir / f"{src.stem}.{target.split(':')[0]}"
    if not produced.exists() or produced.stat().st_size == 0:
        raise ToolError(ErrorCode.CORRUPT_FILE, "LibreOffice no ha podido abrir la hoja")
    return produced


def run(ctx: ToolContext) -> list[dict]:
    ext, target = TARGETS[ctx.tool]
    outputs = []
    ctx.work.mkdir(parents=True, exist_ok=True)
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        in_ext = (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()
        if in_ext != "xls":
            check_zip(inp.path)
        src = ctx.work / f"hoja-{n}.{in_ext}"
        shutil.copyfile(inp.path, src)
        produced = libreoffice(ctx, src, target)
        name = derived_name(inp.name, "", ext)
        dst = ctx.output(name)
        shutil.move(produced, dst)
        outputs.append({"path": str(dst), "name": name, "note": None})
    return with_batch_zip(ctx, outputs, f"{ctx.tool}.zip")
