"""dwg-a-dxf y dwg-a-pdf (7.19, F7-E, D-252): LibreDWG (GPL, programa externo `dwg2dxf`, 11) en sandbox.

LibreDWG lee DWG de R13 a 2018 con una calidad irregular (entidades propias de AutoCAD, sombreados o cotas pueden
faltar): la nota lo avisa. El DXF se comprueba con ezdxf (`recover`) antes de entregarlo; para el PDF sigue la ruta de
dxf-a-pdf (7.3): ezdxf a SVG y el Chromium de Gotenberg.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name, run_engine
from tools.pdf.common import with_batch_zip

DWG_VERSIONS = {b"AC1012": "R13", b"AC1014": "R14", b"AC1015": "2000", b"AC1018": "2004", b"AC1021": "2007", b"AC1024": "2010",
                b"AC1027": "2013", b"AC1032": "2018"}
TEXTS = {
    "es": {"irregular": "DWG {v} convertido con LibreDWG: revisa el resultado, porque algunas entidades propias de AutoCAD "
                        "(sombreados, cotas asociativas, objetos de aplicaciones) pueden faltar o cambiar."},
    "en": {"irregular": "DWG {v} converted with LibreDWG: check the result, because some AutoCAD-specific entities (hatches, "
                        "associative dimensions, application objects) may be missing or change."},
}


def dwg_version(path: Path) -> str:
    with open(path, "rb") as f:
        head = f.read(6)
    if head not in DWG_VERSIONS:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "dwg_version")
    return DWG_VERSIONS[head]


def _landlock(ctx: ToolContext, work: Path) -> list[tuple[Path, str]]:
    exe = Path(shutil.which(ctx.settings.DWG2DXF_BIN) or ctx.settings.DWG2DXF_BIN).resolve()
    read = {exe.parent, exe.parent.parent / "lib", exe.parent.parent / "share", Path("/usr/lib"), Path("/lib"), Path("/lib64"),
            Path("/etc/ld.so.cache"), Path("/usr/lib/x86_64-linux-gnu")}
    return [(work, "rw"), *((p, "rx") for p in sorted(read) if p.exists())]


def to_dxf(ctx: ToolContext, n: int, path: Path) -> tuple[Path, str]:
    version = dwg_version(path)
    work = ctx.work / f"dwg-{n}"
    work.mkdir(parents=True, exist_ok=True)
    src = work / "plano.dwg"
    shutil.copyfile(path, src)
    env = {"LD_LIBRARY_PATH": ctx.settings.ENGINES_LIBRARY_PATH} if ctx.settings.ENGINES_LIBRARY_PATH else None
    # dwg2dxf termina con código distinto de 0 si se ha saltado alguna entidad aunque el DXF esté bien: se mira el archivo.
    run_engine([ctx.settings.DWG2DXF_BIN, "-y", "-o", "plano.dxf", "plano.dwg"], cwd=work, timeout=300, mem_mb=2048, extra_env=env,
               ok_codes=tuple(range(256)), max_file_mb=1024, landlock=_landlock(ctx, work))
    dxf = work / "plano.dxf"
    if not dxf.exists() or dxf.stat().st_size < 64:
        raise ToolError(ErrorCode.CORRUPT_FILE, "dwg_unreadable")
    import ezdxf
    from ezdxf import recover

    try:
        _doc, auditor = recover.readfile(str(dxf))
    except (OSError, ezdxf.DXFStructureError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "dwg_unreadable") from exc
    if auditor.has_errors:
        raise ToolError(ErrorCode.CORRUPT_FILE, "dwg_unreadable")
    return dxf, version


def run_dxf(ctx: ToolContext) -> list[dict]:
    t = TEXTS.get(ctx.locale, TEXTS["es"])
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        dxf, version = to_dxf(ctx, n, inp.path)
        name = derived_name(inp.name, "", "dxf")
        dst = ctx.output(name)
        shutil.move(dxf, dst)
        outputs.append({"path": str(dst), "name": name, "note": t["irregular"].format(v=version)})
    return with_batch_zip(ctx, outputs, "planos-dxf.zip")


def run_pdf(ctx: ToolContext) -> list[dict]:
    from tools.media.dxf import dxf_pdf

    o = ctx.options
    t = TEXTS.get(ctx.locale, TEXTS["es"])
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        dxf, version = to_dxf(ctx, n, inp.path)
        name = derived_name(inp.name, "", "pdf")
        dst = ctx.output(name)
        dxf_pdf(ctx, dxf, dst, o)
        outputs.append({"path": str(dst), "name": name, "note": t["irregular"].format(v=version)})
    return with_batch_zip(ctx, outputs, "planos-pdf.zip")
