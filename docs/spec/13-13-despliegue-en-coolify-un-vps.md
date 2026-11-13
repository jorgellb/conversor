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
