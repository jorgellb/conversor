"""proteger-pdf (A.6): AES-256 (o AES-128) con permisos. La contraseña solo vive en memoria."""
from __future__ import annotations

import secrets
import string

import pikepdf

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.pdf.common import open_pdf, with_batch_zip

# Aviso del resultado en el idioma de la página (D-42, D-54 y D-151).
NOTES = {
    "es": {"owner_generated": "Sin contraseña de propietario: se ha generado una al azar que no se guarda en ningún sitio, "
                              "así que los permisos no se podrán cambiar después."},
    "en": {"owner_generated": "No owner password: a random one was generated and is not stored anywhere, "
                              "so the permissions cannot be changed later."},
}


def _random_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    user_pw = ctx.secrets.get("contrasena_apertura") or ""
    owner_pw = ctx.secrets.get("contrasena_propietario") or ""
    restricted = not all([o.permitir_modificar, o.permitir_comentar, o.permitir_imprimir, o.permitir_imprimir_alta,
                          o.permitir_ensamblar, o.permitir_formularios, o.permitir_copiar, o.permitir_copiar_accesibilidad])
    if not user_pw and not restricted:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "Pon una contraseña o restringe algún permiso")
    generated_note = None
    if not owner_pw:
        # Sin contraseña de propietario se genera una al azar que no se guarda en ningún sitio; si hay permisos
        # restringidos, el aviso del resultado lo explica.
        owner_pw = _random_password()
        if restricted:
            generated_note = NOTES.get(ctx.locale, NOTES["es"])["owner_generated"]
    allow = pikepdf.Permissions(
        accessibility=o.permitir_copiar_accesibilidad,
        extract=o.permitir_copiar,
        modify_annotation=o.permitir_comentar,
        modify_assembly=o.permitir_ensamblar,
        modify_form=o.permitir_formularios,
        modify_other=o.permitir_modificar,
        print_lowres=o.permitir_imprimir,
        print_highres=o.permitir_imprimir and o.permitir_imprimir_alta,
    )
    enc = pikepdf.Encryption(owner=owner_pw, user=user_pw, R=6 if o.cifrado == "aes256" else 4, allow=allow, aes=True)
    outputs = []
    for inp in ctx.inputs:
        name = derived_name(inp.name, "-protegido", "pdf")
        dst = ctx.output(name)
        with open_pdf(inp.path, None, ctx.plan.pdf_pages) as pdf:
            pdf.save(dst, encryption=enc)
        outputs.append({"path": str(dst), "name": name, "note": generated_note})
    return with_batch_zip(ctx, outputs, "protegidos.zip")
