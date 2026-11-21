"""scad-a-stl y scad-a-3mf (7.19, F7-E, D-252): OpenSCAD (GPL, programa externo, 11) en sandbox.

- OpenSCAD lee lo que el modelo pida (`include`, `use`, `import()`, `surface()`): con Landlock solo ve la carpeta del
  trabajo, su programa, sus bibliotecas y las fuentes del sistema (7.19: sin acceso fuera del directorio del trabajo).
- Se admite un .scad o un ZIP con el .scad principal y lo que incluye (el único .scad de la raíz o el que se llama como el
  ZIP); el ZIP pasa por `check_zip` y se extrae sin rutas que escapen.
- Las variables del personalizador (`nombre = valor`, una por línea) van con `-D` y solo como literales: números,
  verdadero o falso, texto entre comillas o vectores de números. Nada de expresiones.
- El STL de OpenSCAD pasa por el proceso hijo de las mallas (D-249): STL binario o 3MF con unidades en milímetros.
"""
from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.zipguard import check_zip
from tools.base import ToolContext, run_engine
from tools.mesh.convert import convert_path
from tools.pdf.common import with_batch_zip

NAME = re.compile(r"^\$?[A-Za-z_][A-Za-z0-9_]{0,63}$")
LITERAL = re.compile(r'^(-?\d+(\.\d+)?([eE][-+]?\d+)?|true|false|"[^"\\\n]{0,200}"|\[\s*-?\d+(\.\d+)?(\s*,\s*-?\d+(\.\d+)?){0,15}\s*\])$')
FN = {"modelo": None, "baja": 24, "media": 64, "alta": 128}
MAX_SCAD_FILES = 200


def parse_variables(text: str) -> list[str]:
    """Las líneas `nombre = valor` del personalizador como argumentos `-D` (solo literales)."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        if "=" not in line:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "scad_variable")
        name, value = (part.strip() for part in line.split("=", 1))
        value = value.rstrip(";").strip()
        if not NAME.match(name) or not LITERAL.match(value):
            raise ToolError(ErrorCode.INVALID_OPTIONS, "scad_variable")
        out += ["-D", f"{name}={value}"]
    if len(out) > 100:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "scad_variable")
    return out


def _prepare(work: Path, path: Path, ext: str, name: str) -> Path:
    """El .scad principal dentro de la carpeta del trabajo."""
    if ext == "scad":
        dst = work / "modelo.scad"
        shutil.copyfile(path, dst)
        return dst
    check_zip(path)
    with zipfile.ZipFile(path) as zf:
        members = [i for i in zf.infolist() if not i.is_dir()]
        if len(members) > MAX_SCAD_FILES:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Demasiados archivos en el ZIP")
        for info in members:
            target = (work / info.filename).resolve()
            if not str(target).startswith(str(work.resolve()) + "/"):
                raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "Ruta que escapa en el ZIP")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    roots = [p for p in work.glob("*.scad")]
    stem = Path(name).stem.lower()
    main = next((p for p in roots if p.stem.lower() == stem), roots[0] if len(roots) == 1 else None)
    if main is None:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "scad_main")
    return main


def _landlock(ctx: ToolContext, work: Path) -> list[tuple[Path, str]]:
    exe = Path(shutil.which(ctx.settings.OPENSCAD_BIN) or ctx.settings.OPENSCAD_BIN).resolve()
    read = {exe.parent, exe.parent.parent / "lib", exe.parent.parent / "share", Path("/usr/lib"), Path("/usr/share/openscad"),
            Path("/usr/share/fonts"), Path("/etc/fonts"), Path("/usr/lib/x86_64-linux-gnu"), Path("/lib"), Path("/lib64"),
            Path("/etc/ld.so.cache"), Path("/var/cache/fontconfig")}
    if ctx.settings.ENGINES_LIBRARY_PATH:
        read |= {Path(p) for p in ctx.settings.ENGINES_LIBRARY_PATH.split(":") if p}
    return [(work, "rw"), *((p, "rx") for p in sorted(read) if p.exists())]


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    target = "3mf" if ctx.tool == "scad-a-3mf" else "stl"
    defines = parse_variables(o.variables)
    if FN.get(o.resolucion):
        defines += ["-D", f"$fn={FN[o.resolucion]}"]
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        ext = (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()
        work = ctx.work / f"scad-{n}"
        work.mkdir(parents=True, exist_ok=True)
        main = _prepare(work, inp.path, ext, inp.name)
        env = {"OPENSCADPATH": str(work), "HOME": str(work)}
        if ctx.settings.ENGINES_LIBRARY_PATH:
            env["LD_LIBRARY_PATH"] = ctx.settings.ENGINES_LIBRARY_PATH
        res = run_engine([ctx.settings.OPENSCAD_BIN, "--hardwarnings", "-o", "salida.stl", *defines, str(main.relative_to(work))],
                         cwd=work, timeout=300, mem_mb=3000, limit_data=True, extra_env=env, ok_codes=tuple(range(256)),
                         max_file_mb=2048, landlock=_landlock(ctx, work))
        stl = work / "salida.stl"
        if res.returncode != 0 or not stl.exists() or not stl.stat().st_size:
            log = (res.stderr or b"").decode("utf-8", "replace")
            if "Current top level object is empty" in log or "not a valid 2D or 3D object" in log or "no top level geometry" in log.lower():
                raise ToolError(ErrorCode.INVALID_OPTIONS, "scad_empty")
            raise ToolError(ErrorCode.ENGINE_FAILED, "scad_error")
        outputs += convert_path(ctx, n, stl, "stl", target, inp.name)
    return with_batch_zip(ctx, outputs, f"modelos-{target}.zip")
