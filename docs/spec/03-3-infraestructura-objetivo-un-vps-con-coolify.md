## 3. Infraestructura objetivo: un VPS con Coolify

### 3.1 Servidor

- Ubuntu Server LTS actual, Docker instalado por el script oficial de Coolify y Coolify v4, con la versión estable fijada, en el mismo servidor.
- Tamaño (estimación, no medida; ajústalo con las pruebas de carga de 16.1 y la tabla de 5.4):
  - De F1 a F4: 8 vCPU dedicadas, 32 GB de RAM y 400 GB de NVMe, con las concurrencias de la columna de 8 vCPU.
  - Catálogo completo (F5 a F7): 16 vCPU dedicadas, 64 GB de RAM y 1 TB de NVMe (o 400 GB de sistema más un volumen de 600 GB para archivos).
  - Con 16 GB de RAM, desactiva por flag Docling, el modelo `medium` de Whisper, el vídeo y los grupos `mesh` y `cad`.
  - Evita las vCPU compartidas: OCR, vídeo y Docling usan CPU de forma sostenida.
- Swap de 8 GB con `vm.swappiness=10`. Cada contenedor con `mem_limit` lleva `memswap_limit` igual, para que un worker que se pasa de memoria muera en lugar de paginar.
- `unattended-upgrades` activado.
- Cortafuegos:
  - Docker publica los puertos de los contenedores con reglas propias que UFW no filtra. Usa el cortafuegos del proveedor; si no existe, aplica las reglas en la cadena `DOCKER-USER` (o con ufw-docker) y documenta el método en `docs/DEPLOY.md`.
  - 22 solo desde las IP de administración.
  - 80 y 443 solo desde los rangos IP que publica Cloudflare, actualizados por un cron semanal del host, para que nadie se salte el WAF atacando la IP del servidor.
  - 8000, 6001 y 6002 (panel, tiempo real y terminal de Coolify) cerrados al público en cuanto el panel funcione con su dominio a través del proxy, protegido con Cloudflare Access.
- Si el proveedor lo permite, monta un volumen de bloques dedicado en `/srv/{{PRODUCTO}}` para archivos y copias. Así un disco lleno no tumba el sistema.
- Opcional: gVisor (`runsc`) instalado en el host para los workers que procesan archivos (secciones 12.1 y 13.1).

### 3.2 Servicios del stack

| Servicio | Imagen | Dominio | Función |
| --- | --- | --- | --- |
| `web` | propia (Next.js) | `{{DOMINIO}}` | Web, SEO, autenticación, panel de usuario y de administración |
| `api` | propia (FastAPI) | `api.{{DOMINIO}}` | API pública |
| `apiint` | misma imagen que `api` | ninguno (solo red interna) | Endpoints internos: ganchos de tusd, autorización de descargas, operaciones |
| `upload` | tusd oficial | `upload.{{DOMINIO}}` | Subidas reanudables a disco |
| `files` | Caddy oficial | `files.{{DOMINIO}}` | Descargas firmadas desde disco |
| `beat` | misma imagen que `api` | — | Tareas periódicas |
| `workerpdf`, `workerocr`, `workeroffice`, `workerconvert`, `workermedia`, `workerai`, `workersign`, `workerav`, `workerutils`, `workermesh`, `workercad` | propias por grupo | — | Workers de Celery |
| `gotenberg` | Gotenberg oficial | — | LibreOffice y Chromium para archivos subidos, sin ninguna salida de red |
| `gotenbergweb` | Gotenberg oficial | — | Chromium para web-a-pdf y captura-web; sale solo por `egressweb` y nunca recibe archivos de usuarios |
| `postgres` | PostgreSQL con pgvector | — | Base de datos |
| `valkey` | Valkey oficial | — | Broker de Celery, límites y cachés |
| `egressai` | Smokescreen oficial (`ghcr.io/stripe/smokescreen`) | — | Salida de `workerai`, solo hacia OpenRouter |
| `egressweb` | Smokescreen oficial | — | Salida de `gotenbergweb`, `workeroffice` y `workersign` hacia IP públicas |
| `umami` | Umami oficial (opcional) | `stats.{{DOMINIO}}` | Analítica sin cookies |
| `migrate` | misma imagen que `api` | — | Migraciones Alembic, una sola ejecución |
| `migrateauth` | misma imagen que `web` | — | Migraciones de Better Auth, una sola ejecución, antes de `migrate` |
| `mailpit` | Mailpit oficial | — | Correo de desarrollo; solo en `docker-compose.yml` |

### 3.3 Construcción de imágenes

- Las imágenes pesadas (LibreOffice, Docling con Torch solo CPU, OpenCascade, FFmpeg, Whisper) no se construyen en el VPS.
- GitHub Actions construye cada imagen, la etiqueta con la versión y el SHA, y la publica en GitHub Container Registry.
  - Solo se construyen las imágenes cuyo contexto ha cambiado (filtros por ruta) y con caché de capas.
  - El plan gratuito de GitHub incluye 2.000 minutos al mes para repositorios privados; si el consumo previsto lo supera, es una decisión con coste: pídela al propietario.
- Dos ficheros Compose:
  - `docker-compose.yml`: desarrollo local, con `build:`.
  - `docker-compose.coolify.yml`: producción, solo con `image:` y etiquetas fijas.
- En Coolify, el recurso Docker Compose apunta a `docker-compose.coolify.yml`. Las imágenes son siempre privadas: contienen el código cerrado y programas GPL (Calibre, pandoc y otros) cuya distribución pública obligaría a ofrecer su código fuente. En el VPS, inicia sesión en el registro con un token de solo lectura (`read:packages`) y documenta el paso en `docs/DEPLOY.md`.
- Imagen base común de Python con las dependencias compartidas, y una imagen por grupo de workers encima, para reducir disco y tiempo de compilación.
- Modelos (Whisper, Kokoro, embeddings, rembg, Docling) descargados en tiempo de compilación dentro de la imagen, nunca en tiempo de ejecución, porque los workers no tienen salida a internet.

---
