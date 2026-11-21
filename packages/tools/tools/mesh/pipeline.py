"""La conversión de un archivo de malla (7.18, F7-A y F7-B, D-244, D-248 y D-249), sin nada del trabajador: se ejecuta en
el proceso hijo de `child.py` con su memoria y su tiempo acotados, para que un archivo que hinche la memoria (instancias de
un 3MF, polígonos de un PLY, vértices de sobra) mate al hijo y no al trabajador.

Lee el original, gira los ejes si hace falta, aplica unidades y escala, decide las piezas y escribe en `out_dir` uno o
varios archivos; devuelve sus nombres y la nota del resultado.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np

from core.errors import ErrorCode, ToolError
from tools.mesh import extra, formats

TARGET = {"stl-a-obj": "obj", "obj-a-stl": "stl", "stl-a-3mf": "3mf", "3mf-a-stl": "stl", "obj-a-3mf": "3mf",
          "3mf-a-obj": "obj", "stl-a-ply": "ply", "ply-a-stl": "stl", "stl-ascii-a-binario": "stl",
          # F7-B (D-248)
          "amf-a-stl": "stl", "stl-a-amf": "amf", "amf-a-3mf": "3mf", "glb-a-stl": "stl", "stl-a-glb": "glb", "gltf-a-stl": "stl",
          "fbx-a-stl": "stl", "fbx-a-obj": "obj", "dae-a-stl": "stl", "3ds-a-stl": "stl",
          # F7-C (D-250); convertir-modelo-3d elige el formato en sus opciones
          "wrl-a-stl": "stl", "stl-a-wrl": "wrl", "x3d-a-stl": "stl", "stl-a-x3d": "x3d", "stl-a-usdz": "usdz", "obj-a-usdz": "usdz",
          "convertir-modelo-3d": None,
          # F7-D (D-251): CAD con OpenCascade en workercad
          "step-a-stl": "stl", "stp-a-stl": "stl", "step-a-3mf": "3mf", "step-a-obj": "obj", "step-a-glb": "glb", "iges-a-stl": "stl",
          "igs-a-step": "step", "brep-a-stl": "stl", "stl-a-step": "step", "obj-a-step": "step",
          # F7-E (D-252): el STL que genera OpenSCAD
          "scad-a-stl": "stl", "scad-a-3mf": "3mf"}
MULTI = {"obj", "3mf", "amf", "glb", "wrl", "x3d", "usdz"}  # formatos con varias piezas en un archivo
UP = {"glb": "y", "wrl": "y", "x3d": "y", "usdz": "y"}  # eje vertical de cada formato de salida; el resto, Z (impresión 3D)

TEXTS = {
    "es": {"colors_lost": "El STL no guarda colores: el modelo sale sin ellos.",
           "textures_lost": "Las texturas no se convierten: el modelo sale con su geometría y sus colores, si los tiene.",
           "units": "Unidades: {src} → {dst}{scale}.", "scale": ", escala × {f:g}",
           "assumed": "El archivo de origen no guarda unidades: se ha tomado como {src}.",
           "parts": "{n} piezas.", "separated": "Una pieza por archivo, en un ZIP.",
           "already_binary": "El STL ya era binario: se ha vuelto a guardar igual de compacto.",
           "triangles": "{n} triángulos.", "triangle": "1 triángulo.",
           "axes_z": "Se ha pasado del eje Y vertical del original al Z vertical de la impresión 3D.",
           "axes_y": "Se ha pasado del eje Z vertical al Y vertical de glTF.",
           "cad_quality": "Teselado con calidad {q}.", "cad_exact": "La geometría exacta ({n} formas) ha pasado a STEP sin teselar.",
           "step_faceted": "El STEP es un sólido facetado: cada triángulo es una cara plana y no recupera superficies paramétricas "
                           "(cilindros, curvas); sirve para medir, ensamblar o mecanizar, no para editar la forma como un modelo CAD."},
    "en": {"colors_lost": "STL does not store colours: the model comes out without them.",
           "textures_lost": "Textures are not converted: the model keeps its geometry and colours, if any.",
           "units": "Units: {src} → {dst}{scale}.", "scale": ", scale × {f:g}",
           "assumed": "The source file does not store units: it was taken as {src}.",
           "parts": "{n} parts.", "separated": "One part per file, in a ZIP.",
           "already_binary": "The STL was already binary: it was saved again just as compact.",
           "triangles": "{n} triangles.", "triangle": "1 triangle.",
           "axes_z": "Converted from the original's Y-up axis to the Z-up axis of 3D printing.",
           "axes_y": "Converted from Z-up to glTF's Y-up axis.",
           "cad_quality": "Tessellated with {q} quality.", "cad_exact": "The exact geometry ({n} shapes) went to STEP without tessellating.",
           "step_faceted": "The STEP is a faceted solid: each triangle is a flat face and parametric surfaces (cylinders, curves) are "
                           "not recovered; it is good for measuring, assembling or machining, not for editing the shape as a CAD model."},
}


def _unit_label(unit: str, locale: str) -> str:
    es, en = formats.UNIT_NAMES[unit]
    return en if locale == "en" else es


def source_unit(model: formats.Model, option: str) -> tuple[float, str, bool]:
    """(milímetros por unidad, nombre, supuesta)."""
    if option != "auto":
        return formats.UNITS_MM[option], option, False
    if model.unit_mm is not None:
        name = next((k for k, v in formats.UNITS_ALL_MM.items() if abs(v - model.unit_mm) < 1e-9), "mm")
        return model.unit_mm, name, False
    return 1.0, "mm", True


def write(model: formats.Model, target: str, dst: Path, unit: str, ascii: bool) -> None:
    if target == "stl":
        formats.write_stl(model, dst, ascii)
    elif target == "ply":
        formats.write_ply(model, dst)
    elif target == "3mf":
        formats.write_3mf(model, dst, unit)
    elif target == "amf":
        extra.write_amf(model, dst, unit)
    elif target == "glb":
        extra.write_glb(model, dst)
    elif target in ("wrl", "x3d", "off"):
        from tools.mesh import escena

        {"wrl": escena.write_wrl, "x3d": escena.write_x3d, "off": escena.write_off}[target](model, dst)
    elif target == "usdz":
        from tools.mesh import usd

        usd.write_usdz(model, dst, unit)
    elif target == "step":
        from tools.cad import occt

        occt.mesh_to_step(model, dst)
    else:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT)


def _obj_files(model: formats.Model, out_dir: Path, stem: str) -> list[tuple[Path, str]]:
    """El OBJ y, si hay colores, su MTL."""
    obj = out_dir / f"{stem}.obj"
    mtl_text = formats.write_obj(model, obj, f"{stem}.mtl" if model.has_colors else None)
    files = [(obj, f"{stem}.obj")]
    if mtl_text is not None:
        mtl = out_dir / f"{stem}.mtl"
        mtl.write_text(mtl_text, encoding="utf-8")
        files.append((mtl, f"{stem}.mtl"))
    return files


def _zip(dst: Path, files: list[tuple[Path, str]]) -> None:
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, name in files:
            zf.write(path, name)
            path.unlink()


def convert_file(src: Path, ext: str, tool: str, options: dict, locale: str, max_triangles: int, stem: str, out_dir: Path,
                 library_path: str = "") -> list[dict]:
    """Convierte un archivo y deja el resultado en `out_dir`: [{"file", "name", "note"}]."""
    t = TEXTS.get(locale, TEXTS["es"])
    target = TARGET[tool] or options.get("formato", "stl")
    ascii = options.get("stl", "binario") == "ascii" and tool != "stl-ascii-a-binario"
    notes = []
    from tools.cad.occt import CAD_EXTS

    if ext in CAD_EXTS:
        from tools.cad import occt

        if target == "step":  # IGES o BREP a STEP: la geometría exacta, sin teselar
            dst = out_dir / f"{stem}.step"
            n = occt.cad_to_step(src, ext, dst)
            return [{"file": str(dst), "name": dst.name, "note": t["cad_exact"].format(n=n)}]
        quality = options.get("calidad", "media")
        model = occt.read_cad(src, ext, quality, max_triangles)
        names = {"baja": ("baja", "low"), "media": ("media", "medium"), "alta": ("alta", "high")}[quality]
        notes.append(t["cad_quality"].format(q=names[1] if locale == "en" else names[0]))
    else:
        model = formats.load(src, ext, max_triangles, inline=True)
    if not options.get("conservar_ejes", False) and extra.reorient(model, UP.get(target, "z")):
        notes.append(t["axes_z" if UP.get(target, "z") == "z" else "axes_y"])
    if tool == "stl-ascii-a-binario" and formats.stl_is_binary(src):
        notes.append(t["already_binary"])
    src_mm, src_name, assumed = source_unit(model, options.get("unidades_origen", "auto"))
    dst_unit = "m" if target == "glb" else options.get("unidades_destino", "mm")  # GLB: siempre metros (glTF)
    scale = float(options.get("escala", 1.0))
    formats.scaled(model, src_mm / formats.UNITS_MM[dst_unit] * scale)
    formats.check_finite(model)
    if assumed and target in ("3mf", "amf", "glb"):
        notes.append(t["assumed"].format(src=_unit_label(src_name, locale)))
    if src_name != dst_unit or scale != 1:
        notes.append(t["units"].format(src=_unit_label(src_name, locale), dst=_unit_label(dst_unit, locale),
                                       scale=t["scale"].format(f=scale) if scale != 1 else ""))
    if target == "stl" and model.has_colors:
        notes.append(t["colors_lost"])
    if "textures" in model.lost:
        notes.append(t["textures_lost"])
    if target == "step":
        notes.append(t["step_faceted"])
    parts_option = options.get("piezas", "mantener")
    triangles, n_parts = model.triangles, len(model.parts)
    pieces = [model]
    if parts_option == "fusionar" or (parts_option == "mantener" and target not in MULTI):
        pieces = [formats.merged(model, stem)]
    elif parts_option == "separar" and n_parts > 1:
        pieces = [formats.Model([p], model.unit_mm, model.lost, model.up) for p in model.parts]
        notes.append(t["separated"])
    kept = len(pieces) == 1 and len(pieces[0].parts) > 1
    del model
    files: list[tuple[Path, str]] = []
    for k, piece in enumerate(pieces):
        formats.clean_names(piece)
        name_stem = stem if len(pieces) == 1 else f"{stem}-{k + 1:02d}-{formats._obj_name(piece.parts[0].name)}"
        if target == "obj":
            files += _obj_files(piece, out_dir, name_stem)
        else:
            path = out_dir / f"{name_stem}.{target}"
            write(piece, target, path, dst_unit, ascii)
            files.append((path, path.name))
        pieces[k] = None  # type: ignore[call-overload]
    if kept:
        notes.append(t["parts"].format(n=n_parts))
    notes.append(t["triangle"] if triangles == 1 else t["triangles"].format(n=f"{triangles:,}".replace(",", "." if locale != "en" else ",")))
    note = " ".join(notes)
    if len(files) == 1:
        return [{"file": str(files[0][0]), "name": files[0][1], "note": note}]
    # Varios archivos (piezas separadas, o un OBJ con su MTL): un ZIP con todos, sin ZIP dentro de ZIP.
    zip_name = (f"{stem}-obj.zip" if len(pieces) == 1 else f"{stem}-piezas.zip" if locale != "en" else f"{stem}-parts.zip")
    dst = out_dir / zip_name
    _zip(dst, files)
    return [{"file": str(dst), "name": zip_name, "note": note}]


def array_bytes(*arrays: np.ndarray) -> int:
    return sum(a.nbytes for a in arrays if a is not None)


# ——— Operaciones de F7-F (D-253) ———

WRITABLE = {"stl", "obj", "3mf", "ply", "amf", "glb", "off"}
GEN_TOOLS = {"svg-a-stl", "dxf-a-stl", "imagen-a-stl", "logo-a-stl", "texto-a-stl", "litofania", "mapa-de-alturas-a-stl"}
OP_TOOLS = {"reparar-stl", "reducir-poligonos", "escalar-modelo-3d", "cambiar-unidades-stl", "cortar-modelo-3d", "separar-piezas",
            "analizar-stl", "unir-modelos"}


def _out_format(options: dict, ext: str) -> str:
    chosen = options.get("formato_salida", "mismo")
    if chosen != "mismo":
        return chosen
    return ext if ext in WRITABLE else "stl"


def _write_results(results: list, target: str, stem: str, out_dir: Path, notes: list[str], locale: str) -> list[dict]:
    files: list[tuple[Path, str]] = []
    for model, suffix in results:
        formats.clean_names(model)
        if target == "glb":  # glTF: metros e Y vertical (D-256)
            formats.scaled(model, 0.001)
            extra.reorient(model, "y")
        name_stem = f"{stem}-{suffix}" if suffix else stem
        if target == "obj":
            files += _obj_files(model, out_dir, name_stem)
        else:
            path = out_dir / f"{name_stem}.{target}"
            write(model, target, path, "mm", False)
            files.append((path, path.name))
    note = " ".join(notes)
    if len(files) == 1:
        return [{"file": str(files[0][0]), "name": files[0][1], "note": note}]
    zip_name = f"{stem}-piezas.zip" if locale != "en" else f"{stem}-parts.zip"
    dst = out_dir / zip_name
    _zip(dst, files)
    return [{"file": str(dst), "name": zip_name, "note": note}]


def _load_mm(src: Path, ext: str, options: dict, max_triangles: int) -> formats.Model:
    """El modelo en milímetros y con Z vertical, como trabajan todas las operaciones (un GLB llega con Y vertical, D-256)."""
    model = formats.load(src, ext, max_triangles, inline=True)
    extra.reorient(model, "z")
    src_mm, _name, _assumed = source_unit(model, options.get("unidades_origen", "auto"))
    formats.scaled(model, src_mm)  # todo en milímetros
    formats.check_finite(model)
    return model


def operate_file(src: Path, ext: str, tool: str, options: dict, locale: str, max_triangles: int, stem: str, out_dir: Path) -> list[dict]:
    from tools.mesh import operaciones as ops

    model = _load_mm(src, ext, options, max_triangles)
    notes: list[str] = []
    if tool == "analizar-stl":
        text, info = ops.analyse(model, options, locale)
        fmt = options.get("formato", "txt")
        path = out_dir / f"{stem}-{'analisis' if locale != 'en' else 'analysis'}.{fmt}"
        path.write_text(text, encoding="utf-8")
        return [{"file": str(path), "name": path.name, "note": info["summary"]}]
    target = _out_format(options, ext)
    if tool in ops.OPS:
        results = [(ops.OPS[tool](model, options, locale, notes), "")]
    else:
        results = ops.MULTI_OPS[tool](model, options, locale, notes)
    for result, _suffix in results:
        formats.check_finite(result)
    return _write_results(results, target, stem, out_dir, notes, locale)


def join_files(srcs: list[tuple[Path, str, str]], options: dict, locale: str, max_triangles: int, stem: str, out_dir: Path) -> list[dict]:
    """unir-modelos: varios archivos en uno (con sus piezas o en un solo sólido)."""
    from tools.mesh import operaciones as ops

    models, total = [], 0
    for src, ext, name in srcs:
        model = _load_mm(src, ext, options, max_triangles - total)
        total += model.triangles
        if total > max_triangles:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "mesh_triangles")
        models.append((name, model))
    notes: list[str] = []
    joined = ops.join(models, options, locale, notes)
    target = options.get("formato_salida", "3mf")
    return _write_results([(joined, "")], target, stem, out_dir, notes, locale)


def generate_file(src: Path | None, ext: str, tool: str, options: dict, locale: str, max_triangles: int, stem: str, out_dir: Path) -> list[dict]:
    """Generadores de F7-G (D-254): de SVG, DXF, imágenes o texto a un sólido."""
    from tools.mesh import generadores

    model, notes = generadores.generate(tool, src, ext, options, locale, max_triangles, stem)
    formats.check_finite(model)
    return _write_results([(model, "")], options.get("formato_salida", "stl"), stem, out_dir, notes, locale)
