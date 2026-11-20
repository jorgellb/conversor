"""Cierre de F6 (17, D-240): cada herramienta de F6 del catálogo (7) está en el registro con su página en los dos idiomas,
y la paridad con PDF24 de docs/TOOLS.md no deja nada pendiente ni sin explicación."""
from __future__ import annotations

import json
import re
from pathlib import Path

from core.registry import load_registry

ROOT = Path(__file__).resolve().parents[1]


def f6_catalog() -> set[str]:
    spec = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "docs" / "spec").glob("*.md") if "_completo" not in p.name)
    out = set()
    for line in spec.splitlines():
        if not re.search(r"—\s*F6\b", line):
            continue
        m = re.match(r"\s*-\s*(.+?)\s+—", line)
        if not m:
            continue
        # Lo de dentro de un paréntesis son formatos («extraer-archivo-online (zip, rar, 7z, tar.gz)»), no herramientas.
        names = re.sub(r"\([^)]*\)", "", m.group(1))
        out |= {s.strip().strip("`") for s in names.split(",") if re.fullmatch(r"[a-z0-9-]+", s.strip().strip("`"))}
    return out


def test_every_f6_tool_is_registered_with_its_pages():
    registry = load_registry()
    slugs = {t.slug_es: t for t in registry.specs}
    catalog = f6_catalog()
    assert len(catalog) >= 70
    missing = sorted(s for s in catalog if s not in slugs)
    assert missing == []
    for slug in catalog:
        for lang in ("es", "en"):
            page = json.loads((ROOT / "apps" / "web" / "content" / lang / f"{slug}.json").read_text(encoding="utf-8"))
            assert page.get("complete") is True, (lang, slug)


def test_pdf24_parity_has_nothing_pending():
    tools = (ROOT / "docs" / "TOOLS.md").read_text(encoding="utf-8")
    summary = re.search(r"Resumen: (\d+) disponibles, (\d+) pendientes de su fase y (\d+) sin equivalente", tools)
    assert summary and summary.group(2) == "0"
    section = tools.split("## Paridad con PDF24", 1)[1].split("\n## ", 1)[0]
    for row in section.splitlines():
        if "| sin equivalente |" in row:
            assert row.rstrip(" |").split("|")[-1].strip(), row  # cada una con su explicación
