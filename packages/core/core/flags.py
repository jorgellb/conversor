"""Precedencia de flags (5.2).

1. `TOOL_<SLUG>_ENABLED=false` en el entorno apaga siempre.
2. Si no está definida, manda la fila de `feature_flags`.
3. Sin fila, la herramienta está activa desde su fase (si está en el registro, está implementada).
4. Los flags temáticos solo pueden apagar.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

THEMATIC_FLAGS = {
    "HEVC_DECODE_ENABLED": False,
    "INVOICING_ES_ENABLED": False,
    "VIDEO_H264_ENCODING_ENABLED": False,
    "GDRIVE_ENABLED": False,
    "DROPBOX_ENABLED": False,
}

# Herramientas afectadas por cada flag temático.
THEMATIC_TOOLS: dict[str, set[str]] = {
    "HEVC_DECODE_ENABLED": {"heic-a-pdf", "heic-a-jpg", "heic-a-png"},
    "INVOICING_ES_ENABLED": {"crear-factura", "crear-factura-electronica", "pdf-a-factura-electronica"},
}


def env_var_name(slug: str) -> str:
    return "TOOL_" + slug.upper().replace("-", "_") + "_ENABLED"


def _env_bool(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def thematic_enabled(name: str, env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    value = _env_bool(env.get(name))
    return THEMATIC_FLAGS.get(name, False) if value is None else value


def is_tool_enabled(slug: str, db_flags: Mapping[str, bool] | None = None, env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    explicit = _env_bool(env.get(env_var_name(slug)))
    if explicit is False:
        return False
    enabled = True
    if explicit is None and db_flags is not None and slug in db_flags:
        enabled = bool(db_flags[slug])
    for flag, tools in THEMATIC_TOOLS.items():
        if slug in tools and not thematic_enabled(flag, env):
            return False
    return enabled
