"""Conversiones de mallas de F7-A y F7-B (7.18, D-244, D-248 y D-249): cada archivo se convierte en un proceso hijo
(`child.py`) con Landlock, memoria de datos y tiempo acotados. El recuento previo de triángulos (API y trabajador) es un
filtro barato, no un límite de memoria: un 3MF con mil instancias de una malla, un PLY de caras de 255 lados o un OBJ con
millones de vértices sueltos pesan mucho más de lo que cuentan, y con el hijo eso acaba en LIMIT_EXCEEDED y no en el
trabajador muerto.

La conversión en sí (unidades, escala, ejes, piezas y colores) está en `pipeline.py`.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import core
import tools
from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name, run_engine
from tools.mesh.extra import _child_landlock
from tools.mesh.pipeline import TARGET  # noqa: F401 - lo usan las pruebas
from tools.pdf.common import with_batch_zip

CHILD = Path(__file__).with_name("child.py")


def _code_paths() -> list[str]:
    return [str(Path(core.__file__).resolve().parents[1]), str(Path(tools.__file__).resolve().parents[1])]


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        ext = (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()
        work = ctx.work / f"malla-{n}"
        out_dir = work / "salida"
        out_dir.mkdir(parents=True, exist_ok=True)
        src = work / f"original.{ext}"
        shutil.copyfile(inp.path, src)
        target = TARGET[ctx.tool] or o.formato
        job = {"paths": _code_paths(), "src": str(src), "ext": ext, "tool": ctx.tool, "options": o.model_dump(), "locale": ctx.locale,
               "max_triangles": ctx.plan.mesh_triangles, "stem": Path(derived_name(inp.name, "", target)).stem,
               "out_dir": str(out_dir), "result": str(work / "resultado.json")}
        (work / "trabajo.json").write_text(json.dumps(job), encoding="utf-8")
        env = {"LD_LIBRARY_PATH": ctx.settings.ENGINES_LIBRARY_PATH} if ctx.settings.ENGINES_LIBRARY_PATH else {}
        env["PYTHONUTF8"] = "1"
        landlock = _child_landlock(work, ctx.settings) + [(Path(p), "rx") for p in job["paths"]]
        res = run_engine([sys.executable, "-I", str(CHILD), "trabajo.json"], cwd=work, timeout=540, mem_mb=ctx.settings.MESH_MEMORY_MB,
                         limit_data=True, extra_env=env, ok_codes=(0, 2, 5), max_file_mb=4096, landlock=landlock)
        result = work / "resultado.json"
        if res.returncode == 5 or (res.returncode != 0 and not result.exists()):
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "mesh_memory")
        data = json.loads(result.read_text(encoding="utf-8"))
        if "error" in data:
            raise ToolError(data["error"]["code"], data["error"].get("detail"))
        for item in data["outputs"]:
            dst = ctx.output(item["name"])
            shutil.move(item["file"], dst)
            outputs.append({"path": str(dst), "name": item["name"], "note": item["note"]})
        shutil.rmtree(work, ignore_errors=True)
    return with_batch_zip(ctx, outputs, f"modelos-{TARGET[ctx.tool] or o.formato}.zip")
