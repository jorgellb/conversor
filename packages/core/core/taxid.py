"""NIF, NIE y CIF españoles: letra o dígito de control (las mismas reglas que invoice-calc.ts)."""
from __future__ import annotations

import re

DNI = "TRWAGMYFPDXBNJZSQVHLCKE"


def nif_ok(value: str) -> bool:
    v = value
    if re.fullmatch(r"\d{8}[A-Z]", v):
        return DNI[int(v[:8]) % 23] == v[8]
    if re.fullmatch(r"[XYZ]\d{7}[A-Z]", v):
        return DNI[int(str("XYZ".index(v[0])) + v[1:8]) % 23] == v[8]
    if re.fullmatch(r"[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]", v):
        digits = [int(c) for c in v[1:8]]
        total = sum(d if i % 2 else (d * 2 // 10 + d * 2 % 10) for i, d in enumerate(digits))
        control = (10 - total % 10) % 10
        return v[8] in (str(control), "JABCDEFGHI"[control])
    return False


def normalize(value: str) -> str:
    return re.sub(r"[\s.\-]", "", value or "").upper()
