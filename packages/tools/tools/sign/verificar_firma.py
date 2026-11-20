"""verificar-firma (7.13, F6-G, D-219): firmas CAdES (.csig, .p7m, .p7s), XAdES (.xsig, XML firmado) y PAdES (PDF).

En `sign.verify`, con el mismo contexto de validación que verificar-firmas-pdf (lista de confianza de la UE, raíces de
la instalación, revocación en línea por `egressweb` solo si se pide) y el mismo informe HTML y los mismos niveles:
- CAdES: pyHanko (`async_validate_detached_cms`) con el contenido encapsulado o, si la firma va separada, con el
  documento original subido como segundo archivo; cada firmante (cofirmas de AutoFirma) se comprueba por separado, con
  su sello de tiempo (CAdES-T) si lo trae.
- XAdES: signxml comprueba la firma con el certificado que trae (con SHA-1, que siguen usando muchas Facturae) y
  pyhanko-certvalidator, la cadena hasta una raíz de confianza.
- PDF: el análisis de verificar-firmas-pdf.
16.5: un documento alterado sale «No válida».
"""
from __future__ import annotations

import asyncio
import base64
import time
from datetime import datetime
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext
from tools.pdf.common import with_batch_zip
from tools.sign import confianza
from tools.sign.verificar import (DEADLINE_SECONDS, TEXT, SignatureInfo, _name, _qualification, _qualified_tsa, _try, _Validator,
                                  make_session, render, summary)
from tools.utils.firmados import DS, MAX_BYTES, load_signed_data

CMS_EXTS = ("csig", "p7m", "p7s")
XADES_132 = "http://uri.etsi.org/01903/v1.3.2#"


def _config(xades: bool):
    """Los algoritmos de signxml más SHA-1, que siguen usando muchas firmas españolas (la misma regla que la firma de
    Facturae en validar-factura-electronica); nunca HMAC, que no prueba quién firma."""
    from signxml import DigestAlgorithm, SignatureConfiguration, SignatureMethod
    from signxml.xades import XAdESSignatureConfiguration

    methods = frozenset(m for m in SignatureMethod if not m.name.startswith("HMAC"))
    cls = XAdESSignatureConfiguration if xades else SignatureConfiguration
    return cls(signature_methods=methods, digest_algorithms=frozenset(DigestAlgorithm), expect_references=True)
XML_EXTS = ("xsig", "xml")


def _ext(inp) -> str:
    return (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()


def _level(info: SignatureInfo, intact: bool, valid: bool, trusted: bool, revoked: bool, cert, path, state, root_prints,
           moment: datetime | None) -> None:
    """El nivel con las mismas reglas que verificar-firmas-pdf."""
    info.intact, info.valid, info.trusted, info.revoked = intact, valid, trusted, revoked
    if not (intact and valid):
        info.level = "no_valida"
    elif revoked:
        info.level = "revocada"
    elif not trusted:
        country = str(cert.issuer.native.get("country_name") or "") if cert is not None else ""
        info.level = "sin_comprobar" if state.registry is None or country in state.missing else "simple"
    else:
        anchor = confianza.fingerprint(path.trust_anchor.authority.certificate) if path is not None else ""
        if confianza.fingerprint(cert) in root_prints:
            info.level = "plataforma"
        elif anchor in root_prints:
            info.level = "propia"
        else:
            info.level = "avanzada"
            _qualification(state, path, moment, info)


# --- CAdES ------------------------------------------------------------------------------------------------------------


def _single(signed, signer_info):
    from asn1crypto import cms

    fields = {k: signed[k] for k in ("version", "digest_algorithms", "certificates", "crls") if signed[k].native is not None}
    # Siempre como firma separada (el contenido se pasa aparte, con el mismo resumen): así valen igual las adjuntas.
    fields["encap_content_info"] = {"content_type": signed["encap_content_info"]["content_type"].native}
    fields["signer_infos"] = cms.SignerInfos([signer_info])
    return cms.SignedData(fields)


async def _cades(raw: bytes, original: bytes | None, validator: _Validator, state, root_prints, online: bool) -> list[SignatureInfo]:
    from pyhanko.sign.validation import generic_cms

    signed = load_signed_data(raw)
    content = signed["encap_content_info"]["content"].native
    data = content if content is not None else original
    if data is None:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "cms_detached_needs_original")
    infos = []
    for n, signer_info in enumerate(signed["signer_infos"], 1):
        info = SignatureInfo(kind="firma", field=f"CAdES {n}", family="CAdES")
        single = _single(signed, signer_info)

        async def validate(moment=None, fetch=online):
            return await generic_cms.async_validate_detached_cms(
                data, single, signer_validation_context=validator.context(fetch, moment),
                ts_validation_context=validator.context(False), key_usage_settings=validator.key_usage)

        try:
            status = await validate()
        except Exception as exc:  # noqa: BLE001 - firma mal formada, algoritmo desconocido o sin red: se informa
            if online:
                status = await _try(validate(fetch=False))
                info.revocation = "fallo_en_linea"
            else:
                status = None
            if status is None:
                info.problem = type(exc).__name__
                infos.append(info)
                continue
        tst = status.timestamp_validity
        info.tst_ok = bool(tst is not None and tst.intact and tst.valid and tst.trusted)
        if info.tst_ok and status.intact and status.valid and (not status.trusted or status.revoked):
            past = await _try(validate(moment=tst.timestamp))
            if past is not None and past.trusted and not past.revoked:
                info.at_timestamp = "caducado" if not status.revoked else "revocado_despues"
                status = past
        info.signer, info.issuer, info.email = _name(status.signing_cert)
        if tst is not None:
            info.when, info.tsa = tst.timestamp, _name(tst.signing_cert)[0]
            info.when_source = ("qtsa" if _qualified_tsa(state, tst) else "tsa") if info.tst_ok else "tsa_no_confianza"
        else:
            info.when = status.signer_reported_dt
        if not status.trusted and status.trust_problem_indic is not None:
            info.problem = getattr(status.trust_problem_indic, "name", "")
        if info.revocation != "fallo_en_linea":
            info.revocation = ("en_linea" if status.trusted else "no_aplica") if online else "no_comprobada"
        _level(info, bool(status.intact), bool(status.valid), bool(status.trusted), bool(status.revoked), status.signing_cert,
               status.validation_path, state, root_prints, tst.timestamp if info.tst_ok else None)
        info.ades = "CAdES-T" if info.tst_ok else "CAdES-B"
        infos.append(info)
    return infos


# --- XAdES ------------------------------------------------------------------------------------------------------------


def _certs_of(sig) -> list:
    from asn1crypto import x509

    out = []
    for el in sig.iter(f"{{{DS}}}X509Certificate"):
        try:
            out.append(x509.Certificate.load(base64.b64decode("".join((el.text or "").split()))))
        except Exception:  # noqa: BLE001 - un certificado ilegible se ignora
            continue
    return out


def _leaf(certs: list):
    """El certificado del firmante: el primero que no es de una CA (KeyInfo puede traer la cadena entera)."""
    for cert in certs:
        constraints = cert.basic_constraints_value
        if constraints is None or not constraints["ca"].native:
            return cert
    return certs[0] if certs else None


def _pem(cert) -> str:
    import textwrap

    body = "\n".join(textwrap.wrap(base64.b64encode(cert.dump()).decode(), 64))
    return f"-----BEGIN CERTIFICATE-----\n{body}\n-----END CERTIFICATE-----\n"


async def _chain(cert, others: list, validator: _Validator, online: bool, moment=None):
    """(confianza, revocado, ruta, problema) de la cadena del certificado, con el mismo contexto que las firmas PDF."""
    from pyhanko_certvalidator import CertificateValidator
    from pyhanko_certvalidator.errors import (ExpiredError, InvalidCertificateError, NotYetValidError, PathBuildingError,
                                              PathValidationError, RevokedError)

    cv = CertificateValidator(cert, intermediate_certs=others, validation_context=validator.context(online, moment))
    try:
        path = await cv.async_validate_path()
        validator.key_usage.validate(cert)
        return True, False, path, ""
    except RevokedError:
        return False, True, None, "REVOKED"
    except ExpiredError:
        return False, False, None, "EXPIRED"
    except NotYetValidError:
        return False, False, None, "NOT_YET_VALID"
    except PathBuildingError:
        return False, False, None, "NO_CERTIFICATE_CHAIN_FOUND"
    except (PathValidationError, InvalidCertificateError):
        return False, False, None, "CHAIN_CONSTRAINTS_FAILURE"
    except Exception:  # noqa: BLE001 - sin red con revocación obligatoria, uso de clave no permitido…
        return False, False, None, ""


def _signing_time(sig) -> datetime | None:
    for el in sig.iter():
        if el.tag.endswith("}SigningTime") and el.text:
            try:
                return datetime.fromisoformat(el.text.strip().replace("Z", "+00:00"))
            except ValueError:
                return None
    return None


async def _xades(raw: bytes, original: bytes | None, validator: _Validator, state, root_prints, online: bool) -> list[SignatureInfo]:
    import copy

    import defusedxml.ElementTree as DET
    from defusedxml import DefusedXmlException
    from lxml import etree
    from signxml import XMLVerifier
    from signxml.xades import XAdESVerifier

    try:  # entidades y DTD externos fuera antes de que lxml vea nada (16.4)
        DET.fromstring(raw, forbid_dtd=False, forbid_entities=True, forbid_external=True)
    except (DefusedXmlException, ValueError) as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities") from exc
    except SyntaxError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "XML no válido") from exc
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    root = etree.fromstring(raw, parser=parser)
    signatures = root.findall(f".//{{{DS}}}Signature") if root.tag != f"{{{DS}}}Signature" else [root]
    if not signatures:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "xades_no_signature")
    resolver = (lambda uri: original) if original is not None else None
    infos = []
    for n, sig in enumerate(signatures, 1):
        info = SignatureInfo(kind="firma", field=f"XAdES {n}", family="XAdES")
        certs = _certs_of(sig)
        cert = _leaf(certs)
        if cert is None:
            info.problem = "sin_certificado"
            infos.append(info)
            continue
        if len(signatures) > 1:
            # Cada cofirma por separado: se quitan las demás (no forman parte de lo que firma cada una).
            doc = copy.deepcopy(root)
            for i, other in enumerate(doc.findall(f".//{{{DS}}}Signature"), 1):
                if i != n and other.getparent() is not None:
                    other.getparent().remove(other)
            data = etree.tostring(doc)
        else:
            data = raw
        intact = True
        try:
            if XADES_132.encode() in etree.tostring(sig):
                XAdESVerifier().verify(data, x509_cert=_pem(cert), expect_config=_config(True), uri_resolver=resolver)
                info.ades = "XAdES-B"
            else:
                XMLVerifier().verify(data, x509_cert=_pem(cert), expect_config=_config(False), uri_resolver=resolver)
                info.ades = "XMLDSig"
        except Exception as exc:  # noqa: BLE001 - firma rota, referencias que no cuadran o algoritmo no admitido
            intact = False
            info.problem = type(exc).__name__
        if any(el.tag.endswith("}SignatureTimeStamp") for el in sig.iter()):
            info.notes.append("xades_tst")
        info.signer, info.issuer, info.email = _name(cert)
        info.when = _signing_time(sig)
        others = [c for c in certs if c is not cert]
        trusted, revoked, path, problem = await _chain(cert, others, validator, online)
        if online and not trusted and not revoked and problem == "":
            trusted, revoked, path, problem = await _chain(cert, others, validator, False)
            info.revocation = "fallo_en_linea"
        if not trusted and info.problem == "":
            info.problem = problem
        if info.revocation != "fallo_en_linea":
            info.revocation = ("en_linea" if trusted else "no_aplica") if online else "no_comprobada"
        _level(info, intact, intact, trusted, revoked, cert, path, state, root_prints, None)
        infos.append(info)
    return infos


# --- Herramienta ------------------------------------------------------------------------------------------------------


def _split(ctx: ToolContext):
    """La firma y, si hay dos archivos, el documento original (para las firmas separadas)."""
    sigs = [i for i in ctx.inputs if _ext(i) in CMS_EXTS + XML_EXTS + ("pdf",)]
    if len(ctx.inputs) == 2:
        # Con dos archivos, la firma es el .csig, .p7m, .p7s o .xsig; el otro, el documento.
        signed = [i for i in ctx.inputs if _ext(i) in CMS_EXTS + ("xsig",)]
        if len(signed) != 1:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "verify_two_files")
        other = next(i for i in ctx.inputs if i is not signed[0])
        return signed[0], other
    if len(sigs) != 1:
        raise ToolError(ErrorCode.TOO_MANY_FILES, "una firma y, si va separada, el documento")
    return sigs[0], None


async def _analyse(sig, original, state, roots, online: bool, proxy: str | None) -> list[SignatureInfo]:
    session = make_session(proxy) if online else None
    try:
        validator = _Validator(state, roots, None, session)
        root_prints = {confianza.fingerprint(c) for c in roots}
        raw = sig.path.read_bytes()
        original_bytes = original.path.read_bytes() if original is not None else None
        if _ext(sig) in CMS_EXTS:
            return await _cades(raw, original_bytes, validator, state, root_prints, online)
        return await _xades(raw, original_bytes, validator, state, root_prints, online)
    finally:
        if session is not None:
            await session.close()


def run(ctx: ToolContext) -> list[dict]:
    t = TEXT.get(ctx.locale, TEXT["es"])
    sig, original = _split(ctx)
    if _ext(sig) == "pdf":
        from tools.sign import verificar

        ctx.inputs = [sig]
        return verificar.run(ctx)
    for inp in (sig, original):
        if inp is not None and inp.path.stat().st_size > MAX_BYTES:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Archivo de más de 100 MB")
    state = confianza.eu_registry(ctx.settings)
    roots = confianza.extra_roots(ctx.settings)
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        items = asyncio.run(asyncio.wait_for(_analyse(sig, original, state, roots, ctx.options.revocacion, ctx.settings.EGRESS_WEB_URL),
                                             max(1, deadline - time.monotonic())))
    except ToolError:
        raise
    except (asyncio.TimeoutError, TimeoutError) as exc:
        raise ToolError(ErrorCode.TIMEOUT, "verificación de firmas") from exc
    stem = Path(sig.name).stem or "documento"
    name = t["report"].format(stem=stem)
    dst = ctx.output(name)
    dst.write_text(render(sig.name, items, state, ctx.locale), encoding="utf-8")
    return with_batch_zip(ctx, [{"path": str(dst), "name": name, "note": summary(items, ctx.locale)}], t["zip"])
