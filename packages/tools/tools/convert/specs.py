"""Convertir desde PDF con Docling (7.4 y A.9): Word, ODT, RTF, Excel, ODS, PowerPoint, ODP, Markdown, HTML, EPUB, CSV
y JSON, y la página única convertir-desde-pdf, cuyo formulario cambia según el formato de salida."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, create_model, field_validator

from core.options import opt
from core.registry import ToolSpec

MODES = {"editable": ("Editable", "Editable"),
         "editable_imagenes": ("Editable con gráficos vectoriales como imágenes", "Editable with vector graphics as images"),
         "fiel": ("Fiel al diseño (se edita peor)", "Faithful layout (harder to edit)")}
LAYOUTS = {"auto": ("Automático", "Automatic"), "fijo": ("Fijo: cada página tal cual, con texto seleccionable", "Fixed: each page as it looks, with selectable text"),
           "fluido": ("Fluido: el texto se adapta a la pantalla", "Flowing: text adapts to the screen")}


def _languages(v: list[str]) -> list[str]:
    for code in v:
        if not re.match(r"^[a-z]{3}(_[a-z]+)?$", code):
            raise ValueError(f"Código de idioma no válido: {code}")
    return v


def _pages():
    return opt("todas", "Páginas", "Pages")


def _ocr():
    return opt(True, "OCR automático si no hay texto", "Automatic OCR if there is no text", advanced=True)


def _ocr_languages():
    return opt(["spa"], "Idiomas del OCR", "OCR languages", min_length=1, max_length=3, advanced=True,
               show_if={"ocr_si_no_hay_texto": (True,)})


class _Languages(BaseModel):
    @field_validator("idiomas", check_fields=False)
    @classmethod
    def _codes(cls, v: list[str]) -> list[str]:
        return _languages(v)


class PdfAWordOptions(_Languages):
    modo: Literal["editable", "editable_imagenes", "fiel"] = opt("editable", "Modo", "Mode", labels=MODES)
    paginas: str = _pages()
    ocr_si_no_hay_texto: bool = _ocr()
    idiomas: list[str] = _ocr_languages()


class PdfADocumentoOptions(PdfAWordOptions):
    """pdf-a-odt y pdf-a-rtf: lo mismo que pdf-a-word."""


class PdfAPresentacionOptions(_Languages):
    """pdf-a-ppt y pdf-a-odp: una diapositiva por página."""

    modo: Literal["editable", "editable_imagenes", "fiel"] = opt(
        "editable", "Modo", "Mode",
        labels={**MODES, "editable_imagenes": ("Editable con la página sin texto de fondo", "Editable with the text-free page as background")})
    paginas: str = _pages()
    ocr_si_no_hay_texto: bool = _ocr()
    idiomas: list[str] = _ocr_languages()


class PdfAHojaOptions(_Languages):
    """pdf-a-excel y pdf-a-ods (A.9, D-261): modo [editable: las tablas con Docling], editable con las imágenes en su hoja,
    o fiel al diseño (una hoja por página con cada texto en su fila y su columna)."""

    modo: Literal["editable", "editable_imagenes", "fiel"] = opt("editable", "Modo", "Mode", labels={
        "editable": ("Editable: las tablas, reconstruidas", "Editable: the tables, rebuilt"),
        "editable_imagenes": ("Editable, con las imágenes y gráficos en una hoja aparte", "Editable, with images and charts on a separate sheet"),
        "fiel": ("Fiel al diseño: cada página en una hoja, con el texto en su sitio (se edita peor)",
                 "Faithful layout: each page on a sheet, text in place (harder to edit)")})

    hojas: Literal["una_por_tabla", "todas_en_una"] = opt(
        "una_por_tabla", "Hojas", "Sheets",
        labels={"una_por_tabla": ("Una hoja por tabla", "One sheet per table"), "todas_en_una": ("Todas las tablas en una hoja", "All tables in one sheet")})
    numeros: bool = opt(True, "Convertir los números (1.234,56) en números de verdad", "Turn numbers (1,234.56) into real numbers", advanced=True)
    paginas: str = _pages()
    ocr_si_no_hay_texto: bool = _ocr()
    idiomas: list[str] = _ocr_languages()


class PdfAMarkdownOptions(_Languages):
    imagenes: Literal["incluidas", "sin"] = opt(
        "incluidas", "Imágenes", "Images",
        labels={"incluidas": ("Incluidas, en un ZIP", "Included, in a ZIP"), "sin": ("Sin imágenes", "Without images")})
    quitar_encabezados: bool = opt(True, "Quitar encabezados y pies de página repetidos", "Remove repeated headers and footers")
    paginas: str = _pages()
    ocr_si_no_hay_texto: bool = _ocr()
    idiomas: list[str] = _ocr_languages()


class PdfAHtmlOptions(_Languages):
    """pdf-a-html y pdf-a-epub."""

    diseno: Literal["auto", "fijo", "fluido"] = opt("auto", "Diseño", "Layout", labels=LAYOUTS)
    paginas: str = _pages()
    ocr_si_no_hay_texto: bool = _ocr()
    idiomas: list[str] = _ocr_languages()


class PdfACsvOptions(_Languages):
    delimitador: Literal["coma", "punto_y_coma", "tabulador"] = opt(
        "coma", "Separador", "Delimiter",
        labels={"coma": ("Coma (,)", "Comma (,)"), "punto_y_coma": ("Punto y coma (;), para Excel en español", "Semicolon (;), for Excel in Spanish"),
                "tabulador": ("Tabulador", "Tab")})
    codificacion: Literal["utf-8-sig", "utf-8"] = opt(
        "utf-8-sig", "Codificación", "Encoding", advanced=True,
        labels={"utf-8-sig": ("UTF-8 con BOM (Excel)", "UTF-8 with BOM (Excel)"), "utf-8": ("UTF-8", "UTF-8")})
    paginas: str = _pages()
    ocr_si_no_hay_texto: bool = _ocr()
    idiomas: list[str] = _ocr_languages()


class PdfAJsonOptions(_Languages):
    contenido: Literal["tablas", "documento"] = opt(
        "tablas", "Contenido", "Content",
        labels={"tablas": ("Las tablas", "The tables"), "documento": ("El documento entero (estructura de Docling)", "The whole document (Docling structure)")})
    paginas: str = _pages()
    ocr_si_no_hay_texto: bool = _ocr()
    idiomas: list[str] = _ocr_languages()


class CopiarOptions(_Languages):
    """copiar-de-pdf (A.4): los escaneos pasan antes por ocr-pdf desde la web; aquí solo el OCR de Docling, opcional."""

    ocr_si_no_hay_texto: bool = opt(False, "OCR de las zonas sin texto", "OCR of areas without text", advanced=True)
    idiomas: list[str] = _ocr_languages()


def _office_route(options: dict) -> tuple[str, str]:
    if options.get("modo") == "fiel":
        return "office", "office.heavy"
    return "convert", "convert"


def convert_tool(slug_es, slug_en, name_es, name_en, options, impl, outputs, summary_es, summary_en, **kw) -> ToolSpec:
    return ToolSpec(slug_es=slug_es, slug_en=slug_en, name_es=name_es, name_en=name_en, category="pdf", where="server",
                    inputs=("pdf",), outputs=outputs, options=options, worker_group="convert", cost_class="heavy", impl=impl,
                    launch=True, phase="F2", time_limit=3600, summary_es=summary_es, summary_en=summary_en, **kw)


SPECS: list[ToolSpec] = [
    convert_tool("pdf-a-word", "pdf-to-word", "PDF a Word", "PDF to Word", PdfAWordOptions, "tools.convert.pdf_a_word:run", ("docx", "zip"),
                 "Convierte un PDF en un documento de Word editable.", "Turn a PDF into an editable Word document.",
                 related=("word-a-pdf", "ocr-pdf"), route=_office_route),
    convert_tool("pdf-a-odt", "pdf-to-odt", "PDF a ODT", "PDF to ODT", PdfADocumentoOptions, "tools.convert.oficina:run_text", ("odt", "zip"),
                 "Convierte un PDF en un documento de texto de LibreOffice (ODT) editable.",
                 "Turn a PDF into an editable LibreOffice text document (ODT).", related=("pdf-a-word", "odt-a-pdf")),
    convert_tool("pdf-a-rtf", "pdf-to-rtf", "PDF a RTF", "PDF to RTF", PdfADocumentoOptions, "tools.convert.oficina:run_text", ("rtf", "zip"),
                 "Convierte un PDF en un documento RTF que abre cualquier procesador de textos.",
                 "Turn a PDF into an RTF document that any word processor can open.", related=("pdf-a-word", "rtf-a-pdf")),
    convert_tool("pdf-a-excel", "pdf-to-excel", "PDF a Excel", "PDF to Excel", PdfAHojaOptions, "tools.convert.oficina:run_sheet", ("xlsx", "zip"),
                 "Pasa las tablas de un PDF a una hoja de Excel, con los números como números.",
                 "Move the tables of a PDF into an Excel sheet, with numbers as numbers.", related=("pdf-a-csv", "excel-a-pdf")),
    convert_tool("pdf-a-ods", "pdf-to-ods", "PDF a ODS", "PDF to ODS", PdfAHojaOptions, "tools.convert.oficina:run_sheet", ("ods", "zip"),
                 "Pasa las tablas de un PDF a una hoja de cálculo de LibreOffice (ODS).",
                 "Move the tables of a PDF into a LibreOffice spreadsheet (ODS).", related=("pdf-a-excel", "pdf-a-csv")),
    convert_tool("pdf-a-ppt", "pdf-to-ppt", "PDF a PowerPoint", "PDF to PowerPoint", PdfAPresentacionOptions, "tools.convert.oficina:run_slides",
                 ("pptx", "zip"), "Convierte cada página del PDF en una diapositiva de PowerPoint editable.",
                 "Turn each PDF page into an editable PowerPoint slide.", related=("ppt-a-pdf", "pdf-a-odp")),
    convert_tool("pdf-a-odp", "pdf-to-odp", "PDF a ODP", "PDF to ODP", PdfAPresentacionOptions, "tools.convert.oficina:run_slides", ("odp", "zip"),
                 "Convierte cada página del PDF en una diapositiva de LibreOffice Impress (ODP).",
                 "Turn each PDF page into a LibreOffice Impress slide (ODP).", related=("pdf-a-ppt",)),
    convert_tool("pdf-a-markdown", "pdf-to-markdown", "PDF a Markdown", "PDF to Markdown", PdfAMarkdownOptions, "tools.convert.web:run_markdown",
                 ("md", "zip"), "Convierte un PDF en Markdown con títulos, listas, tablas e imágenes.",
                 "Turn a PDF into Markdown with headings, lists, tables and images.", related=("markdown-a-pdf", "pdf-a-html")),
    convert_tool("pdf-a-html", "pdf-to-html", "PDF a HTML", "PDF to HTML", PdfAHtmlOptions, "tools.convert.web:run_html", ("html", "zip"),
                 "Convierte un PDF en una página web, con diseño fijo o fluido.",
                 "Turn a PDF into a web page, with a fixed or flowing layout.", related=("html-a-pdf", "pdf-a-markdown")),
    convert_tool("pdf-a-epub", "pdf-to-epub", "PDF a EPUB", "PDF to EPUB", PdfAHtmlOptions, "tools.convert.web:run_epub", ("epub", "zip"),
                 "Convierte un PDF en un libro electrónico EPUB para leer en el móvil o en un lector.",
                 "Turn a PDF into an EPUB e-book to read on your phone or e-reader.", related=("epub-a-pdf", "pdf-a-html")),
    convert_tool("pdf-a-csv", "pdf-to-csv", "PDF a CSV", "PDF to CSV", PdfACsvOptions, "tools.convert.datos:run_csv", ("csv", "zip"),
                 "Saca las tablas de un PDF a archivos CSV.", "Extract the tables of a PDF to CSV files.", related=("pdf-a-excel", "pdf-a-json")),
    convert_tool("pdf-a-json", "pdf-to-json", "PDF a JSON", "PDF to JSON", PdfAJsonOptions, "tools.convert.datos:run_json", ("json", "zip"),
                 "Saca las tablas o la estructura de un PDF a JSON.", "Extract the tables or the structure of a PDF to JSON.",
                 related=("pdf-a-csv",)),
    ToolSpec(slug_es="copiar-de-pdf", slug_en="copy-from-pdf", name_es="Copiar de PDF", name_en="Copy from PDF", category="pdf",
             where="hybrid", inputs=("pdf",), outputs=("json", "md", "xlsx"), options=CopiarOptions, worker_group="convert",
             cost_class="heavy", impl="tools.convert.copiar:run", launch=True, phase="F2", time_limit=1800, max_files=1,
             summary_es="Copia párrafos, títulos, listas y tablas de un PDF con un clic, con formato para Word, Excel o correo.",
             summary_en="Copy paragraphs, headings, lists and tables from a PDF with one click, formatted for Word, Excel or email.",
             related=("pdf-a-word", "pdf-a-excel", "ocr-pdf")),
]


# --- convertir-desde-pdf --------------------------------------------------------------------------------------------

# Formato de salida → herramienta que lo hace (A.9). La página única delega en ella con las mismas opciones.
FORMATS: dict[str, str] = {
    "docx": "pdf-a-word", "xlsx": "pdf-a-excel", "pptx": "pdf-a-ppt", "odt": "pdf-a-odt", "ods": "pdf-a-ods", "odp": "pdf-a-odp",
    "rtf": "pdf-a-rtf", "txt": "pdf-a-txt", "html": "pdf-a-html", "epub": "pdf-a-epub", "md": "pdf-a-markdown", "csv": "pdf-a-csv",
    "json": "pdf-a-json", "jpg": "pdf-a-jpg", "png": "pdf-a-png", "webp": "pdf-a-webp", "tiff": "pdf-a-tiff", "svg": "pdf-a-svg",
    "pdfa": "pdf-a-pdfa",
}
FORMAT_LABELS = {"docx": ("Word (DOCX)", "Word (DOCX)"), "xlsx": ("Excel (XLSX)", "Excel (XLSX)"), "pptx": ("PowerPoint (PPTX)", "PowerPoint (PPTX)"),
                 "odt": ("ODT", "ODT"), "ods": ("ODS", "ODS"), "odp": ("ODP", "ODP"), "rtf": ("RTF", "RTF"), "txt": ("TXT", "TXT"),
                 "html": ("HTML", "HTML"), "epub": ("EPUB", "EPUB"), "md": ("Markdown", "Markdown"), "csv": ("CSV", "CSV"),
                 "json": ("JSON", "JSON"), "jpg": ("JPG", "JPG"), "png": ("PNG", "PNG"), "webp": ("WEBP", "WEBP"), "tiff": ("TIFF", "TIFF"),
                 "svg": ("SVG", "SVG"), "pdfa": ("PDF/A", "PDF/A")}
LIGHT_FORMATS = {"jpg", "png", "webp", "tiff", "svg"}
# Textos de A.9 para las opciones que comparten varios formatos.
LABEL_OVERRIDES = {"color": {"color": ("RGB, 24 bits", "RGB, 24-bit"), "cmyk": ("CMYK, 32 bits (JPG y TIFF)", "CMYK, 32-bit (JPG and TIFF)"),
                             "gris": ("Gris, 8 bits", "Greyscale, 8-bit"), "bn": ("Blanco y negro, 1 bit (PNG y TIFF)", "Black and white, 1-bit (PNG and TIFF)")}}


def _target_options() -> dict[str, type[BaseModel]]:
    from tools.client.specs import PdfAImagenesOptions
    from tools.ocr.specs import PdfaOptions
    from tools.pdf.specs import PdfASvgOptions, PdfATiffOptions, PdfATxtOptions

    local = {s.slug_es: s.options for s in SPECS}
    return {fmt: {"pdf-a-jpg": PdfAImagenesOptions, "pdf-a-png": PdfAImagenesOptions, "pdf-a-webp": PdfAImagenesOptions,
                  "pdf-a-tiff": PdfATiffOptions, "pdf-a-svg": PdfASvgOptions, "pdf-a-txt": PdfATxtOptions,
                  "pdf-a-pdfa": PdfaOptions}.get(slug) or local[slug] for fmt, slug in FORMATS.items()}


def _build_hub_options() -> type[BaseModel]:
    """Un campo por opción distinta de los formatos, visible solo con los formatos que la usan (x-show-if)."""
    from copy import deepcopy

    fields: dict[str, tuple] = {}
    formats_of: dict[str, list[str]] = {}
    for fmt, model in _target_options().items():
        for name, info in model.model_fields.items():
            if name == "formato":  # pdf-a-imagenes: aquí el formato es el de la página única
                continue
            formats_of.setdefault(name, []).append(fmt)
            if name not in fields:
                fields[name] = (info.annotation, deepcopy(info))
    for name, (_, info) in fields.items():
        extra = dict(info.json_schema_extra or {})
        own = dict(extra.get("x-show-if") or {})
        formats = formats_of[name]
        if len(formats) < len(FORMATS):
            own["formato"] = sorted(set(own["formato"]) & set(formats)) if "formato" in own else formats
        if own:
            extra["x-show-if"] = own
        if name in LABEL_OVERRIDES:
            extra["x-labels"] = {k: {"es": v[0], "en": v[1]} for k, v in LABEL_OVERRIDES[name].items()}
        info.json_schema_extra = extra
    formato = opt("docx", "Formato de salida", "Output format", labels=FORMAT_LABELS)
    model = create_model("DesdePdfOptions", __base__=_Languages,
                         formato=(Literal[tuple(FORMATS)], formato), **fields)  # type: ignore[valid-type]
    return model


DesdePdfOptions = _build_hub_options()


def _hub_route(options: dict) -> tuple[str, str]:
    from core.registry import load_registry

    spec = load_registry().require(FORMATS[options.get("formato", "docx")])
    return spec.target(options)


def _hub_cost(options: dict) -> str:
    fmt = options.get("formato", "docx")
    if fmt in LIGHT_FORMATS or (fmt == "txt" and not options.get("ocr_si_no_hay_texto", True)):
        return "light"
    return "heavy"


SPECS.append(ToolSpec(
    slug_es="convertir-desde-pdf", slug_en="convert-from-pdf", name_es="Convertir desde PDF", name_en="Convert from PDF", category="pdf",
    where="server", inputs=("pdf",), outputs=(*sorted({"pdf" if f == "pdfa" else f for f in FORMATS}), "zip"), options=DesdePdfOptions,
    worker_group="convert", cost_class="light",
    impl="tools.convert.hub:run", launch=True, phase="F2", time_limit=3600,
    summary_es="Convierte un PDF a Word, Excel, PowerPoint, ODT, imágenes, HTML, EPUB, Markdown, CSV, JSON o PDF/A desde una sola página.",
    summary_en="Convert a PDF to Word, Excel, PowerPoint, ODT, images, HTML, EPUB, Markdown, CSV, JSON or PDF/A from one page.",
    related=("pdf-a-word", "pdf-a-excel", "pdf-a-imagenes"), route=_hub_route, cost=_hub_cost,
))
