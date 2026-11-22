"""Criterio 18 (D-264): cada herramienta del registro tiene al menos una prueba que la ejecuta. Aquí, las que solo se
probaban a través de una hermana con la misma implementación."""
from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest
import respx
import trimesh
from httpx import Response

from test_media_tools import _gotenberg
from test_tools import make_ctx, run  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[1]


def test_every_registered_tool_is_named_by_some_test():
    registry = json.loads((ROOT / "packages/registry/registry.json").read_text(encoding="utf-8"))["tools"]
    files = [p for d in ("tests", "packages/client-tools/test", "apps/web/test") for p in (ROOT / d).rglob("*")
             if p.is_file() and p.suffix in (".py", ".ts")]
    texts = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in files)
    missing = [t["slug_es"] for t in registry if not any(q in texts for q in (f'"{t["slug_es"]}"', f"'{t['slug_es']}'", f"/{t['slug_es']}"))]
    assert missing == []


@respx.mock
@pytest.mark.parametrize("tool,ext,members", [
    ("keynote-a-pdf", "key", {"Index/Document.iwa": b"\x00iwa", "Metadata/Properties.plist": b"plist"}),
    ("numbers-a-pdf", "numbers", {"Index/Document.iwa": b"\x00iwa", "Metadata/Properties.plist": b"plist"}),
    ("visio-a-pdf", "vsdx", {"[Content_Types].xml": b"<Types/>", "visio/document.xml": b"<VisioDocument/>"}),
])
def test_partial_office_imports(make_ctx, tmp_path, fixtures_dir, tool, ext, members):
    office = respx.post(_gotenberg("/forms/libreoffice/convert")).mock(
        return_value=Response(200, content=(fixtures_dir / "texto.pdf").read_bytes()))
    src = tmp_path / f"archivo.{ext}"
    with zipfile.ZipFile(src, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    out = run(tool, make_ctx(tool, [src]))
    assert office.called and out[0]["name"] == "archivo.pdf" and "solo en parte" in out[0]["note"]


def test_epub_to_azw3(make_ctx, tmp_path, monkeypatch):
    from test_libros_diapositivas import _epub

    from tools.office import libros_formato

    seen = {}

    def fake(args, cwd, **kw):
        seen["args"] = args
        Path(args[2]).write_bytes(b"TPZ3 convertido")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(libros_formato, "run_engine", fake)
    out = run("epub-a-azw3", make_ctx("epub-a-azw3", [_epub(tmp_path)]))
    assert out[0]["name"] == "libro.azw3" and seen["args"][0] == "ebook-convert" and seen["args"][2].endswith(".azw3")


def _box(tmp_path: Path, ext: str) -> Path:
    path = tmp_path / f"caja.{ext}"
    trimesh.creation.box((10, 20, 30)).export(path)
    return path


@pytest.mark.parametrize("tool,ext,target", [("ply-a-stl", "ply", "stl"), ("stl-a-usdz", "stl", "usdz")])
def test_mesh_conversions_keep_the_box(make_ctx, tmp_path, tool, ext, target):
    if target == "usdz":
        pytest.importorskip("pxr")
    out = run(tool, make_ctx(tool, [_box(tmp_path, ext)]))
    assert out[0]["name"] == f"caja.{target}"
    from tools.mesh import formats

    model = formats.load(Path(out[0]["path"]), target, 10**6)
    extent = sorted((model.parts[0].vertices.max(0) - model.parts[0].vertices.min(0)) * (model.unit_mm or 1))
    assert model.triangles == 12 and [round(v, 3) for v in extent] == [10, 20, 30]


def test_x3d_to_stl(make_ctx, tmp_path):
    from tools.mesh import escena, formats

    box = trimesh.creation.box((10, 20, 30))
    src = tmp_path / "caja.x3d"
    escena.write_x3d(formats.Model([formats.Part("caja", box.vertices, box.faces)]), src)
    out = run("x3d-a-stl", make_ctx("x3d-a-stl", [src]))
    mesh = trimesh.load(out[0]["path"], force="mesh")
    assert len(mesh.faces) == 12 and mesh.is_watertight


def test_step_family_stp_obj_and_back(make_ctx, tmp_path):
    pytest.importorskip("OCP")
    from test_cad import EXPECTED, _step

    stp = _step(tmp_path, "pieza.stp")
    out = run("stp-a-stl", make_ctx("stp-a-stl", [stp], {"piezas": "fusionar"}))
    mesh = trimesh.load(out[0]["path"], force="mesh")
    # Fusionado: la placa (EXPECTED en test_cad) más la parte del eje que sobresale, en un solo sólido cerrado.
    assert mesh.is_watertight and mesh.volume > EXPECTED * 0.99
    obj = run("step-a-obj", make_ctx("step-a-obj", [_step(tmp_path)], {"piezas": "fusionar"}))
    assert obj[0]["name"].endswith((".obj", ".zip"))
    back = run("obj-a-step", make_ctx("obj-a-step", [_box(tmp_path, "obj")]))
    assert back[0]["name"] == "caja.step" and Path(back[0]["path"]).read_text(errors="ignore").startswith("ISO-10303-21")
