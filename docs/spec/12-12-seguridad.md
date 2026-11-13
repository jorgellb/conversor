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
