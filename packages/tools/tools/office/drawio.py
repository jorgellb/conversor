"""drawio-a-pdf y drawio-a-png (7.13, F6-K, D-227): el visor oficial de draw.io en el Chromium de Gotenberg.

En lugar de draw.io de escritorio (Electron con Xvfb, más de 400 MB en la imagen), el diagrama se dibuja con el mismo
motor que usa draw.io (`viewer-static.min.js` de jgraph/drawio, Apache-2.0, fijado por versión y SHA-256 en
infra/drawio/fetch.sh) dentro del Chromium de `gotenberg`, que no tiene red: las formas y las imágenes de fuera no se
cargan. El XML se lee antes con defusedxml para contar las páginas y medir cada una (diagramas comprimidos incluidos).
"""
from __future__ import annotations

import base64
import json
import math
import re
import urllib.parse
import zlib
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.office import gotenberg
from tools.pdf.common import with_batch_zip

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 100
MAX_PNG_SIDE = 8000
MAX_INFLATED = 50 * 1024 * 1024  # entre todas las páginas comprimidas (D-230)
MAX_CELLS = 100_000
BORDER = 10
MM_PX = 96 / 25.4

WAIT = {"waitForExpression": "window.ready === true", "failOnConsoleExceptions": "true"}
NOTES = {
    "es": {"pages": "{n} página(s) del diagrama.", "external": "Las imágenes o formas que el diagrama carga de internet no se incluyen."},
    "en": {"pages": "{n} diagram page(s).", "external": "Images or shapes the diagram loads from the internet are not included."},
}


def _safe(raw: bytes):
    import defusedxml.ElementTree as DET
    from defusedxml import DefusedXmlException

    try:
        return DET.fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (DefusedXmlException, ValueError) as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities") from exc
    except SyntaxError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "draw.io no válido") from exc


class _Budget:
    def __init__(self) -> None:
        self.inflated = 0
        self.cells = 0
        self.external = False


def _model(diagram, budget: _Budget):
    """El mxGraphModel de una página: hijo directo o texto comprimido (Base64 de deflate sin cabecera y URL-encode).

    El Base64 se comprueba estricto, como el `atob` del visor (que fallaría y dejaría a Gotenberg esperando), y lo
    descomprimido de todas las páginas suma contra MAX_INFLATED (D-230)."""
    child = diagram.find("mxGraphModel")
    if child is not None:
        return child
    text = re.sub(r"\s+", "", diagram.text or "")
    if not text:
        return None
    try:
        data = base64.b64decode(text, validate=True)
        inflater = zlib.decompressobj(-15)
        left = MAX_INFLATED - budget.inflated
        inflated = inflater.decompress(data, left + 1)
        if len(inflated) > left or inflater.unconsumed_tail:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Diagrama de más de 50 MB descomprimido")
        budget.inflated += len(inflated)
        xml = urllib.parse.unquote(inflated.decode("utf-8"))
    except (ValueError, zlib.error, UnicodeDecodeError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "página de draw.io ilegible") from exc
    if re.search(r"https?://", xml):
        budget.external = True
    return _safe(xml.encode("utf-8"))


def _num(el, key: str) -> float:
    try:
        v = float(el.get(key, 0))
    except ValueError:
        return 0.0
    return v if math.isfinite(v) else 0.0


def _bounds(model, budget: _Budget) -> tuple[float, float]:
    """Lo que ocupa lo dibujado: vértices (los de un grupo, relativos a él) y los puntos de las flechas."""
    cells = {}
    for cell in model.iter("mxCell"):
        budget.cells += 1
        if budget.cells > MAX_CELLS:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"Más de {MAX_CELLS} elementos en el diagrama")
        cells[cell.get("id")] = cell
    origin: dict[str, tuple[float, float]] = {}

    def offset(cell_id: str | None, depth: int = 0) -> tuple[float, float]:
        cell = cells.get(cell_id)
        if cell is None or depth > 50:
            return (0.0, 0.0)
        if cell_id in origin:
            return origin[cell_id]
        geo = cell.find("mxGeometry")
        base = offset(cell.get("parent"), depth + 1)
        here = (base[0] + _num(geo, "x"), base[1] + _num(geo, "y")) if geo is not None and cell.get("vertex") == "1" else base
        origin[cell_id] = here
        return here

    xs, ys = [], []
    for cell in cells.values():
        geo = cell.find("mxGeometry")
        if geo is None:
            continue
        ox, oy = offset(cell.get("parent"))
        if cell.get("vertex") == "1" and geo.get("relative") != "1":
            x, y = ox + _num(geo, "x"), oy + _num(geo, "y")
            xs += [x, x + _num(geo, "width")]
            ys += [y, y + _num(geo, "height")]
        if cell.get("edge") == "1":
            for point in geo.iter("mxPoint"):
                xs.append(ox + _num(point, "x"))
                ys.append(oy + _num(point, "y"))
    if not xs:
        return (800.0, 600.0)
    return (max(max(xs) - min(xs), 10.0), max(max(ys) - min(ys), 10.0))


def scan(raw: bytes):
    """(páginas [(nombre, (ancho, alto))], elementos <diagram>, ¿carga cosas de internet?)."""
    if len(raw) > MAX_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Diagrama de más de 20 MB")
    root = _safe(raw)
    diagrams = root.findall("diagram") if root.tag == "mxfile" else [root] if root.tag == "mxGraphModel" else []
    if not diagrams:
        raise ToolError(ErrorCode.CORRUPT_FILE, "drawio_empty")
    if len(diagrams) > MAX_PAGES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{len(diagrams)} páginas")
    budget = _Budget()
    budget.external = bool(re.search(rb"https?://", raw))
    out = []
    for i, d in enumerate(diagrams):
        model = d if d.tag == "mxGraphModel" else _model(d, budget)
        size = _bounds(model, budget) if model is not None else (800.0, 600.0)
        out.append((d.get("name") or f"Página {i + 1}", size))
    return out, diagrams, budget.external


def pages(raw: bytes) -> list[tuple[str, tuple[float, float]]]:
    return scan(raw)[0]


def single_page(root_tag: str, diagram) -> str:
    """El archivo con una sola página, para que cada PNG no vuelva a subir el diagrama entero (D-230)."""
    import xml.etree.ElementTree as ET

    body = ET.tostring(diagram, encoding="unicode")
    return body if root_tag == "mxGraphModel" else f"<mxfile>{body}</mxfile>"


def page_html(xml: str, count: int, box: tuple[float, float] | None, fit: bool, transparent: bool, only: int | None = None) -> bytes:
    """Una sección por página con el visor; `box` es el espacio disponible (px) y el SVG se escala para caber en él.
    `window.ready` avisa a Gotenberg (waitForExpression) cuando todas las páginas están dibujadas."""
    indexes = [only] if only is not None else list(range(count))
    sections = "".join(f'<section class="p" id="p{i}"></section>' for i in indexes)
    # Con `only`, el XML ya trae solo esa página (single_page): en el visor es la página 0.
    config = {"xml": xml, "box": box, "fit": fit, "pages": indexes, "border": BORDER, "first": 0}
    background = "transparent" if transparent else "#fff"
    script = (
        # Si una página falla o no se dibuja en 60 s, `window.ready` se pone igualmente y el error sale como excepción
        # sin capturar: Gotenberg (failOnConsoleExceptions) responde 409 en lugar de esperar hasta su límite (D-230).
        "(function(){var c=JSON.parse(document.getElementById('cfg').textContent),tries=0;"
        "function fail(m){window.ready=true;setTimeout(function(){throw new Error('drawio: '+m);},0);}"
        "var doc;try{doc=mxUtils.parseXml(c.xml);}catch(e){fail('xml');return;}"
        "var broken=false;c.pages.forEach(function(i,n){var el=document.getElementById('p'+i);try{"
        "new GraphViewer(el,doc.documentElement,{highlight:'none',nav:false,lightbox:false,toolbar:null,page:c.first+n,border:c.border,"
        "'auto-fit':false,resize:false,'check-visible-state':false});}catch(e){broken=true;}});"
        "if(broken){fail('page');return;}"
        "function fit(){var done=true;c.pages.forEach(function(i){var s=document.querySelector('#p'+i+' svg');"
        "if(!s){done=false;return;}if(s.dataset.f)return;var w=parseFloat(s.getAttribute('width'))||s.getBBox().width||1,"
        "h=parseFloat(s.getAttribute('height'))||s.getBBox().height||1;w=Math.max(w,1);h=Math.max(h,1);"
        "if(!s.getAttribute('viewBox'))s.setAttribute('viewBox','0 0 '+w+' '+h);"
        "var k=1;if(c.box){k=Math.min(c.box[0]/w,c.box[1]/h);if(!c.fit)k=Math.min(k,1);}"
        "s.setAttribute('width',w*k);s.setAttribute('height',h*k);s.style.minWidth='';s.style.minHeight='';s.dataset.f='1';});"
        "if(done){window.ready=true;}else if(++tries>1200){fail('timeout');}else{setTimeout(fit,50);}}fit();})();"
    )
    page = (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>diagrama</title>"
        f"<style>html,body{{margin:0;padding:0;background:{background}}}.p{{break-after:page;overflow:hidden}}"
        ".p:last-child{break-after:auto}.geDiagramContainer{overflow:visible!important}</style>"
        "<script>window.STENCIL_PATH='stencils';window.SHAPES_PATH='shapes';window.STYLE_PATH='styles';window.PROXY_URL='';"
        "window.DRAW_MATH_URL='';window.GRAPH_IMAGE_PATH='img';</script>"
        "<script src=\"viewer.js\"></script></head><body>"
        # Dentro de <script> el texto no se decodifica: «<» como \u003c, para que el XML no pueda cerrar la etiqueta.
        f"{sections}<script type=\"application/json\" id=\"cfg\">{json.dumps(config).replace('<', chr(92) + 'u003c')}</script>"
        f"<script>{script}</script></body></html>"
    )
    return page.encode("utf-8")


def _viewer(ctx: ToolContext) -> bytes:
    path = Path(ctx.settings.DRAWIO_VIEWER)
    if not path.is_file():
        raise ToolError(ErrorCode.ENGINE_FAILED, "visor de draw.io no instalado")
    return path.read_bytes()


def run(ctx: ToolContext) -> list[dict]:
    t = NOTES.get(ctx.locale, NOTES["es"])
    o = ctx.options
    viewer = _viewer(ctx)
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        raw = inp.path.read_bytes()
        info, diagrams, external = scan(raw)
        xml = raw.decode("utf-8", errors="replace").lstrip("\ufeff")
        root_tag = "mxGraphModel" if diagrams[0].tag == "mxGraphModel" else "mxfile"
        notes = [t["pages"].format(n=len(info))]
        if external:
            notes.append(t["external"])
        if ctx.tool == "drawio-a-pdf":
            orientation = o.orientacion
            if orientation == "auto":
                wide = sum(1 for _, (w, h) in info if w > h)
                orientation = "horizontal" if wide * 2 > len(info) else "vertical"
            w_mm, h_mm = gotenberg.PAPER_MM.get(o.papel, gotenberg.PAPER_MM["A4"])
            if orientation == "horizontal":
                w_mm, h_mm = h_mm, w_mm
            margin = 10
            box = ((w_mm - 2 * margin) * MM_PX - 4, (h_mm - 2 * margin) * MM_PX - 4)
            fields = {**gotenberg.page_fields(o.papel, orientation, margin, True), **WAIT}
            files = [("index.html", page_html(xml, len(info), box, o.ajustar, False), "text/html"), ("viewer.js", viewer, "text/javascript")]
            data = gotenberg.chromium_html_files(ctx.settings.GOTENBERG_URL, files, fields, conflict_error=ErrorCode.CORRUPT_FILE)
            name = derived_name(inp.name, "", "pdf")
            dst = ctx.output(name)
            dst.write_bytes(data)
            outputs.append({"path": str(dst), "name": name, "note": " ".join(notes)})
            continue
        images = []
        for i, (title, (w, h)) in enumerate(info):
            scale = min(o.escala, MAX_PNG_SIDE / max(w + 2 * BORDER, h + 2 * BORDER))
            width, height = math.ceil((w + 2 * BORDER) * scale), math.ceil((h + 2 * BORDER) * scale)
            fields = {"width": str(width), "height": str(height), "clip": "true", "format": "png",
                      "omitBackground": str(o.transparente).lower(), **WAIT}
            one = single_page(root_tag, diagrams[i])
            files = [("index.html", page_html(one, 1, (width, height), True, o.transparente, only=i), "text/html"),
                     ("viewer.js", viewer, "text/javascript")]
            png = gotenberg.chromium_screenshot_files(ctx.settings.GOTENBERG_URL, files, fields, conflict_error=ErrorCode.CORRUPT_FILE)
            suffix = "" if len(info) == 1 else "-" + (re.sub(r"[^\w.-]+", "_", title).strip("._")[:60] or str(i + 1))
            name = derived_name(inp.name, suffix, "png")
            dst = ctx.output(name)
            dst.write_bytes(png)
            images.append({"path": str(dst), "name": name, "note": None})
        images[0]["note"] = " ".join(notes)
        outputs += images
    return with_batch_zip(ctx, outputs, f"{ctx.tool}.zip")
