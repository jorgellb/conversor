"""firmar-pdf con certificado propio (A.6, F4-B2b): firma interrumpida; la clave no sale del navegador.

Dos trabajos de la misma herramienta, en `sign.verify` (el contenedor sin el token ni el PIN del sello: el PDF, la cadena
y la firma los manda el usuario):

1. `fase=preparar`: con la cadena de certificados (solo la parte pública, que el navegador saca del .p12 con PKI.js),
   pyHanko prepara la firma (campo, apariencia, hueco reservado) y calcula los atributos firmados de CMS. Salen el PDF
   preparado y `firma-pendiente.json` (resumen, posición del hueco, atributos y algoritmo).
2. El navegador firma los atributos con WebCrypto (RSASSA-PKCS1-v1_5 o ECDSA con SHA-256).
3. `fase=completar`: con el PDF preparado, el estado y el valor de la firma, se comprueba que el hueco y el resumen son
   los del PDF, que el resumen está en los atributos y que la firma es de la clave del certificado; se monta el CMS con
   el sello de tiempo (B-T), se escribe en el hueco y, en B-LT y B-LTA, se añaden los datos de validación (y el sello de
   tiempo del documento). Al final, pyHanko valida la integridad del resultado.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name

STAGE = "propio"
CURVES = {"secp256r1": "P-256", "secp384r1": "P-384", "secp521r1": "P-521"}
MAX_CHAIN_BYTES = 12000  # la cadena va dentro del CMS, con el sello de tiempo, en los 32 KB reservados
STATE_NAME = "firma-pendiente.json"
RESERVED = 32768  # CMS con la cadena del usuario y el sello de tiempo
TEXTS = {
    "es": {"by": "Firmado por: %(signer)s", "date": "Fecha: %(ts)s", "prepared": "Preparado para firmar con tu certificado.",
           "done": "Firmado con tu certificado ({level}).", "suffix": "-firmado"},
    "en": {"by": "Signed by: %(signer)s", "date": "Date: %(ts)s", "prepared": "Prepared to be signed with your certificate.",
           "done": "Signed with your certificate ({level}).", "suffix": "-signed"},
}


def load_chain(pem: str):
    """Cadena del usuario: el certificado del firmante primero (PEM, como la exporta la página)."""
    from asn1crypto import pem as pem_mod
    from asn1crypto import x509

    certs = []
    try:
        for _type, _headers, der in pem_mod.unarmor(pem.encode("ascii"), multiple=True):
            certs.append(x509.Certificate.load(der))
            _ = certs[-1].subject  # fuerza el análisis
    except Exception as exc:  # noqa: BLE001 - PEM o DER que no es un certificado
        raise ToolError(ErrorCode.INVALID_OPTIONS, "own_chain_invalid") from exc
    if not certs or len(certs) > 10 or sum(len(c.dump()) for c in certs) > MAX_CHAIN_BYTES:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "own_chain_invalid")
    algo = certs[0].public_key.algorithm
    if algo not in ("rsa", "ec"):
        raise ToolError(ErrorCode.INVALID_OPTIONS, "own_key_unsupported")
    if algo == "ec":
        try:
            curve = certs[0].public_key.curve
        except Exception as exc:  # noqa: BLE001 - parámetros de curva explícitos
            raise ToolError(ErrorCode.INVALID_OPTIONS, "own_key_unsupported") from exc
        if curve[0] != "named" or curve[1] not in CURVES:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "own_key_unsupported")
    # Uso de la clave: firma digital o no repudio; con solo cifrado, los validadores rechazarían la firma.
    usage = certs[0].key_usage_value
    if usage is not None and not ({"digital_signature", "non_repudiation"} & set(usage.native)):
        raise ToolError(ErrorCode.INVALID_OPTIONS, "own_key_usage")
    return certs


def _mechanism(cert):
    from asn1crypto import algos

    return algos.SignedDigestAlgorithm({"algorithm": "sha256_rsa" if cert.public_key.algorithm == "rsa" else "sha256_ecdsa"})


def _signer(certs, value):
    from pyhanko.sign import signers
    from pyhanko_certvalidator.registry import SimpleCertificateStore

    return signers.ExternalSigner(signing_cert=certs[0], cert_registry=SimpleCertificateStore.from_certs(certs[1:]),
                                  signature_value=value, signature_mechanism=_mechanism(certs[0]))


def _check_validity(ctx: ToolContext, cert) -> None:
    now = ctx.now()
    validity = cert["tbs_certificate"]["validity"]
    if not (validity["not_before"].native <= now <= validity["not_after"].native):
        raise ToolError(ErrorCode.INVALID_OPTIONS, "own_cert_expired")


def _prepare(ctx: ToolContext) -> list[dict]:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    from tools.sign.firmar import DOCMDP, _lines, prepare

    o = ctx.options
    t = TEXTS.get(ctx.locale, TEXTS["es"])
    certs = load_chain(o.cadena)
    _check_validity(ctx, certs[0])
    if len(ctx.inputs) != 1:
        raise ToolError(ErrorCode.TOO_MANY_FILES, "own_one_file")
    inp = ctx.inputs[0]
    item = prepare(ctx, inp.path, inp.name)
    field = item.field.replace("Sello", "Firma") if not item.existing else item.field
    size = (certs[0].public_key.bit_size + 7) // 8 if certs[0].public_key.algorithm == "rsa" else 2 * ((certs[0].public_key.bit_size + 7) // 8) + 9
    signer = _signer(certs, size)
    meta = signers.PdfSignatureMetadata(
        field_name=field, reason=o.motivo or None, location=o.lugar or None, subfilter=fields.SigSeedSubFilter.PADES,
        md_algorithm="sha256", certify=o.certificacion != "no", docmdp_permissions=fields.MDPPerm(DOCMDP.get(o.certificacion, 2)))
    field_spec = style = None
    if item.box is not None or item.existing:
        if item.box is not None:
            field_spec = fields.SigFieldSpec(field, on_page=item.page, box=item.box)
        from tools.sign.firmar import BOX_IMAGE, signature_image, stamp_style

        text = "\n".join([t["by"], t["date"], *_lines("{v}", o.nombre), *_lines("{v}", o.motivo), *_lines("{v}", o.lugar)])
        height = (item.box[3] - item.box[1]) if item.box is not None else BOX_IMAGE[1]
        style = stamp_style(text, signature_image(o.imagen), height)
    writer = IncrementalPdfFileWriter(io.BytesIO(item.data), strict=False)
    if writer.prev.encrypted:
        writer.encrypt("")
    pdf_signer = signers.PdfSigner(meta, signer=signer, stamp_style=style, new_field_spec=field_spec)

    async def go():
        prep, _tbs, out = await pdf_signer.async_digest_doc_for_signing(writer, bytes_reserved=RESERVED)
        attrs = await signer.signed_attrs(prep.document_digest, "sha256", use_pades=True)
        return prep, out.getvalue(), attrs.dump()

    try:
        prep, data, attrs = asyncio.run(go())
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 - un PDF que pyHanko no puede preparar
        raise ToolError(ErrorCode.CORRUPT_FILE, type(exc).__name__) from exc
    pdf_name = derived_name(inp.name, "-preparado", "pdf")
    pdf_out = ctx.output(pdf_name)
    pdf_out.write_bytes(data)
    pub = certs[0].public_key
    state = {
        "v": 1, "digest": base64.b64encode(prep.document_digest).decode(), "start": prep.reserved_region_start,
        "end": prep.reserved_region_end, "attrs": base64.b64encode(attrs).decode(), "hash": "SHA-256",
        "algorithm": "RSASSA-PKCS1-v1_5" if pub.algorithm == "rsa" else "ECDSA",
        "curve": CURVES.get(pub.curve[1], "") if pub.algorithm == "ec" else "",
        "field": field, "name": inp.name,
    }
    state_out = ctx.output(STATE_NAME)
    state_out.write_text(json.dumps(state), encoding="utf-8")
    for i in ctx.inputs:
        i.path.unlink(missing_ok=True)
    return [{"path": str(pdf_out), "name": pdf_name, "note": t["prepared"]}, {"path": str(state_out), "name": STATE_NAME, "note": None}]


def _signature_value(cert, raw: bytes) -> bytes:
    """WebCrypto da ECDSA como r‖s (IEEE P1363); CMS lo quiere en DER. RSA va tal cual."""
    from asn1crypto import algos

    if cert.public_key.algorithm != "ec":
        return raw
    # r‖s mide exactamente dos veces el tamaño de la curva; mirar si empieza por 0x30 (SEQUENCE) falla 1 de cada 256
    # veces, cuando el primer byte de r vale justo eso.
    n = (cert.public_key.bit_size + 7) // 8
    if len(raw) == 2 * n:
        return algos.DSASignature.from_p1363(raw).dump()
    return raw


def _verify_signature(cert, attrs: bytes, value: bytes) -> None:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding

    key = serialization.load_der_public_key(cert.public_key.dump())
    try:
        if cert.public_key.algorithm == "rsa":
            key.verify(value, attrs, padding.PKCS1v15(), hashes.SHA256())
        else:
            key.verify(value, attrs, ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError) as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "own_signature_invalid") from exc


def _reader(data: bytes):
    """Lector de pyHanko del resultado; los PDF con solo contraseña de propietario se descifran con la vacía."""
    from pyhanko.pdf_utils.reader import PdfFileReader

    reader = PdfFileReader(io.BytesIO(data), strict=False)
    if reader.encrypted:
        reader.decrypt("")
    return reader


def _own_error(err: ToolError) -> ToolError:
    """Los fallos de la TSA y de revocación con la cadena del usuario, con sus propios textos (no los del sello)."""
    mapping = {"seal_revinfo": "own_revinfo", "seal_config": "own_chain_path"}
    if err.detail in mapping:
        return ToolError(ErrorCode.ENGINE_FAILED if err.detail == "seal_revinfo" else ErrorCode.INVALID_OPTIONS, mapping[err.detail],
                         transient=err.transient)
    return err


def open_session(ctx: ToolContext):
    """Sesión de aiohttp para la TSA, OCSP y CRL (por `TSA_EGRESS_URL` o `egressweb`); las pruebas la cambian por la PKI de
    certomancer servida en el proceso."""
    import contextlib

    from tools.sign.verificar import make_session

    @contextlib.asynccontextmanager
    async def cm():
        egress = ctx.settings.TSA_EGRESS_URL if ctx.settings.TSA_EGRESS_URL is not None else ctx.settings.EGRESS_WEB_URL
        session = make_session(egress or None)
        try:
            yield session
        finally:
            await session.close()

    return cm()


def _complete(ctx: ToolContext) -> list[dict]:
    from asn1crypto import cms
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.signers import PdfTimeStamper
    from pyhanko.sign.signers.pdf_byterange import PreparedByteRangeDigest
    from pyhanko.sign.signers.pdf_signer import PdfTBSDocument
    from pyhanko.sign.timestamps import HTTPTimeStamper
    from pyhanko.sign.validation import async_add_validation_info, validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    from tools.sign.firmar import _map_error, _tsa_roots

    o = ctx.options
    t = TEXTS.get(ctx.locale, TEXTS["es"])
    certs = load_chain(o.cadena)
    if len(ctx.inputs) != 1:
        raise ToolError(ErrorCode.TOO_MANY_FILES, "own_one_file")
    inp = ctx.inputs[0]
    data = inp.path.read_bytes()
    try:
        state = json.loads(o.estado)
        digest, start, end = base64.b64decode(state["digest"]), int(state["start"]), int(state["end"])
        attrs = base64.b64decode(state["attrs"])
        raw = base64.b64decode(o.firma, validate=True)
    except (ValueError, KeyError, TypeError) as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "own_state_invalid") from exc
    # El hueco tiene que ser el de este PDF (todo ceros entre < y >) y el resumen, el de lo que queda fuera de él.
    if not (0 < start < end <= len(data)) or data[start:end] != b"<" + b"0" * (end - start - 2) + b">":
        raise ToolError(ErrorCode.INVALID_OPTIONS, "own_state_invalid")
    if hashlib.sha256(data[:start] + data[end:]).digest() != digest:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "own_state_invalid")
    try:
        signed_attrs = cms.CMSAttributes.load(attrs)
        message_digest = next(a["values"][0].native for a in signed_attrs if a["type"].native == "message_digest")
    except Exception as exc:  # noqa: BLE001
        raise ToolError(ErrorCode.INVALID_OPTIONS, "own_state_invalid") from exc
    if message_digest != digest:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "own_state_invalid")
    value = _signature_value(certs[0], raw)
    _verify_signature(certs[0], attrs, value)
    level = o.nivel if o.sello_tiempo else "B-B"
    if o.sello_tiempo and not ctx.settings.TSA_URL:
        raise ToolError(ErrorCode.TOOL_DISABLED, "seal_config")

    async def go() -> bytes:
        async with open_session(ctx) as session:
            timestamper = HTTPTimeStamper(ctx.settings.TSA_URL, session=session, timeout=20) if o.sello_tiempo else None
            signer = _signer(certs, value)
            sig_cms = await signer.async_sign_prescribed_attributes("sha256", signed_attrs=signed_attrs, timestamper=timestamper)
            out = io.BytesIO(data)
            await PdfTBSDocument.async_finish_signing(out, prepared_digest=PreparedByteRangeDigest(digest, start, end), signature_cms=sig_cms)
            result = out.getvalue()
            if level in ("B-LT", "B-LTA"):
                from pyhanko_certvalidator.fetchers.aiohttp_fetchers import AIOHttpFetcherBackend

                roots = [certs[-1], *await _tsa_roots(timestamper, ctx.settings)]
                # Cadena del usuario: el mismo tope de descargas que verificar-firmas-pdf (no 1000 peticiones a donde diga).
                from pyhanko_certvalidator.fetchers.api import FetchLimits

                vc = ValidationContext(trust_roots=roots, other_certs=certs[1:], allow_fetching=True, revocation_mode="soft-fail",
                                       fetcher_backend=AIOHttpFetcherBackend(session=session, per_request_timeout=20,
                                                                             limits=FetchLimits(max_requests=30, max_cert_requests=10, max_aia_urls_per_object=3)))
                reader = _reader(result)
                buf = io.BytesIO()
                await async_add_validation_info(reader.embedded_signatures[-1], vc, output=buf)
                result = buf.getvalue()
                if level == "B-LTA":
                    writer = IncrementalPdfFileWriter(io.BytesIO(result), strict=False)
                    if writer.prev.encrypted:
                        writer.encrypt("")
                    buf = io.BytesIO()
                    await PdfTimeStamper(timestamper).async_timestamp_pdf(writer, "sha256", validation_context=vc, output=buf)
                    result = buf.getvalue()
            return result

    try:
        result = asyncio.run(go())
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 - TSA, OCSP o CRL sin respuesta
        raise _own_error(_map_error(exc)) from exc
    reader = _reader(result)
    mine = next((s for s in reader.embedded_signatures if s.field_name == state.get("field")), None)
    if mine is None:
        raise ToolError(ErrorCode.ENGINE_FAILED, "own_output_invalid")
    status = validate_pdf_signature(mine, ValidationContext(trust_roots=[certs[-1]]))
    if not (status.intact and status.valid):
        raise ToolError(ErrorCode.ENGINE_FAILED, "own_output_invalid")
    name = derived_name(Path(str(state.get("name") or inp.name)).name, t["suffix"], "pdf")
    dst = ctx.output(name)
    dst.write_bytes(result)
    for i in ctx.inputs:
        i.path.unlink(missing_ok=True)
    return [{"path": str(dst), "name": name, "note": t["done"].format(level=level)}]


def run(ctx: ToolContext) -> list[dict]:
    # El PDF, la cadena y la firma son del usuario: se tratan en `sign.verify`, nunca junto al token del sello (D-199).
    if ctx.stage != STAGE:
        ctx.handoff("sign", STAGE, None, queue="sign.verify", keep_secrets=False)
    return _prepare(ctx) if ctx.options.fase == "preparar" else _complete(ctx)
