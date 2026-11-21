"""dxf-a-pdf (7.3): ezdxf con su backend SVG y el Chromium de `gotenberg` para pasar a PDF.

Nunca el backend PyMuPDF ni el extra `ezdxf[draw]`, que instalan PyMuPDF (AGPL, 11).
"""
from __future__ import annotations

from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.office import gotenberg
from tools.office.office_a_pdf import select_pages
from tools.pdf.common import with_batch_zip

PAPER_MM = {"A4": (210, 297), "A3": (297, 420), "A2": (420, 594), "A1": (594, 841), "A0": (841, 1189)}


def dxf_to_svg(path: Path, papel: str, orientacion: str, monocromo: bool, margen_mm: float) -> tuple[str, float, float]:
    import ezdxf
    from ezdxf import recover
    from ezdxf.addons.drawing import Frontend, RenderContext, config, layout, svg

    try:
        doc, auditor = recover.readfile(str(path))
    except (OSError, ezdxf.DXFStructureError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "DXF ilegible") from exc
    if auditor.has_errors:
        raise ToolError(ErrorCode.CORRUPT_FILE, "DXF con errores que no se pueden recuperar")
    from ezdxf import bbox as ebbox

    extents = ebbox.extents(doc.modelspace(), fast=True)
    if not extents.has_data:
        raise ToolError(ErrorCode.CORRUPT_FILE, "El plano no tiene nada que dibujar en el espacio modelo")
    wide = bool(extents.size.x >= extents.size.y)
    backend = svg.SVGBackend()
    cfg = config.Configuration(background_policy=config.BackgroundPolicy.WHITE,
                               color_policy=config.ColorPolicy.BLACK if monocromo else config.ColorPolicy.COLOR)
    Frontend(RenderContext(doc), backend, config=cfg).draw_layout(doc.modelspace(), finalize=True)
    w, h = PAPER_MM.get(papel, PAPER_MM["A4"])
    if orientacion == "horizontal" or (orientacion == "auto" and wide):
        w, h = h, w
    page = layout.Page(w, h, layout.Units.mm, margins=layout.Margins.all(margen_mm))
    try:
        return backend.get_string(page, settings=layout.Settings(fit_page=True)), w, h
    except ValueError as exc:  # entidades sin geometría útil
        raise ToolError(ErrorCode.CORRUPT_FILE, "El plano no tiene nada que dibujar") from exc


def dxf_pdf(ctx: ToolContext, path: Path, dst: Path, o) -> None:
    """El plano DXF en un PDF de una página (también lo usa dwg-a-pdf, F7-E)."""
    svg_text, w, h = dxf_to_svg(path, o.papel, o.orientacion, o.monocromo, o.margenes_mm)
    page = (f"<!doctype html><html><head><meta charset=\"utf-8\"><style>@page{{size:{w}mm {h}mm;margin:0}}"
            f"html,body{{margin:0}}svg{{display:block;width:{w}mm;height:{h}mm}}</style></head><body>{svg_text.split('?>', 1)[-1]}</body></html>")
    fields = gotenberg.page_fields("A4", "vertical", 0, True, False, "print", tamano_css=True)
    dst.write_bytes(gotenberg.chromium_html_files(ctx.settings.GOTENBERG_URL, [("index.html", page.encode("utf-8"), "text/html")], fields))
    select_pages(dst, "todas", ctx.plan.pdf_pages)


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        name = derived_name(inp.name, "", "pdf")
        dst = ctx.output(name)
        dxf_pdf(ctx, inp.path, dst, o)
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "planos-pdf.zip")
