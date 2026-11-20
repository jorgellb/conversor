"""F7-A (7.18, D-244): conversiones de mallas STL, OBJ, PLY y 3MF con trimesh y lib3mf. Se comprueba la geometría (número
de caras, volumen y caja), las unidades y la escala, los colores en 3MF, PLY y OBJ con MTL, las piezas, el límite de
triángulos del plan antes de cargar el archivo y que un OBJ no puede leer archivos del disco con `mtllib`."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("trimesh")
pytest.importorskip("lib3mf")

import trimesh  # noqa: E402

from core.errors import ToolError  # noqa: E402
from test_tools import make_ctx, run  # noqa: E402,F401  (fixture)


def _box(tmp_path: Path, name: str = "caja.stl", ascii: bool = False) -> Path:
    mesh = trimesh.creation.box((10, 20, 30))
    path = tmp_path / name
    data = mesh.export(file_type="stl_ascii" if ascii else "stl")
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def _two_parts_3mf(tmp_path: Path, unit: str = "mm", colors: bool = True) -> Path:
    from tools.mesh import formats

    box = trimesh.creation.box((10, 10, 10))
    ball = trimesh.creation.icosphere(2, 4)
    ball.apply_translation((20, 0, 0))
    parts = [formats.Part("cubo", box.vertices, box.faces, np.tile([255, 0, 0, 255], (len(box.faces), 1)).astype(np.uint8) if colors else None),
             formats.Part("bola", ball.vertices, ball.faces, np.tile([0, 0, 255, 255], (len(ball.faces), 1)).astype(np.uint8) if colors else None)]
    path = tmp_path / "piezas.3mf"
    formats.write_3mf(formats.Model(parts), path, unit)
    return path


def _load(path: Path) -> trimesh.Trimesh:
    return trimesh.load(path, force="mesh")


def test_stl_to_3mf_and_back_keeps_geometry_and_units(make_ctx, tmp_path):
    src = _box(tmp_path)
    out = run("stl-a-3mf", make_ctx("stl-a-3mf", [src], {"unidades_destino": "cm"}))
    assert out[0]["name"] == "caja.3mf" and "milímetros → centímetros" in out[0]["note"] and "se ha tomado como milímetros" in out[0]["note"]
    from tools.mesh import formats

    model = formats.load(Path(out[0]["path"]), "3mf", 10**6)
    assert model.unit_mm == 10.0 and model.triangles == 12
    extent = model.parts[0].vertices.max(0) - model.parts[0].vertices.min(0)
    assert np.allclose(extent, (1, 2, 3))  # 10 × 20 × 30 mm en centímetros
    back = run("3mf-a-stl", make_ctx("3mf-a-stl", [Path(out[0]["path"])], {"unidades_destino": "mm"}))
    mesh = _load(Path(back[0]["path"]))
    assert np.allclose(mesh.extents, (10, 20, 30)) and abs(mesh.volume - 6000) < 1e-3


def test_3mf_colors_go_to_ply_and_obj_but_not_stl(make_ctx, tmp_path):
    src = _two_parts_3mf(tmp_path)
    out = run("3mf-a-stl", make_ctx("3mf-a-stl", [src]))
    assert "no guarda colores" in out[0]["note"] and "2 piezas" not in out[0]["note"]
    assert len(_load(Path(out[0]["path"])).faces) == 12 + 320
    out = run("3mf-a-obj", make_ctx("3mf-a-obj", [src]))
    assert out[0]["name"] == "piezas-obj.zip" and "2 piezas" in out[0]["note"]
    with zipfile.ZipFile(out[0]["path"]) as zf:
        obj = zf.read("piezas.obj").decode()
        mtl = zf.read("piezas.mtl").decode()
    assert "mtllib piezas.mtl" in obj and obj.count("\no ") == 2 and "Kd 1.0000 0.0000 0.0000" in mtl and "Kd 0.0000 0.0000 1.0000" in mtl
    # El 3MF de vuelta conserva los colores.
    from tools.mesh import formats

    model = formats.load(src, "3mf", 10**6)
    assert [p.name for p in model.parts] == ["cubo", "bola"] and tuple(model.parts[0].colors[0]) == (255, 0, 0, 255)


def test_stl_to_ply_and_obj_and_ascii_to_binary(make_ctx, tmp_path):
    src = _box(tmp_path, "texto.stl", ascii=True)
    out = run("stl-ascii-a-binario", make_ctx("stl-ascii-a-binario", [src]))
    path = Path(out[0]["path"])
    from tools.mesh.recuento import stl_is_binary

    assert stl_is_binary(path) and path.stat().st_size == 84 + 50 * 12 and path.stat().st_size < src.stat().st_size
    out = run("stl-a-ply", make_ctx("stl-a-ply", [path]))
    assert abs(_load(Path(out[0]["path"])).volume - 6000) < 1e-3
    out = run("stl-a-obj", make_ctx("stl-a-obj", [path], {"escala": 2}))
    assert out[0]["name"] == "texto.obj" and "escala × 2" in out[0]["note"]
    assert abs(_load(Path(out[0]["path"])).volume - 48000) < 1e-2
    out = run("obj-a-stl", make_ctx("obj-a-stl", [Path(out[0]["path"])], {"stl": "ascii"}))
    assert Path(out[0]["path"]).read_bytes().startswith(b"solid")


def test_separate_and_merge_parts(make_ctx, tmp_path):
    src = _two_parts_3mf(tmp_path, colors=False)
    out = run("3mf-a-stl", make_ctx("3mf-a-stl", [src], {"piezas": "separar"}))
    assert out[0]["name"] == "piezas-piezas.zip"
    with zipfile.ZipFile(out[0]["path"]) as zf:
        assert sorted(zf.namelist()) == ["piezas-01-cubo.stl", "piezas-02-bola.stl"]
    out = run("3mf-a-obj", make_ctx("3mf-a-obj", [src], {"piezas": "fusionar"}))
    assert Path(out[0]["path"]).read_text().count("\no ") == 1


def test_triangle_limit_before_loading(make_ctx, tmp_path):
    from tools.mesh.recuento import count_triangles

    big = trimesh.creation.icosphere(subdivisions=5)  # 20 480 caras
    stl = tmp_path / "bola.stl"
    stl.write_bytes(big.export(file_type="stl"))
    ascii = tmp_path / "bola-texto.stl"
    ascii.write_text(big.export(file_type="stl_ascii"))
    obj = tmp_path / "bola.obj"
    obj.write_text(big.export(file_type="obj"))
    ply = tmp_path / "bola.ply"
    ply.write_bytes(big.export(file_type="ply"))
    for path, ext in ((stl, "stl"), (ascii, "stl"), (obj, "obj"), (ply, "ply")):
        assert count_triangles(path, ext) == 20480, ext
    ctx = make_ctx("stl-a-3mf", [stl])
    ctx.plan = ctx.plan.model_copy(update={"mesh_triangles": 20000})
    with pytest.raises(ToolError) as err:
        run("stl-a-3mf", ctx)
    assert err.value.code == "LIMIT_EXCEEDED"


def test_obj_cannot_read_files_from_disk(make_ctx, tmp_path):
    secret = tmp_path / "secreto.mtl"
    secret.write_text("newmtl filtrado\nKd 1 0 0\nmap_Kd /etc/hostname\n")
    obj = tmp_path / "ataque.obj"
    obj.write_text(f"mtllib {secret}\nmtllib ../../../../etc/passwd\nusemtl filtrado\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    out = run("obj-a-3mf", make_ctx("obj-a-3mf", [obj]))
    from tools.mesh import formats

    model = formats.load(Path(out[0]["path"]), "3mf", 10)
    assert model.triangles == 1 and not model.has_colors  # el MTL de fuera no se ha leído


def test_corrupt_inputs_are_tool_errors(make_ctx, tmp_path):
    bad = tmp_path / "roto.3mf"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("3D/3dmodel.model", "<model><resources><object")
    with pytest.raises(ToolError):
        run("3mf-a-stl", make_ctx("3mf-a-stl", [bad]))
    empty = tmp_path / "vacio.obj"
    empty.write_text("# nada\n")
    with pytest.raises(ToolError):
        run("obj-a-stl", make_ctx("obj-a-stl", [empty]))


def test_detection_of_mesh_files(tmp_path):
    from core.filetype import detect, matches

    stl = _box(tmp_path)
    assert detect(stl, ".stl").ext == "stl"
    assert matches(detect(_box(tmp_path, "t.stl", ascii=True), ".stl"), ".stl", ("stl",))
    tmf = _two_parts_3mf(tmp_path)
    assert detect(tmf, ".3mf").ext == "3mf"
    ply = tmp_path / "a.ply"
    ply.write_bytes(trimesh.creation.box().export(file_type="ply"))
    assert detect(ply, ".ply").ext == "ply"
    assert not matches(detect(stl, ".stl"), ".3mf", ("3mf",))


def test_api_precheck_rejects_too_many_triangles_before_queueing(tmp_path):
    from core.errors import AppError
    from core.plans import load_plans_file
    from core.registry import load_precheck, load_registry
    from core.settings import get_settings

    spec = load_registry().require("stl-a-3mf")
    check = load_precheck(spec)
    assert check is not None
    plan = load_plans_file(get_settings().PLANS_FILE)["free"].model_copy(update={"mesh_triangles": 100})
    stl = _box(tmp_path)  # 12 triángulos: pasa
    check(get_settings(), plan, "user", {}, [stl])
    big = tmp_path / "bola.stl"
    big.write_bytes(trimesh.creation.icosphere(subdivisions=3).export(file_type="stl"))  # 1280
    with pytest.raises(AppError) as err:
        check(get_settings(), plan, "user", {}, [big])
    assert err.value.status == 413
    tmf = _two_parts_3mf(tmp_path)
    with pytest.raises(AppError):
        check(get_settings(), plan, "user", {}, [tmf])


def test_lib3mf_does_not_change_the_process_locale(tmp_path):
    import locale

    before = locale.getencoding()
    _two_parts_3mf(tmp_path)
    from tools.mesh import formats

    formats.load(tmp_path / "piezas.3mf", "3mf", 10**6)
    assert locale.getencoding() == before
