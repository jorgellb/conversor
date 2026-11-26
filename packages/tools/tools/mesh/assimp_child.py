"""Proceso hijo de assimp (F7-B, D-248): lee un FBX, DAE o 3DS y deja sus mallas en un .npz.

Se ejecuta con `python -I` bajo `run_engine` (Landlock, memoria y tiempo acotados): assimp es C++ que analiza archivos
de usuario, y un fallo o un desbordamiento mata este proceso, no el trabajador. Solo importa numpy y pyassimp.

Salida: `v{i}`, `f{i}` y, si la pieza tiene color de material, `c{i}` (RGBA de 0 a 255); `names` y `meta` (JSON con la
escala de unidades que diga el archivo). Código 3: demasiados triángulos; 4: sin mallas.
"""
import json
import sys

import numpy as np


def _metadata(scene) -> dict:
    """Escala de unidades y ejes de los metadatos de assimp, leídos de su estructura C (el objeto de pyassimp no admite
    `in` y se itera sin fin)."""
    import ctypes

    wanted = {"UnitScaleFactor", "OriginalUnitScaleFactor", "UpAxis", "UpAxisSign"}
    out: dict = {}
    try:
        pointer = scene.mMetadata
        if not pointer:
            return out
        md = pointer.contents
        for i in range(min(int(md.mNumProperties), 256)):
            key = md.mKeys[i].data.decode("utf-8", "replace")
            if key not in wanted:
                continue
            entry = md.mValues[i]
            kind, data = int(entry.mType), entry.mData
            if not data:
                continue
            if kind == 1:
                out[key] = float(ctypes.cast(data, ctypes.POINTER(ctypes.c_int32)).contents.value)
            elif kind == 3:
                out[key] = float(ctypes.cast(data, ctypes.POINTER(ctypes.c_float)).contents.value)
            elif kind == 4:
                out[key] = float(ctypes.cast(data, ctypes.POINTER(ctypes.c_double)).contents.value)
    except Exception:  # noqa: BLE001 - metadatos opcionales
        return out
    return out


def load_pyassimp():
    """pyassimp 5.2.5 importa `distutils.sysconfig`, que Python 3.12 ya no trae (D-269): en las imágenes, con Python 3.12 y
    sin setuptools, `import pyassimp` fallaba y FBX, DAE y 3DS no funcionaban. Solo usa `get_python_lib` con Anaconda; si
    falta `distutils`, se pone un módulo mínimo con esa función antes de importarlo."""
    import importlib.util
    import sysconfig
    import types

    if importlib.util.find_spec("distutils") is None:
        dist, cfg = types.ModuleType("distutils"), types.ModuleType("distutils.sysconfig")
        cfg.get_python_lib = lambda *_a, **_k: sysconfig.get_paths()["purelib"]
        dist.sysconfig = cfg
        sys.modules.setdefault("distutils", dist)
        sys.modules.setdefault("distutils.sysconfig", cfg)
    import pyassimp

    return pyassimp


def main(src: str, dst: str, max_triangles: int) -> int:
    pyassimp = load_pyassimp()
    from pyassimp import postprocess as pp

    flags = (pp.aiProcess_Triangulate | pp.aiProcess_JoinIdenticalVertices | pp.aiProcess_SortByPType
             | pp.aiProcess_ValidateDataStructure)
    out: dict[str, np.ndarray] = {}
    names: list[str] = []
    total = 0
    with pyassimp.load(src, processing=flags) as scene:
        meta = _metadata(scene)

        def walk(node, parent: np.ndarray, depth: int) -> None:
            nonlocal total
            if depth > 64:
                return
            transform = parent @ np.array(node.transformation, dtype=np.float64)
            for mesh in node.meshes:
                faces = np.asarray(mesh.faces)
                if faces.ndim != 2 or faces.shape[1] != 3 or not len(faces):
                    continue  # puntos y líneas
                total += len(faces)
                if total > max_triangles:
                    raise OverflowError
                verts = np.asarray(mesh.vertices, dtype=np.float64)
                verts = (np.c_[verts, np.ones(len(verts))] @ transform.T)[:, :3]
                i = len(names)
                out[f"v{i}"] = verts
                out[f"f{i}"] = faces.astype(np.int64)
                try:
                    diffuse = scene.materials[mesh.materialindex].properties.get(("diffuse", 0))
                except Exception:  # noqa: BLE001
                    diffuse = None
                if diffuse is not None and len(diffuse) >= 3:
                    rgba = [int(round(max(0.0, min(1.0, float(x))) * 255)) for x in list(diffuse)[:4]] + [255] * (4 - min(4, len(diffuse)))
                    out[f"c{i}"] = np.array(rgba[:4], dtype=np.uint8)
                names.append(str(getattr(node, "name", "") or f"objeto-{i + 1}")[:120])
            for child in node.children:
                walk(child, transform, depth + 1)

        try:
            walk(scene.rootnode, np.eye(4), 0)
        except OverflowError:
            return 3
    if not names:
        return 4
    out["names"] = np.array(json.dumps(names))
    out["meta"] = np.array(json.dumps(meta))
    np.savez(dst, **out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], int(sys.argv[3])))
