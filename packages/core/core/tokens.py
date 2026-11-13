"""Tokens firmados: descargas (4.4), compartir y sesiones anónimas (5.1)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
import time


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _mac(secret: str, message: str) -> str:
    if not secret:
        raise RuntimeError("Falta el secreto de firma")
    return _b64(hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest())


def owner_key(owner_type: str, owner_id: str) -> str:
    return hashlib.sha256(f"{owner_type}:{owner_id}".encode()).hexdigest()[:16]


def sign_download(secret: str, job_id: str, filename: str, owner: str, ttl_seconds: int, now: float | None = None) -> str:
    exp = int((now or time.time()) + ttl_seconds)
    sig = _mac(secret, f"d|{job_id}|{filename}|{exp}|{owner}")
    return f"{exp}.{owner}.{sig}"


def verify_download(secret: str, job_id: str, filename: str, token: str, now: float | None = None) -> bool:
    try:
        exp_s, owner, sig = token.split(".", 2)
        exp = int(exp_s)
    except ValueError:
        return False
    if exp < (now or time.time()):
        return False
    expected = _mac(secret, f"d|{job_id}|{filename}|{exp}|{owner}")
    return hmac.compare_digest(expected, sig)


def issue_anon_token(secret: str, client_id: str, ttl_seconds: int = 86400, now: float | None = None) -> str:
    payload = _b64(json.dumps({"sub": client_id, "exp": int((now or time.time()) + ttl_seconds)}, separators=(",", ":")).encode())
    return f"anon.{payload}.{_mac(secret, 'a|' + payload)}"


def verify_anon_token(secret: str, token: str, now: float | None = None) -> str | None:
    if not token.startswith("anon."):
        return None
    try:
        _, payload, sig = token.split(".", 2)
    except ValueError:
        return None
    if not hmac.compare_digest(_mac(secret, "a|" + payload), sig):
        return None
    try:
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(data.get("exp", 0)) < (now or time.time()):
        return None
    return str(data.get("sub"))


def new_share_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_ip(ip: str) -> str:
    """IPv4 tal cual; IPv6 agrupada por /64 (12.4)."""
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return "desconocida"
    if addr.version == 6:
        if addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False).network_address) + "/64"
    return str(addr)


def hash_ip(secret: str, ip: str) -> str:
    return hmac.new(secret.encode(), normalize_ip(ip).encode(), hashlib.sha256).hexdigest()[:32]
