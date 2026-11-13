"""Catálogo, límites por plan y valoraciones (9.1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.deps import db, registry_dep, settings_dep
from core.flags import is_tool_enabled
from core.jobs import db_flags
from core.models import ToolFeedback
from core.plans import load_plans_file
from core.registry import Registry
from core.settings import Settings
from app import auth

router = APIRouter(prefix="/v1", tags=["herramientas"])


@router.get("/tools")
def list_tools(session: Session = Depends(db), registry: Registry = Depends(registry_dep), settings: Settings = Depends(settings_dep)):
    flags = db_flags(session)
    plans = {pid: p.model_dump() for pid, p in load_plans_file(settings.PLANS_FILE).items()}
    tools = []
    for spec in registry.specs:
        item = spec.to_public()
        item["enabled"] = is_tool_enabled(spec.slug_es, flags)
        tools.append(item)
    return {"tools": tools, "plans": plans, "client_max_mb": settings.CLIENT_MAX_MB}


class FeedbackIn(BaseModel):
    tool: str = Field(max_length=80)
    rating: int | None = Field(default=None, ge=1, le=5)
    message: str | None = Field(default=None, max_length=2000)


@router.post("/feedback", status_code=201)
def feedback(body: FeedbackIn, authorization: str | None = Header(default=None), session: Session = Depends(db),
             registry: Registry = Depends(registry_dep), settings: Settings = Depends(settings_dep)):
    registry.require(body.tool)
    owner = auth.resolve_owner(authorization, session, settings) if authorization else None
    session.add(ToolFeedback(tool=body.tool, rating=body.rating, message=body.message,
                             owner_type=owner.type if owner else "none", owner_id=owner.id if owner else ""))
    return {"ok": True}
