"""docs/TOOLS.md y docs/ERRORS.md generados (01-1, regla 7; 7.24 y 17): al día y con el motivo de cada desactivada."""
from __future__ import annotations

import json
import shutil
import subprocess
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
    assert "| Write PDF (`/en/write-pdf`) | `escribir-pdf` | disponible |" in text
    # Las apagadas por defecto (`default_enabled`) salen como apagadas; firmar-pdf ya no lo está (F4-B2b, D-199).
    assert "| Sign PDF (`/en/sign-pdf`) | `firmar-pdf` | disponible |" in text


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


def _page(complete: bool, reviewed: bool = False) -> str:
    return json.dumps({"complete": complete, "reviewed": reviewed, "intro": [], "faq": []})


@pytest.mark.skipif(shutil.which("git") is None, reason="sin git")
def test_content_status_comes_from_the_git_index(tmp_path, monkeypatch):
    """La columna «Contenido propio» sale del índice de git: los archivos sin añadir de otro lote en paralelo no
    cuentan (así TOOLS.md coincide con el árbol de su commit) y lo añadido se lee tal como está en el índice."""
    content = tmp_path / gen_docs.CONTENT_DIR
    content.mkdir(parents=True)
    (content / "a.json").write_text(_page(True), encoding="utf-8")
    (content / "b.json").write_text(_page(True, True), encoding="utf-8")
    (content / "sin-anadir.json").write_text(_page(True), encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", f"{gen_docs.CONTENT_DIR}/a.json", f"{gen_docs.CONTENT_DIR}/b.json"],
                   check=True)
    (content / "a.json").write_text(_page(False), encoding="utf-8")  # cambio sin añadir: no cuenta
    monkeypatch.setattr(gen_docs, "ROOT", tmp_path)
    assert gen_docs._content() == {"a": "redactado, sin revisar", "b": "revisado"}


def test_content_status_without_a_repository_reads_the_disk(tmp_path, monkeypatch):
    content = tmp_path / gen_docs.CONTENT_DIR
    content.mkdir(parents=True)
    (content / "a.json").write_text(_page(False), encoding="utf-8")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    monkeypatch.setattr(gen_docs, "ROOT", tmp_path)
    assert gen_docs._content() == {"a": "incompleto"}
