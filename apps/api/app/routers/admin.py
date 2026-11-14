"""Panel de administración básico (8.1): colas, disco, flags, errores y purga."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import current_admin, db, registry_dep, settings_dep, valkey_dep
from core import disk, queueguard
from core.flags import is_tool_enabled
from core.jobs import Owner, db_flags
from core.models import AuditLog, FeatureFlag, Job
from core.registry import Registry
from core.settings import Settings

router = APIRouter(prefix="/v1/admin", tags=["administración"])


def overview_data(session: Session, r, settings: Settings, registry: Registry) -> dict:
    from datetime import timedelta

    from core.jobs import utcnow

    st = disk.status(r, Path(settings.FILESTORE_PATH), settings.DISK_MAX_USAGE_PERCENT, settings.DISK_MIN_FREE_GB)
    queues = sorted({s.queue for s in registry.server_tools() if s.queue})
    by_status = dict(session.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    since = utcnow() - timedelta(hours=24)
    rows = session.execute(
        select(Job.tool, func.count(), func.count().filter(Job.status == "failed"))
        .where(Job.created_at >= since).group_by(Job.tool)
    ).all()
    errors = {tool: {"failed": failed, "total": total, "rate": round(failed / total, 3) if total else 0.0}
              for tool, total, failed in rows if failed}
    return {
        "disk": st.as_dict(),
        "queues": {q: {"wait_seconds": int(queueguard.estimated_wait(r, q, q.split(".")[0])),
                       "pending": int(r.get(f"q:{q}:pending") or 0)} for q in queues},
        "jobs_by_status": by_status,
        "errors_by_tool": dict(sorted(errors.items(), key=lambda kv: -kv[1]["rate"])),
        "flags": db_flags(session),
        # Apagadas por el entorno, un flag temático o `default_enabled=False` (D-134): una fila de feature_flags no las
        # enciende, así que el panel no ofrece encenderlas.
        "locked_off": sorted(s.slug_es for s in registry.specs
                             if not is_tool_enabled(s.slug_es, {s.slug_es: True}, default=s.default_enabled)),
    }


@router.get("/overview")
def overview(_: Owner = Depends(current_admin), session: Session = Depends(db), r=Depends(valkey_dep),
             settings: Settings = Depends(settings_dep), registry: Registry = Depends(registry_dep)):
    return overview_data(session, r, settings, registry)


class FlagIn(BaseModel):
    enabled: bool


@router.put("/flags/{slug}")
def set_flag(slug: str, body: FlagIn, admin: Owner = Depends(current_admin), session: Session = Depends(db),
             registry: Registry = Depends(registry_dep)):
    spec = registry.require(slug)
    flag = session.get(FeatureFlag, spec.slug_es) or FeatureFlag(slug=spec.slug_es, plans=[])
    flag.enabled = body.enabled
    session.add(flag)
    session.add(AuditLog(actor=admin.email or admin.id, action="flag", target=f"{spec.slug_es}={body.enabled}"))
    return {"slug": spec.slug_es, "enabled": body.enabled}


@router.post("/purge")
def purge(admin: Owner = Depends(current_admin), session: Session = Depends(db)):
    from core.maintenance import cleanup_expired

    session.add(AuditLog(actor=admin.email or admin.id, action="purge", target=None))
    return cleanup_expired()
