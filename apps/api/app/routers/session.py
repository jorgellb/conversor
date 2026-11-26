"""Sesión anónima con Turnstile (5.1 y 12.4)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.deps import client_ip, db, settings_dep, valkey_dep
from core import external
from core.errors import AppError, ErrorCode
from core.models import AnonClient
from core.quotas import today
from core.settings import Settings
from core.tokens import hash_ip, hash_token, issue_anon_token

router = APIRouter(prefix="/v1/session", tags=["sesión"])
ANON_TTL = 86400

# Sustituible en pruebas.
VERIFY = {"fn": external.verify_turnstile}


class AnonIn(BaseModel):
    turnstile_token: str = Field(min_length=1, max_length=4096)


@router.post("/anon")
def anon_session(body: AnonIn, request: Request, session: Session = Depends(db, scope="function"), settings: Settings = Depends(settings_dep), r=Depends(valkey_dep)):
    ip = client_ip(request, settings)
    ip_h = hash_ip(settings.ANON_TOKEN_SECRET, ip)
    key = f"anon:issued:{ip_h}:{today().isoformat()}"
    issued = r.incr(key)
    if issued == 1:
        r.expire(key, 90000)
    if issued > settings.ANON_TOKENS_PER_IP_DAY:
        raise AppError(ErrorCode.RATE_LIMITED, status=429)
    if not VERIFY["fn"](settings.TURNSTILE_SECRET_KEY, body.turnstile_token, ip):
        raise AppError(ErrorCode.TURNSTILE_FAILED, status=403)
    client_id = uuid.uuid4()
    token = issue_anon_token(settings.ANON_TOKEN_SECRET, str(client_id), ANON_TTL)
    session.add(AnonClient(id=client_id, token_hash=hash_token(token), ip_hash=ip_h,
                           expires_at=datetime.now(timezone.utc) + timedelta(seconds=ANON_TTL)))
    return {"token": token, "expires_in": ANON_TTL}
