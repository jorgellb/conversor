# Super prompt: {{PRODUCTO}} — herramientas PDF y conversor de archivos en un VPS con Coolify

Eres el ingeniero principal de este proyecto. Implementa, no solo expliques: crea el monorepo completo con código, configuración, pruebas, ficheros Docker Compose para Coolify y documentación. Trabaja de forma autónoma por fases; pide confirmación solo ante decisiones irreversibles o que cuesten dinero.

---

## 0. Datos del proyecto y decisiones cerradas

Sustituye estos valores antes de empezar. Si al recibir este documento alguno sigue entre llaves, usa los valores de prueba de la sección 0.1, continúa y no publiques nada:

| Variable | Valor |
| --- | --- |
| `{{PRODUCTO}}` | Nombre comercial |
| `{{DOMINIO}}` | Dominio principal, por ejemplo `ejemplo.com` |
| `{{EMAIL_ADMIN}}` | Correo del primer administrador |

Dominios:

| Uso | Dominio |
| --- | --- |
| Web | `{{DOMINIO}}` |
| API pública | `api.{{DOMINIO}}` |
| Subidas reanudables (tus) | `upload.{{DOMINIO}}` |
| Descargas firmadas | `files.{{DOMINIO}}` |

Decisiones ya tomadas (no las cambies sin anotarlo en `docs/DECISIONS.md`):

1. **Un solo VPS** con Coolify v4. Todo el stack corre en ese servidor.
2. **Almacenamiento propio en disco del VPS. No hay S3** de ningún tipo (ni SeaweedFS, ni MinIO, ni servicios externos). Los archivos viven en un volumen local compartido por los servicios.
3. **IA solo con modelos gratuitos de OpenRouter** (`:free`), con un presupuesto global de 1.000 peticiones al día y 20 por minuto. Lo que se pueda hacer en local (embeddings, transcripción, voz, OCR) se hace en local para no gastar peticiones.
4. **Código cerrado**: prohibido enlazar librerías AGPL (sección 11).
5. Idiomas: español de España (por defecto) e inglés.
6. Pagos con Stripe en modo test, detrás de una interfaz `PaymentProvider`.
7. Delante de todo, Cloudflare (proxy, WAF y Turnstile).
8. **Paridad funcional con PDF24:**
   - Cada herramienta web de tools.pdf24.org tiene aquí un equivalente con, como mínimo, sus opciones (sección 7.23 y Anexo A).
   - La paridad es de funciones: no copies textos, diseños, plantillas ni marca de PDF24.

### 0.1 Lo que aporta el propietario y cuándo

No puedes crear cuentas, comprar nada ni aceptar condiciones de terceros. Trabaja con dobles locales hasta que el propietario aporte cada entrada y no bloquees el cierre técnico de una fase por su ausencia (sección 1.3).

| Entrada | La necesitas para | Mientras no exista |
| --- | --- | --- |
| Valores de `{{PRODUCTO}}`, `{{DOMINIO}}` y `{{EMAIL_ADMIN}}` | Textos, dominios y correo | `Producto Demo`, `ejemplo.test` y `admin@ejemplo.test`; no publiques nada |
| VPS con acceso SSH, Coolify instalado y un token de la API de Coolify | Cierre operativo de cada fase | Solo cierre técnico, en local y en la CI |
| Cuenta de Cloudflare con el dominio, y claves de Turnstile | Despliegue público | Claves de prueba oficiales de Turnstile en `.env.example` |
| Cuenta de Stripe en modo test con productos y precios | Pagos de prueba reales | `FakePaymentProvider` en desarrollo y en la CI |
| Cuenta de OpenRouter con 10 $ comprados y la privacidad configurada (6.1) | IA real | Proveedor falso determinista (6.6) |
| Servidor SMTP con SPF, DKIM y DMARC en el dominio de `MAIL_FROM` | Correo real | Mailpit en `docker-compose.yml` |
| Credenciales de Google OAuth, Google Picker y Dropbox | Acceso con Google, Drive y Dropbox | Funciones apagadas por flag |
| Repositorio remoto para restic (por ejemplo, SFTP en otro servidor) y su contraseña | Copia fuera del servidor | Copia local; el cierre operativo de F1 la exige |
| Certificado del sello de la plataforma y TSA de producción | Sello en producción | Certificado autofirmado y TSA de pruebas |
| Revisiones legales anotadas en `docs/LEGAL.md` | Activar `INVOICING_ES_ENABLED`, `HEVC_DECODE_ENABLED`, `VIDEO_H264_ENCODING_ENABLED` y las herramientas de IA en producción | Flags apagados |

Pide todas las entradas que falten en un único mensaje al empezar, y otra vez al cerrar cada fase. No las pidas una a una.

---

## 1. Cómo trabajar

1. Antes de programar:
   - divide este documento en ficheros de `docs/spec/` (uno por sección y uno por apartado del Anexo A) sin cambiar su texto, con un índice en `docs/spec/INDEX.md`; al empezar cada fase, relee las secciones que usa;
   - crea `docs/PLAN.md` con las fases de la sección 17 desglosadas en tareas, y `docs/PROGRESS.md`, que actualizarás al cerrar cada tarea.
2. Comprueba en internet la versión estable actual de cada dependencia e imagen Docker y fíjala; nunca uses `latest`. No te fíes de la memoria para APIs que cambian (Coolify, OpenRouter, tusd, Better Auth, Next.js, Gotenberg, OCRmyPDF).
3. Cada fase tiene dos cierres:
   - **Cierre técnico**, que haces tú y comprueba la CI:
     - pasan todas las pruebas de la fase y de las anteriores;
     - `docker compose up` arranca en local solo con `.env.example`, con los dobles de la sección 0.1;
     - `docker-compose.coolify.yml` pasa `docker compose config` y un arranque de humo en la CI con los mismos healthchecks;
     - Lighthouse CI (perfil móvil, mediana de 3 ejecuciones) da 90 o más en rendimiento y accesibilidad en la portada y en las páginas de herramienta de la fase.
   - **Cierre operativo**, que requiere las entradas de 0.1:
     - con token de la API de Coolify, despliega y comprueba que todos los healthchecks están en verde y que `/readyz` responde 200 en tres comprobaciones separadas por 10 minutos;
     - sin token, deja los pasos y las comprobaciones para el propietario en `docs/DEPLOY-CHECKLIST.md`, anota el cierre operativo como pendiente en `docs/PROGRESS.md` y sigue con la fase siguiente.
4. Haz commit al cerrar cada tarea, con mensajes descriptivos.
5. Si algo no está decidido aquí, elige la opción más simple coherente con este documento y anótala con su motivo en `docs/DECISIONS.md`.
6. Antes de añadir una dependencia, comprueba su licencia contra la sección 11, incluidas sus dependencias transitivas y sus extras (`paquete[extra]`), y regístrala en `docs/LICENSES.md`.
7. Nada de TODO, stubs ni funciones simuladas en el código entregado. Los dobles de 0.1 y los proveedores falsos solo existen con `APP_ENV=development` o en las pruebas.
   - Una herramienta está lista cuando pasa sus pruebas de 16.5 y 16.6 y su página tiene el contenido de 8.2.
   - Si no lo consigue, queda desactivada con su flag y explicas el motivo en `docs/TOOLS.md`.
   - Una fase puede cerrarse con herramientas desactivadas si no superan el 10 % de las de la fase y ninguna está en la lista de lanzamiento (17.1).
8. Prueba cada herramienta con archivos reales en `tests/fixtures`. Necesitas, como mínimo:
   - **PDF:** de texto, escaneado, con tablas, con formulario, cifrado, dañado, de 300 páginas, firmado digitalmente, PDF/A, con marcadores y en color con gráficos vectoriales.
   - **Ofimática y libros:** DOCX, XLSX, PPTX, ODT, RTF, EPUB, MOBI, CBZ y DjVu.
   - **Imagen:** HEIC, TIFF, SVG, AVIF, GIF animado, RAW DNG y PSD.
   - **Correo:** EML, MSG, MBOX y PST.
   - **Audio y vídeo:** OGG Vorbis, OGG Opus (nota de voz), M4A, FLAC, WMA, AMR, MP4, MOV y MKV.
   - **Subtítulos y fuentes:** SRT, ASS, TTF y OTF.
   - **Comprimidos:** RAR y 7Z.
   - **Firmados y facturas:** .csig, .p7m, .xsig, Facturae, UBL, XRechnung (CII y UBL), Peppol BIS y Factur-X/ZUGFeRD.
   - **GPS:** GPX, KML, KMZ, FIT y SHP.
   - **Contactos y calendario:** VCF e ICS.
   - **Diagramas y música:** draw.io, Mermaid, LaTeX, MIDI y MusicXML.
   - **3D:** STL ASCII y binario, OBJ con MTL, 3MF, AMF, PLY, OFF, GLB, FBX, DAE, 3DS, WRL, X3D y USDZ.
   - **CAD:** STEP, IGES, SCAD, DXF y DWG.
   - **Impresión 3D:** G-code, bgcode y .gcode.3mf.
   - **Origen de las muestras:**
     - prefiere generarlas con scripts de `scripts/fixtures/`, con cualquier herramienta aunque su licencia no permita incluirla en el producto (por ejemplo, PrusaSlicer para bgcode o LibreOffice para DOCX), porque las muestras no se distribuyen con el producto;
     - si descargas una, su licencia debe permitir guardarla en el repositorio privado; anota su origen en `tests/fixtures/SOURCES.md`;
     - si no hay forma de conseguir una muestra válida de un formato, la herramienta queda desactivada y lo anotas en `docs/TOOLS.md`.
9. Al cerrar cada fase, revisa tu propio trabajo como lo haría un revisor externo exigente (seguridad, licencias, accesibilidad, rendimiento, uso de disco y del presupuesto de IA) y corrige lo que encuentres.

---

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

## 3. Infraestructura objetivo: un VPS con Coolify

### 3.1 Servidor

- Ubuntu Server LTS actual, Docker instalado por el script oficial de Coolify y Coolify v4, con la versión estable fijada, en el mismo servidor.
- Tamaño (estimación, no medida; ajústalo con las pruebas de carga de 16.1 y la tabla de 5.4):
  - De F1 a F4: 8 vCPU dedicadas, 32 GB de RAM y 400 GB de NVMe, con las concurrencias de la columna de 8 vCPU.
  - Catálogo completo (F5 a F7): 16 vCPU dedicadas, 64 GB de RAM y 1 TB de NVMe (o 400 GB de sistema más un volumen de 600 GB para archivos).
  - Con 16 GB de RAM, desactiva por flag Docling, el modelo `medium` de Whisper, el vídeo y los grupos `mesh` y `cad`.
  - Evita las vCPU compartidas: OCR, vídeo y Docling usan CPU de forma sostenida.
- Swap de 8 GB con `vm.swappiness=10`. Cada contenedor con `mem_limit` lleva `memswap_limit` igual, para que un worker que se pasa de memoria muera en lugar de paginar.
- `unattended-upgrades` activado.
- Cortafuegos:
  - Docker publica los puertos de los contenedores con reglas propias que UFW no filtra. Usa el cortafuegos del proveedor; si no existe, aplica las reglas en la cadena `DOCKER-USER` (o con ufw-docker) y documenta el método en `docs/DEPLOY.md`.
  - 22 solo desde las IP de administración.
  - 80 y 443 solo desde los rangos IP que publica Cloudflare, actualizados por un cron semanal del host, para que nadie se salte el WAF atacando la IP del servidor.
  - 8000, 6001 y 6002 (panel, tiempo real y terminal de Coolify) cerrados al público en cuanto el panel funcione con su dominio a través del proxy, protegido con Cloudflare Access.
- Si el proveedor lo permite, monta un volumen de bloques dedicado en `/srv/{{PRODUCTO}}` para archivos y copias. Así un disco lleno no tumba el sistema.
- Opcional: gVisor (`runsc`) instalado en el host para los workers que procesan archivos (secciones 12.1 y 13.1).

### 3.2 Servicios del stack

| Servicio | Imagen | Dominio | Función |
| --- | --- | --- | --- |
| `web` | propia (Next.js) | `{{DOMINIO}}` | Web, SEO, autenticación, panel de usuario y de administración |
| `api` | propia (FastAPI) | `api.{{DOMINIO}}` | API pública |
| `apiint` | misma imagen que `api` | ninguno (solo red interna) | Endpoints internos: ganchos de tusd, autorización de descargas, operaciones |
| `upload` | tusd oficial | `upload.{{DOMINIO}}` | Subidas reanudables a disco |
| `files` | Caddy oficial | `files.{{DOMINIO}}` | Descargas firmadas desde disco |
| `beat` | misma imagen que `api` | — | Tareas periódicas |
| `workerpdf`, `workerocr`, `workeroffice`, `workerconvert`, `workermedia`, `workerai`, `workersign`, `workerav`, `workerutils`, `workermesh`, `workercad` | propias por grupo | — | Workers de Celery |
| `gotenberg` | Gotenberg oficial | — | LibreOffice y Chromium para archivos subidos, sin ninguna salida de red |
| `gotenbergweb` | Gotenberg oficial | — | Chromium para web-a-pdf y captura-web; sale solo por `egressweb` y nunca recibe archivos de usuarios |
| `postgres` | PostgreSQL con pgvector | — | Base de datos |
| `valkey` | Valkey oficial | — | Broker de Celery, límites y cachés |
| `egressai` | Smokescreen oficial (`ghcr.io/stripe/smokescreen`) | — | Salida de `workerai`, solo hacia OpenRouter |
| `egressweb` | Smokescreen oficial | — | Salida de `gotenbergweb`, `workeroffice` y `workersign` hacia IP públicas |
| `umami` | Umami oficial (opcional) | `stats.{{DOMINIO}}` | Analítica sin cookies |
| `migrate` | misma imagen que `api` | — | Migraciones Alembic, una sola ejecución |
| `migrateauth` | misma imagen que `web` | — | Migraciones de Better Auth, una sola ejecución, antes de `migrate` |
| `mailpit` | Mailpit oficial | — | Correo de desarrollo; solo en `docker-compose.yml` |

### 3.3 Construcción de imágenes

- Las imágenes pesadas (LibreOffice, Docling con Torch solo CPU, OpenCascade, FFmpeg, Whisper) no se construyen en el VPS.
- GitHub Actions construye cada imagen, la etiqueta con la versión y el SHA, y la publica en GitHub Container Registry.
  - Solo se construyen las imágenes cuyo contexto ha cambiado (filtros por ruta) y con caché de capas.
  - El plan gratuito de GitHub incluye 2.000 minutos al mes para repositorios privados; si el consumo previsto lo supera, es una decisión con coste: pídela al propietario.
- Dos ficheros Compose:
  - `docker-compose.yml`: desarrollo local, con `build:`.
  - `docker-compose.coolify.yml`: producción, solo con `image:` y etiquetas fijas.
- En Coolify, el recurso Docker Compose apunta a `docker-compose.coolify.yml`. Las imágenes son siempre privadas: contienen el código cerrado y programas GPL (Calibre, pandoc y otros) cuya distribución pública obligaría a ofrecer su código fuente. En el VPS, inicia sesión en el registro con un token de solo lectura (`read:packages`) y documenta el paso en `docs/DEPLOY.md`.
- Imagen base común de Python con las dependencias compartidas, y una imagen por grupo de workers encima, para reducir disco y tiempo de compilación.
- Modelos (Whisper, Kokoro, embeddings, rembg, Docling) descargados en tiempo de compilación dentro de la imagen, nunca en tiempo de ejecución, porque los workers no tienen salida a internet.

---

## 4. Almacenamiento propio (sin S3)

### 4.1 Estructura en disco

Un volumen compartido montado en `/srv/files` en `api`, `apiint`, `upload`, `files`, `beat` y todos los workers. Por defecto es un volumen con nombre; documenta en `docs/DEPLOY.md` cómo cambiarlo a un *bind mount* sobre el disco dedicado (`/srv/{{PRODUCTO}}/files`).

```text
/srv/files/
├── uploads/          # tusd: archivos subidos y sus .info
├── jobs/<job_id>/
│   ├── in/           # entradas del trabajo (movidas desde uploads con rename atómico)
│   ├── work/         # temporal del worker (no usar tmpfs para archivos grandes)
│   └── out/          # resultados
└── shares/<share_id>/ # copias para compartir-pdf
```

Copias de seguridad en un segundo volumen, `/srv/backups`, idealmente en otro disco.

### 4.2 Subidas con tusd

- El navegador sube con Uppy y `@uppy/tus` a `https://upload.{{DOMINIO}}/files/`, en trozos de 50 MB. Cloudflare limita el cuerpo de cada petición a 100 MB en los planes gratuito y Pro, y los trozos lo evitan.
- Opciones de tusd (comprueba los nombres en la versión fijada):
  - almacenamiento en `/srv/files/uploads`;
  - `-base-path /files/`;
  - `-behind-proxy`;
  - CORS solo para `https://{{DOMINIO}}`, permitiendo la cabecera `Authorization`;
  - `-max-size` igual al máximo del plan Pro;
  - ganchos HTTP (`-hooks-http`) hacia `http://apiint:8001/tusd-hooks`, reenviando la cabecera `Authorization` (`-hooks-http-forward-headers`), con los eventos `pre-create`, `pre-finish` y `post-terminate` (`-hooks-enabled-events`).
- Gancho `pre-create` (bloqueante). Rechaza con `RejectUpload` y un mensaje claro en el idioma del usuario si falla alguna de estas comprobaciones:
  1. Valida el JWT del usuario o el token anónimo firmado.
  2. Rechaza las subidas con `SizeIsDeferred: true`: sin tamaño declarado no se puede aplicar el límite del plan.
  3. Comprueba el tamaño declarado contra el plan.
  4. Comprueba la extensión declarada contra las herramientas habilitadas.
  5. Comprueba la cuota diaria y el número de archivos por tarea (9.3).
  6. Reserva espacio en disco (4.5); si no hay, rechaza.
- Gancho `pre-finish` (bloqueante: tusd no confirma el último trozo hasta que responde):
  1. Calcula sha256 leyendo el archivo por bloques.
  2. Detecta el tipo real por bytes.
  3. Registra la fila en `uploads` con propietario, caducidad y estado `ready`.
  4. Si el tipo real no es un formato admitido, la fila queda en `rejected`; `POST /v1/jobs` responde `UNSUPPORTED_FORMAT` y la limpieza de 4.5 borra el archivo.
- `POST /v1/jobs` solo acepta subidas en estado `ready` del mismo propietario.
- Gancho `post-terminate`: borra la fila y libera la reserva de disco; la limpieza borra el archivo si tusd no lo ha hecho.

### 4.3 Trabajos sobre disco

- `POST /v1/jobs` mueve (rename en el mismo sistema de archivos) las subidas a `jobs/<job_id>/in/` y encola.
- El worker lee de `in/`, usa `work/` y escribe en `out/`. Antes de registrar un resultado comprueba con `lstat` que es un archivo regular y no un enlace simbólico.
- Nombres de archivo de salida saneados: solo `[a-zA-Z0-9._-]`, sin rutas, como máximo 120 caracteres. El nombre original solo se guarda en base de datos para mostrarlo.

### 4.4 Descargas firmadas con Caddy

- URL: `https://files.{{DOMINIO}}/d/<job_id>/<archivo>?t=<token>`.
- El token es un HMAC-SHA256 con `FILE_TOKEN_SECRET` sobre `job_id`, `archivo`, caducidad y propietario. Caduca en 15 minutos; la interfaz pide URL nuevas a `GET /v1/jobs/{id}` cuando caducan.
- Caddy:
  - hace `forward_auth` a `http://apiint:8001/files/authorize`, que lee la URL original de `X-Forwarded-Uri` y valida el token sin leer el archivo;
  - si recibe 2xx, sirve desde `/srv/files/jobs` con `file_server`;
  - nunca lista directorios;
  - envía `Content-Disposition: attachment`, `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; sandbox` y `Cross-Origin-Resource-Policy: same-site`;
  - responde a CORS solo para `https://{{DOMINIO}}`, para que el visor y las herramientas puedan leer resultados;
  - admite peticiones de rango para audio y vídeo.
- Compartir usa la ruta `/s/<share_id>/<archivo>` sobre `/srv/files/shares`. El token se guarda solo como hash en `shares`; `files/authorize` lo comprueba en la base de datos para poder revocarlo, y caduca como máximo a los `SHARE_MAX_DAYS` días.
- Las condiciones del CDN de Cloudflare en los planes Free, Pro y Business no permiten servir vídeo ni una proporción desproporcionada de archivos grandes. El panel de administración muestra el volumen diario servido por `files` por tipo de archivo, y `docs/DEPLOY.md` describe el plan B de la sección «Decisiones» de la revisión.

### 4.5 Disco: limpieza y protección

- **Celery beat cada 5 minutos:** borra `jobs/<job_id>` vencidos (1 h anónimos, 24 h registrados), subidas sin terminar de más de 24 h, subidas en estado `rejected` y comparticiones vencidas.
- **Celery beat una vez al día:** busca huérfanos en disco sin fila en base de datos y al revés.
- **Reserva de disco:** `pre-create` reserva en Valkey el tamaño declarado multiplicado por `DISK_RESERVE_FACTOR` (3: entrada, temporal y salida), y la reserva se libera cuando el trabajo termina o caduca. Una subida se acepta solo si el espacio libre menos las reservas vivas sigue por encima de `DISK_MIN_FREE_GB`.
- **Guarda de disco:** si el uso del volumen supera `DISK_MAX_USAGE_PERCENT` (85 %) o el espacio libre baja de `DISK_MIN_FREE_GB`:
  - `pre-create` rechaza nuevas subidas con «Servicio saturado, inténtalo en unos minutos»;
  - las herramientas de navegador siguen funcionando;
  - se avisa por correo a `ADMIN_EMAILS`, como máximo una vez por hora.
- **Guarda de colas:** cada cola tiene `QUEUE_MAX_WAIT_SECONDS_<GRUPO>`. Si la espera estimada (trabajos en cola por duración media de los últimos 30 minutos, dividido por la concurrencia) la supera, `POST /v1/jobs` rechaza a anónimos y gratuitos con `QUEUE_FULL`; la interfaz muestra la espera y ofrece la versión de navegador si existe. A Pro solo se le rechaza al doble del umbral.
- `/readyz` informa del uso de disco, de las reservas y de la espera por cola, y el panel de administración lo muestra.

### 4.6 Copias de seguridad

- **Copia de la base de datos:** tarea programada de Coolify cada 6 horas en el contenedor `apiint`, con tiempo máximo de 3.600 s (el valor por defecto de Coolify es 300 s). Ejecuta `python -m app.ops.backup`:
  - `pg_dump` en formato personalizado a `/srv/backups/postgres/`, con un `postgresql-client` de la misma versión mayor que el servidor (instálalo desde el repositorio de PGDG; `/readyz` comprueba la versión);
  - retención local de `BACKUP_RETENTION_DAYS` días.
- **Copia fuera del servidor**, obligatoria para el cierre operativo de F1: con `BACKUP_RESTIC_REPOSITORY` definido (por ejemplo, SFTP a otro servidor propio), restic envía cada copia y aplica `forget --prune` con 7 diarias, 4 semanales y 6 mensuales. `apiint` sale a ese destino por la red `edge` (12.2). Sin esta copia, perder el VPS es perder la base de datos.
- **Qué más se copia:**
  - el directorio del token PKCS#11 del sello (volumen `softhsm`);
  - un volcado cifrado de las variables del recurso en Coolify y del `.env` de Coolify (`/data/coolify/source/.env`): sin `AUTH_SECRET` no se pueden descifrar las claves JWKS que Better Auth guarda cifradas en la base de datos;
  - la base de datos de Coolify (`pg_dump` del contenedor `coolify-db`) con un cron del host descrito en `docs/OPERATIONS.md`.
- Los archivos de usuario no se copian: son temporales por diseño.
- `python -m app.ops.restore <archivo>` restaura y se prueba en la CI con una base vacía. `docs/OPERATIONS.md` describe la restauración completa en un VPS nuevo, con un objetivo de menos de 4 horas, y un simulacro trimestral.
- Si la copia falla dos veces seguidas, se avisa a `ADMIN_EMAILS`.

### 4.7 Límite conocido

Con disco local no se puede repartir el procesamiento en varios servidores sin almacenamiento compartido. Documenta en `docs/DEPLOY.md` que crecer a un segundo servidor exigiría NFS u otro almacenamiento compartido. Queda fuera de alcance.

---

## 5. Arquitectura y flujo de trabajos

### 5.1 Dónde se procesa

- **Herramientas «cliente»:** se procesan en el navegador y nunca suben el archivo. Si el archivo supera `CLIENT_MAX_MB` (100 MB) o el navegador se queda sin memoria, la herramienta lo dice y sugiere una alternativa; no tienen versión de servidor salvo que sean híbridas.
- **Herramientas «híbridas»:** solo las marcadas `hybrid` en el registro: unir-pdf con Office o TIFF, pdf-a-jpg y pdf-a-png con archivos grandes, imagenes-a-pdf con TIFF o lotes grandes, copiar-de-pdf, comparar-pdf con archivos de más de `CLIENT_MAX_MB`, lector-pdf con archivos que no son PDF y girar-pdf con autoorientación. Su parte de servidor es la que indica su línea del catálogo.
- **Herramientas «servidor»:**
  1. El navegador obtiene identidad: JWT si hay sesión, o `POST /v1/session/anon` con Turnstile, que devuelve un token anónimo firmado válido 24 horas.
  2. Sube por tus a `upload.{{DOMINIO}}` y recibe los `upload_id`.
  3. `POST /v1/jobs` con `{tool, upload_ids, options}`. La API valida plan, cuota y opciones, mueve las entradas y encola en la cola del grupo.
  4. `GET /v1/jobs/{id}/events` (Server-Sent Events, latido cada 15 s porque Cloudflare corta conexiones inactivas) informa del progreso.
  5. `GET /v1/jobs/{id}` devuelve las salidas con URLs firmadas de `files.{{DOMINIO}}`.
- La API autentica solo por la cabecera `Authorization` (JWT o token anónimo), nunca por cookies; así no hay superficie de CSRF.

### 5.2 Registro de herramientas

Cada herramienta es un módulo Python (y, si es de cliente o híbrida, un módulo TypeScript) inscrito en un registro central con:

| Campo | Ejemplo |
| --- | --- |
| `slug_es`, `slug_en` | `comprimir-pdf`, `compress-pdf` |
| `category` | `pdf`, `office`, `image`, `audio`, `video`, `ai`, `data`, `sign`, `invoice` o `3d` |
| `where` | `client`, `server` o `hybrid` (5.1) |
| `worker_group` | `pdf`, `ocr`, `office`, `convert`, `media`, `ai`, `sign`, `av`, `utils`, `mesh`, `cad` |
| `cost_class` | `light`, `heavy` o `ai` (9.3) |
| `inputs` / `outputs` | tipos MIME y extensiones |
| `options_schema` | modelo Pydantic con valores por defecto |
| `limits` | por plan, sobrescriben los generales |
| `ai_requests_estimate` | función que estima peticiones de IA antes de encolar |
| `phase` | F1 a F7 |
| `flag` | `TOOL_<SLUG>_ENABLED` y fila en `feature_flags` |
| `indexable` | si tiene página propia indexable |

- El registro separa la especificación (slugs, opciones, límites y fase) de la implementación: `packages/tools/<grupo>/<slug>/spec.py` no importa motores y `impl.py` solo se importa en los workers. La API y la web cargan solo especificaciones, y una prueba falla si importar el registro carga torch, Docling, OpenCascade o FFmpeg.
- `scripts/export_registry.py` genera `packages/registry/registry.json` con el JSON Schema de cada `options_schema`; la web lo importa al compilar y genera sus tipos con json-schema-to-typescript. La CI falla si el JSON no está al día.
- Precedencia de flags:
  1. `TOOL_<SLUG>_ENABLED=false` en el entorno apaga la herramienta siempre (interruptor de emergencia);
  2. si la variable no está definida, manda la fila de `feature_flags`;
  3. sin fila, la herramienta está activa desde su fase;
  4. los flags temáticos (`HEVC_DECODE_ENABLED`, `INVOICING_ES_ENABLED`, `VIDEO_H264_ENCODING_ENABLED`, `GDRIVE_ENABLED`, `DROPBOX_ENABLED`) se aplican además y solo pueden apagar.
- Una herramienta apagada no tiene página indexable: su URL lleva `noindex` y una explicación, y sale del sitemap (7.22).

El registro alimenta la API (`/v1/tools`), la generación estática de páginas, el sitemap y los conversores universales.

### 5.3 Reglas de los trabajos

- **Idempotencia** por `(propietario, sha256 de entradas, herramienta, opciones sin secretos)`: si el resultado sigue en disco, se devuelve sin reprocesar y la subida duplicada se borra. El índice único de `idempotency_key` es parcial: solo cubre trabajos `queued`, `running` o `succeeded` no caducados.
- **Estados:** `queued`, `running`, `succeeded`, `failed`, `cancelled`, `expired`.
- **Errores** con código estable y mensaje traducido. La lista completa está en `docs/ERRORS.md` e incluye `FILE_TOO_LARGE`, `UNSUPPORTED_FORMAT`, `PASSWORD_REQUIRED`, `INVALID_OPTIONS`, `AI_CONSENT_REQUIRED`, `AI_BUDGET_EXHAUSTED`, `AI_UNAVAILABLE`, `QUEUE_FULL`, `DISK_FULL`, `TIMEOUT` y `WORKER_LOST`.
- **Secretos de los trabajos** (contraseñas de PDF y similares): la API los cifra con AES-GCM y `JOB_SECRETS_KEY`, viajan cifrados en los argumentos de la tarea y el worker los descifra en memoria. Nunca se guardan en claro en Valkey, en la base de datos, en logs ni en la clave de idempotencia.
- **Celery:**
  - `time_limit` y `soft_time_limit` por herramienta;
  - `broker_transport_options.visibility_timeout` mayor que el `time_limit` más largo más 10 minutos: Valkey reentrega las tareas sin confirmar cuando vence ese plazo, y con trabajos de vídeo o transcripción de horas se ejecutarían dos veces;
  - `acks_late`, `prefetch_multiplier=1` y `task_reject_on_worker_lost=False`;
  - cada trabajo en curso actualiza `jobs.heartbeat_at` cada 30 s; beat reencola con un intento nuevo los trabajos `running` sin latido desde hace 3 minutos;
  - cada tarea lleva su número de intento y el worker la descarta si `jobs.attempts` ya es mayor;
  - al tercer intento fallido (por ejemplo, porque el contenedor murió por memoria) el trabajo pasa a `failed` con `WORKER_LOST` y no se reencola;
  - reintentos solo en errores transitorios;
  - prioridad para Pro con las prioridades de Celery sobre Valkey (`priority_steps` y `queue_order_strategy="priority"`);
  - sin backend de resultados (`task_ignore_result`): el estado vive en `jobs`;
  - parada en caliente con `stop_grace_period` igual al `time_limit` del grupo, con un máximo de 10 minutos.

### 5.4 Grupos de workers y concurrencia por defecto (8 y 16 vCPU)

| Grupo | Motores principales | Concurrencia (8 / 16 vCPU) | Hilos por trabajo | `mem_limit` (8 / 16 vCPU) |
| --- | --- | --- | --- | --- |
| `pdf` | pikepdf, qpdf, pypdfium2, Pillow | 3 / 6 | 1 | 3 / 6 GB |
| `ocr` | OCRmyPDF, Tesseract, veraPDF | 1 / 2 | 2 | 3 / 6 GB |
| `office` | LibreOffice con unoserver, Calibre, cliente de Gotenberg | 2 / 3 (`light` 1 y `heavy` 1 en 8 vCPU) | 1 | 3 / 4 GB |
| `convert` | Docling (backend pypdfium2) | 1 / 1 | 2 | 5 / 8 GB |
| `media` | imágenes, libros, correo, CAD 2D | 2 / 3 | 1 | 3 / 4 GB |
| `ai` | OpenRouter, fastembed | 4 / 6 | 1 | 2 / 3 GB |
| `sign` | pyHanko | 1 / 1 | 1 | 1 / 1 GB |
| `av` | FFmpeg, faster-whisper, Kokoro | 2 / 3 (`light` 1 y `heavy` 1 en 8 vCPU) | 2 | 3 / 6 GB |
| `utils` | formatos de F6, KoSIT en modo servicio | 2 / 2 | 1 | 3 / 4 GB |
| `mesh` | mallas 3D y G-code | 1 / 2 | 1 | 4 / 6 GB |
| `cad` | OpenCascade, OpenSCAD, LibreDWG | 1 / 1 | 1 | 4 / 6 GB |
| `gotenberg` | LibreOffice y Chromium | 1 instancia | sin cambio | 3 / 4 GB |
| `gotenbergweb` | Chromium | 1 instancia | sin cambio | 1,5 / 2 GB |

- Todo configurable con `CONCURRENCY_<GRUPO>` y `THREADS_<GRUPO>`.
- Fija los hilos de cada motor a `THREADS_<GRUPO>`: OCRmyPDF `--jobs`, `OMP_THREAD_LIMIT`, `OMP_NUM_THREADS`, `torch.set_num_threads`, FFmpeg `-threads` y faster-whisper `cpu_threads`. Por defecto, la mayoría de estos motores usan todos los núcleos, y una veintena de procesos a la vez saturarían el servidor.
- `cpus` de cada contenedor = concurrencia × hilos. `cpu_shares` mayor para `web`, `api`, `apiint`, `upload`, `files` y `workerpdf`, para que las páginas y las herramientas rápidas respondan durante los picos.
- `postgres` lleva `mem_limit` de 2,5 / 4 GB. La suma de los `mem_limit` puede superar la RAM en un 15 % como máximo (unos 36 GB en 32 GB hasta F4 y unos 72 GB en 64 GB con el catálogo completo). `oom_score_adj` de −500 para `postgres`, `valkey`, `web`, `api`, `apiint`, `upload` y `files`, y de +500 para los workers: si se agota la memoria del host, el núcleo mata antes un worker (su trabajo vuelve a la cola, 5.3) que la base de datos.
- `av` y `office` tienen dos colas con procesos separados, `light` (notas de voz, conversiones cortas) y `heavy` (transcripciones, vídeo, hojas de cálculo enormes), para que un trabajo de horas no bloquee los de segundos.
- KoSIT Validator corre como servicio HTTP dentro de `workerutils` (modo daemon), para no arrancar la JVM en cada factura.
- Kokoro va en `av`, que es intensivo en CPU, y no en `ai`, que queda para trabajos de entrada y salida con OpenRouter.

---

## 6. IA con modelos gratuitos de OpenRouter

### 6.1 Condiciones de OpenRouter que condicionan el diseño

| Condición (comprobada el 31/10/2026; vuelve a comprobarla al empezar F3) | Consecuencia en el sistema |
| --- | --- |
| Modelos gratuitos: 20 peticiones por minuto; 50 al día si la cuenta ha comprado menos de 10 créditos en total y 1.000 al día si ha comprado al menos 10 | Comprar una vez 10 $ es una decisión con coste: pídela (0.1). Limitador propio por debajo de esas cifras |
| El límite es global de la cuenta: más claves o más cuentas no suman | Una sola clave |
| Con saldo negativo puede devolver 402, también en modelos gratuitos | Mantener saldo positivo y avisar en el panel |
| `GET /api/v1/key` devuelve `free_model_daily_requests` (`used`, `limit` y `remaining`) del día UTC | Es la fuente de verdad del consumo diario; el limitador propio se reconcilia con ella |
| La documentación no dice si los intentos fallidos cuentan para el límite diario | Contar cada intento y cada reintento contra el presupuesto |
| Los modelos gratuitos rotan sin aviso | Descubrimiento automático y lista de reserva |
| La política de datos depende del proveedor de cada modelo: unos entrenan con los textos y otros no. La cuenta tiene ajustes separados para modelos gratuitos y de pago, y `provider.data_collection: "deny"` en cada petición limita el enrutado a proveedores que no recogen datos | Cuenta configurada para no permitir proveedores que entrenan ni que publican; todas las peticiones llevan `data_collection: "deny"`; si no queda ningún modelo válido para una herramienta, se desactiva sola (6.2) |

Documenta en `docs/OPERATIONS.md` los pasos de configuración de la cuenta de OpenRouter: compra única, ajustes de privacidad que no permiten entrenar ni publicar, y clave.

### 6.2 Descubrimiento de modelos

- Al arrancar y cada `LLM_MODELS_REFRESH_HOURS` horas, `GET {OPENROUTER_BASE_URL}/models`. Guarda los modelos con precio 0 en entrada y en salida, lleven o no el sufijo `:free`.
- Guarda en `llm_models`:
  - `context_length` y `max_completion_tokens`;
  - si admite `response_format` o salidas estructuradas;
  - si admite imagen de entrada;
  - fecha de última vez visto.
- Orden de preferencia:
  1. `LLM_PREFERRED_MODELS` (lista ordenada; puede estar vacía);
  2. los descubiertos, ordenados por tasa de éxito propia de los últimos 7 días y después por contexto.
- Cada petición envía `models` con hasta 3 candidatos que cumplan los requisitos de la tarea (contexto, tokens de salida, JSON y visión) y `provider: {"data_collection": "deny"}`. OpenRouter pasa al siguiente si uno falla o está saturado; la respuesta indica el modelo usado y se registra.
- Último recurso: el enrutador `openrouter/free` (`LLM_FALLBACK_ROUTER`), también con `data_collection: "deny"`.
- Un modelo que falla porque ningún proveedor cumple `data_collection: "deny"` queda desactivado 24 horas (`disabled_until`).
- Si ningún modelo cumple los requisitos de una herramienta, esa herramienta se muestra «no disponible temporalmente» (`AI_UNAVAILABLE`) sin gastar peticiones.
- El panel de administración muestra la lista, permite desactivar un modelo y fijar preferencias.

### 6.3 Presupuesto y limitador

Limitador global en Valkey, atómico (script Lua):

| Parámetro | Valor por defecto |
| --- | --- |
| `AI_RPM_LIMIT` | 18 por minuto (ventana deslizante) |
| `AI_DAILY_BUDGET` | 950 al día (margen de 50 sobre el límite) |
| `AI_PRO_RESERVE` | 400 peticiones diarias reservadas para Pro |
| `AI_CHAT_RPM_SHARE` | 0,5: el chat usa como máximo la mitad del límite por minuto |
| `AI_TASK_MAX_REQUESTS` | 20 peticiones por tarea |
| `AI_BUDGET_RESET_TZ` | `UTC` (reinicio a las 00:00 UTC, como el contador de OpenRouter) |

- **Antes de encolar**, la herramienta estima sus peticiones (`ai_requests_estimate`). La API las reserva contra estos límites:
  1. la cuota diaria del usuario y el máximo por tarea (9.3);
  2. el presupuesto global (sin tocar la reserva Pro si el usuario no es Pro);
  3. el límite por minuto.
- **Si no hay presupuesto**, error `AI_BUDGET_EXHAUSTED` con la hora de reinicio en hora de Madrid.
- **Las reservas no usadas** se devuelven al terminar el trabajo.
- **Cada petición real**, incluidos los fallos y los reintentos, cuenta y se registra en `ai_requests`: modelo, tokens, latencia y estado, nunca el contenido.
- **Errores 429 o 5xx de OpenRouter:** espera exponencial respetando `Retry-After` y como máximo 2 reintentos, que cuentan contra el presupuesto.
- **Reconciliación:** cada 10 minutos, `GET {OPENROUTER_BASE_URL}/key`. Si `free_model_daily_requests.used` es mayor que el contador propio, el contador sube a ese valor; si `remaining` baja de 20, solo Pro puede usar IA. El saldo se muestra en el panel de administración.
- **Tamaño de bloque:** el texto de cada petición se trocea según el contexto y el `max_completion_tokens` del modelo elegido, porque una traducción ocupa a la salida tanto como a la entrada. Nunca por un número fijo de caracteres.
- Coste estimado por herramienta:

| Herramienta | Peticiones |
| --- | --- |
| resumir-pdf | 1 si cabe en el contexto; si no, 1 por bloque + 1 final |
| chat-pdf | 1 por mensaje |
| generador-de-preguntas, pdf-a-fichas, ticket-a-excel | 1 |
| pdf-a-presentacion | 2 |
| traducir-pdf, traducir-word/excel/powerpoint | 1 por bloque, con bloques que quepan en la salida máxima del modelo |
| manuscrito-a-texto | 1 por página (máximo 10) |
| resumir-reunion, traducir-subtitulos | 1 por bloque de transcripción |
| transcribir-audio, video-a-subtitulos, pdf-a-audio, imagen-a-texto | 0 (local) |

- Si una tarea necesitaría más de `AI_TASK_MAX_REQUESTS`, la API lo dice antes de encolar y ofrece procesar un rango de páginas.
- Las herramientas de IA se anuncian como «beta, sujeta a disponibilidad diaria», y su página muestra cuántas peticiones quedan hoy (`GET /v1/ai/budget`).

### 6.4 Componentes locales (no gastan peticiones)

- **Embeddings:** fastembed con `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (Apache-2.0, 384 dimensiones), que fastembed admite de serie; `intfloat/multilingual-e5-small` no está en su lista de modelos. Vectores en pgvector con la dimensión del modelo.
- **Transcripción:** faster-whisper en CPU, modelo `small` con `int8` por defecto y `medium` opcional.
- **Voz:** Kokoro (pesos Apache-2.0) con voces en español e inglés.
  - Los fonemas se obtienen ejecutando `espeak-ng` como proceso externo (GPL) y se pasan a Kokoro. No instales `misaki[en]` ni `phonemizer-fork`: son GPL y se cargarían dentro del proceso de Python.
  - Kokoro no publica versión desde abril de 2025; fija la versión y anota el riesgo de mantenimiento en `docs/DECISIONS.md`.
  - La calidad en español la valida el propietario con una escucha antes de activar pdf-a-audio en español.
  - Texto troceado por frases y salida MP3 con FFmpeg.
- **Quitar fondo:** rembg con `REMBG_MODEL=isnet-general-use` o `u2net`, tras verificar la licencia de sus pesos. Nunca `bria-rmbg`, que es el modelo por defecto de rembg y cuyo uso comercial exige un acuerdo de pago con BRIA.
- **OCR:** Tesseract.
- **Extracción de texto:** pypdfium2; si el PDF es escaneado, OCR en `workerocr`; estructura y tablas con Docling solo en `workerconvert`. El resultado se guarda en `document_texts` y `workerai` lo reutiliza sin cargar Docling.

### 6.5 Diseño para gastar pocas peticiones

- Una sola llamada por tarea siempre que el documento quepa en el contexto del modelo elegido; si no, por bloques grandes, no por página.
- Chat: el documento entero en contexto si cabe; si no, recuperación local con pgvector y 6 a 8 fragmentos.
- Salida JSON:
  - con `response_format` y esquema si el modelo lo admite;
  - si no, instrucciones estrictas, parseo tolerante y como máximo 1 petición de reparación.
- Caché por `(propietario, sha256, herramienta, opciones, idioma)` con la misma caducidad que los archivos del usuario. Repetir una tarea no gasta. No se comparte entre usuarios: hacerlo revelaría si otra persona ha procesado el mismo documento.
- Límite de páginas por tarea de IA según el plan (sección 9.3).

### 6.6 Privacidad y consentimiento

- Antes de la primera tarea de IA de cada sesión, la interfaz muestra este aviso con casilla obligatoria:
  > «Para esta herramienta, el texto de tu documento se envía a un proveedor de IA externo a través de OpenRouter, que puede estar fuera de la Unión Europea. Solo usamos proveedores que declaran no entrenar con los datos, pero pueden conservarlos un tiempo según su política. No la uses con documentos confidenciales ni con datos personales de terceros.»
- Sin consentimiento, la API devuelve 400 (`AI_CONSENT_REQUIRED`). `AI_REQUIRE_CONSENT` está a `true` y no puede desactivarse en producción. Cada consentimiento se guarda en `ai_consents` con la fecha y la versión del texto.
- Nunca se envía a OpenRouter contenido de las herramientas de firma, verificación de firmas, contactos, calendario, correo o certificados. Esas herramientas no tienen opción de IA.
- `provider.data_collection: "deny"` va en todas las peticiones y no se puede cambiar en producción.
- La política de privacidad lista a OpenRouter y a sus proveedores como destinatarios, explica la posible transferencia fuera de la UE y enlaza a sus políticas. Añade en `docs/LEGAL.md` que debe revisarlo un especialista en protección de datos, junto con una evaluación de impacto (EIPD) del tratamiento con IA.
- Interfaz `LLMProvider` para cambiar en el futuro a modelos de pago con retención cero sin tocar las herramientas.
- Proveedor falso determinista cuando `OPENROUTER_API_KEY` está vacío y `APP_ENV=development`.

---

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

## 8. Frontend y SEO

### 8.1 Páginas

- `/es` y `/en`:
  - portada con buscador de herramientas;
  - favoritos (estrella en cada herramienta), usadas recientemente y usadas con frecuencia, guardados en el navegador y, con sesión iniciada, en la cuenta;
  - categorías (PDF, Office, Imagen, Audio, Vídeo, IA, Datos, 3D, Firma, Facturas);
  - herramientas más usadas.
- `/es/<slug>`: una página por herramienta, generada en compilación desde el registro.
- `/es/convertir-archivo` y `/es/convertir-modelo-3d`.
- `/es/precios`, `/es/privacidad`, `/es/terminos`, `/es/aviso-legal`, `/es/ayuda`, `/es/contacto`.
- `/cuenta`: historial de trabajos (solo metadatos), plan, uso diario (tareas, peticiones de IA), facturación con el portal de cliente de Stripe y borrado de cuenta.
- `/admin` (rol administrador):
  - colas por grupo;
  - uso de disco;
  - presupuesto de IA del día y saldo de OpenRouter;
  - lista de modelos;
  - tasa de error por herramienta;
  - flags de herramientas;
  - purga manual de archivos.

### 8.2 Plantilla de página de herramienta

1. H1 con la acción («Convertir OGG a MP3») y subtítulo de una línea.
2. Zona de subida (arrastrar, varios archivos, pegar desde el portapapeles) con el aviso de dónde se procesa:
   - herramientas cliente: «Tu archivo no sale de tu dispositivo»;
   - herramientas servidor: «Se borra en 1 hora».
3. Opciones de la herramienta, generadas desde `options_schema` y nunca menos que las del Anexo A:
   - las básicas, visibles;
   - el resto, en un bloque plegado «Opciones adicionales»;
   - las últimas opciones usadas se recuerdan por herramienta en el navegador;
   - las opciones que dependen de otra (por ejemplo, las de cada formato de salida) solo aparecen cuando aplican.
4. Progreso, resultado, descarga y «Seguir con otra herramienta» con el mismo archivo. Además:
   - **Enviar por correo**, solo para usuarios registrados:
     - se envía un enlace firmado que caduca a las 24 horas, nunca el archivo adjunto;
     - plan gratuito: solo a su propia dirección verificada; Pro: hasta 3 destinatarios por envío;
     - límite diario `MAIL_SHARE_DAILY_LIMIT`, Turnstile y enlace «Informar de abuso» en cada correo;
     - el dominio de `MAIL_FROM` tiene SPF, DKIM y DMARC.
   - **Guardar en Google Drive o Dropbox:**
     - Google Drive: el navegador descarga el resultado y lo sube con la API de Drive y el ámbito `drive.file`;
     - Dropbox: el componente Saver recibe la URL firmada y son los servidores de Dropbox quienes descargan el archivo, así que esa URL dura 15 minutos y el WAF no debe bloquearlos;
     - ninguna credencial pasa por el servidor;
     - los scripts de Google y de Dropbox se cargan solo al pulsar el botón, nunca al cargar la página;
     - cada uno va detrás de su flag (`GDRIVE_ENABLED`, `DROPBOX_ENABLED`).
   - **Abrir desde Google Drive o Dropbox** en la zona de subida, con los mismos flags.
5. Contenido propio de cada página, en cada idioma: qué hace, pasos, preguntas frecuentes, límites por plan, formatos de entrada y salida y herramientas relacionadas.
   - Orientativo: 300 palabras propias por página. Ningún párrafo se repite literalmente en más de 3 páginas; una prueba de la CI lo comprueba.
   - Lo redactas tú a partir del registro, la sección 7 y el Anexo A, sin inventar cifras ni funciones. El propietario lo revisa por muestreo antes de quitar el `noindex` (7.22).
   - Valoración de 1 a 5 e «Informar de un problema» (tabla `tool_feedback`). Solo se muestran valoraciones reales, nunca inventadas.
6. Datos estructurados `SoftwareApplication` (con `offers` a precio 0, y `aggregateRating` solo cuando haya al menos 5 valoraciones reales) y `BreadcrumbList`. Google retiró en 2026 los resultados enriquecidos de preguntas frecuentes, así que `FAQPage` no aporta. Imagen Open Graph generada por herramienta, `hreflang` con `x-default`, `canonical` y sitemap por idioma.

### 8.3 Rendimiento y accesibilidad

- WebAssembly y librerías pesadas cargadas solo al elegir archivo; procesamiento en Web Workers.
- Objetivo: Lighthouse móvil de 90 o más en rendimiento y accesibilidad en las páginas de aterrizaje.
- PWA instalable; las herramientas cliente funcionan sin conexión.
- Modo oscuro, navegación por teclado y etiquetas accesibles.
- Textos de interfaz y SEO en archivos de mensajes por idioma, en español de España.

---

## 9. Backend

### 9.1 API pública (`api.{{DOMINIO}}`)

| Método y ruta | Descripción |
| --- | --- |
| `GET /v1/tools` | Catálogo, límites por plan y flags |
| `POST /v1/session/anon` | Verifica Turnstile y emite un token anónimo firmado válido 24 horas, con límite de emisiones por IP (12.4) |
| `GET /v1/uploads/{id}` | Estado de una subida (`ready` o `rejected`) |
| `POST /v1/jobs` | Crea trabajo: `{tool, upload_ids, options, ai_consent?}` |
| `GET /v1/jobs/{id}` | Estado, progreso, salidas con URL firmada y caducidad, error |
| `GET /v1/jobs/{id}/events` | Server-Sent Events con latido |
| `DELETE /v1/jobs/{id}` | Borra el trabajo y sus archivos ya |
| `GET /v1/me`, `/v1/me/usage`, `/v1/me/jobs` | Datos del usuario |
| `GET /v1/me/export` | Exportación de los datos de la cuenta (RGPD) |
| `POST /v1/shares` | Crea enlace para compartir |
| `POST /v1/ai/chat` | Mensaje de chat sobre un documento ya procesado. La API no sale a internet: encola en `workerai` y retransmite por Server-Sent Events los fragmentos que este publica en Valkey |
| `GET /v1/ai/budget` | Peticiones de IA restantes para el usuario y disponibilidad global |
| `POST /v1/billing/checkout`, `/v1/billing/portal`, `/v1/billing/webhook` | Stripe. El webhook verifica la firma sobre el cuerpo sin modificar y es idempotente por `event.id` (tabla `stripe_events`) |
| `/v1/signature-requests`, `/v1/sign/{token}` | Solicitar firmas (F4) |
| `GET /healthz`, `/readyz` | Vida y preparación (base de datos, Valkey, disco, reservas, colas, Gotenberg y versión de `pg_dump`) |

### 9.2 API interna (`apiint:8001`, sin dominio)

| Ruta | Descripción |
| --- | --- |
| `POST /tusd-hooks` | Ganchos de tusd (sección 4.2) |
| `GET /files/authorize` | Autorización de descargas para Caddy (sección 4.4) |
| `GET /ops/metrics` | Métricas para el panel de administración |

### 9.3 Planes y límites (tabla `plans`, editable)

| Límite | Anónimo | Gratis registrado | Pro |
| --- | --- | --- | --- |
| Tareas ligeras de servidor al día (`cost_class=light`: comprimir, Office a PDF, proteger, audio corto y similares) | 20 | 50 | 1.000 (uso justo) |
| Tareas pesadas de servidor al día (`heavy`: OCR, PDF a Office, transcripción, vídeo, CAD y similares) | 2 | 10 | 200 |
| Archivos por tarea | 5 | 20 | 100 |
| Tamaño máximo por archivo | 50 MB | 100 MB | 1 GB |
| Tamaño total por tarea | 100 MB | 300 MB | 2 GB |
| Páginas por PDF | 100 | 300 | 2.000 |
| Duración de audio | 10 min | 30 min | 4 h |
| Vídeo | No | No | Sí, hasta 1 h y 1 GB |
| Triángulos por malla | 1 millón | 2 millones | 10 millones |
| Peticiones de IA al día | 0 | 3 | 30 |
| Peticiones de IA por tarea | — | 5 | 20 (`AI_TASK_MAX_REQUESTS`) |
| Páginas por tarea de IA | — | 30 | 150 |
| Caracteres por tarea de pdf-a-audio | — | 20.000 | 300.000 |
| Retención de archivos | 1 h | 24 h | 24 h; compartir hasta 7 días |
| Prioridad de cola | baja | normal | alta |

- Los límites viven en la tabla `plans`, sembrada por una migración desde `config/plans.yaml`; no hay variables de entorno que los dupliquen.
- Una tarea es un `POST /v1/jobs` con todos sus archivos. Un resultado servido por idempotencia no cuenta, y las herramientas de navegador no cuentan nunca.
- Las cuotas anónimas se cuentan por token y por IP (por /64 en IPv6); manda la más restrictiva.
- «Uso justo» en Pro: por encima de 1.000 tareas ligeras al día, el trabajo pasa a prioridad normal y se avisa al administrador.
- Los límites de IA son máximos, no garantías: dependen del presupuesto global de 6.3, y la página muestra lo que queda hoy.

### 9.4 Modelo de datos

| Tabla | Columnas clave |
| --- | --- |
| tablas de Better Auth | usuarios (con `role`, `banned` y demás campos del plugin de administración), sesiones, cuentas, verificaciones y `jwks`; las crea `migrateauth` con la CLI de Better Auth |
| `profiles` | `user_id`, `plan_id`, `locale`, `created_at` (el rol vive en la tabla de usuarios de Better Auth) |
| `plans` | `id`, `name`, `limits` (jsonb) |
| `subscriptions` | `user_id`, `stripe_customer_id`, `stripe_subscription_id`, `status`, `current_period_end` |
| `stripe_events` | `id` (id del evento de Stripe), `type`, `received_at`, `processed_at` |
| `anon_clients` | `id`, `token_hash`, `ip_hash`, `created_at`, `expires_at` |
| `uploads` | `id` (id de tus), `owner_type`, `owner_id`, `path`, `size`, `sha256`, `detected_mime`, `original_name`, `state` (`uploading`, `ready`, `rejected` o `consumed`), `created_at`, `expires_at` |
| `jobs` | `id`, `owner_type`, `owner_id`, `tool`, `options` (sin secretos), `status`, `progress`, `worker_group`, `priority`, `idempotency_key` (único parcial, 5.3), `attempts`, `heartbeat_at`, `ai_reserved`, `ai_used`, `error_code`, `created_at`, `started_at`, `finished_at`, `expires_at`, `cpu_seconds` |
| `job_inputs` / `job_outputs` | `job_id`, `name`, `path`, `size`, `mime`, `sha256` |
| `usage_daily` | `owner_type`, `owner_id`, `date`, `cost_class`, `tasks`, `ai_requests`, `mail_shares` |
| `ai_requests` | `id`, `owner_type`, `owner_id`, `tool`, `model`, `prompt_tokens`, `completion_tokens`, `status`, `latency_ms`, `created_at` (sin contenido) |
| `ai_consents` | `owner_type`, `owner_id`, `text_version`, `created_at` |
| `llm_models` | `id`, `context_length`, `max_completion_tokens`, `supports_json`, `supports_images`, `enabled`, `disabled_until`, `priority`, `success_rate_7d`, `last_seen_at` |
| `document_texts` | `owner_type`, `owner_id`, `sha256`, `pages` (jsonb), `extractor`, `expires_at` |
| `document_chunks` | `id`, `owner_type`, `owner_id`, `sha256`, `page`, `chunk_index`, `text`, `embedding` (vector), `expires_at` |
| `ai_cache` | `key` (incluye el propietario), `result` (jsonb), `expires_at` |
| `shares` | `id`, `job_output_id`, `token_hash`, `expires_at`, `downloads`, `revoked_at` |
| `tool_feedback` | `id`, `tool`, `rating`, `message`, `owner_type`, `owner_id`, `created_at` (sin archivos) |
| `user_tool_prefs` | `user_id`, `favorites`, `recent` (jsonb) |
| `signature_requests` | `id`, `owner_id`, `job_output_id`, `status`, `created_at`, `expires_at` |
| `signers` | `id`, `request_id`, `email`, `name`, `sign_order`, `token_hash`, `code_hash`, `status`, `signed_at` |
| `audit_events` | `id`, `request_id`, `event`, `actor`, `ip_hash`, `user_agent`, `document_sha256`, `created_at`; alimenta el certificado de auditoría de solicitar-firmas |
| `seal_signatures` | `id`, `job_id`, `document_sha256`, `level`, `created_at`; registra cada uso del sello de la plataforma |
| `feature_flags` | `slug`, `enabled`, `plans` |
| `audit_log` | `actor`, `action`, `target`, `created_at`; acciones de administración |

- Todo contenido derivado de documentos de usuario (`document_texts`, `document_chunks`, `ai_cache`) pertenece a un solo propietario, caduca con sus archivos y lo borra Celery beat. Las cachés no se comparten entre usuarios.
- Alembic gestiona todas las tablas salvo las de Better Auth, que crea `migrateauth`; `migrate` se ejecuta después.
- Los workers usan un rol de PostgreSQL (`SERVICE_PASSWORD_WORKERDB`) con permisos solo sobre `jobs`, `job_inputs`, `job_outputs`, `usage_daily`, `ai_requests`, `document_texts`, `document_chunks`, `ai_cache`, `llm_models` y `seal_signatures`.

---

## 10. Firma

- Sello de la plataforma:
  - certificado y clave por PKCS#11 (SoftHSM2 en el VPS, salvo que el propietario aporte un HSM); en desarrollo, uno autofirmado generado por script; nunca en el repositorio;
  - solo `workersign` monta el token (volumen `softhsm`) y conoce `SIGN_PKCS11_PIN`; `workersign` no ejecuta otros motores que pyHanko y tiene el aislamiento de 12.1;
  - cada uso se registra en `seal_signatures` con el sha256 del documento; `SEAL_DAILY_LIMIT` limita los sellos diarios y `SEAL_ENABLED=false` lo apaga al instante;
  - con un token software no hay dispositivo cualificado de creación de sellos, así que el sello no es cualificado y no se anuncia como tal.
- Sello de tiempo RFC 3161 con `TSA_URL`. La TSA de producción la elige el propietario (0.1), porque puede tener coste y ser o no cualificada.
- La interfaz explica que la firma dibujada es simple y que el sello acredita la integridad del documento y el momento, no la identidad del firmante. Añade en `docs/LEGAL.md` que los niveles eIDAS que se prometan deben revisarse con un especialista.
- Certificado propio del usuario o de su empresa: solo con firma interrumpida (A.6). La clave nunca llega al servidor, y el servidor nunca guarda certificados con clave privada.
  - La interfaz no promete «avanzada» ni «cualificada» de antemano.
  - Muestra el nivel que detecta verificar-firmas-pdf sobre el resultado.

---

## 11. Licencias

- **Política en un fichero:** `scripts/license_policy.yaml` contiene las listas de esta sección y es lo que aplica la CI.
- **Frontend** (se distribuye al navegador): MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD, MPL-2.0, Zlib, Unlicense, CC0-1.0, BlueOak-1.0.0, CC-BY-4.0 (solo datos, como caniuse-lite) y OFL-1.1 (solo fuentes). En licencias dobles se elige la permisiva (por ejemplo, node-forge con BSD-3-Clause).
- **Backend:** lo anterior más PSF-2.0, Python-2.0, HPND y MIT-CMU (Pillow), LGPL-2.1, LGPL-3.0, EPL-2.0, EUPL-1.2 (solo datos) y LicenseRef-TOST-1.0 (usd-core).
- **GPL**, solo como programa externo en servidor, invocado por línea de órdenes y nunca importado: la CI falla si un paquete de Python o de npm instalado es GPL o AGPL. Los programas GPL permitidos son los de la sección 2.
- **Prohibido enlazar o empaquetar AGPL:** Ghostscript, MuPDF, PyMuPDF, pdf2docx, BabelDOC, EbookLib, Documenso, DocuSeal, PrusaSlicer, OrcaSlicer, Bambu Studio, CuraEngine, UVtools, libbgcode, MinIO, Garage, xmlsig y similares.
- **Trampas conocidas:**
  - `ezdxf[draw]` instala PyMuPDF: instala `ezdxf` sin ese extra y usa su backend SVG;
  - el paquete `ocrmypdf` de las distribuciones depende de Ghostscript: instala OCRmyPDF con pip;
  - extract-msg es GPL: para MSG usa olefile y compressed-rtf;
  - `misaki[en]` y `phonemizer-fork` son GPL: espeak-ng solo como programa externo;
  - los wheels de pillow-heif incluyen x265 (GPLv2);
  - el modelo por defecto de rembg (`bria-rmbg`) exige un acuerdo de pago para uso comercial.
- **Impresión 3D:** permitidos lib3mf (BSD-2-Clause), trimesh, assimp, manifold3d, usd-core (TOST-1.0) y OpenCascade (LGPL con excepción).
- **Paridad con PDF24** (comprueba cada licencia al añadirla):
  - Frontend: qr-code-styling, Konva, TipTap (solo paquetes MIT del registro público de npm; Pages y la conversión a DOCX de TipTap son de pago y no se usan), `docx`, mammoth, KaTeX, PKI.js, xadesjs, mermaid, `@resvg/resvg-wasm`, glTF Transform y SheetJS Community Edition (Apache-2.0, instalada desde cdn.sheetjs.com con versión fijada, porque la del registro de npm, 0.18.5, tiene vulnerabilidades sin corregir; Renovate no la vigila, así que revísala a mano en cada fase).
  - Backend: img2pdf (LGPL), drafthorse (Apache-2.0), factur-x (BSD), signxml (Apache-2.0), olefile (BSD) y unoserver (MIT).
  - Como programas externos: KoSIT Validator (Java, Apache-2.0), unpaper (GPL, lo invoca OCRmyPDF), pngquant (GPL), jbig2enc (Apache-2.0), tiffcp de libtiff, draw.io desktop (GPL-3.0) y espeak-ng (GPL-3.0).
  - Las reglas Schematron de EN 16931 (EUPL-1.2), XRechnung y Peppol se usan como datos en servidor y se registran en `docs/LICENSES.md` con la licencia que publique cada una.
- **FFmpeg:**
  - preferir compilación LGPL;
  - una compilación GPL (con x264) solo como programa externo en servidor;
  - nunca `libfdk_aac`;
  - nunca ffmpeg.wasm en el frontend: `@ffmpeg/core` es GPL-2.0-or-later.
- **Códecs:**
  - riesgo bajo: MP3, Opus, Vorbis y FLAC;
  - AAC (codificador nativo de FFmpeg), VP9 y AV1: sus autores los publican libres de regalías o con licencias de patentes propias, pero hay pools que reclaman licencias; anota la revisión en `docs/LEGAL.md`;
  - codificación H.264 tras `VIDEO_H264_ENCODING_ENABLED`, apagado hasta la revisión legal;
  - decodificación HEVC (vídeo H.265 y HEIC) tras `HEVC_DECODE_ENABLED`, apagado hasta la revisión legal;
  - documenta en `docs/LEGAL.md` que el uso comercial de H.264 y HEVC puede requerir licencia de patentes, también como servicio en la nube.
- **Modelos y recursos:** comprueba y registra la licencia de los modelos de Whisper, Kokoro, embeddings, rembg y Docling (código MIT; modelos con Apache-2.0 o CDLA-Permissive-2.0 según la ficha de cada uno; no uses modelos sin ficha de licencia) y del banco de sonidos de FluidSynth.
- **CI:**
  - `scripts/check_licenses.py` (pip-licenses y license-checker de npm) aplica `scripts/license_policy.yaml` y falla ante una licencia fuera de lista, una licencia desconocida o un paquete GPL o AGPL;
  - `scripts/check_images.sh` falla si alguna imagen contiene `gs`, `mutool` o PyMuPDF;
  - SBOM CycloneDX en cada compilación.

---

## 12. Seguridad

### 12.1 Workers

- Usuario sin privilegios, `read_only` con tmpfs pequeño en `/tmp` (los archivos grandes van a `jobs/<id>/work`, y `TMPDIR` y `HOME` apuntan ahí en cada trabajo), `cap_drop: [ALL]`, `no-new-privileges`, `pids_limit`, `mem_limit`, `memswap_limit` y `cpus` por servicio (5.4).
- Runtime configurable con `WORKER_RUNTIME`: `runsc` (gVisor) si está instalado en el host, `runc` por defecto. Comprueba en el primer despliegue que Coolify conserva la clave `runtime`; si no, anota el riesgo aceptado en `docs/SECURITY.md`.
- Secretos mínimos por contenedor, con la matriz en `docs/SECURITY.md`. Cada contenedor comprueba al arrancar que no ve variables que no le tocan; si las ve, no pasa `/readyz`.
  - Los workers que procesan archivos solo reciben `VALKEY_URL`, `DATABASE_URL_WORKER` (rol limitado de 9.4) y, si su grupo maneja contraseñas, `JOB_SECRETS_KEY`.
  - `OPENROUTER_API_KEY` solo en `workerai`; `SIGN_PKCS11_PIN` solo en `workersign`.
  - `FILE_TOKEN_SECRET`, `ANON_TOKEN_SECRET`, `AUTH_SECRET` y las claves de Stripe, SMTP, Google y Dropbox nunca llegan a un worker.
- Cada motor externo (LibreOffice, Calibre, pandoc, Tectonic, OpenSCAD, MuseScore, draw.io, FFmpeg, readpst, LibreDWG, ddjvu, pdftocairo, espeak-ng) se ejecuta como subproceso con entorno vacío salvo `PATH`, `HOME` y `TMPDIR` del trabajo, con el directorio del trabajo como directorio actual y con tiempo y memoria limitados (`prlimit`).
- El proceso del worker se marca como no volcable (`PR_SET_DUMPABLE=0`), para que un subproceso no pueda leer su `/proc/<pid>/environ`.

### 12.2 Redes

- Redes de Compose:
  - `internal` (`internal: true`, sin salida a internet): todos los servicios;
  - `edge` (con salida): solo `web`, `api`, `apiint`, `beat`, `egressai` y `egressweb`;
  - `webrender` (`internal: true`): `gotenbergweb`, `egressweb`, `workeroffice` y `workersign`;
  - `airelay` (`internal: true`): `workerai` y `egressai`;
  - Coolify añade su red para el proxy en los servicios con dominio (`web`, `api`, `upload`, `files` y `umami`).
- Qué sale y por dónde:
  - `web`: Google OAuth y SMTP;
  - `api`: verificación de Turnstile, API de Stripe y SMTP;
  - `apiint` y `beat`: SMTP de avisos y repositorio remoto de restic;
  - `workerai`: OpenRouter, solo por `egressai`;
  - `gotenbergweb` (web-a-pdf y captura-web), `workeroffice` (documentos enlazados de web-a-pdf) y `workersign` (TSA, OCSP, CRL y lista de confianza de la UE): solo por `egressweb`;
  - el resto, nada.
- Smokescreen identifica a sus clientes por certificado TLS. Para no montar mTLS hay dos instancias, cada una con su política:
  - `egressai`: modo `enforce` con OpenRouter como único dominio permitido;
  - `egressweb`: cualquier host público; deniega IP privadas, de enlace local, de metadatos de la nube y de las redes de Docker (`--deny-range` para 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 100.64.0.0/10, 169.254.0.0/16, fc00::/7 y fe80::/10).
- La API solo acepta en web-a-pdf y captura-web URL `http` o `https` con puerto 80 o 443.
- Gotenberg (desde la 8.32 los filtros de salida vienen desactivados por defecto):
  - `gotenberg`, que recibe archivos de usuarios, no tiene salida: además de estar solo en la red `internal`, lleva `--chromium-deny-public-ips=true`, `--chromium-deny-private-ips=true`, `--libreoffice-deny-public-ips=true` y `--libreoffice-deny-private-ips=true`;
  - `gotenbergweb` usa `--chromium-proxy-server=http://egressweb:4750` y nunca recibe archivos de usuarios;
  - en los dos, `downloadFrom` y los webhooks quedan bloqueados (`--api-download-from-deny-public-ips`, `--api-download-from-deny-private-ips`, `--webhook-deny-public-ips` y `--webhook-deny-private-ips` a `true`).
- Tras el primer despliegue, revisa la vista *Deployable Compose* de Coolify y confirma que se conservan `runtime`, `read_only`, `cap_drop`, límites y redes internas. Una prueba de humo en el VPS intenta salir a internet desde cada worker y desde `gotenberg`, y debe fallar. Si alguna clave se pierde, aplica una alternativa y documéntala en `docs/DEPLOY.md`.

### 12.3 Entradas

- Tipo real por bytes; límites de tamaño, páginas, duración, píxeles y triángulos comprobados antes de procesar.
- Protección frente a bombas de descompresión:
  - imágenes: `IMAGE_MAX_PIXELS` (100 megapíxeles) comprobado en la cabecera antes de decodificar, y el mismo valor en `Image.MAX_IMAGE_PIXELS` de Pillow;
  - PDF: al rasterizar, ninguna página pasa de `RENDER_MAX_PIXELS` (50 megapíxeles; la resolución baja para respetarlo), con tiempo máximo por página;
  - comprimidos: ver abajo.
- Contraseñas de PDF solo en memoria (5.3).
- LibreOffice sin macros y sin recursos enlazados (Gotenberg 8.34 o posterior los descarta; en `workeroffice`, la misma política y sin red). Chromium sin acceso a `file://` fuera del directorio de la petición.
- FFmpeg:
  - `-nostdin` y `-protocol_whitelist file,pipe`;
  - lista blanca de formatos de entrada, sin listas HLS, concat ni playlists, que pueden leer archivos locales o URLs;
  - `ffprobe` previo;
  - límites de duración y de tiempo de proceso.
- XML (Facturae, UBL, CII, XAdES, KML, GPX, 3MF, AMF, DAE, X3D, draw.io, MusicXML) siempre con defusedxml, sin entidades externas.
- SVG: en el navegador, resvg sin recursos externos; en servidor (svg-a-pdf y svg-a-stl), solo imágenes en `data:` y ninguna referencia a archivos ni URL.
- Comprimidos y contenedores ZIP (3MF, KMZ, DOCX, XLSX, PPTX, ODT, EPUB y .gcode.3mf). Rechaza:
  - rutas con `..` o absolutas;
  - enlaces simbólicos;
  - más de 10.000 entradas;
  - más de 2 GB descomprimidos en total, o una relación de compresión mayor de 100:1 en una entrada;
  - en documentos de Office, más de 500 MB descomprimidos.
- Entradas que son código o que referencian archivos (pandoc, OpenSCAD, LaTeX, draw.io y Calibre):
  - sin red;
  - pandoc siempre con `--sandbox`;
  - OpenSCAD: un análisis previo rechaza `include`, `use`, `import` y `surface` con rutas absolutas o con `..`;
  - Tectonic sin shell-escape;
  - Calibre sin archivos locales fuera del directorio del trabajo en la entrada HTML;
  - entorno vacío y límites estrictos de tiempo y memoria (12.1);
  - los mensajes de error de los motores no se devuelven literalmente al usuario;
  - una prueba por motor (16.4) intenta leer `/etc/hostname` y el entorno del proceso padre y comprueba que el resultado no contiene secretos.

### 12.4 Aplicación

- Rate limiting en la API y en los ganchos de tusd por IP y por usuario. La IP real sale de `CF-Connecting-IP` solo cuando la petición llega desde los rangos de Cloudflare (Traefik con `forwardedHeaders.trustedIPs`); en IPv6 se agrupa por /64.
- `POST /v1/session/anon`: Turnstile y como máximo `ANON_TOKENS_PER_IP_DAY` tokens por IP al día.
- CORS de la API restringido a `https://{{DOMINIO}}`; la API autentica solo por la cabecera `Authorization`.
- Cabeceras de la web: `Strict-Transport-Security` con `includeSubDomains`; `Content-Security-Policy` con nonce por petición (`script-src 'self' 'nonce-<valor>' 'wasm-unsafe-eval'`, `worker-src 'self' blob:`, y los dominios de Turnstile, Google y Dropbox solo en las páginas que los usan); `frame-ancestors 'none'`; `Referrer-Policy: strict-origin-when-cross-origin`; y `Permissions-Policy` que solo permite la cámara en escaner-pdf, crear-collage, crear-tarjeta y firmar-pdf.
- Tokens de descarga firmados y con caducidad corta; enlaces de compartir con el token guardado solo como hash.
- Logs sin nombres de archivo ni contenido: solo sha256, tamaño, herramienta, duración y código de error. Los argumentos de las tareas de Celery no se registran.
- Secretos solo por variables de entorno generadas por Coolify; nunca en el repositorio ni en logs.
- Webhooks de Stripe: verificación de firma sobre el cuerpo sin modificar, idempotencia por `event.id` y comprobación de que el WAF y la protección contra bots de Cloudflare no los bloquean.
- Renovate, Trivy en la CI y reconstrucción de imágenes ante parches de seguridad de LibreOffice, PDFium, FFmpeg, Chromium, Tesseract, libheif o FreeType.

### 12.5 RGPD

- Bases jurídicas: ejecución del servicio pedido para procesar archivos (art. 6.1.b del RGPD), consentimiento para las herramientas de IA (6.6) e interés legítimo para seguridad y antiabuso. Regístralas en el registro de actividades de tratamiento de `docs/LEGAL.md`.
- Archivos en el VPS (UE), borrado automático aplicado por Celery beat y plazos publicados en la política de privacidad. `anon_clients`, `ai_requests`, `usage_daily` y los logs se conservan 90 días; `audit_events` y `seal_signatures`, el plazo que fije el asesor.
- Lista de subencargados: proveedor del VPS, Cloudflare, OpenRouter y sus proveedores de modelos, Stripe, proveedor de correo, Sentry si se activa, y Google y Dropbox cuando el usuario los usa. Para cada uno, el país y la garantía de transferencia (marco de privacidad UE-EE. UU., cláusulas tipo u otra).
- Evaluación de impacto (EIPD) del uso de IA con modelos de terceros en `docs/LEGAL.md`, para revisarla con un especialista.
- Analítica sin cookies; sin banner de consentimiento salvo que se añadan cookies no esenciales. La sesión y Turnstile se tratan como estrictamente necesarias, y los scripts de Google y Dropbox solo se cargan cuando el usuario los pide.
- Exportación (`GET /v1/me/export`) y borrado de cuenta desde `/cuenta`.

---

## 13. Despliegue en Coolify (un VPS)

### 13.1 Preparación del VPS

1. Instalar el sistema, crear usuario con clave SSH y desactivar el acceso por contraseña.
2. Cortafuegos del proveedor (o reglas en `DOCKER-USER`) según 3.1: 22 desde las IP de administración, 80 y 443 desde los rangos de Cloudflare, y nada más.
3. Montar el disco dedicado en `/srv/{{PRODUCTO}}`, si existe.
4. Instalar Coolify con su script oficial y la versión estable fijada.
5. Opcional: instalar gVisor y registrar `runsc` en Docker.
6. En Cloudflare:
   - DNS proxied para `{{DOMINIO}}`, `api`, `upload`, `files` y `stats`;
   - SSL en modo Full (strict) con un certificado de origen de Cloudflare instalado en el proxy de Coolify, y Authenticated Origin Pulls activado si el proxy de Coolify lo admite;
   - WAF básico, comprobando que la protección contra bots no bloquea los webhooks de Stripe;
   - regla de caché para las páginas HTML de herramientas cuando no hay cookie de sesión, con purga en cada despliegue;
   - widget de Turnstile.
7. Panel de Coolify con su dominio a través del proxy y Cloudflare Access; después, cierra 8000, 6001 y 6002.

### 13.2 Recurso en Coolify

- Proyecto `{{PRODUCTO}}`, entorno `production`, recurso Docker Compose desde el repositorio de GitHub, apuntando a `docker-compose.coolify.yml`.
- Dominios mediante variables mágicas de Coolify, sin `ports:`. `SERVICE_URL_<ID>_<PUERTO>` incluye el esquema y `SERVICE_FQDN_<ID>_<PUERTO>` es solo el dominio; usa la primera para las URL públicas:
  - `SERVICE_URL_WEB_3000`
  - `SERVICE_URL_API_8000`
  - `SERVICE_URL_UPLOAD_8080`
  - `SERVICE_URL_FILES_8090`
  - `SERVICE_URL_UMAMI_3000` (opcional)
- Nombres de servicio sin guiones ni guiones bajos en los que tienen dominio (Coolify convierte guiones y puntos en guiones bajos dentro de la variable).
- Secretos con variables mágicas, que Coolify genera y conserva entre despliegues:
  - `SERVICE_USER_POSTGRES`, `SERVICE_PASSWORD_POSTGRES`
  - `SERVICE_PASSWORD_VALKEY`
  - `SERVICE_PASSWORD_64_AUTH`
  - `SERVICE_PASSWORD_64_FILES`
  - `SERVICE_PASSWORD_64_ANON`
  - `SERVICE_PASSWORD_64_JOBSECRETS`
  - `SERVICE_PASSWORD_WORKERDB` (rol de PostgreSQL limitado de 9.4)
- El resto de variables con `${VAR:?}` para que Coolify las pida, o con valor por defecto (sección 14). Cada servicio declara en `environment:` solo las variables que le tocan (12.1).
- `healthcheck` en todos los servicios de larga duración. `migrateauth` y `migrate` llevan `exclude_from_hc: true` y `restart: "no"`; los servicios que dependen de ellos usan `depends_on` con `condition: service_completed_successfully`, y el resto, `service_healthy`.
- Volúmenes: `filestore` (`/srv/files`), `backups` (`/srv/backups`), `softhsm` (en `workersign`, y en `apiint` solo para la copia), y datos de `postgres`, `valkey` y `umami`.
- Rotación de logs con `logging: driver json-file` y `max-size: 10m`, `max-file: 5` en cada servicio.
- Tarea programada de Coolify: copia en `apiint` cada 6 horas, con tiempo máximo de 3.600 s (4.6). La actualización de los rangos de Cloudflare y la copia de Coolify van en cron del host, descritas en `docs/OPERATIONS.md`.
- Un despliegue de Compose recrea los contenedores: los workers paran en caliente (5.3) y `docs/DEPLOY.md` indica que los despliegues se hacen en horas valle.

### 13.3 Documentación de despliegue

`README.md` y `docs/DEPLOY.md` con, al menos:

1. Requisitos y preparación del VPS.
2. Instalación de Coolify.
3. Acceso al registro de imágenes.
4. Alta del recurso.
5. Variables obligatorias y DNS.
6. Cloudflare.
7. Primer despliegue y creación del administrador (`{{EMAIL_ADMIN}}`).
8. Configuración de la cuenta de OpenRouter.
9. Copias, restauración y actualización.
10. Qué hacer si se llena el disco o se agota el presupuesto de IA.
11. Paso a producción de los pagos: alta en la ventanilla única de IVA (OSS) si se vende a consumidores de otros países de la UE, registros fiscales en Stripe Tax, claves en vivo, precios definitivos y términos y política de reembolsos revisados.
12. Lista de comprobación del cierre operativo de cada fase (`docs/DEPLOY-CHECKLIST.md`).

---

## 14. Variables de entorno

| Variable | Por defecto | Descripción |
| --- | --- | --- |
| `APP_ENV` | `production` | `development` activa proveedores falsos |
| `APP_NAME` | `{{PRODUCTO}}` | Nombre visible |
| `PUBLIC_WEB_URL` | `https://{{DOMINIO}}` | URL de la web |
| `PUBLIC_API_URL` | `https://api.{{DOMINIO}}` | URL de la API |
| `PUBLIC_UPLOAD_URL` | `https://upload.{{DOMINIO}}/files/` | Punto de subida tus |
| `PUBLIC_FILES_URL` | `https://files.{{DOMINIO}}` | Descargas |
| `DEFAULT_LOCALE` | `es` | Idioma por defecto |
| `DISPLAY_TZ` | `Europe/Madrid` | Zona para mostrar horas |
| `DATABASE_URL` | compuesta con las variables mágicas | PostgreSQL |
| `VALKEY_URL` | compuesta con las variables mágicas | Valkey |
| `DATABASE_URL_WORKER` | compuesta con `SERVICE_PASSWORD_WORKERDB` | Rol de PostgreSQL limitado de los workers (9.4) |
| `AUTH_SECRET` | `${SERVICE_PASSWORD_64_AUTH}` | Better Auth |
| `AUTH_JWKS_URL` | `http://web:3000/api/auth/jwks` | JWKS para la API |
| `FILE_TOKEN_SECRET` | `${SERVICE_PASSWORD_64_FILES}` | Firma de descargas |
| `ANON_TOKEN_SECRET` | `${SERVICE_PASSWORD_64_ANON}` | Firma de tokens anónimos |
| `BETTER_AUTH_URL` | `https://{{DOMINIO}}` | URL base de Better Auth |
| `JOB_SECRETS_KEY` | `${SERVICE_PASSWORD_64_JOBSECRETS}` | Cifrado de contraseñas en las tareas (5.3) |
| `FILESTORE_PATH` | `/srv/files` | Raíz del almacenamiento |
| `DISK_MAX_USAGE_PERCENT` | `85` | Guarda de disco |
| `DISK_MIN_FREE_GB` | `20` | Guarda de disco |
| `DISK_RESERVE_FACTOR` | `3` | Reserva de disco por subida (4.5) |
| `QUEUE_MAX_WAIT_SECONDS_<GRUPO>` | `300` (`pdf`: `120`) | Guarda de colas (4.5) |
| `CLIENT_MAX_MB` | `100` | Tamaño máximo en herramientas de navegador (5.1) |
| `FILE_TTL_ANON_MINUTES` | `60` | Retención anónimos |
| `FILE_TTL_USER_HOURS` | `24` | Retención registrados |
| `SHARE_MAX_DAYS` | `7` | Caducidad máxima al compartir |
| `UPLOAD_MAX_BYTES` | `1073741824` | Máximo absoluto (Pro) |
| `UPLOAD_CHUNK_BYTES` | `52428800` | Trozo de tus en el navegador |
| `BACKUP_PATH` | `/srv/backups` | Copias locales |
| `BACKUP_RETENTION_DAYS` | `14` | Retención de copias |
| `BACKUP_RESTIC_REPOSITORY` | vacío | Copia remota propia (opcional) |
| `BACKUP_RESTIC_PASSWORD` | vacío | Clave de restic |
| `ADMIN_EMAILS` | `{{EMAIL_ADMIN}}` | Avisos y administradores |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | vacío | Acceso con Google (opcional) |
| `SMTP_URL`, `MAIL_FROM` | obligatorio | Correo saliente |
| `MAIL_SHARE_DAILY_LIMIT` | `10` | Envíos de resultados por correo al día por usuario |
| `GOOGLE_PICKER_CLIENT_ID`, `GOOGLE_PICKER_API_KEY`, `DROPBOX_APP_KEY` | vacío (desactivado) | Abrir y guardar en Google Drive y Dropbox |
| `GDRIVE_ENABLED`, `DROPBOX_ENABLED` | `false` | Flags de Google Drive y Dropbox |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | obligatorio | Antiabuso |
| `RATE_LIMIT_PER_MINUTE` | `60` | Por IP en la API |
| `ANON_TOKENS_PER_IP_DAY` | `10` | Tokens anónimos por IP y día (12.4) |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | modo test | Pagos |
| `STRIPE_PRICE_PRO_MONTHLY`, `STRIPE_PRICE_PRO_YEARLY` | modo test | Precios |
| `OPENROUTER_API_KEY` | obligatorio en producción | Clave de OpenRouter |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | API compatible con OpenAI |
| `LLM_PREFERRED_MODELS` | vacío | Lista ordenada de ids `:free` |
| `LLM_FALLBACK_ROUTER` | `openrouter/free` | Último recurso |
| `LLM_MODELS_REFRESH_HOURS` | `6` | Descubrimiento de modelos |
| `AI_DAILY_BUDGET` | `950` | Tope diario propio |
| `AI_PRO_RESERVE` | `400` | Reserva diaria para Pro |
| `AI_RPM_LIMIT` | `18` | Tope por minuto propio |
| `AI_BUDGET_RESET_TZ` | `UTC` | Zona del reinicio diario |
| `AI_REQUIRE_CONSENT` | `true` | Consentimiento obligatorio |
| `AI_CHAT_RPM_SHARE` | `0.5` | Parte del límite por minuto que puede usar el chat |
| `AI_TASK_MAX_REQUESTS` | `20` | Peticiones máximas por tarea |
| `EMBEDDINGS_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Embeddings locales |
| `WHISPER_MODEL` | `small` | Transcripción local |
| `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE` | `cpu`, `int8` | Transcripción local |
| `TTS_ENGINE` | `kokoro` | Voz local |
| `TTS_VOICE_ES`, `TTS_VOICE_EN` | voces de Kokoro | Voces por idioma |
| `REMBG_MODEL` | `isnet-general-use` | Quitar fondo (6.4) |
| `SOUNDFONT_PATH` | banco con licencia comercial | MIDI a audio |
| `TECTONIC_BUNDLE_PATH` | ruta en la imagen | LaTeX sin red |
| `VIDEO_H264_ENCODING_ENABLED` | `false` | Codificación H.264 tras la revisión legal (11) |
| `HEVC_DECODE_ENABLED` | `false` | HEIC y vídeo HEVC tras la revisión legal (7.2) |
| `INVOICING_ES_ENABLED` | `false` | Herramientas que generan facturas (7.23) |
| `IMAGE_MAX_PIXELS` | `100000000` | Límite de píxeles de una imagen (12.3) |
| `RENDER_MAX_PIXELS` | `50000000` | Píxeles máximos por página rasterizada (12.3) |
| `OPENSCAD_TIMEOUT_SECONDS` | `60` | Sandbox de OpenSCAD |
| `WORKER_RUNTIME` | `runc` | `runsc` para gVisor |
| `CONCURRENCY_<GRUPO>` | ver sección 5.4 | Concurrencia por grupo |
| `THREADS_<GRUPO>` | ver sección 5.4 | Hilos por trabajo |
| `GOTENBERG_URL` | `http://gotenberg:3000` | Gotenberg sin red, para archivos subidos |
| `GOTENBERG_WEB_URL` | `http://gotenbergweb:3000` | Gotenberg para URL |
| `EGRESS_AI_URL` | `http://egressai:4750` | Proxy de salida hacia OpenRouter |
| `EGRESS_WEB_URL` | `http://egressweb:4750` | Proxy de salida hacia la web pública |
| `SIGN_PKCS11_MODULE`, `SIGN_PKCS11_TOKEN_LABEL`, `SIGN_PKCS11_KEY_LABEL`, `SIGN_PKCS11_PIN` | SoftHSM2 en desarrollo | Sello de la plataforma (10) |
| `SIGN_CERT_PATH`, `TSA_URL` | vacío en desarrollo | Cadena del sello y TSA |
| `SEAL_ENABLED`, `SEAL_DAILY_LIMIT` | `true`, `500` | Interruptor y límite diario del sello |
| `EUTL_LOTL_URL`, `EUTL_REFRESH_HOURS` | lista oficial de la Comisión Europea, `24` | Lista de confianza para verificar firmas |
| `KOSIT_VALIDATOR_PATH`, `KOSIT_SCENARIOS_PATH` | rutas en la imagen | Validación de factura electrónica |
| `OCR_MAX_LANGUAGES` | `3` | Idiomas simultáneos en ocr-pdf |
| `SENTRY_DSN` | vacío | Errores (opcional) |
| `UMAMI_URL`, `UMAMI_WEBSITE_ID` | vacío | Analítica (opcional) |
| `LOG_LEVEL` | `INFO` | Nivel de log |
| `TOOL_<SLUG>_ENABLED` | según fase | Flag por herramienta |

`.env.example` con todas ellas y valores de desarrollo.

Los límites por plan (duración de audio, triángulos y demás) no son variables de entorno: viven en `plans` (9.3).

---

## 15. Estructura del repositorio

```text
.
├── apps/
│   ├── web/                    # Next.js: páginas, herramientas cliente, auth, admin
│   └── api/                    # FastAPI: app pública, app interna, ops
├── packages/
│   ├── core/                   # Python: registro, almacenamiento, límites, IA
│   ├── registry/               # registry.json y JSON Schema generados (5.2)
│   ├── tools/                  # Python: <grupo>/<slug>/spec.py e impl.py
│   └── client-tools/           # TypeScript: herramientas de navegador en Web Workers
├── workers/                    # Dockerfiles por grupo y arranque de Celery
├── config/
│   └── plans.yaml              # límites por plan (9.3)
├── infra/
│   ├── caddy/Caddyfile
│   ├── smokescreen/
│   │   ├── acl-ai.yaml
│   │   └── acl-web.yaml
│   ├── gotenberg/              # flags de gotenberg y gotenbergweb (12.2)
│   └── tusd/
├── scripts/                    # check_licenses.py, license_policy.yaml, check_images.sh, export_registry.py, fixtures/
├── tests/                      # pytest, fixtures, e2e con Playwright, k6
├── docs/
│   └── spec/                   # este documento troceado (sección 1)
├── docker-compose.yml          # desarrollo, con Mailpit y los dobles de 0.1
├── docker-compose.coolify.yml  # producción
└── .env.example
```

---

## 16. Pruebas

### 16.1 Generales

- **Python:** pytest con fixtures reales. Por herramienta comprueba:
  - tipo de salida por bytes;
  - número de páginas;
  - texto esperado;
  - cifrado;
  - PDF/A validado con veraPDF;
  - firma válida con pyHanko.
- **Web:**
  - Vitest para la lógica de las herramientas cliente;
  - Playwright para unir, comprimir, word-a-pdf, pdf-a-word, ogg-a-mp3, stl-a-3mf, chat-pdf con LLM falso y el flujo de pago con `FakePaymentProvider`; el pago con claves de prueba reales de Stripe se comprueba en el cierre operativo de F1;
  - Playwright también verifica que las herramientas cliente no envían el archivo a la red;
  - regresión visual: capturas de la plantilla de herramienta en móvil y escritorio, y de los PDF de folleto-pdf, varias-paginas-por-hoja, numerar-paginas-pdf y marca-de-agua-pdf pasados a PNG con pypdfium2, con un umbral de diferencia de píxeles;
  - Lighthouse CI según 1.3.
- **Registro:** `registry.json` está al día y el registro se importa en la API sin cargar motores (5.2).
- **Licencias e imágenes:** `check_licenses.py` y `check_images.sh` en la CI (11).
- **Carga:** k6 con 50 trabajos simultáneos de comprimir-pdf y 10 de ogg-a-mp3, más un pico de 300 trabajos ligeros en 5 minutos desde 100 clientes, midiendo CPU, RAM, disco y tiempo de respuesta de las páginas. Aparece `QUEUE_FULL` antes de que la espera supere el umbral y las páginas siguen por debajo de 1 s. Los resultados alimentan `docs/OPERATIONS.md` y los valores de 5.4.

### 16.2 Almacenamiento

- `pre-create` rechaza archivos por encima del plan, subidas con tamaño diferido (`Upload-Defer-Length`) y cualquier subida cuando la guarda de disco está activa.
- Un archivo cuyo tipo real no coincide con la extensión queda `rejected`, `POST /v1/jobs` responde `UNSUPPORTED_FORMAT` y la limpieza lo borra.
- `POST /v1/jobs` enviado justo después de terminar la subida funciona siempre, porque `pre-finish` es bloqueante.
- La reserva de disco impide aceptar más subidas de las que caben.
- Token de descarga caducado o manipulado: 403. Ruta con `..` en el nombre: rechazada. Caddy no lista directorios y envía las cabeceras de 4.4.
- Celery beat borra trabajos vencidos y huérfanos.
- `backup` y `restore` funcionan sobre una base de prueba, y `backup` sube la copia con restic a un servidor SFTP en contenedor.

### 16.3 IA

- La petición 951 del día se bloquea con `AI_BUDGET_EXHAUSTED`.
- Un usuario gratuito no consume la reserva Pro.
- El limitador respeta 18 peticiones por minuto y el reparto del chat.
- Si el primer modelo devuelve 429, la petición se resuelve con el siguiente candidato.
- Todas las peticiones llevan `provider.data_collection: "deny"`.
- El descubrimiento guarda los modelos de precio 0 con su `max_completion_tokens`.
- La reconciliación con `/key` sube el contador propio cuando OpenRouter cuenta más.
- Sin modelos válidos, la herramienta responde `AI_UNAVAILABLE` sin gastar peticiones.
- Sin consentimiento, 400.
- Las herramientas excluidas nunca llaman a OpenRouter (se prueba con un transporte que falla si se usa).
- La caché evita una segunda petición para la misma tarea del mismo usuario y nunca sirve el resultado de otro usuario.

### 16.4 Seguridad

- web-a-pdf y captura-web contra 169.254.169.254, localhost, el nombre de otro servicio y una IP privada alcanzada tras una redirección: bloqueadas.
- Desde cada worker y desde `gotenberg`, una conexión a internet falla; desde `workerai`, solo responde OpenRouter.
- Bombas de descompresión (ZIP, PNG gigante, PDF con una página enorme y XLSX con relación de compresión alta): cortadas.
- Tiempo límite: mata el proceso.
- Ningún secreto en logs ni en los argumentos de tareas guardados en Valkey.
- Matriz de secretos: cada contenedor arranca solo con sus variables (12.1).
- Lectura de archivos locales: un Markdown con `![](/proc/self/environ)` para pandoc, un `.tex` con `\input{/etc/hostname}`, un SVG con `<image href="file:///etc/hostname">`, un `.scad` con `import("/etc/hostname")` y un EPUB con `<img src="file:///etc/hostname">` se rechazan, o el resultado no contiene ese archivo ni ningún secreto.
- Una lista HLS que apunta a `/etc/passwd` o a una URL: rechazada.
- Un XML con entidad externa y un ZIP con rutas `../`: rechazados.
- Cabeceras CSP, HSTS y `Permissions-Policy` presentes en la web, y `Content-Security-Policy: default-src 'none'; sandbox` en `files`.
- `POST /v1/session/anon` por encima de `ANON_TOKENS_PER_IP_DAY` desde la misma IP: rechazado. Una cabecera `CF-Connecting-IP` falsificada desde fuera de los rangos de Cloudflare: ignorada.
- Webhook de Stripe con firma inválida: 400; el mismo evento dos veces: se procesa una vez.
- Redacción: tras redactar un área que cubre texto, parte de una imagen y un trazado vectorial, no queda el texto, los píxeles de la imagen bajo el área están sustituidos y el trazado ya no se dibuja en esa zona.

### 16.5 Formatos

- **Audio y vídeo:** duración conservada (±50 ms) y códec correcto, comprobados con ffprobe.
- **Firmas:** el documento extraído de un .csig o .p7m de prueba coincide byte a byte con el original; verificar-firma detecta un documento alterado.
- **Datos:**
  - GPX ↔ KML conserva el número de puntos;
  - VCF → CSV → VCF conserva los contactos;
  - arreglar-codificacion-csv recupera tildes y eñes.
- **3D:**
  - STL → 3MF → STL conserva volumen (error menor del 0,1 %) y número de triángulos;
  - STEP → STL sale estanco;
  - lib3mf valida cada 3MF generado;
  - reparar-stl deja estanca una malla de prueba con huecos;
  - bgcode → gcode → bgcode reproduce el G-code de archivos reales de PrusaSlicer;
  - OpenSCAD con `import` fuera del directorio del trabajo falla.
- **Vídeo:** un MOV con H.264 y AAC pasa a MP4 sin recodificar (mismo códec y mismo número de fotogramas).

### 16.6 Opciones (Anexo A)

- **Prueba de contrato por herramienta:** el `options_schema` publicado en `/v1/tools` tiene las opciones del Anexo A con sus valores por defecto y rangos, y la API rechaza valores fuera de rango con `INVALID_OPTIONS`.
- **Prueba de efecto** al menos para:
  - comprimir-pdf: con las opciones por defecto reduce un PDF con fotos; nunca devuelve un archivo mayor que el original; el texto extraído es idéntico al original.
  - numerar-paginas-pdf: patrón `{NUM} / {CNT}` con primera página 3 y primer número 1; el texto aparece donde toca.
  - marca-de-agua-pdf: el mosaico cubre la página.
  - proteger-pdf: cada permiso desactivado se refleja en el PDF; AES-256.
  - redactar-pdf: con cada método, el texto redactado ya no se encuentra en el resultado y se cumplen las comprobaciones de redacción de 16.4.
  - pdf-escala-de-grises: en las páginas no rasterizadas no queda ningún operador de color distinto de gris, el texto sigue siendo extraíble y el informe lista las páginas rasterizadas.
  - pdf-modo-oscuro: el texto sigue siendo extraíble y las imágenes no cambian en «conservar tonos».
  - ocr-pdf: con salida PDF/A pasa veraPDF.
  - unir-pdf: con «páginas en blanco tras archivos impares», cada documento empieza en página impar.
  - folleto-pdf: 10 páginas dan 12, con la contraportada al final.
  - imprimir-pdf: con 4 por hoja, el PDF de impresión tiene el número de hojas esperado.
  - pdf-a-tiff: en blanco y negro con G4, `tiffinfo` confirma la compresión.
  - generar-codigo-qr: con logotipo y corrección H, zxing-cpp lee el código.
  - crear-factura-electronica: el XML generado pasa el KoSIT Validator en cada perfil.
  - verificar-firmas-pdf: detecta un cambio no permitido tras una firma de certificación.
  - pdf-a-pdfa: un PDF con fuentes sin incrustar falla con un informe y ofrece la alternativa rasterizada; en ningún momento se ejecuta Ghostscript.
  - quitar-fondo: el modelo cargado es el de `REMBG_MODEL`, nunca `bria-rmbg`.

### 16.7 Operación

- Restauración completa desde la copia remota en un entorno limpio de la CI (base de datos, variables cifradas y token del sello), una vez por fase.
- Arranque de humo del Compose de producción con sus healthchecks.
- Un worker que muere por memoria deja el trabajo en `WORKER_LOST` al tercer intento, sin bucles.
- Un trabajo más largo que una hora (el `visibility_timeout` por defecto) se ejecuta una sola vez.

---

## 17. Fases y entregables

| Fase | Contenido | Cierre técnico (1.3) |
| --- | --- | --- |
| F1 Núcleo y lanzamiento | Monorepo, Compose local y de Coolify, autenticación, anónimos con cuotas, tusd, Caddy, trabajos, limpieza y guardas de disco y de colas, copias (también la remota), planes y Stripe, catálogo F1, conversor-pdf, convertir-a-pdf, panel de administración básico y las herramientas adelantadas de 17.1 | Pruebas de 16.1 a 16.4 y 16.7 de su ámbito en verde y Lighthouse según 1.3 |
| F2 PDF de servidor | Resto del catálogo F2, escáner, comparar y montar | Herramientas F2 en verde |
| F3 IA | Descubrimiento de modelos, limitador y presupuesto, consentimiento, embeddings y voz locales, catálogo F3 | Pruebas de 16.3 en verde y uso real de peticiones registrado |
| F4 Firma y extras | Firma, compartir, solicitar firmas, PDF/UA y facturas (validar y visualizar primero; los generadores detrás de `INVOICING_ES_ENABLED`) | Firma validada con pyHanko y flujo de solicitud probado de extremo a extremo |
| F5 Multimedia | Audio, vídeo (solo Pro), imágenes, IA de audio y vídeo, convertir-archivo | Pruebas de audio y vídeo y prueba de carga de ogg-a-mp3 |
| F6 Utilidades | Documentos y datos, comprimidos, subtítulos, fuentes, firmados y factura electrónica, GPS, contactos y calendario, diagramas, música, captura web | Pruebas de 16.5 de su ámbito en verde |
| F7 Impresión 3D y CAD | Mallas, CAD, herramientas, generadores, G-code, convertir-modelo-3d | Pruebas 3D de 16.5 en verde |

Las fases conservan su número porque las líneas del catálogo lo citan, pero se ejecutan en este orden: núcleo de F1 y lista de lanzamiento (17.1), lanzamiento público, resto de F1, F2, F5 sin vídeo, F3, F4, F6, vídeo de F5 y F7. Cada fase tiene además su cierre operativo (1.3).

### 17.1 Lista de lanzamiento

El lanzamiento público solo necesita el núcleo de F1 y estas herramientas. Las demás de F1 pueden quedar con `noindex` (7.22) hasta terminarse después del lanzamiento.

- **Navegador:** unir-pdf, dividir-pdf, girar-pdf, eliminar-paginas-pdf, extraer-paginas-pdf, organizar-pdf, numerar-paginas-pdf, marca-de-agua-pdf, editar-pdf, rellenar-pdf, jpg-a-pdf, png-a-pdf, imagenes-a-pdf, pdf-a-jpg, pdf-a-png, pdf-a-imagenes, generar-contrasena; y se adelantan de F5 png-a-jpg, webp-a-jpg, comprimir-imagen y redimensionar-imagen.
- **Servidor:** comprimir-pdf, convertir-a-pdf, word-a-pdf, excel-a-pdf, ppt-a-pdf; y se adelantan de F2 pdf-a-word, ocr-pdf, proteger-pdf y desbloquear-pdf, y de F5 ogg-a-mp3, opus-a-mp3, m4a-a-mp3 y mp4-a-mp3.
- Cada herramienta adelantada llega con todas sus opciones del Anexo A.

Las herramientas de la sección 7.23 entran en la fase que indica cada línea, y las opciones del Anexo A llegan con su herramienta. Ninguna fase se cierra con herramientas por debajo de esas opciones, salvo las desactivadas según 1.7. Al cerrar F6, comprueba en `docs/TOOLS.md` que cada herramienta web de PDF24 tiene su equivalente o una explicación de por qué no.

---

## 18. Criterios de aceptación

- `docker compose up` arranca todo en local solo con `.env.example` y los dobles de 0.1.
- El cierre técnico de cada fase está en verde en la CI, y el operativo está hecho o figura como pendiente en `docs/PROGRESS.md`, con sus pasos en `docs/DEPLOY-CHECKLIST.md`.
- Con las entradas de 0.1, el repositorio se despliega en un único VPS con Coolify v4 con todos los healthchecks en verde.
- No existe ninguna dependencia ni variable de S3: todo el almacenamiento está en disco del VPS.
- Cada herramienta habilitada tiene páginas es y en, funciona de extremo a extremo y su prueba pasa; las desactivadas cumplen 1.7.
- Cada herramienta expone como mínimo las opciones del Anexo A, con sus valores por defecto y rangos.
- Las herramientas cliente no envían el archivo a la red.
- La IA solo usa modelos gratuitos de OpenRouter con `data_collection: "deny"`, nunca supera 18 peticiones por minuto ni `AI_DAILY_BUDGET` al día, y exige consentimiento.
- Ninguna dependencia AGPL enlazada o empaquetada y ningún paquete GPL importado, comprobado en la CI.
- Ningún worker sale a internet salvo por los proxies de 12.2, y ningún contenedor ve secretos que no le tocan.
- Los archivos y el contenido derivado desaparecen al vencer su plazo.
- Las guardas de disco y de colas funcionan y avisan al administrador.
- La copia remota existe y la restauración está probada (16.7).
- Ningún secreto en el repositorio ni en los logs.
- `docs/` completo: PLAN, PROGRESS, DECISIONS, ARCHITECTURE, TOOLS, LICENSES, LEGAL, SECURITY, DEPLOY, DEPLOY-CHECKLIST, OPERATIONS, ERRORS y `spec/`.

---

## Anexo A. Opciones por herramienta

Este anexo fija las opciones mínimas de cada herramienta: todas las de PDF24 más algunos extras marcados como **Extra**. Los valores por defecto van entre corchetes y los rangos, entre paréntesis.

### A.0 Convenciones comunes

- **Rangos de páginas:**
  - sintaxis `1-3, 5, 8-` (un final abierto llega hasta la última página);
  - atajos «impares», «pares» y «todas»;
  - se validan en cliente y en servidor.
- **Posición:** rejilla de 9 (arriba, medio o abajo × izquierda, centro o derecha); algunas herramientas usan 6.
- **Color:** selector más opacidad de 0 a 1.
- **Unidades:** mm o pulgadas. Internamente, puntos PDF: 1 mm = 2,8346 pt.
- **Papel:**
  - A0 a A6, Letter y Legal, y Personalizado;
  - las herramientas de impresión añaden A3, A5 y Media carta donde aplica.
- **Fuentes «Sans | Serif | Mono»:** Noto Sans, Noto Serif y Noto Sans Mono (OFL), incrustadas como subconjunto, para que salgan bien tildes, eñes, € y alfabetos no latinos.
- **Lotes:**
  - varios archivos reciben las mismas opciones;
  - la salida es un archivo por entrada más un ZIP con todo, salvo que la herramienta una en un solo archivo.
- **PDF con contraseña:** se pide la contraseña al abrir, nunca se fuerza (`PASSWORD_REQUIRED`).
- **Resultado:**
  - muestra tamaño antes y después, número de páginas y avisos (por ejemplo, «se ha perdido el PDF/A» o «se han quitado las etiquetas de accesibilidad»);
  - siempre ofrece «Seguir con otra herramienta».

### A.1 Crear

- **crear-pdf** (F1): accesos a unir, convertir a PDF, imágenes a PDF, web a PDF, solicitud de empleo, escáner, collage, tarjeta, factura, formulario y escribir-pdf.
- **imagenes-a-pdf, jpg-a-pdf, png-a-pdf, webp-a-pdf, gif-a-pdf, bmp-a-pdf y tiff-a-pdf** (navegador; TIFF en servidor):
  - Tamaño de página:
    - A0–A6 [A4], Letter, Legal;
    - «Según la imagen» (DPI [150], 1–10000), en el que la página toma el tamaño de la imagen;
    - Personalizado (ancho × alto [210 × 297], mm o pulgadas).
  - Orientación: [Automática] | Vertical | Horizontal.
  - Margen: [Sin margen] | 5 | 10 | 15 | 20 | 25 mm | Personalizado.
  - Unir en un solo PDF [sí]. Marcadores con el nombre de cada imagen [no].
  - Orden por arrastre; se respeta la orientación EXIF.
  - **Extra:**
    - Ajuste: [Encajar] | Rellenar recortando | Tamaño real.
    - Los JPEG se incrustan sin recomprimir (`embedJpg` de pdf-lib; img2pdf en servidor).
- **web-a-pdf** (F1, Chromium de `gotenbergweb` por `egressweb`):
  - URL de una página web o de un documento convertible (DOCX, XLSX, PPTX, ODT, imagen o PDF), que se descarga con los límites del plan y se convierte con su herramienta, como hace PDF24.
  - **Extra:**
    - Papel [A4] y Orientación [Vertical].
    - Márgenes [10 mm].
    - Imprimir fondos [sí].
    - Una sola página larga [no].
    - Tipo de medio [print] | screen.
    - Espera antes de capturar [1 s] (0–10).
    - Esquema de color [claro] | oscuro.
  - Usa los campos de la ruta Chromium de Gotenberg de la versión fijada: `paperWidth`, `paperHeight`, `landscape`, `marginTop` y el resto de márgenes, `printBackground`, `singlePage`, `emulatedMediaType`, `waitDelay` y `emulatedMediaFeatures` (`prefers-color-scheme`).
- **escribir-pdf** (F6, navegador):
  - **Editor:** títulos, fuentes, tamaños, colores, negrita, cursiva, subrayado, listas y listas de tareas, tablas, imágenes, enlaces, notas al pie, fórmulas (KaTeX), columnas, índice automático, saltos de página, caracteres especiales y emojis, buscar y reemplazar.
  - **Página:**
    - Papel [A4] y márgenes [25 mm].
    - Encabezado y pie con números de página.
    - Marca de agua.
    - Papel con membrete, con un PDF de fondo aplicado como en superponer-pdf.
    - Borde de página.
  - **Plantillas propias:** carta, presupuesto, CV, acta, informe, certificado, folleto y solicitud.
  - **Vista previa por páginas:** el editor muestra saltos de página aproximados y el botón «Vista previa exacta» genera el PDF en servidor y lo muestra. No uses la extensión Pages de TipTap, que es de pago.
  - **El PDF exportado lleva:**
    - índice con los números de página reales, calculados en dos pasadas: se genera el PDF, se leen las páginas de cada título en el esquema que crea Gotenberg (`generateDocumentOutline`) y se vuelve a generar con los números;
    - campos rellenables insertados desde el editor (texto, casilla y fecha), creados con pdf-lib tras la conversión;
    - propiedades del documento (título, autor, asunto y palabras clave).
  - **Abrir:**
    - DOCX con mammoth;
    - ODT, convertido a HTML con LibreOffice en `workeroffice`;
    - Markdown;
    - PDF, convertido a HTML con Docling.
  - **Exportar:**
    - PDF: HTML enviado a Gotenberg, con marcadores desde los títulos (`generateDocumentOutline`) y PDF etiquetado (`generateTaggedPdf`).
    - DOCX con `docx`.
    - Markdown.
    - ODT con pandoc en servidor.
  - **Combinación de correspondencia:**
    - desde CSV o XLSX, con campos `{Columna}`;
    - salida [un PDF por fila, en ZIP] | un PDF con todas.
  - **Firma dibujada y QR:** se insertan como imagen.
  - **Borradores y versiones:** en IndexedDB del navegador. Nada se guarda en servidor, coherente con la política de retención. La sincronización en la cuenta se anota como mejora en `docs/TOOLS.md`.
  - **Dictado y lectura en voz alta:** Web Speech API del navegador cuando exista; no gasta peticiones de IA.
- **escaner-pdf** (F2):
  - Captura con cámara, detección automática de bordes y corrección de perspectiva (OpenCV.js).
  - Filtro: [Documento] (blanco y negro adaptativo) | Gris | Color realzado | Original.
  - Girar, reordenar, repetir y añadir páginas.
  - Tamaño de página: [Automático] | A4 | Letter.
  - **Extra:** OCR en servidor al terminar [no].
- **crear-collage** (F5, navegador):
  - **Plantillas:** cuadrícula y mosaico de 1 a 30 fotos, corazón, círculo, estrella, instantáneas, colocación libre y filas que conservan proporciones.
  - **Edición:** encuadre arrastrando, intercambio de celdas, separación y esquinas redondeadas arrastrables.
  - **Fotos:** desde archivo o directamente con la cámara del dispositivo.
  - **Adornos:**
    - textos con fuentes OFL incluidas;
    - stickers, formas y marcos propios;
    - sombras y fondo (color, degradado o imagen).
  - **Tamaño real con marcas de corte:**
    - foto de carné 35 × 45 mm (UE y visados) y 32 mm de alto por 26 mm de ancho (DNI y pasaporte españoles; el RD 1553/2005 que fijaba esa medida para el DNI fue derogado por el RD 255/2025); comprueba las medidas oficiales vigentes antes de publicarlas;
    - documento de identidad ID-1 (85,6 × 54 mm), anverso y reverso;
    - tarjetas y copias de foto;
    - una sola foto puede rellenar todas las celdas.
  - **Documentación fotográfica:** pie numerado con la fecha de captura (EXIF), encabezado por página y números de página.
  - **Salida:**
    - Papel [A4], Orientación y Resolución de exportación [300 ppp].
    - Formato [PDF] (fotos sin recomprimir) | JPG | PNG | Imprimir.
- **crear-tarjeta** (F6, navegador):
  - **Formato:** postal o díptica, con plantillas propias por ocasión.
  - **Contenido:**
    - fotos con filtros y máscaras;
    - texto con curva, sombra y contorno;
    - stickers, marcos, patrones y QR.
  - **Salida:**
    - [Imprimir en casa]: varias por A4 o Letter, con marcas de corte y reversos alineados para doble cara; la díptica sale doblada.
    - Imprenta: cada cara a tamaño final, sangrado [3 mm], BleedBox y TrimBox, marcas de corte e imágenes a 300 ppp como mínimo.
    - Imagen para enviar.
  - **Destinatarios:** desde CSV o XLSX, con campos `{Nombre}` y la dirección al reverso.
  - **Fotos:** desde archivo o con la cámara del dispositivo.
- **solicitud-de-empleo-pdf** (F2, servidor):
  - Entradas:
    - Carta de presentación (opcional);
    - CV (obligatorio);
    - Adjuntos (varios; Office, imágenes o PDF), en el orden elegido.
  - Marcador por documento [sí].
  - **Extra:**
    - Índice inicial [no].
    - Comprimir si supera [10 MB] [sí].
- **generar-codigo-qr** (F5, navegador):
  - **Tipos:**
    - URL;
    - WiFi: SSID, contraseña, cifrado [WPA/WPA2] | WEP | ninguno, red oculta [no];
    - texto;
    - vCard: nombre, apellidos, nombre visible, email, empresa, cargo, web y teléfono con tipo [trabajo] | móvil | personal | otro;
    - transferencia SEPA (EPC): beneficiario, IBAN validado, BIC, importe y concepto;
    - PayPal: correo o identificador de PayPal.Me, importe y moneda.
    - **Extra:** email, teléfono, SMS y evento de calendario.
  - **Logotipo:**
    - quitar fondo [no];
    - tamaño relativo [0,4] (0,1–1);
    - margen [0] px (0–100).
    - Con logotipo se fuerza la corrección H.
  - **Estilo:**
    - fondo [#FFFFFF], módulos [#000000], ojos exteriores [#000000] y ojos interiores [#000000], cada uno con degradado opcional (lineal o radial, con ángulo de 0° a 315° en pasos de 45°);
    - forma de módulos y de ojos;
    - borde con grosor [5], espaciado [20] y color [#000000];
    - forma general [cuadrado] | círculo.
  - **Técnico:**
    - Versión [auto] (1–40);
    - Modo [Byte] | Numérico | Alfanumérico | Kanji;
    - Corrección [Q] | L | M | H.
  - **Salida:**
    - Tamaño [500] px (100–10000).
    - Formato PNG | SVG | **Extra:** PDF vectorial.
    - Copiar al portapapeles.
    - Importar y exportar la configuración en JSON.
  - Tras generar, se lee con zxing-cpp; si no se lee, se avisa (contraste o logotipo excesivo).

### A.2 Facturas

- **crear-factura** (F4, navegador):
  - Plantilla propia con logotipo.
  - Emisor y cliente con NIF/CIF.
  - Número, fecha y vencimiento.
  - Conceptos: descripción, cantidad, unidad, precio, descuento e IVA [21 %] | 10 % | 4 % | 0 %.
  - Recargo de equivalencia [no] y retención de IRPF [no] | 7 % | 15 % | personalizada.
  - Moneda [EUR], idioma, notas, forma de pago e IBAN.
  - Totales automáticos y vista previa en vivo.
  - Emisor y clientes recordados en el navegador.
  - Salida PDF.
  - Botón «Convertir en factura electrónica».
- **crear-factura-electronica** (F4, servidor; firma en el navegador; detrás de `INVOICING_ES_ENABLED`):
  - Formulario EN 16931 con validación en vivo de los campos obligatorios.
  - Formato de salida:
    - [Factur-X/ZUGFeRD], con perfil MINIMUM | BASIC WL | BASIC | [EN 16931] | EXTENDED | XRECHNUNG; MINIMUM y BASIC WL no son facturas EN 16931 completas y la interfaz lo avisa;
    - XRechnung CII | UBL;
    - Peppol BIS Billing 3.0;
    - UBL 2.1 (EN 16931), la sintaxis de la solución pública española;
    - Facturae 3.2.2, con firma XAdES-EPES opcional hecha en el navegador con xadesjs y el certificado del usuario o de su empresa (.p12 o .pfx abierto con PKI.js); la clave nunca sale del navegador.
  - Importar desde PDF: usa el flujo de pdf-a-factura-electronica.
  - Antes de entregar, valida con el mismo motor que validar-factura-electronica.
- **pdf-a-factura-electronica** (F4):
  - Perfil Factur-X [EN 16931].
  - Si el PDF trae XML, lo usa.
  - Si no:
    1. extrae los datos (texto con PDFium, reglas y una sola petición de LLM con esquema JSON, con consentimiento);
    2. muestra el formulario de revisión, que es obligatorio y tiene todos los campos editables;
    3. convierte el PDF a PDF/A-3 conservando sus páginas e incrusta el XML.
- **factura-electronica-a-pdf** (F6):
  - Entrada: CII, UBL o Facturae, en lote.
  - Salida: [PDF/A-3 con el XML original incrustado byte a byte] | PDF simple.
  - Idioma de la representación [el de la factura].
- **validar-factura-electronica** (F4, servidor):
  - Detecta la sintaxis y la especificación por `CustomizationID` o por el contexto del documento.
  - Reglas: EN 16931, XRechnung, Peppol BIS, Factur-X/ZUGFeRD y Facturae (XSD y firma), con los escenarios de KoSIT descritos en 7.23.
  - Resultado por regla:
    - identificador, gravedad, explicación propia en lenguaje sencillo para las frecuentes y qué hacer;
    - campo afectado resaltado sobre la representación de la factura.
  - Se puede ver, imprimir o guardar como PDF, y abrir los anexos.
  - Lote o ZIP, con resumen (número, emisor, fecha, total y resultado) exportable a CSV.
  - El archivo se borra al terminar.

### A.3 Editar

- **editar-pdf** (F1, EmbedPDF):
  - Empezar con página en blanco, de tamaño elegible.
  - Texto: fuente, tamaño, color, negrita, cursiva y alineación.
  - Imágenes, formas (rectángulo, elipse, línea, flecha y polígono), dibujo libre, firma y nota.
  - Tapar con rectángulo de color.
  - Páginas: insertar en blanco, borrar, girar y reordenar.
  - Rellenar formularios.
  - No se reescriben párrafos; se ofrece pdf-a-word.
- **anotar-pdf** (F1):
  - Herramientas: resaltar, subrayar, tachar, nota adhesiva, cuadro de texto, flecha, formas, imagen y mano alzada con presión del lápiz (Pointer Events).
  - Color, grosor y opacidad.
  - Lista de comentarios.
  - Guardar como [anotaciones estándar, editables en otros lectores] | aplanadas.
  - **Extra:** exportar e importar comentarios en XFDF.
- **rellenar-pdf** (F1):
  - Campos AcroForm.
  - Texto libre sobre PDF no rellenables.
  - Marcas ✓ y ✗, fecha e imagen de firma.
  - Guardar [editable] | aplanado.
  - Los formularios XFA se avisan como no compatibles.
- **hacer-pdf-rellenable** (F4):
  - Partir de un PDF o de una página en blanco.
  - **Tipos de campo:**
    - texto de una línea o multilínea;
    - casilla;
    - grupo de botones de opción;
    - desplegable (editable o no);
    - lista (selección múltiple);
    - botón (restablecer formulario o abrir URL);
    - firma.
  - **Propiedades:** nombre, valor por defecto, obligatorio, solo lectura, longitud máxima, alineación, fuente y tamaño [auto], borde y fondo.
  - Mover, duplicar, alinear y borrar campos, incluidos los existentes.
  - **Extra:** detección automática de campos en líneas y casillas vacías, con revisión del usuario.
  - Los campos de firma se crean con pyHanko y son compatibles con firmar-pdf.
- **marca-de-agua-pdf** (F1):
  - Tipo: [Texto] | **Extra:** Imagen (PNG, JPG o SVG, escala [50 %]).
  - Texto [CONFIDENCIAL].
  - Fuente Sans | Serif | Mono y Tamaño [40] pt (1–500).
  - Color [#E67610] y Opacidad [0,4].
  - Ángulo [−45°].
  - Posición: rejilla de 9 [centro] | Mosaico (rellenar página).
  - Espacio X e Y [5 / 5] mm: margen respecto al borde, o separación en mosaico.
  - Páginas [todas] | rango.
  - **Extra:**
    - Capa [encima] | debajo del contenido.
    - Aplanar las páginas para dificultar que se quite [no].
- **numerar-paginas-pdf** (F1):
  - Patrón [`{NUM} / {CNT}`]. Variables: `{NUM}`, `{CNT}` y **Extra:** `{FECHA}` y `{ARCHIVO}`.
  - Posición: rejilla de 9 [abajo centro].
  - Fuente Sans | Serif | Mono y Tamaño [8] pt (1–100).
  - Color [#000000] y Opacidad [1].
  - Ángulo [0°].
  - Margen X e Y [5 / 5] mm.
  - Primera página numerada [1] y Primer número [1].
  - Última página numerada [la última].
  - Total mostrado en `{CNT}` [el real] | valor fijo.
  - **Extra:**
    - Posición en espejo para pares e impares (exterior, para libros) [no].
    - Estilo [1, 2, 3] | i, ii, iii | a, b, c.
- **superponer-pdf** (F2):
  - Archivo de superposición: PDF o cualquier formato convertible, como un membrete en Word.
  - Documentos de destino (varios).
  - Posición: [Fondo] | Primer plano.
  - Repetir la última página de la superposición [sí].
  - **Extra:**
    - Aplicar a [todas] | primera | rango.
    - Escalar al tamaño de cada página [sí].
- **recortar-pdf** (F1):
  - Izquierda, Superior, Derecha e Inferior [0] mm (paso 0,1).
  - Caja: [CropBox] | TrimBox.
  - Modo visual (rectángulo sobre la vista previa) [no].
  - Páginas [todas] | rango.
  - **Extra:**
    - Recorte automático de márgenes blancos: render con PDFium y margen de seguridad [2 mm].
    - Márgenes distintos para pares e impares.
- **cambiar-tamano-pagina-pdf** (F1):
  - Tamaño: A0–A6 [A4], Letter, Legal o Personalizado (mm o pulgadas).
  - Orientación: [Automática] | Vertical | Horizontal.
  - Páginas: [Todas] | Intervalo.
  - **Extra:** Contenido [escalar para encajar] | centrar sin escalar.
- **metadatos-pdf** (F2):
  - Ver y editar: Título, Autor, Asunto, Palabras clave, Fecha de creación y Fecha de modificación (con segundos), más **Extra:** Creador y Productor.
  - Se sincroniza con XMP.
  - Acción «Quitar todo» (eliminar-metadatos-pdf), que muestra antes lo que se va a borrar.
  - Lotes.

### A.4 Organizar

- **unir-pdf** (F1; en servidor si hay Office o imágenes TIFF):
  - Orden por arrastre. **Extra:** ordenar por nombre.
  - Elegir páginas de cada archivo [no].
  - Marcadores por archivo [no].
  - Páginas en blanco: [ninguna] | tras cada archivo | solo tras los de número impar de páginas (para imprimir a doble cara).
  - Portada con el nombre antes de cada archivo [no].
  - Índice inicial con enlaces [no].
  - Nombre de archivo impreso en sus páginas [no]:
    - posición (6) [arriba centro];
    - tamaño [10] pt (4–72).
- **montar-pdf** (F2, navegador):
  - Varios PDF e imágenes en columnas.
  - Arrastrar páginas entre documentos.
  - Crear un documento nuevo; girar, borrar y duplicar páginas.
  - Guardar cada documento por separado o todos en ZIP.
- **dividir-pdf** (F1):
  - Modo:
    - [Cada N páginas] (N [1]);
    - Pares e impares (dos PDF);
    - En dos mitades;
    - Personalizado: tijeras entre miniaturas o «dividir después de» (3, 7, 12).
  - **Extra:**
    - Por marcadores de primer nivel.
    - Por tamaño máximo en MB.
    - Por páginas en blanco (separadores de escaneo).
    - Patrón de nombre de salida.
- **organizar-pdf** (F1):
  - Arrastrar miniaturas.
  - Invertir el orden.
  - **Extra:** intercalar anversos y reversos de un escaneo a doble cara hecho en dos pasadas.
- **eliminar-paginas-pdf** (F1): clic por página, rango, pares o impares.
- **extraer-paginas-pdf** (F1):
  - Clic, rango (1-5, 8, 11-13), pares o impares.
  - Salida: [un PDF] | **Extra:** un PDF por página.
- **girar-pdf** (F1):
  - Todas o por página: 90° horario | antihorario | 180°.
  - **Extra:** autoorientar con la detección de orientación de Tesseract, en servidor.
- **varias-paginas-por-hoja** (F1):
  - Páginas por hoja: [2] | 3 | 4 | 6 | 8 | 9 | 12 | 16.
  - Orden: [horizontal] | vertical.
  - Hoja: A0–A6 [A4], Letter, Legal.
  - Orientación [automática].
  - Márgenes [0] % (0–50).
  - Dirección: [izquierda a derecha] | derecha a izquierda.
  - Bordes [no], con Color [#000000] y Ancho [0,5] pt.
- **imprimir-pdf** (F2, navegador):
  - Vista previa por hoja.
  - Páginas: [todas] | rango | impares | pares. Orden inverso [no].
  - Papel: [A4] | Letter | A3 | A5.
  - Escala: [ajustar al papel] | tamaño real.
  - Páginas por hoja: [1] | 2 | 4 | 6 | 9 | 16, con orden y bordes finos [no].
  - Escala de grises [no].
  - Doble cara manual: asistente para imprimir anversos, dar la vuelta al montón e imprimir reversos, con la opción «los reversos salen invertidos» recordada en el navegador.
  - Formularios y anotaciones impresos [sí].
  - Si el PDF restringe la impresión, solo se imprime con la contraseña de propietario.
  - Implementación: genera un PDF de impresión con pdf-lib y lo imprime desde un iframe. Recuerda elegir «Tamaño real» en el diálogo. Si el navegador no imprime un PDF desde un iframe (Safari y la mayoría de móviles), ofrece descargar el PDF de impresión.
- **folleto-pdf** (F1, navegador):
  - Papel: [A4, folleto A5] | A3, folleto A4 | Letter, folleto media carta.
  - Encuadernación: [izquierda] | derecha.
  - Medianil en el pliegue [0] mm.
  - Hojas por cuadernillo: [todas en uno] | N (varios cuadernillos para documentos gruesos).
  - Páginas en blanco automáticas hasta un múltiplo de 4, con «La última página sigue siendo la contraportada» [sí].
  - Vista previa de hojas y hojeado del folleto.
  - Salida: imprimir (doble cara por el borde corto, o manual) | guardar PDF.
- **cortar-paginas-por-la-mitad** (F2, navegador):
  - Corte: [automático, por el lado largo] | vertical | horizontal.
  - Orden de las mitades: [izquierda a derecha] | derecha a izquierda.
  - **Extra:**
    - No cortar la primera ni la última página [no] (portadas de libros escaneados).
    - Deshacer la imposición de un folleto escaneado [no].
  - Implementación: duplica la página y ajusta MediaBox y CropBox, sin rasterizar.
- **marcadores-pdf** (F2):
  - Árbol de marcadores.
  - Añadir desde la página y posición actuales; renombrar; borrar uno o todos; sangrar y desangrar; arrastrar.
  - Destino: página, posición vertical y zoom.
  - Estilo: negrita, cursiva y color. Abierto o cerrado.
  - **Extra:** generar marcadores desde los títulos (Docling).
- **extraer-imagenes-pdf** (F2):
  - Formato: [original] (JPEG tal cual; el resto a PNG) | PNG | JPG.
  - **Extra:**
    - Ignorar imágenes de menos de [32 px].
    - Eliminar duplicadas [sí].
  - Descarga en ZIP.
- **copiar-de-pdf** (F2, híbrida):
  - **Reconocimiento:** al pasar el ratón resalta bloques (párrafo, título, lista, tabla, imagen o índice). Un clic copia el bloque; también hay selección libre.
  - **Copiar como:**
    - [con formato], en HTML para Word y correo;
    - tabla para Excel (TSV y HTML);
    - texto;
    - Markdown, HTML, CSV o JSON.
  - **Documento entero:** imagen como PNG; todo como Markdown; todas las tablas a un XLSX, con una hoja por tabla.
  - **Escaneos:** OCR (más de 100 idiomas) y enderezado en servidor, bajo demanda.

### A.5 Optimizar y reparar

- **comprimir-pdf** (F1):
  - **Extra:** Nivel [Equilibrado] (144 ppp, 75 %) | Fuerte (96 ppp, 60 %) | Sin pérdida | Personalizado.
  - Resolución máxima de imágenes [144] ppp (10–300).
  - Calidad JPEG [75] % (1–100).
  - Opciones adicionales:
    - Eliminar miniaturas [sí].
    - Deduplicar flujos [sí].
    - Rasterizar gráficos vectoriales muy pesados [sí] (umbral por número de operadores por página).
    - Reducir fuentes incrustadas [sí]: quita fuentes duplicadas y no usadas; solo crea subconjuntos de fuentes TrueType o CFF simples cuyos glifos usados se puedan calcular con exactitud, y no toca las demás.
    - Compresión de imagen moderna (JPEG 2000 con OpenJPEG; JBIG2 sin pérdida para blanco y negro) [no].
    - Imágenes a gris [no].
    - Flate máximo y flujos de objetos [no].
    - Aplanar formularios [no].
    - Quitar output intents [no] (avisa de que rompe PDF/A).
    - Quitar adjuntos [no].
    - Quitar anotaciones [no].
    - Quitar marcadores [no].
    - Quitar metadatos [no].
    - Quitar estructura y etiquetas [no] (avisa de que rompe la accesibilidad).
  - Si el resultado no es menor, se devuelve el original y se dice.
- **pdf-escala-de-grises** (F2):
  - Método: [vectorial] (reescribe los operadores de color; el texto y los vectores siguen siendo vectores; las páginas que no se pueden convertir con seguridad se rasterizan en gris y se avisa) | **Extra:** rasterizar todo.
  - Imágenes, degradados y anotaciones a gris.
  - Conserva enlaces, marcadores y formularios.
- **pdf-modo-oscuro** (F2):
  - Modo: [Oscuro conservando tonos] (invierte la luminosidad y mantiene el tono; las fotos no cambian) | Negativo (todo invertido).
  - Fondo: Negro | [Gris oscuro].
  - No tocar las páginas que ya son oscuras [sí]. Se detectan por la luminancia media de la miniatura.
  - El texto sigue siendo texto, buscable y copiable.
  - Lotes en ZIP.
- **optimizar-pdf-web** (F2):
  - Linealizar con qpdf.
  - **Extra:** comprimir antes [no].
- **ocr-pdf** (F2):
  - Idiomas: multiselección hasta `OCR_MAX_LANGUAGES`.
    - Por defecto, el del navegador.
    - Lista completa de Tesseract (unos 125) con `tessdata_fast`, incluidos los CJK verticales y Fraktur; `tessdata_best` para los nueve idiomas de la sección 2.
  - Salida: [PDF con capa de texto] | PDF/A-2b (`--output-type pdfa-2 --pdfa-backend internal`; si no se puede sin Ghostscript, error claro y opción de rasterizar) | **Extra:** TXT.
  - Enderezar [sí] (`--deskew`).
  - Autorrotar páginas [no] (`--rotate-pages`).
  - Quitar fondo [no]: con `--remove-background` si la versión fijada lo admite; si no, preprocesado propio con OpenCV.
  - Limpiar páginas [no] (`--clean`, con unpaper).
  - Texto existente: [omitir las páginas con texto] (`--skip-text`, o `--mode skip` en la v17) | Forzar OCR (`--force-ocr`, o `--mode force`).
  - Unir todos los archivos en uno [no].
  - Título, Autor, Asunto y Palabras clave de la salida.
  - Progreso por página.
- **reparar-pdf** (F2):
  - Sin opciones.
  - Orden de intentos: reconstrucción con qpdf y pikepdf; si falla, guardar de nuevo con pypdfium2; como último recurso, rasterizar las páginas legibles.
  - Informe de lo recuperado.
- **rasterizar-pdf** (F2):
  - Resolución [144] ppp (10–300; hasta 600 en Pro).
  - Calidad [75] %.
  - Color: [sin cambios] | gris | **Extra:** blanco y negro de 1 bit.
- **aplanar-pdf** (F1): Aplanar [formularios] | anotaciones | ambos.
- **pdf-a-pdfa** (F2):
  - Nivel: [PDF/A-2b] | 1b | 2u | 3b; 2a y 3a solo si el PDF está etiquetado.
  - Se valida con veraPDF y se adjunta el informe.
  - Conversión con OCRmyPDF (`--pdfa-backend internal`, sin OCR en las páginas que ya tienen texto). Si el archivo no se puede convertir sin Ghostscript (por ejemplo, por fuentes sin incrustar), la tarea falla con el informe y ofrece rasterizar las páginas con capa de texto OCR.

### A.6 Seguridad

- **proteger-pdf** (F2):
  - Contraseña de apertura, con medidor de robustez y botón «Generar».
  - Contraseña de propietario. Si queda vacía y hay restricciones, se genera una aleatoria y se muestra una sola vez.
  - Permisos, todos [permitidos]:
    - modificar;
    - comentar;
    - imprimir;
    - imprimir en alta calidad;
    - ensamblar;
    - rellenar formularios;
    - copiar;
    - copiar por accesibilidad.
  - Cifrado [AES-256] | **Extra:** AES-128 para lectores antiguos.
  - Aviso: el respeto de los permisos depende del lector.
- **desbloquear-pdf** (F2): contraseña actual; quita cifrado y restricciones solo si la contraseña es correcta.
- **firmar-pdf** (F4):
  - Modo: [Insertar firma] | Firmar digitalmente.
  - **Origen de la firma:**
    - dibujar (ratón, táctil o lápiz; color y grosor);
    - escribir (fuentes caligráficas OFL);
    - subir imagen (quitar fondo);
    - cámara.
  - **Elementos:** iniciales y fecha. Colocar, redimensionar y repetir en varias páginas.
  - **Firma digital:**
    - [visible], con imagen, nombre, fecha, motivo y lugar | invisible;
    - certificado [sello de la plataforma], en servidor por PKCS#11 | certificado propio o de la empresa (.p12 o .pfx) con firma interrumpida: el servidor prepara el PDF y el resumen, el navegador firma con WebCrypto tras abrir el archivo con PKI.js, y la clave no sale del navegador;
    - nivel PAdES [B-T] | B-LT | B-LTA;
    - certificación (DocMDP): [no] | sin cambios | permitir formularios | permitir formularios y anotaciones;
    - sello de tiempo [sí].
- **redactar-pdf** (F1):
  - Rectángulos dibujados, listados en la barra lateral para revisarlos o quitarlos.
  - Buscar y «Redactar todas las coincidencias».
  - **Extra:** patrones de DNI/NIE, IBAN, email y teléfono.
  - Color del recuadro [negro] y texto en el recuadro [ninguno].
  - Método:
    - [Rasterizar las páginas afectadas] a 300 ppp, como hace PDF24: elimina con seguridad texto, imágenes y vectores bajo el área; el resto de la página pierde la selección de texto y se ofrece pasar ocr-pdf;
    - Eliminar solo el contenido bajo el área, con EmbedPDF y PDFium, que conserva el texto del resto de la página. Solo se ofrece cuando pasa las pruebas de redacción de 16.4 con texto, imágenes y vectores.
  - Siempre quita también los metadatos.
  - Tras guardar, se comprueba el resultado: el texto redactado no aparece, no queda texto dentro de las áreas y los píxeles de las imágenes bajo las áreas están sustituidos. Si algo falla, la tarea falla.
- **eliminar-metadatos-pdf** (F2):
  - Sin opciones obligatorias.
  - Quita el diccionario Info, XMP, fechas, productor y software.
  - Muestra antes lo que se va a borrar.
  - Lotes.
- **generar-contrasena** (F1, navegador):
  - Longitud [16] (8–64).
  - Mayúsculas [sí], Minúsculas [sí], Números [sí] y Símbolos [no].
  - **Extra:**
    - Excluir caracteres ambiguos (0/O, l/1/I) [no].
    - Cantidad [1] (1–20).
  - Copiar.
  - Nada sale del navegador.

### A.7 Ver y comprobar

- **lector-pdf** (F1): visor EmbedPDF. Si el archivo no es PDF, se convierte en servidor y se muestra.
- **comparar-pdf** (F2, en el navegador; en servidor solo con archivos de más de `CLIENT_MAX_MB`):
  - Archivos A y B.
  - Vista:
    - [texto]: añadido, borrado y cambiado, marcado en ambos, con una lista de cambios navegable;
    - superposición (A en rojo, B en azul);
    - deslizador.
  - **Extra:**
    - Ignorar mayúsculas y espacios [no].
    - Informe PDF descargable.
- **buscar-en-pdf** (F2, navegador):
  - Texto a buscar.
  - Distinguir mayúsculas [no], Palabra completa [no] y Expresión regular [no].
  - Muchos archivos a la vez.
  - Resultados con archivo, página y contexto; un clic abre la página resaltada.
  - Exportar a CSV.
  - Los archivos sin texto se señalan, con enlace a ocr-pdf.
- **validar-pdfa** (F2):
  - Perfil: [Automático, el que declara el archivo] | PDF/A-1a, 1b, 2a, 2b, 2u, 3a, 3b, 3u, 4, 4e, 4f | PDF/UA-1, PDF/UA-2.
  - Resultado: cumple o no cumple.
  - Por regla: cláusula ISO, explicación propia en lenguaje sencillo, número de incumplimientos y páginas.
  - «Convertir a PDF/A» y volver a comprobar.
  - Informe descargable.
- **verificar-firmas-pdf** (F4):
  - **Por cada firma:**
    - firmante y emisor;
    - fecha, indicando si procede de una TSA de confianza;
    - integridad;
    - cambios posteriores y si estaban permitidos (DocMDP/FieldMDP, con el análisis de diferencias de pyHanko);
    - nivel (simple, avanzada o cualificada) y si tiene validación a largo plazo.
  - **Confianza:** lista de confianza de la UE, con prestador y país para firmas y sellos cualificados.
  - **Revocación OCSP/CRL:** [bajo petición], por `egressweb`.
  - Informe imprimible o en PDF.
- **preferencias-visor-pdf** (F2):
  - Quitar todas [no].
  - Diseño de página (`/PageLayout`): SinglePage, OneColumn, TwoColumnLeft, TwoColumnRight, TwoPageLeft, TwoPageRight.
  - Modo de página (`/PageMode`): FullScreen, UseAttachments, UseNone, UseOC, UseOutlines, UseThumbs.
  - Página inicial y zoom inicial (`/OpenAction`): Fit, FitH, FitV o personalizado (%).
  - `/ViewerPreferences`:
    - CenterWindow, FitWindow y DisplayDocTitle;
    - HideMenubar, HideToolbar y HideWindowUI;
    - NonFullScreenPageMode;
    - Duplex;
    - PrintArea, PrintClip, ViewArea y ViewClip (MediaBox, CropBox, BleedBox, TrimBox o ArtBox);
    - PrintScaling;
    - Direction.
  - Todas las opciones empiezan en [No cambiar].

### A.8 Convertir a PDF

- **Office** (Word, Excel, PowerPoint, sus formatos antiguos, OpenDocument incluido ODG, RTF, Publisher y CSV), con las opciones de la ruta LibreOffice de Gotenberg:
  - Formato: [PDF] | PDF/A-2b | PDF/UA.
  - Páginas [todas] | rango.
  - Marcadores desde los títulos [sí].
  - Exportar campos de formulario [sí].
  - Calidad de imágenes [90] % y resolución máxima [300] ppp.
  - Contraseña del documento de entrada.
  - Excel: cada hoja en una sola página [no].
  - PowerPoint: diapositivas ocultas [no] y páginas de notas [no].
  - Word: comentarios en el margen [no].
- **TXT:**
  - Detección automática de la codificación (charset-normalizer).
  - Fuente [monoespaciada] | proporcional.
  - Papel [A4] y Márgenes [20 mm].
- **Markdown:**
  - GitHub Flavored: tablas, listas de tareas y código con resaltado.
  - Tema [claro] | sobrio.
  - Papel [A4].
  - markdown-it y Chromium.
- **EPUB, MOBI, AZW3 y FB2** (Calibre `ebook-convert`):
  - Papel [A5] | A4 | Letter.
  - Márgenes [15 mm].
  - Tamaño de letra base [12] pt.
  - Índice al principio [sí].
- **SVG:** sale vectorial y con el tamaño del SVG [sí] | encajado en A4.
- **TIFF multipágina:** cada página del TIFF es una página del PDF; la compresión G4 o JPEG se conserva sin recomprimir (img2pdf).
- **HEIC:** solo con `HEVC_DECODE_ENABLED`. Si está apagado, la página explica cómo exportar a JPEG desde iPhone y Mac.
- **UDF:** solo con su flag (7.23).

### A.9 Convertir desde PDF

- **convertir-desde-pdf y las páginas pdf-a-***: un mismo `options_schema` condicionado por el formato.
  - Formatos: TXT, RTF, HTML, DOCX, PPTX, XLSX, ODT, ODP, ODS, PNG, JPG, WEBP, TIFF, SVG, PDF/A, EPUB, Markdown, CSV y JSON.
  - Páginas [todas] | rango, en todos los formatos.
- **Imagen (JPG, PNG, WEBP y TIFF):**
  - Color:
    - [RGB, 24 bits];
    - CMYK, 32 bits (JPG y TIFF, con perfil ICC mediante LittleCMS);
    - gris, 8 bits;
    - blanco y negro, 1 bit (PNG y TIFF).
  - Compresión TIFF en blanco y negro: [G4] | G3 1D | G3 1D con EOL | G3 2D | LZW | PackBits, con tiffcp.
  - Resolución [144] ppp (72–600).
  - Calidad [85] % (JPG y WEBP).
  - TIFF multipágina [sí].
  - Salida: [una imagen por página] | una sola imagen con todas las páginas.
  - ZIP.
- **Office y texto (DOCX, ODT, RTF, PPTX, ODP, XLSX, ODS y TXT):**
  - Modo:
    - [Editable]: texto, tablas e imágenes reconstruidos con Docling;
    - Editable con gráficos vectoriales como imágenes;
    - Fiel al diseño: cajas posicionadas, con la importación de PDF de LibreOffice en `workeroffice`. Se avisa de que se edita peor.
  - OCR automático si no hay texto [sí] (cuenta como tarea de OCR).
  - XLSX: [una hoja por tabla] | todas las tablas en una hoja.
  - PPTX: una diapositiva por página.
  - Aviso común: con escaneos, conviene pasar antes ocr-pdf.
- **HTML y EPUB:**
  - Diseño:
    - [Automático];
    - Fijo: SVG por página con pdftocairo y capa de texto;
    - Fluido: Docling a HTML y, para EPUB, pandoc.
- **Markdown:**
  - Imágenes: [incluidas, en ZIP] | sin imágenes.
  - Quitar encabezados y pies repetidos [sí].
  - Tablas GFM.
- **PDF/A:** ver pdf-a-pdfa.
- **pdf-a-imagenes** (F1):
  - Formato: [JPG] | PNG | WEBP.
  - Color: [color] | gris.
  - Resolución [144] ppp (72–600).
  - Calidad [85] %.
  - Organización: [una carpeta por archivo] | todas las imágenes en una carpeta.
  - Páginas [todas] | rango.

### A.10 Imágenes

- **svg-a-png y svg-a-jpg** (navegador, `@resvg/resvg-wasm`):
  - Tamaño: [original] | 2× | 3× | 4× | ancho personalizado [1000] px (1–16384), manteniendo la proporción.
  - JPG: fondo [blanco] y calidad [90] %.
- **webp-a-jpg y webp-a-png:**
  - JPG: calidad [90] % y fondo para la transparencia [blanco].
  - Conservar metadatos [no].
- **heic-a-jpg y heic-a-png:**
  - Solo con `HEVC_DECODE_ENABLED`.
  - JPG: calidad [90] %.
  - Conservar EXIF [sí], quitando el GPS [sí].
