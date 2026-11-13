"""pdf-a-csv y pdf-a-json (A.9): tablas con Docling en `workerconvert`.

CSV: un archivo por tabla, con el separador y la codificación elegidos. JSON: las tablas (página, cabecera y filas) o el
documento entero en el formato de Docling. Las claves del JSON van en inglés, como es habitual en datos (D-69).
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name, zip_files
from tools.convert.docling_util import convert, page_of, subset_pdf, table_data
from tools.pdf.common import with_batch_zip

DELIMITERS = {"coma": ",", "punto_y_coma": ";", "tabulador": "\t"}


def _tables(ctx: ToolContext, src: Path):
    from docling_core.types.doc import TableItem

    o = ctx.options
    doc = convert(src, o.ocr_si_no_hay_texto, getattr(o, "idiomas", None), pictures=False)
    return doc, [item for item, _ in doc.iterate_items() if isinstance(item, TableItem)]


def run_csv(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        src, pages = subset_pdf(ctx, inp.path, o.paginas, n)
        doc, tables = _tables(ctx, src)
        if not tables:
            raise ToolError(ErrorCode.NO_TABLES, inp.name)
        stem = Path(inp.name).stem or "documento"
        files = []
        for k, table in enumerate(tables, start=1):
            header, rows = table_data(table, doc)
            page = page_of(table)
            original = pages[page - 1] if page and page <= len(pages) else page
            buf = io.StringIO()
            writer = csv.writer(buf, delimiter=DELIMITERS[o.delimitador], lineterminator="\r\n")
            writer.writerows(([header] if header else []) + rows)
            path = ctx.work / f"{stem}-tabla-{k}.csv"
            path.write_bytes(buf.getvalue().encode(o.codificacion))
            files.append((path, f"{stem}-tabla-{k}-p{original}.csv"))
        if len(files) == 1:
            dst = ctx.output(files[0][1])
            dst.write_bytes(files[0][0].read_bytes())
            outputs.append({"path": str(dst), "name": files[0][1]})
        else:
            name = f"{stem}-tablas-csv.zip"
            dst = ctx.output(name)
            zip_files(files, dst)
            outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "pdf-csv.zip")


def run_json(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        src, pages = subset_pdf(ctx, inp.path, o.paginas, n)
        if o.contenido == "documento":
            doc = convert(src, o.ocr_si_no_hay_texto, getattr(o, "idiomas", None), pictures=False)
            data = doc.export_to_dict()
        else:
            doc, tables = _tables(ctx, src)
            items = []
            for k, table in enumerate(tables, start=1):
                header, rows = table_data(table, doc)
                page = page_of(table)
                items.append({"number": k, "page": pages[page - 1] if page and page <= len(pages) else page,
                              "header": header, "rows": rows})
            data = {"source": inp.name, "tables": items}
        name = derived_name(inp.name, "", "json")
        dst = ctx.output(name)
        dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "pdf-json.zip")
