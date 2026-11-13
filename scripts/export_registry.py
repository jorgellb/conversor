"""Genera `packages/registry/registry.json` (5.2): especificaciones públicas, planes y categorías.

Uso: `python scripts/export_registry.py` para escribirlo y `--check` en la CI para fallar si no está al día.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core"), str(ROOT / "packages/tools")]

from core.plans import load_plans_file  # noqa: E402
from core.registry import load_registry  # noqa: E402

OUT = ROOT / "packages/registry/registry.json"
CATEGORIES = [
    {"id": "pdf", "es": "PDF", "en": "PDF"},
    {"id": "office", "es": "Office", "en": "Office"},
    {"id": "image", "es": "Imagen", "en": "Image"},
    {"id": "audio", "es": "Audio", "en": "Audio"},
    {"id": "video", "es": "Vídeo", "en": "Video"},
    {"id": "ai", "es": "IA", "en": "AI"},
    {"id": "data", "es": "Datos", "en": "Data"},
    {"id": "3d", "es": "3D", "en": "3D"},
    {"id": "sign", "es": "Firma", "en": "Sign"},
    {"id": "invoice", "es": "Facturas", "en": "Invoices"},
]


def build() -> str:
    registry = load_registry()
    plans = {pid: p.model_dump() for pid, p in load_plans_file(ROOT / "config/plans.yaml").items()}
    data = {
        "categories": CATEGORIES,
        "plans": plans,
        "tools": [spec.to_public() for spec in registry.specs],
    }
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def main(argv: list[str]) -> int:
    content = build()
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != content:
            print("registry.json no está al día: ejecuta python scripts/export_registry.py", file=sys.stderr)
            return 1
        print("registry.json al día")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(content, encoding="utf-8")
    print(f"Escrito {OUT.relative_to(ROOT)} con {content.count('\"slug_es\"')} herramientas")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
