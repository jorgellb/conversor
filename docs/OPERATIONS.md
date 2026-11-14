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

Las cuatro de `core.maintenance` van a la cola `maintenance` y las ejecuta el propio contenedor `beat`
(`celery worker -B -Q maintenance --pool solo`), con el usuario principal de la base de datos y salida SMTP; las de IA, en
`workerai`. Antes caían en la cola `pdf` y `workerpdf`, con el usuario restringido, no podía borrar `uploads` (D-181).

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

## Prueba de carga (16.1, D-146, D-148 y D-149)

Escenario en `tests/load/escenarios.json` (comprobado por `tests/test_carga_k6.py`): 50 comprimir-pdf y 10 ogg-a-mp3 a
la vez, y un pico de 300 trabajos ligeros en 5 minutos desde 100 clientes. Cada trabajo abre su propia sesión anónima
(360 en total), para que la idempotencia no devuelva un trabajo ya hecho en vez de encolar uno nuevo. Pasa si las
páginas siguen por debajo de 1 s (p99), la espera en cola no supera `QUEUE_MAX_WAIT_SECONDS_<GRUPO>` (120 s en pdf y
300 s en av) porque antes aparece `QUEUE_FULL`, y no hay trabajos fallidos o reutilizados, llegadas descartadas,
`RATE_LIMITED` ni `QUOTA_EXCEEDED` (tampoco de los hooks de tusd) ni ninguna comprobación fallida. Cada llegada termina
como trabajo creado o como `QUEUE_FULL`: una sesión, una subida o una creación rechazadas cuentan como trabajo fallido,
con el motivo y el estado HTTP como etiquetas en `resultados-k6.json`. Un trabajo que sigue en cola pasado el umbral se
anota en ese momento; uno que no termina en la espera máxima más `proceso_max_s` (300 s), o con 5 sondeos seguidos sin
200, cuenta como fallido. El pico empieza con 100 clientes y k6 puede subir hasta 420 (una llegada por segundo × 420 s
de plazo por trabajo), para que una espera larga pero dentro del umbral no descarte llegadas.

1. Muestras: `python scripts/fixtures/generate.py /tmp/muestras` (necesita FFmpeg para `voz.ogg`).
2. Todos los clientes virtuales salen de una IP, y los anónimos cuentan sesiones y tareas también por IP (9.3). Durante
   la prueba se ponen los valores de `limites_durante_la_prueba` de `escenarios.json`, mejor fuera de horas de uso:
   - En Coolify: `RATE_LIMIT_PER_MINUTE=100000`, `ANON_TOKENS_PER_IP_DAY=1000` y las claves de prueba de Turnstile de
     `.env.example` (`TURNSTILE_SITE_KEY` y `TURNSTILE_SECRET_KEY`).
   - La cuota diaria de tareas ligeras del plan anónimo, que vive en la tabla `plans` (no tiene variable y, después de
     sembrarla desde `config/plans.yaml`, se edita en la base). En la terminal del contenedor `postgres`, primero se
     anota el valor actual:
     `psql -U "$POSTGRES_USER" -d conversor -tAc "SELECT limits->'light_tasks_day' FROM plans WHERE id = 'anon'"`
     (20 si nunca se ha cambiado, el valor de `config/plans.yaml`), y después se sube:
     `psql -U "$POSTGRES_USER" -d conversor -c "UPDATE plans SET limits = jsonb_set(limits, '{light_tasks_day}', '1000') WHERE id = 'anon'"`.
     Con 20, desde el trabajo 21 la API responde `QUOTA_EXCEEDED`. El contador es por día: una segunda ejecución el
     mismo día suma otras 360 tareas y otras 360 sesiones.

   Al terminar se vuelven a poner los valores de producción, también la cuota con el valor anotado:
   `psql -U "$POSTGRES_USER" -d conversor -c "UPDATE plans SET limits = jsonb_set(limits, '{light_tasks_day}', '<valor anotado>') WHERE id = 'anon'"`.
3. En el servidor, mientras dura la prueba: `DATOS=/srv/files sh tests/load/recursos.sh recursos-k6.csv` (CPU y RAM por
   contenedor con `docker stats`, y disco de los archivos con `df`, cada 5 s; se para con Ctrl+C).
4. Desde otra máquina: `k6 run -e API=https://api.{{DOMINIO}} -e UPLOAD=https://upload.{{DOMINIO}}/files/
   -e WEB=https://{{DOMINIO}} -e FIXTURES=/tmp/muestras -e SALIDA=resultados-k6.json tests/load/k6.js`.
5. Anotar aquí el resumen que imprime k6 (páginas, espera por grupo, tiempos, `QUEUE_FULL`), el máximo de CPU y RAM de
   cada worker y el disco de `recursos-k6.csv`, y ajustar las concurrencias de 5.4 si sobra o falta CPU.

## Perfiles de 8 y 16 vCPU (5.4, D-138)

`docker-compose.coolify.yml` trae el perfil de 8 vCPU y 32 GB (suma de `mem_limit` de 36,75 GB, dentro del 15 % sobre la
RAM). Cada valor se cambia en las variables de Coolify, sin editar el archivo:

- `MEM_<NOMBRE>`: `mem_limit` y `memswap_limit` de `postgres`, `gotenberg`, `gotenbergweb` y cada worker.
- `CPUS_<NOMBRE>` y `CONCURRENCY_<NOMBRE>`: `cpus` y procesos de cada worker (`cpus` = concurrencia × hilos).

`<NOMBRE>` es el del worker en mayúsculas (`PDF`, `OCR`, `OFFICE_LIGHT`, `OFFICE_HEAVY`, `MEDIA`, `CONVERT`, `AV_LIGHT`,
`AV_HEAVY`, `AI`, `AI_EMBED`). Para un VPS de 16 vCPU y 64 GB (el catálogo completo, D-128), pega estas variables, que
imprime `python scripts/gen_coolify_compose.py --profile 16` (unos 52 GB en total hoy; los workers de F4, F6 y F7 se
suman con su fase sin pasar de 73,6 GB):

```
MEM_POSTGRES=4g
MEM_GOTENBERG=4g
MEM_GOTENBERGWEB=2g
CONCURRENCY_AI=6
MEM_AI=1536m
CPUS_AI=6
CONCURRENCY_AI_EMBED=1
MEM_AI_EMBED=1536m
CPUS_AI_EMBED=1
CONCURRENCY_PDF=6
MEM_PDF=6g
CPUS_PDF=6
CONCURRENCY_OCR=2
MEM_OCR=6g
CPUS_OCR=4
CONCURRENCY_OFFICE_LIGHT=2
MEM_OFFICE_LIGHT=2g
CPUS_OFFICE_LIGHT=2
CONCURRENCY_OFFICE_HEAVY=1
MEM_OFFICE_HEAVY=2g
CPUS_OFFICE_HEAVY=1
CONCURRENCY_MEDIA=3
MEM_MEDIA=4g
CPUS_MEDIA=3
CONCURRENCY_CONVERT=1
MEM_CONVERT=8g
CPUS_CONVERT=2
CONCURRENCY_AV_LIGHT=2
MEM_AV_LIGHT=3g
CPUS_AV_LIGHT=4
CONCURRENCY_AV_HEAVY=1
MEM_AV_HEAVY=3g
CPUS_AV_HEAVY=2
```

Tras cambiar el perfil, comprobar en el panel que ningún worker se reinicia por memoria durante la prueba k6 y anotar aquí
las concurrencias medidas.

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
