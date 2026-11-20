"""Conversión a PDF con Gotenberg (7.3 y A.8)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.options import PAPERS, WebUrl, opt
from core.registry import NoOptions, ToolSpec

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


class EscribirOptions(BaseModel):
    """escribir-pdf (A.1, F6-O1, D-234): página [A4, 25 mm], letra [Noto Serif], encabezado, pie con números de página,
    marca de agua, borde, membrete (el PDF de fondo se sube con el documento) y propiedades del documento."""

    papel: ChromiumPaper = opt("A4", "Papel", "Paper", labels=CHROMIUM_PAPERS)
    orientacion: Literal["vertical", "horizontal"] = opt("vertical", "Orientación", "Orientation", labels=ORIENTATION)
    margenes_mm: float = opt(25, "Márgenes (mm)", "Margins (mm)", ge=5, le=50)
    fuente: Literal["serif", "sans", "mono"] = opt("serif", "Letra del texto", "Body font", labels={
        "serif": ("Con remates (Noto Serif)", "Serif (Noto Serif)"), "sans": ("Sin remates (Noto Sans)", "Sans serif (Noto Sans)"),
        "mono": ("Monoespaciada (Noto Sans Mono)", "Monospace (Noto Sans Mono)")})
    encabezado: str = opt("", "Encabezado", "Header", max_length=200)
    pie: str = opt("", "Pie de página", "Footer", max_length=200)
    numeros_pagina: Literal["pie", "encabezado", "ninguno"] = opt("pie", "Números de página", "Page numbers", labels={
        "pie": ("En el pie", "In the footer"), "encabezado": ("En el encabezado", "In the header"), "ninguno": ("Sin números", "No numbers")})
    formato_numero: Literal["n_de_total", "n"] = opt("n_de_total", "Formato del número", "Number format", advanced=True,
                                                     labels={"n_de_total": ("3 / 10", "3 / 10"), "n": ("3", "3")},
                                                     show_if={"numeros_pagina": ("pie", "encabezado")})
    marca_agua: str = opt("", "Marca de agua", "Watermark", max_length=60, advanced=True)
    borde: Literal["ninguno", "fino", "doble"] = opt("ninguno", "Borde de página", "Page border", advanced=True, labels={
        "ninguno": ("Sin borde", "No border"), "fino": ("Fino", "Thin"), "doble": ("Doble", "Double")})
    membrete: Literal["todas", "primera"] = opt("todas", "Membrete en", "Letterhead on", advanced=True, labels={
        "todas": ("Todas las páginas", "Every page"), "primera": ("Solo la primera", "First page only")})
    titulo: str = opt("", "Título del documento", "Document title", max_length=200, advanced=True)
    autor: str = opt("", "Autor", "Author", max_length=200, advanced=True)
    asunto: str = opt("", "Asunto", "Subject", max_length=300, advanced=True)
    palabras_clave: str = opt("", "Palabras clave", "Keywords", max_length=300, advanced=True)
    idioma: Literal["es", "en"] = opt("es", "Idioma del documento", "Document language", advanced=True,
                                      labels={"es": ("Español", "Spanish"), "en": ("Inglés", "English")})


class LibroFormatoOptions(BaseModel):
    """epub-a-mobi, epub-a-azw3, mobi-a-epub y azw3-a-epub (F6-C, D-237): título y autor nuevos (opcionales) y EPUB [3] | 2."""

    titulo: str = opt("", "Título (déjalo vacío para conservarlo)", "Title (leave empty to keep it)", max_length=200, advanced=True)
    autor: str = opt("", "Autor (déjalo vacío para conservarlo)", "Author (leave empty to keep it)", max_length=200, advanced=True)
    epub3: bool = opt(True, "EPUB 3 (desmarcado, EPUB 2 para lectores antiguos)", "EPUB 3 (unticked, EPUB 2 for old readers)", advanced=True)


class DiapositivasImagenesOptions(BaseModel):
    """pptx-a-imagenes (F6-C, D-237): formato [PNG] | JPG, resolución [150 ppp] y diapositivas (todas o un rango)."""

    formato: Literal["png", "jpg"] = opt("png", "Formato", "Format", labels={"png": ("PNG", "PNG"), "jpg": ("JPG", "JPG")})
    resolucion: Literal[96, 150, 200, 300] = opt(150, "Resolución", "Resolution", labels={
        "96": ("96 ppp (pantalla)", "96 dpi (screen)"), "150": ("150 ppp", "150 dpi"), "200": ("200 ppp", "200 dpi"), "300": ("300 ppp (imprimir)", "300 dpi (print)")})
    diapositivas: str = opt("", "Diapositivas (vacío: todas; p. ej., 1-3, 5)", "Slides (empty: all; e.g. 1-3, 5)", max_length=200, advanced=True)


class DiapositivasVideoOptions(BaseModel):
    """pptx-a-video (F6-C, D-237): segundos por diapositiva [5], resolución [1080p], fundido [sí] y formato [WebM VP9] | MP4 AV1."""

    segundos: int = opt(5, "Segundos por diapositiva", "Seconds per slide", ge=1, le=60)
    resolucion: Literal["720", "1080"] = opt("1080", "Resolución", "Resolution", labels={"720": ("720p (1280 × 720)", "720p (1280 × 720)"), "1080": ("1080p (1920 × 1080)", "1080p (1920 × 1080)")})
    transicion: bool = opt(True, "Fundido entre diapositivas", "Fade between slides")
    formato: Literal["webm", "mp4"] = opt("webm", "Formato", "Format", labels={
        "webm": ("WebM (VP9: navegadores, YouTube)", "WebM (VP9: browsers, YouTube)"), "mp4": ("MP4 (AV1: reproductores modernos)", "MP4 (AV1: modern players)")})
    diapositivas: str = opt("", "Diapositivas (vacío: todas; p. ej., 1-3, 5)", "Slides (empty: all; e.g. 1-3, 5)", max_length=200, advanced=True)


class CapturaOptions(BaseModel):
    """captura-web (7.13, F6-M, D-229): formato [PNG] | JPG, ancho de ventana [1280], alto [800], página completa [sí],
    espera [1 s], esquema [claro] y calidad del JPG [85]. La URL se comprueba en la API (12.2)."""

    url: WebUrl = opt(..., "Dirección de la página", "Page address", max_length=2048)
    formato: Literal["png", "jpg"] = opt("png", "Formato", "Format", labels={"png": ("PNG (sin pérdida)", "PNG (lossless)"),
                                                                        "jpg": ("JPG (más ligero)", "JPG (lighter)")})
    ancho: Literal[375, 768, 1280, 1920] = opt(1280, "Ancho de la ventana", "Window width", labels={
        375: ("375 px (móvil)", "375 px (phone)"), 768: ("768 px (tableta)", "768 px (tablet)"),
        1280: ("1280 px (portátil)", "1280 px (laptop)"), 1920: ("1920 px (pantalla grande)", "1920 px (large screen)")})
    alto: int = opt(800, "Alto de la ventana (px)", "Window height (px)", ge=300, le=4000, advanced=True)
    pagina_completa: bool = opt(True, "Toda la página, no solo lo visible", "The whole page, not just what is visible")
    espera_s: float = opt(1, "Espera antes de capturar (s)", "Wait before capture (s)", ge=0, le=10, advanced=True)
    esquema: Literal["claro", "oscuro"] = opt("claro", "Esquema de color", "Colour scheme", advanced=True,
                                              labels={"claro": ("Claro", "Light"), "oscuro": ("Oscuro", "Dark")})
    calidad: int = opt(85, "Calidad del JPG", "JPG quality", ge=40, le=100, advanced=True, show_if={"formato": ("jpg",)})


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
    # 7.13 (F6-C, D-237): Calibre, como epub-a-pdf; un libro con DRM se rechaza antes de convertirlo.
    *[office(f"{a}-a-{b}", f"{a}-to-{b}", f"{la} a {lb}", f"{la} to {lb}", (a,),
             f"Convierte libros {la} a {lb} para leerlos en {'Kindle' if b in ('mobi', 'azw3') else 'cualquier lector de EPUB'}.",
             f"Convert {la} books to {lb} to read them on {'Kindle' if b in ('mobi', 'azw3') else 'any EPUB reader'}.",
             options=LibroFormatoOptions, impl="tools.office.libros_formato:run", secret_fields=(), outputs=(b, "zip"), phase="F6",
             category="convert", queue_kind="heavy", related=(f"{a}-a-pdf", f"{b}-a-pdf") if b != "epub" else (f"{a}-a-pdf", "epub-a-pdf"))
      for a, b, la, lb in (("epub", "mobi", "EPUB", "MOBI"), ("epub", "azw3", "EPUB", "AZW3"), ("mobi", "epub", "MOBI", "EPUB"),
                           ("azw3", "epub", "AZW3", "EPUB"))],
    # 7.13 (F6-C, D-237): LibreOffice de Gotenberg a PDF y cada diapositiva con pypdfium2.
    office("pptx-a-imagenes", "pptx-to-images", "PowerPoint a imágenes", "PowerPoint to images", ("pptx", "ppt", "odp"),
           "Convierte cada diapositiva de una presentación en una imagen PNG o JPG con la resolución que elijas.",
           "Turn each slide of a presentation into a PNG or JPG image at the resolution you choose.",
           options=DiapositivasImagenesOptions, impl="tools.office.diapositivas:run_images", secret_fields=(), outputs=("png", "jpg", "zip"),
           phase="F6", category="image", related=("ppt-a-pdf", "pptx-a-video")),
    # A.1 (F6-O1, D-234): el editor está en la página; aquí llega su HTML (y, si se elige, el PDF de membrete).
    office("escribir-pdf", "write-pdf", "Escribir PDF", "Write PDF", ("html", "pdf"),
           "Escribe documentos con títulos, tablas, imágenes, fórmulas e índice y descárgalos en PDF, Word o Markdown.",
           "Write documents with headings, tables, images, formulas and a table of contents and download them as PDF, Word or Markdown.",
           options=EscribirOptions, impl="tools.office.escribir:run", secret_fields=(), outputs=("pdf",), phase="F6", category="pdf",
           max_files=2, time_limit=600, related=("html-a-pdf", "markdown-a-pdf", "word-a-pdf")),
    # 7.13 (F6-M, D-229): como web-a-pdf, por gotenbergweb y egressweb; nunca recibe archivos de usuarios.
    office("captura-web", "website-screenshot", "Captura web", "Website screenshot", (),
           "Haz una captura de una página web entera, a partir de su dirección, en PNG o JPG, como en móvil o en ordenador.",
           "Take a screenshot of a whole web page from its address, as PNG or JPG, as on a phone or a computer.",
           options=CapturaOptions, impl="tools.office.captura:run", secret_fields=(), outputs=("png", "jpg"), phase="F6",
           category="image", time_limit=300, related=("web-a-pdf", "comprimir-imagen")),
    # 7.23 (F6-M, D-229): formato sin especificación pública; apagada hasta probarla con documentos reales de UYAP.
    office("udf-a-pdf", "udf-to-pdf", "UDF a PDF", "UDF to PDF", ("udf",),
           "Convierte documentos UDF del editor de UYAP (Turquía) en PDF, con su texto, formato y tablas.",
           "Turn UDF documents from the UYAP editor (Turkey) into PDF, with their text, formatting and tables.",
           options=NoOptions, impl="tools.office.udf:run", secret_fields=(), phase="F6", default_enabled=False,
           related=("word-a-pdf", "convertir-a-pdf")),
    # 7.5 (F4): LibreOffice de Gotenberg con `pdfua` en `office` y, después, veraPDF (solo en la imagen worker-ocr) en `ocr`.
    office("word-a-pdf-accesible", "accessible-word-to-pdf", "Word a PDF accesible", "Accessible Word to PDF",
           ("doc", "docx", "odt", "rtf"),
           "Convierte Word a PDF/UA etiquetado, para lectores de pantalla, y comprueba con veraPDF qué falta y cómo arreglarlo.",
           "Convert Word to tagged PDF/UA for screen readers, and check with veraPDF what is missing and how to fix it.",
           options=AccesibleOptions, impl="tools.office.accesible:run", outputs=("pdf", "html", "zip"), phase="F4",
           launch=True, time_limit=1800, related=("word-a-pdf", "validar-pdfa", "pdf-a-pdfa")),
    office("csv-a-pdf", "csv-to-pdf", "CSV a PDF", "CSV to PDF", ("csv",),
           "Convierte archivos CSV a una tabla en PDF.", "Convert CSV files to a PDF table.", related=("excel-a-pdf",)),
    # 7.13 (F6-L, D-228): MuseScore 3 (GPL) como programa externo y sin interfaz, en workeroffice.
    office("musicxml-a-pdf", "musicxml-to-pdf", "MusicXML a PDF", "MusicXML to PDF", ("musicxml", "mxl", "xml"),
           "Convierte partituras MusicXML (de MuseScore, Sibelius, Finale o Dorico) en un PDF listo para imprimir.",
           "Turn MusicXML scores (from MuseScore, Sibelius, Finale or Dorico) into a print-ready PDF.",
           impl="tools.office.partitura:run", secret_fields=(), phase="F6", category="audio", time_limit=900,
           related=("midi-a-pdf", "midi-a-mp3")),
    office("midi-a-pdf", "midi-to-pdf", "MIDI a PDF", "MIDI to PDF", ("mid",),
           "Convierte archivos MIDI en una partitura en PDF, con sus pentagramas, compases y figuras.",
           "Turn MIDI files into a PDF score, with staves, bars and notes.",
           impl="tools.office.partitura:run", secret_fields=(), phase="F6", category="audio", time_limit=900,
           related=("musicxml-a-pdf", "midi-a-mp3")),
]
