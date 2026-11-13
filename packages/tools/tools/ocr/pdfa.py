"""pdf-a-pdfa (A.5) y validar-pdfa (A.6): OCRmyPDF con `--pdfa-backend internal` (nunca Ghostscript) y veraPDF.

pdf-a-pdfa: si el archivo no se puede convertir sin Ghostscript (por ejemplo, fuentes sin incrustar), devuelve el
informe de veraPDF del original y explica que la opción «rasterizar las páginas» lo resuelve (D-62).
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pikepdf

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.ocr import verapdf
from tools.ocr.ocr_pdf import installed_languages
from tools.pdf.common import open_pdf, with_batch_zip

NOTES = {
    "es": {"untagged": "El PDF no está etiquetado: se ha hecho {done} en lugar de {asked}.",
           "rasterized": "Las páginas se han rasterizado con una capa de texto OCR para poder cumplir la norma.",
           "failed": "No se puede convertir a {asked} sin Ghostscript: revisa el informe y vuelve a probar con «Si no se puede, "
                     "rasterizar las páginas con capa de texto OCR».",
           "undeclared": "El archivo no declara ningún nivel PDF/A ni PDF/UA; se ha comprobado como {flavour}."},
    "en": {"untagged": "The PDF is not tagged: {done} was made instead of {asked}.",
           "rasterized": "The pages were rasterized with an OCR text layer to meet the standard.",
           "failed": "It cannot be converted to {asked} without Ghostscript: check the report and try again with “If it fails, "
                     "rasterize the pages with an OCR text layer”.",
           "undeclared": "The file declares no PDF/A or PDF/UA level; it was checked as {flavour}."},
}
REPORT_NAME = {"es": "informe-{stem}.html", "en": "report-{stem}.html"}


def is_tagged(path: Path) -> bool:
    with pikepdf.open(path) as pdf:
        mark = pdf.Root.get("/MarkInfo")
        return "/StructTreeRoot" in pdf.Root and mark is not None and bool(mark.get("/Marked", False))


def set_conformance(path: Path, conformance: str) -> None:
    """OCRmyPDF declara siempre el nivel «B»; para «U» y «A» se cambia en el XMP y lo comprueba veraPDF."""
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as meta:
            meta["pdfaid:conformance"] = conformance
        pdf.save(path)


def _convert(ctx: ToolContext, src: Path, dst: Path, part: str, force: bool) -> None:
    import ocrmypdf
    from ocrmypdf import exceptions as ocr_exc

    try:
        ocrmypdf.ocr(str(src), str(dst), language=ctx.options.idiomas, mode="force" if force else "skip",
                     output_type=f"pdfa-{part}", pdfa_backend="internal", rasterizer="pypdfium", jobs=max(1, ctx.threads),
                     progress_bar=False, max_image_mpixels=ctx.settings.IMAGE_MAX_PIXELS / 1_000_000)
    except ocr_exc.EncryptedPdfError as exc:
        raise ToolError(ErrorCode.PASSWORD_REQUIRED) from exc
    except ocr_exc.InputFileError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE) from exc
    except ocr_exc.ExitCodeException as exc:
        if getattr(exc, "exit_code", None) == 10 or "pdf/a" in str(exc).lower():
            raise ToolError(ErrorCode.PDFA_NEEDS_GHOSTSCRIPT) from exc
        raise ToolError(ErrorCode.ENGINE_FAILED, type(exc).__name__) from exc


def _report(ctx: ToolContext, pdf: Path, flavour: str, name: str, stem: str, **kw) -> tuple[dict, verapdf.Report]:
    work = ctx.work / f"verapdf-{stem}"
    work.mkdir(parents=True, exist_ok=True)
    report = verapdf.parse_report(verapdf.run_verapdf(pdf, flavour, work))
    report_name = REPORT_NAME.get(ctx.locale, REPORT_NAME["es"]).format(stem=stem)
    dst = ctx.output(report_name)
    dst.write_text(verapdf.render_html(report, name, flavour, ctx.locale, **kw), encoding="utf-8")
    return {"path": str(dst), "name": report_name}, report


def _check_languages(ctx: ToolContext) -> None:
    missing = [code for code in ctx.options.idiomas if code not in installed_languages()]
    if missing:
        raise ToolError(ErrorCode.INVALID_OPTIONS, f"Idiomas no instalados: {', '.join(missing)}")


def run_pdfa(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    notes_t = NOTES.get(ctx.locale, NOTES["es"])
    _check_languages(ctx)
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        with open_pdf(inp.path, None, ctx.plan.pdf_pages):
            pass
        stem = Path(inp.name).stem or "documento"
        level = o.nivel
        notes = []
        if level in ("2a", "3a") and not is_tagged(inp.path):
            level = f"{level[0]}b"
            notes.append(notes_t["untagged"].format(done=verapdf.flavour_label(level), asked=verapdf.flavour_label(o.nivel)))
        part, conformance = level[0], level[1:].upper()
        converted = ctx.work / f"pdfa-{n}.pdf"
        try:
            _convert(ctx, inp.path, converted, part, force=False)
        except ToolError as err:
            if err.code != ErrorCode.PDFA_NEEDS_GHOSTSCRIPT:
                raise
            if not o.rasterizar_si_falla:
                report_out, _ = _report(ctx, inp.path, level, inp.name, stem)
                report_out["note"] = " ".join([*notes, notes_t["failed"].format(asked=verapdf.flavour_label(level))])
                outputs.append(report_out)
                continue
            _convert(ctx, inp.path, converted, part, force=True)
            notes.append(notes_t["rasterized"])
        if conformance in ("U", "A"):
            set_conformance(converted, conformance)
        name = derived_name(inp.name, "-pdfa", "pdf")
        dst = ctx.output(name)
        shutil.copyfile(converted, dst)
        report_out, report = _report(ctx, dst, level, name, stem)
        notes.append(verapdf.verdict(report, level, ctx.locale))
        outputs.append({"path": str(dst), "name": name, "note": " ".join(notes)})
        outputs.append(report_out)
    return with_batch_zip(ctx, outputs, "pdfa.zip")


def run_validate(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    notes_t = NOTES.get(ctx.locale, NOTES["es"])
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        with open_pdf(inp.path, None, ctx.plan.pdf_pages):
            pass
        stem = Path(inp.name).stem or "documento"
        declared = verapdf.declared_flavour(inp.path)
        flavour = o.perfil if o.perfil != "auto" else (declared or "2b")
        declared_ok = o.perfil != "auto" or declared is not None
        out, report = _report(ctx, inp.path, flavour, inp.name, stem, declared=declared, declared_ok=declared_ok)
        notes = [] if declared_ok else [notes_t["undeclared"].format(flavour=verapdf.flavour_label(flavour))]
        notes.append(verapdf.verdict(report, flavour, ctx.locale, declared_ok))
        out["note"] = " ".join(notes)
        outputs.append(out)
    return with_batch_zip(ctx, outputs, "informes-pdfa.zip")
