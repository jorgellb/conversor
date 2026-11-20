"""firmar-pdf, parte de servidor (A.6 y 10, F4-A2): sello de la plataforma PAdES con pyHanko por PKCS#11 en `workersign`.

- La clave está en el token SoftHSM2 (volumen `softhsm`) y solo `workersign` conoce SIGN_PKCS11_PIN (12.1). La cadena
  del sello, en SIGN_CERT_PATH (PEM, del sello a la raíz, que tiene que estar). En desarrollo, el token y un certificado
  autofirmado los crea `infra/sign/dev_token.py`; en producción, el propietario (0.1 y DEPLOY-CHECKLIST).
- Todo lo que hay que leer del PDF del usuario (cifrado, páginas, recuadro, firmas previas) se hace con pyHanko antes de
  abrir la sesión del token; con la sesión abierta solo se firma. Al abrirla se comprueba que la clave del token es la
  del certificado, y cada resultado se valida antes de entregarlo y anotarlo.
- Niveles PAdES B-T (sello de tiempo RFC 3161 de TSA_URL), B-LT (y la información de revocación del sello y de la TSA
  en el DSS) y B-LTA (y un sello de tiempo del documento). Certificación DocMDP opcional. Firma visible o invisible.
- SEAL_ENABLED=false lo apaga al instante; SEAL_DAILY_LIMIT limita los sellos de la plataforma por día (hora de Madrid)
  y SEAL_ACCOUNT_DAILY_LIMIT los de cada cuenta. Cada uso queda en `seal_signatures` con el SHA-256 del resultado.
- Con un token software no hay dispositivo cualificado: el sello no es cualificado y no se anuncia como tal (10). La
  apariencia visible dice quién sella (el titular del certificado, nunca un nombre que escriba el usuario) y que acredita
  la integridad y la fecha, no la identidad de quien sube el documento.
- La TSA, los OCSP y las CRL se consultan por `egressweb` con la sesión limitada de verificar-firmas-pdf.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import textwrap
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from core.errors import AppError, ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.pdf.common import with_batch_zip

log = logging.getLogger("worker")
# Noto Sans (OFL, en el propio paquete): pyHanko 0.38 escribe las anchuras de los glifos y los ajustes de TJ en
# unidades de la fuente y solo acierta con 1000 por em; con DejaVu (2048) el texto del sello salía espaciado y cortado.
FONT = str(Path(__file__).with_name("fonts") / "NotoSans-Regular.ttf")
BOX = (210.0, 72.0)  # ancho y alto de la firma visible, en puntos
MARGIN = 36.0
MADRID = ZoneInfo("Europe/Madrid")
DOCMDP = {"sin_cambios": 1, "formularios": 2, "formularios_anotaciones": 3}
MAX_MB = 100  # el PDF se firma en memoria (IncrementalPdfFileWriter) en un contenedor de 512 MB
WRAP = 46

TEXTS = {
    "es": {"by": "Sellado por: %(signer)s", "date": "Fecha: %(ts)s", "name": "Nombre indicado (sin verificar): {v}",
           "reason": "Motivo: {v}", "location": "Lugar: {v}", "note": "Acredita la integridad y la fecha, no la identidad.",
           "done": "Sellado con el sello de la plataforma ({level}). No es una firma cualificada.",
           "suffix": "-sellado", "zip": "documentos-sellados.zip"},
    "en": {"by": "Sealed by: %(signer)s", "date": "Date: %(ts)s", "name": "Name given (not verified): {v}",
           "reason": "Reason: {v}", "location": "Location: {v}", "note": "Proves integrity and date, not identity.",
           "done": "Sealed with the platform seal ({level}). It is not a qualified signature.",
           "suffix": "-sealed", "zip": "sealed-documents.zip"},
}
# Causas que dicen que la TSA, el OCSP o la CRL no respondieron (se reintenta) frente a un error de configuración.
TRANSIENT_TSA = {"TimestampRequestError"}
TRANSIENT_REVINFO = {"InsufficientRevinfoError", "ClientError", "ClientConnectorError", "ServerDisconnectedError",
                     "ClientPayloadError", "TimeoutError", "CancelledError"}
CONFIG = {"PathBuildingError"}


def precheck(settings, plan, owner_type: str, options: dict, paths: list[Path], locale: str = "es") -> None:
    """Antes de encolar (sin gastar cuota): con cuenta, encendido, tamaño y el límite del día de la plataforma. Con el
    certificado propio (D-199) solo el tamaño: la firma es del usuario y no gasta el sello."""
    if options.get("certificado") == "propio":
        for path in paths:
            if path.stat().st_size > MAX_MB * 1024 * 1024:
                raise AppError(ErrorCode.LIMIT_EXCEEDED, status=413, detail=f"seal_size:{path.stat().st_size // 1048576}>{MAX_MB}")
        return
    if owner_type == "anon":
        raise AppError(ErrorCode.UNAUTHORIZED, status=401, detail="seal_account")
    if not settings.SEAL_ENABLED:
        raise AppError(ErrorCode.TOOL_DISABLED, status=400, detail="seal_disabled")
    for path in paths:
        if path.stat().st_size > MAX_MB * 1024 * 1024:
            raise AppError(ErrorCode.LIMIT_EXCEEDED, status=413, detail=f"seal_size:{path.stat().st_size // 1048576}>{MAX_MB}")
    if seals_today() + len(paths) > settings.SEAL_DAILY_LIMIT:
        raise AppError(ErrorCode.QUOTA_EXCEEDED, status=429, detail="seal_limit")


def load_chain(value: str):
    """Cadena del sello (PEM en un archivo o en la propia variable), del sello a una raíz autofirmada."""
    from pyhanko.keys import load_certs_from_pemder_data

    try:
        data = value.encode("ascii") if value.strip().startswith("-----BEGIN") else Path(value).read_bytes()
        chain = list(load_certs_from_pemder_data(data))
    except (OSError, ValueError) as exc:
        raise ToolError(ErrorCode.TOOL_DISABLED, "seal_config") from exc
    if not chain or chain[-1].self_signed == "no":
        log.error("SIGN_CERT_PATH tiene que llevar la cadena del sello hasta su raíz")
        raise ToolError(ErrorCode.TOOL_DISABLED, "seal_config")
    return chain


def _token_public_key(session, label: str) -> bytes | None:
    import pkcs11
    from pkcs11 import KeyType, ObjectClass
    from pkcs11.util.ec import encode_ec_public_key
    from pkcs11.util.rsa import encode_rsa_public_key

    for key_type, encode in ((KeyType.EC, encode_ec_public_key), (KeyType.RSA, encode_rsa_public_key)):
        try:
            return encode(session.get_key(object_class=ObjectClass.PUBLIC_KEY, key_type=key_type, label=label))
        except (pkcs11.NoSuchKey, pkcs11.MultipleObjectsReturned):
            continue
    return None


@contextmanager
def seal_signer(settings):
    """El firmante PKCS#11 del sello y su cadena. Las pruebas sin SoftHSM2 lo sustituyen por uno con clave en archivo."""
    from asn1crypto import keys
    from pyhanko.config.pkcs11 import TokenCriteria
    from pyhanko.sign import pkcs11

    if not settings.SIGN_PKCS11_PIN or not settings.SIGN_CERT_PATH:
        raise ToolError(ErrorCode.TOOL_DISABLED, "seal_config")
    chain = load_chain(settings.SIGN_CERT_PATH)
    try:
        session = pkcs11.open_pkcs11_session(settings.SIGN_PKCS11_MODULE, token_criteria=TokenCriteria(
            label=settings.SIGN_PKCS11_TOKEN_LABEL), user_pin=settings.SIGN_PKCS11_PIN)
    except Exception as exc:  # noqa: BLE001 - token ausente, PIN incorrecto o biblioteca que no carga (sin el PIN en el texto)
        log.error("no se ha podido abrir el token del sello", extra={"error": type(exc).__name__})
        raise ToolError(ErrorCode.TOOL_DISABLED, "seal_config") from None
    try:
        public = _token_public_key(session, settings.SIGN_PKCS11_KEY_LABEL)
        if public is None or keys.PublicKeyInfo.load(public).dump() != chain[0].public_key.dump():
            log.error("la clave del token no es la del certificado de SIGN_CERT_PATH")
            raise ToolError(ErrorCode.TOOL_DISABLED, "seal_config")
        # use_raw_mechanism: el resumen lo calcula pyHanko y el token solo firma (CKM_ECDSA o CKM_RSA_PKCS); SoftHSM2 y
        # muchos HSM no implementan los mecanismos combinados como CKM_ECDSA_SHA256 (D-190).
        yield pkcs11.PKCS11Signer(session, key_label=settings.SIGN_PKCS11_KEY_LABEL, signing_cert=chain[0],
                                  ca_chain=chain[1:], embed_roots=True, use_raw_mechanism=True), chain
    finally:
        session.close()


def _today_start() -> datetime:
    return datetime.combine(datetime.now(MADRID).date(), time.min, tzinfo=MADRID).astimezone(timezone.utc)


def seals_today() -> int:
    from sqlalchemy import func, select

    from core.db import session_scope
    from core.models import SealSignature

    with session_scope() as s:
        return int(s.execute(select(func.count()).select_from(SealSignature).where(
            SealSignature.created_at >= _today_start())).scalar_one())


def record_seal(job_id: str, sha256: str, level: str) -> None:
    from core.db import session_scope
    from core.models import SealSignature

    with session_scope() as s:
        s.add(SealSignature(job_id=job_id, document_sha256=sha256, level=level))


def _account_key(owner: tuple[str, str]) -> str:
    digest = hashlib.sha256(f"{owner[0]}:{owner[1]}".encode()).hexdigest()[:32]
    return f"seal:{datetime.now(MADRID):%Y%m%d}:{digest}"


def reserve_account(settings, owner: tuple[str, str], n: int) -> None:
    """Límite por cuenta y día (SEAL_ACCOUNT_DAILY_LIMIT), para que una cuenta no gaste el límite de todos."""
    from core.valkey import get_valkey

    r = get_valkey()
    key = _account_key(owner)
    total = r.incrby(key, n)
    r.expire(key, 2 * 86400)
    if total > settings.SEAL_ACCOUNT_DAILY_LIMIT:
        r.decrby(key, n)
        raise ToolError(ErrorCode.QUOTA_EXCEEDED, "seal_account_limit")


def release_account(owner: tuple[str, str], n: int) -> None:
    from core.valkey import get_valkey

    if n > 0:
        get_valkey().decrby(_account_key(owner), n)


@dataclass
class Prepared:
    name: str
    data: bytes
    field: str
    page: int | None
    box: tuple[float, float, float, float] | None
    existing: bool = False  # se firma dentro de un campo vacío del PDF (hacer-pdf-rellenable, D-196)


def _inherited(page, key: str):
    node = page
    for _ in range(64):
        if key in node:
            return node[key]
        parent = node.get("/Parent")
        if parent is None:
            return None
        node = parent.get_object()
    return None


def visual_box(rect: list[float], rotate: int, position: str) -> tuple[float, float, float, float]:
    """Recuadro de la firma en la esquina que se ve en pantalla, en coordenadas de la página (con su /Rotate)."""
    x0, y0, x1, y1 = rect
    rotate %= 360
    width, height = BOX
    vw, vh = (y1 - y0, x1 - x0) if rotate in (90, 270) else (x1 - x0, y1 - y0)
    left = MARGIN if position.endswith("izquierda") else vw - MARGIN - width
    bottom = MARGIN if position.startswith("abajo") else vh - MARGIN - height
    corners = [(left, bottom), (left + width, bottom + height)]
    pts = []
    for vx, vy in corners:  # de la vista girada a la página sin girar
        if rotate == 90:
            pts.append((x0 + vy, y1 - vx))
        elif rotate == 180:
            pts.append((x1 - vx, y1 - vy))
        elif rotate == 270:
            pts.append((x1 - vy, y0 + vx))
        else:
            pts.append((x0 + vx, y0 + vy))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def prepare(ctx: ToolContext, path: Path, name: str) -> Prepared:
    """Lo que hay que saber del PDF antes de abrir el token: cifrado, páginas, firmas previas y recuadro (pyHanko)."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.fields import enumerate_sig_fields
    from pyhanko.sign.validation import read_certification_data

    o = ctx.options
    data = path.read_bytes()
    if len(data) > MAX_MB * 1024 * 1024:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"seal_size:{len(data) // 1048576}>{MAX_MB}")
    try:
        reader = PdfFileReader(io.BytesIO(data), strict=False)
        if reader.encrypted:
            result = reader.decrypt("")
            if not getattr(result, "status", None) or str(result.status).endswith("FAILED"):
                raise ToolError(ErrorCode.PASSWORD_REQUIRED)
        total = int(reader.root["/Pages"]["/Count"])
        signed = [e for e in reader.embedded_signatures]
        certification = read_certification_data(reader)
        used = {field_name for field_name, _value, _ref in enumerate_sig_fields(reader)}
        empty = {field_name for field_name, _value, _ref in enumerate_sig_fields(reader, filled_status=False)}
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ToolError(ErrorCode.CORRUPT_FILE, type(exc).__name__) from exc
    if total < 1 or total > ctx.plan.pdf_pages:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{total} páginas")
    if certification is not None and int(getattr(certification.permission, "value", certification.permission)) == 1:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "seal_locked")
    if o.certificacion != "no" and any(s.sig_object_type == "/Sig" for s in signed):
        raise ToolError(ErrorCode.INVALID_OPTIONS, "seal_certify_signed")
    if o.sello_tiempo and o.nivel == "B-LTA" and any(s.sig_object_type == "/DocTimeStamp" for s in signed):
        raise ToolError(ErrorCode.INVALID_OPTIONS, "seal_lta_existing")
    if o.campo:
        # Campo de firma vacío del propio PDF (A.3: compatibles con firmar-pdf): su recuadro y su página mandan.
        if o.campo not in empty:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "seal_field_missing" if o.campo not in used else "seal_field_signed")
        return Prepared(name, data, o.campo, None, None, existing=True)
    n = 1
    while f"Sello{n}" in used or f"Firma{n}" in used:  # Firma{n}: el nombre de la firma con certificado propio (D-201)
        n += 1
    page_index = box = None
    if o.visible:
        spec = (o.pagina or "ultima").strip().lower()
        if spec in ("ultima", "última", "last"):
            page_index = total - 1
        elif spec in ("primera", "first"):
            page_index = 0
        elif spec.isdigit() and 1 <= int(spec) <= total:
            page_index = int(spec) - 1
        else:
            raise ToolError(ErrorCode.INVALID_OPTIONS, f"pagina:{o.pagina}")
        page = reader.find_page_for_modification(page_index)[0].get_object()
        rect = _inherited(page, "/CropBox") or _inherited(page, "/MediaBox")
        rotate = int(_inherited(page, "/Rotate") or 0)
        box = visual_box([float(v) for v in rect], rotate, o.posicion)
    return Prepared(name, data, f"Sello{n}", page_index, box)


def _lines(label: str, value: str, max_lines: int = 2) -> list[str]:
    """Texto del usuario en líneas cortas: una línea muy larga obligaría a encoger todo el recuadro hasta no leerse."""
    if not value.strip():
        return []
    lines = textwrap.wrap(label.format(v=value.strip()), WRAP)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: WRAP - 1].rstrip() + "…"
    return [line.replace("%", "%%") for line in lines]


def stamp_text(ctx: ToolContext) -> str:
    o = ctx.options
    t = TEXTS.get(ctx.locale, TEXTS["es"])
    lines = [t["by"], t["date"], *_lines(t["name"], o.nombre), *_lines(t["reason"], o.motivo), *_lines(t["location"], o.lugar), t["note"]]
    return "\n".join(lines)


async def _tsa_roots(timestamper, settings) -> list:
    """Raíces de la TSA para validar su certificado al incrustar los datos de B-LT: TSA_TRUST_ROOTS o, si está vacía,
    las autofirmadas que la propia TSA (elegida por el propietario) devuelve en su respuesta."""
    from pyhanko.keys import load_certs_from_pemder_data

    value = (settings.TSA_TRUST_ROOTS or "").strip()
    if value:
        data = value.encode("ascii") if value.startswith("-----BEGIN") else Path(value).read_bytes()
        return list(load_certs_from_pemder_data(data))
    response = await timestamper.async_dummy_response("sha256")
    certs = [c.chosen for c in (response["content"]["certificates"] or []) if c.name == "certificate"]
    roots = [c for c in certs if c.self_signed != "no"]
    # Si la TSA no envía su raíz, se toma como ancla lo que sí envía: la TSA es la que ha configurado el propietario.
    return roots or certs


def _map_error(exc: BaseException) -> ToolError:
    names = set()
    current: BaseException | None = exc
    for _ in range(10):
        if current is None:
            break
        names.add(type(current).__name__)
        current = current.__cause__ or current.__context__
    if names & TRANSIENT_TSA:
        return ToolError(ErrorCode.ENGINE_FAILED, "seal_tsa", transient=True)
    if names & TRANSIENT_REVINFO:
        return ToolError(ErrorCode.ENGINE_FAILED, "seal_revinfo", transient=True)
    if names & CONFIG:
        return ToolError(ErrorCode.TOOL_DISABLED, "seal_config")
    return ToolError(ErrorCode.ENGINE_FAILED, type(exc).__name__)


async def _sign(ctx: ToolContext, item: Prepared, signer, chain, session, timestamper) -> bytes:
    from pyhanko.pdf_utils.font.opentype import GlyphAccumulatorFactory
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.pdf_utils.text import TextBoxStyle
    from pyhanko.sign import fields, signers
    from pyhanko.stamp import TextStampStyle
    from pyhanko_certvalidator import ValidationContext
    from pyhanko_certvalidator.fetchers.aiohttp_fetchers import AIOHttpFetcherBackend

    o = ctx.options
    level = o.nivel if o.sello_tiempo else "B-B"
    writer = IncrementalPdfFileWriter(io.BytesIO(item.data), strict=False)
    if writer.prev.encrypted:
        writer.encrypt("")
    vc = None
    if level in ("B-LT", "B-LTA"):
        # Información de revocación del sello y de la TSA (OCSP o CRL) para el DSS; las dos raíces son de confianza aquí.
        roots = [chain[-1], *await _tsa_roots(timestamper, ctx.settings)]
        vc = ValidationContext(trust_roots=roots, other_certs=chain[1:], allow_fetching=True, revocation_mode="hard-fail",
                               fetcher_backend=AIOHttpFetcherBackend(session=session, per_request_timeout=20))
    meta = signers.PdfSignatureMetadata(
        field_name=item.field, reason=o.motivo or None, location=o.lugar or None,
        subfilter=fields.SigSeedSubFilter.PADES, md_algorithm="sha256",
        certify=o.certificacion != "no", docmdp_permissions=fields.MDPPerm(DOCMDP.get(o.certificacion, 2)),
        embed_validation_info=vc is not None, use_pades_lta=level == "B-LTA", validation_context=vc)
    field_spec = style = None
    if item.box is not None or item.existing:
        if item.box is not None:
            field_spec = fields.SigFieldSpec(item.field, on_page=item.page, box=item.box)
        style = TextStampStyle(stamp_text=stamp_text(ctx), border_width=1,
                               text_box_style=TextBoxStyle(font=GlyphAccumulatorFactory(FONT), font_size=7))
    pdf_signer = signers.PdfSigner(meta, signer=signer, timestamper=timestamper if o.sello_tiempo else None,
                                   stamp_style=style, new_field_spec=field_spec)
    try:
        out = await pdf_signer.async_sign_pdf(writer)
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 - TSA, OCSP o CRL sin respuesta, o un PDF que pyHanko no puede firmar
        raise _map_error(exc) from exc
    return out.getvalue()


async def check_output(data: bytes, chain) -> None:
    """El resultado se valida antes de entregarlo: un certificado que no casa con la clave daría firmas rotas."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation.pdf_embedded import async_validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    reader = PdfFileReader(io.BytesIO(data), strict=False)
    if reader.encrypted:
        reader.decrypt("")
    sig = [e for e in reader.embedded_signatures if e.sig_object_type == "/Sig"][-1]
    status = await async_validate_pdf_signature(sig, signer_validation_context=ValidationContext(trust_roots=[chain[-1]]),
                                                skip_diff=True)
    if not (status.intact and status.valid):
        raise ToolError(ErrorCode.ENGINE_FAILED, "seal_invalid")


def run(ctx: ToolContext) -> list[dict]:
    from tools.sign.verificar import make_session

    o = ctx.options
    t = TEXTS.get(ctx.locale, TEXTS["es"])
    if o.certificado == "propio":  # firma interrumpida con el certificado del usuario, en sign.verify (D-199)
        from tools.sign import propio

        return propio.run(ctx)
    if ctx.owner[0] == "anon":
        raise ToolError(ErrorCode.UNAUTHORIZED, "seal_account")
    if not ctx.settings.SEAL_ENABLED:
        raise ToolError(ErrorCode.TOOL_DISABLED, "seal_disabled")
    if o.sello_tiempo and not ctx.settings.TSA_URL:
        raise ToolError(ErrorCode.TOOL_DISABLED, "seal_config")
    if seals_today() + len(ctx.inputs) > ctx.settings.SEAL_DAILY_LIMIT:
        raise ToolError(ErrorCode.QUOTA_EXCEEDED, "seal_limit")
    # Todo lo que lee el PDF del usuario, antes de abrir el token.
    prepared = [prepare(ctx, inp.path, inp.name) for inp in ctx.inputs]
    level = o.nivel if o.sello_tiempo else "B-B"
    reserve_account(ctx.settings, ctx.owner, len(prepared))
    done = 0
    outputs = []

    async def go(signer, chain):
        nonlocal done
        from pyhanko.sign.timestamps import HTTPTimeStamper

        session = make_session(ctx.settings.EGRESS_WEB_URL)
        # Un solo cliente de la TSA por trabajo: guarda la respuesta de prueba que pyHanko pide para calcular el tamaño.
        timestamper = HTTPTimeStamper(ctx.settings.TSA_URL, session=session, timeout=20) if o.sello_tiempo else None
        try:
            for n, item in enumerate(prepared):
                ctx.report(n / len(prepared), None)
                data = await _sign(ctx, item, signer, chain, session, timestamper)
                await check_output(data, chain)
                name = derived_name(item.name, t["suffix"], "pdf")
                dst = ctx.output(name)
                dst.write_bytes(data)
                record_seal(ctx.job_id, hashlib.sha256(data).hexdigest(), level)
                done += 1
                outputs.append({"path": str(dst), "name": name, "note": t["done"].format(level=level)})
        finally:
            await session.close()

    try:
        with seal_signer(ctx.settings) as (signer, chain):
            asyncio.run(go(signer, chain))
    finally:
        release_account(ctx.owner, len(prepared) - done)
    return with_batch_zip(ctx, outputs, t["zip"])
