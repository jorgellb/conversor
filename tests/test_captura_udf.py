"""F6-M (D-229): captura-web por gotenbergweb (URL comprobada en la API, 16.4) y udf-a-pdf, apagada por defecto."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import respx
from httpx import Response

from core.errors import ToolError
from core.settings import get_settings
from test_media_tools import _gotenberg
from test_tools import make_ctx, run  # noqa: F401  (fixture)


@respx.mock
def test_screenshot_fields_and_name(make_ctx):
    url = f"{get_settings().GOTENBERG_WEB_URL.rstrip('/')}/forms/chromium/screenshot/url"
    route = respx.post(url).mock(return_value=Response(200, content=b"\x89PNG\r\n\x1a\nfalso"))
    out = run("captura-web", make_ctx("captura-web", [], {"url": "https://www.example.com/docs/guia", "ancho": 375}))
    body = route.calls.last.request.content
    assert out[0]["name"] == "example.com-docs-guia.png"
    assert b'name="width"\r\n\r\n375' in body and b'name="clip"\r\n\r\nfalse' in body and b"https://www.example.com/docs/guia" in body


@respx.mock
def test_screenshot_errors(make_ctx):
    url = f"{get_settings().GOTENBERG_WEB_URL.rstrip('/')}/forms/chromium/screenshot/url"
    respx.post(url).mock(return_value=Response(500, text="net::ERR_TUNNEL_CONNECTION_FAILED"))
    with pytest.raises(ToolError) as err:
        run("captura-web", make_ctx("captura-web", [], {"url": "https://example.com/"}))
    assert err.value.code == "URL_UNREACHABLE"


@pytest.mark.parametrize("url", ["http://169.254.169.254/latest/meta-data", "http://localhost/", "http://10.0.0.5/",
                                 "ftp://example.com/", "https://example.com:8443/", "http://gotenberg:3000/"])
def test_screenshot_url_is_checked(url):
    from core.registry import load_registry

    spec = load_registry().require("captura-web")
    with pytest.raises(Exception):
        spec.options.model_validate({"url": url})


def _udf(tmp_path: Path) -> Path:
    text = "Sayın Mahkeme\nDava dilekçesi ğüşıöç\nCelda"
    content = (f'<?xml version="1.0" encoding="UTF-8"?><template format_id="1.8"><content><![CDATA[{text}]]></content>'
               '<elements resolver="hvl-default">'
               '<paragraph Alignment="1"><content startOffset="0" length="13" bold="true" size="14"/></paragraph>'
               '<paragraph Alignment="3"><content startOffset="14" length="21"/></paragraph>'
               '<table><row><cell><paragraph><content startOffset="36" length="5" italic="true"/></paragraph></cell></row></table>'
               '</elements></template>')
    path = tmp_path / "dilekce.udf"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("content.xml", content)
    return path


@respx.mock
def test_udf_to_html_and_pdf(make_ctx, tmp_path, fixtures_dir):
    from tools.office.udf import to_html

    page = to_html(_udf(tmp_path)).decode()
    assert "<span style=\"font-size:14pt;font-weight:bold\">Sayın Mahkeme</span>" in page and "text-align:center" in page
    assert "ğüşıöç" in page and "<td><p" in page and "font-style:italic\">Celda" in page
    chromium = respx.post(_gotenberg("/forms/chromium/convert/html")).mock(
        return_value=Response(200, content=(fixtures_dir / "texto.pdf").read_bytes()))
    out = run("udf-a-pdf", make_ctx("udf-a-pdf", [_udf(tmp_path)]))
    assert out[0]["name"] == "dilekce.pdf" and chromium.called


def test_udf_errors_and_off_by_default(make_ctx, tmp_path):
    from core.registry import load_registry

    assert not load_registry().require("udf-a-pdf").default_enabled
    bad = tmp_path / "x.udf"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("otro.xml", "<a/>")
    with pytest.raises(ToolError) as err:
        run("udf-a-pdf", make_ctx("udf-a-pdf", [bad]))
    assert err.value.detail == "udf_no_content"
