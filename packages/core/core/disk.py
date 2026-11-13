"""Guarda y reserva de disco (4.5)."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

GB = 1024 ** 3
RESERVATIONS_KEY = "disk:reservations"


@dataclass
class DiskStatus:
    total: int
    used: int
    free: int
    reserved: int
    usage_percent: float
    guard_active: bool

    def as_dict(self) -> dict:
        return {
            "total_gb": round(self.total / GB, 2),
            "used_gb": round(self.used / GB, 2),
            "free_gb": round(self.free / GB, 2),
            "reserved_gb": round(self.reserved / GB, 3),
            "usage_percent": round(self.usage_percent, 1),
            "guard_active": self.guard_active,
        }


def reserved_bytes(r) -> int:
    return sum(int(v) for v in r.hvals(RESERVATIONS_KEY))


def status(r, root: Path, max_usage_percent: float, min_free_gb: float) -> DiskStatus:
    root.mkdir(parents=True, exist_ok=True)
    total, used, free = shutil.disk_usage(root)
    reserved = reserved_bytes(r)
    pct = used / total * 100 if total else 100.0
    guard = pct >= max_usage_percent or (free - reserved) < min_free_gb * GB
    return DiskStatus(total, used, free, reserved, pct, guard)


def try_reserve(r, root: Path, key: str, size: int, factor: float, max_usage_percent: float, min_free_gb: float) -> bool:
    """Reserva tamaño × factor si, tras reservar, quedan al menos `min_free_gb` libres."""
    st = status(r, root, max_usage_percent, min_free_gb)
    needed = int(size * factor)
    if st.usage_percent >= max_usage_percent:
        return False
    if st.free - st.reserved - needed < min_free_gb * GB:
        return False
    r.hset(RESERVATIONS_KEY, key, needed)
    return True


def release(r, key: str) -> None:
    r.hdel(RESERVATIONS_KEY, key)


def transfer(r, old_keys: list[str], new_key: str) -> int:
    """Pasa las reservas de varias subidas a un trabajo."""
    total = 0
    for k in old_keys:
        v = r.hget(RESERVATIONS_KEY, k)
        if v:
            total += int(v)
            r.hdel(RESERVATIONS_KEY, k)
    if total:
        r.hset(RESERVATIONS_KEY, new_key, total)
    return total
