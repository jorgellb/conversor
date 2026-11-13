## 15. Estructura del repositorio

```text
.
├── apps/
│   ├── web/                    # Next.js: páginas, herramientas cliente, auth, admin
│   └── api/                    # FastAPI: app pública, app interna, ops
├── packages/
│   ├── core/                   # Python: registro, almacenamiento, límites, IA
│   ├── registry/               # registry.json y JSON Schema generados (5.2)
│   ├── tools/                  # Python: <grupo>/<slug>/spec.py e impl.py
│   └── client-tools/           # TypeScript: herramientas de navegador en Web Workers
├── workers/                    # Dockerfiles por grupo y arranque de Celery
├── config/
│   └── plans.yaml              # límites por plan (9.3)
├── infra/
│   ├── caddy/Caddyfile
│   ├── smokescreen/
│   │   ├── acl-ai.yaml
│   │   └── acl-web.yaml
│   ├── gotenberg/              # flags de gotenberg y gotenbergweb (12.2)
│   └── tusd/
├── scripts/                    # check_licenses.py, license_policy.yaml, check_images.sh, export_registry.py, fixtures/
├── tests/                      # pytest, fixtures, e2e con Playwright, k6
├── docs/
│   └── spec/                   # este documento troceado (sección 1)
├── docker-compose.yml          # desarrollo, con Mailpit y los dobles de 0.1
├── docker-compose.coolify.yml  # producción
└── .env.example
```

---
