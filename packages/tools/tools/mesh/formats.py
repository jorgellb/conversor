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
UNITS_ALL_MM = {**UNITS_MM, "ft": 304.8, "um": 0.001}  # las que puede traer un 3MF o un AMF (D-249)
UNIT_NAMES = {"mm": ("milímetros", "millimetres"), "cm": ("centímetros", "centimetres"), "m": ("metros", "metres"),
              "in": ("pulgadas", "inches"), "ft": ("pies", "feet"), "um": ("micras", "microns")}
MAX_PARTS = 10_000  # piezas (instancias incluidas) de un modelo, D-249
DEFAULT_GREY = (200, 200, 200, 255)
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
    up: str | None = "z"  # eje vertical: «z» (impresión 3D) o «y» (glTF, FBX, DAE y 3DS), D-248

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


class _NoFiles:
    """Resolvedor que no lee nada: con `resolver=None`, trimesh crea uno en la carpeta del archivo (la de las entradas del
    trabajo) y un OBJ podía leer como MTL otra entrada suya (D-249)."""

    def get(self, name):
        raise FileNotFoundError(name)

    def get_base(self):
        return ""

    def namespaced(self, namespace):
        return self

    def keys(self):
        return iter(())

    def write(self, name, data):
        raise PermissionError(name)


VERTEX_RE = re.compile(rb"(?i)\bvertex\s+(\S+)\s+(\S+)\s+(\S+)")


def _stl_ascii(path: Path, max_triangles: int) -> Model:
    """STL ASCII leído por bloques de 16 MB (los `vertex` sin distinguir mayúsculas) y fusionado como el binario: trimesh
    necesitaba unas 8 veces el tamaño del archivo (D-249)."""
    chunks, tail, total = [], b"", 0
    with open(path, "rb") as f:
        while block := f.read(16 * 1024 * 1024):
            data = tail + block
            cut = data.rfind(b"\n")
            data, tail = (data[:cut + 1], data[cut + 1:]) if cut >= 0 else (b"", data)
            found = VERTEX_RE.findall(data)
            if found:
                try:
                    chunks.append(np.array(found, dtype=np.float32))
                except ValueError as exc:
                    raise ToolError(ErrorCode.CORRUPT_FILE, "STL con coordenadas no válidas") from exc
                total += len(found)
                if total > 3 * max_triangles:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, "mesh_triangles")
        if tail:
            found = VERTEX_RE.findall(tail)
            if found:
                chunks.append(np.array(found, dtype=np.float32))
    if not chunks:
        raise ToolError(ErrorCode.CORRUPT_FILE, "El STL no tiene ninguna malla")
    corners = np.concatenate(chunks)
    del chunks
    corners = corners[: len(corners) // 3 * 3]
    if not np.isfinite(corners).all() or not len(corners):
        raise ToolError(ErrorCode.CORRUPT_FILE, "STL con coordenadas no válidas")
    keys = np.ascontiguousarray(corners).view(np.dtype((np.void, 12))).reshape(-1)
    unique, inverse = np.unique(keys, return_inverse=True)
    vertices = unique.view(np.float32).reshape(-1, 3).astype(np.float64)
    return Model(parts=[Part(path.stem or "modelo", vertices, inverse.reshape(-1, 3).astype(np.int64))])


def _from_trimesh(path: Path, ext: str) -> Model:
    import trimesh

    try:
        with open(path, "rb") as f:
            scene = trimesh.load(file_obj=f, file_type=ext, force="scene", resolver=_NoFiles(), process=True)
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
            # El color base de un material glTF sin textura, tal cual; una textura, a un color por cara aproximado, y se avisa.
            material = getattr(visual, "material", None)
            base = getattr(material, "baseColorFactor", None)
            if base is not None and getattr(material, "baseColorTexture", None) is None:
                rgba = np.asarray(base, dtype=np.float64).reshape(-1)[:4]
                rgba = rgba * 255 if rgba.max() <= 1.0 else rgba
                colors = np.tile(np.clip(np.round(rgba), 0, 255).astype(np.uint8), (len(mesh.faces), 1))
            else:
                try:
                    as_color = visual.to_color()
                    colors = np.asarray(as_color.face_colors, dtype=np.uint8) if getattr(as_color, "defined", False) else None
                except Exception:  # noqa: BLE001
                    colors = None
            if getattr(getattr(visual, "material", None), "image", None) is not None or getattr(getattr(visual, "material", None), "baseColorTexture", None) is not None:
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
    # Una búsqueda por combinación distinta (recurso, propiedad) y una tabla: con una máscara por color, un escaneo con un
    # color por cara tardaba minutos (D-249).
    keys, inverse = np.unique(props[:, :2], axis=0, return_inverse=True)
    table = np.tile(np.array(DEFAULT_GREY, dtype=np.uint8), (len(keys), 1))
    for index, (resource, prop) in enumerate(keys.tolist()):
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
        if value is not None:
            table[index] = value
    return table[inverse.reshape(-1)]


def _from_3mf(path: Path, max_triangles: int = 10**9) -> Model:
    with keep_locale():
        return _read_3mf(path, max_triangles)


def _read_3mf(path: Path, max_triangles: int = 10**9) -> Model:
    lib3mf, w = _lib3mf()
    # Descomprimido, unos 200 bytes por triángulo permitido más 64 MB: un 3MF de 42 MB con 2 GB de adjuntos no pasa (D-249).
    check_zip(path, max_uncompressed=min(2 * 1024**3, 200 * max_triangles + 64 * 1024**2))
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

    # Antes de copiar nada: triángulos y piezas que saldrán, contando cada vez que una malla se usa (elementos de
    # construcción y componentes multiplican). Con solo contar `<triangle`, mil instancias de una malla pasaban (D-249).
    counts: dict[int, tuple[int, int]] = {}

    def count(obj, depth: int) -> tuple[int, int]:
        rid = obj.GetResourceID()
        if rid in counts:
            return counts[rid]
        if depth > 16:
            raise ToolError(ErrorCode.CORRUPT_FILE, "Componentes anidados en exceso")
        if obj.IsMeshObject():
            result = (int(model3mf.GetMeshObjectByID(rid).GetTriangleCount()), 1)
        elif obj.IsComponentsObject():
            comps = model3mf.GetComponentsObjectByID(rid)
            tri = parts = 0
            for i in range(comps.GetComponentCount()):
                a, b = count(comps.GetComponent(i).GetObjectResource(), depth + 1)
                tri, parts = tri + a, parts + b
                if tri > max_triangles or parts > MAX_PARTS:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, "mesh_triangles")
            result = (tri, parts)
        else:
            result = (0, 0)
        counts[rid] = result
        return result

    total = total_parts = 0
    items = model3mf.GetBuildItems()
    while items.MoveNext():
        a, b = count(items.GetCurrent().GetObjectResource(), 0)
        total, total_parts = total + a, total_parts + b
        if total > max_triangles or total_parts > MAX_PARTS:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "mesh_triangles")

    def add(obj, transform: np.ndarray, depth: int) -> None:
        if depth > 16:
            raise ToolError(ErrorCode.CORRUPT_FILE, "Componentes anidados en exceso")
        if obj.IsMeshObject():
            mesh = model3mf.GetMeshObjectByID(obj.GetResourceID())
            verts, tris = _mesh_arrays(w, mesh)
            if not len(tris):
                return
            if np.linalg.det(transform[:3, :3]) < 0:
                tris = tris[:, ::-1]  # una simetría (espejo del laminador) invierte las caras: se vuelven a girar (D-249)
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


def load(path: Path, ext: str, max_triangles: int, ctx=None, inline: bool = False) -> Model:
    """`inline`: ya dentro del proceso hijo de las mallas (D-249), assimp se usa en el mismo proceso."""
    from tools.mesh import extra

    if ext in ("fbx", "dae", "3ds"):
        if inline:
            return extra.read_assimp_inline(path, ext, max_triangles)
        return extra.read_assimp(ctx, path, ext, max_triangles)  # cuenta los triángulos el proceso hijo
    check_limit(path, ext, max_triangles)
    if ext in ("wrl", "x3d"):
        from tools.mesh import escena

        return escena.read_scene(path, ext, max_triangles)  # cuenta cada uso de DEF/USE al recorrer la escena
    if ext in ("usd", "usda", "usdc", "usdz"):
        from tools.mesh import usd

        return usd.read_usd(path, max_triangles)
    if ext == "amf":
        return extra.read_amf(path, max_triangles)
    if ext in ("glb", "gltf"):
        model = extra.read_gltf(path, ext)
    elif ext == "3mf":
        model = _from_3mf(path, max_triangles)
    elif ext == "stl" and stl_is_binary(path):
        model = _stl_binary(path)
    elif ext == "stl":
        model = _stl_ascii(path, max_triangles)
    else:
        model = _from_trimesh(path, ext)
    if model.triangles > max_triangles:  # los polígonos de más de 3 lados se triangulan al leer
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{model.triangles} triángulos; como mucho {max_triangles}")
    return model


# ——— Transformaciones ———

def check_finite(model: Model) -> None:
    """Coordenadas finitas tras transformar y escalar (un 1e36 en una transformación de 3MF daba infinitos, D-249)."""
    for part in model.parts:
        if not np.isfinite(part.vertices).all():
            raise ToolError(ErrorCode.CORRUPT_FILE, "Coordenadas fuera de rango")


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
    return Model([Part(name, np.vstack(verts), np.vstack(faces), np.vstack(colors) if any_colors else None)], model.unit_mm, model.lost,
                 model.up)


# ——— Escritura ———

def _trimesh(part: Part):
    import trimesh

    mesh = trimesh.Trimesh(vertices=part.vertices, faces=part.faces, process=False)
    if part.colors is not None:
        mesh.visual.face_colors = part.colors
    return mesh


def _normals(tri: np.ndarray) -> np.ndarray:
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(n, axis=1, keepdims=True)
    return np.divide(n, length, out=np.zeros_like(n), where=length > 0)


def write_stl(model: Model, dst: Path, ascii: bool) -> None:
    """STL escrito por bloques de 1 millón de triángulos (50 bytes por triángulo en binario, sin la cadena entera del
    ASCII en memoria): con trimesh, 2 millones en ASCII llegaban a 2,3 GB (D-249)."""
    total = sum(len(p.faces) for p in model.parts)
    step = 1_000_000
    with open(dst, "wb") as out:
        if ascii:
            out.write(b"solid modelo\n")
        else:
            out.write(b"Conversor 3D".ljust(80, b" ") + np.uint32(total).tobytes())
        for part in model.parts:
            verts = part.vertices.astype(np.float32)
            for start in range(0, len(part.faces), step):
                tri = verts[part.faces[start:start + step]]
                normals = _normals(tri)
                if ascii:
                    rows = np.concatenate([normals[:, None, :], tri], axis=1).reshape(-1, 12)
                    lines = [("facet normal %.6e %.6e %.6e\n outer loop\n  vertex %.6e %.6e %.6e\n  vertex %.6e %.6e %.6e\n"
                              "  vertex %.6e %.6e %.6e\n endloop\nendfacet\n") % tuple(r) for r in rows.tolist()]
                    out.write("".join(lines).encode("ascii"))
                else:
                    records = np.zeros(len(tri), dtype=STL_RECORD)
                    records["normal"], records["v"] = normals, tri
                    out.write(records.tobytes())
        if ascii:
            out.write(b"endsolid modelo\n")


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
            np.savetxt(out, part.vertices, fmt="v %.9g %.9g %.9g")
            faces = part.faces + offset + 1
            if colors and part.colors is not None:
                cols = part.colors
                unique, inverse = np.unique(cols, axis=0, return_inverse=True)
                if len(unique) > MAX_COLORS_OBJ:
                    # Paleta reducida a 6 niveles por canal de color (216 como mucho); la transparencia se conserva.
                    cols = cols.copy()
                    cols[:, :3] = np.round(cols[:, :3] / 51).astype(np.uint8) * 51
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
                if colors:  # una pieza sin color tras otras con color no hereda su material: gris (D-249)
                    if DEFAULT_GREY not in palette:
                        palette[DEFAULT_GREY] = "sin_color"
                        lines_mtl += ["newmtl sin_color", "Kd 0.7843 0.7843 0.7843", "d 1.0000", "illum 1", ""]
                    out.write(f"usemtl {palette[DEFAULT_GREY]}\n")
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
