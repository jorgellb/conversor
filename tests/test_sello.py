"""F4, lote A2: firmar-pdf con el sello de la plataforma (A.6 y 10).

El firmante PKCS#11 (SoftHSM2) se sustituye por uno con clave en archivo de la PKI de pruebas, salvo en
`test_dev_token_and_pkcs11_signer`, que necesita `softhsm2-util` (CI). La TSA, el OCSP y la CRL son los del «illusionist»
de certomancer, sin red; cada resultado se comprueba con la propia verificación de verificar-firmas-pdf.
"""
from __future__ import annotations

import asyncio
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pikepdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "fixtures"))

from test_firmas import _signer, arch, analyse  # noqa: E402,F401 - fixtures compartidas
from test_tools import make_ctx, run  # noqa: E402,F401

TOOL = "firmar-pdf"
TSA = "http://certomancer.test/conversor-pruebas/tsa/tsa"


def _pdf(tmp_path: Path, pages: int = 2, name: str = "contrato.pdf") -> Path:
    pdf = pikepdf.new()
    for _ in range(pages):
        pdf.add_blank_page(page_size=(595, 842))
    path = tmp_path / name
    pdf.save(path)
    return path


def _chain(arch):
    return [arch.get_cert("seal"), arch.get_cert("interm"), arch.get_cert("root")]


def _seal(arch, make_ctx, src: Path, options: dict | None = None, locale: str = "es", chain=None, tsa_arch=None) -> bytes:
    """`prepare` y `_sign` con el firmante de archivo y la PKI de certomancer servida en el proceso (`tsa_arch`: otra
    PKI para la TSA, con otra raíz)."""
    from certomancer.integrations.aiohttp_illusionist import AsyncIllusionist
    from pyhanko.sign.timestamps import HTTPTimeStamper

    from core.settings import get_settings
    from tools.sign import firmar

    ctx = make_ctx(TOOL, [src], options or {})
    ctx.locale = locale
    ctx.settings = get_settings().model_copy(update={"TSA_URL": TSA})
    item = firmar.prepare(ctx, ctx.inputs[0].path, ctx.inputs[0].name)

    async def go():
        async with AsyncIllusionist(arch).serving_session() as session:
            if tsa_arch is None:
                tsa_session = session
                return await firmar._sign(ctx, item, _signer(arch, "seal"), chain or _chain(arch), session,
                                          HTTPTimeStamper(TSA, session=tsa_session))
            async with AsyncIllusionist(tsa_arch).serving_session() as tsa_session:
                return await firmar._sign(ctx, item, _signer(arch, "seal"), chain or _chain(arch), session,
                                          HTTPTimeStamper(TSA, session=tsa_session))

    data = asyncio.run(go())
    asyncio.run(firmar.check_output(data, chain or _chain(arch)))
    return data


@pytest.mark.parametrize("level", ["B-T", "B-LT", "B-LTA"])
def test_pades_levels_verified_by_pyhanko(arch, make_ctx, tmp_path, level):
    data = _seal(arch, make_ctx, _pdf(tmp_path), {"nivel": level, "motivo": "Conformidad", "lugar": "Madrid"})
    items = analyse(data, roots=[arch.get_cert("root"), arch.get_cert("seal")])
    seal = items[0]
    assert (seal.kind, seal.level, seal.intact, seal.valid, seal.pades) == ("firma", "plataforma", True, True, level)
    assert (seal.reason, seal.location, seal.when_source, seal.tsa) == ("Conformidad", "Madrid", "tsa", "TSA de pruebas")
    if level == "B-LTA":
        assert items[-1].kind == "sello_tiempo" and items[-1].tst_ok


def test_visible_box_on_chosen_page_and_corner(arch, make_ctx, tmp_path):
    data = _seal(arch, make_ctx, _pdf(tmp_path, pages=3), {"pagina": "1", "posicion": "arriba_izquierda", "nombre": "Conversor"})
    with pikepdf.open(io.BytesIO(data)) as pdf:
        annots = [a for p in pdf.pages for a in (p.obj.get("/Annots") or [])]
        widget = next(a for a in annots if a.get("/FT") == "/Sig")
        assert pdf.pages[0].obj.get("/Annots") is not None and not pdf.pages[2].obj.get("/Annots")
        x0, y0, x1, y1 = (float(v) for v in widget.Rect)
        assert x0 == 36 and y1 == 842 - 36 and x1 - x0 == 210 and "/AP" in widget
        assert widget.get("/T") == "Sello1"
    invisible = _seal(arch, make_ctx, _pdf(tmp_path, name="b.pdf"), {"visible": False})
    with pikepdf.open(io.BytesIO(invisible)) as pdf:
        widget = next(a for p in pdf.pages for a in (p.obj.get("/Annots") or []) if a.get("/FT") == "/Sig")
        assert [float(v) for v in widget.Rect] == [0, 0, 0, 0]


def test_certification_docmdp_is_detected_and_enforced(arch, make_ctx, tmp_path):
    data = _seal(arch, make_ctx, _pdf(tmp_path), {"certificacion": "sin_cambios"})
    [seal] = analyse(data, roots=[arch.get_cert("root")])
    assert seal.certified == "sin_cambios" and seal.level == "propia"


def test_second_seal_gets_a_new_field_and_both_stay_valid(arch, make_ctx, tmp_path):
    first = tmp_path / "uno.pdf"
    first.write_bytes(_seal(arch, make_ctx, _pdf(tmp_path)))
    items = analyse(_seal(arch, make_ctx, first), roots=[arch.get_cert("root")])
    assert [s.field for s in items] == ["Sello1", "Sello2"] and all(s.level == "propia" for s in items)
    assert items[0].changes == "formularios" and items[0].changes_ok


def test_without_timestamp_is_b_b_and_needs_no_tsa(arch, make_ctx, tmp_path):
    from tools.sign import firmar

    ctx = make_ctx(TOOL, [_pdf(tmp_path)], {"sello_tiempo": False})
    item = firmar.prepare(ctx, ctx.inputs[0].path, ctx.inputs[0].name)

    async def go():
        return await firmar._sign(ctx, item, _signer(arch, "seal"), _chain(arch), None, None)

    [seal] = analyse(asyncio.run(go()), roots=[arch.get_cert("root")])
    assert seal.pades == "B-B" and seal.when_source == "declarada"


def test_options_and_errors(arch, make_ctx, tmp_path, monkeypatch):
    from core.errors import AppError, ToolError
    from core.registry import load_registry
    from core.settings import get_settings
    from tools.sign import firmar

    spec = load_registry().require(TOOL)
    assert spec.queue == "sign" and spec.category == "sign" and spec.default_enabled is False and spec.ai is None
    defaults = spec.options().model_dump()
    assert defaults == {"certificado": "plataforma", "visible": True, "pagina": "ultima", "posicion": "abajo_derecha",
                        "campo": "", "nombre": "", "motivo": "", "lugar": "", "sello_tiempo": True, "nivel": "B-T", "certificacion": "no"}
    settings = get_settings()
    with pytest.raises(AppError) as err:
        firmar.precheck(settings, None, "anon", {}, [])
    assert (err.value.code, err.value.detail) == ("UNAUTHORIZED", "seal_account")
    with pytest.raises(AppError) as err:
        firmar.precheck(settings.model_copy(update={"SEAL_ENABLED": False}), None, "user", {}, [])
    assert err.value.detail == "seal_disabled"
    monkeypatch.setattr(firmar, "seals_today", lambda: 0)
    firmar.precheck(settings, None, "user", {}, [])
    monkeypatch.setattr(firmar, "seals_today", lambda: settings.SEAL_DAILY_LIMIT)
    with pytest.raises(AppError) as err:
        firmar.precheck(settings, None, "user", {}, [tmp_path / "x"]) if (tmp_path / "x").write_bytes(b"%PDF") else None
    assert err.value.detail == "seal_limit"

    ctx = make_ctx(TOOL, [_pdf(tmp_path)])
    ctx.owner = ("user", "u1")
    ctx.settings = settings.model_copy(update={"TSA_URL": TSA})
    monkeypatch.setattr(firmar, "seals_today", lambda: settings.SEAL_DAILY_LIMIT)
    with pytest.raises(ToolError) as err:
        run(TOOL, ctx)
    assert (err.value.code, err.value.detail) == ("QUOTA_EXCEEDED", "seal_limit")
    monkeypatch.setattr(firmar, "seals_today", lambda: 0)
    monkeypatch.setattr(firmar, "reserve_account", lambda *a: None)
    monkeypatch.setattr(firmar, "release_account", lambda *a: None)
    ctx.settings = settings.model_copy(update={"SIGN_PKCS11_PIN": "", "SIGN_CERT_PATH": "", "TSA_URL": TSA})
    with pytest.raises(ToolError) as err:
        run(TOOL, ctx)
    assert err.value.detail == "seal_config"
    with pytest.raises(ToolError) as err:
        firmar.prepare(make_ctx(TOOL, [_pdf(tmp_path, name="p.pdf")], {"pagina": "9"}), tmp_path / "p.pdf", "p.pdf")
    assert err.value.code == "INVALID_OPTIONS"
    no_tsa = make_ctx(TOOL, [_pdf(tmp_path, name="c.pdf")])
    no_tsa.owner = ("user", "u1")
    no_tsa.settings = settings.model_copy(update={"TSA_URL": ""})
    with pytest.raises(ToolError) as err:
        run(TOOL, no_tsa)
    assert err.value.detail == "seal_config"  # falta de configuración, no «vuelve a probar»


@pytest.mark.integration
def test_run_records_each_seal(arch, make_ctx, tmp_path, monkeypatch, services):
    """Cada uso del sello queda en seal_signatures con el SHA-256 del resultado (10 y 9.4), y cuenta para el límite."""
    import hashlib
    from contextlib import contextmanager

    from core.db import session_scope
    from core.models import SealSignature
    from tools.sign import firmar

    @contextmanager
    def file_signer(_settings):
        yield _signer(arch, "seal"), _chain(arch)

    monkeypatch.setattr(firmar, "seal_signer", file_signer)
    before = firmar.seals_today()
    ctx = make_ctx(TOOL, [_pdf(tmp_path), _pdf(tmp_path, name="otro.pdf")], {"sello_tiempo": False})
    ctx.owner = ("user", "u1")
    out = run(TOOL, ctx)
    assert [o["name"] for o in out] == ["contrato-sellado.pdf", "otro-sellado.pdf", "documentos-sellados.zip"]
    assert out[0]["note"] == "Sellado con el sello de la plataforma (B-B). No es una firma cualificada."
    assert firmar.seals_today() == before + 2
    digest = hashlib.sha256(Path(out[0]["path"]).read_bytes()).hexdigest()
    with session_scope() as s:
        row = s.query(SealSignature).filter_by(document_sha256=digest).one()
        assert (str(row.job_id), row.level) == (ctx.job_id, "B-B")


@pytest.mark.skipif(shutil.which("softhsm2-util") is None, reason="SoftHSM2 no instalado: job python de la CI")
def test_dev_token_and_pkcs11_signer(tmp_path, monkeypatch):
    """infra/sign/dev_token.py crea el token, la clave dentro y un certificado autofirmado; seal_signer firma con él."""
    from types import SimpleNamespace

    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    from tools.sign import firmar

    conf = tmp_path / "softhsm2.conf"
    (tmp_path / "tokens").mkdir()
    conf.write_text(f"directories.tokendir = {tmp_path / 'tokens'}\nobjectstore.backend = file\n")
    module = next(p for p in ("/usr/lib/softhsm/libsofthsm2.so", "/usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so") if os.path.exists(p))
    env = {**os.environ, "SOFTHSM2_CONF": str(conf), "SIGN_PKCS11_MODULE": module, "SIGN_PKCS11_PIN": "1234-dev"}
    cert = tmp_path / "sello.pem"
    root = Path(__file__).resolve().parents[1]
    for _ in range(2):  # la segunda vez no cambia nada (idempotente)
        proc = subprocess.run([sys.executable, str(root / "infra" / "sign" / "dev_token.py"), str(cert)], env=env,
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr[-2000:]
    monkeypatch.setenv("SOFTHSM2_CONF", str(conf))
    settings = SimpleNamespace(SIGN_PKCS11_MODULE=module, SIGN_PKCS11_TOKEN_LABEL="conversor-sello", SIGN_PKCS11_KEY_LABEL="sello",
                               SIGN_PKCS11_PIN="1234-dev", SIGN_CERT_PATH=str(cert))
    pdf = pikepdf.new()
    pdf.add_blank_page()
    buf = io.BytesIO()
    pdf.save(buf)
    with firmar.seal_signer(settings) as (signer, chain):
        data = signers.sign_pdf(IncrementalPdfFileWriter(io.BytesIO(buf.getvalue())),
                                signers.PdfSignatureMetadata(field_name="Sello1", subfilter=fields.SigSeedSubFilter.PADES),
                                signer=signer).getvalue()
    [s] = analyse(data, roots=chain)
    assert s.intact and s.valid and s.level == "plataforma" and s.signer == "Sello de desarrollo (autofirmado)"
    from core.errors import ToolError

    with pytest.raises(ToolError) as err:
        with firmar.seal_signer(SimpleNamespace(**{**vars(settings), "SIGN_PKCS11_PIN": "mal"})):
            pass
    assert err.value.detail == "seal_config"


def test_tsa_under_another_root_still_gets_b_lt(arch, make_ctx, tmp_path, tmp_path_factory):
    """La TSA no tiene por qué compartir la raíz del sello: sus raíces salen de su propia respuesta."""
    import pki

    other = pki.load(tmp_path_factory.mktemp("pki-tsa"))
    data = _seal(arch, make_ctx, _pdf(tmp_path), {"nivel": "B-LT"}, tsa_arch=other)
    [seal] = analyse(data, roots=[arch.get_cert("root"), other.get_cert("root"), arch.get_cert("seal")])
    assert seal.level == "plataforma" and seal.pades == "B-LT" and seal.when_source == "tsa"


def test_chain_without_root_is_a_configuration_error(arch, tmp_path):
    from asn1crypto import pem

    from core.errors import ToolError
    from tools.sign import firmar

    path = tmp_path / "sin-raiz.pem"
    path.write_bytes(b"".join(pem.armor("CERTIFICATE", arch.get_cert(c).dump()) for c in ("seal", "interm")))
    with pytest.raises(ToolError) as err:
        firmar.load_chain(str(path))
    assert err.value.detail == "seal_config"
    inline = b"".join(pem.armor("CERTIFICATE", arch.get_cert(c).dump()) for c in ("seal", "interm", "root")).decode()
    assert len(firmar.load_chain(inline)) == 3  # también el PEM en la propia variable


def test_stamp_shows_the_certificate_holder_and_wraps_user_text(make_ctx, tmp_path):
    from tools.sign import firmar

    ctx = make_ctx(TOOL, [_pdf(tmp_path)], {"nombre": "Agencia Tributaria", "motivo": "x" * 200, "lugar": "Madrid 100%"})
    text = firmar.stamp_text(ctx)
    lines = text.split("\n")
    assert lines[0] == "Sellado por: %(signer)s"  # el titular del certificado, nunca el nombre escrito
    assert "Nombre indicado (sin verificar): Agencia Tributaria" in " ".join(lines)
    assert all(len(line) <= firmar.WRAP + 1 for line in lines[2:-1]) and "Lugar: Madrid 100%%" in lines


def test_visible_box_follows_rotation_and_cropbox():
    from tools.sign.firmar import visual_box

    assert visual_box([0, 0, 595, 842], 0, "abajo_derecha") == (595 - 36 - 210, 36, 595 - 36, 36 + 72)
    x0, y0, x1, y1 = visual_box([0, 0, 595, 842], 90, "abajo_derecha")  # vista apaisada de 842 × 595
    assert (x1 - x0, y1 - y0) == (72, 210) and x0 >= 0 and y1 <= 842
    assert visual_box([10, 20, 605, 862], 0, "arriba_izquierda") == (46, 862 - 36 - 72, 46 + 210, 862 - 36)


def test_certification_rules(arch, make_ctx, tmp_path):
    from core.errors import ToolError
    from tools.sign import firmar

    locked = tmp_path / "bloqueado.pdf"
    locked.write_bytes(_seal(arch, make_ctx, _pdf(tmp_path), {"certificacion": "sin_cambios"}))
    with pytest.raises(ToolError) as err:
        firmar.prepare(make_ctx(TOOL, [locked]), locked, "b.pdf")
    assert err.value.detail == "seal_locked"
    signed = tmp_path / "firmado.pdf"
    signed.write_bytes(_seal(arch, make_ctx, _pdf(tmp_path, name="d.pdf")))
    with pytest.raises(ToolError) as err:
        firmar.prepare(make_ctx(TOOL, [signed], {"certificacion": "formularios"}), signed, "f.pdf")
    assert err.value.detail == "seal_certify_signed"
    lta = tmp_path / "lta.pdf"
    lta.write_bytes(_seal(arch, make_ctx, _pdf(tmp_path, name="e.pdf"), {"nivel": "B-LTA"}))
    with pytest.raises(ToolError) as err:
        firmar.prepare(make_ctx(TOOL, [lta], {"nivel": "B-LTA"}), lta, "l.pdf")
    assert err.value.detail == "seal_lta_existing"


def test_output_check_rejects_a_certificate_that_is_not_the_key(arch, make_ctx, tmp_path):
    """Si el certificado de SIGN_CERT_PATH no casa con la clave, el resultado no se entrega ni se anota."""
    from core.errors import ToolError
    from tools.sign import firmar

    ctx = make_ctx(TOOL, [_pdf(tmp_path)], {"sello_tiempo": False})
    item = firmar.prepare(ctx, ctx.inputs[0].path, ctx.inputs[0].name)
    wrong = [arch.get_cert("signer1"), arch.get_cert("interm"), arch.get_cert("root")]
    from pyhanko.sign import signers

    from pyhanko_certvalidator.registry import SimpleCertificateStore

    mismatched = signers.SimpleSigner(signing_cert=wrong[0], signing_key=arch.key_set.get_private_key("seal"),
                                      cert_registry=SimpleCertificateStore.from_certs(wrong[1:]))
    data = asyncio.run(firmar._sign(ctx, item, mismatched, wrong, None, None))
    with pytest.raises(ToolError) as err:
        asyncio.run(firmar.check_output(data, wrong))
    assert err.value.detail == "seal_invalid"


def test_seal_into_an_empty_field_made_by_hacer_pdf_rellenable(arch, make_ctx, tmp_path):
    """A.3: los campos de firma de hacer-pdf-rellenable se firman con firmar-pdf (campo, D-196)."""
    from core.errors import ToolError
    from test_tools import run

    tool = "hacer-pdf-rellenable"
    form = run(tool, make_ctx(tool, [_pdf(tmp_path, name="ficha.pdf")], {"firmas": [
        {"nombre": "Firma cliente", "pagina": 2, "x1": 300, "y1": 100, "x2": 500, "y2": 160}]}))[0]["path"]
    data = _seal(arch, make_ctx, Path(form), {"campo": "Firma cliente"})
    [seal] = analyse(data, roots=[arch.get_cert("root")])
    assert seal.field == "Firma cliente" and seal.level == "propia"
    with pikepdf.open(io.BytesIO(data)) as pdf:
        widget = next(a for a in (pdf.pages[1].obj.get("/Annots") or []) if a.get("/FT") == "/Sig")
        assert [round(float(v)) for v in widget.Rect] == [300, 100, 500, 160] and "/AP" in widget
    signed = tmp_path / "firmado.pdf"
    signed.write_bytes(data)
    for name, detail in (("Firma cliente", "seal_field_signed"), ("No existe", "seal_field_missing")):
        with pytest.raises(ToolError) as err:
            _seal(arch, make_ctx, signed, {"campo": name})
        assert err.value.detail == detail
