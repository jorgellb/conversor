"""Texto de una página PDF colocado según su posición (A.9, D-261), para los modos «fiel al diseño» de pdf-a-txt (columnas
con espacios, como en el papel) y de pdf-a-excel y pdf-a-ods (una hoja por página, cada trozo de texto en la celda de su
fila y su columna).

Los caracteres salen de PDFium con su caja. Se juntan en líneas por su altura (media altura de letra de tolerancia) y, dentro
de cada línea, en trozos separados por huecos de más de 1,5 veces el ancho medio de letra. Las columnas de la hoja son los
comienzos de trozo que se repiten en la página (agrupados a dos anchos de letra).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field


@dataclass
class Segment:
    x0: float
    x1: float
    text: str


@dataclass
class Line:
    top: float
    bottom: float
    segments: list[Segment] = field(default_factory=list)


@dataclass
class Layout:
    lines: list[Line]
    char_width: float
    line_height: float
    left: float


def page_layout(page) -> Layout:
    """Líneas de arriba abajo con sus trozos de izquierda a derecha (coordenadas de PDF: y hacia arriba)."""
    textpage = page.get_textpage()
    try:
        chars = []
        for i in range(textpage.count_chars()):
            ch = textpage.get_text_range(i, 1)
            if not ch or ch in "\r\n\x02￾":
                continue
            left, bottom, right, top = textpage.get_charbox(i, loose=True)  # cajas por el avance, no por el dibujo de la letra
            if right <= left and ch != " ":
                continue
            chars.append((left, bottom, right, top, ch))
    finally:
        textpage.close()
    visible = [c for c in chars if c[4].strip()]
    if not visible:
        return Layout([], 6.0, 12.0, 0.0)
    char_width = statistics.median(c[2] - c[0] for c in visible) or 5.0
    height = statistics.median(c[3] - c[1] for c in visible) or 10.0
    # Líneas por el centro vertical de cada letra (de arriba abajo).
    lines: list[tuple[float, list]] = []
    for c in sorted(visible + [c for c in chars if not c[4].strip()], key=lambda c: (-(c[1] + c[3]) / 2, c[0])):
        mid = (c[1] + c[3]) / 2
        if not c[4].strip():
            # Un espacio va con la línea que tiene a su altura, si la hay; si no, no cuenta.
            for row_mid, row in lines:
                if abs(row_mid - mid) <= height / 2:
                    row.append(c)
                    break
            continue
        for k, (row_mid, row) in enumerate(lines):
            if abs(row_mid - mid) <= height / 2:
                row.append(c)
                break
        else:
            lines.append((mid, [c]))
    out: list[Line] = []
    for _mid, row in sorted(lines, key=lambda r: -r[0]):
        row = sorted((c for c in row), key=lambda c: c[0])
        line = Line(top=max(c[3] for c in row), bottom=min(c[1] for c in row))
        current: Segment | None = None
        last_right = None
        for left, _bottom, right, _top, ch in row:
            if not ch.strip():
                continue
            gap = left - last_right if last_right is not None else 0.0
            if current is None or gap > 1.5 * char_width:
                current = Segment(left, right, ch)
                line.segments.append(current)
            else:
                current.text += (" " if gap > 0.25 * char_width else "") + ch
                current.x1 = right
            last_right = right
        if line.segments:
            out.append(line)
    left = min(s.x0 for line in out for s in line.segments) if out else 0.0
    return Layout(out, char_width, height * 1.25, left)


def layout_text(layout: Layout) -> str:
    """Las líneas con los trozos en su columna (espacios según la posición) y líneas en blanco donde hay huecos."""
    rows: list[str] = []
    previous_bottom = None
    for line in layout.lines:
        if previous_bottom is not None:
            blank = int((previous_bottom - line.top) / layout.line_height)
            rows.extend([""] * max(0, min(blank, 3)))
        text = ""
        for seg in line.segments:
            col = int(round((seg.x0 - layout.left) / layout.char_width))
            if len(text) >= col:
                text += (" " if text else "") + seg.text
            else:
                text += " " * (col - len(text)) + seg.text
        rows.append(text.rstrip())
        previous_bottom = line.bottom
    return "\n".join(rows)


def layout_grid(layout: Layout) -> list[list[str]]:
    """Filas y columnas de la página: cada trozo en la celda de su línea y de la columna en la que empieza."""
    starts = sorted(seg.x0 for line in layout.lines for seg in line.segments)
    columns: list[float] = []
    for x in starts:
        if not columns or x - columns[-1] > 2 * layout.char_width:
            columns.append(x)
    grid: list[list[str]] = []
    for line in layout.lines:
        row = [""] * len(columns)
        for seg in line.segments:
            k = max(i for i, c in enumerate(columns) if c <= seg.x0 + 2 * layout.char_width)
            row[k] = f"{row[k]} {seg.text}".strip()
        while row and not row[-1]:
            row.pop()
        grid.append(row)
    return grid
