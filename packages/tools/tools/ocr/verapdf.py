"""veraPDF (A.5 y A.6): ejecución, lectura del informe XML (MRR) y explicación de cada regla en lenguaje sencillo.

veraPDF es Java y corre como proceso externo en `workerocr` con entorno vacío, sin red y memoria de datos limitada
(la JVM reserva mucho espacio de direcciones, como Chromium; D-52). Devuelve 1 cuando el archivo no cumple.
"""
from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from defusedxml import ElementTree as SafeET

from core.errors import ErrorCode, ToolError
from tools.base import run_engine

FLAVOURS = ("1a", "1b", "2a", "2b", "2u", "3a", "3b", "3u", "4", "4e", "4f", "ua1", "ua2")
MAX_DISPLAYED = 50
PAGE = re.compile(r"pages\[(\d+)\]")


def flavour_label(flavour: str) -> str:
    if flavour.startswith("ua"):
        return f"PDF/UA-{flavour[2:]}"
    return f"PDF/A-{flavour}"


@dataclass
class Rule:
    specification: str
    clause: str
    test: str
    description: str
    obj: str
    tags: str
    failed: int
    pages: set[int] = field(default_factory=set)
    messages: list[str] = field(default_factory=list)


@dataclass
class Report:
    compliant: bool
    profile: str
    failed_rules: int
    failed_checks: int
    passed_rules: int
    rules: list[Rule]
    version: str = ""


def declared_flavour(path: Path) -> str | None:
    """Nivel que el propio archivo declara en su XMP (pdfaid y pdfuaid)."""
    import pikepdf

    try:
        with pikepdf.open(path) as pdf, pdf.open_metadata() as meta:
            part = str(meta.get("pdfaid:part", "") or "").strip()
            conformance = str(meta.get("pdfaid:conformance", "") or "").strip().lower()
            ua = ""
            try:
                ua = str(meta.get("{http://www.aiim.org/pdfua/ns/id/}part", "") or "").strip()
            except (KeyError, ValueError):
                ua = ""
    except pikepdf.PdfError:
        return None
    if part in ("1", "2", "3"):
        flavour = f"{part}{conformance or 'b'}"
        return flavour if flavour in FLAVOURS else f"{part}b"
    if part == "4":
        return f"4{conformance}" if conformance in ("e", "f") else "4"
    if ua in ("1", "2"):
        return f"ua{ua}"
    return None


def run_verapdf(path: Path, flavour: str, cwd: Path) -> bytes:
    exe = shutil.which("verapdf")
    if not exe:
        raise ToolError(ErrorCode.ENGINE_FAILED, "veraPDF no está instalado")
    env = {"JAVA_OPTS": f"-Xmx1536m -XX:+UseSerialGC -XX:-UsePerfData -Djava.awt.headless=true -Djava.io.tmpdir={cwd}"}
    proc = run_engine([exe, "--format", "mrr", "--flavour", flavour, "--maxfailuresdisplayed", str(MAX_DISPLAYED), str(path)],
                      cwd=cwd, timeout=900, mem_mb=2560, extra_env=env, limit_data=True, ok_codes=(0, 1))
    return proc.stdout


def parse_report(data: bytes) -> Report:
    try:
        root = SafeET.fromstring(data)
    except Exception as exc:  # noqa: BLE001 - salida inesperada del motor
        raise ToolError(ErrorCode.ENGINE_FAILED, "Informe de veraPDF ilegible") from exc
    version = next((r.get("version", "") for r in root.iter("releaseDetails") if r.get("id") in ("core", "gui", "apps")), "")
    vr = next(root.iter("validationReport"), None)
    if vr is None:
        message = " ".join((e.text or "") for e in root.iter("exceptionMessage")).lower()
        if "encrypt" in message or "password" in message:
            rule = Rule("ISO 19005", "6.1", "", "The file shall not be encrypted.", "CosDocument", "security", 1)
            return Report(False, "", 1, 1, 0, [rule], version)
        raise ToolError(ErrorCode.CORRUPT_FILE, "veraPDF no pudo leer el archivo")
    details = vr.find("details")
    rules: list[Rule] = []
    for r in (details.findall("rule") if details is not None else []):
        if r.get("status") != "failed":
            continue
        checks = [c for c in r.findall("check") if c.get("status") == "failed"]
        rule = Rule(specification=r.get("specification", ""), clause=r.get("clause", ""), test=r.get("testNumber", ""),
                    description=(r.findtext("description") or "").strip(), obj=(r.findtext("object") or "").strip(),
                    tags=r.get("tags", ""), failed=int(r.get("failedChecks") or len(checks) or 1))
        for c in checks:
            m = PAGE.search(c.findtext("context") or "")
            if m:
                rule.pages.add(int(m.group(1)) + 1)
            msg = (c.findtext("errorMessage") or "").strip()
            if msg and msg not in rule.messages and len(rule.messages) < 3:
                rule.messages.append(msg)
        rules.append(rule)
    rules.sort(key=lambda x: (-x.failed, x.clause))

    def num(name: str) -> int:
        return int(details.get(name, 0) or 0) if details is not None else 0

    compliant = vr.get("isCompliant", "false").lower() == "true"
    return Report(compliant, vr.get("profileName", ""), num("failedRules") or len(rules), num("failedChecks") or sum(r.failed for r in rules),
                  num("passedRules"), rules, version)


# --- Explicaciones en lenguaje sencillo -----------------------------------------------------------------------------

# Clasificación: primero las etiquetas de la regla, después la clase del objeto que comprueba veraPDF y por último la
# descripción con palabras completas («cross-reference table» no es una tabla etiquetada).
TAGS = {
    "font": "font", "fonts": "font", "metadata": "metadata", "structure": "structure", "tagged": "structure",
    "alt-text": "structure", "lang": "structure", "heading": "structure", "table": "structure", "list": "structure",
    "colorspace": "color", "color": "color", "outputintent": "color", "transparency": "transparency",
    "annotation": "annotation", "annotations": "annotation", "form": "annotation", "action": "action", "actions": "action",
    "javascript": "action", "embeddedfile": "embedded", "embeddedfiles": "embedded", "syntax": "syntax",
    "image": "image", "encryption": "security", "security": "security",
}
OBJECTS: list[tuple[str, tuple[str, ...]]] = [
    ("font", ("pdfont", "pdtype0font", "pdtype1font", "pdtype3font", "pdtruetypefont", "pdcidfont", "pdsimplefont", "glyph",
              "pdcmap", "cmapfile", "fontprogram")),
    ("metadata", ("mainxmppackage", "xmppackage", "pdfaidentification", "xmpproperty", "cosinfo", "pdmetadata", "infodictionary")),
    ("structure", ("pdstructtreeroot", "pdstructelem", "structelem", "pdmarkinfo")),
    ("color", ("pdoutputintent", "iccprofile", "iccinputprofile", "iccoutputprofile", "pddevicergb", "pddevicecmyk",
               "pddevicegray", "pdcolorspace", "pdiccbased", "pdseparation", "pddevicen")),
    ("transparency", ("pdextgstate", "pdgroup", "pdsmaskimage")),
    ("annotation", ("pdannot", "pdwidgetannot", "pdacroform", "pdformfield")),
    ("action", ("pdaction", "javascript")),
    ("embedded", ("cosfilespecification", "pdembeddedfile", "embeddedfile")),
    ("image", ("pdximage", "jpeg2000", "pdinlineimage")),
    ("security", ("encrypt",)),
    ("syntax", ("cosdocument", "costrailer", "cosxref", "cosstream", "cosindirect", "cosstring", "cosdict", "cosname",
                "cosarray", "cosreal", "cosinteger", "cosfilter", "pdpage")),
]
WORDS: list[tuple[str, str]] = [
    ("security", r"\bencrypt"),
    ("font", r"\bfonts?\b|\bglyphs?\b"),
    ("metadata", r"\bmetadata\b|\bxmp\b"),
    ("structure", r"\bstructure (tree|element)|\btagged\b|\balternate description|\bnatural language\b"),
    ("color", r"\boutput ?intents?\b|\bcolou?r ?spaces?\b|\bicc\b"),
    ("transparency", r"\btransparen|\bsoft mask|\bblend mode"),
    ("annotation", r"\bannotations?\b|\bform fields?\b"),
    ("action", r"\bjavascript\b|\bactions?\b"),
    ("embedded", r"\bembedded files?\b|\bfile specification"),
    ("image", r"\bimages?\b|\blzw\b|\binterpolat"),
    ("syntax", r"\btrailer\b|\bcross[- ]reference\b|\bheader\b|\bstreams?\b|\bobjects?\b"),
]

EXPLANATIONS = {
    "es": {
        "security": "El archivo está cifrado o protegido, y la norma no lo permite.",
        "font": "Hay fuentes sin incrustar o con datos incompletos (anchos de los caracteres, codificación o correspondencia con Unicode).",
        "metadata": "Faltan los metadatos XMP, no declaran el nivel o no coinciden con los datos del documento.",
        "structure": "Falta la estructura etiquetada (orden de lectura, títulos, texto alternativo o idioma) que exigen los niveles «a» y PDF/UA.",
        "color": "Usa colores que dependen del dispositivo sin un perfil de salida (OutputIntent) que los defina, o un perfil ICC no válido.",
        "transparency": "Usa transparencias que este nivel no admite (PDF/A-1) o sin el espacio de color de fusión que pide la norma.",
        "annotation": "Hay anotaciones o campos de formulario sin apariencia, ocultos o de un tipo que la norma no permite.",
        "action": "Contiene JavaScript o acciones (abrir archivos, lanzar programas, enviar formularios) que la norma prohíbe.",
        "embedded": "Lleva archivos adjuntos que este nivel no permite (PDF/A-1, ninguno; PDF/A-2, solo otros PDF/A).",
        "image": "Hay imágenes con una compresión o unos parámetros que la norma no admite (por ejemplo, LZW o interpolación).",
        "syntax": "Hay errores en la estructura interna del PDF (cabecera, tabla de referencias, identificador del archivo o flujos).",
        "other": "El archivo no cumple esta regla de la norma.",
    },
    "en": {
        "security": "The file is encrypted or protected, which the standard does not allow.",
        "font": "Some fonts are not embedded or have incomplete data (character widths, encoding or Unicode mapping).",
        "metadata": "The XMP metadata is missing, does not declare the level or does not match the document data.",
        "structure": "The tagged structure (reading order, headings, alternative text or language) required by level “a” and PDF/UA is missing.",
        "color": "It uses device-dependent colours without an output profile (OutputIntent) that defines them, or an invalid ICC profile.",
        "transparency": "It uses transparency that this level does not allow (PDF/A-1) or without the blending colour space the standard requires.",
        "annotation": "Some annotations or form fields have no appearance, are hidden or are of a type the standard does not allow.",
        "action": "It contains JavaScript or actions (opening files, launching programs, submitting forms) that the standard forbids.",
        "embedded": "It has attachments this level does not allow (PDF/A-1: none; PDF/A-2: only other PDF/A files).",
        "image": "Some images use a compression or parameters the standard does not allow (for example LZW or interpolation).",
        "syntax": "There are errors in the internal structure of the PDF (header, cross-reference table, file identifier or streams).",
        "other": "The file does not meet this rule of the standard.",
    },
}


def category(rule: Rule) -> str:
    for tag in (t.strip().lower() for t in rule.tags.split(",")):
        if tag in TAGS:
            return TAGS[tag]
    obj = rule.obj.lower()
    for name, classes in OBJECTS:
        if any(c in obj for c in classes):
            return name
    text = rule.description.lower()
    for name, pattern in WORDS:
        if re.search(pattern, text):
            return name
    return "other"


def explain(rule: Rule, locale: str) -> str:
    return EXPLANATIONS.get(locale, EXPLANATIONS["es"])[category(rule)]


# --- Informe HTML ---------------------------------------------------------------------------------------------------

TEXT = {
    "es": {"title": "Informe de validación", "file": "Archivo", "profile": "Comprobado como", "ok": "Cumple", "ko": "No cumple",
           "rules": "Reglas incumplidas", "checks": "Incumplimientos", "clause": "Regla", "meaning": "Qué significa",
           "count": "Veces", "pages": "Páginas", "document": "Todo el documento", "detail": "Detalle técnico (veraPDF)",
           "none": "veraPDF no ha encontrado ningún incumplimiento.", "engine": "Validado con veraPDF",
           "shown": "Las páginas salen de los primeros {n} casos de cada regla.", "declared": "Nivel que declara el archivo",
           "undeclared": "ninguno"},
    "en": {"title": "Validation report", "file": "File", "profile": "Checked as", "ok": "Compliant", "ko": "Not compliant",
           "rules": "Failed rules", "checks": "Failures", "clause": "Rule", "meaning": "What it means",
           "count": "Times", "pages": "Pages", "document": "Whole document", "detail": "Technical detail (veraPDF)",
           "none": "veraPDF found no failures.", "engine": "Validated with veraPDF",
           "shown": "Pages come from the first {n} cases of each rule.", "declared": "Level the file declares",
           "undeclared": "none"},
}


def verdict(report: Report, flavour: str, locale: str, declared_ok: bool = True) -> str:
    t = TEXT.get(locale, TEXT["es"])
    if report.compliant and declared_ok:
        return f"{t['ok']}: {flavour_label(flavour)}."
    return f"{t['ko']}: {flavour_label(flavour)} ({t['rules'].lower()}: {report.failed_rules}; {t['checks'].lower()}: {report.failed_checks})."


def render_html(report: Report, file_name: str, flavour: str, locale: str, declared: str | None = None,
                declared_ok: bool = True) -> str:
    t = TEXT.get(locale, TEXT["es"])
    e = html.escape
    ok = report.compliant and declared_ok
    rows = []
    for r in report.rules:
        pages = ", ".join(str(p) for p in sorted(r.pages)[:30]) or t["document"]
        msgs = "".join(f"<li>{e(m)}</li>" for m in r.messages)
        rows.append(
            f"<tr><td class=\"c\">{e(r.specification)}<br><b>{e(r.clause)}</b>{(' · ' + e(r.test)) if r.test else ''}</td>"
            f"<td>{e(explain(r, locale))}<details><summary>{e(t['detail'])}</summary><p>{e(r.description)}</p>"
            f"{f'<ul>{msgs}</ul>' if msgs else ''}</details></td><td class=\"n\">{r.failed}</td><td>{e(pages)}</td></tr>")
    table = (f"<table><thead><tr><th>{e(t['clause'])}</th><th>{e(t['meaning'])}</th><th>{e(t['count'])}</th><th>{e(t['pages'])}</th>"
             f"</tr></thead><tbody>{''.join(rows)}</tbody></table><p class=\"m\">{e(t['shown'].format(n=MAX_DISPLAYED))}</p>"
             if rows else f"<p>{e(t['none'])}</p>")
    declared_row = (f"<tr><th>{e(t['declared'])}</th><td>{e(flavour_label(declared) if declared else t['undeclared'])}</td></tr>"
                    if declared is not None or not declared_ok else "")
    return (f"<!doctype html><html lang=\"{e(locale)}\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\">"
            f"<title>{e(t['title'])}: {e(file_name)}</title><style>"
            "body{font:15px/1.5 system-ui,sans-serif;color:#1f2328;max-width:960px;margin:24px auto;padding:0 16px}"
            "h1{font-size:22px}.v{display:inline-block;padding:4px 12px;border-radius:6px;font-weight:600}"
            ".ok{background:#dafbe1;color:#116329}.ko{background:#ffebe9;color:#a40e26}"
            "table{border-collapse:collapse;width:100%;margin-top:12px}th,td{border-bottom:1px solid #d0d7de;padding:8px;"
            "text-align:left;vertical-align:top}.c{white-space:nowrap;font-size:13px}.n{text-align:right}"
            "details{margin-top:4px;color:#59636e;font-size:13px}.m{color:#59636e;font-size:13px}"
            ".s th{width:14em;border:0;padding:2px 8px 2px 0}.s td{border:0;padding:2px 0}"
            "</style></head><body>"
            f"<h1>{e(t['title'])}</h1><p class=\"v {'ok' if ok else 'ko'}\">{e(t['ok'] if ok else t['ko'])}</p>"
            f"<table class=\"s\"><tr><th>{e(t['file'])}</th><td>{e(file_name)}</td></tr>"
            f"<tr><th>{e(t['profile'])}</th><td>{e(flavour_label(flavour))}</td></tr>{declared_row}"
            f"<tr><th>{e(t['rules'])}</th><td>{report.failed_rules}</td></tr>"
            f"<tr><th>{e(t['checks'])}</th><td>{report.failed_checks}</td></tr></table>"
            f"{table}<p class=\"m\">{e(t['engine'])} {e(report.version)}</p></body></html>")
