"""desbloquear-pdf (A.6): quita cifrado y restricciones solo con la contraseña correcta; nunca fuerza."""
from __future__ import annotations

from tools.base import ToolContext, derived_name
from tools.pdf.common import open_pdf, with_batch_zip


def run(ctx: ToolContext) -> list[dict]:
    password = ctx.secrets.get("contrasena")
    outputs = []
    for inp in ctx.inputs:
        name = derived_name(inp.name, "-desbloqueado", "pdf")
        dst = ctx.output(name)
        with open_pdf(inp.path, password, ctx.plan.pdf_pages) as pdf:
            pdf.save(dst, encryption=False)
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "desbloqueados.zip")
