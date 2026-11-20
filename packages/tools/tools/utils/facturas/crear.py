"""crear-factura-electronica (A.2 y 7.23, F4-E2, D-205): genera el XML, lo valida y lo entrega.

1. `utils` (`workerutils`): XML con `generar.build`; XSD oficial y KoSIT (CII y UBL) o el XSD de Facturae, el mismo
   motor que validar-factura-electronica. Si no pasa, el trabajo falla con la primera regla incumplida: nunca se entrega
   una factura que el validador rechaza. Factur-X: la representación de factura-electronica-a-pdf en PDF/A-3b (Chromium
   de Gotenberg) y el XML como `factur-x.xml` con los metadatos XMP de Factur-X (biblioteca factur-x).
2. `ocr` (solo Factur-X): veraPDF, la misma etapa que factura-electronica-a-pdf.
"""
from __future__ import annotations

import logging
import re
import shutil

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext
from tools.utils.facturas import convertir, generar, lectura, motores, representar
from tools.utils.facturas.validar import spec_label

log = logging.getLogger("worker")
XML_NAME = "factur-x.xml"
TEXTS = {
    "es": {"valid": "Validada con KoSIT ({spec}): sin errores.", "facturae": "Cumple el XSD oficial de Facturae 3.2.2. Sin firmar: "
           "fírmala con tu certificado antes de enviarla a tu cliente o a FACe.", "dir3": "Para FACe faltan los códigos DIR3 de la "
           "Administración destinataria.", "warnings": "{n} avisos del validador.", "file": "factura",
           "embedded": "PDF/A-3 con la factura electrónica generada incrustada ({name})."},
    "en": {"valid": "Validated with KoSIT ({spec}): no errors.", "facturae": "Meets the official Facturae 3.2.2 XSD. Not signed: "
           "sign it with your certificate before sending it to your customer or to FACe.", "dir3": "For FACe, the receiving "
           "administration's DIR3 codes are missing.", "warnings": "{n} validator warnings.", "file": "invoice",
           "embedded": "PDF/A-3 with the generated e-invoice embedded ({name})."},
}


def _texts(ctx: ToolContext) -> dict:
    return TEXTS.get(ctx.locale, TEXTS["es"])


def _name(ctx: ToolContext, ext: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", ctx.options.factura.numero).strip("-.")[:60] or "1"
    return f"{_texts(ctx)['file']}-{safe}.{ext}"


def validate(ctx: ToolContext, data: bytes, syntax: str) -> tuple[str, int]:
    """El veredicto del validador; si rechaza, ToolError con la primera regla. Devuelve la especificación y los avisos."""
    root, inv = lectura.read_invoice(data)
    if syntax == "facturae":
        result = motores.facturae(ctx.settings, root, data, lectura.facturae_version(root), check_signature=False)
    else:
        errors = motores.syntax_errors(ctx.settings, root, syntax)
        if errors:
            log.warning("factura generada que no cumple el XSD", extra={"error_code": errors[0][:200]})
            raise ToolError(ErrorCode.INVALID_OPTIONS, f"einvoice_invalid:XSD {errors[0][:160]}")
        result = motores.kosit(ctx.settings, data, ctx.work)
    failing = [f for f in result.findings if f.level == "error"]
    if not result.accepted or failing:
        first = failing[0] if failing else None
        log.warning("factura generada rechazada", extra={"error_code": first.code if first else "KoSIT"})
        rule = f"{first.code}: {first.text[:160]}" if first else "KoSIT"
        raise ToolError(ErrorCode.INVALID_OPTIONS, f"einvoice_invalid:{rule}")
    warnings = sum(1 for f in result.findings if f.level == "warning")
    return spec_label(inv), warnings


def _utils_stage(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    t = _texts(ctx)
    if not o.factura.lineas:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "einvoice_lines")
    data, syntax = generar.build(o.factura, o.formato, o.perfil)
    ctx.report(0.3, None)
    spec, warnings = validate(ctx, data, syntax)
    note = t["facturae"] if syntax == "facturae" else t["valid"].format(spec=spec)
    if syntax == "facturae" and not o.factura.unidad_tramitadora.strip():
        note += " " + t["dir3"]
    if warnings:
        note += " " + t["warnings"].format(n=warnings)
    if o.formato != "facturx":
        name = _name(ctx, "xml")
        dst = ctx.output(name)
        dst.write_bytes(data)
        return [{"path": str(dst), "name": name, "note": note}]
    # Factur-X: la representación en PDF/A-3b y el XML con los metadatos de Factur-X.
    import facturx

    root, inv = lectura.read_invoice(data)
    detail = representar.detail_of(root, inv)
    lang = representar.language_of(detail, ctx.locale, o.factura.idioma)
    xml_name = "xrechnung.xml" if o.perfil == "xrechnung" else XML_NAME
    pdf = convertir._pdf(ctx, representar.render(detail, lang, spec, xml_name), True, 0)
    relationship = "data" if o.perfil in ("minimum", "basicwl") else "alternative"
    out = facturx.generate_from_binary(pdf.read_bytes(), data, flavor="factur-x", level="autodetect", check_xsd=False,
                                       lang=lang, afrelationship=relationship)
    if o.perfil == "xrechnung":
        out = xrechnung_profile(out)
    pdf.write_bytes(out)
    stage = ctx.stage_dir()
    (stage / XML_NAME).write_bytes(data)
    import json

    (stage / convertir.MANIFEST).write_text(json.dumps([{"n": 0, "name": _name(ctx, "pdf"), "xml": xml_name, "warnings": [note]}],
                                                       ensure_ascii=False), encoding="utf-8")
    ctx.handoff("ocr", convertir.STAGE, convertir._texts(ctx)["check"], keep_secrets=False)
    return []  # no se llega: handoff


def xrechnung_profile(pdf_bytes: bytes) -> bytes:
    """Factur-X 1.0.07 y ZUGFeRD 2.3: el perfil XRECHNUNG lleva `xrechnung.xml` y ConformanceLevel XRECHNUNG (la
    biblioteca factur-x lo trata como EN 16931)."""
    import io

    import pikepdf

    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        spec = pdf.attachments[XML_NAME].obj
        data = pdf.attachments[XML_NAME].get_file().read_bytes()
        del pdf.attachments[XML_NAME]
        new = pikepdf.AttachedFileSpec(pdf, data, filename="xrechnung.xml", description=str(spec.get("/Desc", "")),
                                       mime_type="text/xml", relationship=pikepdf.Name.Alternative)
        pdf.attachments["xrechnung.xml"] = new
        pdf.Root.AF = pikepdf.Array([pdf.attachments["xrechnung.xml"].obj])
        xmp = pdf.Root.Metadata.read_bytes()
        xmp = re.sub(rb"(<fx:ConformanceLevel>)[^<]*(</fx:ConformanceLevel>)", rb"\1XRECHNUNG\2", xmp)
        xmp = re.sub(rb"(<fx:DocumentFileName>)[^<]*(</fx:DocumentFileName>)", rb"\1xrechnung.xml\2", xmp)
        # PDF/A: el flujo de metadatos va sin filtro.
        pdf.Root.Metadata = pdf.make_stream(xmp, Type=pikepdf.Name.Metadata, Subtype=pikepdf.Name.XML)
        buf = io.BytesIO()
        pdf.save(buf)
    return buf.getvalue()


def _verapdf_stage(ctx: ToolContext) -> list[dict]:
    outputs = convertir._verapdf_stage(ctx)
    # La nota de factura-electronica-a-pdf dice «el XML original»; aquí el XML se ha generado.
    original = convertir._texts(ctx)["embedded"]
    for o in outputs:
        if o.get("note") and o["name"].endswith(".pdf"):
            for name in (XML_NAME, "xrechnung.xml"):
                o["note"] = o["note"].replace(original.format(name=name), _texts(ctx)["embedded"].format(name=name))
    xml = ctx.store.job_dir(ctx.job_id) / "stage" / XML_NAME
    if xml.exists():
        name = _name(ctx, "xml")
        dst = ctx.output(name)
        shutil.copyfile(xml, dst)
        outputs.append({"path": str(dst), "name": name, "note": None})
    return outputs


def run(ctx: ToolContext) -> list[dict]:
    return _verapdf_stage(ctx) if ctx.stage == convertir.STAGE else _utils_stage(ctx)
