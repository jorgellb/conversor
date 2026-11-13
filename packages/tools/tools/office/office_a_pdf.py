"""word-a-pdf, excel-a-pdf, ppt-a-pdf y el resto de Office a PDF (7.3 y A.8), con la ruta LibreOffice de Gotenberg."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pikepdf

from core.errors import ErrorCode, ToolError
from core.options import parse_page_ranges
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


def select_pages(pdf_path: Path, spec: str, max_pages: int) -> None:
    """Rango de páginas aplicado tras convertir, para admitir «8-» y «impares» (A.0)."""
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        total = len(pdf.pages)
        if total > max_pages:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{total} páginas")
        if spec and spec.strip().lower() not in ("todas", "all"):
            try:
                keep = parse_page_ranges(spec, total)
            except ValueError as exc:
                raise ToolError(ErrorCode.INVALID_OPTIONS, str(exc)) from exc
            new = pikepdf.Pdf.new()
            for i in keep:
                new.pages.append(pdf.pages[i])
            new.save(pdf_path)
            new.close()
            return
        pdf.save(pdf_path)


def convert_office(ctx: ToolContext, path: Path, name: str, ext: str) -> Path:
    o = ctx.options
    if zipfile.is_zipfile(path):
        check_zip(path)
    upload_name = f"documento.{ext}"
    data = gotenberg.libreoffice(ctx.settings.GOTENBERG_URL, path, upload_name, lo_fields(o, ctx.secrets.get("contrasena")))
    dst = ctx.output(derived_name(name, "", "pdf"))
    dst.write_bytes(data)
    select_pages(dst, o.paginas, ctx.plan.pdf_pages)
    return dst


def run(ctx: ToolContext) -> list[dict]:
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        dst = convert_office(ctx, inp.path, inp.name, inp.ext or Path(inp.name).suffix.lstrip("."))
        outputs.append({"path": str(dst), "name": derived_name(inp.name, "", "pdf")})
    return with_batch_zip(ctx, outputs, "documentos-pdf.zip")
