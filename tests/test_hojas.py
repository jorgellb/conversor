"""F3, lote C: hojas de imagen-a-excel y ticket-a-excel (tools/ai/hojas.py) sin motores: números, fechas, BOM,
separadores e inyección de fórmulas (12.3)."""
from __future__ import annotations

from datetime import date


def test_xlsx_numbers_dates_and_no_formulas(tmp_path):
    from openpyxl import load_workbook

    from tools.ai import hojas

    dst = tmp_path / "h.xlsx"
    rows = [["Concepto", "Importe", "Fecha"], ["Café", "1.234,56", date(2026, 11, 14)], ["=HYPERLINK(\"x\")", "-3,50", None]]
    hojas.write_xlsx(dst, [hojas.Sheet("Tickets", rows, money={1})], "es")
    ws = load_workbook(dst).active
    assert ws.title == "Tickets" and ws["B2"].value == 1234.56 and ws["B3"].value == -3.5
    assert ws["C2"].value.date() == date(2026, 11, 14) and ws["C2"].number_format == "DD/MM/YYYY"
    assert ws["A3"].data_type == "s" and ws["A3"].value == "=HYPERLINK(\"x\")"  # texto, no fórmula
    assert ws["A1"].font.bold and ws.freeze_panes == "A2"
    plain = tmp_path / "t.xlsx"
    hojas.write_xlsx(plain, [hojas.Sheet("T", rows)], "es", numbers=False)
    assert load_workbook(plain).active["B2"].value == "1.234,56"


def test_csv_bom_delimiter_decimals_and_formula_guard():
    from tools.ai import hojas

    rows = [["a", "b"], ["=1+1", 2.5], ["-3,50", "+34 600"], ["@x", date(2026, 1, 2)]]
    es = hojas.csv_bytes(rows, "punto_y_coma", "es").decode("utf-8")
    assert es.startswith("﻿") and "'=1+1;2,50" in es and "-3,50;'+34 600" in es and "'@x;2026-01-02" in es
    en = hojas.csv_bytes([["n", 2.5]], "tabulador", "en").decode("utf-8")
    assert "n\t2.50" in en


def test_parse_number_by_locale():
    from tools.ai.hojas import parse_number

    assert parse_number("1.234,56", "es") == 1234.56 and parse_number("1,234.56", "en") == 1234.56
    assert parse_number("12", "es") == 12 and parse_number("3,50 €", "es") == 3.5 and parse_number("abc", "es") is None


def test_codes_stay_text_and_integers_keep_every_digit(tmp_path):
    """Un código postal con su cero, una cuenta de 20 cifras o un IBAN no son cantidades: se quedan como texto."""
    from openpyxl import load_workbook

    from tools import numeros
    from tools.ai import hojas

    assert hojas.parse_number("08001", "es") is None and hojas.parse_number("0012", "en") is None
    assert hojas.parse_number("12345678901234567890", "es") is None
    assert hojas.parse_number("0", "es") == 0 and hojas.parse_number("0,5", "es") == 0.5 and hojas.parse_number("-0.25", "en") == -0.25
    assert hojas.parse_number("123456789012345", "es") == 123456789012345  # 15 cifras: un entero exacto
    assert numeros.parse_number("3,50 €", "es") is None and numeros.parse_number("1.230", "es") == 1230  # pdf-a-excel
    dst = tmp_path / "c.xlsx"
    hojas.write_xlsx(dst, [hojas.Sheet("Datos", [["CP", "Cuenta"], ["08001", "12345678901234567890"]])], "es")
    ws = load_workbook(dst).active
    assert ws["A2"].value == "08001" and ws["B2"].value == "12345678901234567890"


def test_sheet_titles_without_edge_apostrophes():
    from tools.ai.hojas import sheet_title

    used: set[str] = set()
    assert sheet_title("'Ventas'", used) == "Ventas" and sheet_title("[2026]: total*", used) == "2026 total"
    assert sheet_title("''", used) == "Hoja" and sheet_title("ventas", used) == "ventas 2"
    assert sheet_title("L'Hospitalet", used) == "L'Hospitalet"
