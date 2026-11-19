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

SPECS: list[ToolSpec] = [
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
