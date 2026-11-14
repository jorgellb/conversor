# Progreso

Estado a 14 de noviembre de 2026. Entrega: **F1 cerrado** (núcleo, lista de lanzamiento de 17.1, resto del catálogo F1 y las
acciones de resultado de 8.2) y **F2 cerrado**: lotes A (11 herramientas PDF de servidor), B (6 del navegador), C (19 a PDF
con programas externos), D1 (6 desde PDF sin Docling), D2 (12 desde PDF con Docling), D3 (copiar-de-pdf) y escaner-pdf; tabla en
`PLAN.md`. **F5 sin vídeo cerrado**: lotes A (audio), B1 (imágenes en el navegador), B2 (códigos QR), C (imágenes en el servidor),
D1 y D2 (crear-collage), E (transcripción) y F (convertir-archivo). **F3 (IA) en curso**: lotes A1 (núcleo de IA y
resumir-pdf), A2 (chat-pdf) y B (preguntas, fichas, presentación y traducción) hechos. **Goal de trabajo continuo**
(`docs/GOAL.md`): lote transversal G0-A (infraestructura de proceso) hecho.

## Cierre técnico

| Comprobación | Resultado |
| --- | --- |
| `pytest` (núcleo, API con PostgreSQL y Valkey reales, herramientas de servidor, HTML/Markdown/TXT/web a PDF con Gotenberg simulado, envío por correo, lote C con Calibre, DjVuLibre, libheif, libarchive y ezdxf reales, lote D1 con tiffcp, pdftocairo, OCRmyPDF y Tesseract reales, lote D2 con Docling 2.145, LibreOffice y Tesseract reales, audio de F5 con FFmpeg real, imágenes de F5 en el servidor con libheif, LibRaw, psd-tools, vtracer y rembg (modelo u2net) reales, transcripción con faster-whisper real (modelo tiny, y small comprobado a mano) y FFmpeg, detección por bytes con los 70 casos compartidos con el navegador, IA con el proveedor falso y transportes simulados (petición 951, reserva Pro, límite por minuto y del chat, 429 resuelto por el siguiente candidato, `data_collection` en todas las peticiones, descubrimiento, reconciliación, sin modelos, sin consentimiento, herramientas excluidas, caché por propietario y resumir-pdf de extremo a extremo con bloques y un escaneo que pasa por la cola de OCR; chat-pdf con eventos, documento entero o búsqueda con vectores reales en pgvector, conversación, errores sin gasto, streaming de OpenRouter simulado con reintento y fallo a mitad, y borrado de cuenta; preguntas en Word y Moodle, fichas en tres formatos, presentación de 2 peticiones con notas y tema, traducción alineada por lotes con glosario y PDF por Gotenberg, párrafos rehechos, GIFT escapado y límites por tarea), operación y seguridad) | 1458 en verde (con la prueba de contrato de 16.6 de las 157 herramientas, D-135), 9 omitidas (veraPDF, modelos de rembg, embeddings y faster-whisper, ctranslate2 y la muestra DOCX no disponibles en el entorno de trabajo) y 4 que fallan solo aquí porque este LibreOffice no tiene Writer ni Impress (pdf-a-word, pdf-a-odt y pdf-a-rtf fieles, pdf-a-ppt y pdf-a-odp, pdf-a-ods; la CI instala `libreoffice-writer-nogui`); la CI ejecuta todas |
| Vitest de `packages/client-tools` (organizar, editar, formularios, recortar, tamaño de página, varias por hoja, folleto, aplanar, redactar con PDFium real, anotar y XFDF, marcadores, capa de texto, metadatos, cortar por la mitad, imprimir, montar, comparar, buscar, escáner con OpenCV.js y las imágenes de F5: BMP, ICO, TIFF y GIF propios comprobados con UTIF, conversiones con jSquash y resvg reales, metadatos y favicon, códigos QR con zxing-cpp, conversor SVG → PDF comparado con resvg, crear-collage: plantillas, encuadre, orientación EXIF comparada con el giro de los códecs, PDF con las fotos sin recomprimir y una sola copia por foto y fuente, imágenes a la resolución pedida, operaciones del editor, tamaño real medido en el PDF renderizado, marcas de corte, resolución en PNG y JPG, fecha EXIF y pies, encabezado y números de página leídos del PDF, detección por bytes con los casos del servidor y un ZIP de 20 MB leído por tramos…) | 264 en verde |
| Vitest de `apps/web` (contenido propio, slugs, mensajes, CSP con y sin Google Drive y Dropbox, papeles de la solicitud, alias y formatos de copiar-de-pdf, rutas de convertir-archivo, aviso de IA literal con la versión del servidor, paridad de flags con `flags.py`, versiones exactas de npm y proyectos de Playwright con las URL simuladas en la CI) | 29 en verde |
| Playwright en navegador (60 pruebas: formularios de preguntas, fichas, presentación y traducción con sus opciones dependientes, chat-pdf con el servidor simulado (preparar, respuesta por trozos con las páginas, conversación que viaja con la siguiente pregunta y presupuesto agotado), resumir-pdf con el servidor simulado (cuenta necesaria, aviso obligatorio que viaja con el trabajo, peticiones que quedan, «no disponible temporalmente» y sin peticiones), convertir-archivo (un PNG llamado .jpg detectado y convertido a ICO en la misma página sin subir nada, enlace compartido con `noindex` y sin canonical, sitemap, audio con salidas de servidor, tipos mezclados y desconocidos), conversor-pdf por los bytes, páginas de transcribir-audio y video-a-subtitulos, crear-collage (intercambio de celdas arrastrando comprobado en el PNG exportado, PDF con la foto sin recomprimir, texto y sticker, foto con la cámara simulada, cabecera de permisos, hoja de carné a tamaño real con 20 copias de una sola foto y documentación fotográfica con la fecha EXIF leída en el navegador), páginas de las imágenes en el servidor (ayuda HEIC con el flag apagado, RAW admitidos y opciones), generar-codigo-qr y leer-codigo-qr (logotipo con corrección H leído por zxing-cpp, WiFi en SVG, SEPA en PDF vectorial, Kanji y UTF-8, degradado y borde, aviso si no se lee, configuración en JSON, QR dentro de un PDF), imágenes de F5 en Chromium (convertir-imagen a AVIF, WEBP, GIF, BMP, TIFF e ICO, TIFF por páginas, GIF animado, SVG con texto, favicon, metadatos y Base64), escaner-pdf con cámara simulada, copiar-de-pdf con el servidor simulado y el portapapeles real, formulario de convertir-desde-pdf, pdf-a-webp en el navegador, lote C de F2 (alias canónico, ayuda HEIC y papeles de la solicitud), lote B de F2, metadatos leídos en el navegador, unir, pdf-a-jpg, numerar, editar, rellenar, contraseña, redactar, varias por hoja y recortar, recorte visual, folleto con vista previa e impresión, anotar, lector con miniaturas y texto seleccionable, crear-pdf y web-a-pdf, «Seguir con otra herramienta», Drive y Dropbox apagados, hreflang y cabeceras) | 60 en verde |
| TypeScript 7 (`tsc --noEmit`) en las dos áreas | Sin errores |
| `next build` (Next 16.4.3) | Correcto |
| Licencias (Python y npm de producción) | 0 problemas en npm; en Python, 0 en las dependencias del proyecto (la `.venv` local tiene además los paquetes CUDA de NVIDIA que trae un torch sin `--index-url .../cpu`, instalado fuera de G0-A; la CI y las imágenes usan el torch de CPU) |
| `registry.json` (157 herramientas), `docs/TOOLS.md` y `docs/ERRORS.md` (`gen_docs.py --check`), `docker-compose.coolify.yml` y los casos de `filetype` al día; los dos Compose válidos con `docker compose config` (solo en la CI: no hay Docker) | Correcto |

## No verificado en esta entrega

- **IA contra OpenRouter real**: no hay clave en el entorno de trabajo. Las pruebas usan el proveedor falso y transportes
  simulados con las respuestas documentadas (429 con `Retry-After`, 404 por la política de datos, 503, JSON). El cierre
  técnico de F3 (uso real de peticiones registrado) necesita la clave del propietario. `egressai`, la imagen `worker-ai`
  (con el modelo de embeddings) y `workeraiembed`, sin Docker, como el resto de imágenes; la prueba de chat-pdf con la pila
  completa (`servidor.spec.ts`) queda para la CI.

- **Imágenes Docker y arranque de humo del Compose**: el entorno de trabajo no tiene demonio de Docker. Las imágenes y
  la prueba `e2e-compose` se ejecutan en GitHub Actions; es el primer paso pendiente.
- **Conversiones reales con Gotenberg** de html-a-pdf, markdown-a-pdf, txt-a-pdf, web-a-pdf y, del lote C, svg-a-pdf,
  eml-a-pdf, msg-a-pdf, dxf-a-pdf, pages/keynote/numbers/visio/publisher-a-pdf y el índice de solicitud-de-empleo-pdf: las
  pruebas simulan Gotenberg y comprueban lo que se le envía; el HTML de Markdown, TXT y de un correo se ha impreso con el
  Chromium local para revisar el resultado. Si LibreOffice importa bien un .pages, .key, .numbers, .vsd o .pub real
  solo se sabrá con la pila completa.
- **veraPDF**: el instalador no se ha podido ejecutar en el entorno de trabajo (código externo). pdf-a-pdfa y
  validar-pdfa se han probado con OCRmyPDF y Tesseract reales y un informe de veraPDF de ejemplo; la CI instala veraPDF
  1.30.3 y ejecuta la prueba real (D-63).
- **Imagen `worker-media`**: la compilación de libheif solo para decodificar (D-49) no se ha podido probar sin Docker; en
  el entorno de trabajo, heic-a-pdf se ha probado con el libheif del sistema. Los flags de `gotenbergweb` (`--chromium-proxy-server`, `--libreoffice-disable-routes`) se comprueban
  en el arranque de humo.
- **Smokescreen**: la etiqueta `v0.1.0` sale del proxy de módulos de Go; no se pudo consultar GHCR (D-30).
- **Playwright del proyecto `servidor`**, la parte de servidor de `lector-pdf` y el formulario «Enviar por correo» en la
  web: pendientes de la ejecución con la pila completa (la API del envío sí tiene pruebas con PostgreSQL real).
- **Google Drive y Dropbox** contra los servicios reales: hacen falta las claves del propietario (D-36).
- **Lighthouse** (1.3) y **prueba de carga k6** (16.1): en el VPS.
- **veraPDF** para la salida PDF/A de ocr-pdf (16.6).
- **G0-A**: `gen_coolify_compose.py --validate` y `docker compose config` con las variables `${MEM_*}` y `${CPUS_*}`, y la imagen `worker-av` con el FFmpeg 8.1 fijado por fecha y SHA-256 (D-137): solo en la CI, sin Docker. El audio de F5 con ese binario, en la CI de imágenes (DEPLOY-CHECKLIST).

## Herramientas y página de herramienta

Todo el catálogo F1 de la sección 7 está hecho con las opciones del Anexo A (salvedades en D-23 a D-26):

- **Navegador:** recortar-pdf (también en modo visual), cambiar-tamano-pagina-pdf, varias-paginas-por-hoja,
  folleto-pdf (con vista previa, hojeado e impresión), aplanar-pdf, redactar-pdf, anotar-pdf, lector-pdf (híbrida, con
  miniaturas, marcadores y texto seleccionable), webp-a-pdf, gif-a-pdf y bmp-a-pdf, además de las de 17.1.
- **Servidor:** html-a-pdf, markdown-a-pdf, txt-a-pdf (con Chromium, A.8) y web-a-pdf, además de las de 17.1.
- **Páginas índice:** conversor-pdf y crear-pdf.
- **Resultado (8.2.4):** descargar, imprimir los PDF, «Seguir con otra herramienta», enviar por correo (cuentas
  registradas, D-35) y guardar en Google Drive o Dropbox; en la zona de subida, abrir desde Google Drive o Dropbox
  (los dos detrás de sus flags, D-36).
- Contenido propio redactado para 8 herramientas (es y en), pendiente de la revisión del propietario (D-15). El resto
  de páginas lleva `noindex` hasta tener contenido revisado (D-31).

## F2, lote A (servidor)

reparar-pdf, optimizar-pdf-web, pdf-escala-de-grises, pdf-modo-oscuro, extraer-imagenes-pdf, metadatos-pdf,
eliminar-metadatos-pdf, rasterizar-pdf, preferencias-visor-pdf, superponer-pdf y tiff-a-pdf, con las opciones del
Anexo A y pruebas sobre el resultado (colores en píxeles, texto que se puede buscar, enlaces, XMP, linealizado…).
Salvedades en D-38 a D-43.

## F2, lote B (navegador)

cortar-paginas-por-la-mitad (también deshace la imposición de un folleto escaneado), imprimir-pdf (vista previa por
hoja y asistente de doble cara manual), montar-pdf (tablero de columnas con arrastrar y soltar), comparar-pdf (texto,
superposición, deslizador e informe PDF), buscar-en-pdf (muchos archivos, página resaltada y CSV) y marcadores-pdf
(editor de árbol con destino, estilo y estado). Nada sale del navegador. Salvedades en D-44 a D-48.

## F2, lote C (a PDF con programas externos)

svg-a-pdf, heic-a-pdf (detrás de `HEVC_DECODE_ENABLED`, con ayuda para pasar a JPEG mientras esté apagado),
pages/keynote/numbers/visio/publisher-a-pdf y el alias pub-a-pdf, epub/mobi/azw3/fb2-a-pdf con Calibre (índice al
principio y numeración de páginas que coincide), cbz/cbr-a-pdf (también RAR), djvu-a-pdf, eml-a-pdf y msg-a-pdf
(cabeceras, cuerpo saneado, imágenes incrustadas y adjuntos convertibles como páginas siguientes), dxf-a-pdf y
solicitud-de-empleo-pdf. Nuevo `workermedia`; los trabajos guardan el idioma de la página para los textos que van
dentro del resultado. Salvedades en D-49 a D-59.

## F2, lote D1 (desde PDF sin Docling)

pdf-a-txt (OCR solo de las páginas escaneadas, que cuenta como tarea de OCR), pdf-a-tiff (G4, G3, LZW, PackBits, CMYK
con perfil ICC, multipágina o una imagen por página), pdf-a-webp (en el navegador), pdf-a-svg, pdf-a-pdfa (sin
Ghostscript, con informe de veraPDF y alternativa rasterizada) y validar-pdfa (PDF/A-1 a 4 y PDF/UA, explicación de
cada regla en lenguaje sencillo e informe descargable). pdf-a-jpg admite CMYK en el servidor. Salvedades en D-60 a D-66.

## F2, lote D2 (desde PDF con Docling)

pdf-a-excel y pdf-a-ods (una hoja por tabla, números de verdad), pdf-a-ppt y pdf-a-odp (editable con cada bloque en su
sitio, editable con la página sin texto de fondo, o fiel con LibreOffice), pdf-a-odt y pdf-a-rtf, pdf-a-markdown (tablas
GFM e imágenes en ZIP), pdf-a-html y pdf-a-epub (diseño fluido o fijo con texto seleccionable), pdf-a-csv, pdf-a-json y la
página única convertir-desde-pdf, cuyo formulario cambia con el formato. pdf-a-word usa ya el OCR de Tesseract. Probado con
Docling 2.145, LibreOffice y Tesseract reales. Salvedades en D-67 a D-73.

## F2, lote D3 (copiar-de-pdf)

El PDF se ve y se selecciona en el navegador sin subirlo; al pedir los bloques, Docling reconoce títulos, párrafos, listas,
tablas, imágenes e índices, que se resaltan al pasar el ratón y se copian con un clic con formato para Word y el correo,
como tabla para Excel, texto, Markdown, HTML, CSV o JSON. Documento entero en Markdown, tablas en XLSX y página como PNG.
Los escaneos pasan antes por el OCR con enderezado. Salvedades en D-74 y D-75.

## F2, escaner-pdf

Cámara con el borde del papel detectado en vivo, corrección de perspectiva, filtros (documento en blanco y negro, gris,
color realzado u original), fotos desde la galería, girar, reordenar, repetir y quitar páginas, tamaño automático, A4 o
Carta, y OCR opcional al terminar. Todo en el navegador con OpenCV.js en un worker; la cámara solo se permite en esa
página y el escáner tiene acceso directo en la aplicación instalada. Salvedades en D-76.

## F5, lote A (audio)

aac, flac, wav, wma, amr y aiff a MP3, ogg-a-wav y mp3-a-wav, cortar-audio (con fundidos), unir-audios (con silencio o
fundido cruzado), normalizar-volumen (−16, −14 o −23 LUFS en dos pasadas) y cambiar-velocidad-audio (con o sin conservar
el tono), con la salida en MP3, WAV o el mismo formato. Probado con FFmpeg real. Salvedades en D-78.

## F5, lote B1 (imágenes en el navegador)

jpg-a-png, webp-a-png, gif-a-png, jpg-a-webp, png-a-webp, avif-a-jpg, jpg-a-avif, bmp-a-jpg, tiff-a-jpg (una imagen por
página), png-a-ico y convertir-imagen (JPG, PNG, WEBP, AVIF, GIF, BMP, TIFF e ICO en cualquier combinación, también desde
SVG), svg-a-png y svg-a-jpg (resvg, A.10), crear-favicon (ICO, iconos de Apple y Android, maskable, manifiesto y código
HTML), quitar-metadatos-foto (todo o solo el GPS, sin recomprimir) e imagen-a-base64. Todo en el navegador, sin subir
nada. El WebAssembly (también PDFium) se sirve desde `/codecs/` con el resumen del contenido en el nombre (D-80).
Salvedades en D-79 a D-86.

## F5, lote B2 (códigos QR)

generar-codigo-qr con todos los tipos de A.1 (URL, WiFi, texto, vCard, SEPA, PayPal, correo, teléfono, SMS y evento),
logotipo (con corrección H), colores y degradados, formas, borde, versión, modo (también Kanji) y corrección; salida en
PNG, SVG o PDF vectorial, copia al portapapeles, configuración en JSON y lectura de comprobación con zxing-cpp.
leer-codigo-qr lee QR y otros códigos de imágenes y PDF. Todo en el navegador. Salvedades en D-88 a D-94.

## F5, lote C (imágenes en el servidor)

heic-a-jpg y heic-a-png (con EXIF y sin GPS; detrás de `HEVC_DECODE_ENABLED`), raw-a-jpg (CR2, NEF, ARW y DNG con
LibRaw en un proceso aparte), psd-a-png (imagen completa o cada capa), png-a-svg y jpg-a-svg (vtracer) y quitar-fondo
(rembg con el modelo u2net dentro de la imagen; nunca bria-rmbg). Todo en `workermedia`. Salvedades en D-95 a D-99; el
modelo de quitar-fondo lo confirma el propietario (DEPLOY-CHECKLIST).

## F5, lote D1 (crear-collage)

Editor en la página con Konva: plantillas de cuadrícula, mosaico, filas, corazón, círculo, estrella, instantáneas y
colocación libre (1 a 30 fotos por página y varias páginas); encuadre arrastrando, zoom, intercambio de celdas,
separación, margen y esquinas; textos con fuentes Noto, stickers y formas propios, marcos, sombras y fondo de color,
degradado o foto; fotos desde archivo o con la cámara; deshacer y rehacer. Salida en PDF con las fotos sin recomprimir,
JPG o PNG a 150, 300 o 600 ppp, o impresión. Todo en el navegador. Salvedades en D-100 a D-106.

## F5, lote D2 (crear-collage: tamaño real y documentación fotográfica)

Tamaño real con marcas de corte: fotos de carné de la UE y visados (35 × 45 mm) y de DNI y pasaporte (26 × 32 mm,
comprobadas en el BOE), documento ID-1 por las dos caras, tarjetas, copias de foto y medidas a mano; una foto llena la
hoja con el mismo encuadre en todas las copias, y PNG y JPG llevan la resolución para imprimirse a su tamaño.
Documentación fotográfica: fotos enteras con pie numerado, fecha de captura del EXIF y texto propio, encabezado y
números de página. Salvedades en D-107 a D-110.

## F5, lote E (transcripción local)

transcribir-audio (TXT, DOCX y SRT, con el minuto de cada párrafo si se pide) y video-a-subtitulos (SRT y VTT con líneas
del ancho elegido) con faster-whisper en CPU: modelo small en int8 dentro de la imagen, idioma detectado o elegido entre
20 y filtro de silencios, en la cola pesada de av con su propio worker. Sin PyAV, cuyas ruedas traen x264 y x265: decodifica
el FFmpeg LGPL de la imagen. Sin IA externa ni consentimiento. Salvedades en D-111 a D-114.

## F5, lote F (convertir-archivo)

`/es/convertir-archivo` y `/en/file-converter`: el tipo real se detecta en el navegador por los bytes (un PNG llamado
.jpg es un PNG), sin subir nada, con los mismos casos de prueba que el detector del servidor, y solo se ofrecen las salidas
posibles, agrupadas y con el sitio donde se hacen. La conversión elegida se hace en la misma página con el archivo ya
puesto y el formato fijado; los enlaces con la conversión llevan `noindex`. conversor-pdf también mira los bytes.
Salvedades en D-115 a D-118.

## F3, lote A1 (núcleo de IA y resumir-pdf)

Modelos gratuitos de OpenRouter descubiertos solos (precio 0, contexto, salida máxima, JSON e imagen), hasta 3
candidatos por petición con `data_collection: "deny"` siempre, reintentos con el siguiente candidato y el enrutador como
último recurso; presupuesto diario en Valkey con reserva Pro, límite por minuto con la parte del chat, reconciliación con
`/key` y cuota de cada usuario; consentimiento del aviso de 6.6; caché por propietario; `workerai` y `egressai` (solo
OpenRouter). resumir-pdf con una petición si cabe y por bloques si no, escaneos leídos con OCR en la cola `ocr`, y la
página dice cuántas peticiones quedan hoy. Sin clave, en desarrollo, un proveedor falso determinista. Salvedades en D-119
a D-126.

## F3, lote A2 (chat-pdf)

Preguntas sobre un PDF con respuesta por trozos que cita las páginas. Preparar el documento no gasta peticiones: texto
(con OCR si hace falta) y, si es largo, fragmentos con su vector (fastembed, modelo multilingüe dentro de la imagen) en
pgvector, en un worker propio sin clave ni salida. Cada pregunta gasta una petición: el documento entero si cabe con la
conversación, o los 8 fragmentos más cercanos y sus vecinos. La API retransmite como eventos lo que `workerai` escribe en
un stream de Valkey. Salvedades en D-127 a D-129.

## F3, lote B (generar a partir de un PDF)

generador-de-preguntas (test, verdadero o falso, respuesta corta o mezcla; Word para imprimir con soluciones, Moodle o
texto), pdf-a-fichas (Anki o Quizlet, CSV o Word para recortar), pdf-a-presentacion (PowerPoint 16:9 con tres estilos y
notas del orador, en las 2 peticiones de 6.3) y traducir-pdf (12 idiomas, Word y PDF con maquetación simplificada,
términos que no se traducen) detrás de `TranslationProvider`. JSON con esquema validado y, si el documento o lo pedido no
caben, varias peticiones reservadas antes de empezar. Salvedades en D-130 a D-133.

## G0-A (infraestructura de proceso)

Prueba de contrato de 16.6 para todo el registro (`tests/test_contrato_opciones.py`): el `options_schema` de
`GET /v1/tools` es el del modelo y el de `registry.json`, los valores por defecto son válidos y cada mínimo, máximo,
patrón, longitud y lista cerrada da `INVALID_OPTIONS` en `POST /v1/jobs`, también con PostgreSQL y Valkey reales; la
tabla `tests/anexo_a_minimos.py` comprueba las opciones del Anexo A y apunta lo que falta. `ToolSpec.default_enabled`
en la API, la web y el panel de administración; flags temáticos iguales en `flags.py` y `flags.ts`; `gen_docs.py` con
estado, desactivadas con su motivo (`config/tools-notes.yaml`), 7.24 y la paridad con las 124 herramientas de PDF24
(`config/pdf24.yaml`); Playwright con f4, f6 y f7 y las URL simuladas en la CI; «firmas», «csig», «p7m» y «xsig» fuera
de la IA; FFmpeg fijado por fecha y SHA-256; diff-match-patch sin `^`; `${MEM_<NOMBRE>}` y `${CPUS_<NOMBRE>}` con el
perfil de 16 vCPU; tablas por lotes en `PLAN.md`. Salvedades en D-134 a D-141.

## Pendiente

- Huecos documentados: método «eliminar bajo el área» de redactar (D-25, A.6 solo lo permite si pasa sus pruebas) y
  enlaces pulsables en el lector (D-23).
- F3: lotes C, D y E (`PLAN.md`); después F4, F6, vídeo de F5 y F7, en el orden de 17 (ondas de `docs/GOAL.md`).
- Huecos del Anexo A sin lote: autoorientar de girar-pdf (A.4) y el Modo de pdf-a-excel, pdf-a-ods y pdf-a-txt (A.9),
  apuntados en `PENDIENTES` de `tests/anexo_a_minimos.py` (D-135).
- Cierre técnico de F3 (17): uso real de peticiones registrado, con la clave de OpenRouter del propietario.
- JPG y PNG siguen con el codificador del lienzo (D-04 y D-79): MozJPEG y oxipng no se han añadido.
- Notas de las herramientas de los lotes anteriores en inglés (D-42 y D-54).

## Cierre operativo de F1

Pendiente de las entradas del propietario (0.1); pasos en `DEPLOY-CHECKLIST.md` (incluye el digest de Smokescreen y
las pruebas de salida de `egressweb`).
