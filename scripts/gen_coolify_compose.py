"""Genera docker-compose.coolify.yml (13.2) sin anclas YAML, que Coolify no siempre respeta.

Uso: `python scripts/gen_coolify_compose.py` y, en la CI, `--check` para fallar si el archivo no está al día.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docker-compose.coolify.yml"

# Beat programa las tareas y además ejecuta las de mantenimiento, con el usuario principal de la base de datos (D-181).
BEAT_COMMAND = ["celery", "-A", "core.celeryapp", "worker", "-B", "-Q", "maintenance", "--pool", "solo", "-n", "beat@%h",
                "--pidfile", "/tmp/beat.pid", "-s", "/tmp/celerybeat-schedule"]
LOG = {"driver": "json-file", "options": {"max-size": "10m", "max-file": "5"}}
IMG = "ghcr.io/${GHCR_OWNER:?Propietario del registro}/conversor-NAME:${IMAGE_TAG:?Etiqueta de imagen}"
DB = "postgresql+psycopg://${SERVICE_USER_POSTGRES}:${SERVICE_PASSWORD_POSTGRES}@postgres:5432/conversor"
VK = "redis://default:${SERVICE_PASSWORD_VALKEY}@valkey:6379/0"
WDB = "postgresql+psycopg://conversor_worker:${SERVICE_PASSWORD_WORKERDB}@postgres:5432/conversor"
FS = ["filestore:/srv/files"]

PUBLIC = {
    "APP_ENV": "production",
    "APP_NAME": "${APP_NAME:?Nombre del producto}",
    "PUBLIC_WEB_URL": "${SERVICE_URL_WEB}",
    "PUBLIC_API_URL": "${SERVICE_URL_API}",
    "PUBLIC_UPLOAD_URL": "${SERVICE_URL_UPLOAD}/files/",
    "PUBLIC_FILES_URL": "${SERVICE_URL_FILES}",
    "BETTER_AUTH_URL": "${SERVICE_URL_WEB}",
    "LOG_LEVEL": "${LOG_LEVEL:-INFO}",
}
LIMITS = {
    "MAIL_SHARE_DAILY_LIMIT": "${MAIL_SHARE_DAILY_LIMIT:-10}",
    "DISK_MAX_USAGE_PERCENT": "${DISK_MAX_USAGE_PERCENT:-85}",
    "DISK_MIN_FREE_GB": "${DISK_MIN_FREE_GB:-20}",
    "DISK_RESERVE_FACTOR": "${DISK_RESERVE_FACTOR:-3}",
    "QUEUE_MAX_WAIT_SECONDS_PDF": "${QUEUE_MAX_WAIT_SECONDS_PDF:-120}",
    "CLIENT_MAX_MB": "${CLIENT_MAX_MB:-100}",
    "FILE_TTL_ANON_MINUTES": "${FILE_TTL_ANON_MINUTES:-60}",
    "FILE_TTL_USER_HOURS": "${FILE_TTL_USER_HOURS:-24}",
    "UPLOAD_MAX_BYTES": "${UPLOAD_MAX_BYTES:-1073741824}",
    "DOWNLOAD_TOKEN_MINUTES": "${DOWNLOAD_TOKEN_MINUTES:-15}",
    "RATE_LIMIT_PER_MINUTE": "${RATE_LIMIT_PER_MINUTE:-60}",
    "ANON_TOKENS_PER_IP_DAY": "${ANON_TOKENS_PER_IP_DAY:-10}",
    "TRUST_CF_CONNECTING_IP": "${TRUST_CF_CONNECTING_IP:-true}",
    "IMAGE_MAX_PIXELS": "${IMAGE_MAX_PIXELS:-100000000}",
    "RENDER_MAX_PIXELS": "${RENDER_MAX_PIXELS:-50000000}",
    "GOTENBERG_URL": "http://gotenberg:3000",
    "ADMIN_EMAILS": "${ADMIN_EMAILS:?Correo del administrador}",
    "HEVC_DECODE_ENABLED": "${HEVC_DECODE_ENABLED:-false}",
    "INVOICING_ES_ENABLED": "${INVOICING_ES_ENABLED:-false}",
}
MAIL = {"SMTP_URL": "${SMTP_URL:?URL SMTP}", "MAIL_FROM": "${MAIL_FROM:?Remitente}"}
# IA (6.3 y 14): los límites los leen la API (reserva al encolar), beat (calendario), workerai (peticiones) y
# workeravheavy, que reserva las de traducir-subtitulos y resumir-reunion antes de transcribir (F3-E, D-174).
AI = {
    "LLM_PREFERRED_MODELS": "${LLM_PREFERRED_MODELS:-}",
    "LLM_FALLBACK_ROUTER": "${LLM_FALLBACK_ROUTER:-openrouter/free}",
    "LLM_MODELS_REFRESH_HOURS": "${LLM_MODELS_REFRESH_HOURS:-6}",
    "AI_DAILY_BUDGET": "${AI_DAILY_BUDGET:-950}",
    "AI_PRO_RESERVE": "${AI_PRO_RESERVE:-400}",
    "AI_RPM_LIMIT": "${AI_RPM_LIMIT:-18}",
    "AI_BUDGET_RESET_TZ": "${AI_BUDGET_RESET_TZ:-UTC}",
    "AI_REQUIRE_CONSENT": "true",
    "AI_CHAT_RPM_SHARE": "${AI_CHAT_RPM_SHARE:-0.5}",
    "AI_TASK_MAX_REQUESTS": "${AI_TASK_MAX_REQUESTS:-20}",
}

# Voz de pdf-a-audio (6.4 y 14): la leen la API (no encola un idioma sin voz) y workeravheavy. La española se queda vacía
# hasta la escucha del propietario (docs/DEPLOY-CHECKLIST.md).
TTS = {"TTS_ENGINE": "${TTS_ENGINE:-kokoro}", "TTS_VOICE_ES": "${TTS_VOICE_ES:-}", "TTS_VOICE_EN": "${TTS_VOICE_EN:-af_heart}"}


GOTENBERG = "gotenberg/gotenberg:8.39.0"
# Smokescreen v0.1.0 (18-09-2026) compilado por images.yml desde infra/smokescreen/Dockerfile: Stripe no publica imagen (D-155).
SMOKESCREEN = "ghcr.io/${GHCR_OWNER:?Propietario del registro}/conversor-smokescreen:${IMAGE_TAG:?Etiqueta de imagen}"
# 12.2: egressweb niega IP privadas, de enlace local, CGNAT y de las redes de Docker.
DENY_RANGES = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16", "fc00::/7", "fe80::/10"]


def img(name: str) -> str:
    return IMG.replace("NAME", name)


def hc(test: list[str], interval: str = "30s", start: str = "30s") -> dict:
    return {"test": test, "interval": interval, "timeout": "10s", "retries": 3, "start_period": start}


def py_hc(port: int) -> dict:
    code = f"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:{port}/healthz',timeout=5).status==200 else 1)"
    return hc(["CMD", "python", "-c", code])


def env_name(name: str) -> str:
    return name.upper().replace("-", "_")


def memory(name: str, default: str) -> dict:
    """`mem_limit` y `memswap_limit` sobreescribibles con `MEM_<NOMBRE>` (5.4): el valor por defecto es el perfil de
    8 vCPU y 32 GB; el de 16 vCPU y 64 GB está en docs/OPERATIONS.md (D-138)."""
    value = f"${{MEM_{env_name(name)}:-{default}}}"
    return {"mem_limit": value, "memswap_limit": value}


# Perfil de 16 vCPU y 64 GB (5.4; con workerai y workeraiembed repartidos como en D-128): variables para Coolify que
# imprime `--profile 16` y que se documentan en docs/OPERATIONS.md. Los nombres son los de los servicios sin
# «worker». Los grupos de F4, F6 y F7 (sign, utils, mesh y cad) se añaden con su fase.
PROFILE_16 = {
    "MEM_POSTGRES": "4g", "MEM_GOTENBERG": "4g", "MEM_GOTENBERGWEB": "2g",
    "CONCURRENCY_AI": "6", "MEM_AI": "1536m", "CPUS_AI": "6",
    "CONCURRENCY_AI_EMBED": "1", "MEM_AI_EMBED": "1536m", "CPUS_AI_EMBED": "1",
    "CONCURRENCY_PDF": "6", "MEM_PDF": "6g", "CPUS_PDF": "6",
    "CONCURRENCY_OCR": "2", "MEM_OCR": "6g", "CPUS_OCR": "4",
    "CONCURRENCY_OFFICE_LIGHT": "2", "MEM_OFFICE_LIGHT": "2g", "CPUS_OFFICE_LIGHT": "2",
    "CONCURRENCY_OFFICE_HEAVY": "1", "MEM_OFFICE_HEAVY": "2g", "CPUS_OFFICE_HEAVY": "1",
    "CONCURRENCY_MEDIA": "3", "MEM_MEDIA": "4g", "CPUS_MEDIA": "3",
    "CONCURRENCY_CONVERT": "1", "MEM_CONVERT": "8g", "CPUS_CONVERT": "2",
    "CONCURRENCY_AV_LIGHT": "2", "MEM_AV_LIGHT": "3g", "CPUS_AV_LIGHT": "4",
    "CONCURRENCY_AV_HEAVY": "1", "MEM_AV_HEAVY": "3g", "CPUS_AV_HEAVY": "2",
    "CONCURRENCY_SIGN_VERIFY": "1", "MEM_SIGN_VERIFY": "1g", "CPUS_SIGN_VERIFY": "1",
    "CONCURRENCY_SIGN": "1", "MEM_SIGN": "1g", "CPUS_SIGN": "1",
}


def svc(image: str, **kw) -> dict:
    return {"image": image, "restart": "unless-stopped", "logging": LOG, **kw}


def worker(target: str, role: str, name: str, queue: str, conc: int, threads: int, mem: str, cpus: int,
           extra_env: dict | None = None, secrets: bool = False, networks: list[str] | None = None,
           volumes: list[str] | None = None) -> dict:
    env = {
        "SERVICE_ROLE": role, "WORKER_NAME": name, "APP_ENV": "production", "VALKEY_URL": VK, "DATABASE_URL_WORKER": WDB,
        "THREADS": str(threads), "OMP_THREAD_LIMIT": str(threads), "OMP_NUM_THREADS": str(threads),
        "IMAGE_MAX_PIXELS": "${IMAGE_MAX_PIXELS:-100000000}", "RENDER_MAX_PIXELS": "${RENDER_MAX_PIXELS:-50000000}",
        "LOG_LEVEL": "${LOG_LEVEL:-INFO}",
    }
    if secrets:
        env["JOB_SECRETS_KEY"] = "${SERVICE_PASSWORD_64_JOBSECRETS}"
    env.update(extra_env or {})
    var = "CONCURRENCY_" + env_name(name)
    cmd = ["celery", "-A", "core.celeryapp", "worker", "-Q", queue, "-n", f"{name}@%h", "-c", f"${{{var}:-{conc}}}",
           "--prefetch-multiplier", "1", "-O", "fair", "--without-gossip", "--without-mingle"]
    ping = 'celery -A core.celeryapp inspect ping -d "$${WORKER_NAME}@$${HOSTNAME}" --timeout 10 >/dev/null'
    return svc(
        img(target), command=cmd, environment=env, volumes=FS + (volumes or []), networks=networks or ["internal"], user="10001:10001",
        read_only=True, tmpfs=["/tmp:size=64m"], cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
        pids_limit=256, **memory(name, mem), cpus=f"${{CPUS_{env_name(name)}:-{cpus}}}", oom_score_adj=500,
        stop_grace_period="10m",
        runtime="${WORKER_RUNTIME:-runc}",
        depends_on={"migrate": {"condition": "service_completed_successfully"}, "valkey": {"condition": "service_healthy"}},
        healthcheck=hc(["CMD-SHELL", ping], "60s", "90s"),
    )


def build() -> dict:
    api_env = {
        **PUBLIC, **LIMITS, **MAIL, **AI, **TTS, "SEAL_ENABLED": "${SEAL_ENABLED:-true}", "SERVICE_URL_API_8000": "", "SERVICE_ROLE": "api", "DATABASE_URL": DB, "VALKEY_URL": VK,
        "AUTH_JWKS_URL": "http://web:3000/api/auth/jwks", "FILE_TOKEN_SECRET": "${SERVICE_PASSWORD_64_FILES}",
        "ANON_TOKEN_SECRET": "${SERVICE_PASSWORD_64_ANON}", "JOB_SECRETS_KEY": "${SERVICE_PASSWORD_64_JOBSECRETS}",
        "TURNSTILE_SECRET_KEY": "${TURNSTILE_SECRET_KEY:?Clave secreta de Turnstile}",
        "PAYMENT_PROVIDER": "${PAYMENT_PROVIDER:-stripe}", "STRIPE_SECRET_KEY": "${STRIPE_SECRET_KEY:-}",
        "STRIPE_WEBHOOK_SECRET": "${STRIPE_WEBHOOK_SECRET:-}", "STRIPE_PRICE_PRO_MONTHLY": "${STRIPE_PRICE_PRO_MONTHLY:-}",
        "STRIPE_PRICE_PRO_YEARLY": "${STRIPE_PRICE_PRO_YEARLY:-}",
    }
    apiint_env = {
        **PUBLIC, **LIMITS, **MAIL, "SERVICE_ROLE": "apiint", "DATABASE_URL": DB, "VALKEY_URL": VK,
        "AUTH_JWKS_URL": "http://web:3000/api/auth/jwks", "FILE_TOKEN_SECRET": "${SERVICE_PASSWORD_64_FILES}",
        "ANON_TOKEN_SECRET": "${SERVICE_PASSWORD_64_ANON}", "BACKUP_PATH": "/srv/backups",
        "BACKUP_RETENTION_DAYS": "${BACKUP_RETENTION_DAYS:-14}", "BACKUP_RESTIC_REPOSITORY": "${BACKUP_RESTIC_REPOSITORY:-}",
        "BACKUP_RESTIC_PASSWORD": "${BACKUP_RESTIC_PASSWORD:-}",
    }
    beat_env = {**PUBLIC, **LIMITS, **MAIL, **AI, "SERVICE_ROLE": "beat", "DATABASE_URL": DB, "VALKEY_URL": VK}
    auth_db = "postgresql://${SERVICE_USER_POSTGRES}:${SERVICE_PASSWORD_POSTGRES}@postgres:5432/conversor"
    web_env = {
        **PUBLIC, **MAIL, "SERVICE_URL_WEB_3000": "", "AUTH_SECRET": "${SERVICE_PASSWORD_64_AUTH}", "AUTH_DATABASE_URL": auth_db,
        "TURNSTILE_SITE_KEY": "${TURNSTILE_SITE_KEY:?Clave pública de Turnstile}", "CLIENT_MAX_MB": "${CLIENT_MAX_MB:-100}",
        "UPLOAD_CHUNK_BYTES": "${UPLOAD_CHUNK_BYTES:-52428800}", "ADMIN_EMAILS": "${ADMIN_EMAILS:?Correo del administrador}",
        "GOOGLE_CLIENT_ID": "${GOOGLE_CLIENT_ID:-}", "GOOGLE_CLIENT_SECRET": "${GOOGLE_CLIENT_SECRET:-}",
        "SITE_INDEXABLE": "${SITE_INDEXABLE:-true}",
        # Google Drive y Dropbox (8.2.4): claves públicas del navegador, apagados por defecto.
        "GDRIVE_ENABLED": "${GDRIVE_ENABLED:-false}", "GOOGLE_PICKER_CLIENT_ID": "${GOOGLE_PICKER_CLIENT_ID:-}",
        "GOOGLE_PICKER_API_KEY": "${GOOGLE_PICKER_API_KEY:-}", "DROPBOX_ENABLED": "${DROPBOX_ENABLED:-false}",
        "DROPBOX_APP_KEY": "${DROPBOX_APP_KEY:-}",
    }
    after_migrate = {"migrate": {"condition": "service_completed_successfully"}, "valkey": {"condition": "service_healthy"}}
    services = {
        "postgres": svc(
            "pgvector/pgvector:0.8.7-pg16-bookworm",
            environment={"POSTGRES_USER": "${SERVICE_USER_POSTGRES}", "POSTGRES_PASSWORD": "${SERVICE_PASSWORD_POSTGRES}",
                         "POSTGRES_DB": "conversor"},
            volumes=["pgdata:/var/lib/postgresql/data"], networks=["internal"], **memory("postgres", "2560m"),
            oom_score_adj=-500, shm_size="256m",
            healthcheck=hc(["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d conversor"], "10s", "20s"),
        ),
        "valkey": svc(
            "valkey/valkey:9.0.7-alpine",
            command=["valkey-server", "--requirepass", "${SERVICE_PASSWORD_VALKEY}", "--save", "60", "1000", "--appendonly", "no",
                     "--maxmemory", "400mb", "--maxmemory-policy", "noeviction"],
            environment={"VALKEY_PASSWORD": "${SERVICE_PASSWORD_VALKEY}"},
            volumes=["valkeydata:/data"], networks=["internal"], mem_limit="512m", memswap_limit="512m", oom_score_adj=-500,
            healthcheck=hc(["CMD-SHELL", "valkey-cli -a $${VALKEY_PASSWORD} --no-auth-warning ping | grep -q PONG"], "10s", "10s"),
        ),
        "prepare": {
            "image": img("api"), "restart": "no", "logging": LOG, "user": "0:0", "exclude_from_hc": True,
            "command": ["sh", "-c", "mkdir -p /srv/files/uploads /srv/files/jobs /srv/files/shares /srv/backups/postgres"
                        " && chown -R 10001:10001 /srv/files /srv/backups"],
            "volumes": ["filestore:/srv/files", "backups:/srv/backups"], "networks": ["internal"],
        },
        "migrateauth": {
            "image": img("web"), "restart": "no", "logging": LOG, "exclude_from_hc": True,
            "command": ["node", "migrate/migrate-auth.mjs"],
            "environment": {"AUTH_DATABASE_URL": auth_db, "AUTH_SECRET": "${SERVICE_PASSWORD_64_AUTH}", "BETTER_AUTH_URL": "${SERVICE_URL_WEB}"},
            "networks": ["internal"], "depends_on": {"postgres": {"condition": "service_healthy"}},
        },
        "migrate": {
            "image": img("api"), "restart": "no", "logging": LOG, "exclude_from_hc": True,
            "command": ["alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"],
            "environment": {"SERVICE_ROLE": "migrate", "DATABASE_URL": DB, "WORKER_DB_PASSWORD": "${SERVICE_PASSWORD_WORKERDB}"},
            "networks": ["internal"],
            "depends_on": {"prepare": {"condition": "service_completed_successfully"},
                           "migrateauth": {"condition": "service_completed_successfully"},
                           "postgres": {"condition": "service_healthy"}},
        },
        "web": svc(
            img("web"), environment=web_env, networks=["internal", "edge"], mem_limit="1g", memswap_limit="1g", cpu_shares=2048,
            oom_score_adj=-500, user="10001:10001",
            depends_on={"migrateauth": {"condition": "service_completed_successfully"}},
            healthcheck=hc(["CMD", "node", "-e",
                            "fetch('http://127.0.0.1:3000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]),
        ),
        "api": svc(
            img("api"), environment=api_env, volumes=FS, networks=["internal", "edge"], mem_limit="1g", memswap_limit="1g",
            cpu_shares=2048, oom_score_adj=-500, user="10001:10001", read_only=True, tmpfs=["/tmp:size=64m"],
            depends_on=after_migrate, healthcheck=py_hc(8000),
        ),
        "apiint": svc(
            img("api"), command=["uvicorn", "app.internal.app:app", "--host", "0.0.0.0", "--port", "8001", "--no-server-header"],
            environment=apiint_env, volumes=FS + ["backups:/srv/backups"], networks=["internal", "edge"], mem_limit="1g",
            memswap_limit="1g", cpu_shares=2048, oom_score_adj=-500, user="10001:10001", read_only=True, tmpfs=["/tmp:size=256m"],
            depends_on=after_migrate, healthcheck=py_hc(8001),
        ),
        "beat": svc(
            img("api"), command=BEAT_COMMAND,
            environment=beat_env, volumes=FS, networks=["internal", "edge"], mem_limit="512m", memswap_limit="512m",
            user="10001:10001", read_only=True, tmpfs=["/tmp:size=16m"], depends_on=after_migrate,
            healthcheck=hc(["CMD-SHELL", "kill -0 $$(cat /tmp/beat.pid)"], "60s", "30s"),
        ),
        "upload": svc(
            "tusproject/tusd:v2.10.1", user="10001:10001", environment={"SERVICE_URL_UPLOAD_8080": ""},
            command=["-host=0.0.0.0", "-port=8080", "-base-path=/files/", "-upload-dir=/srv/files/uploads", "-behind-proxy",
                     "-disable-download", "-max-size=${UPLOAD_MAX_BYTES:-1073741824}", "-hooks-http=http://apiint:8001/tusd-hooks",
                     "-hooks-http-forward-headers=Authorization,Accept-Language,CF-Connecting-IP,X-Forwarded-For",
                     "-hooks-enabled-events=pre-create,pre-finish,post-terminate",
                     "-cors-allow-origin=^${SERVICE_URL_WEB}$", "-cors-allow-headers=Authorization,Accept-Language"],
            volumes=FS, networks=["internal"], mem_limit="256m", memswap_limit="256m", cpu_shares=2048, oom_score_adj=-500,
            depends_on={"apiint": {"condition": "service_healthy"}},
            healthcheck=hc(["CMD-SHELL", "wget -q -O /dev/null http://127.0.0.1:8080/metrics"]),
        ),
        "files": svc(
            "caddy:2.11.7-alpine", user="10001:10001",
            environment={"SERVICE_URL_FILES_8090": "", "PUBLIC_WEB_URL": "${SERVICE_URL_WEB}", "XDG_DATA_HOME": "/tmp/caddy-data",
                         "XDG_CONFIG_HOME": "/tmp/caddy-config"},
            command=["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"],
            volumes=["filestore:/srv/files:ro", "./infra/caddy/Caddyfile:/etc/caddy/Caddyfile:ro"], networks=["internal"],
            read_only=True, tmpfs=["/tmp:size=16m"], mem_limit="256m", memswap_limit="256m", cpu_shares=2048, oom_score_adj=-500,
            depends_on={"apiint": {"condition": "service_healthy"}},
            healthcheck=hc(["CMD-SHELL", "wget -q -O /dev/null http://127.0.0.1:8090/healthz"]),
        ),
        "gotenberg": svc(
            GOTENBERG,
            command=["gotenberg", "--api-timeout=300s", "--log-format=json", "--libreoffice-restart-after=10",
                     "--chromium-restart-after=10", "--chromium-deny-public-ips=true", "--chromium-deny-private-ips=true",
                     "--libreoffice-deny-public-ips=true", "--libreoffice-deny-private-ips=true",
                     "--api-download-from-deny-public-ips=true", "--api-download-from-deny-private-ips=true",
                     "--webhook-deny-public-ips=true", "--webhook-deny-private-ips=true"],
            networks=["internal"], **memory("gotenberg", "3g"), cpus=2, oom_score_adj=500,
            healthcheck=hc(["CMD", "curl", "-fsS", "http://127.0.0.1:3000/health"]),
        ),
        # web-a-pdf (12.2): Chromium con salida solo por egressweb; nunca recibe archivos de usuarios.
        "gotenbergweb": svc(
            GOTENBERG,
            command=["gotenberg", "--api-timeout=180s", "--log-format=json", "--chromium-restart-after=10",
                     "--chromium-proxy-server=http://egressweb:4750", "--libreoffice-disable-routes=true",
                     "--api-download-from-deny-public-ips=true", "--api-download-from-deny-private-ips=true",
                     "--webhook-deny-public-ips=true", "--webhook-deny-private-ips=true"],
            networks=["webrender"], **memory("gotenbergweb", "1536m"), cpus=1, oom_score_adj=500,
            depends_on={"egressweb": {"condition": "service_started"}},
            healthcheck=hc(["CMD", "curl", "-fsS", "http://127.0.0.1:3000/health"]),
        ),
        "egressweb": svc(
            SMOKESCREEN,
            command=["--listen-ip=0.0.0.0", "--listen-port=4750", "--egress-acl-file=/etc/smokescreen/acl.yaml", "--allow-missing-role",
                     *[f"--deny-range={r}" for r in DENY_RANGES]],
            volumes=["./infra/smokescreen/acl-web.yaml:/etc/smokescreen/acl.yaml:ro"],
            networks=["webrender", "edge"], read_only=True, cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
            mem_limit="256m", memswap_limit="256m", cpus=1, exclude_from_hc=True,
        ),
        # IA (6 y 12.2): la única con OPENROUTER_API_KEY; sale solo hacia OpenRouter por egressai. Sin clave, las
        # herramientas de IA se ven «no disponibles temporalmente» y el resto del servicio funciona igual.
        "egressai": svc(
            SMOKESCREEN,
            command=["--listen-ip=0.0.0.0", "--listen-port=4750", "--egress-acl-file=/etc/smokescreen/acl.yaml", "--allow-missing-role",
                     *[f"--deny-range={r}" for r in DENY_RANGES]],
            volumes=["./infra/smokescreen/acl-ai.yaml:/etc/smokescreen/acl.yaml:ro"],
            networks=["airelay", "edge"], read_only=True, cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
            mem_limit="256m", memswap_limit="256m", cpus=1, exclude_from_hc=True,
        ),
        "workerai": worker("worker-ai", "worker-ai", "ai", "ai", 4, 1, "1g", 4,
                           {**AI, "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY:-}", "OPENROUTER_BASE_URL":
                            "${OPENROUTER_BASE_URL:-https://openrouter.ai/api/v1}", "EGRESS_AI_URL": "http://egressai:4750",
                            # traducir-pdf imprime el PDF con el Chromium de gotenberg (sin red, 12.2).
                            "GOTENBERG_URL": "http://gotenberg:3000"},
                           networks=["internal", "airelay"]),
        # chat-pdf (6.4): embeddings locales en su cola; el modelo ocupa unos 0,7 GB por proceso (D-128). Sin clave ni salida.
        "workeraiembed": worker("worker-ai", "worker-ai", "ai-embed", "ai.embed", 1, 1, "1280m", 1),
        # Sello de la plataforma (10, D-188): el único con el token (volumen softhsm) y SIGN_PKCS11_PIN; sale por
        # egressweb a la TSA y a los OCSP y CRL del sello. El token y SIGN_CERT_PATH los prepara el propietario.
        "workersign": worker("worker-sign", "worker-sign", "sign", "sign", 1, 1, "512m", 1,
                             {"EGRESS_WEB_URL": "http://egressweb:4750", "SIGN_PKCS11_MODULE": "/usr/lib/softhsm/libsofthsm2.so",
                              "SIGN_PKCS11_TOKEN_LABEL": "${SIGN_PKCS11_TOKEN_LABEL:-conversor-sello}",
                              "SIGN_PKCS11_KEY_LABEL": "${SIGN_PKCS11_KEY_LABEL:-sello}", "SIGN_PKCS11_PIN": "${SIGN_PKCS11_PIN:-}",
                              "SIGN_CERT_PATH": "${SIGN_CERT_PATH:-/var/lib/softhsm/sello.pem}", "TSA_URL": "${TSA_URL:-}",
                              "SEAL_ENABLED": "${SEAL_ENABLED:-true}", "SEAL_DAILY_LIMIT": "${SEAL_DAILY_LIMIT:-500}",
                              "SEAL_ACCOUNT_DAILY_LIMIT": "${SEAL_ACCOUNT_DAILY_LIMIT:-20}", "TSA_TRUST_ROOTS": "${TSA_TRUST_ROOTS:-}"},
                             networks=["internal", "webrender"], volumes=["softhsm:/var/lib/softhsm"]),
        # verificar-firmas-pdf (7.23, D-185): imagen worker-sign sin el token ni el PIN del sello; sale por egressweb
        # para la lista de confianza de la UE (beat) y OCSP y CRL a petición, y la guarda en el volumen eutl.
        # 768 MB en el perfil de 8 vCPU: el registro de la UE ocupa unos 245 MB por proceso (31 listas, medido) y la
        # descarga diaria otro tanto en el mismo proceso (D-185 y D-186).
        "workersignverify": worker("worker-sign", "worker-sign-verify", "sign-verify", "sign.verify", 1, 1, "768m", 1,
                                   {"EGRESS_WEB_URL": "http://egressweb:4750", "EUTL_CACHE_PATH": "/srv/eutl",
                                    "EUTL_LOTL_URL": "${EUTL_LOTL_URL:-https://ec.europa.eu/tools/lotl/eu-lotl.xml}",
                                    "EUTL_REFRESH_HOURS": "${EUTL_REFRESH_HOURS:-24}",
                                    "SIGN_VERIFY_EXTRA_ROOTS": "${SIGN_VERIFY_EXTRA_ROOTS:-}"},
                                   networks=["internal", "webrender"], volumes=["eutl:/srv/eutl"]),
        "workerpdf": worker("worker-pdf", "worker-pdf", "pdf", "pdf", 3, 1, "3g", 3, secrets=True),
        "workerocr": worker("worker-ocr", "worker-ocr", "ocr", "ocr", 1, 2, "3g", 2),
        "workeroffice": worker("worker-office", "worker-office", "office-light", "office.light", 1, 1, "1536m", 1,
                               {"GOTENBERG_URL": "http://gotenberg:3000", "GOTENBERG_WEB_URL": "http://gotenbergweb:3000",
                                "EGRESS_WEB_URL": "http://egressweb:4750"}, secrets=True, networks=["internal", "webrender"]),
        "workerofficeheavy": worker("worker-office", "worker-office", "office-heavy", "office.heavy", 1, 1, "2g", 1,
                                    {"GOTENBERG_URL": "http://gotenberg:3000"}, secrets=True),
        "workermedia": worker("worker-media", "worker-media", "media", "media", 1, 1, "1536m", 1, {"GOTENBERG_URL": "http://gotenberg:3000"}),
        "workerconvert": worker("worker-convert", "worker-convert", "convert", "convert", 1, 2, "5g", 2, {"HF_HUB_OFFLINE": "1"}),
        # Audio ligero con FFmpeg (2,25 GB en el perfil de 8 vCPU; 3 GB en el de 16, D-186).
        "workerav": worker("worker-av", "worker-av", "av-light", "av.light", 1, 2, "2304m", 2),
        # Transcripciones (cola pesada, 5.4): un trabajo a la vez con 2 hilos; el modelo va dentro de la imagen.
        "workeravheavy": worker("worker-av", "worker-av", "av-heavy", "av.heavy", 1, 2, "3g", 2,
                                {"WHISPER_MODEL": "${WHISPER_MODEL:-small}", "WHISPER_DEVICE": "${WHISPER_DEVICE:-cpu}",
                                 "WHISPER_COMPUTE_TYPE": "${WHISPER_COMPUTE_TYPE:-int8}", **TTS, **AI}),
    }
    return {
        "services": services,
        "networks": {"internal": {"internal": True}, "edge": {}, "webrender": {"internal": True}, "airelay": {"internal": True}},
        "volumes": {"pgdata": {}, "valkeydata": {}, "filestore": {}, "backups": {}, "eutl": {}, "softhsm": {}},
    }


HEADER = """# Producción en Coolify v4 (13.2): solo `image:` con etiquetas fijas, dominios por variables mágicas y sin `ports:`.
# Generado por scripts/gen_coolify_compose.py: edita el generador, no este archivo.
# Los servicios de fases posteriores (workerutils, workermesh, workercad y umami) se añaden con su
# fase.
# Memoria y CPU (5.4): `MEM_<NOMBRE>` cambia `mem_limit` y `memswap_limit` de postgres, gotenberg, gotenbergweb y cada
# worker, y `CPUS_<NOMBRE>` y `CONCURRENCY_<NOMBRE>`, los de cada worker. Por defecto, el perfil de 8 vCPU; el de
# 16 vCPU lo imprime `python scripts/gen_coolify_compose.py --profile 16` (docs/OPERATIONS.md).
"""


def render() -> str:
    return HEADER + yaml.safe_dump(build(), sort_keys=False, allow_unicode=True, width=200)


# Valores ficticios solo para validar el esquema: en Coolify los pone la plataforma o el propietario.
DUMMY_ENV = {
    "GHCR_OWNER": "propietario", "IMAGE_TAG": "0.0.0", "APP_NAME": "Producto Demo", "ADMIN_EMAILS": "admin@ejemplo.test",
    "SMTP_URL": "smtp://correo.ejemplo.test:587", "MAIL_FROM": "no-responder@ejemplo.test", "TURNSTILE_SECRET_KEY": "x",
    "TURNSTILE_SITE_KEY": "x", "SERVICE_URL_WEB": "https://ejemplo.test", "SERVICE_URL_API": "https://api.ejemplo.test",
    "SERVICE_URL_UPLOAD": "https://upload.ejemplo.test", "SERVICE_URL_FILES": "https://files.ejemplo.test",
    "SERVICE_USER_POSTGRES": "u", "SERVICE_PASSWORD_POSTGRES": "p", "SERVICE_PASSWORD_VALKEY": "p", "SERVICE_PASSWORD_WORKERDB": "p",
    "SERVICE_PASSWORD_64_AUTH": "p", "SERVICE_PASSWORD_64_FILES": "p", "SERVICE_PASSWORD_64_ANON": "p",
    "SERVICE_PASSWORD_64_JOBSECRETS": "p",
}


def validate() -> int:
    """`docker compose config` sobre una copia sin `exclude_from_hc`, que es una clave propia de Coolify."""
    import os
    import subprocess
    import tempfile

    doc = build()
    for service in doc["services"].values():
        service.pop("exclude_from_hc", None)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "docker-compose.yml"
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
        (Path(tmp) / "infra" / "caddy").mkdir(parents=True)
        (Path(tmp) / "infra" / "caddy" / "Caddyfile").write_text("", encoding="utf-8")
        (Path(tmp) / "infra" / "smokescreen").mkdir(parents=True)
        (Path(tmp) / "infra" / "smokescreen" / "acl-web.yaml").write_text("", encoding="utf-8")
        res = subprocess.run(["docker", "compose", "-f", str(path), "config", "--quiet"], env={**os.environ, **DUMMY_ENV},
                             capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        return 1
    print("docker-compose.coolify.yml válido")
    return 0


def main(argv: list[str]) -> int:
    if "--validate" in argv:
        return validate()
    if "--profile" in argv:
        if argv[argv.index("--profile") + 1:argv.index("--profile") + 2] != ["16"]:
            print("Uso: --profile 16 (el perfil de 8 vCPU es el valor por defecto del archivo)", file=sys.stderr)
            return 2
        print("\n".join(f"{k}={v}" for k, v in PROFILE_16.items()))
        return 0
    content = render()
    if "--check" in argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != content:
            print("docker-compose.coolify.yml no está al día: ejecuta python scripts/gen_coolify_compose.py", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(content, encoding="utf-8")
    print(f"Escrito {OUT.name} con {len(build()['services'])} servicios")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
