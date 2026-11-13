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
