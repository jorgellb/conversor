"""Herramientas de navegador e híbridas (7.1, 7.2, 7.11, 7.23) con las opciones del Anexo A.

La lógica de las herramientas de navegador vive en `packages/client-tools` (TypeScript).
Las híbridas tienen además una implementación de servidor (`impl`).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.options import COLOR_PATTERN, FONTS, GRID9, PAPERS, opt
from core.registry import NoOptions, ToolSpec
from tools.office.specs import ALL_OFFICE, OfficeOptions
from tools.office.specs import IMAGES as OFFICE_IMAGES

PDF = ("pdf",)
IMAGES = ("jpg", "png", "webp", "gif", "bmp", "tiff")
# lector-pdf: lo que no es PDF se convierte en servidor con el motor de convertir-a-pdf (A.7).
VIEWABLE = ALL_OFFICE + OFFICE_IMAGES

Grid9 = Literal["arriba-izquierda", "arriba-centro", "arriba-derecha", "medio-izquierda", "centro",
                "medio-derecha", "abajo-izquierda", "abajo-centro", "abajo-derecha"]
Grid6 = Literal["arriba-izquierda", "arriba-centro", "arriba-derecha", "abajo-izquierda", "abajo-centro", "abajo-derecha"]
Font = Literal["sans", "serif", "mono"]
PaperName = Literal["A0", "A1", "A2", "A3", "A4", "A5", "A6", "Letter", "Legal"]


class UnirOptions(BaseModel):
    ordenar_por_nombre: bool = opt(False, "Ordenar por nombre", "Sort by name")
    rangos: list[str] = opt([], "Páginas de cada archivo", "Pages of each file", advanced=True)
    marcadores: bool = opt(False, "Marcadores por archivo", "Bookmark per file")
    paginas_en_blanco: Literal["ninguna", "tras_cada_archivo", "tras_impares"] = opt(
        "ninguna", "Páginas en blanco", "Blank pages", advanced=True,
        labels={"ninguna": ("Ninguna", "None"), "tras_cada_archivo": ("Tras cada archivo", "After each file"),
                "tras_impares": ("Solo tras los de número impar de páginas", "Only after files with an odd page count")})
    portada: bool = opt(False, "Portada con el nombre antes de cada archivo", "Cover page with the name before each file", advanced=True)
    indice: bool = opt(False, "Índice inicial con enlaces", "Table of contents with links", advanced=True)
    nombre_en_paginas: bool = opt(False, "Nombre de archivo impreso en sus páginas", "File name printed on its pages", advanced=True)
    posicion_nombre: Grid6 = opt("arriba-centro", "Posición del nombre", "Name position", advanced=True, show_if={"nombre_en_paginas": (True,)},
                                 labels={k: v for k, v in GRID9.items() if not k.startswith("medio") and k != "centro"})
    tamano_nombre: int = opt(10, "Tamaño del nombre (pt)", "Name size (pt)", advanced=True, ge=4, le=72, show_if={"nombre_en_paginas": (True,)})


class DividirOptions(BaseModel):
    modo: Literal["cada_n", "pares_impares", "mitades", "personalizado", "marcadores", "tamano", "en_blanco"] = opt(
        "cada_n", "Modo", "Mode",
        labels={"cada_n": ("Cada N páginas", "Every N pages"), "pares_impares": ("Pares e impares", "Even and odd"),
                "mitades": ("En dos mitades", "In two halves"), "personalizado": ("Personalizado", "Custom"),
                "marcadores": ("Por marcadores de primer nivel", "By top-level bookmarks"),
                "tamano": ("Por tamaño máximo", "By maximum size"), "en_blanco": ("Por páginas en blanco", "By blank pages")})
    n: int = opt(1, "Páginas por PDF", "Pages per PDF", ge=1, le=10000, show_if={"modo": ("cada_n",)})
    dividir_despues: str = opt("", "Dividir después de las páginas", "Split after pages", show_if={"modo": ("personalizado",)})
    tamano_mb: float = opt(10.0, "Tamaño máximo (MB)", "Maximum size (MB)", ge=0.1, le=2000, show_if={"modo": ("tamano",)})
    patron_nombre: str = opt("{nombre}-{n}", "Patrón de nombre de salida", "Output name pattern", advanced=True, max_length=80)


class GirarOptions(BaseModel):
    angulo: Literal[90, -90, 180] = opt(90, "Giro", "Rotation", labels={"90": ("90° horario", "90° clockwise"),
                                                                       "-90": ("90° antihorario", "90° counterclockwise"),
                                                                       "180": ("180°", "180°")})
    paginas: str = opt("todas", "Páginas", "Pages")
    por_pagina: dict[str, int] = opt({}, "Giro por página", "Rotation per page", advanced=True)
    # A.4 Extra (D-261): con Tesseract en el servidor; la web manda allí el trabajo cuando se marca.
    autoorientar: bool = opt(False, "Autoorientar (enderezar las páginas de lado o del revés; se hace en el servidor)",
                             "Auto-orient (straighten sideways or upside-down pages; done on the server)", advanced=True)


class EliminarOptions(BaseModel):
    # Obligatoria (D-135): sin páginas no hay nada que eliminar, y la web no deja empezar hasta que se rellena.
    paginas: str = opt(..., "Páginas que se eliminan", "Pages to delete", min_length=1)


class ExtraerOptions(BaseModel):
    paginas: str = opt("todas", "Páginas", "Pages")
    salida: Literal["un_pdf", "un_pdf_por_pagina"] = opt("un_pdf", "Salida", "Output",
                                                       labels={"un_pdf": ("Un PDF", "One PDF"),
                                                               "un_pdf_por_pagina": ("Un PDF por página", "One PDF per page")})


class OrganizarOptions(BaseModel):
    orden: list[int] = opt([], "Orden de las páginas", "Page order")
    invertir: bool = opt(False, "Invertir el orden", "Reverse order")
    intercalar: bool = opt(False, "Intercalar anversos y reversos (escaneo a doble cara en dos pasadas)",
                           "Interleave fronts and backs (two-pass duplex scan)", advanced=True)


class NumerarOptions(BaseModel):
    patron: str = opt("{NUM} / {CNT}", "Patrón", "Pattern", max_length=80)
    posicion: Grid9 = opt("abajo-centro", "Posición", "Position", labels=GRID9)
    fuente: Font = opt("sans", "Fuente", "Font", labels=FONTS)
    tamano: float = opt(8, "Tamaño (pt)", "Size (pt)", ge=1, le=100)
    color: str = opt("#000000", "Color", "Color", pattern=COLOR_PATTERN, advanced=True)
    opacidad: float = opt(1.0, "Opacidad", "Opacity", ge=0, le=1, advanced=True)
    angulo: float = opt(0, "Ángulo", "Angle", ge=-360, le=360, advanced=True)
    margen_x: float = opt(5, "Margen X (mm)", "Margin X (mm)", ge=0, le=200, advanced=True)
    margen_y: float = opt(5, "Margen Y (mm)", "Margin Y (mm)", ge=0, le=200, advanced=True)
    primera_pagina: int = opt(1, "Primera página numerada", "First numbered page", ge=1, advanced=True)
    primer_numero: int = opt(1, "Primer número", "First number", ge=0, advanced=True)
    ultima_pagina: int | None = opt(None, "Última página numerada", "Last numbered page", ge=1, advanced=True)
    total_fijo: int | None = opt(None, "Total mostrado en {CNT}", "Total shown in {CNT}", ge=0, advanced=True)
    espejo: bool = opt(False, "Posición en espejo para pares e impares", "Mirror position on even and odd pages", advanced=True)
    estilo: Literal["arabigo", "romano", "letras"] = opt("arabigo", "Estilo", "Style", advanced=True,
                                                         labels={"arabigo": ("1, 2, 3", "1, 2, 3"), "romano": ("i, ii, iii", "i, ii, iii"),
                                                                 "letras": ("a, b, c", "a, b, c")})


class MarcaAguaOptions(BaseModel):
    tipo: Literal["texto", "imagen"] = opt("texto", "Tipo", "Type", labels={"texto": ("Texto", "Text"), "imagen": ("Imagen", "Image")})
    texto: str = opt("CONFIDENCIAL", "Texto", "Text", max_length=200, show_if={"tipo": ("texto",)})
    escala_imagen: float = opt(50, "Escala de la imagen (%)", "Image scale (%)", ge=1, le=400, show_if={"tipo": ("imagen",)})
    fuente: Font = opt("sans", "Fuente", "Font", labels=FONTS, show_if={"tipo": ("texto",)})
    tamano: float = opt(40, "Tamaño (pt)", "Size (pt)", ge=1, le=500, show_if={"tipo": ("texto",)})
    color: str = opt("#E67610", "Color", "Color", pattern=COLOR_PATTERN, advanced=True)
    opacidad: float = opt(0.4, "Opacidad", "Opacity", ge=0, le=1, advanced=True)
    angulo: float = opt(-45, "Ángulo", "Angle", ge=-360, le=360, advanced=True)
    posicion: Literal["arriba-izquierda", "arriba-centro", "arriba-derecha", "medio-izquierda", "centro",
                      "medio-derecha", "abajo-izquierda", "abajo-centro", "abajo-derecha", "mosaico"] = opt(
        "centro", "Posición", "Position", labels={**GRID9, "mosaico": ("Mosaico (rellenar página)", "Tile (fill page)")})
    espacio_x: float = opt(5, "Espacio X (mm)", "Spacing X (mm)", ge=0, le=500, advanced=True, show_if={"posicion": ("mosaico",)})
    espacio_y: float = opt(5, "Espacio Y (mm)", "Spacing Y (mm)", ge=0, le=500, advanced=True, show_if={"posicion": ("mosaico",)})
    paginas: str = opt("todas", "Páginas", "Pages", advanced=True)
    capa: Literal["encima", "debajo"] = opt("encima", "Capa", "Layer", advanced=True,
                                            labels={"encima": ("Encima del contenido", "Above content"),
                                                    "debajo": ("Debajo del contenido", "Below content")})
    aplanar: bool = opt(False, "Aplanar las páginas para dificultar que se quite", "Flatten pages so it is harder to remove", advanced=True)


class EditarOptions(BaseModel):
    """editar-pdf (A.3): el contenido se edita en pantalla; estas opciones son las de empezar en blanco."""

    tamano_pagina_nueva: PaperName = opt("A4", "Tamaño de la página en blanco", "Blank page size", labels=PAPERS)
    orientacion_nueva: Literal["vertical", "horizontal"] = opt("vertical", "Orientación de la página en blanco", "Blank page orientation",
                                                               labels={"vertical": ("Vertical", "Portrait"), "horizontal": ("Horizontal", "Landscape")})


class RellenarOptions(BaseModel):
    guardar: Literal["editable", "aplanado"] = opt("editable", "Guardar", "Save as",
                                                    labels={"editable": ("Editable", "Editable"),
                                                            "aplanado": ("Aplanado (los campos dejan de poder editarse)", "Flattened (fields can no longer be edited)")})


class CampoFirma(BaseModel):
    """Un campo de firma vacío que añade pyHanko (A.3): página desde 1 y rectángulo en el espacio de usuario."""

    nombre: str = opt("Firma", "Nombre del campo", "Field name", min_length=1, max_length=120, pattern=r"^[^.\x00-\x1f]+$")
    pagina: int = opt(1, "Página", "Page", ge=1, le=10000)
    x1: float = opt(0, "x1", "x1", ge=-14400, le=14400)
    y1: float = opt(0, "y1", "y1", ge=-14400, le=14400)
    x2: float = opt(100, "x2", "x2", ge=-14400, le=14400)
    y2: float = opt(40, "y2", "y2", ge=-14400, le=14400)


class HacerRellenableOptions(BaseModel):
    """hacer-pdf-rellenable y crear-formulario-pdf (A.3, F4-B1): los campos se diseñan en pantalla y pdf-lib los crea en
    el navegador; la ruta de servidor solo recibe los campos de firma, que crea pyHanko."""

    firmas: list[CampoFirma] = opt([], "Campos de firma", "Signature fields", advanced=True, max_length=50)


class CrearFacturaOptions(BaseModel):
    """crear-factura (A.2, F4-E1): esquema de lo que ofrece el diseñador propio de la página (plantilla, IVA de cada
    concepto, recargo, IRPF, moneda e idioma), que tiene su formulario y manda la factura entera (`invoice`) y el logotipo
    (`logo`); estas opciones no se leen por separado."""

    plantilla: Literal["clasica", "moderna", "minima"] = opt("clasica", "Plantilla", "Template", labels={
        "clasica": ("Clásica", "Classic"), "moderna": ("Moderna", "Modern"), "minima": ("Mínima", "Minimal")})
    iva: Literal["21", "10", "4", "0"] = opt("21", "IVA de cada concepto", "VAT of each item",
                                             labels={v: (f"{v} %", f"{v} %") for v in ("21", "10", "4", "0")})
    recargo: bool = opt(False, "Recargo de equivalencia", "Equivalence surcharge")
    irpf: Literal["0", "7", "15", "personalizada"] = opt("0", "Retención de IRPF", "Income tax withholding", labels={
        "0": ("No", "No"), "7": ("7 %", "7 %"), "15": ("15 %", "15 %"), "personalizada": ("Personalizada", "Custom")})
    irpf_personalizada: float = opt(19, "Retención personalizada (%)", "Custom withholding (%)", ge=0, le=50,
                                    show_if={"irpf": ("personalizada",)})
    moneda: str = opt("EUR", "Moneda (ISO 4217)", "Currency (ISO 4217)", pattern=r"^[A-Z]{3}$", max_length=3)
    idioma: Literal["es", "en"] = opt("es", "Idioma de la factura", "Invoice language", labels={"es": ("Español", "Spanish"), "en": ("Inglés", "English")})


class RecortarOptions(BaseModel):
    izquierda: float = opt(0, "Izquierda (mm)", "Left (mm)", ge=0, le=1000, show_if={"automatico": (False,)})
    superior: float = opt(0, "Superior (mm)", "Top (mm)", ge=0, le=1000, show_if={"automatico": (False,)})
    derecha: float = opt(0, "Derecha (mm)", "Right (mm)", ge=0, le=1000, show_if={"automatico": (False,)})
    inferior: float = opt(0, "Inferior (mm)", "Bottom (mm)", ge=0, le=1000, show_if={"automatico": (False,)})
    caja: Literal["CropBox", "TrimBox"] = opt("CropBox", "Caja", "Box", advanced=True,
                                              labels={"CropBox": ("CropBox (lo que se ve)", "CropBox (what is shown)"),
                                                      "TrimBox": ("TrimBox (corte de imprenta)", "TrimBox (print trim)")})
    modo_visual: bool = opt(False, "Modo visual (rectángulo sobre la vista previa)", "Visual mode (rectangle on the preview)",
                            show_if={"automatico": (False,)})
    paginas: str = opt("todas", "Páginas", "Pages")
    automatico: bool = opt(False, "Recortar automáticamente los márgenes blancos", "Automatically crop white margins")
    margen_seguridad: float = opt(2, "Margen de seguridad (mm)", "Safety margin (mm)", ge=0, le=50, show_if={"automatico": (True,)})
    pares_distintos: bool = opt(False, "Márgenes distintos en las páginas pares", "Different margins on even pages", advanced=True,
                                show_if={"automatico": (False,)})
    izquierda_pares: float = opt(0, "Izquierda en pares (mm)", "Left on even pages (mm)", ge=0, le=1000, advanced=True, show_if={"pares_distintos": (True,)})
    superior_pares: float = opt(0, "Superior en pares (mm)", "Top on even pages (mm)", ge=0, le=1000, advanced=True, show_if={"pares_distintos": (True,)})
    derecha_pares: float = opt(0, "Derecha en pares (mm)", "Right on even pages (mm)", ge=0, le=1000, advanced=True, show_if={"pares_distintos": (True,)})
    inferior_pares: float = opt(0, "Inferior en pares (mm)", "Bottom on even pages (mm)", ge=0, le=1000, advanced=True, show_if={"pares_distintos": (True,)})


class CambiarTamanoOptions(BaseModel):
    tamano: Literal["A0", "A1", "A2", "A3", "A4", "A5", "A6", "Letter", "Legal", "personalizado"] = opt(
        "A4", "Tamaño", "Size", labels={**PAPERS, "personalizado": ("Personalizado", "Custom")})
    ancho: float = opt(210, "Ancho", "Width", gt=0, le=5000, show_if={"tamano": ("personalizado",)})
    alto: float = opt(297, "Alto", "Height", gt=0, le=5000, show_if={"tamano": ("personalizado",)})
    unidad: Literal["mm", "in"] = opt("mm", "Unidad", "Unit", labels={"mm": ("mm", "mm"), "in": ("pulgadas", "inches")},
                                      show_if={"tamano": ("personalizado",)})
    orientacion: Literal["auto", "vertical", "horizontal"] = opt("auto", "Orientación", "Orientation",
                                                               labels={"auto": ("Automática", "Automatic"), "vertical": ("Vertical", "Portrait"),
                                                                       "horizontal": ("Horizontal", "Landscape")})
    paginas: str = opt("todas", "Páginas", "Pages")
    contenido: Literal["escalar", "centrar"] = opt("escalar", "Contenido", "Content", advanced=True,
                                                  labels={"escalar": ("Escalar para encajar", "Scale to fit"),
                                                          "centrar": ("Centrar sin escalar", "Centre without scaling")})


class VariasPorHojaOptions(BaseModel):
    por_hoja: Literal[2, 3, 4, 6, 8, 9, 12, 16] = opt(2, "Páginas por hoja", "Pages per sheet",
                                                       labels={str(n): (str(n), str(n)) for n in (2, 3, 4, 6, 8, 9, 12, 16)})
    orden: Literal["horizontal", "vertical"] = opt("horizontal", "Orden", "Order",
                                                   labels={"horizontal": ("Por filas", "By rows"), "vertical": ("Por columnas", "By columns")})
    hoja: PaperName = opt("A4", "Hoja", "Sheet", labels=PAPERS)
    orientacion: Literal["auto", "vertical", "horizontal"] = opt("auto", "Orientación", "Orientation",
                                                               labels={"auto": ("Automática", "Automatic"), "vertical": ("Vertical", "Portrait"),
                                                                       "horizontal": ("Horizontal", "Landscape")})
    margenes: int = opt(0, "Márgenes (%)", "Margins (%)", ge=0, le=50, advanced=True)
    direccion: Literal["ltr", "rtl"] = opt("ltr", "Dirección", "Direction", advanced=True,
                                           labels={"ltr": ("De izquierda a derecha", "Left to right"), "rtl": ("De derecha a izquierda", "Right to left")})
    bordes: bool = opt(False, "Bordes", "Borders", advanced=True)
    color_borde: str = opt("#000000", "Color del borde", "Border colour", pattern=COLOR_PATTERN, advanced=True, show_if={"bordes": (True,)})
    ancho_borde: float = opt(0.5, "Ancho del borde (pt)", "Border width (pt)", ge=0.1, le=10, advanced=True, show_if={"bordes": (True,)})


class FolletoOptions(BaseModel):
    papel: Literal["a4_a5", "a3_a4", "letter_media_carta"] = opt(
        "a4_a5", "Papel", "Paper", labels={"a4_a5": ("A4, folleto A5", "A4, A5 booklet"), "a3_a4": ("A3, folleto A4", "A3, A4 booklet"),
                                           "letter_media_carta": ("Carta, folleto media carta", "Letter, half-letter booklet")})
    encuadernacion: Literal["izquierda", "derecha"] = opt("izquierda", "Encuadernación", "Binding",
                                                         labels={"izquierda": ("Izquierda", "Left"), "derecha": ("Derecha", "Right")})
    medianil: float = opt(0, "Medianil en el pliegue (mm)", "Gutter at the fold (mm)", ge=0, le=50, advanced=True)
    hojas_por_cuadernillo: int = opt(0, "Hojas por cuadernillo (0 = todas en uno)", "Sheets per signature (0 = all in one)", ge=0, le=100, advanced=True)
    contraportada_al_final: bool = opt(True, "La última página sigue siendo la contraportada", "The last page stays the back cover")
    salida: Literal["pdf", "manual"] = opt("pdf", "Salida", "Output",
                                           labels={"pdf": ("PDF para imprimir a doble cara (borde corto)", "PDF for duplex printing (short edge)"),
                                                   "manual": ("Doble cara manual: anversos y reversos", "Manual duplex: fronts and backs")})


class AplanarOptions(BaseModel):
    aplanar: Literal["formularios", "anotaciones", "ambos"] = opt(
        "formularios", "Aplanar", "Flatten", labels={"formularios": ("Formularios", "Forms"), "anotaciones": ("Anotaciones", "Annotations"),
                                                     "ambos": ("Ambos", "Both")})


class RedactarOptions(BaseModel):
    color: str = opt("#000000", "Color del recuadro", "Box colour", pattern=COLOR_PATTERN)
    texto: str = opt("", "Texto en el recuadro", "Text in the box", max_length=40)
    # «Eliminar solo el contenido bajo el área» pasa las pruebas de redacción de 16.4 con texto, imágenes y vectores (D-153).
    metodo: Literal["rasterizar", "eliminar"] = opt(
        "rasterizar", "Método", "Method",
        labels={"rasterizar": ("Rasterizar las páginas afectadas (300 ppp)", "Rasterise affected pages (300 dpi)"),
                "eliminar": ("Eliminar solo el contenido bajo el área", "Remove only the content under the area")})


class AnotarOptions(BaseModel):
    """anotar-pdf (A.3): las marcas se hacen en pantalla; aquí, cómo se guardan."""

    guardar: Literal["anotaciones", "aplanadas"] = opt(
        "anotaciones", "Guardar como", "Save as",
        labels={"anotaciones": ("Anotaciones estándar, editables en otros lectores", "Standard annotations, editable in other readers"),
                "aplanadas": ("Aplanadas (dibujadas en la página)", "Flattened (drawn on the page)")})
    autor: str = opt("", "Autor de los comentarios", "Comment author", max_length=60)


class CortarMitadOptions(BaseModel):
    corte: Literal["auto", "vertical", "horizontal"] = opt(
        "auto", "Corte", "Cut", labels={"auto": ("Automático, por el lado largo", "Automatic, along the long side"),
                                        "vertical": ("Vertical", "Vertical"), "horizontal": ("Horizontal", "Horizontal")})
    orden: Literal["izq_der", "der_izq"] = opt("izq_der", "Orden de las mitades", "Order of the halves",
                                               labels={"izq_der": ("Izquierda a derecha", "Left to right"), "der_izq": ("Derecha a izquierda", "Right to left")})
    respetar_portadas: bool = opt(False, "No cortar la primera ni la última página", "Do not cut the first or the last page", advanced=True)
    deshacer_folleto: bool = opt(False, "Deshacer la imposición de un folleto escaneado", "Undo the imposition of a scanned booklet", advanced=True)


class ImprimirOptions(BaseModel):
    paginas: Literal["todas", "rango", "impares", "pares"] = opt(
        "todas", "Páginas", "Pages", labels={"todas": ("Todas", "All"), "rango": ("Rango", "Range"), "impares": ("Impares", "Odd"), "pares": ("Pares", "Even")})
    rango: str = opt("", "Rango de páginas", "Page range", max_length=200, show_if={"paginas": ("rango",)})
    orden_inverso: bool = opt(False, "Orden inverso", "Reverse order")
    papel: Literal["A4", "Letter", "A3", "A5"] = opt("A4", "Papel", "Paper", labels={k: (k, k) for k in ("A4", "Letter", "A3", "A5")})
    escala: Literal["ajustar", "real"] = opt("ajustar", "Escala", "Scale", labels={"ajustar": ("Ajustar al papel", "Fit to paper"), "real": ("Tamaño real", "Actual size")})
    por_hoja: Literal[1, 2, 4, 6, 9, 16] = opt(1, "Páginas por hoja", "Pages per sheet")
    orden: Literal["horizontal", "vertical"] = opt("horizontal", "Orden en la hoja", "Order on the sheet", advanced=True,
                                                   labels={"horizontal": ("Por filas", "By rows"), "vertical": ("Por columnas", "By columns")})
    bordes: bool = opt(False, "Bordes finos entre páginas", "Thin borders between pages", advanced=True)
    gris: bool = opt(False, "Escala de grises", "Grayscale")
    formularios_anotaciones: bool = opt(True, "Imprimir formularios y anotaciones", "Print forms and annotations")
    doble_cara: Literal["no", "manual"] = opt("no", "Doble cara", "Duplex",
                                              labels={"no": ("No, o la hace la impresora", "No, or the printer does it"), "manual": ("Manual, con asistente", "Manual, with an assistant")})
    reversos_invertidos: bool = opt(False, "Los reversos salen invertidos", "The backs come out reversed", show_if={"doble_cara": ("manual",)})


class MontarOptions(BaseModel):
    """montar-pdf: el tablero de la web rellena `docs` (documentos y sus páginas)."""

    docs: list[dict] = opt([], "Documentos", "Documents")


class MarcadoresOptions(BaseModel):
    """marcadores-pdf: el editor de la web rellena `items` (árbol de marcadores)."""

    items: list[dict] = opt([], "Marcadores", "Bookmarks")


class CompararOptions(BaseModel):
    ignorar_mayusculas_espacios: bool = opt(False, "Ignorar mayúsculas y espacios", "Ignore case and spaces", advanced=True)


class BuscarOptions(BaseModel):
    texto: str = opt("", "Texto a buscar", "Text to search", max_length=500)
    mayusculas: bool = opt(False, "Distinguir mayúsculas", "Match case")
    palabra_completa: bool = opt(False, "Palabra completa", "Whole word")
    expresion_regular: bool = opt(False, "Expresión regular", "Regular expression")


class ImagenesAPdfOptions(BaseModel):
    tamano_pagina: Literal["A0", "A1", "A2", "A3", "A4", "A5", "A6", "Letter", "Legal", "segun_imagen", "personalizado"] = opt(
        "A4", "Tamaño de página", "Page size",
        labels={**PAPERS, "segun_imagen": ("Según la imagen", "Fit to image"), "personalizado": ("Personalizado", "Custom")})
    dpi: int = opt(150, "DPI (según la imagen)", "DPI (fit to image)", ge=1, le=10000, advanced=True, show_if={"tamano_pagina": ("segun_imagen",)})
    ancho: float = opt(210, "Ancho", "Width", gt=0, le=5000, show_if={"tamano_pagina": ("personalizado",)})
    alto: float = opt(297, "Alto", "Height", gt=0, le=5000, show_if={"tamano_pagina": ("personalizado",)})
    unidad: Literal["mm", "in"] = opt("mm", "Unidad", "Unit", advanced=True, labels={"mm": ("mm", "mm"), "in": ("pulgadas", "inches")})
    orientacion: Literal["auto", "vertical", "horizontal"] = opt("auto", "Orientación", "Orientation",
                                                               labels={"auto": ("Automática", "Automatic"), "vertical": ("Vertical", "Portrait"),
                                                                       "horizontal": ("Horizontal", "Landscape")})
    margen: Literal["0", "5", "10", "15", "20", "25", "personalizado"] = opt(
        "0", "Margen", "Margin", labels={"0": ("Sin margen", "No margin"), "5": ("5 mm", "5 mm"), "10": ("10 mm", "10 mm"),
                                          "15": ("15 mm", "15 mm"), "20": ("20 mm", "20 mm"), "25": ("25 mm", "25 mm"),
                                          "personalizado": ("Personalizado", "Custom")})
    margen_personalizado: float = opt(0, "Margen personalizado", "Custom margin", ge=0, le=500, show_if={"margen": ("personalizado",)})
    unir: bool = opt(True, "Unir en un solo PDF", "Merge into one PDF")
    marcadores: bool = opt(False, "Marcadores con el nombre de cada imagen", "Bookmarks with each image name", advanced=True)
    ajuste: Literal["encajar", "rellenar", "tamano_real"] = opt("encajar", "Ajuste", "Fit", advanced=True,
                                                             labels={"encajar": ("Encajar", "Fit"), "rellenar": ("Rellenar recortando", "Fill and crop"),
                                                                     "tamano_real": ("Tamaño real", "Actual size")})


class PdfAImagenesOptions(BaseModel):
    formato: Literal["jpg", "png", "webp"] = opt("jpg", "Formato", "Format", labels={"jpg": ("JPG", "JPG"), "png": ("PNG", "PNG"), "webp": ("WEBP", "WEBP")})
    color: Literal["color", "gris", "bn", "cmyk"] = opt("color", "Color", "Color",
                                                     labels={"color": ("Color", "Color"), "gris": ("Gris", "Grayscale"),
                                                             "bn": ("Blanco y negro (PNG)", "Black and white (PNG)"),
                                                             "cmyk": ("CMYK con perfil ICC (JPG, en el servidor)", "CMYK with ICC profile (JPG, on the server)")})
    dpi: int = opt(144, "Resolución (ppp)", "Resolution (dpi)", ge=72, le=600)
    calidad: int = opt(85, "Calidad (%)", "Quality (%)", ge=1, le=100, show_if={"formato": ("jpg", "webp")})
    paginas: str = opt("todas", "Páginas", "Pages")
    salida: Literal["una_por_pagina", "una_sola"] = opt("una_por_pagina", "Salida", "Output", advanced=True,
                                                       labels={"una_por_pagina": ("Una imagen por página", "One image per page"),
                                                               "una_sola": ("Una sola imagen con todas las páginas", "One image with all pages")})
    organizacion: Literal["carpeta_por_archivo", "todas_juntas"] = opt("carpeta_por_archivo", "Organización", "Organization", advanced=True,
                                                                       labels={"carpeta_por_archivo": ("Una carpeta por archivo", "One folder per file"),
                                                                               "todas_juntas": ("Todas las imágenes en una carpeta", "All images in one folder")})


class EscanerOptions(BaseModel):
    """escaner-pdf (A.4): todo en el navegador; el OCR opcional del final sube el PDF a ocr-pdf."""

    filtro: Literal["documento", "gris", "color", "original"] = opt(
        "documento", "Filtro", "Filter",
        labels={"documento": ("Documento (blanco y negro adaptativo)", "Document (adaptive black and white)"), "gris": ("Gris", "Grey"),
                "color": ("Color realzado", "Enhanced colour"), "original": ("Original", "Original")})
    tamano_pagina: Literal["auto", "A4", "Letter"] = opt(
        "auto", "Tamaño de página", "Page size", labels={"auto": ("Automático", "Automatic"), "A4": ("A4", "A4"), "Letter": ("Carta", "Letter")})
    ocr_al_terminar: bool = opt(False, "OCR en el servidor al terminar", "OCR on the server when done", advanced=True)


class ContrasenaOptions(BaseModel):
    longitud: int = opt(16, "Longitud", "Length", ge=8, le=64)
    mayusculas: bool = opt(True, "Mayúsculas", "Uppercase")
    minusculas: bool = opt(True, "Minúsculas", "Lowercase")
    numeros: bool = opt(True, "Números", "Numbers")
    simbolos: bool = opt(False, "Símbolos", "Symbols")
    excluir_ambiguos: bool = opt(False, "Excluir caracteres ambiguos (0/O, l/1/I)", "Exclude ambiguous characters (0/O, l/1/I)", advanced=True)
    cantidad: int = opt(1, "Cantidad", "Quantity", ge=1, le=20, advanced=True)


class ImagenAJpgOptions(BaseModel):
    calidad: int = opt(90, "Calidad (%)", "Quality (%)", ge=1, le=100)
    fondo: str = opt("#FFFFFF", "Fondo para la transparencia", "Background for transparency", pattern=COLOR_PATTERN)
    conservar_metadatos: bool = opt(False, "Conservar metadatos", "Keep metadata", advanced=True)


class ComprimirImagenOptions(BaseModel):
    calidad: int = opt(75, "Calidad (%)", "Quality (%)", ge=1, le=100)
    formato: Literal["mismo", "jpg", "webp"] = opt("mismo", "Formato de salida", "Output format",
                                                   labels={"mismo": ("El mismo", "Same"), "jpg": ("JPG", "JPG"), "webp": ("WEBP", "WEBP")})
    ancho_maximo: int | None = opt(None, "Ancho máximo (px)", "Maximum width (px)", ge=16, le=20000, advanced=True)
    quitar_metadatos: bool = opt(True, "Quitar metadatos (EXIF y GPS)", "Remove metadata (EXIF and GPS)", advanced=True)


class RedimensionarOptions(BaseModel):
    modo: Literal["porcentaje", "ancho", "alto", "caja"] = opt("porcentaje", "Modo", "Mode",
                                                               labels={"porcentaje": ("Porcentaje", "Percentage"), "ancho": ("Ancho fijo", "Fixed width"),
                                                                       "alto": ("Alto fijo", "Fixed height"), "caja": ("Caja máxima", "Bounding box")})
    porcentaje: float = opt(50, "Porcentaje", "Percentage", gt=0, le=1000, show_if={"modo": ("porcentaje",)})
    ancho: int = opt(1920, "Ancho (px)", "Width (px)", ge=1, le=20000, show_if={"modo": ("ancho", "caja")})
    alto: int = opt(1080, "Alto (px)", "Height (px)", ge=1, le=20000, show_if={"modo": ("alto", "caja")})
    formato: Literal["mismo", "jpg", "png", "webp"] = opt("mismo", "Formato de salida", "Output format", advanced=True,
                                                          labels={"mismo": ("El mismo", "Same"), "jpg": ("JPG", "JPG"), "png": ("PNG", "PNG"), "webp": ("WEBP", "WEBP")})
    calidad: int = opt(90, "Calidad (%)", "Quality (%)", ge=1, le=100, advanced=True)


# ——— Imágenes en el navegador (7.11 y A.10) ———

IcoSize = Literal[16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
ICO_LABELS = {str(s): (f"{s} px", f"{s} px") for s in (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)}
AJUSTE = {"encajar": ("Encajar (con fondo transparente)", "Fit (transparent background)"),
          "recortar": ("Recortar al centro", "Crop to the centre")}
AVIF_SPEED = {"rapida": ("Rápida", "Fast"), "equilibrada": ("Equilibrada", "Balanced"),
              "lenta": ("Lenta (archivo más pequeño)", "Slow (smaller file)")}
PAGINAS_TIFF = {"todas": ("Todas (una imagen por página)", "All (one image per page)"), "primera": ("Solo la primera", "Only the first")}
OUT_FORMATS = ("jpg", "png", "webp", "avif", "gif", "bmp", "tiff", "ico")
CONVERT_INPUTS = ("jpg", "png", "webp", "avif", "gif", "bmp", "tiff", "ico", "svg")
METADATA = "Conservar metadatos (EXIF)", "Keep metadata (EXIF)"
BACKGROUND = "Fondo para la transparencia", "Background for transparency"


class ImagenAPngOptions(BaseModel):
    conservar_metadatos: bool = opt(False, *METADATA, advanced=True)


class ImagenAWebpOptions(BaseModel):
    calidad: int = opt(80, "Calidad (%)", "Quality (%)", ge=1, le=100, show_if={"sin_perdida": (False,)})
    sin_perdida: bool = opt(False, "Sin pérdida", "Lossless")
    conservar_metadatos: bool = opt(False, *METADATA, advanced=True)


class ImagenAAvifOptions(BaseModel):
    calidad: int = opt(60, "Calidad (%)", "Quality (%)", ge=1, le=100)
    velocidad: Literal["rapida", "equilibrada", "lenta"] = opt("equilibrada", "Velocidad de compresión", "Compression speed",
                                                              advanced=True, labels=AVIF_SPEED)


class JpgOptions(BaseModel):
    calidad: int = opt(90, "Calidad (%)", "Quality (%)", ge=1, le=100)
    fondo: str = opt("#FFFFFF", *BACKGROUND, pattern=COLOR_PATTERN)


class TiffAJpgOptions(JpgOptions):
    paginas: Literal["todas", "primera"] = opt("todas", "Páginas", "Pages", labels=PAGINAS_TIFF)


class IcoOptions(BaseModel):
    tamanos_ico: list[IcoSize] = opt([16, 32, 48, 256], "Tamaños", "Sizes", labels=ICO_LABELS, min_length=1)
    ajuste: Literal["encajar", "recortar"] = opt("encajar", "Si no es cuadrada", "If it is not square", labels=AJUSTE)


class ConvertirImagenOptions(BaseModel):
    formato: Literal["jpg", "png", "webp", "avif", "gif", "bmp", "tiff", "ico"] = opt(
        "jpg", "Convertir a", "Convert to", labels={f: (f.upper(), f.upper()) for f in OUT_FORMATS})
    calidad: int = opt(85, "Calidad (%)", "Quality (%)", ge=1, le=100, show_if={"formato": ("jpg", "webp", "avif")})
    sin_perdida: bool = opt(False, "WEBP sin pérdida", "Lossless WEBP", show_if={"formato": ("webp",)})
    fondo: str = opt("#FFFFFF", *BACKGROUND, pattern=COLOR_PATTERN, show_if={"formato": ("jpg", "bmp")})
    tamanos_ico: list[IcoSize] = opt([16, 32, 48, 256], "Tamaños del icono", "Icon sizes", labels=ICO_LABELS, min_length=1,
                                     show_if={"formato": ("ico",)})
    ajuste: Literal["encajar", "recortar"] = opt("encajar", "Si no es cuadrada", "If it is not square", labels=AJUSTE,
                                                show_if={"formato": ("ico",)})
    velocidad: Literal["rapida", "equilibrada", "lenta"] = opt("equilibrada", "Velocidad de compresión AVIF", "AVIF compression speed",
                                                              advanced=True, labels=AVIF_SPEED, show_if={"formato": ("avif",)})
    conservar_metadatos: bool = opt(False, *METADATA, advanced=True, show_if={"formato": ("jpg", "png", "webp")})
    paginas: Literal["todas", "primera"] = opt("todas", "Páginas de los TIFF", "TIFF pages", advanced=True, labels=PAGINAS_TIFF)


SVG_SIZES = {"original": ("Tamaño original", "Original size"), "2x": ("2×", "2×"), "3x": ("3×", "3×"), "4x": ("4×", "4×"),
             "ancho": ("Ancho personalizado", "Custom width")}


class SvgAPngOptions(BaseModel):
    """svg-a-png (A.10): resvg en el navegador, sin cargar recursos externos."""

    tamano: Literal["original", "2x", "3x", "4x", "ancho"] = opt("original", "Tamaño", "Size", labels=SVG_SIZES)
    ancho: int = opt(1000, "Ancho (px, se mantiene la proporción)", "Width (px, keeps the aspect ratio)", ge=1, le=16384,
                     show_if={"tamano": ("ancho",)})


class SvgAJpgOptions(SvgAPngOptions):
    fondo: str = opt("#FFFFFF", "Fondo", "Background", pattern=COLOR_PATTERN)
    calidad: int = opt(90, "Calidad (%)", "Quality (%)", ge=1, le=100)


class FaviconOptions(BaseModel):
    nombre: str = opt("", "Nombre del sitio (para el manifiesto)", "Site name (for the manifest)", max_length=60)
    color_tema: str = opt("#FFFFFF", "Color del tema", "Theme colour", pattern=COLOR_PATTERN)
    fondo: str = opt("#FFFFFF", "Fondo de los iconos de Apple y Android", "Background of the Apple and Android icons", pattern=COLOR_PATTERN)
    margen: int = opt(10, "Margen del icono de Apple (%)", "Apple icon margin (%)", ge=0, le=30, advanced=True)
    ajuste: Literal["encajar", "recortar"] = opt("encajar", "Si no es cuadrada", "If it is not square", labels=AJUSTE, advanced=True)


class QuitarMetadatosOptions(BaseModel):
    que: Literal["todo", "solo_gps"] = opt(
        "todo", "Qué quitar", "What to remove",
        labels={"todo": ("Todos los metadatos (EXIF, GPS, XMP, IPTC y comentarios)", "All metadata (EXIF, GPS, XMP, IPTC and comments)"),
                "solo_gps": ("Solo la ubicación GPS", "Only the GPS location")})
    conservar_orientacion: bool = opt(True, "Conservar la orientación (para que no salga girada)", "Keep the orientation (so it is not shown rotated)",
                                      show_if={"que": ("todo",)})


class Base64Options(BaseModel):
    formato: Literal["data_uri", "base64", "css", "html"] = opt(
        "data_uri", "Formato", "Format",
        labels={"data_uri": ("Data URI (data:image/…;base64,…)", "Data URI (data:image/…;base64,…)"), "base64": ("Solo Base64", "Base64 only"),
                "css": ("CSS (background-image)", "CSS (background-image)"), "html": ("HTML (<img>)", "HTML (<img>)")})


# ——— Códigos QR (A.1 y 7.11) ———

QR_TYPES = {"url": ("Enlace (URL)", "Link (URL)"), "wifi": ("Red WiFi", "WiFi network"), "texto": ("Texto", "Text"),
            "vcard": ("Contacto (vCard)", "Contact (vCard)"), "sepa": ("Transferencia SEPA", "SEPA transfer"), "paypal": ("PayPal", "PayPal"),
            "email": ("Correo electrónico", "Email"), "telefono": ("Teléfono", "Phone"), "sms": ("SMS", "SMS"),
            "evento": ("Evento de calendario", "Calendar event")}
GRADIENTS = {"ninguno": ("Sin degradado", "No gradient"), "lineal": ("Lineal", "Linear"), "radial": ("Radial", "Radial")}
Angle = Literal[0, 45, 90, 135, 180, 225, 270, 315]
ANGLES = {str(a): (f"{a}°", f"{a}°") for a in (0, 45, 90, 135, 180, 225, 270, 315)}
DOT_SHAPES = {"cuadrado": ("Cuadrados", "Squares"), "puntos": ("Puntos", "Dots"), "redondeado": ("Redondeados", "Rounded"),
              "muy_redondeado": ("Muy redondeados", "Extra rounded"), "elegante": ("Elegantes", "Classy"),
              "elegante_redondeado": ("Elegantes redondeados", "Classy rounded")}
EYE_OUTER = {"cuadrado": ("Cuadrado", "Square"), "punto": ("Círculo", "Circle"), "muy_redondeado": ("Redondeado", "Rounded")}
EYE_INNER = {"cuadrado": ("Cuadrado", "Square"), "punto": ("Círculo", "Circle")}
Gradient = Literal["ninguno", "lineal", "radial"]


def _tipo(*tipos: str) -> dict:
    return {"tipo": tipos}


class GenerarQrOptions(BaseModel):
    """generar-codigo-qr (A.1): qr-code-styling en la página y comprobación de lectura con zxing-cpp en el worker."""

    tipo: Literal["url", "wifi", "texto", "vcard", "sepa", "paypal", "email", "telefono", "sms", "evento"] = opt(
        "url", "Tipo de contenido", "Content type", labels=QR_TYPES)
    url: str = opt("", "Dirección", "Address", max_length=2000, show_if=_tipo("url"), widget="url")
    wifi_ssid: str = opt("", "Nombre de la red (SSID)", "Network name (SSID)", max_length=32, show_if=_tipo("wifi"))
    wifi_contrasena: str = opt("", "Contraseña", "Password", max_length=63, show_if={"tipo": ("wifi",), "wifi_cifrado": ("WPA", "WEP")})
    wifi_cifrado: Literal["WPA", "WEP", "nopass"] = opt("WPA", "Cifrado", "Encryption", show_if=_tipo("wifi"),
                                                       labels={"WPA": ("WPA/WPA2", "WPA/WPA2"), "WEP": ("WEP", "WEP"), "nopass": ("Ninguno", "None")})
    wifi_oculta: bool = opt(False, "Red oculta", "Hidden network", show_if=_tipo("wifi"))
    texto: str = opt("", "Texto", "Text", max_length=2900, show_if=_tipo("texto"), widget="textarea")
    vcard_nombre: str = opt("", "Nombre", "First name", max_length=100, show_if=_tipo("vcard"))
    vcard_apellidos: str = opt("", "Apellidos", "Last name", max_length=100, show_if=_tipo("vcard"))
    vcard_nombre_visible: str = opt("", "Nombre visible (vacío: nombre y apellidos)", "Display name (empty: first and last name)", max_length=150,
                                    show_if=_tipo("vcard"))
    vcard_email: str = opt("", "Correo electrónico", "Email", max_length=150, show_if=_tipo("vcard"), widget="email")
    vcard_empresa: str = opt("", "Empresa", "Company", max_length=150, show_if=_tipo("vcard"))
    vcard_cargo: str = opt("", "Cargo", "Job title", max_length=150, show_if=_tipo("vcard"))
    vcard_web: str = opt("", "Web", "Website", max_length=500, show_if=_tipo("vcard"), widget="url")
    vcard_telefono: str = opt("", "Teléfono", "Phone", max_length=30, show_if=_tipo("vcard"), widget="tel")
    vcard_tipo_telefono: Literal["trabajo", "movil", "personal", "otro"] = opt(
        "trabajo", "Tipo de teléfono", "Phone type", show_if=_tipo("vcard"),
        labels={"trabajo": ("Trabajo", "Work"), "movil": ("Móvil", "Mobile"), "personal": ("Personal", "Home"), "otro": ("Otro", "Other")})
    sepa_beneficiario: str = opt("", "Beneficiario", "Beneficiary", max_length=70, show_if=_tipo("sepa"))
    sepa_iban: str = opt("", "IBAN", "IBAN", max_length=42, show_if=_tipo("sepa"))
    sepa_bic: str = opt("", "BIC (opcional en el EEE)", "BIC (optional in the EEA)", max_length=11, show_if=_tipo("sepa"))
    sepa_importe: float | None = opt(None, "Importe en euros (opcional)", "Amount in euros (optional)", ge=0.01, le=999999999.99,
                                     show_if=_tipo("sepa"))
    sepa_concepto: str = opt("", "Concepto", "Remittance information", max_length=140, show_if=_tipo("sepa"))
    paypal_cuenta: str = opt("", "Correo o identificador de PayPal.Me", "Email or PayPal.Me ID", max_length=150, show_if=_tipo("paypal"))
    paypal_importe: float | None = opt(None, "Importe (opcional)", "Amount (optional)", ge=0.01, le=999999999.99, show_if=_tipo("paypal"))
    paypal_moneda: Literal["EUR", "USD", "GBP", "CHF", "MXN", "ARS", "BRL", "CAD", "AUD", "JPY"] = opt(
        "EUR", "Moneda", "Currency", show_if=_tipo("paypal"))
    email_para: str = opt("", "Para", "To", max_length=150, show_if=_tipo("email"), widget="email")
    email_asunto: str = opt("", "Asunto", "Subject", max_length=200, show_if=_tipo("email"))
    email_mensaje: str = opt("", "Mensaje", "Message", max_length=1500, show_if=_tipo("email"), widget="textarea")
    telefono_numero: str = opt("", "Número de teléfono", "Phone number", max_length=30, show_if=_tipo("telefono"), widget="tel")
    sms_numero: str = opt("", "Número de teléfono", "Phone number", max_length=30, show_if=_tipo("sms"), widget="tel")
    sms_mensaje: str = opt("", "Mensaje", "Message", max_length=600, show_if=_tipo("sms"), widget="textarea")
    evento_titulo: str = opt("", "Título", "Title", max_length=200, show_if=_tipo("evento"))
    evento_inicio: str = opt("", "Inicio", "Start", max_length=20, show_if=_tipo("evento"), widget="datetime-local")
    evento_fin: str = opt("", "Final (opcional)", "End (optional)", max_length=20, show_if=_tipo("evento"), widget="datetime-local")
    evento_todo_el_dia: bool = opt(False, "Todo el día", "All day", show_if=_tipo("evento"))
    evento_lugar: str = opt("", "Lugar", "Location", max_length=200, show_if=_tipo("evento"))
    evento_descripcion: str = opt("", "Descripción", "Description", max_length=800, show_if=_tipo("evento"), widget="textarea")
    formato: Literal["png", "svg", "pdf"] = opt("png", "Formato", "Format",
                                                labels={"png": ("PNG", "PNG"), "svg": ("SVG", "SVG"), "pdf": ("PDF vectorial", "Vector PDF")})
    tamano: int = opt(500, "Tamaño (px)", "Size (px)", ge=100, le=10000)
    logo_quitar_fondo: bool = opt(False, "Quitar los módulos de detrás del logotipo", "Remove the modules behind the logo")
    logo_tamano: float = opt(0.4, "Tamaño relativo del logotipo", "Relative logo size", ge=0.1, le=1)
    logo_margen: int = opt(0, "Margen del logotipo (px)", "Logo margin (px)", ge=0, le=100)
    fondo: str = opt("#FFFFFF", "Fondo", "Background", pattern=COLOR_PATTERN, advanced=True)
    fondo_degradado: Gradient = opt("ninguno", "Degradado del fondo", "Background gradient", labels=GRADIENTS, advanced=True)
    fondo_color2: str = opt("#E5E7EB", "Segundo color del fondo", "Second background colour", pattern=COLOR_PATTERN, advanced=True,
                            show_if={"fondo_degradado": ("lineal", "radial")})
    fondo_angulo: Angle = opt(0, "Ángulo del degradado del fondo", "Background gradient angle", labels=ANGLES, advanced=True,
                              show_if={"fondo_degradado": ("lineal",)})
    modulos: str = opt("#000000", "Módulos", "Modules", pattern=COLOR_PATTERN, advanced=True)
    modulos_degradado: Gradient = opt("ninguno", "Degradado de los módulos", "Modules gradient", labels=GRADIENTS, advanced=True)
    modulos_color2: str = opt("#1D4ED8", "Segundo color de los módulos", "Second modules colour", pattern=COLOR_PATTERN, advanced=True,
                              show_if={"modulos_degradado": ("lineal", "radial")})
    modulos_angulo: Angle = opt(0, "Ángulo del degradado de los módulos", "Modules gradient angle", labels=ANGLES, advanced=True,
                                show_if={"modulos_degradado": ("lineal",)})
    ojos_exteriores: str = opt("#000000", "Ojos exteriores", "Outer eyes", pattern=COLOR_PATTERN, advanced=True)
    ojos_exteriores_degradado: Gradient = opt("ninguno", "Degradado de los ojos exteriores", "Outer eyes gradient", labels=GRADIENTS, advanced=True)
    ojos_exteriores_color2: str = opt("#1D4ED8", "Segundo color de los ojos exteriores", "Second outer eyes colour", pattern=COLOR_PATTERN,
                                      advanced=True, show_if={"ojos_exteriores_degradado": ("lineal", "radial")})
    ojos_exteriores_angulo: Angle = opt(0, "Ángulo del degradado de los ojos exteriores", "Outer eyes gradient angle", labels=ANGLES,
                                        advanced=True, show_if={"ojos_exteriores_degradado": ("lineal",)})
    ojos_interiores: str = opt("#000000", "Ojos interiores", "Inner eyes", pattern=COLOR_PATTERN, advanced=True)
    ojos_interiores_degradado: Gradient = opt("ninguno", "Degradado de los ojos interiores", "Inner eyes gradient", labels=GRADIENTS, advanced=True)
    ojos_interiores_color2: str = opt("#1D4ED8", "Segundo color de los ojos interiores", "Second inner eyes colour", pattern=COLOR_PATTERN,
                                      advanced=True, show_if={"ojos_interiores_degradado": ("lineal", "radial")})
    ojos_interiores_angulo: Angle = opt(0, "Ángulo del degradado de los ojos interiores", "Inner eyes gradient angle", labels=ANGLES,
                                        advanced=True, show_if={"ojos_interiores_degradado": ("lineal",)})
    forma_modulos: Literal["cuadrado", "puntos", "redondeado", "muy_redondeado", "elegante", "elegante_redondeado"] = opt(
        "cuadrado", "Forma de los módulos", "Module shape", labels=DOT_SHAPES, advanced=True)
    forma_ojos_exteriores: Literal["cuadrado", "punto", "muy_redondeado"] = opt("cuadrado", "Forma de los ojos exteriores", "Outer eye shape",
                                                                                labels=EYE_OUTER, advanced=True)
    forma_ojos_interiores: Literal["cuadrado", "punto"] = opt("cuadrado", "Forma de los ojos interiores", "Inner eye shape", labels=EYE_INNER,
                                                             advanced=True)
    forma: Literal["cuadrado", "circulo"] = opt("cuadrado", "Forma general", "Overall shape",
                                               labels={"cuadrado": ("Cuadrado", "Square"), "circulo": ("Círculo", "Circle")}, advanced=True)
    borde: bool = opt(False, "Borde", "Border", advanced=True)
    borde_grosor: int = opt(5, "Grosor del borde (px)", "Border thickness (px)", ge=1, le=200, advanced=True, show_if={"borde": (True,)})
    borde_espaciado: int = opt(20, "Espacio entre borde y código (px)", "Space between border and code (px)", ge=0, le=500, advanced=True,
                               show_if={"borde": (True,)})
    borde_color: str = opt("#000000", "Color del borde", "Border colour", pattern=COLOR_PATTERN, advanced=True, show_if={"borde": (True,)})
    version: int = opt(0, "Versión (0 = automática; 1–40)", "Version (0 = automatic; 1–40)", ge=0, le=40, advanced=True)
    modo: Literal["byte", "numerico", "alfanumerico", "kanji"] = opt(
        "byte", "Modo", "Mode", advanced=True,
        labels={"byte": ("Byte", "Byte"), "numerico": ("Numérico", "Numeric"), "alfanumerico": ("Alfanumérico", "Alphanumeric"),
                "kanji": ("Kanji", "Kanji")})
    correccion: Literal["Q", "L", "M", "H"] = opt(
        "Q", "Corrección de errores (con logotipo, siempre H)", "Error correction (always H with a logo)", advanced=True,
        labels={"Q": ("Q (25 %)", "Q (25%)"), "L": ("L (7 %)", "L (7%)"), "M": ("M (15 %)", "M (15%)"), "H": ("H (30 %)", "H (30%)")})


class LeerQrOptions(BaseModel):
    formatos: Literal["qr", "todos"] = opt(
        "qr", "Qué códigos buscar", "Which codes to look for",
        labels={"qr": ("Códigos QR", "QR codes"),
                "todos": ("Todos (QR, Data Matrix, Aztec, PDF417, EAN, UPC, Code 128…)", "All (QR, Data Matrix, Aztec, PDF417, EAN, UPC, Code 128…)")})


# ——— crear-collage (A.1) ———

COLLAGE_INPUTS = ("jpg", "png", "webp", "gif", "bmp", "avif")


class CrearCollageOptions(BaseModel):
    """crear-collage (A.1): el editor compone el collage en la página; el worker recibe además el documento (`doc`)."""

    papel: Literal["A4", "Letter"] = opt("A4", "Papel", "Paper", labels={"A4": ("A4", "A4"), "Letter": ("Carta (Letter)", "Letter")})
    orientacion: Literal["vertical", "horizontal"] = opt("vertical", "Orientación", "Orientation",
                                                       labels={"vertical": ("Vertical", "Portrait"), "horizontal": ("Horizontal", "Landscape")})
    formato: Literal["pdf", "jpg", "png"] = opt(
        "pdf", "Formato", "Format",
        labels={"pdf": ("PDF (fotos sin recomprimir)", "PDF (photos not recompressed)"), "jpg": ("JPG", "JPG"), "png": ("PNG", "PNG")})
    resolucion: Literal[150, 300, 600] = opt(300, "Resolución de exportación", "Export resolution",
                                             labels={"150": ("150 ppp", "150 dpi"), "300": ("300 ppp", "300 dpi"), "600": ("600 ppp", "600 dpi")},
                                             show_if={"formato": ("jpg", "png")})


# ——— crear-tarjeta (A.1, F6-N2, D-232) ———


class CrearTarjetaOptions(BaseModel):
    """crear-tarjeta (A.1): el editor compone la tarjeta en la página; el worker recibe además el documento (`doc`)."""

    salida: Literal["casa", "imprenta", "imagen"] = opt("casa", "Salida", "Output", labels={
        "casa": ("Imprimir en casa (varias por hoja, con marcas de corte)", "Print at home (several per sheet, with crop marks)"),
        "imprenta": ("Imprenta (tamaño final con sangrado)", "Print shop (final size with bleed)"),
        "imagen": ("Imagen para enviar", "Image to send")})
    papel: Literal["A4", "Letter"] = opt("A4", "Papel", "Paper", labels={"A4": ("A4", "A4"), "Letter": ("Carta (Letter)", "Letter")},
                                         show_if={"salida": ("casa",)})
    sangrado: float = opt(3, "Sangrado (mm)", "Bleed (mm)", ge=0, le=5, show_if={"salida": ("imprenta",)})
    formato_imagen: Literal["jpg", "png"] = opt("jpg", "Formato de la imagen", "Image format",
                                                labels={"jpg": ("JPG", "JPG"), "png": ("PNG", "PNG")}, show_if={"salida": ("imagen",)})


# ——— mermaid-a-svg y mermaid-a-png (7.13, F6-N, D-231) ———

MERMAID_THEMES = {"default": ("Clásico", "Classic"), "neutral": ("Neutro (blanco y negro)", "Neutral (black and white)"),
                  "dark": ("Oscuro", "Dark"), "forest": ("Bosque (verdes)", "Forest (greens)"), "base": ("Sencillo", "Plain")}
MERMAID_BACKGROUNDS = {"auto": ("El del tema", "The theme's own"), "blanco": ("Blanco", "White"), "transparente": ("Transparente", "Transparent")}


class MermaidSvgOptions(BaseModel):
    """mermaid-a-svg (D-231): tema [clásico] y fondo [el del tema]; el código se escribe o se sube en la página."""

    tema: Literal["default", "neutral", "dark", "forest", "base"] = opt("default", "Tema", "Theme", labels=MERMAID_THEMES)
    fondo: Literal["auto", "blanco", "transparente"] = opt("auto", "Fondo", "Background", labels=MERMAID_BACKGROUNDS)


class MermaidPngOptions(MermaidSvgOptions):
    """mermaid-a-png (D-231): además, la escala [2×] (con un tope de 100 megapíxeles)."""

    escala: Literal[1, 2, 3, 4] = opt(2, "Escala", "Scale", labels={"1": ("1× (pantalla)", "1× (screen)"), "2": ("2× (nítida)", "2× (sharp)"),
                                                                  "3": ("3×", "3×"), "4": ("4× (para imprimir)", "4× (for print)")})


def client(slug_es, slug_en, name_es, name_en, options, inputs, outputs, summary_es, summary_en, **kw) -> ToolSpec:
    return ToolSpec(slug_es=slug_es, slug_en=slug_en, name_es=name_es, name_en=name_en, category=kw.pop("category", "pdf"),
                    where=kw.pop("where", "client"), inputs=inputs, outputs=outputs, options=options, launch=kw.pop("launch", True),
                    summary_es=summary_es, summary_en=summary_en, **kw)


def image(slug_es, slug_en, name_es, name_en, options, inputs, outputs, summary_es, summary_en, **kw) -> ToolSpec:
    return client(slug_es, slug_en, name_es, name_en, options, inputs, outputs, summary_es, summary_en, category="image", phase="F5", **kw)


# ——— visor-3d, visor-gcode, comprimir-glb y render-modelo-3d (7.20, F7-H, D-257) ———

MESH_VIEW = ("stl", "obj", "mtl", "3mf", "ply", "glb", "gltf", "amf")


class ComprimirGlbOptions(BaseModel):
    """comprimir-glb (D-257): Draco [alta: 14, 10 y 12 bits], meshopt o sin compresión; soldar [sí]; texturas a WebP y
    tamaño máximo. Nunca devuelve un archivo mayor."""

    metodo: Literal["draco", "meshopt", "ninguno"] = opt("draco", "Compresión", "Compression", labels={
        "draco": ("Draco (la más compatible)", "Draco (most compatible)"),
        "meshopt": ("meshopt (más rápida de abrir)", "meshopt (faster to open)"),
        "ninguno": ("Ninguna (quitar la compresión)", "None (remove compression)")})
    calidad: Literal["alta", "media", "baja"] = opt("alta", "Calidad de la geometría", "Geometry quality", labels={
        "alta": ("Alta (sin diferencias visibles)", "High (no visible difference)"),
        "media": ("Media", "Medium"), "baja": ("Baja (lo más pequeño)", "Low (smallest)")},
        show_if={"metodo": ("draco", "meshopt")})
    soldar: bool = opt(True, "Unir vértices repetidos", "Merge repeated vertices", advanced=True)
    texturas: Literal["conservar", "webp"] = opt("conservar", "Texturas", "Textures", labels={
        "conservar": ("Dejarlas como están", "Keep them as they are"), "webp": ("Pasarlas a WebP", "Convert them to WebP")})
    tamano_textura: Literal[0, 512, 1024, 2048, 4096] = opt(0, "Tamaño máximo de las texturas", "Maximum texture size", labels={
        "0": ("Sin cambiar", "Unchanged"), "512": ("512 px", "512 px"), "1024": ("1024 px", "1024 px"), "2048": ("2048 px", "2048 px"),
        "4096": ("4096 px", "4096 px")}, advanced=True)
    calidad_textura: int = opt(85, "Calidad de las texturas WebP", "WebP texture quality", ge=40, le=100, advanced=True,
                               show_if={"texturas": ("webp",)})


class RenderModeloOptions(BaseModel):
    """render-modelo-3d (D-257): tamaño [1024 px], ángulo [isométrico], fondo [transparente] y color [el del modelo]."""

    tamano: Literal[512, 1024, 2048] = opt(1024, "Tamaño", "Size", labels={"512": ("512 px", "512 px"), "1024": ("1024 px", "1024 px"),
                                                                       "2048": ("2048 px", "2048 px")})
    angulo: Literal["isometrico", "frontal", "superior", "lateral"] = opt("isometrico", "Vista", "View", labels={
        "isometrico": ("Isométrica", "Isometric"), "frontal": ("De frente", "Front"), "superior": ("Desde arriba", "Top"),
        "lateral": ("De lado", "Side")})
    fondo: Literal["transparente", "blanco", "color"] = opt("transparente", "Fondo", "Background", labels={
        "transparente": ("Transparente", "Transparent"), "blanco": ("Blanco", "White"), "color": ("Un color", "A colour")})
    color_fondo: str = opt("#F3F4F6", "Color del fondo", "Background colour", pattern=COLOR_PATTERN, show_if={"fondo": ("color",)})
    color_modelo: Literal["original", "propio"] = opt("original", "Color del modelo", "Model colour", labels={
        "original": ("El del archivo", "The file's own"), "propio": ("Uno a elegir", "One of my choice")})
    color: str = opt("#E67610", "Color", "Colour", pattern=COLOR_PATTERN, show_if={"color_modelo": ("propio",)})
    eje_vertical: Literal["auto", "z", "y"] = opt("auto", "Eje vertical", "Up axis", labels={
        "auto": ("Según el formato", "By format"), "z": ("Z (impresión 3D)", "Z (3D printing)"), "y": ("Y (glTF, juegos)", "Y (glTF, games)")},
        advanced=True)


SPECS: list[ToolSpec] = [
    client("unir-pdf", "merge-pdf", "Unir PDF", "Merge PDF", UnirOptions, PDF, PDF,
           "Junta varios PDF en uno, en el orden que elijas.", "Combine several PDFs into one, in the order you choose.",
           related=("dividir-pdf", "organizar-pdf", "comprimir-pdf")),
    client("dividir-pdf", "split-pdf", "Dividir PDF", "Split PDF", DividirOptions, PDF, ("pdf", "zip"),
           "Separa un PDF en varios por páginas, pares e impares, marcadores o tamaño.", "Split a PDF by pages, odd and even, bookmarks or size.",
           related=("unir-pdf", "extraer-paginas-pdf")),
    client("girar-pdf", "rotate-pdf", "Girar PDF", "Rotate PDF", GirarOptions, PDF, (*PDF, "zip"),
           "Gira todas las páginas o solo algunas.", "Rotate all pages or only some of them.", related=("organizar-pdf",),
           where="hybrid", worker_group="ocr", impl="tools.pdf.girar:run", cost_class="light", time_limit=1800),
    client("eliminar-paginas-pdf", "delete-pdf-pages", "Eliminar páginas de un PDF", "Delete PDF pages", EliminarOptions, PDF, PDF,
           "Quita las páginas que no quieres.", "Remove the pages you don't want.", related=("extraer-paginas-pdf",)),
    client("extraer-paginas-pdf", "extract-pdf-pages", "Extraer páginas de un PDF", "Extract PDF pages", ExtraerOptions, PDF, ("pdf", "zip"),
           "Saca páginas sueltas o rangos a un PDF nuevo.", "Pull single pages or ranges into a new PDF.", related=("dividir-pdf",)),
    client("organizar-pdf", "organize-pdf", "Ordenar páginas de un PDF", "Organize PDF pages", OrganizarOptions, PDF, PDF,
           "Cambia el orden de las páginas, invierte o intercala escaneos a doble cara.", "Reorder pages, reverse them or interleave duplex scans.",
           related=("girar-pdf", "eliminar-paginas-pdf")),
    client("numerar-paginas-pdf", "add-page-numbers-pdf", "Numerar páginas de un PDF", "Add page numbers to PDF", NumerarOptions, PDF, PDF,
           "Añade números de página con el formato y la posición que quieras.", "Add page numbers with the format and position you want.",
           related=("marca-de-agua-pdf",)),
    client("marca-de-agua-pdf", "watermark-pdf", "Marca de agua en PDF", "Watermark PDF", MarcaAguaOptions, ("pdf", "png", "jpg"), PDF,
           "Pon un texto o una imagen encima o debajo del contenido.", "Put text or an image above or below the content.",
           related=("numerar-paginas-pdf", "proteger-pdf")),
    client("editar-pdf", "edit-pdf", "Editar PDF", "Edit PDF", EditarOptions, PDF, PDF,
           "Añade texto, imágenes, formas, firmas y notas, tapa zonas y ordena páginas.",
           "Add text, images, shapes, signatures and notes, cover areas and reorder pages.",
           max_files=1, related=("rellenar-pdf", "pdf-a-word", "organizar-pdf")),
    client("rellenar-pdf", "fill-pdf", "Rellenar formulario PDF", "Fill PDF form", RellenarOptions, PDF, PDF,
           "Rellena formularios PDF, marca casillas y añade fecha y firma, en tu navegador.",
           "Fill in PDF forms, tick boxes and add a date and signature, in your browser.",
           max_files=1, related=("editar-pdf", "proteger-pdf")),
    client("recortar-pdf", "crop-pdf", "Recortar PDF", "Crop PDF", RecortarOptions, PDF, ("pdf", "zip"),
           "Recorta los márgenes de las páginas a mano o quita los blancos automáticamente.",
           "Crop page margins by hand or remove white margins automatically.", related=("cambiar-tamano-pagina-pdf",)),
    client("cambiar-tamano-pagina-pdf", "resize-pdf-pages", "Cambiar el tamaño de las páginas", "Resize PDF pages", CambiarTamanoOptions,
           PDF, ("pdf", "zip"), "Pasa las páginas a A4, Carta u otro tamaño escalando o centrando el contenido.",
           "Change pages to A4, Letter or another size by scaling or centring the content.", related=("recortar-pdf", "varias-paginas-por-hoja")),
    client("varias-paginas-por-hoja", "n-up-pdf", "Varias páginas por hoja", "Multiple pages per sheet", VariasPorHojaOptions, PDF, ("pdf", "zip"),
           "Pon 2, 4, 6 o más páginas en cada hoja para ahorrar papel al imprimir.",
           "Put 2, 4, 6 or more pages on each sheet to save paper when printing.", related=("folleto-pdf", "cambiar-tamano-pagina-pdf")),
    client("folleto-pdf", "booklet-pdf", "Crear folleto PDF", "Make a PDF booklet", FolletoOptions, PDF, ("pdf", "zip"),
           "Ordena las páginas para imprimir un folleto doblado, con cuadernillos y medianil.",
           "Arrange pages to print a folded booklet, with signatures and a gutter.", max_files=1, related=("varias-paginas-por-hoja",)),
    client("aplanar-pdf", "flatten-pdf", "Aplanar PDF", "Flatten PDF", AplanarOptions, PDF, ("pdf", "zip"),
           "Convierte formularios y anotaciones en contenido fijo que ya no se puede cambiar.",
           "Turn forms and annotations into fixed content that can no longer be changed.", related=("rellenar-pdf", "proteger-pdf")),
    # A.3 (F4-B1): diseñador de campos en el navegador (pdf-lib); los campos de firma, con pyHanko en `workerpdf`.
    client("hacer-pdf-rellenable", "make-pdf-fillable", "Hacer un PDF rellenable", "Make a PDF fillable", HacerRellenableOptions, PDF, PDF,
           "Añade campos de texto, casillas, opciones, listas, botones y firmas a un PDF para que se pueda rellenar.",
           "Add text fields, checkboxes, options, lists, buttons and signatures to a PDF so it can be filled in.",
           where="hybrid", worker_group="pdf", impl="tools.pdf.campos_firma:run", cost_class="light", phase="F4", time_limit=300,
           max_files=1, related=("crear-formulario-pdf", "rellenar-pdf", "firmar-pdf")),
    client("crear-formulario-pdf", "create-pdf-form", "Crear un formulario PDF", "Create a PDF form", HacerRellenableOptions, PDF, PDF,
           "Diseña un formulario PDF rellenable desde una página en blanco o a partir de un PDF que ya tengas.",
           "Design a fillable PDF form from a blank page or from a PDF you already have.",
           where="hybrid", worker_group="pdf", impl="tools.pdf.campos_firma:run", cost_class="light", phase="F4", time_limit=300,
           max_files=1, related=("hacer-pdf-rellenable", "rellenar-pdf", "firmar-pdf")),
    # A.2 (F4-E1, D-204): diseñador de facturas en el navegador; apagada por INVOICING_ES_ENABLED y por defecto (7.23).
    client("crear-factura", "create-invoice", "Crear factura", "Create invoice", CrearFacturaOptions, (), PDF,
           "Haz una factura en PDF con tu logotipo, IVA, recargo de equivalencia e IRPF, con los totales calculados al momento.",
           "Make a PDF invoice with your logo, VAT, equivalence surcharge and withholding, with totals worked out as you type.",
           category="invoice", phase="F4", default_enabled=False, related=("crear-factura-electronica", "validar-factura-electronica")),
    client("anotar-pdf", "annotate-pdf", "Anotar PDF", "Annotate PDF", AnotarOptions, PDF, PDF,
           "Resalta, subraya, tacha y añade notas, flechas y dibujos; se guardan como comentarios estándar.",
           "Highlight, underline, strike out and add notes, arrows and drawings, saved as standard comments.",
           max_files=1, related=("editar-pdf", "aplanar-pdf", "lector-pdf")),
    client("lector-pdf", "pdf-reader", "Lector de PDF", "PDF reader", OfficeOptions, PDF + VIEWABLE, PDF,
           "Abre y lee un PDF en el navegador, con zoom, búsqueda, descarga e impresión. Otros documentos se convierten antes.",
           "Open and read a PDF in your browser, with zoom, search, download and print. Other documents are converted first.",
           where="hybrid", worker_group="office", impl="tools.office.lector_pdf:run", cost_class="light", queue_kind="light",
           time_limit=900, secret_fields=("contrasena",), max_files=1, related=("anotar-pdf", "convertir-a-pdf", "editar-pdf")),
    client("cortar-paginas-por-la-mitad", "split-pages-in-half", "Cortar páginas por la mitad", "Split pages in half", CortarMitadOptions,
           PDF, ("pdf", "zip"), "Separa en dos cada página de un escaneo a doble página o de un folleto, sin perder calidad.",
           "Split each page of a two-page scan or a booklet in two, without losing quality.", phase="F2",
           related=("recortar-pdf", "organizar-pdf")),
    client("imprimir-pdf", "print-pdf", "Imprimir PDF", "Print PDF", ImprimirOptions, PDF, ("pdf", "zip"),
           "Prepara la impresión: páginas, papel, varias por hoja, gris y doble cara manual con asistente.",
           "Get it ready to print: pages, paper, several per sheet, grey and manual duplex with an assistant.",
           max_files=1, phase="F2", related=("folleto-pdf", "varias-paginas-por-hoja")),
    client("montar-pdf", "assemble-pdf", "Montar PDF", "Assemble PDF", MontarOptions, PDF + ("jpg", "png", "webp", "gif", "bmp"), ("pdf", "zip"),
           "Pon varios PDF e imágenes en columnas y pasa páginas de uno a otro; guarda cada documento o todos.",
           "Lay out several PDFs and images in columns and move pages between them; save each document or all.",
           phase="F2", related=("unir-pdf", "organizar-pdf")),
    client("marcadores-pdf", "pdf-bookmarks", "Editar marcadores de un PDF", "Edit PDF bookmarks", MarcadoresOptions, PDF, PDF,
           "Crea, ordena, anida y da estilo a los marcadores del PDF, con su página, posición y zoom.",
           "Create, reorder, nest and style the PDF bookmarks, with their page, position and zoom.",
           max_files=1, phase="F2", related=("lector-pdf", "metadatos-pdf")),
    client("comparar-pdf", "compare-pdf", "Comparar PDF", "Compare PDF", CompararOptions, PDF, PDF,
           "Encuentra lo añadido, borrado y cambiado entre dos PDF, con superposición y deslizador.",
           "Find what was added, removed and changed between two PDFs, with overlay and slider.",
           max_files=2, phase="F2", related=("buscar-en-pdf", "lector-pdf")),
    client("buscar-en-pdf", "search-pdf", "Buscar en PDF", "Search PDF", BuscarOptions, PDF, ("csv",),
           "Busca un texto en muchos PDF a la vez y exporta los resultados a CSV, sin subir nada.",
           "Search for text in many PDFs at once and export the results to CSV, without uploading anything.",
           phase="F2", related=("lector-pdf", "ocr-pdf")),
    client("redactar-pdf", "redact-pdf", "Redactar PDF", "Redact PDF", RedactarOptions, PDF, PDF,
           "Tapa de forma segura nombres, DNI, IBAN y otros datos: desaparecen del archivo, no solo de la vista.",
           "Securely black out names, ID numbers, IBANs and other data: they are removed from the file, not just hidden.",
           max_files=1, related=("ocr-pdf", "proteger-pdf")),
    client("webp-a-pdf", "webp-to-pdf", "WEBP a PDF", "WEBP to PDF", ImagenesAPdfOptions, ("webp",), PDF,
           "Convierte imágenes WEBP en un PDF en tu navegador.", "Convert WEBP images into a PDF in your browser.", related=("imagenes-a-pdf",)),
    client("gif-a-pdf", "gif-to-pdf", "GIF a PDF", "GIF to PDF", ImagenesAPdfOptions, ("gif",), PDF,
           "Convierte imágenes GIF en un PDF en tu navegador.", "Convert GIF images into a PDF in your browser.", related=("imagenes-a-pdf",)),
    client("bmp-a-pdf", "bmp-to-pdf", "BMP a PDF", "BMP to PDF", ImagenesAPdfOptions, ("bmp",), PDF,
           "Convierte imágenes BMP en un PDF en tu navegador.", "Convert BMP images into a PDF in your browser.", related=("imagenes-a-pdf",)),
    client("tiff-a-pdf", "tiff-to-pdf", "TIFF a PDF", "TIFF to PDF", ImagenesAPdfOptions, ("tiff",), PDF,
           "Convierte TIFF, también multipágina, en PDF sin recomprimir (G4 y JPEG se conservan).",
           "Convert TIFF, multi-page too, to PDF without recompressing (G4 and JPEG are kept).",
           where="server", worker_group="pdf", impl="tools.pdf.imagenes_a_pdf:run", phase="F2", related=("imagenes-a-pdf",)),
    client("imagenes-a-pdf", "images-to-pdf", "Imágenes a PDF", "Images to PDF", ImagenesAPdfOptions, IMAGES, PDF,
           "Convierte fotos e imágenes en un PDF, sin recomprimir los JPEG.", "Turn photos and images into a PDF without recompressing JPEGs.",
           where="hybrid", worker_group="pdf", impl="tools.pdf.imagenes_a_pdf:run", related=("pdf-a-imagenes", "comprimir-pdf")),
    client("jpg-a-pdf", "jpg-to-pdf", "JPG a PDF", "JPG to PDF", ImagenesAPdfOptions, ("jpg",), PDF,
           "Convierte imágenes JPG en un PDF sin perder calidad.", "Convert JPG images into a PDF without losing quality.",
           where="hybrid", worker_group="pdf", impl="tools.pdf.imagenes_a_pdf:run", related=("pdf-a-jpg", "imagenes-a-pdf")),
    client("png-a-pdf", "png-to-pdf", "PNG a PDF", "PNG to PDF", ImagenesAPdfOptions, ("png",), PDF,
           "Convierte imágenes PNG en un PDF.", "Convert PNG images into a PDF.",
           where="hybrid", worker_group="pdf", impl="tools.pdf.imagenes_a_pdf:run", related=("pdf-a-png", "imagenes-a-pdf")),
    client("pdf-a-jpg", "pdf-to-jpg", "PDF a JPG", "PDF to JPG", PdfAImagenesOptions, PDF, ("jpg", "zip"),
           "Convierte cada página del PDF en una imagen JPG.", "Turn each PDF page into a JPG image.",
           where="hybrid", worker_group="pdf", impl="tools.pdf.pdf_a_imagenes:run", related=("jpg-a-pdf", "pdf-a-png")),
    client("pdf-a-png", "pdf-to-png", "PDF a PNG", "PDF to PNG", PdfAImagenesOptions, PDF, ("png", "zip"),
           "Convierte cada página del PDF en una imagen PNG.", "Turn each PDF page into a PNG image.",
           where="hybrid", worker_group="pdf", impl="tools.pdf.pdf_a_imagenes:run", related=("png-a-pdf", "pdf-a-jpg")),
    client("pdf-a-webp", "pdf-to-webp", "PDF a WEBP", "PDF to WEBP", PdfAImagenesOptions, PDF, ("webp", "zip"),
           "Convierte cada página del PDF en una imagen WEBP.", "Turn each PDF page into a WEBP image.", phase="F2",
           where="hybrid", worker_group="pdf", impl="tools.pdf.pdf_a_imagenes:run", related=("webp-a-pdf", "pdf-a-jpg")),
    client("pdf-a-imagenes", "pdf-to-images", "PDF a imágenes", "PDF to images", PdfAImagenesOptions, PDF, ("zip",),
           "Pasa uno o varios PDF a imágenes JPG, PNG o WEBP.", "Turn one or more PDFs into JPG, PNG or WEBP images.",
           where="hybrid", worker_group="pdf", impl="tools.pdf.pdf_a_imagenes:run", related=("imagenes-a-pdf",)),
    client("escaner-pdf", "pdf-scanner", "Escáner PDF", "PDF scanner", EscanerOptions, ("jpg", "png", "webp"), PDF,
           "Escanea documentos con la cámara del móvil: detecta los bordes, endereza la foto y crea el PDF en tu dispositivo.",
           "Scan documents with your phone camera: it finds the edges, straightens the photo and creates the PDF on your device.",
           phase="F2", related=("ocr-pdf", "imagenes-a-pdf", "comprimir-pdf")),
    client("generar-contrasena", "password-generator", "Generar contraseña", "Password generator", ContrasenaOptions, (), (),
           "Crea contraseñas seguras en tu navegador; nada sale del dispositivo.", "Create strong passwords in your browser; nothing leaves your device.",
           category="data", related=("proteger-pdf",)),
    client("png-a-jpg", "png-to-jpg", "PNG a JPG", "PNG to JPG", ImagenAJpgOptions, ("png",), ("jpg",),
           "Convierte imágenes PNG a JPG en tu navegador.", "Convert PNG images to JPG in your browser.", category="image", phase="F5",
           related=("webp-a-jpg", "comprimir-imagen")),
    client("webp-a-jpg", "webp-to-jpg", "WEBP a JPG", "WEBP to JPG", ImagenAJpgOptions, ("webp",), ("jpg",),
           "Convierte imágenes WEBP a JPG en tu navegador.", "Convert WEBP images to JPG in your browser.", category="image", phase="F5",
           related=("png-a-jpg", "comprimir-imagen")),
    client("comprimir-imagen", "compress-image", "Comprimir imagen", "Compress image", ComprimirImagenOptions, ("jpg", "png", "webp"), ("jpg", "png", "webp"),
           "Reduce el peso de tus fotos sin subirlas a ningún servidor.", "Make your photos smaller without uploading them anywhere.",
           category="image", phase="F5", related=("redimensionar-imagen",)),
    client("redimensionar-imagen", "resize-image", "Redimensionar imagen", "Resize image", RedimensionarOptions, ("jpg", "png", "webp"), ("jpg", "png", "webp"),
           "Cambia el tamaño de tus imágenes en el navegador.", "Resize your images in the browser.", category="image", phase="F5",
           related=("comprimir-imagen",)),
    image("jpg-a-png", "jpg-to-png", "JPG a PNG", "JPG to PNG", ImagenAPngOptions, ("jpg",), ("png", "zip"),
          "Convierte fotos JPG a PNG en tu navegador, sin subirlas.", "Convert JPG photos to PNG in your browser, without uploading them.",
          related=("png-a-jpg", "convertir-imagen")),
    image("webp-a-png", "webp-to-png", "WEBP a PNG", "WEBP to PNG", ImagenAPngOptions, ("webp",), ("png", "zip"),
          "Convierte imágenes WEBP a PNG conservando la transparencia.", "Convert WEBP images to PNG, keeping the transparency.",
          related=("webp-a-jpg", "convertir-imagen")),
    image("gif-a-png", "gif-to-png", "GIF a PNG", "GIF to PNG", NoOptions, ("gif",), ("png", "zip"),
          "Convierte GIF a PNG con su transparencia; de los animados, el primer fotograma.",
          "Convert GIF to PNG with its transparency; for animated ones, the first frame.", related=("convertir-imagen",)),
    image("jpg-a-webp", "jpg-to-webp", "JPG a WEBP", "JPG to WEBP", ImagenAWebpOptions, ("jpg",), ("webp", "zip"),
          "Convierte fotos JPG a WEBP, más ligero para tu web.", "Convert JPG photos to WEBP, lighter for your website.",
          related=("png-a-webp", "jpg-a-avif", "comprimir-imagen")),
    image("png-a-webp", "png-to-webp", "PNG a WEBP", "PNG to WEBP", ImagenAWebpOptions, ("png",), ("webp", "zip"),
          "Convierte PNG a WEBP con o sin pérdida, conservando la transparencia.", "Convert PNG to WEBP, lossy or lossless, keeping the transparency.",
          related=("jpg-a-webp", "webp-a-png")),
    image("avif-a-jpg", "avif-to-jpg", "AVIF a JPG", "AVIF to JPG", JpgOptions, ("avif",), ("jpg", "zip"),
          "Convierte imágenes AVIF a JPG, que se abre en cualquier programa.", "Convert AVIF images to JPG, which opens in any program.",
          related=("jpg-a-avif", "convertir-imagen")),
    image("jpg-a-avif", "jpg-to-avif", "JPG a AVIF", "JPG to AVIF", ImagenAAvifOptions, ("jpg",), ("avif", "zip"),
          "Convierte JPG a AVIF: la misma calidad en mucho menos espacio.", "Convert JPG to AVIF: the same quality in much less space.",
          related=("avif-a-jpg", "jpg-a-webp")),
    image("bmp-a-jpg", "bmp-to-jpg", "BMP a JPG", "BMP to JPG", JpgOptions, ("bmp",), ("jpg", "zip"),
          "Convierte imágenes BMP a JPG, que ocupan mucho menos.", "Convert BMP images to JPG, which take far less space.",
          related=("convertir-imagen",)),
    image("tiff-a-jpg", "tiff-to-jpg", "TIFF a JPG", "TIFF to JPG", TiffAJpgOptions, ("tiff",), ("jpg", "zip"),
          "Convierte TIFF a JPG, también los de varias páginas (una imagen por página).",
          "Convert TIFF to JPG, multi-page ones too (one image per page).", related=("tiff-a-pdf", "convertir-imagen")),
    image("png-a-ico", "png-to-ico", "PNG a ICO", "PNG to ICO", IcoOptions, ("png",), ("ico", "zip"),
          "Crea un icono ICO de Windows con varios tamaños a partir de un PNG.", "Create a Windows ICO icon with several sizes from a PNG.",
          related=("crear-favicon", "convertir-imagen")),
    image("convertir-imagen", "convert-image", "Convertir imagen", "Convert image", ConvertirImagenOptions, CONVERT_INPUTS, (*OUT_FORMATS, "zip"),
          "Convierte entre JPG, PNG, WEBP, AVIF, GIF, BMP, TIFF e ICO en tu navegador.",
          "Convert between JPG, PNG, WEBP, AVIF, GIF, BMP, TIFF and ICO in your browser.",
          related=("comprimir-imagen", "redimensionar-imagen", "quitar-metadatos-foto")),
    image("svg-a-png", "svg-to-png", "SVG a PNG", "SVG to PNG", SvgAPngOptions, ("svg",), ("png", "zip"),
          "Convierte SVG a PNG con transparencia, al tamaño que quieras.", "Convert SVG to PNG with transparency, at the size you want.",
          related=("svg-a-jpg", "svg-a-pdf", "crear-favicon")),
    image("svg-a-jpg", "svg-to-jpg", "SVG a JPG", "SVG to JPG", SvgAJpgOptions, ("svg",), ("jpg", "zip"),
          "Convierte SVG a JPG con el fondo y el tamaño que elijas.", "Convert SVG to JPG with the background and size you choose.",
          related=("svg-a-png", "svg-a-pdf")),
    image("crear-favicon", "favicon-generator", "Crear favicon", "Favicon generator", FaviconOptions, ("png", "jpg", "webp", "svg"),
          ("ico", "png", "zip"),
          "Crea el favicon de tu web: ICO, iconos de Apple y Android, manifiesto y el código HTML para pegar.",
          "Create your website's favicon: ICO, Apple and Android icons, manifest and the HTML code to paste.",
          max_files=1, related=("png-a-ico", "svg-a-png")),
    image("quitar-metadatos-foto", "remove-photo-metadata", "Quitar metadatos de fotos", "Remove photo metadata", QuitarMetadatosOptions,
          ("jpg", "png", "webp"), ("jpg", "png", "webp", "zip"),
          "Borra la ubicación GPS y los datos EXIF de tus fotos antes de compartirlas, sin perder calidad.",
          "Remove the GPS location and EXIF data from your photos before sharing them, without losing quality.",
          related=("comprimir-imagen", "eliminar-metadatos-pdf")),
    image("imagen-a-base64", "image-to-base64", "Imagen a Base64", "Image to Base64", Base64Options,
          ("jpg", "png", "webp", "gif", "svg", "avif", "bmp", "ico"), ("txt", "zip"),
          "Convierte una imagen en texto Base64 o data URI para HTML y CSS.", "Turn an image into Base64 text or a data URI for HTML and CSS.",
          related=("convertir-imagen",)),
    image("leer-codigo-qr", "qr-code-reader", "Leer código QR", "QR code reader", LeerQrOptions,
          ("jpg", "png", "webp", "gif", "bmp", "avif", "tiff", "svg", "pdf"), ("csv",),
          "Lee códigos QR y de barras de fotos, capturas y PDF sin subirlos.",
          "Read QR codes and barcodes from photos, screenshots and PDFs without uploading them.", related=("generar-codigo-qr",)),
    image("generar-codigo-qr", "qr-code-generator", "Generar código QR", "QR code generator", GenerarQrOptions, (), ("png", "svg", "pdf"),
          "Crea códigos QR de enlaces, WiFi, contactos, pagos SEPA y más, con colores, logotipo y comprobación de lectura.",
          "Create QR codes for links, WiFi, contacts, SEPA payments and more, with colours, a logo and a read check.",
          secret_fields=("wifi_contrasena",), related=("leer-codigo-qr", "crear-favicon")),
    client("crear-tarjeta", "card-maker", "Crear tarjeta", "Card maker", CrearTarjetaOptions, COLLAGE_INPUTS, ("pdf", "jpg", "png", "zip"),
           "Diseña postales y tarjetas dobladas con plantillas por ocasión, fotos, textos y QR, para imprimir en casa o en imprenta.",
           "Design postcards and folded cards with templates for each occasion, photos, text and QR codes, to print at home or at a print shop.",
           category="image", phase="F6", max_files=60, related=("crear-collage", "generar-codigo-qr", "imagenes-a-pdf")),
    client("mermaid-a-svg", "mermaid-to-svg", "Mermaid a SVG", "Mermaid to SVG", MermaidSvgOptions, ("mmd",), ("svg",),
           "Escribe o pega código Mermaid y descarga el diagrama en SVG, con vista previa en vivo y sin subir nada.",
           "Write or paste Mermaid code and download the diagram as SVG, with a live preview and nothing uploaded.",
           category="image", phase="F6", related=("mermaid-a-png", "svg-a-png", "drawio-a-pdf")),
    client("visor-3d", "3d-viewer", "Visor 3D", "3D viewer", NoOptions, MESH_VIEW, ("png",),
           "Abre STL, OBJ, 3MF, PLY, GLB y AMF en el navegador: gira, mide, corta en sección y guarda una captura.",
           "Open STL, OBJ, 3MF, PLY, GLB and AMF in your browser: orbit, measure, section and save a screenshot.",
           category="3d", phase="F7", max_files=20, related=("render-modelo-3d", "convertir-modelo-3d", "analizar-modelo-3d")),
    client("visor-gcode", "gcode-viewer", "Visor de G-code", "G-code viewer", NoOptions, ("gcode", "bgcode"), ("png",),
           "Mira capa a capa el G-code o el bgcode de tu impresora 3D, con tipos de extrusión, desplazamientos y reproducción.",
           "View your 3D printer's G-code or bgcode layer by layer, with extrusion types, travel moves and playback.",
           category="3d", phase="F7", max_files=1, related=("analizar-gcode", "gcode-a-imagen", "bgcode-a-gcode")),
    client("comprimir-glb", "compress-glb", "Comprimir GLB", "Compress GLB", ComprimirGlbOptions, ("glb", "gltf"), ("glb", "zip"),
           "Reduce el tamaño de modelos GLB con Draco o meshopt y texturas WebP, en tu navegador y sin subirlos.",
           "Shrink GLB models with Draco or meshopt and WebP textures, in your browser and without uploading them.",
           category="3d", phase="F7", max_files=20, related=("reducir-poligonos", "stl-a-glb", "visor-3d")),
    client("render-modelo-3d", "render-3d-model", "Render de modelo 3D", "Render 3D model", RenderModeloOptions, MESH_VIEW, ("png", "zip"),
           "Crea una imagen PNG de tu modelo 3D (STL, 3MF, GLB, OBJ…) desde el ángulo que quieras, con fondo transparente.",
           "Create a PNG image of your 3D model (STL, 3MF, GLB, OBJ…) from any angle, with a transparent background.",
           category="3d", phase="F7", max_files=20, related=("visor-3d", "convertir-modelo-3d", "extraer-miniatura-gcode")),
    client("mermaid-a-png", "mermaid-to-png", "Mermaid a PNG", "Mermaid to PNG", MermaidPngOptions, ("mmd",), ("png",),
           "Convierte diagramas Mermaid (flujos, secuencias, Gantt, clases…) en imágenes PNG nítidas en tu navegador.",
           "Turn Mermaid diagrams (flowcharts, sequences, Gantt, classes…) into sharp PNG images in your browser.",
           category="image", phase="F6", related=("mermaid-a-svg", "drawio-a-png", "svg-a-png")),
    image("crear-collage", "collage-maker", "Crear collage", "Collage maker", CrearCollageOptions, COLLAGE_INPUTS, ("pdf", "jpg", "png", "zip"),
          "Junta tus fotos en un collage con plantillas, textos, stickers y marcos, y descárgalo en PDF o imagen sin subirlas.",
          "Combine your photos in a collage with templates, text, stickers and frames, and download it as PDF or image without uploading them.",
          max_files=60, related=("imagenes-a-pdf", "redimensionar-imagen", "comprimir-imagen")),
]
