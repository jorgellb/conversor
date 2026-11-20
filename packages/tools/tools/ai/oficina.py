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
import shutil
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
MAX_PART = 16 * 1024 * 1024
MAX_PARSED = 24 * 1024 * 1024
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
    """Los párrafos de una parte con sus tramos, recorridos en orden (D-243):
    - un salto (`w:br`, `w:tab`, `a:br`…) cierra el tramo, esté dentro de la ejecución o al lado;
    - los campos no se traducen y cierran el tramo: en Word, el resultado entre `fldChar` separate y end y lo de dentro
      de `w:fldSimple` (números de página, referencias, numeración de figuras); en PowerPoint, `a:fld` (número de
      diapositiva, fecha);
    - un cuadro de texto de Word tiene sus propios párrafos dentro de una ejecución: se leen aparte, como párrafos suyos;
    - en Excel solo cuentan el `t` directo y las ejecuciones `r` de la cadena (nunca la fonética `rPh`)."""
    out = []
    tag_p, tag_r, tag_t = _q(kind.ns, kind.paragraph), _q(kind.ns, kind.run), _q(kind.ns, kind.text)
    breaks = {_q(kind.ns, b) for b in kind.breaks}
    fields = {_q(W, "fldSimple"), _q(A, "fld")}
    fld_char, fld_type = _q(W, "fldChar"), _q(W, "fldCharType")
    is_excel = kind.ns == S
    containers = [*root.iter(tag_p), *root.iter(_q(S, "is"))] if is_excel else root.iter(tag_p)
    for p in containers:
        para = Paragraph()
        state = {"current": [], "key": None, "field": 0}

        def boundary() -> None:
            if state["current"]:
                para.groups.append(state["current"])
            state["current"], state["key"] = [], None

        def text(t, key: bytes) -> None:
            if state["field"]:
                return
            if state["key"] is not None and key != state["key"]:
                boundary()
            state["current"].append(t)
            state["key"] = key

        def run(r) -> None:
            props = r.find(_q(kind.ns, kind.props))
            key = etree.tostring(props) if props is not None else b""
            for child in r:
                if child.tag == tag_t:
                    text(child, key)
                elif child.tag in breaks:
                    boundary()
                elif child.tag == fld_char:
                    kind_ = child.get(fld_type)
                    boundary()
                    if kind_ == "begin":
                        state["field"] += 1
                    elif kind_ == "end" and state["field"]:
                        state["field"] -= 1

        def walk(el) -> None:
            for child in el:
                if child.tag == tag_p:
                    continue  # párrafo anidado (cuadro de texto): se lee como párrafo propio
                if child.tag == tag_r:
                    run(child)
                elif child.tag == tag_t and is_excel:
                    text(child, b"")
                elif child.tag in breaks:
                    boundary()
                elif child.tag in fields:
                    boundary()  # su contenido es el resultado del campo: no se traduce
                elif not is_excel and isinstance(child.tag, str):
                    walk(child)  # hipervínculos, revisiones, controles de contenido, etiquetas inteligentes…

        walk(p)
        boundary()
        if para.groups:
            out.append(para)
    return out


ANY_TAG = re.compile(r"</?\d{1,3}>")
NOT_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff\ud800-\udfff]")


def _ids_once(translated: str, n: int) -> dict[int, str] | None:
    """Cada tramo una vez y solo una, sin etiquetas anidadas; si no, None (va todo al primer tramo)."""
    ids = [int(m) for m in re.findall(r"<(\d{1,3})>", translated)]
    if sorted(ids) != list(range(n)):
        return None
    found = {int(m.group(1)): m.group(2) for m in TAG.finditer(translated)}
    if sorted(found) != list(range(n)) or any(ANY_TAG.search(v) for v in found.values()):
        return None
    return found


def apply(para: Paragraph, translated: str) -> None:
    """Pone la traducción en los tramos. Cada tramo recupera los espacios de sus bordes del original (el modelo los
    suele recortar y «Hola **mundo** ya» quedaría pegado), y nunca queda una etiqueta suelta en el documento."""
    translated = NOT_XML.sub("", translated)
    originals = para.texts()
    n = len(para.groups)
    pieces: list[str] | None = None
    if n > 1 and (found := _ids_once(translated, n)) is not None:
        pieces = [found[i] for i in range(n)]
        # Lo que el modelo deje fuera de las etiquetas («[inglés] » del proveedor falso) va al primer tramo.
        outside = TAG.sub("", translated).strip()
        if outside:
            pieces[0] = f"{outside} {pieces[0]}"
    if pieces is None:
        pieces = [ANY_TAG.sub("", translated)] + [""] * (n - 1)
        originals = ["".join(originals)] + [""] * (n - 1)
    for group, text, original in zip(para.groups, pieces, originals):
        if text and original:
            lead = original[:len(original) - len(original.lstrip())]
            trail = original[len(original.rstrip()):]
            text = lead + text.strip() + trail
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
    fixed: set[str] = field(default_factory=set)  # textos que no se traducen (encabezados de tablas de Excel)


def _parse(raw: bytes, name: str):
    tree = etree.ElementTree(etree.fromstring(raw, PARSER))
    # Sin DOCTYPE ni entidades (Office nunca los usa): se mira el documento ya leído, no los primeros bytes (D-243).
    if tree.docinfo.doctype or tree.docinfo.internalDTD is not None:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities")
    return tree


def _table_names(zf: zipfile.ZipFile) -> set[str]:
    """Nombres de las columnas de las tablas y de los campos de las tablas dinámicas de Excel: sus celdas de encabezado
    no se traducen, porque las fórmulas (Tabla1[Nombre]) y las definiciones los usan tal cual (D-243)."""
    names: set[str] = set()
    for info in zf.infolist():
        if re.match(r"^xl/(tables/table\d+|pivotCache/pivotCacheDefinition\d+)\.xml$", info.filename) and info.file_size < MAX_PART:
            root = _parse(zf.read(info), info.filename).getroot()
            for el in root.iter(_q(S, "tableColumn"), _q(S, "cacheField")):
                if el.get("name"):
                    names.add(el.get("name"))
    return names


def read(path: Path, kind: Kind) -> Document:
    """Las partes con texto, analizadas. Memoria acotada (D-243): cada parte, como mucho 16 MB de XML, y todas juntas
    24 MB (un árbol de lxml ocupa unas 25 veces lo que el XML); las hojas de Excel sin cadenas propias (`inlineStr`) ni
    se analizan."""
    check_zip(path)
    doc = Document(path, kind)
    parsed = 0
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                language_only = kind.ns == W and info.filename == "word/styles.xml"
                if not kind.parts.match(info.filename) and not language_only:
                    continue
                if info.file_size > MAX_PART:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{info.filename} de más de {MAX_PART // 1024 // 1024} MB")
                raw = zf.read(info)
                if info.filename.startswith("xl/worksheets/") and b"inlineStr" not in raw:
                    continue
                parsed += len(raw)
                if parsed > MAX_PARSED:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Documento demasiado grande para traducirlo")
                tree = _parse(raw, info.filename)
                doc.parts[info.filename] = tree
                if not language_only:
                    doc.paragraphs += paragraphs_of(tree.getroot(), kind)
            if kind.ns == S:
                doc.fixed = _table_names(zf)
    except (zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, f"{kind.ext} ilegible") from exc
    if not doc.paragraphs and not doc.parts:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, f"No es un {kind.ext.upper()}")
    return doc


def write(doc: Document, dst: Path) -> None:
    """El mismo ZIP con las partes traducidas; el resto de miembros se copia por trozos, sin cargarlo entero (un PPTX con
    vídeos dentro puede pesar cientos de MB)."""
    with zipfile.ZipFile(doc.path) as src, zipfile.ZipFile(dst, "w") as out:
        for info in src.infolist():
            if info.filename in doc.parts:
                data = etree.tostring(doc.parts[info.filename], xml_declaration=True, encoding="UTF-8", standalone=True)
                out.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
            else:
                copy = zipfile.ZipInfo(info.filename, info.date_time)
                copy.compress_type, copy.external_attr, copy.comment = info.compress_type, info.external_attr, info.comment
                with src.open(info) as fin, out.open(copy, "w", force_zip64=info.file_size > 2**31) as fout:
                    shutil.copyfileobj(fin, fout, 1024 * 1024)


def sources(doc: Document, batch_chars: int) -> tuple[list[str], dict[str, list[Paragraph]]]:
    """Textos que se mandan (sin repetidos ni párrafos sin letras) y los párrafos de cada uno. Un párrafo con tramos más
    largo que un lote va sin etiquetas: el traductor lo partiría por frases y las rompería."""
    unique: dict[str, list[Paragraph]] = {}
    for para in doc.paragraphs:
        plain = para.plain()
        if not LETTER.search(plain) or plain in doc.fixed:
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
    """Idioma del texto de Word (w:lang) para la ortografía y la lectura en voz alta: el de cada ejecución que lo diga y
    el predeterminado del documento (docDefaults de styles.xml), que es el que usan casi todos (D-243)."""
    styles = doc.parts.get("word/styles.xml")
    if styles is not None:
        defaults = styles.getroot().find(_q(W, "docDefaults"))
        if defaults is None:
            defaults = etree.Element(_q(W, "docDefaults"))
            styles.getroot().insert(0, defaults)
        rpr_default = defaults.find(_q(W, "rPrDefault"))
        if rpr_default is None:
            rpr_default = etree.SubElement(defaults, _q(W, "rPrDefault"))
        rpr = rpr_default.find(_q(W, "rPr"))
        if rpr is None:
            rpr = etree.SubElement(rpr_default, _q(W, "rPr"))
        if rpr.find(_q(W, "lang")) is None:
            etree.SubElement(rpr, _q(W, "lang"))
    for tree in doc.parts.values():
        for lang in tree.getroot().iter(_q(W, "lang")):
            lang.set(_q(W, "val"), language)
