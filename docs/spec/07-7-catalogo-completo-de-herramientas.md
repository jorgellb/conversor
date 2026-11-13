## 7. Catálogo completo de herramientas

Cada herramienta tiene página en `/es/<slug-es>` y `/en/<slug-en>` desde su fase. Formato de cada línea: slugs — motor — fase.

Las opciones de cada herramienta, con sus valores por defecto, rangos y cómo se implementan, están en el **Anexo A**. El `options_schema` de cada herramienta las cubre como mínimo.

### 7.1 Organizar y editar PDF (cliente)

- unir-pdf, dividir-pdf, girar-pdf, eliminar-paginas-pdf, extraer-paginas-pdf, organizar-pdf — `@cantoo/pdf-lib` — F1
- numerar-paginas-pdf, marca-de-agua-pdf, recortar-pdf (CropBox) — `@cantoo/pdf-lib` — F1
- cambiar-tamano-pagina-pdf, varias-paginas-por-hoja, folleto-pdf (imposición para imprimir) — `@cantoo/pdf-lib` con `embedPage` — F1
- lector-pdf, anotar-pdf, editar-pdf (añadir texto, imágenes y formas; no reescribir párrafos), rellenar-pdf, aplanar-pdf — EmbedPDF — F1
- redactar-pdf — EmbedPDF y PDFium; por defecto rasteriza las zonas afectadas (A.6) — F1
- escaner-pdf — cámara, OpenCV.js y pdf-lib, usable como PWA — F2

### 7.2 Imágenes y PDF

- pdf-a-jpg, pdf-a-png — PDFium en navegador; pypdfium2 en servidor si el archivo es grande — F1
- jpg-a-pdf, png-a-pdf, webp-a-pdf, gif-a-pdf, bmp-a-pdf — navegador (canvas y pdf-lib) — F1
- tiff-a-pdf (img2pdf, sin recomprimir), svg-a-pdf (Chromium de `gotenberg`), heic-a-pdf — servidor — F2
  - Para HEIC usa libheif compilado solo para decodificar, con libde265 y sin x265.
  - No uses los wheels de pillow-heif: incluyen x265 y quedan bajo GPLv2.
  - Todo lo HEVC (HEIC y vídeo H.265) va detrás de `HEVC_DECODE_ENABLED`, apagado por defecto. PDF24 rechaza HEIC por el riesgo de patentes de HEVC, y el programa HEVC Advance cobra por usuario a los servicios en la nube que usan decodificadores HEVC. Actívalo solo tras la revisión que documentes en `docs/LEGAL.md`. Mientras esté apagado, la página explica cómo exportar a JPEG desde el móvil y lleva `noindex`.
- pdf-a-tiff (multipágina), pdf-a-webp — pypdfium2 y Pillow — F2; pdf-a-svg — pdftocairo — F2

### 7.3 A PDF desde Office, web, libros y otros (servidor)

- convertir-a-pdf — página general que acepta todos los formatos de esta sección y elige el motor — F1
- word-a-pdf, excel-a-pdf, ppt-a-pdf (aceptan también doc, xls, ppt y pps), odt-a-pdf, ods-a-pdf, odp-a-pdf, rtf-a-pdf, txt-a-pdf, csv-a-pdf — Gotenberg con LibreOffice — F1
- html-a-pdf y markdown-a-pdf — Chromium de `gotenberg`, sin red: se aceptan HTML suelto o un ZIP con sus recursos, y los recursos remotos no se cargan (la página lo explica) — F1
- web-a-pdf — Chromium de `gotenbergweb`, por `egressweb`; si la URL apunta a un documento convertible (por ejemplo, un DOCX o una imagen), `workeroffice` lo descarga por `egressweb` con los límites del plan y lo convierte como si se hubiera subido — F1
- pages-a-pdf, keynote-a-pdf, numbers-a-pdf, visio-a-pdf, publisher-a-pdf — LibreOffice (importación parcial; avisar de la calidad) — F2
- epub-a-pdf, mobi-a-pdf, azw3-a-pdf, fb2-a-pdf — Calibre — F2
- cbz-a-pdf, cbr-a-pdf — libarchive, Pillow y pikepdf — F2
- djvu-a-pdf — ddjvu — F2
- eml-a-pdf, msg-a-pdf — `email` de la biblioteca estándar y mail-parser para EML; olefile y compressed-rtf para MSG (no uses extract-msg, que es GPL); HTML saneado y Chromium de `gotenberg`; cabeceras, cuerpo y adjuntos convertibles como páginas siguientes — F2
- dxf-a-pdf — ezdxf con su backend SVG y Chromium de `gotenberg` para pasar a PDF; nunca el backend PyMuPDF ni el extra `ezdxf[draw]`, que instalan PyMuPDF (AGPL) — F2

### 7.4 Desde PDF (servidor)

- pdf-a-word, pdf-a-excel, pdf-a-ppt — Docling (backend pypdfium2) con python-docx, openpyxl y python-pptx, detrás de una interfaz `ConversionProvider` — F2
  - El resultado es editable y se recompone el flujo del texto; no es una copia exacta del diseño. La página lo dice y ofrece el modo «Fiel al diseño» (A.9), que usa la importación de PDF de LibreOffice en `workeroffice`.
  - Límite de páginas por plan (9.3) y tiempo máximo por página; si se supera, se ofrece procesar un rango.
- pdf-a-odt, pdf-a-ods, pdf-a-odp, pdf-a-rtf — salida anterior convertida con LibreOffice (unoserver) en `workeroffice`, porque Gotenberg solo produce PDF — F2
- pdf-a-txt (pypdfium2), pdf-a-markdown y pdf-a-html (Docling), pdf-a-csv y pdf-a-json (tablas con Docling) — F2
- pdf-a-epub — Docling a HTML y pandoc con `--sandbox` — F2

### 7.5 PDF a PDF (servidor)

- comprimir-pdf — pikepdf y Pillow (recompresión y reducción de imágenes por niveles) más el optimizador de OCRmyPDF — F1
- ocr-pdf, pdf-a-pdfa — OCRmyPDF 17 con rasterizador pypdfium2 y `--pdfa-backend internal` (nunca usa Ghostscript), Tesseract y validación con veraPDF. Si un PDF no se puede convertir a PDF/A sin Ghostscript, la tarea falla con un informe claro y ofrece rasterizar las páginas con capa de texto OCR — F2
- pikepdf, qpdf y pypdfium2 — F2:
  - proteger-pdf (AES-256);
  - desbloquear-pdf (solo con la contraseña del usuario, nunca forzando);
  - reparar-pdf;
  - optimizar-pdf-web (linealizar);
  - pdf-escala-de-grises (reescribiendo los operadores de color de los flujos de contenido, de modo que texto y vectores siguen siendo vectoriales, y pasando a gris imágenes, degradados y anotaciones; las páginas con construcciones que no sepa convertir con seguridad, como sombreados por función o espacios DeviceN, se rasterizan en gris y se avisa);
  - extraer-imagenes-pdf;
  - metadatos-pdf (ver y editar) y eliminar-metadatos-pdf (página propia, como en PDF24, que quita todo y muestra antes lo que va a borrar).
- comparar-pdf — híbrida: texto con PDFium y diff-match-patch, y diferencias visuales por página, en el navegador; en servidor solo si algún archivo supera `CLIENT_MAX_MB` — F2
- word-a-pdf-accesible — Gotenberg con `pdfua` y validación con veraPDF — F4
- pdf-a-factura-electronica (Factur-X / ZUGFeRD) — XML CII y PDF/A-3; detalle y resto de herramientas de factura en 7.23 — F4

### 7.6 IA sobre documentos (grupo ai)

- chat-pdf, resumir-pdf, generador-de-preguntas, traducir-pdf — F3
  - traducir-pdf regenera DOCX y PDF con maquetación simplificada, detrás de una interfaz `TranslationProvider`. No uses BabelDOC (AGPL).
- imagen-a-texto (Tesseract, local, grupo `ocr`) — F3
- imagen-a-excel (OCR, Docling y, si hace falta, LLM) — F3
- ticket-a-excel (LLM con salida estructurada) — F3
- pdf-a-presentacion (LLM y python-pptx) — F3
- pdf-a-fichas (LLM) — F3
- pdf-a-audio (Kokoro local, grupo `av`, con límite de caracteres por plan en 9.3) — F3

### 7.7 Firma y compartir

- firmar-pdf — firma dibujada, escrita o subida en el navegador, con sello PAdES B-T opcional en servidor mediante pyHanko — F4. Firma digital con certificado propio, niveles PAdES y certificación: en A.6.
- compartir-pdf — enlace firmado con caducidad elegible hasta `SHARE_MAX_DAYS` — F4
- solicitar-firmas — flujo propio con pyHanko — F4:
  - campos de firma;
  - invitación por correo;
  - código de verificación;
  - sello final PAdES B-LT;
  - certificado de auditoría.

### 7.8 Audio (grupo av)

- ogg-a-mp3, ogg-a-wav, opus-a-mp3 (notas de voz de WhatsApp), m4a-a-mp3, aac-a-mp3, flac-a-mp3, wav-a-mp3, mp3-a-wav, wma-a-mp3, amr-a-mp3, aiff-a-mp3, mp4-a-mp3 (extraer audio de un vídeo) — FFmpeg — F5
- Opciones:
  - MP3 a 128, 192 o 320 kbps o VBR;
  - WAV PCM de 16 bits a 44,1 o 48 kHz;
  - mono o estéreo;
  - normalizar volumen con `loudnorm`;
  - conversión por lotes con descarga en ZIP.
- cortar-audio, unir-audios, normalizar-volumen, cambiar-velocidad-audio — FFmpeg — F5

### 7.9 Vídeo (grupo av, solo Pro)

- mp4-a-webm, webm-a-mp4, mov-a-mp4, mkv-a-mp4, avi-a-mp4, video-a-gif, gif-a-mp4 — FFmpeg — F5
  - Si los códecs de entrada caben en el contenedor de salida (por ejemplo, H.264 y AAC de un MOV o un MKV a MP4), se remultiplexa con `-c copy`: tarda segundos y no codifica nada.
  - Solo se recodifica a H.264 con `VIDEO_H264_ENCODING_ENABLED` activo; si está apagado, el MP4 de salida usa AV1 y la página lo indica.
  - Las entradas HEVC (vídeos de iPhone) necesitan `HEVC_DECODE_ENABLED` salvo que solo se remultipliquen; si no se puede, la página lo explica.
- comprimir-video, recortar-video, rotar-video, quitar-audio-video — FFmpeg, sin recodificar cuando el corte y la operación lo permiten — F5

### 7.10 IA de audio y vídeo (grupos av y ai)

- transcribir-audio (TXT, DOCX y SRT), video-a-subtitulos (SRT y VTT) — faster-whisper local — F5
- traducir-subtitulos, resumir-reunion — transcripción local y LLM — F5

### 7.11 Imágenes

- png-a-jpg, jpg-a-png, webp-a-jpg, webp-a-png, jpg-a-webp, png-a-webp, avif-a-jpg, jpg-a-avif, gif-a-png, bmp-a-jpg, tiff-a-jpg, png-a-ico y convertir-imagen (cualquier combinación) — jSquash y canvas en el navegador — F5
- heic-a-jpg, heic-a-png — servidor, con la misma decodificación y el mismo flag `HEVC_DECODE_ENABLED` que heic-a-pdf — F5
- svg-a-png, svg-a-jpg — `@resvg/resvg-wasm` en el navegador, sin cargar recursos externos — F5
- comprimir-imagen, redimensionar-imagen, crear-favicon, quitar-metadatos-foto (EXIF y GPS), imagen-a-base64, leer-codigo-qr (zxing-cpp en WebAssembly) — navegador — F5
- quitar-fondo — rembg con el modelo de 6.4 — F5
- raw-a-jpg (CR2, NEF, ARW y DNG con LibRaw mediante rawpy), psd-a-png (psd-tools), png-a-svg y jpg-a-svg (vectorizar con vtracer) — servidor — F5

### 7.12 Documentos y datos (grupo utils)

- docx-a-odt, odt-a-docx, docx-a-markdown, markdown-a-docx, docx-a-html, html-a-docx — pandoc siempre con `--sandbox`, que le impide leer archivos que no sean la entrada y acceder a la red — F6
- xlsx-a-csv, csv-a-xlsx, ods-a-xlsx, xlsx-a-ods, csv-a-json, json-a-csv, json-a-xml, xml-a-json, yaml-a-json, json-a-yaml, excel-a-json — openpyxl y librería estándar — F6
- arreglar-codificacion-csv (de Windows-1252 y otras a UTF-8; recupera tildes y eñes) — charset-normalizer — F6
- epub-a-mobi, epub-a-azw3, mobi-a-epub, azw3-a-epub — Calibre — F6
- pptx-a-imagenes — Gotenberg a PDF y pypdfium2 — F6; pptx-a-video — diapositivas renderizadas y FFmpeg — F6
- traducir-word, traducir-excel, traducir-powerpoint (conservando el formato) — python-docx, openpyxl, python-pptx y LLM — F6
- manuscrito-a-texto — modelo gratuito con entrada de imagen; si no hay ninguno disponible, la herramienta se desactiva sola y lo indica — F6

### 7.13 Comprimidos, subtítulos y fuentes (grupo utils)

- rar-a-zip, 7z-a-zip, tar-a-zip, extraer-archivo-online (zip, rar, 7z, tar.gz) — libarchive — F6
- srt-a-vtt, vtt-a-srt, ass-a-srt — pysubs2 — F6
- ttf-a-woff2, otf-a-woff2, woff2-a-ttf, woff-a-ttf, ttf-a-otf, otf-a-ttf — fontTools — F6. El usuario declara tener derecho a convertir la fuente.

### 7.14 Documentos firmados y factura electrónica (grupo utils)

- csig-a-pdf, p7m-a-pdf, xsig-a-pdf (extraer el documento original firmado; si no es un PDF, se entrega tal cual y se ofrece convertirlo) — asn1crypto, cryptography y defusedxml — F6
- verificar-firma — pyHanko para CAdES y PAdES, con su validación AdES y sus listas de confianza de la UE, y signxml para XAdES — F6
  - Admite .csig, .xsig, .p7m y PDF firmados.
  - Muestra firmante, fecha, validez de la cadena y si el documento cambió.
  - La parte de PDF se adelanta a F4 como verificar-firmas-pdf (sección 7.23), con lista de confianza de la UE y revocación.
- facturae-a-pdf, ubl-a-pdf, cii-a-pdf — validación con el XSD oficial, plantilla HTML y Chromium de `gotenberg` — F6

### 7.15 GPS y mapas (grupo utils)

- gpx-a-kml, kml-a-gpx, kmz-a-gpx, gpx-a-geojson, geojson-a-kml, tcx-a-gpx, shp-a-geojson, shp-a-kml, csv-a-kml (columnas de latitud y longitud) — GDAL/OGR y gpxpy — F6
- fit-a-gpx, fit-a-csv (Garmin) — fitparse — F6

### 7.16 Contactos, calendario y correo (grupo utils)

- vcf-a-csv, csv-a-vcf, vcf-a-excel (con plantillas de Google y Outlook) — vobject — F6
- ics-a-csv, csv-a-ics, ics-a-excel — icalendar — F6
- mbox-a-eml, mbox-a-pdf, pst-a-mbox, pst-a-pdf — readpst (GPL, externo) y el flujo de eml-a-pdf — F6

### 7.17 Diagramas, música y web (grupo utils)

- drawio-a-pdf, drawio-a-png — draw.io desktop (GPL-3.0, proceso externo) en modo exportación con `xvfb-run`, sin red y con tiempo máximo — F6
- mermaid-a-png, mermaid-a-svg — mermaid en el navegador — F6
- latex-a-pdf — Tectonic sin shell-escape, sin red (con el paquete de TeX precargado en la imagen y el modo sin descargas de la versión fijada), como proceso con entorno vacío y con el aislamiento de 12.1 — F6
- midi-a-mp3, midi-a-wav — FluidSynth con un banco de sonidos cuya licencia permita uso comercial (verifícala y regístrala) — F6
- musicxml-a-pdf, midi-a-pdf (partitura) — MuseScore (GPL, externo, sin interfaz) — F6
- captura-web (URL a PNG o JPG) — Chromium de `gotenbergweb`, por `egressweb` — F6

### 7.18 Impresión 3D: mallas (grupo mesh)

- **Entradas:** STL (ASCII y binario), OBJ con MTL, 3MF, AMF, PLY, OFF, glTF/GLB, FBX (solo lectura), DAE (Collada), 3DS (solo lectura), VRML/WRL, X3D y USD/USDZ.
- **Salidas:** STL (ASCII o binario), OBJ con MTL, 3MF, AMF, PLY, OFF, GLB, X3D, VRML/WRL y USDZ.
- **Motores:**
  - lib3mf para 3MF (lectura, escritura y validación);
  - trimesh para STL, OBJ, PLY, OFF y GLB;
  - assimp para FBX, DAE, 3DS, X3D y VRML;
  - usd-core para USD/USDZ;
  - AMF con lector y escritor propios según la especificación ISO/ASTM 52915 (XML, opcionalmente comprimido).
- **Páginas propias:** stl-a-obj, obj-a-stl, stl-a-3mf, 3mf-a-stl, obj-a-3mf, 3mf-a-obj, stl-a-ply, ply-a-stl, amf-a-stl, stl-a-amf, amf-a-3mf, glb-a-stl, stl-a-glb, gltf-a-stl, fbx-a-stl, fbx-a-obj, dae-a-stl, 3ds-a-stl, wrl-a-stl, stl-a-wrl, x3d-a-stl, stl-a-x3d, stl-a-usdz, obj-a-usdz y stl-ascii-a-binario. El resto de combinaciones, desde convertir-modelo-3d.
- **Opciones:**
  - unidades de origen y destino (mm, cm, m, pulgadas);
  - escala;
  - fusionar o separar objetos;
  - conservar colores y materiales cuando el destino lo permite, avisando si se pierden (por ejemplo, al pasar a STL).
- **Fase:** F7.

### 7.19 Impresión 3D: CAD (grupo cad)

- step-a-stl, stp-a-stl, step-a-3mf, step-a-obj, step-a-glb, iges-a-stl, igs-a-step, brep-a-stl — OpenCascade (cadquery/OCP) con calidad de teselado elegible — F7
- stl-a-step, obj-a-step — sólido facetado a partir de la malla; avisar de que no recupera superficies paramétricas — F7
- scad-a-stl, scad-a-3mf — OpenSCAD (GPL, externo) en sandbox, sin acceso fuera del directorio del trabajo — F7
- dwg-a-dxf, dwg-a-pdf — LibreDWG (GPL, externo) para pasar a DXF y la ruta de dxf-a-pdf (7.3) para el PDF; calidad irregular, avisar al usuario — F7

### 7.20 Impresión 3D: herramientas y generadores

- visor-3d (STL, OBJ, 3MF, PLY, GLB, AMF) y visor-gcode — three.js en el navegador — F7
- reparar-stl (huecos, normales invertidas, aristas no manifold, autointersecciones) — manifold3d y trimesh — F7
- reducir-poligonos — fast-simplification (decimación cuádrica) — F7
- escalar-modelo-3d, cambiar-unidades-stl, cortar-modelo-3d (por un plano), separar-piezas, unir-modelos — trimesh y manifold3d — F7
- analizar-stl — estanqueidad, dimensiones, volumen, superficie y estimación de filamento en gramos y metros por material (PLA, PETG, ABS, TPU) y relleno, marcada como estimación — F7
- comprimir-glb (Draco, con glTF Transform y draco3d) y render-modelo-3d (miniatura PNG con three.js) — navegador — F7
- Generadores, con shapely, trimesh y manifold3d — F7:
  - svg-a-stl y dxf-a-stl (extrusión con altura elegible);
  - imagen-a-stl y logo-a-stl (vectorizar con vtracer y extruir);
  - texto-a-stl (fontTools y extrusión);
  - litofania (foto a STL plana, curva o cilíndrica);
  - mapa-de-alturas-a-stl (relieve).

### 7.21 Impresión 3D: G-code (grupo mesh)

- gcode-a-bgcode, bgcode-a-gcode — implementación propia a partir de la especificación publicada por Prusa — F7
  - Cubre bloques, CRC, DEFLATE, Heatshrink y MeatPack.
  - No copies código de libbgcode, que es AGPL.
  - Pruébala contra archivos reales de PrusaSlicer.
- analizar-gcode — parser propio — F7
  - Extrae tiempo, filamento, temperaturas, capas y laminador, leyendo los comentarios.
- gcode-a-imagen (trayectorias por capa en PNG o SVG), extraer-miniatura-gcode (miniaturas incrustadas en G-code y bgcode) — parser propio — F7
- extraer-gcode-3mf (G-code y miniaturas de un .gcode.3mf de Bambu Lab) — ZIP y parser propio — F7

### 7.22 Orquestación

- conversor-pdf — página que elige la ruta según formatos de entrada y salida — F1, y crece en cada fase
- convertir-archivo y convertir-modelo-3d — F5 y F7
  - Son conversores universales: detectan el tipo por bytes y ofrecen solo las salidas posibles.
  - Las combinaciones sin página propia no tienen URL indexable: se resuelven dentro del conversor universal, y un enlace compartido con parámetros lleva `noindex`.
- Reglas de indexación para todo el catálogo:
  - Una página se indexa solo cuando su herramienta está activa, ha pasado sus pruebas y su contenido propio (8.2) está completo en ese idioma; hasta entonces lleva `noindex` y no está en el sitemap.
  - Las páginas alias (por ejemplo, pub-a-pdf) llevan `canonical` a la principal.

### 7.23 Paridad con PDF24: herramientas añadidas

Son las herramientas de tools.pdf24.org que no estaban en el catálogo. El formato es el mismo (slugs — motor — fase), y sus opciones están en el Anexo A.

**Crear**

- crear-pdf — página índice de las formas de crear un PDF — F1
- imagenes-a-pdf — varias imágenes en un PDF, en el navegador; TIFF y lotes grandes con img2pdf en servidor — F1
- solicitud-de-empleo-pdf — carta, CV y adjuntos (Office, imágenes o PDF) convertidos con Gotenberg y unidos con pikepdf, con un marcador por documento — F2
- generar-codigo-qr — qr-code-styling (MIT) en el navegador, con comprobación de lectura por zxing-cpp — F5
- crear-collage — canvas con Konva (MIT) y pdf-lib en el navegador — F5
- crear-tarjeta — mismo motor que crear-collage, con salida para imprenta (sangrado, TrimBox, BleedBox y marcas de corte) — F6
- escribir-pdf — F6
  - Procesador de textos en el navegador con TipTap (MIT, sin extensiones de pago).
  - Salidas: PDF con Gotenberg y Chromium, DOCX con `docx` (MIT), Markdown y ODT con pandoc.

**Facturas (grupo utils)**

Las herramientas que generan facturas (crear-factura, crear-factura-electronica y pdf-a-factura-electronica) van detrás de `INVOICING_ES_ENABLED`, apagado por defecto, además de su flag propio. Las que validan o muestran facturas (validar-factura-electronica y factura-electronica-a-pdf) no generan facturas y pueden activarse antes.

- crear-factura — página de elección y diseñador visual de facturas PDF en el navegador, con plantillas propias, IVA, recargo de equivalencia y retención de IRPF — F4
- crear-factura-electronica — F4
  - Formulario EN 16931 con validación en vivo.
  - Salidas: Factur-X/ZUGFeRD, XRechnung (CII o UBL), Peppol BIS Billing 3.0, UBL 2.1 y Facturae 3.2.2.
  - Facturae puede llevar firma XAdES-EPES con la política de firma de Facturae, hecha en el navegador con xadesjs y el certificado del usuario o de su empresa (.p12 o .pfx abierto con PKI.js). La clave privada nunca sale del navegador.
  - CII con drafthorse; incrustación con factur-x, o con los campos Factur-X de Gotenberg (`facturxXml` y siguientes) cuando el PDF se genera desde HTML.
- pdf-a-factura-electronica — F4
  - Si el PDF ya trae XML, lo reutiliza.
  - Si no, extrae los datos en este orden: texto, reglas y una sola petición de LLM con salida estructurada, con consentimiento.
  - La revisión en formulario es obligatoria: nada se genera sin que el usuario confirme.
  - Conserva las páginas originales.
- factura-electronica-a-pdf — F6
  - Amplía cii-a-pdf, ubl-a-pdf y facturae-a-pdf (7.14).
  - Salida PDF/A-3 con el XML original incrustado sin modificar un byte.
  - Admite lotes.
- validar-factura-electronica — F4
  - Motor: KoSIT Validator (Java, Apache-2.0, como programa externo en modo servicio) con las configuraciones públicas de XRechnung (`validator-configuration-xrechnung`) y Peppol BIS (`validator-configuration-bis`).
  - Para EN 16931 sin CIUS y para Factur-X/ZUGFeRD no hay configuración pública: crea escenarios propios con los artefactos oficiales (Schematron de EN 16931 de la Comisión Europea, con licencia EUPL-1.2, y Schematron de Factur-X/ZUGFeRD) y anota sus licencias en `docs/LICENSES.md`.
  - KoSIT 1.6 solo recibe mantenimiento: anota en `docs/DECISIONS.md` la alternativa si deja de publicarse.
  - Facturae: XSD y verificación de la firma con signxml.
- **Aviso legal.** Anótalo en `docs/LEGAL.md` para revisarlo con un asesor antes de activar `INVOICING_ES_ENABLED`:
  - Un generador de facturas usado por empresas o autónomos españoles es un sistema informático de facturación (Reglamento Veri*factu, RD 1007/2023). Los productores de estos sistemas deben cumplirlo desde el 29/7/2025; los usuarios están obligados desde el 1/1/2027 (sociedades) y el 1/7/2027 (resto), según el RDL 15/2025.
  - La factura electrónica obligatoria entre empresas (RD 238/2026 y Orden HAC/1028/2026, en vigor desde el 6/10/2026) obliga a emitir por plataformas de intercambio o por la solución pública de la AEAT, y a enviar a esta una copia en UBL. Estas herramientas no son una plataforma de intercambio: generan, convierten y validan formatos.
  - Mientras tanto, las páginas avisan de que no sustituyen a un software de facturación.

**Editar**

- superponer-pdf — membrete o capa, de fondo o en primer plano, sobre documentos; convierte antes a PDF lo que no lo sea; pikepdf (`add_underlay` y `add_overlay`) — F2
- hacer-pdf-rellenable, con crear-formulario-pdf como página de entrada — diseñador de campos con pdf-lib en el navegador; campos de firma con pyHanko en servidor — F4

**Organizar**

- montar-pdf — tablero de varios documentos para mover páginas entre ellos, unir, dividir y guardar cada uno; EmbedPDF y pdf-lib — F2
- imprimir-pdf — imposición con pdf-lib e impresión desde un iframe, con asistente de doble cara manual — F2
- cortar-paginas-por-la-mitad — duplica cada página y ajusta MediaBox y CropBox, sin rasterizar; pdf-lib — F2
- marcadores-pdf — editor de marcadores; pikepdf en servidor y vista en el navegador — F2
- copiar-de-pdf — F2
  - Híbrida: texto y bloques simples en el navegador con PDFium.
  - Tablas, escaneos y estructura, bajo demanda en servidor con Docling y OCR.

**Optimizar**

- pdf-modo-oscuro — reescritura de colores en los flujos de contenido con pikepdf; miniaturas con pypdfium2 para detectar páginas ya oscuras — F2
- rasterizar-pdf — pypdfium2, Pillow y pikepdf — F2

**Seguridad**

- generar-contrasena — en el navegador con `crypto.getRandomValues`, sin sesgo de módulo — F1

**Ver y comprobar**

- buscar-en-pdf — PDFium en el navegador, sobre muchos archivos, con exportación a CSV — F2
- validar-pdfa — veraPDF con perfiles PDF/A-1 a PDF/A-4 y PDF/UA-1 y 2; informe en lenguaje claro — F2
- verificar-firmas-pdf — F4
  - pyHanko (validación AdES, análisis de diferencias y listas de confianza de la UE) con pyhanko-certvalidator.
  - Lista de confianza de la UE (LOTL y listas nacionales), descargada por `egressweb` y cacheada; pyHanko comprueba la firma de la LOTL contra el ancla publicada en el Diario Oficial de la UE.
  - Revocación OCSP y CRL a petición.
- preferencias-visor-pdf — pikepdf sobre `/ViewerPreferences`, `/PageLayout`, `/PageMode` y `/OpenAction` — F2

**Convertir**

- odg-a-pdf — LibreOffice — F1
- pub-a-pdf — alias de publisher-a-pdf, con `canonical` a esa página — F2
- pdf-a-imagenes — lote a JPG, PNG o WEBP — F1
- convertir-desde-pdf — página única cuyo formulario cambia según el formato de salida (A.9) — F2
- udf-a-pdf — documentos de UYAP (Turquía) — F6
  - Va detrás de un flag apagado por defecto.
  - Investiga el formato antes de implementarlo; si no es viable, documéntalo en `docs/TOOLS.md`.

**Ya cubiertas**

No cambian en el catálogo; solo ganan las opciones del Anexo A:

- unir, dividir, girar, eliminar, extraer y ordenar páginas;
- numerar, marca de agua, recortar, cambiar tamaño, varias por hoja y folleto;
- editar, anotar, rellenar, aplanar y redactar;
- comprimir, escala de grises, OCR, PDF/A, reparar y optimizar para web;
- proteger, desbloquear, metadatos y extraer imágenes;
- comparar, lector, firmar, escáner y web a PDF;
- las conversiones a PDF y desde PDF, y las de SVG, WEBP y HEIC.

**No aplica:**

- Los programas de escritorio de PDF24 (Creator, impresora virtual y lector). Su equivalente aquí es la PWA instalable (8.3).
- La extensión para Chrome: anótala en `docs/TOOLS.md` como mejora posterior.

### 7.24 Fuera de alcance

- XPS, PostScript/EPS y PDF/X: dependen de Ghostscript o MuPDF (AGPL).
- Laminar modelos a G-code: PrusaSlicer, OrcaSlicer, Bambu Studio y CuraEngine son AGPL.
- Archivos laminados para resina (CTB, PWMX, GOO, SL1 y similares): la herramienta de referencia, UVtools, es AGPL y CTB va cifrado.
- Formatos nativos de CAD propietario (SLDPRT, F3D, IPT, CATPart) sin SDK comercial.
- Quitar DRM, convertir certificados con clave privada y descargar de YouTube o redes sociales.

Documenta los cuatro primeros en `docs/TOOLS.md` como posibles con licencia comercial o tras revisión legal.

---
