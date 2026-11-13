"""comprimir-pdf (7.5 y A.5): recompresión de imágenes con pikepdf y Pillow, limpieza y guardado compacto.

Nunca devuelve un archivo mayor que el original. No usa Ghostscript.
"""
from __future__ import annotations

import hashlib
import io
import shutil
from pathlib import Path

import pikepdf
from PIL import Image
from pikepdf import Name, PdfImage

from core.errors import ErrorCode
from tools.base import ToolContext, derived_name
from tools.pdf import raster
from tools.pdf.common import open_pdf, with_batch_zip

PRESETS = {"equilibrado": (144, 75), "fuerte": (96, 60), "sin_perdida": (None, None)}
HEAVY_VECTOR_OPS = 150_000


def _settings(o) -> tuple[int | None, int | None]:
    if o.nivel == "personalizado":
        return o.dpi, o.calidad
    return PRESETS[o.nivel]


def _max_page_inches(pdf: pikepdf.Pdf) -> float:
    best = 0.0
    for page in pdf.pages:
        box = page.mediabox
        w, h = abs(float(box[2]) - float(box[0])), abs(float(box[3]) - float(box[1]))
        best = max(best, w / 72, h / 72)
    return best or 11.7


def _iter_image_objects(pdf: pikepdf.Pdf):
    seen: set[tuple[int, int]] = set()
    for page in pdf.pages:
        stack = [page.obj.get("/Resources")]
        while stack:
            res = stack.pop()
            if not isinstance(res, pikepdf.Dictionary):
                continue
            xobjs = res.get("/XObject")
            if not isinstance(xobjs, pikepdf.Dictionary):
                continue
            for _, xobj in xobjs.items():
                if not isinstance(xobj, pikepdf.Stream):
                    continue
                key = xobj.objgen
                if key in seen:
                    continue
                seen.add(key)
                subtype = xobj.get("/Subtype")
                if subtype == Name.Image:
                    yield xobj
                elif subtype == Name.Form:
                    stack.append(xobj.get("/Resources"))


def _recompress_image(xobj: pikepdf.Stream, max_side: int | None, quality: int | None, gray: bool, jpx: bool) -> bool:
    if "/SMask" in xobj or "/Mask" in xobj or xobj.get("/ImageMask", False) or "/Decode" in xobj:
        return False
    try:
        pimg = PdfImage(xobj)
        if pimg.bits_per_component != 8 or pimg.indexed or pimg.is_separation or pimg.is_device_n:
            return False
        if pimg.colorspace not in ("/DeviceRGB", "/DeviceGray", "/ICCBased"):
            return False
        filters = pimg.filters
        if any(f in ("/JBIG2Decode", "/CCITTFaxDecode", "/JPXDecode") for f in filters):
            return False
        img = pimg.as_pil_image()
    except (pikepdf.PdfError, NotImplementedError, ValueError, OSError):
        return False
    if img.mode not in ("RGB", "L"):
        return False
    if quality is None:
        return False
    original_size = len(xobj.read_raw_bytes())
    changed = False
    if max_side and max(img.size) > max_side:
        ratio = max_side / max(img.size)
        img = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.LANCZOS)
        changed = True
    if gray and img.mode != "L":
        img = img.convert("L")
        changed = True
    buf = io.BytesIO()
    if jpx:
        img.save(buf, format="JPEG2000", quality_mode="rates", quality_layers=[max(5, int(100 / max(quality, 1) * 4))])
        filt = Name.JPXDecode
    else:
        img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=False)
        filt = Name.DCTDecode
    data = buf.getvalue()
    if not changed and len(data) >= original_size * 0.95:
        return False
    xobj.write(data, filter=filt)
    xobj.Width, xobj.Height = img.width, img.height
    xobj.BitsPerComponent = 8
    xobj.ColorSpace = Name.DeviceGray if img.mode == "L" else Name.DeviceRGB
    for key in ("/DecodeParms", "/Interpolate"):
        if key in xobj:
            del xobj[key]
    return True


def _dedupe_streams(pdf: pikepdf.Pdf) -> int:
    """Une imágenes idénticas en un solo objeto y actualiza las referencias."""
    by_hash: dict[str, pikepdf.Stream] = {}
    replaced = 0
    for page in pdf.pages:
        res = page.obj.get("/Resources")
        xobjs = res.get("/XObject") if isinstance(res, pikepdf.Dictionary) else None
        if not isinstance(xobjs, pikepdf.Dictionary):
            continue
        for name, xobj in list(xobjs.items()):
            if not isinstance(xobj, pikepdf.Stream) or xobj.get("/Subtype") != Name.Image:
                continue
            digest = hashlib.sha256(xobj.read_raw_bytes() + repr(sorted((k, str(v)) for k, v in xobj.items() if k != "/Length")).encode()).hexdigest()
            first = by_hash.setdefault(digest, xobj)
            if first.objgen != xobj.objgen:
                xobjs[name] = first
                replaced += 1
    return replaced


def _dedupe_fonts(pdf: pikepdf.Pdf) -> int:
    by_hash: dict[str, pikepdf.Stream] = {}
    replaced = 0
    for obj in pdf.objects:
        if not isinstance(obj, pikepdf.Dictionary) or obj.get("/Type") != Name.FontDescriptor:
            continue
        for key in ("/FontFile", "/FontFile2", "/FontFile3"):
            stream = obj.get(key)
            if isinstance(stream, pikepdf.Stream):
                digest = key + hashlib.sha256(stream.read_raw_bytes()).hexdigest()
                first = by_hash.setdefault(digest, stream)
                if first.objgen != stream.objgen:
                    obj[key] = first
                    replaced += 1
    return replaced


def _rasterize_heavy_vector_pages(src: Path, pdf: pikepdf.Pdf, dpi: int, quality: int) -> int:
    """Rasteriza solo páginas sin texto con un número enorme de operadores de dibujo."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(src))
    done = 0
    try:
        for i, page in enumerate(pdf.pages):
            try:
                ops = len(pikepdf.parse_content_stream(page))
            except pikepdf.PdfError:
                continue
            if ops < HEAVY_VECTOR_OPS:
                continue
            ppage = doc[i]
            if ppage.get_textpage().count_chars() > 0:
                continue
            # Imagen de la página tal como se ve, colocada sobre la CropBox deshaciendo /Rotate (tools/pdf/raster.py).
            img = ppage.render(scale=dpi / 72, draw_annots=False).to_pil().convert("RGB")
            raster.replace_with_image(pdf, page, img, quality)
            done += 1
    finally:
        doc.close()
    return done


def compress_one(src: Path, dst: Path, o, password: str | None, max_pages: int) -> dict:
    dpi, quality = _settings(o)
    stats = {"images": 0, "dedup": 0, "fonts": 0, "raster_pages": 0}
    with open_pdf(src, password, max_pages) as pdf:
        if o.eliminar_miniaturas:
            for page in pdf.pages:
                if "/Thumb" in page.obj:
                    del page.obj["/Thumb"]
        if o.aplanar_formularios:
            pdf.flatten_annotations(mode="all")
            if "/AcroForm" in pdf.Root:
                del pdf.Root["/AcroForm"]
        if o.quitar_anotaciones:
            for page in pdf.pages:
                annots = page.obj.get("/Annots")
                if isinstance(annots, pikepdf.Array):
                    keep = [a for a in annots if isinstance(a, pikepdf.Dictionary) and a.get("/Subtype") == Name.Widget]
                    page.obj.Annots = pikepdf.Array(keep)
        if o.quitar_adjuntos:
            names = pdf.Root.get("/Names")
            if isinstance(names, pikepdf.Dictionary) and "/EmbeddedFiles" in names:
                del names["/EmbeddedFiles"]
            for page in pdf.pages:
                annots = page.obj.get("/Annots")
                if isinstance(annots, pikepdf.Array):
                    page.obj.Annots = pikepdf.Array([a for a in annots if not (isinstance(a, pikepdf.Dictionary) and a.get("/Subtype") == Name.FileAttachment)])
        if o.quitar_marcadores and "/Outlines" in pdf.Root:
            del pdf.Root["/Outlines"]
        if o.quitar_metadatos:
            if "/Metadata" in pdf.Root:
                del pdf.Root["/Metadata"]
            if "/Info" in pdf.trailer:
                del pdf.trailer["/Info"]
        if o.quitar_output_intents and "/OutputIntents" in pdf.Root:
            del pdf.Root["/OutputIntents"]
        if o.quitar_estructura:
            for key in ("/StructTreeRoot", "/MarkInfo"):
                if key in pdf.Root:
                    del pdf.Root[key]
            for page in pdf.pages:
                if "/StructParents" in page.obj:
                    del page.obj["/StructParents"]
        if dpi and o.rasterizar_vectoriales:
            stats["raster_pages"] = _rasterize_heavy_vector_pages(src, pdf, dpi, quality or 75)
        if quality:
            max_side = int(_max_page_inches(pdf) * dpi) if dpi else None
            for xobj in list(_iter_image_objects(pdf)):
                if _recompress_image(xobj, max_side, quality, o.imagenes_gris, o.compresion_moderna):
                    stats["images"] += 1
        if o.deduplicar:
            stats["dedup"] = _dedupe_streams(pdf)
        if o.reducir_fuentes:
            stats["fonts"] = _dedupe_fonts(pdf)
        pdf.remove_unreferenced_resources()
        pdf.save(dst, compress_streams=True, object_stream_mode=pikepdf.ObjectStreamMode.generate,
                 recompress_flate=o.flate_maximo, preserve_pdfa=not o.quitar_output_intents)
    return stats


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    password = ctx.secrets.get("contrasena")
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / max(1, len(ctx.inputs)), None)
        dst = ctx.output(derived_name(inp.name, "-comprimido", "pdf"))
        compress_one(inp.path, dst, o, password, ctx.plan.pdf_pages)
        note = None
        if dst.stat().st_size >= inp.size:
            shutil.copyfile(inp.path, dst)
            note = ErrorCode.NOT_SMALLER
        before, after = inp.size, dst.stat().st_size
        outputs.append({"path": str(dst), "name": derived_name(inp.name, "-comprimido", "pdf"),
                        "note": note or f"{before}->{after}"})
    return with_batch_zip(ctx, outputs, "comprimidos.zip")
