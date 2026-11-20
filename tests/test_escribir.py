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
    assert b'data-toc="h-uno">0000</span>' in first["index.html"]
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


@respx.mock
def test_review_d238_linear_parsing_csp_and_bad_inputs(make_ctx, tmp_path, fixtures_dir):
    """D-238: HTML con miles de «<span » o «<body>» se lee en tiempo lineal; la página lleva su CSP; un título con un
    sustituto suelto no rompe nada y un membrete cifrado da su error."""
    import time

    from tools.office.escribir import fill_toc, toc_entries

    t0 = time.monotonic()
    assert toc_entries("<span " * 200_000) == [] and toc_entries('<span class="toc-page" ' * 30_000) == []
    fill_toc("<body>" * 200_000, lambda _k: "1")
    assert time.monotonic() - t0 < 3
    route = respx.post(_gotenberg("/forms/chromium/convert/html")).mock(return_value=Response(200, content=CHROMIUM_PDF.read_bytes()))
    out = run("escribir-pdf", make_ctx("escribir-pdf", [_write(tmp_path, "d.html", "<body>" * 5000 + "<p>x</p>")],
                                       {"titulo": "Informe final", "pie": "pie", "numeros_pagina": "pie", "margenes_mm": 15}))
    parts = _parts(route.calls.last.request)
    assert b"Content-Security-Policy" in parts["index.html"] and b"default-src 'none'" in parts["index.html"]
    assert b"padding:0 15mm" in parts["footer.html"] and out[0]["name"] == "Informe final.pdf"
    # Un sustituto suelto no llega aquí: la validación de las opciones ya lo rechaza (INVALID_OPTIONS en la API).
    from tools.office.specs import EscribirOptions
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EscribirOptions(titulo="mal \ud800")
    encrypted = tmp_path / "membrete.pdf"
    with pikepdf.open(CHROMIUM_PDF) as pdf:
        pdf.save(encrypted, encryption=pikepdf.Encryption(user="secreta", owner="secreta"))
    with pytest.raises(ToolError) as err:
        run("escribir-pdf", make_ctx("escribir-pdf", [_write(tmp_path, "e.html", "<p>x</p>"), encrypted]))
    assert err.value.code == "PASSWORD_REQUIRED"


def test_meta_refresh_and_external_tags_never_reach_chromium():
    """D-246: un <meta http-equiv="refresh"> en el cuerpo (o en cualquier HTML que va a Chromium) navegaría a file:///tmp/
    sin que la CSP lo impida."""
    from tools.office.escribir import BODY_BLOCKED
    from tools.office.gotenberg import no_refresh

    attacks = [b'<meta http-equiv="refresh" content="0;url=file:///tmp/">', b"<META HTTP-EQUIV=Refresh CONTENT='0;url=file:///etc/'>",
               b'<meta content="0;url=file:///" http-equiv="&#114;efresh">', b"<meta http-equiv='\trefresh '>"]
    for attack in attacks:
        assert b"efresh" not in no_refresh(b"<p>hola</p>" + attack).lower().replace(b"&#114;", b"r")
    kept = b'<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'">'
    assert no_refresh(kept) == kept
    body = '<p>x</p><meta http-equiv="refresh" content="0"><base href="file:///"><link rel=stylesheet href=x><iframe src=y></iframe>'
    assert BODY_BLOCKED.sub("", body) == "<p>x</p>"


def test_main_gotenberg_denies_listing_tmp():
    import re
    from pathlib import Path

    import yaml

    doc = yaml.safe_load((Path(__file__).resolve().parents[1] / "docker-compose.coolify.yml").read_text(encoding="utf-8"))
    flag = next(a for a in doc["services"]["gotenberg"]["command"] if a.startswith("--chromium-deny-list="))
    deny = re.compile(flag.split("=", 1)[1])
    assert not deny.match("file:///tmp/1b2c/index.html") and not deny.match("data:image/png;base64,AA")
    for url in ("file:///tmp/", "file:///tmp/1b2c/", "file:///etc/passwd", "file:///srv/files/x"):
        assert deny.match(url), url
