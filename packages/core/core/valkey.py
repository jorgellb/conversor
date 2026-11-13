"""Cliente de Valkey (protocolo compatible con Redis)."""
from __future__ import annotations

from functools import lru_cache

import redis

from core.settings import get_settings


@lru_cache
def get_valkey() -> redis.Redis:
    return redis.Redis.from_url(get_settings().VALKEY_URL, decode_responses=True, socket_timeout=5)
