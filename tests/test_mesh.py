"""F7-A (7.18, D-244): conversiones de mallas STL, OBJ, PLY y 3MF con trimesh y lib3mf. Se comprueba la geometría (número
de caras, volumen y caja), las unidades y la escala, los colores en 3MF, PLY y OBJ con MTL, las piezas, el límite de
triángulos del plan antes de cargar el archivo y que un OBJ no puede leer archivos del disco con `mtllib`."""
from __future__ import annotations

import io
import math
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


# ——— F7-B (D-248): AMF, GLB, glTF, FBX, DAE y 3DS ———

def _assimp_export(tmp_path: Path, mesh: trimesh.Trimesh, fmt: str, ext: str) -> Path:
    """Muestra creada con el propio assimp en un subproceso (necesita libassimp; si no está, la prueba se salta)."""
    import os
    import subprocess
    import sys

    from core.settings import get_settings

    src = tmp_path / "base.obj"
    mesh.export(src)
    out = tmp_path / f"modelo.{ext}"
    env = {**os.environ, "LD_LIBRARY_PATH": get_settings().ENGINES_LIBRARY_PATH or os.environ.get("LD_LIBRARY_PATH", "")}
    code = ("import sys, pyassimp\nwith pyassimp.load(sys.argv[1]) as s:\n    pyassimp.export(s, sys.argv[2], file_type=sys.argv[3])\n")
    res = subprocess.run([sys.executable, "-c", code, str(src), str(out), fmt], env=env, capture_output=True)
    if res.returncode or not out.exists():
        pytest.skip("assimp no disponible: " + res.stderr.decode()[-200:])
    return out


def test_amf_roundtrip_with_units_colors_and_instances(make_ctx, tmp_path):
    src = _two_parts_3mf(tmp_path)
    out = run("3mf-a-stl", make_ctx("3mf-a-stl", [src]))  # solo para tener un STL de referencia
    stl = Path(out[0]["path"])
    amf_out = run("stl-a-amf", make_ctx("stl-a-amf", [stl], {"unidades_destino": "in"}))
    amf = Path(amf_out[0]["path"])
    assert amf.name == "piezas.amf" and zipfile.is_zipfile(amf)
    from tools.mesh import extra

    model = extra.read_amf(amf, 10**6)
    assert model.unit_mm == 25.4 and model.triangles == 332
    back = run("amf-a-stl", make_ctx("amf-a-stl", [amf]))
    assert abs(_load(Path(back[0]["path"])).volume - _load(stl).volume) < 1e-2
    # AMF a mano: material con color, constelación con dos instancias desplazadas y unidad en pulgadas.
    xml = ('<?xml version="1.0"?><amf unit="inch"><material id="7"><color><r>1</r><g>0</g><b>0</b></color></material>'
           '<object id="1"><mesh><vertices>' + "".join(f"<vertex><coordinates><x>{x}</x><y>{y}</y><z>{z}</z></coordinates></vertex>"
                                                     for x, y, z in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)))
           + '</vertices><volume materialid="7"><triangle><v1>0</v1><v2>2</v2><v3>1</v3></triangle><triangle><v1>0</v1><v2>1</v2><v3>3</v3></triangle>'
           '<triangle><v1>0</v1><v2>3</v2><v3>2</v3></triangle><triangle><v1>1</v1><v2>2</v2><v3>3</v3></triangle></volume></mesh></object>'
           '<constellation id="2"><instance objectid="1"><deltax>0</deltax></instance><instance objectid="1"><deltax>5</deltax><rz>90</rz></instance></constellation></amf>')
    hand = tmp_path / "mano.amf"
    hand.write_text(xml)
    model = extra.read_amf(hand, 100)
    assert len(model.parts) == 2 and model.triangles == 8 and tuple(model.parts[0].colors[0]) == (255, 0, 0, 255)
    assert np.allclose(model.parts[1].vertices[1], (5, 1, 0))  # (1, 0, 0) girado 90° en Z y desplazado 5
    out = run("amf-a-3mf", make_ctx("amf-a-3mf", [hand], {"unidades_destino": "mm"}))
    from tools.mesh import formats

    tmf = formats.load(Path(out[0]["path"]), "3mf", 100)
    assert np.isclose(tmf.parts[1].vertices[:, 0].max(), 5 * 25.4) and tmf.has_colors


def test_glb_is_y_up_in_metres_and_keeps_colours(make_ctx, tmp_path):
    src = _two_parts_3mf(tmp_path)
    stl = Path(run("3mf-a-stl", make_ctx("3mf-a-stl", [src]))[0]["path"])
    out = run("stl-a-glb", make_ctx("stl-a-glb", [stl]))
    glb = Path(out[0]["path"])
    assert glb.read_bytes()[:4] == b"glTF" and "Y vertical de glTF" in out[0]["note"] and "milímetros → metros" in out[0]["note"]
    scene = trimesh.load(glb)
    # Cubo de 10 mm en el origen y bola de radio 4 en x = 20: de −5 a 24 mm, en metros; Z vertical pasa a Y.
    assert np.allclose(scene.extents, (0.029, 0.01, 0.01), atol=1e-4)
    # De vuelta a STL: milímetros y Z vertical otra vez, con la misma caja.
    back = run("glb-a-stl", make_ctx("glb-a-stl", [glb]))
    assert np.allclose(_load(Path(back[0]["path"])).extents, _load(stl).extents, atol=1e-3)
    # Colores: un material por color.
    from tools.mesh import extra, formats

    model = formats.load(src, "3mf", 10**6)
    extra.write_glb(model, tmp_path / "c.glb")
    again = formats.load(tmp_path / "c.glb", "glb", 10**6)
    assert again.has_colors and {tuple(c) for p in again.parts for c in np.unique(p.colors, axis=0)} >= {(255, 0, 0, 255), (0, 0, 255, 255)}


def test_gltf_needs_embedded_buffers(make_ctx, tmp_path):
    import base64
    import json

    from tools.mesh.recuento import count_triangles

    box = trimesh.creation.box((1, 2, 3))
    files = box.export(file_type="gltf")
    doc = json.loads(files["model.gltf"])
    external = tmp_path / "fuera.gltf"
    external.write_text(json.dumps(doc))
    with pytest.raises(ToolError) as err:
        run("gltf-a-stl", make_ctx("gltf-a-stl", [external]))
    assert err.value.detail == "gltf_external"
    for buf in doc["buffers"]:
        buf["uri"] = "data:application/octet-stream;base64," + base64.b64encode(files[buf["uri"]]).decode()
    embedded = tmp_path / "dentro.gltf"
    embedded.write_text(json.dumps(doc))
    assert count_triangles(embedded, "gltf") == 12
    out = run("gltf-a-stl", make_ctx("gltf-a-stl", [embedded]))
    assert np.allclose(sorted(_load(Path(out[0]["path"])).extents), [1000, 2000, 3000])  # metros a milímetros


@pytest.mark.parametrize("fmt,ext,tool", [("fbx", "fbx", "fbx-a-stl"), ("collada", "dae", "dae-a-stl"), ("3ds", "3ds", "3ds-a-stl"),
                                          ("fbx", "fbx", "fbx-a-obj")])
def test_assimp_formats_in_a_sandboxed_child(make_ctx, tmp_path, fmt, ext, tool):
    box = trimesh.creation.box((10, 20, 30))
    src = _assimp_export(tmp_path, box, fmt, ext)
    out = run(tool, make_ctx(tool, [src], {"conservar_ejes": True, "unidades_origen": "mm"}))
    mesh = _load(Path(out[0]["path"]))
    assert len(mesh.faces) == 12
    extents = sorted(np.round(mesh.extents, 3))
    assert extents == [10, 20, 30] or extents == [0.01, 0.02, 0.03] or ext == "3ds"


def test_assimp_child_limit_and_crash_isolation(make_ctx, tmp_path):
    src = _assimp_export(tmp_path, trimesh.creation.icosphere(3), "collada", "dae")
    ctx = make_ctx("dae-a-stl", [src])
    ctx.plan = ctx.plan.model_copy(update={"mesh_triangles": 100})
    with pytest.raises(ToolError) as err:
        run("dae-a-stl", ctx)
    assert err.value.code == "LIMIT_EXCEEDED"
    junk = tmp_path / "basura.fbx"
    junk.write_bytes(b"Kaydara FBX Binary  \x00\x1a\x00" + b"\xff" * 4000)
    with pytest.raises(ToolError):
        run("fbx-a-stl", make_ctx("fbx-a-stl", [junk]))


def test_detection_of_f7b_files(tmp_path):
    from core.filetype import detect

    glb = tmp_path / "a.glb"
    glb.write_bytes(trimesh.creation.box().export(file_type="glb"))
    assert detect(glb, ".glb").ext == "glb"
    fbx = tmp_path / "a.fbx"
    fbx.write_bytes(b"Kaydara FBX Binary  \x00\x1a\x00" + b"\x00" * 100)
    assert detect(fbx, ".fbx").ext == "fbx"
    amf = tmp_path / "z.amf"
    with zipfile.ZipFile(amf, "w") as zf:
        zf.writestr("z.amf", "<amf/>")
    assert detect(amf, ".amf").ext == "amf"


# ——— D-249: correcciones de la revisión de F7-A ———

def _3mf_instances(tmp_path: Path, items: int, mirror: bool = False) -> Path:
    import lib3mf

    from tools.mesh import formats

    w = lib3mf.get_wrapper()
    model = w.CreateModel()
    box = trimesh.creation.box((10, 10, 10))
    mesh = model.AddMeshObject()
    mesh.SetGeometry([lib3mf.Position((lib3mf.ctypes.c_float * 3)(*v)) for v in box.vertices.astype(np.float32)],
                     [lib3mf.Triangle((lib3mf.ctypes.c_uint32 * 3)(*f)) for f in box.faces.astype(np.uint32)])
    for i in range(items):
        t = w.GetIdentityTransform()
        if mirror:
            t.Fields[0][0] = -1.0
        t.Fields[3][0] = 20.0 * i
        model.AddBuildItem(mesh, t)
    path = tmp_path / f"instancias-{items}.3mf"
    with formats.keep_locale():
        model.QueryWriter("3mf").WriteToFile(str(path))
    return path


def test_3mf_instances_count_before_copying(tmp_path):
    from tools.mesh import formats

    many = _3mf_instances(tmp_path, 50)  # 12 triángulos × 50 elementos
    with pytest.raises(ToolError) as err:
        formats.load(many, "3mf", 500)
    assert err.value.code == "LIMIT_EXCEEDED"
    assert formats.load(many, "3mf", 600).triangles == 600


def test_mirrored_3mf_keeps_outward_faces(tmp_path):
    from tools.mesh import formats

    model = formats.load(_3mf_instances(tmp_path, 1, mirror=True), "3mf", 100)
    part = model.parts[0]
    assert trimesh.Trimesh(part.vertices, part.faces, process=False).volume > 0


def test_counts_that_used_to_be_bypassed(tmp_path):
    from tools.mesh.recuento import count_triangles

    ply = tmp_path / "trampa.ply"
    ply.write_bytes(b"ply\nformat ascii 1.0\ncomment element face 1\nelement vertex 3000\nproperty float x\nproperty float y\n"
                    b"property float z\nelement face 2000\nproperty list uchar int vertex_indices\nend_header\n")
    assert count_triangles(ply, "ply") == 2000
    stl = tmp_path / "MAYUS.stl"
    stl.write_text("SOLID A\n" + "FACET NORMAL 0 0 1\n OUTER LOOP\n" + "  VERTEX 0 0 0\n  VERTEX 1 0 0\n  VERTEX 0 1 0\n ENDLOOP\nENDFACET\n" * 7)
    assert count_triangles(stl, "stl") == 7
    obj = tmp_path / "vertices.obj"
    obj.write_text("v 0 0 0\n" * 3000 + "f 1 2 3\n")
    assert count_triangles(obj, "obj") == 1000


def test_memory_blowup_kills_the_child_not_the_worker(make_ctx, tmp_path, monkeypatch):
    big = tmp_path / "bola.stl"
    big.write_bytes(trimesh.creation.icosphere(subdivisions=7).export(file_type="stl"))
    ctx = make_ctx("stl-a-3mf", [big])
    monkeypatch.setattr(ctx.settings, "MESH_MEMORY_MB", 90)
    with pytest.raises(ToolError) as err:
        run("stl-a-3mf", ctx)
    assert err.value.code in ("LIMIT_EXCEEDED", "ENGINE_FAILED")


def test_obj_material_next_to_it_is_not_read(tmp_path):
    from tools.mesh import formats

    (tmp_path / "mat.mtl").write_text("newmtl rojo\nKd 1 0 0\n")
    obj = tmp_path / "ataque.obj"
    obj.write_text("mtllib mat.mtl\nusemtl rojo\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    model = formats._from_trimesh(obj, "obj")
    assert not model.has_colors and "textures" not in model.lost


def test_obj_palette_keeps_alpha_and_uncoloured_parts_are_grey(tmp_path):
    from tools.mesh import formats

    box = trimesh.creation.box()
    rng = np.random.default_rng(1)
    colors = np.c_[rng.integers(0, 255, (len(box.faces), 3)), np.full(len(box.faces), 255)].astype(np.uint8)
    colors = np.repeat(colors, 30, axis=0)[: len(box.faces)]
    many = trimesh.creation.icosphere(4)
    many_colors = np.c_[rng.integers(0, 255, (len(many.faces), 3)), np.full(len(many.faces), 255)].astype(np.uint8)
    model = formats.Model([formats.Part("color", many.vertices, many.faces, many_colors), formats.Part("liso", box.vertices, box.faces)])
    mtl = formats.write_obj(model, tmp_path / "a.obj", "a.mtl")
    assert "d 0.9412" not in mtl and mtl.count("newmtl") <= 217
    text = (tmp_path / "a.obj").read_text()
    assert text.split("\no liso\n", 1)[1].split("\nf ", 1)[0].endswith("usemtl sin_color")


# ——— F7-C (D-250): VRML, X3D, USDZ, OFF y convertir-modelo-3d ———

VRML = b"""#VRML V2.0 utf8
# pieza con DEF/USE, Transform y color por cara
DEF Caja Transform { translation 10 0 0 rotation 0 0 1 1.5708 children [
  Shape { appearance Appearance { material Material { diffuseColor 1 0 0 } }
    geometry IndexedFaceSet { coord Coordinate { point [ 0 0 0, 1 0 0, 1 1 0, 0 1 0 ] }
      coordIndex [ 0 1 2 3 -1 ] colorPerVertex FALSE color Color { color [ 0 0 1 ] } } } ] }
Transform { translation 0 5 0 children [ USE Caja ] }
"""


def test_vrml_def_use_transforms_and_colours(make_ctx, tmp_path):
    from tools.mesh import escena

    wrl = tmp_path / "escena.wrl"
    wrl.write_bytes(VRML)
    model = escena.read_scene(wrl, "wrl", 100)
    assert model.triangles == 4 and len(model.parts) == 2 and model.up == "y"
    assert tuple(model.parts[0].colors[0]) == (0, 0, 255, 255)  # el color por cara gana al del material
    assert np.allclose(model.parts[0].vertices[1], (10, 1, 0), atol=1e-4)  # (1, 0, 0) girado 90° en Z y desplazado
    assert np.allclose(model.parts[1].vertices[1], (10, 6, 0), atol=1e-4)
    with pytest.raises(ToolError):
        escena.read_scene(wrl, "wrl", 3)  # USE cuenta sus triángulos otra vez
    out = run("wrl-a-stl", make_ctx("wrl-a-stl", [wrl]))
    assert len(_load(Path(out[0]["path"])).faces) == 4 and "Z vertical" in out[0]["note"]


def test_x3d_and_vrml_writers_roundtrip(make_ctx, tmp_path):
    from tools.mesh import escena

    src = _two_parts_3mf(tmp_path)
    stl = Path(run("3mf-a-stl", make_ctx("3mf-a-stl", [src]))[0]["path"])
    for tool, ext in (("stl-a-x3d", "x3d"), ("stl-a-wrl", "wrl")):
        out = Path(run(tool, make_ctx(tool, [stl]))[0]["path"])
        assert out.suffix == f".{ext}"
        back = escena.read_scene(out, ext, 10**6)
        assert back.triangles == 332
    model = formats_load(src)
    escena.write_x3d(model, tmp_path / "c.x3d")
    again = escena.read_scene(tmp_path / "c.x3d", "x3d", 10**6)
    assert again.has_colors and {tuple(c) for c in np.unique(np.vstack([p.colors for p in again.parts]), axis=0)} == {(255, 0, 0, 255), (0, 0, 255, 255)}


def formats_load(path: Path):
    from tools.mesh import formats

    return formats.load(path, path.suffix.lstrip("."), 10**6)


def test_usdz_for_augmented_reality(make_ctx, tmp_path):
    pytest.importorskip("pxr")
    from tools.mesh import usd

    src = _two_parts_3mf(tmp_path, colors=False)
    obj = Path(run("3mf-a-obj", make_ctx("3mf-a-obj", [src], {"piezas": "fusionar"}))[0]["path"])
    assert obj.suffix == ".obj"
    out = run("obj-a-usdz", make_ctx("obj-a-usdz", [obj], {"unidades_destino": "m"}))
    usdz = Path(out[0]["path"])
    assert usdz.suffix == ".usdz" and zipfile.is_zipfile(usdz)
    with zipfile.ZipFile(usdz) as zf:
        assert zf.infolist()[0].filename.endswith(".usdc") and zf.infolist()[0].compress_type == zipfile.ZIP_STORED
    model = usd.read_usd(usdz, 10**6)
    assert model.unit_mm == 1000.0 and model.up == "y" and model.triangles == 332
    colored = tmp_path / "color.usdz"
    usd.write_usdz(formats_load(_two_parts_3mf(tmp_path)), colored, "mm")
    assert usd.read_usd(colored, 10**6).has_colors
    extents = np.ptp(np.vstack([p.vertices for p in model.parts]), axis=0)
    assert np.isclose(extents.max(), 0.029, atol=1e-3)  # 29 mm en metros


@pytest.mark.parametrize("fmt", ["stl", "obj", "3mf", "ply", "off", "amf", "glb", "x3d", "wrl", "usdz"])
def test_convert_any_model_to_every_output(make_ctx, tmp_path, fmt):
    if fmt == "usdz":
        pytest.importorskip("pxr")
    src = _box(tmp_path)
    out = run("convertir-modelo-3d", make_ctx("convertir-modelo-3d", [src], {"formato": fmt}))
    assert out[0]["name"].endswith(f".{fmt}") or out[0]["name"].endswith(".zip")
    back = run("convertir-modelo-3d", make_ctx("convertir-modelo-3d", [Path(out[0]["path"])], {"formato": "stl"})) if fmt != "obj" or out[0]["name"].endswith(".obj") else None
    if back:
        mesh = _load(Path(back[0]["path"]))
        assert len(mesh.faces) == 12 and np.allclose(sorted(mesh.extents), [10, 20, 30], atol=1e-3)


def test_detection_of_f7c_files(tmp_path):
    from core.filetype import detect, matches

    wrl = tmp_path / "a.wrl"
    wrl.write_bytes(VRML)
    assert matches(detect(wrl, ".wrl"), ".wrl", ("wrl",))
    off = tmp_path / "a.off"
    off.write_text("OFF\n3 1 0\n0 0 0\n1 0 0\n0 1 0\n3 0 1 2\n")
    assert matches(detect(off, ".off"), ".off", ("off",))


# ——— F7-F (D-253): reparar, reducir, escalar, unidades, cortar, separar, unir y analizar ———

def _broken(tmp_path: Path) -> Path:
    box = trimesh.creation.box((10, 10, 10))
    faces = box.faces[1:]  # un hueco (falta un triángulo)
    faces = np.vstack([faces, faces[:1], [[0, 0, 1]]])  # una cara repetida y una degenerada
    loose = trimesh.creation.box((0.1, 0.1, 0.1))
    loose.apply_translation((50, 0, 0))
    mesh = trimesh.util.concatenate([trimesh.Trimesh(box.vertices, faces, process=False), loose])
    path = tmp_path / "roto.stl"
    path.write_bytes(trimesh.Trimesh(mesh.vertices, mesh.faces, process=False).export(file_type="stl"))
    return path


def test_repair_closes_holes_and_cleans(make_ctx, tmp_path):
    out = run("reparar-stl", make_ctx("reparar-stl", [_broken(tmp_path)]))
    mesh = _load(Path(out[0]["path"]))
    assert mesh.is_watertight and abs(mesh.volume - 1000) < 1e-6
    note = out[0]["note"]
    assert "1 huecos cerrados" in note and "1 caras degeneradas" in note and "1 repetidas" in note and "piezas sueltas" in note
    assert "cerrada (estanca)" in note


def test_reduce_polygons(make_ctx, tmp_path):
    src = tmp_path / "bola.stl"
    src.write_bytes(trimesh.creation.icosphere(5).export(file_type="stl"))
    out = run("reducir-poligonos", make_ctx("reducir-poligonos", [src], {"reduccion": 80}))
    mesh = _load(Path(out[0]["path"]))
    assert 3500 < len(mesh.faces) < 4600 and "80 % menos" in out[0]["note"].replace("79 %", "80 %").replace("81 %", "80 %")
    out = run("reducir-poligonos", make_ctx("reducir-poligonos", [src], {"triangulos": 1000, "formato_salida": "3mf"}))
    assert out[0]["name"].endswith(".3mf")


def test_scale_and_units(make_ctx, tmp_path):
    src = _box(tmp_path)
    out = run("escalar-modelo-3d", make_ctx("escalar-modelo-3d", [src], {"modo": "medida", "eje": "mayor", "medida_mm": 60}))
    assert np.allclose(sorted(_load(Path(out[0]["path"])).extents), [20, 40, 60])
    out = run("escalar-modelo-3d", make_ctx("escalar-modelo-3d", [src], {"factor": 2, "escala_z": 0.5}))
    assert np.allclose(_load(Path(out[0]["path"])).extents, [20, 40, 30])
    inches = tmp_path / "pulgadas.stl"
    inches.write_bytes(trimesh.creation.box((1, 2, 3)).export(file_type="stl"))
    out = run("cambiar-unidades-stl", make_ctx("cambiar-unidades-stl", [inches], {"de": "in", "a": "mm"}))
    assert np.allclose(_load(Path(out[0]["path"])).extents, [25.4, 50.8, 76.2]) and "pulgadas → milímetros" in out[0]["note"]


def test_cut_caps_the_section(make_ctx, tmp_path):
    src = _box(tmp_path)  # 10 × 20 × 30 centrada en el origen
    out = run("cortar-modelo-3d", make_ctx("cortar-modelo-3d", [src], {"eje": "z", "posicion": 25}))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        names = sorted(zf.namelist())
        zf.extractall(tmp_path / "corte")
    assert names == ["caja-debajo.stl", "caja-encima.stl"] and "tapada" in out[0]["note"]
    low = trimesh.load(tmp_path / "corte" / "caja-debajo.stl", force="mesh")
    high = trimesh.load(tmp_path / "corte" / "caja-encima.stl", force="mesh")
    assert low.is_watertight and high.is_watertight
    assert abs(low.volume - 1500) < 1e-3 and abs(high.volume - 4500) < 1e-3
    only = run("cortar-modelo-3d", make_ctx("cortar-modelo-3d", [src], {"unidad_posicion": "mm", "posicion": 0, "conservar": "encima"}))
    assert abs(_load(Path(only[0]["path"])).volume - 3000) < 1e-3
    with pytest.raises(ToolError):
        run("cortar-modelo-3d", make_ctx("cortar-modelo-3d", [src], {"unidad_posicion": "mm", "posicion": 100, "conservar": "encima"}))


def test_separate_and_join(make_ctx, tmp_path):
    a = trimesh.creation.box((10, 10, 10))
    b = trimesh.creation.icosphere(2, 5)
    b.apply_translation((30, 0, 0))
    both = tmp_path / "dos.stl"
    both.write_bytes(trimesh.util.concatenate([a, b]).export(file_type="stl"))
    out = run("separar-piezas", make_ctx("separar-piezas", [both]))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        assert len(zf.namelist()) == 2
    assert "2 piezas separadas" in out[0]["note"]
    one = tmp_path / "uno.stl"
    one.write_bytes(a.export(file_type="stl"))
    two = tmp_path / "otro.stl"
    two.write_bytes(trimesh.creation.box((10, 10, 10)).apply_translation((5, 0, 0)).export(file_type="stl"))
    out = run("unir-modelos", make_ctx("unir-modelos", [one, two], {"fusionar": True, "formato_salida": "stl"}))
    mesh = _load(Path(out[0]["path"]))
    assert abs(mesh.volume - 1500) < 1e-3 and "un solo sólido" in out[0]["note"]  # se solapan 5 mm
    out = run("unir-modelos", make_ctx("unir-modelos", [one, two], {"modo": "distribuir"}))
    from tools.mesh import formats

    model = formats.load(Path(out[0]["path"]), "3mf", 10**6)
    assert [p.name for p in model.parts] == ["uno", "otro"]
    assert model.parts[1].vertices[:, 0].min() >= model.parts[0].vertices[:, 0].max() + 4.99
    with pytest.raises(ToolError):
        run("unir-modelos", make_ctx("unir-modelos", [one]))


def test_analyse_with_filament_estimate(make_ctx, tmp_path):
    import json

    src = _box(tmp_path)
    out = run("analizar-stl", make_ctx("analizar-stl", [src], {"material": "PETG", "relleno": 20, "formato": "json"}))
    data = json.loads(Path(out[0]["path"]).read_text())
    assert data["estanca"] and data["volumen_cm3"] == 6.0 and data["dimensiones_mm"] == {"x": 10.0, "y": 20.0, "z": 30.0}
    est = data["estimacion_filamento"]
    shell = min(6000, 2200 * 1.2)
    expected = (shell + 0.2 * (6000 - shell)) / 1000 * 1.27
    assert est["material"] == "PETG" and abs(est["gramos"] - expected) < 0.1 and "Estimación de PETG" in out[0]["note"]
    text = run("analizar-stl", make_ctx("analizar-stl", [_broken(tmp_path)]))
    body = Path(text[0]["path"]).read_text()
    assert "Estanca (cerrada): no" in body and "no se puede medir" in body


# ——— F7-G (D-254): generadores ———

def _png(tmp_path: Path, name: str, array: np.ndarray) -> Path:
    from PIL import Image

    path = tmp_path / name
    Image.fromarray(array.astype(np.uint8)).save(path)
    return path


def test_svg_extrudes_filled_shapes_with_holes(make_ctx, tmp_path):
    svg = tmp_path / "anillo.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm" viewBox="0 0 100 50">'
                   '<path fill-rule="evenodd" d="M0 0H40V40H0Z M10 10H30V30H10Z"/>'
                   '<rect x="50" y="0" width="20" height="20" fill="none" stroke="black"/>'  # solo trazo: no cuenta
                   '<circle cx="80" cy="20" r="10"/></svg>')
    out = run("svg-a-stl", make_ctx("svg-a-stl", [svg], {"altura_mm": 2}))
    mesh = _load(Path(out[0]["path"]))
    expected = (40 * 40 - 20 * 20 + math.pi * 100) * 2  # cuadrado con agujero y círculo, a 2 mm
    assert mesh.is_watertight and abs(mesh.volume - expected) / expected < 0.01
    assert np.isclose(mesh.extents[2], 2.0)
    out = run("svg-a-stl", make_ctx("svg-a-stl", [svg], {"altura_mm": 2, "ancho_mm": 180, "base_mm": 1}))
    mesh = _load(Path(out[0]["path"]))
    assert mesh.is_watertight and np.isclose(mesh.extents[2], 3.0) and mesh.extents[0] > 180


def test_dxf_closed_outlines_and_linked_lines(make_ctx, tmp_path):
    import ezdxf

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5  # centímetros
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (4, 0), (4, 4), (0, 4)], close=True)
    for a, b in (((6, 0), (8, 0)), ((8, 0), (8, 2)), ((8, 2), (6, 2)), ((6, 2), (6, 0))):  # cuadrado de líneas sueltas
        msp.add_line(a, b)
    path = tmp_path / "plano.dxf"
    doc.saveas(path)
    out = run("dxf-a-stl", make_ctx("dxf-a-stl", [path], {"altura_mm": 1}))
    mesh = _load(Path(out[0]["path"]))
    assert abs(mesh.volume - (40 * 40 + 20 * 20) * 1) < 1  # en milímetros


def test_logo_and_image_relief(make_ctx, tmp_path):
    img = np.full((200, 300), 255)
    img[50:150, 40:140] = 0  # cuadrado negro
    img[80:120, 70:110] = 255  # con agujero blanco
    img[60:140, 180:260] = 100  # gris medio
    logo = _png(tmp_path, "logo.png", img)
    out = run("logo-a-stl", make_ctx("logo-a-stl", [logo], {"ancho_mm": 150, "altura_mm": 2, "umbral": 150}))
    mesh = _load(Path(out[0]["path"]))
    assert mesh.is_watertight and np.isclose(mesh.extents[2], 2.0, atol=1e-3)
    px = 150 / 300
    expected = ((100 * 100 - 40 * 40) + 80 * 80) * px * px * 2
    assert abs(mesh.volume - expected) / expected < 0.05
    out = run("imagen-a-stl", make_ctx("imagen-a-stl", [logo], {"niveles": 3, "altura_mm": 3, "base_mm": 1}))
    mesh = _load(Path(out[0]["path"]))
    assert mesh.is_watertight and np.isclose(mesh.extents[2], 4.0, atol=1e-3) and "niveles" in out[0]["note"]


def test_text_to_stl_without_input(make_ctx, tmp_path):
    out = run("texto-a-stl", make_ctx("texto-a-stl", [], {"texto": "Ana\nB-1", "tamano_mm": 10, "altura_mm": 2, "base_mm": 1.5}))
    mesh = _load(Path(out[0]["path"]))
    assert out[0]["name"] == "texto.stl" and mesh.is_watertight and np.isclose(mesh.extents[2], 3.5, atol=1e-3)
    assert 20 < mesh.extents[0] < 60 and "DejaVuSans-Bold" in out[0]["note"]
    with pytest.raises(ToolError):
        run("texto-a-stl", make_ctx("texto-a-stl", [], {"texto": "   "}))


@pytest.mark.parametrize("shape", ["plana", "curva", "cilindrica"])
def test_lithophane_is_watertight(make_ctx, tmp_path, shape):
    gradient = np.tile(np.linspace(0, 255, 120), (80, 1))
    photo = _png(tmp_path, "foto.png", gradient)
    out = run("litofania", make_ctx("litofania", [photo], {"forma": shape, "ancho_mm": 100, "resolucion": 1}))
    mesh = _load(Path(out[0]["path"]))
    assert mesh.is_watertight and mesh.volume > 0
    if shape == "plana":
        assert np.isclose(mesh.extents[2], 3.0, atol=0.05) and np.isclose(mesh.extents[0], 100, atol=0.5)


def test_heightmap_relief(make_ctx, tmp_path):
    ramp = np.tile(np.linspace(0, 255, 64), (32, 1))
    path = _png(tmp_path, "terreno.png", ramp)
    out = run("mapa-de-alturas-a-stl", make_ctx("mapa-de-alturas-a-stl", [path], {"ancho_mm": 64, "altura_mm": 10, "base_mm": 2, "resolucion": 1}))
    mesh = _load(Path(out[0]["path"]))
    assert mesh.is_watertight and np.isclose(mesh.extents[2], 12.0, atol=0.01)
    assert abs(mesh.volume - (2 + 5) * 64 * mesh.extents[1]) / mesh.volume < 0.05  # rampa: altura media 5 sobre la base
