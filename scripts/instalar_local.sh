#!/bin/sh
# Instala en esta máquina (Debian 13 o Ubuntu 24.04) lo necesario para probar el portal entero en local: Docker con
# Compose y Buildx (para `docker compose up --build` y `scripts/build_push_images.sh`) y los motores que usan las pruebas
# fuera de Docker (`pytest` y `scripts/dev_local.py`). Solo paquetes oficiales de la distribución.
#
#   sudo sh scripts/instalar_local.sh
#
# Después hay que cerrar la sesión y volver a entrar (o `newgrp docker`) para usar Docker sin sudo.
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Ejecútalo con sudo: sudo sh scripts/instalar_local.sh" >&2
  exit 1
fi
USUARIO="${SUDO_USER:-}"

export DEBIAN_FRONTEND=noninteractive
apt-get update

echo "==> Docker, Compose v2 y Buildx"
# docker-cli va aparte en Debian 13 (solo «recomendado» por docker.io): sin él no hay orden `docker`.
apt-get install -y --no-install-recommends docker.io docker-cli docker-compose docker-buildx uidmap ca-certificates apparmor xz-utils git

echo "==> Motores de las herramientas (los mismos que instala la CI)"
apt-get install -y --no-install-recommends \
  libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui libreoffice-draw-nogui \
  softhsm2 calibre openscad libassimp5 pst-utils gdal-bin \
  fluidsynth fluid-soundfont-gm musescore3 espeak-ng fonts-liberation2 fonts-dejavu \
  tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng tesseract-ocr-osd ffmpeg \
  djvulibre-bin libheif-examples poppler-utils libtiff-tools qpdf restic default-jre-headless

echo "==> Servicio de Docker"
systemctl enable --now docker
if [ -n "$USUARIO" ]; then
  usermod -aG docker "$USUARIO"
  echo "Añadido $USUARIO al grupo docker: cierra la sesión y vuelve a entrar (o ejecuta «newgrp docker»)."
fi

docker --version
docker compose version
docker buildx version
echo "Listo. Siguiente paso: docker compose up --build (README) o python scripts/dev_local.py start."
