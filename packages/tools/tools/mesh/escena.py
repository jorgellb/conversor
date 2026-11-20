"""VRML97 (.wrl) y X3D (.x3d) propios (7.18, F7-C, D-250): las dos codificaciones del mismo grafo de escena.

Se leen `Transform` (traslación, giro eje-ángulo, escala y centro), `Group`, `Shape` con `Appearance`/`Material`
(`diffuseColor`, `transparency`), `IndexedFaceSet` (polígonos en abanico, `color` por cara o por vértice) e
`IndexedTriangleSet`, con `DEF`/`USE`: cada uso de un nodo cuenta sus triángulos (las instancias multiplican) y nada de
fuera se carga (`Inline` y las texturas se ignoran). VRML y X3D usan Y vertical por especificación; las unidades no se
guardan (milímetros salvo que se diga otra cosa, que es lo que usan los servicios de impresión en color).
Se escriben como una `Shape` por pieza con `IndexedFaceSet` y, si hay colores, `colorPerVertex FALSE`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from lxml import etree

from core.errors import ErrorCode, ToolError
from tools.mesh.formats import DEFAULT_GREY, Model, Part

PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
MAX_DEPTH = 64
MAX_PARTS = 10_000


@dataclass
class Node:
    kind: str
    fields: dict = field(default_factory=dict)


# ——— VRML97: tokens y nodos ———

TOKEN = re.compile(rb'"(?:[^"\\]|\\.)*"|[\[\]{}]|[^\s\[\]{}",#]+')


def _tokens(data: bytes):
    # Sin comentarios (# hasta el final de línea, fuera de cadenas) y con las comas como espacio.
    for line in data.splitlines():
        if b"#" in line:
            out, quoted = bytearray(), False
            for ch in line:
                if ch == 34:
                    quoted = not quoted
                if ch == 35 and not quoted:
                    break
                out.append(ch)
            line = bytes(out)
        yield from TOKEN.findall(line)


class _Vrml:
    def __init__(self, data: bytes):
        self.tokens = list(_tokens(data))
        self.i = 0
        self.defs: dict[str, Node] = {}

    def peek(self) -> bytes | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self) -> bytes:
        if self.i >= len(self.tokens):
            raise ToolError(ErrorCode.CORRUPT_FILE, "VRML incompleto")
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def nodes(self, depth: int = 0) -> list[Node]:
        out = []
        while (tok := self.peek()) is not None and tok not in (b"]", b"}"):
            if tok in (b"PROTO", b"EXTERNPROTO", b"ROUTE"):
                raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "vrml_proto")
            node = self.node(depth)
            if node is not None:
                out.append(node)
        return out

    def node(self, depth: int) -> Node | None:
        if depth > MAX_DEPTH:
            raise ToolError(ErrorCode.CORRUPT_FILE, "VRML anidado en exceso")
        tok = self.take()
        if tok == b"USE":
            name = self.take().decode("utf-8", "replace")
            return self.defs.get(name)
        name = None
        if tok == b"DEF":
            name = self.take().decode("utf-8", "replace")
            tok = self.take()
        if tok == b"NULL":
            return None
        kind = tok.decode("utf-8", "replace")
        if self.take() != b"{":
            raise ToolError(ErrorCode.CORRUPT_FILE, f"VRML no válido cerca de {kind}")
        node = Node(kind)
        while (key := self.take()) != b"}":
            fname = key.decode("utf-8", "replace")
            nxt = self.peek()
            if nxt == b"[":
                self.take()
                inner = self.peek()
                if inner is not None and (inner[:1].isalpha() and inner not in (b"TRUE", b"FALSE") or inner in (b"DEF", b"USE")):
                    node.fields[fname] = self.nodes(depth + 1)
                    if self.take() != b"]":
                        raise ToolError(ErrorCode.CORRUPT_FILE, "VRML no válido: falta «]»")
                else:
                    values = []
                    while (v := self.take()) != b"]":
                        values.append(v)
                    node.fields[fname] = values
            elif nxt is not None and (nxt[:1].isalpha() and nxt not in (b"TRUE", b"FALSE")) and self._is_node_start():
                node.fields[fname] = self.node(depth + 1)
            else:
                values = [self.take()]
                while (v := self.peek()) is not None and _is_number(v):
                    values.append(self.take())
                node.fields[fname] = values
        if name:
            self.defs[name] = node
        return node

    def _is_node_start(self) -> bool:
        tok = self.peek()
        if tok in (b"DEF", b"USE", b"NULL"):
            return True
        return self.i + 1 < len(self.tokens) and self.tokens[self.i + 1] == b"{"


NUM = re.compile(rb"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$")


def _is_number(tok: bytes) -> bool:
    return bool(NUM.match(tok))


def parse_vrml(path: Path) -> list[Node]:
    data = path.read_bytes()
    if not data.lstrip().startswith(b"#VRML V2.0"):
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "vrml_version")
    parser = _Vrml(data)
    nodes = parser.nodes()
    return nodes


# ——— X3D (XML) ———

def parse_x3d(path: Path) -> list[Node]:
    try:
        tree = etree.parse(str(path), PARSER)
    except etree.XMLSyntaxError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "X3D ilegible") from exc
    if tree.docinfo.internalDTD is not None:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities")
    root = tree.getroot()
    scene = next((c for c in root.iter() if isinstance(c.tag, str) and etree.QName(c).localname == "Scene"), None)
    if scene is None:
        raise ToolError(ErrorCode.CORRUPT_FILE, "X3D sin escena")
    defs: dict[str, Node] = {}

    def convert(el, depth: int) -> Node | None:
        if depth > MAX_DEPTH:
            raise ToolError(ErrorCode.CORRUPT_FILE, "X3D anidado en exceso")
        if el.get("USE"):
            return defs.get(el.get("USE"))
        node = Node(etree.QName(el).localname)
        for key, value in el.attrib.items():
            if key not in ("DEF", "USE", "containerField"):
                node.fields[key] = value.replace(",", " ").split()
        kids = [convert(c, depth + 1) for c in el if isinstance(c.tag, str)]
        kids = [k for k in kids if k is not None]
        for kid in kids:
            slot = {"Appearance": "appearance", "Material": "material", "Coordinate": "coord", "Color": "color",
                    "ColorRGBA": "color"}.get(kid.kind)
            if slot is None and kid.kind in ("IndexedFaceSet", "IndexedTriangleSet", "Box", "Sphere", "Cylinder", "Cone"):
                slot = "geometry"
            if slot:
                node.fields[slot] = kid
            else:
                node.fields.setdefault("children", []).append(kid)
        if el.get("DEF"):
            defs[el.get("DEF")] = node
        return node

    return [n for n in (convert(c, 0) for c in scene if isinstance(c.tag, str)) if n is not None]


# ——— Evaluación del grafo ———

def _floats(values) -> np.ndarray:
    try:
        return np.array([float(v) for v in values], dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "Número no válido en la escena") from exc


def _ints(values) -> np.ndarray:
    try:
        return np.array([int(float(v)) for v in values], dtype=np.int64)
    except (TypeError, ValueError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "Índice no válido en la escena") from exc


def _vec(node: Node, name: str, default) -> np.ndarray:
    v = node.fields.get(name)
    if not isinstance(v, list) or not v or isinstance(v[0], Node):
        return np.array(default, dtype=np.float64)
    arr = _floats(v)
    return arr if len(arr) == len(default) else np.array(default, dtype=np.float64)


def _axis_angle(x: float, y: float, z: float, angle: float) -> np.ndarray:
    axis = np.array([x, y, z])
    norm = np.linalg.norm(axis)
    if norm == 0 or angle == 0:
        return np.eye(3)
    x, y, z = axis / norm
    c, s, t = np.cos(angle), np.sin(angle), 1 - np.cos(angle)
    return np.array([[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                     [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                     [t * x * z - s * y, t * y * z + s * x, t * z * z + c]])


def _transform(node: Node) -> np.ndarray:
    t = _vec(node, "translation", (0, 0, 0))
    r = _vec(node, "rotation", (0, 0, 1, 0))
    s = _vec(node, "scale", (1, 1, 1))
    c = _vec(node, "center", (0, 0, 0))
    m = np.eye(4)
    m[:3, :3] = _axis_angle(*r) @ np.diag(s)
    m[:3, 3] = t + c - m[:3, :3] @ c
    return m


def _color(node: Node | None) -> tuple[int, int, int, int] | None:
    app = node.fields.get("appearance") if node else None
    mat = app.fields.get("material") if isinstance(app, Node) else None
    if not isinstance(mat, Node):
        return None
    rgb = _vec(mat, "diffuseColor", (0.8, 0.8, 0.8))
    alpha = 1.0 - float(_vec(mat, "transparency", (0.0,))[0])
    return tuple(int(round(max(0.0, min(1.0, v)) * 255)) for v in (*rgb, alpha))  # type: ignore[return-value]


def _geometry(geom: Node, shape_color) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    coord = geom.fields.get("coord")
    if not isinstance(coord, Node):
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), None
    points = _floats(coord.fields.get("point", []))
    verts = points[: len(points) // 3 * 3].reshape(-1, 3)
    if geom.kind == "IndexedTriangleSet":
        idx = _ints(geom.fields.get("index", []))
        faces = idx[: len(idx) // 3 * 3].reshape(-1, 3)
        polygon_of = np.arange(len(faces))
    else:
        idx = _ints(geom.fields.get("coordIndex", []))
        faces_list, polygon_of_list, polygon = [], [], []
        n_poly = 0
        for i in list(idx) + [-1]:
            if i < 0:
                for k in range(1, len(polygon) - 1):  # abanico
                    faces_list.append((polygon[0], polygon[k], polygon[k + 1]))
                    polygon_of_list.append(n_poly)
                if polygon:
                    n_poly += 1
                polygon = []
            else:
                polygon.append(int(i))
        faces = np.array(faces_list, dtype=np.int64).reshape(-1, 3)
        polygon_of = np.array(polygon_of_list, dtype=np.int64)
    if len(faces) and (faces.min() < 0 or faces.max() >= len(verts)):
        raise ToolError(ErrorCode.CORRUPT_FILE, "Caras que apuntan a vértices que no existen")
    colors = None
    color_node = geom.fields.get("color")
    if isinstance(color_node, Node) and len(faces):
        width = 4 if color_node.kind == "ColorRGBA" else 3
        cvals = _floats(color_node.fields.get("color", []))
        table = cvals[: len(cvals) // width * width].reshape(-1, width)
        if len(table):
            per_vertex = (geom.fields.get("colorPerVertex", [b"TRUE"])[0] in (b"TRUE", "true", "TRUE"))
            if per_vertex:
                pick = np.clip(faces[:, 0], 0, len(table) - 1)  # el color del primer vértice de cada triángulo
            else:
                pick = np.clip(polygon_of, 0, len(table) - 1)
            rgb = np.clip(table[pick][:, :3] * 255, 0, 255).round().astype(np.uint8)
            alpha = (np.clip(table[pick][:, 3] * 255, 0, 255).round().astype(np.uint8) if width == 4
                     else np.full(len(faces), 255, np.uint8))
            colors = np.c_[rgb, alpha]
    if colors is None and shape_color is not None and len(faces):
        colors = np.tile(np.array(shape_color, dtype=np.uint8), (len(faces), 1))
    return verts, faces, colors


def evaluate(nodes: list[Node], max_triangles: int) -> Model:
    model = Model(parts=[], unit_mm=None, up="y")
    total = 0

    def walk(node: Node, transform: np.ndarray, depth: int, name: str) -> None:
        nonlocal total
        if depth > MAX_DEPTH:
            raise ToolError(ErrorCode.CORRUPT_FILE, "Escena anidada en exceso")
        if node.kind == "Transform":
            transform = transform @ _transform(node)
        if node.kind == "Shape":
            geom = node.fields.get("geometry")
            if isinstance(geom, Node) and geom.kind in ("IndexedFaceSet", "IndexedTriangleSet"):
                verts, faces, colors = _geometry(geom, _color(node))
                if len(faces):
                    total += len(faces)
                    if total > max_triangles or len(model.parts) >= MAX_PARTS:
                        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "mesh_triangles")
                    v = (np.c_[verts, np.ones(len(verts))] @ transform.T)[:, :3]
                    if np.linalg.det(transform[:3, :3]) < 0:
                        faces = faces[:, ::-1]
                    model.parts.append(Part(name or f"objeto-{len(model.parts) + 1}", v, faces, colors))
            return
        for child in node.fields.get("children", []) or []:
            if isinstance(child, Node):
                walk(child, transform, depth + 1, name)

    for n, node in enumerate(nodes):
        walk(node, np.eye(4), 0, "")
    if not model.parts:
        raise ToolError(ErrorCode.CORRUPT_FILE, "La escena no tiene ninguna malla")
    return model


def read_scene(path: Path, ext: str, max_triangles: int) -> Model:
    nodes = parse_vrml(path) if ext == "wrl" else parse_x3d(path)
    return evaluate(nodes, max_triangles)


# ——— Escritura ———

def _part_arrays(part: Part):
    colors = part.colors if part.colors is not None else None
    return part.vertices, part.faces, colors


def write_wrl(model: Model, dst: Path) -> None:
    with open(dst, "w", encoding="utf-8", newline="\n") as out:
        out.write("#VRML V2.0 utf8\n# Conversor 3D\n")
        for part in model.parts:
            verts, faces, colors = _part_arrays(part)
            name = re.sub(r"[^A-Za-z0-9_]", "_", part.name)[:60] or "pieza"
            grey = np.array(DEFAULT_GREY[:3]) / 255
            out.write(f"DEF {name if name[0].isalpha() else 'p_' + name} Shape {{\n appearance Appearance {{ material Material {{ diffuseColor "
                      f"{grey[0]:.4f} {grey[1]:.4f} {grey[2]:.4f} }} }}\n geometry IndexedFaceSet {{\n  solid TRUE\n  coord Coordinate {{ point [\n")
            np.savetxt(out, verts, fmt="   %.9g %.9g %.9g,")
            out.write("  ] }\n  coordIndex [\n")
            np.savetxt(out, faces, fmt="   %d %d %d -1,")
            out.write("  ]\n")
            if colors is not None:
                unique, inverse = np.unique(colors[:, :3], axis=0, return_inverse=True)
                out.write("  colorPerVertex FALSE\n  color Color { color [\n")
                np.savetxt(out, unique / 255.0, fmt="   %.4f %.4f %.4f,")
                out.write("  ] }\n  colorIndex [\n")
                np.savetxt(out, inverse.reshape(-1, 1), fmt="   %d")
                out.write("  ]\n")
            out.write(" }\n}\n")


def write_x3d(model: Model, dst: Path) -> None:
    x3d = etree.Element("X3D", profile="Interchange", version="3.3")
    scene = etree.SubElement(x3d, "Scene")
    for part in model.parts:
        verts, faces, colors = _part_arrays(part)
        shape = etree.SubElement(scene, "Shape")
        app = etree.SubElement(shape, "Appearance")
        etree.SubElement(app, "Material", diffuseColor=" ".join(f"{c / 255:.4f}" for c in DEFAULT_GREY[:3]))
        attrs = {"solid": "true", "coordIndex": " ".join(f"{a} {b} {c} -1" for a, b, c in faces.tolist())}
        if colors is not None:
            unique, inverse = np.unique(colors[:, :3], axis=0, return_inverse=True)
            attrs["colorPerVertex"] = "false"
            attrs["colorIndex"] = " ".join(str(i) for i in inverse.reshape(-1).tolist())
        ifs = etree.SubElement(shape, "IndexedFaceSet", **attrs)
        etree.SubElement(ifs, "Coordinate", point=" ".join(f"{x:.9g} {y:.9g} {z:.9g}" for x, y, z in verts.tolist()))
        if colors is not None:
            etree.SubElement(ifs, "Color", color=" ".join(f"{r / 255:.4f} {g / 255:.4f} {b / 255:.4f}" for r, g, b in unique.tolist()))
    dst.write_bytes(etree.tostring(x3d, xml_declaration=True, encoding="UTF-8", pretty_print=True))


def write_off(model: Model, dst: Path) -> None:
    from tools.mesh.formats import merged

    part = merged(model).parts[0]
    with open(dst, "w", encoding="utf-8", newline="\n") as out:
        out.write(f"OFF\n{len(part.vertices)} {len(part.faces)} 0\n")
        np.savetxt(out, part.vertices, fmt="%.9g %.9g %.9g")
        np.savetxt(out, part.faces, fmt="3 %d %d %d")
