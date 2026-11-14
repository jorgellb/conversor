"""Hojas de cálculo de imagen-a-excel y ticket-a-excel (F3, lote C): XLSX con openpyxl y CSV.

Se usan en `workerconvert`, `workerocr` y `workerai`, así que no cargan Docling ni LibreOffice. Los números se guardan
como números (D-67) y las fechas como fechas; los CSV llevan BOM para que Excel lea bien las tildes.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from tools import numeros

DELIMITERS = {"coma": ",", "punto_y_coma": ";", "tabulador": "\t"}


def parse_number(text: str, locale: str) -> int | float | None:
    """Número de una celda del OCR o del modelo; los importes pueden llevar €, $ o £ (la regla común, D-67)."""
    return numeros.parse_number(text, locale, currency=True)


@dataclass
class Sheet:
    title: str
    rows: list[list]
    header: bool = True
    # Columnas (desde 0) con importes: formato de dos decimales.
    money: set[int] = field(default_factory=set)


def sheet_title(text: str, used: set[str]) -> str:
    # Excel no admite []:*?/\ ni un apóstrofo al principio o al final (el título lo puede escribir el modelo).
    base = re.sub(r"[\[\]:*?/\\]", "", text).strip().strip("'").strip()[:31].strip().strip("'") or "Hoja"
    title, k = base, 2
    while title.lower() in used:
        suffix = f" {k}"
        title = base[: 31 - len(suffix)] + suffix
        k += 1
    used.add(title.lower())
    return title


def write_xlsx(dst: Path, sheets: list[Sheet], locale: str, numbers: bool = True) -> None:
    """Un libro con esas hojas. Con `numbers`, el texto que es un número pasa a número de verdad (no en la cabecera)."""
    from datetime import date

    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    for sheet in sheets:
        ws = wb.create_sheet(sheet_title(sheet.title, used))
        widths: dict[int, int] = {}
        for r, row in enumerate(sheet.rows, start=1):
            head = sheet.header and r == 1
            for c, value in enumerate(row, start=1):
                if isinstance(value, str) and numbers and not head:
                    parsed = parse_number(value, locale)
                    value = parsed if parsed is not None else value
                cell = ws.cell(row=r, column=c, value=value)
                if isinstance(value, str) and value.startswith("="):
                    cell.data_type = "s"  # texto del OCR o del modelo, nunca una fórmula (12.3)
                if head:
                    cell.font = Font(bold=True)
                elif isinstance(value, date):
                    cell.number_format = "DD/MM/YYYY" if locale != "en" else "YYYY-MM-DD"
                elif (c - 1) in sheet.money and isinstance(value, (int, float)):
                    cell.number_format = "#,##0.00"
                if value is not None:
                    widths[c] = max(widths.get(c, 0), len(str(value)))
        for col, width in widths.items():
            ws.column_dimensions[get_column_letter(col)].width = min(60, max(8, width + 2))
        if sheet.header and sheet.rows:
            ws.freeze_panes = "A2"
    if not wb.worksheets:
        wb.create_sheet("Hoja")
    wb.save(dst)


def csv_bytes(rows: list[list], delimiter: str, locale: str) -> bytes:
    """CSV con BOM. Los decimales van con la coma en español y con el punto en inglés."""
    from datetime import date

    def text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            # Inyección de fórmulas en CSV: una celda que empieza por =, +, @ o un tabulador va con un apóstrofo delante
            # (un «-» solo si no es un número), para que la hoja de cálculo la abra como texto (12.3).
            risky = value[:1] in ("=", "+", "@", "\t", "\r") or (value[:1] == "-" and parse_number(value, locale) is None)
            return "'" + value if risky else value
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, float):
            out = f"{value:.2f}"
            return out.replace(".", ",") if locale != "en" else out
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=DELIMITERS.get(delimiter, ","), lineterminator="\r\n")
    for row in rows:
        writer.writerow([text(v) for v in row])
    return ("﻿" + buf.getvalue()).encode("utf-8")
