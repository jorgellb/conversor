"""Documentos firmados (7.13, F6-G, D-219): csig-a-pdf, p7m-a-pdf y xsig-a-pdf sacan el documento original.

- CAdES y PKCS#7 (.csig de AutoFirma, .p7m, .p7s): asn1crypto lee el SignedData (DER, PEM o Base64) y el contenido
  encapsulado sale tal cual, byte a byte (16.5); si dentro hay otra firma (firmado dos veces), se desenvuelve también.
- XAdES (.xsig): defusedxml (sin entidades ni DTD externos); el documento es el `ds:Object` o el nodo de contenido
  (`CONTENT` de AutoFirma) al que apunta la firma, en Base64 o como XML. Con una firma envuelta en el propio XML
  (Facturae firmada), el documento es ese XML sin la firma.
Aquí no se comprueba la firma: eso es verificar-firma, en `sign.verify`. Si el documento no es un PDF se entrega tal cual
y la nota lo dice (7.13).
"""
from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path

from core import filetype
from core.errors import ErrorCode, ToolError
from tools.base import ToolContext
from tools.pdf.common import with_batch_zip

MAX_BYTES = 100 * 1024 * 1024
MAX_NESTING = 5
DS = "http://www.w3.org/2000/09/xmldsig#"
SIGNED_EXTS = (".p7m", ".p7s", ".csig", ".xsig", ".p7b")
BASE64_RE = re.compile(rb"^[A-Za-z0-9+/=\s]+$")

NOTES = {
    "es": {"signed_by": "Firmado por {who}.", "signers": "{n} firmantes: {who}.", "levels": "Estaba firmado {n} veces (unas dentro de otras).",
           "not_pdf": "El documento firmado no es un PDF sino {ext}: se entrega tal cual; puedes convertirlo después.",
           "unchecked": "La firma no se ha comprobado aquí: para saber si es válida, usa Verificar firma.",
           "xml_rebuilt": "El XML se entrega sin la firma; puede diferir en espacios del original."},
    "en": {"signed_by": "Signed by {who}.", "signers": "{n} signers: {who}.", "levels": "It was signed {n} times (one inside another).",
           "not_pdf": "The signed document is not a PDF but {ext}: it is delivered as it is; you can convert it afterwards.",
           "unchecked": "The signature was not checked here: to know whether it is valid, use Verify signature.",
           "xml_rebuilt": "The XML is delivered without the signature; whitespace may differ from the original."},
}


# --- CMS --------------------------------------------------------------------------------------------------------------


def cms_bytes(raw: bytes) -> bytes:
    """DER de un CMS que puede venir en PEM («-----BEGIN PKCS7-----») o en Base64 (algunos .p7m de la administración)."""
    stripped = raw.strip()
    if stripped.startswith(b"-----BEGIN"):
        body = b"".join(line for line in stripped.splitlines() if not line.startswith(b"-----"))
        try:
            return base64.b64decode(body, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise ToolError(ErrorCode.CORRUPT_FILE, "PEM no válido") from exc
    if stripped[:1] != b"\x30" and BASE64_RE.fullmatch(stripped[:4096]):
        try:
            return base64.b64decode(b"".join(stripped.split()), validate=True)
        except (binascii.Error, ValueError):
            pass
    return raw


def load_signed_data(raw: bytes):
    """El SignedData de un CMS, o ToolError si no lo es."""
    from asn1crypto import cms

    data = cms_bytes(raw)
    try:
        info = cms.ContentInfo.load(data)
        if info["content_type"].native != "signed_data":
            raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "cms_not_signed")
        signed = info["content"]
        signed.native  # noqa: B018 - fuerza la lectura completa: un DER roto falla aquí y no más tarde
        return signed
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 - asn1crypto lanza ValueError, TypeError o KeyError según el defecto
        raise ToolError(ErrorCode.CORRUPT_FILE, "cms") from exc


def signer_names(signed) -> list[str]:
    """Nombre común de cada firmante (por el emisor y el número de serie de su SignerInfo)."""
    certs = {}
    for choice in signed["certificates"] or []:
        if choice.name == "certificate":
            cert = choice.chosen
            certs[(cert.issuer.dump(), cert.serial_number)] = cert
    names = []
    for si in signed["signer_infos"]:
        sid = si["sid"]
        cert = None
        if sid.name == "issuer_and_serial_number":
            cert = certs.get((sid.chosen["issuer"].dump(), sid.chosen["serial_number"].native))
        else:
            key_id = sid.chosen.native
            cert = next((c for c in certs.values() if c.key_identifier == key_id), None)
        subject = cert.subject.native if cert is not None else {}
        names.append(str(subject.get("common_name") or subject.get("organization_name") or "?"))
    return names


def unwrap_cms(raw: bytes) -> tuple[bytes, list[list[str]]]:
    """El contenido encapsulado, byte a byte, y los firmantes de cada capa. Sin contenido (firma separada), error."""
    layers: list[list[str]] = []
    data = raw
    for _ in range(MAX_NESTING):
        signed = load_signed_data(data)
        layers.append(signer_names(signed))
        content = signed["encap_content_info"]["content"]
        if content.native is None:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "cms_detached")
        data = content.native if isinstance(content.native, bytes) else content.contents
        try:
            load_signed_data(data)
        except ToolError:
            return data, layers
    raise ToolError(ErrorCode.LIMIT_EXCEEDED, "cms_nesting")


# --- XAdES ------------------------------------------------------------------------------------------------------------


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def unwrap_xades(raw: bytes) -> tuple[bytes, list[str], bool]:
    """(documento, firmantes, si se ha rehecho el XML). El documento es el nodo al que apunta una referencia de la firma
    que no es la de las propiedades firmadas ni la de KeyInfo."""
    import defusedxml.ElementTree as DET
    from defusedxml import DefusedXmlException

    try:
        root = DET.fromstring(raw, forbid_dtd=False, forbid_entities=True, forbid_external=True)
    except (DefusedXmlException, ValueError) as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities") from exc
    except SyntaxError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "XML no válido") from exc
    signatures = list(root.iter(f"{{{DS}}}Signature"))
    if not signatures:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "xades_no_signature")
    by_id = {el.get(attr): el for el in root.iter() for attr in ("Id", "ID", "id") if el.get(attr)}
    names = [_xades_signer(sig) for sig in signatures]
    for sig in signatures:
        for ref in sig.iter(f"{{{DS}}}Reference"):
            uri = ref.get("URI")
            if ref.get("Type", "").endswith("#SignedProperties") or uri is None:
                continue
            if uri == "":
                # Firma envuelta: el documento es el propio XML sin las firmas.
                return _without_signatures(root), names, True
            if not uri.startswith("#"):
                continue  # referencia a un archivo de fuera: firma separada
            node = by_id.get(uri[1:])
            if node is None or _local(node.tag) in ("KeyInfo", "SignedProperties", "Signature"):
                continue
            data, rebuilt = _node_content(node)
            return data, names, rebuilt
    raise ToolError(ErrorCode.INVALID_OPTIONS, "xades_detached")


def _node_content(node) -> tuple[bytes, bool]:
    """Base64 (`Encoding` o texto que solo puede serlo) o el XML hijo (vuelto a escribir: True)."""
    import xml.etree.ElementTree as ET

    encoding = (node.get("Encoding") or "").lower()
    text = (node.text or "").strip()
    children = list(node)
    if children and not text:
        return ET.tostring(children[0], encoding="utf-8", xml_declaration=True), True
    if "base64" in encoding or (text and not children and re.fullmatch(r"[A-Za-z0-9+/=\s]+", text) and len(text) % 4 == 0):
        try:
            return base64.b64decode("".join(text.split()), validate=True), False
        except (binascii.Error, ValueError) as exc:
            raise ToolError(ErrorCode.CORRUPT_FILE, "Base64 no válido en la firma") from exc
    return (node.text or "").encode("utf-8"), False


def _without_signatures(root) -> bytes:
    import copy
    import xml.etree.ElementTree as ET

    tree = copy.deepcopy(root)
    for parent in tree.iter():
        for child in list(parent):
            if child.tag == f"{{{DS}}}Signature":
                parent.remove(child)
    return ET.tostring(tree, encoding="utf-8", xml_declaration=True)


def _xades_signer(sig) -> str:
    from asn1crypto import x509

    for el in sig.iter(f"{{{DS}}}X509Certificate"):
        try:
            cert = x509.Certificate.load(base64.b64decode("".join((el.text or "").split())))
            subject = cert.subject.native
            return str(subject.get("common_name") or subject.get("organization_name") or "?")
        except Exception:  # noqa: BLE001 - un certificado ilegible no impide sacar el documento
            continue
    return "?"


# --- Herramienta ------------------------------------------------------------------------------------------------------


def output_name(original: str, data: bytes, ctx: ToolContext) -> tuple[str, str]:
    """«contrato.pdf.csig» → «contrato.pdf»; sin extensión dentro, la que digan sus bytes."""
    name = original
    while Path(name).suffix.lower() in SIGNED_EXTS:
        name = name[: -len(Path(name).suffix)]
    probe = ctx.work / "documento.bin"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_bytes(data)
    found = filetype.detect(probe, Path(name).suffix.lstrip("."))
    probe.unlink()
    ext = found.ext if found is not None else ""
    if data.lstrip()[:5] == b"<?xml" and not ext.startswith(("xml", "svg", "html")):
        ext = "xml"
    stem, inner = Path(name).stem or "documento", Path(name).suffix.lstrip(".").lower()
    if inner and (not ext or filetype.normalize_ext(inner) == ext or (found and filetype.family_of(inner) == found.family)):
        return f"{stem}.{inner}", filetype.normalize_ext(inner)
    return f"{stem}.{ext or 'bin'}", ext or "bin"


def run(ctx: ToolContext) -> list[dict]:
    t = NOTES.get(ctx.locale, NOTES["es"])
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        if inp.path.stat().st_size > MAX_BYTES:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Firma de más de 100 MB")
        raw = inp.path.read_bytes()
        notes = []
        if ctx.tool == "xsig-a-pdf":
            data, names, rebuilt = unwrap_xades(raw)
            layers = [names]
            if rebuilt and data.lstrip()[:5] == b"<?xml":
                notes.append(t["xml_rebuilt"])
        else:
            data, layers = unwrap_cms(raw)
        who = [w for layer in layers for w in layer]
        notes.insert(0, t["signed_by"].format(who=", ".join(who)) if len(who) == 1 else t["signers"].format(n=len(who), who=", ".join(who)))
        if len(layers) > 1:
            notes.append(t["levels"].format(n=len(layers)))
        name, ext = output_name(inp.name, data, ctx)
        if ext != "pdf":
            notes.append(t["not_pdf"].format(ext=ext.upper()))
        notes.append(t["unchecked"])
        dst = ctx.output(name)
        dst.write_bytes(data)
        outputs.append({"path": str(dst), "name": name, "note": " ".join(notes)})
    return with_batch_zip(ctx, outputs, f"{ctx.tool}.zip")
