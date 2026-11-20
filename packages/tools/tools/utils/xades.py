"""XAdES y XMLDSig compartido por xsig-a-pdf (`workerutils`) y verificar-firma (`sign.verify`) (F6-G, D-219 y D-222).

- Lectura: defusedxml primero (sin entidades ni DTD externos, 16.4, y con un tope de profundidad), después lxml con
  `huge_tree` (un .xsig con un PDF de 8 MB tiene un nodo de texto enorme) y sin red.
- Ids repetidos: si un mismo valor aparece en dos atributos Id, ID, id o xml:id, la referencia es ambigua y se rechaza
  (signxml solo lo detecta dentro de un mismo nombre de atributo: era la puerta a un «signature wrapping»).
- Cada firma se verifica en su sitio, sin quitar las demás: un verificador de signxml que encuentra la firma por su
  posición. Así un `ds:Signature` inyectado en el documento rompe la firma de verdad en lugar de pasar por cofirma, y
  las cofirmas sucesivas (cada una sobre el documento con la anterior) siguen valiendo.
- Cobertura: la firma tiene que cubrir datos (no solo KeyInfo o las propiedades firmadas) y, si va dentro de un
  documento, el documento entero (URI="" o el Id de su raíz).
"""
from __future__ import annotations

import base64
from collections import Counter

from core.errors import ErrorCode, ToolError

DS = "http://www.w3.org/2000/09/xmldsig#"
XADES_132 = "http://uri.etsi.org/01903/v1.3.2#"
XML_NS = "http://www.w3.org/XML/1998/namespace"
MAX_DEPTH = 200
ID_ATTRS = ("Id", "ID", "id")
WRAPPERS = ("AFIRMA",)  # el contenedor de las firmas «internally detached» de AutoFirma


def parser():
    from lxml import etree

    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=True, remove_comments=False)


def parse(raw: bytes):
    """La raíz lxml de un XML firmado, tras comprobarlo con defusedxml (entidades, DTD externos y profundidad)."""
    import io

    import defusedxml.ElementTree as DET
    from defusedxml import DefusedXmlException
    from lxml import etree

    depth = 0
    try:
        for event, _el in DET.iterparse(io.BytesIO(raw), events=("start", "end"), forbid_dtd=False, forbid_entities=True,
                                        forbid_external=True):
            depth += 1 if event == "start" else -1
            if depth > MAX_DEPTH:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "data_too_deep")
    except (DefusedXmlException, ValueError) as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities") from exc
    except SyntaxError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "XML no válido") from exc
    try:
        return etree.fromstring(raw, parser=parser())
    except etree.XMLSyntaxError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "XML no válido") from exc


def local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def signatures(root) -> list:
    return [root] if root.tag == f"{{{DS}}}Signature" else list(root.iter(f"{{{DS}}}Signature"))


def ids(el) -> list[str]:
    values = [el.get(a) for a in ID_ATTRS if el.get(a)]
    xml_id = el.get(f"{{{XML_NS}}}id")
    return values + ([xml_id] if xml_id else [])


def duplicate_ids(root) -> bool:
    count = Counter(v for el in root.iter() if isinstance(el.tag, str) for v in ids(el))
    return any(n > 1 for n in count.values())


def by_id(root) -> dict:
    return {v: el for el in root.iter() if isinstance(el.tag, str) for v in ids(el)}


def data_references(sig, index: dict) -> list:
    """Las referencias a datos: ni las propiedades firmadas ni KeyInfo (por su tipo o por el nodo al que apuntan)."""
    out = []
    signed_info = sig.find(f"{{{DS}}}SignedInfo")
    for ref in (signed_info.findall(f"{{{DS}}}Reference") if signed_info is not None else []):
        uri = ref.get("URI")
        if uri is None or (ref.get("Type") or "").endswith("#SignedProperties"):
            continue
        if uri.startswith("#"):
            node = index.get(uri[1:])
            if node is not None and local(node.tag) in ("KeyInfo", "SignedProperties", "QualifyingProperties", "Signature"):
                continue
        out.append(ref)
    return out


def covers_document(root, sig, refs: list) -> bool:
    """Si la firma está dentro de un documento que no es solo su contenedor, ¿cubre el documento entero?"""
    if root is sig or local(root.tag) in WRAPPERS:
        return bool(refs)
    root_ids = set(ids(root))
    return any(r.get("URI") == "" or (r.get("URI", "").startswith("#") and r.get("URI")[1:] in root_ids) for r in refs)


def external(refs: list) -> list:
    return [r for r in refs if r.get("URI") and not r.get("URI").startswith("#")]


def certificates(sig) -> list:
    from asn1crypto import x509

    out = []
    for el in sig.iter(f"{{{DS}}}X509Certificate"):
        try:
            out.append(x509.Certificate.load(base64.b64decode("".join((el.text or "").split()))))
        except Exception:  # noqa: BLE001 - un certificado ilegible se ignora
            continue
    return out


def leaf(certs: list):
    """El certificado del firmante: el primero que no es de una CA (KeyInfo puede traer la cadena entera)."""
    for cert in certs:
        constraints = cert.basic_constraints_value
        if constraints is None or not constraints["ca"].native:
            return cert
    return certs[0] if certs else None


def pem(cert) -> str:
    import textwrap

    body = "\n".join(textwrap.wrap(base64.b64encode(cert.dump()).decode(), 64))
    return f"-----BEGIN CERTIFICATE-----\n{body}\n-----END CERTIFICATE-----\n"


def config(xades: bool):
    """Los algoritmos de signxml más SHA-1, que siguen usando muchas firmas españolas (la misma regla que la firma de
    Facturae en validar-factura-electronica); nunca HMAC, que no prueba quién firma. Las referencias se comprueban aquí."""
    from signxml import DigestAlgorithm, SignatureConfiguration, SignatureMethod
    from signxml.xades import XAdESSignatureConfiguration

    methods = frozenset(m for m in SignatureMethod if not m.name.startswith("HMAC"))
    cls = XAdESSignatureConfiguration if xades else SignatureConfiguration
    return cls(signature_methods=methods, digest_algorithms=frozenset(DigestAlgorithm), expect_references=True)


def verify(raw: bytes, index: int, cert, resolver=None) -> None:
    """Comprueba la firma número `index` (en el orden del documento) con su certificado, sin tocar el documento. Lanza la
    excepción de signxml si no vale."""
    from signxml import XMLVerifier
    from signxml.xades import XAdESVerifier

    def targeted(base):
        class Targeted(base):
            def _get_signature(self, root):
                if root.tag == f"{{{DS}}}Signature":
                    return root
                found = list(root.iter(f"{{{DS}}}Signature"))
                if index >= len(found):
                    from signxml.exceptions import InvalidInput

                    raise InvalidInput("firma no encontrada")
                return found[index]

        return Targeted

    xades = XADES_132.encode() in raw
    verifier = targeted(XAdESVerifier if xades else XMLVerifier)()
    verifier.verify(raw, x509_cert=pem(cert), expect_config=config(xades), uri_resolver=resolver, parser=parser())


def reference_ok(raw: bytes, index: int, cert, resolver=None) -> tuple[bool, str]:
    try:
        verify(raw, index, cert, resolver)
        return True, ""
    except Exception as exc:  # noqa: BLE001 - firma rota, referencias que no cuadran o algoritmo no admitido
        return False, type(exc).__name__
