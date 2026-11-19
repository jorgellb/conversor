"""F4, lote A: verificar-firmas-pdf (A.7 y 7.23) con la PKI de pruebas de certomancer (scripts/fixtures/pki.py).

Las firmas se hacen con pyHanko y claves en archivo (el sello por PKCS#11 llega con F4-A2). La lista de la UE se sustituye por un `TSPRegistry` montado aquí con la CA de pruebas como servicio
cualificado, y OCSP y CRL en línea por el «illusionist» de certomancer (un servidor aiohttp en el proceso): sin red.
"""
from __future__ import annotations

import asyncio
import io
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pikepdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "fixtures"))

from test_tools import make_ctx, run  # noqa: E402,F401 - fixture compartida

TOOL = "verificar-firmas-pdf"


@pytest.fixture(scope="session")
def arch(tmp_path_factory):
    import pki

    return pki.load(tmp_path_factory.mktemp("pki"))


def _signer(arch, label="signer1"):
    from pyhanko.sign import signers
    from pyhanko_certvalidator.registry import SimpleCertificateStore

    return signers.SimpleSigner(signing_cert=arch.get_cert(label), signing_key=arch.key_set.get_private_key(label),
                                cert_registry=SimpleCertificateStore.from_certs([arch.get_cert("interm"), arch.get_cert("root")]))


def _tsa(arch, at: datetime | None = None):
    from pyhanko.sign.timestamps.dummy_client import DummyTimeStamper
    from pyhanko_certvalidator.registry import SimpleCertificateStore

    return DummyTimeStamper(tsa_cert=arch.get_cert("tsa"), tsa_key=arch.key_set.get_private_key("tsa"),
                            certs_to_embed=SimpleCertificateStore.from_certs([arch.get_cert("root")]), fixed_dt=at)


def _blank(pages: int = 1) -> bytes:
    pdf = pikepdf.new()
    for _ in range(pages):
        pdf.add_blank_page()
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def sign(arch, data: bytes, certify=None, timestamp: bool = True, field: str = "Firma1", who: str = "signer1",
         ts_at: datetime | None = None, subfilter=None) -> bytes:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    meta = signers.PdfSignatureMetadata(field_name=field, reason="Conforme", location="Madrid",
                                        subfilter=subfilter or fields.SigSeedSubFilter.PADES,
                                        certify=certify is not None, docmdp_permissions=certify or fields.MDPPerm.FILL_FORMS)
    return signers.sign_pdf(IncrementalPdfFileWriter(io.BytesIO(data)), meta, signer=_signer(arch, who),
                            timestamper=_tsa(arch, ts_at) if timestamp else None).getvalue()


def _registry(arch, qualified_tsa: bool = False):
    """La CA de pruebas como servicio de CA cualificado de un «país» ES, como lo dejaría la lista de la UE."""
    from pyhanko.sign.validation.qualified.tsp import (
        CA_QC_URI, QTST_URI, BaseServiceInformation, CAServiceInformation, QTSTServiceInformation, TSPRegistry)

    registry = TSPRegistry()
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    info = BaseServiceInformation(service_type=CA_QC_URI, service_name="Prestador de pruebas", valid_from=since, valid_until=None,
                                  provider_certs=(arch.get_cert("root"),), additional_info_certificate_type=frozenset(),
                                  other_additional_info=frozenset())
    registry.register_ca(CAServiceInformation(base_info=info, qualifications=frozenset(), expired_certs_revocation_info=None))
    if qualified_tsa:
        tsa = BaseServiceInformation(service_type=QTST_URI, service_name="TSA cualificada de pruebas", valid_from=since,
                                     valid_until=None, provider_certs=(arch.get_cert("tsa"),),
                                     additional_info_certificate_type=frozenset(), other_additional_info=frozenset())
        registry.register_tst(QTSTServiceInformation(base_info=tsa, qualifications=frozenset()))
    return registry


def _state(registry=None):
    from tools.sign.confianza import TrustState

    return TrustState(registry, datetime.now(timezone.utc) if registry is not None else None, ["ES"] if registry is not None else [])


def _empty_eu():
    from pyhanko.sign.validation.qualified.tsp import TSPRegistry

    return _state(TSPRegistry())


def analyse(data: bytes, state=None, roots=(), online: bool = False, session=None):
    from tools.sign import verificar

    items, _lenient = asyncio.run(verificar._analyse(data, state or _state(), list(roots), online, None, session=session))
    return items


# --- Niveles, integridad y cambios ---------------------------------------------------------------------------------


def test_platform_seal_and_own_root(arch):
    """«Sello de la plataforma» solo si el propio certificado está en las raíces propias; si solo está su raíz, «propia»."""
    [s] = analyse(sign(arch, _blank()), roots=[arch.get_cert("root"), arch.get_cert("signer1")])
    assert (s.kind, s.level, s.intact, s.valid, s.trusted) == ("firma", "plataforma", True, True, True)
    [s] = analyse(sign(arch, _blank()), roots=[arch.get_cert("root")])
    assert s.level == "propia"
    assert s.signer == "Ana Firmante" and s.email == "ana@ejemplo.test" and s.issuer == "Intermedia de pruebas"
    assert (s.reason, s.location, s.pades, s.when_source, s.tsa) == ("Conforme", "Madrid", "B-T", "tsa", "TSA de pruebas")


def test_eu_listed_provider_is_advanced_with_service_and_country(arch):
    [s] = analyse(sign(arch, _blank()), state=_state(_registry(arch)))
    assert s.level == "avanzada" and s.qualified_service == "Prestador de pruebas" and s.country == "ES"


def test_qualified_tsa_marks_the_date_as_qualified(arch):
    [s] = analyse(sign(arch, _blank()), state=_state(_registry(arch, qualified_tsa=True)))
    assert s.when_source == "qtsa"


def test_untrusted_chain_is_simple_and_says_why(arch):
    [s] = analyse(sign(arch, _blank()), state=_empty_eu())
    assert (s.level, s.trusted, s.problem, s.when_source, s.pades) == ("simple", False, "NO_CERTIFICATE_CHAIN_FOUND", "tsa_no_confianza", "B-B")
    [s] = analyse(sign(arch, _blank()))  # sin lista de la UE no se puede saber: «sin comprobar», no «simple»
    assert s.level == "sin_comprobar"


def test_qualified_certificate_from_listed_ca_is_qualified(arch):
    [s] = analyse(sign(arch, _blank(), who="signer-qc"), state=_state(_registry(arch)))
    assert (s.level, s.qualified_service, s.country) == ("cualificada", "Prestador de pruebas", "ES")
    [s] = analyse(sign(arch, _blank(), who="signer-qc"), roots=[arch.get_cert("root")])
    assert s.level == "propia"  # sin la lista de la UE no hay cualificación


def test_expired_certificate_is_valid_at_the_timestamp_date(arch):
    """AdES: con un sello de tiempo de confianza de cuando el certificado era válido, la firma sigue valiendo."""
    stamped = sign(arch, _blank(), who="signer3", ts_at=datetime(2021, 6, 1, tzinfo=timezone.utc))
    [s] = analyse(stamped, roots=[arch.get_cert("root")])
    assert (s.level, s.at_timestamp, s.trusted, s.when.year) == ("propia", "caducado", True, 2021)
    [s] = analyse(sign(arch, _blank(), who="signer3", timestamp=False), roots=[arch.get_cert("root")])
    assert s.level == "sin_comprobar"  # sin lista de la UE
    assert not s.trusted and s.problem in ("OUT_OF_BOUNDS_NO_POE", "EXPIRED")


def test_adobe_subfilter_is_not_pades(arch):
    from pyhanko.sign import fields

    [s] = analyse(sign(arch, _blank(), subfilter=fields.SigSeedSubFilter.ADOBE_PKCS7_DETACHED), roots=[arch.get_cert("root")])
    assert s.pades == "no_pades" and s.subfilter == "adbe.pkcs7.detached" and s.level == "propia"


def test_too_many_signatures(arch, monkeypatch):
    from core.errors import ToolError
    from tools.sign import verificar

    monkeypatch.setattr(verificar, "MAX_SIGNATURES", 1)
    with pytest.raises(ToolError) as err:
        analyse(sign(arch, sign(arch, _blank()), field="Firma2"))
    assert err.value.code == "LIMIT_EXCEEDED" and err.value.detail == "sig_count:2>1"


def test_without_timestamp_the_date_is_only_claimed(arch):
    [s] = analyse(sign(arch, _blank(), timestamp=False), roots=[arch.get_cert("root")])
    assert (s.pades, s.when_source) == ("B-B", "declarada") and s.when is not None


def test_changed_byte_breaks_integrity(arch):
    bad = bytearray(sign(arch, _blank()))
    i = bad.find(b"/Type /Page")
    bad[i + 1:i + 5] = b"Typo"
    [s] = analyse(bytes(bad), roots=[arch.get_cert("root")])
    assert s.level == "no_valida" and not s.intact


def _incremental(data: bytes, change) -> bytes:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter

    w = IncrementalPdfFileWriter(io.BytesIO(data))
    page = w.root["/Pages"]["/Kids"][0].get_object()
    change(w, page)
    w.update_container(page)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def test_content_change_after_signing_is_not_allowed(arch):
    from pyhanko.pdf_utils import generic

    rotated = _incremental(sign(arch, _blank()), lambda w, p: p.__setitem__(generic.NameObject("/Rotate"), generic.NumberObject(90)))
    [s] = analyse(rotated, roots=[arch.get_cert("root")])
    assert (s.changes, s.changes_ok, s.level) == ("otros", False, "no_valida") and s.intact


def test_certification_no_changes_then_comment_is_detected(arch):
    """16.6: un cambio que la certificación (DocMDP) no permite se detecta con el análisis de diferencias de pyHanko."""
    from pyhanko.pdf_utils import generic
    from pyhanko.sign import fields

    def comment(w, page):
        annot = generic.DictionaryObject({
            generic.NameObject("/Type"): generic.NameObject("/Annot"), generic.NameObject("/Subtype"): generic.NameObject("/Text"),
            generic.NameObject("/Rect"): generic.ArrayObject([generic.NumberObject(0)] * 4),
            generic.NameObject("/Contents"): generic.TextStringObject("añadido después")})
        page[generic.NameObject("/Annots")] = generic.ArrayObject([w.add_object(annot)])

    certified = sign(arch, _blank(), certify=fields.MDPPerm.NO_CHANGES)
    [ok] = analyse(certified, roots=[arch.get_cert("root")])
    assert ok.certified == "sin_cambios" and ok.changes == "ninguno" and ok.level == "propia"
    [s] = analyse(_incremental(certified, comment), roots=[arch.get_cert("root")])
    assert s.certified == "sin_cambios" and not s.changes_ok and s.level == "no_valida"


def test_two_signatures_lt_and_lta_levels(arch):
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers
    from pyhanko.sign.validation.dss import DocumentSecurityStore

    twice = sign(arch, sign(arch, _blank()), field="Firma2")
    [a, b] = analyse(twice, roots=[arch.get_cert("root")])
    assert a.changes == "formularios" and a.changes_ok and a.level == b.level == "propia" and a.certified == ""
    buf = io.BytesIO(twice)
    crl = arch.service_registry.get_crl("interm", datetime.now(timezone.utc))
    DocumentSecurityStore.add_dss(buf, sig_contents=None, certs=[arch.get_cert("interm"), arch.get_cert("root")], crls=[crl])
    lt = buf.getvalue()
    assert [s.pades for s in analyse(lt, roots=[arch.get_cert("root")])] == ["B-LT", "B-LT"]
    assert {s.revocation for s in analyse(lt, roots=[arch.get_cert("root")])} == {"documento"}
    lta = signers.PdfTimeStamper(_tsa(arch)).timestamp_pdf(IncrementalPdfFileWriter(io.BytesIO(lt)), md_algorithm="sha256").getvalue()
    items = analyse(lta, roots=[arch.get_cert("root")])
    assert [s.kind for s in items] == ["firma", "firma", "sello_tiempo"]
    assert [s.pades for s in items[:2]] == ["B-LTA", "B-LTA"] and items[2].when_source == "tsa"


def _with_dss(arch, data: bytes, who: str, crl: bool = False, ocsp: bool = False) -> bytes:
    from pyhanko.sign.validation.dss import DocumentSecurityStore
    from pyhanko_certvalidator.authority import AuthorityWithCert
    from pyhanko_certvalidator.fetchers.common_utils import format_ocsp_request

    now = datetime.now(timezone.utc)
    kwargs = {"certs": [arch.get_cert("interm"), arch.get_cert("root")]}
    if crl:
        kwargs["crls"] = [arch.service_registry.get_crl("interm", now)]
    if ocsp:
        req = format_ocsp_request(arch.get_cert(who), AuthorityWithCert(arch.get_cert("interm")), certid_hash_algo="sha1",
                                  request_nonces=False)
        kwargs["ocsps"] = [arch.service_registry.summon_responder("interm", at_time=now).build_ocsp_response(req)]
    buf = io.BytesIO(data)
    DocumentSecurityStore.add_dss(buf, sig_contents=None, **kwargs)
    return buf.getvalue()


@pytest.mark.parametrize("with_crl", [True, False], ids=["crl", "ocsp"])
def test_revoked_after_the_timestamp_is_valid_before_is_revoked(arch, with_crl):
    """Berta está revocada desde 2025: con un sello de tiempo de 2024 la firma valía (CRL u OCSP en el DSS); de 2025-06, no."""
    before = sign(arch, _blank(), who="signer2", ts_at=datetime(2024, 6, 1, tzinfo=timezone.utc))
    [s] = analyse(_with_dss(arch, before, "signer2", crl=with_crl, ocsp=not with_crl), roots=[arch.get_cert("root")])
    assert (s.level, s.at_timestamp, s.revoked) == ("propia", "revocado_despues", False)
    after = sign(arch, _blank(), who="signer2", ts_at=datetime(2025, 6, 1, tzinfo=timezone.utc))
    [s] = analyse(_with_dss(arch, after, "signer2", crl=with_crl, ocsp=not with_crl), roots=[arch.get_cert("root")])
    assert s.level == "revocada" and s.at_timestamp == ""


def test_blt_with_embedded_ocsp_is_valid_with_a_neutral_reason(arch):
    """B-LT corriente: sello de tiempo y OCSP del documento. No se dice que el prestador haya dejado de ser de confianza."""
    [s] = analyse(_with_dss(arch, sign(arch, _blank()), "signer1", ocsp=True), roots=[arch.get_cert("root")])
    assert s.level == "propia" and s.pades == "B-LT" and s.at_timestamp in ("", "con_datos_documento")


def test_owner_password_only_signed_pdf_is_verified(arch, make_ctx, tmp_path, monkeypatch):
    """Con contraseña de propietario solamente (permisos), habitual en contratos: se abre con la de usuario vacía."""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    from tools.sign import confianza

    pdf = pikepdf.new()
    pdf.add_blank_page()
    buf = io.BytesIO()
    pdf.save(buf, encryption=pikepdf.Encryption(owner="dueño", user="", R=6, allow=pikepdf.Permissions(modify_other=False)))
    w = IncrementalPdfFileWriter(io.BytesIO(buf.getvalue()))
    w.encrypt("")
    signed = signers.sign_pdf(w, signers.PdfSignatureMetadata(field_name="Firma1", subfilter=fields.SigSeedSubFilter.PADES),
                              signer=_signer(arch), timestamper=_tsa(arch)).getvalue()
    [s] = analyse(signed, roots=[arch.get_cert("root")])
    assert (s.level, s.signer) == ("propia", "Ana Firmante")
    monkeypatch.setattr(confianza, "eu_registry", lambda settings: _state())
    out = run(TOOL, make_ctx(TOOL, [_write(tmp_path, "contrato.pdf", signed)]))
    assert out[0]["note"].startswith("1 firma(s)")


def test_oversized_response_is_cut_while_reading():
    """Una respuesta OCSP, CRL o de certificado de más de MAX_RESPONSE_BYTES se corta al leerla, sin cargarla entera."""
    import aiohttp
    from aiohttp import web

    from tools.sign import verificar

    async def go():
        async def big(request):
            resp = web.StreamResponse()
            await resp.prepare(request)
            for _ in range(40):
                await resp.write(b"x" * (1024 * 1024))
            return resp

        app = web.Application()
        app.router.add_get("/crl", big)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        session = verificar.make_session(None)
        try:
            async with session.get(f"http://127.0.0.1:{port}/crl") as resp:
                with pytest.raises(aiohttp.ClientPayloadError):
                    await resp.read()
        finally:
            await session.close()
            await runner.cleanup()

    asyncio.run(go())


# --- Revocación en línea ------------------------------------------------------------------------------------------


def _online(arch, data: bytes):
    from certomancer.integrations.aiohttp_illusionist import AsyncIllusionist
    from tools.sign import verificar
    from tools.sign.confianza import TrustState

    async def go():
        async with AsyncIllusionist(arch).serving_session() as session:
            return (await verificar._analyse(data, TrustState(None, None), [arch.get_cert("root")], True, None, session=session))[0]

    return asyncio.run(go())


def test_online_revocation_check_through_ocsp_and_crl(arch):
    [s] = _online(arch, sign(arch, _blank()))
    assert (s.revocation, s.level, s.revoked) == ("en_linea", "propia", False)


def test_online_revocation_detects_a_revoked_certificate(arch):
    [s] = _online(arch, sign(arch, _blank(), who="signer2"))
    assert s.signer == "Berta Revocada" and s.revoked and s.level == "revocada"
    [offline] = analyse(sign(arch, _blank(), who="signer2"), roots=[arch.get_cert("root")])
    assert offline.revocation == "no_comprobada" and offline.level == "propia"  # sin la opción no se sabe


def test_online_revocation_unreachable_falls_back_and_says_so(arch):
    """Sin respuesta del OCSP ni de la CRL (aquí, una sesión sin servidor): se dice y se clasifica sin red."""
    import aiohttp

    from tools.sign import verificar
    from tools.sign.confianza import TrustState

    signed = sign(arch, _blank())

    async def go():
        async with aiohttp.ClientSession(proxy="http://127.0.0.1:9", timeout=aiohttp.ClientTimeout(total=5)) as session:
            return (await verificar._analyse(signed, TrustState(None, None), [arch.get_cert("root")], True, None, session=session))[0]

    [s] = asyncio.run(go())
    assert (s.revocation, s.level) == ("fallo_en_linea", "propia")


def test_online_revocation_timeout_falls_back(arch, monkeypatch):
    """Un OCSP o una CRL que aceptan la conexión y no contestan nunca (tiempo agotado, no conexión rechazada)."""
    import aiohttp

    from tools.sign import verificar
    from tools.sign.confianza import TrustState

    monkeypatch.setattr(verificar, "REQUEST_TIMEOUT", 1)
    signed = sign(arch, _blank())

    async def go():
        async def tarpit(reader, writer):
            await asyncio.sleep(30)

        server = await asyncio.start_server(tarpit, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            async with aiohttp.ClientSession(proxy=f"http://127.0.0.1:{port}") as session:
                return (await verificar._analyse(signed, TrustState(None, None), [arch.get_cert("root")], True, None,
                                                 session=session))[0]
        finally:
            server.close()

    [s] = asyncio.run(go())
    assert (s.revocation, s.level, s.problem) == ("fallo_en_linea", "propia", "")


# --- La herramienta: informe, lotes, errores y lista de la UE ---------------------------------------------------------


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_tool_report_batch_and_notes(make_ctx, arch, tmp_path, monkeypatch):
    from tools.sign import confianza

    monkeypatch.setattr(confianza, "eu_registry", lambda settings: _state(_registry(arch)))
    signed = _write(tmp_path, "contrato <firmado>.pdf", sign(arch, _blank()))
    plain = _write(tmp_path, "sin-firma.pdf", _blank())
    out = run(TOOL, make_ctx(TOOL, [signed, plain]))
    assert [o["name"] for o in out] == ["informe-firmas-contrato <firmado>.html", "informe-firmas-sin-firma.html", "informes-firmas.zip"]
    assert out[0]["note"] == "1 firma(s): 1 válida(s) y de confianza." and out[1]["note"] == "Sin firmas digitales."
    page = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert "contrato &lt;firmado&gt;.pdf" in page and "<firmado>" not in page
    assert "Avanzada (certificado de un prestador de la lista de la UE)" in page
    assert "Servicio cualificado: Prestador de pruebas (ES)." in page and "Lista de confianza de la UE descargada el" in page
    assert "No comprobada: activa «Comprobar la revocación en línea»" in page
    assert "El documento no tiene firmas digitales." in Path(out[1]["path"]).read_text(encoding="utf-8")


def test_tool_without_eu_list_says_not_checked_in_english(make_ctx, arch, tmp_path, monkeypatch):
    from core.settings import get_settings

    monkeypatch.setattr(get_settings(), "EUTL_CACHE_PATH", tmp_path / "vacia")
    ctx = make_ctx(TOOL, [_write(tmp_path, "a.pdf", sign(arch, _blank()))])
    ctx.locale = "en"
    out = run(TOOL, ctx)
    page = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert out[0]["name"] == "signature-report-a.html" and "EU trusted list not checked" in page
    assert "Not checked: the EU trusted list is missing" in page and out[0]["note"] == "1 signature(s): 0 valid and trusted."


def test_tool_extra_roots_setting(make_ctx, arch, tmp_path, monkeypatch):
    from asn1crypto import pem

    from core.settings import get_settings

    roots = tmp_path / "raices.pem"
    roots.write_bytes(pem.armor("CERTIFICATE", arch.get_cert("root").dump()) + pem.armor("CERTIFICATE", arch.get_cert("signer1").dump()))
    monkeypatch.setattr(get_settings(), "SIGN_VERIFY_EXTRA_ROOTS", str(roots))
    monkeypatch.setattr(get_settings(), "EUTL_CACHE_PATH", tmp_path / "vacia")
    out = run(TOOL, make_ctx(TOOL, [_write(tmp_path, "a.pdf", sign(arch, _blank()))]))
    assert "Sello de la plataforma (no cualificado)" in Path(out[0]["path"]).read_text(encoding="utf-8")


def test_tool_errors(make_ctx, fixtures_dir, tmp_path):
    from core.errors import ToolError

    with pytest.raises(ToolError) as err:
        run(TOOL, make_ctx(TOOL, [fixtures_dir / "cifrado.pdf"]))
    assert err.value.code == "PASSWORD_REQUIRED"
    with pytest.raises(ToolError) as err:
        run(TOOL, make_ctx(TOOL, [_write(tmp_path, "roto.pdf", b"%PDF-1.7\nnada")]))
    assert err.value.code == "CORRUPT_FILE"
    ctx = make_ctx(TOOL, [_write(tmp_path, "largo.pdf", _blank(3))], plan="anon")
    ctx.plan.pdf_pages = 2
    with pytest.raises(ToolError) as err:
        run(TOOL, ctx)
    assert err.value.code == "LIMIT_EXCEEDED"


def test_sign_category_never_uses_ai():
    from core.ai import EXCLUDED_CATEGORIES
    from core.registry import load_registry

    spec = load_registry().require(TOOL)
    assert spec.category in EXCLUDED_CATEGORIES and spec.ai is None and spec.queue == "sign.verify"


# --- Lista de confianza de la UE: caché versionada y carga sin red -----------------------------------------------


def test_eutl_cache_versions_pointer_and_stale(tmp_path, monkeypatch):
    """`refresh` deja una versión nueva y cambia el puntero al final; `eu_registry` la lee sin red y avisa si es vieja."""
    from types import SimpleNamespace

    from pyhanko.sign.validation.qualified import eutl_parse

    from tools.sign import confianza

    settings = SimpleNamespace(EUTL_CACHE_PATH=tmp_path, EUTL_REFRESH_HOURS=24, EGRESS_WEB_URL="", EUTL_LOTL_URL="x")

    async def fake_download(_settings):
        return "<lotl/>", [], {"ES": "<tl-es/>", "FR": "<tl-fr/>"}, ["IT: caída"], ["ES", "FR", "IT"]

    monkeypatch.setattr(confianza, "_download", fake_download)
    summary = confianza.refresh(settings)
    assert summary["territories"] == ["ES", "FR"] and summary["errors"] == ["IT: caída"]
    folder = tmp_path / summary["version"]
    assert (folder / "tl" / "ES.xml").read_text() == "<tl-es/>"

    refs = [eutl_parse.TLReference("https://es", "ES", [], frozenset()), eutl_parse.TLReference("https://pt", "PT", [], frozenset())]
    loaded: list[str] = []
    monkeypatch.setattr(eutl_parse, "validate_and_parse_lotl",
                        lambda xml, certs: eutl_parse.LOTLParseResult(refs, [], [], datetime.now(timezone.utc)))
    monkeypatch.setattr(eutl_parse, "trust_list_to_registry", lambda xml, certs, registry=None: loaded.append(xml))
    confianza._MEMO.clear()
    state = confianza.eu_registry(settings)
    assert state.registry is not None and state.territories == ["ES"] and loaded == ["<tl-es/>"] and not state.stale
    assert state.missing == ["PT"]  # en la LOTL pero sin lista guardada: el informe lo dice

    async def empty(_settings):
        return "<lotl/>", [], {}, ["todo caído"], ["ES", "FR"]

    monkeypatch.setattr(confianza, "_download", empty)
    # Todo caído: cada país conserva su última lista validada (y se volverá a validar al cargarla).
    carried = confianza.refresh(settings)
    assert carried["carried"] == ["ES", "FR"] and carried["territories"] == ["ES", "FR"]
    assert (tmp_path / carried["version"] / "tl" / "FR.xml").read_text() == "<tl-fr/>"
    assert not confianza.due(settings)
    # Una copia arrastrada de hace más de 7 días ya no vale: ese país queda fuera.
    old_est = tmp_path / carried["version"] / "estado.json"
    data = json.loads(old_est.read_text())
    data["fetched"]["FR"] = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    old_est.write_text(json.dumps(data))
    again = confianza.refresh(settings)
    assert again["carried"] == ["ES"] and again["missing"] == ["FR"]
    folder, summary = tmp_path / again["version"], again

    old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    est = folder / "estado.json"
    est.write_text(est.read_text().replace(summary["refreshed_at"], old))
    confianza._MEMO.clear()
    assert confianza.eu_registry(settings).stale and confianza.due(settings)
    (tmp_path / "actual.json").write_text('{"version": "../../etc"}')
    assert confianza.eu_registry(settings).registry is None
