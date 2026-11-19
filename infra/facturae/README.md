# Esquemas de Facturae

XSD oficiales de Facturae 3.2, 3.2.1 y 3.2.2, descargados el 20/11/2026 de facturae.gob.es
(`https://www.facturae.gob.es/content/dam/facturae/formato/versiones/Facturaev3_2_2.xml` y equivalentes), y el XSD de
XMLDSig del W3C (`https://www.w3.org/TR/xmldsig-core/xmldsig-core-schema.xsd`), que importan. `SHA256SUMS` fija cada
archivo; `workers/Dockerfile` los copia a `/opt/facturae` y los comprueba. Se cargan sin red: el `import` de XMLDSig se
apunta a la copia local (`tools/utils/facturas/motores.py`). Licencias en `docs/LICENSES.md`.
