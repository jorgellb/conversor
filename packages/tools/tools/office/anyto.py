"""Pasar a PDF cualquier archivo convertible y unir partes con un marcador cada una.

Lo usan los adjuntos de eml-a-pdf y msg-a-pdf y solicitud-de-empleo-pdf (F2). Office va por la ruta LibreOffice de
`gotenberg` (sin red); las imágenes, con img2pdf sin recomprimir los JPEG.
"""
from __future__ import annotations

import contextlib
import io
import zipfile
from pathlib import Path

import img2pdf
import pikepdf

from core.errors import ErrorCode, ToolError
from core.filetype import detect, normalize_ext
from core.zipguard import check_zip
from tools.base import ToolContext, open_image
from tools.office import gotenberg
from tools.office.office_a_pdf import lo_fields
from tools.office.specs import OfficeOptions

IMAGES = {"jpg", "png", "gif", "bmp", "tiff", "webp"}
NATIVE = {"jpg", "png", "tiff", "gif"}
OFFICE = {"doc", "docx", "odt", "rtf", "txt", "xls", "xlsx", "ods", "csv", "ppt", "pptx", "pps", "odp", "odg"}


def image_to_pdf(src: Path, ext: str, dst: Path, max_pixels: int) -> Path:
    """Imagen en una página A4 (encajada); los JPEG, PNG, TIFF y GIF entran sin recomprimir."""
    with open_image(src, max_pixels) as img:
        if ext in NATIVE:
            blob = src.read_bytes()
        else:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            blob = buf.getvalue()
    a4 = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
    dst.write_bytes(img2pdf.convert(blob, layout_fun=img2pdf.get_layout_fun(pagesize=a4, fit=img2pdf.FitMode.into, auto_orient=True)))
    return dst


def to_pdf(ctx: ToolContext, src: Path, name: str, key: str) -> Path | None:
    """PDF del archivo o `None` si no es convertible. `key` hace únicos los archivos intermedios."""
    declared = normalize_ext(Path(name).suffix)
    found = detect(src, declared)
    real = found.ext if found else ""
    if real == "pdf":
        return src
    dst = ctx.work / f"parte-{key}.pdf"
    if real in IMAGES:
        return image_to_pdf(src, real, dst, ctx.settings.IMAGE_MAX_PIXELS)
    office_ext = real if real in OFFICE else declared if (found and found.family in ("ole2", "text", "zip") and declared in OFFICE) else None
    if office_ext is None:
        return None
    if zipfile.is_zipfile(src):
        check_zip(src)
    dst.write_bytes(gotenberg.libreoffice(ctx.settings.GOTENBERG_URL, src, f"documento.{office_ext}", lo_fields(OfficeOptions(), None)))
    return dst


def merge_with_bookmarks(parts: list[tuple[str, Path]], dst: Path, max_pages: int) -> int:
    """Une las partes en orden con un marcador por parte; devuelve el número de páginas."""
    starts: list[tuple[str, int]] = []
    # Las fuentes siguen abiertas hasta guardar: qpdf puede leer sus flujos al escribir el resultado.
    with contextlib.ExitStack() as stack:
        out = stack.enter_context(pikepdf.new())
        for title, path in parts:
            try:
                src = stack.enter_context(pikepdf.open(path))
            except pikepdf.PasswordError as exc:
                raise ToolError(ErrorCode.PASSWORD_REQUIRED, title) from exc
            except pikepdf.PdfError as exc:
                raise ToolError(ErrorCode.CORRUPT_FILE, title) from exc
            starts.append((title, len(out.pages)))
            out.pages.extend(src.pages)
            if len(out.pages) > max_pages:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{len(out.pages)} páginas")
        with out.open_outline() as outline:
            for title, page in starts:
                outline.root.append(pikepdf.OutlineItem(title, page))
        out.save(dst)
        return len(out.pages)
