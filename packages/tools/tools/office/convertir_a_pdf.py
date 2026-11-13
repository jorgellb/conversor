"""convertir-a-pdf (7.3): elige el motor según el tipo real de cada archivo."""
from __future__ import annotations

import io
from pathlib import Path

import img2pdf
from PIL import Image

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name, open_image
from tools.office import gotenberg
from tools.office.office_a_pdf import convert_office, select_pages
from tools.pdf.common import with_batch_zip

IMAGES = {"jpg", "png", "gif", "bmp", "tiff", "webp"}
NATIVE = {"jpg", "png", "tiff", "gif"}


def _image(ctx: ToolContext, path: Path, name: str, ext: str) -> Path:
    with open_image(path, ctx.settings.IMAGE_MAX_PIXELS) as img:
        if ext in NATIVE:
            blob = path.read_bytes()
        else:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            blob = buf.getvalue()
    dst = ctx.output(derived_name(name, "", "pdf"))
    a4 = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
    dst.write_bytes(img2pdf.convert(blob, layout_fun=img2pdf.get_layout_fun(pagesize=a4, fit=img2pdf.FitMode.into, auto_orient=True)))
    select_pages(dst, ctx.options.paginas, ctx.plan.pdf_pages)
    return dst


def _html(ctx: ToolContext, path: Path, name: str) -> Path:
    o = ctx.options
    fields = {"printBackground": "true", "paperWidth": "8.27", "paperHeight": "11.7", "skipNetworkIdleEvent": "true"}
    if o.formato == "pdfa":
        fields["pdfa"] = "PDF/A-2b"
    elif o.formato == "pdfua":
        fields["pdfua"] = "true"
        fields["generateTaggedPdf"] = "true"
    data = gotenberg.chromium_html(ctx.settings.GOTENBERG_URL, path, fields)
    dst = ctx.output(derived_name(name, "", "pdf"))
    dst.write_bytes(data)
    select_pages(dst, o.paginas, ctx.plan.pdf_pages)
    return dst


def run(ctx: ToolContext) -> list[dict]:
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        ext = inp.ext or Path(inp.name).suffix.lstrip(".").lower()
        if ext in IMAGES:
            dst = _image(ctx, inp.path, inp.name, ext)
        elif ext == "html":
            dst = _html(ctx, inp.path, inp.name)
        else:
            dst = convert_office(ctx, inp.path, inp.name, Path(inp.name).suffix.lstrip(".").lower() or ext)
        outputs.append({"path": str(dst), "name": derived_name(inp.name, "", "pdf")})
    return with_batch_zip(ctx, outputs, "convertidos-pdf.zip")
