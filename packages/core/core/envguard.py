"""Matriz de secretos por contenedor (12.1) y endurecimiento del proceso del worker."""
from __future__ import annotations

import ctypes
import os
from collections.abc import Mapping

SENSITIVE = {
    "FILE_TOKEN_SECRET", "ANON_TOKEN_SECRET", "AUTH_SECRET", "BETTER_AUTH_SECRET", "JOB_SECRETS_KEY",
    "PAYPAL_CLIENT_SECRET", "SMTP_URL", "GOOGLE_CLIENT_SECRET",
    "GOOGLE_PICKER_API_KEY", "DROPBOX_APP_KEY", "OPENROUTER_API_KEY", "SIGN_PKCS11_PIN",
    "BACKUP_RESTIC_PASSWORD", "TURNSTILE_SECRET_KEY", "DATABASE_URL",
}

ALLOWED: dict[str, set[str]] = {
    "web": {"AUTH_SECRET", "BETTER_AUTH_SECRET", "DATABASE_URL", "SMTP_URL", "GOOGLE_CLIENT_SECRET"},
    "api": {"FILE_TOKEN_SECRET", "ANON_TOKEN_SECRET", "JOB_SECRETS_KEY", "PAYPAL_CLIENT_SECRET",
            "SMTP_URL", "TURNSTILE_SECRET_KEY", "DATABASE_URL"},
    "apiint": {"FILE_TOKEN_SECRET", "ANON_TOKEN_SECRET", "DATABASE_URL", "SMTP_URL", "BACKUP_RESTIC_PASSWORD"},
    # FILE_TOKEN_SECRET: los enlaces de descarga del correo final de solicitar-firmas (F4-C2, D-202).
    "beat": {"DATABASE_URL", "SMTP_URL", "FILE_TOKEN_SECRET"},
    "migrate": {"DATABASE_URL"},
    "worker-pdf": {"JOB_SECRETS_KEY"},
    "worker-office": {"JOB_SECRETS_KEY"},
    "worker-ocr": set(),
    "worker-convert": set(),
    "worker-av": set(),
    "worker-media": set(),
    "worker-utils": set(),
    "worker-ai": {"OPENROUTER_API_KEY"},
    "worker-sign": {"SIGN_PKCS11_PIN"},
    # Verificación de firmas (7.23): misma imagen que workersign, sin el PIN ni el token del sello (D-185).
    "worker-sign-verify": set(),
    "test": SENSITIVE,
}


def violations(role: str, env: Mapping[str, str] | None = None) -> list[str]:
    env = os.environ if env is None else env
    allowed = ALLOWED.get(role, set())
    return sorted(v for v in SENSITIVE if env.get(v) and v not in allowed)


def harden_process() -> None:
    """PR_SET_DUMPABLE=0: un subproceso con el mismo usuario no puede leer /proc/<pid>/environ."""
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        PR_SET_DUMPABLE = 4
        libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)
    except OSError:
        pass
