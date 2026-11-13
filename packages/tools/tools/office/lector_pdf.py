"""lector-pdf (A.7): parte de servidor. Los PDF se abren en el navegador; el resto se convierte como en convertir-a-pdf."""
from __future__ import annotations

from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext
from tools.office import convertir_a_pdf


def run(ctx: ToolContext) -> list[dict]:
    for inp in ctx.inputs:
        ext = inp.ext or Path(inp.name).suffix.lstrip(".").lower()
        if ext == "pdf":
            # El visor abre los PDF sin subirlos; un PDF aquí es un uso indebido de la API.
            raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "Los PDF se abren en el navegador")
    return convertir_a_pdf.run(ctx)
