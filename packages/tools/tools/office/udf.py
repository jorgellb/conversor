"""udf-a-pdf (7.23, F6-M, D-229): documentos UDF del editor de UYAP (Turquía), apagada por defecto.

No hay especificación pública. Lo que se sabe del formato (y lo que leen los conversores libres que circulan): un ZIP
con `content.xml`, cuya etiqueta `<template>` guarda el texto entero en `<content>` (CDATA) y, en `<elements>`, los
párrafos, tablas e imágenes como trozos de ese texto (`startOffset` y `length`) con su formato (negrita, cursiva,
subrayado, tamaño, fuente, alineación). Aquí se reconstruye como HTML y lo imprime el Chromium de `gotenberg` sin red.
El XML se lee con defusedxml.
"""
from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.zipguard import check_zip
from tools.base import ToolContext, derived_name
from tools.office import gotenberg
from tools.pdf.common import with_batch_zip

ALIGN = {"0": "left", "1": "center", "2": "right", "3": "justify"}
MAX_CONTENT = 30 * 1024 * 1024
MAX_HTML = 40 * 1024 * 1024  # lo que puede salir en total: un trozo del texto se puede citar muchas veces (D-233)
MAX_DEPTH = 20  # tablas dentro de tablas
MAX_IMAGE = 10 * 1024 * 1024
BASE64 = re.compile(r"[A-Za-z0-9+/]+={0,2}")


class _Budget:
    def __init__(self) -> None:
        self.left = MAX_HTML

    def take(self, piece: str) -> str:
        self.left -= len(piece)
        if self.left < 0:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "El documento UDF produce demasiado contenido")
        return piece


def _safe(raw: bytes):
    import defusedxml.ElementTree as DET
    from defusedxml import DefusedXmlException

    try:
        return DET.fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (DefusedXmlException, ValueError) as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities") from exc
    except SyntaxError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "UDF no válido") from exc


def _int(value, default=0) -> int:
    try:
        return max(0, min(10**9, int(float(value))))
    except (TypeError, ValueError, OverflowError):
        return default


def _span(el, text: str, budget: _Budget) -> str:
    start, length = _int(el.get("startOffset")), _int(el.get("length"))
    piece = html.escape(budget.take(text[start:start + length])).replace("\n", "<br>").replace("\t", "&emsp;")
    if not piece:
        return ""
    style = []
    if el.get("size"):
        style.append(f"font-size:{max(4, min(_int(el.get('size'), 12), 200))}pt")
    if el.get("family"):
        style.append("font-family:" + html.escape(re.sub(r"[^\w -]", "", el.get("family")), quote=True))
    if el.get("bold") == "true":
        style.append("font-weight:bold")
    if el.get("italic") == "true":
        style.append("font-style:italic")
    if el.get("underline") == "true":
        style.append("text-decoration:underline")
    return f'<span style="{";".join(style)}">{piece}</span>' if style else piece


def _paragraph(el, text: str, budget: _Budget) -> str:
    align = ALIGN.get(el.get("Alignment", "0"), "left")
    indent = min(_int(el.get("LeftIndent")), 500)
    inner = "".join(_span(c, text, budget) for c in el if c.tag in ("content", "field", "space"))
    for img in el.iter("image"):
        data = "".join((img.get("imageData") or "").split())
        # El valor entero tiene que ser Base64: si no, cerraría el atributo y metería marcas en la página.
        if data and len(data) <= MAX_IMAGE * 4 // 3 and BASE64.fullmatch(data):
            inner += budget.take(f'<img src="data:image/png;base64,{data}" style="max-width:100%">')
    return f'<p style="text-align:{align};margin-left:{indent}pt">{inner or "&nbsp;"}</p>'


def _block(el, text: str, budget: _Budget, depth: int = 0) -> str:
    if depth > MAX_DEPTH:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Demasiadas tablas una dentro de otra")
    if el.tag == "paragraph":
        return _paragraph(el, text, budget)
    if el.tag == "table":
        rows = []
        for row in el.findall("row"):  # solo las filas de esta tabla: las de las tablas anidadas van con su celda
            cells = "".join("<td>" + "".join(_block(c, text, budget, depth + 1) for c in cell) + "</td>" for cell in row.findall("cell"))
            rows.append(budget.take(f"<tr>{cells}</tr>"))
        return f"<table>{''.join(rows)}</table>"
    return ""


def to_html(raw_zip: Path) -> bytes:
    check_zip(raw_zip, max_uncompressed=200 * 1024 * 1024)
    try:
        with zipfile.ZipFile(raw_zip) as zf:
            info = zf.getinfo("content.xml")
            if info.file_size > MAX_CONTENT:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "content.xml de más de 30 MB")
            root = _safe(zf.read(info))
    except KeyError as exc:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "udf_no_content") from exc
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "udf") from exc
    if root.tag != "template":
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "udf_no_content")
    text = root.findtext("content") or ""
    elements = root.find("elements")
    budget = _Budget()
    body = "".join(_block(el, text, budget) for el in (elements if elements is not None else []))
    if not body.strip():
        body = "".join(f"<p>{html.escape(line) or '&nbsp;'}</p>" for line in text.split("\n"))
    css = (f"body{{font-family:'Times New Roman',{gotenberg.SANS};font-size:12pt;line-height:1.35}}p{{margin:0 0 4pt}}"
           "table{border-collapse:collapse;width:100%;margin:6pt 0}td{border:1px solid #444;padding:3pt;vertical-align:top}")
    return (f"<!doctype html><html><head><meta charset=\"utf-8\"><title>UDF</title><style>{css}</style></head>"
            f"<body>{body}</body></html>").encode("utf-8")


def run(ctx: ToolContext) -> list[dict]:
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        page = to_html(inp.path)
        data = gotenberg.chromium_html_files(ctx.settings.GOTENBERG_URL, [("index.html", page, "text/html")],
                                             gotenberg.page_fields("A4", "vertical", 20, True, False, "print"))
        name = derived_name(inp.name, "", "pdf")
        dst = ctx.output(name)
        dst.write_bytes(data)
        outputs.append({"path": str(dst), "name": name, "note": None})
    return with_batch_zip(ctx, outputs, "udf-pdf.zip")
