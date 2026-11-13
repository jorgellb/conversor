"""superponer-pdf (A.3): membrete o capa de fondo o en primer plano con pikepdf (`add_underlay` y `add_overlay`).

El primer archivo es la superposición (PDF, Office o imagen, que se convierte antes) y los demás, los documentos.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import img2pdf
import pikepdf

from core.errors import ErrorCode, ToolError
from core.options import parse_page_ranges
from core.zipguard import check_zip
from tools.base import ToolContext, derived_name, open_image
from tools.office import gotenberg
from tools.office.office_a_pdf import lo_fields
from tools.office.specs import OfficeOptions
from tools.pdf.common import open_pdf, with_batch_zip

IMAGES = {"jpg", "png", "gif", "bmp", "tiff", "webp"}


def overlay_pdf(ctx: ToolContext, path: Path, name: str, ext: str) -> Path:
    if ext == "pdf":
        return path
    dst = ctx.work / "superposicion.pdf"
    if ext in IMAGES:
        with open_image(path, ctx.settings.IMAGE_MAX_PIXELS) as img:
            if ext in ("jpg", "png", "tiff", "gif"):
                blob = path.read_bytes()
            else:
                import io

                buf = io.BytesIO()
                img.convert("RGBA").save(buf, format="PNG")
                blob = buf.getvalue()
        dst.write_bytes(img2pdf.convert(blob))
        return dst
    if zipfile.is_zipfile(path):
        check_zip(path)
    dst.write_bytes(gotenberg.libreoffice(ctx.settings.GOTENBERG_URL, path, f"superposicion.{ext}", lo_fields(OfficeOptions(), None)))
    return dst


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    if len(ctx.inputs) < 2:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "Hacen falta la superposición y al menos un documento")
    first = ctx.inputs[0]
    over_path = overlay_pdf(ctx, first.path, first.name, first.ext or Path(first.name).suffix.lstrip(".").lower())
    outputs = []
    with open_pdf(over_path, None, ctx.plan.pdf_pages) as over:
        if not len(over.pages):
            raise ToolError(ErrorCode.CORRUPT_FILE, "La superposición no tiene páginas")
        for n, inp in enumerate(ctx.inputs[1:]):
            ctx.report(n / (len(ctx.inputs) - 1), None)
            if (inp.ext or Path(inp.name).suffix.lstrip(".").lower()) != "pdf":
                raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, f"{inp.name}: los documentos deben ser PDF")
            name = derived_name(inp.name, "-superpuesto", "pdf")
            dst = ctx.output(name)
            with open_pdf(inp.path, None, ctx.plan.pdf_pages) as pdf:
                total = len(pdf.pages)
                if o.aplicar_a == "primera":
                    targets = [0]
                elif o.aplicar_a == "rango":
                    try:
                        targets = parse_page_ranges(o.rango, total)
                    except ValueError as exc:
                        raise ToolError(ErrorCode.INVALID_OPTIONS, str(exc)) from exc
                else:
                    targets = list(range(total))
                forms: dict[int, pikepdf.Object] = {}
                for k, index in enumerate(targets):
                    src_index = min(k, len(over.pages) - 1) if o.repetir_ultima else k
                    if src_index >= len(over.pages):
                        continue
                    if src_index not in forms:
                        forms[src_index] = pdf.copy_foreign(over.pages[src_index].as_form_xobject())
                    page = pdf.pages[index]
                    if o.escalar:
                        rect = pikepdf.Rectangle(page.trimbox)
                    else:
                        ob = over.pages[src_index].mediabox
                        x0, y0 = float(page.mediabox[0]), float(page.mediabox[1])
                        rect = pikepdf.Rectangle(x0, y0, x0 + float(ob[2]) - float(ob[0]), y0 + float(ob[3]) - float(ob[1]))
                    if o.posicion == "fondo":
                        page.add_underlay(forms[src_index], rect)
                    else:
                        page.add_overlay(forms[src_index], rect)
                pdf.save(dst)
            outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "pdf-superpuestos.zip")
