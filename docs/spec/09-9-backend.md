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
