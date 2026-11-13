"""Parte de servidor de imagenes-a-pdf, jpg-a-pdf y png-a-pdf (A.1): img2pdf, sin recomprimir JPEG.

Se usa con TIFF multipágina y lotes grandes; el resto se hace en el navegador.
"""
from __future__ import annotations

import io
from pathlib import Path

import img2pdf
import pikepdf
from PIL import Image

from core.errors import ErrorCode, ToolError
from core.options import MM_TO_PT, PAPER_MM
from tools.base import ToolContext, derived_name, open_image, zip_files

NATIVE = {"jpg", "png", "tiff", "gif"}


def _page_size(o) -> tuple[float, float] | None:
    if o.tamano_pagina == "segun_imagen":
        return None
    if o.tamano_pagina == "personalizado":
        factor = MM_TO_PT if o.unidad == "mm" else 72.0
        w, h = o.ancho * factor, o.alto * factor
    else:
        w_mm, h_mm = PAPER_MM[o.tamano_pagina]
        w, h = w_mm * MM_TO_PT, h_mm * MM_TO_PT
    if o.orientacion == "horizontal" and w < h:
        w, h = h, w
    if o.orientacion == "vertical" and w > h:
        w, h = h, w
    return (w, h)


def _border(o) -> tuple[float, float]:
    mm = o.margen_personalizado if o.margen == "personalizado" else float(o.margen)
    factor = MM_TO_PT if o.unidad == "mm" else 72.0
    value = mm * (MM_TO_PT if o.margen != "personalizado" else factor)
    return (value, value)


def _layout(o):
    pagesize = _page_size(o)
    if pagesize is None:
        return img2pdf.get_fixed_dpi_layout_fun((o.dpi, o.dpi))
    fit = {"encajar": img2pdf.FitMode.into, "rellenar": img2pdf.FitMode.fill, "tamano_real": img2pdf.FitMode.shrink}[o.ajuste]
    return img2pdf.get_layout_fun(pagesize=pagesize, imgsize=None, border=_border(o), fit=fit, auto_orient=o.orientacion == "auto")


def _image_bytes(path: Path, ext: str, max_pixels: int) -> bytes:
    with open_image(path, max_pixels) as img:
        if ext in NATIVE:
            return path.read_bytes()
        buf = io.BytesIO()
        img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB").save(buf, format="PNG")
        return buf.getvalue()


def _add_bookmarks(pdf_path: Path, names: list[str], pages_per_image: list[int]) -> None:
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        with pdf.open_outline() as outline:
            page = 0
            for name, count in zip(names, pages_per_image):
                outline.root.append(pikepdf.OutlineItem(Path(name).stem, page))
                page += count
        pdf.save(pdf_path)


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    layout = _layout(o)
    blobs = [_image_bytes(i.path, i.ext, ctx.settings.IMAGE_MAX_PIXELS) for i in ctx.inputs]
    try:
        if o.unir:
            name = derived_name(ctx.inputs[0].name if len(ctx.inputs) == 1 else "imagenes", "", "pdf")
            dst = ctx.output(name)
            dst.write_bytes(img2pdf.convert(blobs, layout_fun=layout))
            if o.marcadores:
                counts = [_frames(b) for b in blobs]
                _add_bookmarks(dst, [i.name for i in ctx.inputs], counts)
            return [{"path": str(dst), "name": name}]
        outputs = []
        for inp, blob in zip(ctx.inputs, blobs):
            name = derived_name(inp.name, "", "pdf")
            dst = ctx.output(name)
            dst.write_bytes(img2pdf.convert(blob, layout_fun=layout))
            outputs.append({"path": str(dst), "name": name})
    except (img2pdf.ImageOpenError, img2pdf.PdfTooLargeError, ValueError) as exc:
        raise ToolError(ErrorCode.ENGINE_FAILED, type(exc).__name__) from exc
    if len(outputs) > 1:
        zip_path = ctx.output("imagenes-pdf.zip")
        zip_files([(Path(x["path"]), x["name"]) for x in outputs], zip_path)
        outputs.append({"path": str(zip_path), "name": "imagenes-pdf.zip", "note": "zip"})
    return outputs


def _frames(blob: bytes) -> int:
    with Image.open(io.BytesIO(blob)) as img:  # ya comprobada en _image_bytes
        return getattr(img, "n_frames", 1) if img.format == "TIFF" else 1
