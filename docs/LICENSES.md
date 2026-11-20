# Licencias (11)

La política está en `scripts/license_policy.yaml` y la aplica `scripts/check_licenses.py` (Python y dependencias de
producción de npm). Resultado en esta entrega: **0 problemas** en los dos. `scripts/check_images.sh` comprueba en la CI
que ninguna imagen trae `gs`, `mutool` ni PyMuPDF, y las imágenes se publican con SBOM.

## Componentes destacados

| Componente | Licencia | Uso |
| --- | --- | --- |
| `@cantoo/pdf-lib`, `@cantoo/fontkit` | MIT | Herramientas PDF en el navegador |
| `@embedpdf/pdfium` (PDFium en WebAssembly) | MIT (envoltorio); PDFium con su propia licencia BSD/Apache incluida en `LICENSE.pdfium` | Renderizado en el navegador |
| Noto Sans, Noto Serif y Noto Sans Mono | OFL-1.1 (`apps/web/public/fonts/OFL.txt`) | Texto incrustado en PDF; también las muestras generadas de imágenes con texto, tablas y tickets (`scripts/fixtures/imagenes_ocr.py`) |
| `@lhci/cli` 0.16.1 y `lighthouse` 13.6.0 | Apache-2.0 | Lighthouse CI en el job `web` (solo desarrollo y CI, no se distribuye; D-145) |
| `axe-core` 4.14.0 (dependencia de Lighthouse) | MPL-2.0 | Auditoría de accesibilidad de Lighthouse (solo CI) |
| `sentry` 0.49.0 (CLI de Sentry: `@lhci/cli` > `lighthouse` > `@sentry/node` > `@sentry/bundler-plugins` > `sentry`) | FSL-1.1-Apache-2.0 (código fuente disponible; Apache-2.0 a los dos años) | Arrastrada por Lighthouse; no se ejecuta ni se distribuye, solo está instalada en desarrollo y CI (D-145) |
| k6 (Grafana) | AGPL-3.0 | Programa externo para la prueba de carga que ejecuta el propietario (16.1); no se instala en el repositorio, en las imágenes ni en la CI |
| `@uppy/core`, `@uppy/tus`, `tus-js-client` | MIT | Subidas reanudables |
| `diff-match-patch` 1.0.5 (y `@types/diff-match-patch` 1.0.36, MIT, solo desarrollo) | Apache-2.0 | comparar-pdf en el navegador; versiones exactas (D-140) |
| OpenCV.js (`@techstark/opencv-js`) | Apache-2.0 | escaner-pdf en el navegador (servido desde `public/opencv/`) |
| `@jsquash/avif` y `@jsquash/webp` (códecs de Squoosh en WebAssembly) | Apache-2.0; dentro, libavif y libaom BSD-2-Clause y libwebp BSD-3-Clause | AVIF y WebP en el navegador (servidos desde `public/codecs/`) |
| `@resvg/resvg-wasm` | MPL-2.0 (sin modificar) | svg-a-png, svg-a-jpg y crear-favicon |
| `utif2` con `pako` | MIT; MIT y Zlib | TIFF en el navegador |
| `gifenc` | MIT | GIF en el navegador |
| `wasm-feature-detect` | Apache-2.0 | Elegir el códec WebP con SIMD |
| `zxing-wasm` (zxing-cpp en WebAssembly) | MIT; zxing-cpp Apache-2.0 | leer-codigo-qr y la comprobación de generar-codigo-qr (servido desde `public/codecs/`) |
| `qr-code-styling` y `qrcode-generator` | MIT | generar-codigo-qr en la página |
| `konva` y `react-konva` | MIT | Editor de crear-collage en la página (solo en el navegador) |
| faster-whisper | MIT | transcribir-audio y video-a-subtitulos en `workeravheavy`; sin PyAV (D-111) |
| CTranslate2 | MIT; su rueda trae libgomp (GPL-3.0 con la excepción de la biblioteca de ejecución de GCC) | Motor de faster-whisper |
| `tokenizers`, `huggingface-hub` | Apache-2.0 | Dependencias de faster-whisper (sin red: `HF_HUB_OFFLINE=1`) |
| Modelos faster-whisper `small` y `medium` (Systran, convertidos de Whisper) | MIT | Transcripción; descargados al construir con su SHA-256 (D-112) |
| Silero VAD | MIT | Filtro de silencios, dentro del paquete faster-whisper |
| PyAV (`av`) | **Prohibido**: sus ruedas traen libx264 y libx265 (GPL) | Se quita al instalar con `infra/uv-overrides.txt` (D-111) |
| Modelo Kokoro-82M v1.0 (hexgrad) en la conversión a ONNX de `onnx-community/Kokoro-82M-v1.0-ONNX` (revisión `1939ad2a`), con su vocabulario de fonemas y las voces ef_dora, em_alex, em_santa, af_heart, af_bella y am_michael | Apache-2.0 (ficha del modelo y de la conversión) | Voz de pdf-a-audio en `workeravheavy`; descargado al construir con el SHA-256 de cada archivo (`infra/kokoro/fetch-model.sh`; D-167) |
| espeak-ng y sus datos de idiomas (paquete de Debian) | GPL-3.0-or-later | Programa externo en worker-av: fonemas IPA de pdf-a-audio con `run_engine` (entorno vacío, tiempo y memoria limitados); nunca se carga en el proceso de Python (11; D-168) |
| onnxruntime 1.31.0 | MIT | Inferencia de Kokoro en worker-av (también en quitar-fondo y en los embeddings) |
| pypdfium2 5.14.0 y pikepdf 10.17.0 en worker-av | Apache-2.0 o BSD-3-Clause (PDFium BSD/Apache); MPL-2.0 | Texto del PDF de pdf-a-audio (el mismo extractor que las herramientas de IA) |
| `misaki`, `phonemizer`, `phonemizer-fork`, `espeakng-loader`, `kokoro` y `kokoro-onnx` | **Prohibidos**: GPL o cargan espeak-ng (GPL) dentro del proceso | Nunca se instalan: están en `forbidden_packages` y worker-av y `scripts/check_images.sh` comprueban que no hay ninguno (D-167) |
| fpdf2 (dependencia de OCRmyPDF) | LGPL-3.0 | Solo genera las muestras de pdf-a-audio en las pruebas (`scripts/fixtures/lectura_pdf.py`) |
| rawpy con LibRaw | MIT; LibRaw LGPL-2.1 o CDDL-1.0 (sin los paquetes de demosaico GPL) | raw-a-jpg en `workermedia`, en un proceso aparte |
| psd-tools | MIT | psd-a-png (sin aggdraw) |
| vtracer | MIT | png-a-svg y jpg-a-svg |
| rembg, onnxruntime y PyMatting | MIT | quitar-fondo |
| numba y llvmlite; scikit-image; imageio y tifffile | BSD-2-Clause (llvmlite con LLVM, Apache-2.0 con excepción LLVM); BSD-3-Clause; BSD | Dependencias de rembg y psd-tools |
| Modelo u2net de rembg | Apache-2.0 (repositorio U-2-Net) | quitar-fondo; descargado al construir con su SHA-256 (D-96) |
| `@jsquash/jpeg` 1.6.0 (MozJPEG de Squoosh en WebAssembly) | Apache-2.0; dentro, MozJPEG/libjpeg-turbo con las licencias IJG, BSD-3-Clause y Zlib | JPEG de las herramientas de imagen en el navegador (solo el codificador; D-150). En las pruebas, también el decodificador |
| `@jsquash/oxipng` 2.3.0 (oxipng de Squoosh en WebAssembly, versión de un hilo) | Apache-2.0; dentro, oxipng MIT | PNG sin pérdida de las herramientas de imagen en el navegador (D-150) |
| `@jsquash/png` | Apache-2.0 | Solo en las pruebas (decodificar y codificar en Node) |
| Next.js, React, next-intl, Better Auth | MIT | Web |
| pikepdf | MPL-2.0 | PDF en servidor |
| pypdfium2 | Apache-2.0 / BSD-3-Clause | Renderizado en servidor |
| img2pdf | LGPL-3.0 | Imágenes a PDF sin recomprimir |
| OCRmyPDF (instalado con pip, sin Ghostscript) | MPL-2.0 | OCR |
| Tesseract | Apache-2.0 | OCR (programa externo) |
| Docling | MIT (código); revisar la ficha de cada modelo descargado | Desde PDF: Word, Excel, PowerPoint, ODF, RTF, Markdown, HTML, EPUB, CSV y JSON |
| PyTorch (solo CPU), transformers, accelerate | BSD-3-Clause y otras permisivas; Apache-2.0 | Modelos de Docling |
| python-docx, openpyxl, python-pptx, lxml | MIT; MIT; MIT; BSD-3-Clause | DOCX, XLSX, PPTX y EPUB fluido |
| openpyxl 3.1.5 (y su dependencia et-xmlfile) en el extra `ai`; python-docx 1.2.0 e img2pdf 0.6.3 en el extra `ocr` | MIT; MIT; MIT y LGPL-3.0 | XLSX de imagen-a-excel y ticket-a-excel en `workerai`; DOCX e imágenes a PDF de imagen-a-texto en `workerocr` (F3, lote C; las mismas versiones que en los otros extras) |
| pysubs2 1.9.1 (Python puro, sin dependencias) en el extra `ai`; se adelanta de F6 (7.13, D-177) | MIT | Leer y escribir los SRT, WebVTT y ASS de traducir-subtitulos en `workerai` |
| node-forge 1.4.0 (web) | BSD-3-Clause (doble licencia BSD-3-Clause o GPL-2.0; se usa con la BSD) | Solo la derivación de claves de PKCS#12 y 3DES/RC2 para abrir .p12 antiguos en el navegador (F4-Z, D-210); se carga solo con esos archivos |
| xadesjs 2.6.8, xmldsigjs 2.8.8, xml-core 1.2.6 y xpath 0.0.34 (web) | MIT | Firma XAdES-EPES de Facturae en el navegador (crear-factura-electronica, F4-E2b, D-207); se cargan solo al firmar |
| PKI.js 3.4.3 y asn1js 3.0.6, con pvtsutils, pvutils, bytestreamjs, @noble/hashes y tslib (web) | BSD-3-Clause; BSD-3-Clause; MIT; MIT; BSD-3-Clause; MIT; 0BSD | Abrir el .p12/.pfx en el navegador para la firma con certificado propio de firmar-pdf (F4-B2b); se carga solo al abrir el certificado |
| Dancing Script, Great Vibes y Caveat (fuentes de la firma escrita de firmar-pdf, `apps/web/public/fonts/firma`) | OFL-1.1 | Solo se pintan en el navegador para hacer la imagen de la firma (F4-B2a) |
| pyHanko 0.38.1 (extras `pkcs11`, `image-support`, `opentype` y `etsi`) y pyhanko-certvalidator 0.33.0, en el extra `sign` (F4); pyHanko sin extras también en el extra `pdf` (F4-B1) | MIT | Validación PAdES y AdES, análisis de diferencias, lista de confianza de la UE y, en F4-A2, el sello de la plataforma; en `workerpdf`, los campos de firma de hacer-pdf-rellenable |
| Dependencias de pyHanko: aiohttp (y multidict, yarl, frozenlist, aiosignal, propcache), asn1crypto, oscrypto, uritools, tzlocal, certifi, xsdata, signxml, uharfbuzz, fontTools, python-barcode, python-pkcs11 0.9.5 | Apache-2.0; MIT; MIT; MIT; MIT; MPL-2.0; MIT; Apache-2.0; Apache-2.0; MIT; MIT; MIT | Descargas por `egressweb`, X.509 y CMS, XML firmado de las listas de confianza (nunca xmlsig, AGPL), firma visible y PKCS#11 |
| SoftHSM2 (paquete `softhsm2` de Debian) en la imagen worker-sign | BSD-2-Clause | Token PKCS#11 del sello de la plataforma (10); biblioteca cargada por python-pkcs11 |
| KoSIT Validator 1.6.3 (programa Java aparte en `workerutils`) y las configuraciones de XRechnung 3.0.2 y Peppol BIS 3.0.21 (`itplr-kosit/validator-configuration-*`) | Apache-2.0 | Validación de facturas UBL y CII (F4-D, D-191) |
| Schematron de Peppol BIS Billing 3.0 (OpenPeppol, dentro de la configuración de Peppol) | sin licencia declarada en `OpenPEPPOL/peppol-bis-invoice-3`; OpenPeppol los publica para validar | Reglas PEPPOL-EN16931-*; **confirmar con OpenPeppol antes de publicar la imagen** (DEPLOY-CHECKLIST) |
| XSD de UBL 2.1 (OASIS) y de CII D16B (UN/CEFACT), dentro de las configuraciones | OASIS IPR Policy (uso y redistribución sin cambios); UN/CEFACT, uso libre | Esquemas de las sintaxis |
| Reglas EN 16931 de la Comisión Europea (Schematron de `ConnectingEurope/eInvoicing-EN16931`, dentro de la configuración de XRechnung) | EUPL-1.2 | Reglas de negocio de EN 16931; se redistribuyen sin cambios en la imagen worker-utils |
| factur-x 7.9 (extra `utils`) y sus dependencias python-stdnum, iso4217, pypdf y requests (con urllib3, idna, charset-normalizer y certifi) | BSD-3-Clause; LGPL-2.1+; dominio público; BSD-3-Clause; Apache-2.0 (MIT, BSD-3-Clause, MIT y MPL-2.0) | XML de Factur-X en PDF y XSD y Schematron oficiales de Factur-X 1.09 (artefactos de FNFE-MPE y FeRD que redistribuye factur-x; se redistribuyen sin cambios dentro de la imagen worker-utils publicada, que es el uso previsto por la especificación) |
| OpenJDK 17 JRE headless (Debian) en la imagen worker-utils | GPL-2.0 con Classpath Exception | Ejecuta KoSIT como programa aparte |
| pandoc 3.13 (binario estático oficial de jgm/pandoc, `infra/pandoc/fetch.sh` con SHA-256) | GPL-2.0-or-later | Programa externo en `workerutils` con `run_engine` y siempre `--sandbox`: docx-a-odt, odt-a-docx, docx-a-markdown, markdown-a-docx, docx-a-html y html-a-docx (F6-A, D-212); nunca se enlaza ni se distribuye fuera de las imágenes privadas (3 y 11) |
| XSD de Facturae 3.2, 3.2.1 y 3.2.2 (facturae.gob.es) y XSD de XMLDSig (W3C), en `infra/facturae` | Reutilización de la información del sector público (Ley 37/2007); W3C Software and Document License | Validación de Facturae |
| Noto Sans Regular 2.004 (Google, `packages/tools/tools/sign/fonts`, con su SHA-256) | SIL OFL 1.1 (texto en `OFL-NotoSans.txt`) | Texto de los sellos visibles de firmar-pdf y solicitar-firmas; sustituye a DejaVu, con la que pyHanko 0.38 calculaba mal las anchuras (D-202) |
| certomancer 0.16.0 (extra `dev` y la imagen `certomancer` de desarrollo; nunca en producción) | MIT | PKI de pruebas: CA, TSA, OCSP y CRL (dobles de 0.1) |
| Lista de confianza de la UE (LOTL y listas nacionales) | Datos públicos de la Comisión Europea y de cada Estado; se descargan al ejecutar y no se redistribuyen | Confianza y cualificación al verificar firmas (7.23) |
| psycopg | LGPL-3.0 | Controlador de PostgreSQL |
| LibreOffice | MPL-2.0 | Programa externo en `workeroffice`, `workerconvert` y dentro de Gotenberg |
| Gotenberg | MIT | Servicio externo (`gotenberg` sin red y `gotenbergweb` para web-a-pdf) |
| Smokescreen v0.1.0 (compilado desde su etiqueta con `golang:1.25.14-bookworm`, D-155) | MIT (el binario lleva `LICENSE.txt`; sus dependencias en `vendor/` son MIT, BSD y Apache-2.0) | Proxies de salida `egressweb` y `egressai` |
| markdown-it-py, mdit-py-plugins | MIT | markdown-a-pdf |
| Pygments | BSD-2-Clause | Código resaltado en markdown-a-pdf |
| charset-normalizer | MIT | Detección de la codificación en txt-a-pdf y markdown-a-pdf, y de los CSV de F6-B en `workerutils` (D-213) |
| openpyxl 3.1.5 (y et-xmlfile) en el extra `utils` | MIT | xlsx-a-csv, csv-a-xlsx y excel-a-json (F6-B1, D-213) |
| fontTools 4.68.0 y brotli 1.2.1 en el extra `utils` | MIT; MIT | Conversiones de fuentes TTF, OTF, WOFF y WOFF2 (F6-F, D-215) |
| asn1crypto 1.5.1 en el extra `utils`; signxml 5.3.0 y lxml 6.1.3 en el extra `sign` | MIT; Apache-2.0 y BSD-3-Clause | csig-a-pdf, p7m-a-pdf y xsig-a-pdf, y las firmas XAdES de verificar-firma en `sign.verify` (F6-G, D-219) |
| gpxpy 1.6.2 en el extra `utils`; GDAL `ogr2ogr` (gdal-bin, Debian) en `workerutils` | Apache-2.0; MIT | GPX de F6-H1 y Shapefile a GeoJSON y KML como programa externo (D-220); nunca `osgeo` en el proceso (11) |
| fitparse 1.2.0 en el extra `utils` | MIT | FIT de relojes y ciclocomputadores en fit-a-gpx y fit-a-csv (F6-H2, D-223) |
| trimesh 5.2.1, lib3mf 2.5.0, numpy, scipy y networkx en el extra `mesh` | MIT; BSD-2-Clause; BSD-3-Clause | Mallas STL, OBJ, PLY y 3MF de F7-A (D-244), en `workermesh`; lib3mf por su biblioteca C con búferes de numpy |
| pyassimp 5.2.5 en el extra `mesh`; libassimp5 (con libdraco8, libminizip1 y libpugixml1v5) de Debian en `workermesh` | ISC; BSD-3-Clause (Apache-2.0, Zlib y MIT las dependencias) | FBX, DAE y 3DS de F7-B en un proceso hijo con Landlock (D-248); AMF y GLB sin bibliotecas nuevas |
| vobject 0.9.9 (con pytz y six) e icalendar 7.3.0 (con tzdata) en el extra `utils` | Apache-2.0; BSD-2-Clause | vCard e iCalendar de F6-I (D-224) |
| readpst de libpst (pst-utils, Debian) en `workermedia` | GPL-2.0-or-later | pst-a-mbox y pst-a-pdf como programa externo (F6-J, D-225) |
| Tectonic 0.17.0 (binario oficial musl) y los paquetes de TeX de su caché | MIT; licencias libres de TeX Live (LPPL, GPL, OFL y otras) | latex-a-pdf en `workerutils`, aislado con Landlock (F6-K, D-227) |
| Visor de draw.io `viewer-static.min.js` v32.6.10 (jgraph/drawio) | Apache-2.0 | drawio-a-pdf y drawio-a-png en el Chromium de Gotenberg (F6-K, D-227) |
| mammoth 1.13.0 (npm) | BSD-2-Clause | abrir Word en escribir-pdf; jszip (MIT o GPL-3.0, se usa con MIT); argparse no se empaqueta (F6-O2, D-236) |
| marked 18.1.3 (npm) | MIT | abrir Markdown en escribir-pdf |
| TipTap 3.33.0 (@tiptap/*, npm) | MIT | editor de escribir-pdf; solo paquetes del registro público, sin Pages ni la conversión a DOCX de pago (F6-O1, D-234) |
| KaTeX 0.18.10 (npm) | MIT | fórmulas de escribir-pdf (en el editor y como MathML en el PDF) |
| docx 9.15.2 (npm) | MIT | exportación de escribir-pdf a Word en el navegador |
| linkedom 0.18.15 (npm, desarrollo) | ISC | DOM para las pruebas de la exportación de escribir-pdf; no llega al build |
| qrcode-generator 1.5.2 (npm) | MIT | códigos QR de crear-tarjeta en el editor y en el worker (F6-N2, D-232) |
| mermaid 12.2.0 (npm) | MIT | mermaid-a-svg y mermaid-a-png en el navegador (F6-N1, D-231); sus dependencias son MIT, ISC, BSD, Apache-2.0 y DOMPurify (MPL-2.0 o Apache-2.0); elkjs (EPL-2.0) no se empaqueta |
| FluidSynth (Debian) y el banco FluidR3_GM (fluid-soundfont-gm) en `workerav` | LGPL-2.1-or-later; MIT | midi-a-mp3 y midi-a-wav, FluidSynth como programa externo (F6-L, D-228) |
| MuseScore 3 (musescore3, Debian) en `workeroffice` | GPL-3.0 | musicxml-a-pdf y midi-a-pdf como programa externo sin interfaz (F6-L, D-228) |
| libarchive-c 5.3 y libarchive13 (Debian) en `workerutils`; pysubs2 1.9.1 en el extra `utils` | CC0-1.0 y BSD-2-Clause; MIT | Comprimidos RAR, 7z y tar y subtítulos SRT, WebVTT y ASS (F6-E, D-217); sin unrar ni p7zip (11) |
| PyYAML 6.0.3 (con libyaml) y defusedxml 0.7.1 | MIT; PSF-2.0 | yaml-a-json, json-a-yaml y xml-a-json (F6-B2, D-214): `CSafeLoader` y XML sin entidades ni DTD externos |
| LibreOffice Calc (`libreoffice-calc-nogui`, Debian) en `workeroffice` | MPL-2.0 | ods-a-xlsx y xlsx-a-ods como programa externo (F6-B1) |
| FFmpeg (compilación LGPL de BtbN, n8.1.3-27 del autobuild 2026-10-31, D-137) | LGPL-2.1 o posterior | Programa externo en `workerav`; SHA-256 fijado y la imagen falla si detecta `--enable-gpl` |
| tusd | MIT | Servicio de subidas |
| Caddy | Apache-2.0 | Descargas |
| PostgreSQL y pgvector | PostgreSQL License | Base de datos |
| Valkey | BSD-3-Clause | Cola y límites |
| Calibre (`ebook-convert`, paquete de Debian) | GPL-3.0 | Programa externo en `workeroffice`: EPUB, MOBI, AZW3 y FB2 a PDF |
| DjVuLibre (`ddjvu`) | GPL-2.0 | Programa externo en `workermedia`: djvu-a-pdf |
| libheif (`heif-dec`, compilado solo para decodificar) y libde265 | LGPL-3.0 | Programa externo en `workermedia`: heic-a-pdf, detrás de `HEVC_DECODE_ENABLED`; sin x265 (D-49) |
| libarchive y libarchive-c | BSD-2-Clause y CC0-1.0 | CBZ y CBR |
| ezdxf (sin el extra `draw`) con numpy, fontTools y pyparsing | MIT; numpy BSD-3-Clause y otras permisivas | dxf-a-pdf |
| olefile | BSD-2-Clause | msg-a-pdf |
| compressed-rtf | MIT | Cuerpo RTF de msg-a-pdf |
| nh3 | MIT | Saneado del HTML de los correos |
| veraPDF | MPL-2.0 o GPL-3.0 (doble licencia) | Programa externo en `workerocr`: pdf-a-pdfa y validar-pdfa |
| OpenJDK 17 (paquete de Debian) | GPL-2.0 con excepción de enlace (Classpath) | Para ejecutar veraPDF |
| poppler-utils (`pdftocairo`) | GPL-2.0/GPL-3.0 | Programa externo en `workerpdf`: pdf-a-svg |
| libtiff-tools (`tiffcp`) | libtiff (permisiva, tipo BSD) | pdf-a-tiff |
| Perfil `FOGRA39L_coated.icc` (colord, copiado en `infra/icc` con su SHA-256, D-154) | CC0-1.0 | CMYK en pdf-a-jpg y pdf-a-tiff |

Prohibidos y comprobados por la CI: Ghostscript, MuPDF, PyMuPDF, pdf2docx, extract-msg, pillow-heif y el resto de la
lista de 11. Las imágenes son privadas porque llevan programas GPL (Calibre, DjVuLibre) como procesos externos (3.3).
