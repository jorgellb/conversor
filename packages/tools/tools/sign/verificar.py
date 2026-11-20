"""verificar-firmas-pdf (A.7 y 7.23): validación de cada firma y sello de tiempo con pyHanko, sin el token del sello.

Por cada firma: firmante y emisor; fecha y si viene de un sello de tiempo de confianza (o cualificado); integridad;
cambios posteriores y si estaban permitidos (análisis de diferencias de pyHanko con DocMDP y FieldMDP); nivel (no
válida, revocada, simple, sello de la plataforma, raíz propia, avanzada, con certificado cualificado o cualificada) y
nivel PAdES (B-B, B-T, B-LT o B-LTA; o «PDF, no PAdES»).

Fechas: el certificado se valida hoy y, si hoy no es de confianza (caducado, revocado después o un prestador que ha
dejado la lista) pero la firma lleva un sello de tiempo íntegro y de confianza, se valida en la fecha de ese sello, como
hace la validación AdES (EN 319 102-1): la firma es válida si lo era cuando se selló, y el informe dice por qué hoy no.

Confianza: la lista de la UE de la última descarga (`confianza.eu_registry`, sin red) y las raíces propias de
SIGN_VERIFY_EXTRA_ROOTS. La revocación usa la información del documento (DSS) y, solo con la opción, OCSP y CRL en línea
por `egressweb`, con límites de peticiones, tamaño y tiempo. El informe es HTML imprimible (también como PDF desde el
navegador). Los niveles son técnicos: eIDAS los decide con más criterios que los que se ven en el archivo (LEGAL.md).
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import io
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext
from tools.pdf.common import with_batch_zip
from tools.sign import confianza

LEVELS = ("no_valida", "revocada", "simple", "sin_comprobar", "propia", "plataforma", "avanzada", "avanzada_qc", "cualificada")
TRUSTED_LEVELS = frozenset({"propia", "plataforma", "avanzada", "avanzada_qc", "cualificada"})
MAX_SIGNATURES = 50
DEADLINE_SECONDS = 780  # time_limit de la herramienta (900 s) menos un margen
REQUEST_TIMEOUT = 10
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
# Indicaciones de certvalidator cuando falta o no llega la información de revocación (no cuando dice «revocado»);
# un OCSP o una CRL que no responden en modo estricto dan CERTIFICATE_CHAIN_GENERAL_FAILURE (InsufficientRevinfoError).
# Solo se usa la validación sin red si con ella la cadena sí es de confianza.
REVINFO_PROBLEMS = frozenset({"TRY_LATER", "REVOCATION_OUT_OF_BOUNDS_NO_POE", "NO_POE", "OUT_OF_BOUNDS_NOT_REVOKED",
                              "CERTIFICATE_CHAIN_GENERAL_FAILURE"})


@dataclass
class SignatureInfo:
    kind: str  # «firma» o «sello_tiempo» (sello de tiempo del documento, /DocTimeStamp)
    field: str
    signer: str = ""
    issuer: str = ""
    email: str = ""
    when: datetime | None = None
    when_source: str = "declarada"  # declarada, tsa, qtsa o tsa_no_confianza
    tsa: str = ""
    intact: bool = False
    valid: bool = False
    trusted: bool = False
    revoked: bool = False
    revocation: str = "no_comprobada"  # en_linea, documento, no_comprobada, fallo_en_linea o no_aplica
    changes: str = "ninguno"  # ninguno, lta, formularios, anotaciones, otros
    changes_ok: bool = True
    certified: str = ""  # DocMDP de la firma de certificación
    level: str = "no_valida"
    pades: str = ""
    subfilter: str = ""
    at_timestamp: str = ""  # por qué se ha validado en la fecha del sello: caducado, revocado_despues o fuera_de_lista
    qualified_service: str = ""
    country: str = ""
    reason: str = ""
    location: str = ""
    problem: str = ""
    tst_ok: bool = False
    notes: list[str] = field(default_factory=list)
    family: str = "PAdES"  # CAdES y XAdES: verificar-firma (F6-G)
    ades: str = ""  # su nivel: CAdES-B, CAdES-T, XAdES-B o XMLDSig


def _name(cert) -> tuple[str, str, str]:
    try:
        subject, issuer = cert.subject.native, cert.issuer.native
        who = subject.get("common_name") or subject.get("organization_name") or cert.subject.human_friendly
        by = issuer.get("common_name") or issuer.get("organization_name") or cert.issuer.human_friendly
        return str(who), str(by), str(subject.get("email_address") or "")
    except Exception:  # noqa: BLE001 - nombre con una codificación que asn1crypto no entiende
        return "?", "?", ""


def _text(value) -> str:
    try:
        return str(value)[:300] if value is not None else ""
    except Exception:  # noqa: BLE001 - texto del PDF mal codificado
        return ""


def _changes(level) -> str:
    from pyhanko.sign.diff_analysis import ModificationLevel

    return {ModificationLevel.NONE: "ninguno", ModificationLevel.LTA_UPDATES: "lta", ModificationLevel.FORM_FILLING: "formularios",
            ModificationLevel.ANNOTATIONS: "anotaciones"}.get(level, "otros")


def _certification(sig) -> str:
    """Solo la firma de certificación (una referencia con TransformMethod /DocMDP), no un /Lock de campo."""
    try:
        refs = sig.sig_object.get("/Reference") or []
        if not any(str(r.get_object().get("/TransformMethod")) == "/DocMDP" for r in refs):
            return ""
        level = sig.docmdp_level
    except Exception:  # noqa: BLE001
        return ""
    if level is None:
        return ""
    return {1: "sin_cambios", 2: "formularios", 3: "formularios_anotaciones"}.get(int(getattr(level, "value", level)), "")


def _dss_covers(dss, cert) -> bool:
    """El DSS trae una CRL del emisor del certificado o una respuesta OCSP para su número de serie (B-LT de esta firma)."""
    from asn1crypto import crl, ocsp

    if dss is None:
        return False
    for ref in dss.crls:
        try:
            if crl.CertificateList.load(ref.get_object().data)["tbs_cert_list"]["issuer"] == cert.issuer:
                return True
        except Exception:  # noqa: BLE001
            continue
    for ref in dss.ocsps:
        try:
            resp = ocsp.OCSPResponse.load(ref.get_object().data)
            basic = resp["response_bytes"]["response"].parsed
            for r in basic["tbs_response_data"]["responses"]:
                cid = r["cert_id"]
                algo = cid["hash_algorithm"]["algorithm"].native
                same_issuer = hashlib.new(algo, cert.issuer.dump()).digest() == cid["issuer_name_hash"].native
                if same_issuer and cid["serial_number"].native == cert.serial_number:
                    return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _qualification(state: confianza.TrustState, path, moment, info: SignatureInfo) -> None:
    from pyhanko.sign.validation.qualified.assess import QualificationAssessor
    from pyhanko.sign.validation.qualified.tsp import QcCertType

    if state.registry is None or path is None:
        return
    try:
        result = QualificationAssessor(state.registry).check_entity_cert_qualified(path, moment)
    except Exception:  # noqa: BLE001 - el análisis de cualificación no invalida la firma
        return
    sd = result.service_definition
    if sd is not None:
        info.qualified_service = sd.base_info.service_name
        for cert in sd.base_info.provider_certs:
            country = cert.subject.native.get("country_name")
            if country:
                info.country = str(country)
                break
    if result.status.qualified and result.status.qc_type != QcCertType.QC_WEB:
        if result.status.qc_key_security.is_qscd:
            info.level = "cualificada"
            if result.status.qc_type == QcCertType.QC_ESEAL:
                info.notes.append("sello")
        else:
            info.level = "avanzada_qc"


def _qualified_tsa(state: confianza.TrustState, ts_status) -> bool:
    """La TSA (o una autoridad de su cadena) estaba en la lista como servicio de sellos de tiempo cualificado (QTST)
    en la fecha del sello."""
    from pyhanko.sign.validation.qualified.tsp import QTST_URI
    from pyhanko_certvalidator.authority import AuthorityWithCert

    if state.registry is None:
        return False
    authorities = [AuthorityWithCert(ts_status.signing_cert)]
    if ts_status.validation_path is not None:
        authorities.extend(ts_status.validation_path.iter_authorities())
    for authority in authorities:
        for sd in state.registry.applicable_service_definitions(authority, ts_status.timestamp):
            if sd.base_info.service_type == QTST_URI:
                return True
    return False


def make_session(proxy: str | None):
    """Sesión para OCSP, CRL y certificados por `egressweb`. `response_class` lee por trozos y corta una respuesta de
    más de MAX_RESPONSE_BYTES (o que lo anuncia en Content-Length): certvalidator llama a `read()`, que en aiohttp
    acumula el cuerpo entero antes de cualquier aviso (una «CRL» de varios GB tumbaría el contenedor)."""
    import aiohttp

    class Limited(aiohttp.ClientResponse):
        async def read(self) -> bytes:
            if self._body is None:
                if self.content_length is not None and self.content_length > MAX_RESPONSE_BYTES:
                    self.close()
                    raise aiohttp.ClientPayloadError("respuesta demasiado grande")
                data = bytearray()
                async for chunk in self.content.iter_chunked(64 * 1024):
                    data += chunk
                    if len(data) > MAX_RESPONSE_BYTES:
                        self.close()
                        raise aiohttp.ClientPayloadError("respuesta demasiado grande")
                self._body = bytes(data)
            return self._body

    return aiohttp.ClientSession(proxy=proxy or None, trust_env=False, timeout=aiohttp.ClientTimeout(total=60),
                                 response_class=Limited)


class _Validator:
    """Contextos de validación de un documento, con un único presupuesto de peticiones en línea."""

    def __init__(self, state, roots, dss, session):
        from pyhanko.sign.validation.settings import KeyUsageConstraints
        from pyhanko_certvalidator.fetchers.aiohttp_fetchers import AIOHttpFetcherBackend
        from pyhanko_certvalidator.fetchers.api import FetchLimits

        self.state, self.roots, self.dss = state, roots, dss
        self.dss_broken = False
        # `get_fetchers()` empieza un presupuesto nuevo en cada llamada: se crea una vez y lo comparten todos los
        # contextos del documento (y su caché de respuestas).
        self.fetchers = (AIOHttpFetcherBackend(session=session, per_request_timeout=REQUEST_TIMEOUT,
                                               limits=FetchLimits(max_requests=30, max_cert_requests=10,
                                                                  max_aia_urls_per_object=3)).get_fetchers()
                         if session is not None else None)
        # Firma o sello: vale `digitalSignature` o `nonRepudiation` (un certificado de sello suele llevar solo el primero).
        self.key_usage = KeyUsageConstraints(key_usage={"digital_signature", "non_repudiation"}, match_all_key_usages=False)

    def context(self, fetch: bool, moment: datetime | None = None, use_dss: bool = True, skip_leaf_revocation: bool = False):
        from pyhanko_certvalidator import ValidationContext
        from pyhanko_certvalidator.policy_decl import CertRevTrustPolicy, RevocationCheckingPolicy, RevocationCheckingRule

        online = fetch and self.fetchers is not None
        kwargs = {"trust_manager": confianza.trust_manager(self.state.registry, self.roots), "allow_fetching": online,
                  "revocation_mode": "hard-fail" if online else "soft-fail"}
        if online:
            kwargs["fetchers"] = self.fetchers
        if moment is not None:
            # Validación en la fecha del sello de tiempo: vale la información de revocación posterior (AdES).
            kwargs.update(moment=moment, retroactive_revinfo=True)
        if skip_leaf_revocation:
            # Revocado después del sello (fecha conocida por la validación de hoy): en la fecha del sello no lo estaba.
            kwargs.pop("revocation_mode")
            kwargs["revinfo_policy"] = CertRevTrustPolicy(RevocationCheckingPolicy(
                ee_certificate_rule=RevocationCheckingRule.NO_CHECK,
                intermediate_ca_cert_rule=(RevocationCheckingRule.CHECK_IF_DECLARED if online
                                           else RevocationCheckingRule.CHECK_IF_DECLARED_SOFT)))
        if self.dss is not None and use_dss and not self.dss_broken:
            try:
                return self.dss.as_validation_context(kwargs)
            except Exception:  # noqa: BLE001 - DSS mal formado: se valida sin él y el informe lo dice
                self.dss_broken = True
        return ValidationContext(**kwargs)

    async def signature(self, sig, fetch: bool, moment: datetime | None = None, **kw):
        from pyhanko.sign.validation import pdf_embedded

        # El sello de tiempo de la firma se valida siempre hoy y sin red (su TSA no tiene por qué publicar OCSP).
        return await pdf_embedded.async_validate_pdf_signature(
            sig, signer_validation_context=self.context(fetch, moment, **kw), ts_validation_context=self.context(False),
            key_usage_settings=self.key_usage)

    async def timestamp(self, sig):
        from pyhanko.sign.validation import pdf_embedded

        return await pdf_embedded.async_validate_pdf_timestamp(sig, validation_context=self.context(False))


def _reader(stream, strict: bool):
    from pyhanko.pdf_utils.reader import PdfFileReader

    reader = PdfFileReader(stream, strict=strict)
    if reader.encrypted:  # con contraseña de propietario solamente (permisos): se abre con la de usuario vacía
        result = reader.decrypt("")
        if not getattr(result, "status", None) or str(result.status).endswith("FAILED"):
            raise ToolError(ErrorCode.PASSWORD_REQUIRED)
    list(reader.embedded_signatures)
    return reader


async def _analyse(data, state: confianza.TrustState, roots, online: bool, proxy: str | None,
                   session=None) -> tuple[list[SignatureInfo], bool]:
    """Firmas del documento (`data`: bytes o un archivo abierto) y si se leyó en modo tolerante. Primero en modo
    estricto, que rechaza las tablas de referencias híbridas con contenido distinto (pyHanko); ante cualquier error de
    estructura (al abrir o durante el análisis de diferencias), todo otra vez en modo tolerante y con aviso.
    `session`: sesión de aiohttp para OCSP y CRL (las pruebas pasan la del «illusionist» de certomancer)."""
    from pyhanko.pdf_utils.misc import PdfReadError, PdfStrictReadError

    stream = io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data
    try:
        return await _analyse_once(stream, True, state, roots, online, proxy, session), False
    except (PdfStrictReadError, PdfReadError):
        stream.seek(0)
        return await _analyse_once(stream, False, state, roots, online, proxy, session), True


async def _analyse_once(stream, strict: bool, state, roots, online: bool, proxy, session) -> list[SignatureInfo]:
    from pyhanko.pdf_utils.misc import PdfStrictReadError
    from pyhanko.sign.validation.dss import DocumentSecurityStore, NoDSSFoundError

    reader = _reader(stream, strict)
    try:
        dss = DocumentSecurityStore.read_dss(reader)
    except NoDSSFoundError:
        dss = None
    except Exception:  # noqa: BLE001 - DSS ilegible: sin él
        dss = None
    embedded = list(reader.embedded_signatures)
    if len(embedded) > MAX_SIGNATURES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"sig_count:{len(embedded)}>{MAX_SIGNATURES}")
    own_session = online and session is None
    if own_session:
        session = make_session(proxy)
    validator = _Validator(state, roots, dss, session if online else None)
    root_prints = {confianza.fingerprint(c) for c in roots}
    out: list[SignatureInfo] = []
    try:
        for sig in embedded:
            is_ts = sig.sig_object_type == "/DocTimeStamp"
            info = SignatureInfo(kind="sello_tiempo" if is_ts else "firma", field=_text(sig.field_name))
            try:
                if is_ts:
                    status = await validator.timestamp(sig)
                    info.when, info.intact, info.valid, info.trusted = status.timestamp, bool(status.intact), bool(status.valid), bool(status.trusted)
                    info.tst_ok = info.intact and info.valid and info.trusted
                    info.when_source = ("qtsa" if _qualified_tsa(state, status) else "tsa") if info.tst_ok else "tsa_no_confianza"
                    info.signer = info.tsa = _name(status.signing_cert)[0]
                    info.issuer = _name(status.signing_cert)[1]
                    info.level = ""  # el nivel solo se da a las firmas
                else:
                    await _signature(validator, state, sig, info, online, root_prints, dss)
            except ToolError:
                raise
            except PdfStrictReadError:
                if strict:
                    raise
                info.problem, info.level = "PdfStrictReadError", "no_valida"
            except Exception as exc:  # noqa: BLE001 - firma mal formada: se informa y se sigue con las demás
                info.problem, info.level = type(exc).__name__, "no_valida"
            if validator.dss_broken and "dss" not in info.notes:
                info.notes.append("dss")
            out.append(info)
        # B-LTA: un sello de tiempo del documento íntegro y de confianza después de la firma (que ya es B-LT).
        for i, info in enumerate(out):
            if info.pades == "B-LT" and any(o.kind == "sello_tiempo" and o.tst_ok for o in out[i + 1:]):
                info.pades = "B-LTA"
    finally:
        if own_session:
            await session.close()
    return out


async def _try(coro):
    try:
        return await coro
    except Exception:  # noqa: BLE001 - un segundo intento que falla no cambia el primer resultado
        return None


def _cause(now_status, cert) -> str:
    """Por qué hoy no vale una firma que sí valía en la fecha de su sello de tiempo."""
    if now_status.revoked:
        return "revocado_despues"
    if cert["tbs_certificate"]["validity"]["not_after"].native < datetime.now(timezone.utc):
        return "caducado"
    problem = getattr(now_status.trust_problem_indic, "name", "") if now_status.trust_problem_indic is not None else ""
    if problem in REVINFO_PROBLEMS:
        return "con_datos_documento"  # la información de revocación del documento ya no es reciente (B-LT habitual)
    return "fuera_de_lista"


async def _signature(validator: _Validator, state, sig, info: SignatureInfo, online: bool, root_prints: set[str], dss) -> None:
    online_failed = False
    try:
        status = await validator.signature(sig, online)
    except Exception:  # noqa: BLE001 - OCSP o CRL sin respuesta (también el tiempo agotado): se repite sin red
        if not online:
            raise
        status, online_failed = await validator.signature(sig, False), True
    problem = getattr(status.trust_problem_indic, "name", "") if status.trust_problem_indic is not None else ""
    if online and not online_failed and not status.trusted and not status.revoked and problem in REVINFO_PROBLEMS:
        offline = await validator.signature(sig, False)
        if offline.trusted:
            status, online_failed = offline, True
    tst = status.timestamp_validity
    info.tst_ok = bool(tst is not None and tst.intact and tst.valid and tst.trusted)
    now_status = status
    fetch_past = online and not online_failed
    if info.tst_ok and status.intact and status.valid and (not status.trusted or status.revoked):
        # Hoy no es de confianza, pero había un sello de tiempo válido: se valida en la fecha del sello (AdES).
        past = await _try(validator.signature(sig, fetch_past, moment=tst.timestamp))
        details = getattr(now_status, "revocation_details", None)
        revoked_at = getattr(details, "revocation_date", None) if details is not None and not details.ca_revoked else None
        if (past is None or not past.trusted) and revoked_at is not None and revoked_at > tst.timestamp:
            # Con OCSP, certvalidator no da por buena en la fecha del sello una respuesta «revocado» posterior: la fecha
            # de revocación ya se conoce y es posterior al sello, así que se valida sin revisar la del firmante.
            past = await _try(validator.signature(sig, fetch_past, moment=tst.timestamp, skip_leaf_revocation=True))
        if past is not None and past.trusted and not past.revoked:
            info.at_timestamp = _cause(now_status, status.signing_cert)
            status = past
    elif not status.trusted and not status.revoked and problem in REVINFO_PROBLEMS and dss is not None and not online:
        # Sin sello de tiempo y con información de revocación del documento ya antigua: sin ella, como si no la trajera.
        alt = await _try(validator.signature(sig, False, use_dss=False))
        if alt is not None and alt.trusted:
            status = alt
            info.notes.append("revinfo_antigua")
    info.signer, info.issuer, info.email = _name(status.signing_cert)
    info.intact, info.valid, info.trusted = bool(status.intact), bool(status.valid), bool(status.trusted)
    info.revoked = bool(status.revoked)
    info.changes = _changes(status.modification_level)
    info.changes_ok = bool(status.docmdp_ok) if status.docmdp_ok is not None else True
    info.certified = _certification(sig)
    info.reason, info.location = _text(sig.sig_object.get("/Reason")), _text(sig.sig_object.get("/Location"))
    info.subfilter = _text(sig.sig_object.get("/SubFilter")).lstrip("/")
    if not info.trusted:
        info.problem = getattr(now_status.trust_problem_indic, "name", "") if now_status.trust_problem_indic is not None else ""
    if tst is not None:
        info.when, info.tsa = tst.timestamp, _name(tst.signing_cert)[0]
        info.when_source = ("qtsa" if _qualified_tsa(state, tst) else "tsa") if info.tst_ok else "tsa_no_confianza"
    else:
        info.when = status.signer_reported_dt
    covers = _dss_covers(dss, status.signing_cert)
    if online_failed:
        info.revocation = "fallo_en_linea"
    elif online:
        info.revocation = "en_linea" if info.trusted else "no_aplica"
    elif "revinfo_antigua" in info.notes:
        info.revocation = "antigua"
    else:
        info.revocation = "documento" if covers else "no_comprobada"
    if not (info.intact and info.valid) or not info.changes_ok:
        info.level = "no_valida"
    elif info.revoked:
        info.level = "revocada"
    elif not info.trusted:
        issuer_country = str(status.signing_cert.issuer.native.get("country_name") or "")
        # Sin la lista de la UE (o sin la del país del emisor) no se puede saber si el prestador es de confianza.
        info.level = "sin_comprobar" if state.registry is None or issuer_country in state.missing else "simple"
    else:
        path = status.validation_path
        anchor = confianza.fingerprint(path.trust_anchor.authority.certificate) if path is not None else ""
        if confianza.fingerprint(status.signing_cert) in root_prints:
            info.level = "plataforma"  # el certificado del sello está en SIGN_VERIFY_EXTRA_ROOTS
        elif anchor in root_prints:
            info.level = "propia"
        else:
            info.level = "avanzada"
            _qualification(state, path, tst.timestamp if info.tst_ok else None, info)
    if info.subfilter != "ETSI.CAdES.detached":
        info.pades = "no_pades"
    elif info.tst_ok:
        info.pades = "B-LT" if covers else "B-T"
    else:
        info.pades = "B-B"


# --- Textos ---------------------------------------------------------------------------------------------------------

TEXT = {
    "es": {
        "title": "Informe de firmas", "file": "Archivo", "none": "El documento no tiene firmas digitales.",
        "signature": "Firma", "timestamp": "Sello de tiempo del documento", "field": "Campo",
        "signer": "Firmante", "issuer": "Emitido por", "tsa_name": "Autoridad de sellado", "date": "Fecha", "integrity": "Integridad",
        "changes": "Cambios posteriores", "level": "Nivel", "pades": "Nivel PAdES", "trust": "Confianza",
        "revocation": "Revocación", "reason": "Motivo", "location": "Lugar", "certified": "Certificación (DocMDP)",
        "intact": "El documento no ha cambiado desde la firma.", "broken": "El contenido firmado ha cambiado o la firma está dañada.",
        "ts_ok": "El sello de tiempo es íntegro y de confianza.", "ts_bad": "El sello de tiempo está dañado o no es de confianza.",
        "when": {"declarada": "declarada por el firmante (sin sello de tiempo)", "tsa": "del sello de tiempo de {tsa}, de confianza",
                 "qtsa": "del sello de tiempo cualificado de {tsa}", "tsa_no_confianza": "del sello de tiempo de {tsa}, que no es de confianza"},
        "change": {"ninguno": "Ninguno.", "lta": "Solo datos de validación y sellos de tiempo (permitidos).",
                   "formularios": "Relleno de formularios y firmas.", "anotaciones": "Formularios, firmas y comentarios.",
                   "otros": "Cambios de contenido después de firmar."},
        "allowed": " Estaban permitidos.", "forbidden": " No estaban permitidos: el documento ya no es el que se firmó.",
        "levels": {"no_valida": "No válida", "revocada": "Certificado revocado",
                   "simple": "Firma electrónica simple (certificado que no es de confianza)",
                   "sin_comprobar": "Sin comprobar: falta la lista de confianza de la UE para saber si el prestador es de confianza",
                   "propia": "De confianza por una raíz añadida en esta instalación (no está en la lista de la UE)",
                   "plataforma": "Sello de la plataforma (no cualificado)", "avanzada": "Avanzada (certificado de un prestador de la lista de la UE)",
                   "avanzada_qc": "Avanzada con certificado cualificado (la clave no consta en un dispositivo cualificado)",
                   "cualificada": "Cualificada"},
        "at_ts": {"caducado": "Válida en la fecha del sello de tiempo; el certificado ha caducado después.",
                  "revocado_despues": "Válida en la fecha del sello de tiempo; el certificado se revocó después.",
                  "fuera_de_lista": "Válida en la fecha del sello de tiempo; hoy el prestador ya no es de confianza.",
                  "con_datos_documento": "Validada en la fecha del sello de tiempo con la información de revocación que trae el documento."},
        "seal": " (sello electrónico)", "qualified_by": "Servicio cualificado: {service}{country}.",
        "trust_yes": "La cadena llega a una raíz de confianza.",
        "problems": {"NO_CERTIFICATE_CHAIN_FOUND": "El certificado no lleva a ningún prestador de confianza.",
                     "OUT_OF_BOUNDS_NO_POE": "El certificado ha caducado y no hay un sello de tiempo de confianza de cuando era válido.",
                     "EXPIRED": "El certificado ha caducado y no hay un sello de tiempo de confianza de cuando era válido.",
                     "NOT_YET_VALID": "El certificado todavía no era válido en esa fecha.",
                     "CHAIN_CONSTRAINTS_FAILURE": "La cadena no cumple sus restricciones (uso de las claves o políticas).",
                     "REVOKED_CA_NO_POE": "Un certificado de la cadena está revocado.",
                     "TRY_LATER": "No se ha podido obtener la información de revocación.",
                     "": "La cadena no se ha podido validar."},
        "rev": {"en_linea": "Comprobada en línea con los servicios OCSP o CRL que indica el certificado.",
                "documento": "Con la información de revocación que trae el documento.",
                "no_comprobada": "No comprobada: activa «Comprobar la revocación en línea» para hacerlo.",
                "no_aplica": "No se comprueba: la cadena no es de confianza.",
                "antigua": "La información de revocación que trae el documento es antigua y no hay sello de tiempo de cuando era válida: no se ha tenido en cuenta.",
                "fallo_en_linea": "No se ha podido comprobar en línea (el servicio OCSP o CRL no respondió); el nivel se ha calculado con lo que trae el documento."},
        "revoked": "El certificado está revocado.", "docmdp": {"sin_cambios": "no se permiten cambios", "formularios": "se permite rellenar formularios",
                                                             "formularios_anotaciones": "se permiten formularios y comentarios"},
        "no_pades": "PDF (no PAdES: {subfilter})",
        "eutl": "Lista de confianza de la UE descargada el {date} ({n} países).", "eutl_stale": " Está desactualizada: puede no reflejar cambios recientes.",
        "eutl_missing": " Sin la lista de: {missing}.", "eutl_carried": " Copias anteriores (no se pudieron actualizar): {carried}.",
        "dss": "Los datos de validación del documento (DSS) están dañados y no se han usado.",
        "eutl_none": "Lista de confianza de la UE no comprobada: todavía no se ha podido descargar. Ninguna firma puede salir como avanzada ni cualificada.",
        "lenient": "El archivo tiene errores de estructura y se ha leído en modo tolerante: dos lectores podrían mostrar contenidos distintos. Desconfía si no esperabas este documento así.",
        "legal": "Los niveles son una indicación técnica a partir del archivo; el valor jurídico de una firma (eIDAS) depende de más circunstancias.",
        "error": "No se ha podido validar esta firma ({problem}).",
        "summary": "{n} firma(s): {ok} válida(s) y de confianza.", "summary_none": "Sin firmas digitales.",
        "report": "informe-firmas-{stem}.html", "zip": "informes-firmas.zip",
        "format": "Formato", "xades_tst": "Trae un sello de tiempo XAdES, que no se ha comprobado: la fecha es la que declara el firmante.",
    },
    "en": {
        "title": "Signature report", "file": "File", "none": "The document has no digital signatures.",
        "signature": "Signature", "timestamp": "Document time stamp", "field": "Field",
        "signer": "Signer", "issuer": "Issued by", "tsa_name": "Time-stamping authority", "date": "Date", "integrity": "Integrity",
        "changes": "Later changes", "level": "Level", "pades": "PAdES level", "trust": "Trust",
        "revocation": "Revocation", "reason": "Reason", "location": "Location", "certified": "Certification (DocMDP)",
        "intact": "The document has not changed since it was signed.", "broken": "The signed content has changed or the signature is damaged.",
        "ts_ok": "The time stamp is intact and trusted.", "ts_bad": "The time stamp is damaged or not trusted.",
        "when": {"declarada": "claimed by the signer (no time stamp)", "tsa": "from {tsa}'s time stamp, trusted",
                 "qtsa": "from {tsa}'s qualified time stamp", "tsa_no_confianza": "from {tsa}'s time stamp, not trusted"},
        "change": {"ninguno": "None.", "lta": "Only validation data and time stamps (allowed).",
                   "formularios": "Form filling and signatures.", "anotaciones": "Forms, signatures and comments.",
                   "otros": "Content changes after signing."},
        "allowed": " They were allowed.", "forbidden": " They were not allowed: the document is no longer the one that was signed.",
        "levels": {"no_valida": "Not valid", "revocada": "Certificate revoked",
                   "simple": "Simple electronic signature (untrusted certificate)",
                   "sin_comprobar": "Not checked: the EU trusted list is missing, so the provider's trust cannot be known",
                   "propia": "Trusted through a root added in this installation (not on the EU list)",
                   "plataforma": "Platform seal (not qualified)", "avanzada": "Advanced (certificate from a provider on the EU list)",
                   "avanzada_qc": "Advanced with a qualified certificate (the key is not declared on a qualified device)",
                   "cualificada": "Qualified"},
        "at_ts": {"caducado": "Valid at the time-stamp date; the certificate expired afterwards.",
                  "revocado_despues": "Valid at the time-stamp date; the certificate was revoked afterwards.",
                  "fuera_de_lista": "Valid at the time-stamp date; today the provider is no longer trusted.",
                  "con_datos_documento": "Validated at the time-stamp date with the revocation information included in the document."},
        "seal": " (electronic seal)", "qualified_by": "Qualified service: {service}{country}.",
        "trust_yes": "The chain reaches a trusted root.",
        "problems": {"NO_CERTIFICATE_CHAIN_FOUND": "The certificate does not lead to any trusted provider.",
                     "OUT_OF_BOUNDS_NO_POE": "The certificate has expired and there is no trusted time stamp from when it was valid.",
                     "EXPIRED": "The certificate has expired and there is no trusted time stamp from when it was valid.",
                     "NOT_YET_VALID": "The certificate was not valid yet at that date.",
                     "CHAIN_CONSTRAINTS_FAILURE": "The chain does not meet its constraints (key usage or policies).",
                     "REVOKED_CA_NO_POE": "A certificate in the chain is revoked.",
                     "TRY_LATER": "The revocation information could not be obtained.",
                     "": "The chain could not be validated."},
        "rev": {"en_linea": "Checked online with the OCSP or CRL services the certificate names.",
                "documento": "With the revocation information included in the document.",
                "no_comprobada": "Not checked: turn on “Check revocation online” to do it.",
                "no_aplica": "Not checked: the chain is not trusted.",
                "antigua": "The revocation information in the document is old and there is no time stamp from when it was current: it was not used.",
                "fallo_en_linea": "It could not be checked online (the OCSP or CRL service did not answer); the level was worked out from what the document includes."},
        "revoked": "The certificate is revoked.", "docmdp": {"sin_cambios": "no changes allowed", "formularios": "form filling allowed",
                                                            "formularios_anotaciones": "forms and comments allowed"},
        "no_pades": "PDF (not PAdES: {subfilter})",
        "eutl": "EU trusted list downloaded on {date} ({n} countries).", "eutl_stale": " It is out of date: it may not reflect recent changes.",
        "eutl_missing": " Missing the list of: {missing}.", "eutl_carried": " Earlier copies (could not be updated): {carried}.",
        "dss": "The document's validation data (DSS) is damaged and was not used.",
        "eutl_none": "EU trusted list not checked: it could not be downloaded yet. No signature can come out as advanced or qualified.",
        "lenient": "The file has structural errors and was read in tolerant mode: two readers could show different content. Be wary if you did not expect this document to look like this.",
        "legal": "Levels are a technical indication from the file; the legal value of a signature (eIDAS) depends on more circumstances.",
        "error": "This signature could not be validated ({problem}).",
        "summary": "{n} signature(s): {ok} valid and trusted.", "summary_none": "No digital signatures.",
        "report": "signature-report-{stem}.html", "zip": "signature-reports.zip",
        "format": "Format", "xades_tst": "It carries an XAdES time stamp, which was not checked: the date is the one the signer claims.",
    },
}


def _row(label: str, value: str) -> str:
    return f"<tr><th>{html.escape(label)}</th><td>{value}</td></tr>"


def _block(t, n: int, s: SignatureInfo) -> str:
    e = html.escape
    title = f"{t['timestamp'] if s.kind == 'sello_tiempo' else t['signature']} {n}"
    rows = [_row(t["field"], e(s.field))]
    if s.problem and not s.signer:
        rows.append(_row(t["level"], e(t["error"].format(problem=s.problem))))
        return f"<section><h2>{e(title)}</h2><table>{''.join(rows)}</table></section>"
    if s.kind == "sello_tiempo":
        rows.append(_row(t["tsa_name"], e(s.signer)))
        if s.when:
            rows.append(_row(t["date"], e(f"{s.when:%d/%m/%Y %H:%M:%S %Z}".strip())))
        rows.append(_row(t["integrity"], e(t["ts_ok"] if s.tst_ok else t["ts_bad"])))
        return f"<section><h2>{e(title)}</h2><table>{''.join(rows)}</table></section>"
    rows.append(_row(t["signer"], e(s.signer + (f" <{s.email}>" if s.email else ""))))
    rows.append(_row(t["issuer"], e(s.issuer)))
    if s.when:
        rows.append(_row(t["date"], e(f"{s.when:%d/%m/%Y %H:%M:%S %Z}".strip() + ", " + t["when"][s.when_source].format(tsa=s.tsa))))
    rows.append(_row(t["integrity"], e(t["intact"] if s.intact and s.valid else t["broken"])))
    if s.family == "PAdES":
        rows.append(_row(t["changes"], e(t["change"][s.changes] + ("" if s.changes == "ninguno" else t["allowed"] if s.changes_ok else t["forbidden"]))))
    if s.certified:
        rows.append(_row(t["certified"], e(t["docmdp"][s.certified])))
    level = t["levels"][s.level] + (t["seal"] if "sello" in s.notes else "")
    extra = f"<br>{e(t['at_ts'][s.at_timestamp])}" if s.at_timestamp else ""
    rows.append(_row(t["level"], f"<b class=\"l-{e(s.level)}\">{e(level)}</b>{extra}"))
    if s.family == "PAdES":
        rows.append(_row(t["pades"], e(t["no_pades"].format(subfilter=s.subfilter or "?") if s.pades == "no_pades" else s.pades)))
    else:
        rows.append(_row(t["format"], e(s.ades or s.family) + (f"<br>{e(t['xades_tst'])}" if "xades_tst" in s.notes else "")))
    trust = t["trust_yes"] if s.trusted else t["problems"].get(s.problem, t["problems"][""])
    if s.qualified_service:
        trust += " " + t["qualified_by"].format(service=s.qualified_service, country=f" ({s.country})" if s.country else "")
    rows.append(_row(t["trust"], e(trust)))
    rows.append(_row(t["revocation"], e(t["revoked"] if s.revoked else t["rev"][s.revocation])))
    if s.reason:
        rows.append(_row(t["reason"], e(s.reason)))
    if s.location:
        rows.append(_row(t["location"], e(s.location)))
    return f"<section><h2>{e(title)}</h2><table>{''.join(rows)}</table></section>"


def render(name: str, items: list[SignatureInfo], state: confianza.TrustState, locale: str, lenient: bool = False) -> str:
    t = TEXT.get(locale, TEXT["es"])
    e = html.escape
    body = "".join(_block(t, n, s) for n, s in enumerate(items, 1)) or f"<p>{e(t['none'])}</p>"
    if state.registry is not None and state.refreshed_at:
        eutl = (t["eutl"].format(date=f"{state.refreshed_at:%d/%m/%Y}", n=len(state.territories))
                + (t["eutl_stale"] if state.stale else "") + (t["eutl_missing"].format(missing=", ".join(state.missing)) if state.missing else "")
                + (t["eutl_carried"].format(carried=", ".join(f"{k} ({v:%d/%m/%Y})" for k, v in sorted(state.carried.items())))
                   if state.carried else ""))
    else:
        eutl = t["eutl_none"]
    warning = (f"<p class=\"w\">{e(t['lenient'])}</p>" if lenient else "") + (
        f"<p class=\"w\">{e(t['dss'])}</p>" if any("dss" in s.notes for s in items) else "")
    return (f"<!doctype html><html lang=\"{e(locale)}\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\">"
            f"<title>{e(t['title'])}: {e(name)}</title><style>"
            "body{font:15px/1.5 system-ui,sans-serif;color:#1f2328;max-width:900px;margin:24px auto;padding:0 16px}"
            "h1{font-size:22px}h2{font-size:17px;margin-top:28px}table{border-collapse:collapse;width:100%}"
            "th,td{border-bottom:1px solid #d0d7de;padding:6px 8px;text-align:left;vertical-align:top}th{width:13em;color:#59636e}"
            ".l-cualificada,.l-avanzada,.l-avanzada_qc,.l-plataforma,.l-propia{color:#116329}.l-no_valida,.l-revocada{color:#a40e26}"
            ".l-simple,.l-sin_comprobar{color:#7d4e00}.m{color:#59636e;font-size:13px}.w{background:#fff8c5;padding:8px 12px;border-radius:6px}"
            "section{break-inside:avoid}@media print{body{margin:0;max-width:none}}</style></head><body>"
            f"<h1>{e(t['title'])}</h1><p>{e(t['file'])}: <b>{e(name)}</b></p>{warning}{body}"
            f"<p class=\"m\">{e(eutl)}</p><p class=\"m\">{e(t['legal'])}</p></body></html>")


def summary(items: list[SignatureInfo], locale: str) -> str:
    t = TEXT.get(locale, TEXT["es"])
    sigs = [s for s in items if s.kind == "firma"]
    if not sigs:
        return t["summary_none"]
    return t["summary"].format(n=len(sigs), ok=sum(1 for s in sigs if s.level in TRUSTED_LEVELS))


def run(ctx: ToolContext) -> list[dict]:
    from tools.pdf.common import open_pdf

    t = TEXT.get(ctx.locale, TEXT["es"])
    state = confianza.eu_registry(ctx.settings)
    roots = confianza.extra_roots(ctx.settings)
    outputs = []
    # Un plazo para todo el trabajo (hasta 100 archivos), dentro del límite de la tarea: wait_for solo corta en las
    # esperas de red; el trabajo de CPU de pyHanko lo corta el límite de Celery.
    deadline = time.monotonic() + DEADLINE_SECONDS
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        with open_pdf(inp.path, None, ctx.plan.pdf_pages):
            pass  # cifrado, corrupto o con más páginas que el plan: los errores de siempre antes de pyHanko
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ToolError(ErrorCode.TIMEOUT, "verificación de firmas")
        try:
            with open(inp.path, "rb") as stream:  # sin cargar el archivo entero en memoria
                items, lenient = asyncio.run(asyncio.wait_for(
                    _analyse(stream, state, roots, ctx.options.revocacion, ctx.settings.EGRESS_WEB_URL), remaining))
        except ToolError:
            raise
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise ToolError(ErrorCode.TIMEOUT, "verificación de firmas") from exc
        except Exception as exc:  # noqa: BLE001 - pyHanko no puede leer la estructura del archivo
            raise ToolError(ErrorCode.CORRUPT_FILE, type(exc).__name__) from exc
        stem = Path(inp.name).stem or "documento"
        name = t["report"].format(stem=stem)
        dst = ctx.output(name)
        dst.write_text(render(inp.name, items, state, ctx.locale, lenient), encoding="utf-8")
        outputs.append({"path": str(dst), "name": name, "note": summary(items, ctx.locale)})
    return with_batch_zip(ctx, outputs, t["zip"])
