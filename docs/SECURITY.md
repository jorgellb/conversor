# Seguridad (12)

## Matriz de secretos (12.1)

Definida en `packages/core/core/envguard.py`. `/readyz` falla en producción si un contenedor ve una variable que no le
toca; un worker en esa situación no arranca (código 78).

| Contenedor | Secretos permitidos |
| --- | --- |
| `web` | `AUTH_SECRET`, `AUTH_DATABASE_URL`, `SMTP_URL`, `GOOGLE_CLIENT_SECRET` |
| `api` | `FILE_TOKEN_SECRET`, `ANON_TOKEN_SECRET`, `JOB_SECRETS_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `SMTP_URL`, `TURNSTILE_SECRET_KEY`, `DATABASE_URL` |
| `apiint` | `FILE_TOKEN_SECRET`, `ANON_TOKEN_SECRET`, `DATABASE_URL`, `SMTP_URL`, `BACKUP_RESTIC_PASSWORD` |
| `beat` | `DATABASE_URL`, `SMTP_URL` |
| `migrate` | `DATABASE_URL` (y `WORKER_DB_PASSWORD` para crear el rol de los workers) |
| `workerpdf`, `workeroffice` | `JOB_SECRETS_KEY` (y `DATABASE_URL_WORKER`, rol limitado) |
| `workerocr`, `workerconvert`, `workerav`, `workermedia` | solo `DATABASE_URL_WORKER` y `VALKEY_URL` |
| `workersignverify` (verificar-firmas-pdf, F4) | solo `DATABASE_URL_WORKER` y `VALKEY_URL`: ni `SIGN_PKCS11_PIN` ni el volumen del token del sello (D-185) |

## Workers

Usuario 10001, `read_only` con `/tmp` de 64 MB, `cap_drop: [ALL]`, `no-new-privileges`, `pids_limit`, `mem_limit` igual a
`memswap_limit`, `cpus`, `oom_score_adj` +500 y `runtime` configurable (`WORKER_RUNTIME=runsc` con gVisor). Cada motor
externo (LibreOffice, FFmpeg, ffprobe, Calibre, ddjvu, heif-dec, veraPDF, pdftocairo, tiffcp, espeak-ng) corre con `run_engine`: entorno vacío salvo `PATH`,
`HOME` y `TMPDIR` del trabajo, nuevo grupo de procesos, `RLIMIT_AS` (o `RLIMIT_DATA` para Calibre, que lleva Chromium,
y para la JVM de veraPDF; D-52 y D-63) y tiempo límite que mata al grupo. El proceso del worker se marca con `PR_SET_DUMPABLE=0`, así que un motor no
puede leer su entorno por `/proc`. FFmpeg lleva `-nostdin` y lista blanca de protocolos; las listas HLS se rechazan por
tipo real. Calibre usa una configuración y una caché dentro del directorio del trabajo.

La API no abre los archivos de los usuarios en su proceso. La única excepción es el recuento de caracteres de pdf-a-audio
antes de encolar (9.3). Se hace en un proceso aparte (`python -I tools/av/contar_texto.py`) con `run_engine`: entorno
vacío, 1 GB y 90 s. Antes, la API se marca con `PR_SET_DUMPABLE=0`, como los workers, para que ese proceso (del mismo
usuario) no pueda leer sus secretos por `/proc`. Si el recuento falla, se encola igual y el worker lo vuelve a comprobar
todo (D-169).

## Redes (12.2)

`internal` (sin salida) para todo lo demás; `edge` solo para `web`, `api`, `apiint`, `beat` y `egressweb`. `gotenberg`
solo en `internal` y con todos los filtros de salida activados. `webrender` (sin salida) une `workeroffice`,
`gotenbergweb` y `egressweb`: `gotenbergweb` y `egressweb` no están en `internal`, porque cualquier servicio de esa red
podría usarlos para salir a internet (D-34). `egressweb` (Smokescreen, compilado desde su etiqueta v0.1.0 en una imagen `scratch` sin
usuario root, D-155) niega las IP privadas, de enlace local, CGNAT y de Docker; la API solo admite URL `http` o `https` con puerto 80 o 443 hacia nombres públicos, y el worker vuelve a
comprobar cada redirección. Prueba de humo en el VPS: una conexión a internet desde cada worker y desde `gotenberg`
debe fallar, y desde `workeroffice` solo sale por `egressweb` (DEPLOY-CHECKLIST).

Verificación de firmas (F4, D-185): `workersignverify` está en `internal` y `webrender` y sale solo por `egressweb`, a la
lista de confianza de la UE (beat, cada `EUTL_REFRESH_HOURS`) y, si el usuario lo pide, a los OCSP y CRL que nombran los
certificados del documento (URL que pone quien firmó: por eso van por `egressweb`, que niega las IP privadas). Las listas
se guardan en el volumen `eutl` solo si su firma valida, desde el ancla del DOUE que trae pyHanko; una descarga a medias
nunca sustituye a la versión buena (puntero `actual.json` atómico), y cada lista tiene un tope de 25 MB. El XML lo lee
pyHanko con su manejador restringido de lxml (sin entidades externas). Los PDF se abren con pyHanko en modo estricto (rechaza
las tablas de referencias híbridas que muestran contenidos distintos); solo si hay errores de estructura, en modo tolerante
y con un aviso destacado en el informe. Cada firma mal formada se informa sin detener las demás, la revocación en línea
tiene límites de peticiones, tamaño y tiempo por documento (D-186) y el informe HTML escapa todo lo que viene del archivo.

## Entradas

Tipo real por bytes (`core/filetype.py`), nombres saneados, `lstat` antes de registrar salidas, límites de píxeles
(`IMAGE_MAX_PIXELS`, `RENDER_MAX_PIXELS`), bombas ZIP en Office cortadas (`core/zipguard.py`), rutas `../` rechazadas en
descargas y ZIP, contraseñas nunca en base de datos, logs ni argumentos en claro de Celery. EPUB y FB2 con `file:`, rutas
absolutas, `..` fuera del libro o entidades XML se rechazan antes de Calibre (D-53); SVG y FB2 se leen con defusedxml;
el HTML de los correos se sanea con nh3 y lo imprime `gotenberg` sin red (D-51); los cómics pasan por los límites de
las bombas de compresión y no se extrae nada con `..` ni rutas absolutas. En el navegador, los SVG los pinta resvg sin
red, sin fuentes del sistema y sin cargar imágenes externas (D-82), y cada imagen decodificada tiene un límite de 50 MP
(D-79). zxing-cpp se carga desde el propio origen, nunca desde su CDN, y leer-codigo-qr muestra los enlaces sin abrirlos
(D-92). En el servidor, LibRaw revela los RAW en un proceso aparte con límites de memoria y tiempo (D-97) y el modelo de
rembg viene en la imagen, fijado por SHA-256, sin descargas en ejecución (D-96).

## Web y descargas

Los modelos locales (rembg, faster-whisper) van dentro de las imágenes con su SHA-256 y los workers no los descargan al ejecutar (`HF_HUB_OFFLINE=1`; no tienen salida a internet). `Permissions-Policy` sin cámara salvo en escaner-pdf y crear-collage (`camera=(self)`, D-76 y D-105). CSP con nonce por petición, `frame-ancestors 'none'`, Turnstile solo en páginas que suben archivos, HSTS con
`includeSubDomains`, `Permissions-Policy` sin cámara ni micrófono (12.4). `files.` responde con
`Content-Security-Policy: default-src 'none'; sandbox`, `Content-Disposition: attachment`, `nosniff`,
`Cross-Origin-Resource-Policy: same-site` y CORS solo para la web.

## Abuso

Límite por minuto por IP en la API y en `pre-create` (por IP y por usuario), tokens anónimos por IP y día, cuotas por
plan y por clase de coste, IPv6 agrupada por /64 y `CF-Connecting-IP` solo desde rangos de Cloudflare.

## Riesgos aceptados y pendientes

- Sin Docker en el entorno de desarrollo de esta entrega: falta comprobar en el VPS que Coolify conserva `runtime`,
  `read_only`, `cap_drop`, límites y redes internas (12.2).
- `style-src 'unsafe-inline'` (D-09).

## Compartir y servicios de terceros (8.2.4)

- «Enviar por correo» solo para cuentas con el correo verificado; el plan gratuito solo a su propia dirección y Pro
  hasta 3 destinatarios; Turnstile y `MAIL_SHARE_DAILY_LIMIT` por usuario y día. El correo lleva un enlace a
  `files./s/<id>/<archivo>?t=<token>` que caduca a las 24 horas; en la base de datos solo se guarda el hash del token, y
  Caddy pregunta a `apiint` antes de servirlo. Nunca se adjunta el archivo.
- Google Drive y Dropbox: el navegador habla directamente con ellos (ámbito `drive.file`); ninguna credencial pasa por
  el servidor. Sus dominios solo entran en la CSP de las páginas de herramientas cuando su flag está activo y hay claves.

## Redacción y enlaces de PDF en el navegador (G1-A)

- redactar-pdf, con los dos métodos, borra del archivo los objetos a los que ya no llega nada (el contenido sustituido
  seguiría dentro del PDF aunque no se viera) y comprueba el resultado antes de entregarlo; con «eliminar», además, que
  bajo cada área no se dibuja nada antes de pintar los recuadros (D-153).
- lector-pdf solo hace pulsables los enlaces `http`, `https` y `mailto`, en una pestaña nueva con
  `noopener noreferrer`; `javascript:`, `file:` y las acciones de lanzar programas se ignoran (D-152).

