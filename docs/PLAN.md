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
| C (F3-C). Imagen y datos | imagen-a-texto (Tesseract en `ocr`, sin IA), imagen-a-excel (Docling en `convert` y, si no reconoce la tabla, LLM con esquema en `ai`; IA opcional) y ticket-a-excel (OCR en `ocr` y LLM con esquema en `ai`, 1 petición por ticket, comprobación de la suma) | Hecho (D-159 a D-165) |
| D (F3-D). Voz | pdf-a-audio (Kokoro-82M en ONNX con fonemas de espeak-ng como proceso externo, en `av.heavy`; caracteres por tarea comprobados en la API antes de encolar; voz española apagada hasta la escucha del propietario) | Hecho (D-166 a D-173) |
| E (F3-E). IA de audio (de F5) | traducir-subtitulos (SRT, VTT y ASS con pysubs2, un elemento JSON por subtítulo y tiempos intactos; audio y vídeo transcritos antes en `av.heavy`) y resumir-reunion (faster-whisper en `av.heavy` y acta con esquema en `ai`, por bloques si no cabe); peticiones estimadas y reservadas antes de transcribir | Hecho (D-174 a D-179) |
| F3-Z. Cierre de F3 | 16.3 y uso real de peticiones (clave de OpenRouter del propietario) | En curso: rendimiento, e2e-compose y mantenimiento de beat (D-181); token de descarga canónico y Next.js 16.4.6 (D-183); CI entera en verde por primera vez con dc0e262 (D-190), también e2e-compose y Lighthouse; faltan la revisión externa y el uso real con la clave |

## Goal de trabajo continuo: lotes transversales (`docs/GOAL.md`, D-134 en adelante)

Las ondas, dependencias y la definición de terminado están en `docs/GOAL.md`; el detalle de cada lote, en
`docs/goal/lotes.json`.

| Lote | Contenido | Estado |
| --- | --- | --- |
| G0-A. Infraestructura de proceso | Prueba de contrato 16.6 genérica y tabla del Anexo A, `default_enabled`, paridad de flags web y API, `gen_docs` con estado, motivos, 7.24 y paridad con PDF24, Playwright con f4, f6 y f7, `EXCLUDED_WORDS` con «firmas», FFmpeg fijado por fecha y SHA-256, diff-match-patch sin `^`, `${MEM_<NOMBRE>}` y perfil de 16 vCPU; URL simuladas de Playwright en la CI; `TOOLS.md` generado desde el índice de git | Hecho (D-134 a D-143) |
| G0-B. CI de calidad | Lighthouse CI (móvil, mediana de 3, portada y una página por fase), regresión visual de 16.1 (plantilla en móvil y escritorio y cuatro PDF con pypdfium2), Playwright de 16.1 con el servidor simulado y `servidor.spec.ts` revisado, k6 revisado con su escenario comprobado; contraste y cabecera móvil corregidos; el aviso tardío de progreso de Uppy ya no borra el resultado | Hecho (D-144 a D-149); k6 y Lighthouse oficial en el VPS; referencias visuales y `servidor.spec.ts` se confirman en la CI |
| G1-A. Huecos | redactar-pdf (eliminar bajo el área, D-25), lector-pdf (enlaces, D-23), MozJPEG y oxipng (D-04 y D-79), notas en inglés (D-42 y D-54); fallos de la primera CI (perfil FOGRA39, Smokescreen y muestras sin FFmpeg) | Hecho (D-150 a D-158) |
| G2-C01 a G2-C15. Contenido 8.2 | Contenido propio es/en de las 145 páginas que no lo tienen, en lotes de unas 10 | Hecho; los borradores de D-77 (copiar-de-pdf y escaner-pdf) y crear-collage, completos en D-180. Falta la revisión del propietario (D-15) |

## F4: firma, formularios, facturas y accesibilidad (en curso)

| Lote | Herramientas | Estado |
| --- | --- | --- |
| F4-A | verificar-firmas-pdf y firmar-pdf en servidor (`workersign` y `sign.verify`, pyHanko, SoftHSM2, LOTL; migración 0006) | Hecho: verificar-firmas-pdf y la lista de la UE (F4-A1, D-185 a D-187) y el sello de firmar-pdf en `workersign` con la migración 0006 (F4-A2, D-188); firmar-pdf sigue apagada hasta F4-B |
| F4-B | firmar-pdf en el navegador, hacer-pdf-rellenable y crear-formulario-pdf | Hecho: hacer-pdf-rellenable y crear-formulario-pdf (F4-B1, D-195 y D-198), «Insertar firma» y el sello desde la página (F4-B2a, D-196) y el certificado propio con firma interrumpida (F4-B2b, D-199); firmar-pdf, encendida |
| F4-C | compartir-pdf y solicitar-firmas (B-LT, Mailpit) | Hecho: compartir-pdf (F4-C1, D-200) y solicitar-firmas (F4-C2, D-202 y D-203); la e2e con Mailpit, en la CI |
| F4-D | validar-factura-electronica, factura-electronica-a-pdf, facturae-a-pdf, ubl-a-pdf y cii-a-pdf (`workerutils`, KoSIT) | Hecho: validar-factura-electronica y `workerutils` con KoSIT (F4-D1, D-191) y la representación en PDF/A-3 con el XML incrustado (F4-D2, D-192) |
| F4-E | crear-factura, crear-factura-electronica y pdf-a-factura-electronica (detrás de `INVOICING_ES_ENABLED`) | En curso: crear-factura (F4-E1, D-204 y D-206) y crear-factura-electronica (F4-E2, D-205) hechas; la firma XAdES-EPES de Facturae en el navegador (F4-E2b, D-207) y pdf-a-factura-electronica (F4-E3, D-208) hechas, con las revisiones de F4-E2 y F4-E3 corregidas (D-209 y D-211) |
| F4-F | word-a-pdf-accesible (office → ocr, veraPDF) | Hecho (D-182 y D-184); veraPDF y el PDF/UA de LibreOffice reales, en la CI |
| F4-Z | Cierre de F4: firma validada con pyHanko y solicitud de extremo a extremo | Hecho aquí: imagen de la firma dentro de la apariencia PAdES y .p12 con 3DES o RC2 (D-210), revisión de F4-E3 corregida (D-211); la e2e de servidor de solicitar-firmas con Mailpit está escrita y se comprueba en la CI cuando vuelva a arrancar |

## F6: formatos, datos y documentos (en curso)

| Lote | Herramientas | Estado |
| --- | --- | --- |
| F6-A | docx-a-odt, odt-a-docx, docx-a-markdown, markdown-a-docx, docx-a-html, html-a-docx (pandoc estático) | Hecho (D-212), con la revisión corregida (D-216) |
| F6-B1 | xlsx-a-csv, csv-a-xlsx, ods-a-xlsx, xlsx-a-ods, excel-a-json, arreglar-codificacion-csv | Hecho (D-213), con la revisión corregida (D-218); ods-a-xlsx y xlsx-a-ods con LibreOffice Calc real, en la CI |
| F6-B2 | csv-a-json, json-a-csv, json-a-xml, xml-a-json, yaml-a-json, json-a-yaml | Hecho (D-214), con la revisión corregida (D-218) |
| F6-C | epub-a-mobi, epub-a-azw3, mobi-a-epub, azw3-a-epub, pptx-a-imagenes, pptx-a-video | Pendiente (F4-Z) |
| F6-D | traducir-word, traducir-excel, traducir-powerpoint, manuscrito-a-texto | Pendiente (F4-Z) |
| F6-E | rar-a-zip, 7z-a-zip, tar-a-zip, extraer-archivo-online, srt-a-vtt, vtt-a-srt, ass-a-srt | Hecho (D-217) |
| F6-F | ttf-a-woff2, otf-a-woff2, woff2-a-ttf, woff-a-ttf, ttf-a-otf, otf-a-ttf | Hecho (D-215) |
| F6-G | csig-a-pdf, p7m-a-pdf, xsig-a-pdf, verificar-firma | Hecho (D-219); sellos de tiempo de XAdES sin comprobar (anotado) |
| F6-H1 | gpx-a-kml, kml-a-gpx, kmz-a-gpx, gpx-a-geojson, geojson-a-kml, shp-a-geojson, shp-a-kml, csv-a-kml | Hecho (D-220), con la revisión corregida (D-226); Shapefile con ogr2ogr real, en la CI |
| F6-H2 | tcx-a-gpx, fit-a-gpx, fit-a-csv | Hecho (D-223) |
| F6-I | vcf-a-csv, csv-a-vcf, vcf-a-excel, ics-a-csv, csv-a-ics, ics-a-excel | Hecho (D-224) |
| F6-J | mbox-a-eml, mbox-a-pdf, pst-a-mbox, pst-a-pdf | Hecho (D-225); pst-a-mbox y pst-a-pdf apagadas hasta probarlas con un PST real |
| F6-K | drawio-a-pdf, drawio-a-png, latex-a-pdf | Hecho (D-227); Landlock en el Docker del VPS, en DEPLOY-CHECKLIST |
| F6-L | midi-a-mp3, midi-a-wav, musicxml-a-pdf, midi-a-pdf | Hecho (D-228) |
| F6-M | captura-web, udf-a-pdf (`default_enabled=False`) | Hecho (D-229); udf-a-pdf apagada hasta probarla con documentos reales |
| F6-N1 | mermaid-a-png, mermaid-a-svg | Hecho (D-231) |
| F6-N2 | crear-tarjeta | Hecho (D-232) |
| F6-O1 | escribir-pdf: editor y exportación | Pendiente (F4-Z) |
| F6-O2 | escribir-pdf: abrir, ODT, combinación de correspondencia y extras | Pendiente (F6-O1 y F6-A) |
| F6-Z | Cierre de F6: 16.5 de su ámbito y paridad con PDF24 en `TOOLS.md` | Pendiente (F6-A a F6-O2) |

## F5: vídeo (pendiente, después de F6)

| Lote | Herramientas | Estado |
| --- | --- | --- |
| F5-V1 | mp4-a-webm, webm-a-mp4, mov-a-mp4, mkv-a-mp4, avi-a-mp4, video-a-gif, gif-a-mp4 (solo Pro) | Pendiente (F6-Z) |
| F5-V2 | comprimir-video, recortar-video, rotar-video, quitar-audio-video | Pendiente (F5-V1) |
| F5-Z | Cierre de F5: audio, vídeo y carga de ogg-a-mp3 | Pendiente (F5-V2) |

## F7: 3D, CAD e impresión 3D (pendiente)

| Lote | Herramientas | Estado |
| --- | --- | --- |
| F7-A | stl-a-obj, obj-a-stl, stl-a-3mf, 3mf-a-stl, obj-a-3mf, 3mf-a-obj, stl-a-ply, ply-a-stl, stl-ascii-a-binario (`workermesh`) | Pendiente (F5-Z) |
| F7-B | amf-a-stl, stl-a-amf, amf-a-3mf, glb-a-stl, stl-a-glb, gltf-a-stl, fbx-a-stl, fbx-a-obj, dae-a-stl, 3ds-a-stl | Pendiente (F7-A) |
| F7-C | wrl-a-stl, stl-a-wrl, x3d-a-stl, stl-a-x3d, stl-a-usdz, obj-a-usdz, convertir-modelo-3d | Pendiente (F7-A y F7-B) |
| F7-D | step-a-stl, stp-a-stl, step-a-3mf, step-a-obj, step-a-glb, iges-a-stl, igs-a-step, brep-a-stl, stl-a-step, obj-a-step (`workercad`) | Pendiente (F5-Z) |
| F7-E | scad-a-stl, scad-a-3mf, dwg-a-dxf, dwg-a-pdf | Pendiente (F7-D) |
| F7-F | reparar-stl, reducir-poligonos, escalar-modelo-3d, cambiar-unidades-stl, cortar-modelo-3d, separar-piezas, unir-modelos, analizar-stl | Pendiente (F7-A) |
| F7-G | svg-a-stl, dxf-a-stl, imagen-a-stl, logo-a-stl, texto-a-stl, litofania, mapa-de-alturas-a-stl | Pendiente (F7-A) |
| F7-H | visor-3d, visor-gcode, comprimir-glb, render-modelo-3d (navegador) | Pendiente (F5-Z) |
| F7-I | gcode-a-bgcode, bgcode-a-gcode, analizar-gcode, gcode-a-imagen, extraer-miniatura-gcode, extraer-gcode-3mf | Pendiente (F7-A) |
| F7-Z | Cierre de F7 y del proyecto: 16.5 de 3D, criterios de 18 y 16.7 | Pendiente (F7-A a F7-I) |

## Siguiente paso

1. Construir las imágenes en GitHub Actions y hacer el arranque de humo del Compose (`e2e-compose` en la CI),
   incluidas `gotenbergweb` y `egressweb`.
2. Cierre operativo de F1 con las entradas del propietario (0.1): VPS, Cloudflare, Stripe, SMTP y repositorio de restic.
3. Revisión del contenido propio redactado y contenido del resto de páginas para quitar el `noindex`.
4. Onda 1 de `docs/GOAL.md`: G0-B, F3-C, F3-D y F3-E hechos; después F3-Z; luego F4, F6, vídeo de F5 y F7 (orden de 17).
