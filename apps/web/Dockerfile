# syntax=docker/dockerfile:1.7
# Web (Next.js standalone) y migrateauth en la misma imagen (3.2).
ARG NODE_IMAGE=node:22.23.4-bookworm-slim

FROM ${NODE_IMAGE} AS deps
WORKDIR /repo
COPY package.json package-lock.json ./
COPY packages/registry/package.json packages/registry/
COPY packages/client-tools/package.json packages/client-tools/
COPY apps/web/package.json apps/web/
RUN npm ci --no-audit --no-fund

FROM deps AS build
ENV NEXT_TELEMETRY_DISABLED=1
COPY packages/registry packages/registry
COPY packages/client-tools packages/client-tools
COPY apps/web apps/web
RUN npm run build -w @conversor/web

# Dependencias mínimas del script de migración de Better Auth.
FROM ${NODE_IMAGE} AS migrate-deps
WORKDIR /migrate
COPY --from=deps /repo/node_modules/better-auth/package.json /tmp/ba.json
RUN npm init -y >/dev/null && npm install --no-audit --no-fund --omit=dev \
      "better-auth@$(node -p "require('/tmp/ba.json').version")" pg@8.23.1

FROM ${NODE_IMAGE} AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
RUN groupadd -g 10001 app && useradd -u 10001 -g app -m -d /home/app -s /usr/sbin/nologin app
COPY --from=build --chown=app:app /repo/apps/web/.next/standalone ./
COPY --from=build --chown=app:app /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=app:app /repo/apps/web/public ./apps/web/public
COPY --from=migrate-deps --chown=app:app /migrate/node_modules ./migrate/node_modules
COPY --chown=app:app apps/web/scripts/migrate-auth.mjs ./migrate/migrate-auth.mjs
COPY --chown=app:app apps/web/content ./apps/web/content
USER app
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
