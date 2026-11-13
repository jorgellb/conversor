# Plan (17)

El plan completo está en `docs/spec/` (v2). Orden de ejecución acordado (17): núcleo de F1 y lista de lanzamiento
(17.1) → lanzamiento público → resto de F1 → F2 → F5 sin vídeo → F3 → F4 → F6 → vídeo de F5 → F7.

## Entrega anterior: núcleo de F1 y lista de lanzamiento

| Bloque | Estado |
| --- | --- |
| Monorepo, Compose local y de Coolify, imágenes por grupo | Hecho (imágenes sin construir aquí: no hay Docker en el entorno de trabajo) |
| Autenticación (Better Auth: correo y contraseña, enlace mágico, Google opcional, JWT, administración) | Hecho |
| Anónimos con Turnstile, cuotas por plan y por IP, límite por minuto | Hecho |
| tusd con ganchos bloqueantes, Caddy con `forward_auth`, trabajos, idempotencia, secretos cifrados | Hecho |
| Limpieza, guardas de disco y de colas, latido y `WORKER_LOST`, rol limitado de PostgreSQL | Hecho |
| Copias (`pg_dump` y restic) y restauración | Hecho (restic remoto pendiente de un repositorio real) |
| Planes, `FakePaymentProvider` y Stripe en modo test (checkout, portal y webhook idempotente) | Hecho (faltan claves y precios del propietario) |
| Herramientas de navegador de 17.1 | Hechas, incluidas `editar-pdf` y `rellenar-pdf` |
| Herramientas de servidor de 17.1 | Hechas |
| Web: portada, plantilla de herramienta, precios, cuenta, administración básica, legales, SEO y PWA | Hecho |
| `conversor-pdf` | Versión mínima: elige la herramienta según la extensión |

## Esta entrega: resto de F1

| Bloque | Estado |
| --- | --- |
| recortar-pdf, cambiar-tamano-pagina-pdf, varias-paginas-por-hoja, folleto-pdf, aplanar-pdf | Hecho en el navegador (sin modo visual de recorte ni vista previa del folleto, D-26) |
| webp-a-pdf, gif-a-pdf, bmp-a-pdf | Hecho en el navegador |
| redactar-pdf con búsqueda, patrones (DNI/NIE, IBAN, correo, teléfono), rasterizado a 300 ppp y comprobación | Hecho (solo el método de rasterizar, D-25) |
| anotar-pdf con anotaciones estándar, lista de comentarios, guardar aplanadas y XFDF | Hecho (D-24) |
| lector-pdf: visor con zoom, búsqueda, descarga e impresión; otros formatos convertidos en servidor | Hecho (D-23) |
| html-a-pdf, markdown-a-pdf y txt-a-pdf con el Chromium de `gotenberg` sin red | Hecho (D-27 y D-28) |
| web-a-pdf con `gotenbergweb` y `egressweb` (Smokescreen) y la red `webrender` | Hecho (D-29 y D-30) |
| crear-pdf (página índice) | Hecho: enlaza solo herramientas que existen |

## Cierre de F1

| Bloque | Estado |
| --- | --- |
| Lector con miniaturas, marcadores y texto seleccionable | Hecho (D-23) |
| Recorte en modo visual; folleto con vista previa, hojeado e impresión | Hecho (D-26) |
| Imprimir resultados PDF desde el navegador | Hecho |
| Enviar por correo (enlace de 24 h, límites por plan y por día, Turnstile, abuso) | Hecho (D-35) |
| Abrir desde y guardar en Google Drive y Dropbox, detrás de flags | Hecho, sin probar contra los servicios reales (D-36) |
| `connect-src blob:` («Seguir con otra herramienta» con resultados del navegador) | Corregido (D-37) |

## F2 (cerrado)

F2 tiene unas 55 herramientas; se hace por lotes, cada uno con sus pruebas:

| Lote | Herramientas | Estado |
| --- | --- | --- |
| A. PDF de servidor con pikepdf y pypdfium2 | reparar-pdf, optimizar-pdf-web, pdf-escala-de-grises, pdf-modo-oscuro, extraer-imagenes-pdf, metadatos-pdf, eliminar-metadatos-pdf, rasterizar-pdf, preferencias-visor-pdf, superponer-pdf, tiff-a-pdf | Hecho (D-38 a D-43) |
| B. Navegador | cortar-paginas-por-la-mitad, imprimir-pdf, montar-pdf, comparar-pdf, buscar-en-pdf y marcadores-pdf | Hecho (D-44 a D-48); copiar-de-pdf pasa al lote D y escaner-pdf queda pendiente |
| C. A PDF con programas externos | svg-a-pdf, heic-a-pdf, pages/keynote/numbers/visio/publisher-a-pdf (y pub-a-pdf), epub/mobi/azw3/fb2-a-pdf, cbz/cbr-a-pdf, djvu-a-pdf, eml/msg-a-pdf, dxf-a-pdf, solicitud-de-empleo-pdf | Hecho (D-49 a D-59); heic-a-pdf, detrás de `HEVC_DECODE_ENABLED` |
| D1. Desde PDF sin Docling (A.5, A.6 y A.9) | pdf-a-txt, pdf-a-tiff, pdf-a-webp, pdf-a-svg, pdf-a-pdfa, validar-pdfa y CMYK en pdf-a-jpg | Hecho (D-60 a D-66) |
| D2. Desde PDF con Docling (A.9) | pdf-a-excel, pdf-a-ppt, pdf-a-odt/ods/odp/rtf, pdf-a-markdown, pdf-a-html, pdf-a-csv, pdf-a-json, pdf-a-epub y convertir-desde-pdf | Hecho (D-67 a D-73) |
| D3. copiar-de-pdf (híbrida, A.4) | Bloques reconocidos con Docling y copia con formato | Hecho (D-74 y D-75) |
| E. escaner-pdf (A.4) | Cámara con detección de bordes y perspectiva (OpenCV.js), filtros, páginas y PDF; PWA | Hecho (D-76) |

## F5 sin vídeo (cerrado)

Se hace por lotes, cada uno con sus pruebas; el vídeo de F5 va después de F6 (17):

| Lote | Herramientas | Estado |
| --- | --- | --- |
| A. Audio | aac, flac, wav, wma, amr y aiff a MP3, ogg-a-wav, mp3-a-wav, cortar-audio, unir-audios, normalizar-volumen y cambiar-velocidad-audio (ogg, opus, m4a y mp4 a MP3 se adelantaron en F1) | Hecho (D-78) |
| B1. Imágenes en el navegador | jSquash, conversiones entre JPG, PNG, WEBP, AVIF, GIF, BMP, TIFF e ICO y convertir-imagen, crear-favicon, quitar-metadatos-foto, imagen-a-base64, svg-a-png y svg-a-jpg | Hecho (D-79 a D-86) |
| B2. Códigos QR | leer-codigo-qr (zxing-wasm) y generar-codigo-qr (qr-code-styling, opciones de A.1) | Hecho (D-88 a D-94) |
| C. Imágenes en el servidor | heic-a-jpg y heic-a-png (flag HEVC), raw-a-jpg, psd-a-png, png-a-svg y jpg-a-svg, quitar-fondo | Hecho (D-95 a D-99) |
| D1. crear-collage | Plantillas, edición, adornos, fotos con la cámara y salida en PDF (fotos sin recomprimir), JPG, PNG o impresión; Konva en la página y el worker para exportar | Hecho (D-100 a D-106) |
| D2. crear-collage: tamaño real y documentación | Fotos de carné (UE y visados 35 × 45 mm; DNI y pasaporte 26 × 32 mm, comprobadas en el BOE) con marcas de corte, ID-1 anverso y reverso, tarjetas, copias, una foto en todas las celdas y documentación fotográfica (pie numerado con la fecha EXIF, encabezado y números de página) | Hecho (D-107 a D-110) |
| E. Transcripción | transcribir-audio (TXT, DOCX y SRT) y video-a-subtitulos (SRT y VTT) con faster-whisper local, sin PyAV (traducir-subtitulos y resumir-reunion necesitan el LLM de F3) | Hecho (D-111 a D-114) |
| F. convertir-archivo | Conversor universal: tipo detectado por los bytes en el navegador, solo las salidas posibles (sacadas del registro) y la conversión en la misma página; conversor-pdf también mira los bytes | Hecho (D-115 a D-118) |

## F3: IA (en curso)

Se hace por lotes, cada uno con sus pruebas (D-119):

| Lote | Herramientas | Estado |
| --- | --- | --- |
| A1. Núcleo de IA y resumir-pdf | `LLMProvider` (OpenRouter y falso), descubrimiento de modelos, limitador y presupuesto en Valkey con reserva Pro, reconciliación con `/key`, consentimiento, caché por propietario, `workerai` y `egressai`, texto de los PDF con OCR de escaneos en `ocr`, panel de IA en la página y en administración; resumir-pdf | Hecho (D-120 a D-126) |
| A2. chat-pdf | Embeddings locales (fastembed) en pgvector con su propio worker, `POST /v1/ai/chat` con eventos por un stream de Valkey, interfaz de chat con las páginas citadas y Playwright con LLM falso (16.1) | Hecho (D-127 a D-129) |
| B. Documento con LLM | generador-de-preguntas (Word, Moodle y texto), pdf-a-fichas (Anki o Quizlet, CSV y Word), pdf-a-presentacion (python-pptx, 2 peticiones) y traducir-pdf (`TranslationProvider`, Word y PDF con maquetación simplificada) | Hecho (D-130 a D-133) |
| C. Imagen y datos | imagen-a-texto (Tesseract), imagen-a-excel (OCR, Docling y LLM si hace falta) y ticket-a-excel | Pendiente |
| D. Voz | pdf-a-audio (Kokoro con fonemas de espeak-ng como proceso externo) | Pendiente |
| E. IA de audio (de F5) | traducir-subtitulos y resumir-reunion | Pendiente |

## Siguiente paso

1. Construir las imágenes en GitHub Actions y hacer el arranque de humo del Compose (`e2e-compose` en la CI),
   incluidas `gotenbergweb` y `egressweb`.
2. Cierre operativo de F1 con las entradas del propietario (0.1): VPS, Cloudflare, Stripe, SMTP y repositorio de restic.
3. Revisión del contenido propio redactado y contenido del resto de páginas para quitar el `noindex`.
4. F3: lote C (tabla de arriba); después F4, F6, vídeo de F5 y F7 (orden de 17).
