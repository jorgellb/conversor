"""F3, lote C: imagen-a-excel en `workerconvert` con Docling y Tesseract reales (sin IA: la tabla se reconoce o la IA
está apagada). El camino con IA va en tests/test_ia_imagenes.py con el proveedor falso.

Se ejecuta en el job `docling` de la CI (Docling solo va en la imagen `worker-convert`); sin Docling se omite.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from core.errors import ErrorCode, ToolError
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida

pytest.importorskip("docling")
pytestmark = [pytest.mark.needs_docling, pytest.mark.needs_tesseract,
              pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no instalado")]
TOOL = "imagen-a-excel"


def _values(path: str) -> dict[str, list[list]]:
    from openpyxl import load_workbook

    wb = load_workbook(path)
    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}


def test_printed_table_to_xlsx_with_real_numbers(make_ctx, fixtures_dir):
    out = run(TOOL, make_ctx(TOOL, [fixtures_dir / "tabla.png"]))
    assert out[0]["name"] == "tabla.xlsx" and out[0]["note"] == "Tablas reconocidas sin IA: 1."
    (title, rows), = _values(out[0]["path"]).items()
    assert title == "Tabla 1" and rows[0] == ["Producto", "Unidades", "Precio"]
    assert ["Manzanas", 12, 3.5] in rows and ["Naranjas", 1230, 15] in rows


def test_numbers_off_and_all_tables_in_one_sheet(make_ctx, fixtures_dir):
    out = run(TOOL, make_ctx(TOOL, [fixtures_dir / "tabla.png"], {"numeros": False, "hojas": "todas_en_una"}))
    (title, rows), = _values(out[0]["path"]).items()
    assert title == "Tablas" and rows[0][0] == "Tabla 1" and ["Manzanas", "12", "3,50"] in rows


def test_spreadsheet_screenshot_to_csv_with_delimiter(make_ctx, fixtures_dir):
    out = run(TOOL, make_ctx(TOOL, [fixtures_dir / "tabla-hoja.png"], {"formato": "csv", "delimitador": "punto_y_coma"}))
    assert out[0]["name"] == "tabla-hoja-tabla-1.csv"
    body = Path(out[0]["path"]).read_bytes().decode("utf-8")
    assert body.startswith("﻿") and "Producto;Unidades;Precio" in body and "Manzanas;12;3,50" in body


def test_skewed_table_is_straightened_before_docling(make_ctx, fixtures_dir):
    out = run(TOOL, make_ctx(TOOL, [fixtures_dir / "tabla-torcida.png"], {"usar_ia": False}))
    rows = next(iter(_values(out[0]["path"]).values()))
    assert any(r and r[0] == "Manzanas" for r in rows), rows


def test_without_ai_an_unrecognised_table_lists_the_text_or_fails_in_csv(make_ctx, fixtures_dir):
    out = run(TOOL, make_ctx(TOOL, [fixtures_dir / "tabla-manuscrita.png"], {"usar_ia": False}))
    assert "No se ha encontrado ninguna tabla" in out[0]["note"]
    (title, rows), = _values(out[0]["path"]).items()
    assert title == "Texto" and any("Manzanas" in str(r[0]) for r in rows)
    with pytest.raises(ToolError) as err:
        run(TOOL, make_ctx(TOOL, [fixtures_dir / "tabla-manuscrita.png"], {"usar_ia": False, "formato": "csv"}))
    assert err.value.code == ErrorCode.NO_TABLES and err.value.detail == "image_no_tables"


def test_ocr_languages_change_the_cells(make_ctx, fixtures_dir):
    """«Idiomas del OCR» llega a Docling: en español se leen las tildes y la eñe, en inglés no. Los códigos postales con
    un cero delante se quedan en texto."""
    def rows(languages: list[str]) -> list[list]:
        out = run(TOOL, make_ctx(TOOL, [fixtures_dir / "tabla-acentos.png"], {"idiomas": languages, "usar_ia": False}))
        return next(iter(_values(out[0]["path"]).values()))

    spanish, english = rows(["spa"]), rows(["eng"])
    assert ["Almería", "04001", "Andalucía"] in spanish and ["Logroño", 26001, "La Rioja"] in spanish, spanish
    assert spanish != english and not any("Logroño" in str(c) for r in english for c in r), english


def test_csv_names_follow_the_locale(make_ctx, fixtures_dir):
    ctx = make_ctx(TOOL, [fixtures_dir / "tabla-hoja.png"], {"formato": "csv"})
    ctx.locale = "en"
    out = run(TOOL, ctx)
    assert out[0]["name"] == "tabla-hoja-table-1.csv"


def test_pixel_bomb_is_rejected_before_docling(make_ctx, fixtures_dir):
    with pytest.raises(ToolError) as err:
        run(TOOL, make_ctx(TOOL, [fixtures_dir / "gigante.png"]))
    assert err.value.code == ErrorCode.LIMIT_EXCEEDED
