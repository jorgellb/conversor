"""Formatos de F7-B (7.18, D-248): AMF propio, GLB y glTF con trimesh, y FBX, DAE y 3DS con assimp en un proceso hijo.

Ejes: STL, OBJ, PLY, 3MF y AMF se usan con Z vertical (la impresión 3D); glTF lo define con Y vertical y assimp deja FBX,
DAE y 3DS con Y vertical, así que al pasar de unos a otros se gira (`Model.up`), salvo que se pida conservar los ejes.
Unidades: glTF en metros (su especificación), DAE en metros tras aplicar su `<unit>` (assimp lo hace), FBX con su
`UnitScaleFactor` (centímetros por unidad) y 3DS sin unidades.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

import numpy as np
from lxml import etree

from core.errors import ErrorCode, ToolError
from core.zipguard import check_zip
from tools.mesh.formats import Model, Part

PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
AMF_UNITS = {"millimeter": 1.0, "inch": 25.4, "feet": 304.8, "meter": 1000.0, "micron": 0.001}
UNIT_TO_AMF = {"mm": "millimeter", "cm": "millimeter", "m": "meter", "in": "inch"}
DEFAULT_COLOR = (200, 200, 200, 255)


# ——— Ejes ———

def y_to_z(v: np.ndarray) -> np.ndarray:
    """De Y vertical (glTF, FBX, DAE, 3DS por assimp) a Z vertical: (x, y, z) → (x, −z, y)."""
    return np.c_[v[:, 0], -v[:, 2], v[:, 1]]


def z_to_y(v: np.ndarray) -> np.ndarray:
    return np.c_[v[:, 0], v[:, 2], -v[:, 1]]


def reorient(model: Model, up: str) -> bool:
    """Deja el modelo con el eje vertical `up` («y» o «z»); devuelve si ha girado algo."""
    if model.up == up or model.up is None:
        return False
    for part in model.parts:
        part.vertices = y_to_z(part.vertices) if up == "z" else z_to_y(part.vertices)
    model.up = up
    return True


# ——— AMF (ISO/ASTM 52915) ———

def _amf_root(path: Path):
    """El XML del AMF, plano o comprimido en ZIP (un solo .amf dentro, como lo guarda PrusaSlicer)."""
    if zipfile.is_zipfile(path):
        check_zip(path)
        with zipfile.ZipFile(path) as zf:
            members = [i for i in zf.infolist() if not i.is_dir()]
            if len(members) != 1:
                raise ToolError(ErrorCode.CORRUPT_FILE, "El AMF comprimido debe llevar un solo archivo")
            if members[0].file_size > 512 * 1024 * 1024:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "AMF de más de 512 MB descomprimido")
            with zf.open(members[0]) as f:
                return _parse(f)
    with open(path, "rb") as f:
        return _parse(f)


def _parse(fobj):
    try:
        tree = etree.parse(fobj, PARSER)
    except etree.XMLSyntaxError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "AMF ilegible") from exc
    if tree.docinfo.doctype or tree.docinfo.internalDTD is not None:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities")
    root = tree.getroot()
    if etree.QName(root).localname.lower() != "amf":
        raise ToolError(ErrorCode.CORRUPT_FILE, "No es un AMF")
    return root


def _children(el, name: str):
    return [c for c in el if isinstance(c.tag, str) and etree.QName(c).localname.lower() == name]


def _child(el, name: str):
    found = _children(el, name)
    return found[0] if found else None


def _num(el, name: str, default: float = 0.0) -> float:
    c = _child(el, name)
    try:
        return float(c.text) if c is not None and c.text else default
    except ValueError:
        return default


def _color(el) -> tuple[int, int, int, int] | None:
    c = _child(el, "color")
    if c is None:
        return None
    vals = [_num(c, k, 1.0 if k == "a" else 0.0) for k in ("r", "g", "b", "a")]
    return tuple(int(round(max(0.0, min(1.0, v)) * 255)) for v in vals)  # type: ignore[return-value]


def _rotation(rx: float, ry: float, rz: float) -> np.ndarray:
    x, y, z = np.radians([rx, ry, rz])
    cx, sx, cy, sy, cz, sz = np.cos(x), np.sin(x), np.cos(y), np.sin(y), np.cos(z), np.sin(z)
    rot_x = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    rot_y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rot_z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rot_z @ rot_y @ rot_x


def read_amf(path: Path, max_triangles: int) -> Model:
    root = _amf_root(path)
    unit_mm = AMF_UNITS.get((root.get("unit") or "millimeter").lower(), 1.0)
    materials = {m.get("id"): _color(m) for m in _children(root, "material")}
    objects: dict[str, list[Part]] = {}
    total = 0
    for obj in _children(root, "object"):
        mesh = _child(obj, "mesh")
        if mesh is None:
            continue
        vertices_el = _child(mesh, "vertices")
        coords = []
        for vertex in _children(vertices_el, "vertex") if vertices_el is not None else []:
            c = _child(vertex, "coordinates")
            coords.append((_num(c, "x"), _num(c, "y"), _num(c, "z")) if c is not None else (0.0, 0.0, 0.0))
        verts = np.array(coords, dtype=np.float64).reshape(-1, 3)
        obj_color = _color(obj)
        faces, colors = [], []
        for volume in _children(mesh, "volume"):
            color = _color(volume) or materials.get(volume.get("materialid")) or obj_color
            for tri in _children(volume, "triangle"):
                total += 1
                if total > max_triangles:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"Más de {max_triangles} triángulos")
                faces.append((int(_num(tri, "v1", -1)), int(_num(tri, "v2", -1)), int(_num(tri, "v3", -1))))
                colors.append(color)
        if not faces:
            continue
        f = np.array(faces, dtype=np.int64)
        if f.min() < 0 or f.max() >= len(verts):
            raise ToolError(ErrorCode.CORRUPT_FILE, "AMF con triángulos que apuntan a vértices que no existen")
        has_color = any(c is not None for c in colors)
        cols = np.array([c or DEFAULT_COLOR for c in colors], dtype=np.uint8) if has_color else None
        name = (_child(obj, "metadata").text if _child(obj, "metadata") is not None and _child(obj, "metadata").text else None) or f"objeto-{obj.get('id')}"
        objects[obj.get("id") or str(len(objects))] = [Part(name[:120], verts, f, cols)]
    if not objects:
        raise ToolError(ErrorCode.CORRUPT_FILE, "El AMF no tiene ninguna malla")
    parts: list[Part] = []
    constellations = _children(root, "constellation")
    if constellations:
        for const in constellations:
            for inst in _children(const, "instance"):
                base = objects.get(inst.get("objectid"))
                if not base:
                    continue
                total += sum(len(p.faces) for p in base)
                if total > max_triangles:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"Más de {max_triangles} triángulos")
                rot = _rotation(_num(inst, "rx"), _num(inst, "ry"), _num(inst, "rz"))
                delta = np.array([_num(inst, "deltax"), _num(inst, "deltay"), _num(inst, "deltaz")])
                for p in base:
                    parts.append(Part(p.name, p.vertices @ rot.T + delta, p.faces, p.colors))
    if not parts:
        parts = [p for ps in objects.values() for p in ps]
    model = Model(parts, unit_mm)
    model.up = "z"
    return model


def write_amf(model: Model, dst: Path, unit: str) -> None:
    """AMF comprimido en ZIP (como PrusaSlicer): un objeto por pieza, un volumen por color y un material por color."""
    amf = etree.Element("amf", unit=UNIT_TO_AMF.get(unit, "millimeter"), version="1.1")
    if unit == "cm":  # AMF no tiene centímetros: se guarda en milímetros
        for part in model.parts:
            part.vertices = part.vertices * 10.0
    etree.SubElement(amf, "metadata", type="producer").text = "Conversor 3D"
    palette: dict[tuple[int, ...], str] = {}
    for n, part in enumerate(model.parts, start=1):
        obj = etree.SubElement(amf, "object", id=str(n))
        etree.SubElement(obj, "metadata", type="name").text = part.name
        mesh = etree.SubElement(obj, "mesh")
        verts = etree.SubElement(mesh, "vertices")
        for x, y, z in part.vertices:
            c = etree.SubElement(etree.SubElement(verts, "vertex"), "coordinates")
            etree.SubElement(c, "x").text = f"{x:.6g}"
            etree.SubElement(c, "y").text = f"{y:.6g}"
            etree.SubElement(c, "z").text = f"{z:.6g}"
        groups = [(None, np.arange(len(part.faces)))]
        if part.colors is not None:
            unique, inverse = np.unique(part.colors, axis=0, return_inverse=True)
            groups = [(tuple(int(x) for x in unique[i]), np.flatnonzero(inverse.reshape(-1) == i)) for i in range(len(unique))]
        for color, idx in groups:
            attrs = {}
            if color is not None:
                if color not in palette:
                    palette[color] = str(len(palette) + 1)
                attrs["materialid"] = palette[color]
            volume = etree.SubElement(mesh, "volume", **attrs)
            for a, b, c in part.faces[idx]:
                tri = etree.SubElement(volume, "triangle")
                etree.SubElement(tri, "v1").text = str(a)
                etree.SubElement(tri, "v2").text = str(b)
                etree.SubElement(tri, "v3").text = str(c)
    for color, mid in palette.items():
        mat = etree.SubElement(amf, "material", id=mid)
        col = etree.SubElement(mat, "color")
        for key, value in zip("rgba", color):
            etree.SubElement(col, key).text = f"{value / 255:.4f}"
    data = etree.tostring(amf, xml_declaration=True, encoding="UTF-8")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(dst.stem + ".amf", data)


# ——— glTF y GLB ———

def check_gltf(path: Path) -> None:
    """Un .gltf solo con búferes incrustados (data:): sus archivos .bin o imágenes de fuera no se han subido."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "glTF ilegible") from exc
    for buf in doc.get("buffers", []) if isinstance(doc, dict) else []:
        uri = buf.get("uri", "") if isinstance(buf, dict) else ""
        if uri and not uri.startswith("data:"):
            raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "gltf_external")


def read_gltf(path: Path, ext: str) -> Model:
    from tools.mesh.formats import _from_trimesh

    if ext == "gltf":
        check_gltf(path)
    model = _from_trimesh(path, "glb" if ext == "glb" else "gltf")
    model.unit_mm = 1000.0  # glTF siempre en metros
    model.up = "y"
    return model


def write_glb(model: Model, dst: Path) -> None:
    """GLB con una malla por pieza y, si hay colores, un material PBR por color (sin mezclar colores entre caras)."""
    import trimesh
    from trimesh.visual.material import PBRMaterial
    from trimesh.visual.texture import TextureVisuals

    scene = trimesh.Scene()
    for part in model.parts:
        if part.colors is None:
            scene.add_geometry(trimesh.Trimesh(part.vertices, part.faces, process=False), geom_name=part.name)
            continue
        unique, inverse = np.unique(part.colors, axis=0, return_inverse=True)
        inverse = inverse.reshape(-1)
        for i, color in enumerate(unique):
            faces = part.faces[inverse == i]
            used, remap = np.unique(faces, return_inverse=True)
            mesh = trimesh.Trimesh(part.vertices[used], remap.reshape(-1, 3), process=False)
            mesh.visual = TextureVisuals(material=PBRMaterial(baseColorFactor=[int(x) for x in color], metallicFactor=0.0,
                                                              roughnessFactor=0.8))
            scene.add_geometry(mesh, geom_name=f"{part.name}-{i + 1}" if len(unique) > 1 else part.name)
    dst.write_bytes(scene.export(file_type="glb"))


# ——— FBX, DAE y 3DS con assimp ———

def _child_landlock(work: Path, settings) -> list[tuple[Path, str]]:
    read = {Path(sys.prefix), Path(sys.base_prefix), Path(__file__).parent, Path("/usr"), Path("/lib"), Path("/lib64"), Path("/etc")}
    read |= {Path(p) for p in sys.path if p and Path(p).is_dir() and "site-packages" in p}
    if settings.ENGINES_LIBRARY_PATH:
        read |= {Path(p) for p in settings.ENGINES_LIBRARY_PATH.split(":") if p}
    return [(work, "rw"), *((p, "rx") for p in sorted(read) if p.exists())]


def read_assimp(ctx, path: Path, ext: str, max_triangles: int) -> Model:
    from tools.base import run_engine

    work = ctx.work / f"assimp-{path.stem[:20]}"
    work.mkdir(parents=True, exist_ok=True)
    src = work / f"modelo.{ext}"
    shutil.copyfile(path, src)
    env = {"LD_LIBRARY_PATH": ctx.settings.ENGINES_LIBRARY_PATH} if ctx.settings.ENGINES_LIBRARY_PATH else None
    child = Path(__file__).with_name("assimp_child.py")
    res = run_engine([sys.executable, "-I", str(child), src.name, "salida.npz", str(max_triangles)], cwd=work, timeout=300,
                     mem_mb=2048, extra_env=env, ok_codes=(0, 3, 4), max_file_mb=2048, landlock=_child_landlock(work, ctx.settings))
    if res.returncode == 3:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"Más de {max_triangles} triángulos")
    if res.returncode == 4:
        raise ToolError(ErrorCode.CORRUPT_FILE, f"El {ext.upper()} no tiene ninguna malla")
    try:
        data = np.load(work / "salida.npz", allow_pickle=False)
        names = json.loads(str(data["names"]))
        meta = json.loads(str(data["meta"]))
        parts = []
        for i, name in enumerate(names):
            faces = data[f"f{i}"]
            color = data[f"c{i}"] if f"c{i}" in data.files else None
            colors = np.tile(color, (len(faces), 1)) if color is not None else None
            parts.append(Part(re.sub(r"[\x00-\x1f]", "", name) or f"objeto-{i + 1}", data[f"v{i}"].astype(np.float64), faces.astype(np.int64), colors))
    except (OSError, KeyError, ValueError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, f"{ext.upper()} ilegible") from exc
    unit_mm = None
    if ext == "dae":
        unit_mm = 1000.0  # assimp aplica <unit meter="…"> y deja metros
    elif ext == "fbx":
        unit_mm = float(meta.get("UnitScaleFactor") or 1.0) * 10.0  # centímetros por unidad
    model = Model(parts, unit_mm)
    model.up = "y"
    return model
