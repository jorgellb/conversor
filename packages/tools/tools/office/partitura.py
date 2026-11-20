"""musicxml-a-pdf y midi-a-pdf (7.13, F6-L, D-228): MuseScore 3 (GPL) como programa externo y sin interfaz.

`mscore3 -o salida.pdf entrada` con `QT_QPA_PLATFORM=offscreen` y su configuración dentro del directorio del trabajo.
MusicXML se comprueba antes con defusedxml (sin entidades ni DTD externos, 16.4); el .mxl es un ZIP con su
META-INF/container.xml y pasa por `check_zip`. MIDI: MuseScore lo transcribe a partitura (cuantización automática).
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.zipguard import check_zip
from tools.base import ToolContext, derived_name, run_engine
from tools.pdf.common import with_batch_zip

MAX_BYTES = 20 * 1024 * 1024


def _check_xml(raw: bytes) -> None:
    import defusedxml.ElementTree as DET
    from defusedxml import DefusedXmlException

    try:
        root = DET.fromstring(raw, forbid_dtd=False, forbid_entities=True, forbid_external=True)
    except (DefusedXmlException, ValueError) as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities") from exc
    except SyntaxError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "MusicXML no válido") from exc
    if root.tag not in ("score-partwise", "score-timewise"):
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "musicxml_not_score")


def _checked(inp) -> str:
    ext = (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()
    if inp.path.stat().st_size > MAX_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Partitura de más de 20 MB")
    if ext in ("musicxml", "xml"):
        _check_xml(inp.path.read_bytes())
        return "musicxml"
    if ext == "mxl":
        check_zip(inp.path, max_uncompressed=100 * 1024 * 1024)
        with zipfile.ZipFile(inp.path) as zf:
            for info in zf.infolist():
                if info.filename.lower().endswith((".xml", ".musicxml")) and not info.filename.startswith("META-INF/"):
                    _check_xml(zf.read(info))
                    break
            else:
                raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "musicxml_not_score")
        return "mxl"
    if inp.path.read_bytes()[:4] != b"MThd":
        raise ToolError(ErrorCode.CORRUPT_FILE, "midi")
    return "mid"


def run(ctx: ToolContext) -> list[dict]:
    exe = Path(ctx.settings.MSCORE_BIN)
    if not exe.is_file():
        raise ToolError(ErrorCode.ENGINE_FAILED, "MuseScore no está instalado")
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        ext = _checked(inp)
        folder = ctx.work / f"partitura-{n}"
        folder.mkdir(parents=True, exist_ok=True)
        src = folder / f"entrada.{ext}"
        shutil.copyfile(inp.path, src)
        env = {"QT_QPA_PLATFORM": "offscreen", "XDG_RUNTIME_DIR": str(folder), "XDG_CONFIG_HOME": str(folder / "config"),
               "XDG_DATA_HOME": str(folder / "data"), "XDG_CACHE_HOME": str(folder / "cache")}
        if ctx.settings.ENGINES_LIBRARY_PATH:
            env["LD_LIBRARY_PATH"] = ctx.settings.ENGINES_LIBRARY_PATH
        run_engine([str(exe), "-o", "salida.pdf", src.name], cwd=folder, timeout=600, mem_mb=3072, limit_data=True, extra_env=env,
                   ok_codes=tuple(range(256)))
        produced = folder / "salida.pdf"
        if not produced.exists() or produced.stat().st_size == 0:
            raise ToolError(ErrorCode.CORRUPT_FILE, "MuseScore no ha podido leer la partitura")
        name = derived_name(inp.name, "", "pdf")
        dst = ctx.output(name)
        shutil.move(produced, dst)
        outputs.append({"path": str(dst), "name": name, "note": None})
    return with_batch_zip(ctx, outputs, f"{ctx.tool}.zip")
