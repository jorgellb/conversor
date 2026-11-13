## 2. Stack obligatorio

| Capa | Tecnología |
| --- | --- |
| Web | Next.js (App Router), TypeScript, Tailwind, next-intl; salida `standalone` |
| Procesado en navegador | EmbedPDF (PDFium en WebAssembly), `@cantoo/pdf-lib`, jSquash, zxing-wasm (zxing-cpp), OpenCV.js, three.js, glTF Transform con draco3d, mermaid, `@resvg/resvg-wasm` y diff-match-patch; todo en Web Workers |
| Firma en navegador | PKI.js para abrir .p12/.pfx, WebCrypto para firmar y xadesjs para XAdES |
| Subidas | tusd (servidor tus, MIT) con almacenamiento en disco; Uppy con el plugin `@uppy/tus` en el navegador |
| Descargas | Caddy como servidor de archivos con `forward_auth` hacia la API interna |
| Autenticación | Better Auth en Next.js (correo y contraseña, enlace mágico, Google, plugin de administración) con plugin JWT; la API valida los JWT por JWKS |
| API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| Cola | Celery con Valkey; una cola por grupo de workers, y dos (`light` y `heavy`) en `av` y `office`; Celery beat para tareas periódicas; el estado de los trabajos vive en PostgreSQL, sin backend de resultados |
| Base de datos | PostgreSQL con pgvector |
| Office y HTML a PDF | Gotenberg (LibreOffice y Chromium) en dos instancias: `gotenberg`, sin red, para archivos subidos, y `gotenbergweb`, solo para URL (12.2) |
| Office a formatos que no son PDF | LibreOffice sin interfaz con unoserver (MIT) dentro de `workeroffice`; Gotenberg solo produce PDF |
| Motores PDF | pikepdf, qpdf, pypdfium2, Pillow, OCRmyPDF 17 o posterior (instalado con pip, rasterizador pypdfium2 y `--pdfa-backend internal`, sin Ghostscript) con Tesseract (`tessdata_fast` con todos los idiomas y `tessdata_best` para spa, cat, eus, glg, eng, fra, deu, ita y por), veraPDF, Docling, python-docx, openpyxl, python-pptx, pyHanko, ezdxf (sin el extra `draw`) |
| Audio y vídeo | FFmpeg (compilación LGPL preferente) |
| IA local | faster-whisper (transcripción), Kokoro (voz, pesos Apache-2.0, con fonemas de espeak-ng como proceso externo), fastembed (embeddings) |
| IA remota | OpenRouter, solo modelos gratuitos y solo proveedores que no recogen los datos para entrenar (6.1) |
| Imágenes en servidor | rembg (modelo de 6.4), LibRaw con rawpy, psd-tools, vtracer |
| Utilidades | pandoc (siempre con `--sandbox`), Calibre, libarchive, pysubs2, fontTools, asn1crypto, signxml, defusedxml, GDAL/OGR, gpxpy, fitparse, vobject, icalendar, mail-parser, olefile y compressed-rtf (MSG), draw.io desktop, Tectonic, FluidSynth, charset-normalizer |
| 3D y CAD | lib3mf, trimesh, assimp, manifold3d, fast-simplification, usd-core, shapely, OpenCascade (cadquery/OCP) |
| Programas GPL, solo como proceso externo en servidor | Calibre `ebook-convert`, djvulibre `ddjvu`, poppler `pdftocairo`, pandoc, readpst, MuseScore, OpenSCAD, LibreDWG, draw.io desktop, unpaper, pngquant y espeak-ng |
| Pagos | Stripe Billing y Stripe Tax en modo test |
| Proxy de salida | Smokescreen en dos instancias, `egressai` y `egressweb` (12.2) |
| Antiabuso | Cloudflare Turnstile |
| Analítica | Umami autoalojado (sin cookies), opcional |
| Observabilidad | Logs JSON, OpenTelemetry, Sentry opcional |

---
