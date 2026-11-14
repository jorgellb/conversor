"""Números escritos en una celda de texto (D-67): una sola regla para pdf-a-excel, imagen-a-excel y ticket-a-excel.

Sin dependencias: se usa en `workerconvert`, `workerocr` y `workerai`.
"""
from __future__ import annotations

import re

NUMBER = {"es": re.compile(r"^-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$"), "en": re.compile(r"^-?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")}
CURRENCY = ("€", "$", "£")
MAX_DIGITS = 15  # cifras significativas que un número de Excel (doble precisión) guarda sin perder ninguna


def parse_number(text: str, locale: str, currency: bool = False) -> int | float | None:
    """Número escrito como en el idioma de la página («1.234,56» en español, «1,234.56» en inglés) o None.

    Se queda en texto (None) lo que parece un código y no una cantidad: con un cero delante («08001», un código postal;
    «0», «0,5» y «-0,25» sí son números) o con más de 15 cifras (una cuenta o un IBAN, que el número redondearía). Los
    enteros se leen con `int`, nunca pasando por `float`. Con `currency`, quita antes los símbolos €, $ y £.
    """
    t = text.strip().replace(" ", "").replace(" ", "")
    if currency:
        for symbol in CURRENCY:
            t = t.replace(symbol, "")
    pattern = NUMBER.get(locale, NUMBER["es"])
    if not t or not pattern.match(t):
        return None
    t = t.replace(",", "") if locale == "en" else t.replace(".", "").replace(",", ".")
    whole, _, decimals = t.lstrip("-").partition(".")
    if len(whole) > 1 and whole.startswith("0"):
        return None
    if len((whole + decimals).lstrip("0")) > MAX_DIGITS:
        return None
    if not decimals:
        return int(t)
    try:
        return float(t)
    except ValueError:
        return None
