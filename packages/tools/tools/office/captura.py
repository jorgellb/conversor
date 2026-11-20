"""captura-web (7.13, F6-M, D-229): URL a PNG o JPG con el Chromium de `gotenbergweb`, que sale solo por `egressweb`.

La URL ya llega comprobada por la API (12.2: http o https, puerto 80 o 443, servidor público); `egressweb` (Smokescreen)
niega además las IP privadas, también tras una redirección (16.4). La captura es la página entera o solo lo visible.
"""
from __future__ import annotations

import json
import re
from urllib.parse import unquote, urlsplit

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext
from tools.office import gotenberg

MAX_BYTES = 60 * 1024 * 1024


def _name(url: str, ext: str) -> str:
    parts = urlsplit(url)
    path = re.sub(r"[^A-Za-z0-9._-]+", "-", unquote(parts.path).strip("/"))[:60].strip("-.")
    host = (parts.hostname or "web").removeprefix("www.")
    return f"{host}-{path}.{ext}" if path else f"{host}.{ext}"


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    ctx.report(0.1, None)
    fields = {"width": str(o.ancho), "height": str(o.alto), "clip": str(not o.pagina_completa).lower(),
              "format": "png" if o.formato == "png" else "jpeg", "waitDelay": f"{round(o.espera_s * 1000)}ms",
              "emulatedMediaFeatures": json.dumps([{"name": "prefers-color-scheme", "value": "dark" if o.esquema == "oscuro" else "light"}])}
    if o.formato == "jpg":
        fields["quality"] = str(o.calidad)
    files: list = []
    data = gotenberg._post(f"{ctx.settings.GOTENBERG_WEB_URL.rstrip('/')}/forms/chromium/screenshot/url", files,
                           {**fields, "url": o.url}, 180, page_error=ErrorCode.URL_UNREACHABLE, max_bytes=MAX_BYTES)
    if len(data) > MAX_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Captura de más de 60 MB")
    if not (data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8")):
        raise ToolError(ErrorCode.ENGINE_FAILED, "Gotenberg no devolvió una imagen")
    ext = "png" if o.formato == "png" else "jpg"
    name = _name(o.url, ext)
    dst = ctx.output(name)
    dst.write_bytes(data)
    return [{"path": str(dst), "name": name, "note": None}]
