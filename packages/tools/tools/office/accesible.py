"""word-a-pdf-accesible (7.5): Word a PDF/UA-1 etiquetado y comprobación con veraPDF (D-182).

Dos etapas:

1. `office` (cola `office.light`): LibreOffice de Gotenberg con `pdfua`, rango de páginas aplicado por LibreOffice (las
   etiquetas no se pierden) y arreglos seguros de metadatos que Word suele dejar sin poner: título (el de la opción o,
   si no, el nombre del archivo) mostrado en la barra del lector, identificador `pdfuaid` e idioma si se elige. Los PDF
   quedan en la carpeta `stage/` del trabajo y el trabajo pasa a `ocr` sin los secretos (la contraseña ya no hace falta).
2. `ocr`: veraPDF con el perfil PDF/UA-1 (solo está en la imagen worker-ocr) y el informe en lenguaje sencillo de
   validar-pdfa, con cómo se arregla cada fallo en Word.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pikepdf

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.office.office_a_pdf import libreoffice_pdf, lo_fields
from tools.pdf.common import with_batch_zip

FLAVOUR = "ua1"
UA_NS = "http://www.aiim.org/pdfua/ns/id/"
STAGE = "verapdf"
MANIFEST = "accesible.json"

TEXTS = {
    "es": {"check": "Comprobando la accesibilidad con veraPDF…",
           "title_option": "Se ha puesto el título «{title}», porque el documento no tenía.",
           "title_name": "El documento no tenía título: se ha puesto «{title}», el nombre del archivo. Ponle un título en Word "
                         "(Archivo → Información → Propiedades).",
           "lang_set": "Idioma principal del texto: {lang}.",
           "lang_missing": "El documento no declara su idioma: elígelo en la opción «Idioma principal del texto» o en Word.",
           "provisional": "El título puesto es provisional: cámbialo por uno que describa el documento.",
           "untagged": "LibreOffice no ha generado la estructura etiquetada; el PDF no será accesible.",
           "zip": "documentos-accesibles.zip"},
    "en": {"check": "Checking accessibility with veraPDF…",
           "title_option": "The title “{title}” was set, because the document had none.",
           "title_name": "The document had no title: “{title}”, the file name, was set. Give it a title in Word "
                         "(File → Info → Properties).",
           "lang_set": "Main text language: {lang}.",
           "lang_missing": "The document does not declare its language: choose it in the “Main text language” option or in Word.",
           "provisional": "The title set is provisional: replace it with one that describes the document.",
           "untagged": "LibreOffice did not produce the tagged structure; the PDF will not be accessible.",
           "zip": "accessible-documents.zip"},
}


def _texts(ctx: ToolContext) -> dict[str, str]:
    return TEXTS.get(ctx.locale, TEXTS["es"])


def _fields(ctx: ToolContext) -> dict[str, str]:
    o = ctx.options
    # A.8 Office con el formato fijado a PDF/UA; las opciones de Excel y PowerPoint no se aplican a Word.
    office = SimpleNamespace(formato="pdfua", marcadores=o.marcadores, campos_formulario=o.campos_formulario,
                             calidad_imagenes=o.calidad_imagenes, resolucion_maxima=o.resolucion_maxima,
                             hoja_una_pagina=False, diapositivas_ocultas=False, paginas_notas=False,
                             comentarios_margen=o.comentarios_margen)
    return lo_fields(office, ctx.secrets.get("contrasena"))


def _info_title(pdf: pikepdf.Pdf) -> str:
    try:
        return str(pdf.docinfo.get("/Title", "") or "").strip()
    except (TypeError, ValueError):
        return ""


def fix_metadata(path: Path, title_option: str, file_stem: str, language: str) -> list[tuple[str, dict[str, str]]]:
    """Arreglos que no cambian el contenido ni las etiquetas. Devuelve las notas (clave y valores) para el resultado."""
    notes: list[tuple[str, dict[str, str]]] = []
    try:
        pdf = pikepdf.open(path, allow_overwriting_input=True)
    except pikepdf.PdfError as exc:
        raise ToolError(ErrorCode.ENGINE_FAILED, "Gotenberg devolvió un PDF ilegible") from exc
    with pdf:
        mark = pdf.Root.get("/MarkInfo")
        if "/StructTreeRoot" not in pdf.Root or mark is None or not bool(mark.get("/Marked", False)):
            notes.append(("untagged", {}))
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            # PDF/UA-1 (7.1) pide el título en el XMP: si solo está en /Info se copia; si no hay, el de la opción o el
            # nombre del archivo.
            if not str(meta.get("dc:title", "") or "").strip():
                info = _info_title(pdf)
                title = info or title_option.strip() or file_stem
                meta["dc:title"] = title
                if not info:
                    notes.append(("title_option" if title_option.strip() else "title_name", {"title": title}))
            meta[f"{{{UA_NS}}}part"] = "1"
        prefs = pdf.Root.get("/ViewerPreferences")
        if not isinstance(prefs, pikepdf.Dictionary):
            prefs = pikepdf.Dictionary()
        prefs.DisplayDocTitle = True
        pdf.Root.ViewerPreferences = prefs
        if language != "documento":
            pdf.Root.Lang = pikepdf.String(language)
            notes.append(("lang_set", {"lang": language}))
        elif not str(pdf.Root.get("/Lang", "") or "").strip():
            notes.append(("lang_missing", {}))
        pdf.save(path)
    return notes


def _office_stage(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    stage = ctx.stage_dir()
    fields = _fields(ctx)
    manifest = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(0.8 * n / len(ctx.inputs), None)
        ext = inp.ext or Path(inp.name).suffix.lstrip(".").lower()
        dst = stage / f"{n}.pdf"
        libreoffice_pdf(ctx, inp.path, ext, fields, o.paginas, dst, keep_structure=True)
        notes = fix_metadata(dst, o.titulo, Path(inp.name).stem or "documento", o.idioma)
        manifest.append({"n": n, "name": inp.name, "notes": notes})
    (stage / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    ctx.handoff("ocr", STAGE, _texts(ctx)["check"], keep_secrets=False)
    return []  # handoff lanza siempre


def _verapdf_stage(ctx: ToolContext) -> list[dict]:
    from tools.ocr import verapdf
    from tools.ocr.pdfa import write_report

    t = _texts(ctx)
    stage = ctx.store.job_dir(ctx.job_id) / "stage"
    try:
        manifest = json.loads((stage / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError(ErrorCode.INTERNAL, "falta el resultado de la etapa de LibreOffice") from exc
    outputs = []
    for k, item in enumerate(manifest):
        ctx.report(k / len(manifest), t["check"])
        name = derived_name(item["name"], "", "pdf")
        dst = ctx.output(name)
        shutil.copyfile(stage / f"{int(item['n'])}.pdf", dst)
        stem = Path(item["name"]).stem or "documento"
        report_out, report = write_report(ctx, dst, FLAVOUR, name, stem)
        notes = [t[key].format(**values) for key, values in item["notes"]]
        notes.append(verapdf.verdict(report, FLAVOUR, ctx.locale))
        if any(key == "title_name" for key, _ in item["notes"]):
            notes.append(t["provisional"])  # el nombre del archivo pasa la regla, pero no describe el documento
        outputs.append({"path": str(dst), "name": name, "note": " ".join(notes)})
        outputs.append(report_out)
    # `stage/` no se borra aquí: si el worker cae antes de registrar el resultado, el reintento lo necesita. Se borra con
    # el trabajo (Store.remove_job) o, si falla, con los huérfanos (D-182).
    return with_batch_zip(ctx, outputs, t["zip"])


def run(ctx: ToolContext) -> list[dict]:
    return _verapdf_stage(ctx) if ctx.stage == STAGE else _office_stage(ctx)
