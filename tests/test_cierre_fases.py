"""Cierres de fase (17, D-240 y D-244): cada herramienta de F5 y de F6 del catálogo (7) está en el registro con su página
completa en los dos idiomas; el vídeo de F5 es solo para Pro (`needs_video`) y la paridad con PDF24 de docs/TOOLS.md no
deja nada pendiente ni sin explicación."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core.registry import load_registry

ROOT = Path(__file__).resolve().parents[1]


def catalog_of(phase: str) -> set[str]:
    spec = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "docs" / "spec").glob("*.md") if "_completo" not in p.name)
    out = set()
    for line in spec.splitlines():
        if not re.search(rf"—\s*{phase}\b", line):
            continue
        m = re.match(r"\s*-\s*(.+?)\s+—", line)
        if not m:
            continue
        # Lo de dentro de un paréntesis son formatos («extraer-archivo-online (zip, rar, 7z, tar.gz)»), no herramientas.
        names = re.sub(r"\([^)]*\)", "", m.group(1))
        out |= {s.strip().strip("`") for s in names.split(",") if re.fullmatch(r"[a-z0-9-]+", s.strip().strip("`"))}
    return out


@pytest.mark.parametrize("phase,minimum", [("F5", 50), ("F6", 70)])
def test_every_tool_of_the_phase_is_registered_with_its_pages(phase, minimum):
    registry = load_registry()
    slugs = {t.slug_es: t for t in registry.specs}
    catalog = catalog_of(phase)
    assert len(catalog) >= minimum
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


def test_f5_video_is_pro_only():
    """7.9: todo el vídeo (conversores y edición) y pptx-a-video piden un plan con vídeo; los subtítulos, no."""
    registry = load_registry()
    video = {"mp4-a-webm", "webm-a-mp4", "mov-a-mp4", "mkv-a-mp4", "avi-a-mp4", "video-a-gif", "gif-a-mp4", "comprimir-video",
             "recortar-video", "rotar-video", "quitar-audio-video", "pptx-a-video"}
    assert {t.slug_es for t in registry.specs if t.needs_video} == video
