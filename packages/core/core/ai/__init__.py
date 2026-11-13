"""IA con modelos gratuitos de OpenRouter (sección 6): presupuesto, descubrimiento, proveedor y caché.

La API solo reserva y consulta (no sale a internet); las peticiones las hace `workerai`, el único con la clave.
"""
from __future__ import annotations

# Versión del texto del aviso de 6.6. La web muestra el mismo texto (messages: ai.consent) con esta versión; si el texto
# cambia, cambia la versión y se vuelve a pedir el consentimiento.
CONSENT_VERSION = "2026-11-05"

# 6.6: nunca se envía a OpenRouter contenido de firma, verificación de firmas, contactos, calendario, correo o
# certificados. Además de la categoría `sign`, se bloquean por nombre (las de F4 y F6 llegarán con estos nombres).
EXCLUDED_CATEGORIES = frozenset({"sign"})
EXCLUDED_WORDS = ("firma", "firmar", "certificado", "contacto", "vcf", "calendario", "ics", "eml", "msg", "correo", "pst", "mbox")


def is_excluded(slug: str, category: str) -> bool:
    if category in EXCLUDED_CATEGORIES:
        return True
    parts = slug.replace("_", "-").split("-")
    return any(word in parts for word in EXCLUDED_WORDS)
