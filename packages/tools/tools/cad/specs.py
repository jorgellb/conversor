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


class ScadOptions(MeshOptions):
    """scad-a-3mf (7.19, F7-E, D-252): variables del personalizador, resolución de las curvas y las opciones de malla."""

    variables: str = opt("", "Variables (nombre = valor, una por línea)", "Variables (name = value, one per line)", widget="textarea",
                         max_length=4000, advanced=False)
    resolucion: Literal["modelo", "baja", "media", "alta"] = opt("modelo", "Resolución de las curvas ($fn)", "Curve resolution ($fn)", advanced=True,
                                                                  labels={"modelo": ("La del modelo", "The model's"), "baja": ("Baja (24)", "Low (24)"),
                                                                          "media": ("Media (64)", "Medium (64)"), "alta": ("Alta (128)", "High (128)")})


class ScadStlOptions(ScadOptions):
    stl: Literal["binario", "ascii"] = opt("binario", "Tipo de STL", "STL type", advanced=True, labels={
        "binario": ("Binario (más pequeño)", "Binary (smaller)"), "ascii": ("ASCII (texto)", "ASCII (text)")})


def _dwg_pdf_options():
    from tools.media.specs import DxfOptions

    return DxfOptions


SPECS += [
    ToolSpec(slug_es="scad-a-stl", slug_en="scad-to-stl", name_es="SCAD a STL", name_en="SCAD to STL", category="3d", where="server",
             inputs=("scad", "zip"), outputs=("stl", "zip"), options=ScadStlOptions, worker_group="cad", cost_class="heavy",
             impl="tools.cad.scad:run", launch=True, phase="F7", time_limit=600, max_files=5,
             summary_es="Convierte modelos de OpenSCAD en STL para imprimir, con las variables del personalizador que quieras.",
             summary_en="Turn OpenSCAD models into STL for printing, with the customizer variables you want.", related=("scad-a-3mf", "stl-a-3mf")),
    ToolSpec(slug_es="scad-a-3mf", slug_en="scad-to-3mf", name_es="SCAD a 3MF", name_en="SCAD to 3MF", category="3d", where="server",
             inputs=("scad", "zip"), outputs=("3mf", "zip"), options=ScadOptions, worker_group="cad", cost_class="heavy",
             impl="tools.cad.scad:run", launch=True, phase="F7", time_limit=600, max_files=5,
             summary_es="Convierte modelos de OpenSCAD en 3MF con sus milímetros, listos para el laminador.",
             summary_en="Turn OpenSCAD models into 3MF with their millimetres, ready for the slicer.", related=("scad-a-stl", "3mf-a-stl")),
    ToolSpec(slug_es="dwg-a-dxf", slug_en="dwg-to-dxf", name_es="DWG a DXF", name_en="DWG to DXF", category="3d", where="server",
             inputs=("dwg",), outputs=("dxf", "zip"), options=NoOptions, worker_group="cad", cost_class="heavy",
             impl="tools.cad.dwg:run_dxf", launch=True, phase="F7", time_limit=600, max_files=5,
             summary_es="Convierte planos DWG de AutoCAD en DXF, el formato de intercambio que abre cualquier programa de CAD.",
             summary_en="Convert AutoCAD DWG drawings into DXF, the exchange format any CAD program opens.", related=("dwg-a-pdf", "dxf-a-pdf")),
    ToolSpec(slug_es="dwg-a-pdf", slug_en="dwg-to-pdf", name_es="DWG a PDF", name_en="DWG to PDF", category="3d", where="server",
             inputs=("dwg",), outputs=("pdf", "zip"), options=_dwg_pdf_options(), worker_group="cad", cost_class="heavy",
             impl="tools.cad.dwg:run_pdf", launch=True, phase="F7", time_limit=600, max_files=5,
             summary_es="Convierte planos DWG de AutoCAD en PDF para verlos, imprimirlos o enviarlos sin AutoCAD.",
             summary_en="Convert AutoCAD DWG drawings into PDF to view, print or send them without AutoCAD.", related=("dwg-a-dxf", "dxf-a-pdf")),
]
