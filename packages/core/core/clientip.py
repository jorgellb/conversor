"""IP real del cliente (12.4).

La API y tusd están detrás del proxy de Coolify (Traefik). Traefik añade al final de `X-Forwarded-For`
la IP de quien le abrió la conexión, así que el último salto de esa cabecera es el par TCP real.
`CF-Connecting-IP` solo se acepta cuando ese par está en los rangos de Cloudflare: si alguien llega
directo al origen y falsifica la cabecera, se usa su IP de verdad.
"""
from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from functools import lru_cache

# Rangos publicados en https://www.cloudflare.com/ips/ (revisar en cada fase; se pueden sustituir con
# CLOUDFLARE_IP_RANGES separados por comas).
CLOUDFLARE_RANGES = (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
    "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
    "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32",
    "2a06:98c0::/29", "2c0f:f248::/32",
)


@lru_cache(maxsize=8)
def _networks(override: str) -> tuple:
    ranges = [r.strip() for r in override.split(",") if r.strip()] if override else list(CLOUDFLARE_RANGES)
    return tuple(ipaddress.ip_network(r, strict=False) for r in ranges)


def _ip(value: str | None):
    if not value:
        return None
    try:
        return ipaddress.ip_address(value.strip().strip("[]"))
    except ValueError:
        return None


def _header(headers: Mapping, name: str) -> str | None:
    value = headers.get(name)
    if value is None:
        for k, v in headers.items():
            if k.lower() == name:
                value = v
                break
    if isinstance(value, list):
        value = value[0] if value else None
    return value


def real_ip(peer: str | None, headers: Mapping, trust_cf: bool, cf_ranges: str = "") -> str:
    """Devuelve la IP del cliente.

    - `peer`: dirección TCP que ve este proceso (normalmente Traefik, en una red privada de Docker).
    - Si `peer` es privada o de bucle local, se toma el último elemento de `X-Forwarded-For`.
    - Si ese salto pertenece a Cloudflare y `trust_cf` está activo, se usa `CF-Connecting-IP`.
    """
    hop = _ip(peer)
    if hop is None or hop.is_private or hop.is_loopback:
        xff = _header(headers, "x-forwarded-for")
        if xff:
            last = _ip(xff.split(",")[-1])
            if last is not None:
                hop = last
    if hop is None:
        return peer or "0.0.0.0"
    if trust_cf and any(hop in net for net in _networks(cf_ranges)):
        cf = _ip(_header(headers, "cf-connecting-ip"))
        if cf is not None:
            return str(cf)
    return str(hop)
