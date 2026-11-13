### A.2 Facturas

- **crear-factura** (F4, navegador):
  - Plantilla propia con logotipo.
  - Emisor y cliente con NIF/CIF.
  - Número, fecha y vencimiento.
  - Conceptos: descripción, cantidad, unidad, precio, descuento e IVA [21 %] | 10 % | 4 % | 0 %.
  - Recargo de equivalencia [no] y retención de IRPF [no] | 7 % | 15 % | personalizada.
  - Moneda [EUR], idioma, notas, forma de pago e IBAN.
  - Totales automáticos y vista previa en vivo.
  - Emisor y clientes recordados en el navegador.
  - Salida PDF.
  - Botón «Convertir en factura electrónica».
- **crear-factura-electronica** (F4, servidor; firma en el navegador; detrás de `INVOICING_ES_ENABLED`):
  - Formulario EN 16931 con validación en vivo de los campos obligatorios.
  - Formato de salida:
    - [Factur-X/ZUGFeRD], con perfil MINIMUM | BASIC WL | BASIC | [EN 16931] | EXTENDED | XRECHNUNG; MINIMUM y BASIC WL no son facturas EN 16931 completas y la interfaz lo avisa;
    - XRechnung CII | UBL;
    - Peppol BIS Billing 3.0;
    - UBL 2.1 (EN 16931), la sintaxis de la solución pública española;
    - Facturae 3.2.2, con firma XAdES-EPES opcional hecha en el navegador con xadesjs y el certificado del usuario o de su empresa (.p12 o .pfx abierto con PKI.js); la clave nunca sale del navegador.
  - Importar desde PDF: usa el flujo de pdf-a-factura-electronica.
  - Antes de entregar, valida con el mismo motor que validar-factura-electronica.
- **pdf-a-factura-electronica** (F4):
  - Perfil Factur-X [EN 16931].
  - Si el PDF trae XML, lo usa.
  - Si no:
    1. extrae los datos (texto con PDFium, reglas y una sola petición de LLM con esquema JSON, con consentimiento);
    2. muestra el formulario de revisión, que es obligatorio y tiene todos los campos editables;
    3. convierte el PDF a PDF/A-3 conservando sus páginas e incrusta el XML.
- **factura-electronica-a-pdf** (F6):
  - Entrada: CII, UBL o Facturae, en lote.
  - Salida: [PDF/A-3 con el XML original incrustado byte a byte] | PDF simple.
  - Idioma de la representación [el de la factura].
- **validar-factura-electronica** (F4, servidor):
  - Detecta la sintaxis y la especificación por `CustomizationID` o por el contexto del documento.
  - Reglas: EN 16931, XRechnung, Peppol BIS, Factur-X/ZUGFeRD y Facturae (XSD y firma), con los escenarios de KoSIT descritos en 7.23.
  - Resultado por regla:
    - identificador, gravedad, explicación propia en lenguaje sencillo para las frecuentes y qué hacer;
    - campo afectado resaltado sobre la representación de la factura.
  - Se puede ver, imprimir o guardar como PDF, y abrir los anexos.
  - Lote o ZIP, con resumen (número, emisor, fecha, total y resultado) exportable a CSV.
  - El archivo se borra al terminar.
