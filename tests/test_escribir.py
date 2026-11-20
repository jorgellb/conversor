"""escribir-pdf (A.1, F6-O1, D-234): HTML del editor a PDF con Gotenberg, índice en dos pasadas con los destinos que
crea Chromium, encabezado y pie, marca de agua, borde, membrete y propiedades. Gotenberg se simula con un PDF que generó
Chromium (tests/fixtures/escribir-indice.pdf: los títulos h-uno y h-dos en las páginas 1 y 2, y un campo)."""
from __future__ import annotations

import re
from pathlib import Path

import pikepdf
import pytest
import respx
from httpx import Response

from core.errors import ToolError
from test_media_tools import _gotenberg
from test_tools import make_ctx, run  # noqa: F401  (fixture)

CHROMIUM_PDF = Path(__file__).parent / "fixtures" / "escribir-indice.pdf"
BODY = ('<nav class="indice"><h2>Índice</h2><ol><li data-nivel="1"><a href="#h-uno">Uno</a><span class="toc-dots"></span>'
        '<span class="toc-page" data-toc="h-uno"></span></li><li data-nivel="2"><a href="#h-dos">Dos</a><span class="toc-dots"></span>'
        '<span class="toc-page" data-toc="h-dos"></span></li></ol></nav><h1 id="h-uno">Uno</h1><p>Año</p><h2 id="h-dos">Dos</h2>')


def _write(tmp_path: Path, name: str, data: str | bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def _parts(request) -> dict[str, bytes]:
    body = request.content
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    out = {}
    for part in body.split(b"--" + boundary):
        m = re.search(rb'name="([^"]+)"(?:; filename="([^"]+)")?\r\n(?:Content-Type: [^\r]+\r\n)?\r\n(.*)\r\n$', part, re.S)
        if m:
            out[(m.group(2) or m.group(1)).decode()] = m.group(3)
    return out


@respx.mock
def test_two_passes_fill_the_table_of_contents(make_ctx, tmp_path, fixtures_dir):
    pdf = CHROMIUM_PDF.read_bytes()
    route = respx.post(_gotenberg("/forms/chromium/convert/html")).mock(return_value=Response(200, content=pdf))
    options = {"titulo": "Informe anual", "autor": "Ana", "asunto": "Cuentas", "palabras_clave": "informe, 2026", "encabezado": "Empresa S.L.",
               "pie": "Confidencial", "numeros_pagina": "pie", "marca_agua": "BORRADOR", "borde": "doble"}
    out = run("escribir-pdf", make_ctx("escribir-pdf", [_write(tmp_path, "documento.html", BODY)], options))
    assert route.call_count == 2 and out[0]["name"] == "Informe anual.pdf" and out[0]["note"] is None
    first, second = (_parts(c.request) for c in route.calls)
    assert b'data-toc="h-uno">000</span>' in first["index.html"]
    assert b'data-toc="h-uno">1</span>' in second["index.html"] and b'data-toc="h-dos">2</span>' in second["index.html"]
    page = second["index.html"]
    assert b'lang="es"' in page and b"BORRADOR" in page and b"borde-pagina doble" in page and b"<title>Informe anual</title>" in page
    assert b'class="pageNumber"' in second["footer.html"] and b"Confidencial" in second["footer.html"] and b"Empresa S.L." in second["header.html"]
    assert second["generateDocumentOutline"] == b"true" and second["generateTaggedPdf"] == b"true" and second["marginBottom"] == b"25mm"
    with pikepdf.open(out[0]["path"]) as doc:
        assert str(doc.docinfo["/Title"]) == "Informe anual" and str(doc.docinfo["/Author"]) == "Ana"
        assert str(doc.docinfo["/Keywords"]) == "informe, 2026" and str(doc.Root.Lang) == "es"
        with doc.open_metadata() as meta:
            assert meta["dc:title"] == "Informe anual"


@respx.mock
def test_without_toc_one_pass_and_letterhead(make_ctx, tmp_path, fixtures_dir):
    pdf = CHROMIUM_PDF.read_bytes()
    route = respx.post(_gotenberg("/forms/chromium/convert/html")).mock(return_value=Response(200, content=pdf))
    letterhead = fixtures_dir / "texto.pdf"
    out = run("escribir-pdf", make_ctx("escribir-pdf", [_write(tmp_path, "d.html", "<p>Hola</p>"), letterhead],
                                       {"numeros_pagina": "ninguno", "membrete": "primera", "margenes_mm": 10}))
    assert route.call_count == 1
    parts = _parts(route.calls.last.request)
    assert "footer.html" not in parts and "header.html" not in parts and parts["marginTop"] == b"10mm"
    with pikepdf.open(out[0]["path"]) as doc:
        with pikepdf.open(CHROMIUM_PDF) as original:
            before = [len(p.Resources.get("/XObject", {})) for p in original.pages]
        after = [len(p.Resources.get("/XObject", {})) for p in doc.pages]
        # El membrete va debajo como un XObject más, solo en la primera página.
        assert after[0] == before[0] + 1 and after[1:] == before[1:]
    assert out[0]["name"] == "documento.pdf"


@respx.mock
def test_missing_destination_is_noted(make_ctx, tmp_path, fixtures_dir):
    pdf = CHROMIUM_PDF.read_bytes()
    respx.post(_gotenberg("/forms/chromium/convert/html")).mock(return_value=Response(200, content=pdf))
    body = BODY.replace("h-dos", "h-tres")
    out = run("escribir-pdf", make_ctx("escribir-pdf", [_write(tmp_path, "d.html", body)]))
    assert "índice no tienen número" in out[0]["note"]


def test_inputs_are_checked(make_ctx, tmp_path, fixtures_dir):
    with pytest.raises(ToolError):
        run("escribir-pdf", make_ctx("escribir-pdf", [fixtures_dir / "texto.pdf"]))
