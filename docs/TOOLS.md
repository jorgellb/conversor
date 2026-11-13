# Herramientas (7 y 17.1)

Catálogo publicado en esta entrega: F1 completo (lista de lanzamiento de 17.1 y resto de F1) y las herramientas adelantadas de F2 y F5. Generado por `scripts/gen_docs.py` desde `packages/registry/registry.json`. «Indexable» exige herramienta activa, pruebas en verde y contenido propio completo en el idioma (7.22); sin él, la página lleva `noindex`.

| Herramienta (es / en) | Dónde | Grupo | Coste | Fase | Entrada → salida | Contenido propio |
| --- | --- | --- | --- | --- | --- | --- |
| `unir-pdf` / `merge-pdf` | navegador | — | light | F1 | pdf → pdf | redactado, sin revisar |
| `dividir-pdf` / `split-pdf` | navegador | — | light | F1 | pdf → pdf, zip | pendiente |
| `girar-pdf` / `rotate-pdf` | navegador | — | light | F1 | pdf → pdf | pendiente |
| `eliminar-paginas-pdf` / `delete-pdf-pages` | navegador | — | light | F1 | pdf → pdf | pendiente |
| `extraer-paginas-pdf` / `extract-pdf-pages` | navegador | — | light | F1 | pdf → pdf, zip | pendiente |
| `organizar-pdf` / `organize-pdf` | navegador | — | light | F1 | pdf → pdf | pendiente |
| `numerar-paginas-pdf` / `add-page-numbers-pdf` | navegador | — | light | F1 | pdf → pdf | pendiente |
| `marca-de-agua-pdf` / `watermark-pdf` | navegador | — | light | F1 | pdf, png, jpg → pdf | pendiente |
| `editar-pdf` / `edit-pdf` | navegador | — | light | F1 | pdf → pdf | redactado, sin revisar |
| `rellenar-pdf` / `fill-pdf` | navegador | — | light | F1 | pdf → pdf | redactado, sin revisar |
| `recortar-pdf` / `crop-pdf` | navegador | — | light | F1 | pdf → pdf, zip | pendiente |
| `cambiar-tamano-pagina-pdf` / `resize-pdf-pages` | navegador | — | light | F1 | pdf → pdf, zip | pendiente |
| `varias-paginas-por-hoja` / `n-up-pdf` | navegador | — | light | F1 | pdf → pdf, zip | pendiente |
| `folleto-pdf` / `booklet-pdf` | navegador | — | light | F1 | pdf → pdf, zip | pendiente |
| `aplanar-pdf` / `flatten-pdf` | navegador | — | light | F1 | pdf → pdf, zip | pendiente |
| `anotar-pdf` / `annotate-pdf` | navegador | — | light | F1 | pdf → pdf | pendiente |
| `lector-pdf` / `pdf-reader` | híbrida | office | light | F1 | pdf, doc, docx, rtf, odt, txt, xls, xlsx, ods, csv, ppt, pptx, pps, odp, odg, jpg, png, gif, bmp, tiff, webp → pdf | pendiente |
| `cortar-paginas-por-la-mitad` / `split-pages-in-half` | navegador | — | light | F2 | pdf → pdf, zip | pendiente |
| `imprimir-pdf` / `print-pdf` | navegador | — | light | F2 | pdf → pdf, zip | pendiente |
| `montar-pdf` / `assemble-pdf` | navegador | — | light | F2 | pdf, jpg, png, webp, gif, bmp → pdf, zip | pendiente |
| `marcadores-pdf` / `pdf-bookmarks` | navegador | — | light | F2 | pdf → pdf | pendiente |
| `comparar-pdf` / `compare-pdf` | navegador | — | light | F2 | pdf → pdf | pendiente |
| `buscar-en-pdf` / `search-pdf` | navegador | — | light | F2 | pdf → csv | pendiente |
| `redactar-pdf` / `redact-pdf` | navegador | — | light | F1 | pdf → pdf | pendiente |
| `webp-a-pdf` / `webp-to-pdf` | navegador | — | light | F1 | webp → pdf | pendiente |
| `gif-a-pdf` / `gif-to-pdf` | navegador | — | light | F1 | gif → pdf | pendiente |
| `bmp-a-pdf` / `bmp-to-pdf` | navegador | — | light | F1 | bmp → pdf | pendiente |
| `tiff-a-pdf` / `tiff-to-pdf` | servidor | pdf | light | F2 | tiff → pdf | pendiente |
| `imagenes-a-pdf` / `images-to-pdf` | híbrida | pdf | light | F1 | jpg, png, webp, gif, bmp, tiff → pdf | pendiente |
| `jpg-a-pdf` / `jpg-to-pdf` | híbrida | pdf | light | F1 | jpg → pdf | redactado, sin revisar |
| `png-a-pdf` / `png-to-pdf` | híbrida | pdf | light | F1 | png → pdf | pendiente |
| `pdf-a-jpg` / `pdf-to-jpg` | híbrida | pdf | light | F1 | pdf → jpg, zip | redactado, sin revisar |
| `pdf-a-png` / `pdf-to-png` | híbrida | pdf | light | F1 | pdf → png, zip | pendiente |
| `pdf-a-webp` / `pdf-to-webp` | híbrida | pdf | light | F2 | pdf → webp, zip | pendiente |
| `pdf-a-imagenes` / `pdf-to-images` | híbrida | pdf | light | F1 | pdf → zip | pendiente |
| `escaner-pdf` / `pdf-scanner` | navegador | — | light | F2 | jpg, png, webp → pdf | incompleto |
| `generar-contrasena` / `password-generator` | navegador | — | light | F1 | — → pantalla | pendiente |
| `png-a-jpg` / `png-to-jpg` | navegador | — | light | F5 | png → jpg | pendiente |
| `webp-a-jpg` / `webp-to-jpg` | navegador | — | light | F5 | webp → jpg | pendiente |
| `comprimir-imagen` / `compress-image` | navegador | — | light | F5 | jpg, png, webp → jpg, png, webp | pendiente |
| `redimensionar-imagen` / `resize-image` | navegador | — | light | F5 | jpg, png, webp → jpg, png, webp | pendiente |
| `jpg-a-png` / `jpg-to-png` | navegador | — | light | F5 | jpg → png, zip | pendiente |
| `webp-a-png` / `webp-to-png` | navegador | — | light | F5 | webp → png, zip | pendiente |
| `gif-a-png` / `gif-to-png` | navegador | — | light | F5 | gif → png, zip | pendiente |
| `jpg-a-webp` / `jpg-to-webp` | navegador | — | light | F5 | jpg → webp, zip | pendiente |
| `png-a-webp` / `png-to-webp` | navegador | — | light | F5 | png → webp, zip | pendiente |
| `avif-a-jpg` / `avif-to-jpg` | navegador | — | light | F5 | avif → jpg, zip | pendiente |
| `jpg-a-avif` / `jpg-to-avif` | navegador | — | light | F5 | jpg → avif, zip | pendiente |
| `bmp-a-jpg` / `bmp-to-jpg` | navegador | — | light | F5 | bmp → jpg, zip | pendiente |
| `tiff-a-jpg` / `tiff-to-jpg` | navegador | — | light | F5 | tiff → jpg, zip | pendiente |
| `png-a-ico` / `png-to-ico` | navegador | — | light | F5 | png → ico, zip | pendiente |
| `convertir-imagen` / `convert-image` | navegador | — | light | F5 | jpg, png, webp, avif, gif, bmp, tiff, ico, svg → jpg, png, webp, avif, gif, bmp, tiff, ico, zip | pendiente |
| `svg-a-png` / `svg-to-png` | navegador | — | light | F5 | svg → png, zip | pendiente |
| `svg-a-jpg` / `svg-to-jpg` | navegador | — | light | F5 | svg → jpg, zip | pendiente |
| `crear-favicon` / `favicon-generator` | navegador | — | light | F5 | png, jpg, webp, svg → ico, png, zip | pendiente |
| `quitar-metadatos-foto` / `remove-photo-metadata` | navegador | — | light | F5 | jpg, png, webp → jpg, png, webp, zip | pendiente |
| `imagen-a-base64` / `image-to-base64` | navegador | — | light | F5 | jpg, png, webp, gif, svg, avif, bmp, ico → txt, zip | pendiente |
| `leer-codigo-qr` / `qr-code-reader` | navegador | — | light | F5 | jpg, png, webp, gif, bmp, avif, tiff, svg, pdf → csv | pendiente |
| `generar-codigo-qr` / `qr-code-generator` | navegador | — | light | F5 | — → png, svg, pdf | pendiente |
| `crear-collage` / `collage-maker` | navegador | — | light | F5 | jpg, png, webp, gif, bmp, avif → pdf, jpg, png, zip | incompleto |
| `comprimir-pdf` / `compress-pdf` | servidor | pdf | light | F1 | pdf → pdf, zip | redactado, sin revisar |
| `proteger-pdf` / `protect-pdf` | servidor | pdf | light | F2 | pdf → pdf, zip | pendiente |
| `desbloquear-pdf` / `unlock-pdf` | servidor | pdf | light | F2 | pdf → pdf, zip | pendiente |
| `reparar-pdf` / `repair-pdf` | servidor | pdf | light | F2 | pdf → pdf, zip | pendiente |
| `optimizar-pdf-web` / `optimize-pdf-for-web` | servidor | pdf | light | F2 | pdf → pdf, zip | pendiente |
| `pdf-escala-de-grises` / `grayscale-pdf` | servidor | pdf | light | F2 | pdf → pdf, zip | pendiente |
| `pdf-modo-oscuro` / `dark-mode-pdf` | servidor | pdf | light | F2 | pdf → pdf, zip | pendiente |
| `extraer-imagenes-pdf` / `extract-images-from-pdf` | servidor | pdf | light | F2 | pdf → zip | pendiente |
| `metadatos-pdf` / `pdf-metadata` | servidor | pdf | light | F2 | pdf → pdf, zip | pendiente |
| `eliminar-metadatos-pdf` / `remove-pdf-metadata` | servidor | pdf | light | F2 | pdf → pdf, zip | pendiente |
| `rasterizar-pdf` / `rasterize-pdf` | servidor | pdf | light | F2 | pdf → pdf, zip | pendiente |
| `preferencias-visor-pdf` / `pdf-viewer-preferences` | servidor | pdf | light | F2 | pdf → pdf, zip | pendiente |
| `pdf-a-tiff` / `pdf-to-tiff` | servidor | pdf | light | F2 | pdf → tiff, zip | pendiente |
| `pdf-a-svg` / `pdf-to-svg` | servidor | pdf | light | F2 | pdf → svg, zip | pendiente |
| `pdf-a-txt` / `pdf-to-txt` | servidor | pdf | light | F2 | pdf → txt, zip | pendiente |
| `convertir-a-pdf` / `convert-to-pdf` | servidor | office | light | F1 | doc, docx, rtf, odt, txt, xls, xlsx, ods, csv, ppt, pptx, pps, odp, odg, jpg, png, gif, bmp, tiff, webp, html → pdf, zip | pendiente |
| `word-a-pdf` / `word-to-pdf` | servidor | office | light | F1 | doc, docx → pdf, zip | redactado, sin revisar |
| `excel-a-pdf` / `excel-to-pdf` | servidor | office | light | F1 | xls, xlsx → pdf, zip | pendiente |
| `ppt-a-pdf` / `powerpoint-to-pdf` | servidor | office | light | F1 | ppt, pptx, pps → pdf, zip | pendiente |
| `odt-a-pdf` / `odt-to-pdf` | servidor | office | light | F1 | odt → pdf, zip | pendiente |
| `ods-a-pdf` / `ods-to-pdf` | servidor | office | light | F1 | ods → pdf, zip | pendiente |
| `odp-a-pdf` / `odp-to-pdf` | servidor | office | light | F1 | odp → pdf, zip | pendiente |
| `odg-a-pdf` / `odg-to-pdf` | servidor | office | light | F1 | odg → pdf, zip | pendiente |
| `rtf-a-pdf` / `rtf-to-pdf` | servidor | office | light | F1 | rtf → pdf, zip | pendiente |
| `txt-a-pdf` / `txt-to-pdf` | servidor | office | light | F1 | txt → pdf, zip | pendiente |
| `html-a-pdf` / `html-to-pdf` | servidor | office | light | F1 | html, zip → pdf, zip | pendiente |
| `markdown-a-pdf` / `markdown-to-pdf` | servidor | office | light | F1 | md → pdf, zip | pendiente |
| `superponer-pdf` / `overlay-pdf` | servidor | office | light | F2 | pdf, doc, docx, rtf, odt, txt, xls, xlsx, ods, csv, ppt, pptx, pps, odp, odg, jpg, png, gif, bmp, tiff, webp → pdf, zip | pendiente |
| `svg-a-pdf` / `svg-to-pdf` | servidor | office | light | F2 | svg → pdf, zip | pendiente |
| `pages-a-pdf` / `pages-to-pdf` | servidor | office | light | F2 | pages → pdf, zip | pendiente |
| `keynote-a-pdf` / `keynote-to-pdf` | servidor | office | light | F2 | key → pdf, zip | pendiente |
| `numbers-a-pdf` / `numbers-to-pdf` | servidor | office | light | F2 | numbers → pdf, zip | pendiente |
| `visio-a-pdf` / `visio-to-pdf` | servidor | office | light | F2 | vsd, vsdx → pdf, zip | pendiente |
| `publisher-a-pdf` / `publisher-to-pdf` | servidor | office | light | F2 | pub → pdf, zip | pendiente |
| `pub-a-pdf` / `pub-to-pdf` | servidor | office | light | F2 | pub → pdf, zip | pendiente |
| `epub-a-pdf` / `epub-to-pdf` | servidor | office | light | F2 | epub → pdf, zip | pendiente |
| `mobi-a-pdf` / `mobi-to-pdf` | servidor | office | light | F2 | mobi → pdf, zip | pendiente |
| `azw3-a-pdf` / `azw3-to-pdf` | servidor | office | light | F2 | azw3 → pdf, zip | pendiente |
| `fb2-a-pdf` / `fb2-to-pdf` | servidor | office | light | F2 | fb2 → pdf, zip | pendiente |
| `solicitud-de-empleo-pdf` / `job-application-pdf` | servidor | office | light | F2 | pdf, doc, docx, rtf, odt, txt, xls, xlsx, ods, csv, ppt, pptx, pps, odp, odg, jpg, png, gif, bmp, tiff, webp → pdf, zip | pendiente |
| `web-a-pdf` / `web-to-pdf` | servidor | office | light | F1 | — → pdf | pendiente |
| `csv-a-pdf` / `csv-to-pdf` | servidor | office | light | F1 | csv → pdf, zip | pendiente |
| `ocr-pdf` / `ocr-pdf` | servidor | ocr | heavy | F2 | pdf → pdf, txt, zip | pendiente |
| `pdf-a-pdfa` / `pdf-to-pdfa` | servidor | ocr | heavy | F2 | pdf → pdf, html, zip | pendiente |
| `validar-pdfa` / `validate-pdfa` | servidor | ocr | light | F2 | pdf → html, zip | pendiente |
| `pdf-a-word` / `pdf-to-word` | servidor | convert | heavy | F2 | pdf → docx, zip | redactado, sin revisar |
| `pdf-a-odt` / `pdf-to-odt` | servidor | convert | heavy | F2 | pdf → odt, zip | pendiente |
| `pdf-a-rtf` / `pdf-to-rtf` | servidor | convert | heavy | F2 | pdf → rtf, zip | pendiente |
| `pdf-a-excel` / `pdf-to-excel` | servidor | convert | heavy | F2 | pdf → xlsx, zip | pendiente |
| `pdf-a-ods` / `pdf-to-ods` | servidor | convert | heavy | F2 | pdf → ods, zip | pendiente |
| `pdf-a-ppt` / `pdf-to-ppt` | servidor | convert | heavy | F2 | pdf → pptx, zip | pendiente |
| `pdf-a-odp` / `pdf-to-odp` | servidor | convert | heavy | F2 | pdf → odp, zip | pendiente |
| `pdf-a-markdown` / `pdf-to-markdown` | servidor | convert | heavy | F2 | pdf → md, zip | pendiente |
| `pdf-a-html` / `pdf-to-html` | servidor | convert | heavy | F2 | pdf → html, zip | pendiente |
| `pdf-a-epub` / `pdf-to-epub` | servidor | convert | heavy | F2 | pdf → epub, zip | pendiente |
| `pdf-a-csv` / `pdf-to-csv` | servidor | convert | heavy | F2 | pdf → csv, zip | pendiente |
| `pdf-a-json` / `pdf-to-json` | servidor | convert | heavy | F2 | pdf → json, zip | pendiente |
| `copiar-de-pdf` / `copy-from-pdf` | híbrida | convert | heavy | F2 | pdf → json, md, xlsx | incompleto |
| `convertir-desde-pdf` / `convert-from-pdf` | servidor | convert | light | F2 | pdf → csv, docx, epub, html, jpg, json, md, odp, ods, odt, pdf, png, pptx, rtf, svg, tiff, txt, webp, xlsx, zip | pendiente |
| `ogg-a-mp3` / `ogg-to-mp3` | servidor | av | light | F5 | ogg, opus, oga → mp3, zip | pendiente |
| `opus-a-mp3` / `opus-to-mp3` | servidor | av | light | F5 | opus, ogg → mp3, zip | pendiente |
| `m4a-a-mp3` / `m4a-to-mp3` | servidor | av | light | F5 | m4a → mp3, zip | pendiente |
| `mp4-a-mp3` / `mp4-to-mp3` | servidor | av | light | F5 | mp4, m4a → mp3, zip | pendiente |
| `aac-a-mp3` / `aac-to-mp3` | servidor | av | light | F5 | aac, m4a → mp3, zip | pendiente |
| `flac-a-mp3` / `flac-to-mp3` | servidor | av | light | F5 | flac → mp3, zip | pendiente |
| `wav-a-mp3` / `wav-to-mp3` | servidor | av | light | F5 | wav → mp3, zip | pendiente |
| `wma-a-mp3` / `wma-to-mp3` | servidor | av | light | F5 | wma → mp3, zip | pendiente |
| `amr-a-mp3` / `amr-to-mp3` | servidor | av | light | F5 | amr → mp3, zip | pendiente |
| `aiff-a-mp3` / `aiff-to-mp3` | servidor | av | light | F5 | aiff, aif → mp3, zip | pendiente |
| `ogg-a-wav` / `ogg-to-wav` | servidor | av | light | F5 | ogg, opus, oga → wav, zip | pendiente |
| `mp3-a-wav` / `mp3-to-wav` | servidor | av | light | F5 | mp3 → wav, zip | pendiente |
| `cortar-audio` / `cut-audio` | servidor | av | light | F5 | mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr → mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr, zip | pendiente |
| `unir-audios` / `merge-audio` | servidor | av | light | F5 | mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr → mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr | pendiente |
| `normalizar-volumen` / `normalize-audio` | servidor | av | light | F5 | mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr → mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr, zip | pendiente |
| `cambiar-velocidad-audio` / `change-audio-speed` | servidor | av | light | F5 | mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr → mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr, zip | pendiente |
| `transcribir-audio` / `transcribe-audio` | servidor | av | heavy | F5 | mp3, wav, ogg, opus, m4a, aac, flac, aiff, wma, amr, mp4, webm → txt, docx, srt, zip | pendiente |
| `video-a-subtitulos` / `video-to-subtitles` | servidor | av | heavy | F5 | mp4, mov, mkv, webm, avi → srt, vtt, zip | pendiente |
| `heic-a-pdf` / `heic-to-pdf` | servidor | media | light | F2 | heic → pdf, zip | pendiente |
| `cbz-a-pdf` / `cbz-to-pdf` | servidor | media | light | F2 | cbz → pdf, zip | pendiente |
| `cbr-a-pdf` / `cbr-to-pdf` | servidor | media | light | F2 | cbr → pdf, zip | pendiente |
| `djvu-a-pdf` / `djvu-to-pdf` | servidor | media | light | F2 | djvu → pdf, zip | pendiente |
| `eml-a-pdf` / `eml-to-pdf` | servidor | media | light | F2 | eml → pdf, zip | pendiente |
| `msg-a-pdf` / `msg-to-pdf` | servidor | media | light | F2 | msg → pdf, zip | pendiente |
| `dxf-a-pdf` / `dxf-to-pdf` | servidor | media | light | F2 | dxf → pdf, zip | pendiente |
| `heic-a-jpg` / `heic-to-jpg` | servidor | media | light | F5 | heic → jpg, zip | pendiente |
| `heic-a-png` / `heic-to-png` | servidor | media | light | F5 | heic → png, zip | pendiente |
| `raw-a-jpg` / `raw-to-jpg` | servidor | media | light | F5 | cr2, nef, arw, dng → jpg, zip | pendiente |
| `psd-a-png` / `psd-to-png` | servidor | media | light | F5 | psd, psb → png, zip | pendiente |
| `png-a-svg` / `png-to-svg` | servidor | media | light | F5 | png → svg, zip | pendiente |
| `jpg-a-svg` / `jpg-to-svg` | servidor | media | light | F5 | jpg → svg, zip | pendiente |
| `quitar-fondo` / `remove-background` | servidor | media | heavy | F5 | jpg, png, webp → png, webp, jpg, zip | pendiente |
| `resumir-pdf` / `summarize-pdf` | servidor | ai | ai | F3 | pdf → docx, txt, md | pendiente |
| `chat-pdf` / `chat-with-pdf` | servidor | ai | ai | F3 | pdf → pantalla | pendiente |
| `generador-de-preguntas` / `question-generator` | servidor | ai | ai | F3 | pdf → docx, txt | pendiente |
| `pdf-a-fichas` / `pdf-to-flashcards` | servidor | ai | ai | F3 | pdf → txt, csv, docx | pendiente |
| `pdf-a-presentacion` / `pdf-to-presentation` | servidor | ai | ai | F3 | pdf → pptx | pendiente |
| `traducir-pdf` / `translate-pdf` | servidor | ai | ai | F3 | pdf → docx, pdf | pendiente |

La lista de lanzamiento (17.1) está completa. El resto del catálogo (secciones 7.3 a 7.23) llega en su fase; la comparación con PDF24 se cierra en F6 (17.1).
