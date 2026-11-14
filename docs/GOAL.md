# Objetivo: terminar el portal de conversión de documentos

Este documento es el «goal» de trabajo continuo: dice qué falta, en qué orden, cuándo está terminada cada cosa y qué bloquea al propietario. Manda la especificación de `docs/spec/` (índice en `docs/spec/INDEX.md`). Si algo de aquí la contradice, gana la especificación y se corrige este documento. Las decisiones nuevas se anotan en `docs/DECISIONS.md` a partir de **D-134**.

## 1. Objetivo

Completar el catálogo entero de la sección 7 (`07-7-catalogo-completo-de-herramientas.md`), con todas las opciones del Anexo A (`a-*.md`), en el orden de ejecución de la sección 17 (`17-17-fases-y-entregables.md`): **resto de F3 → F4 → F6 → vídeo de F5 → F7**. Cada fase termina con su cierre técnico (01-1, regla 3) y el proyecto termina con los criterios de aceptación de la sección 18 (`18-18-criterios-de-aceptacion.md`).

Las prioridades de producto, para ser el mejor portal de conversión:

- todas las herramientas con sus opciones completas;
- procesado en el navegador siempre que la especificación lo permite (el archivo no sale del dispositivo);
- páginas rápidas y accesibles (Lighthouse de 90 o más);
- contenido propio en español y en inglés en cada página;
- seguridad y licencias limpias (secciones 11 y 12);
- IA gratuita con consentimiento (sección 6).

## 2. Punto de partida (14/11/2026)

- **Fases cerradas:** F1 y F2. F5 sin vídeo también está cerrada.
- **F3 en curso:** lotes A1, A2 y B hechos (D-119 a D-133).
- **Registro:** `packages/registry/registry.json` tiene **157 herramientas** (F1 43, F2 60, F3 6, F5 48). Por dónde se ejecutan: 97 en servidor, 51 en el navegador y 9 híbridas.
- **Grupos de workers:** existen pdf, ocr, office, convert, media, av, ai y ai.embed. Faltan sign, utils, mesh y cad (5.4).
- **Contenido propio:** solo 11 páginas tienen contenido de 8.2. A las otras **145** les falta (la de pub-a-pdf es un alias y no lo necesita).
- **Huecos conocidos:**
  - D-23: enlaces del lector.
  - D-25: método «eliminar bajo el área» de redactar.
  - D-04 y D-79: MozJPEG y oxipng.
  - D-42 y D-54: notas en inglés.
  - D-13: el FFmpeg de BtbN sale de una compilación `latest`.
  - Rangos `^` en `diff-match-patch`.
  - `apps/web/src/lib/flags.ts` solo apaga crear-factura-electronica con `INVOICING_ES_ENABLED`, mientras que `flags.py` apaga tres herramientas.
  - Playwright no reconoce los archivos `f4`, `f6` ni `f7`.
  - No hay Lighthouse CI, regresión visual ni prueba de contrato 16.6 genérica.
  - `gen_docs.py` tiene una cabecera antigua y no explica por qué está desactivada una herramienta.

**Pendientes: 176 herramientas.** Al final, el catálogo tendrá 333.

| Fase | Herramientas nuevas | Origen |
| --- | --- | --- |
| F3 (resto) | 6 | 7.6 y 7.10, D-119 |
| F4 | 11 | 7.5, 7.7 y 7.23 |
| F6 | 83 (4 se adelantan a F4) | 7.12 a 7.17 y 7.23 |
| F5 vídeo | 11 | 7.9 |
| F7 | 65 | 7.18 a 7.22 |

## 3. Definición de terminado

### 3.1 Por herramienta (01-1 regla 7, 16.5, 16.6, 8.2, 18)

1. **ToolSpec:**
   - `slug_es` exacto de 07 y `slug_en` según la convención anotada;
   - nombres y resumen en es y en;
   - `inputs` y `outputs`, con `zip` si admite lotes (A.0);
   - `related`, `phase` y el grupo de worker de 5.4 (o la desviación anotada).
2. **Opciones:** como mínimo todas las del Anexo A, con sus valores por defecto y rangos. Si el Anexo A no las fija, el conjunto anotado en un D.
3. **Implementación sin TODO, stubs ni simulaciones:**
   - motores externos solo con `run_engine` (entorno vacío, tiempo y memoria limitados);
   - límites de píxeles, `zipguard`, `defusedxml`, límites del plan (9.3) y errores con `ErrorCode`;
   - nada GPL importado y nada AGPL (11).
4. **Pruebas:**
   - la prueba de contrato 16.6 (genérica, de G0-A) en verde;
   - una prueba de efecto por cada opción que cambia el resultado, comprobada sobre los bytes de salida;
   - las de 16.5 de su formato y las de 16.4 de su clase de ataque;
   - el ZIP de lotes (A.0) y los códigos de error;
   - Playwright de la página: etiquetas, valores por defecto, `show_if`, `accept` y `noindex`;
   - en las herramientas del navegador, además, que no salga ningún archivo a la red y que no haya violaciones de CSP.
5. **Muestras reales** en `tests/fixtures` o generadas por `scripts/fixtures/`, con su origen en `tests/fixtures/SOURCES.md` si se descargan (01-1 regla 8).
6. **Contenido 8.2 en es y en** (`apps/web/content/{es,en}/<slug_es>.json`):
   - `complete: true` y `reviewed: false`, con al menos 250 palabras;
   - qué hace, pasos, preguntas frecuentes, límites por plan, formatos y herramientas relacionadas;
   - sin cifras inventadas y sin párrafos repetidos en más de 3 páginas.
7. **Archivos regenerados:**
   - `registry.json`, `docs/TOOLS.md` y `docs/ERRORS.md`;
   - el Compose de Coolify, si cambian los workers;
   - los casos de `filetype`, si hay un formato nuevo.
8. **Licencias y flag:**
   - licencias con 0 problemas y filas nuevas en `docs/LICENSES.md`;
   - `TOOL_<SLUG>_ENABLED=false` la apaga.
9. **Si no cumple todo lo anterior,** queda desactivada (con su flag o con `default_enabled=False`) y `docs/TOOLS.md` explica el motivo.

### 3.2 Por lote

- Todas sus herramientas cumplen 3.1 o están desactivadas con su motivo.
- Pasan todas las pruebas que se pueden ejecutar en esta máquina. Las que no se pueden ejecutar aquí se anotan en «No verificado en esta entrega» de `docs/PROGRESS.md`.
- La revisión adversarial no deja ningún hallazgo abierto.
- La documentación está al día.
- Hay commit del lote en la rama de trabajo.

### 3.3 Por fase (lote Z)

- **Cierre técnico (01-1, regla 3):**
  - pasan las pruebas de la fase y de las anteriores;
  - `docker compose up` arranca solo con `.env.example`;
  - `docker-compose.coolify.yml` pasa `config` y el arranque de humo;
  - Lighthouse móvil da 90 o más en la portada y en las páginas de la fase.
- **Criterio propio de la fase (17):**
  - F3: 16.3 y uso real de peticiones;
  - F4: firma validada con pyHanko y solicitud de extremo a extremo;
  - F5: audio, vídeo y carga de ogg-a-mp3;
  - F6: 16.5 de su ámbito y paridad con PDF24 en `TOOLS.md`;
  - F7: 16.5 de 3D.
- **Desactivadas:** como máximo el 10 % de la fase (regla 7).
- **Revisión externa exigente (regla 9):** seguridad, licencias, accesibilidad, rendimiento, disco y presupuesto de IA.
- **Cierre operativo:** hecho, o pendiente en `PROGRESS.md` con sus pasos en `DEPLOY-CHECKLIST.md`.

### 3.4 Del proyecto

Se cumplen todos los criterios de 18, uno por uno, con la prueba o el documento que lo demuestra. `docs/` debe estar completo: PLAN, PROGRESS, DECISIONS, ARCHITECTURE, TOOLS, LICENSES, LEGAL, SECURITY, DEPLOY, DEPLOY-CHECKLIST, OPERATIONS, ERRORS y `spec/`.

## 4. Orden y ondas

Una onda es un grupo de lotes que se pueden hacer a la vez. Al final de cada onda se hace un paso de integración (6.9).

- **Onda 0:** G0-A, G1-A y G2-C01 a G2-C15. Los de contenido y G1-A pueden seguir abiertos durante las ondas siguientes.
- **Onda 1 (F3):** G0-B, F3-C y F3-D en paralelo; después F3-E; después F3-Z.
- **Onda 2 (F4):** F4-A, F4-D y F4-F en paralelo; después F4-B y F4-C; después F4-E; después F4-Z.
- **Onda 3 (F6):** F6-A, B1, B2, C, D, E, F, G, H1, H2, I, J, K, L, M, N y O1 en paralelo; después F6-O2; después F6-Z.
- **Onda 4 (vídeo de F5):** F5-V1, F5-V2 y F5-Z, uno detrás de otro.
- **Onda 5 (F7):**
  - empiezan en paralelo F7-A, F7-D y F7-H;
  - después de F7-A: F7-B, F7-F, F7-G y F7-I;
  - después de F7-B: F7-C;
  - después de F7-D: F7-E;
  - al final, F7-Z.

Archivos comunes que se fusionan en la integración y no impiden el paralelismo: `packages/registry/registry.json`, los `specs.py` de cada grupo, `apps/web/messages/*.json`, `docs/*.md`, `docker-compose*.yml`, `workers/Dockerfile`, `pyproject.toml` y `package-lock.json`.

## 5. Lotes

| Lote | Fase | Herramientas | Grupo y motor | Depende de | Tamaño |
| --- | --- | --- | --- | --- | --- |
| G0-A | Transversal | — (prueba de contrato 16.6 genérica, `default_enabled`, paridad de flags, `gen_docs` con motivos y tabla de PDF24, testMatch f4, f6 y f7, `EXCLUDED_WORDS` firmas, fijar FFmpeg y diff-match-patch, `${MEM_<GRUPO>}`, tablas de PLAN y D-134 en adelante). **Hecho** (D-134 a D-143) | — | — | M |
| G0-B | Transversal | — (Lighthouse CI, regresión visual de 16.1, Playwright de 16.1 que falten, revisión de k6). **Hecho** (D-144 a D-149) | CI | G0-A | M |
| G1-A | Huecos | redactar-pdf (eliminar bajo el área, D-25), lector-pdf (enlaces, D-23), comprimir-imagen, convertir-imagen, png-a-jpg, jpg-a-png y redimensionar-imagen (MozJPEG y oxipng, D-04 y D-79); notas en inglés (D-42 y D-54). **Hecho** (D-150 a D-158) | navegador y servidor | — | M |
| G2-C01 | Contenido 8.2 | dividir, girar, eliminar-paginas, extraer-paginas, organizar, montar, cortar-paginas-por-la-mitad, imprimir, folleto, varias-paginas-por-hoja | web | — | S |
| G2-C02 | Contenido 8.2 | numerar, marca-de-agua, recortar, cambiar-tamano-pagina, aplanar, anotar, redactar, marcadores, comparar, buscar-en-pdf | web | — | S |
| G2-C03 | Contenido 8.2 | webp-a-pdf, gif-a-pdf, bmp-a-pdf, png-a-pdf, imagenes-a-pdf, tiff-a-pdf, lector-pdf, pdf-a-png, pdf-a-webp, pdf-a-imagenes | web | — | S |
| G2-C04 | Contenido 8.2 | proteger, desbloquear, reparar, optimizar-pdf-web, pdf-escala-de-grises, pdf-modo-oscuro, rasterizar, ocr-pdf, pdf-a-pdfa, validar-pdfa | web | — | S |
| G2-C05 | Contenido 8.2 | extraer-imagenes-pdf, metadatos-pdf, eliminar-metadatos-pdf, preferencias-visor-pdf, superponer-pdf, solicitud-de-empleo-pdf, generar-contrasena, pdf-a-tiff, pdf-a-svg, pdf-a-txt | web | — | S |
| G2-C06 | Contenido 8.2 | pdf-a-odt, pdf-a-rtf, pdf-a-excel, pdf-a-ods, pdf-a-ppt, pdf-a-odp, pdf-a-markdown, pdf-a-html, pdf-a-epub, pdf-a-csv | web | — | S |
| G2-C07 | Contenido 8.2 | pdf-a-json, convertir-desde-pdf, heic-a-pdf, cbz-a-pdf, cbr-a-pdf, djvu-a-pdf, eml-a-pdf, msg-a-pdf, dxf-a-pdf | web | — | S |
| G2-C08 | Contenido 8.2 | convertir-a-pdf, excel-a-pdf, ppt-a-pdf, odt-a-pdf, ods-a-pdf, odp-a-pdf, odg-a-pdf, rtf-a-pdf, txt-a-pdf, csv-a-pdf | web | — | S |
| G2-C09 | Contenido 8.2 | html-a-pdf, markdown-a-pdf, svg-a-pdf, web-a-pdf, pages-a-pdf, keynote-a-pdf, numbers-a-pdf, visio-a-pdf, publisher-a-pdf | web | — | S |
| G2-C10 | Contenido 8.2 | resumir-pdf, chat-pdf, generador-de-preguntas, pdf-a-fichas, pdf-a-presentacion, traducir-pdf, transcribir-audio, video-a-subtitulos | web | — | S |
| G2-C11 | Contenido 8.2 | ogg, opus, m4a, mp4, aac, flac, wav, wma, amr y aiff a MP3 | web | — | S |
| G2-C12 | Contenido 8.2 | ogg-a-wav, mp3-a-wav, cortar-audio, unir-audios, normalizar-volumen, cambiar-velocidad-audio, epub-a-pdf, mobi-a-pdf, azw3-a-pdf, fb2-a-pdf | web | — | S |
| G2-C13 | Contenido 8.2 | png-a-jpg, webp-a-jpg, jpg-a-png, webp-a-png, gif-a-png, jpg-a-webp, png-a-webp, avif-a-jpg, jpg-a-avif, bmp-a-jpg | web | — | S |
| G2-C14 | Contenido 8.2 | tiff-a-jpg, png-a-ico, convertir-imagen, svg-a-png, svg-a-jpg, comprimir-imagen, redimensionar-imagen, crear-favicon, quitar-metadatos-foto, imagen-a-base64 | web | — | S |
| G2-C15 | Contenido 8.2 | leer-codigo-qr, generar-codigo-qr, heic-a-jpg, heic-a-png, raw-a-jpg, psd-a-png, png-a-svg, jpg-a-svg, quitar-fondo | web | — | S |
| F3-C | F3 | imagen-a-texto, imagen-a-excel, ticket-a-excel. **Hecho** (D-159 a D-165) | ocr, convert y ai (Tesseract, Docling y LLM con esquema) | G0-A | L |
| F3-D | F3 | pdf-a-audio. **Hecho** (D-166 a D-173) | av.heavy (Kokoro en ONNX y espeak-ng externo) | G0-A | XL |
| F3-E | F3 (7.10) | traducir-subtitulos, resumir-reunion | av.heavy y ai (faster-whisper y LLM, pysubs2) | F3-D | M |
| F3-Z | Cierre de F3 | — | — | F3-C, F3-D, F3-E, G2-C10, G0-B | S |
| F4-A | F4 | verificar-firmas-pdf, firmar-pdf (servidor) | sign y sign.verify (pyHanko, SoftHSM2, LOTL, certomancer; migración 0006) | F3-Z | XL |
| F4-B | F4 | firmar-pdf (navegador), hacer-pdf-rellenable, crear-formulario-pdf | navegador (pdf-lib, PKI.js) y pdf (campos con pyHanko) | F4-A | XL |
| F4-C | F4 | compartir-pdf, solicitar-firmas | api, apiint y beat; sign (B-LT); Mailpit | F4-A | XL |
| F4-D | F4 (+4 de F6) | validar-factura-electronica, factura-electronica-a-pdf, facturae-a-pdf, ubl-a-pdf, cii-a-pdf | utils, el nuevo workerutils (KoSIT daemon, XSD, signxml, Gotenberg, PDF/A-3) | F3-Z | XL |
| F4-E | F4 | crear-factura, crear-factura-electronica, pdf-a-factura-electronica | navegador y utils (drafthorse, factur-x, xadesjs; detrás de `INVOICING_ES_ENABLED`) | F4-D, F4-B | XL |
| F4-F | F4 | word-a-pdf-accesible | office → ocr (pdfua y veraPDF) | F3-Z | S |
| F4-Z | Cierre de F4 | — | — | F4-A a F4-F | S |
| F6-A | F6 | docx-a-odt, odt-a-docx, docx-a-markdown, markdown-a-docx, docx-a-html, html-a-docx | utils (pandoc estático `--sandbox`) | F4-Z | M |
| F6-B1 | F6 | xlsx-a-csv, csv-a-xlsx, ods-a-xlsx, xlsx-a-ods, excel-a-json, arreglar-codificacion-csv | utils y office (openpyxl, LibreOffice para ODS, charset-normalizer) | F4-Z | M |
| F6-B2 | F6 | csv-a-json, json-a-csv, json-a-xml, xml-a-json, yaml-a-json, json-a-yaml | utils (biblioteca estándar, defusedxml, PyYAML) | F4-Z | S |
| F6-C | F6 | epub-a-mobi, epub-a-azw3, mobi-a-epub, azw3-a-epub, pptx-a-imagenes, pptx-a-video | office (Calibre, Gotenberg) → av.heavy (FFmpeg) | F4-Z | M |
| F6-D | F6 | traducir-word, traducir-excel, traducir-powerpoint, manuscrito-a-texto | ai | F4-Z | L |
| F6-E | F6 | rar-a-zip, 7z-a-zip, tar-a-zip, extraer-archivo-online, srt-a-vtt, vtt-a-srt, ass-a-srt | utils (libarchive, pysubs2) | F4-Z | M |
| F6-F | F6 | ttf-a-woff2, otf-a-woff2, woff2-a-ttf, woff-a-ttf, ttf-a-otf, otf-a-ttf | utils (fontTools) | F4-Z | M |
| F6-G | F6 | csig-a-pdf, p7m-a-pdf, xsig-a-pdf, verificar-firma | utils y sign.verify (asn1crypto, signxml, pyHanko) | F4-Z | L |
| F6-H1 | F6 | gpx-a-kml, kml-a-gpx, kmz-a-gpx, gpx-a-geojson, geojson-a-kml, shp-a-geojson, shp-a-kml, csv-a-kml | utils (ogr2ogr externo, gpxpy) | F4-Z | M |
| F6-H2 | F6 | tcx-a-gpx, fit-a-gpx, fit-a-csv | utils (parser TCX propio, fitparse) | F4-Z | S |
| F6-I | F6 | vcf-a-csv, csv-a-vcf, vcf-a-excel, ics-a-csv, csv-a-ics, ics-a-excel | utils (vobject, icalendar) | F4-Z | M |
| F6-J | F6 | mbox-a-eml, mbox-a-pdf, pst-a-mbox, pst-a-pdf | utils.heavy (mailbox, readpst externo, flujo de eml-a-pdf) | F4-Z | M |
| F6-K | F6 | drawio-a-pdf, drawio-a-png, latex-a-pdf | utils.heavy (draw.io con xvfb, Tectonic) | F4-Z | L |
| F6-L | F6 | midi-a-mp3, midi-a-wav, musicxml-a-pdf, midi-a-pdf | utils.heavy (FluidSynth, FFmpeg LGPL, MuseScore) | F4-Z | M |
| F6-M | F6 | captura-web, udf-a-pdf | office (gotenbergweb por egressweb) y utils (`default_enabled=False`) | F4-Z | M |
| F6-N | F6 | mermaid-a-png, mermaid-a-svg, crear-tarjeta | navegador (mermaid en iframe sandbox, resvg, Konva) | F4-Z | L |
| F6-O1 | F6 | escribir-pdf (editor y exportación) | navegador (TipTap MIT) y office (Gotenberg en dos pasadas) | F4-Z | XL |
| F6-O2 | F6 | escribir-pdf (abrir, ODT, combinación de correspondencia y extras) | navegador, office, convert y utils | F6-O1, F6-A | L |
| F6-Z | Cierre de F6 | — (16.5 de F6, paridad con PDF24 en TOOLS.md) | — | F6-A a F6-O2 | M |
| F5-V1 | F5 vídeo | mp4-a-webm, webm-a-mp4, mov-a-mp4, mkv-a-mp4, avi-a-mp4, video-a-gif, gif-a-mp4 | av.heavy (FFmpeg LGPL, solo Pro) | F6-Z | L |
| F5-V2 | F5 vídeo | comprimir-video, recortar-video, rotar-video, quitar-audio-video | av.heavy | F5-V1 | M |
| F5-Z | Cierre de F5 | — (audio, vídeo y carga de ogg-a-mp3) | — | F5-V2 | S |
| F7-A | F7 | stl-a-obj, obj-a-stl, stl-a-3mf, 3mf-a-stl, obj-a-3mf, 3mf-a-obj, stl-a-ply, ply-a-stl, stl-ascii-a-binario | mesh, el nuevo workermesh (trimesh, lib3mf) | F5-Z | L |
| F7-B | F7 | amf-a-stl, stl-a-amf, amf-a-3mf, glb-a-stl, stl-a-glb, gltf-a-stl, fbx-a-stl, fbx-a-obj, dae-a-stl, 3ds-a-stl | mesh (AMF propio, assimp externo) | F7-A | L |
| F7-C | F7 | wrl-a-stl, stl-a-wrl, x3d-a-stl, stl-a-x3d, stl-a-usdz, obj-a-usdz, convertir-modelo-3d | mesh (assimp, usd-core) y web | F7-A, F7-B | L |
| F7-D | F7 | step-a-stl, stp-a-stl, step-a-3mf, step-a-obj, step-a-glb, iges-a-stl, igs-a-step, brep-a-stl, stl-a-step, obj-a-step | cad, el nuevo workercad (OCP) | F5-Z | L |
| F7-E | F7 | scad-a-stl, scad-a-3mf, dwg-a-dxf, dwg-a-pdf | cad (OpenSCAD y LibreDWG externos) | F7-D | M |
| F7-F | F7 | reparar-stl, reducir-poligonos, escalar-modelo-3d, cambiar-unidades-stl, cortar-modelo-3d, separar-piezas, unir-modelos, analizar-stl | mesh (manifold3d, fast-simplification) | F7-A | M |
| F7-G | F7 | svg-a-stl, dxf-a-stl, imagen-a-stl, logo-a-stl, texto-a-stl, litofania, mapa-de-alturas-a-stl | mesh (shapely, vtracer, fontTools) | F7-A | M |
| F7-H | F7 | visor-3d, visor-gcode, comprimir-glb, render-modelo-3d | navegador (three.js, glTF Transform, draco3d) | F5-Z | L |
| F7-I | F7 | gcode-a-bgcode, bgcode-a-gcode, analizar-gcode, gcode-a-imagen, extraer-miniatura-gcode, extraer-gcode-3mf | mesh (implementación propia; nunca libbgcode) | F7-A | L |
| F7-Z | Cierre de F7 y del proyecto | — (16.5 de 3D, criterios de 18, 16.7) | — | F7-A a F7-I | M |

Notas por lote (en cada una, la sección de la especificación que la justifica):

- **F3-C.** imagen-a-texto no gasta peticiones (6.3) y no pide consentimiento. imagen-a-excel reserva 1 petición y la devuelve si no la usa, porque 6.3 no fija su coste: se anota como decisión. ticket-a-excel gasta 1 petición por ticket (6.3) y comprueba que las líneas sumen el total. Hay que añadir `openpyxl` al extra `ai`.
- **F3-D.** Etapa `kokoro-model` en el Dockerfile con SHA-256. La voz española sigue apagada mientras `TTS_VOICE_ES` esté vacía (6.4). Se comprueba `tts_chars_task` antes de encolar (9.3). Este lote genera la voz sintética que necesitan las muestras de F3-E (D-114).
- **F3-E.** Un elemento JSON por cue, para conservar los tiempos. `TranslationProvider` (D-132). `pysubs2` se adelanta de F6. Map-reduce por bloques de transcripción (6.3).
- **F4-A.**
  - `workersign`: 1 GB, red webrender, secretos solo ahí (12.1).
  - La cola `sign.verify` va sin token.
  - El beat refresca la LOTL y la comprueba contra el ancla del DOUE (7.23 y 14).
  - Migración 0006 (9.4).
  - CA, TSA y OCSP de pruebas como dobles de 0.1.
  - Pruebas: 16.1 (firma válida) y 16.6 (cambio no permitido tras una certificación).
- **F4-B.** Opciones de A.6 y A.3 (`a-6-a-6-seguridad.md`, `a-3-a-3-editar.md`). La cámara se permite con `Permissions-Policy` (D-105). Firma interrumpida (10). crear-formulario-pdf es una página de entrada con su propio contenido, no un alias (7.23).
- **F4-C.** Endpoints de 9.1. El token se guarda solo como hash (12.6). Las solicitudes se guardan en `/srv/files/requests/<id>`, que es una desviación de 4.1. Playwright de extremo a extremo con Mailpit (17).
- **F4-D.** Opciones de A.2 (`a-2-a-2-facturas.md`). Configuraciones de KoSIT y escenarios propios con sus licencias en `LICENSES.md` (7.23). XML incrustado byte a byte y PDF/A-3 comprobado con veraPDF. Nunca `xmlsig`.
- **F4-E.** Aviso legal en `LEGAL.md` y en la página (7.23). La clave privada nunca sale del navegador. La revisión en formulario es obligatoria, y se hace en dos trabajos.
- **F6.**
  - **Seguridad (16.4):** `/proc/self/environ` (pandoc), `file:///etc/hostname` (EPUB), XXE, ZIP con `../`, `\input{/etc/hostname}` (LaTeX) y SSRF (captura-web).
  - **Formatos (16.5):** firmas byte a byte, GPX ↔ KML, VCF ida y vuelta, y la codificación de CSV.
  - **Detección por bytes:** cada formato nuevo se añade a `filetype.py` y a `filetype.ts`, con casos compartidos (D-115).
  - **Licencias:** sin unrar ni p7zip en la imagen, sin EbookLib, sin elkjs, sin `ezdxf[draw]` y sin `osgeo` en el proceso (11).
- **F5 vídeo.** Opciones de 7.8 y 7.9. Solo Pro, con el límite de duración de 9.3. MOV a MP4 sin recodificar (16.5).
- **F7.**
  - Opciones de 7.18: unidades, escala, fusionar o separar, y colores con aviso.
  - Límite de triángulos por plan (9.3).
  - Pruebas de 16.5 de 3D.
  - Playwright de stl-a-3mf (16.1).
  - OpenSCAD con `import` fuera del directorio del trabajo falla (16.4 y 16.5).
  - Fuera de alcance, según 7.24: laminar modelos, resina y CAD propietario.

## 6. Bucle de ejecución (sin parar)

Para cada lote, en el orden de 4:

1. **Leer.**
   - De la especificación: la línea del catálogo (07), el apartado del Anexo A, 5.4 (grupo), 11 (licencias), 12 (seguridad), 16 (pruebas) y 01-1.
   - Del repositorio: `docs/DECISIONS.md` y el código de referencia de su receta:
     - servidor: F5 lote C (`media/specs.py`, `fondo.py` y `fotos.py`);
     - navegador: F5 lote B1 (`imageconvert.ts`, `client/specs.py`);
     - IA: F3 lote B (`ai/fichas.py`, `comun.py`).
2. **Versiones y licencias.**
   - Comprobar en internet la versión estable de cada dependencia e imagen y fijarla exacta, nunca `latest` (01-1 regla 2).
   - Revisar la licencia de cada dependencia, con sus dependencias transitivas y sus extras, contra 11 (regla 6).
3. **Implementar** según la receta: specs → módulo → detección → worker y Compose → web, si la herramienta necesita una interfaz propia.
4. **Probar.**
   - Muestras generadas por script.
   - pytest: efecto de cada opción, 16.4, 16.5 y errores.
   - Vitest en las herramientas del navegador.
   - Playwright de la página (proyecto navegador; `servidor.spec.ts` si hace falta la pila completa).
   - Las pruebas que necesitan un motor ausente se marcan con skip y su razón. El motor se instala en el paso «Motores del sistema» de `ci.yml`.
5. **Regenerar.**
   - `.venv/bin/python scripts/export_registry.py` y `scripts/gen_docs.py`.
   - Si cambian los workers: `scripts/gen_coolify_compose.py` con `--check`.
   - Si hay un formato nuevo: `python scripts/fixtures/filetype_cases.py`.
6. **Verificar en local**, con los comandos de 7, y anotar lo que solo puede comprobar la CI.
7. **Revisión adversarial.** Un revisor independiente (un subagente sin contexto del implementador) revisa:
   - la corrección frente a la especificación y el Anexo A;
   - la seguridad (SSRF, salida de red, bombas, lectura de archivos locales, XXE, zip-slip y secretos);
   - las licencias;
   - la accesibilidad;
   - el rendimiento y el disco;
   - el presupuesto de IA;
   - que no haya TODO ni stubs.

   Se corrige todo lo que encuentre y se repite la revisión hasta que no quede nada.
8. **Documentar.**
   - `PLAN.md`: fila «Hecho (D-a a D-b)».
   - `PROGRESS.md`: sección del lote, recuentos y «No verificado».
   - `DECISIONS.md`: un D por cada decisión no fijada en la especificación o desviación.
   - `LICENSES.md`, `ARCHITECTURE.md`, `SECURITY.md`, `LEGAL.md` y `DEPLOY-CHECKLIST.md`, cuando corresponda.
   - `tests/fixtures/SOURCES.md` y `.env.example`, si hay muestras descargadas o variables nuevas.
9. **Commit** descriptivo al cerrar el lote (regla 4), en la rama de trabajo, nunca en `main`.
10. **Integración** al final de cada onda paralela:
    - fusionar los archivos comunes;
    - regenerar `registry.json`, `TOOLS.md`, `ERRORS.md`, el Compose y los casos de `filetype`;
    - ejecutar todas las pruebas;
    - resolver los conflictos de mensajes es/en.
11. **Lote Z** de la fase: los cierres de 3.3.
12. **Bloqueos.** Si algo depende del propietario, no se espera:
    - se desactiva la herramienta con su motivo en `TOOLS.md`;
    - se añade la comprobación a `DEPLOY-CHECKLIST.md`;
    - se sigue con el lote siguiente.

## 7. Verificación

- **Python:** `.venv/bin/pytest -q` (por archivo con `-x` si falta memoria). Marcas: `integration` (PostgreSQL y Valkey), `needs_tesseract`, `needs_docling` y `needs_soffice`.
- **Licencias:**
  - `.venv/bin/python scripts/check_licenses.py python`;
  - `python3 scripts/check_licenses.py npm`.
- **Archivos generados:**
  - `scripts/export_registry.py --check`;
  - `scripts/gen_coolify_compose.py --check` (`--validate` y `docker compose -f docker-compose.yml config --quiet`, solo en la CI);
  - `python scripts/fixtures/filetype_cases.py --check`.
- **Web:** `npm test`, `npm run typecheck` (TypeScript 7) y `npm run build`.
- **Playwright** con `next start -p 3100`:
  - variables `PORT=3100`, `PUBLIC_WEB_URL=http://127.0.0.1:3100`, `BETTER_AUTH_URL=http://127.0.0.1:3100`, `PUBLIC_API_URL=http://127.0.0.1:8100`, `PUBLIC_UPLOAD_URL=http://127.0.0.1:8180`, `PUBLIC_FILES_URL=http://127.0.0.1:8190` (los simulados de las pruebas; D-141), `AUTH_SECRET=...` y `PW_CHROMIUM_PATH` apuntando al Chrome de `/opt/google`;
  - comando `npx playwright test -c tests/e2e/playwright.config.ts --project=navegador`.
- **CI** (`.github/workflows/ci.yml` e `images.yml`): imágenes con SBOM, `check_images.sh`, job docling, `e2e-compose` con el proyecto servidor y Lighthouse (desde G0-B).

## 8. Límites del entorno de trabajo (comprobado el 14/11/2026)

- **Máquina:** Debian 13 (trixie), 8 vCPU, **7 GB de RAM** y 410 GB libres. Docling, faster-whisper, OCP y `next build` no deben ejecutarse a la vez.
- **Sin Docker** (ni demonio ni CLI). Imágenes, `docker compose up`, `--validate`, `check_images.sh` y `e2e-compose` solo en la CI.
- **Sin PostgreSQL ni redis o valkey.** Las pruebas `integration` (API, IA, chat, compartir, firmas) no corren aquí salvo que el propietario los instale. `conftest.py` acepta cualquier versión en `/usr/lib/postgresql/*/bin`.
- **No están en el PATH:**
  - motores: tesseract, ffmpeg, ffprobe, pandoc, Calibre, ogr2ogr, readpst, fluidsynth, tectonic, MuseScore, OpenSCAD, draw.io, java, softhsm2-util, espeak-ng;
  - utilidades: xvfb-run, heif-enc, ddjvu, tiffcp, rar, chromium.
- **Disponibles:**
  - LibreOffice (`soffice`), `pdftocairo` y `7z` (solo para generar muestras, nunca en el producto);
  - Node 26.13.1 y npm, y Google Chrome en `/opt/google` para Playwright;
  - `.venv` con pytest, pip-licenses, docling, ezdxf, fonttools, img2pdf, mail-parser, celery y alembic.
- **Paquetes de Python nuevos:** se instalan en `.venv` con `uv pip install` y versión fijada.
- **Programas externos para probar en local:** binarios estáticos con versión y SHA-256 fijados en una caché fuera del repositorio (por ejemplo `~/.cache/conversor-motores`), solo para pruebas: pandoc, tectonic, FFmpeg LGPL de BtbN por fecha y JRE para KoSIT. Si no se puede, la CI.
- **Sin clave de OpenRouter:** el proveedor falso (D-126 y D-133).
- **Sin sudo:** lo que necesite `apt` queda para la CI o para el propietario.

## 9. Bloqueos del propietario

- Clave de OpenRouter para el cierre técnico de F3 (17).
- Permiso para hacer commit en una rama de trabajo y push a GitHub, para que la CI ejecute imágenes, integración, `e2e-compose`, veraPDF, KoSIT y los motores ausentes.
- Instalar en esta máquina (con sudo) postgresql, redis-server y los motores de sistema, o aceptar que esas pruebas solo corran en la CI.
- Token de Coolify y VPS para el cierre operativo de cada fase. El catálogo completo necesita **16 vCPU y 64 GB** (5.4; D-128).
- Entradas de 0.1 de F1: Cloudflare, Stripe, SMTP, restic, Google Drive y Dropbox.
- Revisión del contenido para pasar a `reviewed: true` y quitar el `noindex` (8.2.5, 7.22).
- Revisiones legales:
  - patentes de vídeo e imagen: HEVC, H.264, AAC, VP9 y AV1 (11);
  - facturación (`INVOICING_ES_ENABLED`): Veri*factu y RD 238/2026 (7.23);
  - firma: niveles eIDAS (10).
- Firma en producción: certificado del sello o HSM, TSA y PIN (10, 0.1).
- Escucha de la voz española de Kokoro (6.4).
- Modelo de quitar-fondo y modelos con su licencia (11).
- Muestras sin fuente libre: PST, FIT, UDF, Facturae firmada real y bgcode de PrusaSlicer si la CI no puede generarlo.
- Lighthouse oficial, prueba k6 y digests de Smokescreen y Gotenberg en el VPS.

## 10. Riesgos principales y respuesta

- **Kokoro sin el paquete oficial:** el pipeline propio puede tener fonemas mal mapeados. Respuesta: pruebas con muestras en inglés y escucha del propietario para el español (6.4).
- **PDF hostiles con la clave del sello:** la verificación va aparte, en `sign.verify` sin token.
- **KoSIT 1.6 en mantenimiento y Schematron de Factur-X:** se anota una alternativa y se comprueba la licencia de cada artefacto (7.23).
- **Memoria del VPS:** perfil de 64 GB y `${MEM_<GRUPO>}`.
- **Regla del 10 % en F6:** se vigila con antelación. Candidatas a quedar desactivadas: udf-a-pdf, manuscrito-a-texto y las pst-*.
- **Cadenas entre colas** (av → ai, convert → ai, office → av): pruebas de fallo a mitad de cadena, con devolución de reservas y `WORKER_LOST` (16.7).
- **escribir-pdf (XL):** se parte en F6-O1 y F6-O2, con Lighthouse en la página.
