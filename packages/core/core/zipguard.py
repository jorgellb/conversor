"""Comprobación de contenedores ZIP (OOXML, ODF, EPUB y ZIP) antes de pasarlos a un motor (12.3).

Corta las bombas de descompresión y las rutas `../` sin descomprimir nada.
"""
from __future__ import annotations

import zipfile
from pathlib import Path, PurePosixPath

from core.errors import ErrorCode, ToolError

MAX_MEMBERS = 10_000
MAX_RATIO = 100
MAX_UNCOMPRESSED = 2 * 1024 ** 3


def check_zip(path: Path, max_uncompressed: int = MAX_UNCOMPRESSED, max_ratio: int = MAX_RATIO,
              max_members: int = MAX_MEMBERS) -> int:
    """Devuelve el tamaño descomprimido total o lanza `ToolError`."""
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
    except (zipfile.BadZipFile, OSError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "ZIP no válido") from exc
    if len(infos) > max_members:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{len(infos)} elementos")
    total = 0
    packed = 0
    for info in infos:
        name = PurePosixPath(info.filename.replace("\\", "/"))
        if name.is_absolute() or ".." in name.parts:
            raise ToolError(ErrorCode.CORRUPT_FILE, "Ruta no permitida dentro del ZIP")
        total += info.file_size
        packed += info.compress_size
        if info.compress_size and info.file_size / info.compress_size > max_ratio and info.file_size > 10 * 1024 * 1024:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Relación de compresión excesiva")
    if total > max_uncompressed:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Contenido descomprimido demasiado grande")
    if packed and total / packed > max_ratio and total > 50 * 1024 * 1024:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Relación de compresión excesiva")
    return total
