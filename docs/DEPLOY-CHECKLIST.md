# Cierre operativo de F1 (1.3 y 13.3)

Marca cada punto en el VPS. Lo que no se pueda hacer queda como pendiente en `PROGRESS.md`.

## Antes del primer despliegue

- [x] Fijar `FFMPEG_BUILD` en `workers/Dockerfile` a un autobuild de BtbN con fecha y comprobar su SHA-256 (D-13):
      `autobuild-2026-10-31-12-59`, FFmpeg n8.1.3-27 LGPL, con `FFMPEG_SHA256` (D-137).
- [ ] Construir `worker-av` en la CI de imágenes con ese FFmpeg 8.1 (`sha256sum -c` y la comprobación de
      `--enable-gpl` pasan) y repetir el audio de F5 (`tests/test_audio_f5.py`) con ese binario; guardar una copia del
      archivo de BtbN (por ejemplo, como recurso de una publicación propia) por si BtbN lo retira.
- [ ] Perfil de memoria y CPU: en un VPS de 16 vCPU y 64 GB, pegar en Coolify las variables de
      `python scripts/gen_coolify_compose.py --profile 16` (`docs/OPERATIONS.md`, D-138); `--validate` (`docker compose
      config`) pasa en la CI con las variables `${MEM_*}` y `${CPUS_*}`.
- [ ] **Propietario:** decidir si se añaden equivalentes de «Print PDF as poster» y «OFD to PDF» de PDF24, que no están
      en la especificación (tabla de paridad de `docs/TOOLS.md`, D-139).
- [ ] Revisar la ficha de licencia de los modelos que descarga `docling-tools` en `worker-convert`.
- [ ] Smokescreen ya no viene de `ghcr.io/stripe/smokescreen` (esa imagen no existe): `images.yml` compila `infra/smokescreen/Dockerfile` desde la etiqueta v0.1.0 y publica `ghcr.io/<propietario>/conversor-smokescreen` (D-155). Comprobar en el primer despliegue que `egressweb` y `egressai` arrancan con esa imagen y que web-a-pdf sale a internet y no llega a una IP privada (D-30).
- [ ] Contenido propio de cada página revisado por muestreo y marcado con `reviewed: true` en `apps/web/content/` (7.22).
- [ ] Textos de las páginas índice revisados (título, descripción e introducción de conversor-pdf, crear-pdf y
      convertir-archivo, en `apps/web/messages/`): se indexan y están en el sitemap sin pasar por `reviewed` (D-117 y D-118).
- [ ] Datos del titular en los textos legales (`apps/web/src/components/legal.ts`) revisados por un profesional.
- [ ] Precios de Pro en Stripe (modo test) y `STRIPE_PRICE_PRO_MONTHLY` y `STRIPE_PRICE_PRO_YEARLY`.
- [ ] IA (F3): cuenta de OpenRouter según `OPERATIONS.md` (decidir la compra única de 10 créditos, 0.1; privacidad sin
      entrenar ni publicar), `OPENROUTER_API_KEY` solo en `workerai`, y comprobar en el panel (IA) que hay modelos tras el
      descubrimiento y que la reconciliación muestra `free_model_daily_requests`. Cierre técnico de F3: una tarea real de
      resumir-pdf registrada en `ai_requests` con el modelo usado.
- [ ] Lote D de F3 con la pila completa: pdf-a-audio en `workeravheavy` con un PDF real en inglés de unas 20 páginas
      (MP3 que se oye bien, sin cabeceras ni números de página, `ffprobe` con códec mp3 y la duración de la nota) y con
      un escaneo (pasa por `workerocr` y vuelve a `av.heavy`); la imagen `worker-av` con espeak-ng, el modelo de Kokoro en
      `/opt/models/kokoro` (SHA-256 de `infra/kokoro/fetch-model.sh`) y sin misaki, phonemizer ni kokoro
      (`scripts/check_images.sh`); `workeravheavy` sin reinicios por memoria con faster-whisper y Kokoro cargados a la vez
      (3 GB); la API rechaza un documento de más de 20.000 caracteres con la cuenta gratuita sin contar la tarea (D-169).
- [ ] Lote E de F3 con la pila completa: traducir-subtitulos con un SRT real de una película (unos 1.500 subtítulos:
      varias peticiones, tiempos idénticos al original, el resultado se abre en VLC como `<nombre>.es.srt`) y con un vídeo
      MP4 (pasa de `ai` a `workeravheavy` y vuelve); resumir-reunion con una grabación real de 30 a 60 minutos con varias
      voces (acta coherente con decisiones y tareas, en DOCX y en Markdown) y otra de más de 4 h con Pro (falla antes de
      transcribir y pide un tramo); `workeravheavy` lee los límites `AI_*` y `LLM_*` del Compose de Coolify y no tiene
      `OPENROUTER_API_KEY` (D-176); las peticiones de cada tarea aparecen en `ai_requests` y las reservas sin usar vuelven.
- [ ] **Escucha de la voz española de Kokoro (6.4)**: generar con `TTS_VOICE_ES=ef_dora` en un entorno de prueba (o con
      `python scripts/fixtures/lectura_pdf.py --voz es "<texto>" salida.ogg`) unos párrafos reales con números, fechas,
      siglas y palabras en inglés, con ef_dora y em_alex; si se aceptan, poner `TTS_VOICE_ES=ef_dora` en Coolify (API y
      `workeravheavy`). Hasta entonces la lectura en español está apagada (D-170).
- [ ] Lote C de F3 con la pila completa: imagen-a-texto en `workerocr` con una foto real de un documento (TXT, Word y
      PDF buscable); imagen-a-excel con una captura de una hoja de cálculo (termina en `workerconvert` y la petición
      reservada vuelve, D-160) y con una tabla escrita a mano (pasa a `workerai`); ticket-a-excel con 3 tickets reales en
      papel térmico (una petición por ticket en `ai_requests` y la columna «Cuadra» correcta, D-163). `workerconvert` y
      `workerocr` sin reinicios por memoria y la imagen `worker-ai` con openpyxl.
- [ ] Revisión de la IA por un especialista en protección de datos (aviso, política de privacidad y EIPD de `LEGAL.md`)
      antes de anunciar las herramientas de IA.
- [ ] SMTP con SPF, DKIM y DMARC en el dominio de `MAIL_FROM`.
- [ ] Repositorio remoto de restic y su contraseña (`BACKUP_RESTIC_REPOSITORY`, `BACKUP_RESTIC_PASSWORD`).
- [ ] Si se activan Google Drive o Dropbox (`GDRIVE_ENABLED`, `DROPBOX_ENABLED`): cliente OAuth web con el dominio como
      origen de JavaScript, clave de API limitada a Google Picker API y Drive API activada (`GOOGLE_PICKER_CLIENT_ID`,
      `GOOGLE_PICKER_API_KEY`); app de Dropbox con el dominio en «Chooser/Saver domains» (`DROPBOX_APP_KEY`). El WAF no
      debe bloquear a los servidores de Dropbox cuando descargan de `files.` (D-36).
- [ ] Confirmar que existe la versión de libheif fijada en `workers/Dockerfile` (`LIBHEIF_VERSION`, 1.19.8), que la
      etapa `libheif-build` compila y que `ldd /usr/local/bin/heif-dec` en `worker-media` no muestra x265 (D-49).
- [ ] `HEVC_DECODE_ENABLED` sigue apagado hasta la revisión legal anotada en `docs/LEGAL.md` (también apaga heic-a-jpg y
      heic-a-png).
- [ ] **Propietario:** confirmar el modelo de quitar-fondo. Por defecto u2net (pesos del repositorio U-2-Net, con LICENSE
      Apache-2.0). isnet-general-use solo tras revisar su licencia (el repositorio DIS no tiene archivo de licencia y su
      conjunto de datos tiene condiciones propias, D-96); para cambiarlo, construir `worker-media` con
      `--build-arg REMBG_MODEL=isnet-general-use --build-arg REMBG_MODEL_SHA256=60920e99c45464f2ba57bee2ad08c919a52bbf852739e96947fbb4358c0d964a`
      y poner `REMBG_MODEL=isnet-general-use` en `workermedia`. Nunca bria-rmbg.
- [ ] La imagen `worker-ocr` instala veraPDF 1.30.3 con `infra/verapdf/auto-install.xml` (nombres de los paquetes de
      IzPack incluidos) y `verapdf --version` responde; el paso de la CI que lo instala pasa y
      `test_real_verapdf_accepts_the_pdfa_we_produce` no se omite (D-63).

- [ ] Sello de la plataforma (10, D-188): el propietario elige el certificado del sello y la TSA (0.1), inicializa el
      token en el volumen `softhsm` de `workersign` (`softhsm2-util --init-token --free --label conversor-sello`),
      importa la clave con la etiqueta `sello` y deja la cadena en PEM en `/var/lib/softhsm/sello.pem`
      (`SIGN_CERT_PATH`, del sello a la raíz, que tiene que estar); fija `SIGN_PKCS11_PIN`, `TSA_URL` (y `TSA_TRUST_ROOTS` si la TSA no envía su raíz) y `SEAL_ACCOUNT_DAILY_LIMIT` en Coolify y pone la misma cadena en
      `SIGN_VERIFY_EXTRA_ROOTS` de `workersignverify` (el PEM en la propia variable). Nunca el token de desarrollo.

## Tras el despliegue

- [ ] Todos los healthchecks en verde en Coolify.
- [ ] La vista *Deployable Compose* conserva `runtime`, `read_only`, `cap_drop`, límites, `memswap_limit` y la red `internal`.
- [ ] Desde cada worker y desde `gotenberg`, `python -c "import urllib.request; urllib.request.urlopen('https://example.com', timeout=5)"` (o `curl`) falla.
- [ ] Desde `workeroffice`, la misma petición con `HTTPS_PROXY=http://egressweb:4750` sale, y hacia `http://10.0.0.1/` o `http://169.254.169.254/` la niega `egressweb`.
- [ ] `web-a-pdf` con una página pública y con un enlace a un PDF devuelve el PDF; con `http://127.0.0.1/` la API responde `INVALID_OPTIONS`.
- [ ] `gotenbergweb` no responde desde `api` ni desde los workers que no son `workeroffice` (solo está en `webrender`).
- [ ] `GET https://api.{{DOMINIO}}/readyz` responde 200 con `secrets: ok` en `api` y `apiint`.
- [ ] Una descarga con el token cambiado devuelve 403 y `files.` envía las cabeceras de 4.4.
- [ ] `workersignverify` descarga la lista de confianza de la UE al arrancar: en su log, «lista de confianza de la UE
      actualizada» con unos 30 países, y `/srv/eutl/actual.json` existe; verificar-firmas-pdf con un PDF firmado con un
      certificado cualificado (por ejemplo, del DNIe o de la FNMT) sale «Cualificada» con el prestador y el país (D-185).
- [ ] Con `TOOL_FIRMAR_PDF_ENABLED=true` (hasta F4-B), firmar-pdf con una cuenta devuelve el PDF sellado en B-T y
      verificar-firmas-pdf lo da como «Sello de la plataforma (no cualificado)» con la fecha de la TSA; con B-LT, nivel
      B-LT; y `seal_signatures` tiene una fila por sello.
- [ ] `workerutils` arranca KoSIT antes que Celery (en su log, «Daemon started») y validar-factura-electronica con una
      factura UBL o XRechnung real del propietario da su escenario y, con un error introducido, la regla y su
      explicación (D-191); una Facturae firmada real (AutoFirma o FNMT) sale «Firma XAdES íntegra» y, tocada, «no es válida»
      (las pruebas solo tienen firmas hechas aquí, D-193); y factura-electronica-a-pdf da un PDF/A-3b que veraPDF acepta
      con el XML dentro (D-192).
- [ ] firmar-pdf con un certificado propio real (FNMT o de empresa, .p12 exportado con AES): la página lo abre, la firma sale
      PAdES B-T y Adobe Acrobat Reader y verificar-firmas-pdf la dan por buena con la identidad del titular (D-199).
- [ ] solicitar-firmas con la pila real (F4-C2): la invitación, el código y el correo final llegan (SPF/DKIM del
      dominio) sin ir a spam; el firmante firma desde el móvil; el documento final pasa por verificar-firmas-pdf y por
      Adobe Reader con las firmas válidas; beat avanza una solicitud con la página cerrada. Revisar con el asesor el
      consentimiento y la conservación de la auditoría (LEGAL).
- [ ] crear-factura-electronica con un certificado real (FNMT o de empresa, RSA): el Facturae firmado en el navegador pasa
      el validador de facturae.gob.es y FACe lo acepta (con los códigos DIR3 que pida la Administración destinataria).
- [ ] Confirmar con OpenPeppol las condiciones de redistribución del Schematron de Peppol BIS 3.0 dentro de la imagen worker-utils (su repositorio no declara licencia; D-191 y LICENSES).
- [ ] Con «Comprobar la revocación en línea», un PDF firmado con un certificado de la FNMT consulta su OCSP por `egressweb`
      (en el log de Smokescreen) y el informe dice «Comprobada en línea».
- [ ] `upload.` y `files.` responden a través del proxy de Coolify (los dos servicios solo están en `internal` más la red que
      añade Coolify; D-181) y una subida de prueba llega a tusd.
- [ ] Los logs de `beat` muestran `beat: Starting...` y `cleanup_expired ... succeeded` cada 5 minutos, sin
      `permission denied` (D-181).
- [ ] Un anónimo puede comprimir un PDF y la tercera tarea pesada del día devuelve `QUOTA_EXCEEDED`.
- [ ] Pago de prueba con Stripe (modo test) y webhook recibido una sola vez.
- [ ] «Enviar por correo» con una cuenta gratuita (solo a sí misma) y otra Pro (3 destinatarios): llega el enlace, descarga
      durante 24 horas y después responde 403; el correo pasa SPF, DKIM y DMARC.
- [ ] Con Google Drive y Dropbox activados: abrir un PDF desde cada uno y guardar un resultado en cada uno.
- [ ] Copia ejecutada por la tarea de Coolify, subida con restic, y restauración probada en una base vacía.
- [ ] `CF-Connecting-IP` falsificado contra la IP del origen: ignorado (los puertos 80/443 solo aceptan Cloudflare).
- [ ] Lighthouse móvil ≥ 90 en rendimiento y accesibilidad en la portada y en `comprimir-pdf` con el dominio real, Cloudflare
      y Umami (1.3); la CI ya lo mide contra `next start` en cada cambio (D-145).
- [ ] Prueba de carga k6 con los pasos de `OPERATIONS.md` (límites por IP subidos, `light_tasks_day` del plan `anon`
      a 1000 en la tabla `plans` y claves de prueba de Turnstile solo durante la prueba, `tests/load/recursos.sh` en el
      servidor) y resultados y concurrencias anotados en `OPERATIONS.md` (D-146, D-148 y D-149). Volver a dejar
      `RATE_LIMIT_PER_MINUTE`, `ANON_TOKENS_PER_IP_DAY`, `light_tasks_day` del plan `anon` (20) y las claves de
      Turnstile de producción al terminar (la cuota, con el valor anotado antes de subirla si se cambió desde la base).
- [ ] Primera ejecución de G0-B en la CI: Lighthouse en el job `web`, regresión visual de la plantilla con el Chromium de
      Playwright y de los PDF en el job `python`; si una captura falla solo por el suavizado del texto, regenerar las
      referencias en la CI con `--update-snapshots` y revisarlas antes de confirmarlas (D-144).
- [ ] escaner-pdf en un Android con Chrome y en un iPhone con Safari: permiso de cámara, borde detectado en vivo,
      varias páginas, filtro Documento con sombras reales, PDF descargado, instalación como aplicación y uso sin conexión
      tras la primera visita; con OCR al terminar, el PDF con texto.
- [ ] crear-collage en un Android con Chrome y en un iPhone con Safari: fotos desde la galería y con la cámara (permiso,
      cambio de cámara), encuadrar arrastrando con el dedo, intercambiar celdas, textos y stickers con los tiradores, y
      el PDF, el JPG y la impresión; en escritorio, un collage de 30 fotos grandes en varias páginas (memoria y tiempo).
- [ ] crear-collage a tamaño real: imprimir al 100 % la hoja de carné (35 × 45 y 26 × 32 mm) y el ID-1 por las dos caras
      en las impresoras de prueba y medirlos con regla; recortar por las marcas de corte. Confirmar antes de anunciarlo
      que las medidas oficiales siguen vigentes (D-107).
- [ ] Transcripción en el VPS: construir worker-av (baja el modelo small, 483 MB; medium solo si se quiere la precisión
      alta, con `--build-arg WHISPER_MODELS="small medium"`), transcribir una entrevista de 10 minutos en español y otra
      en inglés, medir el tiempo (en la máquina de trabajo, 0,72 veces la duración con 2 hilos; ajustar `time_limit` si el
      VPS es más lento) y que el propietario revise la calidad en español antes de anunciarla.
- [ ] copiar-de-pdf con la pila completa en Chrome, Firefox y Safari: reconocer bloques de un informe, copiar una tabla y
      pegarla en Excel y en Word, copiar una imagen, y un escaneo que pasa por el OCR antes del análisis.
- [ ] Lote D2 de F2 con la pila completa: un PDF con tablas a Excel, ODS, CSV y JSON; un informe a PowerPoint en los tres
      modos; un escaneo a Word con OCR; un PDF largo a EPUB fluido y fijo; y convertir-desde-pdf con varios formatos.
      `workerconvert` sin reinicios por memoria (Docling y LibreOffice en el mismo contenedor de 5 GB).
- [ ] Lote D1 de F2 con la pila completa: pdf-a-pdfa de un PDF con fuentes sin incrustar (informe y aviso; con
      «rasterizar», PDF/A-2b que veraPDF acepta), validar-pdfa de un PDF/A real, pdf-a-tiff G4 de 200 páginas y
      pdf-a-txt de un escaneo (cuenta una tarea de OCR); `workerocr` sin reinicios por memoria con veraPDF.
- [ ] Lote C de F5 con la pila completa: raw-a-jpg de un CR2, un NEF y un ARW reales (LibRaw), psd-a-png de un PSD de
      Photoshop con capas y efectos, png-a-svg de un logotipo y quitar-fondo de una foto de producto y de un retrato con
      «Refinar los bordes»; `workermedia` (1,5 GB) sin reinicios por memoria y sin intentos de descarga del modelo.
- [ ] G1-A con la pila completa: la imagen `worker-pdf` construye con el perfil FOGRA39 de `infra/icc` (D-154) y
  pdf-a-jpg en CMYK lo incrusta; `egressweb` y `egressai` arrancan con `conversor-smokescreen` (D-155); en la web en
  inglés, las notas de reparar-pdf, comprimir-pdf y proteger-pdf salen en inglés (D-151).
- [ ] Lote C de F2 con la pila completa: un EPUB a PDF (índice al principio), un CBR en RAR, un DjVu, un EML con
      adjuntos, un MSG de Outlook real, un DXF de un programa de CAD y un .pages; `workermedia` y `workerofficeheavy`
      sin reinicios por memoria (`docker stats`).
