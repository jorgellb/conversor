"""Precedencia de flags (5.2).

1. `TOOL_<SLUG>_ENABLED=false` en el entorno apaga siempre.
2. Si no está definida, manda la fila de `feature_flags`.
3. Sin fila, la herramienta está activa desde su fase (si está en el registro, está implementada).
4. Los flags temáticos solo pueden apagar.

Una herramienta con `default_enabled=False` (D-134) solo se enciende con `TOOL_<SLUG>_ENABLED=true`: la fila de
`feature_flags` puede apagarla, pero no encenderla, porque la web solo ve el entorno y las dos tienen que coincidir.

`THEMATIC_TOOLS` tiene que ser igual que `THEMATIC` de `apps/web/src/lib/flags.ts` (lo comprueba
`apps/web/test/flags.test.ts`).
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

# Herramientas que apaga cada flag temático. VIDEO_H264_ENCODING_ENABLED no apaga herramientas, solo la opción H.264
# de las de vídeo (11), y GDRIVE_ENABLED y DROPBOX_ENABLED, botones de la página (8.2.4).
THEMATIC_TOOLS: dict[str, set[str]] = {
    "HEVC_DECODE_ENABLED": {"heic-a-pdf", "heic-a-jpg", "heic-a-png"},
    # 7.23: solo las que generan facturas; las que validan o muestran facturas pueden activarse antes.
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


def _default_enabled(slug: str) -> bool:
    from core.registry import load_registry

    spec = load_registry().get(slug)
    return True if spec is None else spec.default_enabled


def is_tool_enabled(slug: str, db_flags: Mapping[str, bool] | None = None, env: Mapping[str, str] | None = None,
                    default: bool | None = None) -> bool:
    """`default` es el `default_enabled` del ToolSpec; si no se pasa, se lee del registro."""
    env = os.environ if env is None else env
    explicit = _env_bool(env.get(env_var_name(slug)))
    if explicit is False:
        return False
    for flag, tools in THEMATIC_TOOLS.items():
        if slug in tools and not thematic_enabled(flag, env):
            return False
    if explicit is True:
        return True
    if not (_default_enabled(slug) if default is None else default):
        return False
    if db_flags is not None and slug in db_flags:
        return bool(db_flags[slug])
    return True
