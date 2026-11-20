"""F6-G (7.13, D-219): csig-a-pdf, p7m-a-pdf, xsig-a-pdf y verificar-firma con la PKI de pruebas de certomancer.

16.5: el documento extraído de un .csig o .p7m coincide byte a byte con el original y verificar-firma detecta un documento
alterado. La lista de la UE se deja vacía y la raíz de pruebas se añade con SIGN_VERIFY_EXTRA_ROOTS (nivel «propia»).
"""
from __future__ import annotations

import asyncio
import base64

import sys
from pathlib import Path

import pytest

from core.errors import ToolError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "fixtures"))

from test_firmas import _blank, _signer, _tsa, arch  # noqa: E402,F401 - fixtures compartidas
from test_tools import make_ctx, run  # noqa: E402,F401

pytest.importorskip("signxml")


def _cms(arch, data: bytes | None, detached: bool = False, who: str = "signer1", timestamp: bool = False, payload=None) -> bytes:
    signer = _signer(arch, who)
    info = asyncio.run(signer.async_sign_general_data(payload if payload is not None else data, "sha256", detached=detached,
                                                      use_cades=True, timestamper=_tsa(arch) if timestamp else None))
    return info.dump()


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.fixture
def own_root(arch, tmp_path, monkeypatch):
    from asn1crypto import pem

    from core.settings import get_settings

    roots = tmp_path / "raiz.pem"
    roots.write_bytes(pem.armor("CERTIFICATE", arch.get_cert("root").dump()))
    monkeypatch.setattr(get_settings(), "SIGN_VERIFY_EXTRA_ROOTS", str(roots))
    monkeypatch.setattr(get_settings(), "EUTL_CACHE_PATH", tmp_path / "sin-lista")


def _report(out) -> str:
    return Path(out[0]["path"]).read_text(encoding="utf-8")


# --- Extraer --------------------------------------------------------------------------------------------------------


def test_csig_and_nested_p7m_give_the_original_byte_for_byte(make_ctx, arch, tmp_path):
    pdf = _blank(2)
    csig = _write(tmp_path, "contrato.pdf.csig", _cms(arch, pdf))
    out = run("csig-a-pdf", make_ctx("csig-a-pdf", [csig]))
    assert out[0]["name"] == "contrato.pdf" and Path(out[0]["path"]).read_bytes() == pdf
    assert out[0]["note"].startswith("Firmado por ") and "Verificar firma" in out[0]["note"]
    twice = _write(tmp_path, "contrato.pdf.p7m", _cms(arch, csig.read_bytes(), who="signer2"))
    out = run("p7m-a-pdf", make_ctx("p7m-a-pdf", [twice]))
    assert Path(out[0]["path"]).read_bytes() == pdf and "firmado 2 veces" in out[0]["note"].lower()


def test_pem_base64_and_non_pdf_content(make_ctx, arch, tmp_path):
    from asn1crypto import pem

    der = _cms(arch, b"PK\x03\x04 no es un docx de verdad, pero va firmado")
    for name, data in (("aviso.p7m", pem.armor("PKCS7", der)), ("aviso2.p7m", base64.encodebytes(der))):
        out = run("p7m-a-pdf", make_ctx("p7m-a-pdf", [_write(tmp_path, name, data)]))
        assert Path(out[0]["path"]).read_bytes().startswith(b"PK\x03\x04") and "no es un PDF" in out[0]["note"]
    docx = _write(tmp_path, "carta.docx.p7m", der)
    assert run("p7m-a-pdf", make_ctx("p7m-a-pdf", [docx]))[0]["name"] == "carta.docx"


def test_detached_and_garbage(make_ctx, arch, tmp_path):
    with pytest.raises(ToolError) as err:
        run("p7m-a-pdf", make_ctx("p7m-a-pdf", [_write(tmp_path, "sep.p7s", _cms(arch, b"hola", detached=True))]))
    assert err.value.detail == "cms_detached"
    with pytest.raises(ToolError) as err:
        run("csig-a-pdf", make_ctx("csig-a-pdf", [_write(tmp_path, "roto.csig", b"\x30\x82\x01\x00" + bytes(256))]))
    assert err.value.code == "CORRUPT_FILE"


def _xades_enveloping(content: bytes) -> bytes:
    """Una .xsig como las de AutoFirma (el documento en un ds:Object en Base64); para extraer no hace falta que la firma
    sea válida."""
    b64 = base64.b64encode(content).decode()
    return (f'<?xml version="1.0" encoding="UTF-8"?><ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="Sig">'
            '<ds:SignedInfo><ds:Reference URI="#Obj"><ds:DigestValue>x</ds:DigestValue></ds:Reference>'
            '<ds:Reference Type="http://uri.etsi.org/01903#SignedProperties" URI="#Props"/></ds:SignedInfo>'
            f'<ds:Object Id="Obj" MimeType="application/pdf" Encoding="http://www.w3.org/2000/09/xmldsig#base64">{b64}</ds:Object>'
            '</ds:Signature>').encode()


def test_xsig_enveloping_base64(make_ctx, tmp_path):
    pdf = _blank()
    out = run("xsig-a-pdf", make_ctx("xsig-a-pdf", [_write(tmp_path, "solicitud.pdf.xsig", _xades_enveloping(pdf))]))
    assert out[0]["name"] == "solicitud.pdf" and Path(out[0]["path"]).read_bytes() == pdf


def _signed_xml(arch, xml: bytes) -> bytes:
    from asn1crypto import pem
    from lxml import etree
    from signxml import methods
    from signxml.xades import XAdESSigner

    key = pem.armor("PRIVATE KEY", arch.key_set.get_private_key("signer1").dump())
    certs = [pem.armor("CERTIFICATE", arch.get_cert(c).dump()).decode() for c in ("signer1", "interm")]
    from signxml import SignatureMethod

    signed = XAdESSigner(method=methods.enveloped, signature_algorithm=SignatureMethod.ECDSA_SHA256).sign(
        etree.fromstring(xml), key=key, cert=certs)
    return etree.tostring(signed, xml_declaration=True, encoding="UTF-8")


def test_enveloped_xml_without_its_signature(make_ctx, arch, tmp_path):
    signed = _signed_xml(arch, b"<Factura><Importe>100.00</Importe></Factura>")
    out = run("xsig-a-pdf", make_ctx("xsig-a-pdf", [_write(tmp_path, "factura.xml", signed)]))
    data = Path(out[0]["path"]).read_bytes()
    assert out[0]["name"] == "factura.xml" and b"<Importe>100.00</Importe>" in data and b"Signature" not in data


# --- Verificar ---------------------------------------------------------------------------------------------------------


def test_verify_cades_attached_and_altered(make_ctx, arch, tmp_path, own_root):
    pdf = _blank()
    der = _cms(arch, pdf, timestamp=True)
    out = run("verificar-firma", make_ctx("verificar-firma", [_write(tmp_path, "doc.pdf.csig", der)]))
    page = _report(out)
    assert "De confianza por una raíz añadida" in page and "CAdES-T" in page and "1 firma(s): 1 válida(s)" in out[0]["note"]
    altered = der.replace(pdf[-40:], pdf[-40:-1] + b"X")
    assert altered != der
    out = run("verificar-firma", make_ctx("verificar-firma", [_write(tmp_path, "alterado.csig", altered)]))
    assert "No válida" in _report(out) and "0 válida(s)" in out[0]["note"]


def test_verify_detached_with_its_document(make_ctx, arch, tmp_path, own_root):
    doc = b"Acta de la junta del 20 de noviembre."
    sig = _write(tmp_path, "acta.txt.p7s", _cms(arch, doc, detached=True))
    out = run("verificar-firma", make_ctx("verificar-firma", [sig, _write(tmp_path, "acta.txt", doc)]))
    assert "1 válida(s)" in out[0]["note"]
    out = run("verificar-firma", make_ctx("verificar-firma", [sig, _write(tmp_path, "acta2.txt", doc + b" Cambiada.")]))
    assert "0 válida(s)" in out[0]["note"]
    with pytest.raises(ToolError) as err:
        run("verificar-firma", make_ctx("verificar-firma", [sig]))
    assert err.value.detail == "cms_detached_needs_original"


def test_verify_co_signatures_each_one(make_ctx, arch, tmp_path, own_root):
    from asn1crypto import cms

    doc = b"Convenio firmado por dos partes."
    a = cms.ContentInfo.load(_cms(arch, doc))
    b = cms.ContentInfo.load(_cms(arch, doc, who="signer2"))
    signed = a["content"]
    certs = list(signed["certificates"]) + [c for c in b["content"]["certificates"] if c.dump() not in {x.dump() for x in signed["certificates"]}]
    both = cms.ContentInfo({"content_type": "signed_data", "content": cms.SignedData({
        "version": signed["version"], "digest_algorithms": signed["digest_algorithms"], "encap_content_info": signed["encap_content_info"],
        "certificates": certs, "signer_infos": list(signed["signer_infos"]) + list(b["content"]["signer_infos"])})})
    out = run("verificar-firma", make_ctx("verificar-firma", [_write(tmp_path, "convenio.csig", both.dump())]))
    assert "2 firma(s): 2 válida(s)" in out[0]["note"] and "CAdES 2" in _report(out)


def test_verify_xades_and_tampered_xml(make_ctx, arch, tmp_path, own_root):
    signed = _signed_xml(arch, b"<Factura><Importe>100.00</Importe></Factura>")
    out = run("verificar-firma", make_ctx("verificar-firma", [_write(tmp_path, "f.xml", signed)]))
    assert "1 válida(s)" in out[0]["note"] and "XAdES-B" in _report(out)
    tampered = signed.replace(b"100.00", b"900.00")
    out = run("verificar-firma", make_ctx("verificar-firma", [_write(tmp_path, "g.xml", tampered)]))
    assert "0 válida(s)" in out[0]["note"] and "No válida" in _report(out)


def test_verify_untrusted_chain_is_simple(make_ctx, arch, tmp_path, monkeypatch):
    from core.settings import get_settings

    monkeypatch.setattr(get_settings(), "SIGN_VERIFY_EXTRA_ROOTS", "")
    monkeypatch.setattr(get_settings(), "EUTL_CACHE_PATH", tmp_path / "sin-lista")
    out = run("verificar-firma", make_ctx("verificar-firma", [_write(tmp_path, "d.p7m", _cms(arch, b"hola"))]))
    page = _report(out)
    assert "0 válida(s)" in out[0]["note"] and "El documento no ha cambiado desde la firma." in page


def test_verify_pdf_goes_to_the_pdf_analysis(make_ctx, arch, tmp_path, own_root):
    from test_firmas import sign

    out = run("verificar-firma", make_ctx("verificar-firma", [_write(tmp_path, "a.pdf", sign(arch, _blank()))]))
    assert "Nivel PAdES" in _report(out)


def test_verify_two_files_need_one_signature(make_ctx, tmp_path):
    with pytest.raises(ToolError) as err:
        run("verificar-firma", make_ctx("verificar-firma", [_write(tmp_path, "a.txt", b"a"), _write(tmp_path, "b.txt", b"b")]))
    assert err.value.detail == "verify_two_files"


def test_xades_xxe_rejected(make_ctx, tmp_path):
    xxe = (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/hostname">]>'
           b'<r xmlns:ds="http://www.w3.org/2000/09/xmldsig#">&x;<ds:Signature/></r>')
    for tool in ("xsig-a-pdf", "verificar-firma"):
        with pytest.raises(ToolError) as err:
            run(tool, make_ctx(tool, [_write(tmp_path, "x.xsig", xxe)]))
        assert err.value.detail == "xml_entities"



# --- Revisión de F6-G (D-222) -----------------------------------------------------------------------------------------


def _signer_kwargs(arch):
    from asn1crypto import pem
    from signxml import SignatureMethod

    key = pem.armor("PRIVATE KEY", arch.key_set.get_private_key("signer1").dump())
    certs = [pem.armor("CERTIFICATE", arch.get_cert(c).dump()).decode() for c in ("signer1", "interm")]
    return {"key": key, "cert": certs}, SignatureMethod.ECDSA_SHA256


def _afirma(arch, pdf: bytes) -> bytes:
    """Firma «internally detached» de AutoFirma: el documento en CONTENT y la firma a su lado, válida de verdad."""
    from lxml import etree
    from signxml import methods
    from signxml.xades import XAdESSigner

    kwargs, alg = _signer_kwargs(arch)
    root = etree.fromstring(f'<AFIRMA><CONTENT Id="CONTENT-1" Encoding="base64">{base64.b64encode(pdf).decode()}</CONTENT></AFIRMA>'.encode())
    sig = XAdESSigner(method=methods.detached, signature_algorithm=alg).sign(root, reference_uri="#CONTENT-1", **kwargs)
    root.append(sig)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def test_real_cms_with_a_pdf_inside_is_detected_as_a_signature(arch, tmp_path):
    from core.filetype import detect, matches

    path = _write(tmp_path, "contrato.pdf.csig", _cms(arch, _blank()))
    found = detect(path, "csig")
    assert found.ext == "csig" and matches(found, "csig", ("csig", "p7m", "p7s"))


def test_afirma_extraction_and_verification(make_ctx, arch, tmp_path, own_root):
    pdf = _blank()
    xsig = _write(tmp_path, "s.pdf.xsig", _afirma(arch, pdf))
    out = run("xsig-a-pdf", make_ctx("xsig-a-pdf", [xsig]))
    assert Path(out[0]["path"]).read_bytes() == pdf and "comprobar" not in out[0]["note"].split(".")[0]
    assert "1 válida(s)" in run("verificar-firma", make_ctx("verificar-firma", [xsig]))[0]["note"]


def test_duplicate_ids_wrapping_is_refused(make_ctx, arch, tmp_path, own_root):
    evil = base64.b64encode(b"%PDF-1.4 EVIL").decode()
    raw = _afirma(arch, _blank()).replace(b"</AFIRMA>", f'<CONTENT id="CONTENT-1" Encoding="base64">{evil}</CONTENT></AFIRMA>'.encode())
    path = _write(tmp_path, "w.xsig", raw)
    with pytest.raises(ToolError) as err:
        run("xsig-a-pdf", make_ctx("xsig-a-pdf", [path]))
    assert err.value.detail == "xades_duplicate_ids"
    out = run("verificar-firma", make_ctx("verificar-firma", [path]))
    assert "0 válida(s)" in out[0]["note"] and "repite identificadores" in _report(out)


def test_injected_signature_breaks_the_real_one(make_ctx, arch, tmp_path, own_root):
    signed = _signed_xml(arch, b"<Factura><Importe>100.00</Importe></Factura>")
    injected = signed.replace(b"<Factura>", b'<Factura><ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#"><Importe>999999.00</Importe></ds:Signature>', 1)
    out = run("verificar-firma", make_ctx("verificar-firma", [_write(tmp_path, "i.xml", injected)]))
    assert "0 válida(s)" in out[0]["note"]
    fake = signed.replace(b"</Factura>", b'<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#"><ds:SignedInfo>'
                          b'<ds:Reference URI="#e"/></ds:SignedInfo><ds:Object Id="e" Encoding="base64">JVBERi0xLjQgRVZJTA==</ds:Object>'
                          b'</ds:Signature></Factura>')
    out = run("xsig-a-pdf", make_ctx("xsig-a-pdf", [_write(tmp_path, "f.xml", fake)]))
    assert b"EVIL" not in Path(out[0]["path"]).read_bytes()


def test_partial_reference_is_not_valid(make_ctx, arch, tmp_path, own_root):
    from lxml import etree
    from signxml import methods
    from signxml.xades import XAdESSigner

    kwargs, alg = _signer_kwargs(arch)
    doc = etree.fromstring(b'<Factura><Meta Id="m">v1</Meta><Importe>100.00</Importe></Factura>')
    signed = etree.tostring(XAdESSigner(method=methods.enveloped, signature_algorithm=alg).sign(doc, reference_uri="#m", **kwargs))
    out = run("verificar-firma", make_ctx("verificar-firma", [_write(tmp_path, "p.xml", signed.replace(b"100.00", b"999.00"))]))
    assert "0 válida(s)" in out[0]["note"] and "no cubre el documento entero" in _report(out)


def test_nested_cades_checks_every_layer_and_second_file(make_ctx, arch, tmp_path, own_root):
    from asn1crypto import cms

    inner = cms.ContentInfo.load(_cms(arch, b"contenido", who="signer2"))
    si = inner["content"]["signer_infos"][0]
    sig = bytearray(si["signature"].native)
    sig[-1] ^= 1
    si["signature"] = bytes(sig)
    outer = _cms(arch, inner.dump())
    out = run("verificar-firma", make_ctx("verificar-firma", [_write(tmp_path, "doble.p7m", outer)]))
    assert "2 firma(s): 1 válida(s)" in out[0]["note"] and "capa 2" in _report(out)
    attached = _write(tmp_path, "a.txt.p7m", _cms(arch, b"contenido A"))
    with pytest.raises(ToolError) as err:
        run("verificar-firma", make_ctx("verificar-firma", [attached, _write(tmp_path, "b.txt", b"documento B")]))
    assert err.value.detail == "verify_attached_mismatch"


def test_deep_xml_is_limited(make_ctx, tmp_path):
    deep = (b'<?xml version="1.0"?>' + b"<a>" * 300 + b'<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#"/>' + b"</a>" * 300)
    for tool in ("xsig-a-pdf", "verificar-firma"):
        with pytest.raises(ToolError) as err:
            run(tool, make_ctx(tool, [_write(tmp_path, "hondo.xsig", deep)]))
        assert err.value.code == "LIMIT_EXCEEDED"
