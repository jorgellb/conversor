"""word-a-pdf, excel-a-pdf, ppt-a-pdf y el resto de Office a PDF (7.3 y A.8), con la ruta LibreOffice de Gotenberg."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pikepdf

from core.errors import ErrorCode, ToolError
from core.options import RANGE_RE, parse_page_ranges
from core.zipguard import check_zip
from tools.base import ToolContext, derived_name
from tools.office import gotenberg
from tools.pdf.common import with_batch_zip


def lo_fields(o, password: str | None) -> dict[str, str]:
    fields = {
        "exportBookmarks": str(o.marcadores).lower(),
        "exportFormFields": str(o.campos_formulario).lower(),
        "quality": str(o.calidad_imagenes),
        "reduceImageResolution": "true",
        "maxImageResolution": str(o.resolucion_maxima),
        "singlePageSheets": str(o.hoja_una_pagina).lower(),
        "exportHiddenSlides": str(o.diapositivas_ocultas).lower(),
        "exportNotesPages": str(o.paginas_notas).lower(),
        "exportNotesInMargin": str(o.comentarios_margen).lower(),
    }
    if o.formato == "pdfa":
        fields["pdfa"] = "PDF/A-2b"
    elif o.formato == "pdfua":
        fields["pdfua"] = "true"
        fields["generateTaggedPdf"] = "true"
    if password:
        fields["password"] = password
    return fields


def _all(spec: str) -> bool:
    return not spec or spec.strip().lower() in ("todas", "all")


def select_pages(pdf_path: Path, spec: str, max_pages: int) -> None:
    """Rango de páginas aplicado tras convertir, para admitir «8-» y «impares» (A.0). Copia las páginas a un PDF nuevo:
    solo vale para PDF normal, porque pierde la estructura etiquetada y los metadatos (PDF/A y PDF/UA usan `native_range`)."""
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        total = len(pdf.pages)
        if total > max_pages:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{total} páginas")
        if not _all(spec):
            keep = _parse(spec, total)
            new = pikepdf.Pdf.new()
            for i in keep:
                new.pages.append(pdf.pages[i])
            new.save(pdf_path)
            new.close()
            return
        pdf.save(pdf_path)


def _parse(spec: str, total: int) -> list[int]:
    try:
        return parse_page_ranges(spec, total)
    except ValueError as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, str(exc)) from exc


def native_range(spec: str, total: int) -> str | None:
    """Rango de A.0 resuelto contra el total de páginas y escrito como `PageRange` de LibreOffice («1-3,5,8-10»), en el
    orden del documento. None si son todas."""
    keep = sorted(set(_parse(spec, total)))
    if len(keep) == total:
        return None
    runs: list[list[int]] = []
    for i in keep:
        if runs and i == runs[-1][1] + 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    return ",".join(f"{a + 1}" if a == b else f"{a + 1}-{b + 1}" for a, b in runs)


def check_native_spec(spec: str) -> None:
    """Antes de convertir con un rango que aplicará el motor (PDF/A y PDF/UA): sintaxis de A.0 y orden creciente, porque
    LibreOffice y Chromium sacan las páginas en el orden del documento y no se pueden reordenar sin perder las
    etiquetas. Así un rango mal escrito no gasta una conversión."""
    s = (spec or "").strip().lower()
    if not s or s in ("todas", "all", "impares", "odd", "pares", "even"):
        return
    last = 0
    for part in s.split(","):
        if not part.strip():
            continue
        m = RANGE_RE.match(part)
        if not m or (m.group(1) is None and m.group(3) is None):
            raise ToolError(ErrorCode.INVALID_OPTIONS, f"Rango no válido: {part.strip()}")
        start_s, dash, end_s = m.groups()
        start = int(start_s) if start_s else 1
        end = int(end_s) if end_s else (None if dash else start)
        if start < 1 or (end is not None and end < start):
            raise ToolError(ErrorCode.INVALID_OPTIONS, f"Rango no válido: {part.strip()}")
        if start <= last:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "range_order")
        last = end if end is not None else float("inf")


def page_count(pdf_path: Path, max_pages: int) -> int:
    try:
        with pikepdf.open(pdf_path) as pdf:
            total = len(pdf.pages)
    except pikepdf.PdfError as exc:
        raise ToolError(ErrorCode.ENGINE_FAILED, "el motor devolvió un PDF ilegible") from exc
    if total > max_pages:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{total} páginas")
    return total


def libreoffice_pdf(ctx: ToolContext, path: Path, ext: str, fields: dict[str, str], spec: str, dst: Path,
                    keep_structure: bool) -> Path:
    """Convierte con Gotenberg y aplica el rango. Con `keep_structure` (PDF/A y PDF/UA), el rango lo aplica LibreOffice
    en una segunda conversión (`nativePageRanges`), para no perder las etiquetas ni los metadatos de la norma."""
    if keep_structure:
        check_native_spec(spec)
    if zipfile.is_zipfile(path):
        check_zip(path)
    upload_name = f"documento.{ext}"
    dst.write_bytes(gotenberg.libreoffice(ctx.settings.GOTENBERG_URL, path, upload_name, fields))
    if not keep_structure:
        select_pages(dst, spec, ctx.plan.pdf_pages)
        return dst
    total = page_count(dst, ctx.plan.pdf_pages)
    if not _all(spec):
        ranges = native_range(spec, total)
        if ranges:
            dst.write_bytes(gotenberg.libreoffice(ctx.settings.GOTENBERG_URL, path, upload_name, {**fields, "nativePageRanges": ranges}))
    return dst


def convert_office(ctx: ToolContext, path: Path, name: str, ext: str) -> Path:
    o = ctx.options
    if o.formato != "pdf" and not _all(o.paginas) and (o.paginas_notas or o.diapositivas_ocultas):
        # LibreOffice aplica `PageRange` a las diapositivas y no a las páginas del PDF (las notas y las ocultas cambian
        # la cuenta), y con PDF/A o PDF/UA el rango no se puede aplicar después sin perder la norma.
        raise ToolError(ErrorCode.INVALID_OPTIONS, "range_slides")
    dst = ctx.output(derived_name(name, "", "pdf"))
    return libreoffice_pdf(ctx, path, ext, lo_fields(o, ctx.secrets.get("contrasena")), o.paginas, dst,
                           keep_structure=o.formato != "pdf")


def run(ctx: ToolContext) -> list[dict]:
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        dst = convert_office(ctx, inp.path, inp.name, inp.ext or Path(inp.name).suffix.lstrip("."))
        outputs.append({"path": str(dst), "name": derived_name(inp.name, "", "pdf")})
    return with_batch_zip(ctx, outputs, "documentos-pdf.zip")
