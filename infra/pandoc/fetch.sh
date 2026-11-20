#!/bin/sh
# pandoc estático (F6-A, D-212): binario oficial de jgm/pandoc con la versión y el SHA-256 fijados. GPL-2.0-or-later:
# solo como proceso externo en el servidor y en imágenes privadas (2.2, 3 y 11). Uso: fetch.sh <directorio destino>.
set -eu
VERSION=3.13
SHA256_AMD64=38aa33b325a2bc96a4c39409631212db55702f564250bcdbead180b3bf646389
SHA256_ARM64=21e1d4ba09bd0b334590d204580fd4f6629b21be4ab6a32b26cc98982e9e0c68
dest="$1"
case "$(uname -m)" in
  x86_64|amd64) arch=amd64; sum="$SHA256_AMD64" ;;
  aarch64|arm64) arch=arm64; sum="$SHA256_ARM64" ;;
  *) echo "arquitectura no admitida: $(uname -m)" >&2; exit 1 ;;
esac
tmp="$(mktemp -d)"
curl -fsSL -o "$tmp/pandoc.tgz" "https://github.com/jgm/pandoc/releases/download/${VERSION}/pandoc-${VERSION}-linux-${arch}.tar.gz"
echo "${sum}  $tmp/pandoc.tgz" | sha256sum -c -
tar -xzf "$tmp/pandoc.tgz" -C "$tmp"
mkdir -p "$dest"
install -m 0755 "$tmp/pandoc-${VERSION}/bin/pandoc" "$dest/pandoc"
rm -r "$tmp"
"$dest/pandoc" --version | head -1
