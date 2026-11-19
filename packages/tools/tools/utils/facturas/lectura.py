"""Lectura segura de facturas electrónicas (7.23, 12.3 y 16.4) y datos comunes para el informe y el resumen.

- XML sin DTD ni entidades (`defusedxml` lo rechaza antes de llegar a KoSIT, que es Java y no debe ver un DOCTYPE),
  sin red y con un tope de tamaño.
- Sintaxis: UBL 2.1 (Invoice y CreditNote), CII D16B (Factur-X, ZUGFeRD, XRechnung CII) y Facturae 3.2, 3.2.1 y 3.2.2.
- Especificación: `CustomizationID` en UBL y `GuidelineSpecifiedDocumentContextParameter/ID` en CII (A.2).
- PDF: el XML incrustado de Factur-X, ZUGFeRD 2 o XRechnung (adjunto del PDF), leído con pikepdf y con tope de
  descompresión, y los demás archivos incrustados como anexos.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from core.errors import ErrorCode, ToolError

MAX_XML_BYTES = 20 * 1024 * 1024
UBL_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
UBL_CREDIT = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
CII = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
# Espacio de nombres (el `targetNamespace` de cada XSD oficial) → versión.
FACTURAE = {"http://www.facturae.es/Facturae/2009/v3.2/Facturae": "3_2",
            "http://www.facturae.es/Facturae/2014/v3.2.1/Facturae": "3_2_1",
            "http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_2.xml": "3_2_2"}
MAX_ATTACHMENTS = 20
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MIME_EXT = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg", "text/csv": "csv", "text/xml": "xml",
            "application/xml": "xml", "text/plain": "txt", "application/zip": "zip", "image/tiff": "tif", "image/gif": "gif",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
            "application/vnd.oasis.opendocument.spreadsheet": "ods"}
NS = {"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
      "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
      "rsm": CII, "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
      "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"}
# Nombres de los adjuntos de PDF con la factura (Factur-X 1.0, ZUGFeRD 1 y 2, XRechnung).
PDF_XML_NAMES = ("factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml", "zugferd_invoice.xml", "zugferd.xml")


@dataclass
class Invoice:
    """Lo que se enseña en el informe y en el resumen CSV (A.2: número, emisor, fecha, total y resultado)."""

    syntax: str  # ubl, cii o facturae
    spec: str = ""  # CustomizationID, ID de la guía o versión de Facturae
    kind: str = ""  # factura o abono
    number: str = ""
    date: str = ""
    seller: str = ""
    seller_vat: str = ""
    buyer: str = ""
    buyer_vat: str = ""
    currency: str = ""
    total: str = ""
    lines: list[tuple[str, str, str]] = field(default_factory=list)  # descripción, cantidad e importe
    attachments: list[tuple[str, str, bytes]] = field(default_factory=list)  # nombre, tipo MIME y contenido (como mucho 20)
    signed: bool = False


def parse_xml(data: bytes):
    """Árbol de lxml de un XML de usuario: sin DTD, sin entidades y sin red."""
    from defusedxml import DefusedXmlException
    from defusedxml.lxml import fromstring
    from lxml import etree

    if len(data) > MAX_XML_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"xml_size:{len(data) // 1048576}>{MAX_XML_BYTES // 1048576}")
    if re.search(rb"<!DOCTYPE|<!ENTITY", data[:65536], re.I):
        raise ToolError(ErrorCode.CORRUPT_FILE, "xml_dtd")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_comments=False)
    try:
        return fromstring(data, parser=parser, forbid_dtd=True, forbid_entities=True)
    except (DefusedXmlException, etree.XMLSyntaxError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "xml_syntax") from exc


def _stream_bytes(stream, limit: int) -> bytes:
    """Contenido de un flujo de un PDF de usuario sin descomprimirlo entero de golpe: un adjunto Flate de 200 KB puede
    inflarse a varios GB. Sin filtro o con FlateDecode sin predictor, se descomprime con un tope; cualquier otro filtro
    (LZW, RunLength, cadenas de filtros) se rechaza, porque las facturas incrustadas usan Flate."""
    import zlib

    import pikepdf

    raw = stream.read_raw_bytes()
    filters = stream.get("/Filter")
    names = [str(f) for f in filters] if isinstance(filters, pikepdf.Array) else ([str(filters)] if filters is not None else [])
    if not names:
        data = raw
    elif names == ["/FlateDecode"] and stream.get("/DecodeParms") is None:
        inflater = zlib.decompressobj()
        try:
            data = inflater.decompress(raw, limit + 1)
        except zlib.error as exc:
            raise ToolError(ErrorCode.CORRUPT_FILE, "pdf") from exc
    else:
        raise ToolError(ErrorCode.CORRUPT_FILE, "pdf_attachment_filter")
    if len(data) > limit:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"xml_size:{len(data) // 1048576}>{limit // 1048576}")
    return data


def _pdf_files(pdf) -> list[tuple[str, object]]:
    """(nombre, flujo) de los archivos incrustados de un PDF, como mucho 2 × MAX_ATTACHMENTS."""
    out = []
    for name, spec in list(pdf.attachments.items())[: 2 * MAX_ATTACHMENTS]:
        try:
            out.append((name, spec.obj.EF.F))
        except (AttributeError, KeyError):
            continue
    return out


def xml_from_pdf(path: Path) -> tuple[bytes, str, list[tuple[str, str, bytes]]] | None:
    """El XML de factura que lleva un PDF como adjunto (Factur-X, ZUGFeRD o XRechnung), con el nombre del adjunto y los
    demás archivos incrustados (los anexos de la factura, A.2), leídos con tope."""
    import pikepdf

    try:
        with pikepdf.open(path) as pdf:
            files = _pdf_files(pdf)
            names = sorted(files, key=lambda f: (f[0].lower() not in PDF_XML_NAMES, f[0]))
            chosen = None
            for name, stream in names:
                if not name.lower().endswith(".xml"):
                    continue
                data = _stream_bytes(stream, MAX_XML_BYTES)
                if name.lower() in PDF_XML_NAMES or CII.encode() in data[:4096] or b"ubl:schema" in data[:4096]:
                    chosen = (data, name)
                    break
            if chosen is None:
                return None
            others = []
            for name, stream in files:
                if name == chosen[1] or len(others) >= MAX_ATTACHMENTS:
                    continue
                try:
                    content = _stream_bytes(stream, MAX_ATTACHMENT_BYTES)
                except ToolError:
                    continue  # un anexo demasiado grande o con otro filtro no impide validar la factura
                subtype = stream.get("/Subtype")
                others.append((name, str(subtype)[1:].replace("#2F", "/") if subtype is not None else "", content))
            return chosen[0], chosen[1], others
    except pikepdf.PasswordError as exc:
        raise ToolError(ErrorCode.PASSWORD_REQUIRED) from exc
    except pikepdf.PdfError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "pdf") from exc


def _b64(text: str | None, limit: int = MAX_ATTACHMENT_BYTES) -> bytes | None:
    import base64
    import binascii

    if not text or len(text) > limit * 4 // 3 + 4096:
        return None
    try:
        return base64.b64decode("".join(text.split()), validate=True)
    except (binascii.Error, ValueError):
        return None


def attachment_name(name: str, mime: str) -> str:
    """Nombre del anexo con extensión: si no la trae, la de su tipo MIME."""
    base = Path((name or "anexo").replace("\\", "/")).name or "anexo"
    if "." not in base.strip(".") and MIME_EXT.get((mime or "").lower()):
        base = f"{base}.{MIME_EXT[mime.lower()]}"
    return base


def _t(node, path: str) -> str:
    if node is None:
        return ""
    found = node.find(path, NS)
    return (found.text or "").strip() if found is not None and found.text else ""


def _ubl(root) -> Invoice:
    credit = root.tag == f"{{{UBL_CREDIT}}}CreditNote"
    inv = Invoice("ubl", _t(root, "cbc:CustomizationID"), "abono" if credit else "factura")
    inv.number, inv.date = _t(root, "cbc:ID"), _t(root, "cbc:IssueDate")
    seller = root.find("cac:AccountingSupplierParty/cac:Party", NS)
    buyer = root.find("cac:AccountingCustomerParty/cac:Party", NS)
    inv.seller = _t(seller, "cac:PartyLegalEntity/cbc:RegistrationName") or _t(seller, "cac:PartyName/cbc:Name")
    inv.buyer = _t(buyer, "cac:PartyLegalEntity/cbc:RegistrationName") or _t(buyer, "cac:PartyName/cbc:Name")
    inv.seller_vat, inv.buyer_vat = _t(seller, "cac:PartyTaxScheme/cbc:CompanyID"), _t(buyer, "cac:PartyTaxScheme/cbc:CompanyID")
    inv.currency = _t(root, "cbc:DocumentCurrencyCode")
    inv.total = _t(root, "cac:LegalMonetaryTotal/cbc:PayableAmount")
    tag = "cac:CreditNoteLine" if credit else "cac:InvoiceLine"
    qty = "cbc:CreditedQuantity" if credit else "cbc:InvoicedQuantity"
    for line in root.findall(tag, NS)[:200]:
        inv.lines.append((_t(line, "cac:Item/cbc:Name"), _t(line, qty), _t(line, "cbc:LineExtensionAmount")))
    for ref in root.findall("cac:AdditionalDocumentReference", NS)[:MAX_ATTACHMENTS]:
        obj = ref.find("cac:Attachment/cbc:EmbeddedDocumentBinaryObject", NS)
        content = _b64(obj.text) if obj is not None else None
        if content is not None:
            inv.attachments.append((obj.get("filename") or _t(ref, "cbc:ID") or "anexo", obj.get("mimeCode", ""), content))
    return inv


def _cii(root) -> Invoice:
    inv = Invoice("cii", _t(root, "rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID"))
    inv.kind = "abono" if _t(root, "rsm:ExchangedDocument/ram:TypeCode") == "381" else "factura"
    inv.number = _t(root, "rsm:ExchangedDocument/ram:ID")
    raw = _t(root, "rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString")
    inv.date = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}" if re.fullmatch(r"\d{8}", raw) else raw
    agreement = root.find("rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeAgreement", NS)
    inv.seller, inv.buyer = _t(agreement, "ram:SellerTradeParty/ram:Name"), _t(agreement, "ram:BuyerTradeParty/ram:Name")
    inv.seller_vat = _t(agreement, "ram:SellerTradeParty/ram:SpecifiedTaxRegistration/ram:ID")
    inv.buyer_vat = _t(agreement, "ram:BuyerTradeParty/ram:SpecifiedTaxRegistration/ram:ID")
    settlement = root.find("rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeSettlement", NS)
    inv.currency = _t(settlement, "ram:InvoiceCurrencyCode")
    inv.total = _t(settlement, "ram:SpecifiedTradeSettlementHeaderMonetarySummation/ram:DuePayableAmount")
    for line in root.findall("rsm:SupplyChainTradeTransaction/ram:IncludedSupplyChainTradeLineItem", NS)[:200]:
        inv.lines.append((_t(line, "ram:SpecifiedTradeProduct/ram:Name"), _t(line, "ram:SpecifiedLineTradeDelivery/ram:BilledQuantity"),
                          _t(line, "ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount")))
    # Anexos de XRechnung CII y Factur-X EXTENDED: AdditionalReferencedDocument/AttachmentBinaryObject.
    for ref in (agreement.findall("ram:AdditionalReferencedDocument", NS)[:MAX_ATTACHMENTS] if agreement is not None else []):
        obj = ref.find("ram:AttachmentBinaryObject", NS)
        content = _b64(obj.text) if obj is not None else None
        if content is not None:
            inv.attachments.append((obj.get("filename") or _t(ref, "ram:IssuerAssignedID") or "anexo", obj.get("mimeCode", ""), content))
    return inv


def _local(node, name: str):
    for child in node.iter():
        if isinstance(child.tag, str) and child.tag.rsplit("}", 1)[-1] == name:
            return child
    return None


def _ltext(node, *names: str) -> str:
    for name in names:
        found = _local(node, name) if node is not None else None
        if found is not None and found.text:
            return found.text.strip()
    return ""


def _facturae(root, version: str) -> Invoice:
    inv = Invoice("facturae", f"Facturae {version.replace('_', '.')}")
    seller, buyer = _local(root, "SellerParty"), _local(root, "BuyerParty")
    invoice = _local(root, "Invoice")
    # InvoiceClass: OO original, OR original rectificativa, OC recapitulativa; CO, CR y CC sus copias.
    inv.kind = "abono" if _ltext(invoice, "InvoiceClass") in ("OR", "CR") else "factura"
    inv.number = (_ltext(invoice, "InvoiceSeriesCode") + _ltext(invoice, "InvoiceNumber")).strip()
    inv.date = _ltext(invoice, "IssueDate")
    inv.seller = _ltext(seller, "CorporateName", "Name")
    inv.buyer = _ltext(buyer, "CorporateName", "Name")
    inv.seller_vat, inv.buyer_vat = _ltext(seller, "TaxIdentificationNumber"), _ltext(buyer, "TaxIdentificationNumber")
    inv.currency = _ltext(invoice, "InvoiceCurrencyCode")
    inv.total = _ltext(invoice, "TotalExecutableAmount", "InvoiceTotal")
    for line in [e for e in (invoice.iter() if invoice is not None else []) if isinstance(e.tag, str) and e.tag.endswith("InvoiceLine")][:200]:
        inv.lines.append((_ltext(line, "ItemDescription"), _ltext(line, "Quantity"), _ltext(line, "TotalCost")))
    inv.signed = _local(root, "Signature") is not None
    # Anexos: Invoice/AdditionalData/RelatedDocuments/Attachment (AttachmentData en base64; sin comprimir o con ZIP).
    related = _local(invoice, "RelatedDocuments") if invoice is not None else None
    for k, att in enumerate([e for e in (related if related is not None else []) if isinstance(e.tag, str)
                             and e.tag.rsplit("}", 1)[-1] == "Attachment"][:MAX_ATTACHMENTS], 1):
        content = _b64(_ltext(att, "AttachmentData"))
        if content is None:
            continue
        fmt = _ltext(att, "AttachmentFormat").lower()
        compression = _ltext(att, "AttachmentCompressionAlgorithm").upper()
        ext = "zip" if compression == "ZIP" else fmt or "bin"
        inv.attachments.append((f"anexo-{k}.{ext}", "application/zip" if ext == "zip" else "", content))
    return inv


def read_invoice(data: bytes):
    """(árbol, datos) de una factura; `INVALID_OPTIONS` `not_invoice` si el XML no es de una sintaxis conocida."""
    root = parse_xml(data)
    ns = root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else ""
    if ns in (UBL_INVOICE, UBL_CREDIT):
        return root, _ubl(root)
    if ns == CII and root.tag.endswith("CrossIndustryInvoice"):
        return root, _cii(root)
    if ns in FACTURAE and root.tag.endswith("}Facturae"):
        return root, _facturae(root, FACTURAE[ns])
    raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "not_invoice")


def facturae_version(root) -> str:
    return FACTURAE.get(root.tag[1:].split("}", 1)[0], "")


def pretty_xml(data: bytes) -> str:
    """Texto del XML para el anexo del informe (sin reinterpretar nada)."""
    import codecs

    m = re.match(rb"<\?xml[^>]*encoding=[\"']([A-Za-z0-9._-]+)[\"']", data.lstrip(b"\xef\xbb\xbf")[:200])
    encoding = m.group(1).decode() if m else "utf-8"
    try:
        codecs.lookup(encoding)
    except LookupError:
        encoding = "utf-8"
    return io.TextIOWrapper(io.BytesIO(data), encoding=encoding, errors="replace").read()
