"""reparar-pdf, optimizar-pdf-web, extraer-imagenes-pdf y rasterizar-pdf (A.4 y A.5)."""
from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import img2pdf
import pikepdf
import pypdfium2 as pdfium
from pikepdf import Name

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.pdf import raster
from tools.pdf.common import open_pdf, with_batch_zip

# --- reparar-pdf -------------------------------------------------------------------------------------------------


# Avisos del resultado en el idioma de la página (D-42, D-54 y D-151).
NOTES = {
    "es": {
        "qpdf": "Reconstruido con qpdf y pikepdf: {pages} páginas recuperadas.",
        "pdfium": "Guardado de nuevo con PDFium: {pages} páginas recuperadas.",
        "raster": "Rasterizado: {done} de {total} páginas recuperadas como imagen (sin texto seleccionable).",
        "lost": " Páginas perdidas: {pages}.",
        "images": "{count} imágenes extraídas.",
        "skipped": " {count} no se han podido leer (códecs no compatibles).",
    },
    "en": {
        "qpdf": "Rebuilt with qpdf and pikepdf: {pages} pages recovered.",
        "pdfium": "Saved again with PDFium: {pages} pages recovered.",
        "raster": "Rasterised: {done} of {total} pages recovered as images (no selectable text).",
        "lost": " Lost pages: {pages}.",
        "images": "{count} images extracted.",
        "skipped": " {count} could not be read (unsupported codecs).",
    },
}


def _notes(ctx: ToolContext) -> dict[str, str]:
    return NOTES.get(ctx.locale, NOTES["es"])


def _repair_one(ctx: ToolContext, src: Path, dst: Path) -> str:
    """Orden de intentos de A.5: qpdf y pikepdf, PDFium, y por último rasterizar las páginas legibles."""
    try:
        with pikepdf.open(src, attempt_recovery=True) as pdf:
            pages = len(pdf.pages)
            if pages > ctx.plan.pdf_pages:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{pages} páginas")
            pdf.save(dst)
        with pikepdf.open(dst, attempt_recovery=False):
            pass
        return _notes(ctx)["qpdf"].format(pages=pages)
    except pikepdf.PasswordError as exc:
        raise ToolError(ErrorCode.PASSWORD_REQUIRED) from exc
    except ToolError:
        raise
    except Exception:  # noqa: BLE001 - se prueba el siguiente método
        pass
    try:
        doc = pdfium.PdfDocument(str(src))
    except Exception as exc:  # noqa: BLE001
        raise ToolError(ErrorCode.CORRUPT_FILE, "Ningún método puede leer el archivo") from exc
    try:
        total = len(doc)
        if total > ctx.plan.pdf_pages:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{total} páginas")
        try:
            doc.save(str(dst))
            with pikepdf.open(dst, attempt_recovery=False):
                pass
            return _notes(ctx)["pdfium"].format(pages=total)
        except Exception:  # noqa: BLE001 - último recurso
            pass
        images, lost = [], []
        for i in range(total):
            try:
                img = raster.render(doc, i, 150, ctx.settings.RENDER_MAX_PIXELS).convert("RGB")
            except ToolError:
                raise
            except Exception:  # noqa: BLE001 - página ilegible
                lost.append(i + 1)
                continue
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            images.append(buf.getvalue())
        if not images:
            raise ToolError(ErrorCode.CORRUPT_FILE, "Ninguna página legible")
        dst.write_bytes(img2pdf.convert(images, layout_fun=img2pdf.get_fixed_dpi_layout_fun((150, 150))))
        note = _notes(ctx)["raster"].format(done=len(images), total=total)
        if lost:
            note += _notes(ctx)["lost"].format(pages=", ".join(map(str, lost)))
        return note
    finally:
        doc.close()


def run_repair(ctx: ToolContext) -> list[dict]:
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        name = derived_name(inp.name, "-reparado", "pdf")
        dst = ctx.output(name)
        outputs.append({"path": str(dst), "name": name, "note": _repair_one(ctx, inp.path, dst)})
    return with_batch_zip(ctx, outputs, "pdf-reparados.zip")


# --- optimizar-pdf-web --------------------------------------------------------------------------------------------


def run_web(ctx: ToolContext) -> list[dict]:
    from tools.pdf.comprimir_pdf import compress_one
    from tools.pdf.specs import ComprimirOptions

    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        name = derived_name(inp.name, "-web", "pdf")
        dst = ctx.output(name)
        src = inp.path
        if ctx.options.comprimir_antes:
            tmp = ctx.work / f"comprimido-{n}.pdf"
            compress_one(src, tmp, ComprimirOptions(), None, ctx.plan.pdf_pages)
            if tmp.exists() and tmp.stat().st_size < src.stat().st_size:
                src = tmp
        with open_pdf(src, None, ctx.plan.pdf_pages) as pdf:
            pdf.save(dst, linearize=True)
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "pdf-web.zip")


# --- extraer-imagenes-pdf -----------------------------------------------------------------------------------------


def _images(page: pikepdf.Page):
    """Imágenes de la página, también dentro de formularios XObject (sin máscaras de 1 bit)."""
    seen: set[tuple[int, int]] = set()
    stack = [page.obj.get("/Resources")]
    while stack:
        res = stack.pop()
        xobjs = res.get("/XObject") if isinstance(res, pikepdf.Dictionary) else None
        if not isinstance(xobjs, pikepdf.Dictionary):
            continue
        for _, xobj in xobjs.items():
            if not isinstance(xobj, pikepdf.Stream) or xobj.objgen in seen:
                continue
            seen.add(xobj.objgen)
            if xobj.get("/Subtype") == Name.Image and not xobj.get("/ImageMask"):
                yield xobj
            elif xobj.get("/Subtype") == Name.Form:
                stack.append(xobj.get("/Resources"))


def _encode(xobj: pikepdf.Stream, formato: str) -> tuple[bytes, str]:
    filters = xobj.get("/Filter")
    if formato == "original" and (filters == Name.DCTDecode or (isinstance(filters, pikepdf.Array) and list(filters) == [Name.DCTDecode])):
        return xobj.read_raw_bytes(), "jpg"  # JPEG tal cual
    img = pikepdf.PdfImage(xobj).as_pil_image()
    buf = io.BytesIO()
    if formato == "jpg":
        img.convert("L" if img.mode in ("1", "L", "LA") else "RGB").save(buf, format="JPEG", quality=90)
        return buf.getvalue(), "jpg"
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), "png"


def run_extract_images(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    entries: list[tuple[str, bytes]] = []
    skipped = 0
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        prefix = f"{Path(inp.name).stem}/" if len(ctx.inputs) > 1 else ""
        hashes: set[str] = set()
        count = 0
        with open_pdf(inp.path, None, ctx.plan.pdf_pages) as pdf:
            done: set[tuple[int, int]] = set()
            for page_no, page in enumerate(pdf.pages, 1):
                for xobj in _images(page):
                    if xobj.objgen in done:
                        continue
                    done.add(xobj.objgen)
                    if min(int(xobj.get("/Width", 0)), int(xobj.get("/Height", 0))) < o.min_px:
                        continue
                    if o.eliminar_duplicadas:
                        digest = hashlib.sha256(xobj.read_raw_bytes()).hexdigest()
                        if digest in hashes:
                            continue
                        hashes.add(digest)
                    try:
                        data, ext = _encode(xobj, o.formato)
                    except Exception:  # noqa: BLE001 - JBIG2 u otros códecs que Pillow no lee
                        skipped += 1
                        continue
                    count += 1
                    entries.append((f"{prefix}pagina-{page_no:03d}-imagen-{count:03d}.{ext}", data))
    if not entries:
        raise ToolError(ErrorCode.NO_IMAGES)
    zip_name = f"{Path(ctx.inputs[0].name).stem}-imagenes.zip" if len(ctx.inputs) == 1 else "imagenes.zip"
    dst = ctx.output(zip_name)
    with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arc, data in entries:
            zf.writestr(arc, data)
    note = _notes(ctx)["images"].format(count=len(entries))
    if skipped:
        note += _notes(ctx)["skipped"].format(count=skipped)
    return [{"path": str(dst), "name": zip_name, "note": note}]


# --- rasterizar-pdf -----------------------------------------------------------------------------------------------


def run_rasterize(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    if o.dpi > 300 and ctx.plan.id != "pro":
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Más de 300 ppp solo en Pro")
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        name = derived_name(inp.name, "-rasterizado", "pdf")
        dst = ctx.output(name)
        with open_pdf(inp.path, None, ctx.plan.pdf_pages):
            pass  # contraseña y límite de páginas
        doc = pdfium.PdfDocument(str(inp.path))
        try:
            images = []
            for i in range(len(doc)):
                ctx.report((n + i / max(1, len(doc))) / len(ctx.inputs), None)
                img = raster.render(doc, i, o.dpi, ctx.settings.RENDER_MAX_PIXELS)
                buf = io.BytesIO()
                if o.color == "bn":
                    img.convert("L").convert("1").save(buf, format="PNG", optimize=True)
                else:
                    img.convert("L" if o.color == "gris" else "RGB").save(buf, format="JPEG", quality=o.calidad)
                images.append(buf.getvalue())
        finally:
            doc.close()
        dst.write_bytes(img2pdf.convert(images, layout_fun=img2pdf.get_fixed_dpi_layout_fun((o.dpi, o.dpi))))
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "pdf-rasterizados.zip")
