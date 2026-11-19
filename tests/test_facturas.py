"""F4, lote D: validar-factura-electronica (A.2 y 7.23) con KoSIT real en modo servicio y los XSD de Facturae.

KoSIT corre fuera de las pruebas (en la CI lo arranca el job python; aquí, `KOSIT_URL` apunta al de la caché local de
motores). Sin KoSIT, las pruebas que lo necesitan se saltan; las de Facturae, lectura y seguridad no lo necesitan.
"""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

import httpx
import pikepdf
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fixtures"))

import facturas  # noqa: E402
from test_firmas import arch  # noqa: E402,F401 - PKI de pruebas
from test_tools import make_ctx, run  # noqa: E402,F401 - fixture compartida

TOOL = "validar-factura-electronica"


def _kosit_up() -> bool:
    from core.settings import get_settings

    url = get_settings().KOSIT_URL.rstrip("/") + "/server/health"
    try:
        return httpx.get(url, timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


needs_kosit = pytest.mark.skipif(not _kosit_up(), reason="KoSIT no está en marcha en KOSIT_URL (job python de la CI)")


@pytest.fixture(autouse=True)
def facturae_xsd(monkeypatch):
    from core.settings import get_settings

    monkeypatch.setattr(get_settings(), "FACTURAE_XSD_DIR", ROOT / "infra" / "facturae")


def _file(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _validate(make_ctx, files: list[Path], locale: str = "es"):
    ctx = make_ctx(TOOL, files)
    ctx.locale = locale
    return run(TOOL, ctx), ctx


# --- Lectura y seguridad (sin KoSIT) ------------------------------------------------------------------------------


def test_detects_syntax_spec_and_data():
    from tools.utils.facturas import lectura

    _root, inv = lectura.read_invoice(facturas.ubl_invoice(facturas.UBL_PEPPOL))
    assert (inv.syntax, inv.spec, inv.kind, inv.number, inv.seller, inv.buyer, inv.total, inv.currency) == (
        "ubl", facturas.UBL_PEPPOL, "factura", "F-2026-0042", "Ejemplo Servicios SL", "Cliente Pruebas SA", "2002.55", "EUR")
    assert len(inv.lines) == 2
    _root, inv = lectura.read_invoice(facturas.cii_invoice(facturas.CII_BASIC))
    assert (inv.syntax, inv.spec, inv.date, inv.total) == ("cii", facturas.CII_BASIC, "2026-11-02", "2002.55")
    _root, inv = lectura.read_invoice(facturas.facturae())
    assert (inv.syntax, inv.spec, inv.number, inv.seller_vat, inv.total, inv.signed) == (
        "facturae", "Facturae 3.2.2", "F202642", "B12345674", "2002.55", False)


@pytest.mark.parametrize("payload, detail", [
    (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/hostname">]><x>&e;</x>', "xml_dtd"),
    (b'<?xml version="1.0"?><!DOCTYPE lol [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><lol>&b;</lol>', "xml_dtd"),
    (b"<Invoice><no-cerrado>", "xml_syntax"),
])
def test_xxe_bombs_and_broken_xml_never_reach_kosit(payload, detail, make_ctx, tmp_path, monkeypatch):
    """16.4: un DOCTYPE o una entidad se rechazan antes de llegar a KoSIT (Java), que no se llama."""
    from tools.utils.facturas import motores

    monkeypatch.setattr(motores, "kosit", lambda *a: pytest.fail("no debe llegar a KoSIT"))
    out, _ctx = _validate(make_ctx, [_file(tmp_path, "x.xml", payload)])
    page = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert out[0]["note"] == "No se ha podido validar." and "hostname" not in page
    assert {"xml_dtd": "DOCTYPE", "xml_syntax": "no está bien formado"}[detail] in page


def test_facturae_xsd_and_xades_signature(make_ctx, tmp_path, arch):
    from asn1crypto import pem
    from cryptography.hazmat.primitives import serialization
    from lxml import etree
    from signxml.xades import XAdESSigner

    out, _ = _validate(make_ctx, [_file(tmp_path, "facturae.xml", facturas.facturae())])
    assert out[0]["note"] == "Válida (Facturae 3.2.2)."
    assert "Sin firma electrónica." in Path(out[0]["path"]).read_text(encoding="utf-8")
    key = serialization.load_der_private_key(arch.key_set.get_private_key("signer1").dump(), None)
    signed = etree.tostring(XAdESSigner(signature_algorithm="ecdsa-sha256").sign(
        etree.fromstring(facturas.facturae()), key=key, cert=pem.armor("CERTIFICATE", arch.get_cert("signer1").dump())))
    out, _ = _validate(make_ctx, [_file(tmp_path, "firmada.xml", signed)])
    assert out[0]["note"] == "Válida (Facturae 3.2.2)." and "Firma XAdES íntegra" in Path(out[0]["path"]).read_text(encoding="utf-8")
    tampered = signed.replace(b"Cliente Pruebas SA", b"Otro Cliente SA", 1)
    out, _ = _validate(make_ctx, [_file(tmp_path, "manipulada.xml", tampered)])
    page = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert out[0]["note"].startswith("No válida (Facturae 3.2.2)") and "FIRMA" in page
    broken = facturas.facturae().replace(b"<Modality>I</Modality>", b"<Modality>X</Modality>")
    out, _ = _validate(make_ctx, [_file(tmp_path, "mal.xml", broken)])
    assert out[0]["note"].startswith("No válida") and "XSD" in Path(out[0]["path"]).read_text(encoding="utf-8")


def test_kosit_down_is_transient(make_ctx, tmp_path, monkeypatch):
    from core.errors import ToolError
    from core.settings import get_settings

    monkeypatch.setattr(get_settings(), "KOSIT_URL", "http://127.0.0.1:9/")
    with pytest.raises(ToolError) as err:
        _validate(make_ctx, [_file(tmp_path, "a.xml", facturas.ubl_invoice())])
    assert err.value.code == "ENGINE_FAILED" and err.value.transient


def test_explanations_cover_frequent_rules():
    from tools.utils.facturas import explicaciones

    what, todo = explicaciones.explain("BR-CO-16", "es")
    assert "importe a pagar" in what and "BT-115" in todo
    assert explicaciones.explain("BR-07", "en")[0] == "The buyer name (BT-44) is missing."
    assert explicaciones.explain("BR-CO-99", "es")[0].startswith("Un cálculo")
    assert explicaciones.explain("FX-SCH-A-000372", "es")[0].startswith("Una regla propia de Factur-X")


# --- Con KoSIT -----------------------------------------------------------------------------------------------------


@needs_kosit
@pytest.mark.parametrize("name, note", [
    ("ubl-en16931.xml", "Válida (EN 16931 (UBL))."),
    ("ubl-xrechnung.xml", "Válida (XRechnung)."),
    ("ubl-peppol.xml", "Válida (Peppol BIS Billing 3.0)."),
    ("cii-en16931.xml", "Válida (EN 16931 (CII))."),
    ("cii-basic.xml", None),
    ("cii-minimum.xml", None),
])
def test_valid_invoices_per_specification(name, note, make_ctx, tmp_path):
    out, _ = _validate(make_ctx, [_file(tmp_path, name, facturas.SAMPLES[name]())])
    if note:
        assert out[0]["note"] == note
    else:  # Factur-X BASIC y MINIMUM pueden traer avisos del Schematron de Factur-X
        assert out[0]["note"].startswith("Válida")
    page = Path(out[0]["path"]).read_text(encoding="utf-8")
    if name == "cii-minimum.xml":
        assert "no son facturas EN 16931 completas" in page


@needs_kosit
def test_errors_with_rule_explanation_and_highlighted_field(make_ctx, tmp_path):
    out, _ = _validate(make_ctx, [_file(tmp_path, "mal.xml", facturas.SAMPLES["ubl-total-mal.xml"]())])
    page = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert out[0]["note"] == "No válida (EN 16931 (UBL)): 1 error(es)."
    assert "BR-CO-16" in page and "El importe a pagar no cuadra" in page and "Revisa BT-115" in page
    assert '<section class="b hl"><h3>Totales <span class="tag">BR-CO-16</span>' in page
    out, _ = _validate(make_ctx, [_file(tmp_path, "sin.xml", facturas.SAMPLES["ubl-sin-comprador.xml"]())], locale="en")
    page = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert out[0]["name"] == "validation-sin.html" and "The buyer name (BT-44) is missing." in page
    assert '<section class="b hl"><h3>Customer' in page


@needs_kosit
def test_batch_zip_csv_summary_and_inputs_deleted(make_ctx, tmp_path):
    bundle = tmp_path / "lote.zip"
    with zipfile.ZipFile(bundle, "w") as zf:
        for name in ("ubl-en16931.xml", "ubl-total-mal.xml", "no-es-factura.xml", "cii-en16931.xml"):
            zf.writestr(f"facturas/{name}", facturas.SAMPLES[name]())
    out, ctx = _validate(make_ctx, [bundle])
    names = [o["name"] for o in out]
    assert names[0] == "resumen-validacion.csv" and names[-1] == "validacion-facturas.zip"
    assert out[0]["note"] == "2 de 4 facturas válidas."
    rows = list(csv.reader(io.StringIO(Path(out[0]["path"]).read_text(encoding="utf-8-sig"))))
    assert rows[0][:3] == ["archivo", "numero", "emisor"] and len(rows) == 5
    assert ["ubl-total-mal.xml", "F-2026-0099", "Ejemplo Servicios SL"] == rows[2][:3] and rows[2][7] == "No válida"
    assert rows[3][7] == "No se ha podido validar."  # no es una factura
    assert not any(inp.path.exists() for inp in ctx.inputs)  # A.2: se borra al terminar
    slip = tmp_path / "slip.zip"
    with zipfile.ZipFile(slip, "w") as zf:
        zf.writestr("../fuera.xml", facturas.ubl_invoice())
    from core.errors import ToolError

    with pytest.raises(ToolError) as err:  # 12.3: zip-slip
        _validate(make_ctx, [slip])
    assert err.value.code == "CORRUPT_FILE"


@needs_kosit
def test_factur_x_pdf_and_pdf_without_xml(make_ctx, tmp_path):
    from facturx import generate_from_binary

    pdf = pikepdf.new()
    pdf.add_blank_page()
    buf = io.BytesIO()
    pdf.save(buf)
    fx = generate_from_binary(buf.getvalue(), facturas.cii_invoice(facturas.CII_EN16931), flavor="factur-x", level="en16931",
                              check_xsd=False)
    out, _ = _validate(make_ctx, [_file(tmp_path, "factura.pdf", fx), _file(tmp_path, "sin-xml.pdf", buf.getvalue())])
    reports = [o for o in out if o["name"].endswith(".html")]
    assert reports[0]["note"] == "Válida (EN 16931 (CII))."
    assert "no lleva una factura electrónica incrustada" in Path(reports[1]["path"]).read_text(encoding="utf-8")


@needs_kosit
def test_ubl_attachment_is_delivered(make_ctx, tmp_path):
    import base64

    data = facturas.ubl_invoice().replace(b"<cac:AccountingSupplierParty>", b"""<cac:AdditionalDocumentReference><cbc:ID>Pedido</cbc:ID>
    <cac:Attachment><cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain" filename="../pedido.txt">"""
        + base64.b64encode(b"pedido 7") + b"""</cbc:EmbeddedDocumentBinaryObject></cac:Attachment></cac:AdditionalDocumentReference>
  <cac:AccountingSupplierParty>""", 1)
    out, _ = _validate(make_ctx, [_file(tmp_path, "con-adjunto.xml", data)])
    attachment = next(o for o in out if "-anexo-" in o["name"])
    assert Path(attachment["path"]).read_bytes() == b"pedido 7" and "/" not in attachment["name"]


# --- Revisión de F4-D1 (D-191) ---------------------------------------------------------------------------------------


def _self_signed():
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Firmante de pruebas")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(7)
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=30)).sign(key, hashes.SHA256()))
    return key, cert


def _dsig_sha1(data: bytes, key, cert, uri: str = "") -> bytes:
    """Firma XMLDSig envolvente RSA-SHA1 hecha a mano (signxml ya no firma con SHA-1, pero muchas Facturae reales lo
    usan): con `uri`, la referencia cubre solo `Parties` y no la factura entera."""
    import base64
    import hashlib

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from lxml import etree

    ds = "http://www.w3.org/2000/09/xmldsig#"
    root = etree.fromstring(data)
    target = root
    if uri:
        target = root.find(".//Parties")
        target.set("Id", uri[1:])
    digest = base64.b64encode(hashlib.sha1(etree.tostring(target, method="c14n")).digest()).decode()  # noqa: S324
    signed_info = etree.fromstring(
        f'<ds:SignedInfo xmlns:ds="{ds}"><ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>'
        f'<ds:SignatureMethod Algorithm="{ds}rsa-sha1"/><ds:Reference URI="{uri}"><ds:Transforms>'
        f'<ds:Transform Algorithm="{ds}enveloped-signature"/></ds:Transforms><ds:DigestMethod Algorithm="{ds}sha1"/>'
        f"<ds:DigestValue>{digest}</ds:DigestValue></ds:Reference></ds:SignedInfo>")
    sig = etree.SubElement(root, f"{{{ds}}}Signature", nsmap={"ds": ds})
    sig.append(signed_info)
    value = key.sign(etree.tostring(signed_info, method="c14n"), padding.PKCS1v15(), hashes.SHA1())  # noqa: S303
    etree.SubElement(sig, f"{{{ds}}}SignatureValue").text = base64.b64encode(value).decode()
    x509_data = etree.SubElement(etree.SubElement(sig, f"{{{ds}}}KeyInfo"), f"{{{ds}}}X509Data")
    etree.SubElement(x509_data, f"{{{ds}}}X509Certificate").text = base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


@pytest.mark.parametrize("version", ["3.2", "3.2.1", "3.2.2"])
def test_every_facturae_version_is_recognised_by_its_namespace(version, make_ctx, tmp_path):
    out, _ = _validate(make_ctx, [_file(tmp_path, "f.xml", facturas.facturae(version=version))])
    assert out[0]["note"] == f"Válida (Facturae {version})."


def test_facturae_sha1_signature_and_signature_not_covering_the_invoice(make_ctx, tmp_path):
    key, cert = _self_signed()
    signed = _dsig_sha1(facturas.facturae(version="3.2.1"), key, cert)
    out, _ = _validate(make_ctx, [_file(tmp_path, "sha1.xml", signed)])
    assert out[0]["note"] == "Válida (Facturae 3.2.1)."
    assert "Firma XML íntegra" in Path(out[0]["path"]).read_text(encoding="utf-8")
    partial = _dsig_sha1(facturas.facturae(), key, cert, uri="#partes")
    out, _ = _validate(make_ctx, [_file(tmp_path, "parcial.xml", partial)])
    page = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert out[0]["note"].startswith("No válida") and "no cubre la factura entera" in page


def test_bad_files_stay_in_their_row_and_do_not_fail_the_batch(make_ctx, tmp_path):
    encrypted = tmp_path / "cifrado.pdf"
    pdf = pikepdf.new()
    pdf.add_blank_page()
    pdf.save(encrypted, encryption=pikepdf.Encryption(owner="o", user="u"))
    files = [_file(tmp_path, "f.xml", facturas.facturae()), _file(tmp_path, "roto.pdf", b"%PDF-1.7 esto no es un PDF"), encrypted]
    out, _ = _validate(make_ctx, files)
    assert out[0]["note"] == "1 de 3 facturas válidas."
    pages = {o["name"]: Path(o["path"]).read_text(encoding="utf-8") for o in out if o["name"].endswith(".html")}
    assert "el PDF está dañado" in pages["validacion-roto.html"]
    assert "protegido con contraseña" in pages["validacion-cifrado.html"]


def test_zip_members_are_counted_before_reading_and_oversized_ones_reported(make_ctx, tmp_path, monkeypatch):
    from core.errors import ToolError
    from tools.utils.facturas import lectura

    many = tmp_path / "muchas.zip"
    with zipfile.ZipFile(many, "w") as zf:
        for i in range(101):
            zf.writestr(f"f{i}.xml", b"<x/>")
    with monkeypatch.context() as m, pytest.raises(ToolError) as err:
        m.setattr(zipfile.ZipFile, "open", lambda *a, **k: pytest.fail("no debe leer ningún miembro"))
        _validate(make_ctx, [many])
    assert err.value.code == "TOO_MANY_FILES"
    monkeypatch.setattr(lectura, "MAX_XML_BYTES", len(facturas.facturae()) + 10)
    mixed = tmp_path / "mixto.zip"
    with zipfile.ZipFile(mixed, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("buena.xml", facturas.facturae())
        zf.writestr("grande.xml", facturas.facturae() + b" " * 100)
    out, _ = _validate(make_ctx, [mixed])
    assert out[0]["note"] == "1 de 2 facturas válidas."
    page = next(Path(o["path"]).read_text(encoding="utf-8") for o in out if o["name"] == "validacion-grande.html")
    assert "supera los 20 MB" in page


def test_pdf_attachment_bomb_is_never_inflated_whole(make_ctx, tmp_path, monkeypatch):
    import zlib

    from tools.utils.facturas import lectura

    bomb = tmp_path / "bomba.pdf"
    pdf = pikepdf.new()
    pdf.add_blank_page()
    payload = zlib.compress(b"<" + b" " * (40 * 1024 * 1024), 9)  # unos 40 KB que se inflan a 40 MB
    stream = pikepdf.Stream(pdf, payload)
    stream.Filter = pikepdf.Name.FlateDecode
    stream.Type = pikepdf.Name.EmbeddedFile
    spec = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Filespec, F="factur-x.xml", UF="factur-x.xml",
                                                EF=pikepdf.Dictionary(F=pdf.make_indirect(stream))))
    pdf.Root.Names = pikepdf.Dictionary(EmbeddedFiles=pikepdf.Dictionary(Names=pikepdf.Array(["factur-x.xml", spec])))
    pdf.save(bomb)
    real_decompress = zlib.decompressobj
    sizes = []

    class Spy:
        def __init__(self):
            self.inner = real_decompress()

        def decompress(self, data, max_length=0):
            out = self.inner.decompress(data, max_length)
            sizes.append((max_length, len(out)))
            return out

    monkeypatch.setattr(zlib, "decompressobj", Spy)
    out, _ = _validate(make_ctx, [bomb])
    assert out[0]["note"] == "No se ha podido validar."
    assert "supera los 20 MB" in Path(out[0]["path"]).read_text(encoding="utf-8")
    assert sizes and all(0 < limit <= lectura.MAX_XML_BYTES + 1 and n <= limit for limit, n in sizes)


def test_cii_attachment_gets_the_extension_of_its_mime_type():
    from tools.utils.facturas import lectura

    _root, inv = lectura.read_invoice(facturas.cii_invoice(attachment=b"%PDF-1.4 albaran"))
    assert [(lectura.attachment_name(n, m), c) for n, m, c in inv.attachments] == [("albaran.pdf", b"%PDF-1.4 albaran")]
    _root, inv = lectura.read_invoice(facturas.facturae(attachment=b"%PDF-1.4 anexo"))
    assert [(n, c) for n, _m, c in inv.attachments] == [("anexo-1.pdf", b"%PDF-1.4 anexo")]


@needs_kosit
def test_custom_levels_of_the_scenario_and_kosit_verdict(make_ctx, tmp_path):
    # XRechnung rebaja BR-CL-23 (unidad de medida) de «fatal» a aviso: KoSIT acepta la factura y el informe también.
    data = facturas.ubl_invoice(facturas.UBL_XRECHNUNG).replace(b'unitCode="C62"', b'unitCode="QQQ1"', 1)
    out, _ = _validate(make_ctx, [_file(tmp_path, "x.xml", data)])
    page = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert out[0]["note"].startswith("Válida con") and "(XRechnung)" in out[0]["note"]
    assert '<tr class="warning"><td class="c">BR-CL-23</td>' in page


@needs_kosit
@pytest.mark.parametrize("guideline, scenario", [
    ("urn:cen.eu:en16931:2017#compliant#urn:zugferd.de:2p0:basic", "Factur-X BASIC (CII)"),
    ("urn:cen.eu:en16931:2017#conformant#urn:zugferd.de:2p0:extended", "Factur-X EXTENDED (CII)"),
    ("urn:zugferd.de:2p0:minimum", "Factur-X MINIMUM (CII)"),
])
def test_zugferd_2_identifiers_use_the_factur_x_scenarios(guideline, scenario):
    from core.settings import get_settings
    from tools.utils.facturas import motores

    assert motores.kosit(get_settings(), facturas.cii_invoice(guideline)).scenario == scenario


@needs_kosit
def test_kosit_xsd_findings_carry_line_and_column(make_ctx, tmp_path):
    data = facturas.ubl_invoice(facturas.UBL_EN16931).replace(b"<cbc:IssueDate>", b"<cbc:Basura>x</cbc:Basura><cbc:IssueDate>", 1)
    out, _ = _validate(make_ctx, [_file(tmp_path, "x.xml", data)])
    assert out[0]["note"].startswith("No válida") and "Línea 5, columna" in Path(out[0]["path"]).read_text(encoding="utf-8")
