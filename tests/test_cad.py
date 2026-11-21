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


# ——— F7-E (D-252): OpenSCAD y LibreDWG (simulados aquí; reales en la CI, en la imagen de workercad) ———

import shutil as _shutil  # noqa: E402
import subprocess  # noqa: E402
import zipfile  # noqa: E402

BOX_ASCII = trimesh.creation.box((10, 20, 30)).export(file_type="stl_ascii")


def _fake_engines(monkeypatch, seen: dict, scad_output: str | None = BOX_ASCII):
    from tools.base import run_engine as real
    from tools.cad import dwg, scad

    def fake(args, cwd, **kw):
        name = Path(args[0]).name
        if name == "openscad":
            seen["scad"] = (args, kw)
            if scad_output is not None:
                (Path(cwd) / "salida.stl").write_text(scad_output)
            return subprocess.CompletedProcess(args, 0 if scad_output else 1, b"", b"WARNING: Current top level object is empty.")
        if name == "dwg2dxf":
            seen["dwg"] = (args, kw)
            import ezdxf

            doc = ezdxf.new("R2000")
            doc.modelspace().add_line((0, 0), (100, 50))
            doc.modelspace().add_circle((50, 25), 10)
            doc.saveas(Path(cwd) / "plano.dxf")
            return subprocess.CompletedProcess(args, 0, b"", b"")
        return real(args, cwd=cwd, **kw)

    monkeypatch.setattr(scad, "run_engine", fake)
    monkeypatch.setattr(dwg, "run_engine", fake)


def test_scad_to_3mf_with_customizer_variables(make_ctx, tmp_path, monkeypatch):
    seen: dict = {}
    _fake_engines(monkeypatch, seen)
    src = tmp_path / "soporte.scad"
    src.write_text("ancho = 10; cube([ancho, 20, 30]);\n")
    out = run("scad-a-3mf", make_ctx("scad-a-3mf", [src], {"variables": "ancho = 12\n$fa = 6\netiqueta = \"A-1\"\nagujeros = [3, 4.5]",
                                                         "resolucion": "alta"}))
    args, kw = seen["scad"]
    assert args[-1] == "./modelo.scad" and ["-D", "ancho=12"] == args[args.index("-D"):args.index("-D") + 2]
    assert "-D" in args and "$fn=128" in args and 'etiqueta="A-1"' in args and "agujeros=[3, 4.5]" in args
    rules = dict(kw["landlock"])
    assert any(str(p).endswith("scad-0") for p in rules) and all(mode in ("rx", "rw") for mode in rules.values())
    from tools.mesh import formats

    assert formats.load(Path(out[0]["path"]), "3mf", 100).triangles == 12


@pytest.mark.parametrize("bad", ['x = import("/etc/passwd")', "x = 1; y = 2", "a b = 3", 'x = "a" + "b"', "x = cube(1)", "x"])
def test_scad_variables_are_literals_only(bad):
    from tools.cad.scad import parse_variables

    with pytest.raises(ToolError) as err:
        parse_variables(bad)
    assert err.value.detail == "scad_variable"


def test_scad_zip_with_includes_and_escape(make_ctx, tmp_path, monkeypatch):
    seen: dict = {}
    _fake_engines(monkeypatch, seen)
    ok = tmp_path / "caja.zip"
    with zipfile.ZipFile(ok, "w") as zf:
        zf.writestr("caja.scad", "include <lib/util.scad>\nmodulo();\n")
        zf.writestr("lib/util.scad", "module modulo() { cube(5); }\n")
    out = run("scad-a-stl", make_ctx("scad-a-stl", [ok]))
    assert seen["scad"][0][-1] == "./caja.scad" and out[0]["name"].endswith(".stl")
    bad = tmp_path / "malo.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("malo.scad", "cube(1);")
        zf.writestr("../../fuera.scad", "cube(1);")
    with pytest.raises(ToolError):
        run("scad-a-stl", make_ctx("scad-a-stl", [bad]))


def test_scad_empty_model(make_ctx, tmp_path, monkeypatch):
    _fake_engines(monkeypatch, {}, scad_output=None)
    src = tmp_path / "vacio.scad"
    src.write_text("// nada\n")
    with pytest.raises(ToolError) as err:
        run("scad-a-stl", make_ctx("scad-a-stl", [src]))
    assert err.value.detail == "scad_empty"


@pytest.mark.skipif(not _shutil.which("openscad"), reason="sin OpenSCAD (está en la imagen de workercad)")
def test_scad_real_openscad_cannot_read_outside(make_ctx, tmp_path):
    src = tmp_path / "ataque.scad"
    src.write_text('import("/etc/hostname"); cube(1);\n')
    out = run("scad-a-stl", make_ctx("scad-a-stl", [src]))
    assert len(trimesh.load(out[0]["path"], force="mesh").faces) == 12


def _dwg(tmp_path: Path, magic: bytes = b"AC1015") -> Path:
    path = tmp_path / "plano.dwg"
    path.write_bytes(magic + b"\x00" * 200)
    return path


def test_dwg_to_dxf_and_version_check(make_ctx, tmp_path, monkeypatch):
    import ezdxf

    seen: dict = {}
    _fake_engines(monkeypatch, seen)
    out = run("dwg-a-dxf", make_ctx("dwg-a-dxf", [_dwg(tmp_path)]))
    assert out[0]["name"] == "plano.dxf" and "DWG 2000" in out[0]["note"] and "LibreDWG" in out[0]["note"]
    assert len(ezdxf.readfile(out[0]["path"]).modelspace()) == 2
    assert seen["dwg"][0][1:] == ["-y", "-o", "plano.dxf", "plano.dwg"] and "landlock" in seen["dwg"][1]
    with pytest.raises(ToolError) as err:
        run("dwg-a-dxf", make_ctx("dwg-a-dxf", [_dwg(tmp_path, b"AC1009")]))
    assert err.value.detail == "dwg_version"


def test_dwg_to_pdf_through_gotenberg(make_ctx, tmp_path, monkeypatch):
    import respx
    from httpx import Response

    from test_media_tools import _gotenberg

    _fake_engines(monkeypatch, {})
    import pikepdf

    one = pikepdf.new()
    one.add_blank_page()
    blank = tmp_path / "b.pdf"
    one.save(blank)
    with respx.mock:
        route = respx.post(_gotenberg("/forms/chromium/convert/html")).mock(return_value=Response(200, content=blank.read_bytes()))
        out = run("dwg-a-pdf", make_ctx("dwg-a-pdf", [_dwg(tmp_path)], {"papel": "A3"}))
    assert out[0]["name"] == "plano.pdf" and route.called
    sent = route.calls[0].request.content
    assert b"<svg" in sent and b"297mm" in sent


def test_dwg_detection(tmp_path):
    from core.filetype import detect

    assert detect(_dwg(tmp_path), ".dwg").ext == "dwg"


def test_step_assembly_keeps_part_names_colours_and_locations(make_ctx, tmp_path):
    """D-256: en un ensamblaje, el nombre y el color son los de la pieza referida y cada instancia lleva su ubicación."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Trsf, gp_Vec
    from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_StepModelType
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool

    from tools.mesh import formats

    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    colors = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    assembly = shapes.NewShape()
    TDataStd_Name.Set_s(assembly, TCollection_ExtendedString("Conjunto"))
    screw = shapes.AddShape(BRepPrimAPI_MakeCylinder(2, 20).Shape(), False)
    TDataStd_Name.Set_s(screw, TCollection_ExtendedString("Tornillo"))
    colors.SetColor(screw, Quantity_Color(1, 0, 0, Quantity_TypeOfColor.Quantity_TOC_RGB), XCAFDoc_ColorType.XCAFDoc_ColorGen)
    nut = shapes.AddShape(BRepPrimAPI_MakeBox(8, 8, 4).Shape(), False)
    TDataStd_Name.Set_s(nut, TCollection_ExtendedString("Tuerca"))
    colors.SetColor(nut, Quantity_Color(0, 0, 1, Quantity_TypeOfColor.Quantity_TOC_RGB), XCAFDoc_ColorType.XCAFDoc_ColorGen)
    move = gp_Trsf()
    move.SetTranslation(gp_Vec(50, 0, 0))
    shapes.AddComponent(assembly, screw, TopLoc_Location())
    shapes.AddComponent(assembly, nut, TopLoc_Location(move))
    shapes.UpdateAssemblies()
    writer = STEPCAFControl_Writer()
    writer.SetColorMode(True)
    writer.SetNameMode(True)
    writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs)
    path = tmp_path / "conjunto.step"
    writer.Write(str(path))
    out = run("step-a-3mf", make_ctx("step-a-3mf", [path]))
    model = formats.load(Path(out[0]["path"]), "3mf", 10**6)
    by_name = {p.name: p for p in model.parts}
    assert set(by_name) == {"Tornillo", "Tuerca"}
    assert tuple(by_name["Tornillo"].colors[0])[:3] == (255, 0, 0) and tuple(by_name["Tuerca"].colors[0])[:3] == (0, 0, 255)
    assert by_name["Tuerca"].vertices[:, 0].min() >= 49.9  # su ubicación en el ensamblaje
