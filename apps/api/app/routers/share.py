"""Enviar un resultado por correo (8.2.4): enlace firmado que caduca a las 24 horas, nunca el archivo adjunto."""
from __future__ import annotations

import logging
import os
import re
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.deps import client_ip, current_user, db, settings_dep
from core import external
from core.errors import AppError, ErrorCode
from core.jobs import Owner
from core.models import Job, Share
from core.quotas import count_mail_share
from core.settings import Settings
from core.storage import Store
from core.tokens import new_share_token

router = APIRouter(prefix="/v1", tags=["compartir"])
log = logging.getLogger("conversor.share")

SHARE_HOURS = 24
PRO_MAX_RECIPIENTS = 3
EMAIL_RE = re.compile(r"^[^@\s<>\"',;]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,}$")

# Sustituibles en pruebas.
VERIFY = {"fn": external.verify_turnstile}
SEND = {"fn": external.send_mail}

TEXTS = {
    "es": {
        "subject_self": "Tu archivo de {site}: {name}",
        "subject_other": "{sender} te envía un archivo: {name}",
        "body": ("{intro}\n\nDescárgalo aquí (el enlace caduca el {expires} UTC):\n{url}\n\n"
                 "No respondas a este correo. Si no esperabas este archivo o crees que es un abuso, avísanos:\n{abuse}\n"
                 "Indica este código: {code}\n"),
        "intro_self": "Aquí tienes el resultado de {site}: «{name}».",
        "intro_other": "{sender} ha usado {site} y te envía «{name}».",
        "contact": "contacto",
    },
    "en": {
        "subject_self": "Your file from {site}: {name}",
        "subject_other": "{sender} sent you a file: {name}",
        "body": ("{intro}\n\nDownload it here (the link expires on {expires} UTC):\n{url}\n\n"
                 "Do not reply to this email. If you did not expect this file or think it is abuse, let us know:\n{abuse}\n"
                 "Quote this code: {code}\n"),
        "intro_self": "Here is your result from {site}: “{name}”.",
        "intro_other": "{sender} used {site} and sent you “{name}”.",
        "contact": "contact",
    },
}


class MailIn(BaseModel):
    to: list[str] = Field(min_length=1, max_length=PRO_MAX_RECIPIENTS)
    turnstile_token: str = Field(min_length=1, max_length=4096)
    locale: Literal["es", "en"] = "es"

    @field_validator("to")
    @classmethod
    def _emails(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for raw in value:
            email = raw.strip().lower()
            if not EMAIL_RE.match(email):
                raise ValueError("Dirección de correo no válida")
            if email not in out:
                out.append(email)
        return out


def _share_copy(src: Path, dst_dir: Path, filename: str) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / filename
    try:
        os.link(src, dst)  # mismo volumen: sin copia
    except OSError:
        shutil.copyfile(src, dst)
    return dst


@router.post("/jobs/{job_id}/outputs/{position}/mail")
def mail_output(job_id: str, position: int, body: MailIn, request: Request, owner: Owner = Depends(current_user),
                session: Session = Depends(db), settings: Settings = Depends(settings_dep)):
    try:
        job = session.get(Job, uuid.UUID(job_id))
    except ValueError as exc:
        raise AppError(ErrorCode.NOT_FOUND, status=404) from exc
    if job is None or job.owner_type != owner.type or job.owner_id != owner.id:
        raise AppError(ErrorCode.NOT_FOUND, status=404)
    output = next((o for o in job.outputs if o.position == position), None) if job.status == "succeeded" else None
    if output is None or not Path(output.path).is_file():
        raise AppError(ErrorCode.NOT_FOUND, status=404, detail="El resultado no existe o ya se ha borrado")
    if not owner.email or not owner.email_verified:
        raise AppError(ErrorCode.FORBIDDEN, status=403, detail="Hace falta un correo verificado")
    if not owner.is_pro and body.to != [owner.email.lower()]:
        # Plan gratuito: solo a su propia dirección verificada.
        raise AppError(ErrorCode.FORBIDDEN, status=403, detail="En el plan gratuito solo puedes enviártelo a ti")
    if not VERIFY["fn"](settings.TURNSTILE_SECRET_KEY, body.turnstile_token, client_ip(request, settings)):
        raise AppError(ErrorCode.TURNSTILE_FAILED, status=403)
    count_mail_share(session, owner.id, settings.MAIL_SHARE_DAILY_LIMIT)

    token, token_hash = new_share_token()
    share = Share(id=uuid.uuid4(), job_output_id=output.id, owner_id=owner.id, filename=output.filename, token_hash=token_hash,
                  expires_at=datetime.now(timezone.utc) + timedelta(hours=SHARE_HOURS))
    store = Store(settings.FILESTORE_PATH)
    share_dir = store.share_dir(str(share.id))
    _share_copy(Path(output.path), share_dir, output.filename)
    session.add(share)
    session.flush()

    t = TEXTS[body.locale]
    site = settings.APP_NAME
    to_self = body.to == [owner.email.lower()]
    url = f"{settings.PUBLIC_FILES_URL.rstrip('/')}/s/{share.id}/{output.filename}?t={token}"
    abuse = f"{settings.PUBLIC_WEB_URL.rstrip('/')}/{body.locale}/{t['contact']}?abuso={share.id}"
    intro = (t["intro_self"] if to_self else t["intro_other"]).format(site=site, name=output.name, sender=owner.email)
    subject = (t["subject_self"] if to_self else t["subject_other"]).format(site=site, name=output.name, sender=owner.email)
    text = t["body"].format(intro=intro, url=url, abuse=abuse, code=share.id, expires=share.expires_at.strftime("%d/%m/%Y %H:%M"))
    try:
        SEND["fn"](settings.SMTP_URL, settings.MAIL_FROM, body.to, subject[:200], text)
    except Exception as exc:  # noqa: BLE001 - SMTP caído o mal configurado
        shutil.rmtree(share_dir, ignore_errors=True)
        log.warning("envío de resultado fallido", extra={"job_id": str(job.id), "error": type(exc).__name__})
        raise AppError(ErrorCode.MAIL_FAILED, status=502) from exc
    log.info("resultado enviado por correo", extra={"job_id": str(job.id), "recipients": len(body.to)})
    return {"sent": len(body.to), "expires_at": share.expires_at.isoformat()}


# --- compartir-pdf (7.7, F4-C1, D-200): enlace firmado con caducidad elegible, revocable y con contador de descargas ---

SHARE_HOURS_CHOICES = (1, 24, 72, 168)
FREE_MAX_HOURS = 24  # 9: retención de 24 h con cuenta; «compartir hasta 7 días», en Pro (SHARE_MAX_DAYS)


class ShareIn(BaseModel):
    job_id: uuid.UUID
    position: int = Field(ge=0, le=1000)
    hours: int = Field(ge=1, le=24 * 30)
    turnstile_token: str = Field(min_length=1, max_length=4096)


def _share_view(share: Share, settings: Settings, token: str | None = None) -> dict:
    view = {"id": str(share.id), "filename": share.filename, "expires_at": share.expires_at.isoformat(), "downloads": share.downloads,
            "revoked": share.revoked_at is not None}
    if token:
        view["url"] = f"{settings.PUBLIC_FILES_URL.rstrip('/')}/s/{share.id}/{share.filename}?t={token}"
    return view


@router.post("/shares")
def create_share(body: ShareIn, request: Request, owner: Owner = Depends(current_user), session: Session = Depends(db),
                 settings: Settings = Depends(settings_dep)):
    """Enlace para descargar un resultado durante 1 hora, 1, 3 o 7 días (Pro hasta SHARE_MAX_DAYS; gratis, 24 h).
    Solo con cuenta: el enlace dura más que la retención de un anónimo. El token solo se ve una vez (se guarda su hash)."""
    if owner.type != "user":
        raise AppError(ErrorCode.UNAUTHORIZED, status=401, detail="share_account")
    limit = settings.SHARE_MAX_DAYS * 24 if owner.is_pro else FREE_MAX_HOURS
    if body.hours not in SHARE_HOURS_CHOICES or body.hours > limit:
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422, detail=f"share_hours:{body.hours}>{limit}")
    job = session.get(Job, body.job_id)
    if job is None or job.owner_type != owner.type or job.owner_id != owner.id:
        raise AppError(ErrorCode.NOT_FOUND, status=404)
    output = next((o for o in job.outputs if o.position == body.position), None) if job.status == "succeeded" else None
    if output is None or not Path(output.path).is_file():
        raise AppError(ErrorCode.NOT_FOUND, status=404, detail="El resultado no existe o ya se ha borrado")
    if not VERIFY["fn"](settings.TURNSTILE_SECRET_KEY, body.turnstile_token, client_ip(request, settings)):
        raise AppError(ErrorCode.TURNSTILE_FAILED, status=403)
    count_mail_share(session, owner.id, settings.MAIL_SHARE_DAILY_LIMIT)  # el mismo cupo diario que enviar por correo
    token, token_hash = new_share_token()
    share = Share(id=uuid.uuid4(), job_output_id=output.id, owner_id=owner.id, filename=output.filename, token_hash=token_hash,
                  expires_at=datetime.now(timezone.utc) + timedelta(hours=body.hours))
    store = Store(settings.FILESTORE_PATH)
    _share_copy(Path(output.path), store.share_dir(str(share.id)), output.filename)
    session.add(share)
    session.flush()
    log.info("enlace para compartir", extra={"job_id": str(job.id), "hours": body.hours})
    return _share_view(share, settings, token)


@router.get("/shares")
def list_shares(owner: Owner = Depends(current_user), session: Session = Depends(db), settings: Settings = Depends(settings_dep)):
    """Los enlaces del usuario que no han caducado (los caducados los borra el mantenimiento), sin el token."""
    if owner.type != "user":
        raise AppError(ErrorCode.UNAUTHORIZED, status=401, detail="share_account")
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    rows = session.scalars(select(Share).where(Share.owner_id == owner.id, Share.expires_at > now).order_by(Share.expires_at.desc()).limit(100))
    return {"shares": [_share_view(s, settings) for s in rows]}


@router.delete("/shares/{share_id}")
def revoke_share(share_id: uuid.UUID, owner: Owner = Depends(current_user), session: Session = Depends(db),
                 settings: Settings = Depends(settings_dep)):
    """Revoca el enlace al momento (files/authorize lo comprueba en la base de datos) y borra su copia."""
    share = session.get(Share, share_id)
    if share is None or owner.type != "user" or share.owner_id != owner.id:
        raise AppError(ErrorCode.NOT_FOUND, status=404)
    if share.revoked_at is None:
        share.revoked_at = datetime.now(timezone.utc)
        shutil.rmtree(Store(settings.FILESTORE_PATH).share_dir(str(share.id)), ignore_errors=True)
    return _share_view(share, settings)
