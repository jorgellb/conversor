"""factura-electronica-a-pdf y sus páginas propias facturae-a-pdf, ubl-a-pdf y cii-a-pdf (A.2, 7.14 y 7.23; F4-D2).

Dos etapas:

1. `utils` (`workerutils`): lee el XML sin DTD ni entidades, comprueba que es una factura de la sintaxis de la página y
   su XSD oficial (7.14: Facturae con los de facturae.gob.es; UBL 2.1 y CII D16B con los de la configuración de KoSIT),
   imprime la representación (`representar`) con el Chromium de `gotenberg` (sin red) y, en la salida «PDF/A-3», pide
   PDF/A-3b e incrusta el XML original con pikepdf, sin cambiar un byte, como archivo asociado del documento (`/AF`,
   relación `Source`, tipo MIME y fecha). Comprueba que el adjunto es idéntico al original.
2. `ocr` (`workerocr`, el único con veraPDF): valida el PDF/A-3b y dice el resultado en la nota; si no cumple, entrega
   también el informe de veraPDF. La salida «PDF simple» termina en la primera etapa.

En lote, un archivo que no se puede convertir no para los demás: se dice en `no-convertidas.txt` (D-194).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from core.errors import ErrorCode, ToolError, message
from tools.base import ToolContext, derived_name
from tools.pdf.common import with_batch_zip
from tools.utils.facturas import lectura, motores, representar
from tools.utils.facturas.validar import spec_label

STAGE = "verapdf"
MANIFEST = "facturas.json"
SYNTAX_OF = {"facturae-a-pdf": "facturae", "ubl-a-pdf": "ubl", "cii-a-pdf": "cii"}
# Lo que corta un archivo; los fallos del motor (Gotenberg caído, que se reintenta) siguen parando la tarea entera.
PER_FILE = (ErrorCode.CORRUPT_FILE, ErrorCode.UNSUPPORTED_FORMAT, ErrorCode.LIMIT_EXCEEDED, ErrorCode.INVALID_OPTIONS)
TEXTS = {
    "es": {"check": "Comprobando el PDF/A-3 con veraPDF…", "embedded": "PDF/A-3 con el XML original incrustado sin cambios ({name}).",
           "simple": "PDF sin el XML incrustado.", "zip": "facturas-pdf.zip", "desc": "Factura electrónica original",
           "failed": "no-convertidas.txt", "failed_head": "Archivos que no se han convertido:",
           "failed_note": "{n} archivo(s) no se han convertido: mira el motivo en este archivo.",
           "unchecked": "No se ha podido comprobar con veraPDF.", "xsd": "La factura no cumple el esquema oficial de {syntax}: {first}"},
    "en": {"check": "Checking the PDF/A-3 with veraPDF…", "embedded": "PDF/A-3 with the original XML embedded unchanged ({name}).",
           "simple": "PDF without the embedded XML.", "zip": "invoices-pdf.zip", "desc": "Original e-invoice",
           "failed": "not-converted.txt", "failed_head": "Files that were not converted:",
           "failed_note": "{n} file(s) were not converted: see why in this file.",
           "unchecked": "It could not be checked with veraPDF.", "xsd": "The invoice does not meet the official {syntax} schema: {first}"},
}
SYNTAX_NAMES = {"facturae": "Facturae", "ubl": "UBL 2.1", "cii": "CII D16B"}


def _texts(ctx: ToolContext) -> dict[str, str]:
    return TEXTS.get(ctx.locale, TEXTS["es"])


def embed(pdf_path: Path, xml: bytes, name: str, description: str = "Factura electrónica original") -> None:
    """XML original como archivo asociado del documento (PDF/A-3, ISO 19005-3 6.8): /AF del catálogo, AFRelationship
    Source, Subtype con su tipo MIME y fecha de modificación. Después se lee de vuelta y se compara byte a byte."""
    import pikepdf

    stamp = datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%SZ")
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        spec = pikepdf.AttachedFileSpec(pdf, xml, filename=name, description=description,
                                        mime_type="application/xml", creation_date=stamp, mod_date=stamp,
                                        relationship=pikepdf.Name.Source)
        pdf.attachments[name] = spec
        filespec = pdf.attachments[name].obj
        af = pdf.Root.get("/AF")
        if not isinstance(af, pikepdf.Array):
            af = pikepdf.Array()
        af.append(filespec)
        pdf.Root.AF = af
        pdf.save(pdf_path)
    with pikepdf.open(pdf_path) as pdf:
        stored = pdf.attachments[name].get_file().read_bytes()
    if hashlib.sha256(stored).digest() != hashlib.sha256(xml).digest():
        raise ToolError(ErrorCode.ENGINE_FAILED, "xml_changed")


def _pdf(ctx: ToolContext, html_text: str, pdfa: bool, n: int) -> Path:
    from tools.office import gotenberg

    page = ctx.work / f"factura-{n}.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(html_text, encoding="utf-8")
    fields = {"printBackground": "true", "preferCssPageSize": "true", "skipNetworkIdleEvent": "true"}
    if pdfa:
        fields["pdfa"] = "PDF/A-3b"
    out = ctx.stage_dir() / f"{n}.pdf"
    out.write_bytes(gotenberg.chromium_html(ctx.settings.GOTENBERG_URL, page, fields))
    return out


def _check(ctx: ToolContext, root, inv, data: bytes, want: str | None) -> None:
    """Sintaxis de la página y XSD oficial (7.14)."""
    t = _texts(ctx)
    if want and inv.syntax != want:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, f"invoice_syntax:{inv.syntax}>{want}")
    if inv.syntax == "facturae":
        result = motores.facturae(ctx.settings, root, data, lectura.facturae_version(root), check_signature=False)
        errors = [f.text for f in result.findings if f.code == "XSD"]
        detail = "facturae_xsd_invalid"
    else:
        errors = motores.syntax_errors(ctx.settings, root, inv.syntax)
        detail = "invoice_xsd_invalid"
    if errors:
        err = ToolError(ErrorCode.CORRUPT_FILE, detail)
        err.user_message = t["xsd"].format(syntax=SYNTAX_NAMES[inv.syntax], first=errors[0][:300])  # para no-convertidas.txt
        raise err


def _failed_output(ctx: ToolContext, failed: list[tuple[str, ToolError]]) -> dict:
    t = _texts(ctx)
    lines = [t["failed_head"], ""]
    for name, err in failed:
        reason = getattr(err, "user_message", None) or message(err.code, ctx.locale, err.detail)
        lines.append(f"- {name}: {reason}")
    dst = ctx.output(t["failed"])
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"path": str(dst), "name": t["failed"], "note": t["failed_note"].format(n=len(failed))}


def _utils_stage(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    t = _texts(ctx)
    want = SYNTAX_OF.get(ctx.tool)
    pdfa = o.salida == "pdfa3"
    manifest = []
    plain: list[tuple[int, str, str]] = []
    failed: list[tuple[str, ToolError]] = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(0.8 * n / len(ctx.inputs), None)
        try:
            if inp.path.stat().st_size > lectura.MAX_XML_BYTES:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"xml_size:{inp.path.stat().st_size // 1048576}>{lectura.MAX_XML_BYTES // 1048576}")
            data = inp.path.read_bytes()
            root, inv = lectura.read_invoice(data)
            _check(ctx, root, inv, data, want)
        except ToolError as err:
            if err.code not in PER_FILE or len(ctx.inputs) == 1:
                raise
            failed.append((inp.name, err))
            continue
        detail = representar.detail_of(root, inv)
        del root
        lang = representar.language_of(detail, ctx.locale, o.idioma)
        name = Path(inp.name).name if inp.name.lower().endswith(".xml") else f"{Path(inp.name).stem}.xml"
        pdf = _pdf(ctx, representar.render(detail, lang, spec_label(inv), name), pdfa, n)
        warnings = representar.warnings(detail, lang)
        if pdfa:
            embed(pdf, data, name, t["desc"])
            manifest.append({"n": n, "name": inp.name, "xml": name, "warnings": warnings})
        else:
            plain.append((n, inp.name, " ".join([t["simple"], *warnings])))
    if failed and not manifest and not plain:
        raise failed[0][1]  # ninguno se ha podido convertir: el error del primero
    if failed:
        (ctx.stage_dir() / "failed.json").write_text(json.dumps(
            [[name, err.code, err.detail, getattr(err, "user_message", None)] for name, err in failed], ensure_ascii=False), encoding="utf-8")
    if pdfa:
        (ctx.stage_dir() / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        ctx.handoff("ocr", STAGE, t["check"], keep_secrets=False)
    # PDF simple: se copian al final, para que un reintento a mitad de lote no deje salidas sueltas.
    outputs = []
    for n, original, note in plain:
        out_name = derived_name(original, "", "pdf")
        dst = ctx.output(out_name)
        shutil.copyfile(ctx.stage_dir() / f"{n}.pdf", dst)
        outputs.append({"path": str(dst), "name": out_name, "note": note})
    if failed:
        outputs.append(_failed_output(ctx, failed))
    return with_batch_zip(ctx, outputs, t["zip"])


def _verapdf_stage(ctx: ToolContext) -> list[dict]:
    from tools.ocr import verapdf
    from tools.ocr.pdfa import write_report

    t = _texts(ctx)
    stage = ctx.store.job_dir(ctx.job_id) / "stage"
    try:
        manifest = json.loads((stage / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError(ErrorCode.INTERNAL, "falta el resultado de la etapa de utils") from exc
    outputs = []
    for k, item in enumerate(manifest):
        ctx.report(k / len(manifest), t["check"])
        name = derived_name(item["name"], "", "pdf")
        dst = ctx.output(name)
        shutil.copyfile(stage / f"{int(item['n'])}.pdf", dst)
        notes = [t["embedded"].format(name=item["xml"]), *item.get("warnings", [])]
        report_out = None
        try:
            report_out, report = write_report(ctx, dst, "3b", name, Path(item["name"]).stem or "factura")
            notes.append(verapdf.verdict(report, "3b", ctx.locale))
        except ToolError as err:
            if err.transient:
                raise
            notes.append(t["unchecked"])  # el PDF se entrega igual: el XML está dentro y comprobado
        outputs.append({"path": str(dst), "name": name, "note": " ".join(notes)})
        if report_out is not None and not report.compliant:
            outputs.append({**report_out, "note": None})
        elif report_out is not None:
            Path(report_out["path"]).unlink(missing_ok=True)
    failed_path = stage / "failed.json"
    if failed_path.exists():
        failed = [(name, _restore(code, detail, msg)) for name, code, detail, msg in json.loads(failed_path.read_text(encoding="utf-8"))]
        outputs.append(_failed_output(ctx, failed))
    return with_batch_zip(ctx, outputs, t["zip"])


def _restore(code: str, detail: str | None, user_message: str | None) -> ToolError:
    err = ToolError(ErrorCode(code), detail)
    if user_message:
        err.user_message = user_message
    return err


def run(ctx: ToolContext) -> list[dict]:
    return _verapdf_stage(ctx) if ctx.stage == STAGE else _utils_stage(ctx)
