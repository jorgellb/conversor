"""Documentos con pandoc (7.12, F6-A, D-212 y D-216): docx, odt, Markdown y HTML.

pandoc 3.13 estático, como proceso externo (GPL, 11) y siempre con `--sandbox` (12.3): no lee más archivos que los de su
línea de órdenes ni sale a la red. Un Markdown o un HTML suelto va directo a pandoc, que deja fuera las imágenes que no
puede leer. Con un ZIP, el documento pasa por el árbol JSON de pandoc y aquí se cambian por URI `data:` las imágenes que
están dentro del ZIP (PNG, JPEG o GIF por sus bytes; TIFF, BMP y WebP se pasan a PNG), cada una leída una sola vez y con
un tope de bytes que cuenta todas sus referencias. Lo de fuera del ZIP no se carga nunca y se avisa.
"""
from __future__ import annotations

import base64
import io
import json
import posixpath
import re
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from core.errors import ErrorCode, ToolError
from core.zipguard import check_zip
from tools.base import ToolContext, derived_name, run_engine, zip_files
from tools.office.chromium_a_pdf import decode_text
from tools.pdf.common import with_batch_zip

TIMEOUT = 240
MEM_MB = 1536
# El montón de Haskell por debajo del límite del proceso: un documento enorme acaba con un error propio (código 251)
# en lugar de un SIGKILL sin explicación.
RTS = ["+RTS", "-M1024m", "-RTS"]
# Texto de un Markdown o un HTML. Dentro de un ZIP pasa por el árbol JSON en Python, que ocupa cientos de veces el texto:
# ahí el límite es menor (D-216).
MAX_TEXT_BYTES = 10 * 1024 * 1024
MAX_ZIP_TEXT_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_EMBED_BYTES = 60 * 1024 * 1024  # suma de todas las referencias: una imagen usada 100 veces cuenta 100
MAX_IMAGES = 500
# Office (12.3): 500 MB descomprimidos; y lo que pandoc escribiría al repetir cada imagen en cada referencia.
MAX_OFFICE_UNCOMPRESSED = 500 * 1024 * 1024
MAX_OFFICE_EXPANDED = 300 * 1024 * 1024
WEB_TYPES = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg", b"GIF87a": "image/gif", b"GIF89a": "image/gif"}
CONVERTIBLE = (".tif", ".tiff", ".bmp", ".webp")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", *CONVERTIBLE)
MEDIA_DIR = "media"
# Códigos de salida de pandoc que significan «no se puede leer»: PandocSomeError (docx roto), PandocXMLError,
# PandocParseError y PandocParsecError.
UNREADABLE = (63, 44, 64, 65)

READERS = {"gfm": "gfm", "markdown": "markdown", "commonmark": "commonmark_x"}
WRITERS = {"gfm": "gfm", "markdown": "markdown", "commonmark": "commonmark_x"}

NOTES = {
    "es": {
        "missing": "{n} imagen(es) no se han incluido: solo se cargan las que van dentro del ZIP junto al documento, nunca de "
                   "la web ni de otras carpetas.",
        "missing_single": "{n} imagen(es) no se han incluido: sube un ZIP con el documento y sus imágenes para que entren.",
        "dropped": "{n} imagen(es) no eran PNG, JPEG, GIF, TIFF, BMP ni WebP válidos o pasaban de 10 MB y se han dejado fuera.",
        "too_many": "{n} imagen(es) no se han incluido porque las imágenes del documento ya sumaban 60 MB.",
        "unsupported": "{n} imagen(es) en un formato que no se puede incluir (EMF, WMF u otro) se han quedado en su texto alternativo.",
    },
    "en": {
        "missing": "{n} image(s) were not included: only images inside the ZIP next to the document are loaded, never from "
                   "the web or other folders.",
        "missing_single": "{n} image(s) were not included: upload a ZIP with the document and its images to include them.",
        "dropped": "{n} image(s) were not valid PNG, JPEG, GIF, TIFF, BMP or WebP files or exceeded 10 MB and were left out.",
        "too_many": "{n} image(s) were not included because the document's images already added up to 60 MB.",
        "unsupported": "{n} image(s) in a format that cannot be included (EMF, WMF or other) were replaced by their alt text.",
    },
}


def pandoc(ctx: ToolContext, args: list[str]) -> str:
    """pandoc con `--sandbox` en el directorio del trabajo; devuelve sus avisos (que no se enseñan tal cual)."""
    exe = Path(ctx.settings.PANDOC_BIN)
    if not exe.is_file():
        raise ToolError(ErrorCode.ENGINE_FAILED, "pandoc no está instalado")
    result = run_engine([str(exe), *RTS, "--sandbox", *args], cwd=ctx.work, timeout=TIMEOUT, mem_mb=MEM_MB,
                        ok_codes=tuple(range(256)))
    err = result.stderr.decode("utf-8", errors="replace")
    if result.returncode == 0:
        return err
    if result.returncode == 251 or "Heap exhausted" in err:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "pandoc_memory")
    if result.returncode in UNREADABLE:
        raise ToolError(ErrorCode.CORRUPT_FILE, "pandoc no ha podido leerlo")
    raise ToolError(ErrorCode.ENGINE_FAILED, f"pandoc terminó con código {result.returncode}")


def _web_type(data: bytes) -> str | None:
    return next((mime for magic, mime in WEB_TYPES.items() if data.startswith(magic)), None)


def web_image(ctx: ToolContext, data: bytes, name: str) -> tuple[bytes, str] | None:
    """(bytes, MIME) que Word, los navegadores y GitHub muestran: PNG, JPEG y GIF tal cual; TIFF, BMP y WebP pasados a PNG
    con el límite de píxeles (12.3). None si no es ninguno de ellos o pasa de 10 MB."""
    if len(data) > MAX_IMAGE_BYTES:
        return None
    mime = _web_type(data)
    if mime:
        return data, mime
    if not name.lower().endswith(CONVERTIBLE):
        return None
    from PIL import Image, UnidentifiedImageError

    from tools.base import open_image

    path = ctx.work / "conv-imagen.bin"
    path.write_bytes(data)
    try:
        with open_image(path, ctx.settings.IMAGE_MAX_PIXELS) as img:
            img.seek(0)
            buf = io.BytesIO()
            img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB").save(buf, "PNG", optimize=True)
    except (UnidentifiedImageError, OSError, ValueError, ToolError):
        return None
    finally:
        path.unlink(missing_ok=True)
    return buf.getvalue(), "image/png"


# --- Árbol JSON de pandoc -------------------------------------------------------------------------------------------


def _images(tree) -> list[dict]:
    """Cada nodo Image (`{"t": "Image", "c": [attr, alt, [url, title]]}`), recorriendo el árbol sin recursión: un
    documento con miles de niveles de listas o citas no agota la pila de Python."""
    found, stack = [], [tree]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("t") == "Image":
                found.append(node)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


def _without_empty_images(tree: dict) -> None:
    """Una imagen sin destino se queda en su texto alternativo (pandoc avisaría y la dejaría rota). Sin recursión."""
    stack = [tree]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            if any(isinstance(i, dict) and i.get("t") == "Image" and not i["c"][2][0] for i in node):
                node[:] = [x for i in node for x in (i["c"][1] if isinstance(i, dict) and i.get("t") == "Image"
                                                     and not i["c"][2][0] else [i])]
            stack.extend(node)


def _load_tree(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except RecursionError as exc:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_too_deep") from exc


def _save_tree(path: Path, tree: dict) -> None:
    try:
        path.write_text(json.dumps(tree), encoding="utf-8")
    except RecursionError as exc:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_too_deep") from exc


def _local_target(url: str) -> str | None:
    """Ruta relativa dentro del documento, o None si es web, `file:`, `data:` o absoluta."""
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or url.startswith(("/", "\\")):
        return None
    path = unquote(parts.path).replace("\\", "/")
    return path or None


class ZipImages:
    """Las imágenes de un ZIP, leídas solo cuando el documento las usa y una sola vez cada una."""

    def __init__(self, ctx: ToolContext, path: Path, entries: dict[str, zipfile.ZipInfo]):
        self.ctx, self.path, self.entries = ctx, path, entries
        self.cache: dict[str, tuple[str, int] | None] = {}

    def data_uri(self, key: str) -> tuple[str, int] | None | bool:
        """(URI, bytes), None si no vale, False si no está en el ZIP."""
        info = self.entries.get(key)
        if info is None or not key.lower().endswith(IMAGE_EXTS):
            return False
        if key not in self.cache:
            image = None
            if info.file_size <= MAX_IMAGE_BYTES and len(self.cache) < MAX_IMAGES:
                with zipfile.ZipFile(self.path) as zf:
                    image = web_image(self.ctx, zf.read(info), key)
            self.cache[key] = (f"data:{image[1]};base64,{base64.b64encode(image[0]).decode()}", len(image[0])) if image else None
        return self.cache[key]


def embed_images(tree: dict, base: str, images: ZipImages | None) -> dict[str, int]:
    """Cambia cada imagen del ZIP por su URI `data:`; las demás quedan sin destino. Las `data:` del documento solo se
    conservan si son PNG, JPEG o GIF. Devuelve los recuentos para las notas."""
    counts = {"missing": 0, "dropped": 0, "too_many": 0}
    total = 0
    for node in _images(tree):
        url = node["c"][2][0]
        if url.startswith("data:"):
            if not re.match(r"data:image/(png|jpeg|gif)[;,]", url):
                node["c"][2][0] = ""
                counts["dropped"] += 1
            continue
        target = _local_target(url)
        key = posixpath.normpath(posixpath.join(base, target)) if target else ""
        found = images.data_uri(key) if images and key and not key.startswith("../") else False
        node["c"][2][0] = ""
        if found is False:
            counts["missing"] += 1
        elif found is None:
            counts["dropped"] += 1
        elif total + found[1] > MAX_EMBED_BYTES:
            counts["too_many"] += 1
        else:
            total += found[1]
            node["c"][2][0] = found[0]
    return counts


# --- Entradas ------------------------------------------------------------------------------------------------------


def _members(path: Path) -> dict[str, zipfile.ZipInfo]:
    check_zip(path)
    with zipfile.ZipFile(path) as zf:
        entries = {}
        for info in zf.infolist():
            parts = [p for p in info.filename.replace("\\", "/").split("/") if p not in ("", ".")]
            if info.is_dir() or not parts or ".." in parts or parts[0] == "__MACOSX" or any(p.startswith(".") for p in parts):
                continue
            entries["/".join(parts)] = info
    return entries


def document_from_zip(path: Path, exts: tuple[str, ...], names: tuple[str, ...]) -> tuple[str, bytes, dict[str, zipfile.ZipInfo]]:
    """El documento principal de un ZIP (el de `names` o el menos profundo), su texto y las entradas del ZIP."""
    entries = _members(path)
    docs = [n for n in entries if n.lower().endswith(exts)]
    if not docs:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "zip_no_document")
    main = min(docs, key=lambda n: (n.count("/"), posixpath.basename(n).lower() not in names, n))
    if entries[main].file_size > MAX_ZIP_TEXT_BYTES:  # antes de leerlo: el ZIP puede descomprimir mucho más
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Documento de más de 2 MB dentro del ZIP")
    with zipfile.ZipFile(path) as zf:
        text = zf.read(entries[main])
    return main, text, entries


def _input_ext(inp) -> str:
    return (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()


def check_office_expansion(path: Path, ext: str) -> None:
    """Lo que pandoc escribiría al copiar cada imagen en cada sitio donde se usa (su escritor ODT y el Markdown con
    carpeta no comparten las repetidas): suma de tamaño × referencias, con un tope."""
    with zipfile.ZipFile(path) as zf:
        sizes = {i.filename: i.file_size for i in zf.infolist()}
        if ext == "docx":
            refs: dict[str, int] = {}
            for name in [n for n in sizes if re.fullmatch(r"word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml", n)]:
                rels_name = f"word/_rels/{posixpath.basename(name)}.rels"
                if rels_name not in sizes:
                    continue
                rels = zf.read(rels_name).decode("utf-8", "replace")
                targets = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
                targets.update({k: v for v, k in re.findall(r'Target="([^"]+)"[^>]*Id="([^"]+)"', rels)})
                for rid in re.findall(r'r:(?:embed|link)="([^"]+)"', zf.read(name).decode("utf-8", "replace")):
                    target = targets.get(rid)
                    if target:
                        key = posixpath.normpath(posixpath.join("word", target))
                        refs[key] = refs.get(key, 0) + 1
        else:
            content = zf.read("content.xml").decode("utf-8", "replace") if "content.xml" in sizes else ""
            refs = {}
            for href in re.findall(r'xlink:href="([^"]+)"', content):
                refs[href] = refs.get(href, 0) + 1
    if sum(sizes.get(k, 0) * n for k, n in refs.items()) > MAX_OFFICE_EXPANDED:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "pandoc_memory")


# --- Conversiones --------------------------------------------------------------------------------------------------


def _office_input(ctx: ToolContext, inp, ext: str, n: int) -> Path:
    """docx y odt son ZIP: se comprueban (bomba, rutas, 500 MB de 12.3 y las imágenes repetidas) antes de dárselos a
    pandoc, con un nombre fijo y sin espacios."""
    check_zip(inp.path, max_uncompressed=MAX_OFFICE_UNCOMPRESSED)
    try:
        check_office_expansion(inp.path, ext)
    except zipfile.BadZipFile as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, ext) from exc
    ctx.work.mkdir(parents=True, exist_ok=True)
    src = ctx.work / f"entrada-{n}.{ext}"
    src.write_bytes(inp.path.read_bytes())
    return src


def _read_markdown(ctx: ToolContext, reader: str, src: Path, out: Path, extra: list[str]) -> str:
    """pandoc con el Markdown; si su bloque YAML inicial no es válido (un «---» seguido de «Hora: 10:30»), se lee otra vez
    sin metadatos en lugar de fallar."""
    args = [str(src.name), "-o", str(out.name), *extra]
    try:
        return pandoc(ctx, ["-f", reader, *args])
    except ToolError as err:
        if err.code != ErrorCode.CORRUPT_FILE or reader == "html":
            raise
        return pandoc(ctx, ["-f", f"{reader}-yaml_metadata_block", *args])


def _text_to_docx(ctx: ToolContext, inp, reader: str, kind: str, extra: list[str], n: int) -> tuple[Path, list[str]]:
    """Markdown o HTML a docx. Suelto, directo; en un ZIP con sus imágenes, pasando por el árbol JSON."""
    t = NOTES.get(ctx.locale, NOTES["es"])
    ctx.work.mkdir(parents=True, exist_ok=True)
    src = ctx.work / f"entrada-{n}.{kind}"
    out = src.with_suffix(".docx")
    if _input_ext(inp) != "zip":
        if inp.path.stat().st_size > MAX_TEXT_BYTES:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Texto de más de 10 MB")
        src.write_text(decode_text(inp.path.read_bytes()), encoding="utf-8")
        warnings = _read_markdown(ctx, reader, src, out, extra)
        missing = len(re.findall(r"Could not fetch resource", warnings))
        return out, [t["missing_single"].format(n=missing)] if missing else []
    exts, names = ((".md", ".markdown"), ("readme.md", "index.md")) if kind == "md" else ((".html", ".htm"), ("index.html", "index.htm"))
    main, raw, entries = document_from_zip(inp.path, exts, names)
    src.write_text(decode_text(raw), encoding="utf-8")
    ast = src.with_suffix(".json")
    _read_markdown(ctx, reader, src, ast, ["-t", "json"])
    tree = _load_tree(ast)
    counts = embed_images(tree, posixpath.dirname(main), ZipImages(ctx, inp.path, entries))
    _without_empty_images(tree)
    _save_tree(ast, tree)
    del tree
    pandoc(ctx, ["-f", "json", str(ast.name), "-o", str(out.name), *extra])
    return out, [t[key].format(n=v) for key, v in counts.items() if v]


def _docx_to_markdown(ctx: ToolContext, src: Path, writer: str, imagenes: str, stem: str) -> tuple[Path, str, list[str]]:
    """docx a Markdown; con imágenes, ZIP con el .md y la carpeta media/ (una vez cada imagen, aunque se use en varios
    sitios), dentro del .md como `data:` (con el mismo tope que las entradas) o fuera."""
    t = NOTES.get(ctx.locale, NOTES["es"])
    media = ctx.work / f"media-{src.stem}"
    ast = src.with_suffix(".json")
    pandoc(ctx, ["-f", "docx", str(src.name), "-t", "json", f"--extract-media={media.name}", "-o", str(ast.name)])
    tree = _load_tree(ast)
    files: dict[Path, str] = {}  # archivo extraído → nombre en el ZIP
    uris: dict[Path, str | None] = {}
    counts = {"unsupported": 0, "too_many": 0}
    inlined = 0
    for node in _images(tree):
        node["c"][0] = ["", [], []]  # sin ancho ni alto: Markdown limpio (`![alt](media/…)`) en lugar de una etiqueta <img>
        url = node["c"][2][0]
        node["c"][2][0] = ""
        local = (ctx.work / url).resolve() if _local_target(url) else None
        if imagenes == "omitir" or not local or not local.is_relative_to(media.resolve()) or not local.is_file():
            continue
        if local not in uris:
            image = web_image(ctx, local.read_bytes(), local.name)
            if image is None and local.suffix.lower() == ".svg" and local.stat().st_size <= MAX_IMAGE_BYTES:
                image = (local.read_bytes(), "image/svg+xml")
            if image is None:
                uris[local] = None
            elif imagenes == "incrustadas":
                uris[local] = f"data:{image[1]};base64,{base64.b64encode(image[0]).decode()}"
            else:
                ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/svg+xml": ".svg"}[image[1]]
                name = f"{MEDIA_DIR}/imagen-{len(files) + 1}{ext}"
                stored = ctx.work / f"{src.stem}-{len(files) + 1}{ext}"
                stored.write_bytes(image[0])
                files[local] = name
                uris[local] = name
        target = uris.get(local)
        if target is None:
            counts["unsupported"] += 1
        elif target.startswith("data:"):
            if inlined + len(target) > MAX_EMBED_BYTES:
                counts["too_many"] += 1
            else:
                inlined += len(target)
                node["c"][2][0] = target
        else:
            node["c"][2][0] = target
    _without_empty_images(tree)
    _save_tree(ast, tree)
    del tree
    md = ctx.work / f"{src.stem}.md"
    pandoc(ctx, ["-f", "json", str(ast.name), "-t", writer, "--wrap=none", "-o", str(md.name)])
    notes = [t[key].format(n=v) for key, v in counts.items() if v]
    if not files:
        return md, "md", notes
    packed = ctx.work / f"{src.stem}.zip"
    stored = {name: ctx.work / f"{src.stem}-{i}{Path(name).suffix}" for i, name in enumerate(files.values(), 1)}
    zip_files([(md, f"{stem}.md"), *((path, name) for name, path in stored.items())], packed)
    return packed, "zip", notes


def run(ctx: ToolContext) -> list[dict]:
    slug, o = ctx.tool, ctx.options
    outputs: list[dict] = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        stem = Path(inp.name).stem or "documento"
        notes: list[str] = []
        if slug in ("docx-a-odt", "odt-a-docx", "docx-a-html"):
            ext_in = "odt" if slug == "odt-a-docx" else "docx"
            src = _office_input(ctx, inp, ext_in, n)
            if slug == "docx-a-html":
                out, ext = src.with_suffix(".html"), "html"
                args = ["-s", "--embed-resources", "--math-method=mathml", "--metadata", f"pagetitle={stem}",
                        *(["--toc"] if o.indice else [])]
            else:
                ext = "docx" if slug == "odt-a-docx" else "odt"
                out, args = src.with_suffix(f".{ext}"), []
            pandoc(ctx, ["-f", ext_in, str(src.name), "-o", str(out.name), *args])
        elif slug == "docx-a-markdown":
            src = _office_input(ctx, inp, "docx", n)
            out, ext, notes = _docx_to_markdown(ctx, src, WRITERS[o.sabor], o.imagenes, stem)
        elif slug in ("markdown-a-docx", "html-a-docx"):
            extra = [*(["--toc"] if o.indice else []), *(["--number-sections"] if getattr(o, "numerar", False) else [])]
            if slug == "markdown-a-docx":
                out, notes = _text_to_docx(ctx, inp, READERS[o.sabor], "md", extra, n)
            else:
                out, notes = _text_to_docx(ctx, inp, "html", "html", extra, n)
            ext = "docx"
        else:  # pragma: no cover - el registro solo apunta aquí estas seis
            raise ToolError(ErrorCode.INVALID_OPTIONS, slug)
        name = derived_name(inp.name, "", ext)
        dst = ctx.output(name)
        dst.write_bytes(out.read_bytes())
        outputs.append({"path": str(dst), "name": name, "note": " ".join(notes) or None})
    return with_batch_zip(ctx, outputs, f"{slug}.zip")
