"""convertir-desde-pdf (A.9): una página cuyo formulario cambia con el formato; delega en la herramienta de ese formato
con las mismas opciones y en el mismo worker (el enrutado ya lo eligió según el formato)."""
from __future__ import annotations

import dataclasses

from core.errors import ErrorCode, ToolError
from core.registry import load_impl, load_registry
from tools.base import ToolContext
from tools.convert.specs import FORMATS


def run(ctx: ToolContext) -> list[dict]:
    values = ctx.options.model_dump()
    slug = FORMATS.get(values.get("formato", ""))
    if slug is None:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "formato")
    spec = load_registry().require(slug)
    accepted = spec.options.model_fields
    try:
        options = spec.options.model_validate({k: v for k, v in values.items() if k in accepted})
    except ValueError as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, str(exc)[:200]) from exc
    return load_impl(spec)(dataclasses.replace(ctx, tool=slug, options=options))
