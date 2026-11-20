"""USD y USDZ con usd-core (pxr, LicenseRef-TOST-1.0, 11) (7.18, F7-C, D-250).

- Lectura de .usd, .usda, .usdc y .usdz: cada `UsdGeom.Mesh` con su transformación al mundo, polígonos en abanico,
  `displayColor` (constante, por cara o por vértice) y las unidades (`metersPerUnit`) y el eje vertical (`upAxis`) de la
  escena. Las referencias a otros archivos no se resuelven fuera del paquete: un USDZ lleva dentro todo lo que usa.
- Escritura de USDZ para la realidad aumentada (Quick Look del iPhone y el iPad): Y vertical, `metersPerUnit` según las
  unidades de destino y un `displayColor` por cara.
Se ejecuta dentro del proceso hijo de las mallas (D-249): pxr es C++ que analiza archivos de usuario.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from core.errors import ErrorCode, ToolError
from tools.mesh.formats import UNITS_MM, Model, Part

MAX_PRIMS = 100_000


def read_usd(path: Path, max_triangles: int) -> Model:
    from pxr import Ar, Usd, UsdGeom  # noqa: F401 - Ar carga el resolvedor de paquetes

    try:
        stage = Usd.Stage.Open(str(path), Usd.Stage.LoadAll)
    except Exception as exc:  # noqa: BLE001 - pxr lanza Tf.ErrorException
        raise ToolError(ErrorCode.CORRUPT_FILE, "USD ilegible") from exc
    if stage is None:
        raise ToolError(ErrorCode.CORRUPT_FILE, "USD ilegible")
    meters = UsdGeom.GetStageMetersPerUnit(stage) or 0.01
    up = "z" if UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z else "y"
    model = Model(parts=[], unit_mm=meters * 1000.0, up=up)
    cache = UsdGeom.XformCache()
    total = 0
    for n, prim in enumerate(stage.Traverse()):
        if n > MAX_PRIMS:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Escena USD demasiado grande")
        if not prim.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(prim)
        points = mesh.GetPointsAttr().Get()
        counts = mesh.GetFaceVertexCountsAttr().Get()
        indices = mesh.GetFaceVertexIndicesAttr().Get()
        if not points or not counts or not indices:
            continue
        verts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        counts = np.asarray(counts, dtype=np.int64)
        indices = np.asarray(indices, dtype=np.int64)
        if counts.sum() != len(indices) or (counts < 3).any():
            raise ToolError(ErrorCode.CORRUPT_FILE, "Malla USD no válida")
        tri_count = int((counts - 2).sum())
        total += tri_count
        if total > max_triangles:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "mesh_triangles")
        starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
        poly = np.repeat(np.arange(len(counts)), counts - 2)
        k = np.concatenate([np.arange(1, c - 1) for c in counts]) if len(counts) < 2_000_000 else None
        if k is None:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "mesh_triangles")
        base = starts[poly]
        faces = np.c_[indices[base], indices[base + k], indices[base + k + 1]]
        if faces.min() < 0 or faces.max() >= len(verts):
            raise ToolError(ErrorCode.CORRUPT_FILE, "Malla USD con índices fuera de rango")
        if mesh.GetOrientationAttr().Get() == UsdGeom.Tokens.leftHanded:
            faces = faces[:, ::-1]
        matrix = np.array(cache.GetLocalToWorldTransform(prim), dtype=np.float64)  # USD: filas (v · M)
        world = (np.c_[verts, np.ones(len(verts))] @ matrix)[:, :3]
        if np.linalg.det(matrix[:3, :3]) < 0:
            faces = faces[:, ::-1]
        colors = None
        primvar = UsdGeom.PrimvarsAPI(prim).GetPrimvar("displayColor")
        if primvar and primvar.HasValue():
            values = np.asarray(primvar.Get(), dtype=np.float64).reshape(-1, 3)
            interp = primvar.GetInterpolation()
            if len(values):
                if interp == UsdGeom.Tokens.constant:
                    pick = np.zeros(len(faces), dtype=np.int64)
                elif interp == UsdGeom.Tokens.uniform:
                    pick = np.clip(poly, 0, len(values) - 1)
                else:
                    pick = np.clip(faces[:, 0], 0, len(values) - 1)
                rgb = np.clip(values[pick] * 255, 0, 255).round().astype(np.uint8)
                colors = np.c_[rgb, np.full(len(faces), 255, np.uint8)]
        model.parts.append(Part(prim.GetName() or f"objeto-{len(model.parts) + 1}", world, faces, colors))
    if not model.parts:
        raise ToolError(ErrorCode.CORRUPT_FILE, "El USD no tiene ninguna malla")
    return model


def write_usdz(model: Model, dst: Path, unit: str) -> None:
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdUtils, Vt

    usdc = dst.with_suffix(".usdc")
    stage = Usd.Stage.CreateNew(str(usdc))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, UNITS_MM[unit] / 1000.0)
    root = UsdGeom.Xform.Define(stage, "/Modelo")
    stage.SetDefaultPrim(root.GetPrim())
    used: set[str] = set()
    for n, part in enumerate(model.parts, start=1):
        name = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in part.name)[:60] or "pieza"
        if not name[0].isalpha():
            name = f"p_{name}"
        while name in used:
            name = f"{name}_{n}"
        used.add(name)
        mesh = UsdGeom.Mesh.Define(stage, Sdf.Path(f"/Modelo/{name}"))
        mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(part.vertices, dtype=np.float32)))
        mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(part.faces), 3, dtype=np.int32)))
        mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(np.ascontiguousarray(part.faces.reshape(-1), dtype=np.int32)))
        mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        mesh.CreateDoubleSidedAttr(False)
        lo, hi = part.vertices.min(axis=0), part.vertices.max(axis=0)
        mesh.CreateExtentAttr(Vt.Vec3fArray([Gf.Vec3f(*lo.tolist()), Gf.Vec3f(*hi.tolist())]))
        if part.colors is not None:
            primvar = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("displayColor", Sdf.ValueTypeNames.Color3fArray, UsdGeom.Tokens.uniform)
            primvar.Set(Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(part.colors[:, :3] / 255.0, dtype=np.float32)))
    stage.GetRootLayer().Save()
    if not UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(str(usdc)), str(dst)):
        raise ToolError(ErrorCode.ENGINE_FAILED, "No se pudo crear el USDZ")
    usdc.unlink(missing_ok=True)
