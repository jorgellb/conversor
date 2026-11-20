"""F4, lote B2b: firmar-pdf con certificado propio (A.6, D-199): firma interrumpida en dos trabajos.

El navegador (PKI.js y WebCrypto) se simula con la clave de la PKI de pruebas: firma los atributos que devuelve la fase
«preparar» como lo haría WebCrypto (RSA PKCS#1 v1.5, o ECDSA en formato r‖s). La TSA, OCSP y CRL, los de certomancer.
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

import pikepdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "fixtures"))

from test_firmas import analyse, arch  # noqa: E402,F401
from test_sello import TSA, _pdf  # noqa: E402
from test_tools import make_ctx, run  # noqa: E402,F401

TOOL = "firmar-pdf"


def _pem(*certs) -> str:
    from asn1crypto import pem

    return "".join(pem.armor("CERTIFICATE", c.dump()).decode() for c in certs)


@pytest.fixture()
def tsa(arch, monkeypatch):
    from certomancer.integrations.aiohttp_illusionist import AsyncIllusionist

    from core.settings import get_settings
    from tools.sign import propio

    monkeypatch.setattr(propio, "open_session", lambda ctx: AsyncIllusionist(arch).serving_session())
    monkeypatch.setattr(get_settings(), "TSA_URL", TSA)


def _browser_sign(arch, label: str, attrs_b64: str) -> str:
    """Lo que hace WebCrypto en la página: firma DER de los atributos; ECDSA sale como r‖s."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    key = serialization.load_der_private_key(arch.key_set.get_private_key(label).dump(), None)
    data = base64.b64decode(attrs_b64)
    if isinstance(key, ec.EllipticCurvePrivateKey):
        r, s = decode_dss_signature(key.sign(data, ec.ECDSA(hashes.SHA256())))
        n = (key.curve.key_size + 7) // 8
        return base64.b64encode(r.to_bytes(n, "big") + s.to_bytes(n, "big")).decode()
    return base64.b64encode(key.sign(data, padding.PKCS1v15(), hashes.SHA256())).decode()


def _stage(ctx):
    from tools.base import Handoff

    with pytest.raises(Handoff) as step:
        run(TOOL, ctx)
    assert (step.value.queue, step.value.stage, step.value.keep_secrets) == ("sign.verify", "propio", False)
    ctx.stage = step.value.stage
    return run(TOOL, ctx)


def _sign(arch, make_ctx, tmp_path, label="signer1", options=None, tamper=None):
    chain = _pem(arch.get_cert(label), arch.get_cert("interm"), arch.get_cert("root"))
    base = {"certificado": "propio", "cadena": chain, **(options or {})}
    out = _stage(make_ctx(TOOL, [_pdf(tmp_path)], {**base, "fase": "preparar"}))
    prepared = Path(out[0]["path"])
    state = json.loads(Path(out[1]["path"]).read_text())
    assert out[0]["name"] == "contrato-preparado.pdf" and out[1]["name"] == "firma-pendiente.json"
    firma = _browser_sign(arch, label, state["attrs"])
    data = prepared.read_bytes()
    if tamper:
        data, state, firma = tamper(data, state, firma)
    second = tmp_path / "contrato-preparado.pdf"
    second.write_bytes(data)
    out = _stage(make_ctx(TOOL, [second], {**base, "fase": "completar", "estado": json.dumps(state), "firma": firma}))
    return out, state


@pytest.mark.parametrize("level", ["B-T", "B-LT"])
def test_own_certificate_two_steps_give_a_valid_pades(arch, make_ctx, tmp_path, tsa, level):
    out, state = _sign(arch, make_ctx, tmp_path, options={"nivel": level})
    assert out[0]["name"] == "contrato-firmado.pdf" and out[0]["note"] == f"Firmado con tu certificado ({level})."
    data = Path(out[0]["path"]).read_bytes()
    [sig] = analyse(data, roots=[arch.get_cert("root")])
    assert sig.field == state["field"] == "Firma1" and sig.level == "propia"
    with pikepdf.open(io.BytesIO(data)) as pdf:
        assert ("/DSS" in pdf.Root) == (level == "B-LT")


def test_ecdsa_and_rsa_keys(arch, make_ctx, tmp_path, tsa):
    """signer1 es P-256 (como un DNIe): WebCrypto da r‖s y el servidor lo pasa a DER. Una CA RSA de la PKI sirve para la
    vía RSA PKCS#1 v1.5 (aquí solo cuenta que la firma sea criptográficamente válida)."""
    _out, state = _sign(arch, make_ctx, tmp_path)
    assert (state["algorithm"], state["curve"]) == ("ECDSA", "P-256")
    chain = _pem(arch.get_cert("interm"), arch.get_cert("root"))
    base = {"certificado": "propio", "cadena": chain, "visible": False}
    out = _stage(make_ctx(TOOL, [_pdf(tmp_path, name="rsa.pdf")], {**base, "fase": "preparar"}))
    state = json.loads(Path(out[1]["path"]).read_text())
    assert state["algorithm"] == "RSASSA-PKCS1-v1_5"
    second = tmp_path / "rsa-preparado.pdf"
    second.write_bytes(Path(out[0]["path"]).read_bytes())
    out = _stage(make_ctx(TOOL, [second], {**base, "fase": "completar", "estado": json.dumps(state),
                                           "firma": _browser_sign(arch, "interm", state["attrs"])}))
    assert out[0]["name"] == "rsa-firmado.pdf"


@pytest.mark.parametrize("what, detail", [
    ("pdf", "own_state_invalid"), ("hueco", "own_state_invalid"), ("firma", "own_signature_invalid"),
])
def test_tampering_is_rejected(arch, make_ctx, tmp_path, tsa, what, detail):
    from core.errors import ToolError

    def tamper(data, state, firma):
        if what == "pdf":
            return data.replace(b"/Type /Page", b"/Type  /Page", 1) if b"/Type /Page" in data else data[:-5] + b"xx\n%%EOF\n"[:5], state, firma
        if what == "hueco":
            return data, {**state, "start": state["start"] + 2}, firma
        raw = bytearray(base64.b64decode(firma))
        raw[10] ^= 0xFF
        return data, state, base64.b64encode(bytes(raw)).decode()

    with pytest.raises(ToolError) as err:
        _sign(arch, make_ctx, tmp_path, tamper=tamper)
    assert err.value.detail == detail


def test_own_certificate_needs_a_chain_and_no_account(arch, make_ctx, tmp_path):
    from core.errors import ToolError
    from tools.sign import firmar

    firmar.precheck(None, None, "anon", {"certificado": "propio"}, [_pdf(tmp_path)])  # sin cuenta ni sello
    with pytest.raises(ToolError) as err:
        _stage(make_ctx(TOOL, [_pdf(tmp_path)], {"certificado": "propio", "cadena": "no es un PEM", "fase": "preparar"}))
    assert err.value.detail == "own_chain_invalid"


def test_p1363_signature_starting_with_0x30_is_not_taken_for_der(arch):
    """1 de cada 256 firmas ECDSA en r‖s empiezan por 0x30 (el byte de SEQUENCE en DER)."""
    from asn1crypto import algos

    from tools.sign.propio import _signature_value

    cert = arch.get_cert("signer1")
    raw = b"\x30" + b"\x11" * 31 + b"\x22" * 32
    assert algos.DSASignature.load(_signature_value(cert, raw)).to_p1363() == raw



def test_second_own_signature_and_encrypted_input(arch, make_ctx, tmp_path, tsa):
    """Dos firmantes seguidos (Firma1 y Firma2) y un PDF con solo contraseña de propietario (D-201)."""
    out, _ = _sign(arch, make_ctx, tmp_path)
    first = tmp_path / "uno.pdf"
    first.write_bytes(Path(out[0]["path"]).read_bytes())
    chain = _pem(arch.get_cert("signer1"), arch.get_cert("interm"), arch.get_cert("root"))
    base = {"certificado": "propio", "cadena": chain}
    prep = _stage(make_ctx(TOOL, [first], {**base, "fase": "preparar"}))
    state = json.loads(Path(prep[1]["path"]).read_text())
    assert state["field"] == "Firma2"
    enc = tmp_path / "cifrado.pdf"
    with pikepdf.open(_pdf(tmp_path, name="c.pdf")) as pdf:
        pdf.save(enc, encryption=pikepdf.Encryption(owner="dueno", user="", R=6))
    prep = _stage(make_ctx(TOOL, [enc], {**base, "fase": "preparar", "nivel": "B-LT"}))
    state = json.loads(Path(prep[1]["path"]).read_text())
    second = tmp_path / "cifrado-preparado.pdf"
    second.write_bytes(Path(prep[0]["path"]).read_bytes())
    done = _stage(make_ctx(TOOL, [second], {**base, "fase": "completar", "nivel": "B-LT", "estado": json.dumps(state),
                                            "firma": _browser_sign(arch, "signer1", state["attrs"])}))
    assert done[0]["note"] == "Firmado con tu certificado (B-LT)."


def test_certificate_without_signing_key_usage_is_rejected():
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    from core.errors import ToolError
    from tools.sign.propio import load_chain

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Solo cifrar")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(1)
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=True, data_encipherment=False,
                                         key_agreement=True, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256()))
    with pytest.raises(ToolError) as err:
        load_chain(cert.public_bytes(serialization.Encoding.PEM).decode())
    assert err.value.detail == "own_key_usage"
