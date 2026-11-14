"""pdf-escala-de-grises y pdf-modo-oscuro (A.5) sobre el motor de `colores.py`."""
from __future__ import annotations

import pikepdf
import pypdfium2 as pdfium

from tools.base import ToolContext, derived_name
from tools.pdf import raster
from tools.pdf.colores import Rewriter, dark_keep_hue, negative, to_gray
from tools.pdf.common import open_pdf, with_batch_zip

GRAY_DPI = 150
BACKGROUNDS = {"negro": (0.0, 0.0, 0.0), "gris_oscuro": (0.12, 0.12, 0.13)}
DARK_PAGE = 0.35


def _pages_list(indexes: list[int]) -> str:
    return ", ".join(str(i + 1) for i in indexes)


# Avisos del resultado en el idioma de la página (D-42, D-54 y D-151).
NOTES = {
    "es": {
        "gray_raster": "Páginas rasterizadas en gris porque no se podían convertir con seguridad: {pages}.",
        "dark_skipped": "Páginas que ya eran oscuras y no se han tocado: {pages}.",
        "dark_partial": "Páginas con elementos que se han dejado con sus colores: {pages}.",
    },
    "en": {
        "gray_raster": "Pages rasterised in grey because they could not be converted safely: {pages}.",
        "dark_skipped": "Pages that were already dark and were left untouched: {pages}.",
        "dark_partial": "Pages with elements that were left with their colours: {pages}.",
    },
}


def _notes(ctx: ToolContext) -> dict[str, str]:
    return NOTES.get(ctx.locale, NOTES["es"])


def _acroform_da(pdf: pikepdf.Pdf, rw: Rewriter) -> None:
    form = pdf.Root.get("/AcroForm")
    if isinstance(form, pikepdf.Dictionary) and "/DA" in form:
        form.DA = pikepdf.String(rw.convert_da(str(form.DA)))


def run_gray(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        name = derived_name(inp.name, "-gris", "pdf")
        dst = ctx.output(name)
        with open_pdf(inp.path, None, ctx.plan.pdf_pages) as pdf:
            raster_pages: list[int] = []
            if o.metodo == "vectorial":
                rw = Rewriter(pdf, to_gray, images="gris", inline_images_safe=False)
                for i, page in enumerate(pdf.pages):
                    if rw.page(page):
                        raster_pages.append(i)
                _acroform_da(pdf, rw)
            else:
                raster_pages = list(range(len(pdf.pages)))
            if raster_pages:
                doc = pdfium.PdfDocument(str(inp.path))
                try:
                    for i in raster_pages:
                        img = raster.render(doc, i, GRAY_DPI, ctx.settings.RENDER_MAX_PIXELS, draw_annots=False).convert("L")
                        raster.replace_with_image(pdf, pdf.pages[i], img)
                finally:
                    doc.close()
            pdf.save(dst)
        note = None
        if o.metodo == "vectorial" and raster_pages:
            note = _notes(ctx)["gray_raster"].format(pages=_pages_list(raster_pages))
        outputs.append({"path": str(dst), "name": name, "note": note})
    return with_batch_zip(ctx, outputs, "pdf-gris.zip")


def run_dark(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    fn = dark_keep_hue if o.modo == "conservar" else negative
    bg = BACKGROUNDS[o.fondo]
    fg = round(fn((0.0, 0.0, 0.0))[0], 4)  # el negro por defecto del texto
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        name = derived_name(inp.name, "-oscuro", "pdf")
        dst = ctx.output(name)
        skipped: list[int] = []
        partial: list[int] = []
        with open_pdf(inp.path, None, ctx.plan.pdf_pages) as pdf:
            doc = pdfium.PdfDocument(str(inp.path)) if o.saltar_oscuras else None
            try:
                rw = Rewriter(pdf, fn, images="igual" if o.modo == "conservar" else "invertir", inline_images_safe=True)
                for i, page in enumerate(pdf.pages):
                    if doc is not None and raster.mean_luminance(doc, i) < DARK_PAGE:
                        skipped.append(i)
                        continue
                    x0, y0, x1, y1 = (float(v) for v in page.mediabox)
                    prefix = (f"q {bg[0]} {bg[1]} {bg[2]} rg {x0:.3f} {y0:.3f} {x1 - x0:.3f} {y1 - y0:.3f} re f Q "
                              f"{fg} g {fg} G\n").encode()
                    if rw.page(page, prefix):
                        partial.append(i)
                _acroform_da(pdf, rw)
            finally:
                if doc is not None:
                    doc.close()
            pdf.save(dst)
        notes = []
        if skipped:
            notes.append(_notes(ctx)["dark_skipped"].format(pages=_pages_list(skipped)))
        if partial:
            notes.append(_notes(ctx)["dark_partial"].format(pages=_pages_list(partial)))
        outputs.append({"path": str(dst), "name": name, "note": " ".join(notes) or None})
    return with_batch_zip(ctx, outputs, "pdf-oscuro.zip")
