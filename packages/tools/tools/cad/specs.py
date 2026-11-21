"""Impresión 3D: CAD (7.19, F7-D, D-251): herramientas del grupo `cad` (`workercad`, cola `cad`)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.options import opt
from core.registry import NoOptions, ToolSpec
from tools.mesh.specs import UNIT_LABELS, MeshGlbOptions, MeshOptions, MeshStlOptions

QUALITY = {"baja": ("Baja (menos triángulos)", "Low (fewer triangles)"), "media": ("Media", "Medium"),
           "alta": ("Alta (curvas más suaves)", "High (smoother curves)")}


def _quality():
    return opt("media", "Calidad del teselado", "Tessellation quality", labels=QUALITY)


class CadStlOptions(MeshStlOptions):
    """7.19: calidad del teselado [media] más las opciones de malla de 7.18."""

    calidad: Literal["baja", "media", "alta"] = _quality()


class CadMeshOptions(MeshOptions):
    calidad: Literal["baja", "media", "alta"] = _quality()


class CadGlbOptions(MeshGlbOptions):
    calidad: Literal["baja", "media", "alta"] = _quality()


class MeshToStepOptions(BaseModel):
    """stl-a-step y obj-a-step (7.19): unidades del original y escala; el STEP sale en milímetros."""

    unidades_origen: Literal["auto", "mm", "cm", "m", "in"] = opt(
        "auto", "Unidades del original", "Units of the original",
        labels={"auto": ("Las del archivo (o milímetros)", "The file's (or millimetres)"), **UNIT_LABELS})
    escala: float = opt(1.0, "Escala", "Scale", ge=0.001, le=1000, advanced=True)


NAMES = {"step": "STEP", "stp": "STP", "iges": "IGES", "igs": "IGS", "brep": "BREP", "stl": "STL", "3mf": "3MF", "obj": "OBJ", "glb": "GLB"}


def cad(src: str, dst: str, related: tuple[str, ...], summary_es: str, summary_en: str, options=None) -> ToolSpec:
    a, b = NAMES[src], NAMES[dst]
    if options is None:
        options = {"stl": CadStlOptions, "glb": CadGlbOptions}.get(dst, CadMeshOptions)
    return ToolSpec(
        slug_es=f"{src}-a-{dst}", slug_en=f"{src}-to-{dst}", name_es=f"{a} a {b}", name_en=f"{a} to {b}", category="3d", where="server",
        inputs=(src,), outputs=(dst, "zip"), options=options, worker_group="cad", cost_class="heavy", queue_kind=None,
        impl="tools.mesh.convert:run", launch=True, phase="F7", time_limit=600, max_files=5, summary_es=summary_es,
        precheck="tools.mesh.recuento:precheck" if src in ("stl", "obj") else None,
        summary_en=summary_en, related=related)


T_ES = "Convierte piezas de CAD {a} a una malla {b} para imprimirlas en 3D, con la calidad de teselado que elijas."
T_EN = "Convert {a} CAD parts to an {b} mesh for 3D printing, with the tessellation quality you choose."
SPECS = [
    cad("step", "stl", ("step-a-3mf", "stl-a-step"), T_ES.format(a="STEP", b="STL"), T_EN.format(a="STEP", b="STL")),
    cad("stp", "stl", ("step-a-stl", "step-a-3mf"), T_ES.format(a="STP", b="STL"), T_EN.format(a="STP", b="STL")),
    cad("step", "3mf", ("step-a-stl", "3mf-a-stl"), "Convierte piezas STEP a 3MF con sus nombres, colores y unidades para el laminador.",
        "Convert STEP parts to 3MF with their names, colours and units for the slicer."),
    cad("step", "obj", ("step-a-stl", "step-a-glb"), T_ES.format(a="STEP", b="OBJ").replace("para imprimirlas en 3D", "para Blender y los visores"),
        T_EN.format(a="STEP", b="OBJ").replace("for 3D printing", "for Blender and viewers")),
    cad("step", "glb", ("step-a-obj", "stl-a-glb"), "Convierte piezas STEP a GLB para enseñarlas en la web o en realidad aumentada.",
        "Convert STEP parts to GLB to show them on the web or in augmented reality."),
    cad("iges", "stl", ("igs-a-step", "step-a-stl"), T_ES.format(a="IGES", b="STL"), T_EN.format(a="IGES", b="STL")),
    cad("igs", "step", ("iges-a-stl", "step-a-stl"), "Convierte piezas IGES a STEP conservando la geometría exacta, sin teselar.",
        "Convert IGES parts to STEP keeping the exact geometry, without tessellating.", options=NoOptions),
    cad("brep", "stl", ("step-a-stl", "stl-a-step"), T_ES.format(a="BREP de OpenCascade", b="STL"),
        T_EN.format(a="OpenCascade BREP", b="STL")),
    cad("stl", "step", ("step-a-stl", "obj-a-step"), "Convierte una malla STL en un sólido STEP facetado para abrirla en programas de CAD.",
        "Turn an STL mesh into a faceted STEP solid to open it in CAD programs.", options=MeshToStepOptions),
    cad("obj", "step", ("stl-a-step", "step-a-obj"), "Convierte una malla OBJ en un sólido STEP facetado para abrirla en programas de CAD.",
        "Turn an OBJ mesh into a faceted STEP solid to open it in CAD programs.", options=MeshToStepOptions),
]
