"""html-a-pdf, markdown-a-pdf y txt-a-pdf (7.3 y A.8) con el Chromium de `gotenberg`, que no tiene salida de red.

Los recursos remotos no se cargan: solo los que vienen dentro del ZIP (HTML) o incrustados en el documento.
"""
from __future__ import annotations

import codecs
import html
import mimetypes
import posixpath
import re
import zipfile
from pathlib import Path
from urllib.parse import unquote

import charset_normalizer

from core.errors import ErrorCode, ToolError
from core.zipguard import check_zip
from tools.base import ToolContext, derived_name
from tools.office import gotenberg
from tools.office.office_a_pdf import select_pages
from tools.pdf.common import with_batch_zip

# Texto que se maqueta como mucho (TXT y Markdown); más allá, Chromium tarda demasiado y el PDF no sería manejable.
MAX_TEXT_BYTES = 10 * 1024 * 1024
TEXT_ASSETS = (".html", ".htm", ".css", ".svg")
SANS = gotenberg.SANS
SERIF = '"Noto Serif", "DejaVu Serif", "Liberation Serif", "Times New Roman", serif'
MONO = '"Noto Sans Mono", "DejaVu Sans Mono", "Liberation Mono", "Courier New", monospace'
WESTERN = ("cp1252", "iso8859_15", "latin_1")


def decode_text(data: bytes) -> str:
    """Texto con la codificación detectada (A.8): BOM, UTF-8 estricto y, si no, charset-normalizer."""
    for bom, codec in ((codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16")):
        if data.startswith(bom):
            return data.decode(codec, errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    results = charset_normalizer.from_bytes(data)
    best = results.best()
    if best is None:
        return data.decode("cp1252", errors="replace")
    tied = [r for r in results if r.chaos == best.chaos and r.coherence == best.coherence]
    if len(tied) > 1 or best.coherence == 0:
        # Empate (habitual en textos cortos entre cp1250 y cp1252): se prefiere Europa occidental, que es el público
        # de la web (es y en). Un texto que solo encaja en otra codificación la conserva.
        for enc in WESTERN:
            for r in tied:
                if r.encoding == enc:
                    return str(r)
        try:
            text = data.decode("cp1252")
        except UnicodeDecodeError:
            return str(best)
        if all(c.isprintable() or c in "\r\n\t\f" for c in text):
            return text
    return str(best)


def _read_text(path: Path) -> str:
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Texto de más de 10 MB")
    return decode_text(path.read_bytes())


def _document(title: str, css: str, body: str) -> bytes:
    return (
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title><style>{css}</style></head>"
        f"<body>{body}</body></html>"
    ).encode("utf-8")


def _convert(ctx: ToolContext, files: list[tuple[str, bytes, str]], fields: dict[str, str], name: str) -> dict:
    data = gotenberg.chromium_html_files(ctx.settings.GOTENBERG_URL, files, fields)
    display = derived_name(name, "", "pdf")
    dst = ctx.output(display)
    dst.write_bytes(data)
    select_pages(dst, "todas", ctx.plan.pdf_pages)
    return {"path": str(dst), "name": display}


# --- HTML ---------------------------------------------------------------------------------------------------------

_ATTR_RE = re.compile(r"""(?P<pre>\b(?:src|href|poster|background|data)\s*=\s*)(?P<q>["'])(?P<url>[^"'<>]*)(?P=q)""", re.I)
_CSS_URL_RE = re.compile(r"""(?P<pre>url\(\s*)(?P<q>["']?)(?P<url>[^"')]+)(?P=q)(?P<post>\s*\))""", re.I)
_IMPORT_RE = re.compile(r"""(?P<pre>@import\s+)(?P<q>["'])(?P<url>[^"']+)(?P=q)""", re.I)
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)


def _flat_name(path: str, used: set[str]) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.replace("/", "__")).strip("._") or "recurso"
    name, n = stem, 2
    while name.lower() in used:
        base, dot, ext = stem.rpartition(".")
        name = f"{base}-{n}.{ext}" if dot else f"{stem}-{n}"
        n += 1
    used.add(name.lower())
    return name


def _rewrite(text: str, member: str, root: str, flat: dict[str, str]) -> str:
    """Cambia las referencias relativas a archivos del ZIP por su nombre en el nivel único que usa Gotenberg."""
    base = posixpath.dirname(member)

    def target(url: str) -> str | None:
        if not url or url.startswith(("#", "//")) or _SCHEME_RE.match(url):
            return None
        path, _, rest = url.partition("?")
        path, _, frag = path.partition("#")
        ref = unquote(path)
        resolved = posixpath.normpath(posixpath.join(root, ref.lstrip("/")) if ref.startswith("/") else posixpath.join(base, ref))
        name = flat.get(resolved)
        if name is None:
            return None
        return name + (f"#{frag}" if frag else "")

    def sub(m: re.Match) -> str:
        new = target(m.group("url").strip())
        if new is None:
            return m.group(0)
        return f"{m.group('pre')}{m.group('q')}{new}{m.group('q')}{m.groupdict().get('post') or ''}"

    for pattern in (_ATTR_RE, _CSS_URL_RE, _IMPORT_RE):
        text = pattern.sub(sub, text)
    return text


def site_from_zip(path: Path) -> list[tuple[str, bytes, str]]:
    """HTML con sus recursos desde un ZIP: elige el `index.html` (o el HTML menos profundo) y aplana las carpetas."""
    check_zip(path)
    with zipfile.ZipFile(path) as zf:
        entries: dict[str, zipfile.ZipInfo] = {}
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = [p for p in info.filename.replace("\\", "/").split("/") if p not in ("", ".")]
            if not parts or ".." in parts or parts[0] == "__MACOSX" or any(p.startswith(".") for p in parts):
                continue
            entries["/".join(parts)] = info
        pages = [n for n in entries if n.lower().endswith((".html", ".htm"))]
        if not pages:
            raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "El ZIP no contiene ningún HTML")
        index = min(pages, key=lambda n: (n.count("/"), posixpath.basename(n).lower() not in ("index.html", "index.htm"), n))
        root = posixpath.dirname(index)
        used = {"index.html"}
        prefix = f"{root}/" if root else ""
        flat = {n: ("index.html" if n == index else _flat_name(n.removeprefix(prefix), used)) for n in entries}
        files: list[tuple[str, bytes, str]] = []
        for member, info in entries.items():
            data = zf.read(info)
            if member.lower().endswith(TEXT_ASSETS):
                text = data.decode("utf-8", errors="surrogateescape")
                data = _rewrite(text, member, root, flat).encode("utf-8", errors="surrogateescape")
            mime = "text/html" if flat[member] == "index.html" else mimetypes.guess_type(member)[0] or "application/octet-stream"
            files.append((flat[member], data, mime))
    files.sort(key=lambda f: f[0] != "index.html")
    return files


def run_html(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    fields = gotenberg.page_fields(o.papel, o.orientacion, o.margenes_mm, o.imprimir_fondos, o.una_pagina, o.medio, o.tamano_css)
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        ext = inp.ext or Path(inp.name).suffix.lstrip(".").lower()
        if ext == "zip":
            files = site_from_zip(inp.path)
        else:
            files = [("index.html", inp.path.read_bytes(), "text/html")]
        outputs.append(_convert(ctx, files, fields, inp.name))
    return with_batch_zip(ctx, outputs, "html-pdf.zip")


# --- Markdown -----------------------------------------------------------------------------------------------------

THEMES = {
    "claro": (
        f"body{{font-family:{SANS};font-size:11pt;line-height:1.55;color:#1f2328}}"
        "h1,h2{border-bottom:1px solid #d1d9e0;padding-bottom:.25em}"
        "a{color:#0969da}"
        f"code,pre{{font-family:{MONO};font-size:9.5pt}}"
        "code{background:#eff1f3;padding:.1em .3em;border-radius:4px}"
        "pre{background:#f6f8fa;padding:12px;border-radius:6px;white-space:pre-wrap;overflow-wrap:anywhere}"
        "pre code{background:none;padding:0}"
        "blockquote{margin:0;padding:0 1em;color:#59636e;border-left:.25em solid #d1d9e0}"
        "table{border-collapse:collapse}th,td{border:1px solid #d1d9e0;padding:6px 12px}tr:nth-child(2n){background:#f6f8fa}",
        "default",
    ),
    "sobrio": (
        f"body{{font-family:{SERIF};font-size:11.5pt;line-height:1.5;color:#000}}"
        "h1,h2,h3{font-weight:600}a{color:#000}"
        f"code,pre{{font-family:{MONO};font-size:9.5pt}}"
        "pre{border-left:2px solid #999;padding:4px 10px;white-space:pre-wrap;overflow-wrap:anywhere}"
        "blockquote{margin:0 1.5em;font-style:italic}"
        "table{border-collapse:collapse}th,td{border-bottom:1px solid #999;padding:4px 10px}",
        "bw",
    ),
}
COMMON_CSS = (
    "img{max-width:100%}ul.contains-task-list{list-style:none;padding-left:1.2em}"
    "li.task-list-item input{margin:0 .4em 0 -1.2em}h1,h2,h3{break-after:avoid}pre,table,img{break-inside:avoid}"
)


def render_markdown(text: str, tema: str = "claro", title: str = "documento") -> bytes:
    """Markdown con sabor GitHub (tablas, listas de tareas, tachado y código resaltado) a HTML completo."""
    from markdown_it import MarkdownIt
    from mdit_py_plugins.tasklists import tasklists_plugin
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name
    from pygments.util import ClassNotFound

    css, style = THEMES.get(tema, THEMES["claro"])
    formatter = HtmlFormatter(nowrap=True)

    def highlight_code(code: str, lang: str, _attrs) -> str:
        try:
            lexer = get_lexer_by_name(lang.strip().split()[0]) if lang.strip() else None
        except ClassNotFound:
            lexer = None
        if lexer is None:
            return ""
        return f'<pre class="highlight"><code>{highlight(code, lexer, formatter)}</code></pre>'

    md = MarkdownIt("commonmark", {"html": True, "highlight": highlight_code}).enable(["table", "strikethrough"]).use(tasklists_plugin)
    body = md.render(text)
    pygments_css = HtmlFormatter(style=style).get_style_defs(".highlight")
    return _document(title, css + COMMON_CSS + pygments_css, body)


def run_markdown(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    fields = gotenberg.page_fields(o.papel, "vertical", 20, True, False, "print")
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        page = render_markdown(_read_text(inp.path), o.tema, Path(inp.name).stem)
        outputs.append(_convert(ctx, [("index.html", page, "text/html")], fields, inp.name))
    return with_batch_zip(ctx, outputs, "markdown-pdf.zip")


# --- TXT ----------------------------------------------------------------------------------------------------------


def render_text(text: str, fuente: str = "monoespaciada", title: str = "texto") -> bytes:
    family = MONO if fuente == "monoespaciada" else SANS
    size = "9.5pt" if fuente == "monoespaciada" else "11pt"
    css = (f"body{{margin:0}}pre{{margin:0;font-family:{family};font-size:{size};line-height:1.35;"
           "white-space:pre-wrap;overflow-wrap:anywhere;tab-size:8}")
    return _document(title, css, f"<pre>{html.escape(text.replace(chr(12), ''))}</pre>")


def run_txt(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    fields = gotenberg.page_fields(o.papel, "vertical", o.margenes_mm, True, False, "print")
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        page = render_text(_read_text(inp.path), o.fuente, Path(inp.name).stem)
        outputs.append(_convert(ctx, [("index.html", page, "text/html")], fields, inp.name))
    return with_batch_zip(ctx, outputs, "textos-pdf.zip")
