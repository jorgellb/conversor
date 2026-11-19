"""validar-factura-electronica (A.2 y 7.23): EN 16931, XRechnung, Peppol BIS, Factur-X/ZUGFeRD y Facturae.

Por factura: sintaxis y especificación detectadas, resultado, y por regla su identificador, gravedad, explicación propia
y qué hacer, con la parte afectada resaltada sobre la representación de la factura. Los anexos (UBL, CII, Facturae y los
demás archivos incrustados de un PDF) salen como archivos. Lo que impide leer un archivo se queda en su informe y en el
resumen; el veredicto de KoSIT manda, con los niveles del escenario (D-193).
En lote (varios archivos o un ZIP), además un resumen CSV (número, emisor, fecha, total y resultado). Las entradas se
borran al terminar (A.2: «el archivo se borra al terminar»).
"""
from __future__ import annotations

import csv
import html
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.storage import sanitize_filename
from core.zipguard import check_zip
from tools.base import ToolContext, zip_files
from tools.utils.facturas import explicaciones, lectura, motores

MAX_INVOICES = 100
MAX_ATTACHMENT_BYTES = lectura.MAX_ATTACHMENT_BYTES
MAX_BATCH_BYTES = 400 * 1024 * 1024  # XML y PDF descomprimidos de un ZIP, en disco (se leen de uno en uno)
# Parte de la representación que corresponde a cada elemento de la ruta del fallo (UBL y CII).
SECTIONS = (
    ("totales", ("LegalMonetaryTotal", "SpecifiedTradeSettlementHeaderMonetarySummation", "InvoiceTotals")),
    ("iva", ("TaxTotal", "TaxSubtotal", "ApplicableTradeTax", "TaxesOutputs")),
    ("lineas", ("InvoiceLine", "CreditNoteLine", "IncludedSupplyChainTradeLineItem", "Items")),
    ("comprador", ("AccountingCustomerParty", "BuyerTradeParty", "BuyerParty")),
    ("vendedor", ("AccountingSupplierParty", "SellerTradeParty", "SellerParty")),
    ("pago", ("PaymentMeans", "PaymentTerms", "SpecifiedTradeSettlementPaymentMeans", "SpecifiedTradePaymentTerms", "PaymentDetails")),
)
# Reglas que se evalúan sobre la factura entera (su ruta no dice a qué parte afectan): la parte de su término de negocio.
CODE_SECTIONS = {
    **dict.fromkeys(("BR-06", "BR-08", "BR-09", "BR-S-02", "BR-CO-09", "BR-CO-26", "BR-DE-2", "PEPPOL-EN16931-R020"), "vendedor"),
    **dict.fromkeys(("BR-07", "BR-10", "BR-11", "PEPPOL-EN16931-R010", "BR-DE-15"), "comprador"),
    **dict.fromkeys(("BR-12", "BR-13", "BR-14", "BR-15", "BR-CO-10", "BR-CO-13", "BR-CO-15", "BR-CO-16"), "totales"),
    **dict.fromkeys(("BR-16", "BR-21", "BR-22", "BR-23", "BR-24", "BR-25", "BR-26"), "lineas"),
    **dict.fromkeys(("BR-CO-14", "BR-CO-17", "BR-S-08"), "iva"),
    **dict.fromkeys(("BR-CO-25", "BR-DE-1"), "pago"),
}
SPEC_LABEL = [
    ("xeinkauf.de:kosit:xrechnung", "XRechnung"), ("peppol.eu:2017:poacc:billing", "Peppol BIS Billing 3.0"),
    ("factur-x.eu:1p0:minimum", "Factur-X MINIMUM"), ("factur-x.eu:1p0:basicwl", "Factur-X BASIC WL"),
    ("factur-x.eu:1p0:basic", "Factur-X BASIC"), ("factur-x.eu:1p0:extended", "Factur-X EXTENDED"),
]
NOT_EN16931 = ("factur-x.eu:1p0:minimum", "factur-x.eu:1p0:basicwl")

TEXT = {
    "es": {"title": "Validación de factura electrónica", "file": "Archivo", "syntax": "Sintaxis", "spec": "Especificación",
           "result_ok": "Válida", "result_ko": "No válida", "result_warn": "Válida con avisos", "number": "Número", "date": "Fecha",
           "seller": "Emisor", "buyer": "Cliente", "total": "Importe a pagar", "lines": "Líneas", "rules": "Reglas",
           "code": "Regla", "level": "Gravedad", "what": "Qué pasa", "todo": "Qué hacer", "where": "Dónde", "engine_text": "Texto del motor",
           "levels": {"error": "Error", "fatal": "Error", "warning": "Aviso", "information": "Información"},
           "sections": {"totales": "Totales", "iva": "IVA", "lineas": "Líneas", "comprador": "Cliente", "vendedor": "Emisor",
                        "pago": "Pago", "documento": "Documento"},
           "none": "Sin fallos ni avisos.", "attachments": "Anexos (se entregan como archivos aparte)", "xml": "XML de la factura",
           "not_full": "MINIMUM y BASIC WL no son facturas EN 16931 completas: sirven como resumen, no como factura electrónica.",
           "other_cius": "Validada solo con las reglas EN 16931: no hay configuración pública para su CIUS ({spec}).",
           "signature": {"sin_firma": "Sin firma electrónica.", "valida": "Firma XAdES íntegra (el certificado no se comprueba aquí: usa verificar-firma).",
                         "no_valida": "La firma no es válida o no cubre la factura entera.",
                         "valida_dsig": "Firma XML íntegra; sus propiedades XAdES (si las tiene, de una versión anterior a 1.3.2) no se comprueban aquí."},
           "no_scenario": "No es una factura de una sintaxis o especificación que se pueda validar (UBL, CII o Facturae con su CustomizationID).",
           "no_xml": "El PDF no lleva una factura electrónica incrustada (Factur-X, ZUGFeRD o XRechnung).",
           "unreadable": "No se ha podido leer: {reason}.", "reasons": {"xml_dtd": "el XML declara un DOCTYPE o entidades, que no se admiten",
                                                                     "xml_syntax": "el XML no está bien formado", "pdf": "el PDF está dañado",
                                                                     "not_invoice": "no es una factura UBL, CII ni Facturae",
                                                                     "password": "el PDF está protegido con contraseña",
                                                                     "too_big": "supera los 20 MB por factura",
                                                                     "pdf_attachment_filter": "la factura incrustada usa una compresión no admitida"},
           "engine": "Validado con KoSIT y las reglas oficiales; Facturae con su XSD oficial.",
           "report": "validacion-{stem}.html", "summary": "resumen-validacion.csv", "zip": "validacion-facturas.zip",
           "csv": ["archivo", "numero", "emisor", "nif_emisor", "fecha", "total", "moneda", "resultado", "especificacion", "errores", "avisos"],
           "note_ok": "Válida ({spec}).", "note_ko": "No válida ({spec}): {n} error(es).", "note_warn": "Válida con {n} aviso(s) ({spec}).",
           "note_bad": "No se ha podido validar.", "note_rejected": "No válida ({spec}): KoSIT la rechaza.", "batch": "{ok} de {n} facturas válidas."},
    "en": {"title": "E-invoice validation", "file": "File", "syntax": "Syntax", "spec": "Specification",
           "result_ok": "Valid", "result_ko": "Not valid", "result_warn": "Valid with warnings", "number": "Number", "date": "Date",
           "seller": "Seller", "buyer": "Customer", "total": "Amount due", "lines": "Lines", "rules": "Rules",
           "code": "Rule", "level": "Severity", "what": "What is wrong", "todo": "What to do", "where": "Where", "engine_text": "Engine text",
           "levels": {"error": "Error", "fatal": "Error", "warning": "Warning", "information": "Information"},
           "sections": {"totales": "Totals", "iva": "VAT", "lineas": "Lines", "comprador": "Customer", "vendedor": "Seller",
                        "pago": "Payment", "documento": "Document"},
           "none": "No errors or warnings.", "attachments": "Attachments (delivered as separate files)", "xml": "Invoice XML",
           "not_full": "MINIMUM and BASIC WL are not complete EN 16931 invoices: they work as a summary, not as an e-invoice.",
           "other_cius": "Validated with the EN 16931 rules only: there is no public configuration for its CIUS ({spec}).",
           "signature": {"sin_firma": "No electronic signature.", "valida": "XAdES signature intact (the certificate is not checked here: use verify-signature).",
                         "no_valida": "The signature is not valid or does not cover the whole invoice.",
                         "valida_dsig": "XML signature intact; its XAdES properties (if any, from a version before 1.3.2) are not checked here."},
           "no_scenario": "It is not an invoice of a syntax or specification that can be validated (UBL, CII or Facturae with its CustomizationID).",
           "no_xml": "The PDF does not carry an embedded e-invoice (Factur-X, ZUGFeRD or XRechnung).",
           "unreadable": "It could not be read: {reason}.", "reasons": {"xml_dtd": "the XML declares a DOCTYPE or entities, which are not allowed",
                                                                     "xml_syntax": "the XML is not well formed", "pdf": "the PDF is damaged",
                                                                     "not_invoice": "it is not a UBL, CII or Facturae invoice",
                                                                     "password": "the PDF is password-protected",
                                                                     "too_big": "it exceeds 20 MB per invoice",
                                                                     "pdf_attachment_filter": "the embedded invoice uses an unsupported compression"},
           "engine": "Validated with KoSIT and the official rules; Facturae with its official XSD.",
           "report": "validation-{stem}.html", "summary": "validation-summary.csv", "zip": "invoice-validation.zip",
           "csv": ["file", "number", "seller", "seller_vat", "date", "total", "currency", "result", "specification", "errors", "warnings"],
           "note_ok": "Valid ({spec}).", "note_ko": "Not valid ({spec}): {n} error(s).", "note_warn": "Valid with {n} warning(s) ({spec}).",
           "note_bad": "It could not be validated.", "note_rejected": "Not valid ({spec}): rejected by KoSIT.", "batch": "{ok} of {n} invoices valid."},
}


@dataclass
class Checked:
    name: str
    invoice: lectura.Invoice | None
    result: motores.Result | None
    problem: str = ""  # no_xml, no_scenario o un motivo de lectura
    data: bytes = b""

    @property
    def errors(self) -> int:
        return sum(1 for f in (self.result.findings if self.result else []) if f.level in ("error", "fatal"))

    @property
    def warnings(self) -> int:
        return sum(1 for f in (self.result.findings if self.result else []) if f.level == "warning")

    @property
    def status(self) -> str:
        if self.problem or self.result is None or (self.result.engine == "kosit" and not self.result.scenario):
            return "bad"
        if self.result.engine == "kosit":  # el veredicto es el de KoSIT, con los niveles del escenario (customLevel)
            return ("warn" if self.warnings or self.errors else "ok") if self.result.accepted else "ko"
        if not self.result.accepted or self.errors:
            return "ko"
        return "warn" if self.warnings else "ok"


def spec_label(inv: lectura.Invoice | None, scenario: str = "") -> str:
    if inv is None:
        return scenario
    if inv.syntax == "facturae":
        return inv.spec
    for key, label in SPEC_LABEL:
        if key in inv.spec:
            return label
    if inv.spec == "urn:cen.eu:en16931:2017":
        return f"EN 16931 ({inv.syntax.upper()})"
    return scenario or inv.spec


TRANSIENT_OR_INTERNAL = (ErrorCode.ENGINE_FAILED, ErrorCode.INTERNAL)


def check(ctx: ToolContext, name: str, path: Path, is_pdf: bool = False) -> Checked:
    """Una factura. Lo que impide leer este archivo (dañado, cifrado, demasiado grande, sin factura) se queda en su
    informe y en el resumen; solo los fallos del motor (KoSIT caído, que se reintenta) paran la tarea entera."""
    extra: list[tuple[str, str, bytes]] = []
    try:
        if is_pdf:
            found = lectura.xml_from_pdf(path)
            if found is None:
                return Checked(name, None, None, "no_xml")
            data, _xml_name, extra = found
        else:
            if path.stat().st_size > lectura.MAX_XML_BYTES:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "xml_size")
            data = path.read_bytes()
        root, inv = lectura.read_invoice(data)
    except ToolError as err:
        if err.code in TRANSIENT_OR_INTERNAL:
            raise
        return Checked(name, None, None, _reason(err))  # sin repetir en el informe lo que no se ha leído
    inv.attachments.extend(extra[: lectura.MAX_ATTACHMENTS - len(inv.attachments)])
    if inv.syntax == "facturae":
        result = motores.facturae(ctx.settings, root, data, lectura.facturae_version(root))
    else:
        result = motores.kosit(ctx.settings, data, ctx.work)
        if not result.scenario:
            return Checked(name, inv, result, "no_scenario", data)
    return Checked(name, inv, result, "", data)


def _reason(err: ToolError) -> str:
    detail = (err.detail or "").split(":", 1)[0]
    if err.code == ErrorCode.PASSWORD_REQUIRED:
        return "password"
    if err.code == ErrorCode.LIMIT_EXCEEDED:
        return "too_big"
    return detail if detail in ("xml_dtd", "xml_syntax", "pdf", "not_invoice", "pdf_attachment_filter") else "xml_syntax"


def _section(location: str, code: str = "") -> str:
    for key, names in SECTIONS:
        if any(n in location for n in names):
            return key
    return CODE_SECTIONS.get(code, "documento")


def render(item: Checked, locale: str) -> str:
    t = TEXT.get(locale, TEXT["es"])
    e = html.escape
    inv, result = item.invoice, item.result
    status = item.status
    badge = {"ok": t["result_ok"], "warn": t["result_warn"], "ko": t["result_ko"], "bad": t["result_ko"]}[status]
    parts = [f"<h1>{e(t['title'])}</h1><p class=\"v {'ok' if status in ('ok', 'warn') else 'ko'}\">{e(badge)}</p>",
             f"<table class=\"s\"><tr><th>{e(t['file'])}</th><td>{e(item.name)}</td></tr>"]
    if inv is not None:
        parts.append(f"<tr><th>{e(t['syntax'])}</th><td>{e(inv.syntax.upper())}</td></tr>"
                     f"<tr><th>{e(t['spec'])}</th><td>{e(spec_label(inv, result.scenario if result else ''))}"
                     f"<br><code>{e(inv.spec)}</code></td></tr>")
    parts.append("</table>")
    notes = []
    if item.problem:
        reason = t["reasons"].get(item.problem, item.problem)
        notes.append(t["no_xml"] if item.problem == "no_xml" else t["no_scenario"] if item.problem == "no_scenario"
                     else t["unreadable"].format(reason=reason))
    if inv is not None and any(k in inv.spec for k in NOT_EN16931):
        notes.append(t["not_full"])
    if result is not None and result.scenario.startswith("EN16931 con otra CIUS"):
        notes.append(t["other_cius"].format(spec=inv.spec if inv else ""))
    if result is not None and result.signature:
        notes.append(t["signature"][result.signature])
    parts.extend(f"<p class=\"n\">{e(n)}</p>" for n in notes)
    highlighted: dict[str, list[str]] = {}
    for f in (result.findings if result else []):
        highlighted.setdefault(_section(f.location, f.code), []).append(f.code)
    if inv is not None:
        def block(key: str, label: str, rows: list[tuple[str, str]]) -> str:
            codes = highlighted.get(key, [])
            mark = f" <span class=\"tag\">{e(', '.join(sorted(set(codes))[:8]))}</span>" if codes else ""
            body = "".join(f"<tr><th>{e(k)}</th><td>{e(v or '—')}</td></tr>" for k, v in rows)
            return f"<section class=\"b{' hl' if codes else ''}\"><h3>{e(label)}{mark}</h3><table>{body}</table></section>"

        parts.append("<div class=\"rep\">")
        parts.append(block("documento", t["sections"]["documento"], [(t["number"], inv.number), (t["date"], inv.date)]))
        parts.append(block("vendedor", t["sections"]["vendedor"], [(t["seller"], inv.seller), ("NIF/VAT", inv.seller_vat)]))
        parts.append(block("comprador", t["sections"]["comprador"], [(t["buyer"], inv.buyer), ("NIF/VAT", inv.buyer_vat)]))
        line_rows = [(desc, f"{qty} · {amount}") for desc, qty, amount in inv.lines[:50]]
        parts.append(block("lineas", t["sections"]["lineas"], line_rows or [(t["lines"], "")]))
        parts.append(block("totales", t["sections"]["totales"], [(t["total"], f"{inv.total} {inv.currency}".strip())]))
        for key in ("iva", "pago"):
            if key in highlighted:
                parts.append(block(key, t["sections"][key], []))
        parts.append("</div>")
    findings = result.findings if result else []
    if findings:
        rows = []
        for f in findings[:500]:
            what, todo = explicaciones.explain(f.code, locale)
            lvl = t["levels"].get(f.level, f.level)
            rows.append(f"<tr class=\"{e(f.level)}\"><td class=\"c\">{e(f.code)}</td><td>{e(lvl)}</td><td>{e(what)}"
                        f"<details><summary>{e(t['engine_text'])}</summary>{e(f.text)}</details></td><td>{e(todo)}</td>"
                        f"<td>{e(t['sections'][_section(f.location, f.code)])}</td></tr>")
        parts.append(f"<h2>{e(t['rules'])}</h2><table class=\"r\"><thead><tr><th>{e(t['code'])}</th><th>{e(t['level'])}</th>"
                     f"<th>{e(t['what'])}</th><th>{e(t['todo'])}</th><th>{e(t['where'])}</th></tr></thead><tbody>{''.join(rows)}</tbody></table>")
    elif result is not None and not item.problem:
        parts.append(f"<p>{e(t['none'])}</p>")
    if inv is not None and inv.attachments:
        parts.append(f"<h2>{e(t['attachments'])}</h2><ul>" + "".join(f"<li>{e(lectura.attachment_name(n, m))} ({e(m or '?')})</li>" for n, m, _ in inv.attachments) + "</ul>")
    if item.data:
        parts.append(f"<details><summary>{e(t['xml'])}</summary><pre>{e(lectura.pretty_xml(item.data)[:400_000])}</pre></details>")
    parts.append(f"<p class=\"m\">{e(t['engine'])}</p>")
    return (f"<!doctype html><html lang=\"{e(locale)}\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\">"
            f"<title>{e(t['title'])}: {e(item.name)}</title><style>"
            "body{font:15px/1.5 system-ui,sans-serif;color:#1f2328;max-width:1000px;margin:24px auto;padding:0 16px}"
            "h1{font-size:22px}h2{font-size:18px;margin-top:28px}h3{font-size:15px;margin:0 0 6px}"
            ".v{display:inline-block;padding:4px 12px;border-radius:6px;font-weight:600}.ok{background:#dafbe1;color:#116329}"
            ".ko{background:#ffebe9;color:#a40e26}table{border-collapse:collapse;width:100%}th,td{padding:5px 8px;text-align:left;vertical-align:top}"
            ".s th{width:12em;color:#59636e}.r th,.r td{border-bottom:1px solid #d0d7de}.c{white-space:nowrap;font-family:ui-monospace,monospace}"
            ".r tr.error td:first-child,.r tr.fatal td:first-child{border-left:4px solid #cf222e}.r tr.warning td:first-child{border-left:4px solid #bf8700}"
            ".rep{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-top:16px}"
            ".b{border:1px solid #d0d7de;border-radius:8px;padding:10px}.b th{color:#59636e;width:9em}"
            ".hl{border:2px solid #cf222e;background:#fff5f5}.tag{background:#cf222e;color:#fff;border-radius:4px;padding:0 6px;font-size:12px}"
            ".n{background:#fff8c5;padding:8px 12px;border-radius:6px}pre{white-space:pre-wrap;font-size:12px;background:#f6f8fa;padding:8px}"
            "details{color:#59636e;font-size:13px}.m{color:#59636e;font-size:13px}@media print{details{display:none}}"
            "</style></head><body>" + "".join(parts) + "</body></html>")


def _expand(ctx: ToolContext) -> list[tuple[str, Path | None, bool]]:
    """(nombre, ruta o None si supera el tope, es PDF) de cada factura de las entradas. Los ZIP se abren con zipguard (12.3), se cuentan antes de
    leer nada y sus miembros se extraen a disco de uno en uno, con tope por miembro y por lote: en memoria solo está la
    factura que se valida."""
    out: list[tuple[str, Path | None, bool]] = []
    for inp in ctx.inputs:
        ext = (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()
        if ext != "zip":
            out.append((inp.name, inp.path, ext == "pdf"))
            continue
        check_zip(inp.path)
        with zipfile.ZipFile(inp.path) as zf:
            members = [i for i in zf.infolist() if not i.is_dir() and not Path(i.filename).name.startswith(".")
                       and Path(i.filename).suffix.lower() in (".xml", ".pdf")]
            if len(out) + len(members) > MAX_INVOICES:
                raise ToolError(ErrorCode.TOO_MANY_FILES, f"invoices:{len(out) + len(members)}>{MAX_INVOICES}")
            total = sum(i.file_size for i in members)
            if total > MAX_BATCH_BYTES:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"zip_total:{total // 1048576}>{MAX_BATCH_BYTES // 1048576}")
            for info in members:
                base = Path(info.filename).name
                is_pdf = base.lower().endswith(".pdf")
                dst = ctx.work / f"zip-{len(out)}{'.pdf' if is_pdf else '.xml'}"
                dst.parent.mkdir(parents=True, exist_ok=True)
                limit = lectura.MAX_XML_BYTES * (5 if is_pdf else 1)
                if info.file_size > limit:
                    out.append((base, None, is_pdf))  # se informa en su fila como demasiado grande, sin leerlo
                    continue
                try:
                    with zf.open(info) as src, dst.open("wb") as fh:
                        copied = 0
                        while chunk := src.read(1 << 20):
                            copied += len(chunk)
                            if copied > limit:
                                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "zip_member")
                            fh.write(chunk)
                except (RuntimeError, zipfile.BadZipFile, NotImplementedError, OSError) as exc:  # cifrado, CRC o método
                    raise ToolError(ErrorCode.CORRUPT_FILE, "zip") from exc
                out.append((base, dst, is_pdf))
        if len(out) > MAX_INVOICES:
            raise ToolError(ErrorCode.TOO_MANY_FILES, f"invoices:{len(out)}>{MAX_INVOICES}")
    if len(out) > MAX_INVOICES:
        raise ToolError(ErrorCode.TOO_MANY_FILES, f"invoices:{len(out)}>{MAX_INVOICES}")
    return out


def run(ctx: ToolContext) -> list[dict]:
    t = TEXT.get(ctx.locale, TEXT["es"])
    items = _expand(ctx)
    outputs: list[dict] = []
    checked: list[Checked] = []
    used: set[str] = set()
    for n, (name, path, is_pdf) in enumerate(items):
        ctx.report(n / max(1, len(items)), None)
        if path is None:
            item = Checked(name, None, None, "too_big")
        else:
            item = check(ctx, name, path, is_pdf)
        checked.append(item)
        stem = Path(name).stem or "factura"
        report_name = t["report"].format(stem=stem)
        while report_name in used:
            stem += "-2"
            report_name = t["report"].format(stem=stem)
        used.add(report_name)
        dst = ctx.output(report_name)
        dst.write_text(render(item, ctx.locale), encoding="utf-8")
        spec = spec_label(item.invoice, item.result.scenario if item.result else "")
        note = {"ok": t["note_ok"].format(spec=spec), "warn": t["note_warn"].format(n=item.warnings + item.errors, spec=spec),
                "ko": t["note_ko"].format(n=item.errors, spec=spec) if item.errors else t["note_rejected"].format(spec=spec),
                "bad": t["note_bad"]}[item.status]
        outputs.append({"path": str(dst), "name": report_name, "note": note})
        for k, (att_name, mime, content) in enumerate((item.invoice.attachments if item.invoice else [])[: lectura.MAX_ATTACHMENTS], 1):
            if len(content) > MAX_ATTACHMENT_BYTES:
                continue
            base = lectura.attachment_name(att_name, mime)
            safe = sanitize_filename(f"{stem}-anexo-{k}-{base}")[:120] or f"{stem}-anexo-{k}"
            att = ctx.output(safe)
            att.write_bytes(content)
            outputs.append({"path": str(att), "name": safe, "note": None})
        item.data = b""  # el XML ya está en el informe; no se guarda hasta el final del lote
        if item.invoice is not None:
            item.invoice.attachments = [(a, m, b"") for a, m, _ in item.invoice.attachments]
    if len(checked) > 1:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(t["csv"])
        labels = {"ok": t["result_ok"], "warn": t["result_warn"], "ko": t["result_ko"], "bad": t["note_bad"]}
        for item in checked:
            inv = item.invoice
            writer.writerow([_csv_safe(item.name), *(_csv_safe(v) for v in ((inv.number, inv.seller, inv.seller_vat, inv.date, inv.total, inv.currency)
                                                                             if inv else ("",) * 6)),
                             labels[item.status], _csv_safe(spec_label(inv, item.result.scenario if item.result else "")), item.errors, item.warnings])
        summary = ctx.output(t["summary"])
        summary.write_text(buf.getvalue(), encoding="utf-8-sig")
        ok = sum(1 for i in checked if i.status in ("ok", "warn"))
        outputs.insert(0, {"path": str(summary), "name": t["summary"], "note": t["batch"].format(ok=ok, n=len(checked))})
    if len(outputs) > 1:
        bundle = ctx.output(t["zip"])
        zip_files([(Path(o["path"]), o["name"]) for o in outputs], bundle)
        outputs.append({"path": str(bundle), "name": t["zip"], "note": "zip"})
    for inp in ctx.inputs:  # A.2: el archivo se borra al terminar
        inp.path.unlink(missing_ok=True)
    return outputs


def _csv_safe(value) -> str:
    """Evita la inyección de fórmulas al abrir el CSV en una hoja de cálculo."""
    text = str(value or "")
    if re.fullmatch(r"-?\d+(?:[.,]\d+)?", text):  # importes negativos de los abonos
        return text
    return "'" + text if re.match(r"^[=+\-@\t\r]", text) else text
