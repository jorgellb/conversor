# Progreso

Estado a 14 de noviembre de 2026. Entrega: **F1 cerrado** (núcleo, lista de lanzamiento de 17.1, resto del catálogo F1 y las
acciones de resultado de 8.2) y **F2 cerrado**: lotes A (11 herramientas PDF de servidor), B (6 del navegador), C (19 a PDF
con programas externos), D1 (6 desde PDF sin Docling), D2 (12 desde PDF con Docling), D3 (copiar-de-pdf) y escaner-pdf; tabla en
`PLAN.md`. **F5 sin vídeo cerrado**: lotes A (audio), B1 (imágenes en el navegador), B2 (códigos QR), C (imágenes en el servidor),
D1 y D2 (crear-collage), E (transcripción) y F (convertir-archivo). **F3 (IA) en curso**: lotes A1 (núcleo de IA y
resumir-pdf), A2 (chat-pdf), B (preguntas, fichas, presentación y traducción) y C (imagen a texto, imagen a Excel y
ticket a Excel; D-159 a D-165), D (pdf-a-audio con Kokoro y espeak-ng; D-166 a D-173) y E (traducir-subtitulos y
resumir-reunion, de 7.10; D-174 a D-178) hechos. **Goal de trabajo continuo**
(`docs/GOAL.md`): lote transversal G0-A (infraestructura de proceso) hecho (D-134 a D-143) y G0-B (Lighthouse CI, regresión visual, Playwright
de 16.1 y prueba de carga revisada) hecho (D-144 a D-149); G1-A (huecos de F1, F2 y F5 y fallos de la primera CI) hecho
(D-150 a D-158).

## Cierre técnico

| Comprobación | Resultado |
| --- | --- |
| `pytest` (núcleo, API con PostgreSQL y Valkey reales, herramientas de servidor, HTML/Markdown/TXT/web a PDF con Gotenberg simulado, envío por correo, lote C con Calibre, DjVuLibre, libheif, libarchive y ezdxf reales, lote D1 con tiffcp, pdftocairo, OCRmyPDF y Tesseract reales, lote D2 con Docling 2.145, LibreOffice y Tesseract reales, audio de F5 con FFmpeg real, imágenes de F5 en el servidor con libheif, LibRaw, psd-tools, vtracer y rembg (modelo u2net) reales, transcripción con faster-whisper real (modelo tiny, y small comprobado a mano) y FFmpeg, detección por bytes con los 70 casos compartidos con el navegador, IA con el proveedor falso y transportes simulados (petición 951, reserva Pro, límite por minuto y del chat, 429 resuelto por el siguiente candidato, `data_collection` en todas las peticiones, descubrimiento, reconciliación, sin modelos, sin consentimiento, herramientas excluidas, caché por propietario y resumir-pdf de extremo a extremo con bloques y un escaneo que pasa por la cola de OCR; chat-pdf con eventos, documento entero o búsqueda con vectores reales en pgvector, conversación, errores sin gasto, streaming de OpenRouter simulado con reintento y fallo a mitad, y borrado de cuenta; preguntas en Word y Moodle, fichas en tres formatos, presentación de 2 peticiones con notas y tema, traducción alineada por lotes con glosario y PDF por Gotenberg, párrafos rehechos, GIFT escapado y límites por tarea), operación y seguridad) | 1652 en verde (con el lote E de F3: traducir-subtitulos y resumir-reunion de extremo a extremo con FFmpeg, faster-whisper y la voz sintética de Kokoro reales y el proveedor falso, colas `ai` → `av.heavy` → `ai`, un elemento por subtítulo, tramos, límite de peticiones y de minutos y reservas devueltas a mitad de cadena; con el lote D de F3: pdf-a-audio con espeak-ng 1.52, FFmpeg, Kokoro en ONNX y faster-whisper reales (modelos en `KOKORO_HOME` y `WHISPER_HOME`), recuento de caracteres de la API antes de encolar, voz española apagada y párrafos en tiempo lineal; con el lote C de F3: imagen-a-texto con Tesseract y OCRmyPDF reales, imagen-a-excel con Docling real y por la API con su etapa de IA, ticket-a-excel con el OCR real, consentimiento, AI_UNAVAILABLE, reservas devueltas, límite por tarea, caché y PNG gigante; con la prueba de contrato de 16.6 de las 163 herramientas, D-135, la de `gen_docs.py` con el índice de git, D-143, la regresión visual de los PDF de folleto, varias por hoja, numerar y marca de agua con pypdfium2, D-144, y el escenario de k6, D-146), 4 omitidas (veraPDF, modelo u2net de rembg, modelo de embeddings y la muestra DOCX no disponibles en el entorno de trabajo) y 4 que fallan solo aquí porque este LibreOffice no tiene Writer ni Impress (pdf-a-word, pdf-a-odt y pdf-a-rtf fieles, pdf-a-ppt y pdf-a-odp, pdf-a-ods; la CI instala `libreoffice-writer-nogui`); la CI ejecuta todas |
| Vitest de `packages/client-tools` (organizar, editar, formularios, recortar, tamaño de página, varias por hoja, folleto, aplanar, redactar con PDFium real, anotar y XFDF, marcadores, capa de texto, metadatos, cortar por la mitad, imprimir, montar, comparar, buscar, escáner con OpenCV.js y las imágenes de F5: BMP, ICO, TIFF y GIF propios comprobados con UTIF, conversiones con jSquash y resvg reales, metadatos y favicon, códigos QR con zxing-cpp, conversor SVG → PDF comparado con resvg, crear-collage: plantillas, encuadre, orientación EXIF comparada con el giro de los códecs, PDF con las fotos sin recomprimir y una sola copia por foto y fuente, imágenes a la resolución pedida, operaciones del editor, tamaño real medido en el PDF renderizado, marcas de corte, resolución en PNG y JPG, fecha EXIF y pies, encabezado y números de página leídos del PDF, detección por bytes con los casos del servidor y un ZIP de 20 MB leído por tramos, y los PDF de la regresión visual, MozJPEG y oxipng sobre los bytes de salida, redactar con el método «eliminar» (texto, imagen, trazado, grupo, página girada, campos y enlaces, objetos huérfanos) y enlaces del lector…) | 295 en verde |
| Vitest de `apps/web` (contenido propio, slugs, mensajes, CSP con y sin Google Drive y Dropbox, papeles de la solicitud, alias y formatos de copiar-de-pdf, rutas de convertir-archivo, aviso de IA literal con la versión del servidor, paridad de flags con `flags.py` (también el recorte de espacios de `envFlag`), versiones exactas de npm, proyectos de Playwright con las URL simuladas en la CI, referencias de la regresión visual y configuración de Lighthouse CI, rutas de imagen a texto y a Excel y la IA opcional de imagen-a-excel) | 35 en verde |
| Playwright en navegador (73 pruebas: formularios del lote E de F3 (traducir-subtitulos y resumir-reunion con sus formatos de entrada y valores por defecto) y del lote C de F3 (imagen a texto sin panel de IA, imagen a Excel con el panel que desaparece al apagar la IA y ticket a Excel con sus opciones de CSV), regresión visual de la plantilla en móvil y escritorio (D-144), flujos de servidor de comprimir-pdf, word-a-pdf, pdf-a-word y ogg-a-mp3 con tus, eventos y descarga firmada simulados y pago con FakePaymentProvider (D-147), formularios de preguntas, fichas, presentación y traducción con sus opciones dependientes, chat-pdf con el servidor simulado (preparar, respuesta por trozos con las páginas, conversación que viaja con la siguiente pregunta y presupuesto agotado), resumir-pdf con el servidor simulado (cuenta necesaria, aviso obligatorio que viaja con el trabajo, peticiones que quedan, «no disponible temporalmente» y sin peticiones), convertir-archivo (un PNG llamado .jpg detectado y convertido a ICO en la misma página sin subir nada, enlace compartido con `noindex` y sin canonical, sitemap, audio con salidas de servidor, tipos mezclados y desconocidos), conversor-pdf por los bytes, páginas de transcribir-audio y video-a-subtitulos, crear-collage (intercambio de celdas arrastrando comprobado en el PNG exportado, PDF con la foto sin recomprimir, texto y sticker, foto con la cámara simulada, cabecera de permisos, hoja de carné a tamaño real con 20 copias de una sola foto y documentación fotográfica con la fecha EXIF leída en el navegador), páginas de las imágenes en el servidor (ayuda HEIC con el flag apagado, RAW admitidos y opciones), generar-codigo-qr y leer-codigo-qr (logotipo con corrección H leído por zxing-cpp, WiFi en SVG, SEPA en PDF vectorial, Kanji y UTF-8, degradado y borde, aviso si no se lee, configuración en JSON, QR dentro de un PDF), imágenes de F5 en Chromium (convertir-imagen a AVIF, WEBP, GIF, BMP, TIFF e ICO, TIFF por páginas, GIF animado, SVG con texto, favicon, metadatos y Base64), escaner-pdf con cámara simulada, copiar-de-pdf con el servidor simulado y el portapapeles real, formulario de convertir-desde-pdf, pdf-a-webp en el navegador, lote C de F2 (alias canónico, ayuda HEIC y papeles de la solicitud), lote B de F2, metadatos leídos en el navegador, unir, pdf-a-jpg, numerar, editar, rellenar, contraseña, redactar, varias por hoja y recortar, recorte visual, folleto con vista previa e impresión, anotar, lector con miniaturas y texto seleccionable, crear-pdf y web-a-pdf, «Seguir con otra herramienta», Drive y Dropbox apagados, hreflang y cabeceras) | 69 en verde en la última ejecución completa en el puerto 3100 (también 12 de 12 repeticiones de chat-f3 tras el arreglo de D-147); en F3-C, ejecutadas aquí en el puerto 3123 (el 3100 estaba ocupado): 64 en verde, con las 4 de `ia-f3.spec.ts` (su origen CORS sigue ahora a `WEB_URL`) y marcadores-pdf al repetirla, y las 8 que fijan el origen 3100 (chat-f3, flujos-f1 y copiar-de-pdf) sin ejecutar |
| TypeScript 7 (`tsc --noEmit`) en las dos áreas | Sin errores |
| `next build` (Next 16.4.3) | Correcto |
| Lighthouse CI (`@lhci/cli` 0.16.1, móvil, mediana de 3) contra `next start` | Rendimiento: portada 0,99, comprimir-pdf 0,98, pdf-a-word 0,97, resumir-pdf 0,98 y ogg-a-mp3 0,96; accesibilidad 1,0 en las cinco (D-145) |
| Licencias (Python y npm de producción) | 0 problemas en npm; en Python, 0 en las dependencias del proyecto (la `.venv` local tiene además los paquetes CUDA de NVIDIA que trae un torch sin `--index-url .../cpu`, instalado fuera de G0-A; la CI y las imágenes usan el torch de CPU) |
| `registry.json` (163 herramientas), `docs/TOOLS.md` y `docs/ERRORS.md` (`gen_docs.py --check`), `docker-compose.coolify.yml` y los casos de `filetype` al día; los dos Compose válidos con `docker compose config` (solo en la CI: no hay Docker) | Correcto |

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
- **Smokescreen**: la imagen se compila desde la etiqueta v0.1.0 (D-155); su compilación y el arranque de `egressweb` y
  `egressai` solo se comprueban en la CI de imágenes y en `e2e-compose` (sin Docker aquí).
- **G1-A**: la imagen `worker-pdf` con el perfil FOGRA39 de `infra/icc` (D-154) y el job `docling` sin FFmpeg (D-156),
  solo en la CI. Cuatro pruebas de LibreOffice fallan aquí porque el LibreOffice local no tiene el filtro de importación
  de PDF (`libreoffice-pdfimport`), que la CI instala: `test_pdf_to_word_faithful_with_libreoffice` (`tests/test_tools.py`)
  y `test_ods_through_libreoffice`, `test_ppt_faithful_and_odp` y `test_odt_and_rtf_editable_and_faithful`
  (`tests/test_desde_pdf_docling.py`). Las 10 pruebas de Playwright que simulan la API (`chat-f3.spec.ts`,
  `ia-f3.spec.ts`, `flujos-f1.spec.ts` y la de copiar-de-pdf de `f2.spec.ts`) fijan el origen `http://127.0.0.1:3100`
  en sus cabeceras CORS y no se pudieron ejecutar aquí en otro puerto: solo corren en la CI.
- **Playwright del proyecto `servidor`**, la parte de servidor de `lector-pdf` y el formulario «Enviar por correo» en la
  web: pendientes de la ejecución con la pila completa (la API del envío sí tiene pruebas con PostgreSQL real).
- **Google Drive y Dropbox** contra los servicios reales: hacen falta las claves del propietario (D-36).
- **Lighthouse** (1.3): medido aquí con Chrome 157 y en la CI en cada cambio (D-145); con el dominio real, Cloudflare y
  Umami, en el VPS (DEPLOY-CHECKLIST). **Prueba de carga k6** (16.1): el escenario está comprobado (D-146), pero solo se
  puede ejecutar con la pila completa en el VPS (pasos en `OPERATIONS.md`).
- **G0-B en la CI**: las referencias de la regresión visual de la plantilla se generaron aquí con el Chromium de
  Playwright 1.64.1 (el mismo que instala la CI); la primera ejecución en GitHub las confirma. Lighthouse y la regresión
  de los PDF en los jobs `web` y `python`, y las muestras de `servidor.spec.ts` en `e2e-compose`, solo en la CI.
- **veraPDF** para la salida PDF/A de ocr-pdf (16.6).
- **F3, lote C**: imagen-a-excel de extremo a extremo por la API se ha probado con la etapa de Docling sustituida por su
  resultado (con tabla y sin ella); Docling real sobre las imágenes, con `make_ctx`, en `tests/test_imagen_excel_docling.py`
  (aquí y en el job `docling` de la CI, que no tiene PostgreSQL). Las respuestas del modelo vienen del proveedor falso y de
  un proveedor de prueba con los datos de los tickets de muestra: la calidad con modelos reales de OpenRouter y con
  tickets reales en papel térmico, en el VPS (DEPLOY-CHECKLIST). Las imágenes `worker-ocr` (python-docx e img2pdf) y
  `worker-ai` (openpyxl), sin Docker, solo en la CI.
- **F3, lote D**: la imagen `worker-av` con espeak-ng de bookworm (1.51; aquí se probó con el 1.52 de trixie), la etapa
  `kokoro-model` y la comprobación de paquetes prohibidos, solo en la CI (sin Docker); pdf-a-audio con un PDF real largo
  (horas de audio) y la memoria de `workeravheavy` con los dos modelos, en el VPS (DEPLOY-CHECKLIST); la calidad de la voz
  española, en la escucha del propietario (6.4).
- **F3, lote E**: traducir-subtitulos y resumir-reunion se han probado de extremo a extremo por la API con el proveedor
  falso, FFmpeg 7.1 de Debian y faster-whisper tiny reales (y la voz sintética de Kokoro para una reunión corta); la
  calidad de las traducciones y de las actas con modelos reales de OpenRouter, una película entera, una reunión real de
  varias voces y el paso de `ai` a `workeravheavy` con las imágenes de verdad (FFmpeg LGPL de BtbN y modelo small), en el
  VPS o en la CI (DEPLOY-CHECKLIST). El Compose de Coolify con los límites de IA en `workeravheavy`, sin Docker, solo en
  la CI. La revisión adversarial de GOAL.md 6.7 la hizo el propio implementador (no había herramienta para lanzar un
  revisor independiente); queda para la revisión externa de F3-Z.
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

## F3, lote C (imagen y datos)

imagen-a-texto (OCR local con Tesseract y OCRmyPDF en `workerocr`, sin IA y sin cuenta: TXT, Word o PDF buscable,
idiomas, enderezado propio, giro por la orientación de Tesseract, TIFF de varias páginas y lotes con ZIP),
imagen-a-excel (Docling sobre la imagen enderezada en `workerconvert`; solo si no hay tabla y con la IA activada, el
texto del OCR pasa a `workerai` y un JSON con esquema reconstruye las tablas; la petición reservada se devuelve si no se
usa y, con la IA apagada, no hace falta cuenta ni consentimiento) y ticket-a-excel (OCR en `workerocr` y una petición
por ticket en `workerai`, con la API reservando una por archivo, JSON con esquema, comprobación de que los conceptos y el
desglose de IVA suman el total, y XLSX con hojas de tickets y conceptos o CSV). Muestras generadas con Pillow y las
fuentes Noto en `scripts/fixtures/imagenes_ocr.py`; celdas protegidas contra la inyección de fórmulas. Salvedades en
D-159 a D-165 (D-165, de la revisión: una sola regla para los números de las celdas en `tools/numeros.py`).
Cierre del lote: `export_registry.py`, `gen_coolify_compose.py` y `gen_docs.py` regenerados sin cambios y sus
`--check` en verde; Vitest (292 de client-tools y 35 de web), `tsc` sin errores y pytest completo con PostgreSQL 17 y
Redis locales (1571 en verde, 9 omitidas por modelos o programas que no hay aquí: embeddings, u2net, faster-whisper y
ctranslate2, veraPDF y un DOCX de prueba; y las 4 de LibreOffice sin el filtro de importación de PDF de siempre,
`libreoffice-pdfimport`). Sin verificar aquí: imágenes `worker-ocr`, `worker-convert` y `worker-ai` (sin Docker), las
8 pruebas de Playwright que fijan el origen 3100 y la calidad con modelos reales de OpenRouter (sin clave).

## F3, lote D (voz local)

pdf-a-audio (7.6): lee un PDF en voz alta y entrega un MP3. Kokoro-82M v1.0 en ONNX Runtime dentro de la imagen
worker-av (revisión y SHA-256 fijados, `infra/kokoro/fetch-model.sh`), con los fonemas de espeak-ng como programa
externo y un paso propio de IPA al alfabeto de Kokoro, sin los paquetes kokoro, kokoro-onnx, misaki ni phonemizer
(prohibidos en la política de licencias y comprobados en la imagen). Cola `av.heavy`, 0 peticiones de IA, clase
pesada. La API cuenta antes de encolar, en un proceso aparte, los caracteres que se van a leer (`ToolSpec.precheck`):
sin cuenta no hay acceso, más de 20.000 (gratis) o 300.000 (Pro) se rechaza sin gastar la tarea, y la lectura en
español no se encola mientras `TTS_VOICE_ES` esté vacía (6.4, a la espera de la escucha del propietario). El worker
saca el texto con pypdfium2 (`document_texts`; los escaneos pasan por `workerocr` y vuelven a `av.heavy`), quita
cabeceras, pies y números de página, arma los párrafos (también por el salto vertical entre líneas, que ahora marca el
extractor común), detecta el idioma y genera el MP3 con el FFmpeg LGPL por tramos de 10 minutos. Opciones: páginas,
idioma, voz (recomendada, de mujer o de hombre), velocidad, calidad MP3, pausa entre párrafos, saltar cabeceras y OCR.
Muestras generadas con fpdf2 (`scripts/fixtures/lectura_pdf.py`), que también da la voz sintética para las pruebas de
transcripción de F3-E (D-114). Salvedades en D-166 a D-173.
Cierre del lote: `export_registry.py`, `gen_coolify_compose.py` y `gen_docs.py` regenerados sin cambios y sus
`--check` en verde; Vitest (292 de client-tools y 35 de web), `tsc` sin errores y pytest completo con PostgreSQL 17 y
Redis locales (1598 en verde y 17 omitidas sin los modelos; con `KOKORO_HOME` y `WHISPER_HOME` apuntando a una caché
local fuera del repositorio, las 37 de `test_pdf_audio.py` y `test_transcripcion.py` en verde, y quedan 4 omitidas:
veraPDF, u2net, embeddings y un DOCX de prueba). Siguen fallando solo aquí las 4 de LibreOffice sin Writer, Impress ni
`libreoffice-pdfimport` (pdf-a-word fiel, pdf-a-ods, pdf-a-ppt y pdf-a-odp, pdf-a-odt y pdf-a-rtf), ajenas al lote.
Sin verificar aquí: la imagen `worker-av` con espeak-ng 1.51 de bookworm, la etapa `kokoro-model` y la comprobación de
paquetes prohibidos (sin Docker, solo en la CI), un PDF real de horas de audio y la memoria de `workeravheavy` (VPS) y
la escucha de la voz española por el propietario (6.4), que decide cuándo poner `TTS_VOICE_ES=ef_dora`.

## F3, lote E (IA de audio: subtítulos traducidos y resumen de reuniones)

traducir-subtitulos y resumir-reunion (7.10, de F5, hechas en F3 por necesitar el LLM; D-119). traducir-subtitulos
traduce SRT, WebVTT y ASS (también SSA) con pysubs2 (MIT, adelantado de F6) en `workerai`: cada subtítulo con letras es
un elemento de la lista JSON de `TranslationProvider` (exactamente uno por subtítulo), los tiempos no se tocan, las líneas
se vuelven a partir al ancho elegido y se conservan la cursiva de línea entera, las posiciones, los estilos, comentarios y
dibujos de ASS; opción bilingüe, glosario y un tramo «Desde» y «Hasta» (lo de fuera queda igual, para traducir un archivo
muy largo en dos tareas). Un audio o un vídeo pasa de `ai` a `av.heavy`, se transcribe con faster-whisper (tarea pesada)
y vuelve. resumir-reunion empieza siempre en `av.heavy` y hace en `ai` un acta con esquema (resumen, temas, decisiones,
tareas con responsable y fecha y preguntas abiertas), por bloques y una final si no cabe, en DOCX, TXT o Markdown, con la
transcripción opcional. En la etapa de `av.heavy` se mide el tramo contra los minutos del plan y se estiman y reservan las
peticiones antes de transcribir; la transcripción viaja por `document_texts` y, si la cadena falla a mitad, se devuelven
las reservas. ASS entra en la detección por bytes de los dos lados. Muestras: `scripts/fixtures/subtitulos.py`,
`tests/fixtures/jfk.ogg` y la voz sintética de F3-D. Contenido 8.2 en es y en. Salvedades en D-174 a D-178.
Cierre del lote: `export_registry.py` (163 herramientas), `gen_coolify_compose.py` (límites de IA en `workeravheavy`),
`filetype_cases.py` (73 casos) y `gen_docs.py` regenerados con sus `--check` en verde; Vitest (295 de client-tools y 35 de web), `tsc` sin errores, `next build` y Playwright del proyecto navegador (las 5 de `ia-f3.spec.ts`, con la nueva del lote E, en verde; el resto del proyecto, 67 en verde y las 8 que fijan el origen `127.0.0.1:3100` sin poder ejecutarse aquí porque ese puerto lo ocupaba otro proceso) y pytest completo con PostgreSQL 17 y Redis locales y `WHISPER_HOME` y `KOKORO_HOME` apuntando a una caché local (1652 en verde, las 18 de `tests/test_ia_audio.py` entre ellas; 4 omitidas: veraPDF, u2net, embeddings y un DOCX de prueba). Siguen fallando solo aquí las 4 de LibreOffice sin Writer, Impress ni `libreoffice-pdfimport`, ajenas al lote. Licencias de Python: pysubs2 sin problemas; la `.venv` local sigue con los 16 paquetes CUDA de NVIDIA de antes, ajenos al lote. Sin verificar aquí: modelos reales de OpenRouter, una película y una reunión real y las imágenes con Docker (DEPLOY-CHECKLIST).
Tras la revisión (D-179): subtítulos en UTF-16 y UTF-32 con BOM reconocidos por bytes en los dos lados (solo para SRT, VTT y ASS), etiquetas ASS recorridas en tiempo lineal y subtítulos de más de 2.000 caracteres rechazados, la cursiva o la negrita que se cierra dentro de la línea ya no se extiende a toda la traducción, la versión bilingüe conserva la línea original con sus etiquetas y el resultado avisa de los ajustes de posición y las voces de WebVTT que se pierden. pytest de `test_ia_audio.py` y `test_filetype_cases.py` con PostgreSQL y Redis locales (99 en verde, con una prueba nueva), pytest completo (1659 en verde, 4 omitidas y las 4 de LibreOffice de siempre) y Vitest de client-tools (301) y `tsc` en verde.

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
perfil de 16 vCPU; tablas por lotes en `PLAN.md`. Correcciones de la revisión (D-142): la comprobación de FFmpeg
de `worker-av` ya no acepta una suma SHA-256 distinta ni un FFmpeg con `--enable-gpl`, fases de la cabecera desde
`config/tools-notes.yaml`, `minLength` y `minItems` en la prueba de contrato y `envFlag` igual a `_env_bool`. La columna
«Contenido propio» de `TOOLS.md` sale del índice de git y no del árbol de trabajo (D-143), para que los archivos sin
añadir de los lotes de contenido en paralelo no la cambien: `gen_docs.py --check` y `tests/test_docs.py` pasan en un
`git archive` limpio del commit. Salvedades en D-134 a D-143.

## G0-B (calidad del cierre técnico)

Lighthouse CI en el job `web` con `@lhci/cli` 0.16.1: perfil móvil, mediana de 3 y 90 o más en rendimiento y
accesibilidad en la portada y una página por fase (F1 comprimir-pdf, F2 pdf-a-word, F3 resumir-pdf y F5 ogg-a-mp3), con
los informes como artefacto; para llegar a 1,0 en accesibilidad se oscurece el naranja de los botones y del logotipo
(4,9:1) y el selector de idioma tiene un nombre que empieza por su texto. Regresión visual de 16.1: la primera pantalla de
la plantilla de herramienta en móvil y escritorio (que encontró la cabecera saliéndose de la pantalla a 390 px, ahora en
dos líneas) y los PDF de folleto-pdf, varias-paginas-por-hoja, numerar-paginas-pdf y marca-de-agua-pdf generados con el
código del navegador y comparados en PNG con pypdfium2. Playwright de 16.1 con el servidor simulado para comprimir-pdf,
word-a-pdf, pdf-a-word, ogg-a-mp3 y el pago con FakePaymentProvider, y `servidor.spec.ts` revisado (muestras generadas en
`e2e-compose`, Mailpit con espera y nombres exactos). Al repetir las pruebas apareció un fallo real: el último aviso de
progreso de Uppy, emitido con retraso, devolvía la página a «Subiendo…» y borraba el resultado o la conversación de
chat-pdf; ya no se atiende después de la subida. k6 revisado frente a 16.1 con su escenario en JSON comprobado por pytest,
el pico de 300 trabajos completo, una sesión anónima por trabajo (360), cualquier llegada que no acabe en trabajo creado o
`QUEUE_FULL` contada como fallida, la espera en cola por grupo y `tests/load/recursos.sh` para CPU, RAM y disco; durante
la prueba se suben temporalmente los límites por IP y `light_tasks_day` del plan anónimo, y se devuelven al terminar.
Salvedades en D-144 a D-149.

Cierre del lote: registro, `docker-compose.coolify.yml`, `TOOLS.md` y `ERRORS.md` regenerados y sus `--check` en verde;
Vitest (268 de client-tools y 34 de web), `tsc` y pytest (1501 en verde, 9 omitidas y las 4 de LibreOffice sin Writer ni
Impress de siempre). Al pasar la suite entera, `test_carga_k6.py` comparaba `ANON_TOKENS_PER_IP_DAY` con `Settings()`,
que lee el valor que el fixture `services` de conftest pone en el entorno para toda la sesión: ahora se compara con el
valor por defecto del campo. Las dos observaciones de la última revisión de k6 (salidas tempranas de `runJob` y
`tusUpload` sin contar y `checks: rate>0.95`) ya estaban resueltas en D-149 y las comprueba `test_carga_k6.py`. Sin
verificar aquí: la prueba k6 (solo en el VPS con la pila completa), Lighthouse y la regresión visual de referencia en
la CI de GitHub, y `servidor.spec.ts` en `e2e-compose`.

## G1-A (huecos de F1, F2 y F5)

redactar-pdf ofrece el método «Eliminar solo el contenido bajo el área» de A.6: EmbedPDF quita los caracteres que tocan
cada área y los trazados, imágenes, sombreados y grupos que la cruzan pasan a imagen de sí mismos con el área vacía, sin
tocar el resto de la página; se quitan las anotaciones y campos afectados, se comprueba antes de pintar los recuadros que
bajo las áreas no queda nada y, en los dos métodos, se borran del archivo los objetos huérfanos (rasterizar dejaba el
contenido original sin usar dentro del PDF). lector-pdf tiene enlaces pulsables: internos a su página y externos solo
`http`, `https` y `mailto` en una pestaña nueva. Las herramientas de imagen del navegador codifican JPEG con MozJPEG, PNG
con oxipng y WebP con libwebp en WebAssembly en lugar del lienzo. Las notas de resultado de las herramientas de F1 y F2
(navegador y servidor) salen en el idioma de la página. Fallos de la primera CI en GitHub: el perfil FOGRA39 va en
`infra/icc` porque el `colord-data` de bookworm ya no lo trae, Smokescreen se compila desde su etiqueta porque Stripe no
publica imagen y las muestras de audio y vídeo solo se generan con FFmpeg (el job `docling` no lo tiene); los Playwright
del servidor simulado ya estaban en verde desde G0-B. Contenido 8.2 de las siete páginas puesto al día. Salvedades en
D-150 a D-156. Tras la revisión (D-157): redactar-pdf quita también las etiquetas de accesibilidad y la capa XFA, tapa
los términos en todas las cadenas del archivo y comprueba antes de entregar que no siguen en ninguna cadena ni flujo de
texto o de contenido; el aviso de «eliminar» dice cuándo parte del texto de alrededor ha pasado a imagen con un grupo, y
las imágenes de más de 50 MP (o si el WebAssembly se queda sin memoria) se codifican con el lienzo.
Segunda revisión (D-158): redactar-pdf quita también los archivos adjuntos (el DOCX, ZIP o PDF original, el XML de una
factura) y las miniaturas de las páginas, y con «rasterizar» quita de `/AcroForm` los campos que tocan un área.
Cierre del lote: `export_registry.py`, `gen_coolify_compose.py` y `gen_docs.py` regenerados sin cambios y sus
`--check` en verde; Vitest (292 de client-tools y 34 de web), `tsc` sin errores y pytest completo (1511 en verde, 9
omitidas por modelos o programas que no hay aquí: embeddings, u2net, faster-whisper y ctranslate2, veraPDF y un DOCX de
prueba; y las 4 de LibreOffice sin el filtro de importación de PDF de siempre). No hay PostgreSQL ni Docker en esta
máquina.

Verificado aquí: Vitest (282 de client-tools y 34 de web), `tsc`, `next build`, licencias de npm (0 problemas) y pytest sin
la marca `integration` (1441 en verde, 8 omitidas y las 4 de LibreOffice sin el filtro de importación de PDF de siempre;
las de `integration` necesitan PostgreSQL y Valkey, que no hay en esta máquina). Playwright del proyecto `navegador`
contra `next start` en el puerto 3117 (el 3100 lo ocupaba otro servidor): 61 de 71 en verde, con las dos nuevas (redactar con
«eliminar» y enlaces del lector) y todas las del editor y de las imágenes de F5 (marcadores-pdf falló una vez por la
carrera de escritura de siempre y pasó al repetirla); las 10 que simulan la API (chat-pdf, resumir-pdf,
copiar-de-pdf y los flujos de 16.1) fijan el origen `http://127.0.0.1:3100` en sus cabeceras CORS y no se pudieron
ejecutar en otro puerto: quedan para la CI.

## Pendiente

- F3: cierre (F3-Z, `PLAN.md`); después F4, F6, vídeo de F5 y F7, en el orden de 17 (ondas de `docs/GOAL.md`).
- Huecos del Anexo A sin lote: autoorientar de girar-pdf (A.4) y el Modo de pdf-a-excel, pdf-a-ods y pdf-a-txt (A.9),
  apuntados en `PENDIENTES` de `tests/anexo_a_minimos.py` (D-135).
- Cierre técnico de F3 (17): uso real de peticiones registrado, con la clave de OpenRouter del propietario.

## Cierre operativo de F1

Pendiente de las entradas del propietario (0.1); pasos en `DEPLOY-CHECKLIST.md` (incluye el digest de Smokescreen y
las pruebas de salida de `egressweb`).
