"""Subidas y trabajos (5.1 y 9.1)."""
from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import current_owner, db, locale_of, registry_dep, settings_dep, valkey_dep
from core import disk
from core.db import get_sessionmaker
from core.errors import AppError, ErrorCode
from core.jobs import Owner, create_job, enqueue, public_view
from core.models import Job, Upload
from core.registry import Registry
from core.settings import Settings
from core.storage import Store

router = APIRouter(prefix="/v1", tags=["trabajos"])
FINAL = {"succeeded", "failed", "cancelled", "expired"}

# Sustituible en pruebas para ejecutar los trabajos de forma síncrona.
ENQUEUE = {"fn": None}


def _celery():
    from core.celeryapp import celery_app

    return celery_app


class JobIn(BaseModel):
    tool: str = Field(max_length=80)
    # Vacía solo en las herramientas que no reciben archivos (web-a-pdf).
    upload_ids: list[str] = Field(default_factory=list, max_length=200)
    options: dict = Field(default_factory=dict)
    ai_consent: bool | None = None


def _get_job(session: Session, job_id: str, owner: Owner) -> Job:
    try:
        uuid.UUID(job_id)
    except ValueError as exc:
        raise AppError(ErrorCode.NOT_FOUND, status=404) from exc
    job = session.get(Job, job_id)
    if job is None or job.owner_type != owner.type or job.owner_id != owner.id:
        raise AppError(ErrorCode.NOT_FOUND, status=404)
    return job


@router.get("/uploads/{upload_id}")
def upload_state(upload_id: str, owner: Owner = Depends(current_owner), session: Session = Depends(db, scope="function")):
    up = session.get(Upload, upload_id)
    if up is None or up.owner_type != owner.type or up.owner_id != owner.id:
        raise AppError(ErrorCode.NOT_FOUND, status=404)
    return {"id": up.id, "state": up.state, "size": up.size, "detected": up.detected_ext}


@router.post("/jobs", status_code=201)
def post_job(body: JobIn, request: Request, owner: Owner = Depends(current_owner), session: Session = Depends(db, scope="function"),
             registry: Registry = Depends(registry_dep), settings: Settings = Depends(settings_dep), r=Depends(valkey_dep)):
    job, sealed, reused = create_job(session, r, settings, registry, owner, body.tool, body.upload_ids, body.options,
                                     locale_of(request), body.ai_consent)
    try:
        session.commit()
    except Exception:
        if not reused and job.ai_reserved:
            from core.ai.budget import release

            release(r, settings, job.ai_reserved)
        raise
    if not reused:
        spec = registry.require(job.tool)
        if ENQUEUE["fn"] is not None:
            ENQUEUE["fn"](job, sealed, spec)
        else:
            enqueue(_celery(), r, job, sealed, spec)
    session.refresh(job)
    return public_view(job, settings, locale_of(request))


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request, owner: Owner = Depends(current_owner), session: Session = Depends(db, scope="function"),
            settings: Settings = Depends(settings_dep)):
    return public_view(_get_job(session, job_id, owner), settings, locale_of(request))


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request, owner: Owner = Depends(current_owner), settings: Settings = Depends(settings_dep),
                     session: Session = Depends(db, scope="function")):
    _get_job(session, job_id, owner)
    locale = locale_of(request)

    def snapshot() -> dict:
        s = get_sessionmaker()()
        try:
            job = s.get(Job, job_id)
            return public_view(job, settings, locale)
        finally:
            s.close()

    async def stream():
        last = None
        idle = 0.0
        while True:
            if await request.is_disconnected():
                return
            view = await run_in_threadpool(snapshot)
            key = (view["status"], round(view["progress"] or 0, 3), view["message"])
            if key != last:
                last = key
                idle = 0.0
                yield f"event: job\ndata: {json.dumps(view, ensure_ascii=False)}\n\n"
                if view["status"] in FINAL:
                    return
            await asyncio.sleep(1.0)
            idle += 1.0
            if idle >= 15:
                idle = 0.0
                yield ": latido\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, owner: Owner = Depends(current_owner), session: Session = Depends(db, scope="function"),
               settings: Settings = Depends(settings_dep), r=Depends(valkey_dep)):
    job = _get_job(session, job_id, owner)
    Store(settings.FILESTORE_PATH).remove_job(str(job.id))
    disk.release(r, f"job:{job.id}")
    job.status = "cancelled" if job.status in ("queued", "running") else "expired"
    return {"ok": True}


@router.get("/me/jobs")
def my_jobs(request: Request, owner: Owner = Depends(current_owner), session: Session = Depends(db, scope="function"), settings: Settings = Depends(settings_dep)):
    jobs = session.scalars(select(Job).where(Job.owner_type == owner.type, Job.owner_id == owner.id)
                           .order_by(Job.created_at.desc()).limit(50)).all()
    return {"jobs": [public_view(j, settings, locale_of(request)) for j in jobs]}
