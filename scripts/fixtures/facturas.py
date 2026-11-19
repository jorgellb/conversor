"""Muestras de F4-D: facturas electrónicas escritas a mano con datos ficticios (01-1, regla 8).

- UBL 2.1: EN 16931 puro, XRechnung 3.0 y Peppol BIS Billing 3.0 (factura).
- CII D16B: EN 16931 (perfil EN 16931 de Factur-X), Factur-X BASIC y MINIMUM.
- Facturae 3.2.2 sin firmar.
- Errores conocidos: total que no cuadra (BR-CO-15), sin nombre del comprador (BR-07) y un XML que no es una factura.

Cada función devuelve bytes; `generate(out)` escribe todas las muestras en `out/facturas/`.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

LINES = [("Licencia anual del portal", Decimal("1"), Decimal("1200.00")), ("Horas de soporte", Decimal("10"), Decimal("45.50"))]
VAT = Decimal("21")
SELLER = {"name": "Ejemplo Servicios SL", "vat": "ESB12345674", "street": "Calle Mayor 1", "city": "Madrid", "zip": "28013",
          "country": "ES", "email": "facturas@ejemplo.test"}
BUYER = {"name": "Cliente Pruebas SA", "vat": "ESA87654322", "street": "Avenida del Puerto 20", "city": "Valencia", "zip": "46021",
         "country": "ES", "email": "compras@cliente.test"}
UBL_EN16931 = "urn:cen.eu:en16931:2017"
UBL_XRECHNUNG = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
UBL_PEPPOL = "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
CII_EN16931 = "urn:cen.eu:en16931:2017"
CII_BASIC = "urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic"
CII_MINIMUM = "urn:factur-x.eu:1p0:minimum"


def _q(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def totals(lines=LINES) -> tuple[Decimal, Decimal, Decimal]:
    net = sum((qty * price for _n, qty, price in lines), Decimal("0"))
    tax = (net * VAT / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return net, tax, net + tax


def ubl_invoice(customization: str = UBL_EN16931, *, number: str = "F-2026-0042", payable_delta: Decimal = Decimal("0"),
                buyer_name: str | None = BUYER["name"]) -> bytes:
    net, tax, gross = totals()
    lines = "".join(f"""
  <cac:InvoiceLine>
    <cbc:ID>{i}</cbc:ID>
    <cbc:InvoicedQuantity unitCode="C62">{qty}</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="EUR">{_q(qty * price)}</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Name>{name}</cbc:Name>
      <cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>{VAT}</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory>
    </cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="EUR">{_q(price)}</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>""" for i, (name, qty, price) in enumerate(LINES, 1))
    peppol = customization == UBL_PEPPOL
    xrechnung = customization == UBL_XRECHNUNG
    profile = "<cbc:ProfileID>urn:fdc:peppol.eu:2017:poacc:billing:01:1.0</cbc:ProfileID>" if peppol or xrechnung else ""
    buyer_ref = "<cbc:BuyerReference>04011000-12345-34</cbc:BuyerReference>" if xrechnung else (
        "<cbc:BuyerReference>PED-2026-7</cbc:BuyerReference>" if peppol else "")
    # Dirección electrónica (BT-34/BT-49): en Peppol, un código EAS (9920, NIF español); en XRechnung vale el correo (EM).
    endpoint = lambda who: (f'<cbc:EndpointID schemeID="9920">{who["vat"]}</cbc:EndpointID>' if peppol  # noqa: E731
                            else f'<cbc:EndpointID schemeID="EM">{who["email"]}</cbc:EndpointID>' if xrechnung else "")
    contact = (f"""<cac:Contact><cbc:Name>Departamento de facturación</cbc:Name><cbc:Telephone>+34 910 000 000</cbc:Telephone>
        <cbc:ElectronicMail>{SELLER["email"]}</cbc:ElectronicMail></cac:Contact>""" if xrechnung else "")
    buyer_party_name = f"<cac:PartyLegalEntity><cbc:RegistrationName>{buyer_name}</cbc:RegistrationName></cac:PartyLegalEntity>" if buyer_name else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:CustomizationID>{customization}</cbc:CustomizationID>
  {profile}
  <cbc:ID>{number}</cbc:ID>
  <cbc:IssueDate>2026-11-02</cbc:IssueDate>
  <cbc:DueDate>2026-12-02</cbc:DueDate>
  <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
  <cbc:Note>Factura de prueba del portal</cbc:Note>
  <cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
  {buyer_ref}
  <cac:AccountingSupplierParty>
    <cac:Party>
      {endpoint(SELLER)}
      <cac:PostalAddress><cbc:StreetName>{SELLER["street"]}</cbc:StreetName><cbc:CityName>{SELLER["city"]}</cbc:CityName>
        <cbc:PostalZone>{SELLER["zip"]}</cbc:PostalZone><cac:Country><cbc:IdentificationCode>{SELLER["country"]}</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
      <cac:PartyTaxScheme><cbc:CompanyID>{SELLER["vat"]}</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>
      <cac:PartyLegalEntity><cbc:RegistrationName>{SELLER["name"]}</cbc:RegistrationName></cac:PartyLegalEntity>
      {contact}
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      {endpoint(BUYER)}
      <cac:PostalAddress><cbc:StreetName>{BUYER["street"]}</cbc:StreetName><cbc:CityName>{BUYER["city"]}</cbc:CityName>
        <cbc:PostalZone>{BUYER["zip"]}</cbc:PostalZone><cac:Country><cbc:IdentificationCode>{BUYER["country"]}</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
      <cac:PartyTaxScheme><cbc:CompanyID>{BUYER["vat"]}</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>
      {buyer_party_name}
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:PaymentMeans>
    <cbc:PaymentMeansCode>58</cbc:PaymentMeansCode>
    <cac:PayeeFinancialAccount><cbc:ID>ES9121000418450200051332</cbc:ID></cac:PayeeFinancialAccount>
  </cac:PaymentMeans>
  <cac:PaymentTerms><cbc:Note>Pago a 30 días</cbc:Note></cac:PaymentTerms>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="EUR">{_q(tax)}</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="EUR">{_q(net)}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="EUR">{_q(tax)}</cbc:TaxAmount>
      <cac:TaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>{VAT}</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:TaxCategory>
    </cac:TaxSubtotal>
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="EUR">{_q(net)}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="EUR">{_q(net)}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="EUR">{_q(gross)}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="EUR">{_q(gross + payable_delta)}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>{lines}
</Invoice>
""".encode()


def cii_invoice(guideline: str = CII_EN16931, *, number: str = "F-2026-0043", payable_delta: Decimal = Decimal("0"),
                attachment: bytes | None = None) -> bytes:
    """CII D16B; con `attachment`, un anexo sin extensión en el nombre (AdditionalReferencedDocument, tipo MIME PDF)."""
    import base64

    net, tax, gross = totals()
    extra = "" if attachment is None else f"""
      <ram:AdditionalReferencedDocument><ram:IssuerAssignedID>ALB-7</ram:IssuerAssignedID><ram:TypeCode>916</ram:TypeCode>
        <ram:AttachmentBinaryObject mimeCode="application/pdf" filename="albaran">{base64.b64encode(attachment).decode()}</ram:AttachmentBinaryObject>
      </ram:AdditionalReferencedDocument>"""
    minimum = guideline == CII_MINIMUM
    lines = "" if minimum else "".join(f"""
    <ram:IncludedSupplyChainTradeLineItem>
      <ram:AssociatedDocumentLineDocument><ram:LineID>{i}</ram:LineID></ram:AssociatedDocumentLineDocument>
      <ram:SpecifiedTradeProduct><ram:Name>{name}</ram:Name></ram:SpecifiedTradeProduct>
      <ram:SpecifiedLineTradeAgreement><ram:NetPriceProductTradePrice><ram:ChargeAmount>{_q(price)}</ram:ChargeAmount></ram:NetPriceProductTradePrice></ram:SpecifiedLineTradeAgreement>
      <ram:SpecifiedLineTradeDelivery><ram:BilledQuantity unitCode="C62">{qty}</ram:BilledQuantity></ram:SpecifiedLineTradeDelivery>
      <ram:SpecifiedLineTradeSettlement>
        <ram:ApplicableTradeTax><ram:TypeCode>VAT</ram:TypeCode><ram:CategoryCode>S</ram:CategoryCode><ram:RateApplicablePercent>{VAT}</ram:RateApplicablePercent></ram:ApplicableTradeTax>
        <ram:SpecifiedTradeSettlementLineMonetarySummation><ram:LineTotalAmount>{_q(qty * price)}</ram:LineTotalAmount></ram:SpecifiedTradeSettlementLineMonetarySummation>
      </ram:SpecifiedLineTradeSettlement>
    </ram:IncludedSupplyChainTradeLineItem>""" for i, (name, qty, price) in enumerate(LINES, 1))
    party = lambda who, tag: f"""<ram:{tag}>
        <ram:Name>{who["name"]}</ram:Name>
        {"" if minimum and tag == "BuyerTradeParty" else (f'<ram:PostalTradeAddress><ram:CountryID>{who["country"]}</ram:CountryID></ram:PostalTradeAddress>' if minimum else f'<ram:PostalTradeAddress><ram:PostcodeCode>{who["zip"]}</ram:PostcodeCode><ram:LineOne>{who["street"]}</ram:LineOne><ram:CityName>{who["city"]}</ram:CityName><ram:CountryID>{who["country"]}</ram:CountryID></ram:PostalTradeAddress>')}
        {"" if minimum and tag == "BuyerTradeParty" else f'<ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">{who["vat"]}</ram:ID></ram:SpecifiedTaxRegistration>'}
      </ram:{tag}>"""  # noqa: E731
    settlement_tax = "" if minimum else f"""
      <ram:ApplicableTradeTax>
        <ram:CalculatedAmount>{_q(tax)}</ram:CalculatedAmount><ram:TypeCode>VAT</ram:TypeCode>
        <ram:BasisAmount>{_q(net)}</ram:BasisAmount><ram:CategoryCode>S</ram:CategoryCode><ram:RateApplicablePercent>{VAT}</ram:RateApplicablePercent>
      </ram:ApplicableTradeTax>
      <ram:SpecifiedTradePaymentTerms><ram:DueDateDateTime><udt:DateTimeString format="102">20261202</udt:DateTimeString></ram:DueDateDateTime></ram:SpecifiedTradePaymentTerms>"""
    means = "" if minimum else """
      <ram:SpecifiedTradeSettlementPaymentMeans><ram:TypeCode>58</ram:TypeCode>
        <ram:PayeePartyCreditorFinancialAccount><ram:IBANID>ES9121000418450200051332</ram:IBANID></ram:PayeePartyCreditorFinancialAccount>
      </ram:SpecifiedTradeSettlementPaymentMeans>"""
    line_total = "" if minimum else f"<ram:LineTotalAmount>{_q(net)}</ram:LineTotalAmount>"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
    xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
    xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"
    xmlns:qdt="urn:un:unece:uncefact:data:standard:QualifiedDataType:100">
  <rsm:ExchangedDocumentContext>
    <ram:GuidelineSpecifiedDocumentContextParameter><ram:ID>{guideline}</ram:ID></ram:GuidelineSpecifiedDocumentContextParameter>
  </rsm:ExchangedDocumentContext>
  <rsm:ExchangedDocument>
    <ram:ID>{number}</ram:ID>
    <ram:TypeCode>380</ram:TypeCode>
    <ram:IssueDateTime><udt:DateTimeString format="102">20261102</udt:DateTimeString></ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>{lines}
    <ram:ApplicableHeaderTradeAgreement>
      {party(SELLER, "SellerTradeParty")}
      {party(BUYER, "BuyerTradeParty")}{extra}
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeDelivery/>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>{means}{settlement_tax}
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        {line_total}
        <ram:TaxBasisTotalAmount>{_q(net)}</ram:TaxBasisTotalAmount>
        <ram:TaxTotalAmount currencyID="EUR">{_q(tax)}</ram:TaxTotalAmount>
        <ram:GrandTotalAmount>{_q(gross)}</ram:GrandTotalAmount>
        <ram:DuePayableAmount>{_q(gross + payable_delta)}</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>
""".encode()


FACTURAE_NS = {"3.2": "http://www.facturae.es/Facturae/2009/v3.2/Facturae",
               "3.2.1": "http://www.facturae.es/Facturae/2014/v3.2.1/Facturae",
               "3.2.2": "http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_2.xml"}


def facturae(*, number: str = "42", series: str = "F2026", version: str = "3.2.2", attachment: bytes | None = None) -> bytes:
    """Facturae 3.2, 3.2.1 o 3.2.2 (mismo contenido; cambian el espacio de nombres y SchemaVersion); con `attachment`,
    un PDF en AdditionalData/RelatedDocuments."""
    import base64
    net, tax, gross = totals()

    def party(who, role):
        return f"""<{role}>
      <TaxIdentification><PersonTypeCode>J</PersonTypeCode><ResidenceTypeCode>R</ResidenceTypeCode><TaxIdentificationNumber>{who["vat"][2:]}</TaxIdentificationNumber></TaxIdentification>
      <LegalEntity><CorporateName>{who["name"]}</CorporateName>
        <AddressInSpain><Address>{who["street"]}</Address><PostCode>{who["zip"]}</PostCode><Town>{who["city"]}</Town><Province>{who["city"]}</Province><CountryCode>ESP</CountryCode></AddressInSpain>
      </LegalEntity>
    </{role}>"""

    def six(value):  # 3.2 pide seis decimales en los importes de las líneas (DoubleSixDecimalType)
        return f"{value:.6f}" if version == "3.2" else _q(value)

    items = "".join(f"""
        <InvoiceLine>
          <ItemDescription>{name}</ItemDescription><Quantity>{qty}</Quantity><UnitOfMeasure>01</UnitOfMeasure>
          <UnitPriceWithoutTax>{six(price)}</UnitPriceWithoutTax><TotalCost>{six(qty * price)}</TotalCost><GrossAmount>{six(qty * price)}</GrossAmount>
          <TaxesOutputs><Tax><TaxTypeCode>01</TaxTypeCode><TaxRate>{VAT}.00</TaxRate>
            <TaxableBase><TotalAmount>{_q(qty * price)}</TotalAmount></TaxableBase>
            <TaxAmount><TotalAmount>{_q(qty * price * VAT / 100)}</TotalAmount></TaxAmount></Tax></TaxesOutputs>
        </InvoiceLine>""" for name, qty, price in LINES)
    related = "" if attachment is None else f"""
      <AdditionalData><RelatedDocuments><Attachment><AttachmentFormat>pdf</AttachmentFormat><AttachmentEncoding>BASE64</AttachmentEncoding>
        <AttachmentDescription>Albarán</AttachmentDescription><AttachmentData>{base64.b64encode(attachment).decode()}</AttachmentData></Attachment></RelatedDocuments></AdditionalData>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<fe:Facturae xmlns:fe="{FACTURAE_NS[version]}" xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <FileHeader>
    <SchemaVersion>{version}</SchemaVersion><Modality>I</Modality><InvoiceIssuerType>EM</InvoiceIssuerType>
    <Batch><BatchIdentifier>{SELLER["vat"][2:]}{series}{number}</BatchIdentifier><InvoicesCount>1</InvoicesCount>
      <TotalInvoicesAmount><TotalAmount>{_q(gross)}</TotalAmount></TotalInvoicesAmount>
      <TotalOutstandingAmount><TotalAmount>{_q(gross)}</TotalAmount></TotalOutstandingAmount>
      <TotalExecutableAmount><TotalAmount>{_q(gross)}</TotalAmount></TotalExecutableAmount>
      <InvoiceCurrencyCode>EUR</InvoiceCurrencyCode></Batch>
  </FileHeader>
  <Parties>
    {party(SELLER, "SellerParty")}
    {party(BUYER, "BuyerParty")}
  </Parties>
  <Invoices>
    <Invoice>
      <InvoiceHeader><InvoiceNumber>{number}</InvoiceNumber><InvoiceSeriesCode>{series}</InvoiceSeriesCode>
        <InvoiceDocumentType>FC</InvoiceDocumentType><InvoiceClass>OO</InvoiceClass></InvoiceHeader>
      <InvoiceIssueData><IssueDate>2026-11-02</IssueDate><InvoiceCurrencyCode>EUR</InvoiceCurrencyCode><TaxCurrencyCode>EUR</TaxCurrencyCode><LanguageName>es</LanguageName></InvoiceIssueData>
      <TaxesOutputs><Tax><TaxTypeCode>01</TaxTypeCode><TaxRate>{VAT}.00</TaxRate>
        <TaxableBase><TotalAmount>{_q(net)}</TotalAmount></TaxableBase><TaxAmount><TotalAmount>{_q(tax)}</TotalAmount></TaxAmount></Tax></TaxesOutputs>
      <InvoiceTotals>
        <TotalGrossAmount>{_q(net)}</TotalGrossAmount><TotalGrossAmountBeforeTaxes>{_q(net)}</TotalGrossAmountBeforeTaxes>
        <TotalTaxOutputs>{_q(tax)}</TotalTaxOutputs><TotalTaxesWithheld>0.00</TotalTaxesWithheld>
        <InvoiceTotal>{_q(gross)}</InvoiceTotal><TotalOutstandingAmount>{_q(gross)}</TotalOutstandingAmount><TotalExecutableAmount>{_q(gross)}</TotalExecutableAmount>
      </InvoiceTotals>
      <Items>{items}
      </Items>
      <PaymentDetails><Installment><InstallmentDueDate>2026-12-02</InstallmentDueDate><InstallmentAmount>{_q(gross)}</InstallmentAmount>
        <PaymentMeans>04</PaymentMeans><AccountToBeCredited><IBAN>ES9121000418450200051332</IBAN></AccountToBeCredited></Installment></PaymentDetails>{related}
    </Invoice>
  </Invoices>
</fe:Facturae>
""".encode()


SAMPLES = {
    "ubl-en16931.xml": lambda: ubl_invoice(UBL_EN16931),
    "ubl-xrechnung.xml": lambda: ubl_invoice(UBL_XRECHNUNG),
    "ubl-peppol.xml": lambda: ubl_invoice(UBL_PEPPOL),
    "cii-en16931.xml": lambda: cii_invoice(CII_EN16931),
    "cii-basic.xml": lambda: cii_invoice(CII_BASIC),
    "cii-minimum.xml": lambda: cii_invoice(CII_MINIMUM),
    "facturae-322.xml": facturae,
    "ubl-total-mal.xml": lambda: ubl_invoice(UBL_EN16931, number="F-2026-0099", payable_delta=Decimal("10")),
    "ubl-sin-comprador.xml": lambda: ubl_invoice(UBL_EN16931, number="F-2026-0098", buyer_name=None),
    "no-es-factura.xml": lambda: b'<?xml version="1.0"?><pedido><numero>1</numero></pedido>',
}


def generate(out: Path) -> dict[str, Path]:
    folder = out / "facturas"
    folder.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, make in SAMPLES.items():
        path = folder / name
        path.write_bytes(make())
        files[f"facturas/{name}"] = path
    return files


if __name__ == "__main__":
    import sys

    print(generate(Path(sys.argv[1] if len(sys.argv) > 1 else "muestras-facturas")))
