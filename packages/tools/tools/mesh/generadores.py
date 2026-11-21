"""Generadores de F7-G (7.20, D-254): svg-a-stl, dxf-a-stl, imagen-a-stl, logo-a-stl, texto-a-stl, litofania y
mapa-de-alturas-a-stl. Contornos 2D (svgelements, ezdxf, vtracer, fontTools) extruidos con `CrossSection` de manifold3d,
que une los solapes y respeta los agujeros, y relieves de imagen como rejilla cerrada. Todo en milímetros y en el proceso
hijo de las mallas (D-249).
"""
from __future__ import annotations

import io
import math
import re
from pathlib import Path

import numpy as np

from core.errors import ErrorCode, ToolError
from tools.mesh.formats import Model, Part

PX_MM = 25.4 / 96  # un píxel de SVG (CSS) en milímetros
MAX_CONTOURS = 20_000
MAX_POINTS = 2_000_000
MAX_IMAGE_SIDE = 4096
FONTS = {
    "sans": "DejaVuSans.ttf", "sans-negrita": "DejaVuSans-Bold.ttf", "serif": "DejaVuSerif.ttf", "serif-negrita": "DejaVuSerif-Bold.ttf",
    "mono": "DejaVuSansMono.ttf", "condensada": "DejaVuSansCondensed-Bold.ttf",
}
FONT_DIRS = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/TTF", "/usr/share/fonts/dejavu")

TEXTS = {
    "es": {"missing_glyphs": "La fuente no tiene estos caracteres y salen como un recuadro: {chars}. Prueba con otra fuente.",
           "extruded": "{n} contornos extruidos a {h:g} mm: {dims}.", "levels": "{n} niveles de altura de {step:g} mm sobre una base de {b:g} mm: {dims}.",
           "litho": "Litofanía {shape} de {w:g} × {h:g} mm, de {a:g} a {b:g} mm de grosor ({px} × {py} píxeles).",
           "relief": "Relieve de {w:g} × {d:g} mm, hasta {h:g} mm sobre una base de {b:g} mm ({px} × {py} píxeles).",
           "text": "Texto de {n} caracteres en {font}: {dims}.", "shapes": {"plana": "plana", "curva": "curva", "cilindrica": "cilíndrica"}},
    "en": {"missing_glyphs": "The font does not have these characters and they come out as a box: {chars}. Try another font.",
           "extruded": "{n} contours extruded to {h:g} mm: {dims}.", "levels": "{n} height levels of {step:g} mm on a {b:g} mm base: {dims}.",
           "litho": "{shape} lithophane of {w:g} × {h:g} mm, {a:g} to {b:g} mm thick ({px} × {py} pixels).",
           "relief": "Relief of {w:g} × {d:g} mm, up to {h:g} mm on a {b:g} mm base ({px} × {py} pixels).",
           "text": "Text of {n} characters in {font}: {dims}.", "shapes": {"plana": "Flat", "curva": "Curved", "cilindrica": "Cylindrical"}},
}


def _t(locale: str) -> dict:
    return TEXTS.get(locale, TEXTS["es"])


def _dims(parts: list[Part]) -> str:
    v = np.vstack([p.vertices for p in parts])
    x, y, z = np.ptp(v, axis=0)
    return f"{x:.1f} × {y:.1f} × {z:.1f} mm"


# ——— Extrusión de contornos ———

def extrude(contours: list[np.ndarray], height: float, rule: str = "nonzero", z0: float = 0.0):
    import manifold3d as m3

    contours = [c for c in contours if len(c) >= 3 and abs(_area(c)) > 1e-9]
    if not contours:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "gen_no_shapes")
    if len(contours) > MAX_CONTOURS or sum(len(c) for c in contours) > MAX_POINTS:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "gen_too_complex")
    fill = m3.FillRule.EvenOdd if rule == "evenodd" else m3.FillRule.NonZero
    section = m3.CrossSection([np.ascontiguousarray(c, dtype=np.float64) for c in contours], fill)
    if section.is_empty():
        raise ToolError(ErrorCode.INVALID_OPTIONS, "gen_no_shapes")
    solid = m3.Manifold.extrude(section, float(height))
    return solid.translate((0.0, 0.0, float(z0))) if z0 else solid


def _area(c: np.ndarray) -> float:
    x, y = c[:, 0], c[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def to_part(solid, name: str) -> Part:
    mesh = solid.to_mesh()
    return Part(name, np.asarray(mesh.vert_properties, np.float64)[:, :3], np.asarray(mesh.tri_verts, np.int64))


def fit_width(contours: list[np.ndarray], width_mm: float) -> list[np.ndarray]:
    """Escala a un ancho en milímetros (0: tal cual) y lleva la esquina inferior izquierda al origen."""
    pts = np.vstack(contours)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    f = width_mm / (hi[0] - lo[0]) if width_mm and hi[0] > lo[0] else 1.0
    return [(c - lo) * f for c in contours]


def with_base(solid, contours: list[np.ndarray], base_mm: float, margin: float):
    """Una placa rectangular bajo la figura (que sube `base_mm`), unida en un solo sólido."""
    import manifold3d as m3

    if base_mm <= 0:
        return solid
    pts = np.vstack(contours)
    lo, hi = pts.min(axis=0) - margin, pts.max(axis=0) + margin
    plate = m3.Manifold.cube((float(hi[0] - lo[0]), float(hi[1] - lo[1]), float(base_mm))).translate((float(lo[0]), float(lo[1]), 0.0))
    return plate + solid.translate((0.0, 0.0, float(base_mm)))


# ——— SVG ———

def _subpath_points(sub) -> np.ndarray:
    """Puntos de un subcamino: los vértices de los tramos rectos tal cual (las esquinas no se achaflanan) y las curvas
    muestreadas cada 0,25 px (D-258)."""
    from svgelements import Close, Line, Move

    pts = []
    for seg in sub:
        if isinstance(seg, Move):
            if seg.end is not None:
                pts.append((seg.end.x, seg.end.y))
            continue
        if isinstance(seg, (Line, Close)):
            if seg.end is not None:
                pts.append((seg.end.x, seg.end.y))
            continue
        length = seg.length(error=1e-3) if hasattr(seg, "length") else 0
        n = int(min(1000, max(4, (length or 0) / 0.25)))
        sampled = np.asarray(seg.npoint(np.linspace(0, 1, n + 1)), dtype=np.float64).reshape(-1, 2)
        pts.extend(map(tuple, sampled[1:]))
    return np.asarray(pts, dtype=np.float64).reshape(-1, 2)


def svg_shapes(data: bytes) -> tuple[list[np.ndarray], list[tuple[int, int, str]]]:
    """Contornos de las formas con relleno del SVG y, por cada forma, su rango de contornos y su regla de relleno: cada
    forma se rellena con su regla y luego se unen todas, como las pinta un navegador (D-258)."""
    from svgelements import SVG, Path as SvgPath, Shape

    head = data[:4096].lower()
    if b"<!entity" in head or b"<!doctype" in head:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities")
    try:
        svg = SVG.parse(io.BytesIO(data), reify=True, ppi=96.0)
    except Exception as exc:  # noqa: BLE001 - svgelements lanza de todo con SVG rotos
        raise ToolError(ErrorCode.CORRUPT_FILE, "SVG ilegible") from exc
    contours: list[np.ndarray] = []
    groups: list[tuple[int, int, str]] = []
    points = 0
    for element in svg.elements():
        if not isinstance(element, Shape):
            continue
        fill = element.fill
        if fill is None or getattr(fill, "value", None) is None:
            continue  # sin relleno (solo trazo): no se extruye
        rule = "evenodd" if str(element.values.get("fill-rule", "")).lower() == "evenodd" else "nonzero"
        first = len(contours)
        for sub in SvgPath(element).as_subpaths():
            pts = _subpath_points(SvgPath(sub))
            if len(pts) < 3:
                continue
            points += len(pts)
            if len(contours) >= MAX_CONTOURS or points > MAX_POINTS:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "gen_too_complex")
            contours.append(pts * [PX_MM, -PX_MM])  # Y del SVG hacia abajo
        if len(contours) > first:
            groups.append((first, len(contours), rule))
    if not contours:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "gen_no_shapes")
    return contours, groups


def svg_contours(data: bytes) -> tuple[list[np.ndarray], str]:
    contours, groups = svg_shapes(data)
    return contours, "evenodd" if any(g[2] == "evenodd" for g in groups) else "nonzero"


def extrude_groups(contours: list[np.ndarray], groups: list[tuple[int, int, str]], height: float):
    """Cada forma con su regla de relleno y todas unidas antes de extruir."""
    import manifold3d as m3

    if sum(len(c) for c in contours) > MAX_POINTS:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "gen_too_complex")
    sections = []
    for a, b, rule in groups:
        part = [np.ascontiguousarray(c, dtype=np.float64) for c in contours[a:b] if len(c) >= 3 and abs(_area(c)) > 1e-9]
        if part:
            sections.append(m3.CrossSection(part, m3.FillRule.EvenOdd if rule == "evenodd" else m3.FillRule.NonZero))
    if not sections:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "gen_no_shapes")
    section = sections[0] if len(sections) == 1 else m3.CrossSection.batch_boolean(sections, m3.OpType.Add)
    if section.is_empty():
        raise ToolError(ErrorCode.INVALID_OPTIONS, "gen_no_shapes")
    return m3.Manifold.extrude(section, float(height))


def from_svg(data: bytes, options: dict, locale: str, notes: list[str], name: str) -> Model:
    contours, groups = svg_shapes(data)
    contours = fit_width(contours, float(options.get("ancho_mm", 0) or 0))
    height = float(options.get("altura_mm", 5))
    solid = with_base(extrude_groups(contours, groups, height), contours, float(options.get("base_mm", 0)), float(options.get("margen_mm", 3)))
    part = to_part(solid, name)
    notes.append(_t(locale)["extruded"].format(n=len(contours), h=height, dims=_dims([part])))
    return Model([part], 1.0, set(), "z")


# ——— DXF ———

DXF_UNITS = {0: 1.0, 1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0, 13: 0.001, 14: 100.0}


def dxf_contours(path: Path) -> list[np.ndarray]:
    """Contornos cerrados de un DXF: polilíneas cerradas, círculos, elipses y splines cerrados, y cadenas de líneas y arcos
    que cierran (enlazadas por sus extremos)."""
    import ezdxf
    from ezdxf import path as epath
    from ezdxf import recover

    try:
        doc, auditor = recover.readfile(str(path))
    except (OSError, ezdxf.DXFStructureError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "DXF ilegible") from exc
    unit = DXF_UNITS.get(int(doc.header.get("$INSUNITS", 4) or 4), 1.0)
    closed, open_paths = [], []
    for entity in doc.modelspace():
        if entity.dxftype() not in ("LWPOLYLINE", "POLYLINE", "CIRCLE", "ELLIPSE", "SPLINE", "LINE", "ARC"):
            continue
        try:
            p = epath.make_path(entity)
        except Exception:  # noqa: BLE001 - entidad sin geometría útil
            continue
        pts = np.array([(v.x, v.y) for v in p.flattening(0.05 / unit)], dtype=np.float64)  # 0,05 mm en cualquier unidad
        if len(pts) < 2:
            continue
        if entity.dxftype() == "CIRCLE" or p.is_closed or np.allclose(pts[0], pts[-1], atol=1e-6):
            if len(pts) >= 3:
                closed.append(pts[:-1] if np.allclose(pts[0], pts[-1]) else pts)
        else:
            open_paths.append(pts)
        if len(closed) + len(open_paths) > MAX_CONTOURS:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "gen_too_complex")
    closed += _link(open_paths)
    if not closed:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "gen_no_shapes")
    return [c * unit for c in closed]


def _link(paths: list[np.ndarray], tol: float = 1e-4) -> list[np.ndarray]:
    """Une tramos abiertos por sus extremos hasta cerrar contornos. Los extremos van en una rejilla de `tol` (se miran las
    celdas vecinas): lineal en el número de tramos (D-258: con la búsqueda por pares, 7000 líneas tardaban minutos)."""
    paths = [p for p in paths if len(p) >= 2]
    cells: dict[tuple[int, int], set[int]] = {}

    def key(pt) -> tuple[int, int]:
        return (int(round(pt[0] / tol)), int(round(pt[1] / tol)))

    for i, p in enumerate(paths):
        for end_pt in (p[0], p[-1]):
            cells.setdefault(key(end_pt), set()).add(i)
    used = [False] * len(paths)

    def take(pt, skip: int) -> tuple[int, bool] | None:
        kx, ky = key(pt)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in cells.get((kx + dx, ky + dy), ()):
                    if used[j] or j == skip:
                        continue
                    q = paths[j]
                    if np.allclose(pt, q[0], atol=tol):
                        return j, False
                    if np.allclose(pt, q[-1], atol=tol):
                        return j, True
        return None

    loops = []
    for i, start in enumerate(paths):
        if used[i]:
            continue
        used[i] = True
        pieces = [start]
        head, tail = start[0], start[-1]
        while not np.allclose(head, tail, atol=tol):
            found = take(tail, i)
            if found is None:
                break
            j, reverse = found
            used[j] = True
            q = paths[j][::-1] if reverse else paths[j]
            pieces.append(q[1:])
            tail = q[-1]
        chain = np.vstack(pieces)
        if len(chain) >= 4 and np.allclose(chain[0], chain[-1], atol=tol):
            loops.append(chain[:-1])
    return loops


def from_dxf(path: Path, options: dict, locale: str, notes: list[str], name: str) -> Model:
    contours = dxf_contours(path)
    contours = fit_width(contours, float(options.get("ancho_mm", 0) or 0))
    height = float(options.get("altura_mm", 5))
    solid = with_base(extrude(contours, height, "evenodd"), contours, float(options.get("base_mm", 0)), float(options.get("margen_mm", 3)))
    part = to_part(solid, name)
    notes.append(_t(locale)["extruded"].format(n=len(contours), h=height, dims=_dims([part])))
    return Model([part], 1.0, set(), "z")


# ——— Imágenes: logo (un nivel) e imagen (varios niveles) ———

def _open_gray(path: Path, max_side: int = 1600, precise: bool = False):
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = 100_000_000
    try:
        img = Image.open(path)
        img.draft("L", (max_side, max_side))
        img = ImageOps.exif_transpose(img)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(ErrorCode.CORRUPT_FILE, "Imagen no válida") from exc
    if img.mode in ("I;16", "I;16B", "I;16L", "I", "F"):
        # 16 bits o coma flotante (mapas de alturas de terreno): se reparten en 0-255 por su rango real, no se recortan
        # a 255 como haría convert("L") (D-258). En modo F para no perder precisión al reducir.
        arr = np.asarray(img, dtype=np.float64)
        lo, hi = float(arr.min()), float(arr.max())
        img = Image.fromarray(((arr - lo) / (hi - lo or 1.0) * 255.0).astype(np.float32), mode="F")
        img.thumbnail((max_side, max_side))
        return img if precise else img.convert("L")
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        white = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(white, img)
    img = img.convert("L")
    img.thumbnail((max_side, max_side))
    return img


def _mask_contours(mask: np.ndarray, pixel_mm: float) -> list[np.ndarray]:
    """Contornos de una máscara binaria con vtracer (modo polígono, sin motas de menos de 4 píxeles)."""
    import vtracer
    from PIL import Image

    png = io.BytesIO()
    Image.fromarray(np.where(mask, 0, 255).astype(np.uint8)).convert("RGB").save(png, "PNG")
    svg = vtracer.convert_raw_image_to_svg(png.getvalue(), img_format="png", colormode="binary", mode="polygon", filter_speckle=4,
                                           corner_threshold=60, length_threshold=4.0, path_precision=3)
    contours, _rule = svg_contours(svg.encode("utf-8"))
    # vtracer dibuja en píxeles de la imagen: de «px de SVG» a píxeles y de ahí a milímetros.
    return [c / PX_MM * pixel_mm for c in contours]


def from_logo(path: Path, options: dict, locale: str, notes: list[str], name: str) -> Model:
    img = _open_gray(path)
    gray = np.asarray(img, dtype=np.uint8)
    threshold = int(options.get("umbral", 128))
    mask = gray < threshold
    if options.get("invertir", False):
        mask = ~mask
    if not mask.any():
        raise ToolError(ErrorCode.INVALID_OPTIONS, "gen_no_shapes")
    width = float(options.get("ancho_mm", 80))
    contours = _mask_contours(mask, width / gray.shape[1])
    height = float(options.get("altura_mm", 3))
    solid = with_base(extrude(contours, height, "evenodd"), contours, float(options.get("base_mm", 0)), float(options.get("margen_mm", 3)))
    part = to_part(solid, name)
    notes.append(_t(locale)["extruded"].format(n=len(contours), h=height, dims=_dims([part])))
    return Model([part], 1.0, set(), "z")


def from_image_levels(path: Path, options: dict, locale: str, notes: list[str], name: str) -> Model:
    """Relieve por niveles: las zonas más oscuras, más altas (o al revés), en escalones apilados y unidos."""
    import manifold3d as m3

    img = _open_gray(path, 1200)
    gray = np.asarray(img, dtype=np.float64)
    if options.get("invertir", False):
        gray = 255 - gray
    levels = int(options.get("niveles", 4))
    width = float(options.get("ancho_mm", 100))
    pixel = width / gray.shape[1]
    top = float(options.get("altura_mm", 4))
    base = float(options.get("base_mm", 1))
    step = top / levels
    plate = m3.Manifold.cube((width, gray.shape[0] * pixel, base))
    solids = [plate]
    for k in range(1, levels + 1):
        mask = gray < 255 * (1 - k / (levels + 1))  # cuanto más oscuro, más niveles alcanza
        if not mask.any():
            continue
        contours = [c + [0.0, gray.shape[0] * pixel] for c in _mask_contours(mask, pixel)]
        solids.append(extrude(contours, step, "evenodd", z0=base + (k - 1) * step))
    solid = m3.Manifold.batch_boolean(solids, m3.OpType.Add)
    part = to_part(solid, name)
    notes.append(_t(locale)["levels"].format(n=len(solids) - 1, step=round(step, 3), b=base, dims=_dims([part])))
    return Model([part], 1.0, set(), "z")


# ——— Texto ———

class _FlatPen:
    """Pluma de fontTools que aplana las curvas en polilíneas."""

    def __init__(self, glyph_set, steps: int = 8):
        from fontTools.pens.basePen import BasePen

        pen = self

        class Pen(BasePen):
            def _moveTo(self, p):
                pen.current = [p]

            def _lineTo(self, p):
                pen.current.append(p)

            def _curveToOne(self, p1, p2, p3):
                p0 = pen.current[-1]
                for i in range(1, steps + 1):
                    t = i / steps
                    mt = 1 - t
                    pen.current.append((mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0],
                                        mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]))

            def _qCurveToOne(self, p1, p2):
                p0 = pen.current[-1]
                for i in range(1, steps + 1):
                    t = i / steps
                    mt = 1 - t
                    pen.current.append((mt**2 * p0[0] + 2 * mt * t * p1[0] + t**2 * p2[0], mt**2 * p0[1] + 2 * mt * t * p1[1] + t**2 * p2[1]))

            def _closePath(self):
                if len(pen.current) >= 3:
                    pen.contours.append(np.array(pen.current, dtype=np.float64))
                pen.current = []

            _endPath = _closePath

        self.contours: list[np.ndarray] = []
        self.current: list = []
        self.pen = Pen(glyph_set)


def font_path(key: str) -> Path:
    name = FONTS.get(key, FONTS["sans"])
    for folder in FONT_DIRS:
        candidate = Path(folder) / name
        if candidate.exists():
            return candidate
    raise ToolError(ErrorCode.ENGINE_FAILED, "gen_font")


def text_contours(text: str, font_key: str, size_mm: float, align: str) -> list[np.ndarray]:
    from fontTools.ttLib import TTFont

    font = TTFont(str(font_path(font_key)))
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm
    cap = getattr(font["OS/2"], "sCapHeight", 0) or 0.7 * upm
    scale = size_mm / cap
    line_height = 1.25 * upm
    contours = []
    lines = text.split("\n")
    widths = []
    for line in lines:
        widths.append(sum(font["hmtx"][cmap.get(ord(ch), ".notdef")][0] for ch in line))
    longest = max(widths) if widths else 0
    for row, line in enumerate(lines):
        x = {"izquierda": 0.0, "centro": (longest - widths[row]) / 2, "derecha": longest - widths[row]}.get(align, 0.0)
        y = -row * line_height
        for ch in line:
            gname = cmap.get(ord(ch), ".notdef")
            pen = _FlatPen(glyphs)
            glyphs[gname].draw(pen.pen)
            for c in pen.contours:
                contours.append((c + [x, y]) * scale)
            x += font["hmtx"][gname][0]
    return contours


def from_text(options: dict, locale: str, notes: list[str], name: str) -> Model:
    text = re.sub(r"[\x00-\x09\x0b-\x1f]", "", str(options.get("texto", ""))).strip("\n")
    if not text.strip():
        raise ToolError(ErrorCode.INVALID_OPTIONS, "gen_no_text")
    contours = text_contours(text, options.get("fuente", "sans-negrita"), float(options.get("tamano_mm", 10)), options.get("alineacion", "izquierda"))
    height = float(options.get("altura_mm", 3))
    solid = with_base(extrude(contours, height, "nonzero"), contours, float(options.get("base_mm", 0)), float(options.get("margen_mm", 3)))
    part = to_part(solid, name)
    font = Path(FONTS.get(options.get("fuente", "sans-negrita"), FONTS["sans"])).stem
    notes.append(_t(locale)["text"].format(n=len(text), font=font, dims=_dims([part])))
    from fontTools.ttLib import TTFont

    cmap = TTFont(str(font_path(options.get("fuente", "sans-negrita")))).getBestCmap()
    missing = sorted({ch for ch in text if ch not in "\n" and ord(ch) not in cmap})
    if missing:  # la fuente no los tiene: salen como un recuadro (D-258)
        notes.append(_t(locale)["missing_glyphs"].format(chars=" ".join(missing[:20])))
    return Model([part], 1.0, set(), "z")


# ——— Rejillas cerradas: litofanía y mapa de alturas ———

def grid_solid(top: np.ndarray, pixel: float, bottom: float = 0.0, periodic: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Sólido cerrado de una rejilla de alturas (filas × columnas, en mm): cara de arriba, de abajo y paredes. Con
    `periodic`, la última columna se cierra con la primera (cilindro) y no hay paredes laterales."""
    rows, cols = top.shape
    ys, xs = np.mgrid[0:rows, 0:cols]
    x = xs.ravel() * pixel
    y = (rows - 1 - ys.ravel()) * pixel  # la fila 0 de la imagen, arriba
    up = np.c_[x, y, top.ravel()]
    down = np.c_[x, y, np.full(rows * cols, bottom)]
    verts = np.vstack([up, down])
    n = rows * cols
    idx = np.arange(n).reshape(rows, cols)
    right = np.roll(idx, -1, axis=1) if periodic else idx[:, 1:]
    left = idx if periodic else idx[:, :-1]
    a, b = left[:-1], right[:-1]
    c, d = left[1:], right[1:]
    top_faces = np.r_[np.c_[a.ravel(), c.ravel(), b.ravel()], np.c_[b.ravel(), c.ravel(), d.ravel()]]
    bottom_faces = top_faces[:, ::-1] + n
    walls = []

    def wall(edge: np.ndarray, flip: bool) -> None:
        e0, e1 = edge[:-1], edge[1:]
        quads = np.r_[np.c_[e0, e1, e0 + n], np.c_[e1, e1 + n, e0 + n]]
        walls.append(quads[:, ::-1] if flip else quads)

    # Orientación hacia fuera: la fila 0 (arriba, +Y), la última (−Y), la columna 0 (−X) y la última (+X). En el cilindro, las
    # paredes de arriba y de abajo se cierran también en la costura.
    first, last = idx[0, :], idx[-1, :]
    if periodic:
        first, last = np.r_[first, first[:1]], np.r_[last, last[:1]]
    wall(first, False)
    wall(last, True)
    if not periodic:
        wall(idx[:, 0], True)
        wall(idx[:, -1], False)
    faces = np.vstack([top_faces, bottom_faces, *walls]).astype(np.int64)
    return verts, faces


def outward(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Caras hacia fuera: si el volumen con signo sale negativo, se invierten todas."""
    tri = verts[faces]
    signed = float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum()) / 6.0
    return faces[:, ::-1] if signed < 0 else faces


def _image_grid(path: Path, width_mm: float, resolution: float, max_triangles: int) -> tuple[np.ndarray, float]:
    from PIL import Image

    img = _open_gray(path, MAX_IMAGE_SIDE, precise=True)
    cols = int(max(8, min(width_mm * resolution, MAX_IMAGE_SIDE)))
    rows = int(max(8, round(cols * img.height / img.width)))
    if 4 * rows * cols > max_triangles:
        f = math.sqrt(max_triangles / (4 * rows * cols))
        cols, rows = max(8, int(cols * f)), max(8, int(rows * f))
    gray = np.asarray(img.resize((cols, rows), Image.LANCZOS), dtype=np.float64) / 255.0
    return gray, width_mm / (cols - 1)


def lithophane(path: Path, options: dict, locale: str, notes: list[str], name: str, max_triangles: int) -> Model:
    width = float(options.get("ancho_mm", 100))
    gray, pixel = _image_grid(path, width, float(options.get("resolucion", 5)), max_triangles)
    if options.get("espejo", False):
        gray = gray[:, ::-1]
    thin, thick = float(options.get("grosor_min", 0.8)), float(options.get("grosor_max", 3.0))
    if thin >= thick:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "litho_thickness")
    thickness = thin + (1.0 - gray) * (thick - thin)  # lo oscuro, más grueso: deja pasar menos luz
    shape = options.get("forma", "plana")
    periodic = shape == "cilindrica"
    verts, faces = grid_solid(thickness, pixel, 0.0, periodic)
    rows, cols = gray.shape
    if shape in ("curva", "cilindrica"):
        angle = math.radians(360.0 if periodic else float(options.get("angulo", 120)))
        span = cols * pixel if periodic else (cols - 1) * pixel
        radius = span / angle
        # Con el ángulo hacia −X la imagen se lee bien desde fuera, por el lado del relieve (D-258: antes salía al revés).
        theta = -(verts[:, 0] / span * angle - (0 if periodic else angle / 2))
        r = radius + verts[:, 2]  # la imagen por fuera
        verts = np.c_[r * np.sin(theta), r * np.cos(theta), verts[:, 1]]
    part = Part(name, verts, outward(verts, faces))
    t = _t(locale)
    height_mm = (rows - 1) * pixel
    notes.append(t["litho"].format(shape=t["shapes"][shape], w=round(width, 1), h=round(height_mm, 1), a=thin, b=thick, px=cols, py=rows))
    return Model([part], 1.0, set(), "z")


def heightmap(path: Path, options: dict, locale: str, notes: list[str], name: str, max_triangles: int) -> Model:
    width = float(options.get("ancho_mm", 100))
    gray, pixel = _image_grid(path, width, float(options.get("resolucion", 5)), max_triangles)
    if options.get("invertir", False):
        gray = 1.0 - gray
    base, top = float(options.get("base_mm", 2)), float(options.get("altura_mm", 10))
    verts, faces = grid_solid(base + gray * top, pixel, 0.0)
    rows, cols = gray.shape
    notes.append(_t(locale)["relief"].format(w=round(width, 1), d=round((rows - 1) * pixel, 1), h=top, b=base, px=cols, py=rows))
    return Model([Part(name, verts, outward(verts, faces))], 1.0, set(), "z")


def generate(tool: str, src: Path | None, ext: str, options: dict, locale: str, max_triangles: int, name: str) -> tuple[Model, list[str]]:
    notes: list[str] = []
    if tool == "svg-a-stl":
        model = from_svg(src.read_bytes(), options, locale, notes, name)
    elif tool == "dxf-a-stl":
        model = from_dxf(src, options, locale, notes, name)
    elif tool == "logo-a-stl":
        model = from_logo(src, options, locale, notes, name)
    elif tool == "imagen-a-stl":
        model = from_image_levels(src, options, locale, notes, name)
    elif tool == "texto-a-stl":
        model = from_text(options, locale, notes, name)
    elif tool == "litofania":
        model = lithophane(src, options, locale, notes, name, max_triangles)
    elif tool == "mapa-de-alturas-a-stl":
        model = heightmap(src, options, locale, notes, name, max_triangles)
    else:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT)
    if model.triangles > max_triangles:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "mesh_triangles")
    return model, notes
