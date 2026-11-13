"""Rasterizado de páginas con pypdfium2 y sustitución por una imagen que respeta CropBox y /Rotate.

La imagen que devuelve PDFium es la página tal como se ve (recortada y girada). Para no tocar MediaBox, CropBox,
/Rotate ni las anotaciones (enlaces y formularios siguen en su sitio), la imagen se dibuja sobre la CropBox en el
espacio de usuario con una matriz que deshace el giro.
"""
from __future__ import annotations

import io
import zlib

import pikepdf
from pikepdf import Name
from PIL import Image

from core.errors import ErrorCode, ToolError


def render(doc, index: int, dpi: float, max_pixels: int, draw_annots: bool = True) -> Image.Image:
    """Página `index` de un `pypdfium2.PdfDocument` a `dpi`, tal como se ve, con el límite de píxeles (12.3)."""
    page = doc[index]
    try:
        w, h = page.get_size()
        scale = dpi / 72
        if w * scale * h * scale > max_pixels:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"Página {index + 1}: demasiados píxeles a {dpi:g} ppp")
        return page.render(scale=scale, draw_annots=draw_annots, may_draw_forms=draw_annots).to_pil()
    finally:
        page.close()


def mean_luminance(doc, index: int) -> float:
    """Luminancia media (0-1) de una miniatura de la página, para detectar páginas ya oscuras."""
    img = render(doc, index, 12, 10_000_000).convert("L")
    hist = img.histogram()
    total = sum(hist) or 1
    return sum(i * c for i, c in enumerate(hist)) / total / 255


def _box(page: pikepdf.Page) -> tuple[float, float, float, float]:
    box = page.obj.get("/CropBox") or page.mediabox
    x0, y0, x1, y1 = (float(v) for v in box)
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def image_cm(page: pikepdf.Page) -> tuple[float, float, float, float, float, float]:
    """Matriz que lleva el cuadrado unidad de la imagen (página vista) a la CropBox en el espacio de usuario."""
    x0, y0, x1, y1 = _box(page)
    w, h = x1 - x0, y1 - y0
    rotate = int(page.obj.get("/Rotate", 0)) % 360
    if rotate == 90:
        return 0, h, -w, 0, x1, y0
    if rotate == 180:
        return -w, 0, 0, -h, x1, y1
    if rotate == 270:
        return 0, -h, w, 0, x0, y1
    return w, 0, 0, h, x0, y0


def image_stream(pdf: pikepdf.Pdf, img: Image.Image, quality: int = 85) -> pikepdf.Stream:
    """XObject de imagen: JPEG para color y gris, Flate de 1 bit para blanco y negro."""
    if img.mode == "1":
        data = zlib.compress(img.tobytes(), 9)
        return pikepdf.Stream(pdf, data, Type=Name.XObject, Subtype=Name.Image, Width=img.width, Height=img.height,
                              ColorSpace=Name.DeviceGray, BitsPerComponent=1, Filter=Name.FlateDecode,
                              Decode=pikepdf.Array([0, 1]))
    mode = "L" if img.mode in ("L", "LA") else "RGB"
    out = img.convert(mode)
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=quality, optimize=True)
    return pikepdf.Stream(pdf, buf.getvalue(), Type=Name.XObject, Subtype=Name.Image, Width=out.width, Height=out.height,
                          ColorSpace=Name.DeviceGray if mode == "L" else Name.DeviceRGB, BitsPerComponent=8, Filter=Name.DCTDecode)


def replace_with_image(pdf: pikepdf.Pdf, page: pikepdf.Page, img: Image.Image, quality: int = 85) -> None:
    """Sustituye el contenido de la página por la imagen; conserva cajas, giro y anotaciones."""
    xobj = image_stream(pdf, img, quality)
    a, b, c, d, e, f = image_cm(page)
    page.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=xobj))
    page.obj.Contents = pdf.make_stream(f"q {a:.4f} {b:.4f} {c:.4f} {d:.4f} {e:.4f} {f:.4f} cm /Im0 Do Q".encode())
    for key in ("/Group", "/PieceInfo"):
        if key in page.obj:
            del page.obj[key]
