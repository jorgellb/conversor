"""Grupo `media` (5.4): imágenes, libros, correo y CAD 2D. Conversiones a PDF de F2 (7.2 y 7.3)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.options import opt
from core.registry import ToolSpec
from tools.client.specs import ImagenesAPdfOptions

PAPER2 = {"A4": ("A4", "A4"), "Letter": ("Carta", "Letter")}


class ComicOptions(BaseModel):
    tamano: Literal["segun_imagen", "A4", "A5", "Letter"] = opt(
        "segun_imagen", "Tamaño de página", "Page size",
        labels={"segun_imagen": ("Según la imagen", "Same as the image"), "A4": ("A4", "A4"), "A5": ("A5", "A5"), "Letter": ("Carta", "Letter")})


class DjvuOptions(BaseModel):
    calidad: int = opt(85, "Calidad de imagen (%)", "Image quality (%)", ge=25, le=100, advanced=True)
    modo: Literal["color", "black"] = opt("color", "Color", "Colour", advanced=True,
                                         labels={"color": ("Color", "Colour"), "black": ("Solo la capa de blanco y negro", "Black-and-white layer only")})


class CorreoOptions(BaseModel):
    adjuntos: bool = opt(True, "Añadir los adjuntos convertibles como páginas siguientes", "Add convertible attachments as following pages")
    papel: Literal["A4", "Letter"] = opt("A4", "Papel", "Paper", labels=PAPER2)


class DxfOptions(BaseModel):
    papel: Literal["A4", "A3", "A2", "A1", "A0"] = opt("A4", "Papel", "Paper", labels={k: (k, k) for k in ("A4", "A3", "A2", "A1", "A0")})
    orientacion: Literal["auto", "vertical", "horizontal"] = opt(
        "auto", "Orientación", "Orientation",
        labels={"auto": ("Automática", "Automatic"), "vertical": ("Vertical", "Portrait"), "horizontal": ("Horizontal", "Landscape")})
    monocromo: bool = opt(False, "En blanco y negro", "Black and white")
    margenes_mm: float = opt(10, "Márgenes (mm)", "Margins (mm)", ge=0, le=50, advanced=True)


# ——— Imágenes en el servidor (F5, lote C; 7.11 y A.10) ———

COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class HeicOptions(BaseModel):
    """heic-a-jpg y heic-a-png (A.10): solo con HEVC_DECODE_ENABLED."""

    calidad: int = opt(90, "Calidad (%)", "Quality (%)", ge=1, le=100)
    conservar_exif: bool = opt(True, "Conservar los datos EXIF", "Keep the EXIF data")
    quitar_gps: bool = opt(True, "Quitar la ubicación GPS", "Remove the GPS location", show_if={"conservar_exif": (True,)})


class HeicPngOptions(BaseModel):
    conservar_exif: bool = opt(True, "Conservar los datos EXIF", "Keep the EXIF data")
    quitar_gps: bool = opt(True, "Quitar la ubicación GPS", "Remove the GPS location", show_if={"conservar_exif": (True,)})


class RawOptions(BaseModel):
    """raw-a-jpg: revelado de LibRaw; el Anexo A no fija opciones (D-97)."""

    calidad: int = opt(90, "Calidad (%)", "Quality (%)", ge=1, le=100)
    balance_blancos: Literal["camara", "automatico"] = opt(
        "camara", "Balance de blancos", "White balance",
        labels={"camara": ("El de la cámara", "As shot"), "automatico": ("Automático", "Automatic")})
    brillo_automatico: bool = opt(True, "Ajustar el brillo automáticamente", "Adjust brightness automatically", advanced=True)
    tamano: Literal["completo", "mitad"] = opt(
        "completo", "Tamaño", "Size", advanced=True,
        labels={"completo": ("Completo", "Full size"), "mitad": ("La mitad (más rápido)", "Half (faster)")})
    conservar_exif: bool = opt(True, "Conservar los datos EXIF", "Keep the EXIF data", advanced=True)
    quitar_gps: bool = opt(True, "Quitar la ubicación GPS", "Remove the GPS location", advanced=True, show_if={"conservar_exif": (True,)})


class PsdOptions(BaseModel):
    salida: Literal["imagen", "capas"] = opt(
        "imagen", "Qué exportar", "What to export",
        labels={"imagen": ("La imagen completa", "The whole image"), "capas": ("Cada capa visible en un PNG (ZIP)", "Each visible layer as a PNG (ZIP)")})
    transparencia: bool = opt(True, "Conservar la transparencia", "Keep the transparency", show_if={"salida": ("imagen",)})


class VectorizarOptions(BaseModel):
    """png-a-svg y jpg-a-svg con vtracer."""

    colores: Literal["color", "blanco_y_negro"] = opt(
        "color", "Colores", "Colours", labels={"color": ("En color", "Colour"), "blanco_y_negro": ("Blanco y negro", "Black and white")})
    detalle: Literal["alto", "medio", "bajo"] = opt(
        "medio", "Detalle", "Detail",
        labels={"alto": ("Alto (más trazados)", "High (more paths)"), "medio": ("Medio", "Medium"), "bajo": ("Bajo (más limpio)", "Low (cleaner)")})
    trazado: Literal["curvas", "poligonos", "pixeles"] = opt(
        "curvas", "Trazado", "Paths", advanced=True,
        labels={"curvas": ("Curvas suaves", "Smooth curves"), "poligonos": ("Polígonos", "Polygons"), "pixeles": ("Píxeles", "Pixels")})


class QuitarFondoOptions(BaseModel):
    """quitar-fondo con rembg (6.4); el Anexo A no fija opciones (D-96)."""

    formato: Literal["png", "webp", "jpg"] = opt("png", "Formato", "Format",
                                                 labels={"png": ("PNG con transparencia", "PNG with transparency"),
                                                         "webp": ("WEBP con transparencia", "WEBP with transparency"),
                                                         "jpg": ("JPG con fondo de color", "JPG with a colour background")})
    fondo: Literal["transparente", "color"] = opt("transparente", "Fondo", "Background",
                                                  labels={"transparente": ("Transparente", "Transparent"), "color": ("De un color", "A colour")})
    color: str = opt("#FFFFFF", "Color del fondo", "Background colour", pattern=COLOR_PATTERN, show_if={"fondo": ("color",)})
    recortar: bool = opt(False, "Recortar al contorno del objeto", "Crop to the object")
    bordes_finos: bool = opt(False, "Refinar los bordes (pelo, piel; más lento)", "Refine the edges (hair, skin; slower)", advanced=True)


def media(slug_es, slug_en, name_es, name_en, options, inputs, impl, summary_es, summary_en, **kw) -> ToolSpec:
    return ToolSpec(slug_es=slug_es, slug_en=slug_en, name_es=name_es, name_en=name_en, category=kw.pop("category", "pdf"),
                    where="server", inputs=inputs, outputs=kw.pop("outputs", ("pdf", "zip")), options=options, worker_group="media",
                    cost_class=kw.pop("cost_class", "light"), impl=impl, launch=True, phase=kw.pop("phase", "F2"),
                    time_limit=kw.pop("time_limit", 900), summary_es=summary_es, summary_en=summary_en, **kw)


def image(slug_es, slug_en, name_es, name_en, options, inputs, outputs, impl, summary_es, summary_en, **kw) -> ToolSpec:
    return media(slug_es, slug_en, name_es, name_en, options, inputs, impl, summary_es, summary_en, outputs=outputs, category="image",
                 phase="F5", **kw)


SPECS: list[ToolSpec] = [
    media("heic-a-pdf", "heic-to-pdf", "HEIC a PDF", "HEIC to PDF", ImagenesAPdfOptions, ("heic",), "tools.media.imagenes:run_heic",
          "Convierte fotos HEIC del iPhone en PDF.", "Convert iPhone HEIC photos to PDF.", related=("imagenes-a-pdf", "jpg-a-pdf")),
    media("cbz-a-pdf", "cbz-to-pdf", "CBZ a PDF", "CBZ to PDF", ComicOptions, ("cbz",), "tools.media.imagenes:run_comic",
          "Convierte cómics CBZ en un PDF con sus páginas en orden.", "Convert CBZ comics to a PDF with the pages in order.",
          related=("cbr-a-pdf", "imagenes-a-pdf")),
    media("cbr-a-pdf", "cbr-to-pdf", "CBR a PDF", "CBR to PDF", ComicOptions, ("cbr",), "tools.media.imagenes:run_comic",
          "Convierte cómics CBR (RAR o ZIP) en un PDF.", "Convert CBR comics (RAR or ZIP) to a PDF.", related=("cbz-a-pdf",)),
    media("djvu-a-pdf", "djvu-to-pdf", "DjVu a PDF", "DjVu to PDF", DjvuOptions, ("djvu",), "tools.media.imagenes:run_djvu",
          "Convierte documentos DjVu escaneados en PDF.", "Convert scanned DjVu documents to PDF.", related=("ocr-pdf", "comprimir-pdf")),
    media("eml-a-pdf", "eml-to-pdf", "EML a PDF", "EML to PDF", CorreoOptions, ("eml",), "tools.media.correo:run",
          "Guarda un correo EML en PDF con sus cabeceras y los adjuntos convertibles.",
          "Save an EML email as PDF with its headers and the attachments that can be converted.", related=("msg-a-pdf",)),
    media("msg-a-pdf", "msg-to-pdf", "MSG a PDF", "MSG to PDF", CorreoOptions, ("msg",), "tools.media.correo:run",
          "Guarda un mensaje de Outlook (MSG) en PDF con sus cabeceras y adjuntos.",
          "Save an Outlook message (MSG) as PDF with its headers and attachments.", related=("eml-a-pdf",)),
    media("dxf-a-pdf", "dxf-to-pdf", "DXF a PDF", "DXF to PDF", DxfOptions, ("dxf",), "tools.media.dxf:run",
          "Convierte planos DXF en PDF vectorial, en color o en blanco y negro.",
          "Convert DXF drawings to vector PDF, in colour or black and white.", related=("svg-a-pdf",)),
    image("heic-a-jpg", "heic-to-jpg", "HEIC a JPG", "HEIC to JPG", HeicOptions, ("heic",), ("jpg", "zip"), "tools.media.fotos:run_heic_image",
          "Convierte las fotos HEIC del iPhone a JPG, con sus datos EXIF y sin la ubicación.",
          "Convert iPhone HEIC photos to JPG, with their EXIF data and without the location.", related=("heic-a-png", "heic-a-pdf")),
    image("heic-a-png", "heic-to-png", "HEIC a PNG", "HEIC to PNG", HeicPngOptions, ("heic",), ("png", "zip"), "tools.media.fotos:run_heic_image",
          "Convierte las fotos HEIC del iPhone a PNG sin pérdida.", "Convert iPhone HEIC photos to lossless PNG.",
          related=("heic-a-jpg", "heic-a-pdf")),
    image("raw-a-jpg", "raw-to-jpg", "RAW a JPG", "RAW to JPG", RawOptions, ("cr2", "nef", "arw", "dng"), ("jpg", "zip"), "tools.media.fotos:run_raw",
          "Revela fotos RAW de Canon (CR2), Nikon (NEF), Sony (ARW) y DNG a JPG.",
          "Develop RAW photos from Canon (CR2), Nikon (NEF), Sony (ARW) and DNG to JPG.", related=("comprimir-imagen", "redimensionar-imagen")),
    image("psd-a-png", "psd-to-png", "PSD a PNG", "PSD to PNG", PsdOptions, ("psd", "psb"), ("png", "zip"), "tools.media.fotos:run_psd",
          "Convierte archivos de Photoshop (PSD y PSB) a PNG, la imagen completa o cada capa.",
          "Convert Photoshop files (PSD and PSB) to PNG, the whole image or each layer.", related=("convertir-imagen",)),
    image("png-a-svg", "png-to-svg", "PNG a SVG", "PNG to SVG", VectorizarOptions, ("png",), ("svg", "zip"), "tools.media.vectorizar:run",
          "Vectoriza logotipos y dibujos PNG en SVG, en color o en blanco y negro.",
          "Trace PNG logos and drawings into SVG, in colour or black and white.", related=("jpg-a-svg", "svg-a-png")),
    image("jpg-a-svg", "jpg-to-svg", "JPG a SVG", "JPG to SVG", VectorizarOptions, ("jpg",), ("svg", "zip"), "tools.media.vectorizar:run",
          "Vectoriza imágenes JPG en SVG para ampliarlas sin pixelar.", "Trace JPG images into SVG so they scale without pixelation.",
          related=("png-a-svg", "svg-a-png")),
    image("quitar-fondo", "remove-background", "Quitar fondo", "Remove background", QuitarFondoOptions, ("jpg", "png", "webp"),
          ("png", "webp", "jpg", "zip"), "tools.media.fondo:run",
          "Quita el fondo de tus fotos y deja el objeto con fondo transparente o de un color.",
          "Remove the background from your photos and keep the subject on a transparent or coloured background.",
          cost_class="heavy", time_limit=600, related=("convertir-imagen", "redimensionar-imagen")),
]
