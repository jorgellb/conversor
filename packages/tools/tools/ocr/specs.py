"""OCR con OCRmyPDF 17 y Tesseract, sin Ghostscript (7.5 y A.5)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from core.options import opt
from core.registry import ToolSpec

TESSERACT_CODE = r"^[a-z]{3}(_[a-z]+)?$"
# Imágenes que leen imagen-a-texto, imagen-a-excel y ticket-a-excel (HEIC no: necesita HEVC_DECODE_ENABLED, 11).
IMAGE_INPUTS = ("jpg", "png", "webp", "tiff", "bmp", "gif")


class OcrOptions(BaseModel):
    idiomas: list[str] = opt(["spa"], "Idiomas", "Languages", min_length=1, max_length=3)
    salida: Literal["pdf", "pdfa", "txt"] = opt("pdf", "Salida", "Output",
                                              labels={"pdf": ("PDF con capa de texto", "PDF with text layer"),
                                                      "pdfa": ("PDF/A-2b", "PDF/A-2b"), "txt": ("TXT", "TXT")})
    enderezar: bool = opt(True, "Enderezar", "Deskew")
    autorrotar: bool = opt(False, "Autorrotar páginas", "Auto-rotate pages", advanced=True)
    quitar_fondo: bool = opt(False, "Quitar fondo", "Remove background", advanced=True)
    limpiar: bool = opt(False, "Limpiar páginas", "Clean pages", advanced=True)
    texto_existente: Literal["omitir", "forzar"] = opt("omitir", "Texto existente", "Existing text", advanced=True,
                                                      labels={"omitir": ("Omitir las páginas con texto", "Skip pages with text"),
                                                              "forzar": ("Forzar OCR", "Force OCR")})
    unir: bool = opt(False, "Unir todos los archivos en uno", "Merge all files into one", advanced=True)
    rasterizar_si_falla_pdfa: bool = opt(False, "Si no se puede hacer PDF/A, rasterizar las páginas", "If PDF/A is not possible, rasterize pages", advanced=True,
                                          show_if={"salida": ("pdfa",)})
    titulo: str = opt("", "Título", "Title", max_length=300, advanced=True)
    autor: str = opt("", "Autor", "Author", max_length=300, advanced=True)
    asunto: str = opt("", "Asunto", "Subject", max_length=300, advanced=True)
    palabras_clave: str = opt("", "Palabras clave", "Keywords", max_length=500, advanced=True)

    @field_validator("idiomas")
    @classmethod
    def _codes(cls, v: list[str]) -> list[str]:
        import re

        for code in v:
            if not re.match(TESSERACT_CODE, code):
                raise ValueError(f"Código de idioma no válido: {code}")
        return v


def _check_codes(v: list[str]) -> list[str]:
    import re

    for code in v:
        if not re.match(TESSERACT_CODE, code):
            raise ValueError(f"Código de idioma no válido: {code}")
    return v


class PdfaOptions(BaseModel):
    """A.5: nivel [PDF/A-2b] | 1b | 2u | 3b; 2a y 3a solo si el PDF está etiquetado."""

    nivel: Literal["2b", "1b", "2u", "3b", "2a", "3a"] = opt(
        "2b", "Nivel", "Level",
        labels={"2b": ("PDF/A-2b", "PDF/A-2b"), "1b": ("PDF/A-1b", "PDF/A-1b"), "2u": ("PDF/A-2u", "PDF/A-2u"),
                "3b": ("PDF/A-3b", "PDF/A-3b"), "2a": ("PDF/A-2a (solo PDF etiquetados)", "PDF/A-2a (tagged PDFs only)"),
                "3a": ("PDF/A-3a (solo PDF etiquetados)", "PDF/A-3a (tagged PDFs only)")})
    rasterizar_si_falla: bool = opt(False, "Si no se puede, rasterizar las páginas con capa de texto OCR",
                                    "If it fails, rasterize the pages with an OCR text layer")
    idiomas: list[str] = opt(["spa"], "Idiomas del OCR de las páginas escaneadas", "OCR languages for scanned pages",
                             min_length=1, max_length=3, advanced=True)

    @field_validator("idiomas")
    @classmethod
    def _codes(cls, v: list[str]) -> list[str]:
        return _check_codes(v)


class ImagenTextoOptions(BaseModel):
    """imagen-a-texto (7.6): el Anexo A no fija opciones; las de D-159, con los idiomas y el enderezado de ocr-pdf (A.5)."""

    idiomas: list[str] = opt(["spa", "eng"], "Idiomas del texto", "Text languages", min_length=1, max_length=3)
    salida: Literal["txt", "docx", "pdf"] = opt(
        "txt", "Salida", "Output", labels={"txt": ("Texto (TXT)", "Text (TXT)"), "docx": ("Word (DOCX)", "Word (DOCX)"),
                                             "pdf": ("PDF con capa de texto (buscable)", "PDF with text layer (searchable)")})
    enderezar: bool = opt(True, "Enderezar", "Deskew")
    autorrotar: bool = opt(False, "Girar las imágenes que estén de lado o del revés", "Rotate images that are sideways or upside down",
                           advanced=True)
    unir: bool = opt(False, "Un solo archivo con todas las imágenes", "One file with all the images", advanced=True)

    @field_validator("idiomas")
    @classmethod
    def _codes(cls, v: list[str]) -> list[str]:
        return _check_codes(v)


class ValidarPdfaOptions(BaseModel):
    """A.6: perfil automático (el que declara el archivo) o uno concreto."""

    perfil: Literal["auto", "1a", "1b", "2a", "2b", "2u", "3a", "3b", "3u", "4", "4e", "4f", "ua1", "ua2"] = opt(
        "auto", "Perfil", "Profile",
        labels={"auto": ("Automático (el que declara el archivo)", "Automatic (the one the file declares)"),
                **{k: (f"PDF/A-{k}", f"PDF/A-{k}") for k in ("1a", "1b", "2a", "2b", "2u", "3a", "3b", "3u", "4", "4e", "4f")},
                "ua1": ("PDF/UA-1", "PDF/UA-1"), "ua2": ("PDF/UA-2", "PDF/UA-2")})


SPECS: list[ToolSpec] = [
    ToolSpec(
        slug_es="ocr-pdf", slug_en="ocr-pdf", name_es="OCR de PDF", name_en="OCR PDF", category="pdf", where="server",
        inputs=("pdf",), outputs=("pdf", "txt", "zip"), options=OcrOptions, worker_group="ocr", cost_class="heavy",
        impl="tools.ocr.ocr_pdf:run", launch=True, phase="F2", time_limit=3600,
        summary_es="Reconoce el texto de PDF escaneados para poder buscarlo y copiarlo.",
        summary_en="Recognize text in scanned PDFs so you can search and copy it.",
        related=("pdf-a-word", "comprimir-pdf"),
    ),
    ToolSpec(
        slug_es="pdf-a-pdfa", slug_en="pdf-to-pdfa", name_es="PDF a PDF/A", name_en="PDF to PDF/A", category="pdf", where="server",
        inputs=("pdf",), outputs=("pdf", "html", "zip"), options=PdfaOptions, worker_group="ocr", cost_class="heavy",
        impl="tools.ocr.pdfa:run_pdfa", launch=True, phase="F2", time_limit=3600,
        summary_es="Convierte un PDF a PDF/A para archivo y lo valida con veraPDF, sin Ghostscript.",
        summary_en="Convert a PDF to PDF/A for archiving and validate it with veraPDF, without Ghostscript.",
        related=("validar-pdfa", "ocr-pdf"),
    ),
    ToolSpec(
        slug_es="validar-pdfa", slug_en="validate-pdfa", name_es="Validar PDF/A", name_en="Validate PDF/A", category="pdf",
        where="server", inputs=("pdf",), outputs=("html", "zip"), options=ValidarPdfaOptions, worker_group="ocr",
        cost_class="light", impl="tools.ocr.pdfa:run_validate", launch=True, phase="F2", time_limit=1800,
        summary_es="Comprueba con veraPDF si un PDF cumple PDF/A o PDF/UA y explica cada fallo en lenguaje sencillo.",
        summary_en="Check with veraPDF whether a PDF meets PDF/A or PDF/UA and explain each failure in plain language.",
        related=("pdf-a-pdfa",),
    ),
    # 6.3: 0 peticiones (OCR local). Categoría ai en la web (7.6), pero sin IA externa: ni cuenta ni consentimiento.
    ToolSpec(
        slug_es="imagen-a-texto", slug_en="image-to-text", name_es="Imagen a texto", name_en="Image to text", category="ai",
        where="server", inputs=IMAGE_INPUTS, outputs=("txt", "docx", "pdf", "zip"),
        options=ImagenTextoOptions, worker_group="ocr", cost_class="heavy", impl="tools.ocr.imagen:run", launch=True,
        phase="F3", time_limit=1800,
        summary_es="Saca el texto de fotos, capturas y escaneos con OCR, sin enviarlo a ninguna IA externa.",
        summary_en="Extract the text from photos, screenshots and scans with OCR, without sending it to any external AI.",
        related=("ocr-pdf", "imagen-a-excel", "imagenes-a-pdf"),
    ),
]
