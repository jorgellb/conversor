#!/bin/sh
# Modelo de embeddings de chat-pdf (6.4): paraphrase-multilingual-MiniLM-L12-v2 (Apache-2.0, 384 dimensiones) en el ONNX
# cuantizado que usa fastembed (repositorio de Qdrant), con la revisión de Hugging Face fijada y el SHA-256 comprobado.
# Lo usan la imagen worker-ai (al construirla: los workers no tienen salida a internet) y la CI.
# Uso: fetch-model.sh <destino>
set -eu
dest=$1/paraphrase-multilingual-MiniLM-L12-v2
repo=Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q
rev=faf4aa4225822f3bc6376869cb1164e8e3feedd0
mkdir -p "$dest"
for file in config.json special_tokens_map.json tokenizer_config.json tokenizer.json model_optimized.onnx; do
  curl -fsSL --retry 3 -o "$dest/$file" "https://huggingface.co/$repo/resolve/$rev/$file"
done
cat > "$dest/SHA256SUMS" <<SUMS
634d0f66c29dc934c8fa72b8a4fe91dd4d420a22f1d82a241058d4316e659a99  $dest/model_optimized.onnx
fa685fc160bbdbab64058d4fc91b60e62d207e8dc60b9af5c002c5ab946ded00  $dest/tokenizer.json
SUMS
sha256sum -c "$dest/SHA256SUMS"
