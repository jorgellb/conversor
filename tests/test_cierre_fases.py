"""Cierres de fase (17, D-240, D-244 y D-259): cada herramienta de F5, F6 y F7 del catálogo (7) está en el registro con su
página completa en los dos idiomas; el vídeo de F5 es solo para Pro (`needs_video`), la paridad con PDF24 de docs/TOOLS.md no
deja nada pendiente ni sin explicación y las pruebas de formatos 3D de 16.5 están en verde."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from core.registry import load_registry
from test_tools import make_ctx, run  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[1]


def catalog_of(phase: str) -> set[str]:
    spec = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "docs" / "spec").glob("*.md") if "_completo" not in p.name)
    out = set()
    for line in spec.splitlines():
        if not re.search(rf"—\s*{phase}\b", line):
            continue
        m = re.match(r"\s*-\s*(.+?)\s+—", line)
        if not m:
            continue
        # Lo de dentro de un paréntesis son formatos («extraer-archivo-online (zip, rar, 7z, tar.gz)»), no herramientas.
        names = re.sub(r"\([^)]*\)", "", m.group(1))
        out |= {s.strip().strip("`") for s in names.split(",") if re.fullmatch(r"[a-z0-9-]+", s.strip().strip("`"))}
    return out


@pytest.mark.parametrize("phase,minimum", [("F5", 50), ("F6", 70), ("F7", 25)])
def test_every_tool_of_the_phase_is_registered_with_its_pages(phase, minimum):
    registry = load_registry()
    slugs = {t.slug_es: t for t in registry.specs}
    catalog = catalog_of(phase)
    assert len(catalog) >= minimum
    missing = sorted(s for s in catalog if s not in slugs)
    assert missing == []
    for slug in catalog:
        for lang in ("es", "en"):
            page = json.loads((ROOT / "apps" / "web" / "content" / lang / f"{slug}.json").read_text(encoding="utf-8"))
            assert page.get("complete") is True, (lang, slug)


def test_pdf24_parity_has_nothing_pending():
    tools = (ROOT / "docs" / "TOOLS.md").read_text(encoding="utf-8")
    summary = re.search(r"Resumen: (\d+) disponibles, (\d+) pendientes de su fase y (\d+) sin equivalente", tools)
    assert summary and summary.group(2) == "0"
    section = tools.split("## Paridad con PDF24", 1)[1].split("\n## ", 1)[0]
    for row in section.splitlines():
        if "| sin equivalente |" in row:
            assert row.rstrip(" |").split("|")[-1].strip(), row  # cada una con su explicación


def test_f5_video_is_pro_only():
    """7.9: todo el vídeo (conversores y edición) y pptx-a-video piden un plan con vídeo; los subtítulos, no."""
    registry = load_registry()
    video = {"mp4-a-webm", "webm-a-mp4", "mov-a-mp4", "mkv-a-mp4", "avi-a-mp4", "video-a-gif", "gif-a-mp4", "comprimir-video",
             "recortar-video", "rotar-video", "quitar-audio-video", "pptx-a-video"}
    assert {t.slug_es for t in registry.specs if t.needs_video} == video


# ——— F7-Z: formatos 3D de 16.5 (D-259) ———
# Lo que ya prueban otros archivos: STEP → STL estanco (test_cad::test_step_to_stl_with_quality), reparar-stl estanco
# (test_mesh::test_repair_closes_holes_and_cleans) y OpenSCAD sin leer fuera del trabajo
# (test_cad::test_scad_real_openscad_cannot_read_outside, con el OpenSCAD real en la CI).

def _sphere_stl(tmp_path: Path) -> Path:
    import trimesh

    path = tmp_path / "bola.stl"
    trimesh.creation.icosphere(subdivisions=4, radius=20).export(path)
    return path


def test_f7_stl_3mf_stl_keeps_volume_and_triangles(make_ctx, tmp_path):
    import trimesh

    src = _sphere_stl(tmp_path)
    original = trimesh.load(src, force="mesh")
    three = run("stl-a-3mf", make_ctx("stl-a-3mf", [src]))
    back = run("3mf-a-stl", make_ctx("3mf-a-stl", [Path(three[0]["path"])]))
    mesh = trimesh.load(back[0]["path"], force="mesh")
    assert len(mesh.faces) == len(original.faces)
    assert abs(mesh.volume - original.volume) / original.volume < 0.001


def _lib3mf_check(path: Path) -> None:
    import lib3mf

    wrapper = lib3mf.get_wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.SetStrictModeActive(True)
    reader.ReadFromFile(str(path))
    warnings = [reader.GetWarning(k) for k in range(reader.GetWarningCount())]
    assert warnings == [], (path.name, warnings)
    assert model.GetMeshObjects().MoveNext()


@pytest.mark.parametrize("tool,source", [("stl-a-3mf", "stl"), ("obj-a-3mf", "obj"), ("step-a-3mf", "step"), ("svg-a-stl", "svg"),
                                         ("reparar-stl", "3mf")])
def test_f7_lib3mf_validates_every_generated_3mf(make_ctx, tmp_path, tool, source):
    """16.5: lib3mf (en modo estricto) valida los 3MF que generan las conversiones, los generadores y las operaciones."""
    import trimesh

    assert tool in {t.slug_es for t in load_registry().specs}
    if source == "stl":
        src = _sphere_stl(tmp_path)
    elif source == "obj":
        src = tmp_path / "caja.obj"
        trimesh.creation.box((10, 20, 30)).export(src)
    elif source == "step":
        pytest.importorskip("OCP")
        from test_cad import _step

        src = _step(tmp_path)
    elif source == "svg":
        src = tmp_path / "logo.svg"
        src.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="20mm" viewBox="0 0 40 20">'
                       '<rect width="40" height="20"/><circle cx="10" cy="10" r="5" fill="white"/></svg>')
    else:
        three = run("stl-a-3mf", make_ctx("stl-a-3mf", [_sphere_stl(tmp_path)]))
        src = Path(three[0]["path"])
    options = {"formato_salida": "3mf"} if tool in ("svg-a-stl", "reparar-stl") else {}
    out = run(tool, make_ctx(tool, [src], options))
    produced = [Path(o["path"]) for o in out if o["name"].endswith(".3mf")]
    assert produced
    for path in produced:
        _lib3mf_check(path)


def _commands(text: bytes) -> list[bytes]:
    out = []
    for line in text.split(b"\n"):
        line = line.split(b";", 1)[0].strip()
        if line:
            out.append(line)
    return out


@pytest.mark.skipif(not os.environ.get("BGCODE_SAMPLES"), reason="sin muestras reales (la CI clona las de prueba de libbgcode)")
def test_f7_real_prusaslicer_bgcode_roundtrip():
    """16.5: bgcode → gcode → bgcode reproduce el G-code de archivos reales de PrusaSlicer (solo se leen los archivos de
    prueba del repositorio de libbgcode; su código no se usa)."""
    from tools.mesh import gcode as G

    samples = sorted(p for p in Path(os.environ["BGCODE_SAMPLES"]).rglob("*.bgcode") if p.stat().st_size < 64 * 1024 * 1024)
    assert samples, "no hay muestras .bgcode"
    checked = 0
    for path in samples:
        try:
            doc = G.read_bgcode(path.read_bytes())
        except Exception as exc:  # noqa: BLE001 - muestras corruptas a propósito en la batería de libbgcode
            if "corrupt" in path.name.lower() or "invalid" in path.name.lower():
                continue
            raise AssertionError(f"{path.name}: {exc}") from exc
        text = G.join_gcode(doc)
        again = G.read_bgcode(G.write_bgcode(G.split_gcode(text)))
        assert _commands(bytes(again.gcode)) == _commands(bytes(doc.gcode)), path.name
        assert len(again.thumbnails) == len(doc.thumbnails), path.name
        checked += 1
    assert checked
