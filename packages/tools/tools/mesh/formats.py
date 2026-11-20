"""Lectura y escritura de mallas (7.18, F7-A, D-244): STL (ASCII y binario), OBJ, PLY y 3MF.

- STL, OBJ y PLY con trimesh, sin resolvedor de archivos: un OBJ que nombra `mtllib ../../etc/passwd` no lee nada del
  disco (12.3). 3MF con lib3mf (lectura, escritura y validación), llamando a su biblioteca C con búferes de numpy: los
  métodos de Python crean un objeto por vértice y 10 millones de triángulos tardarían más de un minuto.
- Antes de leer nada se cuentan los triángulos sin cargarlos (cabecera del STL binario, «facet» del ASCII, «f» del OBJ,
  «element face» del PLY y `<triangle` del 3MF por flujo) contra `mesh_triangles` del plan (9.3).
- Una malla es una lista de piezas (nombre, vértices, caras y, si las tiene, un color por cara) y la unidad del archivo
  cuando la guarda (3MF); STL, OBJ y PLY no la guardan y se toman en milímetros salvo que se diga otra cosa.
"""
from __future__ import annotations

import ctypes
import locale
import re
from contextlib import contextmanager
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from core.errors import ErrorCode, ToolError
from core.zipguard import check_zip
from tools.mesh.recuento import check_limit, stl_is_binary  # noqa: F401 - stl_is_binary se usa en convert

UNITS_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}
UNIT_NAMES = {"mm": ("milímetros", "millimetres"), "cm": ("centímetros", "centimetres"), "m": ("metros", "metres"),
              "in": ("pulgadas", "inches")}
MESH_EXTS = ("stl", "obj", "ply", "3mf")
MAX_COLORS_OBJ = 256


@dataclass
class Part:
    name: str
    vertices: np.ndarray  # (n, 3) float64
    faces: np.ndarray  # (m, 3) int64
    colors: np.ndarray | None = None  # (m, 4) uint8, un color por cara


@dataclass
class Model:
    parts: list[Part]
    unit_mm: float | None = None  # None: el archivo no guarda unidades
    lost: set[str] = field(default_factory=set)  # lo que no se ha podido leer: «textures», «materials»

    @property
    def triangles(self) -> int:
        return sum(len(p.faces) for p in self.parts)

    @property
    def has_colors(self) -> bool:
        return any(p.colors is not None for p in self.parts)


# ——— Lectura ———

STL_RECORD = np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])


def _stl_binary(path: Path) -> Model:
    """STL binario leído directamente con numpy y con los vértices repetidos fusionados (`np.unique` sobre los 12 bytes de
    cada vértice): unos 130 bytes por triángulo en el pico, frente a unos 620 con trimesh, para que los 10 millones del
    plan Pro quepan en el trabajador (D-244)."""
    with open(path, "rb") as f:
        f.seek(80)
        (n,) = np.frombuffer(f.read(4), "<u4")
    records = np.fromfile(path, dtype=STL_RECORD, offset=84, count=int(n))
    corners = np.ascontiguousarray(records["v"].reshape(-1, 3))
    del records
    if not np.isfinite(corners).all():
        raise ToolError(ErrorCode.CORRUPT_FILE, "STL con coordenadas no válidas")
    keys = corners.view(np.dtype((np.void, 12))).reshape(-1)
    unique, inverse = np.unique(keys, return_inverse=True)
    vertices = unique.view(np.float32).reshape(-1, 3).astype(np.float64)
    del unique, keys, corners
    faces = inverse.reshape(-1, 3).astype(np.int64)
    del inverse
    return Model(parts=[Part(path.stem or "modelo", vertices, faces)])


def _from_trimesh(path: Path, ext: str) -> Model:
    import trimesh

    try:
        with open(path, "rb") as f:
            scene = trimesh.load(file_obj=f, file_type=ext, force="scene", resolver=None, process=True)
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 - trimesh lanza de todo con archivos rotos
        raise ToolError(ErrorCode.CORRUPT_FILE, f"{ext.upper()} ilegible") from exc
    model = Model(parts=[])
    for node in scene.graph.nodes_geometry:
        transform, gname = scene.graph[node]
        geom = scene.geometry.get(gname)
        if geom is None or not hasattr(geom, "faces") or len(geom.faces) == 0:
            continue
        mesh = geom.copy()
        mesh.apply_transform(transform)
        colors = None
        visual = getattr(mesh, "visual", None)
        if visual is not None and visual.kind in ("face", "vertex") and getattr(visual, "defined", False):
            colors = np.asarray(visual.face_colors, dtype=np.uint8)
        elif visual is not None and visual.kind == "texture":
            model.lost.add("textures")
        model.parts.append(Part(str(node if node != gname else gname), np.asarray(mesh.vertices, dtype=np.float64),
                                np.asarray(mesh.faces, dtype=np.int64), colors))
    if not model.parts:
        raise ToolError(ErrorCode.CORRUPT_FILE, "El archivo no tiene ninguna malla")
    return model


def _lib3mf():
    import lib3mf

    return lib3mf, lib3mf.get_wrapper()


@contextmanager
def keep_locale():
    """lib3mf cambia el locale del proceso a «C» al leer y escribir y no lo devuelve: el resto del trabajador abriría sus
    archivos de texto en ASCII (D-244). Se guarda y se restaura alrededor de cada uso."""
    saved = locale.setlocale(locale.LC_ALL)
    try:
        yield
    finally:
        locale.setlocale(locale.LC_ALL, saved)


LIB3MF_UNIT_MM = {0: 0.001, 1: 1.0, 2: 10.0, 3: 25.4, 4: 304.8, 5: 1000.0}  # MicroMeter, MilliMeter, CentiMeter, Inch, Foot, Meter
MM_TO_LIB3MF = {"mm": 1, "cm": 2, "in": 3, "m": 5}


def _transform(t) -> np.ndarray:
    m = np.eye(4)
    for row in range(4):
        for col in range(3):
            m[col, row] = t.Fields[row][col]  # 3MF: filas de 3 (x', y', z') por columnas
    return m


def _mesh_arrays(w, mesh):
    import lib3mf

    nv, nt = mesh.GetVertexCount(), mesh.GetTriangleCount()
    verts = np.zeros((nv, 3), dtype=np.float32)
    tris = np.zeros((nt, 3), dtype=np.uint32)
    needed = ctypes.c_uint64(0)
    if nv:
        w.checkError(mesh, w.lib.lib3mf_meshobject_getvertices(mesh._handle, ctypes.c_uint64(nv), needed,
                                                               (lib3mf.Position * nv).from_buffer(verts)))
    if nt:
        w.checkError(mesh, w.lib.lib3mf_meshobject_gettriangleindices(mesh._handle, ctypes.c_uint64(nt), needed,
                                                                      (lib3mf.Triangle * nt).from_buffer(tris)))
    return verts, tris


def _mesh_colors(model3mf, w, mesh, nt: int) -> np.ndarray | None:
    """Un color por cara desde los grupos de colores o los materiales base (el primer vértice de cada triángulo); el
    color del objeto para las caras sin propiedad."""
    import lib3mf

    rid, pid, has = mesh.GetObjectLevelProperty()
    props = np.zeros((nt, 4), dtype=np.uint32)
    needed = ctypes.c_uint64(0)
    try:
        w.checkError(mesh, w.lib.lib3mf_meshobject_getalltriangleproperties(mesh._handle, ctypes.c_uint64(nt), needed,
                                                                           (lib3mf.TriangleProperties * nt).from_buffer(props)))
    except Exception:  # noqa: BLE001 - malla sin propiedades
        props[:] = 0
    if has:
        missing = props[:, 0] == 0
        props[missing, 0], props[missing, 1] = rid, pid
    if not props[:, 0].any():
        return None
    colors = np.full((nt, 4), (200, 200, 200, 255), dtype=np.uint8)
    cache: dict[tuple[int, int], tuple[int, int, int, int] | None] = {}
    for key in {(int(a), int(b)) for a, b in props[:, :2]}:
        resource, prop = key
        value = None
        if resource:
            try:
                kind = model3mf.GetPropertyTypeByID(resource)
                if kind == lib3mf.PropertyType.Colors:
                    c = model3mf.GetColorGroupByID(resource).GetColor(prop)
                    value = (c.Red, c.Green, c.Blue, c.Alpha)
                elif kind == lib3mf.PropertyType.BaseMaterial:
                    c = model3mf.GetBaseMaterialGroupByID(resource).GetDisplayColor(prop)
                    value = (c.Red, c.Green, c.Blue, c.Alpha)
            except Exception:  # noqa: BLE001 - propiedad de tipo no admitido (texturas, compuestos)
                value = None
        cache[key] = value
    for key, value in cache.items():
        if value is not None:
            mask = (props[:, 0] == key[0]) & (props[:, 1] == key[1])
            colors[mask] = value
    return colors


def _from_3mf(path: Path) -> Model:
    with keep_locale():
        return _read_3mf(path)


def _read_3mf(path: Path) -> Model:
    lib3mf, w = _lib3mf()
    check_zip(path)
    model3mf = w.CreateModel()
    try:
        reader = model3mf.QueryReader("3mf")
        reader.SetStrictModeActive(False)
        reader.ReadFromFile(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ToolError(ErrorCode.CORRUPT_FILE, "3MF ilegible") from exc
    model = Model(parts=[], unit_mm=LIB3MF_UNIT_MM.get(int(model3mf.GetUnit()), 1.0))
    if model3mf.GetTexture2DGroups().MoveNext():
        model.lost.add("textures")

    def add(obj, transform: np.ndarray, depth: int) -> None:
        if depth > 16:
            raise ToolError(ErrorCode.CORRUPT_FILE, "Componentes anidados en exceso")
        if obj.IsMeshObject():
            mesh = model3mf.GetMeshObjectByID(obj.GetResourceID())
            verts, tris = _mesh_arrays(w, mesh)
            if not len(tris):
                return
            v = np.c_[verts.astype(np.float64), np.ones(len(verts))] @ transform.T
            colors = _mesh_colors(model3mf, w, mesh, len(tris))
            model.parts.append(Part(mesh.GetName() or f"objeto-{len(model.parts) + 1}", v[:, :3], tris.astype(np.int64), colors))
        elif obj.IsComponentsObject():
            comps = model3mf.GetComponentsObjectByID(obj.GetResourceID())
            for i in range(comps.GetComponentCount()):
                comp = comps.GetComponent(i)
                inner = _transform(comp.GetTransform()) if comp.HasTransform() else np.eye(4)
                add(comp.GetObjectResource(), transform @ inner, depth + 1)

    items = model3mf.GetBuildItems()
    while items.MoveNext():
        item = items.GetCurrent()
        transform = _transform(item.GetObjectTransform()) if item.HasObjectTransform() else np.eye(4)
        add(item.GetObjectResource(), transform, 0)
    if not model.parts:
        raise ToolError(ErrorCode.CORRUPT_FILE, "El 3MF no tiene ninguna malla")
    return model


def load(path: Path, ext: str, max_triangles: int) -> Model:
    check_limit(path, ext, max_triangles)
    if ext == "3mf":
        model = _from_3mf(path)
    elif ext == "stl" and stl_is_binary(path):
        model = _stl_binary(path)
    else:
        model = _from_trimesh(path, ext)
    if model.triangles > max_triangles:  # los polígonos de más de 3 lados se triangulan al leer
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{model.triangles} triángulos; como mucho {max_triangles}")
    return model


# ——— Transformaciones ———

def scaled(model: Model, factor: float) -> Model:
    if factor != 1.0:
        for part in model.parts:
            part.vertices = part.vertices * factor
    return model


def merged(model: Model, name: str = "modelo") -> Model:
    if len(model.parts) <= 1:
        return model
    offset, faces, verts, colors = 0, [], [], []
    any_colors = model.has_colors
    for p in model.parts:
        verts.append(p.vertices)
        faces.append(p.faces + offset)
        offset += len(p.vertices)
        if any_colors:
            colors.append(p.colors if p.colors is not None else np.full((len(p.faces), 4), (200, 200, 200, 255), np.uint8))
    return Model([Part(name, np.vstack(verts), np.vstack(faces), np.vstack(colors) if any_colors else None)], model.unit_mm, model.lost)


# ——— Escritura ———

def _trimesh(part: Part):
    import trimesh

    mesh = trimesh.Trimesh(vertices=part.vertices, faces=part.faces, process=False)
    if part.colors is not None:
        mesh.visual.face_colors = part.colors
    return mesh


def write_stl(model: Model, dst: Path, ascii: bool) -> None:
    mesh = _trimesh(merged(model).parts[0])
    data = mesh.export(file_type="stl_ascii" if ascii else "stl")
    dst.write_bytes(data.encode("ascii") if isinstance(data, str) else data)


def write_ply(model: Model, dst: Path) -> None:
    dst.write_bytes(_trimesh(merged(model).parts[0]).export(file_type="ply", encoding="binary"))


def _obj_name(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name, flags=re.UNICODE)[:64] or "objeto"


def write_obj(model: Model, dst: Path, mtl_name: str | None) -> str | None:
    """OBJ con un grupo `o` por pieza. Con colores, un material por color en el MTL (como mucho 256; si hay más, se
    agrupan al más cercano de la paleta reducida). Devuelve el texto del MTL, si lo hay."""
    colors = model.has_colors and mtl_name is not None
    palette: dict[tuple[int, ...], str] = {}
    lines_mtl: list[str] = []
    with open(dst, "w", encoding="utf-8", newline="\n") as out:
        out.write("# Generado con el conversor 3D\n")
        if colors:
            out.write(f"mtllib {mtl_name}\n")
        offset = 0
        for part in model.parts:
            out.write(f"o {_obj_name(part.name)}\n")
            np.savetxt(out, part.vertices, fmt="v %.6f %.6f %.6f")
            faces = part.faces + offset + 1
            if colors and part.colors is not None:
                cols = part.colors
                unique, inverse = np.unique(cols, axis=0, return_inverse=True)
                if len(unique) > MAX_COLORS_OBJ:
                    cols = (cols // 32) * 32 + 16  # paleta reducida de 8 niveles por canal (512 como mucho)
                    unique, inverse = np.unique(cols, axis=0, return_inverse=True)
                inverse = inverse.reshape(-1)
                for index in range(len(unique)):
                    key = tuple(int(x) for x in unique[index])
                    if key not in palette:
                        name = f"color_{len(palette) + 1}"
                        palette[key] = name
                        r, g, b, a = (x / 255 for x in key)
                        lines_mtl += [f"newmtl {name}", f"Kd {r:.4f} {g:.4f} {b:.4f}", f"d {a:.4f}", "illum 1", ""]
                    out.write(f"usemtl {palette[key]}\n")
                    np.savetxt(out, faces[inverse == index], fmt="f %d %d %d")
            else:
                np.savetxt(out, faces, fmt="f %d %d %d")
            offset += len(part.vertices)
    return "\n".join(lines_mtl) + "\n" if lines_mtl else None


def write_3mf(model: Model, dst: Path, unit: str) -> None:
    with keep_locale():
        _write_3mf(model, dst, unit)


def _write_3mf(model: Model, dst: Path, unit: str) -> None:
    lib3mf, w = _lib3mf()
    model3mf = w.CreateModel()
    model3mf.SetUnit(lib3mf.ModelUnit(MM_TO_LIB3MF[unit]))
    model3mf.SetLanguage("es-ES")
    for part in model.parts:
        mesh = model3mf.AddMeshObject()
        mesh.SetName(part.name[:255])
        verts = np.ascontiguousarray(part.vertices, dtype=np.float32)
        tris = np.ascontiguousarray(part.faces, dtype=np.uint32)
        w.checkError(mesh, w.lib.lib3mf_meshobject_setgeometry(
            mesh._handle, ctypes.c_uint64(len(verts)), (lib3mf.Position * len(verts)).from_buffer(verts),
            ctypes.c_uint64(len(tris)), (lib3mf.Triangle * len(tris)).from_buffer(tris)))
        if part.colors is not None:
            group = model3mf.AddColorGroup()
            unique, inverse = np.unique(part.colors, axis=0, return_inverse=True)
            ids = np.array([group.AddColor(lib3mf.Color(*(int(x) for x in c))) for c in unique], dtype=np.uint32)
            pids = ids[inverse.reshape(-1)]
            props = np.zeros((len(tris), 4), dtype=np.uint32)
            props[:, 0] = group.GetResourceID()
            props[:, 1:] = pids[:, None]
            w.checkError(mesh, w.lib.lib3mf_meshobject_setalltriangleproperties(
                mesh._handle, ctypes.c_uint64(len(props)), (lib3mf.TriangleProperties * len(props)).from_buffer(props)))
            mesh.SetObjectLevelProperty(group.GetResourceID(), int(ids[0]))
        model3mf.AddBuildItem(mesh, w.GetIdentityTransform())
    model3mf.QueryWriter("3mf").WriteToFile(str(dst))
