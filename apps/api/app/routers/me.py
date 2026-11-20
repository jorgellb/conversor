"""Datos del usuario, uso, preferencias, exportación y borrado (8.1, 9.1 y 12.5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.deps import current_owner, current_user, db, settings_dep
from core.jobs import Owner, load_plan
from core.models import Job, Profile, SignatureRequest, Subscription, ToolFeedback, UsageDaily, UserToolPrefs
from core.quotas import usage
from core.settings import Settings
from core.storage import Store

router = APIRouter(prefix="/v1/me", tags=["cuenta"])


@router.get("")
def me(owner: Owner = Depends(current_owner), session: Session = Depends(db), settings: Settings = Depends(settings_dep)):
    plan = load_plan(session, owner.plan_id, settings)
    return {"type": owner.type, "id": owner.id, "email": owner.email, "plan": owner.plan_id,
            "is_admin": owner.is_admin, "limits": plan.model_dump()}


@router.get("/usage")
def my_usage(owner: Owner = Depends(current_owner), session: Session = Depends(db), settings: Settings = Depends(settings_dep)):
    plan = load_plan(session, owner.plan_id, settings)
    used = usage(session, owner.type, owner.id)
    return {"light": {"used": used.get("light", 0), "limit": plan.light_tasks_day},
            "heavy": {"used": used.get("heavy", 0), "limit": plan.heavy_tasks_day},
            "ai": {"used": used.get("ai", 0), "limit": plan.ai_requests_day}}


class PrefsIn(BaseModel):
    favorites: list[str] = Field(default_factory=list, max_length=100)
    recent: list[str] = Field(default_factory=list, max_length=30)


@router.get("/prefs")
def get_prefs(owner: Owner = Depends(current_user), session: Session = Depends(db)):
    prefs = session.get(UserToolPrefs, owner.id)
    return {"favorites": prefs.favorites if prefs else [], "recent": prefs.recent if prefs else []}


@router.put("/prefs")
def put_prefs(body: PrefsIn, owner: Owner = Depends(current_user), session: Session = Depends(db)):
    prefs = session.get(UserToolPrefs, owner.id) or UserToolPrefs(user_id=owner.id)
    prefs.favorites, prefs.recent = body.favorites, body.recent
    session.add(prefs)
    return {"ok": True}


@router.get("/export")
def export(owner: Owner = Depends(current_user), session: Session = Depends(db)):
    """Exportación de los datos que guarda la API (RGPD). Los de la cuenta los exporta la web."""
    profile = session.get(Profile, owner.id)
    sub = session.get(Subscription, owner.id)
    jobs = session.scalars(select(Job).where(Job.owner_type == "user", Job.owner_id == owner.id)).all()
    return {
        "profile": {"plan": profile.plan_id if profile else None, "locale": profile.locale if profile else None},
        "subscription": {"status": sub.status, "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None} if sub else None,
        "jobs": [{"id": str(j.id), "tool": j.tool, "status": j.status, "created_at": j.created_at.isoformat() if j.created_at else None} for j in jobs],
        "usage": [{"date": u.date.isoformat(), "class": u.cost_class, "tasks": u.tasks}
                  for u in session.scalars(select(UsageDaily).where(UsageDaily.owner_type == "user", UsageDaily.owner_id == owner.id)).all()],
        "signature_requests": [_request_export(session, r) for r in session.scalars(
            select(SignatureRequest).where(SignatureRequest.owner_id == owner.id)).all()],
    }


def _request_export(session: Session, req) -> dict:
    """solicitar-firmas (D-202): la solicitud, sus firmantes y su auditoría, sin hashes de tokens ni de códigos."""
    from core.models import AuditEvent, Signer

    return {
        "id": str(req.id), "document_name": req.document_name, "status": req.status,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "signers": [{"name": s.name, "email": s.email, "status": s.status, "signed_at": s.signed_at.isoformat() if s.signed_at else None}
                    for s in session.scalars(select(Signer).where(Signer.request_id == req.id)).all()],
        "events": [{"event": e.event, "actor": e.actor, "at": e.created_at.isoformat() if e.created_at else None}
                   for e in session.scalars(select(AuditEvent).where(AuditEvent.request_id == req.id).order_by(AuditEvent.id)).all()],
    }


@router.delete("")
def delete_me(owner: Owner = Depends(current_user), session: Session = Depends(db), settings: Settings = Depends(settings_dep)):
    store = Store(settings.FILESTORE_PATH)
    # solicitar-firmas (D-202): sus solicitudes, con firmantes, auditoría y archivos; los trabajos de cada una también.
    for req in session.scalars(select(SignatureRequest).where(SignatureRequest.owner_id == owner.id)).all():
        for job in session.scalars(select(Job).where(Job.owner_type == "request", Job.owner_id == str(req.id))).all():
            store.remove_job(str(job.id))
            session.delete(job)
        import shutil

        shutil.rmtree(store.request_dir(str(req.id)), ignore_errors=True)
        session.delete(req)
    for job in session.scalars(select(Job).where(Job.owner_type == "user", Job.owner_id == owner.id)).all():
        store.remove_job(str(job.id))
        session.delete(job)
    for model in (UsageDaily,):
        session.execute(delete(model).where(model.owner_type == "user", model.owner_id == owner.id))
    session.execute(delete(ToolFeedback).where(ToolFeedback.owner_type == "user", ToolFeedback.owner_id == owner.id))
    # Lo derivado de sus documentos para la IA (texto, fragmentos y caché, 9.4). Quedan `ai_requests` (sin contenido,
    # 90 días) y `ai_consents` (prueba del consentimiento, D-127).
    from sqlalchemy import text as sql

    from core.models import AiCache, DocumentText

    for model in (DocumentText, AiCache):
        session.execute(delete(model).where(model.owner_type == "user", model.owner_id == owner.id))
    session.execute(sql("DELETE FROM document_chunks WHERE owner_type = 'user' AND owner_id = :o"), {"o": owner.id})
    for model in (UserToolPrefs, Subscription, Profile):
        obj = session.get(model, owner.id)
        if obj is not None:
            session.delete(obj)
    return {"ok": True}
