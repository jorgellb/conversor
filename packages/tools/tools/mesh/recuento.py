"""Recuento de triángulos sin cargar la malla (9.3: `mesh_triangles`, F7-A, D-244). Solo biblioteca estándar: lo importa
también la API (`precheck`), que rechaza antes de encolar y sin gastar la tarea."""
from __future__ import annotations

import re
import struct
import zipfile
from pathlib import Path

from core.errors import AppError, ErrorCode, ToolError
from core.zipguard import check_zip

TRIANGLE_RE = re.compile(rb"<(?:[A-Za-z_][\w.-]*:)?triangle[\s/>]")


def _stream_count(fobj, pattern: re.Pattern, chunk: int = 1 << 20) -> int:
    count, tail = 0, b""
    while block := fobj.read(chunk):
        data = tail + block
        count += len(pattern.findall(data))
        tail = data[-64:]
        count -= len(pattern.findall(tail))  # lo que se vuelva a contar en el siguiente bloque
    return count + len(pattern.findall(tail))


def stl_is_binary(path: Path) -> bool:
    size = path.stat().st_size
    if size < 84:
        return False
    with open(path, "rb") as f:
        f.seek(80)
        (n,) = struct.unpack("<I", f.read(4))
    return 84 + 50 * n == size


def count_triangles(path: Path, ext: str) -> int:
    """Triángulos del archivo sin cargarlo (para el límite del plan antes de gastar memoria)."""
    if ext == "stl":
        if stl_is_binary(path):
            with open(path, "rb") as f:
                f.seek(80)
                return struct.unpack("<I", f.read(4))[0]
        with open(path, "rb") as f:
            return _stream_count(f, re.compile(rb"\bfacet\b"))
    if ext == "obj":
        total = 0
        with open(path, "rb") as f:
            for line in f:
                if line[:2] == b"f " or line[:2] == b"f\t":
                    total += max(1, len(line.split()) - 3)
        return total
    if ext == "ply":
        with open(path, "rb") as f:
            header = f.read(65536)
        if not header.startswith(b"ply"):
            raise ToolError(ErrorCode.CORRUPT_FILE, "PLY no válido")
        m = re.search(rb"element\s+face\s+(\d+)", header)
        return int(m.group(1)) if m else 0
    if ext == "3mf":
        check_zip(path)
        total = 0
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.filename.lower().endswith(".model"):
                    with zf.open(info) as f:
                        total += _stream_count(f, TRIANGLE_RE)
        return total
    if ext == "amf":
        if zipfile.is_zipfile(path):
            check_zip(path)
            with zipfile.ZipFile(path) as zf:
                return sum(_stream_count(zf.open(i), TRIANGLE_RE) for i in zf.infolist() if not i.is_dir())
        with open(path, "rb") as f:
            return _stream_count(f, TRIANGLE_RE)
    if ext in ("glb", "gltf"):
        return _gltf_triangles(path, ext)
    raise ToolError(ErrorCode.UNSUPPORTED_FORMAT)


def _gltf_triangles(path: Path, ext: str) -> int:
    """Triángulos que declara el JSON de un glTF o un GLB (índices / 3, o posiciones / 3 sin índices), por cada vez que
    un nodo usa la malla: las instancias multiplican (D-248)."""
    import json

    with open(path, "rb") as f:
        if ext == "glb":
            head = f.read(20)
            if len(head) < 20 or head[:4] != b"glTF":
                raise ToolError(ErrorCode.CORRUPT_FILE, "GLB no válido")
            (length, kind) = struct.unpack("<II", head[12:20])
            if kind != 0x4E4F534A or length > 64 * 1024 * 1024:
                raise ToolError(ErrorCode.CORRUPT_FILE, "GLB no válido")
            raw = f.read(length)
        else:
            raw = f.read(64 * 1024 * 1024 + 1)
            if len(raw) > 64 * 1024 * 1024:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "glTF de más de 64 MB")
    try:
        doc = json.loads(raw)
        accessors = doc.get("accessors", [])
        per_mesh = []
        for mesh in doc.get("meshes", []):
            n = 0
            for prim in mesh.get("primitives", []):
                if prim.get("mode", 4) not in (4, 5, 6):
                    continue
                acc = accessors[prim["indices"]] if "indices" in prim else accessors[prim["attributes"]["POSITION"]]
                n += int(acc.get("count", 0)) // 3 if prim.get("mode", 4) == 4 else max(0, int(acc.get("count", 0)) - 2)
            per_mesh.append(n)
        uses = [node["mesh"] for node in doc.get("nodes", []) if isinstance(node, dict) and "mesh" in node]
        return sum(per_mesh[m] for m in uses if 0 <= m < len(per_mesh)) if uses else sum(per_mesh)
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "glTF ilegible") from exc


def check_limit(path: Path, ext: str, limit: int) -> int:
    n = count_triangles(path, ext)
    if n > limit:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{n} triángulos; como mucho {limit}")
    return n



def precheck(settings, plan, owner_type: str, options: dict, paths: list[Path], locale: str = "es") -> None:
    """Antes de encolar: los triángulos de cada archivo dentro del plan (el trabajador lo vuelve a mirar)."""
    from core.filetype import detect

    for path in paths:
        found = detect(path, "")
        ext = found.ext if found is not None and found.ext in ("ply", "3mf", "amf", "glb") else None
        if ext is None:
            ext = "stl" if stl_is_binary(path) else _text_kind(path)
        if ext is None:
            continue
        try:
            n = count_triangles(path, ext)
        except ToolError:
            continue  # el trabajador dará el error concreto
        if n > plan.mesh_triangles:
            raise AppError(ErrorCode.LIMIT_EXCEEDED, status=413, detail="mesh_triangles", extra={"max": plan.mesh_triangles})


def _text_kind(path: Path) -> str | None:
    with open(path, "rb") as f:
        head = f.read(4096).lstrip()
    if head.startswith(b"solid"):
        return "stl"
    if re.search(rb"(?m)^\s*(v|f|o|g)\s", head):
        return "obj"
    return None
