"""F7-D (7.19, D-251): STEP, IGES y BREP con OpenCascade (piezas creadas con OCP), teselado con calidad elegible, nombres y
colores a 3MF, IGES a STEP sin teselar y mallas a STEP facetado, todo en el proceso hijo de las mallas."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("OCP")
trimesh = pytest.importorskip("trimesh")

from core.errors import ToolError  # noqa: E402
from test_tools import make_ctx, run  # noqa: E402,F401  (fixture)


def _shapes():
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder

    box = BRepPrimAPI_MakeBox(10, 20, 30).Shape()
    hole = BRepPrimAPI_MakeCylinder(3, 40).Shape()
    return BRepAlgoAPI_Cut(box, hole).Shape(), BRepPrimAPI_MakeCylinder(5, 10).Shape()


def _step(tmp_path: Path, name: str = "pieza.step") -> Path:
    from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_StepModelType
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool

    plate, cyl = _shapes()
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    colors = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    a = shapes.AddShape(plate, False)
    TDataStd_Name.Set_s(a, TCollection_ExtendedString("placa"))
    colors.SetColor(a, Quantity_Color(1, 0, 0, Quantity_TypeOfColor.Quantity_TOC_RGB), XCAFDoc_ColorType.XCAFDoc_ColorSurf)
    b = shapes.AddShape(cyl, False)
    TDataStd_Name.Set_s(b, TCollection_ExtendedString("eje"))
    writer = STEPCAFControl_Writer()
    writer.SetColorMode(True)
    writer.SetNameMode(True)
    writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs)
    path = tmp_path / name
    writer.Write(str(path))
    return path


def _iges(tmp_path: Path) -> Path:
    from OCP.IGESControl import IGESControl_Writer

    plate, _ = _shapes()
    writer = IGESControl_Writer("MM", 1)
    writer.AddShape(plate)
    writer.ComputeModel()
    path = tmp_path / "pieza.igs"
    writer.Write(str(path))
    return path


def _volume(path: Path) -> float:
    return abs(trimesh.load(path, force="mesh").volume)


EXPECTED = 10 * 20 * 30 - np.pi * 3**2 * 30 / 4  # caja menos el cuarto de cilindro de su esquina


def test_step_to_stl_with_quality(make_ctx, tmp_path):
    src = _step(tmp_path)
    low = run("step-a-stl", make_ctx("step-a-stl", [src], {"calidad": "baja", "piezas": "separar"}))
    high = run("step-a-stl", make_ctx("step-a-stl", [src], {"calidad": "alta", "piezas": "separar"}))
    import zipfile

    with zipfile.ZipFile(low[0]["path"]) as zf:
        names = sorted(zf.namelist())
        zf.extract(next(n for n in names if "placa" in n), tmp_path / "baja")
    assert any("placa" in n for n in names) and any("eje" in n for n in names) and "calidad baja" in low[0]["note"]
    with zipfile.ZipFile(high[0]["path"]) as zf:
        zf.extract(next(n for n in zf.namelist() if "placa" in n), tmp_path / "alta")
    lo = trimesh.load(next((tmp_path / "baja").glob("*.stl")), force="mesh")
    hi = trimesh.load(next((tmp_path / "alta").glob("*.stl")), force="mesh")
    assert len(hi.faces) > len(lo.faces)
    assert abs(hi.volume - EXPECTED) / EXPECTED < 0.002 and lo.is_watertight and hi.is_watertight


def test_step_to_3mf_keeps_names_colours_and_millimetres(make_ctx, tmp_path):
    from tools.mesh import formats

    out = run("step-a-3mf", make_ctx("step-a-3mf", [_step(tmp_path)]))
    model = formats.load(Path(out[0]["path"]), "3mf", 10**6)
    names = [p.name for p in model.parts]
    assert names == ["placa", "eje"] and model.unit_mm == 1.0
    assert tuple(model.parts[0].colors[0]) == (255, 0, 0, 255) and model.parts[1].colors is None


def test_iges_brep_and_glb(make_ctx, tmp_path):
    igs = _iges(tmp_path)
    out = run("iges-a-stl", make_ctx("iges-a-stl", [igs.rename(tmp_path / "pieza.iges")]))
    assert abs(_volume(Path(out[0]["path"])) - EXPECTED) / EXPECTED < 0.01
    from OCP.BRepTools import BRepTools

    brep = tmp_path / "pieza.brep"
    BRepTools.Write_s(_shapes()[0], str(brep))
    out = run("brep-a-stl", make_ctx("brep-a-stl", [brep]))
    assert abs(_volume(Path(out[0]["path"])) - EXPECTED) / EXPECTED < 0.01
    out = run("step-a-glb", make_ctx("step-a-glb", [_step(tmp_path)]))
    assert Path(out[0]["path"]).read_bytes()[:4] == b"glTF"


def test_iges_to_step_keeps_exact_geometry(make_ctx, tmp_path):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    from tools.cad import occt

    out = run("igs-a-step", make_ctx("igs-a-step", [_iges(tmp_path)]))
    assert "sin teselar" in out[0]["note"]
    [(name, shape, _c, _t)] = occt.read_shapes(Path(out[0]["path"]), "step")
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    assert abs(props.Mass() - EXPECTED) < 1e-3  # exacto, sin facetas


def test_mesh_to_faceted_step(make_ctx, tmp_path):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    from tools.cad import occt

    stl = tmp_path / "caja.stl"
    stl.write_bytes(trimesh.creation.box((10, 20, 30)).export(file_type="stl"))
    out = run("stl-a-step", make_ctx("stl-a-step", [stl]))
    assert out[0]["name"] == "caja.step" and "facetado" in out[0]["note"]
    [(_n, shape, _c, _t)] = occt.read_shapes(Path(out[0]["path"]), "step")
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    assert abs(abs(props.Mass()) - 6000) < 1e-3
    big = tmp_path / "bola.stl"
    big.write_bytes(trimesh.creation.icosphere(7).export(file_type="stl"))  # 327 680 triángulos
    with pytest.raises(ToolError) as err:
        run("stl-a-step", make_ctx("stl-a-step", [big]))
    assert err.value.detail == "step_triangles"


def test_corrupt_cad_is_a_tool_error(make_ctx, tmp_path):
    bad = tmp_path / "roto.step"
    bad.write_text("ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n#1=GARBAGE(;\nENDSEC;\nEND-ISO-10303-21;\n")
    with pytest.raises(ToolError):
        run("step-a-stl", make_ctx("step-a-stl", [bad]))
