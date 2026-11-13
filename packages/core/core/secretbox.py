"""Cifrado de los secretos de un trabajo (contraseñas de PDF) con AES-GCM (5.3).

Los secretos viajan cifrados en los argumentos de la tarea y solo se descifran en memoria
dentro del worker. Nunca se guardan en claro en Valkey, la base de datos ni los logs.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _key(secret: str) -> bytes:
    if not secret:
        raise RuntimeError("Falta JOB_SECRETS_KEY")
    return hashlib.sha256(secret.encode()).digest()


def seal(secret: str, data: dict[str, str]) -> str:
    if not data:
        return ""
    nonce = os.urandom(12)
    ct = AESGCM(_key(secret)).encrypt(nonce, json.dumps(data).encode(), b"job-secrets-v1")
    return "v1." + base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def open_sealed(secret: str, token: str) -> dict[str, str]:
    if not token:
        return {}
    version, _, payload = token.partition(".")
    if version != "v1":
        raise ValueError("Versión de secreto desconocida")
    raw = base64.urlsafe_b64decode(payload)
    plain = AESGCM(_key(secret)).decrypt(raw[:12], raw[12:], b"job-secrets-v1")
    return json.loads(plain)
