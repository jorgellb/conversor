"""pdf-a-markdown, pdf-a-html y pdf-a-epub (A.9) en `workerconvert`.

- Fluido: Docling a Markdown o HTML (con las imágenes dentro); el EPUB fluido se escribe aquí a partir de ese HTML,
  con un capítulo por título (D-70: pandoc de la distribución no puede crear EPUB con `--sandbox`).
- Fijo: cada página como SVG de pdftocairo con una capa de texto transparente encima (se puede seleccionar y buscar);
  en EPUB, un EPUB 3 de diseño fijo (pre-paginated).
- Automático: fluido si al menos la mitad de las páginas tienen texto; si no (escaneos, carteles), fijo (D-68).
"""
from __future__ import annotations

import base64
import html
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pypdfium2 as pdfium

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name, run_engine, zip_files
from tools.convert.docling_util import convert, subset_pdf
from tools.pdf.common import with_batch_zip

MIN_CHARS = 3
TITLES = {"es": {"page": "Página {n}", "toc": "Índice"}, "en": {"page": "Page {n}", "toc": "Contents"}}


def text_ratio(src: Path) -> float:
    doc = pdfium.PdfDocument(str(src))
    try:
        with_text = 0
        for i in range(len(doc)):
            page = doc[i]
            tp = page.get_textpage()
            if len("".join(tp.get_text_range().split())) >= MIN_CHARS:
                with_text += 1
            tp.close()
            page.close()
        return with_text / max(1, len(doc))
    finally:
        doc.close()


def choose_layout(option: str, src: Path) -> str:
    if option in ("fijo", "fluido"):
        return option
    return "fluido" if text_ratio(src) >= 0.5 else "fijo"


def _layers(remove_furniture: bool):
    from docling_core.types.doc.document import ContentLayer

    return {ContentLayer.BODY} if remove_furniture else {ContentLayer.BODY, ContentLayer.FURNITURE}


def _ocr(ctx: ToolContext) -> tuple[bool, list[str] | None]:
    o = ctx.options
    return o.ocr_si_no_hay_texto, getattr(o, "idiomas", None)


# --- Diseño fijo --------------------------------------------------------------------------------------------------


@dataclass
class FixedPage:
    width: float
    height: float
    svg: bytes
    text_layer: str


def _text_layer(page, width: float, height: float) -> str:
    """SVG con el texto en su sitio y transparente: se ve el dibujo de pdftocairo y se selecciona este texto."""
    tp = page.get_textpage()
    parts = []
    try:
        for i in range(tp.count_rects()):
            left, bottom, right, top = tp.get_rect(i)
            text = tp.get_text_bounded(left, bottom, right, top).strip()
            if not text or right <= left or top <= bottom:
                continue
            size = top - bottom
            y = height - bottom - size * 0.2
            parts.append(f'<text x="{left:.2f}" y="{y:.2f}" font-size="{size:.2f}" textLength="{right - left:.2f}" '
                         f'lengthAdjust="spacingAndGlyphs">{html.escape(text)}</text>')
    finally:
        tp.close()
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="t" viewBox="0 0 {width:.2f} {height:.2f}" '
            f'preserveAspectRatio="none">{"".join(parts)}</svg>')


def fixed_pages(ctx: ToolContext, src: Path, work: Path) -> list[FixedPage]:
    exe = shutil.which("pdftocairo") or "pdftocairo"
    local = work / "fijo.pdf"
    shutil.copyfile(src, local)
    doc = pdfium.PdfDocument(str(local))
    pages = []
    try:
        for i in range(len(doc)):
            page = doc[i]
            width, height = page.get_size()
            out = work / f"pagina-{i + 1}.svg"
            run_engine([exe, "-svg", "-f", str(i + 1), "-l", str(i + 1), str(local), str(out)], cwd=work, timeout=300, mem_mb=1536)
            if not out.exists():
                raise ToolError(ErrorCode.ENGINE_FAILED, "pdftocairo no generó el SVG")
            pages.append(FixedPage(width, height, out.read_bytes(), _text_layer(page, width, height)))
            page.close()
            ctx.report(0.5 * (i + 1) / len(doc), None)
    finally:
        doc.close()
    return pages


FIXED_CSS = (".p{position:relative;margin:16px auto;max-width:100%;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.35)}"
             ".p img,.p svg.t{position:absolute;inset:0;width:100%;height:100%}.p svg.t text{fill:transparent}"
             "::selection{background:rgba(0,90,255,.3)}")


def fixed_html(pages: list[FixedPage], title: str, locale: str) -> str:
    body = "".join(
        f'<div class="p" style="width:{p.width:.2f}pt;aspect-ratio:{p.width:.2f}/{p.height:.2f}">'
        f'<img src="data:image/svg+xml;base64,{base64.b64encode(p.svg).decode()}" alt="">{p.text_layer}</div>' for p in pages)
    return (f'<!doctype html><html lang="{html.escape(locale)}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>'
            f"<style>body{{margin:0;padding:8px;background:#525659}}{FIXED_CSS}</style></head><body>{body}</body></html>")


def _write_epub(dst: Path, title: str, locale: str, items: list[tuple[str, bytes, str, str | None]], spine: list[str],
                fixed: bool) -> None:
    """EPUB 3: `items` = (ruta dentro de OEBPS, datos, tipo MIME, propiedades del manifiesto)."""
    ident = f"urn:uuid:{uuid.uuid4()}"
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = "".join(f'<item id="i{k}" href="{html.escape(path)}" media-type="{mime}"{f" properties={chr(34)}{props}{chr(34)}" if props else ""}/>'
                       for k, (path, _, mime, props) in enumerate(items))
    ids = {path: f"i{k}" for k, (path, *_rest) in enumerate(items)}
    rendition = ('<meta property="rendition:layout">pre-paginated</meta><meta property="rendition:spread">none</meta>'
                 if fixed else "")
    opf = ('<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
           f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">{ident}</dc:identifier>'
           f"<dc:title>{html.escape(title)}</dc:title><dc:language>{html.escape(locale)}</dc:language>"
           f'<meta property="dcterms:modified">{modified}</meta>{rendition}</metadata><manifest>{manifest}</manifest>'
           f'<spine>{"".join(f"<itemref idref={chr(34)}{ids[s]}{chr(34)}/>" for s in spine)}</spine></package>')
    container = ('<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        for path, data, _, _ in items:
            zf.writestr(f"OEBPS/{path}", data)


FLOW_CSS = ("body{font-family:serif;line-height:1.5;margin:0 4%}h1,h2,h3{font-family:sans-serif;line-height:1.25}"
            "img{max-width:100%;height:auto}table{border-collapse:collapse;margin:1em 0}td,th{border:1px solid #888;padding:.25em .5em}"
            "figcaption,.caption{font-size:.9em;color:#555}")
XHTML = "http://www.w3.org/1999/xhtml"


def with_lang(page: str, locale: str) -> str:
    """Docling no pone el idioma en <html>: lo necesitan lectores de pantalla y buscadores."""
    return page.replace("<html>", f'<html lang="{html.escape(locale)}">', 1) if "<html>" in page else page


def flowing_epub(page: str, dst: Path, title: str, locale: str) -> None:
    """EPUB 3 a partir del HTML de Docling: un capítulo por título h1/h2, imágenes como archivos e índice."""
    import lxml.html
    from lxml import etree

    t = TITLES.get(locale, TITLES["es"])
    root = lxml.html.document_fromstring(page)
    body = root.find("body")
    container = body if body is not None else root
    while len(container) == 1 and container[0].tag == "div":
        container = container[0]
    items: list[tuple[str, bytes, str, str | None]] = [("estilo.css", FLOW_CSS.encode(), "text/css", None)]
    for k, img in enumerate(container.iter("img"), start=1):
        src = img.get("src", "")
        if src.startswith("data:image/") and ";base64," in src:
            mime, data = src[5:].split(";base64,", 1)
            ext = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}.get(mime, "png")
            items.append((f"imagenes/img-{k}.{ext}", base64.b64decode(data), mime, None))
            img.set("src", f"imagenes/img-{k}.{ext}")
        elif src:
            img.attrib.pop("src")  # nada de recursos de fuera del libro
        img.set("alt", img.get("alt", ""))
    chapters: list[tuple[str, list]] = []
    for el in list(container):
        if not isinstance(el.tag, str):
            continue
        if el.tag in ("h1", "h2") or not chapters:
            heading = el.text_content().strip() if el.tag in ("h1", "h2") else title
            chapters.append((heading or title, []))
        chapters[-1][1].append(el)
    spine, links = [], []
    for n, (heading, elements) in enumerate(chapters, start=1):
        content = "".join(etree.tostring(el, method="xml", encoding="unicode", with_tail=False) for el in elements)
        doc = ('<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
               f'<html xmlns="{XHTML}" lang="{html.escape(locale)}" xml:lang="{html.escape(locale)}"><head><meta charset="utf-8"/>'
               f'<title>{html.escape(heading)}</title><link rel="stylesheet" href="estilo.css"/></head><body>{content}</body></html>')
        etree.fromstring(doc.encode("utf-8"))  # XHTML bien formado o error claro antes de entregarlo
        items.append((f"capitulo-{n}.xhtml", doc.encode("utf-8"), "application/xhtml+xml", None))
        spine.append(f"capitulo-{n}.xhtml")
        links.append(f'<li><a href="capitulo-{n}.xhtml">{html.escape(heading)}</a></li>')
    nav = ('<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml" '
           f'xmlns:epub="http://www.idpf.org/2007/ops"><head><meta charset="utf-8"/><title>{html.escape(t["toc"])}</title></head>'
           f'<body><nav epub:type="toc"><h1>{html.escape(t["toc"])}</h1><ol>{"".join(links)}</ol></nav></body></html>')
    items.append(("nav.xhtml", nav.encode("utf-8"), "application/xhtml+xml", "nav"))
    _write_epub(dst, title, locale, items, spine, fixed=False)


def fixed_epub(pages: list[FixedPage], dst: Path, title: str, locale: str) -> None:
    t = TITLES.get(locale, TITLES["es"])
    items: list[tuple[str, bytes, str, str | None]] = [("estilo.css", (FIXED_CSS + "html,body{margin:0}.p{margin:0;box-shadow:none}").encode(),
                                                       "text/css", None)]
    spine, links = [], []
    for n, p in enumerate(pages, start=1):
        w, h = round(p.width * 4 / 3), round(p.height * 4 / 3)
        items.append((f"pagina-{n}.svg", p.svg, "image/svg+xml", None))
        page = ('<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
                f'<head><meta charset="utf-8"/><meta name="viewport" content="width={w}, height={h}"/>'
                f'<title>{html.escape(t["page"].format(n=n))}</title><link rel="stylesheet" href="estilo.css"/></head>'
                f'<body><div class="p" style="width:{w}px;height:{h}px"><img src="pagina-{n}.svg" alt=""/>{p.text_layer}</div></body></html>')
        items.append((f"pagina-{n}.xhtml", page.encode("utf-8"), "application/xhtml+xml", "svg"))
        spine.append(f"pagina-{n}.xhtml")
        links.append(f'<li><a href="pagina-{n}.xhtml">{html.escape(t["page"].format(n=n))}</a></li>')
    nav = ('<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml" '
           f'xmlns:epub="http://www.idpf.org/2007/ops"><head><meta charset="utf-8"/><title>{html.escape(t["toc"])}</title></head>'
           f'<body><nav epub:type="toc"><h1>{html.escape(t["toc"])}</h1><ol>{"".join(links)}</ol></nav></body></html>')
    items.append(("nav.xhtml", nav.encode("utf-8"), "application/xhtml+xml", "nav"))
    _write_epub(dst, title, locale, items, spine, fixed=True)


# --- Herramientas -------------------------------------------------------------------------------------------------


def run_markdown(ctx: ToolContext) -> list[dict]:
    from docling_core.types.doc import ImageRefMode

    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        src, _ = subset_pdf(ctx, inp.path, o.paginas, n)
        ocr, languages = _ocr(ctx)
        with_images = o.imagenes == "incluidas"
        doc = convert(src, ocr, languages, pictures=with_images, scale=2.0)
        stem = Path(inp.name).stem or "documento"
        layers = _layers(o.quitar_encabezados)
        work = ctx.work / f"md-{n}"
        work.mkdir(parents=True, exist_ok=True)
        md = work / f"{stem}.md"
        if with_images:
            doc.save_as_markdown(md, artifacts_dir=Path(f"{stem}-imagenes"), image_mode=ImageRefMode.REFERENCED,
                                 included_content_layers=layers)
        else:
            md.write_text(doc.export_to_markdown(image_mode=ImageRefMode.PLACEHOLDER, image_placeholder="",
                                                 included_content_layers=layers), encoding="utf-8")
        images = sorted(p for p in (work / f"{stem}-imagenes").glob("*") if p.is_file()) if with_images else []
        if images:
            name = f"{stem}-markdown.zip"
            dst = ctx.output(name)
            zip_files([(md, md.name), *[(p, f"{stem}-imagenes/{p.name}") for p in images]], dst)
        else:
            name = derived_name(inp.name, "", "md")
            dst = ctx.output(name)
            shutil.move(md, dst)
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "pdf-markdown.zip")


def run_html(ctx: ToolContext) -> list[dict]:
    from docling_core.types.doc import ImageRefMode

    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        src, _ = subset_pdf(ctx, inp.path, o.paginas, n)
        stem = Path(inp.name).stem or "documento"
        layout = choose_layout(o.diseno, src)
        work = ctx.work / f"html-{n}"
        work.mkdir(parents=True, exist_ok=True)
        if layout == "fijo":
            page = fixed_html(fixed_pages(ctx, src, work), stem, ctx.locale)
        else:
            ocr, languages = _ocr(ctx)
            doc = convert(src, ocr, languages, pictures=True, scale=2.0)
            page = with_lang(doc.export_to_html(image_mode=ImageRefMode.EMBEDDED, html_lang=ctx.locale,
                                                included_content_layers=_layers(True)), ctx.locale)
        name = derived_name(inp.name, "", "html")
        dst = ctx.output(name)
        dst.write_text(page, encoding="utf-8")
        outputs.append({"path": str(dst), "name": name, "note": None if o.diseno != "auto" else _layout_note(ctx.locale, layout)})
    return with_batch_zip(ctx, outputs, "pdf-html.zip")


def _layout_note(locale: str, layout: str) -> str:
    if locale == "en":
        return "Fixed layout: each page as it looks, with selectable text." if layout == "fijo" else "Flowing layout: text that adapts to the screen."
    return "Diseño fijo: cada página tal cual, con el texto seleccionable." if layout == "fijo" else "Diseño fluido: texto que se adapta a la pantalla."


def run_epub(ctx: ToolContext) -> list[dict]:
    from docling_core.types.doc import ImageRefMode

    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        src, _ = subset_pdf(ctx, inp.path, o.paginas, n)
        stem = Path(inp.name).stem or "documento"
        layout = choose_layout(o.diseno, src)
        work = ctx.work / f"epub-{n}"
        work.mkdir(parents=True, exist_ok=True)
        epub = work / f"{stem}.epub"
        if layout == "fijo":
            fixed_epub(fixed_pages(ctx, src, work), epub, stem, ctx.locale)
        else:
            ocr, languages = _ocr(ctx)
            doc = convert(src, ocr, languages, pictures=True, scale=2.0)
            flowing_epub(doc.export_to_html(image_mode=ImageRefMode.EMBEDDED, html_lang=ctx.locale,
                                            included_content_layers=_layers(True)), epub, stem, ctx.locale)
        if not epub.exists():
            raise ToolError(ErrorCode.ENGINE_FAILED, "No se generó el EPUB")
        name = derived_name(inp.name, "", "epub")
        dst = ctx.output(name)
        shutil.move(epub, dst)
        outputs.append({"path": str(dst), "name": name, "note": None if o.diseno != "auto" else _layout_note(ctx.locale, layout)})
    return with_batch_zip(ctx, outputs, "pdf-epub.zip")
