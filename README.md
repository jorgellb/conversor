# Producto Demo — herramientas PDF y conversor de archivos

Monorepo de la plataforma descrita en `docs/spec/` (versión 2 del plan). Esta entrega cubre **F1 completo**: núcleo,
lista de lanzamiento (17.1) y resto del catálogo F1. Lo que falta está en `docs/PROGRESS.md`.

- `apps/web`: Next.js 16 (App Router), next-intl (es y en), Better Auth, herramientas de navegador en un Web Worker.
- `apps/api`: FastAPI pública (`api`) e interna (`apiint`: ganchos de tusd, autorización de descargas y copias).
- `packages/core`: registro, almacenamiento, cuotas, guardas, tokens, Celery y modelos.
- `packages/tools`: especificaciones (sin motores) e implementaciones de servidor por grupo.
- `packages/client-tools`: herramientas de navegador en TypeScript (`@cantoo/pdf-lib`, PDFium).
- `packages/registry`: `registry.json` generado desde el registro de Python.
- `workers/Dockerfile`: imagen base común y una imagen por grupo; `apps/web/Dockerfile`: web y `migrateauth`.
- `infra/`: Caddy (descargas firmadas), tusd, Gotenberg y Smokescreen.

## Arranque local

Requisitos: Docker con Compose v2.

```bash
docker compose up --build
```

Web en http://localhost:3000, API en http://localhost:8000, correo de pruebas (Mailpit) en http://localhost:8025.
Usa `.env.example` y los dobles de 0.1: pagos falsos, claves de prueba de Turnstile y SMTP de Mailpit.

## Pruebas

```bash
uv venv .venv && uv pip install --python .venv -r pyproject.toml --extra pdf --extra ocr --extra office --extra dev
```

```bash
.venv/bin/pytest
```

`pytest` arranca un PostgreSQL y un Redis locales si no defines `TEST_DATABASE_URL` y `TEST_VALKEY_URL`; las pruebas
de OCR, LibreOffice y FFmpeg se saltan si falta el programa.

```bash
npm ci && npm test && npm run typecheck && npm run build
```

```bash
npx playwright test -c tests/e2e/playwright.config.ts --project=navegador
```

## Despliegue

Coolify v4 en un solo VPS con `docker-compose.coolify.yml`: pasos en `docs/DEPLOY.md` y comprobaciones de cierre en
`docs/DEPLOY-CHECKLIST.md`. Regenera los archivos derivados con:

```bash
python scripts/export_registry.py && python scripts/gen_coolify_compose.py && python scripts/gen_docs.py
```

## Documentación

`docs/PLAN.md`, `PROGRESS.md`, `DECISIONS.md`, `ARCHITECTURE.md`, `TOOLS.md`, `LICENSES.md`, `LEGAL.md`,
`SECURITY.md`, `DEPLOY.md`, `DEPLOY-CHECKLIST.md`, `OPERATIONS.md`, `ERRORS.md` y `spec/` (el plan troceado).
