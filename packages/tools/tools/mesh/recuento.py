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


def _ply_header(path: Path) -> list[tuple[str, int]]:
    """Los elementos de la cabecera de un PLY (sin comentarios), hasta `end_header`; una cabecera de más de 64 KB no es
    de un PLY normal (D-249)."""
    with open(path, "rb") as f:
        header = f.read(65536)
    if not header.startswith(b"ply"):
        raise ToolError(ErrorCode.CORRUPT_FILE, "PLY no válido")
    end = header.find(b"end_header")
    if end < 0:
        raise ToolError(ErrorCode.CORRUPT_FILE, "PLY con una cabecera demasiado larga o sin terminar")
    out = []
    for line in header[:end].splitlines():
        words = line.split()
        if len(words) == 3 and words[0] == b"element" and words[2].isdigit():
            out.append((words[1].decode("ascii", "replace"), int(words[2])))
    return out


def count_triangles(path: Path, ext: str, limit: int | None = None) -> int:
    """Triángulos del archivo sin cargarlo (para el límite del plan antes de gastar memoria). Los vértices de sobra también
    pesan: se cuentan como triángulos a razón de 3 por triángulo (un OBJ con 2 millones de vértices y una cara contaba 1,
    D-249). Con `limit`, deja de contar en cuanto lo supera."""
    if ext == "stl":
        if stl_is_binary(path):
            with open(path, "rb") as f:
                f.seek(80)
                return struct.unpack("<I", f.read(4))[0]
        with open(path, "rb") as f:
            return -(-_stream_count(f, re.compile(rb"(?i)\bvertex\b")) // 3)
    if ext == "obj":
        faces = vertices = 0
        with open(path, "rb") as f:
            for line in f:
                head = line[:2]
                if head in (b"f ", b"f\t"):
                    faces += max(1, len(line.split()) - 3)
                elif head in (b"v ", b"v\t"):
                    vertices += 1
                if limit is not None and max(faces, vertices // 3) > limit:
                    break
        return max(faces, vertices // 3)
    if ext == "ply":
        # Las caras de más de 3 lados triangulan en más: lo frenan el recuento tras leer y la memoria del proceso hijo.
        elements = dict(_ply_header(path))
        return max(elements.get("face", 0), elements.get("vertex", 0) // 3)
    if ext == "3mf":
        check_zip(path)
        total, scanned = 0, 0
        cap = None if limit is None else 200 * limit + 64 * 1024 * 1024
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                name = info.filename.lower()
                if info.is_dir() or name.endswith((".png", ".jpg", ".jpeg", ".rels", ".gcode", ".config")) or name == "[content_types].xml":
                    continue
                scanned += info.file_size
                if cap is not None and scanned > cap:
                    return limit + 1  # demasiado XML para lo que permite el plan
                with zf.open(info) as f:
                    total += _stream_count(f, TRIANGLE_RE)
                if limit is not None and total > limit:
                    return total
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
    if ext == "off":
        with open(path, "rb") as f:
            words = f.read(4096).split()
        try:
            start = 1 if words and words[0].upper().endswith(b"OFF") else 0
            return max(int(words[start + 1]), int(words[start]) // 3)
        except (IndexError, ValueError) as exc:
            raise ToolError(ErrorCode.CORRUPT_FILE, "OFF no válido") from exc
    if ext in ("wrl", "x3d", "usd", "usda", "usdc", "usdz"):
        return 0  # los cuenta su lector al recorrer la escena (las instancias multiplican), dentro del proceso hijo
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
    n = count_triangles(path, ext, limit)
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
            n = count_triangles(path, ext, plan.mesh_triangles)
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
