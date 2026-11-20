"""Opciones mínimas del Anexo A (docs/spec/a-*.md), en forma de tabla, para la prueba de contrato de 16.6.

Cada herramienta del Anexo A que ya está en el registro tiene aquí sus opciones con el nombre del campo de su
`options_schema`, el valor por defecto que fija el Anexo (entre corchetes en la especificación), los valores que tiene
que ofrecer cada lista y los rangos (entre paréntesis). `tests/test_contrato_opciones.py` lo comprueba contra el esquema
publicado (D-135). Lo que el Anexo pide y el esquema aún no tiene va en `PENDIENTES`, con el lote que lo resuelve: la
prueba falla si alguien lo implementa sin pasarlo a `MINIMOS`, o si la tabla dice algo que el esquema no cumple.

Las herramientas de fases posteriores añaden su fila cuando entran en el registro (receta de docs/goal/RECETAS.md).
"""
from __future__ import annotations

from dataclasses import dataclass

ANY = object()


@dataclass(frozen=True)
class Opt:
    """Una opción del Anexo A: campo del esquema, valor por defecto, valores ofrecidos y rango."""

    default: object = ANY
    values: tuple = ()
    ge: float | None = None
    le: float | None = None
    secret: bool = False


def D(default) -> Opt:  # noqa: N802 - notación compacta para la tabla
    return Opt(default=default)


def E(default, *values) -> Opt:  # noqa: N802
    return Opt(default=default, values=values)


def R(default, ge=None, le=None) -> Opt:  # noqa: N802
    return Opt(default=default, ge=ge, le=le)


X = Opt()  # el campo tiene que existir; el Anexo no fija valor por defecto
S = Opt(secret=True)  # contraseña: se publica como writeOnly y se sella por trabajo

PAPERS = ("A0", "A1", "A2", "A3", "A4", "A5", "A6", "Letter", "Legal")
GRID9 = ("arriba-izquierda", "arriba-centro", "arriba-derecha", "medio-izquierda", "centro", "medio-derecha",
         "abajo-izquierda", "abajo-centro", "abajo-derecha")
GRID6 = ("arriba-izquierda", "arriba-centro", "arriba-derecha", "abajo-izquierda", "abajo-centro", "abajo-derecha")
FONTS = ("sans", "serif", "mono")
BOXES = ("MediaBox", "CropBox", "BleedBox", "TrimBox", "ArtBox")
TRI = ("no_cambiar", "si", "no")

# A.1: imágenes a PDF.
IMAGENES_A_PDF = {
    "tamano_pagina": E("A4", *PAPERS, "segun_imagen", "personalizado"),
    "dpi": R(150, 1, 10000),
    "ancho": D(210), "alto": D(297), "unidad": E("mm", "mm", "in"),
    "orientacion": E("auto", "auto", "vertical", "horizontal"),
    "margen": E("0", "0", "5", "10", "15", "20", "25", "personalizado"),
    "unir": D(True), "marcadores": D(False),
    "ajuste": E("encajar", "encajar", "rellenar", "tamano_real"),
}

# A.8: Office con la ruta LibreOffice de Gotenberg.
OFFICE_A_PDF = {
    "formato": E("pdf", "pdf", "pdfa", "pdfua"),
    "paginas": D("todas"), "marcadores": D(True), "campos_formulario": D(True),
    "calidad_imagenes": D(90), "resolucion_maxima": D(300), "contrasena": S,
    "hoja_una_pagina": D(False), "diapositivas_ocultas": D(False), "paginas_notas": D(False), "comentarios_margen": D(False),
}

LIBROS_A_PDF = {"papel": E("A5", "A5", "A4", "Letter"), "margenes_mm": D(15), "tamano_letra": D(12), "indice": D(True)}

# A.9: imagen.
DESDE_PDF_IMAGEN = {
    "formato": E(ANY, "jpg", "png", "webp"), "color": E("color", "color", "gris"),
    "dpi": R(144, 72, 600), "calidad": D(85), "paginas": D("todas"),
    "salida": E("una_por_pagina", "una_por_pagina", "una_sola"),
    "organizacion": E("carpeta_por_archivo", "carpeta_por_archivo", "todas_juntas"),
}
MODO_OFFICE = E("editable", "editable", "editable_imagenes", "fiel")
DESDE_PDF_OFFICE = {"modo": MODO_OFFICE, "paginas": D("todas"), "ocr_si_no_hay_texto": D(True)}
DESDE_PDF_HOJAS = {"hojas": E("una_por_tabla", "una_por_tabla", "todas_en_una"), "paginas": D("todas"),
                   "ocr_si_no_hay_texto": D(True)}
DISENO = E("auto", "auto", "fijo", "fluido")

MINIMOS: dict[str, dict[str, Opt]] = {
    # --- A.1 Crear ---
    **{slug: IMAGENES_A_PDF for slug in ("imagenes-a-pdf", "jpg-a-pdf", "png-a-pdf", "webp-a-pdf", "gif-a-pdf", "bmp-a-pdf",
                                         "tiff-a-pdf")},
    "web-a-pdf": {
        "url": X, "papel": E("A4", "A4"), "orientacion": E("vertical", "vertical", "horizontal"), "margenes_mm": D(10),
        "imprimir_fondos": D(True), "una_pagina": D(False), "medio": E("print", "print", "screen"),
        "espera_s": R(1, 0, 10), "esquema": E("claro", "claro", "oscuro"),
    },
    "escaner-pdf": {
        "filtro": E("documento", "documento", "gris", "color", "original"),
        "tamano_pagina": E("auto", "auto", "A4", "Letter"), "ocr_al_terminar": D(False),
    },
    # Formato «Imprimir» lo ofrece la vista del collage, fuera del esquema.
    "crear-collage": {"papel": E("A4", "A4"), "orientacion": X, "formato": E("pdf", "pdf", "jpg", "png"), "resolucion": D(300)},
    "solicitud-de-empleo-pdf": {"marcadores": D(True), "indice": D(False), "comprimir": D(True), "umbral_mb": D(10)},
    "generar-codigo-qr": {
        "tipo": E("url", "url", "wifi", "texto", "vcard", "sepa", "paypal", "email", "telefono", "sms", "evento"),
        "wifi_ssid": X, "wifi_contrasena": X, "wifi_cifrado": E("WPA", "WPA", "WEP", "nopass"), "wifi_oculta": D(False),
        "vcard_nombre": X, "vcard_apellidos": X, "vcard_nombre_visible": X, "vcard_email": X, "vcard_empresa": X,
        "vcard_cargo": X, "vcard_web": X, "vcard_telefono": X,
        "vcard_tipo_telefono": E("trabajo", "trabajo", "movil", "personal", "otro"),
        "sepa_beneficiario": X, "sepa_iban": X, "sepa_bic": X, "sepa_importe": X, "sepa_concepto": X,
        "paypal_cuenta": X, "paypal_importe": X, "paypal_moneda": X,
        "logo_quitar_fondo": D(False), "logo_tamano": R(0.4, 0.1, 1), "logo_margen": R(0, 0, 100),
        "fondo": D("#FFFFFF"), "modulos": D("#000000"), "ojos_exteriores": D("#000000"), "ojos_interiores": D("#000000"),
        "fondo_degradado": E("ninguno", "ninguno", "lineal", "radial"),
        "modulos_degradado": E("ninguno", "ninguno", "lineal", "radial"),
        "fondo_angulo": E(0, 0, 45, 90, 135, 180, 225, 270, 315),
        "forma_modulos": X, "forma_ojos_exteriores": X, "forma_ojos_interiores": X,
        "borde_grosor": D(5), "borde_espaciado": D(20), "borde_color": D("#000000"),
        "forma": E("cuadrado", "cuadrado", "circulo"),
        "version": R(0, 0, 40),  # 0 es «auto»
        "modo": E("byte", "byte", "numerico", "alfanumerico", "kanji"), "correccion": E("Q", "Q", "L", "M", "H"),
        "tamano": R(500, 100, 10000), "formato": E("png", "png", "svg", "pdf"),
    },
    # --- A.3 Editar ---
    "editar-pdf": {"tamano_pagina_nueva": E(ANY, *PAPERS)},
    "anotar-pdf": {"guardar": E("anotaciones", "anotaciones", "aplanadas")},
    "rellenar-pdf": {"guardar": E("editable", "editable", "aplanado")},
    # A.3 (F4-B1): el diseño de campos es del editor; la ruta de servidor solo recibe los campos de firma.
    "hacer-pdf-rellenable": {}, "crear-formulario-pdf": {},
    "marca-de-agua-pdf": {
        "tipo": E("texto", "texto", "imagen"), "escala_imagen": D(50), "texto": D("CONFIDENCIAL"), "fuente": E(ANY, *FONTS),
        "tamano": R(40, 1, 500), "color": D("#E67610"), "opacidad": R(0.4, 0, 1), "angulo": D(-45),
        "posicion": E("centro", *GRID9, "mosaico"), "espacio_x": D(5), "espacio_y": D(5), "paginas": D("todas"),
        "capa": E("encima", "encima", "debajo"), "aplanar": D(False),
    },
    "numerar-paginas-pdf": {
        "patron": D("{NUM} / {CNT}"), "posicion": E("abajo-centro", *GRID9), "fuente": E(ANY, *FONTS),
        "tamano": R(8, 1, 100), "color": D("#000000"), "opacidad": R(1, 0, 1), "angulo": D(0),
        "margen_x": D(5), "margen_y": D(5), "primera_pagina": D(1), "primer_numero": D(1),
        "ultima_pagina": D(None), "total_fijo": D(None), "espejo": D(False),
        "estilo": E("arabigo", "arabigo", "romano", "letras"),
    },
    "superponer-pdf": {
        "posicion": E("fondo", "fondo", "primer_plano"), "repetir_ultima": D(True),
        "aplicar_a": E("todas", "todas", "primera", "rango"), "escalar": D(True),
    },
    "recortar-pdf": {
        "izquierda": D(0), "superior": D(0), "derecha": D(0), "inferior": D(0), "caja": E("CropBox", "CropBox", "TrimBox"),
        "modo_visual": D(False), "paginas": D("todas"), "automatico": X, "margen_seguridad": D(2), "pares_distintos": X,
    },
    "cambiar-tamano-pagina-pdf": {
        "tamano": E("A4", *PAPERS, "personalizado"), "unidad": E(ANY, "mm", "in"),
        "orientacion": E("auto", "auto", "vertical", "horizontal"), "paginas": D("todas"),
        "contenido": E("escalar", "escalar", "centrar"),
    },
    "metadatos-pdf": {name: X for name in ("titulo", "autor", "asunto", "palabras_clave", "fecha_creacion",
                                           "fecha_modificacion", "creador", "productor")},
    # --- A.4 Organizar ---
    "unir-pdf": {
        "ordenar_por_nombre": X, "rangos": X, "marcadores": D(False),
        "paginas_en_blanco": E("ninguna", "ninguna", "tras_cada_archivo", "tras_impares"),
        "portada": D(False), "indice": D(False), "nombre_en_paginas": D(False),
        "posicion_nombre": E("arriba-centro", *GRID6), "tamano_nombre": R(10, 4, 72),
    },
    "dividir-pdf": {
        "modo": E("cada_n", "cada_n", "pares_impares", "mitades", "personalizado", "marcadores", "tamano", "en_blanco"),
        "n": D(1), "dividir_despues": X, "tamano_mb": X, "patron_nombre": X,
    },
    "organizar-pdf": {"orden": X, "invertir": X, "intercalar": X},
    "eliminar-paginas-pdf": {"paginas": X},
    "extraer-paginas-pdf": {"paginas": X, "salida": E("un_pdf", "un_pdf", "un_pdf_por_pagina")},
    "girar-pdf": {"angulo": E(ANY, 90, -90, 180), "paginas": X, "por_pagina": X},
    "varias-paginas-por-hoja": {
        "por_hoja": E(2, 2, 3, 4, 6, 8, 9, 12, 16), "orden": E("horizontal", "horizontal", "vertical"),
        "hoja": E("A4", *PAPERS), "orientacion": D("auto"), "margenes": R(0, 0, 50), "direccion": E("ltr", "ltr", "rtl"),
        "bordes": D(False), "color_borde": D("#000000"), "ancho_borde": D(0.5),
    },
    "imprimir-pdf": {
        "paginas": E("todas", "todas", "rango", "impares", "pares"), "orden_inverso": D(False),
        "papel": E("A4", "A4", "Letter", "A3", "A5"), "escala": E("ajustar", "ajustar", "real"),
        "por_hoja": E(1, 1, 2, 4, 6, 9, 16), "orden": X, "bordes": D(False), "gris": D(False),
        "doble_cara": E("no", "no", "manual"), "reversos_invertidos": X, "formularios_anotaciones": D(True),
    },
    "folleto-pdf": {
        "papel": E("a4_a5", "a4_a5", "a3_a4", "letter_media_carta"), "encuadernacion": E("izquierda", "izquierda", "derecha"),
        "medianil": D(0), "hojas_por_cuadernillo": D(0),  # 0 es «todas en uno»
        "contraportada_al_final": D(True), "salida": E(ANY, "pdf", "manual"),
    },
    "cortar-paginas-por-la-mitad": {
        "corte": E("auto", "auto", "vertical", "horizontal"), "orden": E("izq_der", "izq_der", "der_izq"),
        "respetar_portadas": D(False), "deshacer_folleto": D(False),
    },
    "marcadores-pdf": {"items": X},
    "extraer-imagenes-pdf": {"formato": E("original", "original", "png", "jpg"), "min_px": D(32), "eliminar_duplicadas": D(True)},
    "copiar-de-pdf": {"ocr_si_no_hay_texto": X, "idiomas": X},
    # --- A.5 Optimizar y reparar ---
    "comprimir-pdf": {
        "nivel": E("equilibrado", "equilibrado", "fuerte", "sin_perdida", "personalizado"),
        "dpi": R(144, 10, 300), "calidad": R(75, 1, 100),
        **{name: D(True) for name in ("eliminar_miniaturas", "deduplicar", "rasterizar_vectoriales", "reducir_fuentes")},
        **{name: D(False) for name in ("compresion_moderna", "imagenes_gris", "flate_maximo", "aplanar_formularios",
                                       "quitar_output_intents", "quitar_adjuntos", "quitar_anotaciones", "quitar_marcadores",
                                       "quitar_metadatos", "quitar_estructura")},
    },
    "pdf-escala-de-grises": {"metodo": E("vectorial", "vectorial", "rasterizar")},
    "pdf-modo-oscuro": {"modo": E("conservar", "conservar", "negativo"), "fondo": E("gris_oscuro", "gris_oscuro", "negro"),
                        "saltar_oscuras": D(True)},
    "optimizar-pdf-web": {"comprimir_antes": D(False)},
    "ocr-pdf": {
        "idiomas": X, "salida": E("pdf", "pdf", "pdfa", "txt"), "enderezar": D(True), "autorrotar": D(False),
        "quitar_fondo": D(False), "limpiar": D(False), "texto_existente": E("omitir", "omitir", "forzar"), "unir": D(False),
        "titulo": X, "autor": X, "asunto": X, "palabras_clave": X,
    },
    "reparar-pdf": {},
    # Hasta 600 ppp en Pro (el límite del plan se aplica aparte, 9.3).
    "rasterizar-pdf": {"dpi": R(144, 10, 600), "calidad": D(75), "color": E("sin_cambios", "sin_cambios", "gris", "bn")},
    "aplanar-pdf": {"aplanar": E("formularios", "formularios", "anotaciones", "ambos")},
    "pdf-a-pdfa": {"nivel": E("2b", "2b", "1b", "2u", "3b", "2a", "3a")},
    # --- A.6 Seguridad ---
    "proteger-pdf": {
        "contrasena_apertura": S, "contrasena_propietario": S,
        **{f"permitir_{name}": D(True) for name in ("modificar", "comentar", "imprimir", "imprimir_alta", "ensamblar",
                                                     "formularios", "copiar", "copiar_accesibilidad")},
        "cifrado": E("aes256", "aes256", "aes128"),
    },
    "desbloquear-pdf": {"contrasena": S},
    "redactar-pdf": {"color": D("#000000"), "texto": D(""), "metodo": E("rasterizar", "rasterizar", "eliminar")},
    "eliminar-metadatos-pdf": {},
    "generar-contrasena": {
        "longitud": R(16, 8, 64), "mayusculas": D(True), "minusculas": D(True), "numeros": D(True), "simbolos": D(False),
        "excluir_ambiguos": D(False), "cantidad": R(1, 1, 20),
    },
    # --- A.7 Ver y comprobar ---
    "comparar-pdf": {"ignorar_mayusculas_espacios": D(False)},
    "buscar-en-pdf": {"texto": X, "mayusculas": D(False), "palabra_completa": D(False), "expresion_regular": D(False)},
    "validar-pdfa": {"perfil": E("auto", "auto", "1a", "1b", "2a", "2b", "2u", "3a", "3b", "3u", "4", "4e", "4f", "ua1", "ua2")},
    # A.2 (F4-D): validar-factura-electronica no tiene opciones (detecta sintaxis y especificación).
    "validar-factura-electronica": {},
    # A.2 (F4-D2): salida [PDF/A-3 con el XML incrustado] | PDF simple e idioma [el de la factura]; las páginas de 7.14 igual.
    **{slug: {"salida": E("pdfa3", "pdfa3", "pdf"), "idioma": E("factura", "factura", "es", "en")}
       for slug in ("factura-electronica-a-pdf", "facturae-a-pdf", "ubl-a-pdf", "cii-a-pdf")},
    # A.6 (F4-A2): la firma digital con el sello de la plataforma; el modo «Insertar firma», el origen de la firma y el
    # certificado propio llegan con F4-B (D-188).
    "firmar-pdf": {"certificado": E("plataforma", "plataforma"), "visible": D(True), "nivel": E("B-T", "B-T", "B-LT", "B-LTA"),
                   "certificacion": E("no", "no", "sin_cambios", "formularios", "formularios_anotaciones"),
                   "sello_tiempo": D(True), "nombre": X, "motivo": X, "lugar": X},
    # A.7 (F4): revocación OCSP y CRL «bajo petición» (apagada por defecto).
    "verificar-firmas-pdf": {"revocacion": D(False)},
    "preferencias-visor-pdf": {
        "quitar_todas": D(False),
        "diseno": E("no_cambiar", "SinglePage", "OneColumn", "TwoColumnLeft", "TwoColumnRight", "TwoPageLeft", "TwoPageRight"),
        "modo": E("no_cambiar", "FullScreen", "UseAttachments", "UseNone", "UseOC", "UseOutlines", "UseThumbs"),
        "pagina_inicial": X, "zoom_inicial": E("no_cambiar", "Fit", "FitH", "FitV", "personalizado"), "zoom_porcentaje": X,
        **{name: E("no_cambiar", *TRI) for name in ("centrar_ventana", "ajustar_ventana", "mostrar_titulo", "ocultar_menu",
                                                     "ocultar_barra", "ocultar_controles")},
        "modo_no_pantalla_completa": D("no_cambiar"),
        "duplex": E("no_cambiar", "Simplex", "DuplexFlipShortEdge", "DuplexFlipLongEdge"),
        **{name: E("no_cambiar", *BOXES) for name in ("area_impresion", "recorte_impresion", "area_vista", "recorte_vista")},
        "escalado_impresion": E("no_cambiar", "None", "AppDefault"), "direccion": E("no_cambiar", "L2R", "R2L"),
    },
    # --- A.8 Convertir a PDF ---
    **{slug: OFFICE_A_PDF for slug in ("convertir-a-pdf", "word-a-pdf", "excel-a-pdf", "ppt-a-pdf", "odt-a-pdf", "ods-a-pdf",
                                       "odp-a-pdf", "odg-a-pdf", "rtf-a-pdf", "csv-a-pdf", "publisher-a-pdf", "pub-a-pdf")},
    # 7.5 (F4): A.8 Office con el formato fijado a PDF/UA y sin las opciones de Excel y PowerPoint (D-182).
    "word-a-pdf-accesible": {"paginas": D("todas"), "marcadores": D(True), "campos_formulario": D(True), "calidad_imagenes": D(90),
                             "resolucion_maxima": D(300), "contrasena": S, "comentarios_margen": D(False)},
    "txt-a-pdf": {"fuente": E("monoespaciada", "monoespaciada", "proporcional"), "papel": D("A4"), "margenes_mm": D(20)},
    "markdown-a-pdf": {"tema": E("claro", "claro", "sobrio"), "papel": D("A4")},
    **{slug: LIBROS_A_PDF for slug in ("epub-a-pdf", "mobi-a-pdf", "azw3-a-pdf", "fb2-a-pdf")},
    "svg-a-pdf": {"tamano": E("svg", "svg", "a4")},
    # --- A.9 Convertir desde PDF ---
    "convertir-desde-pdf": {
        "formato": E(ANY, "txt", "rtf", "html", "docx", "pptx", "xlsx", "odt", "odp", "ods", "png", "jpg", "webp", "tiff",
                     "svg", "pdfa", "epub", "md", "csv", "json"),
        "paginas": D("todas"), "modo": MODO_OFFICE, "ocr_si_no_hay_texto": D(True),
        "color": E("color", "color", "cmyk", "gris", "bn"),
        "compresion_bn": E("g4", "g4", "g3_1d", "g3_1d_eol", "g3_2d", "lzw", "packbits"),
        "dpi": R(144, 72, 600), "calidad": D(85), "multipagina": D(True), "salida": E("una_por_pagina", "una_por_pagina", "una_sola"),
        "hojas": E("una_por_tabla", "una_por_tabla", "todas_en_una"), "diseno": DISENO,
        "imagenes": E("incluidas", "incluidas", "sin"), "quitar_encabezados": D(True),
    },
    **{slug: DESDE_PDF_OFFICE for slug in ("pdf-a-word", "pdf-a-odt", "pdf-a-rtf", "pdf-a-ppt", "pdf-a-odp")},
    **{slug: DESDE_PDF_HOJAS for slug in ("pdf-a-excel", "pdf-a-ods")},
    "pdf-a-html": {"diseno": DISENO, "paginas": D("todas")},
    "pdf-a-epub": {"diseno": DISENO, "paginas": D("todas")},
    "pdf-a-markdown": {"imagenes": E("incluidas", "incluidas", "sin"), "quitar_encabezados": D(True), "paginas": D("todas")},
    "pdf-a-txt": {"paginas": D("todas"), "ocr_si_no_hay_texto": D(True)},
    "pdf-a-csv": {"paginas": D("todas")},
    "pdf-a-json": {"paginas": D("todas")},
    "pdf-a-svg": {"paginas": D("todas")},
    "pdf-a-tiff": {
        "color": E("color", "color", "cmyk", "gris", "bn"),
        "compresion_bn": E("g4", "g4", "g3_1d", "g3_1d_eol", "g3_2d", "lzw", "packbits"),
        "dpi": R(144, 72, 600), "multipagina": D(True), "salida": E("una_por_pagina", "una_por_pagina", "una_sola"),
        "paginas": D("todas"),
    },
    # La página fija el formato con su preajuste; el esquema es el mismo de pdf-a-imagenes.
    **{slug: DESDE_PDF_IMAGEN for slug in ("pdf-a-imagenes", "pdf-a-jpg", "pdf-a-png", "pdf-a-webp")},
    # --- A.10 Imágenes ---
    "svg-a-png": {"tamano": E("original", "original", "2x", "3x", "4x", "ancho"), "ancho": R(1000, 1, 16384)},
    "svg-a-jpg": {"tamano": E("original", "original", "2x", "3x", "4x", "ancho"), "ancho": R(1000, 1, 16384),
                  "fondo": D("#FFFFFF"), "calidad": D(90)},
    "webp-a-jpg": {"calidad": D(90), "fondo": D("#FFFFFF"), "conservar_metadatos": D(False)},
    "webp-a-png": {"conservar_metadatos": D(False)},
    "heic-a-jpg": {"calidad": D(90), "conservar_exif": D(True), "quitar_gps": D(True)},
    "heic-a-png": {"conservar_exif": D(True), "quitar_gps": D(True)},
}

# Lo que el Anexo A pide y el esquema todavía no tiene: (herramienta, opción o valor) -> lote que lo resuelve.
PENDIENTES: dict[tuple[str, str], str] = {
    # A.4 Extra: autoorientar con la detección de orientación de Tesseract, en servidor (docs/goal/huecos.json).
    ("girar-pdf", "autoorientar"): "hueco de A.4, sin lote asignado",
    # A.9: el Modo (Editable | con imágenes | Fiel) también para XLSX, ODS y TXT (D-61 y D-72 no lo ofrecen).
    ("pdf-a-excel", "modo"): "hueco de A.9, sin lote asignado",
    ("pdf-a-ods", "modo"): "hueco de A.9, sin lote asignado",
    ("pdf-a-txt", "modo"): "hueco de A.9, sin lote asignado",
}
