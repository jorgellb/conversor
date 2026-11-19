"""Explicaciones propias en lenguaje sencillo de las reglas frecuentes (A.2) y qué hacer, en español y en inglés.

Los identificadores son los de las reglas de negocio de EN 16931 (BR-…, BR-CO-…, BR-S-…, BR-CL-…), de Peppol BIS y de
XRechnung (BR-DE-…). Las que no están aquí salen con el texto del motor y una explicación por familia.
"""
from __future__ import annotations

RULES: dict[str, tuple[str, str, str, str]] = {
    # código: (qué pasa es, qué hacer es, qué pasa en, qué hacer en)
    "BR-01": ("Falta el identificador de la especificación (BT-24).", "Indica la especificación, por ejemplo urn:cen.eu:en16931:2017.",
              "The specification identifier (BT-24) is missing.", "State the specification, for example urn:cen.eu:en16931:2017."),
    "BR-02": ("Falta el número de factura (BT-1).", "Pon el número de la factura.", "The invoice number (BT-1) is missing.", "Add the invoice number."),
    "BR-03": ("Falta la fecha de emisión (BT-2).", "Pon la fecha de la factura.", "The issue date (BT-2) is missing.", "Add the invoice date."),
    "BR-04": ("Falta el tipo de factura (BT-3).", "Usa 380 para una factura o 381 para un abono.", "The invoice type code (BT-3) is missing.",
              "Use 380 for an invoice or 381 for a credit note."),
    "BR-05": ("Falta la moneda de la factura (BT-5).", "Indica la moneda, por ejemplo EUR.", "The invoice currency (BT-5) is missing.", "State the currency, for example EUR."),
    "BR-06": ("Falta el nombre del vendedor (BT-27).", "Pon la razón social del emisor.", "The seller name (BT-27) is missing.", "Add the issuer's legal name."),
    "BR-07": ("Falta el nombre del comprador (BT-44).", "Pon la razón social o el nombre del cliente.", "The buyer name (BT-44) is missing.",
              "Add the customer's legal name."),
    "BR-08": ("Falta la dirección del vendedor (BG-5).", "Añade la dirección postal del emisor.", "The seller postal address (BG-5) is missing.",
              "Add the issuer's postal address."),
    "BR-09": ("Falta el país del vendedor (BT-40).", "Indica el código de país, por ejemplo ES.", "The seller country (BT-40) is missing.",
              "State the country code, for example ES."),
    "BR-10": ("Falta la dirección del comprador (BG-8).", "Añade la dirección postal del cliente.", "The buyer postal address (BG-8) is missing.",
              "Add the customer's postal address."),
    "BR-11": ("Falta el país del comprador (BT-55).", "Indica el código de país del cliente.", "The buyer country (BT-55) is missing.",
              "State the customer's country code."),
    "BR-12": ("Falta la suma de los importes netos de las líneas (BT-106).", "Revisa los totales de la factura.",
              "The sum of line net amounts (BT-106) is missing.", "Check the invoice totals."),
    "BR-13": ("Falta el total sin IVA (BT-109).", "Revisa los totales de la factura.", "The total without VAT (BT-109) is missing.", "Check the invoice totals."),
    "BR-14": ("Falta el total con IVA (BT-112).", "Revisa los totales de la factura.", "The total with VAT (BT-112) is missing.", "Check the invoice totals."),
    "BR-15": ("Falta el importe a pagar (BT-115).", "Revisa los totales de la factura.", "The amount due (BT-115) is missing.", "Check the invoice totals."),
    "BR-16": ("La factura no tiene ninguna línea.", "Añade al menos una línea con lo que se factura.", "The invoice has no lines.",
              "Add at least one line with what is invoiced."),
    "BR-21": ("Una línea no tiene identificador (BT-126).", "Numera las líneas.", "A line has no identifier (BT-126).", "Number the lines."),
    "BR-22": ("Una línea no tiene cantidad (BT-129).", "Pon la cantidad de cada línea.", "A line has no quantity (BT-129).", "Add the quantity of every line."),
    "BR-23": ("Una línea no tiene unidad de medida (BT-130).", "Usa un código UN/ECE, por ejemplo C62 (unidad) o HUR (hora).",
              "A line has no unit of measure (BT-130).", "Use a UN/ECE code, for example C62 (unit) or HUR (hour)."),
    "BR-24": ("Una línea no tiene importe neto (BT-131).", "Pon el importe de cada línea.", "A line has no net amount (BT-131).", "Add the amount of every line."),
    "BR-25": ("Una línea no tiene descripción (BT-153).", "Describe lo que se factura en cada línea.", "A line has no item name (BT-153).", "Describe what is invoiced on every line."),
    "BR-26": ("Una línea no tiene precio (BT-146).", "Pon el precio unitario de cada línea.", "A line has no price (BT-146).", "Add the unit price of every line."),
    "BR-CO-10": ("La suma de las líneas no coincide con BT-106.", "Recalcula la suma de los importes netos de las líneas.",
                 "The sum of the lines does not match BT-106.", "Recalculate the sum of the line net amounts."),
    "BR-CO-13": ("El total sin IVA no cuadra con las líneas, descuentos y recargos.", "Recalcula BT-109.",
                 "The total without VAT does not match lines, allowances and charges.", "Recalculate BT-109."),
    "BR-CO-14": ("El IVA total no es la suma del IVA de cada tipo.", "Recalcula BT-110 desde el desglose de IVA.",
                 "The total VAT is not the sum of each VAT breakdown.", "Recalculate BT-110 from the VAT breakdown."),
    "BR-CO-15": ("El total con IVA no es el total sin IVA más el IVA.", "Recalcula BT-112.",
                 "The total with VAT is not the total without VAT plus VAT.", "Recalculate BT-112."),
    "BR-CO-16": ("El importe a pagar no cuadra: debería ser el total con IVA menos lo ya pagado más el redondeo.",
                 "Revisa BT-115, BT-113 y BT-114.", "The amount due does not add up: it should be the total with VAT minus the paid amount plus rounding.",
                 "Check BT-115, BT-113 and BT-114."),
    "BR-CO-17": ("El IVA de un tipo no es la base por el porcentaje.", "Recalcula la cuota de IVA de ese tipo y redondea a 2 decimales.",
                 "A VAT amount is not the taxable amount times the rate.", "Recalculate that VAT amount and round to 2 decimals."),
    "BR-CO-25": ("Hay importe a pagar pero no fecha de vencimiento ni condiciones de pago.", "Añade la fecha de vencimiento (BT-9) o las condiciones (BT-20).",
                 "There is an amount due but no due date or payment terms.", "Add the due date (BT-9) or the payment terms (BT-20)."),
    "BR-S-08": ("La base de IVA de un tipo no cuadra con sus líneas.", "Recalcula la base imponible del tipo general (S).",
                "The VAT taxable amount of a rate does not match its lines.", "Recalculate the standard-rate (S) taxable amount."),
    "BR-S-02": ("Hay IVA general pero falta el NIF-IVA del vendedor.", "Añade el NIF con prefijo de país (BT-31), por ejemplo ESB12345674.",
                "There is standard VAT but the seller VAT ID is missing.", "Add the VAT ID with country prefix (BT-31), for example ESB12345674."),
    "BR-CL-01": ("El tipo de documento no está en la lista UNTDID 1001.", "Usa 380 (factura) o 381 (abono).",
                 "The document type is not in the UNTDID 1001 list.", "Use 380 (invoice) or 381 (credit note)."),
    "BR-CL-03": ("La moneda de un importe (atributo currencyID) no es un código ISO 4217.", "Pon en cada importe la moneda de tres letras, por ejemplo EUR.",
                 "The currency of an amount (currencyID attribute) is not an ISO 4217 code.", "Give each amount a three-letter currency, for example EUR."),
    "BR-CL-04": ("La moneda de la factura (BT-5) no es un código ISO 4217.", "Usa el código de tres letras, por ejemplo EUR.",
                 "The invoice currency (BT-5) is not an ISO 4217 code.", "Use the three-letter code, for example EUR."),
    "BR-CO-26": ("No hay ningún identificador del vendedor (BT-29, BT-30 o BT-31).", "Añade al menos el NIF-IVA del vendedor (BT-31) o su registro mercantil (BT-30).",
                 "There is no seller identifier (BT-29, BT-30 or BT-31).", "Add at least the seller VAT ID (BT-31) or its legal registration ID (BT-30)."),
    "BR-DE-2": ("XRechnung pide los datos de contacto del vendedor (BG-6).", "Añade nombre, teléfono y correo de contacto del vendedor (BT-41, BT-42 y BT-43).",
                "XRechnung requires the seller contact (BG-6).", "Add the seller contact name, phone and email (BT-41, BT-42 and BT-43)."),
    "PEPPOL-EN16931-R008": ("El documento tiene elementos vacíos.", "Quita los elementos sin contenido o rellénalos.",
                            "The document contains empty elements.", "Remove the empty elements or fill them in."),
    "BR-CL-14": ("El país no es un código ISO 3166-1.", "Usa el código de dos letras, por ejemplo ES.", "The country is not an ISO 3166-1 code.",
                 "Use the two-letter code, for example ES."),
    "BR-CL-23": ("La unidad de medida no está en la lista UN/ECE 20 o 21.", "Usa por ejemplo C62 (unidad), HUR (hora) o KGM (kilo).",
                 "The unit of measure is not in the UN/ECE 20 or 21 list.", "Use for example C62 (unit), HUR (hour) or KGM (kilogram)."),
    "PEPPOL-EN16931-R001": ("Falta el identificador del proceso de negocio (BT-23).", "Pon urn:fdc:peppol.eu:2017:poacc:billing:01:1.0.",
                            "The business process (BT-23) is missing.", "Use urn:fdc:peppol.eu:2017:poacc:billing:01:1.0."),
    "PEPPOL-EN16931-R010": ("Falta la dirección electrónica del comprador (BT-49).", "Añade su identificador Peppol (por ejemplo 9920 y el NIF).",
                            "The buyer electronic address (BT-49) is missing.", "Add their Peppol identifier (for example 9920 and the VAT ID)."),
    "PEPPOL-EN16931-R020": ("Falta la dirección electrónica del vendedor (BT-34).", "Añade tu identificador Peppol.",
                            "The seller electronic address (BT-34) is missing.", "Add your Peppol identifier."),
    "PEPPOL-EN16931-CL008": ("El esquema de la dirección electrónica no está en la lista EAS.", "Usa un código EAS, por ejemplo 9920 (NIF español) o 0088 (GLN).",
                             "The electronic address scheme is not in the EAS list.", "Use an EAS code, for example 9920 (Spanish VAT) or 0088 (GLN)."),
    "BR-DE-1": ("XRechnung pide los datos de pago (BG-16).", "Añade el medio de pago y el IBAN.", "XRechnung requires payment instructions (BG-16).",
                "Add the payment means and the IBAN."),
    "BR-DE-15": ("XRechnung pide la referencia del comprador (Leitweg-ID, BT-10).", "Pide al cliente público su Leitweg-ID y ponla en BT-10.",
                 "XRechnung requires the buyer reference (Leitweg-ID, BT-10).", "Ask the public customer for their Leitweg-ID and put it in BT-10."),
    "XSD": ("La estructura del XML no sigue el esquema oficial.", "Revisa el elemento indicado: falta, sobra o está en otro orden.",
            "The XML structure does not follow the official schema.", "Check the element shown: it is missing, extra or in the wrong order."),
    "FIRMA": ("La firma electrónica de la factura no es válida: el documento cambió después de firmar o la firma está dañada.",
              "Pide al emisor la factura original firmada.", "The invoice's electronic signature is not valid: the document changed after signing or the signature is damaged.",
              "Ask the issuer for the original signed invoice."),
}

FAMILY = {
    "es": {"BR-CO": "Un cálculo o una relación entre importes no cuadra.", "BR-CL": "Un código no está en la lista oficial que corresponde.",
           "BR-DE": "Una regla propia de XRechnung (Alemania).", "PEPPOL": "Una regla propia de la red Peppol.",
           "FX": "Una regla propia de Factur-X/ZUGFeRD.", "BR": "Una regla de negocio de la norma EN 16931.", "cvc": "La estructura del XML no sigue el esquema.",
           "": "Una regla del motor de validación."},
    "en": {"BR-CO": "A calculation or a relation between amounts does not add up.", "BR-CL": "A code is not in the matching official list.",
           "BR-DE": "An XRechnung rule (Germany).", "PEPPOL": "A Peppol network rule.", "FX": "A Factur-X/ZUGFeRD rule.",
           "BR": "A business rule of the EN 16931 standard.", "cvc": "The XML structure does not follow the schema.", "": "A rule of the validation engine."},
}


def explain(code: str, locale: str) -> tuple[str, str]:
    """(qué pasa, qué hacer) en lenguaje sencillo; sin entrada propia, la explicación de su familia y sin consejo."""
    en = locale == "en"
    if code in RULES:
        r = RULES[code]
        return (r[2], r[3]) if en else (r[0], r[1])
    family = FAMILY["en" if en else "es"]
    for prefix in ("BR-CO", "BR-CL", "BR-DE", "PEPPOL", "FX", "BR", "cvc"):
        if code.startswith(prefix):
            return family[prefix], ""
    return family[""], ""
