#!/usr/bin/env bash
# Falla si alguna imagen contiene Ghostscript, MuPDF (mutool), PyMuPDF, PyAV, libx264/libx265 (11, D-49 y D-111) o los
# paquetes de Python que cargarían espeak-ng (GPL) dentro del proceso: misaki, phonemizer, kokoro y kokoro-onnx (D-167).
# Uso: scripts/check_images.sh ghcr.io/propietario/conversor-api:TAG [más imágenes…]
set -euo pipefail
status=0
probe='for b in gs gsc gsx mutool; do command -v "$b" 2>/dev/null; done
if command -v python3 >/dev/null 2>&1; then
  python3 - <<"PY" 2>/dev/null || true
import importlib.util
for mod in ("fitz", "pymupdf", "av", "misaki", "phonemizer", "kokoro", "kokoro_onnx", "espeakng_loader"):
    if importlib.util.find_spec(mod):
        print("python:" + mod)
PY
fi
find / -xdev \( -name "libx264*" -o -name "libx265*" \) -print 2>/dev/null | sed "s/^/biblioteca: /"'
for image in "$@"; do
  found=$(docker run --rm --network none --entrypoint sh "$image" -c "$probe" || true)
  if [ -n "$found" ]; then
    echo "PROHIBIDO en $image:"
    echo "$found"
    status=1
  else
    echo "OK $image"
  fi
done
exit $status
