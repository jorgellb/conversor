"""html-a-pdf, markdown-a-pdf, txt-a-pdf y web-a-pdf (7.3, A.1 y A.8) con Gotenberg simulado (respx)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pikepdf
import pytest
import respx
from httpx import Response
from pydantic import ValidationError

from core.errors import ToolError
from core.settings import get_settings
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida

from helpers import auth


def _route(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"


def _parts(request) -> dict[str, bytes]:
    """Partes del multipart por nombre de campo (o de archivo) para comprobar lo que se envía a Gotenberg."""
    ctype = request.headers["content-type"]
    boundary = ctype.split("boundary=")[1].encode()
    out: dict[str, bytes] = {}
    for chunk in request.content.split(b"--" + boundary):
        if b"\r\n\r\n" not in chunk:
            continue
        head, body = chunk.split(b"\r\n\r\n", 1)
        head_s = head.decode("utf-8", "replace")
        key = head_s.split('filename="')[1].split('"')[0] if 'filename="' in head_s else head_s.split('name="')[1].split('"')[0]
        out[key] = body.rsplit(b"\r\n", 1)[0]
    return out


@pytest.fixture()
def pdf_bytes(fixtures_dir) -> bytes:
    return (fixtures_dir / "texto.pdf").read_bytes()


@respx.mock
def test_html_zip_flattens_assets_and_rewrites_references(make_ctx, tmp_path, pdf_bytes):
    route = respx.post(_route(get_settings().GOTENBERG_URL, "/forms/chromium/convert/html")).mock(return_value=Response(200, content=pdf_bytes))
    site = tmp_path / "sitio.zip"
    with zipfile.ZipFile(site, "w") as zf:
        zf.writestr("web/index.html", '<link href="css/estilo.css" rel="stylesheet"><img src="img/logo.png"><img src="https://cdn.ejemplo.com/x.png">'
                                      '<a href="#arriba">x</a><img src="/img/logo.png?v=2">')
        zf.writestr("web/css/estilo.css", "body{background:url('../img/fondo.png')} @import 'otra.css';")
        zf.writestr("web/css/otra.css", "p{color:red}")
        zf.writestr("web/img/logo.png", b"\x89PNG logo")
        zf.writestr("web/img/fondo.png", b"\x89PNG fondo")
        zf.writestr("__MACOSX/._index.html", b"basura")
    out = run("html-a-pdf", make_ctx("html-a-pdf", [site], {"papel": "A5", "orientacion": "horizontal", "margenes_mm": 5}))
    parts = _parts(route.calls.last.request)
    index = parts["index.html"].decode()
    assert 'href="css__estilo.css"' in index and 'src="img__logo.png"' in index
    assert 'src="https://cdn.ejemplo.com/x.png"' in index and 'href="#arriba"' in index
    assert index.count("img__logo.png") == 2
    css = parts["css__estilo.css"].decode()
    assert "url('img__fondo.png')" in css and "@import 'css__otra.css'" in css
    assert "img__fondo.png" in parts and not any("MACOSX" in k for k in parts)
    assert parts["paperWidth"] == b"148mm" and parts["landscape"] == b"true" and parts["marginTop"] == b"5mm"
    assert out[0]["name"] == "sitio.pdf"
    with pikepdf.open(out[0]["path"]) as pdf:
        assert len(pdf.pages) >= 1


def test_html_zip_without_html_or_with_escaping_paths_is_rejected(make_ctx, tmp_path):
    site = tmp_path / "vacio.zip"
    with zipfile.ZipFile(site, "w") as zf:
        zf.writestr("a.txt", "hola")
    with pytest.raises(ToolError) as err:
        run("html-a-pdf", make_ctx("html-a-pdf", [site]))
    assert err.value.code == "UNSUPPORTED_FORMAT"
    evil = tmp_path / "salida.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("index.html", "<p>x</p>")
        zf.writestr("../fuera.txt", "no")
    with pytest.raises(ToolError) as err:
        run("html-a-pdf", make_ctx("html-a-pdf", [evil]))
    assert err.value.code == "CORRUPT_FILE"


def test_markdown_gfm_rendering():
    from tools.office.chromium_a_pdf import render_markdown

    page = render_markdown("# Título\n\n| a | b |\n|---|---|\n| 1 | ~~2~~ |\n\n- [x] hecho\n- [ ] pendiente\n\n"
                           "```python\ndef hola():\n    return 1\n```\n", "claro", "notas").decode()
    assert "<title>notas</title>" in page and "<table>" in page and "<s>2</s>" in page
    assert 'class="task-list-item"' in page and "checked" in page
    assert '<pre class="highlight"><code><span' in page and ".highlight .k" in page
    sober = render_markdown("texto", "sobrio").decode()
    assert "Noto Serif" in sober


@respx.mock
def test_markdown_a_pdf_sends_html_with_theme_and_paper(make_ctx, tmp_path, pdf_bytes):
    route = respx.post(_route(get_settings().GOTENBERG_URL, "/forms/chromium/convert/html")).mock(return_value=Response(200, content=pdf_bytes))
    md = tmp_path / "léeme.md"
    md.write_text("# Hola\n\nCon **negrita** y acción.\n", encoding="utf-8")
    out = run("markdown-a-pdf", make_ctx("markdown-a-pdf", [md], {"tema": "sobrio", "papel": "Letter"}))
    parts = _parts(route.calls.last.request)
    assert "<strong>negrita</strong>".encode() in parts["index.html"] and "acción".encode() in parts["index.html"]
    assert parts["paperWidth"] == b"215.9mm"
    assert out[0]["name"] == "léeme.pdf"


def test_decode_text_detects_encodings():
    from tools.office.chromium_a_pdf import decode_text

    text = "El año pasado, la señal de acción llegó a Cádiz con 15 € de coste."
    assert decode_text(text.encode("utf-8")) == text
    assert decode_text(text.encode("cp1252")) == text
    assert decode_text(b"\xff\xfe" + text.encode("utf-16-le")) == text


@respx.mock
def test_txt_a_pdf_fonts_margins_and_escaping(make_ctx, tmp_path, pdf_bytes):
    route = respx.post(_route(get_settings().GOTENBERG_URL, "/forms/chromium/convert/html")).mock(return_value=Response(200, content=pdf_bytes))
    txt = tmp_path / "notas.txt"
    txt.write_bytes("Línea con <etiqueta> & acción\n\tsangría".encode("cp1252"))
    run("txt-a-pdf", make_ctx("txt-a-pdf", [txt], {"fuente": "proporcional", "margenes_mm": 15}))
    parts = _parts(route.calls.last.request)
    page = parts["index.html"].decode("utf-8")
    assert "&lt;etiqueta&gt; &amp; acción" in page and "Noto Sans" in page and "Noto Sans Mono" not in page.split("pre{")[1]
    assert parts["marginLeft"] == b"15mm" and parts["paperWidth"] == b"210mm"


def test_txt_too_big(make_ctx, tmp_path, monkeypatch):
    from tools.office import chromium_a_pdf

    monkeypatch.setattr(chromium_a_pdf, "MAX_TEXT_BYTES", 10)
    txt = tmp_path / "grande.txt"
    txt.write_text("x" * 100)
    with pytest.raises(ToolError) as err:
        run("txt-a-pdf", make_ctx("txt-a-pdf", [txt]))
    assert err.value.code == "LIMIT_EXCEEDED"


# --- web-a-pdf ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://10.1.2.3/x", "https://ejemplo.com:8443/", "ftp://ejemplo.com/",
                                 "http://usuario:clave@ejemplo.com/", "http://gotenberg:3000/", "http://apiint/", "http://[::1]/",
                                 "http://169.254.169.254/latest/meta-data/", "http://0x7f.0.0.1/", "https://intranet.local/", ""])
def test_web_url_rejected(url):
    from tools.office.specs import WebAPdfOptions

    with pytest.raises(ValidationError):
        WebAPdfOptions.model_validate({"url": url})


def test_web_url_accepted_and_normalized():
    from tools.office.specs import WebAPdfOptions

    assert WebAPdfOptions.model_validate({"url": "es.wikipedia.org/wiki/PDF"}).url == "https://es.wikipedia.org/wiki/PDF"
    assert WebAPdfOptions.model_validate({"url": "http://ejemplo.com:80/a?b=1#c"}).url == "http://ejemplo.com:80/a?b=1"


@respx.mock
def test_web_page_goes_to_gotenbergweb_with_options(make_ctx, pdf_bytes):
    settings = get_settings()
    respx.get("https://www.ejemplo.com/informe/anual").mock(return_value=Response(200, headers={"content-type": "text/html; charset=utf-8"},
                                                                                  content=b"<html>hola</html>"))
    route = respx.post(_route(settings.GOTENBERG_WEB_URL, "/forms/chromium/convert/url")).mock(return_value=Response(200, content=pdf_bytes))
    ctx = make_ctx("web-a-pdf", [], {"url": "https://www.ejemplo.com/informe/anual", "orientacion": "horizontal", "esquema": "oscuro",
                                     "espera_s": 2.5, "medio": "screen", "una_pagina": True})
    out = run("web-a-pdf", ctx)
    parts = _parts(route.calls.last.request)
    assert parts["url"] == b"https://www.ejemplo.com/informe/anual"
    assert parts["landscape"] == b"true" and parts["waitDelay"] == b"2.5s" and parts["emulatedMediaType"] == b"screen"
    assert parts["singlePage"] == b"true"
    assert json.loads(parts["emulatedMediaFeatures"]) == [{"name": "prefers-color-scheme", "value": "dark"}]
    assert out[0]["name"] == "ejemplo.com-informe-anual.pdf"
    # La página no pasa por el Gotenberg sin red.
    assert not any(c.request.url.host == "gotenberg" for c in respx.calls)


@respx.mock
def test_web_link_to_pdf_is_downloaded_not_rendered(make_ctx, pdf_bytes):
    respx.get("https://docs.ejemplo.com/f/123").mock(return_value=Response(
        200, headers={"content-type": "application/octet-stream", "content-disposition": 'attachment; filename="Memoria 2025.pdf"'},
        content=pdf_bytes))
    web = respx.post(_route(get_settings().GOTENBERG_WEB_URL, "/forms/chromium/convert/url"))
    out = run("web-a-pdf", make_ctx("web-a-pdf", [], {"url": "https://docs.ejemplo.com/f/123"}))
    assert not web.called
    assert out[0]["name"] == "Memoria 2025.pdf"
    assert Path(out[0]["path"]).read_bytes() == pdf_bytes


@respx.mock
def test_web_link_to_docx_goes_to_libreoffice(make_ctx, fixtures_dir, pdf_bytes):
    settings = get_settings()
    docx = fixtures_dir / "carta.docx"
    if not docx.exists():
        pytest.skip("Sin DOCX de prueba")
    respx.get("https://ejemplo.com/carta.docx").mock(return_value=Response(
        200, headers={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}, content=docx.read_bytes()))
    lo = respx.post(_route(settings.GOTENBERG_URL, "/forms/libreoffice/convert")).mock(return_value=Response(200, content=pdf_bytes))
    out = run("web-a-pdf", make_ctx("web-a-pdf", [], {"url": "https://ejemplo.com/carta.docx"}))
    assert lo.called and out[0]["name"] == "carta.pdf"


@respx.mock
def test_web_redirect_to_private_address_is_refused(make_ctx):
    respx.get("https://ejemplo.com/salto").mock(return_value=Response(302, headers={"location": "http://10.0.0.7/admin"}))
    with pytest.raises(ToolError) as err:
        run("web-a-pdf", make_ctx("web-a-pdf", [], {"url": "https://ejemplo.com/salto"}))
    assert err.value.code == "URL_UNREACHABLE"


@respx.mock
def test_web_egress_denial_and_http_errors(make_ctx):
    respx.get("https://ejemplo.com/negado").mock(return_value=Response(503, headers={"x-smokescreen-error": "denied"}))
    respx.get("https://ejemplo.com/no-existe").mock(return_value=Response(404))
    for path in ("negado", "no-existe"):
        with pytest.raises(ToolError) as err:
            run("web-a-pdf", make_ctx("web-a-pdf", [], {"url": f"https://ejemplo.com/{path}"}))
        assert err.value.code == "URL_UNREACHABLE"


@respx.mock
def test_web_linked_document_respects_plan_size(make_ctx):
    respx.get("https://ejemplo.com/enorme.pdf").mock(return_value=Response(
        200, headers={"content-type": "application/pdf", "content-length": str(50 * 1024 ** 3)}, content=b"%PDF-1.7"))
    with pytest.raises(ToolError) as err:
        run("web-a-pdf", make_ctx("web-a-pdf", [], {"url": "https://ejemplo.com/enorme.pdf"}, plan="anon"))
    assert err.value.code == "FILE_TOO_LARGE"


@respx.mock
def test_web_gotenberg_page_error_is_url_unreachable(make_ctx):
    respx.get("https://ejemplo.com/").mock(return_value=Response(200, headers={"content-type": "text/html"}, content=b"<p>x</p>"))
    respx.post(_route(get_settings().GOTENBERG_WEB_URL, "/forms/chromium/convert/url")).mock(
        return_value=Response(409, text="Invalid HTTP status code from the main page: 500"))
    with pytest.raises(ToolError) as err:
        run("web-a-pdf", make_ctx("web-a-pdf", [], {"url": "https://ejemplo.com/"}))
    assert err.value.code == "URL_UNREACHABLE"


def test_api_web_a_pdf_without_uploads(api, anon_token, monkeypatch):
    from app.routers import jobs as jobs_router

    calls = []
    monkeypatch.setitem(jobs_router.ENQUEUE, "fn", lambda job, sealed, spec: calls.append((job.queue, job.options["url"])))
    token = anon_token()
    ok = api.post("/v1/jobs", json={"tool": "web-a-pdf", "options": {"url": "https://www.ejemplo.com/"}}, headers=auth(token))
    assert ok.status_code == 201, ok.text
    assert calls == [("office.light", "https://www.ejemplo.com/")]
    bad = api.post("/v1/jobs", json={"tool": "web-a-pdf", "options": {"url": "http://192.168.1.1/"}}, headers=auth(token))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_OPTIONS"
    files = api.post("/v1/jobs", json={"tool": "comprimir-pdf", "upload_ids": []}, headers=auth(token))
    assert files.status_code == 400
