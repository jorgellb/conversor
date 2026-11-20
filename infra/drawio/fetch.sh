#!/bin/sh
# Visor de draw.io (F6-K, D-227): viewer-static.min.js de jgraph/drawio, Apache-2.0, versión y SHA-256 fijados.
# Uso: fetch.sh <directorio destino>. Descarga con Python (la imagen de workeroffice no lleva curl).
set -eu
VERSION=v32.6.10
SHA256=35b8ef54369e938ad2399d3c8ce3945591d4b200a01f6942d0e39743bea1f1a1
mkdir -p "$1"
python3 -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" \
  "https://raw.githubusercontent.com/jgraph/drawio/${VERSION}/src/main/webapp/js/viewer-static.min.js" "$1/viewer-static.min.js"
echo "${SHA256}  $1/viewer-static.min.js" | sha256sum -c -
