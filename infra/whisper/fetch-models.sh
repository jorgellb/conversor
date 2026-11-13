#!/bin/sh
# Modelos de faster-whisper (6.4) convertidos a CTranslate2 por Systran, licencia MIT, con la revisión de Hugging Face
# fijada y el SHA-256 de model.bin comprobado. Lo usan la imagen worker-av (al construirla: los workers no tienen salida
# a internet) y la CI. Uso: fetch-models.sh <destino> <modelo> [modelo…]   (modelos: tiny, small, medium)
set -eu
dest=$1
shift
for model in "$@"; do
  case "$model" in
    tiny) rev=d90ca5fe260221311c53c58e660288d3deb8d356; sha=dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1 ;;
    small) rev=536b0662742c02347bc0e980a01041f333bce120; sha=3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671 ;;
    medium) rev=08e178d48790749d25932bbc082711ddcfdfbc4f; sha=9b45e1009dcc4ab601eff815b61d80e60ce3fd8c74c1a14f4a282258286b51ae ;;
    *) echo "Modelo de faster-whisper no admitido: $model" >&2; exit 1 ;;
  esac
  dir="$dest/faster-whisper-$model"
  mkdir -p "$dir"
  for file in config.json tokenizer.json vocabulary.txt model.bin; do
    curl -fsSL --retry 3 -o "$dir/$file" "https://huggingface.co/Systran/faster-whisper-$model/resolve/$rev/$file"
  done
  echo "$sha  $dir/model.bin" | sha256sum -c -
done
