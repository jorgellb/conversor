# Despliegue en Coolify (13)

## 1. Requisitos y preparación del VPS

Ubuntu Server LTS, 8 vCPU dedicadas, 32 GB de RAM y 400 GB de NVMe para F1 a F4 (3.1); con el vídeo de F5 y el 3D de F7,
16 vCPU y 64 GB, con las variables de `python scripts/gen_coolify_compose.py --profile 16` (`workermesh` y `workercad`
con 4 GB cada uno, D-259). Usuario con clave SSH, sin
acceso por contraseña, `unattended-upgrades`, swap de 8 GB con `vm.swappiness=10`. Si hay disco de bloques, móntalo en
`/srv/conversor` (ver «Volúmenes»).

Cortafuegos del proveedor: 22 desde las IP de administración y 80/443 solo desde los rangos de Cloudflare. Si el
proveedor no tiene cortafuegos, usa la cadena `DOCKER-USER` (Docker se salta UFW). El cron semanal que actualiza los
rangos está en `OPERATIONS.md`.

## 2. Coolify

Instala Coolify v4 con su script oficial y la versión estable fijada. Pon el panel detrás de su dominio y de Cloudflare
Access y cierra después 8000, 6001 y 6002. Opcional: gVisor (`runsc`) y `WORKER_RUNTIME=runsc`.

## 3. Registro de imágenes

Las imágenes son privadas (GHCR). En el VPS: `docker login ghcr.io` con un token de solo lectura (`read:packages`).
Las publica `.github/workflows/images.yml` con etiquetas de versión (`v0.1.0` → `0.1.0`) y `sha-<commit>`. Sin GitHub
Actions (por ejemplo, si la cuenta no tiene minutos), se construyen y suben las mismas 14 imágenes desde cualquier máquina
con Docker y buildx: `docker login ghcr.io` con un token `write:packages` y
`GHCR_OWNER=<propietario> IMAGE_TAG=0.1.0 sh scripts/build_push_images.sh` (unos 60 GB de disco y una o dos horas).

## 4. Alta del recurso

Proyecto `{{PRODUCTO}}`, entorno `production`, recurso Docker Compose desde el repositorio, archivo
`docker-compose.coolify.yml`. Dominios: `web` → `{{DOMINIO}}`, `api` → `api.{{DOMINIO}}`, `upload` →
`upload.{{DOMINIO}}`, `files` → `files.{{DOMINIO}}` (variables `SERVICE_URL_*`).

## 5. Variables

Coolify genera `SERVICE_USER_POSTGRES`, `SERVICE_PASSWORD_POSTGRES`, `SERVICE_PASSWORD_VALKEY`,
`SERVICE_PASSWORD_64_AUTH`, `SERVICE_PASSWORD_64_FILES`, `SERVICE_PASSWORD_64_ANON`, `SERVICE_PASSWORD_64_JOBSECRETS` y
`SERVICE_PASSWORD_WORKERDB`. Debes darle: `GHCR_OWNER`, `IMAGE_TAG`, `APP_NAME`, `ADMIN_EMAILS`, `SMTP_URL`, `MAIL_FROM`,
`TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` y, para pagos, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
`STRIPE_PRICE_PRO_MONTHLY` y `STRIPE_PRICE_PRO_YEARLY`. El resto tiene valor por defecto (sección 14).

## 6. Cloudflare

DNS con proxy para el dominio y `api`, `upload` y `files`; SSL Full (strict) con certificado de origen; WAF sin bloquear
los webhooks de Stripe (`/v1/billing/webhook`) ni a los servidores de Dropbox cuando se active; widget de Turnstile; caché
de HTML de herramientas sin cookie de sesión con purga en cada despliegue.

## 7. Primer despliegue y administrador

Orden automático: `prepare` → `migrateauth` → `migrate` → servicios. Regístrate en la web con `{{EMAIL_ADMIN}}`
(incluido en `ADMIN_EMAILS`, la API lo trata como administrador) y entra en `/es/admin`.

## 8. OpenRouter

Llega con F3.

## 9. Copias, restauración y actualización

Tarea programada de Coolify en `apiint` cada 6 horas con tiempo máximo 3.600 s: `python -m app.ops.backup`. Restaurar:
`python -m app.ops.restore /srv/backups/postgres/<archivo>.dump`. Actualizar: nueva etiqueta en `IMAGE_TAG`, despliegue
en horas valle (los workers paran en caliente hasta 10 minutos).

## 10. Disco lleno

La guarda rechaza subidas al 85 % de uso o con menos de `DISK_MIN_FREE_GB` libres y avisa por correo. Ver
`OPERATIONS.md`.

## 11. Pagos en producción

Alta en OSS si procede, Stripe Tax, claves en vivo, precios definitivos y textos de términos y reembolsos revisados.

## Volúmenes

`filestore` y `backups` son volúmenes con nombre. Para usar el disco dedicado, cámbialos a *bind mounts* sobre
`/srv/conversor/files` y `/srv/conversor/backups` con propietario 10001. Crecer a un segundo servidor exigiría
almacenamiento compartido (NFS u otro): fuera de alcance (4.7).

## Límite del CDN

Las condiciones de Cloudflare no permiten servir vídeo ni una proporción desproporcionada de archivos grandes desde el
CDN. Si el volumen servido por `files` crece, el plan B es servir `files.` sin proxy de Cloudflare (DNS gris) con su
propio certificado y límite de ritmo en Caddy.
