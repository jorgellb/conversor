"""Limitador global de IA en Valkey (6.3), atómico con scripts Lua.

- Presupuesto diario (`AI_DAILY_BUDGET`): `total` cuenta las peticiones hechas y las reservadas por trabajos en curso.
  Un usuario que no es Pro no puede llevar `total` por encima de `AI_DAILY_BUDGET - AI_PRO_RESERVE`, así que la reserva
  Pro siempre queda libre para Pro.
- Límite por minuto (`AI_RPM_LIMIT`, ventana deslizante de 60 s); el chat usa como máximo `AI_CHAT_RPM_SHARE` de él.
- `used` cuenta las peticiones reales (y lo que OpenRouter cuente de más, tras la reconciliación con `/key`).
El día es el de `AI_BUDGET_RESET_TZ` (UTC, como el contador de OpenRouter).
"""
from __future__ import annotations

import json
import math
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.settings import Settings

DAY_TTL = 2 * 86400
PRO_ONLY_REMAINING = 20  # 6.3: si a OpenRouter le quedan menos de 20, solo Pro usa IA

_RESERVE = """
local cur = tonumber(redis.call('GET', KEYS[1]) or '0')
local n = tonumber(ARGV[1])
if cur + n > tonumber(ARGV[2]) then return -1 end
local v = redis.call('INCRBY', KEYS[1], n)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return v
"""

_RELEASE = """
local cur = tonumber(redis.call('GET', KEYS[1]) or '0')
local n = math.min(cur, tonumber(ARGV[1]))
if n <= 0 then return cur end
return redis.call('DECRBY', KEYS[1], n)
"""

# Ventana deslizante: KEYS[1] todas las peticiones, KEYS[2] las del chat. Devuelve 0 si hay hueco (y lo ocupa) o los
# milisegundos que faltan para que lo haya.
_RPM = """
local now = tonumber(ARGV[1])
local start = now - 60000
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, start)
redis.call('ZREMRANGEBYSCORE', KEYS[2], 0, start)
local all = redis.call('ZCARD', KEYS[1])
if all >= tonumber(ARGV[2]) then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  return math.max(1, tonumber(oldest[2]) + 60000 - now)
end
if ARGV[4] == '1' then
  local chat = redis.call('ZCARD', KEYS[2])
  if chat >= tonumber(ARGV[3]) then
    local oldest = redis.call('ZRANGE', KEYS[2], 0, 0, 'WITHSCORES')
    return math.max(1, tonumber(oldest[2]) + 60000 - now)
  end
  redis.call('ZADD', KEYS[2], now, ARGV[5])
  redis.call('PEXPIRE', KEYS[2], 61000)
end
redis.call('ZADD', KEYS[1], now, ARGV[5])
redis.call('PEXPIRE', KEYS[1], 61000)
return 0
"""

# Reconciliación: si OpenRouter cuenta más peticiones que nosotros, `used` y `total` suben la diferencia.
_RECONCILE = """
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
local remote = tonumber(ARGV[1])
local delta = remote - used
if delta > 0 then
  redis.call('INCRBY', KEYS[1], delta)
  redis.call('INCRBY', KEYS[2], delta)
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
  redis.call('EXPIRE', KEYS[2], tonumber(ARGV[2]))
  return delta
end
return 0
"""


def budget_day(settings: Settings, now: datetime | None = None) -> str:
    tz = ZoneInfo(settings.AI_BUDGET_RESET_TZ)
    return (now.astimezone(tz) if now else datetime.now(tz)).date().isoformat()


def reset_at(settings: Settings, now: datetime | None = None) -> datetime:
    """Siguiente reinicio del presupuesto (medianoche en `AI_BUDGET_RESET_TZ`), con zona."""
    tz = ZoneInfo(settings.AI_BUDGET_RESET_TZ)
    local = now.astimezone(tz) if now else datetime.now(tz)
    return datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), tzinfo=tz)


def reset_local(settings: Settings, now: datetime | None = None) -> str:
    """Hora del reinicio en la zona de la web (`DISPLAY_TZ`, Madrid), como «01:00»."""
    return reset_at(settings, now).astimezone(ZoneInfo(settings.DISPLAY_TZ)).strftime("%H:%M")


def _keys(settings: Settings, day: str | None = None) -> dict[str, str]:
    d = day or budget_day(settings)
    return {"total": f"ai:{d}:total", "used": f"ai:{d}:used", "pro_only": f"ai:{d}:pro_only"}


def limit_for(settings: Settings, pro: bool) -> int:
    return settings.AI_DAILY_BUDGET if pro else max(0, settings.AI_DAILY_BUDGET - settings.AI_PRO_RESERVE)


def reserve(r, settings: Settings, n: int, pro: bool) -> bool:
    """Reserva `n` peticiones del día. False si no caben (sin tocar la reserva Pro si no es Pro)."""
    if n <= 0:
        return True
    keys = _keys(settings)
    if not pro and r.get(keys["pro_only"]):
        return False
    return int(r.eval(_RESERVE, 1, keys["total"], n, limit_for(settings, pro), DAY_TTL)) >= 0


def release(r, settings: Settings, n: int, day: str | None = None) -> None:
    """Devuelve peticiones reservadas que no se han usado."""
    if n > 0:
        r.eval(_RELEASE, 1, _keys(settings, day)["total"], n)


def count_used(r, settings: Settings, n: int = 1) -> None:
    """Una petición real hecha (ya estaba reservada en `total`)."""
    key = _keys(settings)["used"]
    pipe = r.pipeline()
    pipe.incrby(key, n)
    pipe.expire(key, DAY_TTL)
    pipe.execute()


def acquire_rpm(r, settings: Settings, chat: bool = False, now_ms: int | None = None) -> int:
    """Ocupa un hueco del minuto. Devuelve 0 si lo ha ocupado o los milisegundos que hay que esperar."""
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    chat_limit = max(1, math.floor(settings.AI_RPM_LIMIT * settings.AI_CHAT_RPM_SHARE))
    return int(r.eval(_RPM, 2, "ai:rpm", "ai:rpm:chat", now, settings.AI_RPM_LIMIT, chat_limit, "1" if chat else "0",
                      f"{now}-{uuid.uuid4().hex[:8]}"))


def reconcile(r, settings: Settings, remote_used: int, remaining: int | None) -> int:
    """6.3: sube el contador propio a lo que cuenta OpenRouter y deja la IA solo para Pro si le quedan menos de 20."""
    keys = _keys(settings)
    delta = int(r.eval(_RECONCILE, 2, keys["used"], keys["total"], remote_used, DAY_TTL))
    if remaining is not None and remaining < PRO_ONLY_REMAINING:
        r.set(keys["pro_only"], "1", ex=DAY_TTL)
    return delta


def status(r, settings: Settings) -> dict:
    keys = _keys(settings)
    total = int(r.get(keys["total"]) or 0)
    used = int(r.get(keys["used"]) or 0)
    pro_only = bool(r.get(keys["pro_only"]))
    return {
        "day": budget_day(settings),
        "total": total,
        "used": used,
        "budget": settings.AI_DAILY_BUDGET,
        "pro_reserve": settings.AI_PRO_RESERVE,
        "remaining_free": 0 if pro_only else max(0, limit_for(settings, False) - total),
        "remaining_pro": max(0, limit_for(settings, True) - total),
        "pro_only": pro_only,
        "reset_at": reset_at(settings).isoformat(),
        "reset_local": reset_local(settings),
    }


def save_key_snapshot(r, data: dict) -> None:
    """Lo último que dijo `/key` (uso, límite de la clave, peticiones gratuitas del día), para el panel."""
    r.set("ai:key", json.dumps(data, ensure_ascii=False), ex=DAY_TTL)


def key_snapshot(r) -> dict | None:
    raw = r.get("ai:key")
    return json.loads(raw) if raw else None
