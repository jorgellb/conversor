"""Cliente de Gotenberg (8.x). `gotenberg` no tiene salida a internet (12.2)."""
from __future__ import annotations

import html
import mimetypes
import re
from pathlib import Path

import httpx

from core.errors import ErrorCode, ToolError

# Fuentes de las páginas que imprime el Chromium de Gotenberg (instaladas en su imagen, infra/gotenberg).
SANS = '"Noto Sans", "DejaVu Sans", "Liberation Sans", Arial, sans-serif'


def _post(url: str, files: list[tuple[str, tuple[str | None, bytes | str, str] | tuple[None, str]]], fields: dict[str, str],
          timeout: float, page_error: ErrorCode | None = None, conflict_error: ErrorCode | None = None,
          max_bytes: int | None = None) -> bytes:
    """`max_bytes`: la respuesta se lee por partes y se corta al pasar de ese tamaño (capturas de páginas enormes, D-233)."""
    # Siempre multipart: los campos van como partes sin nombre de archivo.
    parts = list(files) + [(k, (None, v)) for k, v in fields.items()]
    try:
        with httpx.Client(timeout=timeout) as client:
            if max_bytes is None:
                resp = client.post(url, files=parts, headers={"Gotenberg-Trace": "conversor"})
            else:
                with client.stream("POST", url, files=parts, headers={"Gotenberg-Trace": "conversor"}) as streamed:
                    body = bytearray()
                    for chunk in streamed.iter_bytes(1 << 20):
                        body += chunk
                        if len(body) > max_bytes:
                            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Resultado de Gotenberg demasiado grande")
                    resp = httpx.Response(streamed.status_code, headers=streamed.headers, content=bytes(body), request=streamed.request)
    except httpx.TimeoutException as exc:
        raise ToolError(ErrorCode.TIMEOUT, "Gotenberg no respondió a tiempo") from exc
    except httpx.HTTPError as exc:
        raise ToolError(ErrorCode.ENGINE_FAILED, "Gotenberg no disponible", transient=True) from exc
    if resp.status_code in (429, 502, 504):
        raise ToolError(ErrorCode.ENGINE_FAILED, f"Gotenberg ocupado ({resp.status_code})", transient=True)
    if resp.status_code == 503:
        # Gotenberg responde 503 cuando la conversión supera su tiempo; con una URL suele ser la página, no el motor.
        if page_error is not None:
            raise ToolError(ErrorCode.TIMEOUT, "La página tardó demasiado en cargar")
        raise ToolError(ErrorCode.ENGINE_FAILED, "Gotenberg ocupado (503)", transient=True)
    if resp.status_code == 409 and conflict_error is not None:
        # failOnConsoleExceptions: la página ha fallado al dibujar (no es un fallo pasajero del motor).
        raise ToolError(conflict_error, "La página falló al dibujarse")
    if resp.status_code == 400 and "password" in resp.text.lower():
        raise ToolError(ErrorCode.WRONG_PASSWORD)
    if page_error is not None and resp.status_code in (400, 403, 404, 409, 500):
        # Página que no existe, devuelve error o la niega egressweb (12.2).
        raise ToolError(page_error, f"Gotenberg devolvió {resp.status_code}: {resp.text[:200]}")
    if resp.status_code >= 400:
        raise ToolError(ErrorCode.ENGINE_FAILED, f"Gotenberg devolvió {resp.status_code}")
    return resp.content


def libreoffice(base_url: str, path: Path, upload_name: str, fields: dict[str, str], timeout: float = 600) -> bytes:
    mime = mimetypes.guess_type(upload_name)[0] or "application/octet-stream"
    files = [("files", (upload_name, path.read_bytes(), mime))]
    return _post(f"{base_url.rstrip('/')}/forms/libreoffice/convert", files, fields, timeout)


META = re.compile(rb"<meta\b[^>]*>", re.I)
HTTP_EQUIV = re.compile(rb"""http-equiv\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)


def no_refresh(data: bytes) -> bytes:
    """Sin `<meta http-equiv="refresh">`, escrito como sea (entidades, mayúsculas, sin comillas): la CSP no frena una
    navegación y Chromium podría ir a `file:///tmp/` e imprimir archivos de otros trabajos (D-246)."""

    def keep(m: re.Match) -> bytes:
        eq = HTTP_EQUIV.search(m.group(0))
        if eq is None:
            return m.group(0)
        value = next(g for g in eq.groups() if g is not None).decode("latin-1")
        return b"" if html.unescape(value).strip().lower() == "refresh" else m.group(0)

    return META.sub(keep, data)


def _html_part(name: str, data: bytes | str, mime: str) -> tuple[str, bytes | str, str]:
    if mime.startswith("text/html") or name.lower().endswith((".html", ".htm")):
        data = no_refresh(data.encode("utf-8") if isinstance(data, str) else data)
    return name, data, mime


def chromium_html(base_url: str, html_path: Path, fields: dict[str, str], timeout: float = 300) -> bytes:
    files = [("files", _html_part("index.html", html_path.read_bytes(), "text/html"))]
    return _post(f"{base_url.rstrip('/')}/forms/chromium/convert/html", files, fields, timeout)


def chromium_html_files(base_url: str, files: list[tuple[str, bytes, str]], fields: dict[str, str], timeout: float = 300,
                        conflict_error: ErrorCode | None = None) -> bytes:
    """`index.html` y sus recursos, todos en el mismo nivel (Gotenberg no conserva carpetas)."""
    parts = [("files", _html_part(name, data, mime)) for name, data, mime in files]
    return _post(f"{base_url.rstrip('/')}/forms/chromium/convert/html", parts, fields, timeout, conflict_error=conflict_error)


def chromium_screenshot_files(base_url: str, files: list[tuple[str, bytes, str]], fields: dict[str, str], timeout: float = 300,
                              conflict_error: ErrorCode | None = None) -> bytes:
    """Captura de `index.html` y sus recursos (ruta de capturas de Gotenberg 8: width, height, clip y format)."""
    parts = [("files", _html_part(name, data, mime)) for name, data, mime in files]
    return _post(f"{base_url.rstrip('/')}/forms/chromium/screenshot/html", parts, fields, timeout, conflict_error=conflict_error)


def chromium_url(base_url: str, url: str, fields: dict[str, str], timeout: float = 180) -> bytes:
    """Ruta URL de Chromium. Solo para `gotenbergweb`, que sale por `egressweb` (12.2)."""
    return _post(f"{base_url.rstrip('/')}/forms/chromium/convert/url", [], {**fields, "url": url}, timeout,
                 page_error=ErrorCode.URL_UNREACHABLE)


PAPER_MM = {"A3": (297, 420), "A4": (210, 297), "A5": (148, 210), "Letter": (215.9, 279.4), "Legal": (215.9, 355.6)}


def page_fields(papel: str = "A4", orientacion: str = "vertical", margen_mm: float = 10, fondos: bool = True,
                una_pagina: bool = False, medio: str = "print", tamano_css: bool = False) -> dict[str, str]:
    """Campos de página de la ruta Chromium de Gotenberg 8 (admite unidades como «10mm»)."""
    w, h = PAPER_MM.get(papel, PAPER_MM["A4"])
    m = f"{margen_mm:g}mm"
    return {
        "paperWidth": f"{w:g}mm", "paperHeight": f"{h:g}mm", "landscape": str(orientacion == "horizontal").lower(),
        "marginTop": m, "marginBottom": m, "marginLeft": m, "marginRight": m,
        "printBackground": str(fondos).lower(), "singlePage": str(una_pagina).lower(),
        "emulatedMediaType": medio, "preferCssPageSize": str(tamano_css).lower(),
    }
