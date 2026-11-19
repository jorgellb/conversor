"""factura-electronica-a-pdf y sus páginas propias facturae-a-pdf, ubl-a-pdf y cii-a-pdf (A.2, 7.14 y 7.23; F4-D2).

Dos etapas:

1. `utils` (`workerutils`): lee el XML sin DTD ni entidades, comprueba que es una factura (y su XSD en Facturae), imprime
   la representación (`representar`) con el Chromium de `gotenberg` (sin red) y, en la salida «PDF/A-3», pide PDF/A-3b
   e incrusta el XML original con pikepdf, sin cambiar un byte, como archivo asociado del documento (`/AF`, relación
   `Source`, tipo MIME y fecha). Comprueba que el adjunto es idéntico al original.
2. `ocr` (`workerocr`, el único con veraPDF): valida el PDF/A-3b y dice el resultado en la nota (solo en la salida
   PDF/A-3; la salida «PDF simple» termina en la primera etapa).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.pdf.common import with_batch_zip
from tools.utils.facturas import lectura, motores, representar
from tools.utils.facturas.validar import spec_label

STAGE = "verapdf"
MANIFEST = "facturas.json"
SYNTAX_OF = {"facturae-a-pdf": "facturae", "ubl-a-pdf": "ubl", "cii-a-pdf": "cii"}
TEXTS = {
    "es": {"check": "Comprobando el PDF/A-3 con veraPDF…", "embedded": "PDF/A-3 con el XML original incrustado sin cambios ({name}).",
           "simple": "PDF sin el XML incrustado.", "zip": "facturas-pdf.zip", "wrong": "Esta página convierte {want}; el archivo es {got}."},
    "en": {"check": "Checking the PDF/A-3 with veraPDF…", "embedded": "PDF/A-3 with the original XML embedded unchanged ({name}).",
           "simple": "PDF without the embedded XML.", "zip": "invoices-pdf.zip", "wrong": "This page converts {want}; the file is {got}."},
}
SYNTAX_NAMES = {"facturae": "Facturae", "ubl": "UBL", "cii": "CII"}


def _texts(ctx: ToolContext) -> dict[str, str]:
    return TEXTS.get(ctx.locale, TEXTS["es"])


def embed(pdf_path: Path, xml: bytes, name: str) -> None:
    """XML original como archivo asociado del documento (PDF/A-3, ISO 19005-3 6.8): /AF del catálogo, AFRelationship
    Source, Subtype con su tipo MIME y fecha de modificación. Después se lee de vuelta y se compara byte a byte."""
    import pikepdf

    stamp = datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%SZ")
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        spec = pikepdf.AttachedFileSpec(pdf, xml, filename=name, description="Factura electrónica original",
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


def _utils_stage(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    t = _texts(ctx)
    want = SYNTAX_OF.get(ctx.tool)
    pdfa = o.salida == "pdfa3"
    manifest = []
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(0.8 * n / len(ctx.inputs), None)
        data = inp.path.read_bytes()
        root, inv = lectura.read_invoice(data)
        if want and inv.syntax != want:
            raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, f"invoice_syntax:{inv.syntax}>{want}")
        if inv.syntax == "facturae":
            result = motores.facturae(ctx.settings, root, data, lectura.facturae_version(root))
            if any(f.code == "XSD" for f in result.findings):
                raise ToolError(ErrorCode.CORRUPT_FILE, "facturae_xsd_invalid")
        detail = representar.detail(data)
        lang = representar.language_of(detail, ctx.locale, o.idioma)
        name = Path(inp.name).name if inp.name.lower().endswith(".xml") else f"{Path(inp.name).stem}.xml"
        pdf = _pdf(ctx, representar.render(detail, lang, spec_label(inv), name), pdfa, n)
        if pdfa:
            embed(pdf, data, name)
            manifest.append({"n": n, "name": inp.name, "xml": name})
        else:
            out_name = derived_name(inp.name, "", "pdf")
            dst = ctx.output(out_name)
            shutil.copyfile(pdf, dst)
            outputs.append({"path": str(dst), "name": out_name, "note": t["simple"]})
    if pdfa:
        (ctx.stage_dir() / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        ctx.handoff("ocr", STAGE, t["check"])
    return with_batch_zip(ctx, outputs, t["zip"])


def _verapdf_stage(ctx: ToolContext) -> list[dict]:
    from tools.ocr import verapdf

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
        work = ctx.work / f"verapdf-{k}"
        work.mkdir(parents=True, exist_ok=True)
        report = verapdf.parse_report(verapdf.run_verapdf(dst, "3b", work))
        note = " ".join((t["embedded"].format(name=item["xml"]), verapdf.verdict(report, "3b", ctx.locale)))
        outputs.append({"path": str(dst), "name": name, "note": note})
    return with_batch_zip(ctx, outputs, t["zip"])


def run(ctx: ToolContext) -> list[dict]:
    return _verapdf_stage(ctx) if ctx.stage == STAGE else _utils_stage(ctx)
