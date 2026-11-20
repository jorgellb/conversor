"""escribir-pdf (A.1, F6-O1, D-234): el HTML del editor (TipTap, en la página) a PDF con el Chromium de `gotenberg`.

El editor envía el cuerpo del documento (HTML con las imágenes en `data:` y las fórmulas en MathML) y, si se elige,
un PDF de membrete. Aquí se envuelve en una página con su hoja de estilos (las fuentes de la imagen de Gotenberg) y:
- encabezado y pie con los números de página (`header.html` y `footer.html` de Gotenberg);
- marca de agua y borde de página (elementos fijos, que Chromium repite en cada página);
- índice con los números de página reales en dos pasadas: se genera el PDF, se lee la página de cada título en los
  destinos con nombre que crea Chromium para los enlaces del índice (`/Root/Dests`: el id del título) y se vuelve a
  generar con los números; el esquema de marcadores sale de los títulos (`generateDocumentOutline`);
- PDF etiquetado (`generateTaggedPdf`) y propiedades del documento (título, autor, asunto y palabras clave);
- membrete como fondo, como en superponer-pdf.
Los campos rellenables los pone la página con pdf-lib tras la conversión, sobre los enlaces `https://campo.invalid/…`.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import pikepdf

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext
from tools.office import gotenberg
from tools.office.office_a_pdf import select_pages

MAX_HTML = 25 * 1024 * 1024
FONTS = {"sans": '"Noto Sans", "Liberation Sans", sans-serif', "serif": '"Noto Serif", "Liberation Serif", serif',
         "mono": '"Noto Sans Mono", "Liberation Mono", monospace'}
# La casilla del número de cada entrada del índice. Expresión sin anticipaciones (D-238: con ellas, un HTML con muchos
# «<span » tardaba un tiempo cuadrático); los atributos se miran después, en el texto capturado.
SPAN = re.compile(r"(<span\b([^<>]{0,2000})>)([^<]{0,40})(</span>)")
TOC_ID = re.compile(r'\bdata-toc="([A-Za-z][\w-]{0,80})"')
TOC_CLASS = re.compile(r'\bclass="toc-page"')
# Lo que imprime Chromium no ejecuta nada ni carga nada de fuera del documento (ni file:///tmp de otros trabajos): solo
# imágenes y fuentes en data: y estilos en la página. Se pone la primera en <head>: otra en el cuerpo no la relaja (D-238).
PAGE_CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:"
BODY_BLOCKED = re.compile(r"<\s*/?\s*(?:meta|base|link|iframe|frame|frameset|object|embed|script|portal|noscript)\b[^>]*>", re.I)
SURROGATES = re.compile(r"[\ud800-\udfff]")


def toc_entries(body: str) -> list[str]:
    return [m.group(1) for span in SPAN.finditer(body) if TOC_CLASS.search(span.group(2)) for m in [TOC_ID.search(span.group(2))] if m]


def fill_toc(body: str, number) -> str:
    def sub(span: re.Match) -> str:
        attrs = span.group(2)
        m = TOC_ID.search(attrs)
        if not m or not TOC_CLASS.search(attrs):
            return span.group(0)
        return f"{span.group(1)}{number(m.group(1))}{span.group(4)}"
    return SPAN.sub(sub, body)


def clean(text: str) -> str:
    """Sin sustitutos sueltos (llegan en JSON y no se pueden codificar en UTF-8)."""
    return SURROGATES.sub("", text or "")

BASE_CSS = """
html{font-size:11pt}
body{margin:0;font-family:%(font)s;line-height:1.45;color:#111827;font-size:11pt;-webkit-print-color-adjust:exact;print-color-adjust:exact}
h1{font-size:22pt;margin:0 0 10pt}h2{font-size:16pt;margin:14pt 0 8pt}h3{font-size:13pt;margin:12pt 0 6pt}h4,h5,h6{font-size:11pt;margin:10pt 0 4pt}
h1,h2,h3,h4,h5,h6{break-after:avoid;line-height:1.2}
p{margin:0 0 6pt}img{max-width:100%%;height:auto}
table{border-collapse:collapse;width:100%%;margin:6pt 0;break-inside:auto}tr{break-inside:avoid}
th,td{border:1px solid #9ca3af;padding:4pt 6pt;vertical-align:top;text-align:left}th{background:#f3f4f6}
blockquote{margin:6pt 0;padding:2pt 10pt;border-left:3pt solid #d1d5db;color:#374151}
pre{background:#f3f4f6;padding:8pt;border-radius:3pt;white-space:pre-wrap;font-family:%(mono)s;font-size:9.5pt}
code{font-family:%(mono)s;font-size:9.5pt}
ul[data-type="taskList"]{list-style:none;padding-left:4pt}ul[data-type="taskList"] li{display:flex;gap:6pt}
ul[data-type="taskList"] li>label{flex:none}ul[data-type="taskList"] li>div{flex:1}
mark{padding:0 1pt}a{color:#1d4ed8}
.salto-pagina{break-after:page;height:0;border:0;margin:0}
.columnas{column-gap:8mm;margin:6pt 0}.columnas[data-columnas="2"]{column-count:2}.columnas[data-columnas="3"]{column-count:3}
nav.indice{margin:6pt 0 12pt}nav.indice h2{margin-top:0}nav.indice ol{list-style:none;padding:0;margin:0}
nav.indice li{display:flex;gap:4pt;margin:2pt 0}nav.indice li a{color:inherit;text-decoration:none}
nav.indice li .toc-dots{flex:1;border-bottom:1px dotted #9ca3af;margin-bottom:3pt}
nav.indice li .toc-page{min-width:3ch;text-align:right;font-variant-numeric:tabular-nums}
nav.indice li[data-nivel="2"]{padding-left:12pt}nav.indice li[data-nivel="3"]{padding-left:24pt}
.notas{margin-top:14pt;border-top:1px solid #d1d5db;padding-top:6pt;font-size:9.5pt}
.notas ol{padding-left:16pt;margin:0}sup.nota{font-size:7pt}
a.campo{display:inline-block;vertical-align:bottom;border-bottom:1px solid #6b7280;text-decoration:none;color:transparent;height:1.2em}
a.campo[data-tipo="casilla"]{border:1px solid #6b7280;width:1em!important}
math[display="block"]{display:block;margin:6pt 0}
.marca-agua{position:fixed;left:0;right:0;top:40%%;text-align:center;font-size:64pt;font-weight:bold;color:rgba(107,114,128,.16);
  transform:rotate(-35deg);z-index:-1;pointer-events:none;white-space:nowrap}
.borde-pagina{position:fixed;inset:0;pointer-events:none;z-index:-1}
.borde-pagina.fino{border:0.6pt solid #374151}.borde-pagina.doble{border:3pt double #374151}
"""


def _band(text: str, numbers: str, where: str, margin_mm: float = 25, size_pt: float = 9) -> bytes:
    """header.html o footer.html de Gotenberg: el texto propio y, si se piden, los números de página."""
    number = {"n": '<span class="pageNumber"></span>',
              "n_de_total": '<span class="pageNumber"></span> / <span class="totalPages"></span>'}.get(numbers, "")
    left = html.escape(clean(text))
    # Con los mismos márgenes laterales que el texto, para que el encabezado y el pie queden alineados con él.
    style = (f"html,body{{margin:0;padding:0}}body{{font-family:{FONTS['sans']};font-size:{size_pt}pt;color:#4b5563;"
             f"width:100%;padding:0 {margin_mm:g}mm;box-sizing:border-box;display:flex;justify-content:space-between;align-items:center}}")
    if where == "top":
        style += "body{padding-top:8mm}"
    else:
        style += "body{padding-bottom:8mm}"
    return (f'<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="{PAGE_CSP}">'
            f'<style>{style}</style></head><body>'
            f"<span>{left}</span><span>{number}</span></body></html>").encode("utf-8")


def page_html(body: str, o, toc_numbers: dict[str, int] | None = None, placeholder: bool = False) -> bytes:
    font = FONTS.get(o.fuente, FONTS["serif"])
    css = BASE_CSS % {"font": font, "mono": FONTS["mono"]}
    extra = ""
    if o.marca_agua.strip():
        extra += f'<div class="marca-agua" aria-hidden="true">{html.escape(clean(o.marca_agua.strip()))}</div>'
    if o.borde != "ninguno":
        extra += f'<div class="borde-pagina {o.borde}" aria-hidden="true"></div>'
        # El borde va en el límite del área de texto (Chromium recorta lo que sale de ella): el texto se separa de él.
        # box-decoration-break: el relleno se repite en cada página, no solo en la primera.
        css += "body{padding:2mm 4mm;box-decoration-break:clone;-webkit-box-decoration-break:clone}"
    if placeholder:
        # Primera pasada: «0000» reserva el sitio del número (hasta 9999 páginas) para que el índice ocupe lo mismo en las dos.
        body = fill_toc(body, lambda _key: "0000")
    elif toc_numbers is not None:
        body = fill_toc(body, lambda key: str(toc_numbers.get(key, "")))
    lang = "en" if o.idioma == "en" else "es"
    title = html.escape(clean(o.titulo.strip()) or "Documento")
    body = clean(body)
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="{PAGE_CSP}">'
            f'<title>{title}</title><style>{css}</style></head>'
            f"<body>{extra}{body}</body></html>").encode("utf-8")


def destination_pages(pdf_path: Path) -> dict[str, int]:
    """Página (desde 1) de cada destino con nombre: Chromium crea uno por cada id al que apunta un enlace interno."""
    out: dict[str, int] = {}
    with pikepdf.open(pdf_path) as pdf:
        pages = {p.objgen: i + 1 for i, p in enumerate(pdf.pages)}

        def put(name, dest) -> None:
            if isinstance(dest, pikepdf.Dictionary) and "/D" in dest:
                dest = dest.D
            if isinstance(dest, pikepdf.Array) and len(dest) and dest[0].objgen in pages:
                out[str(name).lstrip("/")] = pages[dest[0].objgen]

        dests = pdf.Root.get("/Dests")
        if isinstance(dests, pikepdf.Dictionary):
            for key in dests.keys():
                put(key, dests[key])
        names = pdf.Root.get("/Names")
        if isinstance(names, pikepdf.Dictionary) and "/Dests" in names:
            for key, value in pikepdf.NameTree(names.Dests).items():
                put(key, value)
    return out


def _fields(o, header: bool, footer: bool) -> dict[str, str]:
    fields = gotenberg.page_fields(o.papel, o.orientacion, o.margenes_mm, True)
    fields.update({"generateDocumentOutline": "true", "generateTaggedPdf": "true"})
    if header or footer:
        # Con encabezado o pie, el margen de esa banda no puede ser menor que lo que ocupa.
        top = max(o.margenes_mm, 18) if header else o.margenes_mm
        bottom = max(o.margenes_mm, 18) if footer else o.margenes_mm
        fields["marginTop"], fields["marginBottom"] = f"{top:g}mm", f"{bottom:g}mm"
    return fields


def _convert(ctx: ToolContext, page: bytes, o, dst: Path) -> None:
    header = bool(o.encabezado.strip()) or o.numeros_pagina == "encabezado"
    footer = bool(o.pie.strip()) or o.numeros_pagina == "pie"
    files = [("index.html", page, "text/html")]
    if header:
        files.append(("header.html", _band(o.encabezado, o.formato_numero if o.numeros_pagina == "encabezado" else "", "top", o.margenes_mm), "text/html"))
    if footer:
        files.append(("footer.html", _band(o.pie, o.formato_numero if o.numeros_pagina == "pie" else "", "bottom", o.margenes_mm), "text/html"))
    dst.write_bytes(gotenberg.chromium_html_files(ctx.settings.GOTENBERG_URL, files, _fields(o, header, footer)))


def _letterhead(ctx: ToolContext, pdf_path: Path, letterhead: Path, first_only: bool) -> None:
    from tools.pdf.common import open_pdf

    # Con open_pdf: un membrete cifrado o dañado da su error (contraseña, archivo dañado), no uno interno (D-238).
    with open_pdf(letterhead, None, 50) as over, pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        if not len(over.pages):
            raise ToolError(ErrorCode.CORRUPT_FILE, "El membrete no tiene páginas")
        form = pdf.copy_foreign(over.pages[0].as_form_xobject())
        second = pdf.copy_foreign(over.pages[1].as_form_xobject()) if len(over.pages) > 1 else form
        for i, page in enumerate(pdf.pages):
            if first_only and i:
                break
            # La primera página con la primera del membrete y el resto con la segunda, si la tiene (cartas).
            page.add_underlay(form if i == 0 else second, pikepdf.Rectangle(page.mediabox))
        pdf.save(pdf_path)


def _metadata(pdf_path: Path, o) -> None:
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            if clean(o.titulo).strip():
                meta["dc:title"] = clean(o.titulo).strip()
            if clean(o.autor).strip():
                meta["dc:creator"] = [clean(o.autor).strip()]
            if clean(o.asunto).strip():
                meta["dc:description"] = clean(o.asunto).strip()
            if clean(o.palabras_clave).strip():
                meta["pdf:Keywords"] = clean(o.palabras_clave).strip()
        info = pdf.docinfo
        for key, value in (("/Title", o.titulo), ("/Author", o.autor), ("/Subject", o.asunto), ("/Keywords", o.palabras_clave)):
            if clean(value).strip():
                info[key] = clean(value).strip()
        pdf.Root.Lang = pikepdf.String("en" if o.idioma == "en" else "es")
        if o.titulo.strip():
            pdf.Root.ViewerPreferences = pikepdf.Dictionary(DisplayDocTitle=True)
        pdf.save(pdf_path)


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    docs = [i for i in ctx.inputs if (i.ext or Path(i.name).suffix.lstrip(".")).lower() in ("html", "htm")]
    letterheads = [i for i in ctx.inputs if (i.ext or Path(i.name).suffix.lstrip(".")).lower() == "pdf"]
    if len(docs) != 1 or len(letterheads) > 1:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "escribir_entradas")
    src = docs[0]
    if src.path.stat().st_size > MAX_HTML:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Documento de más de 25 MB")
    body = src.path.read_text(encoding="utf-8", errors="replace")
    # Solo el cuerpo: si llega una página entera, lo de dentro de <body>, buscado sin expresiones que retrocedan (D-238).
    lower = body.lower()
    start = lower.find("<body")
    end = lower.rfind("</body>")
    if start >= 0 and end > start:
        close = body.find(">", start)
        if 0 <= close < end:
            body = body[close + 1:end]
    # Lo que el editor nunca produce y no puede ir en un cuerpo (D-246): metadatos, bases, hojas y marcos externos y
    # guiones. Quien llama a la API directamente se salta el saneado del navegador.
    body = BODY_BLOCKED.sub("", body)
    ctx.report(0.1, None)
    name = (re.sub(r"[^\w .,()-]+", "", clean(o.titulo).strip(), flags=re.UNICODE).strip(" .")[:80] or "documento") + ".pdf"
    dst = ctx.output(name)
    entries = toc_entries(body)
    has_toc = bool(entries)
    _convert(ctx, page_html(body, o, placeholder=has_toc), o, dst)
    # El límite de páginas del plan, ya tras la primera pasada: un documento demasiado largo no paga la segunda.
    select_pages(dst, "todas", ctx.plan.pdf_pages)
    note = None
    if has_toc:
        # Segunda pasada: cada entrada del índice (data-toc = su orden) con la página de su título en el esquema.
        ctx.report(0.5, None)
        numbers = destination_pages(dst)
        _convert(ctx, page_html(body, o, numbers), o, dst)
        if any(key not in numbers for key in entries):
            note = {"es": "Algunos títulos del índice no tienen número: revisa que no haya títulos vacíos.",
                    "en": "Some table of contents entries have no number: check there are no empty headings."}.get(ctx.locale)
    ctx.report(0.8, None)
    select_pages(dst, "todas", ctx.plan.pdf_pages)
    if letterheads:
        _letterhead(ctx, dst, letterheads[0].path, o.membrete == "primera")
    _metadata(dst, o)
    return [{"path": str(dst), "name": name, "note": note}]
