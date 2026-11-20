"""Firma (F4, 7.23, A.6 y A.7): verificación con pyHanko en `sign.verify`, sin el token ni el PIN del sello."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.options import opt
from core.registry import NoOptions, ToolSpec


class VerificarOptions(BaseModel):
    """verificar-firmas-pdf (A.7): la revocación en línea solo a petición, por `egressweb`."""

    revocacion: bool = opt(False, "Comprobar la revocación en línea (OCSP y CRL)", "Check revocation online (OCSP and CRL)")


POSITIONS = {"abajo_derecha": ("Abajo a la derecha", "Bottom right"), "abajo_izquierda": ("Abajo a la izquierda", "Bottom left"),
             "arriba_derecha": ("Arriba a la derecha", "Top right"), "arriba_izquierda": ("Arriba a la izquierda", "Top left")}
LEVELS = {"B-T": ("PAdES B-T (con sello de tiempo)", "PAdES B-T (with time stamp)"),
          "B-LT": ("PAdES B-LT (y datos de validación a largo plazo)", "PAdES B-LT (and long-term validation data)"),
          "B-LTA": ("PAdES B-LTA (y sello de tiempo del documento)", "PAdES B-LTA (and document time stamp)")}
CERTIFICATION = {"no": ("No", "No"), "sin_cambios": ("Sin cambios", "No changes"),
                 "formularios": ("Permitir rellenar formularios", "Allow form filling"),
                 "formularios_anotaciones": ("Permitir formularios y comentarios", "Allow forms and comments")}


class FirmarOptions(BaseModel):
    """firmar-pdf, firma digital (A.6) con el sello de la plataforma; la firma en el navegador y el certificado propio
    llegan en F4-B (D-188)."""

    certificado: Literal["plataforma", "propio"] = opt("plataforma", "Certificado", "Certificate", labels={
        "plataforma": ("Sello de la plataforma", "Platform seal"),
        "propio": ("Certificado propio o de la empresa (.p12 o .pfx)", "Your own or company certificate (.p12 or .pfx)")})
    # Certificado propio (D-199): firma interrumpida en dos trabajos; la página rellena estos campos, no el usuario.
    fase: Literal["preparar", "completar"] = opt("preparar", "Fase de la firma con certificado propio", "Own-certificate signing step",
                                                 advanced=True, labels={"preparar": ("Preparar", "Prepare"), "completar": ("Completar", "Complete")},
                                                 show_if={"certificado": ("propio",)})
    cadena: str = opt("", "Cadena de certificados (PEM, sin la clave)", "Certificate chain (PEM, without the key)", max_length=40000,
                      advanced=True, show_if={"certificado": ("propio",)})
    estado: str = opt("", "Estado de la firma preparada", "Prepared signature state", max_length=40000, advanced=True,
                      show_if={"certificado": ("propio",)})
    firma: str = opt("", "Valor de la firma (base64)", "Signature value (base64)", max_length=4000, advanced=True,
                     show_if={"certificado": ("propio",)})
    visible: bool = opt(True, "Firma visible", "Visible signature")
    pagina: str = opt("ultima", "Página de la firma (última, primera o un número)", "Signature page (last, first or a number)",
                      max_length=10, show_if={"visible": (True,)})
    posicion: Literal[tuple(POSITIONS)] = opt("abajo_derecha", "Posición", "Position", labels=POSITIONS, show_if={"visible": (True,)})
    campo: str = opt("", "Campo de firma vacío del PDF (vacío: uno nuevo)", "Empty signature field of the PDF (empty: a new one)",
                     max_length=120, advanced=True)
    nombre: str = opt("", "Nombre que aparece", "Name shown", max_length=120)
    motivo: str = opt("", "Motivo", "Reason", max_length=200)
    lugar: str = opt("", "Lugar", "Location", max_length=120)
    sello_tiempo: bool = opt(True, "Sello de tiempo", "Time stamp")
    nivel: Literal[tuple(LEVELS)] = opt("B-T", "Nivel PAdES", "PAdES level", labels=LEVELS, show_if={"sello_tiempo": (True,)})
    certificacion: Literal[tuple(CERTIFICATION)] = opt("no", "Certificación (DocMDP)", "Certification (DocMDP)",
                                                       labels=CERTIFICATION, advanced=True)


SPECS: list[ToolSpec] = [
    # A.6 y 10 (F4-A2): el sello de la plataforma en `workersign`, el único con el token y el PIN; «Insertar firma» en el
    # navegador (F4-B2a, D-196) y el certificado propio con firma interrumpida en `sign.verify` (F4-B2b, D-199). El sello,
    # solo con cuenta (precheck).
    ToolSpec(
        slug_es="firmar-pdf", slug_en="sign-pdf", name_es="Firmar PDF", name_en="Sign PDF", category="sign",
        where="hybrid", inputs=("pdf",), outputs=("pdf", "zip"), options=FirmarOptions, worker_group="sign",
        cost_class="light", impl="tools.sign.firmar:run", precheck="tools.sign.firmar:precheck", launch=True,
        phase="F4", time_limit=600, max_files=10,
        summary_es="Firma un PDF a mano en el navegador o digitalmente (PAdES) con tu certificado o el sello de la plataforma.",
        summary_en="Sign a PDF by hand in your browser or digitally (PAdES) with your certificate or the platform seal.",
        related=("verificar-firmas-pdf", "proteger-pdf"),
    ),
    # 7.7 (F4-C1, D-200): el trabajo solo comprueba el PDF; el enlace con caducidad lo crea la página con POST /v1/shares.
    ToolSpec(
        slug_es="compartir-pdf", slug_en="share-pdf", name_es="Compartir PDF", name_en="Share PDF", category="sign",
        where="server", inputs=("pdf",), outputs=("pdf",), options=NoOptions, worker_group="pdf", cost_class="light",
        impl="tools.pdf.compartir:run", precheck="tools.pdf.compartir:precheck", launch=True, phase="F4", time_limit=300,
        max_files=1,
        summary_es="Comparte un PDF con un enlace privado que caduca cuando elijas y que puedes anular en cualquier momento.",
        summary_en="Share a PDF with a private link that expires when you choose and that you can revoke at any time.",
        related=("firmar-pdf", "proteger-pdf"),
    ),
    # 7.23: en `sign.verify`, un contenedor de la imagen worker-sign sin el volumen del token ni el PIN, para que un PDF
    # hostil no conviva con la clave del sello (D-185). Categoría `sign`: nunca crea cliente de IA (6.6).
    ToolSpec(
        slug_es="verificar-firmas-pdf", slug_en="verify-pdf-signatures", name_es="Verificar firmas de PDF",
        name_en="Verify PDF signatures", category="sign", where="server", inputs=("pdf",), outputs=("html", "zip"),
        options=VerificarOptions, worker_group="sign", queue_kind="verify", cost_class="light",
        impl="tools.sign.verificar:run", launch=True, phase="F4", time_limit=900,
        summary_es="Comprueba cada firma de un PDF: firmante, fecha, integridad, cambios posteriores, nivel y lista de confianza de la UE.",
        summary_en="Check every signature in a PDF: signer, date, integrity, later changes, level and the EU trusted list.",
        related=("firmar-pdf", "validar-pdfa"),
    ),
]
