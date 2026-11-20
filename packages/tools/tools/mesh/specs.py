"""Impresión 3D (7.18 a 7.21, F7): herramientas del grupo `mesh` (`workermesh`, cola `mesh`)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.options import opt
from core.registry import ToolSpec

UNIT_LABELS = {"mm": ("Milímetros", "Millimetres"), "cm": ("Centímetros", "Centimetres"), "m": ("Metros", "Metres"),
               "in": ("Pulgadas", "Inches")}
Unit = Literal["mm", "cm", "m", "in"]


class MeshOptions(BaseModel):
    """7.18 (F7-A, D-244): unidades de origen [automáticas] y destino [mm], escala [1] y piezas [mantener]."""

    unidades_origen: Literal["auto", "mm", "cm", "m", "in"] = opt(
        "auto", "Unidades del original", "Units of the original",
        labels={"auto": ("Las del archivo (o milímetros)", "The file's (or millimetres)"), **UNIT_LABELS})
    unidades_destino: Unit = opt("mm", "Unidades del resultado", "Units of the result", labels=UNIT_LABELS)
    escala: float = opt(1.0, "Escala", "Scale", ge=0.001, le=1000, advanced=True)
    piezas: Literal["mantener", "fusionar", "separar"] = opt("mantener", "Piezas", "Parts", advanced=True, labels={
        "mantener": ("Mantenerlas si el formato lo admite", "Keep them if the format allows it"),
        "fusionar": ("Fusionarlas en una", "Merge into one"),
        "separar": ("Un archivo por pieza (ZIP)", "One file per part (ZIP)")})


class MeshStlOptions(MeshOptions):
    """Las de 7.18 más STL [binario] | ASCII."""

    stl: Literal["binario", "ascii"] = opt("binario", "Tipo de STL", "STL type", advanced=True, labels={
        "binario": ("Binario (más pequeño)", "Binary (smaller)"), "ascii": ("ASCII (texto)", "ASCII (text)")})


NAMES = {"stl": "STL", "obj": "OBJ", "3mf": "3MF", "ply": "PLY"}
WHAT = {
    "stl": ("el formato de malla de las impresoras 3D", "the mesh format of 3D printers"),
    "obj": ("el formato de modelos 3D de Blender, Maya y los visores", "the 3D model format of Blender, Maya and viewers"),
    "3mf": ("el formato moderno de impresión 3D, con unidades y colores", "the modern 3D printing format, with units and colours"),
    "ply": ("el formato de escáneres 3D y nubes de puntos con color", "the format of 3D scanners and coloured point clouds"),
}


def mesh(src: str, dst: str, related: tuple[str, ...], slug_es: str | None = None, slug_en: str | None = None,
         name_es: str | None = None, name_en: str | None = None, summary_es: str | None = None, summary_en: str | None = None,
         options: type[BaseModel] | None = None) -> ToolSpec:
    a, b = NAMES[src], NAMES[dst]
    return ToolSpec(
        slug_es=slug_es or f"{src}-a-{dst}", slug_en=slug_en or f"{src}-to-{dst}", name_es=name_es or f"{a} a {b}",
        name_en=name_en or f"{a} to {b}", category="3d", where="server", inputs=(src,), outputs=(dst, "zip"),
        options=options or (MeshStlOptions if dst == "stl" else MeshOptions), worker_group="mesh", cost_class="light",
        impl="tools.mesh.convert:run", precheck="tools.mesh.recuento:precheck", launch=True, phase="F7", time_limit=600,
        max_files=10,
        summary_es=summary_es or f"Convierte modelos {a} a {b}, {WHAT[dst][0]}, con unidades y escala.",
        summary_en=summary_en or f"Convert {a} models to {b}, {WHAT[dst][1]}, with units and scale.", related=related)


SPECS = [
    # 7.18 (F7-A, D-244): trimesh para STL, OBJ y PLY; lib3mf para 3MF.
    mesh("stl", "obj", ("obj-a-stl", "stl-a-3mf")),
    mesh("obj", "stl", ("stl-a-obj", "obj-a-3mf")),
    mesh("stl", "3mf", ("3mf-a-stl", "stl-a-obj")),
    mesh("3mf", "stl", ("stl-a-3mf", "3mf-a-obj")),
    mesh("obj", "3mf", ("3mf-a-obj", "obj-a-stl")),
    mesh("3mf", "obj", ("obj-a-3mf", "3mf-a-stl")),
    mesh("stl", "ply", ("ply-a-stl", "stl-a-obj")),
    mesh("ply", "stl", ("stl-a-ply", "stl-a-3mf")),
    mesh("stl", "stl", ("stl-a-3mf", "stl-a-obj"), slug_es="stl-ascii-a-binario", slug_en="stl-ascii-to-binary",
         name_es="STL ASCII a binario", name_en="STL ASCII to binary", options=MeshOptions,
         summary_es="Convierte un STL de texto (ASCII) en STL binario, que ocupa unas cinco veces menos.",
         summary_en="Convert a text (ASCII) STL into binary STL, about five times smaller."),
]
