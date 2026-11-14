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
| psycopg | LGPL-3.0 | Controlador de PostgreSQL |
| LibreOffice | MPL-2.0 | Programa externo en `workeroffice`, `workerconvert` y dentro de Gotenberg |
| Gotenberg | MIT | Servicio externo (`gotenberg` sin red y `gotenbergweb` para web-a-pdf) |
| Smokescreen v0.1.0 (compilado desde su etiqueta con `golang:1.25.14-bookworm`, D-155) | MIT (el binario lleva `LICENSE.txt`; sus dependencias en `vendor/` son MIT, BSD y Apache-2.0) | Proxies de salida `egressweb` y `egressai` |
| markdown-it-py, mdit-py-plugins | MIT | markdown-a-pdf |
| Pygments | BSD-2-Clause | Código resaltado en markdown-a-pdf |
| charset-normalizer | MIT | Detección de la codificación en txt-a-pdf y markdown-a-pdf |
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
