"""Herramientas de mallas de F7-F (7.20, D-253): reparar-stl, reducir-poligonos, escalar-modelo-3d, cambiar-unidades-stl,
cortar-modelo-3d, separar-piezas, unir-modelos y analizar-stl, con trimesh, manifold3d (Apache-2.0) y fast-simplification
(MIT). Se ejecutan en el proceso hijo de las mallas (D-249), como las conversiones.
"""
from __future__ import annotations

import json
import math

import numpy as np

from core.errors import ErrorCode, ToolError
from tools.mesh.formats import UNITS_MM, Model, Part, merged

DENSITY = {"PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "TPU": 1.21}  # g/cm³

TEXTS = {
    "es": {
        "repair": "Reparada: {holes} huecos cerrados, {degenerate} caras degeneradas y {duplicates} repetidas quitadas, normales "
                  "orientadas{union}. {state}",
        "union": " y piezas solapadas unidas", "closed": "La malla queda cerrada (estanca).",
        "open": "La malla sigue abierta en {n} aristas: tiene huecos que no se han podido cerrar automáticamente.",
        "small": " Se han quitado {n} piezas sueltas pequeñas.", "colors_dropped": "Los colores no se conservan al modificar la malla.",
        "reduced": "{before} → {after} triángulos ({pct} % menos).",
        "scaled": "Escalado × {x:g} en X, × {y:g} en Y y × {z:g} en Z: {dims}.",
        "units": "Unidades: {src} → {dst} (× {f:g}): {dims}.",
        "cut": "Cortado por el plano {axis} = {pos:g} mm{capped}.", "capped": ", con la sección tapada",
        "not_capped": "; sin tapar la sección porque la malla no es cerrada (repárala antes para taparla)",
        "pieces": "{n} piezas separadas.", "one_piece": "El modelo es una sola pieza: no hay nada que separar.",
        "joined": "{n} modelos unidos{union}.", "joined_union": " en un solo sólido (unión booleana)",
        "empty_cut": "El plano no corta el modelo: la parte pedida queda vacía.",
        "estimate": "Estimación de {mat}: {g:.1f} g y {m:.2f} m de filamento de {d} mm con un {r} % de relleno.",
    },
    "en": {
        "repair": "Repaired: {holes} holes closed, {degenerate} degenerate and {duplicates} duplicate faces removed, normals "
                  "oriented{union}. {state}",
        "union": " and overlapping parts merged", "closed": "The mesh is now closed (watertight).",
        "open": "The mesh is still open at {n} edges: it has holes that could not be closed automatically.",
        "small": " {n} small loose parts were removed.", "colors_dropped": "Colours are not kept when the mesh is modified.",
        "reduced": "{before} → {after} triangles ({pct}% fewer).",
        "scaled": "Scaled × {x:g} in X, × {y:g} in Y and × {z:g} in Z: {dims}.",
        "units": "Units: {src} → {dst} (× {f:g}): {dims}.",
        "cut": "Cut by the plane {axis} = {pos:g} mm{capped}.", "capped": ", with the section capped",
        "not_capped": "; the section is not capped because the mesh is not closed (repair it first to cap it)",
        "pieces": "{n} separate parts.", "one_piece": "The model is a single part: there is nothing to separate.",
        "joined": "{n} models joined{union}.", "joined_union": " into one solid (boolean union)",
        "empty_cut": "The plane does not cut the model: the requested part is empty.",
        "estimate": "{mat} estimate: {g:.1f} g and {m:.2f} m of {d} mm filament at {r}% infill.",
    },
}


def _t(locale: str) -> dict:
    return TEXTS.get(locale, TEXTS["es"])


def _trimesh(part: Part, process: bool = True):
    import trimesh

    return trimesh.Trimesh(part.vertices, part.faces, process=process)


def _dims(model: Model) -> str:
    v = np.vstack([p.vertices for p in model.parts])
    x, y, z = np.ptp(v, axis=0)
    return f"{x:.2f} × {y:.2f} × {z:.2f} mm"


def holes(mesh) -> int:
    """Huecos: bucles de aristas de borde (las que tienen una sola cara)."""
    import trimesh

    edges = np.sort(mesh.edges, axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    boundary = unique[counts == 1]
    if not len(boundary):
        return 0
    return len(trimesh.graph.connected_components(boundary, min_len=1))


def component_count(mesh) -> int:
    """Piezas sueltas sin construirlas (D-256: separar un millón de triángulos sueltos costaba minutos y gigas)."""
    import trimesh

    if not len(mesh.faces):
        return 0
    labels = trimesh.graph.connected_component_labels(mesh.face_adjacency, node_count=len(mesh.faces))
    return int(labels.max()) + 1


def edge_stats(mesh) -> tuple[int, int]:
    """(aristas de borde, aristas con más de dos caras)."""
    edges = np.sort(mesh.edges, axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return int((counts == 1).sum()), int((counts > 2).sum())


# ——— reparar-stl ———

def repair(model: Model, options: dict, locale: str, notes: list[str]) -> Model:
    import trimesh

    t = _t(locale)
    mesh = _trimesh(merged(model).parts[0])
    holes_before = holes(mesh)
    degenerate = int((~mesh.nondegenerate_faces()).sum())
    mesh.update_faces(mesh.nondegenerate_faces())
    unique = mesh.unique_faces()
    duplicates = int((~unique).sum())
    mesh.update_faces(unique)
    mesh.remove_unreferenced_vertices()
    removed_small = 0
    if options.get("quitar_sueltas", True) and 1 < component_count(mesh) <= 10_000:
        pieces = mesh.split(only_watertight=False)
        if len(pieces) > 1:
            # Resto pequeño: menos del 1 % de los triángulos o una caja de menos del 2 % de la diagonal de la pieza mayor.
            keep_min = max(4, int(0.01 * len(mesh.faces)))
            biggest = max(float(np.linalg.norm(np.ptp(p.vertices, axis=0))) for p in pieces)
            kept = [p for p in pieces if len(p.faces) >= keep_min and float(np.linalg.norm(np.ptp(p.vertices, axis=0))) >= 0.02 * biggest]
            kept = kept or [max(pieces, key=lambda p: len(p.faces))]
            removed_small = len(pieces) - len(kept)
            mesh = trimesh.util.concatenate(kept)
    trimesh.repair.fix_winding(mesh)
    trimesh.repair.fix_inversion(mesh, multibody=True)
    trimesh.repair.fill_holes(mesh)
    trimesh.repair.fix_normals(mesh, multibody=True)
    union = ""
    if options.get("unir_solapes", True):
        try:
            import manifold3d as m3

            pieces = mesh.split(only_watertight=True)
            if len(pieces) > 1:
                manifolds = [m3.Manifold(m3.Mesh(vert_properties=np.asarray(p.vertices, np.float32), tri_verts=np.asarray(p.faces, np.uint32)))
                             for p in pieces]
                if all(m.status() == m3.Error.NoError for m in manifolds):
                    result = m3.Manifold.batch_boolean(manifolds, m3.OpType.Add).to_mesh()
                    mesh = trimesh.Trimesh(np.asarray(result.vert_properties)[:, :3], np.asarray(result.tri_verts), process=True)
                    union = t["union"]
        except Exception:  # noqa: BLE001 - manifold3d no acepta la malla: se deja sin unir
            union = ""
    boundary_after, _ = edge_stats(mesh)
    state = t["closed"] if boundary_after == 0 else t["open"].format(n=boundary_after)
    closed = max(0, holes_before - holes(mesh))
    notes.append(t["repair"].format(holes=closed, degenerate=degenerate, duplicates=duplicates, union=union, state=state)
                 + (t["small"].format(n=removed_small) if removed_small else ""))
    if model.has_colors:
        notes.append(t["colors_dropped"])
    return Model([Part(model.parts[0].name if len(model.parts) == 1 else "modelo", np.asarray(mesh.vertices, np.float64),
                       np.asarray(mesh.faces, np.int64))], model.unit_mm, set(), model.up)


# ——— reducir-poligonos ———

def reduce(model: Model, options: dict, locale: str, notes: list[str]) -> Model:
    import fast_simplification

    t = _t(locale)
    before = model.triangles
    target = int(options.get("triangulos", 0) or 0)
    ratio = (1 - target / before) if target and target < before else float(options.get("reduccion", 50)) / 100
    ratio = min(0.99, max(0.0, ratio))
    parts = []
    for part in model.parts:
        if len(part.faces) < 8 or ratio <= 0:
            parts.append(Part(part.name, part.vertices, part.faces))
            continue
        points, faces = fast_simplification.simplify(part.vertices.astype(np.float32), part.faces.astype(np.int32), target_reduction=ratio)
        parts.append(Part(part.name, np.asarray(points, np.float64), np.asarray(faces, np.int64)))
    after = sum(len(p.faces) for p in parts)
    notes.append(t["reduced"].format(before=f"{before:,}".replace(",", "."), after=f"{after:,}".replace(",", "."),
                                     pct=round(100 * (1 - after / max(1, before)))))
    if model.has_colors:
        notes.append(t["colors_dropped"])
    return Model(parts, model.unit_mm, set(), model.up)


# ——— escalar-modelo-3d y cambiar-unidades-stl ———

def scale(model: Model, options: dict, locale: str, notes: list[str]) -> Model:
    t = _t(locale)
    v = np.vstack([p.vertices for p in model.parts])
    size = np.ptp(v, axis=0)
    if options.get("modo", "factor") == "medida":
        axis = options.get("eje", "mayor")
        index = int(np.argmax(size)) if axis == "mayor" else "xyz".index(axis)
        if size[index] <= 0:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "mesh_flat")
        f = float(options.get("medida_mm", 100)) / size[index]
        factors = np.array([f, f, f])
    else:
        f = float(options.get("factor", 1.0))
        factors = np.array([f * float(options.get("escala_x", 1.0)), f * float(options.get("escala_y", 1.0)),
                            f * float(options.get("escala_z", 1.0))])
    for part in model.parts:
        part.vertices = part.vertices * factors
        if np.prod(factors) < 0:
            part.faces = part.faces[:, ::-1]
    notes.append(t["scaled"].format(x=factors[0], y=factors[1], z=factors[2], dims=_dims(model)))
    return model


def units(model: Model, options: dict, locale: str, notes: list[str]) -> Model:
    from tools.mesh.pipeline import _unit_label

    t = _t(locale)
    src, dst = options.get("de", "in"), options.get("a", "mm")
    f = UNITS_MM[src] / UNITS_MM[dst]
    for part in model.parts:
        part.vertices = part.vertices * f
    notes.append(t["units"].format(src=_unit_label(src, locale), dst=_unit_label(dst, locale), f=f, dims=_dims(model)))
    return model


# ——— cortar-modelo-3d ———

def cut(model: Model, options: dict, locale: str, notes: list[str]) -> list[tuple[Model, str]]:
    import trimesh

    t = _t(locale)
    part = merged(model).parts[0]
    axis = options.get("eje", "z")
    index = "xyz".index(axis)
    lo, hi = part.vertices[:, index].min(), part.vertices[:, index].max()
    pos = float(options.get("posicion", 50))
    position = lo + (hi - lo) * pos / 100 if options.get("unidad_posicion", "porcentaje") == "porcentaje" else pos
    normal = np.zeros(3)
    normal[index] = 1.0
    keep = options.get("conservar", "ambas")
    below = above = None
    capped = False
    try:
        import manifold3d as m3

        man = m3.Manifold(m3.Mesh(vert_properties=np.asarray(part.vertices, np.float32), tri_verts=np.asarray(part.faces, np.uint32)))
        if man.status() == m3.Error.NoError:
            upper, lower = man.split_by_plane(tuple(normal), float(position))
            to_part = lambda m, name: (Part(name, np.asarray(m.to_mesh().vert_properties, np.float64)[:, :3],  # noqa: E731
                                            np.asarray(m.to_mesh().tri_verts, np.int64)) if not m.is_empty() else None)
            above, below = to_part(upper, "encima"), to_part(lower, "debajo")
            capped = True
    except Exception:  # noqa: BLE001
        capped = False
    if not capped:
        mesh = trimesh.Trimesh(part.vertices, part.faces, process=False)
        origin = normal * position
        for side, sign in (("encima", 1.0), ("debajo", -1.0)):
            sliced = trimesh.intersections.slice_plane(mesh, origin, normal * sign, cap=False)
            piece = Part(side, np.asarray(sliced.vertices), np.asarray(sliced.faces)) if sliced is not None and len(sliced.faces) else None
            if side == "encima":
                above = piece
            else:
                below = piece
    notes.append(t["cut"].format(axis=axis.upper(), pos=round(float(position), 3), capped=t["capped"] if capped else t["not_capped"]))
    if keep == "ambas" and (below is None or above is None):
        notes.append(t["empty_cut"])
    out = []
    for piece, suffix in ((below, "debajo" if locale != "en" else "below"), (above, "encima" if locale != "en" else "above")):
        if keep != "ambas" and piece is not None and piece.name != keep:
            continue
        if piece is None:
            if keep != "ambas":
                raise ToolError(ErrorCode.INVALID_OPTIONS, "mesh_cut_empty")
            continue
        out.append((Model([piece], model.unit_mm, set(), model.up), suffix))
    if not out:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "mesh_cut_empty")
    return out


# ——— separar-piezas ———

def separate(model: Model, options: dict, locale: str, notes: list[str]) -> list[tuple[Model, str]]:
    t = _t(locale)
    mesh = _trimesh(merged(model).parts[0])
    if component_count(mesh) > 5000:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "mesh_pieces")
    pieces = sorted(mesh.split(only_watertight=False), key=lambda p: -len(p.faces))
    minimum = int(options.get("minimo_triangulos", 4) or 1)
    pieces = [p for p in pieces if len(p.faces) >= minimum] or pieces[:1]
    if len(pieces) > 500:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "mesh_pieces")
    if len(pieces) == 1:
        notes.append(t["one_piece"])
    else:
        notes.append(t["pieces"].format(n=len(pieces)))
    return [(Model([Part(f"pieza-{i + 1:03d}", np.asarray(p.vertices, np.float64), np.asarray(p.faces, np.int64))], model.unit_mm, set(), model.up),
             f"{i + 1:03d}") for i, p in enumerate(pieces)]


# ——— unir-modelos ———

def join(models: list[tuple[str, Model]], options: dict, locale: str, notes: list[str]) -> Model:
    t = _t(locale)
    parts = []
    gap = float(options.get("separacion_mm", 5))
    cursor = 0.0
    for name, model in models:
        for p in model.parts:
            p.name = name if len(model.parts) == 1 else f"{name}-{p.name}"
        if options.get("modo", "mantener") == "distribuir":
            v = np.vstack([p.vertices for p in model.parts])
            lo, hi = v.min(axis=0), v.max(axis=0)
            shift = np.array([cursor - lo[0], -(lo[1] + hi[1]) / 2, -lo[2]])
            for p in model.parts:
                p.vertices = p.vertices + shift
            cursor += (hi[0] - lo[0]) + gap
        parts += model.parts
    union = ""
    if options.get("fusionar", False):
        import manifold3d as m3

        manifolds = [m3.Manifold(m3.Mesh(vert_properties=np.asarray(p.vertices, np.float32), tri_verts=np.asarray(p.faces, np.uint32)))
                     for p in parts]
        if not all(m.status() == m3.Error.NoError for m in manifolds):
            raise ToolError(ErrorCode.INVALID_OPTIONS, "mesh_not_closed")
        result = m3.Manifold.batch_boolean(manifolds, m3.OpType.Add).to_mesh()
        parts = [Part("union", np.asarray(result.vert_properties, np.float64)[:, :3], np.asarray(result.tri_verts, np.int64))]
        union = t["joined_union"]
    notes.append(t["joined"].format(n=len(models), union=union))
    return Model(parts, 1.0, set(), "z")


# ——— analizar-stl ———

def analyse(model: Model, options: dict, locale: str) -> tuple[str, dict]:
    """Informe (texto o JSON) y su resumen para la nota."""
    t = _t(locale)
    mesh = _trimesh(merged(model).parts[0])
    boundary, nonmanifold = edge_stats(mesh)
    components = component_count(mesh)
    watertight = bool(mesh.is_watertight)
    volume_mm3 = abs(float(mesh.volume)) if watertight else float("nan")
    area = float(mesh.area)
    size = np.ptp(mesh.vertices, axis=0)
    material = options.get("material", "PLA")
    infill = float(options.get("relleno", 20)) / 100
    wall = float(options.get("paredes_mm", 1.2))
    diameter = float(options.get("diametro", "1.75"))
    estimate = None
    if watertight and volume_mm3 > 0:
        shell = min(volume_mm3, area * wall)
        printed = shell + infill * max(0.0, volume_mm3 - shell)
        grams = printed / 1000 * DENSITY[material]
        metres = printed / (math.pi * (diameter / 2) ** 2) / 1000
        estimate = {"material": material, "gramos": round(grams, 1), "metros": round(metres, 2), "relleno_pct": round(infill * 100),
                    "diametro_mm": diameter, "paredes_mm": wall}
    data = {
        "triangulos": int(len(mesh.faces)), "vertices": int(len(mesh.vertices)), "piezas": components,
        "dimensiones_mm": {"x": round(float(size[0]), 3), "y": round(float(size[1]), 3), "z": round(float(size[2]), 3)},
        "estanca": watertight, "aristas_de_borde": boundary, "aristas_no_manifold": nonmanifold,
        "volumen_cm3": round(volume_mm3 / 1000, 3) if watertight else None, "superficie_cm2": round(area / 100, 3),
        "estimacion_filamento": estimate,
        "aviso": ("La estimación de filamento es aproximada: no tiene en cuenta soportes, balsa ni los ajustes exactos del laminador."
                  if locale != "en" else "The filament estimate is approximate: it ignores supports, rafts and the slicer's exact settings."),
    }
    summary = [f"{data['dimensiones_mm']['x']} × {data['dimensiones_mm']['y']} × {data['dimensiones_mm']['z']} mm",
               t["closed"] if watertight else t["open"].format(n=boundary)]
    if estimate:
        summary.append(t["estimate"].format(mat=material, g=estimate["gramos"], m=estimate["metros"], d=diameter, r=estimate["relleno_pct"]))
    if options.get("formato", "txt") == "json":
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n", {"summary": " ".join(summary)}
    es = locale != "en"
    lines = [("Análisis del modelo" if es else "Model analysis"), "",
             f"{'Triángulos' if es else 'Triangles'}: {data['triangulos']:,}".replace(",", "." if es else ","),
             f"{'Vértices' if es else 'Vertices'}: {data['vertices']:,}".replace(",", "." if es else ","),
             f"{'Piezas sueltas' if es else 'Loose parts'}: {components}",
             f"{'Dimensiones' if es else 'Dimensions'}: {summary[0]}",
             f"{'Estanca (cerrada)' if es else 'Watertight (closed)'}: {('sí' if es else 'yes') if watertight else 'no'}",
             f"{'Aristas de borde (huecos)' if es else 'Boundary edges (holes)'}: {boundary}",
             f"{'Aristas no manifold' if es else 'Non-manifold edges'}: {nonmanifold}",
             f"{'Volumen' if es else 'Volume'}: {data['volumen_cm3']} cm³" if watertight else
             (f"Volumen: no se puede medir porque la malla no es cerrada" if es else "Volume: cannot be measured because the mesh is not closed"),
             f"{'Superficie' if es else 'Surface'}: {data['superficie_cm2']} cm²", ""]
    if estimate:
        lines += [summary[-1], data["aviso"]]
    return "\n".join(lines) + "\n", {"summary": " ".join(summary)}


OPS = {"reparar-stl": repair, "reducir-poligonos": reduce, "escalar-modelo-3d": scale, "cambiar-unidades-stl": units}
MULTI_OPS = {"cortar-modelo-3d": cut, "separar-piezas": separate}
