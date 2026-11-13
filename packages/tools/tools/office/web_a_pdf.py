"""web-a-pdf (A.1): Chromium de `gotenbergweb`, que sale solo por `egressweb` (12.2).

Si la URL apunta a un documento convertible (PDF, Office, OpenDocument o imagen), `workeroffice` lo descarga por
`egressweb` con los límites del plan y lo convierte como si se hubiera subido.
"""
from __future__ import annotations

import json
import posixpath
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import httpx
import pikepdf

from core.errors import ErrorCode, ToolError
from core.filetype import detect, normalize_ext
from core.options import check_web_url
from core.zipguard import check_zip
from tools.base import ToolContext, open_image
from tools.office import gotenberg
from tools.office.office_a_pdf import lo_fields, select_pages
from tools.office.specs import OfficeOptions

CONTENT_TYPES = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
    "application/vnd.oasis.opendocument.presentation": "odp",
    "application/vnd.oasis.opendocument.graphics": "odg",
    "application/rtf": "rtf",
    "text/rtf": "rtf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/bmp": "bmp",
    "image/tiff": "tiff",
}
OFFICE = {"doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "odg", "rtf"}
IMAGES = {"jpg", "png", "gif", "webp", "bmp", "tiff"}
DOCUMENTS = OFFICE | IMAGES | {"pdf"}
# Lo que Chromium muestra como página: se captura con la ruta URL.
PAGE_TYPES = {"", "text/html", "application/xhtml+xml", "text/plain", "image/svg+xml"}
MAX_REDIRECTS = 5
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36 ConversorPDF"


def _filename(disposition: str | None, url: str) -> str:
    if disposition:
        m = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", disposition, re.I) or re.search(r'filename\s*=\s*"?([^";]+)"?', disposition, re.I)
        if m:
            return posixpath.basename(unquote(m.group(1)).replace("\\", "/")).strip() or "documento"
    return posixpath.basename(unquote(urlsplit(url).path)) or "documento"


def _page_name(url: str) -> str:
    parts = urlsplit(url)
    path = re.sub(r"[^A-Za-z0-9._-]+", "-", unquote(parts.path).strip("/"))[:60].strip("-.")
    host = (parts.hostname or "web").removeprefix("www.")
    return f"{host}-{path}.pdf" if path else f"{host}.pdf"


def _blocked(resp: httpx.Response) -> bool:
    return bool(resp.headers.get("x-smokescreen-error")) or resp.status_code == 407


@dataclass
class Fetched:
    kind: str  # «pagina» o «documento»
    url: str
    path: Path | None = None
    ext: str = ""
    name: str = ""


def fetch(ctx: ToolContext, url: str) -> Fetched:
    """Abre la URL por `egressweb` y descarga el documento si no es una página."""
    limit = ctx.plan.max_file_bytes
    headers = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8", "Accept-Language": "es,en;q=0.8"}
    current = url
    try:
        with httpx.Client(proxy=ctx.settings.EGRESS_WEB_URL, timeout=httpx.Timeout(30, connect=10), follow_redirects=False,
                          headers=headers) as client:
            for _ in range(MAX_REDIRECTS + 1):
                with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        try:
                            current = check_web_url(urljoin(current, resp.headers.get("location", "")))
                        except ValueError as exc:
                            raise ToolError(ErrorCode.URL_UNREACHABLE, f"Redirección no permitida: {exc}") from exc
                        continue
                    if _blocked(resp):
                        raise ToolError(ErrorCode.URL_UNREACHABLE, "egressweb ha negado la conexión")
                    if resp.status_code >= 400:
                        raise ToolError(ErrorCode.URL_UNREACHABLE, f"La dirección devolvió {resp.status_code}")
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    name = _filename(resp.headers.get("content-disposition"), current)
                    ext = CONTENT_TYPES.get(ctype)
                    if ext is None and ctype in ("application/octet-stream", "binary/octet-stream", "application/download"):
                        guess = normalize_ext(Path(name).suffix.lstrip("."))
                        ext = guess if guess in DOCUMENTS else None
                    if ext is None:
                        if ctype in PAGE_TYPES or ctype.startswith("text/"):
                            return Fetched("pagina", current)
                        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, f"Tipo no convertible: {ctype}")
                    declared = resp.headers.get("content-length", "")
                    if declared.isdigit() and int(declared) > limit:
                        raise ToolError(ErrorCode.FILE_TOO_LARGE, "Documento enlazado demasiado grande")
                    dst = ctx.work / f"enlazado.{ext}"
                    total = 0
                    with open(dst, "wb") as f:
                        for chunk in resp.iter_bytes(1024 * 1024):
                            total += len(chunk)
                            if total > limit:
                                raise ToolError(ErrorCode.FILE_TOO_LARGE, "Documento enlazado demasiado grande")
                            f.write(chunk)
                    return Fetched("documento", current, dst, ext, name)
            raise ToolError(ErrorCode.URL_UNREACHABLE, "Demasiadas redirecciones")
    except httpx.TimeoutException as exc:
        raise ToolError(ErrorCode.URL_UNREACHABLE, "La dirección no respondió a tiempo") from exc
    except httpx.HTTPError as exc:
        # Incluye la negativa de egressweb a abrir el túnel (IP privada, puerto no permitido) y los fallos de DNS.
        raise ToolError(ErrorCode.URL_UNREACHABLE, f"No se pudo conectar: {type(exc).__name__}") from exc


def _document_to_pdf(ctx: ToolContext, path: Path, ext: str, dst: Path) -> None:
    found = detect(path, ext)
    real = found.ext if found else ""
    if real not in DOCUMENTS and not (real in ("zip", "ole2") and ext in OFFICE):
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, f"El documento enlazado no es {ext}")
    if real == "pdf":
        # El PDF enlazado se entrega sin tocar; solo se comprueba el límite de páginas del plan.
        try:
            with pikepdf.open(path) as pdf:
                pages = len(pdf.pages)
        except pikepdf.PasswordError:
            pages = 0
        except pikepdf.PdfError as exc:
            raise ToolError(ErrorCode.CORRUPT_FILE, "PDF enlazado dañado") from exc
        if pages > ctx.plan.pdf_pages:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{pages} páginas")
        shutil.copyfile(path, dst)
        return
    if real in IMAGES:
        import img2pdf

        with open_image(path, ctx.settings.IMAGE_MAX_PIXELS):
            pass
        a4 = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
        layout = img2pdf.get_layout_fun(pagesize=a4, fit=img2pdf.FitMode.into, auto_orient=True)
        if real in ("jpg", "png", "tiff", "gif"):
            dst.write_bytes(img2pdf.convert(path.read_bytes(), layout_fun=layout))
        else:
            from io import BytesIO

            from PIL import Image

            buf = BytesIO()
            with Image.open(path) as img:
                img.convert("RGB").save(buf, format="PNG")
            dst.write_bytes(img2pdf.convert(buf.getvalue(), layout_fun=layout))
        return
    if zipfile.is_zipfile(path):
        check_zip(path)
    data = gotenberg.libreoffice(ctx.settings.GOTENBERG_URL, path, f"documento.{ext}", lo_fields(OfficeOptions(), None))
    dst.write_bytes(data)
    select_pages(dst, "todas", ctx.plan.pdf_pages)


def chromium_fields(o) -> dict[str, str]:
    fields = gotenberg.page_fields(o.papel, o.orientacion, o.margenes_mm, o.imprimir_fondos, o.una_pagina, o.medio)
    fields["waitDelay"] = f"{o.espera_s:g}s"
    scheme = "dark" if o.esquema == "oscuro" else "light"
    fields["emulatedMediaFeatures"] = json.dumps([{"name": "prefers-color-scheme", "value": scheme}])
    return fields


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    ctx.report(0.05, None)
    got = fetch(ctx, o.url)
    ctx.report(0.3, None)
    if got.kind == "documento" and got.path is not None:
        display = f"{Path(got.name).stem or 'documento'}.pdf"
        dst = ctx.output(display)
        _document_to_pdf(ctx, got.path, got.ext, dst)
        return [{"path": str(dst), "name": display}]
    data = gotenberg.chromium_url(ctx.settings.GOTENBERG_WEB_URL, o.url, chromium_fields(o))
    display = _page_name(got.url)
    dst = ctx.output(display)
    dst.write_bytes(data)
    select_pages(dst, "todas", ctx.plan.pdf_pages)
    return [{"path": str(dst), "name": display}]
