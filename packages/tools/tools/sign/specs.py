"""Firma (F4, 7.23, A.6 y A.7): verificación con pyHanko en `sign.verify`, sin el token ni el PIN del sello."""
from __future__ import annotations

from pydantic import BaseModel

from core.options import opt
from core.registry import ToolSpec


class VerificarOptions(BaseModel):
    """verificar-firmas-pdf (A.7): la revocación en línea solo a petición, por `egressweb`."""

    revocacion: bool = opt(False, "Comprobar la revocación en línea (OCSP y CRL)", "Check revocation online (OCSP and CRL)")


SPECS: list[ToolSpec] = [
    # 7.23: en `sign.verify`, un contenedor de la imagen worker-sign sin el volumen del token ni el PIN, para que un PDF
    # hostil no conviva con la clave del sello (D-185). Categoría `sign`: nunca crea cliente de IA (6.6).
    ToolSpec(
        slug_es="verificar-firmas-pdf", slug_en="verify-pdf-signatures", name_es="Verificar firmas de PDF",
        name_en="Verify PDF signatures", category="sign", where="server", inputs=("pdf",), outputs=("html", "zip"),
        options=VerificarOptions, worker_group="sign", queue_kind="verify", cost_class="light",
        impl="tools.sign.verificar:run", launch=True, phase="F4", time_limit=900,
        summary_es="Comprueba cada firma de un PDF: firmante, fecha, integridad, cambios posteriores, nivel y lista de confianza de la UE.",
        summary_en="Check every signature in a PDF: signer, date, integrity, later changes, level and the EU trusted list.",
        related=("validar-pdfa", "proteger-pdf"),
    ),
]
