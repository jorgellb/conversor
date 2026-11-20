"""Hojas de cálculo y datos (7.12, F6-B, D-213 y D-214): CSV, Excel, JSON, XML y YAML sin motores externos.

openpyxl (MIT) para xlsx, la biblioteca estándar para CSV y JSON, defusedxml para leer XML (sin entidades ni DTD externos,
16.4) y PyYAML con `safe_load` (sin etiquetas de Python) y un límite a la expansión de alias. ods-a-xlsx y xlsx-a-ods van
con LibreOffice en `workeroffice` (tools/office/hojas.py).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import re
import zipfile
from collections import Counter
from decimal import Decimal
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.zipguard import check_zip
from tools.base import ToolContext, derived_name
from tools.pdf.common import with_batch_zip

MAX_DATA_BYTES = 25 * 1024 * 1024
MAX_NODES = 2_000_000  # valores tras expandir los alias de YAML (los textos largos pesan más) o al leer XML
MAX_DEPTH = 200
MAX_OUTPUT_BYTES = 200 * 1024 * 1024  # lo que se escribe: un JSON o un CSV pequeño puede multiplicarse (D-218)
MAX_CELLS = 20_000_000  # filas × columnas al leer Excel o al aplanar JSON
MAX_MERGED = 500_000  # pares copiados por las claves de fusión «<<» de YAML
MAX_CELL_CHARS = 32_767  # lo que cabe en una celda de Excel
EXCEL_ROWS, EXCEL_COLS = 1_048_576, 16_384
SEPARATOR = {"coma": ",", "punto_y_coma": ";", "tabulador": "\t", "barra": "|"}
csv.field_size_limit(MAX_DATA_BYTES)

NOTES = {
    "es": {
        "detected": "Codificación detectada: {enc}; separador: {sep}.",
        "fixed": "{n} secuencia(s) con letras mal convertidas («Ã±», «Ã©»…) corregidas.",
        "nothing": "El archivo ya estaba bien en UTF-8: solo se ha normalizado la salida.",
        "formulas": "{n} fórmula(s) sin valor calculado guardado salen vacías: abre el libro en Excel o LibreOffice, guárdalo y vuelve a convertirlo.",
        "lossy": "{n} carácter(es) que no existen en Windows-1252 se han cambiado por «?».",
        "unwrapped": "Se ha usado la lista «{key}» del objeto principal.",
        "jsonl": "Leído como JSON Lines (un objeto por línea).",
        "docs": "{n} documentos YAML: el JSON es una lista con uno por documento.",
        "sheets": "{n} hojas.",
        "illegal": "{n} celda(s) con caracteres de control (como el fin de archivo de MS-DOS) se han limpiado.",
        "truncated": "{n} celda(s) de más de 32 767 caracteres se han recortado: es lo que cabe en una celda de Excel.",
    },
    "en": {
        "detected": "Encoding detected: {enc}; separator: {sep}.",
        "fixed": "{n} sequence(s) of mis-converted letters (“Ã±”, “Ã©”…) fixed.",
        "nothing": "The file was already valid UTF-8: only the output was normalised.",
        "formulas": "{n} formula(s) with no saved calculated value come out empty: open the workbook in Excel or LibreOffice, save it and convert it again.",
        "lossy": "{n} character(s) that do not exist in Windows-1252 were replaced with “?”.",
        "unwrapped": "The “{key}” list of the main object was used.",
        "jsonl": "Read as JSON Lines (one object per line).",
        "docs": "{n} YAML documents: the JSON is a list with one per document.",
        "sheets": "{n} sheets.",
        "illegal": "{n} cell(s) with control characters (such as the MS-DOS end-of-file mark) were cleaned.",
        "truncated": "{n} cell(s) longer than 32,767 characters were cut: that is what fits in an Excel cell.",
    },
}
SEP_NAMES = {",": "«,»", ";": "«;»", "\t": "tab", "|": "«|»"}


def _t(ctx: ToolContext) -> dict:
    return NOTES.get(ctx.locale, NOTES["es"])


def _read(path: Path) -> bytes:
    if path.stat().st_size > MAX_DATA_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Datos de más de 25 MB")
    return path.read_bytes()


def write_capped(dst: Path, chunks) -> int:
    """Escribe por tramos (texto en UTF-8; los sustitutos sueltos de un JSON pasan a «?») y para en MAX_OUTPUT_BYTES."""
    total = 0
    with open(dst, "wb") as f:
        for chunk in chunks:
            data = chunk.encode("utf-8", errors="replace") if isinstance(chunk, str) else chunk
            total += len(data)
            if total > MAX_OUTPUT_BYTES:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_output_too_big")
            f.write(data)
    return total


def _batched(chunks, size: int = 65536):
    buf, n = [], 0
    for chunk in chunks:
        buf.append(chunk)
        n += len(chunk)
        if n >= size:
            yield "".join(buf)
            buf, n = [], 0
    if buf:
        yield "".join(buf)


def write_json(dst: Path, data) -> None:
    encoder = json.JSONEncoder(ensure_ascii=False, indent=2, allow_nan=False)
    try:
        write_capped(dst, _batched(_with_newline(encoder.iterencode(data))))
    except ValueError as exc:  # un número infinito que no se ha podido convertir
        raise ToolError(ErrorCode.CORRUPT_FILE, "JSON no válido") from exc
    except RecursionError as exc:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_too_deep") from exc


def _with_newline(chunks):
    yield from chunks
    yield "\n"


# Inyección de fórmulas en un CSV que se abrirá en una hoja de cálculo (12.3): la misma regla que tools/ai/hojas.py, un
# apóstrofo delante de lo que empieza por =, +, @, tabulador o retorno, y de «-» si no es un número.
RISKY_START = ("=", "+", "@", "\t", "\r")


PHONE_OR_NUMBER = re.compile(r"[+-][\d\s().,/-]*")


def guard_formula(value: str) -> str:
    """Un «+» o un «-» seguidos solo de cifras, espacios y signos de un teléfono o un número («+34 600 111 222», «-5,2») no
    son peligrosos y no llevan apóstrofo: estropearía los teléfonos al importar contactos en Google u Outlook."""
    if value[:1] in ("=", "@", "\t", "\r") or (value[:1] in "+-" and value[:1] and not PHONE_OR_NUMBER.fullmatch(value)):
        return "'" + value
    return value


def unguard(value: str) -> str:
    """Lo contrario de `guard_formula` al leer un CSV hecho aquí."""
    return value[1:] if value[:1] == "'" and value[1:2] in ("=", "@", "+", "-", "\t", "\r") else value


# --- Texto y codificaciones ---------------------------------------------------------------------------------------

BOMS = ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe\x00\x00", "utf-32"), (b"\x00\x00\xfe\xff", "utf-32"),
        (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16"))
CANDIDATES = ["cp1252", "iso8859_15", "cp850", "mac_roman", "latin_1"]
ENCODINGS = {"windows-1252": "cp1252", "iso-8859-1": "latin_1", "iso-8859-15": "iso8859_15", "cp850": "cp850",
             "mac-roman": "mac_roman", "utf-16": "utf-16"}
LABELS = {"utf-8": "UTF-8", "utf-8-sig": "UTF-8", "utf-16": "UTF-16", "utf-32": "UTF-32", "cp1252": "Windows-1252",
          "iso8859_15": "ISO-8859-15", "cp850": "MS-DOS (CP850)", "mac_roman": "Mac Roman", "latin_1": "ISO-8859-1"}


PUNCT_RE = re.compile(r"[“”‘’–—…•]")


def _spanish_score(text: str) -> float:
    """Cuánto se parece a texto en un idioma latino: letras con tilde y signos comunes suman; controles y símbolos raros
    (lo que sale al leer con la tabla equivocada) restan."""
    good = sum(text.count(c) for c in "áéíóúñÁÉÍÓÚÑüÜàèòçÇ¿¡€ºª")
    bad = sum(1 for c in text if ("\x80" <= c <= "\x9f") or c in "ÃÂ¢¤¦¨©«¬®¯±²³´µ¶·¸¹»¼½¾×÷þÞðÐ¥" or "─" <= c <= "▟")
    # Las comillas tipográficas, las rayas y los puntos suspensivos de Word y Excel (0x91 a 0x97 en Windows-1252) son buena
    # señal junto a un espacio o un signo; entre dos letras («Mar’a», «Nœ–ez») delatan la tabla equivocada (Mac Roman).
    for m in PUNCT_RE.finditer(text):
        before, after = text[m.start() - 1: m.start()], text[m.end(): m.end() + 1]
        if before.isalpha() and after.isalpha():
            bad += m.group() != "’"  # «don’t» es inglés correcto
        else:
            good += 1
    return good - 3 * bad


def decode(raw: bytes, forced: str | None = None) -> tuple[str, str]:
    """(texto, códec): BOM, UTF-8 estricto o la tabla de un byte que mejor encaja (charset-normalizer y una puntuación
    propia para no confundir Windows-1252 con MS-DOS o Mac Roman)."""
    if forced:
        try:
            return raw.decode(forced), forced
        except UnicodeDecodeError as exc:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "csv_wrong_encoding") from exc
    for bom, codec in BOMS:
        if raw.startswith(bom):
            try:
                return raw.decode(codec), codec
            except UnicodeDecodeError:
                break
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    import charset_normalizer

    sample = raw[:200_000]
    options = []
    best = charset_normalizer.from_bytes(sample, cp_isolation=CANDIDATES).best()
    if best is not None:
        options.append(best.encoding)
    options += [c for c in CANDIDATES if c not in options]
    scored = []
    for codec in options:
        try:
            # Windows-1252 por delante: MS-DOS y Mac Roman solo si encajan claramente mejor.
            prior = 2 if codec == "cp1252" else 0
            scored.append((_spanish_score(sample.decode(codec)) + prior, -options.index(codec), codec))
        except UnicodeDecodeError:
            continue
    codec = max(scored)[2] if scored else "latin_1"
    return raw.decode(codec, errors="replace"), codec


_RUN = re.compile(r"[^\x00-\x7f]+")
MOJIBAKE_OK = set("‘’‚“”„†‡•…‰‹›€™–—")


def _as_cp1252_bytes(run: str) -> bytes | None:
    out = bytearray()
    for ch in run:
        try:
            out += ch.encode("cp1252")
        except UnicodeEncodeError:
            if ord(ch) < 256:
                out.append(ord(ch))  # 0x81, 0x8D, 0x8F, 0x90 y 0x9D: Windows los deja pasar como Latin-1
            else:
                return None
    return bytes(out)


def fix_mojibake(text: str) -> tuple[str, int]:
    """«Ã±» → «ñ»: UTF-8 leído como Windows-1252 (o Latin-1) y guardado otra vez. Se corrige tramo a tramo y solo si
    el tramo vuelve a ser UTF-8 válido, así que una «Ã» legítima seguida de otra letra no se toca. Dos pasadas por si se
    hizo dos veces."""
    fixed = 0

    def sub(m: re.Match) -> str:
        nonlocal fixed
        raw = _as_cp1252_bytes(m.group(0))
        if raw is None:
            return m.group(0)
        try:
            new = raw.decode("utf-8")
        except UnicodeDecodeError:
            return m.group(0)
        if new == m.group(0) or not all(c.isascii() or "\u00a0" <= c <= "\u017f" or c in MOJIBAKE_OK for c in new):
            # Lo que da otra cosa que letras latinas o puntuación común no era un error: «café\u00a0»» o «QUÉ»» se quedan.
            return m.group(0)
        fixed += 1
        return new

    for _ in range(2):
        before = fixed
        text = _RUN.sub(sub, text)
        if fixed == before:
            break
    return text, fixed


# --- CSV ------------------------------------------------------------------------------------------------------------


def sniff_separator(text: str) -> str:
    """El separador con el que el encabezado tiene más de una columna y más filas tienen ese mismo número de campos (con
    las comillas del CSV). `csv.Sniffer` elegía la coma en un CSV español con «;» y decimales con coma (D-220)."""
    lines = [line for line in text[:65536].splitlines()[:50] if line.strip()]
    if not lines:
        return ","
    best, best_key = ",", None
    for order, sep in enumerate((";", "\t", ",", "|")):
        counts = [len(row) for row in csv.reader(lines, delimiter=sep)]
        header = counts[0]
        same = sum(1 for c in counts if c == header) / len(counts)
        key = (header > 1, round(same, 2), header if same >= 0.5 else 0, -order)
        if best_key is None or key > best_key:
            best, best_key = sep, key
    return best if best_key and best_key[0] else ","


def read_csv(ctx: ToolContext, path: Path, separador: str = "auto") -> tuple[list[list[str]], str, str]:
    text, codec = decode(_read(path))
    sep = SEPARATOR.get(separador) or sniff_separator(text)
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=sep))
    while rows and not any(cell.strip() for cell in rows[-1]):
        rows.pop()
    return rows, codec, sep


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?)?$")
POINT_RE = re.compile(r"^[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
GROUPED = {"coma": re.compile(r"^[-+]?\d{1,3}(?:\.\d{3})+$"), "punto": re.compile(r"^[-+]?\d{1,3}(?:,\d{3})+$")}
COMMA_RE = re.compile(r"^[-+]?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?$")


def _decimal_of(rows: list[list[str]], sep: str = ",") -> tuple[str, bool]:
    """(coma o punto, si se ha visto con claridad) según lo que más aparezca en las celdas que solo pueden ser una cosa
    («12,5» o «1.234,56» frente a «12.5» o «1,234.56»). Sin pistas, coma con el separador «;» (lo habitual en España)."""
    comma = point = 0
    for row in rows[:2000]:
        for cell in row:
            c = cell.strip()
            if re.fullmatch(r"[-+]?\d+,\d{1,2}|[-+]?\d{1,3}(?:\.\d{3})+,\d+", c):
                comma += 1
            elif re.fullmatch(r"[-+]?\d+\.\d{1,2}|[-+]?\d{1,3}(?:,\d{3})+\.\d+", c):
                point += 1
    if comma == point:
        return ("coma" if sep == ";" else "punto"), False
    return ("coma" if comma > point else "punto"), True


def to_number(value: str, decimal: str, strict: bool = False) -> int | float | None:
    """Número si lo es sin ambigüedad. Se quedan como texto los ceros a la izquierda («00123», códigos postales), los
    números de más de 15 cifras (no caben en Excel sin perder dígitos), los que llevan «+» (teléfonos), la notación
    científica («12E3» suele ser una referencia) y los vacíos. Con `strict` (decimal sin pistas claras), también «1,500» y
    «1.500», que pueden ser mil quinientos o uno y medio."""
    v = value.strip()
    if not v or v.startswith("+") or len(re.sub(r"\D", "", v)) > 15 or (strict and GROUPED[decimal].fullmatch(v)):
        return None
    if decimal == "coma":
        if not COMMA_RE.fullmatch(v):
            return None
        v = v.replace(".", "").replace(",", ".")
    else:
        if not POINT_RE.fullmatch(v):
            return None
        v = v.replace(",", "")
    digits = v.lstrip("-")
    if len(digits) > 1 and digits[0] == "0" and digits[1] != ".":
        return None
    try:
        number = float(v)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return int(v) if re.fullmatch(r"-?\d+", v) else number


def to_date(value: str) -> dt.date | dt.datetime | None:
    v = value.strip()
    if not DATE_RE.fullmatch(v):
        return None
    try:
        parsed = dt.datetime.fromisoformat(v)
    except ValueError:
        return None
    return parsed.date() if len(v) == 10 else parsed


def _write_csv(dst: Path, rows, sep: str, encoding: str, ctx: ToolContext) -> list[str]:
    """CSV por tramos con el tope de salida; devuelve las notas (caracteres perdidos en Windows-1252)."""
    lost = 0

    def chunks():
        nonlocal lost
        if encoding == "utf-8-bom":
            yield b"\xef\xbb\xbf"
        buf = io.StringIO(newline="")
        writer = csv.writer(buf, delimiter=sep, lineterminator="\r\n")
        for n, row in enumerate(rows, 1):
            writer.writerow(row)
            if n % 2000 == 0 or buf.tell() > 1 << 20:
                yield from encode(buf.getvalue())
                buf.seek(0)
                buf.truncate()
        yield from encode(buf.getvalue())

    def encode(text: str):
        nonlocal lost
        if encoding == "windows-1252":
            lost += sum(1 for ch in text if not _encodable(ch))
            yield text.encode("cp1252", errors="replace")
        else:
            yield text.encode("utf-8", errors="replace")

    write_capped(dst, chunks())
    return [_t(ctx)["lossy"].format(n=lost)] if lost else []


def _encodable(ch: str) -> bool:
    try:
        ch.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


# --- Excel ------------------------------------------------------------------------------------------------------------


def _open_workbook(path: Path, data_only: bool = True):
    import openpyxl

    check_zip(path)
    try:
        return openpyxl.load_workbook(path, read_only=True, data_only=data_only)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError, TypeError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "xlsx") from exc


def sheet_rows(path: Path, which: str) -> tuple[list[tuple[str, list[list]]], int]:
    """[(nombre de la hoja, filas)] con los valores calculados y cuántas fórmulas no tienen valor guardado (openpyxl,
    pandas y otros programas escriben fórmulas sin calcularlas)."""
    values, formulas = _open_workbook(path, True), _open_workbook(path, False)
    try:
        # Solo hojas de datos: una hoja de gráfico no tiene celdas (y puede ser la activa).
        sheets = [ws.title for ws in values.worksheets if hasattr(ws, "iter_rows")]
        active = values.active.title if values.active is not None and hasattr(values.active, "iter_rows") else None
        names = sheets if which == "todas" else [active or (sheets[0] if sheets else None)]
        names = [n for n in names if n]
        out, missing, cells = [], 0, 0
        for name in names:
            ws_v, ws_f = values[name], formulas[name]
            # Las hojas ocultas también se exportan con «todas»: son datos del libro. Las filas vacías se cuentan y solo
            # se guardan si después viene una con datos (un formato aplicado hasta la fila 1 048 576 no llena la memoria).
            rows: list[list] = []
            empty = width = 0
            for row_v, row_f in zip(ws_v.iter_rows(values_only=True), ws_f.iter_rows(values_only=True)):
                row = list(row_v)
                for v, f in zip(row, row_f):
                    if v is None and isinstance(f, str) and f.startswith("="):
                        missing += 1
                while row and row[-1] is None:
                    row.pop()
                if not row:
                    empty += 1
                    continue
                if len(rows) + empty >= EXCEL_ROWS:
                    break
                rows.extend([] for _ in range(empty))
                empty = 0
                rows.append(row)
                width = max(width, len(row))
                # Se rellena hasta la fila más ancha al escribir: una celda en XFD1 y otra en A2000 son 33 millones.
                if len(rows) * width > MAX_CELLS - cells:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_too_big")
            width = max((len(r) for r in rows), default=0)
            cells += len(rows) * width
            out.append((name, PaddedRows(rows, width)))
        return out, missing
    finally:
        values.close()
        formulas.close()


class PaddedRows(list):
    """Las filas de una hoja, rellenadas con None hasta la más ancha solo cuando se leen."""

    def __init__(self, rows: list[list], width: int):
        super().__init__(rows)
        self.width = width

    def __iter__(self):
        for row in super().__iter__():
            yield row + [None] * (self.width - len(row))

    def __getitem__(self, i):
        row = super().__getitem__(i)
        return row + [None] * (self.width - len(row)) if isinstance(i, int) else [r + [None] * (self.width - len(r)) for r in row]


def cell_text(value, decimal: str = "punto") -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, dt.datetime):
        return value.date().isoformat() if value.time() == dt.time(0) else value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        total = int(value.total_seconds())
        return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"
    if isinstance(value, float):
        text = str(int(value)) if value.is_integer() and abs(value) < 1e15 else format(Decimal(repr(value)), "f")
        return text.replace(".", ",") if decimal == "coma" else text
    if isinstance(value, int):
        return str(value)
    return str(value)


def json_value(value):
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return cell_text(value)
    if isinstance(value, dt.timedelta):
        return cell_text(value)
    if isinstance(value, float) and value.is_integer() and abs(value) < 2**53:
        return int(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def keys_of(header: list) -> list[str]:
    """Claves a partir del encabezado: vacías → «columna_N», repetidas → «nombre_2»."""
    seen: Counter = Counter()
    out = []
    for i, h in enumerate(header, 1):
        key = cell_text(h).strip() or f"columna_{i}"
        seen[key] += 1
        out.append(key if seen[key] == 1 else f"{key}_{seen[key]}")
    return out


def _safe_sheet_title(name: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", "_", name).strip("'")[:31] or "Hoja"
    title, n = base, 2
    while title.lower() in used:
        suffix = f" ({n})"
        title, n = base[: 31 - len(suffix)] + suffix, n + 1
    used.add(title.lower())
    return title


def _fill_sheet(ws, rows: list[list[str]], o, sep: str = ",") -> dict[str, int]:
    """Filas de un CSV en una hoja: números, fechas ISO y el texto siempre como texto (nunca fórmula: «=HYPERLINK(…)»
    de un CSV no se ejecuta en Excel)."""
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    if len(rows) > EXCEL_ROWS:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{len(rows)} filas")
    width = max((len(r) for r in rows), default=0)
    if width > EXCEL_COLS:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{width} columnas")
    if o.decimal == "auto":
        decimal, clear = _decimal_of(rows[1:] if o.encabezado else rows, sep)
    else:
        decimal, clear = o.decimal, True
    counts = {"illegal": 0, "truncated": 0}
    widths = [0] * width
    for row in rows[:500]:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], min(60, len(cell)))
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(8, w + 2)
    if o.encabezado and rows:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(max(1, width))}{len(rows)}"
    bold = Font(bold=True)
    for r, row in enumerate(rows):
        cells = []
        for text in row:
            value = None
            if ILLEGAL_CHARACTERS_RE.search(text):  # el «\x1a» de fin de archivo de MS-DOS y otros controles
                text = ILLEGAL_CHARACTERS_RE.sub("", text)
                counts["illegal"] += 1
            if len(text) > MAX_CELL_CHARS:
                text = text[:MAX_CELL_CHARS]
                counts["truncated"] += 1
            if o.tipos and not (o.encabezado and r == 0):
                value = to_number(text, decimal, strict=not clear)
                if value is None:
                    value = to_date(text)
            cell = WriteOnlyCell(ws, value=value if value is not None else (text if text != "" else None))
            if value is None and text:
                cell.data_type = "s"  # aunque empiece por «=», «+», «-» o «@»
            if isinstance(value, dt.datetime):
                cell.number_format = "yyyy-mm-dd hh:mm:ss"
            elif isinstance(value, dt.date):
                cell.number_format = "yyyy-mm-dd"
            if o.encabezado and r == 0:
                cell.font = bold
            cells.append(cell)
        ws.append(cells)
    return counts


# --- JSON, XML y YAML ------------------------------------------------------------------------------------------------


def load_json(ctx: ToolContext, path: Path) -> tuple[object, list[str]]:
    text, _ = decode(_read(path))
    try:
        return json.loads(text), []
    except RecursionError as exc:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_too_deep") from exc
    except json.JSONDecodeError as first:
        if len(text) > 1 and "\n" not in text.strip():
            raise ToolError(ErrorCode.CORRUPT_FILE, f"JSON no válido (línea {first.lineno})") from first
        lines = [line for line in text.splitlines() if line.strip()]
        try:
            return [json.loads(line) for line in lines], [_t(ctx)["jsonl"]]
        except (ValueError, RecursionError):
            raise ToolError(ErrorCode.CORRUPT_FILE, f"JSON no válido (línea {first.lineno})") from first
    except ValueError as exc:  # un entero de más de 4300 cifras
        raise ToolError(ErrorCode.CORRUPT_FILE, "JSON no válido") from exc


def _check_size(data, limit: int = MAX_NODES) -> None:
    """Cuenta los valores como si los alias se expandieran (memo por id: un alias de un alias cuenta lo que vale) y
    rechaza los ciclos y lo demasiado profundo. Es lo que impide la «bomba de los mil millones de risas» de YAML."""
    memo: dict[int, int] = {}
    active: set[int] = set()

    def count(node, depth: int) -> int:
        if depth > MAX_DEPTH:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_too_deep")
        if isinstance(node, (str, bytes)):
            return 1 + len(node) // 64  # un texto largo repetido por alias también multiplica la salida
        if not isinstance(node, (dict, list, tuple, set, frozenset)):  # tuplas: !!pairs y !!omap; conjuntos: !!set
            return 1
        key = id(node)
        if key in memo:
            return memo[key]
        if key in active:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "data_cycle")
        active.add(key)
        children = [x for kv in node.items() for x in kv] if isinstance(node, dict) else node
        total = 1
        for child in children:
            total += count(child, depth + 1)
            if total > limit:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_too_big")
        active.discard(key)
        memo[key] = total
        return total

    count(data, 0)


def flatten(obj, prefix: str = "") -> dict[str, object]:
    """{"a": {"b": 1}, "c": [1, 2]} → {"a.b": 1, "c": "[1, 2]"}: las listas van como JSON en su celda."""
    out: dict[str, object] = {}
    if isinstance(obj, dict):
        if not obj and prefix:
            out[prefix] = ""
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            items = flatten(v, key).items() if isinstance(v, dict) else [(key, v)]
            for name, value in items:
                unique, n = name, 2
                while unique in out:  # {"a.b": 1, "a": {"b": 2}}: la segunda no pisa a la primera
                    unique, n = f"{name}_{n}", n + 1
                out[unique] = value
    else:
        out[prefix or "valor"] = obj
    return out


def _csv_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return str(value)


def records_of(ctx: ToolContext, data) -> tuple[list, list[str]]:
    """La lista de registros de un JSON: la propia lista, la única lista de objetos de un objeto ({"data": [...]}) o el
    objeto como una sola fila."""
    if isinstance(data, list):
        return data, []
    if isinstance(data, dict):
        lists = [k for k, v in data.items() if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)]
        if len(lists) == 1:
            return data[lists[0]], [_t(ctx)["unwrapped"].format(key=lists[0])]
        return [data], []
    return [data], []


XML_NAME = re.compile(r"^[A-Za-z_][\w.-]*$")


def xml_name(key: str) -> str:
    # Letras de cualquier idioma valen en un nombre XML («líneas»); el resto, «_».
    name = re.sub(r"[^\w.-]", "_", xml_text(str(key))) or "_"
    if not (name[0].isalpha() or name[0] == "_") or name.lower().startswith("xml"):
        name = f"_{name}"
    return name[:200]


XML_INVALID = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def xml_text(value: str) -> str:
    """Sin los caracteres que XML 1.0 no admite (controles, sustitutos sueltos): el XML sale siempre bien formado."""
    return XML_INVALID.sub("", value)


def to_xml(data, root: str, item: str) -> bytes:
    import xml.etree.ElementTree as ET

    size = 0

    def element(parent, name: str, key=None):
        nonlocal size
        size += 2 * len(name) + 5
        if size > MAX_OUTPUT_BYTES:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_output_too_big")
        child = ET.SubElement(parent, name)
        if key is not None and name != str(key):
            child.set("clave", xml_text(str(key))[:500])
        return child

    def build(parent, value, depth: int) -> None:
        nonlocal size
        if depth > MAX_DEPTH:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_too_deep")
        if isinstance(value, dict):
            for k, v in value.items():
                name = xml_name(k)
                if isinstance(v, list):
                    for x in v:
                        build(element(parent, name, k), x, depth + 1)
                else:
                    build(element(parent, name, k), v, depth + 1)
        elif isinstance(value, list):
            for x in value:
                build(element(parent, item), x, depth + 1)
        elif value is None:
            pass
        elif isinstance(value, bool):
            parent.text = "true" if value else "false"
        else:
            parent.text = xml_text(_csv_cell(value))
            size += len(parent.text)

    top = ET.Element(root)
    build(top, data, 0)
    ET.indent(top)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(top, encoding="utf-8", xml_declaration=False) + b"\n"


def _scalar(text: str):
    t = text.strip()
    if t in ("true", "false"):
        return t == "true"
    if re.fullmatch(r"-?(?:0|[1-9]\d{0,14})", t):
        return int(t)
    if re.fullmatch(r"-?(?:0|[1-9]\d*)\.\d+(?:[eE][-+]?\d+)?", t) and len(t) < 25 and math.isfinite(float(t)):
        return float(t)
    return text


XML_NS = "http://www.w3.org/XML/1998/namespace"


def from_xml(raw: bytes, types: bool) -> dict:
    """XML a JSON: atributos con «@», texto con «#text» si convive con hijos o atributos (también el que va después de un
    hijo), hijos repetidos en una lista y los espacios de nombres con su prefijo («cbc:ID»; si dos URI usan el mismo,
    el segundo lleva un número). defusedxml rechaza entidades y DTD externos (XXE, 16.4). Cada hijo terminado se suelta
    del árbol al empezar el siguiente, así que la memoria no crece con los elementos ya leídos."""
    import defusedxml.ElementTree as DET
    from defusedxml import DefusedXmlException

    prefixes: dict[str, str] = {XML_NS: "xml"}
    taken: set[str] = {"xml"}
    # Cada marco: [elemento, valor (atributos e hijos), trozos de texto, claves que ya son listas]
    stack: list[list] = []
    root_holder: dict = {}
    nodes = 0

    def name(tag: str) -> str:
        if tag.startswith("{"):
            uri, local = tag[1:].split("}", 1)
            prefix = prefixes.get(uri, "")
            return f"{prefix}:{local}" if prefix else local
        return tag

    def value(text: str):
        return _scalar(text) if types else text

    def release(frame: list) -> None:
        """Los hijos terminados del elemento (todos menos el último, que acaba de empezar): su cola de texto va al padre."""
        elem = frame[0]
        while len(elem) > 1:
            child = elem[0]
            if child.tail and child.tail.strip():
                frame[2].append(child.tail.strip())
            elem.remove(child)

    try:
        for event, item in DET.iterparse(io.BytesIO(raw), events=("start-ns", "start", "end"), forbid_dtd=False,
                                         forbid_entities=True, forbid_external=True):
            if event == "start-ns":
                prefix, uri = item
                if uri not in prefixes:
                    unique, n = prefix, 2
                    while unique and unique in taken:
                        unique, n = f"{prefix}{n}", n + 1
                    prefixes[uri] = unique
                    taken.add(unique)
                continue
            if event == "start":
                nodes += 1
                if nodes > MAX_NODES or len(stack) > MAX_DEPTH:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_too_big")
                if stack:
                    release(stack[-1])
                stack.append([item, {"@" + name(k): value(v) for k, v in item.attrib.items()}, [], set()])
                continue
            elem, node, texts, _lists = stack.pop()
            pieces = [(elem.text or "").strip(), *texts, *((c.tail or "").strip() for c in elem)]
            text = " ".join(p for p in pieces if p)
            if not node:
                result = value(text) if text else None
            else:
                if text:
                    node["#text"] = value(text)
                result = node
            key = name(item.tag)
            if stack:
                parent, lists = stack[-1][1], stack[-1][3]
                if key in lists:
                    parent[key].append(result)
                elif key in parent:
                    parent[key] = [parent[key], result]
                    lists.add(key)
                else:
                    parent[key] = result
            else:
                root_holder[key] = result
            tail = elem.tail  # el analizador puede haberla leído ya: clear() la borraría
            elem.clear()
            elem.tail = tail
    except (DefusedXmlException, ValueError) as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities") from exc
    except SyntaxError as exc:  # ParseError
        raise ToolError(ErrorCode.CORRUPT_FILE, "XML no válido") from exc
    return root_holder


def _yaml_loader():
    """SafeLoader (sin etiquetas de Python) que cuenta los pares que copian las claves de fusión «<<»: una cadena de
    fusiones crece de forma cuadrática dentro del propio PyYAML, antes de que `_check_size` vea nada."""
    import yaml

    base = yaml.CSafeLoader if hasattr(yaml, "CSafeLoader") else yaml.SafeLoader

    class Loader(base):
        merged = 0

        def flatten_mapping(self, node):
            super().flatten_mapping(node)
            self.merged += len(node.value)
            if self.merged > MAX_MERGED:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_too_big")

    return Loader


def load_yaml(ctx: ToolContext, path: Path) -> tuple[object, list[str]]:
    import yaml

    text, _ = decode(_read(path))
    try:
        docs = list(yaml.load_all(text, Loader=_yaml_loader()))
    except ValueError as exc:  # un entero de más de 4300 cifras
        raise ToolError(ErrorCode.CORRUPT_FILE, "YAML no válido") from exc
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        raise ToolError(ErrorCode.CORRUPT_FILE, f"YAML no válido (línea {mark.line + 1})" if mark else "YAML no válido") from exc
    except RecursionError as exc:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_too_deep") from exc
    _check_size(docs)
    if not docs:
        return None, []
    if len(docs) == 1:
        return docs[0], []
    return docs, [_t(ctx)["docs"].format(n=len(docs))] if len(docs) > 1 else []


def _yaml_key(key) -> str:
    """Las claves de JSON son texto: true, null y los números como los escribiría JSON; las fechas en ISO."""
    if isinstance(key, str):
        return key
    if isinstance(key, (dt.datetime, dt.date)):
        return key.isoformat()
    if isinstance(key, (bool, int, float)) or key is None:
        return json.dumps(key) if not (isinstance(key, float) and not math.isfinite(key)) else str(key)
    return json.dumps(yaml_to_json_value(key), ensure_ascii=False)


def yaml_to_json_value(obj):
    if isinstance(obj, dict):
        return {_yaml_key(k): yaml_to_json_value(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [yaml_to_json_value(v) for v in obj]
    if isinstance(obj, (dt.datetime, dt.date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        import base64

        return base64.b64encode(obj).decode()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


YAML12_NUMBER = re.compile(r"[-+]?(?:\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?|0x[0-9a-fA-F]+|0o[0-7]+|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN)")


# --- Herramientas -----------------------------------------------------------------------------------------------------


def _xlsx_a_csv(ctx: ToolContext, inp) -> list[dict]:
    o, t = ctx.options, _t(ctx)
    sheets, missing = sheet_rows(inp.path, o.hojas)
    sep = SEPARATOR[o.separador]
    outputs = []
    notes = [t["formulas"].format(n=missing)] if missing else []
    for name, rows in sheets:
        out_name = derived_name(inp.name, f"-{name}" if len(sheets) > 1 else "", "csv")
        dst = ctx.output(out_name)
        lossy = _write_csv(dst, ([guard_formula(v) if isinstance(v, str) else cell_text(v, o.decimal) for v in row] for row in rows),
                           sep, o.codificacion, ctx)
        outputs.append({"path": str(dst), "name": out_name, "note": " ".join(notes + lossy) or None})
    if len(outputs) > 1:
        return [_zip_of(ctx, outputs, derived_name(inp.name, "-csv", "zip"))]
    return outputs


def _zip_of(ctx: ToolContext, outputs: list[dict], name: str) -> dict:
    from tools.base import zip_files

    dst = ctx.output(name)
    zip_files([(Path(o["path"]), o["name"]) for o in outputs], dst)
    for o in outputs:
        Path(o["path"]).unlink(missing_ok=True)
    notes = {o["note"] for o in outputs if o["note"]}
    return {"path": str(dst), "name": name, "note": " ".join(sorted(notes)) or None}


def _csv_a_xlsx(ctx: ToolContext) -> list[dict]:
    import openpyxl

    o, t = ctx.options, _t(ctx)
    parsed = []
    for inp in ctx.inputs:
        rows, codec, sep = read_csv(ctx, inp.path, o.separador)
        parsed.append((inp, rows, t["detected"].format(enc=LABELS.get(codec, codec), sep=SEP_NAMES.get(sep, sep)), sep))
    outputs = []
    if o.libro == "uno" and len(parsed) > 1:
        wb, used = openpyxl.Workbook(write_only=True), set()
        counts = Counter()
        for inp, rows, _note, sep in parsed:
            counts.update(_fill_sheet(wb.create_sheet(_safe_sheet_title(Path(inp.name).stem, used)), rows, o, sep))
        dst = ctx.output("hojas.xlsx")
        wb.save(dst)
        return [{"path": str(dst), "name": "hojas.xlsx", "note": " ".join([t["sheets"].format(n=len(parsed)), *_cell_notes(t, counts)])}]
    for inp, rows, note, sep in parsed:
        wb = openpyxl.Workbook(write_only=True)
        counts = _fill_sheet(wb.create_sheet(_safe_sheet_title(Path(inp.name).stem, set())), rows, o, sep)
        name = derived_name(inp.name, "", "xlsx")
        dst = ctx.output(name)
        wb.save(dst)
        outputs.append({"path": str(dst), "name": name, "note": " ".join([note, *_cell_notes(t, counts)])})
    return with_batch_zip(ctx, outputs, "csv-xlsx.zip")


def _cell_notes(t: dict, counts) -> list[str]:
    notes = []
    if counts.get("illegal"):
        notes.append(t["illegal"].format(n=counts["illegal"]))
    if counts.get("truncated"):
        notes.append(t["truncated"].format(n=counts["truncated"]))
    return notes


def _excel_a_json(ctx: ToolContext, inp) -> dict:
    o, t = ctx.options, _t(ctx)
    sheets, missing = sheet_rows(inp.path, o.hojas)

    def shape(rows: list[list]):
        rows = [[json_value(v) for v in row] for row in rows]
        if o.forma == "filas" or not rows:
            return rows
        while rows and all(v is None for v in rows[0]):
            rows.pop(0)  # la primera fila con datos da las claves
        if not rows:
            return []
        keys = keys_of(rows[0])
        return [dict(zip(keys, row)) for row in rows[1:]]

    data = {name: shape(list(rows)) for name, rows in sheets} if o.hojas == "todas" else shape(list(sheets[0][1]) if sheets else [])
    name = derived_name(inp.name, "", "json")
    dst = ctx.output(name)
    write_json(dst, data)
    return {"path": str(dst), "name": name, "note": t["formulas"].format(n=missing) if missing else None}


def _arreglar(ctx: ToolContext, inp) -> dict:
    o, t = ctx.options, _t(ctx)
    raw = _read(inp.path)
    text, codec = decode(raw, ENCODINGS.get(o.origen))
    # El «Ã±» solo se busca en lo que ya era UTF-8: en un archivo de Windows-1252 esas letras son lo que parecen.
    text, fixed = fix_mojibake(text) if codec in ("utf-8", "utf-8-sig") else (text, 0)
    notes = [t["detected"].format(enc=LABELS.get(codec, codec), sep=SEP_NAMES.get(sniff_separator(text), ","))]
    if fixed:
        notes.append(t["fixed"].format(n=fixed))
    elif codec in ("utf-8", "utf-8-sig"):
        notes.append(t["nothing"])
    data = (b"\xef\xbb\xbf" if o.salida == "utf-8-bom" else b"") + text.lstrip("﻿").encode("utf-8")
    name = derived_name(inp.name, "-utf8", "csv")
    dst = ctx.output(name)
    dst.write_bytes(data)
    return {"path": str(dst), "name": name, "note": " ".join(notes)}


def _csv_a_json(ctx: ToolContext, inp) -> dict:
    o, t = ctx.options, _t(ctx)
    rows, codec, sep = read_csv(ctx, inp.path, o.separador)
    decimal, clear = _decimal_of(rows[1:], sep)

    def typed(v: str):
        if not o.tipos:
            return v
        if v == "":
            return None
        if v.strip().lower() in ("true", "false"):
            return v.strip().lower() == "true"
        number = to_number(v, decimal, strict=not clear)
        return number if number is not None else v

    keys = keys_of(rows[0]) if rows else []

    def objects():
        for row in rows[1:]:
            names = keys + [f"columna_{i}" for i in range(len(keys) + 1, len(row) + 1)]  # filas más largas que el encabezado
            yield {k: typed(v) for k, v in zip(names, row + [""] * (len(names) - len(row)))}

    items = ([typed(v) for v in row] for row in rows) if o.forma == "filas" else objects()
    name = derived_name(inp.name, "", "json")
    dst = ctx.output(name)
    # Un objeto por línea dentro de la lista: se escribe a medida que se lee, con el tope de salida.
    write_capped(dst, _batched(_json_array(items)))
    return {"path": str(dst), "name": name, "note": t["detected"].format(enc=LABELS.get(codec, codec), sep=SEP_NAMES.get(sep, sep))}


def _json_array(items):
    yield "["
    for n, item in enumerate(items):
        yield ("," if n else "") + "\n  " + json.dumps(item, ensure_ascii=False, allow_nan=False)
    yield "\n]\n"


def _json_a_csv(ctx: ToolContext, inp) -> dict:
    o = ctx.options
    data, notes = load_json(ctx, inp.path)
    _check_size(data)
    records, more = records_of(ctx, data)
    notes += more
    if records and all(isinstance(r, list) for r in records):
        rows = ([guard_formula(_csv_cell(v)) if isinstance(v, str) else _csv_cell(v) for v in r] for r in records)
    else:
        flat = [flatten(r) for r in records]
        columns: dict[str, None] = {}
        for f in flat:
            for k in f:
                columns.setdefault(k, None)
        header = list(columns)
        # Cada registro con claves propias son filas × columnas celdas: se mira antes de escribir (D-218).
        if len(flat) * max(1, len(header)) > MAX_CELLS:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_too_big")
        rows = ([guard_formula(k) for k in header],
                *([guard_formula(v) if isinstance(v, str) else _csv_cell(v) for v in (f.get(k) for k in header)] for f in flat))
    name = derived_name(inp.name, "", "csv")
    dst = ctx.output(name)
    lossy = _write_csv(dst, rows, SEPARATOR[o.separador], o.codificacion, ctx)
    return {"path": str(dst), "name": name, "note": " ".join(notes + lossy) or None}


def _json_a_xml(ctx: ToolContext, inp) -> dict:
    o = ctx.options
    data, notes = load_json(ctx, inp.path)
    _check_size(data)
    name = derived_name(inp.name, "", "xml")
    dst = ctx.output(name)
    write_capped(dst, [to_xml(data, o.raiz, o.elemento)])
    return {"path": str(dst), "name": name, "note": " ".join(notes) or None}


def _xml_a_json(ctx: ToolContext, inp) -> dict:
    data = from_xml(_read(inp.path), ctx.options.tipos)
    name = derived_name(inp.name, "", "json")
    dst = ctx.output(name)
    write_json(dst, data)
    return {"path": str(dst), "name": name, "note": None}


def _yaml_a_json(ctx: ToolContext, inp) -> dict:
    data, notes = load_yaml(ctx, inp.path)
    name = derived_name(inp.name, "", "json")
    dst = ctx.output(name)
    write_json(dst, yaml_to_json_value(data))
    return {"path": str(dst), "name": name, "note": " ".join(notes) or None}


def _json_a_yaml(ctx: ToolContext, inp) -> dict:
    import yaml

    data, notes = load_json(ctx, inp.path)
    _check_size(data)
    base = yaml.CSafeDumper if hasattr(yaml, "CSafeDumper") else yaml.SafeDumper

    class Dumper(base):
        pass

    def represent_str(dumper, value: str):
        # Un texto que un lector de YAML 1.2 tomaría por número («1e3», «0x10», «.inf») va entre comillas.
        style = "'" if YAML12_NUMBER.fullmatch(value) else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)

    Dumper.add_representer(str, represent_str)
    try:
        text = yaml.dump(data, Dumper=Dumper, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000)
    except RecursionError as exc:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_too_deep") from exc
    name = derived_name(inp.name, "", "yaml")
    dst = ctx.output(name)
    write_capped(dst, [text])
    return {"path": str(dst), "name": name, "note": " ".join(notes) or None}


ONE_BY_ONE = {"excel-a-json": _excel_a_json, "arreglar-codificacion-csv": _arreglar, "csv-a-json": _csv_a_json,
              "json-a-csv": _json_a_csv, "json-a-xml": _json_a_xml, "xml-a-json": _xml_a_json,
              "yaml-a-json": _yaml_a_json, "json-a-yaml": _json_a_yaml}


def run(ctx: ToolContext) -> list[dict]:
    if ctx.tool == "csv-a-xlsx":
        return _csv_a_xlsx(ctx)
    outputs: list[dict] = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        if ctx.tool == "xlsx-a-csv":
            outputs += _xlsx_a_csv(ctx, inp)
        else:
            outputs.append(ONE_BY_ONE[ctx.tool](ctx, inp))
    return with_batch_zip(ctx, outputs, f"{ctx.tool}.zip")
