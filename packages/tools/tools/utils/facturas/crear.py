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
           "fírmala con tu certificado antes de enviarla a FACe o a tu cliente.", "warnings": "{n} avisos del validador.",
           "file": "factura"},
    "en": {"valid": "Validated with KoSIT ({spec}): no errors.", "facturae": "Meets the official Facturae 3.2.2 XSD. Not signed: "
           "sign it with your certificate before sending it to FACe or your customer.", "warnings": "{n} validator warnings.",
           "file": "invoice"},
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
    pdf = convertir._pdf(ctx, representar.render(detail, lang, spec, XML_NAME), True, 0)
    relationship = "data" if o.perfil in ("minimum", "basicwl") else "alternative"
    out = facturx.generate_from_binary(pdf.read_bytes(), data, flavor="factur-x", level="autodetect", check_xsd=False,
                                       lang=lang, afrelationship=relationship)
    pdf.write_bytes(out)
    stage = ctx.stage_dir()
    (stage / XML_NAME).write_bytes(data)
    import json

    (stage / convertir.MANIFEST).write_text(json.dumps([{"n": 0, "name": _name(ctx, "pdf"), "xml": XML_NAME, "warnings": [note]}],
                                                       ensure_ascii=False), encoding="utf-8")
    ctx.handoff("ocr", convertir.STAGE, convertir._texts(ctx)["check"], keep_secrets=False)
    return []  # no se llega: handoff


def _verapdf_stage(ctx: ToolContext) -> list[dict]:
    outputs = convertir._verapdf_stage(ctx)
    xml = ctx.store.job_dir(ctx.job_id) / "stage" / XML_NAME
    if xml.exists():
        name = _name(ctx, "xml")
        dst = ctx.output(name)
        shutil.copyfile(xml, dst)
        outputs.append({"path": str(dst), "name": name, "note": None})
    return outputs


def run(ctx: ToolContext) -> list[dict]:
    return _verapdf_stage(ctx) if ctx.stage == convertir.STAGE else _utils_stage(ctx)
