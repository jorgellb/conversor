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
BORDER = 10
MM_PX = 96 / 25.4

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


def _model(diagram):
    """El mxGraphModel de una página: hijo directo o texto comprimido (Base64 de deflate sin cabecera y URL-encode)."""
    child = diagram.find("mxGraphModel")
    if child is not None:
        return child
    text = (diagram.text or "").strip()
    if not text:
        return None
    try:
        inflated = zlib.decompressobj(-15).decompress(base64.b64decode(text), 50 * 1024 * 1024)
        return _safe(urllib.parse.unquote(inflated.decode("utf-8")).encode("utf-8"))
    except (ValueError, zlib.error, UnicodeDecodeError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "página de draw.io ilegible") from exc


def pages(raw: bytes) -> list[tuple[str, tuple[float, float]]]:
    """(nombre, (ancho, alto)) de cada página, con el tamaño de lo dibujado (vértices y puntos de las flechas)."""
    if len(raw) > MAX_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Diagrama de más de 20 MB")
    root = _safe(raw)
    diagrams = root.findall("diagram") if root.tag == "mxfile" else [root] if root.tag == "mxGraphModel" else []
    if not diagrams:
        raise ToolError(ErrorCode.CORRUPT_FILE, "drawio_empty")
    if len(diagrams) > MAX_PAGES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{len(diagrams)} páginas")
    out = []
    for i, d in enumerate(diagrams):
        model = d if d.tag == "mxGraphModel" else _model(d)
        xs, ys = [], []
        for geo in (model.iter("mxGeometry") if model is not None else []):
            if geo.get("relative") == "1":
                continue
            try:
                x, y = float(geo.get("x", 0)), float(geo.get("y", 0))
                w, h = float(geo.get("width", 0)), float(geo.get("height", 0))
            except ValueError:
                continue
            if all(math.isfinite(v) for v in (x, y, w, h)):
                xs += [x, x + w]
                ys += [y, y + h]
        size = (max(xs) - min(xs), max(ys) - min(ys)) if xs else (800.0, 600.0)
        out.append((d.get("name") or f"Página {i + 1}", (max(size[0], 10.0), max(size[1], 10.0))))
    return out


def page_html(xml: str, count: int, box: tuple[float, float] | None, fit: bool, transparent: bool, only: int | None = None) -> bytes:
    """Una sección por página con el visor; `box` es el espacio disponible (px) y el SVG se escala para caber en él.
    `window.ready` avisa a Gotenberg (waitForExpression) cuando todas las páginas están dibujadas."""
    indexes = [only] if only is not None else list(range(count))
    sections = "".join(f'<section class="p" id="p{i}"></section>' for i in indexes)
    config = {"xml": xml, "box": box, "fit": fit, "pages": indexes, "border": BORDER}
    background = "transparent" if transparent else "#fff"
    script = (
        "(function(){var c=JSON.parse(document.getElementById('cfg').textContent);"
        "var doc=mxUtils.parseXml(c.xml);"
        "c.pages.forEach(function(i){var el=document.getElementById('p'+i);"
        "new GraphViewer(el,doc.documentElement,{highlight:'none',nav:false,lightbox:false,toolbar:null,page:i,border:c.border,"
        "'auto-fit':false,resize:false,'check-visible-state':false});});"
        "function fit(){var done=true;c.pages.forEach(function(i){var s=document.querySelector('#p'+i+' svg');"
        "if(!s){done=false;return;}if(s.dataset.f)return;var w=parseFloat(s.getAttribute('width'))||s.getBBox().width,"
        "h=parseFloat(s.getAttribute('height'))||s.getBBox().height;if(!s.getAttribute('viewBox'))s.setAttribute('viewBox','0 0 '+w+' '+h);"
        "var k=1;if(c.box){k=Math.min(c.box[0]/w,c.box[1]/h);if(!c.fit)k=Math.min(k,1);}"
        "s.setAttribute('width',w*k);s.setAttribute('height',h*k);s.style.minWidth='';s.style.minHeight='';s.dataset.f='1';});"
        "if(done){window.ready=true;}else{setTimeout(fit,50);}}fit();})();"
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
        info = pages(raw)
        xml = raw.decode("utf-8", errors="replace").lstrip("﻿")
        notes = [t["pages"].format(n=len(info))]
        if re.search(r"https?://", xml):
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
            fields = {**gotenberg.page_fields(o.papel, orientation, margin, True), "waitForExpression": "window.ready === true"}
            files = [("index.html", page_html(xml, len(info), box, o.ajustar, False), "text/html"), ("viewer.js", viewer, "text/javascript")]
            data = gotenberg.chromium_html_files(ctx.settings.GOTENBERG_URL, files, fields)
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
                      "omitBackground": str(o.transparente).lower(), "waitForExpression": "window.ready === true"}
            files = [("index.html", page_html(xml, len(info), (width, height), True, o.transparente, only=i), "text/html"),
                     ("viewer.js", viewer, "text/javascript")]
            png = gotenberg.chromium_screenshot_files(ctx.settings.GOTENBERG_URL, files, fields)
            suffix = "" if len(info) == 1 else "-" + (re.sub(r"[^\w.-]+", "_", title).strip("._")[:60] or str(i + 1))
            name = derived_name(inp.name, suffix, "png")
            dst = ctx.output(name)
            dst.write_bytes(png)
            images.append({"path": str(dst), "name": name, "note": None})
        images[0]["note"] = " ".join(notes)
        outputs += images
    return with_batch_zip(ctx, outputs, f"{ctx.tool}.zip")
