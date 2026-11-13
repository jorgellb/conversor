# Operación

## Tareas periódicas (Celery beat)

| Tarea | Frecuencia | Qué hace |
| --- | --- | --- |
| `cleanup_expired` | 5 min | Borra trabajos vencidos, subidas `rejected` o sin terminar de más de 24 h y comparticiones vencidas |
| `requeue_stale` | 1 min | Reencola trabajos `running` sin latido desde hace 3 min; al tercer intento, `WORKER_LOST` |
| `disk_alert` | 5 min | Avisa por correo (máximo una vez por hora) si la guarda de disco está activa |
| `find_orphans` | diaria 04:17 | Directorios sin fila y filas vivas sin directorio |
| `core.ai.tasks.refresh_models` | al arrancar `workerai` y cada `LLM_MODELS_REFRESH_HOURS` (6 h) | `GET /models` de OpenRouter: guarda los modelos de precio 0 en `llm_models` y recalcula la tasa de éxito de 7 días |
| `core.ai.tasks.reconcile` | 10 min | `GET /key`: si OpenRouter cuenta más peticiones gratuitas que el contador propio, este sube; si le quedan menos de 20, solo Pro usa IA |

`cleanup_expired` también borra el texto extraído y la caché de IA caducados, y las filas de `ai_requests` de más de 90 días.

## Copias

- Base de datos: `python -m app.ops.backup` en `apiint` cada 6 horas (tarea de Coolify, 3.600 s). `pg_dump -Fc` a
  `/srv/backups/postgres/`, retención `BACKUP_RETENTION_DAYS`, restic con 7 diarias, 4 semanales y 6 mensuales. Dos
  fallos seguidos avisan a `ADMIN_EMAILS`.
- Cron del host (no Coolify): volcado cifrado de las variables del recurso y de `/data/coolify/source/.env`, y
  `pg_dump` de `coolify-db`, por ejemplo cada noche con `age` o `gpg` hacia el mismo repositorio de restic.
- Restauración completa en un VPS nuevo (objetivo menor de 4 horas): instalar Coolify, recuperar el `.env` de Coolify
  y las variables del recurso, desplegar con `IMAGE_TAG` conocido, parar `web`, `api` y workers,
  `python -m app.ops.restore <copia>` en `apiint` y arrancar. Simulacro trimestral.

## Rangos de Cloudflare (cron semanal del host)

Descarga `https://www.cloudflare.com/ips-v4` y `ips-v6` y regenera las reglas del cortafuegos para 80/443. Si cambian,
actualiza también `CLOUDFLARE_IP_RANGES` (o `packages/core/core/clientip.py`).

## Disco lleno

1. `/readyz` y `/es/admin` muestran uso, reservas y guarda.
2. Lanza la purga desde el panel (o espera a `cleanup_expired`).
3. Si sigue lleno, baja `FILE_TTL_USER_HOURS` temporalmente o amplía el volumen. Las herramientas de navegador siguen
   funcionando mientras la guarda está activa.

## Colas llenas

`QUEUE_FULL` aparece cuando la espera estimada supera `QUEUE_MAX_WAIT_SECONDS_<GRUPO>` (Pro al doble). Sube
`CONCURRENCY_<GRUPO>` solo si hay CPU libre (`cpus` = concurrencia × hilos) y anota el cambio aquí.

## Concurrencias medidas

Pendiente de la prueba de carga k6 en el VPS (16.1). Valores por defecto de 5.4 para 8 vCPU.

## Logs

JSON en la salida estándar, rotados por Docker (10 MB × 5). Nunca contienen contraseñas ni tokens: las contraseñas de
PDF viajan cifradas y los tokens de descarga solo aparecen en la URL que recibe el navegador.

## Cuenta de OpenRouter (6.1 y 13.3)

1. Crear la cuenta de la empresa en openrouter.ai. Una sola clave: el límite es global de la cuenta y más claves o
   cuentas no suman.
2. Compra única de 10 créditos (decisión con coste del propietario, 0.1): sube el límite de modelos gratuitos de 50 a
   1.000 peticiones al día (20 por minuto en los dos casos, comprobado el 05/11/2026). Mantener el saldo en positivo: con
   saldo negativo OpenRouter puede devolver 402 también en los modelos gratuitos.
3. Ajustes de privacidad de la cuenta: no permitir proveedores que entrenan con los datos ni que publican las
   peticiones, tanto para modelos gratuitos como de pago. Además, cada petición lleva `provider.data_collection: "deny"`.
4. Crear la clave y ponerla solo en `workerai` (`OPENROUTER_API_KEY` en Coolify). Sin clave, las herramientas de IA se ven
   «no disponibles temporalmente» y el resto del servicio sigue igual.
5. Comprobar en el panel de administración (IA) que aparecen modelos tras el primer descubrimiento y que la
   reconciliación muestra `free_model_daily_requests`.

El saldo de la cuenta (`GET /credits`) solo lo puede leer una clave de gestión, que no se guarda en el servidor: el panel
muestra lo que da `/key` (uso, límite de la clave y peticiones gratuitas del día) y el saldo se mira en openrouter.ai.

## Embeddings de chat-pdf

- `workeraiembed` (cola `ai.embed`): 1 proceso con el modelo cargado (0,6 GB en reposo y 0,7 GB al calcular en lotes de
  16) y 1,25 GB de `mem_limit`.
  Un documento de 150 páginas tarda alrededor de un minuto en prepararse con un hilo (medido: 18 fragmentos por segundo).
- El modelo va dentro de la imagen `worker-ai` (`/opt/models/embeddings`, `infra/embeddings/fetch-model.sh`); si falta,
  preparar falla con `ENGINE_FAILED` y no se descarga nada.
- Si las preguntas de documentos largos esperan mucho, es que `ai.embed` está ocupada preparando documentos: sube
  `CONCURRENCY_AI_EMBED` (y la memoria del servicio, 1 GB por proceso).

## IA agotada o no disponible

- `AI_BUDGET_EXHAUSTED`: se ha llegado a `AI_DAILY_BUDGET` (o, sin ser Pro, a `AI_DAILY_BUDGET - AI_PRO_RESERVE`). Se
  reinicia a las 00:00 UTC; el mensaje da la hora en Madrid. No subir el presupuesto por encima del límite de OpenRouter.
- `AI_UNAVAILABLE` sin peticiones: ningún modelo cumple lo que pide la herramienta (contexto, salida, imagen). Mirar en el
  panel si el descubrimiento ha fallado (clave, salida por `egressai`) o si los modelos están pausados (24 h tras un fallo
  de `data_collection`).
- Muchos `rate_limited` en `ai_requests`: bajar `AI_RPM_LIMIT` o fijar modelos menos usados en `LLM_PREFERRED_MODELS`.
