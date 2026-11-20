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
    # F4-Z (D-210): la firma dibujada, escrita o subida dentro de la apariencia del sello visible (A.6: «visible, con imagen»).
    imagen: str = opt("", "Imagen de la firma en el sello (PNG en base64)", "Signature image in the seal (base64 PNG)",
                      max_length=560_000, advanced=True, show_if={"visible": (True,)})
    motivo: str = opt("", "Motivo", "Reason", max_length=200)
    lugar: str = opt("", "Lugar", "Location", max_length=120)
    sello_tiempo: bool = opt(True, "Sello de tiempo", "Time stamp")
    nivel: Literal[tuple(LEVELS)] = opt("B-T", "Nivel PAdES", "PAdES level", labels=LEVELS, show_if={"sello_tiempo": (True,)})
    certificacion: Literal[tuple(CERTIFICATION)] = opt("no", "Certificación (DocMDP)", "Certification (DocMDP)",
                                                       labels=CERTIFICATION, advanced=True)


class Firmante(BaseModel):
    """Un firmante de solicitar-firmas: en `preparar`, su campo (vacío: uno nuevo en la página de firmas); en `final`,
    también su correo y cuándo firmó, para el certificado de auditoría."""

    nombre: str = opt("", "Nombre", "Name", min_length=1, max_length=120)
    campo: str = opt("", "Campo de firma vacío del PDF (vacío: uno nuevo)", "Empty signature field of the PDF (empty: a new one)",
                     max_length=120, pattern=r"^[^.\x00-\x1f]*$")
    correo: str = opt("", "Correo", "Email", max_length=320)
    firmado: str = opt("", "Firmado", "Signed", max_length=40)


class Evento(BaseModel):
    evento: str = opt("", "Evento", "Event", max_length=40)
    actor: str = opt("", "Quién", "Who", max_length=320)
    fecha: str = opt("", "Fecha", "Date", max_length=40)
    ip: str = opt("", "IP (hash)", "IP (hash)", max_length=32)
    agente: str = opt("", "Navegador", "Browser", max_length=400)
    sha256: str = opt("", "SHA-256 del documento", "Document SHA-256", max_length=64)
    detalle: str = opt("", "Detalle", "Detail", max_length=500)


def _solicitar_route(options: dict) -> tuple[str, str]:
    """`preparar` añade campos en `workerpdf`; `firmante` y `final` sellan en `workersign`, el único con la clave."""
    return ("pdf", "pdf") if options.get("fase", "preparar") == "preparar" else ("sign", "sign")


class SolicitarOptions(BaseModel):
    """solicitar-firmas (7.7, F4-C2, D-202). La página solo crea la fase `preparar`; `firmante` y `final` los crea la API
    o beat para la solicitud (propietario «request»), nunca POST /v1/jobs."""

    fase: Literal["preparar", "firmante", "final"] = opt("preparar", "Fase", "Step", advanced=True, labels={
        "preparar": ("Preparar el documento", "Prepare the document"), "firmante": ("Firma de un firmante", "One signer's signature"),
        "final": ("Sello final y certificado", "Final seal and certificate")})
    firmantes: list[Firmante] = opt([], "Firmantes", "Signers", advanced=True, max_length=10)
    campo: str = opt("", "Campo del firmante", "Signer field", max_length=120, advanced=True, show_if={"fase": ("firmante",)})
    nombre: str = opt("", "Nombre del firmante", "Signer name", max_length=120, advanced=True, show_if={"fase": ("firmante",)})
    correo: str = opt("", "Correo verificado del firmante", "Signer's verified email", max_length=320, advanced=True,
                      show_if={"fase": ("firmante",)})
    documento: str = opt("", "Documento", "Document", max_length=200, advanced=True, show_if={"fase": ("final",)})
    solicitud: str = opt("", "Solicitud", "Request", max_length=40, advanced=True, show_if={"fase": ("final",)})
    propietario: str = opt("", "Quién la pidió", "Requested by", max_length=320, advanced=True, show_if={"fase": ("final",)})
    creada: str = opt("", "Creada", "Created", max_length=40, advanced=True, show_if={"fase": ("final",)})
    original_sha256: str = opt("", "SHA-256 del original", "Original SHA-256", max_length=64, advanced=True, show_if={"fase": ("final",)})
    eventos: list[Evento] = opt([], "Eventos", "Events", advanced=True, max_length=300, show_if={"fase": ("final",)})


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
    # 7.7 (F4-C2, D-202): flujo propio con pyHanko (nada de Documenso ni DocuSeal, AGPL). La página prepara el PDF con
    # sus campos (fase `preparar`, `workerpdf`) y crea la solicitud con POST /v1/signature-requests; cada firmante sella
    # su campo y, al final, el sello B-LT y el certificado de auditoría (fases `firmante` y `final`, `workersign`).
    ToolSpec(
        slug_es="solicitar-firmas", slug_en="request-signatures", name_es="Solicitar firmas", name_en="Request signatures",
        category="sign", where="server", inputs=("pdf",), outputs=("pdf",), options=SolicitarOptions, worker_group="pdf",
        cost_class="light", impl="tools.sign.solicitar:run", precheck="tools.sign.solicitar:precheck", launch=True,
        phase="F4", time_limit=600, max_files=1, route=_solicitar_route,
        summary_es="Pide a otras personas que firmen un PDF: invitación por correo, código de verificación, sello final y certificado de auditoría.",
        summary_en="Ask other people to sign a PDF: email invitation, verification code, final seal and audit certificate.",
        related=("firmar-pdf", "verificar-firmas-pdf"),
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
