"""compartir-pdf (7.7, F4-C1, D-200): el PDF se comprueba (que se abre y cabe en el plan) y queda como resultado del
trabajo; el enlace con caducidad lo crea después la página con `POST /v1/shares` (la API: los workers no pueden tocar la
tabla `shares`)."""
from __future__ import annotations

import shutil

from tools.base import ToolContext
from tools.pdf.common import open_pdf


def precheck(settings, plan, owner_type: str, options: dict, paths, locale: str = "es") -> None:
    from core.errors import AppError, ErrorCode

    if owner_type == "anon":
        raise AppError(ErrorCode.UNAUTHORIZED, status=401, detail="share_account")


def run(ctx: ToolContext) -> list[dict]:
    outputs = []
    for inp in ctx.inputs:
        with open_pdf(inp.path, None, ctx.plan.pdf_pages):
            pass
        name = inp.name if inp.name.lower().endswith(".pdf") else f"{inp.name}.pdf"
        dst = ctx.output(name)
        shutil.copyfile(inp.path, dst)
        outputs.append({"path": str(dst), "name": name, "note": None})
    return outputs
