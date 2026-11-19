# Arquitectura

```text
Navegador ──HTTPS──▶ Cloudflare ──▶ Traefik (Coolify)
                                     ├─▶ web     (Next.js: páginas, Better Auth, herramientas de navegador en Web Worker)
                                     ├─▶ api     (FastAPI pública: sesión anónima, trabajos, cuenta, pagos, admin)
                                     ├─▶ upload  (tusd ──ganchos──▶ apiint)
                                     └─▶ files   (Caddy ──forward_auth──▶ apiint)
apiint (red interna): ganchos de tusd, /files/authorize, métricas, copias
Celery (Valkey) ─▶ workerpdf · workerocr · workeroffice(+heavy) · workermedia · workerconvert · workerav(+heavy) · workerai ─▶ gotenberg (sin red)
workeroffice ─(webrender)─▶ gotenbergweb (web-a-pdf) ─▶ egressweb (Smokescreen) ─▶ internet público
workerai ─(airelay)─▶ egressai (Smokescreen) ─▶ openrouter.ai (solo ese dominio)
workeraiembed (cola ai.embed, embeddings locales, sin salida) ─▶ PostgreSQL (pgvector)
workerutils (cola utils.light, KoSIT en 127.0.0.1:8081 dentro del contenedor, sin salida)
workersign (cola sign, token SoftHSM2 y PIN) ─(webrender)─▶ egressweb ─▶ TSA, OCSP y CRL del sello
workersignverify (cola sign.verify, sin token ni PIN) ─(webrender)─▶ egressweb ─▶ lista de confianza de la UE, OCSP y CRL
PostgreSQL (pgvector) · Valkey · volumen filestore (/srv/files) · volumen backups (/srv/backups) · volumen eutl (/srv/eutl) · volumen softhsm (solo workersign)
```

## Dónde se procesa (5.1)

- **Navegador**: `packages/client-tools` dentro de `apps/web/src/workers/client-tool.worker.ts`. PDFium renderiza;
  `@cantoo/pdf-lib` edita; el lienzo decodifica y codifica JPG y PNG; jSquash (AVIF y WebP), resvg (SVG), UTIF (TIFF),
  gifenc y los codificadores propios de BMP, TIFF e ICO hacen el resto de imágenes (D-79); zxing-cpp lee los códigos QR.
  generar-codigo-qr compone el SVG en la página con qr-code-styling y el worker lo pinta, lo comprueba y lo pasa a PDF
  vectorial (D-88). crear-collage edita con Konva en la página y el worker compone cada página en SVG para el PDF (fotos
  sin recomprimir) o la imagen (D-101). Todo el WebAssembly se sirve desde `/codecs/` con el resumen del contenido en el nombre (D-80). El
  archivo nunca sale del dispositivo (Playwright lo comprueba).
- **convertir-archivo**: el tipo se detecta en el navegador (`client-tools/src/filetype.ts`, con los mismos casos que
  `core/filetype.py`) y las salidas salen del registro (`apps/web/src/lib/conversions.ts`); la conversión la hace, en la
  misma página, la herramienta que gana para ese par, con el formato fijado (D-115 a D-117).
- **IA** (`workerai`, cola `ai`, F3): la API comprueba el consentimiento y la disponibilidad y reserva peticiones (cuota del
  usuario en `usage_daily` y presupuesto global en Valkey) sin salir a internet; `workerai`, el único con la clave, lee el
  texto con pypdfium2 (los escaneos pasan por `ocr` y vuelven), reserva el resto, pide a OpenRouter hasta 3 candidatos
  gratuitos con `data_collection: "deny"` por `egressai` y devuelve lo no usado. Descubrimiento de modelos y
  reconciliación con `/key` son tareas de beat en la cola `ai` (D-120 a D-126).
- **chat-pdf**: preparar el documento va a `workeraiembed` (cola `ai.embed`): texto y, si es largo, fragmentos con su vector
  (fastembed) en `document_chunks`. Cada pregunta: la API reserva una petición y encola; si el documento tiene fragmentos,
  `workeraiembed` busca los más cercanos y pasa a `workerai`, que responde por trozos en un stream de Valkey que la API
  retransmite al navegador como eventos (D-127 a D-129).
- **Generar a partir de un PDF** (generador-de-preguntas, pdf-a-fichas, pdf-a-presentacion y traducir-pdf, `workerai`):
  JSON con esquema validado, repartido en bloques y tandas según el modelo; traducir-pdf traduce por lotes alineados
  (`TranslationProvider`) e imprime el PDF con el Chromium de `gotenberg` por la red interna (D-130 a D-133).
- **Imágenes con texto y tablas** (F3, lote C): imagen-a-texto, solo en `workerocr` (Tesseract por OCRmyPDF, sin IA).
  imagen-a-excel empieza en `workerconvert` (Docling sobre la imagen enderezada) y solo si no hay tabla, y con la IA
  activada, pasa a `workerai`; ticket-a-excel lee los tickets en `workerocr` y pasa a `workerai`, una petición por ticket.
  El texto del OCR viaja por `document_texts` del propietario (D-159 a D-164).
- **Transcripción** (`workeravheavy`, cola `av.heavy`): FFmpeg decodifica la pista de audio a PCM de 16 kHz en un proceso
  aparte y faster-whisper (modelo small en int8 dentro de la imagen) la transcribe por tramos de 20 minutos; sin PyAV (D-111).
- **Voz de pdf-a-audio** (`workeravheavy`, cola `av.heavy`): la API cuenta antes de encolar, en un proceso aparte, los
  caracteres que se van a leer (`ToolSpec.precheck`, 9.3); el worker saca el texto con pypdfium2 (`document_texts`; los
  escaneos pasan por `workerocr` y vuelven), quita cabeceras y números de página, espeak-ng (proceso externo) da los
  fonemas, Kokoro en ONNX Runtime la voz por frases y FFmpeg LGPL el MP3 por tramos de 10 minutos (D-166 a D-173;
  un recuento que no termina en 90 s no se encola).
- **Grabaciones con IA** (F3, lote E: traducir-subtitulos y resumir-reunion): los subtítulos SRT, VTT o ASS se traducen
  directamente en `workerai` (pysubs2 y `TranslationProvider`, un elemento JSON por subtítulo, tiempos intactos); un audio
  o un vídeo empieza en `workeravheavy` (resumir-reunion siempre; traducir-subtitulos pasa de `ai` a `av.heavy`), que mide
  el tramo, estima y reserva las peticiones antes de transcribir, transcribe con faster-whisper y deja los subtítulos o los
  párrafos en `document_texts` del propietario; después `workerai` hace las peticiones (acta por bloques y una final si no
  cabe). `workeravheavy` no tiene la clave de OpenRouter y `workerai` no tiene FFmpeg ni Whisper (D-174 a D-178).
- **Híbridas**: imágenes a PDF y PDF a imágenes pasan al servidor con TIFF o con más de `CLIENT_MAX_MB`; `lector-pdf` abre los PDF en el navegador y convierte en servidor (motor de convertir-a-pdf) lo que no es PDF.
- **Servidor**:
  1. Identidad: JWT de Better Auth (`/api/auth/token`, EdDSA, `iss` y `aud` = `BETTER_AUTH_URL`) o token anónimo de
     24 h con Turnstile (`POST /v1/session/anon`).
  2. Subida por tus (Uppy) a `upload.`; `pre-create` valida identidad, tamaño, extensión, cuota, ritmo y disco y
     reserva espacio; `pre-finish` calcula sha256 y el tipo real (`ready` o `rejected`).
  3. `POST /v1/jobs`: opciones validadas con el modelo Pydantic de la herramienta, secretos cifrados (AES-GCM),
     idempotencia, cuota atómica, guarda de colas; mueve las subidas a `jobs/<id>/in/` y encola con prioridad por plan.
  4. Progreso por SSE leído con `fetch` (la API solo autentica por cabecera) y consulta de respaldo.
  5. Descarga por `files.` con token HMAC de 15 minutos que valida `apiint`.

## Trabajos (5.3)

`jobs.attempts` y `start_attempt` descartan entregas repetidas; latido cada 30 s; beat reencola los trabajos sin latido
y al tercer intento los deja en `WORKER_LOST`. Los errores transitorios (Gotenberg ocupado) se reintentan con el mismo
sobre cifrado. Las colas `office` y `av` tienen procesos `light` y `heavy`; Calibre va en `office.heavy`.
Cada trabajo guarda el idioma de la página que lo creó (`jobs.locale`, migración 0003) y la herramienta lo recibe en
`ToolContext.locale` para los textos que van dentro del resultado (D-54).

## Datos

Alembic gestiona las tablas de la API (`apps/api/migrations`); `migrateauth` crea las de Better Auth. Los workers usan
el rol `conversor_worker` (migración 0002). Las cuotas viven en `usage_daily`; las reservas de disco, los contadores de
colas y los límites por minuto, en Valkey.

## Registro

`packages/core/core/registry.py` carga las especificaciones de `packages/tools/tools/*/specs.py` sin importar motores;
`scripts/export_registry.py` genera `packages/registry/registry.json`, que la web importa al compilar para generar páginas,
formularios de opciones (`x-title`, `x-labels`, `x-advanced`, `x-show-if`), sitemap y CSP.
