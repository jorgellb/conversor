"""epub-a-mobi, epub-a-azw3, mobi-a-epub y azw3-a-epub (7.13, F6-C, D-237) con `ebook-convert` de Calibre.

La misma revisión previa y el mismo aislamiento que epub-a-pdf (libros.py: ZIP revisado, nada que apunte fuera del libro,
entorno vacío, configuración en el trabajo y memoria de datos limitada). Un libro con DRM no se puede convertir y se dice
antes de intentarlo: en EPUB, META-INF/encryption.xml con algo más que fuentes ofuscadas; en MOBI y AZW3, el campo de
cifrado de la cabecera PalmDOC del primer registro.
"""
from __future__ import annotations

import re
import shutil
import struct
import zipfile
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name, run_engine
from tools.office.libros import calibre_landlock, check_book, decode_text
from tools.pdf.common import with_batch_zip

TARGET = {"epub-a-mobi": "mobi", "epub-a-azw3": "azw3", "mobi-a-epub": "epub", "azw3-a-epub": "epub"}
FONT_OBFUSCATION = ("http://www.idpf.org/2008/embedding", "http://ns.adobe.com/pdf/enc#RC")
MAX_BOOK = 200 * 1024 * 1024


def has_drm(path: Path, ext: str) -> bool:
    if ext == "epub":
        try:
            with zipfile.ZipFile(path) as zf:
                # Los nombres sin distinguir mayúsculas y el XML con su codificación (D-243).
                names = {n.lower(): n for n in zf.namelist()}
                if "meta-inf/rights.xml" in names:
                    return True
                if "meta-inf/encryption.xml" not in names:
                    return False
                enc = decode_text(zf.read(names["meta-inf/encryption.xml"]))
        except zipfile.BadZipFile:
            return False
        algorithms = [a or b for a, b in re.findall(r"""Algorithm\s*=\s*(?:"([^"]+)"|'([^']+)')""", enc)]
        return any(a not in FONT_OBFUSCATION for a in algorithms)
    with open(path, "rb") as f:
        header = f.read(78 + 8)
        if len(header) < 86 or header[60:68] not in (b"BOOKMOBI", b"TEXtREAd"):
            raise ToolError(ErrorCode.CORRUPT_FILE, "MOBI o AZW3 no válido")
        (offset,) = struct.unpack(">I", header[78:82])  # el primer registro, tras los 78 bytes de la cabecera PDB
        f.seek(offset)
        record0 = f.read(16)
    if len(record0) < 14:
        raise ToolError(ErrorCode.CORRUPT_FILE, "MOBI o AZW3 no válido")
    (encryption,) = struct.unpack(">H", record0[12:14])
    return encryption != 0


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    target = TARGET[ctx.tool]
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        ext = (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()
        if inp.path.stat().st_size > MAX_BOOK:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Libro de más de 200 MB")
        if ext in ("epub", "fb2"):
            check_book(inp.path, ext)
        # MOBI y AZW3 no se pueden revisar por dentro sin descomprimirlos: los cubre Landlock (calibre_landlock, D-243).
        if has_drm(inp.path, ext):
            raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "libro_drm")
        work = ctx.work / f"libro-{n}"
        work.mkdir(parents=True, exist_ok=True)
        src = work / f"libro.{ext}"
        shutil.copyfile(inp.path, src)
        tmp = work / f"salida.{target}"
        args = ["ebook-convert", str(src), str(tmp)]
        if o.titulo.strip():
            args += ["--title", o.titulo.strip()]
        if o.autor.strip():
            args += ["--authors", o.autor.strip()]
        if target in ("mobi", "azw3"):
            args += ["--mobi-keep-original-images"] + (["--mobi-file-type", "both"] if target == "mobi" else [])
        else:
            args += ["--epub-version", "3"] if o.epub3 else ["--epub-version", "2"]
        env = {"QT_QPA_PLATFORM": "offscreen", "CALIBRE_CONFIG_DIRECTORY": str(work / "config"), "CALIBRE_TEMP_DIR": str(work),
               "CALIBRE_CACHE_DIRECTORY": str(work / "cache"), "QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox --disable-gpu"}
        # Memoria de datos y no virtual (D-52) y por debajo del límite del contenedor (D-191), como en epub-a-pdf.
        run_engine(args, cwd=work, timeout=900, mem_mb=1200, extra_env=env, limit_data=True, max_file_mb=1024,
                   landlock=calibre_landlock(work))
        if not tmp.exists() or not tmp.stat().st_size:
            raise ToolError(ErrorCode.ENGINE_FAILED, "Calibre no generó el libro")
        name = derived_name(inp.name, "", target)
        dst = ctx.output(name)
        shutil.move(tmp, dst)
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, f"libros-{target}.zip")
