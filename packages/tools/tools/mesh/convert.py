"""stl-a-obj, obj-a-stl, stl-a-3mf, 3mf-a-stl, obj-a-3mf, 3mf-a-obj, stl-a-ply, ply-a-stl y stl-ascii-a-binario (7.18,
F7-A, D-244).

Opciones de 7.18: unidades de origen (automáticas: las del 3MF, y milímetros para STL, OBJ y PLY, que no las guardan) y
de destino, escala, piezas (mantenerlas si el formato lo admite, fusionarlas en una o separarlas en un archivo cada una,
en un ZIP) y STL binario o ASCII. Los colores pasan a 3MF (grupo de colores), PLY (color por cara) y OBJ (un material por
color en el MTL, y el resultado es un ZIP con los dos); al pasar a STL se pierden y se avisa.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.mesh import extra, formats
from tools.pdf.common import with_batch_zip

TARGET = {"stl-a-obj": "obj", "obj-a-stl": "stl", "stl-a-3mf": "3mf", "3mf-a-stl": "stl", "obj-a-3mf": "3mf",
          "3mf-a-obj": "obj", "stl-a-ply": "ply", "ply-a-stl": "stl", "stl-ascii-a-binario": "stl",
          # F7-B (D-248)
          "amf-a-stl": "stl", "stl-a-amf": "amf", "amf-a-3mf": "3mf", "glb-a-stl": "stl", "stl-a-glb": "glb", "gltf-a-stl": "stl",
          "fbx-a-stl": "stl", "fbx-a-obj": "obj", "dae-a-stl": "stl", "3ds-a-stl": "stl"}
MULTI = {"obj", "3mf", "amf", "glb"}  # formatos con varias piezas en un archivo
UP = {"glb": "y"}  # eje vertical de cada formato de salida; el resto, Z (impresión 3D)

TEXTS = {
    "es": {"colors_lost": "El STL no guarda colores: el modelo sale sin ellos.",
           "textures_lost": "Las texturas no se convierten: el modelo sale con su geometría y sus colores, si los tiene.",
           "units": "Unidades: {src} → {dst}{scale}.", "scale": ", escala × {f:g}",
           "assumed": "El archivo de origen no guarda unidades: se ha tomado como {src}.",
           "parts": "{n} piezas.", "separated": "Una pieza por archivo, en un ZIP.",
           "already_binary": "El STL ya era binario: se ha vuelto a guardar igual de compacto.",
           "triangles": "{n} triángulos.",
           "axes_z": "Se ha pasado del eje Y vertical del original al Z vertical de la impresión 3D.",
           "axes_y": "Se ha pasado del eje Z vertical al Y vertical de glTF."},
    "en": {"colors_lost": "STL does not store colours: the model comes out without them.",
           "textures_lost": "Textures are not converted: the model keeps its geometry and colours, if any.",
           "units": "Units: {src} → {dst}{scale}.", "scale": ", scale × {f:g}",
           "assumed": "The source file does not store units: it was taken as {src}.",
           "parts": "{n} parts.", "separated": "One part per file, in a ZIP.",
           "already_binary": "The STL was already binary: it was saved again just as compact.",
           "triangles": "{n} triangles.",
           "axes_z": "Converted from the original's Y-up axis to the Z-up axis of 3D printing.",
           "axes_y": "Converted from Z-up to glTF's Y-up axis."},
}


def _unit_label(unit: str, locale: str) -> str:
    es, en = formats.UNIT_NAMES[unit]
    return en if locale == "en" else es


def _source_unit(model: formats.Model, option: str) -> tuple[float, str, bool]:
    """(milímetros por unidad, nombre, supuesta)."""
    if option != "auto":
        return formats.UNITS_MM[option], option, False
    if model.unit_mm is not None:
        name = next((k for k, v in formats.UNITS_MM.items() if abs(v - model.unit_mm) < 1e-9), "mm")
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
    else:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT)


def _write_obj(ctx: ToolContext, model: formats.Model, stem: str, n: int) -> tuple[Path, str]:
    """OBJ suelto o, con colores, un ZIP con el OBJ y su MTL."""
    obj = ctx.work / f"{stem}.obj"
    mtl_text = formats.write_obj(model, obj, f"{stem}.mtl" if model.has_colors else None)
    if mtl_text is None:
        name = f"{stem}.obj"
        dst = ctx.output(name)
        obj.replace(dst)
        return dst, name
    name = f"{stem}-obj.zip"
    dst = ctx.output(name)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(obj, f"{stem}.obj")
        zf.writestr(f"{stem}.mtl", mtl_text)
    obj.unlink()
    return dst, name


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    t = TEXTS.get(ctx.locale, TEXTS["es"])
    target = TARGET[ctx.tool]
    ascii = getattr(o, "stl", "binario") == "ascii" and ctx.tool != "stl-ascii-a-binario"
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        ext = (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()
        model = formats.load(inp.path, ext, ctx.plan.mesh_triangles, ctx=ctx)
        notes = []
        if not getattr(o, "conservar_ejes", False) and extra.reorient(model, UP.get(target, "z")):
            notes.append(t["axes_z" if UP.get(target, "z") == "z" else "axes_y"])
        if ctx.tool == "stl-ascii-a-binario" and formats.stl_is_binary(inp.path):
            notes.append(t["already_binary"])
        src_mm, src_name, assumed = _source_unit(model, o.unidades_origen)
        dst_unit = getattr(o, "unidades_destino", "m")  # GLB: siempre metros (glTF)
        dst_mm = formats.UNITS_MM[dst_unit]
        factor = src_mm / dst_mm * o.escala
        formats.scaled(model, factor)
        if assumed and target in ("3mf", "amf", "glb"):
            notes.append(t["assumed"].format(src=_unit_label(src_name, ctx.locale)))
        if src_name != dst_unit or o.escala != 1:
            notes.append(t["units"].format(src=_unit_label(src_name, ctx.locale), dst=_unit_label(dst_unit, ctx.locale),
                                           scale=t["scale"].format(f=o.escala) if o.escala != 1 else ""))
        if target == "stl" and model.has_colors:
            notes.append(t["colors_lost"])
        if "textures" in model.lost:
            notes.append(t["textures_lost"])
        stem = Path(derived_name(inp.name, "", target)).stem
        pieces = [model]
        if o.piezas == "fusionar" or (o.piezas == "mantener" and target not in MULTI):
            pieces = [formats.merged(model, stem)]
        elif o.piezas == "separar" and len(model.parts) > 1:
            pieces = [formats.Model([p], model.unit_mm, model.lost, model.up) for p in model.parts]
            notes.append(t["separated"])
        files = []
        for k, piece in enumerate(pieces):
            name_stem = stem if len(pieces) == 1 else f"{stem}-{k + 1:02d}-{formats._obj_name(piece.parts[0].name)}"
            if target == "obj":
                dst, name = _write_obj(ctx, piece, name_stem, n)
            else:
                name = f"{name_stem}.{target}"
                dst = ctx.output(name)
                write(piece, target, dst, dst_unit, ascii)
            files.append({"path": str(dst), "name": name})
        if len(model.parts) > 1 and len(pieces) == 1 and len(pieces[0].parts) > 1:
            notes.append(t["parts"].format(n=len(model.parts)))
        notes.append(t["triangles"].format(n=f"{model.triangles:,}".replace(",", "." if ctx.locale != "en" else ",")))
        if len(files) > 1:
            zip_name = f"{stem}-piezas.zip" if ctx.locale != "en" else f"{stem}-parts.zip"
            zdst = ctx.output(zip_name)
            with zipfile.ZipFile(zdst, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in files:
                    zf.write(f["path"], f["name"])
                    Path(f["path"]).unlink()
            files = [{"path": str(zdst), "name": zip_name}]
        files[0]["note"] = " ".join(notes)
        outputs += files
    return with_batch_zip(ctx, outputs, f"modelos-{target}.zip")
