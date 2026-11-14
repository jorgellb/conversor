"""imagen-a-excel (7.6): tablas de una foto o una captura a Excel (XLSX) o CSV.

1. En `workerconvert`, Docling reconoce las tablas de la imagen con el OCR de Tesseract (6.4: Docling solo ahí). Si
   encuentra alguna, el trabajo termina ahí y la petición de IA reservada al encolar se devuelve sin usar (D-160).
2. Si no hay ninguna tabla y está activado «usar IA», Tesseract lee el texto conservando las columnas, se guarda en
   `document_texts` y el trabajo pasa a `workerai`: una petición con JSON y esquema (6.5) reconstruye las tablas. El
   resultado queda en la caché del propietario: pedirlo en otro formato no gasta peticiones.
3. Sin IA y sin tablas, el XLSX lleva el texto línea a línea (como pdf-a-excel) y el CSV falla con un aviso claro.
"""
from __future__ import annotations

from pathlib import Path

from core.ai.catalog import Needs
from core.ai.text import estimate_tokens
from core.errors import ErrorCode, ToolError
from tools.ai import comun, hojas, imagen_texto
from tools.base import ToolContext, derived_name, zip_files

TOOL = "imagen-a-excel"
MAX_PAGES = 10  # páginas de un TIFF: cada una es una pasada de Docling
MAX_TEXT = 24000  # caracteres de OCR que se mandan al modelo (una imagen no suele pasar de unos pocos miles)
TEXTS = {
    "es": {"table": "Tabla {n}", "tables": "Tablas", "text": "Texto", "suffix": "-tablas", "found": "Tablas reconocidas sin IA: {n}.",
           "no_tables": "No se ha encontrado ninguna tabla: van las líneas de texto de la imagen, una por fila.",
           "ocr": "Buscando la tabla con IA…", "ai": "La tabla no se reconocía y se ha reconstruido con IA."},
    "en": {"table": "Table {n}", "tables": "Tables", "text": "Text", "suffix": "-tables", "found": "Tables recognised without AI: {n}.",
           "no_tables": "No table was found: the image's lines of text are listed, one per row.",
           "ocr": "Looking for the table with AI…", "ai": "The table was not recognised and has been rebuilt with AI."},
}
SCHEMA = {
    "type": "object",
    "properties": {"tablas": {"type": "array", "items": {
        "type": "object",
        "properties": {"titulo": {"type": "string"}, "columnas": {"type": "array", "items": {"type": "string"}},
                       "filas": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}}},
        "required": ["titulo", "columnas", "filas"], "additionalProperties": False}}},
    "required": ["tablas"], "additionalProperties": False,
}


def _texts(ctx: ToolContext) -> dict[str, str]:
    return TEXTS.get(ctx.locale, TEXTS["es"])


def clean(data) -> list[dict]:
    """Tablas del modelo con todas las filas del mismo ancho. Una lista vacía vale (la imagen no tiene tablas); si más
    de la mitad de las tablas no sirven, se pide una reparación (6.5)."""
    items = data.get("tablas") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("falta «tablas»")
    out = []
    for t in items:
        if not isinstance(t, dict) or not isinstance(t.get("filas"), list):
            continue
        header = [" ".join(str(c).split()) for c in t.get("columnas") or [] if isinstance(c, (str, int, float))]
        rows = [[" ".join(str(c).split()) for c in row] for row in t["filas"] if isinstance(row, list)]
        rows = [r for r in rows if any(r)]
        width = max([len(header), *(len(r) for r in rows)], default=0)
        if width < 2 or not rows:
            continue
        header = (header + [""] * width)[:width] if any(header) else None
        out.append({"titulo": " ".join(str(t.get("titulo", "")).split())[:80], "header": header,
                    "rows": [(r + [""] * width)[:width] for r in rows]})
    if items and len(out) * 2 < len(items):
        raise ValueError("demasiadas tablas no válidas")
    return out


def _deliver(ctx: ToolContext, tables: list[dict], lines: list[str], note: str) -> list[dict]:
    """XLSX (una hoja por tabla o todas en una) o CSV (uno por tabla; varios, en un ZIP)."""
    o = ctx.options
    t = _texts(ctx)
    inp = ctx.inputs[0]
    if not tables and o.formato == "csv":
        raise ToolError(ErrorCode.NO_TABLES, "image_no_tables")
    if o.formato == "xlsx":
        if not tables:
            sheets = [hojas.Sheet(t["text"], [[line] for line in lines], header=False)]
            note = " ".join(x for x in (t["no_tables"], note) if x)
        elif o.hojas == "todas_en_una":
            rows: list[list] = []
            for k, table in enumerate(tables, start=1):
                rows += [[table["titulo"] or t["table"].format(n=k)], *([table["header"]] if table["header"] else []),
                         *table["rows"], []]
            sheets = [hojas.Sheet(t["tables"], rows[:-1], header=False)]
        else:
            sheets = [hojas.Sheet(table["titulo"] or t["table"].format(n=k), ([table["header"]] if table["header"] else [])
                                  + table["rows"], header=bool(table["header"])) for k, table in enumerate(tables, start=1)]
        name = derived_name(inp.name, "", "xlsx")
        dst = ctx.output(name)
        hojas.write_xlsx(dst, sheets, ctx.locale, o.numeros)
        return [{"path": str(dst), "name": name, "note": note or None}]
    stem = Path(inp.name).stem or "imagen"
    files = []
    for k, table in enumerate(tables, start=1):
        path = ctx.work / f"tabla-{k}.csv"
        path.write_bytes(hojas.csv_bytes(([table["header"]] if table["header"] else []) + table["rows"], o.delimitador, ctx.locale))
        files.append((path, f"{stem}-tabla-{k}.csv"))
    if len(files) == 1:
        name = files[0][1]
        dst = ctx.output(name)
        dst.write_bytes(files[0][0].read_bytes())
    else:
        name = f"{stem}{t['suffix']}-csv.zip"
        dst = ctx.output(name)
        zip_files(files, dst)
    return [{"path": str(dst), "name": name, "note": note or None}]


def _docling_tables(ctx: ToolContext, pages: list[Path], languages: list[str]) -> list[dict]:
    from docling_core.types.doc import TableItem

    from tools.convert.docling_util import convert_image, table_data

    tables = []
    for k, page in enumerate(pages):
        ctx.report(0.1 + 0.7 * k / len(pages), None)
        doc = convert_image(page, languages)
        for item, _ in doc.iterate_items():
            if not isinstance(item, TableItem):
                continue
            header, rows = table_data(item, doc)
            width = max([len(header or []), *(len(r) for r in rows)], default=0)
            if width >= 2 and len(rows) + (1 if header else 0) >= 2:
                tables.append({"titulo": "", "header": header, "rows": rows})
    return tables


def _convert_stage(ctx: ToolContext) -> list[dict]:
    from tools.ocr.imagen import check_languages, frames, straighten, tesseract_text

    o = ctx.options
    t = _texts(ctx)
    inp = ctx.inputs[0]
    languages = check_languages(ctx, o.idiomas)
    # Enderezadas antes de buscar tablas: Docling no reconoce una tabla torcida unos grados.
    pages = [straighten(ctx, page, rotate=False, deskew=True)[0] for page in frames(ctx, inp, 0, max_frames=MAX_PAGES)]
    tables = _docling_tables(ctx, pages, languages)
    if tables:
        return _deliver(ctx, tables, [], t["found"].format(n=len(tables)) if o.usar_ia else "")
    text = "\n\n".join(tesseract_text(ctx, p, languages) for p in pages).strip()
    if not imagen_texto.meaningful(text):
        raise ToolError(ErrorCode.NO_TABLES, "image_no_tables")
    if not o.usar_ia:
        return _deliver(ctx, [], [line.strip() for line in text.splitlines() if line.strip()], "")
    imagen_texto.save(ctx, inp, TOOL, languages, text)
    ctx.handoff("ai", "ai", t["ocr"])
    return []  # handoff lanza siempre


def make(ctx: ToolContext, text: str) -> dict:
    body = text[:MAX_TEXT]
    out = min(comun.MAX_OUTPUT, 2 * estimate_tokens(body) + 400)
    ctx.ai.budget.ensure(1)
    system = ("Reconstruyes tablas a partir del texto que un OCR ha leído de una imagen; los espacios separan las "
              f"columnas y cada línea suele ser una fila. {comun.GUARD} Copia cada celda tal cual (también los números "
              "con su formato) y corrige solo errores evidentes del OCR. Pon la cabecera en `columnas` si la hay y cada "
              "fila en `filas`, todas con el mismo número de celdas. Si no hay ninguna tabla, devuelve `tablas` vacía.")
    data, _ = ctx.ai.complete_json(
        [{"role": "system", "content": system}, {"role": "user", "content": f"Texto de la imagen:\n<<<\n{body}\n>>>"}],
        needs=Needs(context=estimate_tokens(body) + out + 900, output=min(out, 1000)), max_tokens=out, schema=SCHEMA,
        check=clean)
    return {"tablas": data, "model": (ctx.ai.models_used or [""])[-1]}


def _ai_stage(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    t = _texts(ctx)
    inp = ctx.inputs[0]
    text = imagen_texto.load(ctx, inp, TOOL, list(o.idiomas))
    if text is None:
        raise ToolError(ErrorCode.INTERNAL, "texto de la imagen no encontrado")
    result, hit = comun.with_cache(ctx, TOOL, {"idiomas": list(o.idiomas)}, lambda: make(ctx, text))
    made = comun.texts(ctx)["made"].format(model=result.get("model") or "IA")
    note = " ".join((t["ai"], comun.note(ctx, hit), made))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return _deliver(ctx, result["tablas"], lines, note)


def run(ctx: ToolContext) -> list[dict]:
    return _ai_stage(ctx) if ctx.stage == "ai" else _convert_stage(ctx)
