"""Motores de validar-factura-electronica (7.23): KoSIT en modo servicio para UBL y CII, y XSD más firma para Facturae.

KoSIT corre dentro de `workerutils` (5.4), en 127.0.0.1 (KOSIT_URL), con las configuraciones públicas de XRechnung y
Peppol BIS y los escenarios propios de `infra/kosit/scenarios.xml` (Factur-X y EN 16931 con otra CIUS). El XML llega
ya leído con `lectura.parse_xml` (sin DTD ni entidades). El informe VARL se lee con defusedxml.

Facturae 3.2, 3.2.1 y 3.2.2: XSD oficiales de facturae.gob.es (FACTURAE_XSD_DIR) con el `import` de XMLDSig apuntando
a la copia local (sin red), y la firma XAdES, si la hay, con signxml (nunca xmlsig, AGPL; 11).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from core.errors import ErrorCode, ToolError

VARL = "{http://www.xoev.de/de/validator/varl/1}"
SCEN = "{http://www.xoev.de/de/validator/framework/1/scenarios}"
CODE = re.compile(r"^\[([A-Za-z0-9_.-]+)\]-?\s*")
DSIG_REMOTE = "http://www.w3.org/TR/xmldsig-core/xmldsig-core-schema.xsd"


@dataclass
class Finding:
    code: str
    level: str  # error, warning o information
    text: str
    location: str = ""


@dataclass
class Result:
    engine: str
    scenario: str = ""
    accepted: bool = False
    findings: list[Finding] = field(default_factory=list)
    signature: str = ""  # Facturae: sin_firma, valida o no_valida


MAX_REPORT_BYTES = 256 * 1024 * 1024  # una factura sintética de 20 MB con fallos en cada línea da unos 80 MB
MAX_MESSAGES = 2000
BIG_INVOICE = 2 * 1024 * 1024
LOCK_PATH = Path("/tmp/kosit.lock")


def _lock(size: int):
    """Las facturas grandes pasan por KoSIT de una en una (cerrojo exclusivo entre los procesos del contenedor) y las
    pequeñas a la vez (compartido): con 1 GB de heap, una de 20 MB cabe y dos a la vez no (D-191)."""
    import contextlib
    import fcntl

    @contextlib.contextmanager
    def held():
        with LOCK_PATH.open("a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX if size > BIG_INVOICE else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    return held()


def kosit(settings, data: bytes, work: Path | None = None) -> Result:
    """Valida con KoSIT. El veredicto es el de KoSIT (`assessment/accept`); los niveles de cada regla se corrigen con los
    `customLevel` del escenario elegido (XRechnung rebaja BR-CL-23 a aviso y sube UBL-CR-646 a error, por ejemplo), que el
    informe VARL aplica solo a la evaluación y no a `message/@level`. El informe se guarda en disco y se lee en streaming,
    con un tope de mensajes: en memoria no está nunca entero."""
    import tempfile

    import httpx
    from defusedxml.ElementTree import iterparse

    folder = work or Path(tempfile.gettempdir())
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=folder, prefix="kosit-", suffix=".xml") as report:
        try:
            with _lock(len(data)), httpx.stream("POST", settings.KOSIT_URL, content=data, headers={"Content-Type": "application/xml"},
                                                timeout=settings.KOSIT_TIMEOUT) as resp:
                size = 0
                for chunk in resp.iter_bytes():
                    size += len(chunk)
                    if size > MAX_REPORT_BYTES:
                        raise ToolError(ErrorCode.ENGINE_FAILED, "kosit: informe demasiado grande")
                    report.write(chunk)
                status = resp.status_code
        except httpx.HTTPError as exc:
            raise ToolError(ErrorCode.ENGINE_FAILED, "kosit", transient=True) from exc
        report.flush()
        report.seek(0)
        head = report.read(256).lstrip()
        if status >= 500 and not head.startswith(b"<"):
            raise ToolError(ErrorCode.ENGINE_FAILED, f"kosit {status}", transient=True)
        report.seek(0)
        result = Result("kosit")
        custom: dict[str, str] = {}
        raw: list[tuple[str, str, str, str]] = []
        try:
            for _event, el in iterparse(report, events=("end",)):
                if el.tag == f"{SCEN}scenario" and not result.scenario:
                    name = el.find(f"{SCEN}name")
                    result.scenario = (name.text or "").strip() if name is not None else ""
                    for level in el.iter(f"{SCEN}customLevel"):
                        if (level.text or "").strip():
                            custom[level.text.strip()] = level.get("level", "error")
                elif el.tag == f"{VARL}message":
                    if len(raw) < MAX_MESSAGES:
                        raw.append(((el.text or "").strip(), el.get("code") or "", el.get("level", "error"),
                                    el.get("xpathLocation") or "", el.get("lineNumber") or "", el.get("columnNumber") or ""))
                    el.clear()
                elif el.tag == f"{VARL}accept":
                    result.accepted = True
        except Exception as exc:  # noqa: BLE001 - respuesta inesperada del motor
            raise ToolError(ErrorCode.ENGINE_FAILED, "kosit: informe ilegible") from exc
    for text, code, level, xpath, line, column in raw:
        match = CODE.match(text)
        if match:
            code = code or match.group(1)
            text = text[match.end():]
        location = _location(xpath)
        if not location and line:  # los fallos del XSD traen línea y columna, no ruta
            text = f"Línea {line}, columna {column or '?'}: {text}"
        result.findings.append(Finding(code=code or "XSD", level=custom.get(code, level), text=text[:1000], location=location))
    return result


def _location(xpath: str) -> str:
    """`/Q{ns}Invoice[1]/Q{ns}LegalMonetaryTotal[1]` → `Invoice/LegalMonetaryTotal` (lo que se resalta en el informe)."""
    parts = re.findall(r"(?:Q\{[^}]*\}|\*:)?([A-Za-z_][\w.-]*)(?:\[[^\]]*\])*", xpath.replace("/", " / "))
    return "/".join(p for p in parts if p and p not in ("namespace-uri",))[:300]


_SCHEMAS: dict[str, object] = {}


def _schema(settings, version: str):
    from lxml import etree

    if version in _SCHEMAS:
        return _SCHEMAS[version]
    folder = Path(settings.FACTURAE_XSD_DIR)
    xsd = folder / f"Facturaev{version}.xsd"
    dsig = folder / "xmldsig-core-schema.xsd"
    if not xsd.exists() or not dsig.exists():
        raise ToolError(ErrorCode.ENGINE_FAILED, "facturae_xsd")
    text = xsd.read_bytes().replace(DSIG_REMOTE.encode(), dsig.resolve().as_uri().encode())
    # Solo con los XSD propios de la imagen (el de XMLDSig declara entidades internas en su DOCTYPE); sin red ni DTD
    # externas. Las facturas de los usuarios nunca pasan por este analizador.
    parser = etree.XMLParser(resolve_entities=True, no_network=True, load_dtd=False)
    schema = etree.XMLSchema(etree.fromstring(text, parser=parser, base_url=xsd.resolve().as_uri()))
    _SCHEMAS[version] = schema
    return schema


def facturae(settings, root, data: bytes, version: str, check_signature: bool = True) -> Result:
    from lxml import etree

    result = Result("facturae", scenario=f"Facturae {version.replace('_', '.')}")
    schema = _schema(settings, version)
    # Se valida una copia sin firma (la firma va en otro espacio de nombres y no la describe el XSD de 3.2 y 3.2.1).
    tree = etree.fromstring(etree.tostring(root))
    for sig in tree.findall("{http://www.w3.org/2000/09/xmldsig#}Signature"):
        tree.remove(sig)
    if not schema.validate(tree):
        for err in list(schema.error_log)[:100]:
            result.findings.append(Finding(code="XSD", level="error", text=f"Línea {err.line}: {err.message}"[:1000],
                                           location=err.path or ""))
    signature = root.find("{http://www.w3.org/2000/09/xmldsig#}Signature")
    if not check_signature:  # factura-electronica-a-pdf solo necesita el XSD (la firma va intacta en el XML incrustado)
        result.signature = ""
    elif signature is None:
        result.signature = "sin_firma"
    else:
        result.signature = _signature(data, root.tag)
        if result.signature == "no_valida":
            result.findings.append(Finding(code="FIRMA", level="error", text="La firma XAdES no es válida."))
    result.accepted = not any(f.level == "error" for f in result.findings)
    return result


XADES_132 = "http://uri.etsi.org/01903/v1.3.2#"


def _config(xades: bool):
    """Algoritmos admitidos: los de signxml más SHA-1, que siguen usando muchas Facturae firmadas (la política de firma
    de Facturae 3.1 lo permitía); nunca HMAC, que no prueba quién firma."""
    from signxml import DigestAlgorithm, SignatureConfiguration, SignatureMethod
    from signxml.xades import XAdESSignatureConfiguration

    methods = frozenset(m for m in SignatureMethod if not m.name.startswith("HMAC"))
    cls = XAdESSignatureConfiguration if xades else SignatureConfiguration
    return cls(signature_methods=methods, digest_algorithms=frozenset(DigestAlgorithm), expect_references=True)


def _signature(data: bytes, root_tag: str) -> str:
    """Integridad de la firma con el certificado que trae la propia firma (su confianza no se comprueba aquí: eso es
    verificar-firma, F6). `valida`: XAdES 1.3.2 íntegra; `valida_dsig`: firma XMLDSig íntegra sin XAdES 1.3.2 (XAdES 1.2.2
    o 1.1.1, cuyas propiedades no se comprueban); `no_valida`: rota, sin certificado, con un algoritmo no admitido o sin una
    referencia que cubra la factura entera (una firma de otra parte del documento no prueba nada de la factura)."""
    import base64
    import textwrap

    from lxml import etree
    from signxml import XMLVerifier
    from signxml.xades import XAdESVerifier

    try:
        root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True))
        node = root.find(".//{http://www.w3.org/2000/09/xmldsig#}X509Certificate")
        if node is None or not (node.text or "").strip():
            return "no_valida"
        der = base64.b64decode("".join(node.text.split()))
        cert = "-----BEGIN CERTIFICATE-----\n" + "\n".join(textwrap.wrap(base64.b64encode(der).decode(), 64)) + "\n-----END CERTIFICATE-----\n"
        old = XADES_132.encode() not in data  # XAdES 1.2.2, 1.1.1 o XMLDSig sin propiedades XAdES
        if old:
            results = XMLVerifier().verify(data, x509_cert=cert, expect_config=_config(False))
        else:
            results = XAdESVerifier().verify(data, x509_cert=cert, expect_config=_config(True))
        results = results if isinstance(results, list) else [results]
        if not any(getattr(r.signed_xml, "tag", None) == root_tag for r in results):
            return "no_valida"
        return "valida_dsig" if old else "valida"
    except Exception:  # noqa: BLE001 - firma rota, referencias que no cuadran o algoritmo no admitido
        return "no_valida"


SYNTAX_XSD = {
    "ubl-invoice": "xrechnung/resources/ubl/2.1/xsd/maindoc/UBL-Invoice-2.1.xsd",
    "ubl-credit": "xrechnung/resources/ubl/2.1/xsd/maindoc/UBL-CreditNote-2.1.xsd",
    "cii": "xrechnung/resources/cii/16b/xsd/CrossIndustryInvoice_100pD16B.xsd",
}


def syntax_errors(settings, root, syntax: str) -> list[str]:
    """Fallos del XSD oficial de la sintaxis (UBL 2.1 o CII D16B, los de la configuración de KoSIT en la imagen; 7.14):
    lista vacía si cumple. Los XSD son archivos propios de la imagen, sin red; el XML del usuario ya viene leído sin DTD."""
    from lxml import etree

    key = syntax if syntax == "cii" else ("ubl-credit" if root.tag.endswith("}CreditNote") else "ubl-invoice")
    if key not in _SCHEMAS:
        path = Path(settings.KOSIT_HOME) / SYNTAX_XSD[key]
        if not path.exists():
            raise ToolError(ErrorCode.ENGINE_FAILED, "xsd de la sintaxis")
        parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
        _SCHEMAS[key] = etree.XMLSchema(etree.parse(str(path), parser=parser))
    schema = _SCHEMAS[key]
    if schema.validate(root):
        return []
    return [f"Línea {err.line}: {err.message}"[:500] for err in list(schema.error_log)[:20]]

