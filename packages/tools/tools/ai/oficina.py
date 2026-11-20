"""traducir-word, traducir-excel y traducir-powerpoint (7.6, 6.3, F6-D, D-239): traducen el texto de un DOCX, un XLSX o
un PPTX conservando el formato.

Se trabaja sobre el XML de Office dentro del ZIP y solo se cambian los textos (`w:t`, `t` y `a:t`): imágenes, gráficos,
tablas, estilos, fórmulas, comentarios y todo lo demás se copian byte a byte. Cada párrafo (`w:p`, `a:p`, o una cadena
compartida `si` de Excel) se parte en tramos de texto con el mismo formato; un salto o un tabulador cierra el tramo. Si el
párrafo tiene varios tramos, van marcados con etiquetas numeradas (<0>…</0>) para que el modelo los conserve y cada uno
vuelve a su sitio con su formato; si el modelo las rompe, el párrafo traducido entero va al primer tramo. Un párrafo sin
letras (cifras, códigos) no se manda; los repetidos se mandan una vez.
Partes: Word, el documento, encabezados, pies, notas al pie y finales (los cuadros de texto van dentro del documento);
PowerPoint, las diapositivas y sus notas; Excel, las cadenas compartidas y las de dentro de las celdas (las fórmulas y
los nombres de las hojas no se tocan, porque las fórmulas los usan).
"""
from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from core.ai.translate import LLMTranslator
from core.errors import ErrorCode, ToolError
from core.zipguard import check_zip
from tools.ai import comun
from tools.base import ToolContext, derived_name

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
MAX_CHARS = 400_000  # texto que se traduce en una tarea (unas 150 páginas)
MAX_PART = 60 * 1024 * 1024
LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
TAG = re.compile(r"<(\d{1,3})>(.*?)</\1>", re.S)
PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_blank_text=False)


@dataclass(frozen=True)
class Kind:
    ext: str
    ns: str
    paragraph: str
    run: str
    text: str
    props: str
    breaks: tuple[str, ...]
    parts: re.Pattern


KINDS = {
    "traducir-word": Kind("docx", W, "p", "r", "t", "rPr", ("tab", "br", "cr", "ptab"),
                          re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$")),
    "traducir-powerpoint": Kind("pptx", A, "p", "r", "t", "rPr", ("br",),
                                re.compile(r"^ppt/(slides/slide\d+|notesSlides/notesSlide\d+)\.xml$")),
    "traducir-excel": Kind("xlsx", S, "si", "r", "t", "rPr", (), re.compile(r"^xl/(sharedStrings|worksheets/sheet\d+)\.xml$")),
}


@dataclass
class Paragraph:
    groups: list[list[etree._Element]] = field(default_factory=list)  # tramos: los elementos de texto de cada uno

    def texts(self) -> list[str]:
        return ["".join(t.text or "" for t in g) for g in self.groups]

    def source(self) -> str:
        texts = self.texts()
        if len(texts) == 1:
            return texts[0]
        return "".join(f"<{i}>{t}</{i}>" for i, t in enumerate(texts))

    def plain(self) -> str:
        return "".join(self.texts())


def _q(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def paragraphs_of(root, kind: Kind) -> list[Paragraph]:
    """Los párrafos de una parte con sus tramos. En Word, un cuadro de texto tiene sus propios párrafos dentro de un
    tramo del párrafo de fuera: cada elemento de texto pertenece solo a su párrafo más cercano."""
    out = []
    tag_p, tag_r, tag_t = _q(kind.ns, kind.paragraph), _q(kind.ns, kind.run), _q(kind.ns, kind.text)
    breaks = {_q(kind.ns, b) for b in kind.breaks}
    is_excel = kind.ns == S
    containers = root.iter(tag_p) if not is_excel else (
        [*root.iter(tag_p), *(c for c in root.iter(_q(S, "is")))])
    for p in containers:
        para = Paragraph()
        current: list[etree._Element] = []
        key = None
        if is_excel and p.find(tag_t) is not None and p.find(tag_r) is None:
            # Cadena sin formato propio: un solo tramo.
            para.groups = [[p.find(tag_t)]]
            out.append(para)
            continue
        for r in p.iter(tag_r):
            owner = next((a for a in r.iterancestors(tag_p, _q(S, "is")) if True), None)
            if owner is not p:
                continue
            props = r.find(_q(kind.ns, kind.props))
            run_key = etree.tostring(props) if props is not None else b""
            for child in r:
                if child.tag == tag_t:
                    if key is not None and run_key != key and current:
                        para.groups.append(current)
                        current = []
                    current.append(child)
                    key = run_key
                elif child.tag in breaks and current:
                    para.groups.append(current)
                    current = []
                    key = None
        if current:
            para.groups.append(current)
        if para.groups:
            out.append(para)
    return out


def apply(para: Paragraph, translated: str) -> None:
    n = len(para.groups)
    pieces: list[str | None] = [None] * n
    if n > 1:
        found = {int(m.group(1)): m.group(2) for m in TAG.finditer(translated)}
        if sorted(found) == list(range(n)):
            pieces = [found[i] for i in range(n)]
            # Lo que el modelo deje fuera de las etiquetas («[inglés] » del proveedor falso) va al primer tramo.
            outside = TAG.sub("", translated).strip()
            if outside:
                pieces[0] = f"{outside} {pieces[0]}"
    if n == 1 or pieces[0] is None:
        text = TAG.sub(lambda m: m.group(2), translated) if n > 1 else translated
        pieces = [text] + [""] * (n - 1)
    for group, text in zip(para.groups, pieces):
        first, *rest = group
        first.text = text
        if text and (text[0].isspace() or text[-1].isspace()):
            first.set(XML_SPACE, "preserve")
        for t in rest:
            t.text = ""


@dataclass
class Document:
    path: Path
    kind: Kind
    parts: dict[str, etree._ElementTree] = field(default_factory=dict)
    paragraphs: list[Paragraph] = field(default_factory=list)


def read(path: Path, kind: Kind) -> Document:
    check_zip(path)
    doc = Document(path, kind)
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if not kind.parts.match(info.filename):
                    continue
                if info.file_size > MAX_PART:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{info.filename} de más de 60 MB")
                raw = zf.read(info)
                if b"<!ENTITY" in raw[:4096] or b"<!DOCTYPE" in raw[:4096]:
                    raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities")
                tree = etree.ElementTree(etree.fromstring(raw, PARSER))
                doc.parts[info.filename] = tree
                doc.paragraphs += paragraphs_of(tree.getroot(), kind)
    except (zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, f"{kind.ext} ilegible") from exc
    if not doc.parts:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, f"No es un {kind.ext.upper()}")
    return doc


def write(doc: Document, dst: Path) -> None:
    """El mismo ZIP con las partes traducidas; el resto de miembros, tal cual (mimetype el primero y sin comprimir)."""
    with zipfile.ZipFile(doc.path) as src, zipfile.ZipFile(dst, "w") as out:
        for info in src.infolist():
            if info.filename in doc.parts:
                data = etree.tostring(doc.parts[info.filename], xml_declaration=True, encoding="UTF-8", standalone=True)
                out.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
            else:
                out.writestr(info, src.read(info), compress_type=info.compress_type)


def sources(doc: Document, batch_chars: int) -> tuple[list[str], dict[str, list[Paragraph]]]:
    """Textos que se mandan (sin repetidos ni párrafos sin letras) y los párrafos de cada uno. Un párrafo con tramos más
    largo que un lote va sin etiquetas: el traductor lo partiría por frases y las rompería."""
    unique: dict[str, list[Paragraph]] = {}
    for para in doc.paragraphs:
        plain = para.plain()
        if not LETTER.search(plain):
            continue
        src = para.source() if len(plain) < batch_chars else plain
        if src != para.source():
            para.groups = [[t for g in para.groups for t in g]]
        unique.setdefault(src, []).append(para)
    total = sum(len(s) for s in unique)
    if not unique:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "ai_empty")
    if total > MAX_CHARS:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{total} caracteres; como mucho {MAX_CHARS}")
    return list(unique), unique


SUFFIX = {"es": "-traducido-{code}", "en": "-translated-{code}"}
TEXTS = {"es": {"made": "Traducción hecha con IA ({model}). Puede tener errores: revísala antes de usarla.",
                "items": "{n} párrafos o celdas traducidos."},
         "en": {"made": "Translated with AI ({model}). It may contain errors: review it before using it.",
                "items": "{n} paragraphs or cells translated."}}


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    if o.origen != "auto" and o.origen == o.destino:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "ai_same_language")
    kind = KINDS[ctx.tool]
    t = TEXTS.get(ctx.locale, TEXTS["es"])
    inp = ctx.inputs[0]
    doc = read(inp.path, kind)
    translator = LLMTranslator(ctx.ai)
    items, where = sources(doc, int(translator.batch_tokens * 3))
    keep = [line.strip() for line in (o.glosario or "").splitlines() if line.strip()][:50]

    def make() -> dict:
        ctx.ai.budget.ensure(len(translator.plan(items)))
        out = translator.translate(items, o.destino, None if o.origen == "auto" else o.origen, keep,
                                   progress=lambda f: ctx.report(0.1 + 0.8 * f, None), markup=True)
        return {"traducciones": out, "model": (ctx.ai.models_used or [""])[-1]}

    digest = hashlib.sha256("\x00".join(items).encode("utf-8")).hexdigest()
    options = {"destino": o.destino, "origen": o.origen, "glosario": (o.glosario or "").strip(), "textos": digest}
    result, hit = comun.with_cache(ctx, ctx.tool, options, make)
    for src, translated in zip(items, result["traducciones"]):
        for para in where[src]:
            apply(para, translated)
    if kind.ns == W:
        _set_language(doc, comun.output_language(o.destino, ctx.locale))
    name = derived_name(inp.name, SUFFIX.get(ctx.locale, SUFFIX["es"]).format(code=o.destino), kind.ext)
    dst = ctx.output(name)
    write(doc, dst)
    note = " ".join(filter(None, [t["made"].format(model=result.get("model") or "IA"), t["items"].format(n=len(items)), comun.note(ctx, hit)]))
    return [{"path": str(dst), "name": name, "note": note}]


def _set_language(doc: Document, language: str) -> None:
    """Idioma del texto de Word (w:lang) para la ortografía y la lectura en voz alta."""
    for tree in doc.parts.values():
        for lang in tree.getroot().iter(_q(W, "lang")):
            lang.set(_q(W, "val"), language)
