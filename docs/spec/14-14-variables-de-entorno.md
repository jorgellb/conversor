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
