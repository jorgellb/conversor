# Herramientas (7, 7.24 y 17)

Catálogo publicado en esta entrega: 257 herramientas (F1 43, F2 60, F3 10, F4 15, F5 50, F6 79). Fases cerradas: F1, F2, F4 y F5 sin vídeo; en curso: F3. El orden y los lotes que faltan están en `docs/PLAN.md` y `docs/GOAL.md`. Generado por `scripts/gen_docs.py` desde `packages/registry/registry.json`, `config/tools-notes.yaml` y `config/pdf24.yaml`: no lo edites a mano.

«Estado» es el de un despliegue con los valores por defecto: `TOOL_<SLUG>_ENABLED=false` apaga cualquiera y la tabla `feature_flags` también (5.2). «Indexable» exige herramienta activa, pruebas en verde y contenido propio completo y revisado en el idioma (7.22); sin él, la página lleva `noindex`.

| Herramienta (es / en) | Dónde | Grupo | Coste | Fase | Estado | Entrada → salida | Contenido propio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `unir-pdf` / `merge-pdf` | navegador | — | light | F1 | activa | pdf → pdf | redactado, sin revisar |
| `dividir-pdf` / `split-pdf` | navegador | — | light | F1 | activa | pdf → pdf, zip | redactado, sin revisar |
| `girar-pdf` / `rotate-pdf` | navegador | — | light | F1 | activa | pdf → pdf | redactado, sin revisar |
| `eliminar-paginas-pdf` / `delete-pdf-pages` | navegador | — | light | F1 | activa | pdf → pdf | redactado, sin revisar |
| `extraer-paginas-pdf` / `extract-pdf-pages` | navegador | — | light | F1 | activa | pdf → pdf, zip | redactado, sin revisar |
| `organizar-pdf` / `organize-pdf` | navegador | — | light | F1 | activa | pdf → pdf | redactado, sin revisar |
| `numerar-paginas-pdf` / `add-page-numbers-pdf` | navegador | — | light | F1 | activa | pdf → pdf | redactado, sin revisar |
| `marca-de-agua-pdf` / `watermark-pdf` | navegador | — | light | F1 | activa | pdf, png, jpg → pdf | redactado, sin revisar |
| `editar-pdf` / `edit-pdf` | navegador | — | light | F1 | activa | pdf → pdf | redactado, sin revisar |
| `rellenar-pdf` / `fill-pdf` | navegador | — | light | F1 | activa | pdf → pdf | redactado, sin revisar |
| `recortar-pdf` / `crop-pdf` | navegador | — | light | F1 | activa | pdf → pdf, zip | redactado, sin revisar |
| `cambiar-tamano-pagina-pdf` / `resize-pdf-pages` | navegador | — | light | F1 | activa | pdf → pdf, zip | redactado, sin revisar |
| `varias-paginas-por-hoja` / `n-up-pdf` | navegador | — | light | F1 | activa | pdf → pdf, zip | redactado, sin revisar |
| `folleto-pdf` / `booklet-pdf` | navegador | — | light | F1 | activa | pdf → pdf, zip | redactado, sin revisar |
| `aplanar-pdf` / `flatten-pdf` | navegador | — | light | F1 | activa | pdf → pdf, zip | redactado, sin revisar |
| `hacer-pdf-rellenable` / `make-pdf-fillable` | híbrida | pdf | light | F4 | activa | pdf → pdf | redactado, sin revisar |
| `crear-formulario-pdf` / `create-pdf-form` | híbrida | pdf | light | F4 | activa | pdf → pdf | redactado, sin revisar |
| `crear-factura` / `create-invoice` | navegador | — | light | F4 | apagada | — → pdf | redactado, sin revisar |
| `anotar-pdf` / `annotate-pdf` | navegador | — | light | F1 | activa | pdf → pdf | redactado, sin revisar |
| `lector-pdf` / `pdf-reader` | híbrida | office | light | F1 | activa | pdf, doc, docx, rtf, odt, txt, xls, xlsx, ods, csv, ppt, pptx, pps, odp, odg, jpg, png, gif, bmp, tiff, webp → pdf | redactado, sin revisar |
| `cortar-paginas-por-la-mitad` / `split-pages-in-half` | navegador | — | light | F2 | activa | pdf → pdf, zip | redactado, sin revisar |
| `imprimir-pdf` / `print-pdf` | navegador | — | light | F2 | activa | pdf → pdf, zip | redactado, sin revisar |
| `montar-pdf` / `assemble-pdf` | navegador | — | light | F2 | activa | pdf, jpg, png, webp, gif, bmp → pdf, zip | redactado, sin revisar |
| `marcadores-pdf` / `pdf-bookmarks` | navegador | — | light | F2 | activa | pdf → pdf | redactado, sin revisar |
| `comparar-pdf` / `compare-pdf` | navegador | — | light | F2 | activa | pdf → pdf | redactado, sin revisar |
| `buscar-en-pdf` / `search-pdf` | navegador | — | light | F2 | activa | pdf → csv | redactado, sin revisar |
| `redactar-pdf` / `redact-pdf` | navegador | — | light | F1 | activa | pdf → pdf | redactado, sin revisar |
| `webp-a-pdf` / `webp-to-pdf` | navegador | — | light | F1 | activa | webp → pdf | redactado, sin revisar |
| `gif-a-pdf` / `gif-to-pdf` | navegador | — | light | F1 | activa | gif → pdf | redactado, sin revisar |
| `bmp-a-pdf` / `bmp-to-pdf` | navegador | — | light | F1 | activa | bmp → pdf | redactado, sin revisar |
| `tiff-a-pdf` / `tiff-to-pdf` | servidor | pdf | light | F2 | activa | tiff → pdf | redactado, sin revisar |
| `imagenes-a-pdf` / `images-to-pdf` | híbrida | pdf | light | F1 | activa | jpg, png, webp, gif, bmp, tiff → pdf | redactado, sin revisar |
| `jpg-a-pdf` / `jpg-to-pdf` | híbrida | pdf | light | F1 | activa | jpg → pdf | redactado, sin revisar |
| `png-a-pdf` / `png-to-pdf` | híbrida | pdf | light | F1 | activa | png → pdf | redactado, sin revisar |
| `pdf-a-jpg` / `pdf-to-jpg` | híbrida | pdf | light | F1 | activa | pdf → jpg, zip | redactado, sin revisar |
| `pdf-a-png` / `pdf-to-png` | híbrida | pdf | light | F1 | activa | pdf → png, zip | redactado, sin revisar |
| `pdf-a-webp` / `pdf-to-webp` | híbrida | pdf | light | F2 | activa | pdf → webp, zip | redactado, sin revisar |
| `pdf-a-imagenes` / `pdf-to-images` | híbrida | pdf | light | F1 | activa | pdf → zip | redactado, sin revisar |
| `escaner-pdf` / `pdf-scanner` | navegador | — | light | F2 | activa | jpg, png, webp → pdf | redactado, sin revisar |
| `generar-contrasena` / `password-generator` | navegador | — | light | F1 | activa | — → pantalla | redactado, sin revisar |
| `png-a-jpg` / `png-to-jpg` | navegador | — | light | F5 | activa | png → jpg | redactado, sin revisar |
| `webp-a-jpg` / `webp-to-jpg` | navegador | — | light | F5 | activa | webp → jpg | redactado, sin revisar |
| `comprimir-imagen` / `compress-image` | navegador | — | light | F5 | activa | jpg, png, webp → jpg, png, webp | redactado, sin revisar |
| `redimensionar-imagen` / `resize-image` | navegador | — | light | F5 | activa | jpg, png, webp → jpg, png, webp | redactado, sin revisar |
| `jpg-a-png` / `jpg-to-png` | navegador | — | light | F5 | activa | jpg → png, zip | redactado, sin revisar |
| `webp-a-png` / `webp-to-png` | navegador | — | light | F5 | activa | webp → png, zip | redactado, sin revisar |
| `gif-a-png` / `gif-to-png` | navegador | — | light | F5 | activa | gif → png, zip | redactado, sin revisar |
| `jpg-a-webp` / `jpg-to-webp` | navegador | — | light | F5 | activa | jpg → webp, zip | redactado, sin revisar |
| `png-a-webp` / `png-to-webp` | navegador | — | light | F5 | activa | png → webp, zip | redactado, sin revisar |
| `avif-a-jpg` / `avif-to-jpg` | navegador | — | light | F5 | activa | avif → jpg, zip | redactado, sin revisar |
| `jpg-a-avif` / `jpg-to-avif` | navegador | — | light | F5 | activa | jpg → avif, zip | redactado, sin revisar |
| `bmp-a-jpg` / `bmp-to-jpg` | navegador | — | light | F5 | activa | bmp → jpg, zip | redactado, sin revisar |
| `tiff-a-jpg` / `tiff-to-jpg` | navegador | — | light | F5 | activa | tiff → jpg, zip | redactado, sin revisar |
| `png-a-ico` / `png-to-ico` | navegador | — | light | F5 | activa | png → ico, zip | redactado, sin revisar |
| `convertir-imagen` / `convert-image` | navegador | — | light | F5 | activa | jpg, png, webp, avif, gif, bmp, tiff, ico, svg → jpg, png, webp, avif, gif, bmp, tiff, ico, zip | redactado, sin revisar |
| `svg-a-png` / `svg-to-png` | navegador | — | light | F5 | activa | svg → png, zip | redactado, sin revisar |
| `svg-a-jpg` / `svg-to-jpg` | navegador | — | light | F5 | activa | svg → jpg, zip | redactado, sin revisar |
| `crear-favicon` / `favicon-generator` | navegador | — | light | F5 | activa | png, jpg, webp, svg → ico, png, zip | redactado, sin revisar |
| `quitar-metadatos-foto` / `remove-photo-metadata` | navegador | — | light | F5 | activa | jpg, png, webp → jpg, png, webp, zip | redactado, sin revisar |
| `imagen-a-base64` / `image-to-base64` | navegador | — | light | F5 | activa | jpg, png, webp, gif, svg, avif, bmp, ico → txt, zip | redactado, sin revisar |
| `leer-codigo-qr` / `qr-code-reader` | navegador | — | light | F5 | activa | jpg, png, webp, gif, bmp, avif, tiff, svg, pdf → csv | redactado, sin revisar |
| `generar-codigo-qr` / `qr-code-generator` | navegador | — | light | F5 | activa | — → png, svg, pdf | redactado, sin revisar |
| `crear-tarjeta` / `card-maker` | navegador | — | light | F6 | activa | jpg, png, webp, gif, bmp, avif → pdf, jpg, png, zip | redactado, sin revisar |
| `mermaid-a-svg` / `mermaid-to-svg` | navegador | — | light | F6 | activa | mmd → svg | redactado, sin revisar |
| `mermaid-a-png` / `mermaid-to-png` | navegador | — | light | F6 | activa | mmd → png | redactado, sin revisar |
| `crear-collage` / `collage-maker` | navegador | — | light | F5 | activa | jpg, png, webp, gif, bmp, avif → pdf, jpg, png, zip | redactado, sin revisar |
| `comprimir-pdf` / `compress-pdf` | servidor | pdf | light | F1 | activa | pdf → pdf, zip | redactado, sin revisar |
| `proteger-pdf` / `protect-pdf` | servidor | pdf | light | F2 | activa | pdf → pdf, zip | redactado, sin revisar |
| `desbloquear-pdf` / `unlock-pdf` | servidor | pdf | light | F2 | activa | pdf → pdf, zip | redactado, sin revisar |
| `reparar-pdf` / `repair-pdf` | servidor | pdf | light | F2 | activa | pdf → pdf, zip | redactado, sin revisar |
| `optimizar-pdf-web` / `optimize-pdf-for-web` | servidor | pdf | light | F2 | activa | pdf → pdf, zip | redactado, sin revisar |
| `pdf-escala-de-grises` / `grayscale-pdf` | servidor | pdf | light | F2 | activa | pdf → pdf, zip | redactado, sin revisar |
| `pdf-modo-oscuro` / `dark-mode-pdf` | servidor | pdf | light | F2 | activa | pdf → pdf, zip | redactado, sin revisar |
| `extraer-imagenes-pdf` / `extract-images-from-pdf` | servidor | pdf | light | F2 | activa | pdf → zip | redactado, sin revisar |
| `metadatos-pdf` / `pdf-metadata` | servidor | pdf | light | F2 | activa | pdf → pdf, zip | redactado, sin revisar |
| `eliminar-metadatos-pdf` / `remove-pdf-metadata` | servidor | pdf | light | F2 | activa | pdf → pdf, zip | redactado, sin revisar |
| `rasterizar-pdf` / `rasterize-pdf` | servidor | pdf | light | F2 | activa | pdf → pdf, zip | redactado, sin revisar |
| `preferencias-visor-pdf` / `pdf-viewer-preferences` | servidor | pdf | light | F2 | activa | pdf → pdf, zip | redactado, sin revisar |
| `pdf-a-tiff` / `pdf-to-tiff` | servidor | pdf | light | F2 | activa | pdf → tiff, zip | redactado, sin revisar |
| `pdf-a-svg` / `pdf-to-svg` | servidor | pdf | light | F2 | activa | pdf → svg, zip | redactado, sin revisar |
| `pdf-a-txt` / `pdf-to-txt` | servidor | pdf | light | F2 | activa | pdf → txt, zip | redactado, sin revisar |
| `convertir-a-pdf` / `convert-to-pdf` | servidor | office | light | F1 | activa | doc, docx, rtf, odt, txt, xls, xlsx, ods, csv, ppt, pptx, pps, odp, odg, jpg, png, gif, bmp, tiff, webp, html → pdf, zip | redactado, sin revisar |
| `word-a-pdf` / `word-to-pdf` | servidor | office | light | F1 | activa | doc, docx → pdf, zip | redactado, sin revisar |
| `excel-a-pdf` / `excel-to-pdf` | servidor | office | light | F1 | activa | xls, xlsx → pdf, zip | redactado, sin revisar |
| `ppt-a-pdf` / `powerpoint-to-pdf` | servidor | office | light | F1 | activa | ppt, pptx, pps → pdf, zip | redactado, sin revisar |
| `odt-a-pdf` / `odt-to-pdf` | servidor | office | light | F1 | activa | odt → pdf, zip | redactado, sin revisar |
| `ods-a-pdf` / `ods-to-pdf` | servidor | office | light | F1 | activa | ods → pdf, zip | redactado, sin revisar |
| `odp-a-pdf` / `odp-to-pdf` | servidor | office | light | F1 | activa | odp → pdf, zip | redactado, sin revisar |
| `odg-a-pdf` / `odg-to-pdf` | servidor | office | light | F1 | activa | odg → pdf, zip | redactado, sin revisar |
| `rtf-a-pdf` / `rtf-to-pdf` | servidor | office | light | F1 | activa | rtf → pdf, zip | redactado, sin revisar |
| `txt-a-pdf` / `txt-to-pdf` | servidor | office | light | F1 | activa | txt → pdf, zip | redactado, sin revisar |
| `html-a-pdf` / `html-to-pdf` | servidor | office | light | F1 | activa | html, zip → pdf, zip | redactado, sin revisar |
| `markdown-a-pdf` / `markdown-to-pdf` | servidor | office | light | F1 | activa | md → pdf, zip | redactado, sin revisar |
| `superponer-pdf` / `overlay-pdf` | servidor | office | light | F2 | activa | pdf, doc, docx, rtf, odt, txt, xls, xlsx, ods, csv, ppt, pptx, pps, odp, odg, jpg, png, gif, bmp, tiff, webp → pdf, zip | redactado, sin revisar |
| `svg-a-pdf` / `svg-to-pdf` | servidor | office | light | F2 | activa | svg → pdf, zip | redactado, sin revisar |
| `pages-a-pdf` / `pages-to-pdf` | servidor | office | light | F2 | activa | pages → pdf, zip | redactado, sin revisar |
| `keynote-a-pdf` / `keynote-to-pdf` | servidor | office | light | F2 | activa | key → pdf, zip | redactado, sin revisar |
| `numbers-a-pdf` / `numbers-to-pdf` | servidor | office | light | F2 | activa | numbers → pdf, zip | redactado, sin revisar |
| `visio-a-pdf` / `visio-to-pdf` | servidor | office | light | F2 | activa | vsd, vsdx → pdf, zip | redactado, sin revisar |
| `publisher-a-pdf` / `publisher-to-pdf` | servidor | office | light | F2 | activa | pub → pdf, zip | redactado, sin revisar |
| `pub-a-pdf` / `pub-to-pdf` | servidor | office | light | F2 | activa, alias de `publisher-a-pdf` | pub → pdf, zip | no aplica (alias) |
| `epub-a-pdf` / `epub-to-pdf` | servidor | office | light | F2 | activa | epub → pdf, zip | redactado, sin revisar |
| `mobi-a-pdf` / `mobi-to-pdf` | servidor | office | light | F2 | activa | mobi → pdf, zip | redactado, sin revisar |
| `azw3-a-pdf` / `azw3-to-pdf` | servidor | office | light | F2 | activa | azw3 → pdf, zip | redactado, sin revisar |
| `fb2-a-pdf` / `fb2-to-pdf` | servidor | office | light | F2 | activa | fb2 → pdf, zip | redactado, sin revisar |
| `solicitud-de-empleo-pdf` / `job-application-pdf` | servidor | office | light | F2 | activa | pdf, doc, docx, rtf, odt, txt, xls, xlsx, ods, csv, ppt, pptx, pps, odp, odg, jpg, png, gif, bmp, tiff, webp → pdf, zip | redactado, sin revisar |
| `web-a-pdf` / `web-to-pdf` | servidor | office | light | F1 | activa | — → pdf | redactado, sin revisar |
| `epub-a-mobi` / `epub-to-mobi` | servidor | office | light | F6 | activa | epub → mobi, zip | redactado, sin revisar |
| `epub-a-azw3` / `epub-to-azw3` | servidor | office | light | F6 | activa | epub → azw3, zip | redactado, sin revisar |
| `mobi-a-epub` / `mobi-to-epub` | servidor | office | light | F6 | activa | mobi → epub, zip | redactado, sin revisar |
| `azw3-a-epub` / `azw3-to-epub` | servidor | office | light | F6 | activa | azw3 → epub, zip | redactado, sin revisar |
| `pptx-a-imagenes` / `pptx-to-images` | servidor | office | light | F6 | activa | pptx, ppt, odp → png, jpg, zip | redactado, sin revisar |
| `escribir-pdf` / `write-pdf` | servidor | office | light | F6 | activa | html, pdf → pdf | redactado, sin revisar |
| `captura-web` / `website-screenshot` | servidor | office | light | F6 | activa | — → png, jpg | redactado, sin revisar |
| `udf-a-pdf` / `udf-to-pdf` | servidor | office | light | F6 | apagada | udf → pdf, zip | redactado, sin revisar |
| `word-a-pdf-accesible` / `accessible-word-to-pdf` | servidor | office | light | F4 | activa | doc, docx, odt, rtf → pdf, html, zip | redactado, sin revisar |
| `csv-a-pdf` / `csv-to-pdf` | servidor | office | light | F1 | activa | csv → pdf, zip | redactado, sin revisar |
| `musicxml-a-pdf` / `musicxml-to-pdf` | servidor | office | light | F6 | activa | musicxml, mxl, xml → pdf, zip | redactado, sin revisar |
| `midi-a-pdf` / `midi-to-pdf` | servidor | office | light | F6 | activa | mid → pdf, zip | redactado, sin revisar |
| `ocr-pdf` / `ocr-pdf` | servidor | ocr | heavy | F2 | activa | pdf → pdf, txt, zip | redactado, sin revisar |
| `pdf-a-pdfa` / `pdf-to-pdfa` | servidor | ocr | heavy | F2 | activa | pdf → pdf, html, zip | redactado, sin revisar |
| `validar-pdfa` / `validate-pdfa` | servidor | ocr | light | F2 | activa | pdf → html, zip | redactado, sin revisar |
| `imagen-a-texto` / `image-to-text` | servidor | ocr | heavy | F3 | activa | jpg, png, webp, tiff, bmp, gif → txt, docx, pdf, zip | redactado, sin revisar |
| `pdf-a-word` / `pdf-to-word` | servidor | convert | heavy | F2 | activa | pdf → docx, zip | redactado, sin revisar |
| `pdf-a-odt` / `pdf-to-odt` | servidor | convert | heavy | F2 | activa | pdf → odt, zip | redactado, sin revisar |
| `pdf-a-rtf` / `pdf-to-rtf` | servidor | convert | heavy | F2 | activa | pdf → rtf, zip | redactado, sin revisar |
| `pdf-a-excel` / `pdf-to-excel` | servidor | convert | heavy | F2 | activa | pdf → xlsx, zip | redactado, sin revisar |
| `pdf-a-ods` / `pdf-to-ods` | servidor | convert | heavy | F2 | activa | pdf → ods, zip | redactado, sin revisar |
| `pdf-a-ppt` / `pdf-to-ppt` | servidor | convert | heavy | F2 | activa | pdf → pptx, zip | redactado, sin revisar |
| `pdf-a-odp` / `pdf-to-odp` | servidor | convert | heavy | F2 | activa | pdf → odp, zip | redactado, sin revisar |
| `pdf-a-markdown` / `pdf-to-markdown` | servidor | convert | heavy | F2 | activa | pdf → md, zip | redactado, sin revisar |
| `pdf-a-html` / `pdf-to-html` | servidor | convert | heavy | F2 | activa | pdf → html, zip | redactado, sin revisar |
| `pdf-a-epub` / `pdf-to-epub` | servidor | convert | heavy | F2 | activa | pdf → epub, zip | redactado, sin revisar |
| `pdf-a-csv` / `pdf-to-csv` | servidor | convert | heavy | F2 | activa | pdf → csv, zip | redactado, sin revisar |
| `pdf-a-json` / `pdf-to-json` | servidor | convert | heavy | F2 | activa | pdf → json, zip | redactado, sin revisar |
| `copiar-de-pdf` / `copy-from-pdf` | híbrida | convert | heavy | F2 | activa | pdf → json, md, xlsx | redactado, sin revisar |
| `convertir-desde-pdf` / `convert-from-pdf` | servidor | convert | light | F2 | activa | pdf → csv, docx, epub, html, jpg, json, md, odp, ods, odt, pdf, png, pptx, rtf, svg, tiff, txt, webp, xlsx, zip | redactado, sin revisar |
| `ogg-a-mp3` / `ogg-to-mp3` | servidor | av | light | F5 | activa | ogg, opus, oga → mp3, zip | redactado, sin revisar |
| `opus-a-mp3` / `opus-to-mp3` | servidor | av | light | F5 | activa | opus, ogg → mp3, zip | redactado, sin revisar |
| `m4a-a-mp3` / `m4a-to-mp3` | servidor | av | light | F5 | activa | m4a → mp3, zip | redactado, sin revisar |
| `mp4-a-mp3` / `mp4-to-mp3` | servidor | av | light | F5 | activa | mp4, m4a → mp3, zip | redactado, sin revisar |
| `aac-a-mp3` / `aac-to-mp3` | servidor | av | light | F5 | activa | aac, m4a → mp3, zip | redactado, sin revisar |
| `flac-a-mp3` / `flac-to-mp3` | servidor | av | light | F5 | activa | flac → mp3, zip | redactado, sin revisar |
| `pptx-a-video` / `pptx-to-video` | servidor | av | heavy | F6 | activa | pptx, ppt, odp → webm, mp4 | redactado, sin revisar |
| `midi-a-mp3` / `midi-to-mp3` | servidor | av | light | F6 | activa | mid → mp3, zip | redactado, sin revisar |
| `midi-a-wav` / `midi-to-wav` | servidor | av | light | F6 | activa | mid → wav, zip | redactado, sin revisar |
| `wav-a-mp3` / `wav-to-mp3` | servidor | av | light | F5 | activa | wav → mp3, zip | redactado, sin revisar |
| `wma-a-mp3` / `wma-to-mp3` | servidor | av | light | F5 | activa | wma → mp3, zip | redactado, sin revisar |
| `amr-a-mp3` / `amr-to-mp3` | servidor | av | light | F5 | activa | amr → mp3, zip | redactado, sin revisar |
| `aiff-a-mp3` / `aiff-to-mp3` | servidor | av | light | F5 | activa | aiff, aif → mp3, zip | redactado, sin revisar |
| `ogg-a-wav` / `ogg-to-wav` | servidor | av | light | F5 | activa | ogg, opus, oga → wav, zip | redactado, sin revisar |
| `mp3-a-wav` / `mp3-to-wav` | servidor | av | light | F5 | activa | mp3 → wav, zip | redactado, sin revisar |
| `cortar-audio` / `cut-audio` | servidor | av | light | F5 | activa | mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr → mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr, zip | redactado, sin revisar |
| `unir-audios` / `merge-audio` | servidor | av | light | F5 | activa | mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr → mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr | redactado, sin revisar |
| `normalizar-volumen` / `normalize-audio` | servidor | av | light | F5 | activa | mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr → mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr, zip | redactado, sin revisar |
| `cambiar-velocidad-audio` / `change-audio-speed` | servidor | av | light | F5 | activa | mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr → mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr, zip | redactado, sin revisar |
| `pdf-a-audio` / `pdf-to-audio` | servidor | av | heavy | F3 | activa | pdf → mp3 | redactado, sin revisar |
| `transcribir-audio` / `transcribe-audio` | servidor | av | heavy | F5 | activa | mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr, mp4, webm → txt, docx, srt, zip | redactado, sin revisar |
| `video-a-subtitulos` / `video-to-subtitles` | servidor | av | heavy | F5 | activa | mp4, mov, mkv, webm, avi → srt, vtt, zip | redactado, sin revisar |
| `heic-a-pdf` / `heic-to-pdf` | servidor | media | light | F2 | apagada | heic → pdf, zip | redactado, sin revisar |
| `cbz-a-pdf` / `cbz-to-pdf` | servidor | media | light | F2 | activa | cbz → pdf, zip | redactado, sin revisar |
| `cbr-a-pdf` / `cbr-to-pdf` | servidor | media | light | F2 | activa | cbr → pdf, zip | redactado, sin revisar |
| `djvu-a-pdf` / `djvu-to-pdf` | servidor | media | light | F2 | activa | djvu → pdf, zip | redactado, sin revisar |
| `eml-a-pdf` / `eml-to-pdf` | servidor | media | light | F2 | activa | eml → pdf, zip | redactado, sin revisar |
| `mbox-a-eml` / `mbox-to-eml` | servidor | media | light | F6 | activa | mbox → zip | redactado, sin revisar |
| `mbox-a-pdf` / `mbox-to-pdf` | servidor | media | light | F6 | activa | mbox → pdf | redactado, sin revisar |
| `pst-a-mbox` / `pst-to-mbox` | servidor | media | light | F6 | apagada | pst, ost → zip | redactado, sin revisar |
| `pst-a-pdf` / `pst-to-pdf` | servidor | media | light | F6 | apagada | pst, ost → pdf | redactado, sin revisar |
| `msg-a-pdf` / `msg-to-pdf` | servidor | media | light | F2 | activa | msg → pdf, zip | redactado, sin revisar |
| `dxf-a-pdf` / `dxf-to-pdf` | servidor | media | light | F2 | activa | dxf → pdf, zip | redactado, sin revisar |
| `heic-a-jpg` / `heic-to-jpg` | servidor | media | light | F5 | apagada | heic → jpg, zip | redactado, sin revisar |
| `heic-a-png` / `heic-to-png` | servidor | media | light | F5 | apagada | heic → png, zip | redactado, sin revisar |
| `raw-a-jpg` / `raw-to-jpg` | servidor | media | light | F5 | activa | cr2, nef, arw, dng → jpg, zip | redactado, sin revisar |
| `psd-a-png` / `psd-to-png` | servidor | media | light | F5 | activa | psd, psb → png, zip | redactado, sin revisar |
| `png-a-svg` / `png-to-svg` | servidor | media | light | F5 | activa | png → svg, zip | redactado, sin revisar |
| `jpg-a-svg` / `jpg-to-svg` | servidor | media | light | F5 | activa | jpg → svg, zip | redactado, sin revisar |
| `quitar-fondo` / `remove-background` | servidor | media | heavy | F5 | activa | jpg, png, webp → png, webp, jpg, zip | redactado, sin revisar |
| `resumir-pdf` / `summarize-pdf` | servidor | ai | ai | F3 | activa | pdf → docx, txt, md | redactado, sin revisar |
| `chat-pdf` / `chat-with-pdf` | servidor | ai | ai | F3 | activa | pdf → pantalla | redactado, sin revisar |
| `generador-de-preguntas` / `question-generator` | servidor | ai | ai | F3 | activa | pdf → docx, txt | redactado, sin revisar |
| `pdf-a-fichas` / `pdf-to-flashcards` | servidor | ai | ai | F3 | activa | pdf → txt, csv, docx | redactado, sin revisar |
| `pdf-a-presentacion` / `pdf-to-presentation` | servidor | ai | ai | F3 | activa | pdf → pptx | redactado, sin revisar |
| `traducir-pdf` / `translate-pdf` | servidor | ai | ai | F3 | activa | pdf → docx, pdf | redactado, sin revisar |
| `traducir-word` / `translate-word` | servidor | ai | ai | F6 | activa | docx → docx | redactado, sin revisar |
| `traducir-excel` / `translate-excel` | servidor | ai | ai | F6 | activa | xlsx → xlsx | redactado, sin revisar |
| `traducir-powerpoint` / `translate-powerpoint` | servidor | ai | ai | F6 | activa | pptx → pptx | redactado, sin revisar |
| `manuscrito-a-texto` / `handwriting-to-text` | servidor | ai | ai | F6 | activa | jpg, png, webp, tiff, bmp, gif, pdf → docx, txt, md | redactado, sin revisar |
| `imagen-a-excel` / `image-to-excel` | servidor | convert | ai | F3 | activa | jpg, png, webp, tiff, bmp, gif → xlsx, csv, zip | redactado, sin revisar |
| `ticket-a-excel` / `receipt-to-excel` | servidor | ocr | ai | F3 | activa | jpg, png, webp, tiff, bmp, gif → xlsx, csv | redactado, sin revisar |
| `traducir-subtitulos` / `translate-subtitles` | servidor | ai | ai | F5 | activa | srt, vtt, ass, mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr, mp4, mov, mkv, webm, avi → srt, vtt, ass | redactado, sin revisar |
| `resumir-reunion` / `summarize-meeting` | servidor | av | ai | F5 | activa | mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr, mp4, mov, mkv, webm, avi → docx, txt, md | redactado, sin revisar |
| `firmar-pdf` / `sign-pdf` | híbrida | sign | light | F4 | activa | pdf → pdf, zip | redactado, sin revisar |
| `compartir-pdf` / `share-pdf` | servidor | pdf | light | F4 | activa | pdf → pdf | redactado, sin revisar |
| `solicitar-firmas` / `request-signatures` | servidor | pdf | light | F4 | activa | pdf → pdf | redactado, sin revisar |
| `verificar-firmas-pdf` / `verify-pdf-signatures` | servidor | sign | light | F4 | activa | pdf → html, zip | redactado, sin revisar |
| `verificar-firma` / `verify-signature` | servidor | sign | light | F6 | activa | csig, p7m, p7s, xsig, xml, pdf, docx, xlsx, pptx, odt, ods, doc, xls, txt, jpg, png, zip → html, zip | redactado, sin revisar |
| `pdf-a-factura-electronica` / `pdf-to-e-invoice` | servidor | utils | ai | F4 | apagada | pdf → json, pdf, xml | redactado, sin revisar |
| `crear-factura-electronica` / `create-e-invoice` | servidor | utils | light | F4 | apagada | — → pdf, xml | redactado, sin revisar |
| `validar-factura-electronica` / `validate-e-invoice` | servidor | utils | light | F4 | activa | xml, pdf, zip → html, csv, zip | redactado, sin revisar |
| `factura-electronica-a-pdf` / `e-invoice-to-pdf` | servidor | utils | light | F4 | activa | xml → pdf, zip | redactado, sin revisar |
| `facturae-a-pdf` / `facturae-to-pdf` | servidor | utils | light | F4 | activa | xml → pdf, zip | redactado, sin revisar |
| `ubl-a-pdf` / `ubl-to-pdf` | servidor | utils | light | F4 | activa | xml → pdf, zip | redactado, sin revisar |
| `cii-a-pdf` / `cii-to-pdf` | servidor | utils | light | F4 | activa | xml → pdf, zip | redactado, sin revisar |
| `docx-a-odt` / `docx-to-odt` | servidor | utils | light | F6 | activa | docx → odt, zip | redactado, sin revisar |
| `odt-a-docx` / `odt-to-docx` | servidor | utils | light | F6 | activa | odt → docx, zip | redactado, sin revisar |
| `docx-a-markdown` / `docx-to-markdown` | servidor | utils | light | F6 | activa | docx → md, zip | redactado, sin revisar |
| `markdown-a-docx` / `markdown-to-docx` | servidor | utils | light | F6 | activa | md, zip → docx, zip | redactado, sin revisar |
| `docx-a-html` / `docx-to-html` | servidor | utils | light | F6 | activa | docx → html, zip | redactado, sin revisar |
| `html-a-docx` / `html-to-docx` | servidor | utils | light | F6 | activa | html, zip → docx, zip | redactado, sin revisar |
| `xlsx-a-csv` / `xlsx-to-csv` | servidor | utils | light | F6 | activa | xlsx → csv, zip | redactado, sin revisar |
| `csv-a-xlsx` / `csv-to-xlsx` | servidor | utils | light | F6 | activa | csv, txt → xlsx, zip | redactado, sin revisar |
| `ods-a-xlsx` / `ods-to-xlsx` | servidor | office | light | F6 | activa | ods → xlsx, zip | redactado, sin revisar |
| `xlsx-a-ods` / `xlsx-to-ods` | servidor | office | light | F6 | activa | xlsx, xls → ods, zip | redactado, sin revisar |
| `excel-a-json` / `excel-to-json` | servidor | utils | light | F6 | activa | xlsx → json, zip | redactado, sin revisar |
| `arreglar-codificacion-csv` / `fix-csv-encoding` | servidor | utils | light | F6 | activa | csv, txt → csv, zip | redactado, sin revisar |
| `csv-a-json` / `csv-to-json` | servidor | utils | light | F6 | activa | csv, txt → json, zip | redactado, sin revisar |
| `json-a-csv` / `json-to-csv` | servidor | utils | light | F6 | activa | json → csv, zip | redactado, sin revisar |
| `json-a-xml` / `json-to-xml` | servidor | utils | light | F6 | activa | json → xml, zip | redactado, sin revisar |
| `xml-a-json` / `xml-to-json` | servidor | utils | light | F6 | activa | xml → json, zip | redactado, sin revisar |
| `yaml-a-json` / `yaml-to-json` | servidor | utils | light | F6 | activa | yaml → json, zip | redactado, sin revisar |
| `json-a-yaml` / `json-to-yaml` | servidor | utils | light | F6 | activa | json → yaml, zip | redactado, sin revisar |
| `ttf-a-woff2` / `ttf-to-woff2` | servidor | utils | light | F6 | activa | ttf → woff2, zip | redactado, sin revisar |
| `otf-a-woff2` / `otf-to-woff2` | servidor | utils | light | F6 | activa | otf → woff2, zip | redactado, sin revisar |
| `woff2-a-ttf` / `woff2-to-ttf` | servidor | utils | light | F6 | activa | woff2 → ttf, zip | redactado, sin revisar |
| `woff-a-ttf` / `woff-to-ttf` | servidor | utils | light | F6 | activa | woff → ttf, zip | redactado, sin revisar |
| `ttf-a-otf` / `ttf-to-otf` | servidor | utils | light | F6 | activa | ttf → otf, zip | redactado, sin revisar |
| `otf-a-ttf` / `otf-to-ttf` | servidor | utils | light | F6 | activa | otf → ttf, zip | redactado, sin revisar |
| `rar-a-zip` / `rar-to-zip` | servidor | utils | light | F6 | activa | rar → zip | redactado, sin revisar |
| `7z-a-zip` / `7z-to-zip` | servidor | utils | light | F6 | activa | 7z → zip | redactado, sin revisar |
| `tar-a-zip` / `tar-to-zip` | servidor | utils | light | F6 | activa | tar, gz, bz2, xz → zip | redactado, sin revisar |
| `extraer-archivo-online` / `extract-archive-online` | servidor | utils | light | F6 | activa | zip, rar, 7z, tar, gz, bz2, xz → zip | redactado, sin revisar |
| `srt-a-vtt` / `srt-to-vtt` | servidor | utils | light | F6 | activa | srt → vtt, zip | redactado, sin revisar |
| `vtt-a-srt` / `vtt-to-srt` | servidor | utils | light | F6 | activa | vtt → srt, zip | redactado, sin revisar |
| `ass-a-srt` / `ass-to-srt` | servidor | utils | light | F6 | activa | ass → srt, zip | redactado, sin revisar |
| `csig-a-pdf` / `csig-to-pdf` | servidor | utils | light | F6 | activa | csig, p7m, p7s → pdf, zip | redactado, sin revisar |
| `p7m-a-pdf` / `p7m-to-pdf` | servidor | utils | light | F6 | activa | p7m, p7s, csig → pdf, zip | redactado, sin revisar |
| `xsig-a-pdf` / `xsig-to-pdf` | servidor | utils | light | F6 | activa | xsig, xml → pdf, zip | redactado, sin revisar |
| `gpx-a-kml` / `gpx-to-kml` | servidor | utils | light | F6 | activa | gpx → kml, zip | redactado, sin revisar |
| `kml-a-gpx` / `kml-to-gpx` | servidor | utils | light | F6 | activa | kml → gpx, zip | redactado, sin revisar |
| `kmz-a-gpx` / `kmz-to-gpx` | servidor | utils | light | F6 | activa | kmz → gpx, zip | redactado, sin revisar |
| `gpx-a-geojson` / `gpx-to-geojson` | servidor | utils | light | F6 | activa | gpx → geojson, zip | redactado, sin revisar |
| `geojson-a-kml` / `geojson-to-kml` | servidor | utils | light | F6 | activa | geojson, json → kml, zip | redactado, sin revisar |
| `shp-a-geojson` / `shp-to-geojson` | servidor | utils | light | F6 | activa | zip → geojson, zip | redactado, sin revisar |
| `shp-a-kml` / `shp-to-kml` | servidor | utils | light | F6 | activa | zip → kml, zip | redactado, sin revisar |
| `csv-a-kml` / `csv-to-kml` | servidor | utils | light | F6 | activa | csv, txt → kml, zip | redactado, sin revisar |
| `tcx-a-gpx` / `tcx-to-gpx` | servidor | utils | light | F6 | activa | tcx → gpx, zip | redactado, sin revisar |
| `fit-a-gpx` / `fit-to-gpx` | servidor | utils | light | F6 | activa | fit → gpx, zip | redactado, sin revisar |
| `fit-a-csv` / `fit-to-csv` | servidor | utils | light | F6 | activa | fit → csv, zip | redactado, sin revisar |
| `vcf-a-csv` / `vcf-to-csv` | servidor | utils | light | F6 | activa | vcf → csv, zip | redactado, sin revisar |
| `csv-a-vcf` / `csv-to-vcf` | servidor | utils | light | F6 | activa | csv, txt → vcf, zip | redactado, sin revisar |
| `vcf-a-excel` / `vcf-to-excel` | servidor | utils | light | F6 | activa | vcf → xlsx, zip | redactado, sin revisar |
| `ics-a-csv` / `ics-to-csv` | servidor | utils | light | F6 | activa | ics → csv, zip | redactado, sin revisar |
| `csv-a-ics` / `csv-to-ics` | servidor | utils | light | F6 | activa | csv, txt → ics, zip | redactado, sin revisar |
| `ics-a-excel` / `ics-to-excel` | servidor | utils | light | F6 | activa | ics → xlsx, zip | redactado, sin revisar |
| `latex-a-pdf` / `latex-to-pdf` | servidor | utils | light | F6 | activa | tex, zip → pdf, zip | redactado, sin revisar |
| `drawio-a-pdf` / `drawio-to-pdf` | servidor | office | light | F6 | activa | drawio → pdf, zip | redactado, sin revisar |
| `drawio-a-png` / `drawio-to-png` | servidor | office | light | F6 | activa | drawio → png, zip | redactado, sin revisar |

## Desactivadas y por qué (01-1, regla 7)

| Herramienta | Motivo |
| --- | --- |
| `crear-factura` | Apagada por defecto; se enciende con `TOOL_CREAR_FACTURA_ENABLED=true`. Genera facturas: además de INVOICING_ES_ENABLED (Veri*factu y factura electrónica, revisión con un asesor en docs/LEGAL.md) necesita TOOL_CREAR_FACTURA_ENABLED=true. La página avisa de que no sustituye a un sistema de facturación verificable. |
| `crear-factura-electronica` | Apagada por defecto; se enciende con `TOOL_CREAR_FACTURA_ELECTRONICA_ENABLED=true`. Genera facturas electrónicas (RD 238/2026 y Veri*factu): además de INVOICING_ES_ENABLED necesita TOOL_CREAR_FACTURA_ELECTRONICA_ENABLED=true, tras la revisión con un asesor de docs/LEGAL.md. |
| `heic-a-jpg` | Apagada mientras `HEVC_DECODE_ENABLED` no esté a `true`. Decodificar HEVC (HEIC y vídeo H.265) puede necesitar licencia de patentes, también como servicio en la nube (7.2 y 11). Apagado hasta la revisión legal anotada en docs/LEGAL.md; mientras tanto, la página explica cómo exportar a JPEG desde el iPhone o el Mac y lleva noindex. |
| `heic-a-pdf` | Apagada mientras `HEVC_DECODE_ENABLED` no esté a `true`. Decodificar HEVC (HEIC y vídeo H.265) puede necesitar licencia de patentes, también como servicio en la nube (7.2 y 11). Apagado hasta la revisión legal anotada en docs/LEGAL.md; mientras tanto, la página explica cómo exportar a JPEG desde el iPhone o el Mac y lleva noindex. |
| `heic-a-png` | Apagada mientras `HEVC_DECODE_ENABLED` no esté a `true`. Decodificar HEVC (HEIC y vídeo H.265) puede necesitar licencia de patentes, también como servicio en la nube (7.2 y 11). Apagado hasta la revisión legal anotada en docs/LEGAL.md; mientras tanto, la página explica cómo exportar a JPEG desde el iPhone o el Mac y lleva noindex. |
| `pdf-a-factura-electronica` | Apagada por defecto; se enciende con `TOOL_PDF_A_FACTURA_ELECTRONICA_ENABLED=true`. Genera facturas electrónicas desde un PDF: además de INVOICING_ES_ENABLED necesita TOOL_PDF_A_FACTURA_ELECTRONICA_ENABLED=true, tras la revisión con un asesor de docs/LEGAL.md. |
| `pst-a-mbox` | Apagada por defecto; se enciende con `TOOL_PST_A_MBOX_ENABLED=true`. readpst (libpst) está en la imagen y la conversión escrita, pero no hay un PST de prueba con licencia libre ni forma libre de generarlo; se enciende tras probarla con un PST real (DEPLOY-CHECKLIST, F6-J). |
| `pst-a-pdf` | Apagada por defecto; se enciende con `TOOL_PST_A_PDF_ENABLED=true`. Igual que pst-a-mbox: falta probar readpst con un PST real antes de encenderla (DEPLOY-CHECKLIST, F6-J). |
| `udf-a-pdf` | Apagada por defecto; se enciende con `TOOL_UDF_A_PDF_ENABLED=true`. 7.23 la quiere detrás de un interruptor apagado: el formato UDF de UYAP no tiene especificación pública; la conversión sigue su estructura conocida (content.xml con el texto y los trozos con formato) y se enciende tras probarla con documentos reales (DEPLOY-CHECKLIST, F6-M). |

## Fuera de alcance (7.24)

| Qué | Por qué | Cómo sería posible |
| --- | --- | --- |
| XPS, PostScript/EPS y PDF/X | Dependen de Ghostscript o MuPDF (AGPL, 11). | Con licencia comercial de Ghostscript o MuPDF, o tras revisión legal. |
| Laminar modelos 3D a G-code | PrusaSlicer, OrcaSlicer, Bambu Studio y CuraEngine son AGPL (11). | Con un laminador con licencia comercial, o tras revisión legal. |
| Archivos laminados para resina (CTB, PWMX, GOO, SL1 y similares) | La herramienta de referencia, UVtools, es AGPL, y CTB va cifrado. | Con licencia comercial o un SDK del fabricante, tras revisión legal. |
| CAD propietario (SLDPRT, F3D, IPT, CATPart) | Sin SDK comercial no se pueden leer. | Con el SDK comercial de cada fabricante. |
| Quitar DRM, convertir certificados con clave privada y descargar de YouTube o redes sociales | Fuera de alcance por motivos legales y de seguridad (7.24). | No se contempla. |

## Paridad con PDF24 (0.8, 7.23 y 17)

Cada herramienta web de tools.pdf24.org (lista revisada el 2026-11-14, `config/pdf24.yaml`) y su equivalente aquí. La paridad es de funciones: no se copian textos, diseños, plantillas ni marca. Al cerrar F6 no puede quedar ninguna fila «pendiente» sin su fase ni ninguna «sin equivalente» sin explicación (17).

| PDF24 | Equivalente | Estado | Nota |
| --- | --- | --- | --- |
| Merge PDF (`/en/merge-pdf`) | `unir-pdf` | disponible |  |
| Split PDF (`/en/split-pdf`) | `dividir-pdf` | disponible |  |
| Compress PDF (`/en/compress-pdf`) | `comprimir-pdf` | disponible |  |
| Edit PDF (`/en/edit-pdf`) | `editar-pdf` | disponible |  |
| Sign PDF (`/en/sign-pdf`) | `firmar-pdf` | disponible |  |
| Create PDF (`/en/create-pdf`) | `crear-pdf` (página fija) | disponible |  |
| PDF Converter (`/en/pdf-converter`) | `conversor-pdf` (página fija) | disponible |  |
| Images to PDF (`/en/images-to-pdf`) | `imagenes-a-pdf` | disponible |  |
| PDF to Images (`/en/pdf-to-images`) | `pdf-a-imagenes` | disponible |  |
| Write PDF (`/en/write-pdf`) | `escribir-pdf` | disponible |  |
| Create PDF with a camera (`/en/scan-pdf`) | `escaner-pdf` | disponible |  |
| Straighten scans (`/en/straighten-pdf`) | `ocr-pdf` | disponible | Sin página propia en 7: el enderezado está en ocr-pdf (Enderezar, A.5) y en escaner-pdf (corrección de perspectiva, A.1). |
| Webpage to PDF (`/en/webpage-to-pdf`) | `web-a-pdf` | disponible |  |
| Create photo collage (`/en/create-photo-collage`) | `crear-collage` | disponible |  |
| Create card (`/en/create-card`) | `crear-tarjeta` | disponible |  |
| Create PDF form (`/en/create-fillable-pdf-form`) | `crear-formulario-pdf`, `hacer-pdf-rellenable` | disponible |  |
| Create PDF job application (`/en/create-job-application`) | `solicitud-de-empleo-pdf` | disponible |  |
| Generate QR code (`/en/generate-qr-code`) | `generar-codigo-qr` | disponible |  |
| Create invoice (`/en/create-invoice`) | `crear-factura` | disponible, apagada (ver «Desactivadas») |  |
| Create invoice visually (`/en/create-invoice-visually`) | `crear-factura` | disponible, apagada (ver «Desactivadas») | Diseñador visual de crear-factura (7.23). |
| Create electronic invoice (`/en/create-electronic-invoice`) | `crear-factura-electronica` | disponible, apagada (ver «Desactivadas») |  |
| PDF invoice to e-invoice (`/en/pdf-to-e-invoice`) | `pdf-a-factura-electronica` | disponible, apagada (ver «Desactivadas») |  |
| XML e-invoice to PDF (`/en/xml-invoice-to-pdf`) | `factura-electronica-a-pdf` | disponible |  |
| Validate e-invoice (`/en/validate-e-invoice`) | `validar-factura-electronica` | disponible |  |
| Annotate PDF (`/en/annotate-pdf`) | `anotar-pdf` | disponible |  |
| Fill out PDF (`/en/fill-out-pdf`) | `rellenar-pdf` | disponible |  |
| Make PDF fillable (`/en/make-pdf-fillable`) | `hacer-pdf-rellenable` | disponible |  |
| Add watermark (`/en/add-watermark`) | `marca-de-agua-pdf` | disponible |  |
| Add page numbers (`/en/add-page-numbers`) | `numerar-paginas-pdf` | disponible |  |
| PDF Overlay (`/en/overlay-pdf`) | `superponer-pdf` | disponible |  |
| Crop PDF (`/en/crop-pdf`) | `recortar-pdf` | disponible |  |
| Change PDF page size (`/en/change-pdf-page-size`) | `cambiar-tamano-pagina-pdf` | disponible |  |
| Change PDF document information (`/en/change-pdf-doc-info`) | `metadatos-pdf` | disponible |  |
| PDF info (`/en/analyze-pdf`) | `metadatos-pdf` | disponible | Sin página propia en 7: metadatos-pdf muestra la información del documento (A.3). |
| Assemble PDF (`/en/assemble-pdf`) | `montar-pdf` | disponible |  |
| Rearrange PDF pages (`/en/rearrange-pdf-pages`) | `organizar-pdf` | disponible |  |
| Remove PDF pages (`/en/remove-pdf-pages`) | `eliminar-paginas-pdf` | disponible |  |
| Extract PDF pages (`/en/extract-pdf-pages`) | `extraer-paginas-pdf` | disponible |  |
| Rotate PDF pages (`/en/rotate-pdf-pages`) | `girar-pdf` | disponible |  |
| Pages per sheet (`/en/pages-per-sheet`) | `varias-paginas-por-hoja` | disponible |  |
| Print PDF (`/en/print-pdf`) | `imprimir-pdf` | disponible |  |
| Create booklet (`/en/create-pdf-booklet`) | `folleto-pdf` | disponible |  |
| Print PDF as poster (`/en/print-pdf-as-poster`) | — | sin equivalente | No está en el catálogo de 7 ni en 7.23. Pendiente de decisión del propietario (posible herramienta nueva en F6). |
| Halve PDF pages (`/en/halve-pdf-pages`) | `cortar-paginas-por-la-mitad` | disponible |  |
| Bookmark PDF (`/en/bookmark-pdf`) | `marcadores-pdf` | disponible |  |
| Extract PDF images (`/en/extract-images`) | `extraer-imagenes-pdf` | disponible |  |
| Copy from PDF (`/en/copy-from-pdf`) | `copiar-de-pdf` | disponible |  |
| PDF to grayscale (`/en/convert-pdf-to-grayscale`) | `pdf-escala-de-grises` | disponible |  |
| Invert PDF colors (`/en/invert-pdf`) | `pdf-modo-oscuro` | disponible | Modo «Negativo» de pdf-modo-oscuro (A.5). |
| Web optimize PDF (`/en/web-optimize-pdf`) | `optimizar-pdf-web` | disponible |  |
| PDF OCR (`/en/ocr-pdf`) | `ocr-pdf` | disponible |  |
| Repair PDF (`/en/repair-pdf`) | `reparar-pdf` | disponible |  |
| Rasterize PDF (`/en/rasterize-pdf`) | `rasterizar-pdf` | disponible |  |
| Flatten PDF (`/en/flatten-pdf`) | `aplanar-pdf` | disponible |  |
| PDF to PDF/A (`/en/pdf-to-pdfa`) | `pdf-a-pdfa` | disponible |  |
| Protect PDF (`/en/lock-pdf`) | `proteger-pdf` | disponible |  |
| Unlock PDF (`/en/unlock-pdf`) | `desbloquear-pdf` | disponible |  |
| Redact PDF (`/en/redact-pdf`) | `redactar-pdf` | disponible |  |
| Remove PDF metadata (`/en/remove-pdf-metadata`) | `eliminar-metadatos-pdf` | disponible |  |
| Generate password (`/en/generate-password`) | `generar-contrasena` | disponible |  |
| View as PDF (`/en/view-pdf`) | `lector-pdf` | disponible |  |
| Compare PDFs (`/en/compare-pdf`) | `comparar-pdf` | disponible |  |
| Search in PDFs (`/en/search-pdf`) | `buscar-en-pdf` | disponible |  |
| Check PDF/A (`/en/validate-pdfa`) | `validar-pdfa` | disponible |  |
| Verify PDF signatures (`/en/verify-pdf-signatures`) | `verificar-firmas-pdf` | disponible |  |
| Set PDF viewer preferences (`/en/set-pdf-viewer-preferences`) | `preferencias-visor-pdf` | disponible |  |
| Convert to PDF (`/en/convert-to-pdf`) | `convertir-a-pdf` | disponible |  |
| Word to PDF (`/en/word-to-pdf`) | `word-a-pdf` | disponible |  |
| PowerPoint to PDF (`/en/powerpoint-to-pdf`) | `ppt-a-pdf` | disponible |  |
| Excel to PDF (`/en/excel-to-pdf`) | `excel-a-pdf` | disponible |  |
| Publisher to PDF (`/en/publisher-to-pdf`) | `publisher-a-pdf` | disponible |  |
| JPG to PDF (`/en/jpg-to-pdf`) | `jpg-a-pdf` | disponible |  |
| PNG to PDF (`/en/png-to-pdf`) | `png-a-pdf` | disponible |  |
| WEBP to PDF (`/en/webp-to-pdf`) | `webp-a-pdf` | disponible |  |
| HEIC to PDF (`/en/heic-to-pdf`) | `heic-a-pdf` | disponible, apagada (ver «Desactivadas») |  |
| SVG to PDF (`/en/svg-to-pdf`) | `svg-a-pdf` | disponible |  |
| TIFF to PDF (`/en/tiff-to-pdf`) | `tiff-a-pdf` | disponible |  |
| DOCX to PDF (`/en/docx-to-pdf`) | `word-a-pdf` | disponible |  |
| PPTX to PDF (`/en/pptx-to-pdf`) | `ppt-a-pdf` | disponible |  |
| XLSX to PDF (`/en/xlsx-to-pdf`) | `excel-a-pdf` | disponible |  |
| DOC to PDF (`/en/doc-to-pdf`) | `word-a-pdf` | disponible | Formatos antiguos de Office en word-a-pdf (A.8). |
| PPT to PDF (`/en/ppt-to-pdf`) | `ppt-a-pdf` | disponible | Formatos antiguos de Office en ppt-a-pdf (A.8). |
| XLS to PDF (`/en/xls-to-pdf`) | `excel-a-pdf` | disponible | Formatos antiguos de Office en excel-a-pdf (A.8). |
| ODT to PDF (`/en/odt-to-pdf`) | `odt-a-pdf` | disponible |  |
| ODG to PDF (`/en/odg-to-pdf`) | `odg-a-pdf` | disponible |  |
| ODS to PDF (`/en/ods-to-pdf`) | `ods-a-pdf` | disponible |  |
| ODP to PDF (`/en/odp-to-pdf`) | `odp-a-pdf` | disponible |  |
| Text to PDF (`/en/txt-to-pdf`) | `txt-a-pdf` | disponible |  |
| RTF to PDF (`/en/rtf-to-pdf`) | `rtf-a-pdf` | disponible |  |
| EPUB to PDF (`/en/epub-to-pdf`) | `epub-a-pdf` | disponible |  |
| PS to PDF (`/en/ps-to-pdf`) | — | sin equivalente | Fuera de alcance (7.24): PostScript depende de Ghostscript (AGPL). Posible con licencia comercial o tras revisión legal. |
| Markdown to PDF (`/en/markdown-to-pdf`) | `markdown-a-pdf` | disponible |  |
| PUB to PDF (`/en/pub-to-pdf`) | `pub-a-pdf` | disponible |  |
| UDF to PDF (`/en/udf-to-pdf`) | `udf-a-pdf` | disponible, apagada (ver «Desactivadas») |  |
| OFD to PDF (`/en/ofd-to-pdf`) | — | sin equivalente | No está en el catálogo de 7 ni en 7.23 (formato OFD chino). Pendiente de decisión del propietario; sin motor libre conocido revisado contra 11. |
| Convert PDF to ... (`/en/convert-from-pdf`) | `convertir-desde-pdf` | disponible |  |
| PDF to Word (`/en/pdf-to-word`) | `pdf-a-word` | disponible |  |
| PDF to PowerPoint (`/en/pdf-to-powerpoint`) | `pdf-a-ppt` | disponible |  |
| PDF to Excel (`/en/pdf-to-excel`) | `pdf-a-excel` | disponible |  |
| PDF to JPG (`/en/pdf-to-jpg`) | `pdf-a-jpg` | disponible |  |
| PDF to PNG (`/en/pdf-to-png`) | `pdf-a-png` | disponible |  |
| PDF to SVG (`/en/pdf-to-svg`) | `pdf-a-svg` | disponible |  |
| PDF to TIFF (`/en/pdf-to-tiff`) | `pdf-a-tiff` | disponible |  |
| PDF to DOCX (`/en/pdf-to-docx`) | `pdf-a-word` | disponible |  |
| PDF to PPTX (`/en/pdf-to-pptx`) | `pdf-a-ppt` | disponible |  |
| PDF to XLSX (`/en/pdf-to-xlsx`) | `pdf-a-excel` | disponible |  |
| PDF to ODT (`/en/pdf-to-odt`) | `pdf-a-odt` | disponible |  |
| PDF to ODS (`/en/pdf-to-ods`) | `pdf-a-ods` | disponible |  |
| PDF to ODP (`/en/pdf-to-odp`) | `pdf-a-odp` | disponible |  |
| PDF to Text (`/en/pdf-to-txt`) | `pdf-a-txt` | disponible |  |
| PDF to RTF (`/en/pdf-to-rtf`) | `pdf-a-rtf` | disponible |  |
| PDF to EPUB (`/en/pdf-to-epub`) | `pdf-a-epub` | disponible |  |
| PDF to HTML (`/en/pdf-to-html`) | `pdf-a-html` | disponible |  |
| PDF to Markdown (`/en/pdf-to-markdown`) | `pdf-a-markdown` | disponible |  |
| Compress images (`/en/compress-images`) | `comprimir-imagen` | disponible |  |
| HEIC to JPG (`/en/heic-to-jpg`) | `heic-a-jpg` | disponible, apagada (ver «Desactivadas») |  |
| HEIC to PNG (`/en/heic-to-png`) | `heic-a-png` | disponible, apagada (ver «Desactivadas») |  |
| WEBP to JPG (`/en/webp-to-jpg`) | `webp-a-jpg` | disponible |  |
| WEBP to PNG (`/en/webp-to-png`) | `webp-a-png` | disponible |  |
| SVG to JPG (`/en/svg-to-jpg`) | `svg-a-jpg` | disponible |  |
| SVG to PNG (`/en/svg-to-png`) | `svg-a-png` | disponible |  |
| PDF24 Creator (`/en/creator`) | — | sin equivalente | No aplica (7.23): programa de escritorio; el equivalente es la PWA instalable (8.3). |
| PDF Printer (`/en/pdf-printer`) | — | sin equivalente | No aplica (7.23): impresora virtual de escritorio; el equivalente es la PWA instalable (8.3). |
| PDF Reader (`/en/pdf-reader`) | — | sin equivalente | No aplica (7.23): lector de escritorio; el equivalente es la PWA instalable (8.3) con lector-pdf. |

Resumen: 118 disponibles, 0 pendientes de su fase y 6 sin equivalente (con su explicación).

## Mejoras posteriores

- escribir-pdf: sincronizar los borradores y versiones con la cuenta (hoy solo en IndexedDB del navegador, A.1).
- Extensión para Chrome equivalente a la de PDF24 (7.23, «No aplica»).
