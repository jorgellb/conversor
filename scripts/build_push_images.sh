#!/bin/sh
# Construye y sube a GHCR las 14 imágenes del Compose de Coolify sin GitHub Actions (las mismas que images.yml: api, los
# 11 workers, web y smokescreen), con la etiqueta que se pondrá en IMAGE_TAG. Requiere Docker con buildx y unos 60 GB
# libres (worker-av, worker-convert y worker-cad son las grandes).
#
#   echo "$TOKEN" | docker login ghcr.io -u <usuario> --password-stdin   # token con write:packages
#   GHCR_OWNER=<usuario u organización> IMAGE_TAG=0.1.0 sh scripts/build_push_images.sh [destino ...]
#
# Sin destinos, construye todos. Después, en Coolify: GHCR_OWNER y IMAGE_TAG iguales a los de aquí (docs/DEPLOY.md, 3 y 5).
set -eu

: "${GHCR_OWNER:?Pon GHCR_OWNER (propietario del registro)}"
: "${IMAGE_TAG:?Pon IMAGE_TAG (por ejemplo 0.1.0)}"
cd "$(dirname "$0")/.."

WORKERS="api worker-pdf worker-ocr worker-office worker-media worker-convert worker-av worker-ai worker-sign worker-utils worker-mesh worker-cad"
TARGETS="${*:-$WORKERS web smokescreen}"
REGISTRY="ghcr.io/$(echo "$GHCR_OWNER" | tr '[:upper:]' '[:lower:]')"
COMMIT="$(git rev-parse HEAD)"

for target in $TARGETS; do
  image="$REGISTRY/conversor-$target"
  case "$target" in
    web) file=apps/web/Dockerfile; extra="" ;;
    smokescreen) file=infra/smokescreen/Dockerfile; extra="" ;;
    *) file=workers/Dockerfile; extra="--target $target" ;;
  esac
  echo "==> $image:$IMAGE_TAG"
  # shellcheck disable=SC2086
  docker buildx build --platform linux/amd64 -f "$file" $extra -t "$image:$IMAGE_TAG" -t "$image:sha-$COMMIT" --push .
  case "$target" in
    api|worker-*) sh scripts/check_images.sh "$image:$IMAGE_TAG" ;;  # sin Ghostscript, MuPDF ni PyMuPDF (11)
  esac
done
echo "Listo: $(echo "$TARGETS" | wc -w) imágenes en $REGISTRY con la etiqueta $IMAGE_TAG"
