"""Genera docs/ERRORS.md (códigos estables y mensajes) y docs/TOOLS.md (catálogo) desde el código y el registro."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core"), str(ROOT / "packages/tools")]

from core.errors import MESSAGES, ErrorCode  # noqa: E402


def errors() -> str:
    lines = ["# Códigos de error (5.3)", "",
             "Códigos estables que devuelven la API (`error.code`) y las herramientas de navegador. Generado por "
             "`scripts/gen_docs.py` desde `packages/core/core/errors.py`.", "",
             "| Código | Mensaje (es) | Mensaje (en) |", "| --- | --- | --- |"]
    for code in ErrorCode:
        es = MESSAGES.get(code, {}).get("es", "")
        en = MESSAGES.get(code, {}).get("en", "")
        lines.append(f"| `{code}` | {es} | {en} |")
    return "\n".join(lines) + "\n"


def tools() -> str:
    data = json.loads((ROOT / "packages/registry/registry.json").read_text(encoding="utf-8"))
    content = {}
    for f in (ROOT / "apps/web/content/es").glob("*.json"):
        page = json.loads(f.read_text(encoding="utf-8"))
        content[f.stem] = "revisado" if page.get("reviewed") else ("redactado, sin revisar" if page.get("complete") else "incompleto")
    lines = ["# Herramientas (7 y 17.1)", "",
             "Catálogo publicado en esta entrega: F1 completo (lista de lanzamiento de 17.1 y resto de F1) y las herramientas adelantadas de F2 y F5. Generado por `scripts/gen_docs.py` "
             "desde `packages/registry/registry.json`. «Indexable» exige herramienta activa, pruebas en verde y contenido "
             "propio completo en el idioma (7.22); sin él, la página lleva `noindex`.", "",
             "| Herramienta (es / en) | Dónde | Grupo | Coste | Fase | Entrada → salida | Contenido propio |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for t in data["tools"]:
        where = {"client": "navegador", "server": "servidor", "hybrid": "híbrida"}[t["where"]]
        lines.append(f"| `{t['slug_es']}` / `{t['slug_en']}` | {where} | {t['worker_group'] or '—'} | {t['cost_class']} | {t['phase']} | "
                     f"{', '.join(t['inputs']) or '—'} → {', '.join(t['outputs']) or 'pantalla'} | {content.get(t['slug_es'], 'pendiente')} |")
    lines += ["", "La lista de lanzamiento (17.1) está completa. El resto del catálogo (secciones 7.3 a 7.23) llega en su fase; "
              "la comparación con PDF24 se cierra en F6 (17.1)."]
    return "\n".join(lines) + "\n"


def main() -> int:
    (ROOT / "docs" / "ERRORS.md").write_text(errors(), encoding="utf-8")
    (ROOT / "docs" / "TOOLS.md").write_text(tools(), encoding="utf-8")
    print("docs/ERRORS.md y docs/TOOLS.md generados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
