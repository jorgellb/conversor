#!/bin/sh
# Tectonic 0.17.0 (F6-K, D-227), MIT, binario musl con su SHA-256, y su caché de paquetes llena con los documentos de
# infra/tectonic/precarga.tex: en el trabajo se compila con --only-cached y sin red. Uso: fetch.sh <bin> <caché>.
set -eu
VERSION=0.17.0
SHA256_AMD64=8533d07f9ccbd7a65824b9e0459041bca34af1eb33daba48f59215593753a3b7
SHA256_ARM64=b10954a95404f3ab2328d2fa59a5ebab8e657f893fab096f98be8db7c0c979b8
case "$(uname -m)" in
  x86_64|amd64) arch=x86_64; sum="$SHA256_AMD64" ;;
  aarch64|arm64) arch=aarch64; sum="$SHA256_ARM64" ;;
  *) echo "arquitectura no admitida" >&2; exit 1 ;;
esac
tmp="$(mktemp -d)"
curl -fsSL -o "$tmp/t.tgz" "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${VERSION}/tectonic-${VERSION}-${arch}-unknown-linux-musl.tar.gz"
echo "${sum}  $tmp/t.tgz" | sha256sum -c -
tar -xzf "$tmp/t.tgz" -C "$tmp"
mkdir -p "$1" "$2"
install -m 0755 "$tmp/tectonic" "$1/tectonic"
cp "$(dirname "$0")/precarga.tex" "$(dirname "$0")/precarga-beamer.tex" "$tmp/"
(cd "$tmp" && TECTONIC_CACHE_DIR="$2" "$1/tectonic" -X compile precarga.tex >/dev/null \
  && TECTONIC_CACHE_DIR="$2" "$1/tectonic" -X compile precarga-beamer.tex >/dev/null)
rm -r "$tmp"
"$1/tectonic" --version
