#!/bin/sh
# KoSIT Validator 1.6.3 (Apache-2.0) y las configuraciones públicas de XRechnung 3.0.2 (2026-08-31) y Peppol BIS 3.0.21,
# con SHA-256 fijados (01-1, regla 2), y el repositorio de escenarios de /opt/kosit (D-191):
#   <destino>/validator   jar y bibliotecas de KoSIT
#   <destino>/xrechnung   configuración de XRechnung (incluye el EN 16931 puro de UBL y CII)
#   <destino>/bis         configuración de Peppol BIS
#   <destino>/facturx     XSD y Schematron de Factur-X 1.09 que trae el paquete factur-x (segundo argumento)
#   <destino>/conversor   escenarios propios (infra/kosit/scenarios.xml, tercer argumento)
#   sh infra/kosit/fetch.sh /opt/kosit <ruta de facturx/xsd_and_schematron> infra/kosit/scenarios.xml
set -eu
DEST="$1"; FACTURX="$2"; SCENARIOS="$3"
BASE=https://github.com
VALIDATOR_SHA256=95d5a399ff5186dae5ddb7edd9a14a9c8352610159a90bfa27d4739a8bc37822
XRECHNUNG_SHA256=2530cd107c414511c5d0462ec10f886910395abfca820db82e83d70bf01221a8
BIS_SHA256=399395de5f6240a76ccc5751e4ee9dd329e37f5f7cfe4ee5c93188294ce8cd68
TMP=$(mktemp -d)
curl -fsSL -o "$TMP/validator.zip" "$BASE/itplr-kosit/validator/releases/download/v1.6.3/validator-1.6.3.zip"
curl -fsSL -o "$TMP/xrechnung.zip" "$BASE/itplr-kosit/validator-configuration-xrechnung/releases/download/v2026-08-31/xrechnung-3.0.2-validator-configuration-2026-08-31.zip"
curl -fsSL -o "$TMP/bis.zip" "$BASE/itplr-kosit/validator-configuration-bis/releases/download/release-3.0.21/validation-configuration-bis-3.0.21.zip"
printf '%s  %s\n%s  %s\n%s  %s\n' "$VALIDATOR_SHA256" "$TMP/validator.zip" "$XRECHNUNG_SHA256" "$TMP/xrechnung.zip" \
  "$BIS_SHA256" "$TMP/bis.zip" | sha256sum -c -
mkdir -p "$DEST/validator" "$DEST/xrechnung" "$DEST/bis" "$DEST/conversor"
python3 -c "import sys, zipfile; [zipfile.ZipFile(z).extractall(d) for z, d in zip(sys.argv[1::2], sys.argv[2::2])]" \
  "$TMP/validator.zip" "$DEST/validator" "$TMP/xrechnung.zip" "$DEST/xrechnung" "$TMP/bis.zip" "$DEST/bis"
cp -r "$FACTURX" "$DEST/facturx"
cp "$SCENARIOS" "$DEST/conversor/scenarios.xml"
rm -rf "$TMP"
test -f "$DEST/validator/validator-1.6.3.jar"
