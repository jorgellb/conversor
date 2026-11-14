"""docs/TOOLS.md y docs/ERRORS.md generados (01-1, regla 7; 7.24 y 17): al día y con el motivo de cada desactivada."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gen_docs  # noqa: E402


def test_docs_up_to_date():
    assert gen_docs.main(["--check"]) == 0, "ejecuta .venv/bin/python scripts/gen_docs.py"


def test_tools_md_sections():
    text = gen_docs.tools()
    for heading in ("## Desactivadas y por qué", "## Fuera de alcance (7.24)", "## Paridad con PDF24", "## Mejoras posteriores"):
        assert heading in text
    # Las de HEVC salen como apagadas y con su motivo.
    assert "| `heic-a-jpg` | Apagada mientras `HEVC_DECODE_ENABLED`" in text
    assert "PostScript" in text and "SLDPRT" in text
    assert "| Merge PDF (`/en/merge-pdf`) | `unir-pdf` | disponible |" in text
    assert "| Sign PDF (`/en/sign-pdf`) | `firmar-pdf` | pendiente (F4) |" in text


def test_default_off_tool_needs_a_reason():
    data = {"tools": [{"slug_es": "udf-a-pdf", "default_enabled": False}]}
    notes = {"temas": {"HEVC_DECODE_ENABLED": "x", "INVOICING_ES_ENABLED": "y"}, "herramientas": {}}
    with pytest.raises(SystemExit, match="udf-a-pdf"):
        gen_docs._off_reasons(data, notes)
    notes["herramientas"] = {"udf-a-pdf": "Sin muestras con licencia clara (01-1, regla 8)."}
    reasons = gen_docs._off_reasons(data, notes)
    assert reasons["udf-a-pdf"].startswith("Apagada por defecto; se enciende con `TOOL_UDF_A_PDF_ENABLED=true`.")


def test_thematic_flag_needs_a_reason():
    with pytest.raises(SystemExit, match="HEVC_DECODE_ENABLED"):
        gen_docs._off_reasons({"tools": []}, {"temas": {}})


def test_pdf24_row_of_a_registered_tool_drops_its_phase(monkeypatch):
    parity = {"revisado": "2026-11-14", "herramientas": [{"pdf24": "Merge PDF", "ruta": "/en/merge-pdf",
                                                          "equivalentes": ["unir-pdf:F1"]}]}
    monkeypatch.setattr(gen_docs, "_yaml", lambda name: parity)
    with pytest.raises(SystemExit, match="unir-pdf ya está en el registro"):
        gen_docs._pdf24({"tools": [{"slug_es": "unir-pdf"}]}, {})


def test_phase_status_comes_from_tools_notes():
    assert gen_docs._phase_status({"fases": {"cerradas": ["F1", "F2", "F5 sin vídeo"], "en_curso": ["F3"]}}) == (
        "Fases cerradas: F1, F2 y F5 sin vídeo; en curso: F3.")
    assert gen_docs._phase_status({"fases": {"cerradas": ["F1", "F2", "F3"], "en_curso": []}}) == (
        "Fases cerradas: F1, F2 y F3.")
    with pytest.raises(SystemExit, match="fases"):
        gen_docs._phase_status({})
