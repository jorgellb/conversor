"""epub-a-pdf, mobi-a-pdf, azw3-a-pdf y fb2-a-pdf (A.8) con `ebook-convert` de Calibre.

Calibre corre como subproceso con entorno vacío, sin red (el worker no tiene salida) y con su configuración dentro del
directorio del trabajo (12.1 y 12.3). Antes se revisa la entrada: ZIP sin bombas ni rutas que escapan, y ninguna
referencia a archivos locales (`file:`, rutas absolutas o `..` fuera del libro) en EPUB y FB2.
"""
from __future__ import annotations

import html
import posixpath
import re
import zipfile
from pathlib import Path

import pikepdf

from core.errors import ErrorCode, ToolError
from core.zipguard import check_zip
from tools.base import ToolContext, derived_name, run_engine
from tools.pdf.common import with_batch_zip

MM_TO_PT = 72 / 25.4
PAPER = {"A5": "a5", "A4": "a4", "Letter": "letter"}
TOC_TITLE = {"es": "Índice", "en": "Contents"}
MAX_TOC_PAGES = 60
TEXT_MEMBERS = (".xhtml", ".html", ".htm", ".xml", ".css", ".svg", ".opf", ".ncx", ".smil")
MAX_SCAN_BYTES = 64 * 1024 * 1024
REF = re.compile(r"""(?:\b(?:src|href|data|poster|xlink:href|l:href|srcset)\s*=\s*(?:"([^"]*)"|'([^']*)')|url\(\s*["']?([^"')]+))""", re.I)
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)
ENTITY = re.compile(r"<!ENTITY", re.I)


def _escapes(ref: str, member: str) -> bool:
    """La referencia apunta fuera del libro: `file:`, ruta absoluta o `..` por encima de la raíz."""
    ref = html.unescape(ref).strip().replace("\\", "/")
    if not ref:
        return False
    if ref.lower().startswith("file:") or ref.startswith("/"):
        return True
    if SCHEME.match(ref):
        return False  # http, https, mailto, data…: el worker no tiene red y Calibre no los sigue
    path = ref.split("#", 1)[0].split("?", 1)[0]
    if not path:
        return False
    return posixpath.normpath(posixpath.join(posixpath.dirname(member), path)).startswith("..")


def _scan_text(text: str, member: str) -> None:
    if ENTITY.search(text):
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "El libro declara entidades XML")
    for m in REF.finditer(text):
        values = [v for v in m.groups() if v]
        for value in values:
            for ref in (value.split(",") if "srcset" in m.group(0)[:8].lower() else [value]):
                if _escapes(ref.strip().split(" ")[0], member):
                    raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "El libro enlaza archivos que no están dentro de él")


def check_book(path: Path, ext: str) -> None:
    """Revisión previa (12.3): ningún libro llega a Calibre con referencias a archivos locales."""
    if ext == "epub":
        if not zipfile.is_zipfile(path):
            raise ToolError(ErrorCode.CORRUPT_FILE, "EPUB ilegible")
        check_zip(path)
        scanned = 0
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir() or not info.filename.lower().endswith(TEXT_MEMBERS):
                    continue
                scanned += info.file_size
                if scanned > MAX_SCAN_BYTES:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Libro demasiado grande")
                _scan_text(zf.read(info).decode("utf-8", "replace"), info.filename)
    elif ext == "fb2":
        from defusedxml import ElementTree as SafeET

        data = path.read_bytes()
        try:
            SafeET.fromstring(data)
        except Exception as exc:  # noqa: BLE001 - XML mal formado o con entidades (XXE)
            raise ToolError(ErrorCode.CORRUPT_FILE, "FB2 no válido") from exc
        _scan_text(data.decode("utf-8", "replace"), "libro.fb2")


def _title_on_top(textpage, title: str) -> bool:
    """El título está solo en la línea más alta de la página. Se mira la posición de los caracteres y no el orden del
    texto extraído, que con las fuentes de Calibre a veces mezcla líneas."""
    boxes = [textpage.get_charbox(i) for i in range(textpage.count_chars())]
    visible = [b for b in boxes if b[2] > b[0] and b[3] > b[1]]
    if not visible:
        return False
    highest = max(b[3] for b in visible)
    searcher = textpage.search(title, match_case=True)
    try:
        while (hit := searcher.get_next()) is not None:
            index, count = hit
            box = boxes[index]
            if box[3] < highest - 1.0:
                continue
            following = [b for b in boxes[index + count:] if b[2] > b[0] and b[3] > b[1]]
            if not following or following[0][3] < box[1] + 1.0:  # lo siguiente ya está en otra línea
                return True
    finally:
        searcher.close()
    return False


def toc_to_front(path: Path, title: str) -> int:
    """Calibre añade el índice al final y sin marcador. Se busca desde el final la página que empieza con su título,
    se pasan esas páginas al principio y se numeran las páginas del PDF (i, ii… el índice; 1, 2… el libro) para que
    los números del índice sigan coincidiendo. Devuelve cuántas páginas tiene el índice (0 si no se encontró)."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    try:
        total = len(doc)
        start = None
        for i in range(total - 1, max(-1, total - 1 - MAX_TOC_PAGES), -1):
            page = doc[i]
            textpage = page.get_textpage()
            try:
                if _title_on_top(textpage, title):
                    start = i
                    break
            finally:
                textpage.close()
                page.close()
    finally:
        doc.close()
    if not start:
        return 0
    count = total - start
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        toc = [pdf.pages[i] for i in range(start, total)]
        for _ in range(count):
            del pdf.pages[start]
        for k, page in enumerate(toc):
            pdf.pages.insert(k, page)
        pdf.Root.PageLabels = pikepdf.Dictionary(
            Nums=pikepdf.Array([0, pikepdf.Dictionary(S=pikepdf.Name.r), count, pikepdf.Dictionary(S=pikepdf.Name.D, St=1)]))
        pdf.save(path)
    return count


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    outputs = []
    margin = f"{o.margenes_mm * MM_TO_PT:.1f}"
    title = TOC_TITLE.get(ctx.locale, TOC_TITLE["es"])
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        ext = (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()
        check_book(inp.path, ext)
        work = ctx.work / f"libro-{n}"
        work.mkdir(parents=True, exist_ok=True)
        src = work / f"libro.{ext}"
        src.write_bytes(inp.path.read_bytes())
        tmp = work / "libro.pdf"
        args = ["ebook-convert", str(src), str(tmp), "--paper-size", PAPER.get(o.papel, "a5"),
                "--pdf-page-margin-left", margin, "--pdf-page-margin-right", margin,
                "--pdf-page-margin-top", margin, "--pdf-page-margin-bottom", margin,
                "--base-font-size", str(o.tamano_letra), "--pdf-default-font-size", str(o.tamano_letra),
                "--disable-remove-fake-margins"]
        if o.indice:
            args += ["--pdf-add-toc", "--toc-title", title]
        env = {"QT_QPA_PLATFORM": "offscreen", "CALIBRE_CONFIG_DIRECTORY": str(work / "config"), "CALIBRE_TEMP_DIR": str(work),
               "CALIBRE_CACHE_DIRECTORY": str(work / "cache"), "QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox --disable-gpu"}
        # Memoria de datos y no virtual: QtWebEngine reserva mucho espacio de direcciones y con RLIMIT_AS no arranca (D-52).
        run_engine(args, cwd=work, timeout=900, mem_mb=1536, extra_env=env, limit_data=True)
        if not tmp.exists():
            raise ToolError(ErrorCode.ENGINE_FAILED, "Calibre no generó el PDF")
        with pikepdf.open(tmp) as pdf:
            if len(pdf.pages) > ctx.plan.pdf_pages:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{len(pdf.pages)} páginas")
        if o.indice:
            toc_to_front(tmp, title)
        name = derived_name(inp.name, "", "pdf")
        dst = ctx.output(name)
        dst.write_bytes(tmp.read_bytes())
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "libros-pdf.zip")
