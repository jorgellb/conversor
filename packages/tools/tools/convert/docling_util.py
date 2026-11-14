"""Piezas comunes del lote D2 (A.9): Docling con backend pypdfium2, tablas, números y LibreOffice en `workerconvert`.

El conversor de Docling se guarda por proceso (cargar sus modelos tarda): un worker de Celery lo reutiliza entre
trabajos. El OCR de Docling usa Tesseract por línea de comandos, el mismo motor que ocr-pdf, solo en las zonas sin
texto. LibreOffice pasa el resultado a ODT, ODS, ODP o RTF y hace el modo «fiel» (D-67).
"""
from __future__ import annotations

import math
import re
import shutil
from functools import lru_cache
from pathlib import Path

import pikepdf

from core.errors import ErrorCode, ToolError
from core.options import parse_page_ranges
from tools.base import ToolContext, run_engine
from tools.pdf.common import open_pdf


def subset_pdf(ctx: ToolContext, src: Path, spec: str, n: int) -> tuple[Path, list[int]]:
    """PDF con solo las páginas pedidas y la lista de sus números originales (desde 1)."""
    with open_pdf(src, None, ctx.plan.pdf_pages) as pdf:
        total = len(pdf.pages)
        if not spec or spec.strip().lower() in ("todas", "all"):
            return src, list(range(1, total + 1))
        try:
            keep = parse_page_ranges(spec, total)
        except ValueError as exc:
            raise ToolError(ErrorCode.INVALID_OPTIONS, str(exc)) from exc
        new = pikepdf.Pdf.new()
        for i in keep:
            new.pages.append(pdf.pages[i])
        dst = ctx.work / f"rango-{n}.pdf"
        new.save(dst)
        new.close()
        return dst, [i + 1 for i in keep]


@lru_cache(maxsize=4)
def _converter(ocr: bool, languages: tuple[str, ...], pictures: bool, scale: float):
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = ocr
    if ocr:
        opts.ocr_options = TesseractCliOcrOptions(lang=list(languages))
    opts.do_table_structure = True
    opts.generate_picture_images = pictures
    opts.images_scale = scale
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts, backend=PyPdfiumDocumentBackend)})


def convert(src: Path, ocr: bool, languages: list[str] | None = None, pictures: bool = True, scale: float = 2.0):
    """DoclingDocument del PDF. Cualquier fallo del modelo se da como ENGINE_FAILED, sin detalles internos."""
    from docling.datamodel.base_models import ConversionStatus

    try:
        result = _converter(ocr, tuple(languages or ("spa",)), pictures, scale).convert(str(src), raises_on_error=False)
    except Exception as exc:  # noqa: BLE001 - errores internos de Docling o de sus modelos
        raise ToolError(ErrorCode.ENGINE_FAILED, "Docling") from exc
    if result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
        raise ToolError(ErrorCode.ENGINE_FAILED, f"Docling: {result.status.value}")
    return result.document


@lru_cache(maxsize=2)
def _image_converter(languages: tuple[str, ...]):
    """Docling para imágenes (imagen-a-excel): OCR de toda la página con Tesseract y estructura de tablas."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
    from docling.document_converter import DocumentConverter, ImageFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = True
    opts.ocr_options = TesseractCliOcrOptions(lang=list(languages), force_full_page_ocr=True)
    opts.do_table_structure = True
    opts.generate_picture_images = False
    return DocumentConverter(format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=opts)})


def convert_image(src: Path, languages: list[str]):
    """DoclingDocument de una imagen (PNG o JPEG ya comprobados con el límite de píxeles)."""
    from docling.datamodel.base_models import ConversionStatus

    try:
        result = _image_converter(tuple(languages)).convert(str(src), raises_on_error=False)
    except Exception as exc:  # noqa: BLE001 - errores internos de Docling o de sus modelos
        raise ToolError(ErrorCode.ENGINE_FAILED, "Docling") from exc
    if result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
        raise ToolError(ErrorCode.ENGINE_FAILED, f"Docling: {result.status.value}")
    return result.document


def page_of(item) -> int | None:
    return item.prov[0].page_no if getattr(item, "prov", None) else None


def table_data(table, doc) -> tuple[list[str] | None, list[list[str]]]:
    """Cabecera (o None si la tabla no la tiene) y filas de una tabla de Docling, como texto."""
    df = table.export_to_dataframe(doc=doc)

    def cell(value) -> str:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return ""
        return str(value).strip()

    header = [" ".join(cell(p) for p in col if cell(p)) if isinstance(col, tuple) else cell(col) for col in df.columns]
    rows = [[cell(v) for v in row] for row in df.itertuples(index=False, name=None)]
    if header == [str(i) for i in range(len(header))]:
        return None, rows  # Docling numera las columnas cuando la tabla no tiene cabecera
    return header, rows


def table_rows(table, doc) -> list[list[str]]:
    header, rows = table_data(table, doc)
    return [header, *rows] if header is not None else rows


def libreoffice(ctx: ToolContext, src: Path, target: str, infilter: str | None = None) -> Path:
    """Convierte con LibreOffice local (perfil dentro del trabajo, entorno vacío y sin red)."""
    profile = ctx.work / "lo-perfil"
    outdir = ctx.work / f"lo-{target}-{src.stem}"
    outdir.mkdir(parents=True, exist_ok=True)
    soffice = shutil.which("soffice") or "soffice"
    args = [soffice, f"-env:UserInstallation=file://{profile}", "--headless", "--norestore", "--nologo"]
    if infilter:
        args.append(f"--infilter={infilter}")
    run_engine([*args, "--convert-to", target, "--outdir", str(outdir), str(src)], cwd=ctx.work, timeout=900, mem_mb=3072)
    produced = outdir / f"{src.stem}.{target.split(':')[0]}"
    if not produced.exists():
        raise ToolError(ErrorCode.ENGINE_FAILED, "LibreOffice no produjo el archivo")
    return produced
