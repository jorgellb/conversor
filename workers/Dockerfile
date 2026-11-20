# syntax=docker/dockerfile:1.7
# Imagen base común de Python (3.3) y una imagen por grupo encima. Se construye en GitHub Actions:
#   docker build -f workers/Dockerfile --target <api|worker-pdf|worker-ocr|worker-office|worker-media|worker-convert|worker-av|worker-ai|worker-sign> .
ARG PYTHON_IMAGE=python:3.12.16-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.6

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1 \
    PYTHONPATH=/app/packages/core:/app/packages/tools:/app/apps/api \
    FILESTORE_PATH=/srv/files \
    PLANS_FILE=/app/config/plans.yaml
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 10001 app && useradd -u 10001 -g app -m -d /home/app -s /usr/sbin/nologin app \
 && mkdir -p /srv/files /srv/backups && chown app:app /srv/files /srv/backups
WORKDIR /app
COPY pyproject.toml ./
RUN uv pip install -r pyproject.toml
ENTRYPOINT ["/usr/bin/tini", "--"]

# --- Código compartido (al final de cada imagen para aprovechar la caché) ---
FROM base AS code
COPY config ./config
COPY packages/core ./packages/core
COPY packages/tools ./packages/tools

# --- api, apiint, beat y migrate: misma imagen (3.2) ---
FROM base AS api
ARG PG_MAJOR=16
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl gnupg restic \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update && apt-get install -y --no-install-recommends postgresql-client-${PG_MAJOR} \
 && apt-get purge -y gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
RUN uv pip install -r pyproject.toml --extra pdf
COPY --from=code /app /app
COPY apps/api ./apps/api
USER app
EXPOSE 8000 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]

# --- Workers ---
FROM base AS worker-pdf
# tiffcp (pdf-a-tiff), pdftocairo (pdf-a-svg; GPL, solo como proceso externo) y el perfil CMYK FOGRA39 de colord (CC0).
# El colord-data de bookworm (1.4.6) ya no trae los perfiles de impresión: el perfil va en infra/icc con su SHA-256 (D-154).
ARG FOGRA39_SHA256=b62f5c72561c15ae2e0072b92ce9df42662f76915d75fac8ca2f6be033ac74fe
COPY infra/icc/FOGRA39L_coated.icc /usr/share/color/icc/colord/FOGRA39L_coated.icc
RUN apt-get update \
 && apt-get install -y --no-install-recommends libtiff-tools poppler-utils \
 && rm -rf /var/lib/apt/lists/* \
 && echo "${FOGRA39_SHA256}  /usr/share/color/icc/colord/FOGRA39L_coated.icc" | sha256sum -c -
RUN uv pip install -r pyproject.toml --extra pdf
COPY --from=code /app /app
USER app
ENV SERVICE_ROLE=worker-pdf
CMD ["celery", "-A", "core.celeryapp", "worker", "-Q", "pdf", "-n", "pdf@%h", "--prefetch-multiplier", "1", "-O", "fair", "--without-gossip", "--without-mingle"]

FROM base AS worker-ocr
# Tesseract con tessdata_fast para todos los idiomas; tessdata_best para spa, cat, eus, glg, eng, fra, deu, ita y por (2).
# veraPDF (pdf-a-pdfa y validar-pdfa; MPL-2.0/GPL-3.0, proceso externo) con su instalador oficial fijado por SHA-256.
ARG VERAPDF_VERSION=1.30.3
ARG VERAPDF_SHA256=b512bf24945503a33fc10738ecffc1f2dccaaf8593a448e94ee9ac86a9559a59
COPY infra/verapdf/auto-install.xml /tmp/verapdf-auto-install.xml
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-all curl unzip openjdk-17-jre-headless \
 && for l in spa cat eus glg eng fra deu ita por; do \
      curl -fsSL -o /usr/share/tesseract-ocr/5/tessdata/$l.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/4.1.0/$l.traineddata; \
    done \
 && curl -fsSL -o /tmp/verapdf.zip "https://software.verapdf.org/rel/${VERAPDF_VERSION%.*}/verapdf-greenfield-${VERAPDF_VERSION}-installer.zip" \
 && echo "${VERAPDF_SHA256}  /tmp/verapdf.zip" | sha256sum -c - \
 && unzip -q /tmp/verapdf.zip -d /tmp/verapdf \
 && java -jar /tmp/verapdf/verapdf-greenfield-${VERAPDF_VERSION}/verapdf-izpack-installer-${VERAPDF_VERSION}.jar /tmp/verapdf-auto-install.xml \
 && ln -s /opt/verapdf/verapdf /usr/local/bin/verapdf \
 && verapdf --version \
 && rm -rf /tmp/verapdf /tmp/verapdf.zip /tmp/verapdf-auto-install.xml \
 && apt-get purge -y curl unzip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
RUN uv pip install -r pyproject.toml --extra ocr
COPY --from=code /app /app
USER app
ENV SERVICE_ROLE=worker-ocr OMP_THREAD_LIMIT=2
CMD ["celery", "-A", "core.celeryapp", "worker", "-Q", "ocr", "-n", "ocr@%h", "--prefetch-multiplier", "1", "-O", "fair", "--without-gossip", "--without-mingle"]

FROM base AS worker-office
# LibreOffice local solo para conversiones que no son a PDF (pdf-a-word fiel); Office a PDF va por Gotenberg.
# Calibre (`ebook-convert`, GPL, solo como proceso externo) para EPUB, MOBI, AZW3 y FB2 a PDF (F2, lote C; D-53).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui \
      calibre fonts-dejavu fonts-liberation2 fonts-noto-core fonts-crosextra-carlito fonts-crosextra-caladea \
 && rm -rf /var/lib/apt/lists/* \
 && ebook-convert --version
RUN uv pip install -r pyproject.toml --extra office
COPY --from=code /app /app
USER app
ENV SERVICE_ROLE=worker-office
CMD ["celery", "-A", "core.celeryapp", "worker", "-Q", "office.light", "-n", "office-light@%h", "--prefetch-multiplier", "1", "-O", "fair", "--without-gossip", "--without-mingle"]

# libheif solo para decodificar (D-49): en bookworm `libheif1` enlaza el codificador x265 (GPL), que no debe estar en
# ninguna imagen de producción. Se compila con libde265 (LGPL) y sin codificadores ni carga de plugins.
FROM ${PYTHON_IMAGE} AS libheif-build
ARG LIBHEIF_VERSION=1.19.8
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential cmake curl ca-certificates pkg-config libde265-dev libpng-dev \
 && curl -fsSL "https://github.com/strukturag/libheif/releases/download/v${LIBHEIF_VERSION}/libheif-${LIBHEIF_VERSION}.tar.gz" \
      -o /tmp/libheif.tar.gz \
 && tar -xzf /tmp/libheif.tar.gz -C /tmp \
 && cmake -S /tmp/libheif-${LIBHEIF_VERSION} -B /tmp/build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/libheif \
      -DWITH_LIBDE265=ON -DWITH_X265=OFF -DWITH_AOM_DECODER=OFF -DWITH_AOM_ENCODER=OFF -DWITH_DAV1D=OFF -DWITH_RAV1E=OFF \
      -DWITH_SvtEnc=OFF -DWITH_KVAZAAR=OFF -DWITH_FFMPEG_DECODER=OFF -DWITH_JPEG_DECODER=OFF -DWITH_JPEG_ENCODER=OFF \
      -DWITH_OpenJPEG_DECODER=OFF -DWITH_OpenJPEG_ENCODER=OFF -DWITH_OPENJPH_ENCODER=OFF -DWITH_LIBSHARPYUV=OFF \
      -DWITH_GDK_PIXBUF=OFF -DENABLE_PLUGIN_LOADING=OFF -DWITH_EXAMPLES=ON -DBUILD_TESTING=OFF \
 && cmake --build /tmp/build -j"$(nproc)" && cmake --install /tmp/build \
 && ! ldd /opt/libheif/bin/heif-dec | grep -qi -e x265 -e aom

# Modelo de rembg para quitar-fondo (6.4), descargado al construir y fijado por SHA-256: los workers no tienen salida a
# internet. Solo u2net (Apache-2.0, por defecto) o isnet-general-use; nunca bria-rmbg (licencia comercial de pago, D-96).
FROM ${PYTHON_IMAGE} AS rembg-model
ARG REMBG_MODEL=u2net
ARG REMBG_MODEL_SHA256=8d10d2f3bb75ae3b6d527c77944fc5e7dcd94b29809d47a739a7a728a912b491
RUN case "${REMBG_MODEL}" in u2net|isnet-general-use) ;; *) echo "Modelo de rembg no admitido: ${REMBG_MODEL}" >&2; exit 1 ;; esac \
 && apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
 && mkdir -p "/opt/rembg/models/${REMBG_MODEL}" \
 && curl -fsSL "https://github.com/danielgatis/rembg/releases/download/v0.0.0/${REMBG_MODEL}.onnx" \
      -o "/opt/rembg/models/${REMBG_MODEL}/${REMBG_MODEL}.onnx" \
 && echo "${REMBG_MODEL_SHA256}  /opt/rembg/models/${REMBG_MODEL}/${REMBG_MODEL}.onnx" | sha256sum -c -

FROM base AS worker-media
ARG REMBG_MODEL=u2net
# DjVuLibre (`ddjvu`, GPL, solo como proceso externo), libarchive para CBZ y CBR, y heif-dec de la etapa anterior.
RUN apt-get update \
 && apt-get install -y --no-install-recommends djvulibre-bin libarchive13 libde265-0 libpng16-16 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=libheif-build /opt/libheif/lib/ /usr/local/lib/
COPY --from=libheif-build /opt/libheif/bin/heif-dec /usr/local/bin/heif-dec
RUN ldconfig && heif-dec --version && ! ldd /usr/local/bin/heif-dec | grep -qi x265
RUN uv pip install -r pyproject.toml --extra media
COPY --from=rembg-model /opt/rembg /opt/rembg
COPY --from=code /app /app
USER app
# numba (pymatting) compila en /tmp porque el sistema de archivos es de solo lectura; onnxruntime con un hilo, como el contenedor.
ENV SERVICE_ROLE=worker-media REMBG_HOME=/opt/rembg REMBG_MODEL=${REMBG_MODEL} NUMBA_CACHE_DIR=/tmp/numba OMP_NUM_THREADS=1
CMD ["celery", "-A", "core.celeryapp", "worker", "-Q", "media", "-n", "media@%h", "--prefetch-multiplier", "1", "-O", "fair", "--without-gossip", "--without-mingle"]

FROM base AS worker-convert
# Docling con Torch solo CPU; los modelos se descargan al construir, nunca en ejecución (3.3).
# LibreOffice para ODT, ODS, ODP y RTF y el modo fiel; Tesseract para el OCR de Docling; pdftocairo para el diseño fijo
# de pdf-a-html y pdf-a-epub (F2, lote D2; D-67).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui \
      tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng tesseract-ocr-cat tesseract-ocr-eus tesseract-ocr-glg \
      tesseract-ocr-fra tesseract-ocr-deu tesseract-ocr-ita tesseract-ocr-por poppler-utils \
      fonts-dejavu fonts-liberation2 fonts-noto-core fonts-crosextra-carlito fonts-crosextra-caladea \
 && rm -rf /var/lib/apt/lists/*
RUN uv pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision \
 && uv pip install -r pyproject.toml --extra convert
ENV HF_HOME=/opt/models/hf DOCLING_ARTIFACTS_PATH=/opt/models/docling
RUN mkdir -p /opt/models && docling-tools models download -o /opt/models/docling && chmod -R a+rX /opt/models
COPY --from=code /app /app
USER app
ENV SERVICE_ROLE=worker-convert OMP_NUM_THREADS=2 HF_HUB_OFFLINE=1
CMD ["celery", "-A", "core.celeryapp", "worker", "-Q", "convert", "-n", "convert@%h", "--prefetch-multiplier", "1", "-O", "fair", "--without-gossip", "--without-mingle"]

# Modelos de faster-whisper (6.4) descargados al construir, con la revisión y el SHA-256 fijados: small por defecto;
# medium es opcional (precisión alta), con --build-arg WHISPER_MODELS="small medium" (unos 1,5 GB más).
FROM ${PYTHON_IMAGE} AS whisper-model
ARG WHISPER_MODELS=small
COPY infra/whisper/fetch-models.sh /tmp/fetch-models.sh
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
 && sh /tmp/fetch-models.sh /opt/models/whisper ${WHISPER_MODELS}

# Voz de pdf-a-audio (6.4): Kokoro-82M v1.0 en ONNX (Apache-2.0) con la revisión de Hugging Face y el SHA-256 de cada
# archivo fijados (infra/kokoro/fetch-model.sh); nunca los paquetes kokoro ni kokoro-onnx (11, D-167).
FROM ${PYTHON_IMAGE} AS kokoro-model
COPY infra/kokoro/fetch-model.sh /tmp/fetch-model.sh
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
 && sh /tmp/fetch-model.sh /opt/models/kokoro && chmod -R a+rX /opt/models

FROM base AS worker-av
# FFmpeg en compilación LGPL (11): binarios estáticos de BtbN con la variante «lgpl», fijados por fecha y SHA-256
# (D-13 y D-137). Autobuild de fin de mes (BtbN los conserva; los diarios se borran) de la rama 8.1, n8.1.3-27.
# El SHA-256 es el de checksums.sha256 de esa publicación, que coincide con el resumen que da GitHub del archivo.
ARG FFMPEG_BUILD=https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-10-31-12-59/ffmpeg-n8.1.3-27-g8dca1586f4-linux64-lgpl-8.1.tar.xz
ARG FFMPEG_SHA256=a64f3171e6ad1f7d358d28890a907ee478c331d1177ec696a93418f79ac3f1f3
RUN apt-get update && apt-get install -y --no-install-recommends curl xz-utils \
 && curl -fsSL "$FFMPEG_BUILD" -o /tmp/ffmpeg.tar.xz \
 && echo "$FFMPEG_SHA256  /tmp/ffmpeg.tar.xz" | sha256sum -c - \
 && tar -xJf /tmp/ffmpeg.tar.xz -C /tmp \
 && install -m 0755 /tmp/ffmpeg-*/bin/ffmpeg /tmp/ffmpeg-*/bin/ffprobe /usr/local/bin/ \
 && rm -rf /tmp/ffmpeg* && apt-get purge -y curl xz-utils && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
 && ffmpeg -hide_banner -version >/dev/null && ffprobe -hide_banner -version >/dev/null \
 && ! (ffmpeg -hide_banner -buildconf | grep -q -- "--enable-gpl")
# espeak-ng (GPL-3.0) para los fonemas de pdf-a-audio, solo como programa externo con run_engine (11 y 12.1).
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng \
 && rm -rf /var/lib/apt/lists/* && espeak-ng --version
COPY infra/uv-overrides.txt ./infra/uv-overrides.txt
# faster-whisper sin PyAV (D-111), y comprobado: ni el módulo `av` ni libx264/libx265 en la imagen. Tampoco los paquetes
# de Python que cargarían espeak-ng dentro del proceso (misaki, phonemizer, kokoro, kokoro-onnx, espeakng-loader; 11).
RUN uv pip install -r pyproject.toml --extra av --override infra/uv-overrides.txt \
 && ! python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('av') else 1)" \
 && ! find / -xdev \( -name 'libx264*' -o -name 'libx265*' \) -print 2>/dev/null | grep -q . \
 && ! python -c "import importlib.util as u, sys; sys.exit(0 if any(u.find_spec(m) for m in ('misaki', 'phonemizer', 'kokoro', 'kokoro_onnx', 'espeakng_loader')) else 1)"
COPY --from=whisper-model /opt/models/whisper /opt/models/whisper
COPY --from=kokoro-model /opt/models/kokoro /opt/models/kokoro
COPY --from=code /app /app
USER app
# Sin descargas al ejecutar: los modelos ya están en WHISPER_HOME y KOKORO_HOME.
ENV SERVICE_ROLE=worker-av WHISPER_HOME=/opt/models/whisper KOKORO_HOME=/opt/models/kokoro HF_HUB_OFFLINE=1
CMD ["celery", "-A", "core.celeryapp", "worker", "-Q", "av.light", "-n", "av-light@%h", "--prefetch-multiplier", "1", "-O", "fair", "--without-gossip", "--without-mingle"]

# Modelo de embeddings de chat-pdf (6.4), fijado por revisión y SHA-256: los workers no descargan nada al ejecutar.
FROM ${PYTHON_IMAGE} AS embeddings-model
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY infra/embeddings/fetch-model.sh /tmp/fetch-model.sh
RUN sh /tmp/fetch-model.sh /opt/models/embeddings

# --- IA (F3): peticiones a OpenRouter (solo por egressai), texto de los PDF con pypdfium2 y embeddings locales
# (fastembed). La misma imagen sirve a workerai (cola ai) y a workeraiembed (cola ai.embed, sin clave ni salida) ---
FROM base AS worker-ai
RUN uv pip install -r pyproject.toml --extra ai
COPY --from=embeddings-model /opt/models/embeddings /opt/models/embeddings
COPY --from=code /app /app
USER app
ENV SERVICE_ROLE=worker-ai EMBEDDINGS_HOME=/opt/models/embeddings HF_HUB_OFFLINE=1
CMD ["celery", "-A", "core.celeryapp", "worker", "-Q", "ai", "-n", "ai@%h", "--prefetch-multiplier", "1", "-O", "fair", "--without-gossip", "--without-mingle"]

# --- Firma (F4): pyHanko con SoftHSM2 (BSD-2, solo la biblioteca PKCS#11 y su utilidad). La misma imagen sirve a
# workersign (cola sign, con el volumen del token y SIGN_PKCS11_PIN; 10 y 12.1) y a workersignverify (cola sign.verify,
# sin token ni PIN, con la caché de la lista de confianza de la UE en /srv/eutl; D-185) ---
FROM base AS worker-sign
RUN apt-get update \
 && apt-get install -y --no-install-recommends softhsm2 \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /var/lib/softhsm/tokens /srv/eutl \
 && chown -R app:app /var/lib/softhsm /srv/eutl \
 && test -f /usr/lib/softhsm/libsofthsm2.so \
 && printf 'directories.tokendir = /var/lib/softhsm/tokens/\nobjectstore.backend = file\nlog.level = ERROR\nslots.removable = false\n' \
      > /etc/softhsm2-app.conf && chmod 644 /etc/softhsm2-app.conf
RUN uv pip install -r pyproject.toml --extra sign
COPY --from=code /app /app
# El texto de los sellos visibles usa la Noto Sans del paquete (OFL, D-202): pyHanko solo acierta con 1000 unidades por em.
RUN cd /app/packages/tools/tools/sign/fonts && sha256sum -c SHA256SUMS
# Token de desarrollo del sello (10): solo lo ejecuta el Compose de desarrollo; en Coolify no se llama.
COPY infra/sign/dev_token.py /app/infra/sign/dev_token.py
USER app
# El /etc/softhsm/softhsm2.conf de Debian es root:softhsm 0640 y el usuario app no lo puede leer (D-189): una
# configuración propia, con los tokens en el volumen. Se comprueba como app al construir la imagen.
ENV SERVICE_ROLE=worker-sign SOFTHSM2_CONF=/etc/softhsm2-app.conf
RUN softhsm2-util --show-slots > /dev/null
CMD ["celery", "-A", "core.celeryapp", "worker", "-Q", "sign", "-n", "sign@%h", "-c", "1", "--prefetch-multiplier", "1", "-O", "fair", "--without-gossip", "--without-mingle"]

# --- Solo desarrollo y CI (0.1): la PKI de pruebas de certomancer (CA, TSA, OCSP y CRL) con claves nuevas al arrancar.
# Nunca va a Coolify ni a images.yml ---
FROM base AS certomancer
RUN uv pip install "certomancer[web-api]==0.16.0" "pyHanko==0.38.1"
COPY scripts/fixtures/pki.py /app/pki.py
USER app
WORKDIR /home/app
EXPOSE 9000
CMD ["python", "/app/pki.py", "serve", "/home/app/pki", "9000"]

# --- Facturas electrónicas (F4-D, grupo utils): KoSIT Validator en modo servicio dentro de workerutils (5.4), con las
# configuraciones públicas de XRechnung y Peppol BIS y los escenarios propios (D-191); Facturae con sus XSD oficiales
# (infra/facturae, SHA256SUMS). JRE 17 de Debian; KoSIT y las configuraciones, con SHA-256 fijados ---
FROM base AS worker-utils
RUN apt-get update \
 && apt-get install -y --no-install-recommends openjdk-17-jre-headless curl libarchive13 \
 && rm -rf /var/lib/apt/lists/* && java -version
RUN uv pip install -r pyproject.toml --extra utils
# pandoc 3.13 estático (F6-A, D-212), versión y SHA-256 fijados en el script; GPL, solo como proceso externo (11).
COPY infra/pandoc/fetch.sh /tmp/pandoc-fetch.sh
RUN sh /tmp/pandoc-fetch.sh /usr/local/bin && rm /tmp/pandoc-fetch.sh
COPY infra/kosit/fetch.sh infra/kosit/scenarios.xml /tmp/kosit/
RUN sh /tmp/kosit/fetch.sh /opt/kosit "$(python -c 'import facturx, pathlib; print(pathlib.Path(facturx.__file__).parent / "xsd_and_schematron")')" \
      /tmp/kosit/scenarios.xml \
 && rm -rf /tmp/kosit
COPY infra/facturae /opt/facturae
RUN cd /opt/facturae && sha256sum -c SHA256SUMS
COPY infra/kosit/start.sh /usr/local/bin/kosit-start
COPY --from=code /app /app
USER app
ENV SERVICE_ROLE=worker-utils FACTURAE_XSD_DIR=/opt/facturae KOSIT_URL=http://127.0.0.1:8081/
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/kosit-start"]
CMD ["celery", "-A", "core.celeryapp", "worker", "-Q", "utils.light", "-n", "utils@%h", "-c", "2", "--prefetch-multiplier", "1", "-O", "fair", "--without-gossip", "--without-mingle"]

