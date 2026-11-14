# Herramientas (7, 7.24 y 17)

Catálogo publicado en esta entrega: 163 herramientas (F1 43, F2 60, F3 10, F5 50). Fases cerradas: F1, F2 y F5 sin vídeo; en curso: F3. El orden y los lotes que faltan están en `docs/PLAN.md` y `docs/GOAL.md`. Generado por `scripts/gen_docs.py` desde `packages/registry/registry.json`, `config/tools-notes.yaml` y `config/pdf24.yaml`: no lo edites a mano.

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
| `csv-a-pdf` / `csv-to-pdf` | servidor | office | light | F1 | activa | csv → pdf, zip | redactado, sin revisar |
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
| `imagen-a-excel` / `image-to-excel` | servidor | convert | ai | F3 | activa | jpg, png, webp, tiff, bmp, gif → xlsx, csv, zip | redactado, sin revisar |
| `ticket-a-excel` / `receipt-to-excel` | servidor | ocr | ai | F3 | activa | jpg, png, webp, tiff, bmp, gif → xlsx, csv | redactado, sin revisar |
| `traducir-subtitulos` / `translate-subtitles` | servidor | ai | ai | F5 | activa | srt, vtt, ass, mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr, mp4, mov, mkv, webm, avi → srt, vtt, ass | redactado, sin revisar |
| `resumir-reunion` / `summarize-meeting` | servidor | av | ai | F5 | activa | mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr, mp4, mov, mkv, webm, avi → docx, txt, md | redactado, sin revisar |

## Desactivadas y por qué (01-1, regla 7)

| Herramienta | Motivo |
| --- | --- |
| `heic-a-jpg` | Apagada mientras `HEVC_DECODE_ENABLED` no esté a `true`. Decodificar HEVC (HEIC y vídeo H.265) puede necesitar licencia de patentes, también como servicio en la nube (7.2 y 11). Apagado hasta la revisión legal anotada en docs/LEGAL.md; mientras tanto, la página explica cómo exportar a JPEG desde el iPhone o el Mac y lleva noindex. |
| `heic-a-pdf` | Apagada mientras `HEVC_DECODE_ENABLED` no esté a `true`. Decodificar HEVC (HEIC y vídeo H.265) puede necesitar licencia de patentes, también como servicio en la nube (7.2 y 11). Apagado hasta la revisión legal anotada en docs/LEGAL.md; mientras tanto, la página explica cómo exportar a JPEG desde el iPhone o el Mac y lleva noindex. |
| `heic-a-png` | Apagada mientras `HEVC_DECODE_ENABLED` no esté a `true`. Decodificar HEVC (HEIC y vídeo H.265) puede necesitar licencia de patentes, también como servicio en la nube (7.2 y 11). Apagado hasta la revisión legal anotada en docs/LEGAL.md; mientras tanto, la página explica cómo exportar a JPEG desde el iPhone o el Mac y lleva noindex. |

Además, cuando lleguen a su fase: `crear-factura`, `crear-factura-electronica`, `pdf-a-factura-electronica` (mismo motivo que su flag temático).

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
| Sign PDF (`/en/sign-pdf`) | `firmar-pdf` | pendiente (F4) |  |
| Create PDF (`/en/create-pdf`) | `crear-pdf` (página fija) | disponible |  |
| PDF Converter (`/en/pdf-converter`) | `conversor-pdf` (página fija) | disponible |  |
| Images to PDF (`/en/images-to-pdf`) | `imagenes-a-pdf` | disponible |  |
| PDF to Images (`/en/pdf-to-images`) | `pdf-a-imagenes` | disponible |  |
| Write PDF (`/en/write-pdf`) | `escribir-pdf` | pendiente (F6) |  |
| Create PDF with a camera (`/en/scan-pdf`) | `escaner-pdf` | disponible |  |
| Straighten scans (`/en/straighten-pdf`) | `ocr-pdf` | disponible | Sin página propia en 7: el enderezado está en ocr-pdf (Enderezar, A.5) y en escaner-pdf (corrección de perspectiva, A.1). |
| Webpage to PDF (`/en/webpage-to-pdf`) | `web-a-pdf` | disponible |  |
| Create photo collage (`/en/create-photo-collage`) | `crear-collage` | disponible |  |
| Create card (`/en/create-card`) | `crear-tarjeta` | pendiente (F6) |  |
| Create PDF form (`/en/create-fillable-pdf-form`) | `crear-formulario-pdf`, `hacer-pdf-rellenable` | pendiente (F4) |  |
| Create PDF job application (`/en/create-job-application`) | `solicitud-de-empleo-pdf` | disponible |  |
| Generate QR code (`/en/generate-qr-code`) | `generar-codigo-qr` | disponible |  |
| Create invoice (`/en/create-invoice`) | `crear-factura` | pendiente (F4) |  |
| Create invoice visually (`/en/create-invoice-visually`) | `crear-factura` | pendiente (F4) | Diseñador visual de crear-factura (7.23). |
| Create electronic invoice (`/en/create-electronic-invoice`) | `crear-factura-electronica` | pendiente (F4) |  |
| PDF invoice to e-invoice (`/en/pdf-to-e-invoice`) | `pdf-a-factura-electronica` | pendiente (F4) |  |
| XML e-invoice to PDF (`/en/xml-invoice-to-pdf`) | `factura-electronica-a-pdf` | pendiente (F6) |  |
| Validate e-invoice (`/en/validate-e-invoice`) | `validar-factura-electronica` | pendiente (F4) |  |
| Annotate PDF (`/en/annotate-pdf`) | `anotar-pdf` | disponible |  |
| Fill out PDF (`/en/fill-out-pdf`) | `rellenar-pdf` | disponible |  |
| Make PDF fillable (`/en/make-pdf-fillable`) | `hacer-pdf-rellenable` | pendiente (F4) |  |
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
| Verify PDF signatures (`/en/verify-pdf-signatures`) | `verificar-firmas-pdf` | pendiente (F4) |  |
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
| UDF to PDF (`/en/udf-to-pdf`) | `udf-a-pdf` | pendiente (F6) |  |
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

Resumen: 105 disponibles, 13 pendientes de su fase y 6 sin equivalente (con su explicación).

## Mejoras posteriores

- escribir-pdf: sincronizar los borradores y versiones con la cuenta (hoy solo en IndexedDB del navegador, A.1).
- Extensión para Chrome equivalente a la de PDF24 (7.23, «No aplica»).
