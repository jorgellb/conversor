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
MAX_MXL_UNCOMPRESSED = 25 * 1024 * 1024
MAX_MIDI_PDF_BYTES = 2 * 1024 * 1024
MAX_MIDI_PDF_SECONDS = 30 * 60
MSCORE_MEM_MB = 1200  # por debajo del límite del contenedor de workeroffice (1536 MB): si no, el límite no saltaría nunca


def _check_xml(stream, score: bool = True) -> None:
    """Sin DTD con entidades ni nada externo, leído por partes (un XML de 25 MB no ocupa GB en el worker, D-233)."""
    import defusedxml.ElementTree as DET
    from defusedxml import DefusedXmlException

    try:
        first = None
        for _event, elem in DET.iterparse(stream, events=("start", "end"), forbid_dtd=False, forbid_entities=True, forbid_external=True):
            if first is None:
                first = elem.tag
            if _event == "end":
                elem.clear()
    except (DefusedXmlException, ValueError) as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities") from exc
    except SyntaxError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "MusicXML no válido") from exc
    if score and first not in ("score-partwise", "score-timewise"):
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "musicxml_not_score")


def _rootfile(zf: zipfile.ZipFile) -> str | None:
    """La partitura que dice META-INF/container.xml (la que abre MuseScore)."""
    import defusedxml.ElementTree as DET

    try:
        raw = zf.read("META-INF/container.xml")
    except KeyError:
        return None
    try:
        root = DET.fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except Exception as exc:  # noqa: BLE001 - DefusedXmlException, ParseError o ValueError
        raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities") from exc
    node = next((el for el in root.iter() if el.tag.rsplit("}", 1)[-1] == "rootfile"), None)
    return node.get("full-path") if node is not None else None


def _checked(inp) -> str:
    ext = (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()
    if inp.path.stat().st_size > MAX_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Partitura de más de 20 MB")
    if ext in ("musicxml", "xml"):
        with open(inp.path, "rb") as stream:
            _check_xml(stream)
        return "musicxml"
    if ext == "mxl":
        # Se comprueban todos los XML del ZIP, no solo el primero: MuseScore abre el que dice container.xml (D-233).
        check_zip(inp.path, max_uncompressed=MAX_MXL_UNCOMPRESSED)
        try:
            with zipfile.ZipFile(inp.path) as zf:
                main = _rootfile(zf)
                names = {i.filename for i in zf.infolist()}
                if main is not None and main not in names:
                    raise ToolError(ErrorCode.CORRUPT_FILE, "MXL sin la partitura que indica container.xml")
                scores = 0
                for info in zf.infolist():
                    lower = info.filename.lower()
                    if info.is_dir() or not lower.endswith((".xml", ".musicxml")):
                        continue
                    is_score = info.filename == main or (main is None and not lower.startswith("meta-inf/"))
                    with zf.open(info) as stream:
                        _check_xml(stream, score=is_score and info.filename == main)
                    scores += 1 if is_score else 0
                if not scores:
                    raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "musicxml_not_score")
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError) as exc:
            # CRC erróneo, cifrado o compresión que zipfile no admite.
            raise ToolError(ErrorCode.CORRUPT_FILE, "MXL dañado o cifrado") from exc
        return "mxl"
    data = inp.path.read_bytes()
    if data[:4] != b"MThd":
        raise ToolError(ErrorCode.CORRUPT_FILE, "midi")
    # midi-a-pdf: MuseScore tarda minutos con MIDI grandes; se acotan el tamaño y la duración.
    from tools.av.midi import duration

    if len(data) > MAX_MIDI_PDF_BYTES or duration(data, playable=False) > MAX_MIDI_PDF_SECONDS:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "MIDI demasiado largo para pasarlo a partitura")
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
        run_engine([str(exe), "-o", "salida.pdf", src.name], cwd=folder, timeout=600, mem_mb=MSCORE_MEM_MB, limit_data=True, extra_env=env,
                   ok_codes=tuple(range(256)))
        produced = folder / "salida.pdf"
        if not produced.exists() or produced.stat().st_size == 0:
            raise ToolError(ErrorCode.CORRUPT_FILE, "MuseScore no ha podido leer la partitura")
        name = derived_name(inp.name, "", "pdf")
        dst = ctx.output(name)
        shutil.move(produced, dst)
        outputs.append({"path": str(dst), "name": name, "note": None})
    return with_batch_zip(ctx, outputs, f"{ctx.tool}.zip")
