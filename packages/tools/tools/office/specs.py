"""Conversión a PDF con Gotenberg (7.3 y A.8)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.options import PAPERS, WebUrl, opt
from core.registry import ToolSpec

WORD = ("doc", "docx", "rtf", "odt", "txt")
EXCEL = ("xls", "xlsx", "ods", "csv")
PPT = ("ppt", "pptx", "pps", "odp")
IMAGES = ("jpg", "png", "gif", "bmp", "tiff", "webp")
ALL_OFFICE = ("doc", "docx", "rtf", "odt", "txt", "xls", "xlsx", "ods", "csv", "ppt", "pptx", "pps", "odp", "odg")


class OfficeOptions(BaseModel):
    formato: Literal["pdf", "pdfa", "pdfua"] = opt("pdf", "Formato", "Format",
                                                 labels={"pdf": ("PDF", "PDF"), "pdfa": ("PDF/A-2b", "PDF/A-2b"), "pdfua": ("PDF/UA", "PDF/UA")})
    paginas: str = opt("todas", "Páginas", "Pages")
    marcadores: bool = opt(True, "Marcadores desde los títulos", "Bookmarks from headings", advanced=True)
    campos_formulario: bool = opt(True, "Exportar campos de formulario", "Export form fields", advanced=True)
    calidad_imagenes: int = opt(90, "Calidad de imágenes (%)", "Image quality (%)", ge=1, le=100, advanced=True)
    resolucion_maxima: Literal[75, 150, 300, 600, 1200] = opt(300, "Resolución máxima (ppp)", "Maximum resolution (dpi)", advanced=True)
    contrasena: str | None = opt(None, "Contraseña del documento", "Document password", advanced=True)
    hoja_una_pagina: bool = opt(False, "Excel: cada hoja en una sola página", "Excel: each sheet on a single page", advanced=True)
    diapositivas_ocultas: bool = opt(False, "PowerPoint: diapositivas ocultas", "PowerPoint: hidden slides", advanced=True)
    paginas_notas: bool = opt(False, "PowerPoint: páginas de notas", "PowerPoint: notes pages", advanced=True)
    comentarios_margen: bool = opt(False, "Word: comentarios en el margen", "Word: comments in margin", advanced=True)


ChromiumPaper = Literal["A3", "A4", "A5", "Letter", "Legal"]
CHROMIUM_PAPERS = {k: v for k, v in PAPERS.items() if k in ("A3", "A4", "A5", "Letter", "Legal")}
ORIENTATION = {"vertical": ("Vertical", "Portrait"), "horizontal": ("Horizontal", "Landscape")}
MEDIA = {"print": ("Impresión (print)", "Print"), "screen": ("Pantalla (screen)", "Screen")}


class HtmlOptions(BaseModel):
    """html-a-pdf (7.3): Chromium de `gotenberg`, sin red."""

    papel: ChromiumPaper = opt("A4", "Papel", "Paper", labels=CHROMIUM_PAPERS)
    orientacion: Literal["vertical", "horizontal"] = opt("vertical", "Orientación", "Orientation", labels=ORIENTATION)
    margenes_mm: float = opt(10, "Márgenes (mm)", "Margins (mm)", ge=0, le=50)
    imprimir_fondos: bool = opt(True, "Imprimir fondos", "Print backgrounds", advanced=True)
    una_pagina: bool = opt(False, "Una sola página larga", "One long page", advanced=True)
    medio: Literal["print", "screen"] = opt("print", "Tipo de medio", "Media type", advanced=True, labels=MEDIA)
    tamano_css: bool = opt(False, "Usar el tamaño de página del CSS (@page)", "Use the CSS page size (@page)", advanced=True)


class MarkdownOptions(BaseModel):
    """markdown-a-pdf (A.8): GitHub Flavored con markdown-it y Chromium."""

    tema: Literal["claro", "sobrio"] = opt("claro", "Tema", "Theme", labels={"claro": ("Claro", "Light"), "sobrio": ("Sobrio", "Sober")})
    papel: ChromiumPaper = opt("A4", "Papel", "Paper", labels=CHROMIUM_PAPERS)


class TxtOptions(BaseModel):
    """txt-a-pdf (A.8): la codificación se detecta sola (charset-normalizer)."""

    fuente: Literal["monoespaciada", "proporcional"] = opt("monoespaciada", "Fuente", "Font",
                                                         labels={"monoespaciada": ("Monoespaciada", "Monospaced"),
                                                                 "proporcional": ("Proporcional", "Proportional")})
    papel: ChromiumPaper = opt("A4", "Papel", "Paper", labels=CHROMIUM_PAPERS)
    margenes_mm: float = opt(20, "Márgenes (mm)", "Margins (mm)", ge=0, le=50)


class WebAPdfOptions(BaseModel):
    """web-a-pdf (A.1): campos de la ruta Chromium de Gotenberg; la URL se comprueba en la API (12.2)."""

    url: WebUrl = opt(..., "Dirección de la página o del documento", "Page or document address", max_length=2048)
    papel: ChromiumPaper = opt("A4", "Papel", "Paper", advanced=True, labels=CHROMIUM_PAPERS)
    orientacion: Literal["vertical", "horizontal"] = opt("vertical", "Orientación", "Orientation", advanced=True, labels=ORIENTATION)
    margenes_mm: float = opt(10, "Márgenes (mm)", "Margins (mm)", ge=0, le=50, advanced=True)
    imprimir_fondos: bool = opt(True, "Imprimir fondos", "Print backgrounds", advanced=True)
    una_pagina: bool = opt(False, "Una sola página larga", "One long page", advanced=True)
    medio: Literal["print", "screen"] = opt("print", "Tipo de medio", "Media type", advanced=True, labels=MEDIA)
    espera_s: float = opt(1, "Espera antes de capturar (s)", "Wait before capture (s)", ge=0, le=10, advanced=True)
    esquema: Literal["claro", "oscuro"] = opt("claro", "Esquema de color", "Colour scheme", advanced=True,
                                              labels={"claro": ("Claro", "Light"), "oscuro": ("Oscuro", "Dark")})


LANGS_UA = {"documento": ("El que declara el documento", "The one the document declares"), "es-ES": ("Español", "Spanish"),
            "en-GB": ("Inglés (Reino Unido)", "English (UK)"), "en-US": ("Inglés (Estados Unidos)", "English (US)"),
            "ca-ES": ("Catalán", "Catalan"), "eu-ES": ("Euskera", "Basque"), "gl-ES": ("Gallego", "Galician"),
            "fr-FR": ("Francés", "French"), "de-DE": ("Alemán", "German"), "it-IT": ("Italiano", "Italian"),
            "pt-PT": ("Portugués", "Portuguese")}


class AccesibleOptions(BaseModel):
    """word-a-pdf-accesible (7.5): las de A.8 Office para Word con el formato fijado a PDF/UA (D-182)."""

    paginas: str = opt("todas", "Páginas", "Pages")
    titulo: str = opt("", "Título del documento (si el archivo no tiene)", "Document title (if the file has none)", max_length=300)
    idioma: Literal[tuple(LANGS_UA)] = opt("documento", "Idioma principal del texto", "Main text language", labels=LANGS_UA)
    marcadores: bool = opt(True, "Marcadores desde los títulos", "Bookmarks from headings", advanced=True)
    campos_formulario: bool = opt(True, "Exportar campos de formulario", "Export form fields", advanced=True)
    calidad_imagenes: int = opt(90, "Calidad de imágenes (%)", "Image quality (%)", ge=1, le=100, advanced=True)
    resolucion_maxima: Literal[75, 150, 300, 600, 1200] = opt(300, "Resolución máxima (ppp)", "Maximum resolution (dpi)", advanced=True)
    contrasena: str | None = opt(None, "Contraseña del documento", "Document password", advanced=True)
    comentarios_margen: bool = opt(False, "Word: comentarios en el margen", "Word: comments in margin", advanced=True)


class SuperponerOptions(BaseModel):
    """superponer-pdf (A.3): el primer archivo es la superposición y los demás, los documentos."""

    posicion: Literal["fondo", "primer_plano"] = opt(
        "fondo", "Posición", "Position",
        labels={"fondo": ("Fondo (detrás del contenido)", "Background (behind the content)"), "primer_plano": ("Primer plano (encima)", "Foreground (on top)")})
    repetir_ultima: bool = opt(True, "Repetir la última página de la superposición", "Repeat the last overlay page")
    aplicar_a: Literal["todas", "primera", "rango"] = opt(
        "todas", "Aplicar a", "Apply to", advanced=True,
        labels={"todas": ("Todas las páginas", "All pages"), "primera": ("Solo la primera", "First page only"), "rango": ("Un rango", "A range")})
    rango: str = opt("", "Páginas", "Pages", advanced=True, max_length=200, show_if={"aplicar_a": ("rango",)})
    escalar: bool = opt(True, "Escalar al tamaño de cada página", "Scale to each page size", advanced=True)


class SvgOptions(BaseModel):
    """svg-a-pdf (A.8)."""

    tamano: Literal["svg", "a4"] = opt("svg", "Tamaño de la página", "Page size",
                                       labels={"svg": ("El del SVG (vectorial)", "The SVG's own (vector)"), "a4": ("Encajado en A4", "Fitted in A4")})


class LibroOptions(BaseModel):
    """epub-a-pdf, mobi-a-pdf, azw3-a-pdf y fb2-a-pdf (A.8) con Calibre."""

    papel: Literal["A5", "A4", "Letter"] = opt("A5", "Papel", "Paper", labels={"A5": ("A5", "A5"), "A4": ("A4", "A4"), "Letter": ("Carta", "Letter")})
    margenes_mm: float = opt(15, "Márgenes (mm)", "Margins (mm)", ge=0, le=50)
    tamano_letra: int = opt(12, "Tamaño de letra base (pt)", "Base font size (pt)", ge=6, le=36)
    indice: bool = opt(True, "Índice al principio", "Table of contents at the start")


class SolicitudOptions(BaseModel):
    """solicitud-de-empleo-pdf (A.1): carta (opcional), CV y adjuntos, en el orden elegido."""

    primera_es_carta: bool = opt(True, "El primer archivo es la carta de presentación", "The first file is the cover letter")
    marcadores: bool = opt(True, "Un marcador por documento", "One bookmark per document")
    indice: bool = opt(False, "Índice inicial", "Table of contents at the start", advanced=True)
    comprimir: bool = opt(True, "Comprimir si supera el tamaño", "Compress if over the size", advanced=True)
    umbral_mb: float = opt(10, "Tamaño máximo antes de comprimir (MB)", "Size before compressing (MB)", ge=1, le=500, advanced=True,
                           show_if={"comprimir": (True,)})


def office(slug_es, slug_en, name_es, name_en, inputs, summary_es, summary_en, launch=True, **kw) -> ToolSpec:
    return ToolSpec(slug_es=slug_es, slug_en=slug_en, name_es=name_es, name_en=name_en, category=kw.pop("category", "office"), where="server",
                    inputs=inputs, outputs=kw.pop("outputs", ("pdf", "zip")), options=kw.pop("options", OfficeOptions),
                    worker_group="office", cost_class="light", queue_kind=kw.pop("queue_kind", "light"), impl=kw.pop("impl", "tools.office.office_a_pdf:run"),
                    launch=launch, secret_fields=kw.pop("secret_fields", ("contrasena",)), time_limit=kw.pop("time_limit", 900),
                    summary_es=summary_es, summary_en=summary_en, **kw)


SPECS: list[ToolSpec] = [
    office("convertir-a-pdf", "convert-to-pdf", "Convertir a PDF", "Convert to PDF", ALL_OFFICE + IMAGES + ("html",),
           "Convierte Word, Excel, PowerPoint, OpenDocument, imágenes y HTML a PDF.",
           "Convert Word, Excel, PowerPoint, OpenDocument, images and HTML to PDF.",
           launch=True, impl="tools.office.convertir_a_pdf:run", related=("word-a-pdf", "imagenes-a-pdf", "comprimir-pdf")),
    office("word-a-pdf", "word-to-pdf", "Word a PDF", "Word to PDF", ("doc", "docx"),
           "Convierte documentos DOC y DOCX a PDF conservando el formato.", "Convert DOC and DOCX documents to PDF keeping the layout.",
           launch=True, related=("pdf-a-word", "word-a-pdf-accesible", "comprimir-pdf")),
    office("excel-a-pdf", "excel-to-pdf", "Excel a PDF", "Excel to PDF", ("xls", "xlsx"),
           "Convierte hojas de cálculo XLS y XLSX a PDF.", "Convert XLS and XLSX spreadsheets to PDF.", launch=True, related=("word-a-pdf",)),
    office("ppt-a-pdf", "powerpoint-to-pdf", "PowerPoint a PDF", "PowerPoint to PDF", ("ppt", "pptx", "pps"),
           "Convierte presentaciones PPT y PPTX a PDF.", "Convert PPT and PPTX presentations to PDF.", launch=True, related=("word-a-pdf",)),
    office("odt-a-pdf", "odt-to-pdf", "ODT a PDF", "ODT to PDF", ("odt",),
           "Convierte documentos de OpenDocument Texto a PDF.", "Convert OpenDocument Text files to PDF.", related=("word-a-pdf",)),
    office("ods-a-pdf", "ods-to-pdf", "ODS a PDF", "ODS to PDF", ("ods",),
           "Convierte hojas de cálculo ODS a PDF.", "Convert ODS spreadsheets to PDF.", related=("excel-a-pdf",)),
    office("odp-a-pdf", "odp-to-pdf", "ODP a PDF", "ODP to PDF", ("odp",),
           "Convierte presentaciones ODP a PDF.", "Convert ODP presentations to PDF.", related=("ppt-a-pdf",)),
    office("odg-a-pdf", "odg-to-pdf", "ODG a PDF", "ODG to PDF", ("odg",),
           "Convierte dibujos de OpenDocument a PDF.", "Convert OpenDocument drawings to PDF.", related=("convertir-a-pdf",)),
    office("rtf-a-pdf", "rtf-to-pdf", "RTF a PDF", "RTF to PDF", ("rtf",),
           "Convierte documentos RTF a PDF.", "Convert RTF documents to PDF.", related=("word-a-pdf",)),
    office("txt-a-pdf", "txt-to-pdf", "TXT a PDF", "TXT to PDF", ("txt",),
           "Convierte archivos de texto a PDF, con la codificación detectada automáticamente.",
           "Convert text files to PDF, with the encoding detected automatically.",
           options=TxtOptions, impl="tools.office.chromium_a_pdf:run_txt", secret_fields=(), related=("markdown-a-pdf", "convertir-a-pdf")),
    office("html-a-pdf", "html-to-pdf", "HTML a PDF", "HTML to PDF", ("html", "zip"),
           "Convierte una página HTML, o un ZIP con la página y sus recursos, a PDF. Los recursos de internet no se cargan.",
           "Convert an HTML page, or a ZIP with the page and its assets, to PDF. Resources from the internet are not loaded.",
           options=HtmlOptions, impl="tools.office.chromium_a_pdf:run_html", secret_fields=(), related=("web-a-pdf", "markdown-a-pdf")),
    office("markdown-a-pdf", "markdown-to-pdf", "Markdown a PDF", "Markdown to PDF", ("md",),
           "Convierte Markdown con tablas, listas de tareas y código resaltado a un PDF limpio.",
           "Convert Markdown with tables, task lists and highlighted code to a clean PDF.",
           options=MarkdownOptions, impl="tools.office.chromium_a_pdf:run_markdown", secret_fields=(), related=("html-a-pdf", "txt-a-pdf")),
    office("superponer-pdf", "overlay-pdf", "Superponer PDF (membrete)", "Overlay PDF (letterhead)", ("pdf",) + ALL_OFFICE + IMAGES,
           "Pon un membrete o una capa de fondo o encima de tus documentos. El primer archivo es la superposición.",
           "Put a letterhead or a layer behind or on top of your documents. The first file is the overlay.",
           options=SuperponerOptions, impl="tools.office.superponer:run", secret_fields=(), phase="F2", category="pdf",
           related=("marca-de-agua-pdf", "unir-pdf")),
    office("svg-a-pdf", "svg-to-pdf", "SVG a PDF", "SVG to PDF", ("svg",),
           "Convierte SVG en PDF vectorial, con su tamaño o encajado en A4.", "Convert SVG to vector PDF, at its size or fitted in A4.",
           options=SvgOptions, impl="tools.office.varios:run_svg", secret_fields=(), phase="F2", related=("imagenes-a-pdf", "dxf-a-pdf")),
    office("pages-a-pdf", "pages-to-pdf", "Pages a PDF", "Pages to PDF", ("pages",),
           "Convierte documentos de Apple Pages a PDF (importación parcial).", "Convert Apple Pages documents to PDF (partial import).",
           impl="tools.office.varios:run_partial", phase="F2", related=("word-a-pdf",)),
    office("keynote-a-pdf", "keynote-to-pdf", "Keynote a PDF", "Keynote to PDF", ("key",),
           "Convierte presentaciones de Apple Keynote a PDF (importación parcial).", "Convert Apple Keynote presentations to PDF (partial import).",
           impl="tools.office.varios:run_partial", phase="F2", related=("ppt-a-pdf",)),
    office("numbers-a-pdf", "numbers-to-pdf", "Numbers a PDF", "Numbers to PDF", ("numbers",),
           "Convierte hojas de Apple Numbers a PDF (importación parcial).", "Convert Apple Numbers spreadsheets to PDF (partial import).",
           impl="tools.office.varios:run_partial", phase="F2", related=("excel-a-pdf",)),
    office("visio-a-pdf", "visio-to-pdf", "Visio a PDF", "Visio to PDF", ("vsd", "vsdx"),
           "Convierte diagramas de Visio a PDF (importación parcial).", "Convert Visio diagrams to PDF (partial import).",
           impl="tools.office.varios:run_partial", phase="F2", related=("convertir-a-pdf",)),
    office("publisher-a-pdf", "publisher-to-pdf", "Publisher a PDF", "Publisher to PDF", ("pub",),
           "Convierte publicaciones de Microsoft Publisher a PDF (importación parcial).",
           "Convert Microsoft Publisher files to PDF (partial import).", impl="tools.office.varios:run_partial", phase="F2",
           related=("word-a-pdf",)),
    office("pub-a-pdf", "pub-to-pdf", "PUB a PDF", "PUB to PDF", ("pub",),
           "Convierte archivos PUB de Publisher a PDF.", "Convert Publisher PUB files to PDF.", impl="tools.office.varios:run_partial",
           phase="F2", canonical_of="publisher-a-pdf", related=("publisher-a-pdf",)),
    *[office(f"{fmt}-a-pdf", f"{fmt}-to-pdf", f"{label} a PDF", f"{label} to PDF", (fmt,),
             f"Convierte libros {label} a PDF con el papel, los márgenes y la letra que elijas.",
             f"Convert {label} books to PDF with the paper, margins and font size you choose.",
             options=LibroOptions, impl="tools.office.libros:run", secret_fields=(), phase="F2", queue_kind="heavy",
             related=("epub-a-pdf", "comprimir-pdf"))
      for fmt, label in (("epub", "EPUB"), ("mobi", "MOBI"), ("azw3", "AZW3"), ("fb2", "FB2"))],
    office("solicitud-de-empleo-pdf", "job-application-pdf", "Solicitud de empleo en PDF", "Job application PDF",
           ("pdf",) + ALL_OFFICE + IMAGES,
           "Une carta, CV y adjuntos (Word, imágenes o PDF) en un solo PDF con un marcador por documento.",
           "Combine cover letter, CV and attachments (Word, images or PDF) into one PDF with a bookmark per document.",
           options=SolicitudOptions, impl="tools.office.varios:run_job_application", secret_fields=(), phase="F2", category="pdf",
           related=("unir-pdf", "comprimir-pdf")),
    office("web-a-pdf", "web-to-pdf", "Web a PDF", "Web to PDF", (),
           "Guarda una página web en PDF a partir de su dirección. Si la dirección es un documento, se convierte.",
           "Save a web page as PDF from its address. If the address is a document, it is converted.",
           options=WebAPdfOptions, impl="tools.office.web_a_pdf:run", secret_fields=(), outputs=("pdf",),
           time_limit=300, related=("html-a-pdf", "convertir-a-pdf")),
    # 7.5 (F4): LibreOffice de Gotenberg con `pdfua` en `office` y, después, veraPDF (solo en la imagen worker-ocr) en `ocr`.
    office("word-a-pdf-accesible", "accessible-word-to-pdf", "Word a PDF accesible", "Accessible Word to PDF",
           ("doc", "docx", "odt", "rtf"),
           "Convierte Word a PDF/UA etiquetado, para lectores de pantalla, y comprueba con veraPDF qué falta y cómo arreglarlo.",
           "Convert Word to tagged PDF/UA for screen readers, and check with veraPDF what is missing and how to fix it.",
           options=AccesibleOptions, impl="tools.office.accesible:run", outputs=("pdf", "html", "zip"), phase="F4",
           launch=True, time_limit=1800, related=("word-a-pdf", "validar-pdfa", "pdf-a-pdfa")),
    office("csv-a-pdf", "csv-to-pdf", "CSV a PDF", "CSV to PDF", ("csv",),
           "Convierte archivos CSV a una tabla en PDF.", "Convert CSV files to a PDF table.", related=("excel-a-pdf",)),
]
