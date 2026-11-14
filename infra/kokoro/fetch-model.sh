#!/bin/sh
# Voz de pdf-a-audio (6.4): Kokoro-82M v1.0 (pesos y voces Apache-2.0, de hexgrad) en la conversión a ONNX de
# onnx-community (Apache-2.0), con la revisión de Hugging Face fijada y el SHA-256 de cada archivo comprobado. Kokoro no
# publica versiones desde abril de 2025 (D-167). Lo usan la imagen worker-av (al construirla: los workers no tienen
# salida a internet) y la CI.
# Uso: fetch-model.sh <destino>
# Deja: <destino>/model.onnx (fp32), <destino>/tokenizer.json (vocabulario de fonemas) y <destino>/voices/<voz>.bin.
set -eu
dest=$1
repo=onnx-community/Kokoro-82M-v1.0-ONNX
rev=1939ad2a8e416c0acfeecc08a694d14ef25f2231
base="https://huggingface.co/$repo/resolve/$rev"
mkdir -p "$dest/voices"
curl -fsSL --retry 3 -o "$dest/model.onnx" "$base/onnx/model.onnx"
curl -fsSL --retry 3 -o "$dest/tokenizer.json" "$base/tokenizer.json"
# Español: ef_dora (mujer), em_alex y em_santa (hombre). Inglés de EE. UU.: af_heart y af_bella (mujer), am_michael (hombre).
for voice in ef_dora em_alex em_santa af_heart af_bella am_michael; do
  curl -fsSL --retry 3 -o "$dest/voices/$voice.bin" "$base/voices/$voice.bin"
done
cat > "$dest/SHA256SUMS" <<SUMS
8fbea51ea711f2af382e88c833d9e288c6dc82ce5e98421ea61c058ce21a34cb  $dest/model.onnx
77a02c8e164413299b4b4c403b14f8e0e1c1b727db4d46a09d6327b861060a34  $dest/tokenizer.json
f66ec66bd295acb18372e37008533a9a3228483ccd294e7538d5d9294ac9a532  $dest/voices/ef_dora.bin
27809e9eafdcbcfff90a3016c697568676531de2a2c39cee29c96c7bd6b83e95  $dest/voices/em_alex.bin
ad43b774e1ca24d05c6161297d8aeb770ac3d29bb95daf516727af5f7d543683  $dest/voices/em_santa.bin
d583ccff3cdca2f7fae535cb998ac07e9fcb90f09737b9a41fa2734ec44a8f0b  $dest/voices/af_heart.bin
f69d836209b78eb8c66e75e3cda491e26ea838a3674257e9d4e5703cbaf55c8b  $dest/voices/af_bella.bin
1d1f21dd8da39c30705cd4c75d039d265e9bc4a2a93ed09bc9e1b1225eb95ba1  $dest/voices/am_michael.bin
SUMS
sha256sum -c "$dest/SHA256SUMS"
