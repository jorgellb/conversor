"""F6-K (7.13, D-227): latex-a-pdf con Tectonic y Landlock (16.4: `\\input{/etc/hostname}`) y draw.io con su visor."""
from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import urllib.parse
import zipfile
import zlib
from pathlib import Path

import pytest
import respx
from httpx import Response

from core.errors import ToolError
from core.settings import get_settings
from test_media_tools import _gotenberg
from test_tools import make_ctx, run  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[1]
HOST = socket.gethostname()
needs_tectonic = pytest.mark.skipif(not Path(get_settings().TECTONIC_BIN).is_file(), reason="sin Tectonic (infra/tectonic/fetch.sh)")


def _write(tmp_path: Path, name: str, data: str | bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def _pdf_text(path: str) -> str:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(path)
    return "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


# --- LaTeX ------------------------------------------------------------------------------------------------------------


@needs_tectonic
def test_latex_compiles_with_math_and_accents(make_ctx, tmp_path):
    tex = "\\documentclass{article}\\usepackage{amsmath}\\begin{document}Año y canción: $\\sum_{i=1}^{n} i$.\\end{document}\n"
    out = run("latex-a-pdf", make_ctx("latex-a-pdf", [_write(tmp_path, "apuntes.tex", tex)]))
    assert out[0]["name"] == "apuntes.pdf" and "Año y canción" in _pdf_text(out[0]["path"])


@needs_tectonic
def test_latex_cannot_read_server_files(make_ctx, tmp_path):
    """16.4: el .tex no puede leer /etc/hostname (Landlock): no compila y el registro no contiene el archivo."""
    from tools.sandbox import abi

    if abi() < 1:
        pytest.skip("núcleo sin Landlock")
    tex = "\\documentclass{article}\\begin{document}X\\input{/etc/hostname}\\end{document}\n"
    out = run("latex-a-pdf", make_ctx("latex-a-pdf", [_write(tmp_path, "malo.tex", tex)]))
    assert out[0]["name"] == "malo-registro.log" and "No se ha podido compilar" in out[0]["note"]
    assert HOST not in Path(out[0]["path"]).read_text() and HOST not in out[0]["note"]


@needs_tectonic
def test_latex_zip_project_with_image(make_ctx, tmp_path):
    from PIL import Image

    img = tmp_path / "logo.png"
    Image.new("RGB", (40, 20), "red").save(img)
    packed = tmp_path / "tesis.zip"
    with zipfile.ZipFile(packed, "w") as zf:
        zf.writestr("tesis/capitulos/uno.tex", "Capítulo uno.")
        zf.writestr("tesis/main.tex", "\\documentclass{article}\\usepackage{graphicx}\\begin{document}"
                                      "\\input{capitulos/uno}\\includegraphics{img/logo.png}\\end{document}")
        zf.write(img, "tesis/img/logo.png")
    out = run("latex-a-pdf", make_ctx("latex-a-pdf", [packed]))
    assert out[0]["name"] == "tesis.pdf" and "Capítulo uno" in _pdf_text(out[0]["path"]) and "tesis/main.tex" in out[0]["note"]


def test_latex_zip_without_main(make_ctx, tmp_path):
    packed = tmp_path / "x.zip"
    with zipfile.ZipFile(packed, "w") as zf:
        zf.writestr("a.tex", "sin clase")
    if not Path(get_settings().TECTONIC_BIN).is_file():
        pytest.skip("sin Tectonic")
    with pytest.raises(ToolError) as err:
        run("latex-a-pdf", make_ctx("latex-a-pdf", [packed]))
    assert err.value.detail == "latex_no_main"


def test_first_error_hides_server_paths():
    from tools.utils.latex import first_error

    log = "blah\n! LaTeX Error: File `/opt/tectonic/cache/x/foo.sty' not found.\nl.3 \\usepackage{foo}\n"
    assert first_error(log) == "«LaTeX Error: File `foo.sty' not found.» (línea 3)"


# --- draw.io ----------------------------------------------------------------------------------------------------------

DIAGRAM = ('<mxfile><diagram id="a" name="Flujo"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
           '<mxCell id="2" value="Inicio ñ" style="rounded=1;" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>'
           '<mxCell id="3" value="Fin" style="ellipse;" vertex="1" parent="1"><mxGeometry x="400" y="40" width="80" height="80" as="geometry"/></mxCell>'
           '</root></mxGraphModel></diagram></mxfile>')


def _compressed(xml: str, name: str) -> str:
    raw = urllib.parse.quote(xml, safe="").encode()
    deflater = zlib.compressobj(9, zlib.DEFLATED, -15)
    data = base64.b64encode(deflater.compress(raw) + deflater.flush()).decode()
    return f'<diagram id="b" name="{name}">{data}</diagram>'


def test_pages_plain_and_compressed():
    from tools.office.drawio import pages

    model = DIAGRAM.split("<diagram", 1)[1].split(">", 1)[1].rsplit("</diagram>", 1)[0]
    raw = DIAGRAM.replace("</mxfile>", _compressed(model.replace('width="80"', 'width="280"'), "Segunda") + "</mxfile>")
    info = pages(raw.encode())
    assert [name for name, _ in info] == ["Flujo", "Segunda"]
    assert info[0][1] == (440.0, 80.0) and info[1][1] == (640.0, 80.0)
    with pytest.raises(ToolError):
        pages(b'<?xml version="1.0"?><!DOCTYPE m [<!ENTITY x SYSTEM "file:///etc/passwd">]><mxfile>&x;</mxfile>')


@respx.mock
def test_drawio_pdf_and_png_requests(make_ctx, tmp_path, fixtures_dir, monkeypatch):
    viewer = tmp_path / "viewer.js"
    viewer.write_text("/* visor */")
    monkeypatch.setattr(get_settings(), "DRAWIO_VIEWER", viewer)
    pdf_bytes = (fixtures_dir / "texto.pdf").read_bytes()
    chromium = respx.post(_gotenberg("/forms/chromium/convert/html")).mock(return_value=Response(200, content=pdf_bytes))
    shot = respx.post(_gotenberg("/forms/chromium/screenshot/html")).mock(return_value=Response(200, content=b"\x89PNG fake"))
    src = _write(tmp_path, "flujo.drawio", DIAGRAM)
    out = run("drawio-a-pdf", make_ctx("drawio-a-pdf", [src]))
    body = chromium.calls.last.request.content
    assert out[0]["name"] == "flujo.pdf" and b'name="landscape"\r\n\r\ntrue' in body and b"window.ready === true" in body
    assert b'filename="viewer.js"' in body
    out = run("drawio-a-png", make_ctx("drawio-a-png", [src], {"escala": 3, "transparente": True}))
    body = shot.calls.last.request.content
    assert out[0]["name"] == "flujo.png" and b'name="width"\r\n\r\n1380' in body and b'name="omitBackground"\r\n\r\ntrue' in body


def test_drawio_renders_offline_in_chromium(tmp_path):
    """El HTML de la herramienta con el visor real dibuja el diagrama en Chromium sin red (Playwright de las e2e)."""
    viewer = Path(get_settings().DRAWIO_VIEWER)
    if not viewer.is_file():
        viewer = Path.home() / ".cache/conversor-motores/drawio/viewer-static.min.js"
    if not viewer.is_file() or not shutil.which("node") or not (ROOT / "node_modules" / "playwright").exists():
        pytest.skip("sin visor de draw.io o sin Playwright")
    from tools.office.drawio import page_html

    (tmp_path / "index.html").write_bytes(page_html(DIAGRAM, 1, (700, 500), True, False))
    # D-230: si el visor no puede con la página, `window.ready` llega igual y el error sale como excepción (409 en Gotenberg).
    (tmp_path / "roto.html").write_bytes(page_html("<mxfile><diagram>%%%</diagram></mxfile>", 1, (700, 500), True, False))
    shutil.copyfile(viewer, tmp_path / "viewer.js")
    script = tmp_path / "render.cjs"
    script.write_text(
        "const { chromium } = require('playwright');(async () => {"
        "const b = await chromium.launch(process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {});"
        "const p = await b.newPage(); const ext = [], errs = []; p.on('request', r => { if (!r.url().startsWith('file:')) ext.push(r.url()); });"
        "p.on('pageerror', e => errs.push(String(e.message)));"
        "await p.route(/^https?:/, r => r.abort()); await p.goto('file://' + process.argv[2] + '/index.html');"
        "await p.waitForFunction('window.ready === true', null, { timeout: 20000 });"
        "const r = await p.evaluate(() => { const s = document.querySelector('svg'); return [s.getAttribute('width'), s.getAttribute('height'), document.body.innerText]; });"
        "await p.goto('file://' + process.argv[2] + '/roto.html'); await p.waitForFunction('window.ready === true', null, { timeout: 20000 });"
        "await p.waitForTimeout(200); console.log(JSON.stringify({ r, ext, errs })); await b.close(); })();")
    env = {**os.environ, "NODE_PATH": str(ROOT / "node_modules")}
    result = subprocess.run(["node", str(script), str(tmp_path)], capture_output=True, text=True, timeout=120, env=env)
    assert result.returncode == 0 and result.stdout.strip(), result.stderr[-2000:]
    data = json.loads(result.stdout.strip().splitlines()[-1])
    width, height, text = data["r"]
    assert "Inicio ñ" in text and "Fin" in text and data["ext"] == []
    assert len(data["errs"]) == 1 and data["errs"][0].startswith("drawio:")  # solo el del diagrama roto
    assert abs(float(width) - 700) < 1 or abs(float(height) - 500) < 1
