"""Configuración por variables de entorno (sección 14 del plan)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=True)

    APP_ENV: str = "production"
    APP_NAME: str = "Producto Demo"
    SERVICE_ROLE: str = "api"
    PUBLIC_WEB_URL: str = "https://ejemplo.test"
    PUBLIC_API_URL: str = "https://api.ejemplo.test"
    PUBLIC_UPLOAD_URL: str = "https://upload.ejemplo.test/files/"
    PUBLIC_FILES_URL: str = "https://files.ejemplo.test"
    DEFAULT_LOCALE: str = "es"
    DISPLAY_TZ: str = "Europe/Madrid"

    DATABASE_URL: str = "postgresql+psycopg://conversor:conversor@postgres:5432/conversor"
    DATABASE_URL_WORKER: str = ""
    VALKEY_URL: str = "redis://valkey:6379/0"

    AUTH_JWKS_URL: str = "http://web:3000/api/auth/jwks"
    BETTER_AUTH_URL: str = "https://ejemplo.test"
    FILE_TOKEN_SECRET: str = ""
    ANON_TOKEN_SECRET: str = ""
    JOB_SECRETS_KEY: str = ""

    FILESTORE_PATH: Path = Path("/srv/files")
    DISK_MAX_USAGE_PERCENT: float = 85.0
    DISK_MIN_FREE_GB: float = 20.0
    DISK_RESERVE_FACTOR: float = 3.0
    CLIENT_MAX_MB: int = 100
    FILE_TTL_ANON_MINUTES: int = 60
    FILE_TTL_USER_HOURS: int = 24
    SHARE_MAX_DAYS: int = 7
    UPLOAD_MAX_BYTES: int = 1073741824
    UPLOAD_CHUNK_BYTES: int = 52428800
    DOWNLOAD_TOKEN_MINUTES: int = 15

    BACKUP_PATH: Path = Path("/srv/backups")
    BACKUP_RETENTION_DAYS: int = 14
    BACKUP_RESTIC_REPOSITORY: str = ""
    BACKUP_RESTIC_PASSWORD: str = ""

    ADMIN_EMAILS: str = "admin@ejemplo.test"
    SMTP_URL: str = ""
    MAIL_SHARE_DAILY_LIMIT: int = 10
    # solicitar-firmas (7.7, F4-C2): solicitudes por cuenta Pro y día (gratis, FREE_SIGN_REQUESTS_PER_DAY en signreq).
    SIGN_REQUEST_DAILY_LIMIT: int = 20
    MAIL_FROM: str = "no-responder@ejemplo.test"

    TURNSTILE_SITE_KEY: str = ""
    TURNSTILE_SECRET_KEY: str = ""
    TRUST_CF_CONNECTING_IP: bool = False
    CLOUDFLARE_IP_RANGES: str = ""
    RATE_LIMIT_PER_MINUTE: int = 60
    ANON_TOKENS_PER_IP_DAY: int = 10

    PAYMENT_PROVIDER: str = "fake"
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_PRO_MONTHLY: str = ""
    STRIPE_PRICE_PRO_YEARLY: str = ""

    IMAGE_MAX_PIXELS: int = 100_000_000
    RENDER_MAX_PIXELS: int = 50_000_000
    # Perfil de salida para CMYK (A.9): FOGRA39 del paquete colord-data, con licencia CC0 (D-60).
    CMYK_ICC_PROFILE: str = "/usr/share/color/icc/colord/FOGRA39L_coated.icc"
    THREADS: int = 1
    GOTENBERG_URL: str = "http://gotenberg:3000"
    GOTENBERG_WEB_URL: str = "http://gotenbergweb:3000"
    EGRESS_WEB_URL: str = "http://egressweb:4750"
    OCR_MAX_LANGUAGES: int = 3
    # Firma (10 y 14, F4). El sello de la plataforma va por PKCS#11 (SoftHSM2) y solo `workersign` conoce el PIN y monta
    # el token; la verificación (`sign.verify`) corre en otro contenedor sin token ni PIN.
    SIGN_PKCS11_MODULE: str = "/usr/lib/softhsm/libsofthsm2.so"
    SIGN_PKCS11_TOKEN_LABEL: str = "conversor-sello"
    SIGN_PKCS11_KEY_LABEL: str = "sello"
    SIGN_PKCS11_PIN: str = ""
    SIGN_CERT_PATH: str = ""
    TSA_URL: str = ""
    # Firma con certificado propio en sign.verify (D-199): salida a la TSA y a OCSP/CRL. Sin definir, EGRESS_WEB_URL;
    # vacía, directa (desarrollo: la TSA de certomancer está en la red interna, que Smokescreen no deja alcanzar).
    TSA_EGRESS_URL: str | None = None
    SEAL_ENABLED: bool = True
    SEAL_DAILY_LIMIT: int = 500
    # Sellos por cuenta y día (D-189), para que una cuenta no gaste el límite de todos.
    SEAL_ACCOUNT_DAILY_LIMIT: int = 20
    # Raíces de la TSA (PEM en un archivo o en la variable) para validar su certificado al incrustar los datos de B-LT;
    # vacía: las autofirmadas que devuelve la propia TSA.
    TSA_TRUST_ROOTS: str = ""
    # Lista de confianza de la UE (7.23): la descarga beat por `egressweb` y la guarda en EUTL_CACHE_PATH (volumen de
    # `workersignverify`). La firma de la LOTL se comprueba desde el ancla del DOUE que trae pyHanko.
    EUTL_LOTL_URL: str = "https://ec.europa.eu/tools/lotl/eu-lotl.xml"
    EUTL_REFRESH_HOURS: int = 24
    EUTL_CACHE_PATH: Path = Path("/srv/eutl")
    # Facturas electrónicas (7.23, F4-D): KoSIT en modo servicio dentro de workerutils (5.4) y los XSD de Facturae.
    KOSIT_URL: str = "http://127.0.0.1:8081/"
    KOSIT_TIMEOUT: float = 120
    FACTURAE_XSD_DIR: Path = Path("/opt/facturae")
    # Configuraciones de KoSIT en la imagen worker-utils: sus XSD de UBL 2.1 y CII D16B validan la sintaxis en las
    # páginas ubl-a-pdf y cii-a-pdf (7.14, D-194).
    KOSIT_HOME: Path = Path("/opt/kosit")
    # pandoc estático de infra/pandoc/fetch.sh en workerutils (F6-A, D-212): GPL, solo como proceso externo (11).
    PANDOC_BIN: Path = Path("/usr/local/bin/pandoc")
    # Certificados (PEM) que la verificación acepta como raíz además de la lista de la UE: la cadena del sello de la
    # plataforma, que no es cualificado (10). Vacío: solo la lista de la UE.
    SIGN_VERIFY_EXTRA_ROOTS: str = ""
    # quitar-fondo (6.4): modelo de rembg ya descargado en la imagen; nunca bria-rmbg (licencia de pago, D-96).
    REMBG_MODEL: str = "u2net"
    REMBG_HOME: Path = Path("/opt/rembg")
    # Transcripción (6.4): faster-whisper en CPU con el modelo ya dentro de la imagen worker-av (nunca se descarga al
    # ejecutar). small en int8 por defecto; medium es opcional (precisión alta).
    WHISPER_MODEL: str = "small"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_HOME: Path = Path("/opt/models/whisper")
    # Voz de pdf-a-audio (6.4 y 14): Kokoro-82M en ONNX dentro de la imagen worker-av (infra/kokoro/fetch-model.sh), con
    # los fonemas de espeak-ng. Un idioma sin voz configurada está apagado: la española se queda vacía hasta que el
    # propietario la escuche (DEPLOY-CHECKLIST). La API también las lee, para no encolar un idioma apagado.
    TTS_ENGINE: str = "kokoro"
    TTS_VOICE_ES: str = ""
    TTS_VOICE_EN: str = "af_heart"
    KOKORO_HOME: Path = Path("/opt/models/kokoro")
    # IA (6 y 14): OpenRouter solo con modelos gratuitos. La clave solo está en workerai (12.1), que sale por egressai.
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_PREFERRED_MODELS: str = ""
    LLM_FALLBACK_ROUTER: str = "openrouter/free"
    LLM_MODELS_REFRESH_HOURS: int = 6
    AI_DAILY_BUDGET: int = 950
    AI_PRO_RESERVE: int = 400
    AI_RPM_LIMIT: int = 18
    AI_BUDGET_RESET_TZ: str = "UTC"
    AI_REQUIRE_CONSENT: bool = True
    AI_CHAT_RPM_SHARE: float = 0.5
    AI_TASK_MAX_REQUESTS: int = 20
    # Segundos que una petición espera hueco en el límite por minuto antes de rendirse (RATE_LIMITED transitorio).
    AI_RPM_WAIT_SECONDS: int = 90
    EGRESS_AI_URL: str = "http://egressai:4750"
    EMBEDDINGS_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # chat-pdf (6.4): el ONNX del modelo, ya dentro de la imagen worker-ai (infra/embeddings/fetch-model.sh).
    EMBEDDINGS_HOME: Path = Path("/opt/models/embeddings")
    QUEUE_DEFAULT_MAX_WAIT_SECONDS: int = 300
    PLANS_FILE: Path = Path(__file__).resolve().parents[3] / "config" / "plans.yaml"
    LOG_LEVEL: str = "INFO"

    queue_max_wait: dict[str, int] = Field(default_factory=dict)

    @property
    def is_dev(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def ai_consent_required(self) -> bool:
        """6.6: el consentimiento no se puede desactivar en producción."""
        return self.AI_REQUIRE_CONSENT or self.APP_ENV == "production"

    @property
    def ai_fake(self) -> bool:
        """6.6: proveedor falso determinista cuando no hay clave y el entorno es de desarrollo."""
        return not self.OPENROUTER_API_KEY and self.APP_ENV in ("development", "test")

    @property
    def preferred_models(self) -> list[str]:
        return [m.strip() for m in self.LLM_PREFERRED_MODELS.split(",") if m.strip()]

    @property
    def admin_emails(self) -> list[str]:
        return [e.strip() for e in self.ADMIN_EMAILS.split(",") if e.strip()]

    def queue_wait_limit(self, group: str) -> int:
        import os

        value = os.environ.get(f"QUEUE_MAX_WAIT_SECONDS_{group.upper()}")
        if value:
            return int(value)
        return 120 if group == "pdf" else self.QUEUE_DEFAULT_MAX_WAIT_SECONDS


@lru_cache
def get_settings() -> Settings:
    return Settings()
