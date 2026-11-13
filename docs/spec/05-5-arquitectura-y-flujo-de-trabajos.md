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
