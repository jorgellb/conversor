"""Grupo utils (F4 y F6): facturas electrónicas con KoSIT en modo servicio dentro de `workerutils` (5.4 y 7.23)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.options import opt
from core.registry import ToolSpec


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


class Linea(BaseModel):
    descripcion: str = opt("", "Descripción", "Description", max_length=1000)
    cantidad: float = opt(1, "Cantidad", "Quantity", gt=0, le=1e9)
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


SPECS: list[ToolSpec] = [
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
]
