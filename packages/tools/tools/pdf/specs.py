"""Herramientas PDF de servidor del grupo `pdf` (7.5 y Anexo A, A.5 y A.6)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from core.options import opt
from core.registry import ToolSpec


class ComprimirOptions(BaseModel):
    nivel: Literal["equilibrado", "fuerte", "sin_perdida", "personalizado"] = opt(
        "equilibrado", "Nivel", "Level",
        labels={"equilibrado": ("Equilibrado (144 ppp, 75 %)", "Balanced (144 dpi, 75%)"),
                "fuerte": ("Fuerte (96 ppp, 60 %)", "Strong (96 dpi, 60%)"),
                "sin_perdida": ("Sin pérdida", "Lossless"), "personalizado": ("Personalizado", "Custom")})
    dpi: int = opt(144, "Resolución máxima de imágenes (ppp)", "Maximum image resolution (dpi)", ge=10, le=300,
                   show_if={"nivel": ("personalizado",)})
    calidad: int = opt(75, "Calidad JPEG (%)", "JPEG quality (%)", ge=1, le=100, show_if={"nivel": ("personalizado",)})
    eliminar_miniaturas: bool = opt(True, "Eliminar miniaturas", "Remove thumbnails", advanced=True)
    deduplicar: bool = opt(True, "Deduplicar flujos", "Deduplicate streams", advanced=True)
    rasterizar_vectoriales: bool = opt(True, "Rasterizar gráficos vectoriales muy pesados", "Rasterize very heavy vector graphics", advanced=True)
    reducir_fuentes: bool = opt(True, "Reducir fuentes incrustadas", "Reduce embedded fonts", advanced=True)
    compresion_moderna: bool = opt(False, "Compresión de imagen moderna (JPEG 2000)", "Modern image compression (JPEG 2000)", advanced=True)
    imagenes_gris: bool = opt(False, "Imágenes a gris", "Images to grayscale", advanced=True)
    flate_maximo: bool = opt(False, "Flate máximo y flujos de objetos", "Maximum Flate and object streams", advanced=True)
    aplanar_formularios: bool = opt(False, "Aplanar formularios", "Flatten forms", advanced=True)
    quitar_output_intents: bool = opt(False, "Quitar output intents (rompe PDF/A)", "Remove output intents (breaks PDF/A)", advanced=True)
    quitar_adjuntos: bool = opt(False, "Quitar adjuntos", "Remove attachments", advanced=True)
    quitar_anotaciones: bool = opt(False, "Quitar anotaciones", "Remove annotations", advanced=True)
    quitar_marcadores: bool = opt(False, "Quitar marcadores", "Remove bookmarks", advanced=True)
    quitar_metadatos: bool = opt(False, "Quitar metadatos", "Remove metadata", advanced=True)
    quitar_estructura: bool = opt(False, "Quitar estructura y etiquetas (rompe la accesibilidad)", "Remove structure and tags (breaks accessibility)", advanced=True)
    contrasena: str | None = opt(None, "Contraseña del PDF", "PDF password", advanced=True)


class ProtegerOptions(BaseModel):
    contrasena_apertura: str | None = opt(None, "Contraseña para abrir", "Password to open", max_length=127)
    contrasena_propietario: str | None = opt(None, "Contraseña de propietario", "Owner password", max_length=127, advanced=True)
    permitir_modificar: bool = opt(True, "Permitir modificar", "Allow modifying", advanced=True)
    permitir_comentar: bool = opt(True, "Permitir comentar", "Allow commenting", advanced=True)
    permitir_imprimir: bool = opt(True, "Permitir imprimir", "Allow printing", advanced=True)
    permitir_imprimir_alta: bool = opt(True, "Permitir imprimir en alta calidad", "Allow high-quality printing", advanced=True)
    permitir_ensamblar: bool = opt(True, "Permitir ensamblar", "Allow assembling", advanced=True)
    permitir_formularios: bool = opt(True, "Permitir rellenar formularios", "Allow filling forms", advanced=True)
    permitir_copiar: bool = opt(True, "Permitir copiar", "Allow copying", advanced=True)
    permitir_copiar_accesibilidad: bool = opt(True, "Permitir copiar por accesibilidad", "Allow copying for accessibility", advanced=True)
    cifrado: Literal["aes256", "aes128"] = opt("aes256", "Cifrado", "Encryption", advanced=True,
                                               labels={"aes256": ("AES-256", "AES-256"), "aes128": ("AES-128 (lectores antiguos)", "AES-128 (old readers)")})


class DesbloquearOptions(BaseModel):
    contrasena: str | None = opt(None, "Contraseña actual", "Current password", max_length=127)


# --- F2: herramientas PDF de servidor con pikepdf y pypdfium2 (A.3 a A.7) --------------------------------------

KEEP = ("no_cambiar", "No cambiar", "No change")
TRI = {"no_cambiar": KEEP[1:], "si": ("Sí", "Yes"), "no": ("No", "No")}
BOXES = {"no_cambiar": KEEP[1:], **{b: (b, b) for b in ("MediaBox", "CropBox", "BleedBox", "TrimBox", "ArtBox")}}
DATE_PATTERN = r"^$|^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$"


class SinOpciones(BaseModel):
    """Herramientas sin opciones (reparar-pdf y eliminar-metadatos-pdf)."""


class WebOptions(BaseModel):
    comprimir_antes: bool = opt(False, "Comprimir antes", "Compress first", advanced=True)


class GrisOptions(BaseModel):
    metodo: Literal["vectorial", "rasterizar"] = opt(
        "vectorial", "Método", "Method", advanced=True,
        labels={"vectorial": ("Vectorial: el texto y los gráficos siguen siendo vectoriales", "Vector: text and graphics stay vector"),
                "rasterizar": ("Rasterizar todo", "Rasterise everything")})


class OscuroOptions(BaseModel):
    modo: Literal["conservar", "negativo"] = opt(
        "conservar", "Modo", "Mode",
        labels={"conservar": ("Oscuro conservando tonos (las fotos no cambian)", "Dark keeping hues (photos unchanged)"),
                "negativo": ("Negativo (todo invertido)", "Negative (everything inverted)")})
    fondo: Literal["gris_oscuro", "negro"] = opt("gris_oscuro", "Fondo", "Background",
                                                 labels={"gris_oscuro": ("Gris oscuro", "Dark grey"), "negro": ("Negro", "Black")})
    saltar_oscuras: bool = opt(True, "No tocar las páginas que ya son oscuras", "Leave pages that are already dark")


class ExtraerImagenesOptions(BaseModel):
    formato: Literal["original", "png", "jpg"] = opt(
        "original", "Formato", "Format",
        labels={"original": ("Original (JPEG tal cual; el resto en PNG)", "Original (JPEG as is; the rest as PNG)"),
                "png": ("PNG", "PNG"), "jpg": ("JPG", "JPG")})
    min_px: int = opt(32, "Ignorar imágenes de menos de (px)", "Ignore images smaller than (px)", ge=0, le=10000, advanced=True)
    eliminar_duplicadas: bool = opt(True, "Eliminar duplicadas", "Remove duplicates", advanced=True)


class MetadatosOptions(BaseModel):
    """Vacío deja el valor que ya tiene cada archivo; la web rellena el formulario con los del primero."""

    titulo: str = opt("", "Título", "Title", max_length=1000)
    autor: str = opt("", "Autor", "Author", max_length=1000)
    asunto: str = opt("", "Asunto", "Subject", max_length=2000)
    palabras_clave: str = opt("", "Palabras clave", "Keywords", max_length=2000)
    fecha_creacion: str = opt("", "Fecha de creación (AAAA-MM-DD HH:MM:SS)", "Creation date (YYYY-MM-DD HH:MM:SS)",
                              max_length=40, pattern=DATE_PATTERN)
    fecha_modificacion: str = opt("", "Fecha de modificación (AAAA-MM-DD HH:MM:SS)", "Modification date (YYYY-MM-DD HH:MM:SS)",
                                  max_length=40, pattern=DATE_PATTERN)
    creador: str = opt("", "Creador", "Creator", max_length=1000, advanced=True)
    productor: str = opt("", "Productor", "Producer", max_length=1000, advanced=True)


class RasterizarOptions(BaseModel):
    dpi: int = opt(144, "Resolución (ppp; más de 300 solo en Pro)", "Resolution (dpi; over 300 Pro only)", ge=10, le=600)
    calidad: int = opt(75, "Calidad (%)", "Quality (%)", ge=1, le=100)
    color: Literal["sin_cambios", "gris", "bn"] = opt(
        "sin_cambios", "Color", "Colour",
        labels={"sin_cambios": ("Sin cambios", "Unchanged"), "gris": ("Gris", "Grey"), "bn": ("Blanco y negro de 1 bit", "1-bit black and white")})


class PreferenciasVisorOptions(BaseModel):
    """A.7: todas empiezan en «No cambiar»."""

    quitar_todas: bool = opt(False, "Quitar todas las preferencias actuales", "Remove all current preferences")
    diseno: Literal["no_cambiar", "SinglePage", "OneColumn", "TwoColumnLeft", "TwoColumnRight", "TwoPageLeft", "TwoPageRight"] = opt(
        "no_cambiar", "Diseño de página", "Page layout",
        labels={"no_cambiar": KEEP[1:], "SinglePage": ("Una página", "Single page"), "OneColumn": ("Una columna continua", "One column"),
                "TwoColumnLeft": ("Dos columnas, impares a la izquierda", "Two columns, odd on the left"),
                "TwoColumnRight": ("Dos columnas, impares a la derecha", "Two columns, odd on the right"),
                "TwoPageLeft": ("Dos páginas, impares a la izquierda", "Two pages, odd on the left"),
                "TwoPageRight": ("Dos páginas, impares a la derecha", "Two pages, odd on the right")})
    modo: Literal["no_cambiar", "UseNone", "UseOutlines", "UseThumbs", "FullScreen", "UseOC", "UseAttachments"] = opt(
        "no_cambiar", "Al abrir, mostrar", "On opening, show",
        labels={"no_cambiar": KEEP[1:], "UseNone": ("Solo la página", "Just the page"), "UseOutlines": ("Marcadores", "Bookmarks"),
                "UseThumbs": ("Miniaturas", "Thumbnails"), "FullScreen": ("Pantalla completa", "Full screen"),
                "UseOC": ("Capas", "Layers"), "UseAttachments": ("Adjuntos", "Attachments")})
    pagina_inicial: int = opt(0, "Página inicial (0 = no cambiar)", "Initial page (0 = no change)", ge=0, le=100000)
    zoom_inicial: Literal["no_cambiar", "Fit", "FitH", "FitV", "personalizado"] = opt(
        "no_cambiar", "Zoom inicial", "Initial zoom",
        labels={"no_cambiar": KEEP[1:], "Fit": ("Página completa", "Whole page"), "FitH": ("Ajustar al ancho", "Fit width"),
                "FitV": ("Ajustar al alto", "Fit height"), "personalizado": ("Personalizado", "Custom")})
    zoom_porcentaje: int = opt(100, "Zoom (%)", "Zoom (%)", ge=10, le=6400, show_if={"zoom_inicial": ("personalizado",)})
    centrar_ventana: Literal["no_cambiar", "si", "no"] = opt("no_cambiar", "Centrar la ventana", "Centre the window", advanced=True, labels=TRI)
    ajustar_ventana: Literal["no_cambiar", "si", "no"] = opt("no_cambiar", "Ajustar la ventana a la página", "Fit the window to the page", advanced=True, labels=TRI)
    mostrar_titulo: Literal["no_cambiar", "si", "no"] = opt("no_cambiar", "Mostrar el título del documento", "Display the document title", advanced=True, labels=TRI)
    ocultar_menu: Literal["no_cambiar", "si", "no"] = opt("no_cambiar", "Ocultar la barra de menús", "Hide the menu bar", advanced=True, labels=TRI)
    ocultar_barra: Literal["no_cambiar", "si", "no"] = opt("no_cambiar", "Ocultar la barra de herramientas", "Hide the toolbar", advanced=True, labels=TRI)
    ocultar_controles: Literal["no_cambiar", "si", "no"] = opt("no_cambiar", "Ocultar los controles de la ventana", "Hide the window controls", advanced=True, labels=TRI)
    modo_no_pantalla_completa: Literal["no_cambiar", "UseNone", "UseOutlines", "UseThumbs", "UseOC"] = opt(
        "no_cambiar", "Al salir de pantalla completa, mostrar", "After leaving full screen, show", advanced=True,
        labels={"no_cambiar": KEEP[1:], "UseNone": ("Solo la página", "Just the page"), "UseOutlines": ("Marcadores", "Bookmarks"),
                "UseThumbs": ("Miniaturas", "Thumbnails"), "UseOC": ("Capas", "Layers")})
    duplex: Literal["no_cambiar", "Simplex", "DuplexFlipShortEdge", "DuplexFlipLongEdge"] = opt(
        "no_cambiar", "Impresión a doble cara", "Duplex printing", advanced=True,
        labels={"no_cambiar": KEEP[1:], "Simplex": ("Una cara", "Single-sided"), "DuplexFlipShortEdge": ("Doble cara, borde corto", "Duplex, short edge"),
                "DuplexFlipLongEdge": ("Doble cara, borde largo", "Duplex, long edge")})
    area_impresion: Literal["no_cambiar", "MediaBox", "CropBox", "BleedBox", "TrimBox", "ArtBox"] = opt("no_cambiar", "Área de impresión", "Print area", advanced=True, labels=BOXES)
    recorte_impresion: Literal["no_cambiar", "MediaBox", "CropBox", "BleedBox", "TrimBox", "ArtBox"] = opt("no_cambiar", "Recorte de impresión", "Print clip", advanced=True, labels=BOXES)
    area_vista: Literal["no_cambiar", "MediaBox", "CropBox", "BleedBox", "TrimBox", "ArtBox"] = opt("no_cambiar", "Área de vista", "View area", advanced=True, labels=BOXES)
    recorte_vista: Literal["no_cambiar", "MediaBox", "CropBox", "BleedBox", "TrimBox", "ArtBox"] = opt("no_cambiar", "Recorte de vista", "View clip", advanced=True, labels=BOXES)
    escalado_impresion: Literal["no_cambiar", "None", "AppDefault"] = opt(
        "no_cambiar", "Escalado al imprimir", "Print scaling", advanced=True,
        labels={"no_cambiar": KEEP[1:], "None": ("Ninguno (tamaño real)", "None (actual size)"), "AppDefault": ("El del lector", "Reader default")})
    direccion: Literal["no_cambiar", "L2R", "R2L"] = opt(
        "no_cambiar", "Dirección de lectura", "Reading direction", advanced=True,
        labels={"no_cambiar": KEEP[1:], "L2R": ("De izquierda a derecha", "Left to right"), "R2L": ("De derecha a izquierda", "Right to left")})


class PdfATiffOptions(BaseModel):
    """A.9, imagen: TIFF con tiffcp; CMYK con LittleCMS y el perfil FOGRA39 (D-60)."""

    color: Literal["color", "cmyk", "gris", "bn"] = opt(
        "color", "Color", "Colour",
        labels={"color": ("RGB, 24 bits", "RGB, 24-bit"), "cmyk": ("CMYK, 32 bits (perfil FOGRA39)", "CMYK, 32-bit (FOGRA39 profile)"),
                "gris": ("Gris, 8 bits", "Greyscale, 8-bit"), "bn": ("Blanco y negro, 1 bit", "Black and white, 1-bit")})
    compresion_bn: Literal["g4", "g3_1d", "g3_1d_eol", "g3_2d", "lzw", "packbits"] = opt(
        "g4", "Compresión en blanco y negro", "Black and white compression", show_if={"color": ("bn",)},
        labels={"g4": ("CCITT G4", "CCITT G4"), "g3_1d": ("CCITT G3 1D", "CCITT G3 1D"),
                "g3_1d_eol": ("CCITT G3 1D con EOL alineado", "CCITT G3 1D with aligned EOL"), "g3_2d": ("CCITT G3 2D", "CCITT G3 2D"),
                "lzw": ("LZW", "LZW"), "packbits": ("PackBits", "PackBits")})
    dpi: int = opt(144, "Resolución (ppp)", "Resolution (dpi)", ge=72, le=600)
    multipagina: bool = opt(True, "TIFF multipágina", "Multi-page TIFF")
    paginas: str = opt("todas", "Páginas", "Pages")
    salida: Literal["una_por_pagina", "una_sola"] = opt(
        "una_por_pagina", "Salida", "Output", advanced=True,
        labels={"una_por_pagina": ("Una imagen por página", "One image per page"),
                "una_sola": ("Una sola imagen con todas las páginas", "One image with all pages")})


class PdfASvgOptions(BaseModel):
    paginas: str = opt("todas", "Páginas", "Pages")


class PdfATxtOptions(BaseModel):
    # A.9 (D-261): en texto plano no hay gráficos que pasar a imagen; quedan los otros dos modos del Anexo.
    modo: Literal["editable", "fiel"] = opt("editable", "Modo", "Mode", labels={
        "editable": ("Editable: el texto en su orden de lectura", "Editable: text in reading order"),
        "fiel": ("Fiel al diseño: columnas y sangrías con espacios, como en el papel", "Faithful layout: columns and indents with spaces, as on paper")})
    paginas: str = opt("todas", "Páginas", "Pages")
    ocr_si_no_hay_texto: bool = opt(True, "OCR automático si no hay texto (cuenta como tarea de OCR)",
                                    "Automatic OCR if there is no text (counts as an OCR task)")
    idiomas: list[str] = opt(["spa"], "Idiomas del OCR", "OCR languages", min_length=1, max_length=3, advanced=True,
                             show_if={"ocr_si_no_hay_texto": (True,)})
    separador: Literal["salto", "linea", "ninguno"] = opt(
        "salto", "Separación entre páginas", "Page separator", advanced=True,
        labels={"salto": ("Salto de página", "Page break"), "linea": ("Línea con el número de página", "Line with the page number"),
                "ninguno": ("Una línea en blanco", "A blank line")})

    @field_validator("idiomas")
    @classmethod
    def _codes(cls, v: list[str]) -> list[str]:
        import re

        for code in v:
            if not re.match(r"^[a-z]{3}(_[a-z]+)?$", code):
                raise ValueError(f"Código de idioma no válido: {code}")
        return v


def _txt_route(options: dict) -> tuple[str, str]:
    """Con OCR automático va a `workerocr` (Tesseract); sin él, basta pypdfium2 en `workerpdf`."""
    return ("ocr", "ocr") if options.get("ocr_si_no_hay_texto", True) else ("pdf", "pdf")


def pdf_tool(slug_es, slug_en, name_es, name_en, options, impl, summary_es, summary_en, **kw) -> ToolSpec:
    return ToolSpec(slug_es=slug_es, slug_en=slug_en, name_es=name_es, name_en=name_en, category="pdf", where="server",
                    inputs=kw.pop("inputs", ("pdf",)), outputs=kw.pop("outputs", ("pdf", "zip")), options=options,
                    worker_group="pdf", cost_class="light", impl=impl, launch=True, phase="F2",
                    time_limit=kw.pop("time_limit", 900), summary_es=summary_es, summary_en=summary_en, **kw)


SPECS: list[ToolSpec] = [
    ToolSpec(
        slug_es="comprimir-pdf", slug_en="compress-pdf", name_es="Comprimir PDF", name_en="Compress PDF",
        category="pdf", where="server", inputs=("pdf",), outputs=("pdf", "zip"), options=ComprimirOptions,
        worker_group="pdf", cost_class="light", impl="tools.pdf.comprimir_pdf:run", launch=True,
        secret_fields=("contrasena",), time_limit=900,
        summary_es="Reduce el tamaño de tus PDF recomprimiendo imágenes y limpiando lo que sobra.",
        summary_en="Make your PDFs smaller by recompressing images and removing what is not needed.",
        related=("unir-pdf", "pdf-a-jpg", "proteger-pdf"),
    ),
    ToolSpec(
        slug_es="proteger-pdf", slug_en="protect-pdf", name_es="Proteger PDF con contraseña", name_en="Password protect PDF",
        category="pdf", where="server", inputs=("pdf",), outputs=("pdf", "zip"), options=ProtegerOptions,
        worker_group="pdf", cost_class="light", impl="tools.pdf.proteger_pdf:run", launch=True, phase="F2",
        secret_fields=("contrasena_apertura", "contrasena_propietario"), time_limit=600,
        summary_es="Cifra tu PDF con AES-256 y decide qué se puede hacer con él.",
        summary_en="Encrypt your PDF with AES-256 and choose what can be done with it.",
        related=("desbloquear-pdf", "marca-de-agua-pdf"),
    ),
    ToolSpec(
        slug_es="desbloquear-pdf", slug_en="unlock-pdf", name_es="Desbloquear PDF", name_en="Unlock PDF",
        category="pdf", where="server", inputs=("pdf",), outputs=("pdf", "zip"), options=DesbloquearOptions,
        worker_group="pdf", cost_class="light", impl="tools.pdf.desbloquear_pdf:run", launch=True, phase="F2",
        secret_fields=("contrasena",), time_limit=600,
        summary_es="Quita la contraseña y las restricciones de un PDF del que conoces la contraseña.",
        summary_en="Remove the password and restrictions from a PDF whose password you know.",
        related=("proteger-pdf",),
    ),
    pdf_tool("reparar-pdf", "repair-pdf", "Reparar PDF", "Repair PDF", SinOpciones, "tools.pdf.mantenimiento:run_repair",
             "Recupera PDF dañados: reconstruye la estructura y, si hace falta, salva las páginas legibles.",
             "Recover damaged PDFs: rebuild the structure and, if needed, save the readable pages.", related=("comprimir-pdf",)),
    pdf_tool("optimizar-pdf-web", "optimize-pdf-for-web", "Optimizar PDF para la web", "Optimize PDF for web", WebOptions,
             "tools.pdf.mantenimiento:run_web", "Linealiza el PDF para que la primera página se vea mientras se descarga el resto.",
             "Linearise the PDF so the first page shows while the rest downloads.", related=("comprimir-pdf",)),
    pdf_tool("pdf-escala-de-grises", "grayscale-pdf", "PDF a escala de grises", "Grayscale PDF", GrisOptions,
             "tools.pdf.colores_tools:run_gray", "Pasa un PDF a gris sin convertirlo en imagen: el texto se puede seguir buscando.",
             "Turn a PDF grey without making it an image: the text stays searchable.", related=("pdf-modo-oscuro", "comprimir-pdf")),
    pdf_tool("pdf-modo-oscuro", "dark-mode-pdf", "PDF en modo oscuro", "Dark mode PDF", OscuroOptions,
             "tools.pdf.colores_tools:run_dark", "Fondo oscuro y texto claro para leer de noche; el texto sigue siendo texto.",
             "Dark background and light text for reading at night; the text stays text.", related=("pdf-escala-de-grises",)),
    pdf_tool("extraer-imagenes-pdf", "extract-images-from-pdf", "Extraer imágenes de un PDF", "Extract images from PDF",
             ExtraerImagenesOptions, "tools.pdf.mantenimiento:run_extract_images",
             "Saca todas las imágenes de un PDF en un ZIP, con los JPEG tal cual.", "Get every image out of a PDF in a ZIP, with JPEGs as they are.",
             outputs=("zip",), related=("pdf-a-imagenes",)),
    pdf_tool("metadatos-pdf", "pdf-metadata", "Editar metadatos de un PDF", "Edit PDF metadata", MetadatosOptions,
             "tools.pdf.documento:run_edit", "Cambia título, autor, asunto, palabras clave y fechas; se sincroniza con XMP.",
             "Change title, author, subject, keywords and dates; kept in sync with XMP.", related=("eliminar-metadatos-pdf",)),
    pdf_tool("eliminar-metadatos-pdf", "remove-pdf-metadata", "Eliminar metadatos de un PDF", "Remove PDF metadata", SinOpciones,
             "tools.pdf.documento:run_remove", "Quita autor, fechas, programa y XMP; antes te enseña lo que va a borrar.",
             "Remove author, dates, software and XMP; it shows you first what will be deleted.", related=("metadatos-pdf", "redactar-pdf")),
    pdf_tool("rasterizar-pdf", "rasterize-pdf", "Rasterizar PDF", "Rasterize PDF", RasterizarOptions, "tools.pdf.mantenimiento:run_rasterize",
             "Convierte cada página en imagen dentro del PDF, en color, gris o blanco y negro.",
             "Turn every page into an image inside the PDF, in colour, grey or black and white.", related=("aplanar-pdf", "comprimir-pdf")),
    pdf_tool("preferencias-visor-pdf", "pdf-viewer-preferences", "Preferencias de visualización del PDF", "PDF viewer preferences",
             PreferenciasVisorOptions, "tools.pdf.documento:run_viewer",
             "Elige cómo se abre el PDF: diseño, panel, página y zoom iniciales y opciones de impresión.",
             "Choose how the PDF opens: layout, panel, initial page and zoom, and print options.", related=("metadatos-pdf",)),
    pdf_tool("pdf-a-tiff", "pdf-to-tiff", "PDF a TIFF", "PDF to TIFF", PdfATiffOptions, "tools.pdf.desde_pdf:run_tiff",
             "Convierte el PDF en TIFF multipágina, en color, CMYK, gris o blanco y negro con G4.",
             "Turn a PDF into a multi-page TIFF, in colour, CMYK, grey or black and white with G4.",
             outputs=("tiff", "zip"), related=("tiff-a-pdf", "pdf-a-imagenes")),
    pdf_tool("pdf-a-svg", "pdf-to-svg", "PDF a SVG", "PDF to SVG", PdfASvgOptions, "tools.pdf.desde_pdf:run_svg",
             "Convierte cada página del PDF en un SVG vectorial.", "Turn each PDF page into a vector SVG.",
             outputs=("svg", "zip"), related=("svg-a-pdf", "pdf-a-imagenes")),
    pdf_tool("pdf-a-txt", "pdf-to-txt", "PDF a TXT", "PDF to TXT", PdfATxtOptions, "tools.pdf.texto:run",
             "Saca el texto del PDF a un archivo TXT, con OCR para las páginas escaneadas.",
             "Extract the text of a PDF to a TXT file, with OCR for scanned pages.",
             outputs=("txt", "zip"), related=("ocr-pdf", "pdf-a-word"), route=_txt_route),
]
