"""Grupo utils (F4 y F6): facturas electrónicas con KoSIT en modo servicio dentro de `workerutils` (5.4 y 7.23) y
conversiones de documentos y datos (7.12 y 7.13)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

from core.options import opt
from core.registry import AiSpec, ToolSpec


class APdfOptions(BaseModel):
    """factura-electronica-a-pdf (A.2): salida [PDF/A-3 con el XML original incrustado byte a byte] | PDF simple e idioma de
    la representación [el de la factura]."""

    salida: Literal["pdfa3", "pdf"] = opt("pdfa3", "Salida", "Output", labels={
        "pdfa3": ("PDF/A-3 con el XML original incrustado", "PDF/A-3 with the original XML embedded"),
        "pdf": ("PDF simple", "Plain PDF")})
    idioma: Literal["factura", "es", "en"] = opt("factura", "Idioma de la representación", "Representation language", labels={
        "factura": ("El de la factura", "The invoice's"), "es": ("Español", "Spanish"), "en": ("Inglés", "English")})


def a_pdf(slug_es: str, slug_en: str, name_es: str, name_en: str, summary_es: str, summary_en: str, related: tuple[str, ...]) -> ToolSpec:
    # 7.14 y A.2 (F4-D2): plantilla HTML, Chromium de gotenberg, PDF/A-3b con el XML incrustado y veraPDF en `ocr`.
    return ToolSpec(slug_es=slug_es, slug_en=slug_en, name_es=name_es, name_en=name_en, category="invoice", where="server",
                    inputs=("xml",), outputs=("pdf", "zip"), options=APdfOptions, worker_group="utils", queue_kind="light",
                    cost_class="light", impl="tools.utils.facturas.convertir:run", launch=True, phase="F4", time_limit=900,
                    max_files=100, summary_es=summary_es, summary_en=summary_en, related=related)

class Parte(BaseModel):
    """Emisor o cliente de crear-factura-electronica (EN 16931: BG-4 y BG-7)."""

    nombre: str = opt("", "Nombre o razón social", "Name or company name", max_length=200)
    nif: str = opt("", "NIF o identificador de IVA", "Tax or VAT ID", max_length=30)
    direccion: str = opt("", "Dirección", "Address", max_length=200)
    cp: str = opt("", "Código postal", "Postcode", max_length=20)
    ciudad: str = opt("", "Población", "City", max_length=100)
    provincia: str = opt("", "Provincia", "Province", max_length=100)
    pais: str = opt("ES", "País (ISO 3166-1)", "Country (ISO 3166-1)", pattern=r"^[A-Z]{2}$", max_length=2)
    correo: str = opt("", "Correo", "Email", max_length=200)
    telefono: str = opt("", "Teléfono", "Phone", max_length=40)
    contacto: str = opt("", "Persona de contacto", "Contact person", max_length=120)
    endpoint_esquema: str = opt("9920", "Esquema de la dirección electrónica (EAS)", "Electronic address scheme (EAS)", max_length=10)
    endpoint_id: str = opt("", "Dirección electrónica (Peppol, XRechnung)", "Electronic address (Peppol, XRechnung)", max_length=200)
    tipo_persona: Literal["", "F", "J"] = opt("", "Persona física o jurídica (Facturae; vacío: según el NIF)",
                                              "Individual or legal entity (Facturae; empty: from the tax ID)", labels={
        "": ("Según el NIF", "From the tax ID"), "F": ("Persona física", "Individual"), "J": ("Persona jurídica", "Legal entity")})


class Linea(BaseModel):
    descripcion: str = opt("", "Descripción", "Description", max_length=1000)
    cantidad: float = opt(1, "Cantidad", "Quantity", ge=-1e9, le=1e9)  # negativa en una devolución; 0 no (problems)
    unidad: str = opt("ud", "Unidad", "Unit", max_length=20)
    precio: float = opt(0, "Precio sin IVA", "Price excl. VAT", ge=0, le=1e12)
    descuento: float = opt(0, "Descuento (%)", "Discount (%)", ge=0, le=100)
    iva: float = opt(21, "IVA (%)", "VAT (%)", ge=0, le=100)


class FacturaE(BaseModel):
    numero: str = opt("", "Número", "Number", max_length=60)
    fecha: str = opt("2026-01-01", "Fecha de expedición", "Issue date", pattern=r"^\d{4}-\d{2}-\d{2}$")
    vencimiento: str = opt("", "Vencimiento", "Due date", pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    fecha_operacion: str = opt("", "Fecha de la operación, si no es la de expedición", "Date of supply, if not the issue date",
                               pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    moneda: str = opt("EUR", "Moneda", "Currency", pattern=r"^[A-Z]{3}$")
    idioma: Literal["es", "en"] = opt("es", "Idioma", "Language")
    referencia_comprador: str = opt("", "Referencia del comprador (Leitweg-ID en XRechnung)", "Buyer reference (Leitweg-ID in XRechnung)", max_length=200)
    pedido: str = opt("", "Referencia del pedido", "Order reference", max_length=200)
    emisor: Parte = opt(Parte(), "Emisor", "Seller")
    cliente: Parte = opt(Parte(), "Cliente", "Buyer")
    lineas: list[Linea] = opt([], "Conceptos", "Items", max_length=500)
    recargo: bool = opt(False, "Recargo de equivalencia (solo Facturae)", "Equivalence surcharge (Facturae only)")
    irpf: float = opt(0, "Retención de IRPF (%, solo Facturae)", "Income tax withholding (%, Facturae only)", ge=0, le=50)
    forma_pago: Literal["", "10", "30", "48", "49", "58", "59"] = opt("58", "Forma de pago (UNTDID 4461)", "Payment means (UNTDID 4461)", labels={
        "": ("Sin indicar", "Not given"), "10": ("Efectivo", "Cash"), "30": ("Transferencia", "Credit transfer"),
        "48": ("Tarjeta", "Card"), "49": ("Domiciliación", "Direct debit"), "58": ("Transferencia SEPA", "SEPA credit transfer"),
        "59": ("Adeudo SEPA", "SEPA direct debit")})
    iban: str = opt("", "IBAN", "IBAN", max_length=40)
    condiciones_pago: str = opt("", "Condiciones de pago", "Payment terms", max_length=500)
    notas: str = opt("", "Observaciones", "Notes", max_length=2000)
    motivo_exencion: str = opt("", "Motivo de la exención (IVA 0 %)", "Exemption reason (0 % VAT)", max_length=500)
    causa_exencion: Literal["", "art20", "art21", "art25", "isp", "nosujeta"] = opt(
        "", "Causa del IVA 0 %", "Reason for 0 % VAT", labels={
            "": ("Sin indicar (exenta)", "Not given (exempt)"), "art20": ("Exenta (art. 20)", "Exempt (art. 20)"),
            "art21": ("Exportación (art. 21)", "Export (art. 21)"), "art25": ("Entrega intracomunitaria (art. 25)", "Intra-Community supply (art. 25)"),
            "isp": ("Inversión del sujeto pasivo (art. 84)", "Reverse charge (art. 84)"), "nosujeta": ("No sujeta (art. 7)", "Not subject (art. 7)")})
    tipo_cambio: float = opt(0, "Euros por unidad de la moneda (otra moneda)", "Euros per currency unit (other currency)", ge=0, le=1e6)
    oficina_contable: str = opt("", "Oficina contable (DIR3, FACe)", "Accounting office (DIR3, FACe)", max_length=10)
    organo_gestor: str = opt("", "Órgano gestor (DIR3, FACe)", "Managing body (DIR3, FACe)", max_length=10)
    unidad_tramitadora: str = opt("", "Unidad tramitadora (DIR3, FACe)", "Processing unit (DIR3, FACe)", max_length=10)
    texto_descuento: str = opt("Descuento", "Texto de los descuentos", "Discount text", max_length=100)


FORMATS = {"facturx": ("Factur-X / ZUGFeRD (PDF con el XML)", "Factur-X / ZUGFeRD (PDF with the XML)"),
           "xrechnung_cii": ("XRechnung CII", "XRechnung CII"), "xrechnung_ubl": ("XRechnung UBL", "XRechnung UBL"),
           "peppol": ("Peppol BIS Billing 3.0", "Peppol BIS Billing 3.0"),
           "ubl": ("UBL 2.1 (EN 16931, solución pública española)", "UBL 2.1 (EN 16931, Spanish public solution)"),
           "facturae": ("Facturae 3.2.2", "Facturae 3.2.2")}
PROFILES = {"minimum": ("MINIMUM (no es una factura EN 16931 completa)", "MINIMUM (not a complete EN 16931 invoice)"),
            "basicwl": ("BASIC WL (no es una factura EN 16931 completa)", "BASIC WL (not a complete EN 16931 invoice)"),
            "basic": ("BASIC", "BASIC"), "en16931": ("EN 16931", "EN 16931"), "extended": ("EXTENDED", "EXTENDED"),
            "xrechnung": ("XRECHNUNG", "XRECHNUNG")}


class CrearFacturaElectronicaOptions(BaseModel):
    """crear-factura-electronica (A.2, F4-E2, D-205): la página manda la factura del formulario EN 16931."""

    formato: Literal[tuple(FORMATS)] = opt("facturx", "Formato", "Format", labels=FORMATS)
    perfil: Literal[tuple(PROFILES)] = opt("en16931", "Perfil Factur-X", "Factur-X profile", labels=PROFILES,
                                           show_if={"formato": ("facturx",)})
    factura: FacturaE = opt(FacturaE(), "Factura", "Invoice", advanced=True)


class PdfAFacturaOptions(BaseModel):
    """pdf-a-factura-electronica (A.2, F4-E3, D-208): perfil Factur-X [EN 16931]. La página crea dos trabajos: `extraer`
    (los datos para el formulario de revisión, con IA solo si se pide y se consiente) y `generar` (con la factura revisada)."""

    fase: Literal["extraer", "generar"] = opt("extraer", "Paso", "Step", advanced=True, labels={
        "extraer": ("Leer los datos de la factura", "Read the invoice data"), "generar": ("Generar el Factur-X", "Generate the Factur-X")})
    perfil: Literal["en16931"] = opt("en16931", "Perfil Factur-X", "Factur-X profile", labels={"en16931": ("EN 16931", "EN 16931")})
    ia: bool = opt(False, "Leer los datos con IA (una petición)", "Read the data with AI (one request)", show_if={"fase": ("extraer",)})
    factura: FacturaE = opt(FacturaE(), "Factura revisada", "Reviewed invoice", advanced=True, show_if={"fase": ("generar",)})

    @model_validator(mode="after")
    def _no_ai_when_generating(self):
        # «generar» no llama al modelo: con `ia` no reservaría peticiones ni pediría consentimiento para nada.
        if self.fase == "generar":
            self.ia = False
        return self


# --- F6-A (7.12, D-212): documentos con pandoc estático y siempre con --sandbox. El Anexo A no fija opciones. ---------

FLAVORS = {"gfm": ("GitHub (GFM)", "GitHub (GFM)"), "commonmark": ("CommonMark", "CommonMark"),
           "markdown": ("Markdown de pandoc", "Pandoc Markdown")}


class DocxMarkdownOptions(BaseModel):
    """docx-a-markdown (D-212): sabor [GitHub] | CommonMark | pandoc e imágenes [carpeta media/ en un ZIP] | dentro del
    Markdown | sin imágenes."""

    sabor: Literal["gfm", "commonmark", "markdown"] = opt("gfm", "Sabor de Markdown", "Markdown flavor", labels=FLAVORS)
    imagenes: Literal["carpeta", "incrustadas", "omitir"] = opt("carpeta", "Imágenes", "Images", labels={
        "carpeta": ("En una carpeta (ZIP con el .md)", "In a folder (ZIP with the .md)"),
        "incrustadas": ("Dentro del Markdown (data:)", "Inside the Markdown (data:)"),
        "omitir": ("Sin imágenes (solo el texto alternativo)", "No images (alt text only)")})


class MarkdownDocxOptions(BaseModel):
    """markdown-a-docx (D-212): sabor [GitHub] | CommonMark | pandoc, índice [no] y secciones numeradas [no]."""

    sabor: Literal["gfm", "commonmark", "markdown"] = opt("gfm", "Sabor de Markdown", "Markdown flavor", labels=FLAVORS)
    indice: bool = opt(False, "Añadir índice", "Add table of contents")
    numerar: bool = opt(False, "Numerar los títulos", "Number the headings")


class IndiceOptions(BaseModel):
    """docx-a-html y html-a-docx (D-212): índice [no]."""

    indice: bool = opt(False, "Añadir índice", "Add table of contents")


def documento(slug_es: str, slug_en: str, name_es: str, name_en: str, inputs: tuple[str, ...], outputs: tuple[str, ...],
              summary_es: str, summary_en: str, related: tuple[str, ...], options: type[BaseModel] | None = None) -> ToolSpec:
    # 7.12 (F6-A, D-212): pandoc es GPL, así que solo como proceso externo en workerutils (11), siempre con --sandbox (12.3).
    extra = {"options": options} if options else {}
    return ToolSpec(slug_es=slug_es, slug_en=slug_en, name_es=name_es, name_en=name_en, category="office", where="server",
                    inputs=inputs, outputs=(*outputs, "zip"), worker_group="utils", queue_kind="light", cost_class="light",
                    impl="tools.utils.documentos:run", launch=True, phase="F6", time_limit=1800, max_files=20,
                    summary_es=summary_es, summary_en=summary_en, related=related, **extra)


# --- F6-B (7.12, D-213 y D-214): hojas de cálculo y datos con openpyxl, la biblioteca estándar, defusedxml y PyYAML. ----
# El Anexo A no fija opciones.

SEPARATORS = {"coma": ("Coma (,)", "Comma (,)"), "punto_y_coma": ("Punto y coma (;)", "Semicolon (;)"),
              "tabulador": ("Tabulador", "Tab")}
DETECT_SEPARATORS = {"auto": ("Detectar", "Detect"), **SEPARATORS, "barra": ("Barra vertical (|)", "Pipe (|)")}
DECIMALS = {"punto": ("Punto (1234.5)", "Point (1234.5)"), "coma": ("Coma (1234,5)", "Comma (1234,5)")}
OUT_ENCODINGS = {"utf-8": ("UTF-8", "UTF-8"), "utf-8-bom": ("UTF-8 con BOM (para Excel)", "UTF-8 with BOM (for Excel)"),
                 "windows-1252": ("Windows-1252 (Excel antiguo)", "Windows-1252 (old Excel)")}
SHEETS = {"activa": ("La hoja activa", "The active sheet"), "todas": ("Todas (un archivo por hoja)", "All (one file per sheet)")}
SHAPES = {"objetos": ("Objetos con la primera fila como claves", "Objects with the first row as keys"),
          "filas": ("Listas de valores, fila a fila", "Lists of values, row by row")}


class XlsxCsvOptions(BaseModel):
    """xlsx-a-csv (D-213): hojas [la activa] | todas, separador [coma] | punto y coma | tabulador, decimal [punto] | coma
    y codificación [UTF-8] | UTF-8 con BOM | Windows-1252."""

    hojas: Literal["activa", "todas"] = opt("activa", "Hojas", "Sheets", labels=SHEETS)
    separador: Literal["coma", "punto_y_coma", "tabulador"] = opt("coma", "Separador", "Separator", labels=SEPARATORS)
    decimal: Literal["punto", "coma"] = opt("punto", "Separador decimal", "Decimal separator", labels=DECIMALS)
    codificacion: Literal["utf-8", "utf-8-bom", "windows-1252"] = opt("utf-8", "Codificación", "Encoding", labels=OUT_ENCODINGS)


class CsvXlsxOptions(BaseModel):
    """csv-a-xlsx (D-213): separador [detectar], decimal [detectar], tipos [convertir números y fechas ISO], encabezado
    [primera fila en negrita, fija y con filtros] y libro [uno por archivo] | uno con una hoja por archivo."""

    separador: Literal["auto", "coma", "punto_y_coma", "tabulador", "barra"] = opt("auto", "Separador", "Separator",
                                                                                   labels=DETECT_SEPARATORS)
    decimal: Literal["auto", "punto", "coma"] = opt("auto", "Separador decimal", "Decimal separator",
                                                    labels={"auto": ("Detectar", "Detect"), **DECIMALS})
    tipos: bool = opt(True, "Convertir números y fechas", "Convert numbers and dates")
    encabezado: bool = opt(True, "La primera fila es el encabezado", "The first row is the header")
    libro: Literal["separados", "uno"] = opt("separados", "Varios CSV", "Several CSV files", labels={
        "separados": ("Un libro por archivo", "One workbook per file"),
        "uno": ("Un solo libro, una hoja por archivo", "One workbook, one sheet per file")})


class ExcelJsonOptions(BaseModel):
    """excel-a-json (D-213): forma [objetos con la primera fila como claves] | filas y hojas [la activa] | todas."""

    forma: Literal["objetos", "filas"] = opt("objetos", "Forma", "Shape", labels=SHAPES)
    hojas: Literal["activa", "todas"] = opt("activa", "Hojas", "Sheets", labels={
        "activa": ("La hoja activa", "The active sheet"), "todas": ("Todas (un objeto por hoja)", "All (one object per sheet)")})


class CodificacionCsvOptions(BaseModel):
    """arreglar-codificacion-csv (D-213): origen [detectar] | Windows-1252 | ISO-8859-1 | ISO-8859-15 | MS-DOS (CP850) |
    Mac Roman | UTF-16 y salida [UTF-8 con BOM] | UTF-8."""

    origen: Literal["auto", "windows-1252", "iso-8859-1", "iso-8859-15", "cp850", "mac-roman", "utf-16"] = opt(
        "auto", "Codificación de origen", "Source encoding", labels={
            "auto": ("Detectar", "Detect"), "windows-1252": ("Windows-1252", "Windows-1252"),
            "iso-8859-1": ("ISO-8859-1 (Latin-1)", "ISO-8859-1 (Latin-1)"), "iso-8859-15": ("ISO-8859-15 (Latin-9)", "ISO-8859-15 (Latin-9)"),
            "cp850": ("MS-DOS (CP850)", "MS-DOS (CP850)"), "mac-roman": ("Mac Roman", "Mac Roman"), "utf-16": ("UTF-16", "UTF-16")})
    salida: Literal["utf-8-bom", "utf-8"] = opt("utf-8-bom", "Salida", "Output", labels={
        "utf-8-bom": ("UTF-8 con BOM (Excel lo abre bien)", "UTF-8 with BOM (Excel opens it correctly)"),
        "utf-8": ("UTF-8 sin BOM", "UTF-8 without BOM")})


class CsvJsonOptions(BaseModel):
    """csv-a-json (D-214): separador [detectar], forma [objetos] | filas y tipos [números, verdadero/falso y vacíos como
    null]."""

    separador: Literal["auto", "coma", "punto_y_coma", "tabulador", "barra"] = opt("auto", "Separador", "Separator",
                                                                                   labels=DETECT_SEPARATORS)
    forma: Literal["objetos", "filas"] = opt("objetos", "Forma", "Shape", labels=SHAPES)
    tipos: bool = opt(True, "Convertir números, true/false y vacíos", "Convert numbers, true/false and empty values")


class JsonCsvOptions(BaseModel):
    """json-a-csv (D-214): separador [coma] | punto y coma | tabulador y codificación [UTF-8] | UTF-8 con BOM."""

    separador: Literal["coma", "punto_y_coma", "tabulador"] = opt("coma", "Separador", "Separator", labels=SEPARATORS)
    codificacion: Literal["utf-8", "utf-8-bom"] = opt("utf-8", "Codificación", "Encoding", labels={
        "utf-8": ("UTF-8", "UTF-8"), "utf-8-bom": ("UTF-8 con BOM (para Excel)", "UTF-8 with BOM (for Excel)")})


class JsonXmlOptions(BaseModel):
    """json-a-xml (D-214): elemento raíz [root] y elemento de cada valor de una lista [item]."""

    raiz: str = opt("root", "Elemento raíz", "Root element", pattern=r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$", max_length=64)
    elemento: str = opt("item", "Elemento de cada valor de una lista", "Element for each list value",
                        pattern=r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$", max_length=64)


class XmlJsonOptions(BaseModel):
    """xml-a-json (D-214): tipos [no: el texto sigue siendo texto] | números y true/false."""

    tipos: bool = opt(False, "Convertir números y true/false", "Convert numbers and true/false")


def datos(slug_es: str, slug_en: str, name_es: str, name_en: str, inputs: tuple[str, ...], outputs: tuple[str, ...],
          summary_es: str, summary_en: str, related: tuple[str, ...], options: type[BaseModel] | None = None,
          category: str = "data", group: str = "utils", impl: str = "tools.utils.datos:run", time_limit: int = 600) -> ToolSpec:
    # 7.12 (F6-B, D-213 y D-214): sin motores externos salvo LibreOffice para ODS, que va en workeroffice.
    extra = {"options": options} if options else {}
    return ToolSpec(slug_es=slug_es, slug_en=slug_en, name_es=name_es, name_en=name_en, category=category, where="server",
                    inputs=inputs, outputs=(*outputs, "zip"), worker_group=group, queue_kind="light", cost_class="light",
                    impl=impl, launch=True, phase="F6", time_limit=time_limit, max_files=20,
                    summary_es=summary_es, summary_en=summary_en, related=related, **extra)


# --- F6-E (7.13, D-217): comprimidos con libarchive y subtítulos con pysubs2. El Anexo A no fija opciones. -------------


class ContrasenaArchivoOptions(BaseModel):
    """extraer-archivo-online (D-217): contraseña de un ZIP cifrado (los RAR y 7z cifrados no se admiten)."""

    contrasena: str | None = opt(None, "Contraseña (solo ZIP cifrados)", "Password (encrypted ZIP only)", advanced=True,
                                 max_length=127)


class SubtitulosOptions(BaseModel):
    """srt-a-vtt, vtt-a-srt y ass-a-srt (D-217): etiquetas de estilo [conservar negrita, cursiva, subrayado y tachado] |
    quitarlas."""

    etiquetas: Literal["conservar", "quitar"] = opt("conservar", "Estilo del texto", "Text style", labels={
        "conservar": ("Conservar negrita, cursiva, subrayado y tachado", "Keep bold, italics, underline and strikethrough"),
        "quitar": ("Solo texto", "Plain text only")})


# --- F6-H1 (7.13, D-220): rutas y mapas. El Anexo A no fija opciones. --------------------------------------------------


class CsvKmlOptions(BaseModel):
    """csv-a-kml (D-220): columnas de latitud y longitud [detectar por el nombre: lat, latitud, lon, lng, longitud…]."""

    columna_latitud: str = opt("", "Columna de latitud (vacío: detectar)", "Latitude column (empty: detect)", advanced=True,
                               max_length=100)
    columna_longitud: str = opt("", "Columna de longitud (vacío: detectar)", "Longitude column (empty: detect)", advanced=True,
                                max_length=100)


# --- F6-I (7.13, D-224): contactos y calendarios. El Anexo A no fija opciones. ----------------------------------------

ZONES = {z: (z.replace("_", " "), z.replace("_", " ")) for z in (
    "Europe/Madrid", "Atlantic/Canary", "Europe/Lisbon", "Europe/London", "Europe/Paris", "UTC", "America/Mexico_City",
    "America/Bogota", "America/Lima", "America/Santiago", "America/Argentina/Buenos_Aires", "America/Caracas",
    "America/New_York", "America/Chicago", "America/Los_Angeles")}


class VcfOptions(BaseModel):
    """vcf-a-csv y vcf-a-excel (D-224): plantilla [Google Contacts] | Outlook | propia (7.13)."""

    plantilla: Literal["google", "outlook", "generico"] = opt("google", "Columnas", "Columns", labels={
        "google": ("Plantilla de Google Contacts", "Google Contacts template"), "outlook": ("Plantilla de Outlook", "Outlook template"),
        "generico": ("Una columna por dato, en tu idioma", "One column per field, in your language")})


class IcsOptions(BaseModel):
    """ics-a-csv e ics-a-excel (D-224, D-230): columnas [completas, con zona horaria y repetición] | Google Calendar | Outlook;
    en estas dos, la zona horaria de las horas [la del calendario: X-WR-TIMEZONE o Madrid]."""

    plantilla: Literal["completo", "google", "outlook"] = opt("completo", "Columnas", "Columns", labels={
        "completo": ("Completas (zona horaria, asistentes, repetición)", "Full (time zone, attendees, recurrence)"),
        "google": ("Plantilla de Google Calendar", "Google Calendar template"), "outlook": ("Plantilla de Outlook", "Outlook template")})
    zona: Literal[("calendario",) + tuple(ZONES)] = opt(
        "calendario", "Zona horaria de las horas", "Time zone of the times", show_if={"plantilla": ("google", "outlook")},
        labels={"calendario": ("La del calendario (o Madrid)", "The calendar's own (or Madrid)"), **ZONES})


class CsvIcsOptions(BaseModel):
    """csv-a-ics (D-224): zona horaria [Europe/Madrid] y orden de las fechas [detectar: mes/día con columnas en inglés]."""

    zona: Literal[tuple(ZONES)] = opt("Europe/Madrid", "Zona horaria de las horas del CSV", "Time zone of the CSV times", labels=ZONES)
    formato_fecha: Literal["auto", "dia_mes", "mes_dia"] = opt("auto", "Fechas como 03/04/2026", "Dates such as 03/04/2026", labels={
        "auto": ("Detectar (mes/día si las columnas están en inglés)", "Detect (month/day if the columns are in English)"),
        "dia_mes": ("Día/mes (3 de abril)", "Day/month (3 April)"), "mes_dia": ("Mes/día (4 de marzo)", "Month/day (March 4)")})


# --- F6-K (7.13, D-227): draw.io y LaTeX. El Anexo A no fija opciones. --------------------------------------------------


class DrawioPdfOptions(BaseModel):
    """drawio-a-pdf (D-227): papel [A4] | A3 | Letter, orientación [automática] y ajustar el diagrama a la página [sí]."""

    papel: Literal["A4", "A3", "Letter"] = opt("A4", "Papel", "Paper", labels={k: (k, k) for k in ("A4", "A3", "Letter")})
    orientacion: Literal["auto", "vertical", "horizontal"] = opt("auto", "Orientación", "Orientation", labels={
        "auto": ("Automática (según el diagrama)", "Automatic (from the diagram)"), "vertical": ("Vertical", "Portrait"),
        "horizontal": ("Horizontal", "Landscape")})
    ajustar: bool = opt(True, "Ajustar el diagrama a la página", "Fit the diagram to the page")


class DrawioPngOptions(BaseModel):
    """drawio-a-png (D-227): escala [2×] y fondo transparente [no]."""

    escala: Literal[1, 2, 3] = opt(2, "Escala", "Scale", labels={1: ("1× (tamaño real)", "1× (actual size)"), 2: ("2× (nítido)", "2× (sharp)"),
                                                                 3: ("3× (para imprimir)", "3× (for print)")})
    transparente: bool = opt(False, "Fondo transparente", "Transparent background")


SPECS: list[ToolSpec] = [
    # A.2 (F4-E3, D-208): genera facturas, así que va detrás de INVOICING_ES_ENABLED y apagada por defecto (7.23). La
    # extracción con IA es una petición con consentimiento (6.6); la categoría invoice puede usar IA, la sign no.
    ToolSpec(
        slug_es="pdf-a-factura-electronica", slug_en="pdf-to-e-invoice", name_es="PDF a factura electrónica",
        name_en="PDF to e-invoice", category="invoice", where="server", inputs=("pdf",), outputs=("json", "pdf", "xml"),
        # Clase «ai» como el resto de herramientas con IA (la web y las cuotas lo leen); la tarea cuenta como ligera y las
        # peticiones de IA van aparte, como en imagen-a-excel (D-161).
        options=PdfAFacturaOptions, worker_group="utils", queue_kind="light", cost_class="ai", cost=lambda o: "light",
        impl="tools.utils.facturas.desde_pdf:run", launch=True, phase="F4", time_limit=1800, max_files=1, default_enabled=False,
        ai=AiSpec(estimate=lambda o: 1, json=True, min_context=8000, min_output=1500, option="ia"),
        summary_es="Convierte una factura en PDF en Factur-X: lee sus datos, te deja revisarlos y genera el PDF/A-3 con el XML.",
        summary_en="Turn a PDF invoice into Factur-X: read its data, let you check it and generate the PDF/A-3 with the XML.",
        related=("crear-factura-electronica", "validar-factura-electronica"),
    ),
    # A.2 (F4-E2, D-205): genera facturas, así que va detrás de INVOICING_ES_ENABLED y apagada por defecto (7.23). Sin
    # archivos: el XML sale del formulario y se valida con el mismo motor que validar-factura-electronica.
    ToolSpec(
        slug_es="crear-factura-electronica", slug_en="create-e-invoice", name_es="Crear factura electrónica",
        name_en="Create e-invoice", category="invoice", where="server", inputs=(), outputs=("pdf", "xml"),
        options=CrearFacturaElectronicaOptions, worker_group="utils", queue_kind="light", cost_class="light",
        impl="tools.utils.facturas.crear:run", launch=True, phase="F4", time_limit=900, default_enabled=False,
        summary_es="Crea facturas Factur-X, XRechnung, Peppol, UBL y Facturae desde un formulario y las valida antes de entregarlas.",
        summary_en="Create Factur-X, XRechnung, Peppol, UBL and Facturae invoices from a form and validate them before delivery.",
        related=("crear-factura", "validar-factura-electronica"),
    ),
    # 7.23 (F4-D): no genera facturas, así que no va detrás de INVOICING_ES_ENABLED. Sin opciones en A.2.
    ToolSpec(
        slug_es="validar-factura-electronica", slug_en="validate-e-invoice", name_es="Validar factura electrónica",
        name_en="Validate e-invoice", category="invoice", where="server", inputs=("xml", "pdf", "zip"),
        outputs=("html", "csv", "zip"), worker_group="utils", queue_kind="light", cost_class="light",
        impl="tools.utils.facturas.validar:run", launch=True, phase="F4", time_limit=900,
        summary_es="Comprueba facturas UBL, CII, Factur-X, XRechnung, Peppol y Facturae con las reglas oficiales y explica cada fallo.",
        summary_en="Check UBL, CII, Factur-X, XRechnung, Peppol and Facturae invoices against the official rules and explain each failure.",
        related=("factura-electronica-a-pdf", "validar-pdfa"),
    ),
    a_pdf("factura-electronica-a-pdf", "e-invoice-to-pdf", "Factura electrónica a PDF", "E-invoice to PDF",
          "Convierte facturas UBL, CII y Facturae en un PDF legible, con el XML original incrustado en PDF/A-3.",
          "Turn UBL, CII and Facturae invoices into a readable PDF, with the original XML embedded in PDF/A-3.",
          ("validar-factura-electronica", "facturae-a-pdf")),
    a_pdf("facturae-a-pdf", "facturae-to-pdf", "Facturae a PDF", "Facturae to PDF",
          "Convierte facturas Facturae 3.2.x en un PDF legible, con el XML original incrustado en PDF/A-3.",
          "Turn Facturae 3.2.x invoices into a readable PDF, with the original XML embedded in PDF/A-3.",
          ("factura-electronica-a-pdf", "validar-factura-electronica")),
    a_pdf("ubl-a-pdf", "ubl-to-pdf", "UBL a PDF", "UBL to PDF",
          "Convierte facturas UBL 2.1 (también Peppol y XRechnung) en un PDF legible, con el XML incrustado en PDF/A-3.",
          "Turn UBL 2.1 invoices (also Peppol and XRechnung) into a readable PDF, with the XML embedded in PDF/A-3.",
          ("factura-electronica-a-pdf", "validar-factura-electronica")),
    a_pdf("cii-a-pdf", "cii-to-pdf", "CII a PDF", "CII to PDF",
          "Convierte facturas CII de UN/CEFACT (también XRechnung CII) en un PDF legible, con el XML incrustado en PDF/A-3.",
          "Turn UN/CEFACT CII invoices (also XRechnung CII) into a readable PDF, with the XML embedded in PDF/A-3.",
          ("factura-electronica-a-pdf", "validar-factura-electronica")),
    documento("docx-a-odt", "docx-to-odt", "DOCX a ODT", "DOCX to ODT", ("docx",), ("odt",),
              "Convierte documentos de Word (.docx) en ODT de LibreOffice conservando títulos, listas, tablas e imágenes.",
              "Turn Word documents (.docx) into LibreOffice ODT, keeping headings, lists, tables and images.",
              ("odt-a-docx", "word-a-pdf")),
    documento("odt-a-docx", "odt-to-docx", "ODT a DOCX", "ODT to DOCX", ("odt",), ("docx",),
              "Convierte documentos ODT de LibreOffice en Word (.docx) conservando títulos, listas, tablas e imágenes.",
              "Turn LibreOffice ODT documents into Word (.docx), keeping headings, lists, tables and images.",
              ("docx-a-odt", "odt-a-pdf")),
    documento("docx-a-markdown", "docx-to-markdown", "DOCX a Markdown", "DOCX to Markdown", ("docx",), ("md",),
              "Convierte documentos de Word en Markdown limpio (GitHub, CommonMark o pandoc), con sus imágenes en una carpeta.",
              "Turn Word documents into clean Markdown (GitHub, CommonMark or pandoc), with their images in a folder.",
              ("markdown-a-docx", "docx-a-html"), DocxMarkdownOptions),
    documento("markdown-a-docx", "markdown-to-docx", "Markdown a DOCX", "Markdown to DOCX", ("md", "zip"), ("docx",),
              "Convierte archivos Markdown en documentos de Word con títulos, tablas, código, fórmulas e imágenes del ZIP.",
              "Turn Markdown files into Word documents with headings, tables, code, formulas and images from the ZIP.",
              ("docx-a-markdown", "markdown-a-pdf"), MarkdownDocxOptions),
    documento("docx-a-html", "docx-to-html", "DOCX a HTML", "DOCX to HTML", ("docx",), ("html",),
              "Convierte documentos de Word en una página HTML de un solo archivo, con las imágenes y las fórmulas dentro.",
              "Turn Word documents into a single-file HTML page, with the images and formulas inside.",
              ("html-a-docx", "docx-a-markdown"), IndiceOptions),
    documento("html-a-docx", "html-to-docx", "HTML a DOCX", "HTML to DOCX", ("html", "zip"), ("docx",),
              "Convierte páginas HTML en documentos de Word editables, con las imágenes que subas en el mismo ZIP.",
              "Turn HTML pages into editable Word documents, with the images you upload in the same ZIP.",
              ("docx-a-html", "html-a-pdf"), IndiceOptions),
    datos("xlsx-a-csv", "xlsx-to-csv", "Excel a CSV", "Excel to CSV", ("xlsx",), ("csv",),
          "Exporta hojas de Excel a CSV con el separador, el decimal y la codificación que necesites, con los valores calculados.",
          "Export Excel sheets to CSV with the separator, decimal mark and encoding you need, using the calculated values.",
          ("csv-a-xlsx", "excel-a-json"), XlsxCsvOptions, category="office"),
    datos("csv-a-xlsx", "csv-to-xlsx", "CSV a Excel", "CSV to Excel", ("csv", "txt"), ("xlsx",),
          "Convierte CSV en hojas de Excel con números y fechas de verdad, encabezado con filtros y la codificación detectada.",
          "Turn CSV files into Excel sheets with real numbers and dates, a filtered header and the encoding detected.",
          ("xlsx-a-csv", "arreglar-codificacion-csv"), CsvXlsxOptions, category="office"),
    datos("ods-a-xlsx", "ods-to-xlsx", "ODS a Excel", "ODS to Excel", ("ods",), ("xlsx",),
          "Convierte hojas de cálculo ODS de LibreOffice en Excel (.xlsx) con sus hojas, fórmulas y formatos.",
          "Turn LibreOffice ODS spreadsheets into Excel (.xlsx) with their sheets, formulas and formatting.",
          ("xlsx-a-ods", "xlsx-a-csv"), category="office", group="office", impl="tools.office.hojas:run"),
    datos("xlsx-a-ods", "xlsx-to-ods", "Excel a ODS", "Excel to ODS", ("xlsx", "xls"), ("ods",),
          "Convierte libros de Excel (.xlsx y .xls) en hojas de cálculo ODS de LibreOffice con sus fórmulas y formatos.",
          "Turn Excel workbooks (.xlsx and .xls) into LibreOffice ODS spreadsheets with their formulas and formatting.",
          ("ods-a-xlsx", "excel-a-pdf"), category="office", group="office", impl="tools.office.hojas:run"),
    datos("excel-a-json", "excel-to-json", "Excel a JSON", "Excel to JSON", ("xlsx",), ("json",),
          "Convierte hojas de Excel en JSON: una lista de objetos con la primera fila como claves, o de filas, con sus tipos.",
          "Turn Excel sheets into JSON: a list of objects keyed by the first row, or of rows, keeping their types.",
          ("csv-a-json", "xlsx-a-csv"), ExcelJsonOptions),
    datos("arreglar-codificacion-csv", "fix-csv-encoding", "Arreglar codificación de CSV", "Fix CSV encoding", ("csv", "txt"),
          ("csv",), "Recupera las tildes y las eñes de un CSV: lo pasa de Windows-1252 y otras codificaciones a UTF-8 y corrige el «Ã±».",
          "Recover the accents in a CSV: convert it from Windows-1252 and other encodings to UTF-8 and fix mojibake like “Ã±”.",
          ("csv-a-xlsx", "xlsx-a-csv"), CodificacionCsvOptions),
    datos("csv-a-json", "csv-to-json", "CSV a JSON", "CSV to JSON", ("csv", "txt"), ("json",),
          "Convierte CSV en JSON, como lista de objetos o de filas, con números y valores vacíos de verdad.",
          "Turn CSV into JSON, as a list of objects or of rows, with real numbers and empty values.",
          ("json-a-csv", "excel-a-json"), CsvJsonOptions),
    datos("json-a-csv", "json-to-csv", "JSON a CSV", "JSON to CSV", ("json",), ("csv",),
          "Convierte JSON (también JSON Lines) en CSV: aplana los objetos anidados en columnas y une las claves de todos.",
          "Turn JSON (JSON Lines too) into CSV: flatten nested objects into columns and merge every object's keys.",
          ("csv-a-json", "json-a-xml"), JsonCsvOptions),
    datos("json-a-xml", "json-to-xml", "JSON a XML", "JSON to XML", ("json",), ("xml",),
          "Convierte JSON en XML bien formado, con nombres de elemento válidos y el elemento raíz que elijas.",
          "Turn JSON into well-formed XML, with valid element names and the root element you choose.",
          ("xml-a-json", "json-a-yaml"), JsonXmlOptions),
    datos("xml-a-json", "xml-to-json", "XML a JSON", "XML to JSON", ("xml",), ("json",),
          "Convierte XML en JSON con atributos, texto y elementos repetidos como listas, sin cargar entidades externas.",
          "Turn XML into JSON with attributes, text and repeated elements as lists, without loading external entities.",
          ("json-a-xml", "json-a-yaml"), XmlJsonOptions),
    datos("yaml-a-json", "yaml-to-json", "YAML a JSON", "YAML to JSON", ("yaml",), ("json",),
          "Convierte YAML en JSON, también con varios documentos, sin ejecutar etiquetas ni expandir alias sin límite.",
          "Turn YAML into JSON, multiple documents too, without running tags or expanding aliases without limit.",
          ("json-a-yaml", "xml-a-json")),
    datos("json-a-yaml", "json-to-yaml", "JSON a YAML", "JSON to YAML", ("json",), ("yaml",),
          "Convierte JSON en YAML legible, con las claves en su orden y los acentos sin escapar.",
          "Turn JSON into readable YAML, with keys in their order and accented letters unescaped.",
          ("yaml-a-json", "json-a-xml")),
    # 7.13 (F6-F, D-215): fuentes con fontTools y brotli. El Anexo A no fija opciones.
    datos("ttf-a-woff2", "ttf-to-woff2", "TTF a WOFF2", "TTF to WOFF2", ("ttf",), ("woff2",),
          "Comprime fuentes TrueType en WOFF2 para la web: el mismo diseño en un archivo hasta un 70 % más pequeño.",
          "Compress TrueType fonts into WOFF2 for the web: the same design in a file up to 70% smaller.",
          ("otf-a-woff2", "woff2-a-ttf"), impl="tools.utils.fuentes:run"),
    datos("otf-a-woff2", "otf-to-woff2", "OTF a WOFF2", "OTF to WOFF2", ("otf",), ("woff2",),
          "Comprime fuentes OpenType en WOFF2 para usarlas en una web con @font-face, sin tocar sus contornos.",
          "Compress OpenType fonts into WOFF2 to use them on a website with @font-face, without touching their outlines.",
          ("ttf-a-woff2", "otf-a-ttf"), impl="tools.utils.fuentes:run"),
    datos("woff2-a-ttf", "woff2-to-ttf", "WOFF2 a TTF", "WOFF2 to TTF", ("woff2",), ("ttf",),
          "Convierte fuentes web WOFF2 en TTF que se pueden instalar en Windows, macOS y Linux o usar en programas de diseño.",
          "Turn WOFF2 web fonts into TTF you can install on Windows, macOS and Linux or use in design programs.",
          ("woff-a-ttf", "ttf-a-woff2"), impl="tools.utils.fuentes:run"),
    datos("woff-a-ttf", "woff-to-ttf", "WOFF a TTF", "WOFF to TTF", ("woff",), ("ttf",),
          "Convierte fuentes web WOFF en TTF instalables, también las que llevan contornos CFF.",
          "Turn WOFF web fonts into installable TTF files, including those with CFF outlines.",
          ("woff2-a-ttf", "ttf-a-woff2"), impl="tools.utils.fuentes:run"),
    datos("ttf-a-otf", "ttf-to-otf", "TTF a OTF", "TTF to OTF", ("ttf",), ("otf",),
          "Convierte fuentes TrueType en OpenType con contornos CFF, pasando las curvas a cúbicas sin perder precisión.",
          "Turn TrueType fonts into OpenType with CFF outlines, converting the curves to cubic ones without losing precision.",
          ("otf-a-ttf", "ttf-a-woff2"), impl="tools.utils.fuentes:run"),
    datos("otf-a-ttf", "otf-to-ttf", "OTF a TTF", "OTF to TTF", ("otf",), ("ttf",),
          "Convierte fuentes OpenType CFF en TrueType para programas y dispositivos que solo admiten TTF.",
          "Turn OpenType CFF fonts into TrueType for programs and devices that only accept TTF.",
          ("ttf-a-otf", "otf-a-woff2"), impl="tools.utils.fuentes:run"),
    # 7.13 (F6-E, D-217): libarchive en workerutils, nunca unrar ni p7zip (11).
    datos("rar-a-zip", "rar-to-zip", "RAR a ZIP", "RAR to ZIP", ("rar",), (),
          "Convierte archivos RAR (también RAR 5) en ZIP, que se abre en cualquier sistema sin instalar nada.",
          "Turn RAR archives (RAR 5 too) into ZIP, which opens on any system without installing anything.",
          ("7z-a-zip", "extraer-archivo-online"), impl="tools.utils.comprimidos:run"),
    datos("7z-a-zip", "7z-to-zip", "7Z a ZIP", "7Z to ZIP", ("7z",), (),
          "Convierte archivos 7z en ZIP con las mismas carpetas y archivos, listo para abrir en Windows, macOS o el móvil.",
          "Turn 7z archives into ZIP with the same folders and files, ready to open on Windows, macOS or a phone.",
          ("rar-a-zip", "tar-a-zip"), impl="tools.utils.comprimidos:run"),
    datos("tar-a-zip", "tar-to-zip", "TAR a ZIP", "TAR to ZIP", ("tar", "gz", "bz2", "xz"), (),
          "Convierte archivos tar, tar.gz, tgz, tar.bz2 y tar.xz en ZIP, conservando las carpetas y las fechas.",
          "Turn tar, tar.gz, tgz, tar.bz2 and tar.xz archives into ZIP, keeping folders and dates.",
          ("7z-a-zip", "extraer-archivo-online"), impl="tools.utils.comprimidos:run"),
    ToolSpec(slug_es="extraer-archivo-online", slug_en="extract-archive-online", name_es="Extraer archivo online",
             name_en="Extract archive online", category="data", where="server", inputs=("zip", "rar", "7z", "tar", "gz", "bz2", "xz"),
             outputs=("zip",), options=ContrasenaArchivoOptions, secret_fields=("contrasena",), worker_group="utils",
             queue_kind="light", cost_class="light", impl="tools.utils.comprimidos:run", launch=True, phase="F6",
             time_limit=600, max_files=1,
             summary_es="Abre archivos ZIP, RAR, 7z y tar sin instalar nada y descarga los archivos que contienen, uno a uno o todos.",
             summary_en="Open ZIP, RAR, 7z and tar archives without installing anything and download the files inside, one by one or all.",
             related=("rar-a-zip", "7z-a-zip")),
    datos("srt-a-vtt", "srt-to-vtt", "SRT a VTT", "SRT to VTT", ("srt",), ("vtt",),
          "Convierte subtítulos SRT en WebVTT para los vídeos de una web (<track>), con los tiempos y las cursivas.",
          "Turn SRT subtitles into WebVTT for videos on a website (<track>), keeping timings and italics.",
          ("vtt-a-srt", "traducir-subtitulos"), SubtitulosOptions, category="video", impl="tools.utils.subtitulos:run"),
    datos("vtt-a-srt", "vtt-to-srt", "VTT a SRT", "VTT to SRT", ("vtt",), ("srt",),
          "Convierte subtítulos WebVTT en SRT, el formato que leen VLC, los televisores y los editores de vídeo.",
          "Turn WebVTT subtitles into SRT, the format VLC, TVs and video editors read.",
          ("srt-a-vtt", "ass-a-srt"), SubtitulosOptions, category="video", impl="tools.utils.subtitulos:run"),
    datos("ass-a-srt", "ass-to-srt", "ASS a SRT", "ASS to SRT", ("ass",), ("srt",),
          "Convierte subtítulos ASS y SSA (Aegisub, anime) en SRT, ordenados por tiempo y con negrita y cursiva.",
          "Turn ASS and SSA subtitles (Aegisub, anime) into SRT, sorted by time and with bold and italics.",
          ("vtt-a-srt", "srt-a-vtt"), SubtitulosOptions, category="video", impl="tools.utils.subtitulos:run"),
    # 7.13 (F6-G, D-219): sacan el documento de la firma sin comprobarla (eso es verificar-firma, en `sign.verify`).
    datos("csig-a-pdf", "csig-to-pdf", "CSIG a PDF", "CSIG to PDF", ("csig", "p7m", "p7s"), ("pdf",),
          "Saca el PDF original de una firma .csig de AutoFirma o Cl@ve, idéntico al que se firmó, para abrirlo e imprimirlo.",
          "Get the original PDF out of an AutoFirma or Cl@ve .csig signature, identical to the one that was signed.",
          ("verificar-firma", "p7m-a-pdf"), category="sign", impl="tools.utils.firmados:run"),
    datos("p7m-a-pdf", "p7m-to-pdf", "P7M a PDF", "P7M to PDF", ("p7m", "p7s", "csig"), ("pdf",),
          "Abre archivos .p7m firmados (notificaciones, facturas, escrituras) y descarga el documento original que contienen.",
          "Open signed .p7m files (notifications, invoices, deeds) and download the original document inside.",
          ("verificar-firma", "csig-a-pdf"), category="sign", impl="tools.utils.firmados:run"),
    datos("xsig-a-pdf", "xsig-to-pdf", "XSIG a PDF", "XSIG to PDF", ("xsig", "xml"), ("pdf",),
          "Saca el documento original de una firma XAdES .xsig de AutoFirma, o el XML sin su firma si iba dentro.",
          "Get the original document out of an AutoFirma XAdES .xsig signature, or the XML without its signature if it was inside.",
          ("verificar-firma", "csig-a-pdf"), category="sign", impl="tools.utils.firmados:run"),
    # 7.13 (F6-H1, D-220): modelo propio, gpxpy para GPX y la GDAL de pyogrio en un proceso aparte para Shapefile (nunca GDAL en el proceso; D-267).
    datos("gpx-a-kml", "gpx-to-kml", "GPX a KML", "GPX to KML", ("gpx",), ("kml",),
          "Convierte rutas y puntos GPX de tu GPS, Strava o Wikiloc en KML para Google Earth y Google My Maps, con sus horas.",
          "Turn GPX routes and waypoints from your GPS, Strava or Wikiloc into KML for Google Earth and My Maps, with their times.",
          ("kml-a-gpx", "gpx-a-geojson"), impl="tools.utils.geo:run", time_limit=1800),
    datos("kml-a-gpx", "kml-to-gpx", "KML a GPX", "KML to GPX", ("kml",), ("gpx",),
          "Convierte rutas y lugares KML de Google Earth o My Maps en GPX para tu GPS, reloj o aplicación de rutas.",
          "Turn KML routes and places from Google Earth or My Maps into GPX for your GPS, watch or route app.",
          ("gpx-a-kml", "kmz-a-gpx"), impl="tools.utils.geo:run", time_limit=1800),
    datos("kmz-a-gpx", "kmz-to-gpx", "KMZ a GPX", "KMZ to GPX", ("kmz",), ("gpx",),
          "Convierte archivos KMZ de Google Earth en GPX con sus rutas, pistas y puntos, listo para el GPS.",
          "Turn Google Earth KMZ files into GPX with their routes, tracks and points, ready for the GPS.",
          ("kml-a-gpx", "gpx-a-kml"), impl="tools.utils.geo:run", time_limit=1800),
    datos("gpx-a-geojson", "gpx-to-geojson", "GPX a GeoJSON", "GPX to GeoJSON", ("gpx",), ("geojson",),
          "Convierte GPX en GeoJSON para mapas web (Leaflet, Mapbox, QGIS), con altura y hora de cada punto.",
          "Turn GPX into GeoJSON for web maps (Leaflet, Mapbox, QGIS), with the elevation and time of each point.",
          ("geojson-a-kml", "gpx-a-kml"), impl="tools.utils.geo:run", time_limit=1800),
    datos("geojson-a-kml", "geojson-to-kml", "GeoJSON a KML", "GeoJSON to KML", ("geojson", "json"), ("kml",),
          "Convierte GeoJSON en KML para Google Earth, con puntos, líneas, polígonos y sus atributos.",
          "Turn GeoJSON into KML for Google Earth, with points, lines, polygons and their attributes.",
          ("gpx-a-geojson", "shp-a-kml"), impl="tools.utils.geo:run", time_limit=1800),
    datos("shp-a-geojson", "shp-to-geojson", "Shapefile a GeoJSON", "Shapefile to GeoJSON", ("zip",), ("geojson",),
          "Convierte capas Shapefile (en un ZIP con .shp, .shx, .dbf y .prj) en GeoJSON en WGS84, con todos sus atributos.",
          "Turn Shapefile layers (in a ZIP with .shp, .shx, .dbf and .prj) into WGS84 GeoJSON, with all their attributes.",
          ("shp-a-kml", "geojson-a-kml"), impl="tools.utils.geo:run", time_limit=1800),
    datos("shp-a-kml", "shp-to-kml", "Shapefile a KML", "Shapefile to KML", ("zip",), ("kml",),
          "Convierte capas Shapefile en KML para verlas en Google Earth, reproyectadas a WGS84 desde su .prj.",
          "Turn Shapefile layers into KML to view them in Google Earth, reprojected to WGS84 from their .prj.",
          ("shp-a-geojson", "geojson-a-kml"), impl="tools.utils.geo:run", time_limit=1800),
    datos("csv-a-kml", "csv-to-kml", "CSV a KML", "CSV to KML", ("csv", "txt"), ("kml",),
          "Convierte una lista de lugares en CSV, con columnas de latitud y longitud, en puntos KML para Google Earth y My Maps.",
          "Turn a CSV list of places, with latitude and longitude columns, into KML points for Google Earth and My Maps.",
          ("geojson-a-kml", "kml-a-gpx"), CsvKmlOptions, impl="tools.utils.geo:run", time_limit=1800),
    # 7.13 (F6-H2, D-223): TCX propio con defusedxml y FIT con fitparse (MIT). El Anexo A no fija opciones.
    datos("tcx-a-gpx", "tcx-to-gpx", "TCX a GPX", "TCX to GPX", ("tcx",), ("gpx",),
          "Convierte actividades TCX de Garmin en GPX con su recorrido, altura, hora, pulso y cadencia, para Strava o tu GPS.",
          "Turn Garmin TCX activities into GPX with their route, elevation, time, heart rate and cadence, for Strava or your GPS.",
          ("fit-a-gpx", "gpx-a-kml"), impl="tools.utils.deportes:run"),
    datos("fit-a-gpx", "fit-to-gpx", "FIT a GPX", "FIT to GPX", ("fit",), ("gpx",),
          "Convierte actividades FIT de Garmin, Wahoo, Coros o Suunto en GPX con el recorrido, el pulso, la cadencia y la potencia.",
          "Turn FIT activities from Garmin, Wahoo, Coros or Suunto into GPX with the route, heart rate, cadence and power.",
          ("fit-a-csv", "tcx-a-gpx"), impl="tools.utils.deportes:run"),
    datos("fit-a-csv", "fit-to-csv", "FIT a CSV", "FIT to CSV", ("fit",), ("csv",),
          "Exporta todos los registros de una actividad FIT a CSV: hora, posición, altura, velocidad, pulso, cadencia y potencia.",
          "Export every record of a FIT activity to CSV: time, position, elevation, speed, heart rate, cadence and power.",
          ("fit-a-gpx", "csv-a-xlsx"), impl="tools.utils.deportes:run"),
    # 7.13 (F6-I, D-224): vobject e icalendar; categoría data con «vcf» o «ics» en el nombre: nunca IA (6.6 y 16.3).
    datos("vcf-a-csv", "vcf-to-csv", "VCF a CSV", "VCF to CSV", ("vcf",), ("csv",),
          "Convierte contactos vCard (.vcf) del móvil, iCloud o Google en CSV con las columnas de Google Contacts u Outlook.",
          "Turn vCard contacts (.vcf) from your phone, iCloud or Google into CSV with Google Contacts or Outlook columns.",
          ("csv-a-vcf", "vcf-a-excel"), VcfOptions, impl="tools.utils.agenda:run"),
    datos("csv-a-vcf", "csv-to-vcf", "CSV a VCF", "CSV to VCF", ("csv", "txt"), ("vcf",),
          "Convierte una lista de contactos en CSV (de Google, Outlook o tu hoja) en vCard para importarla en el móvil o en iCloud.",
          "Turn a CSV contact list (from Google, Outlook or your own sheet) into vCard to import it into your phone or iCloud.",
          ("vcf-a-csv", "vcf-a-excel"), impl="tools.utils.agenda:run"),
    datos("vcf-a-excel", "vcf-to-excel", "VCF a Excel", "VCF to Excel", ("vcf",), ("xlsx",),
          "Convierte contactos vCard en una hoja de Excel con nombre, correos, teléfonos, direcciones y empresa de cada uno.",
          "Turn vCard contacts into an Excel sheet with each contact's name, emails, phones, addresses and company.",
          ("vcf-a-csv", "csv-a-vcf"), VcfOptions, impl="tools.utils.agenda:run"),
    datos("ics-a-csv", "ics-to-csv", "ICS a CSV", "ICS to CSV", ("ics",), ("csv",),
          "Convierte un calendario ICS de Google, Outlook o Apple en CSV: un evento por fila con fechas, horas, lugar y descripción.",
          "Turn an ICS calendar from Google, Outlook or Apple into CSV: one event per row with dates, times, place and description.",
          ("csv-a-ics", "ics-a-excel"), IcsOptions, impl="tools.utils.agenda:run"),
    datos("csv-a-ics", "csv-to-ics", "CSV a ICS", "CSV to ICS", ("csv", "txt"), ("ics",),
          "Convierte una lista de eventos en CSV en un calendario ICS para importarlo en Google Calendar, Outlook o el iPhone.",
          "Turn a CSV list of events into an ICS calendar to import into Google Calendar, Outlook or the iPhone.",
          ("ics-a-csv", "ics-a-excel"), CsvIcsOptions, impl="tools.utils.agenda:run"),
    datos("ics-a-excel", "ics-to-excel", "ICS a Excel", "ICS to Excel", ("ics",), ("xlsx",),
          "Convierte un calendario ICS en una hoja de Excel con todos sus eventos, para revisarlos, filtrarlos o imprimirlos.",
          "Turn an ICS calendar into an Excel sheet with all its events, to review, filter or print them.",
          ("ics-a-csv", "csv-a-ics"), IcsOptions, impl="tools.utils.agenda:run"),
    # 7.13 (F6-K, D-227): Tectonic con Landlock y --only-cached; draw.io con su visor en el Chromium de Gotenberg.
    datos("latex-a-pdf", "latex-to-pdf", "LaTeX a PDF", "LaTeX to PDF", ("tex", "zip"), ("pdf",),
          "Compila documentos LaTeX (.tex o un ZIP con imágenes y bibliografía) en PDF con XeTeX, sin instalar nada.",
          "Compile LaTeX documents (.tex or a ZIP with images and bibliography) into PDF with XeTeX, without installing anything.",
          ("markdown-a-pdf", "word-a-pdf"), category="office", impl="tools.utils.latex:run", time_limit=900),
    datos("drawio-a-pdf", "drawio-to-pdf", "draw.io a PDF", "draw.io to PDF", ("drawio",), ("pdf",),
          "Convierte diagramas de draw.io (diagrams.net) en PDF vectorial, una página por pestaña del diagrama.",
          "Turn draw.io (diagrams.net) diagrams into vector PDF, one page per diagram tab.",
          ("drawio-a-png", "svg-a-pdf"), DrawioPdfOptions, category="office", group="office", impl="tools.office.drawio:run"),
    datos("drawio-a-png", "drawio-to-png", "draw.io a PNG", "draw.io to PNG", ("drawio",), ("png",),
          "Convierte diagramas de draw.io en imágenes PNG nítidas, con fondo blanco o transparente.",
          "Turn draw.io diagrams into sharp PNG images, with a white or transparent background.",
          ("drawio-a-pdf", "png-a-svg"), DrawioPngOptions, category="office", group="office", impl="tools.office.drawio:run"),
]
