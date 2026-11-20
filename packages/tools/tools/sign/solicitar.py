"""solicitar-firmas, parte de los workers (7.7, F4-C2, D-202): campos de firma, firma de cada firmante y sellado final.

- `preparar` (`workerpdf`, la crea la página): comprueba el PDF y deja un campo de firma vacío para cada firmante, el que
  eligió del propio PDF o uno nuevo en una página de firmas que se añade al final. No firma nada.
- `firmante` (`workersign`, la crea la API cuando el firmante confirma con el código de su correo): sello de la plataforma
  PAdES B-T en el campo del firmante, con la imagen de su firma y «Firmado por … (correo verificado)».
- `final` (`workersign`, la crea beat cuando han firmado todos): sello invisible PAdES B-LT sobre el documento y
  certificado de auditoría en PDF (Chromium de Gotenberg, a partir de `audit_events`), también sellado.

Las fases `firmante` y `final` son de la solicitud (propietario «request»): POST /v1/jobs solo admite `preparar`
(`precheck`) y aquí se vuelve a comprobar, porque el sello daría por buena una firma o una auditoría inventadas.
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import io
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from core.errors import AppError, ErrorCode, ToolError
from core.signreq import FREE_MAX_SIGNERS, MAX_SIGNERS, OWNER_TYPE, field_name
from core.signreq import MAX_MB as REQUEST_MB
from tools.base import ToolContext, derived_name
from tools.sign import firmar

log = logging.getLogger("worker")
MAX_MB = firmar.MAX_MB
BOX_W, BOX_H, GAP, MARGIN = 230.0, 70.0, 34.0, 50.0

TEXTS = {
    "es": {"page": "Firmas", "label": "Firma de {name}", "stamp": "Firmado por: {name}\nCorreo verificado: {email}\nFecha: %(ts)s · sello de {site}",
           "reason": "Firmado por {name} ({email}), verificado por correo", "final": "Sello final de {site}", "signed": "-firmado",
           "certificate": "certificado-auditoria.pdf"},
    "en": {"page": "Signatures", "label": "Signature of {name}", "stamp": "Signed by: {name}\nVerified email: {email}\nDate: %(ts)s · {site} seal",
           "reason": "Signed by {name} ({email}), verified by email", "final": "{site} final seal", "signed": "-signed",
           "certificate": "audit-certificate.pdf"},
}


def precheck(settings, plan, owner_type: str, options: dict, paths: list[Path], locale: str = "es") -> None:
    """POST /v1/jobs: solo la fase `preparar`, con cuenta, y como mucho 10 firmantes (3 con la cuenta gratuita)."""
    if options.get("fase", "preparar") != "preparar":
        raise AppError(ErrorCode.INVALID_OPTIONS, status=400, detail="request_stage")
    if owner_type != "user":
        raise AppError(ErrorCode.UNAUTHORIZED, status=401, detail="request_account")
    if not settings.SEAL_ENABLED:
        raise AppError(ErrorCode.TOOL_DISABLED, status=400, detail="seal_disabled")
    signers = options.get("firmantes") or []
    limit = MAX_SIGNERS if getattr(plan, "id", "") == "pro" else FREE_MAX_SIGNERS
    if not signers:
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422, detail="request_no_signers")
    if len(signers) > limit:
        raise AppError(ErrorCode.LIMIT_EXCEEDED, status=422, detail=f"request_signers:{len(signers)}>{limit}")
    for path in paths:
        if path.stat().st_size > REQUEST_MB * 1024 * 1024:
            raise AppError(ErrorCode.LIMIT_EXCEEDED, status=413, detail=f"seal_size:{path.stat().st_size // 1048576}>{REQUEST_MB}")


# --- preparar -----------------------------------------------------------------------------------------------------------


def _pdf_text(value: str) -> bytes:
    """Texto para Helvetica con WinAnsiEncoding (la página de firmas no incrusta fuentes): lo que no cabe, «?»."""
    raw = value.encode("cp1252", "replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _layout(width: float, height: float, count: int) -> list[list[tuple[float, float, float, float]]]:
    """Recuadros de `count` firmas en páginas de `width` × `height`, en dos columnas si caben."""
    cols = 2 if width >= 2 * BOX_W + 3 * MARGIN / 1.5 else 1
    box_w = min(BOX_W, (width - (cols + 1) * MARGIN / 1.5) / cols)
    top = height - MARGIN - 40
    rows = max(1, int((top - MARGIN) // (BOX_H + GAP)))
    pages: list[list[tuple[float, float, float, float]]] = []
    for i in range(count):
        slot = i % (rows * cols)
        if slot == 0:
            pages.append([])
        row, col = divmod(slot, cols)
        x0 = MARGIN / 1.5 + col * (box_w + MARGIN / 1.5)
        y1 = top - row * (BOX_H + GAP)
        pages[-1].append((round(x0, 2), round(y1 - BOX_H, 2), round(x0 + box_w, 2), round(y1, 2)))
    return pages


def _signature_pages(data: bytes, names: list[str], locale: str) -> tuple[bytes, list[tuple[int, tuple]]]:
    """Añade al final las páginas de firmas (del tamaño visible de la última) y devuelve dónde va cada recuadro."""
    import pikepdf

    t = TEXTS.get(locale, TEXTS["es"])
    with pikepdf.open(io.BytesIO(data)) as pdf:
        last = pdf.pages[-1]
        x0, y0, x1, y1 = (float(v) for v in last.mediabox)
        width, height = x1 - x0, y1 - y0
        if int(last.obj.get("/Rotate", 0)) % 180 == 90:
            width, height = height, width
        width, height = max(width, 300.0), max(height, 300.0)
        font = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica,
                                  Encoding=pikepdf.Name.WinAnsiEncoding)
        placed: list[tuple[int, tuple]] = []
        index = 0
        for boxes in _layout(width, height, len(names)):
            ops = [b"BT /F1 14 Tf %.2f %.2f Td (%s) Tj ET" % (MARGIN / 1.5, height - MARGIN, _pdf_text(t["page"]))]
            for box in boxes:
                bx0, by0, bx1, by1 = box
                label = _pdf_text(t["label"].format(name=names[index])[:80])
                ops.append(b"q 0.6 G 0.75 w %.2f %.2f %.2f %.2f re S Q" % (bx0, by0, bx1 - bx0, by1 - by0))
                ops.append(b"BT /F1 9 Tf %.2f %.2f Td (%s) Tj ET" % (bx0, by0 - 13, label))
                placed.append((len(pdf.pages), box))
                index += 1
            page = pdf.add_blank_page(page_size=(width, height))
            page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
            page.obj.Contents = pdf.make_stream(b"\n".join(ops))
        out = io.BytesIO()
        pdf.save(out)
    return out.getvalue(), placed


def _prepare(ctx: ToolContext) -> list[dict]:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.fields import SigFieldSpec, append_signature_field, enumerate_sig_fields
    from pyhanko.sign.validation import read_certification_data

    from tools.pdf.campos_firma import _existing

    if len(ctx.inputs) != 1:
        raise ToolError(ErrorCode.TOO_MANY_FILES, "un solo PDF")
    signers = ctx.options.firmantes
    limit = MAX_SIGNERS if ctx.plan.id == "pro" else FREE_MAX_SIGNERS
    if not signers:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "request_no_signers")
    if len(signers) > limit:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"request_signers:{len(signers)}>{limit}")
    inp = ctx.inputs[0]
    data = inp.path.read_bytes()
    if len(data) > REQUEST_MB * 1024 * 1024:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"seal_size:{len(data) // 1048576}>{REQUEST_MB}")
    try:
        reader = PdfFileReader(io.BytesIO(data), strict=False)
        if reader.encrypted:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "request_encrypted")
        pages = int(reader.root["/Pages"]["/Count"])
        signed = list(reader.embedded_signatures)
        certification = read_certification_data(reader)
        empty = {name for name, _value, _ref in enumerate_sig_fields(reader, filled_status=False)}
        taken = _existing(reader)
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 - PDF roto (12.3)
        raise ToolError(ErrorCode.CORRUPT_FILE, type(exc).__name__) from exc
    if pages < 1 or pages > ctx.plan.pdf_pages:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{pages} páginas")
    if certification is not None:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "seal_locked")
    fields = [field_name(i, s.campo) for i, s in enumerate(signers)]
    if len(set(fields)) != len(fields):
        raise ToolError(ErrorCode.INVALID_OPTIONS, "request_field_repeated")
    new = []
    for i, (signer, name) in enumerate(zip(signers, fields)):
        if signer.campo.strip():
            if name not in empty:
                raise ToolError(ErrorCode.INVALID_OPTIONS, "seal_field_missing" if name not in taken else "seal_field_signed")
        elif name in taken:
            raise ToolError(ErrorCode.INVALID_OPTIONS, f"request_field_taken:{name}")
        else:
            new.append(i)
    if new and signed:
        # Una página nueva después de una firma la invalidaría: con un PDF ya firmado, solo campos que ya tenga.
        raise ToolError(ErrorCode.INVALID_OPTIONS, "request_signed_needs_fields")
    out = data
    if new:
        ctx.report(0.3, None)
        try:
            with_pages, placed = _signature_pages(data, [signers[i].nombre for i in new], ctx.locale)
            writer = IncrementalPdfFileWriter(io.BytesIO(with_pages), strict=False)
            for i, (page, box) in zip(new, placed):
                append_signature_field(writer, SigFieldSpec(sig_field_name=fields[i], on_page=page, box=box))
            buf = io.BytesIO()
            writer.write(buf)
            out = buf.getvalue()
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001 - árbol de páginas o AcroForm que no se pueden ampliar
            raise ToolError(ErrorCode.CORRUPT_FILE, type(exc).__name__) from exc
    name = inp.name if inp.name.lower().endswith(".pdf") else derived_name(inp.name, "", "pdf")
    dst = ctx.output(name)
    dst.write_bytes(out)
    return [{"path": str(dst), "name": name, "note": None}]


# --- firmante y final -------------------------------------------------------------------------------------------------


@asynccontextmanager
async def tsa_clients(settings):
    """Sesión por `egressweb` y cliente de la TSA (las pruebas lo sustituyen por el «illusionist» de certomancer)."""
    from pyhanko.sign.timestamps import HTTPTimeStamper

    from tools.sign.verificar import make_session

    session = make_session(settings.EGRESS_WEB_URL)
    try:
        yield session, HTTPTimeStamper(settings.TSA_URL, session=session, timeout=20)
    finally:
        await session.close()


def _field_box(data: bytes, field: str) -> tuple[float, float] | None:
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.fields import enumerate_sig_fields

    reader = PdfFileReader(io.BytesIO(data), strict=False)
    for name, _value, ref in enumerate_sig_fields(reader, filled_status=False):
        if name != field:
            continue
        obj = ref.get_object()
        rect = obj.get("/Rect")
        if rect is None and obj.get("/Kids"):
            rect = obj["/Kids"][0].get_object().get("/Rect")
        if rect is None:
            return None
        x0, y0, x1, y1 = (float(v) for v in rect)
        return abs(x1 - x0), abs(y1 - y0)
    return None


def _check_field(data: bytes, field: str) -> tuple[float, float] | None:
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.fields import enumerate_sig_fields

    try:
        reader = PdfFileReader(io.BytesIO(data), strict=False)
        empty = {n for n, _v, _r in enumerate_sig_fields(reader, filled_status=False)}
        used = {n for n, _v, _r in enumerate_sig_fields(reader, filled_status=True)}
    except Exception as exc:  # noqa: BLE001
        raise ToolError(ErrorCode.CORRUPT_FILE, type(exc).__name__) from exc
    if field not in empty:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "seal_field_signed" if field in used else "seal_field_missing")
    return _field_box(data, field)


def _image(png: bytes):
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(png))
        img.load()
    except Exception as exc:  # noqa: BLE001 - la API ya la ha comprobado; esto es por si acaso
        raise ToolError(ErrorCode.INVALID_OPTIONS, "request_image") from exc
    return img.convert("RGBA")


async def seal_field(ctx: ToolContext, data: bytes, png: bytes, signer, session, timestamper) -> bytes:
    """El sello de la plataforma (B-T) en el campo del firmante, con su firma arriba y quién y cuándo debajo."""
    from pyhanko.pdf_utils.font.opentype import GlyphAccumulatorFactory
    from pyhanko.pdf_utils.images import PdfImage
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.pdf_utils.layout import AxisAlignment, InnerScaling, Margins, SimpleBoxLayoutRule
    from pyhanko.pdf_utils.text import TextBoxStyle
    from pyhanko.sign import fields, signers
    from pyhanko.stamp import TextStampStyle

    o = ctx.options
    t = TEXTS.get(ctx.locale, TEXTS["es"])
    size = _check_field(data, o.campo)
    height = size[1] if size else 70.0
    name = o.nombre.strip()[:120] or "?"
    email = o.correo.strip()[:320] or "?"
    text_room = min(30.0, height * 0.45)
    style = TextStampStyle(
        stamp_text=t["stamp"].format(name=name.replace("%", "%%"), email=email.replace("%", "%%"),
                                     site=ctx.settings.APP_NAME.replace("%", "%%")),
        border_width=0, background=PdfImage(_image(png)), background_opacity=1,
        background_layout=SimpleBoxLayoutRule(x_align=AxisAlignment.ALIGN_MID, y_align=AxisAlignment.ALIGN_MAX,
                                              margins=Margins(left=2, right=2, top=2, bottom=text_room),
                                              inner_content_scaling=InnerScaling.SHRINK_TO_FIT),
        inner_content_layout=SimpleBoxLayoutRule(x_align=AxisAlignment.ALIGN_MIN, y_align=AxisAlignment.ALIGN_MIN,
                                                 margins=Margins(left=3, right=3, top=3, bottom=2),
                                                 inner_content_scaling=InnerScaling.SHRINK_TO_FIT),
        text_box_style=TextBoxStyle(font=GlyphAccumulatorFactory(firmar.FONT), font_size=7))
    writer = IncrementalPdfFileWriter(io.BytesIO(data), strict=False)
    meta = signers.PdfSignatureMetadata(field_name=o.campo, reason=t["reason"].format(name=name, email=email)[:300],
                                        subfilter=fields.SigSeedSubFilter.PADES, md_algorithm="sha256")
    pdf_signer = signers.PdfSigner(meta, signer=signer, timestamper=timestamper, stamp_style=style)
    try:
        out = await pdf_signer.async_sign_pdf(writer)
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 - TSA sin respuesta o un PDF que pyHanko no puede firmar
        raise firmar._map_error(exc) from exc
    return out.getvalue()


async def seal_invisible_lt(ctx: ToolContext, data: bytes, signer, chain, session, timestamper, reason: str) -> bytes:
    """Sello invisible PAdES B-LT de la plataforma (con la revocación del sello y de la TSA en el DSS)."""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers
    from pyhanko_certvalidator import ValidationContext
    from pyhanko_certvalidator.fetchers.aiohttp_fetchers import AIOHttpFetcherBackend

    roots = [chain[-1], *await firmar._tsa_roots(timestamper, ctx.settings)]
    vc = ValidationContext(trust_roots=roots, other_certs=chain[1:], allow_fetching=True, revocation_mode="hard-fail",
                           fetcher_backend=AIOHttpFetcherBackend(session=session, per_request_timeout=20))
    writer = IncrementalPdfFileWriter(io.BytesIO(data), strict=False)
    taken = set()
    try:
        from pyhanko.sign.fields import enumerate_sig_fields

        taken = {n for n, _v, _r in enumerate_sig_fields(writer.prev, filled_status=None)}
    except Exception:  # noqa: BLE001
        pass
    n = 1
    while f"SelloFinal{n}" in taken:
        n += 1
    meta = signers.PdfSignatureMetadata(field_name=f"SelloFinal{n}", reason=reason[:200], subfilter=fields.SigSeedSubFilter.PADES,
                                        md_algorithm="sha256", embed_validation_info=True, validation_context=vc)
    try:
        out = await signers.PdfSigner(meta, signer=signer, timestamper=timestamper).async_sign_pdf(writer)
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise firmar._map_error(exc) from exc
    return out.getvalue()


EVENTS = {
    "es": {"created": "Solicitud creada", "invited": "Invitación enviada", "reminded": "Recordatorio enviado",
           "opened": "Página de firma abierta", "viewed": "Documento descargado", "code_sent": "Código enviado", "code_failed": "Código incorrecto",
           "code_verified": "Código verificado", "consented": "Consentimiento", "signed": "Firmado",
           "completed": "Completada", "declined": "Rechazada", "cancelled": "Cancelada", "expired": "Caducada", "failed": "Fallida"},
    "en": {"created": "Request created", "invited": "Invitation sent", "reminded": "Reminder sent", "opened": "Signing page opened", "viewed": "Document downloaded",
           "code_sent": "Code sent", "code_failed": "Wrong code", "code_verified": "Code verified", "consented": "Consent",
           "signed": "Signed", "completed": "Completed", "declined": "Declined", "cancelled": "Cancelled", "expired": "Expired",
           "failed": "Failed"},
}
CERT = {
    "es": {"title": "Certificado de auditoría", "doc": "Documento", "id": "Solicitud", "owner": "Solicitada por",
           "created": "Creada", "completed": "Completada", "original": "SHA-256 del documento original",
           "final": "SHA-256 del documento firmado", "seal": "Sello", "signers": "Firmantes", "name": "Nombre",
           "email": "Correo", "field": "Campo", "signed": "Firmado", "method": "Verificación", "by_mail": "Código de un solo uso enviado al correo",
           "events": "Registro de eventos", "when": "Fecha (UTC)", "event": "Evento", "who": "Quién", "ip": "IP (hash)",
           "agent": "Navegador", "detail": "Detalle",
           "note": ("{site} genera este certificado a partir de su registro de eventos de la solicitud. Las firmas de los "
                    "firmantes son sellos de la plataforma que acreditan la integridad del documento, la fecha y que cada "
                    "firmante confirmó con un código enviado a su correo; no son firmas electrónicas cualificadas (eIDAS). "
                    "El documento firmado lleva además un sello final PAdES B-LT de {site}.")},
    "en": {"title": "Audit certificate", "doc": "Document", "id": "Request", "owner": "Requested by", "created": "Created",
           "completed": "Completed", "original": "SHA-256 of the original document", "final": "SHA-256 of the signed document",
           "seal": "Seal", "signers": "Signers", "name": "Name", "email": "Email", "field": "Field", "signed": "Signed",
           "method": "Verification", "by_mail": "One-time code sent by email", "events": "Event log", "when": "Date (UTC)",
           "event": "Event", "who": "Who", "ip": "IP (hash)", "agent": "Browser", "detail": "Detail",
           "note": ("{site} generates this certificate from its event log for the request. The signers' signatures are "
                    "platform seals that prove the integrity of the document, the date and that each signer confirmed "
                    "with a code sent to their email; they are not qualified electronic signatures (eIDAS). The signed "
                    "document also carries a final {site} PAdES B-LT seal.")},
}


def _when(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M:%S")
    except (TypeError, ValueError):
        return ""


def certificate_html(ctx: ToolContext, final_sha: str, completed: datetime) -> str:
    """HTML del certificado de auditoría; todo lo que viene de usuarios va escapado y Chromium no sale a la red."""
    o = ctx.options
    c = CERT.get(ctx.locale, CERT["es"])
    labels = EVENTS.get(ctx.locale, EVENTS["es"])
    site = ctx.settings.APP_NAME
    e = html.escape
    rows = [(c["doc"], o.documento), (c["id"], o.solicitud), (c["owner"], o.propietario), (c["created"], _when(o.creada) + " UTC"),
            (c["completed"], completed.strftime("%d/%m/%Y %H:%M:%S") + " UTC"), (c["original"], o.original_sha256),
            (c["final"], final_sha), (c["seal"], f"{site} · PAdES B-LT")]
    summary = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in rows)
    signers = "".join(
        f"<tr><td>{e(s.nombre)}</td><td>{e(s.correo)}</td><td>{e(s.campo)}</td><td>{e(_when(s.firmado))}</td><td>{e(c['by_mail'])}</td></tr>"
        for s in o.firmantes)
    events = "".join(
        f"<tr><td>{e(_when(ev.fecha))}</td><td>{e(labels.get(ev.evento, ev.evento))}</td><td>{e(ev.actor)}</td><td>{e(ev.ip)}</td>"
        f"<td class='small'>{e(ev.agente)}</td><td class='mono'>{e(ev.sha256[:16])}</td><td>{e(ev.detalle)}</td></tr>"
        for ev in o.eventos)
    return f"""<!doctype html><html lang="{e(ctx.locale)}"><head><meta charset="utf-8"><title>{e(c['title'])}</title>
<style>
body{{font-family:"DejaVu Sans","Noto Sans",Arial,sans-serif;font-size:9pt;color:#111}}h1{{font-size:16pt;margin:0 0 4mm}}
h2{{font-size:11pt;margin:6mm 0 2mm}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #bbb;padding:1.2mm 1.6mm;
text-align:left;vertical-align:top;word-break:break-word}}th{{background:#f2f2f2;width:32%}}thead th{{width:auto}}
.mono{{font-family:"DejaVu Sans Mono",monospace;font-size:7.5pt}}.small{{font-size:7pt}}p.note{{font-size:8pt;color:#333;margin-top:6mm}}
</style></head><body>
<h1>{e(c['title'])}</h1><table>{summary}</table>
<h2>{e(c['signers'])}</h2><table><thead><tr><th>{e(c['name'])}</th><th>{e(c['email'])}</th><th>{e(c['field'])}</th>
<th>{e(c['signed'])}</th><th>{e(c['method'])}</th></tr></thead><tbody>{signers}</tbody></table>
<h2>{e(c['events'])}</h2><table><thead><tr><th>{e(c['when'])}</th><th>{e(c['event'])}</th><th>{e(c['who'])}</th><th>{e(c['ip'])}</th>
<th>{e(c['agent'])}</th><th>SHA-256</th><th>{e(c['detail'])}</th></tr></thead><tbody>{events}</tbody></table>
<p class="note">{e(c['note'].format(site=site))}</p></body></html>"""


def render_certificate(settings, page: str) -> bytes:
    from tools.office import gotenberg

    return gotenberg.chromium_html_files(settings.GOTENBERG_URL, [("index.html", page.encode("utf-8"), "text/html")],
                                         gotenberg.page_fields("A4", "vertical", 15))


async def check_all(data: bytes, chain) -> None:
    """Todas las firmas del documento siguen íntegras y válidas, no solo la última (cada paso es incremental)."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation.pdf_embedded import async_validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    await firmar.check_output(data, chain)
    reader = PdfFileReader(io.BytesIO(data), strict=False)
    if reader.encrypted:
        reader.decrypt("")
    for sig in reader.embedded_signatures:
        if sig.sig_object_type != "/Sig":
            continue
        status = await async_validate_pdf_signature(sig, signer_validation_context=ValidationContext(trust_roots=[chain[-1]]),
                                                    skip_diff=True)
        if not status.intact:
            raise ToolError(ErrorCode.ENGINE_FAILED, "seal_invalid")


def _guard(ctx: ToolContext, seals: int) -> None:
    if ctx.owner[0] != OWNER_TYPE:
        raise ToolError(ErrorCode.FORBIDDEN, "request_stage")
    if not ctx.settings.SEAL_ENABLED:
        raise ToolError(ErrorCode.TOOL_DISABLED, "seal_disabled")
    if not ctx.settings.TSA_URL:
        raise ToolError(ErrorCode.TOOL_DISABLED, "seal_config")
    if firmar.seals_today() + seals > ctx.settings.SEAL_DAILY_LIMIT:
        raise ToolError(ErrorCode.QUOTA_EXCEEDED, "seal_limit")


def _signer_step(ctx: ToolContext) -> list[dict]:
    _guard(ctx, 1)
    doc = next((i for i in ctx.inputs if i.path.suffix.lower() == ".pdf" or i.ext == "pdf"), None)
    image = next((i for i in ctx.inputs if i.ext == "png"), None)
    if doc is None or image is None:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "request_inputs")
    data, png = doc.path.read_bytes(), image.path.read_bytes()
    _check_field(data, ctx.options.campo)  # antes de abrir el token

    async def go(signer, chain) -> bytes:
        async with tsa_clients(ctx.settings) as (session, timestamper):
            out = await seal_field(ctx, data, png, signer, session, timestamper)
        await check_all(out, chain)
        return out

    with firmar.seal_signer(ctx.settings) as (signer, chain):
        out = asyncio.run(go(signer, chain))
    firmar.record_seal(ctx.job_id, hashlib.sha256(out).hexdigest(), "B-T")
    dst = ctx.output(doc.name)
    dst.write_bytes(out)
    return [{"path": str(dst), "name": doc.name, "note": None}]


def _final_step(ctx: ToolContext) -> list[dict]:
    _guard(ctx, 2)
    t = TEXTS.get(ctx.locale, TEXTS["es"])
    doc = ctx.inputs[0]
    data = doc.path.read_bytes()
    reason = t["final"].format(site=ctx.settings.APP_NAME)

    async def go(signer, chain) -> tuple[bytes, bytes]:
        async with tsa_clients(ctx.settings) as (session, timestamper):
            sealed = await seal_invisible_lt(ctx, data, signer, chain, session, timestamper, reason)
            await check_all(sealed, chain)
            page = certificate_html(ctx, hashlib.sha256(sealed).hexdigest(), datetime.now(timezone.utc))
            ctx.report(0.5, None)
            pdf = await asyncio.to_thread(render_certificate, ctx.settings, page)
            cert = await seal_invisible_lt(ctx, pdf, signer, chain, session, timestamper, reason)
            await firmar.check_output(cert, chain)
        return sealed, cert

    with firmar.seal_signer(ctx.settings) as (signer, chain):
        sealed, cert = asyncio.run(go(signer, chain))
    outputs = []
    for data_out, name in ((sealed, derived_name(doc.name, t["signed"], "pdf")), (cert, t["certificate"])):
        firmar.record_seal(ctx.job_id, hashlib.sha256(data_out).hexdigest(), "B-LT")
        dst = ctx.output(name)
        dst.write_bytes(data_out)
        outputs.append({"path": str(dst), "name": name, "note": None})
    return outputs


def run(ctx: ToolContext) -> list[dict]:
    fase = ctx.options.fase
    if fase == "preparar":
        return _prepare(ctx)
    if fase == "firmante":
        return _signer_step(ctx)
    return _final_step(ctx)
