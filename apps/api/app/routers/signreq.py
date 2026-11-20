"""solicitar-firmas (7.7 y 9.1, F4-C2, D-202): /v1/signature-requests (propietario, con cuenta) y /v1/sign/{token}
(firmante, sin cuenta, con el enlace de su correo).

La API es la única que escribe en `signature_requests`, `signers` y `audit_events` junto con beat. Cada consulta avanza
la solicitud (core.signreq.advance), así que el estado no espera al minuto de beat.
"""
from __future__ import annotations

import base64
import io
import logging
import re
import secrets
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import client_ip, current_user, db, registry_dep, settings_dep, valkey_dep
from app.routers.share import EMAIL_RE
from core import external, signreq
from core.errors import AppError, ErrorCode
from core.jobs import Owner
from core.models import Job, SignatureRequest, Signer
from core.registry import Registry
from core.settings import Settings
from core.storage import sanitize_filename
from core.tokens import hash_ip, hash_token

router = APIRouter(prefix="/v1", tags=["firmas"])
log = logging.getLogger("conversor.signreq")

# Sustituibles en pruebas.
VERIFY = {"fn": external.verify_turnstile}
MAX_IMAGE_BYTES = 400_000
CONSENT = {
    "es": "Acepto firmar electrónicamente «{doc}» y que el sello de la plataforma acredite mi firma, la fecha y mi correo.",
    "en": "I agree to sign “{doc}” electronically and to the platform seal proving my signature, the date and my email.",
}


def _send(settings: Settings, to: list[str], subject: str, body: str) -> None:
    (signreq.SEND["fn"] or external.send_mail)(settings.SMTP_URL, settings.MAIL_FROM, to, subject, body)


def _send_now(effects: signreq.Effects, settings: Settings) -> None:
    """Los correos que tienen que salir para que la operación valga (invitaciones al crear, el código): si el SMTP falla,
    la operación se deshace y la página lo dice."""
    try:
        for to, subject, body in effects.mails:
            _send(settings, to, subject, body)
    except Exception as exc:  # noqa: BLE001 - SMTP caído o mal configurado
        log.warning("correo de solicitud de firmas fallido", extra={"error": type(exc).__name__})
        raise AppError(ErrorCode.MAIL_FAILED, status=502) from exc
    effects.mails.clear()


def _audit_from(request: Request, settings: Settings) -> dict:
    return {"ip_hash": hash_ip(settings.ANON_TOKEN_SECRET or "x", client_ip(request, settings)),
            "user_agent": (request.headers.get("user-agent") or "")[:400] or None}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# --- Propietario -------------------------------------------------------------------------------------------------------


class SignerIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Falta el nombre")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("Dirección de correo no válida")
        return value


class RequestIn(BaseModel):
    job_id: uuid.UUID
    position: int = Field(0, ge=0, le=10)
    signers: list[SignerIn] = Field(min_length=1, max_length=signreq.MAX_SIGNERS)
    sequential: bool = True
    message: str = Field("", max_length=1000)
    days: int = Field(14, ge=1, le=signreq.MAX_DAYS)
    locale: Literal["es", "en"] = "es"
    turnstile_token: str = Field(min_length=1, max_length=4096)


def _owner_view(session: Session, settings: Settings, req: SignatureRequest, events: bool = False) -> dict:
    view = {
        "id": str(req.id), "document_name": req.document_name, "status": req.status, "sequential": req.sequential,
        "message": req.message or "", "created_at": _iso(req.created_at), "expires_at": _iso(req.expires_at),
        "completed_at": _iso(req.completed_at), "files": signreq.file_links(settings, req, "owner"),
        "signers": [{"id": str(s.id), "name": s.name, "email": s.email, "status": s.status, "signed_at": _iso(s.signed_at),
                     "invited_at": _iso(s.invited_at)} for s in signreq.signers_of(session, req)],
    }
    if events:
        from core.models import AuditEvent

        rows = session.scalars(select(AuditEvent).where(AuditEvent.request_id == req.id).order_by(AuditEvent.id)).all()
        view["events"] = [{"event": e.event, "actor": e.actor, "at": _iso(e.created_at), "detail": e.detail or ""} for e in rows]
    return view


def _require_account(owner: Owner) -> None:
    if owner.type != "user":
        raise AppError(ErrorCode.UNAUTHORIZED, status=401, detail="request_account")


def _mine(session: Session, owner: Owner, request_id: uuid.UUID, for_update: bool = True) -> SignatureRequest:
    _require_account(owner)
    query = select(SignatureRequest).where(SignatureRequest.id == request_id)
    req = session.scalars(query.with_for_update() if for_update else query).first()
    if req is None or req.owner_id != owner.id:
        raise AppError(ErrorCode.NOT_FOUND, status=404)
    return req


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _take(r, key: str, limit: int, n: int = 1) -> bool:
    """Contador del día en Valkey: no baja al borrar una solicitud (si no, crear y borrar saltaría el cupo)."""
    total = r.incrby(key, n)
    r.expire(key, 2 * 86400)
    if total > limit:
        r.decrby(key, n)
        return False
    return True


def _recipient_key(email: str) -> str:
    import hashlib

    return f"signreq:to:{hashlib.sha256(email.encode()).hexdigest()[:32]}:{_day()}"


@router.post("/signature-requests", status_code=201)
def create_request(body: RequestIn, request: Request, owner: Owner = Depends(current_user), session: Session = Depends(db),
                   settings: Settings = Depends(settings_dep), registry: Registry = Depends(registry_dep), r=Depends(valkey_dep)):
    """Crea la solicitud con el PDF que ha preparado la fase `preparar` del mismo usuario y manda las invitaciones (a
    todos en paralelo; al primero si es en orden)."""
    _require_account(owner)
    if not owner.email or not owner.email_verified:
        raise AppError(ErrorCode.FORBIDDEN, status=403, detail="request_email")
    if not settings.SEAL_ENABLED:
        raise AppError(ErrorCode.TOOL_DISABLED, status=400, detail="seal_disabled")
    job = session.get(Job, body.job_id)
    if job is None or job.owner_type != owner.type or job.owner_id != owner.id or job.tool != signreq.TOOL:
        raise AppError(ErrorCode.NOT_FOUND, status=404, detail="request_job")
    output = next((o for o in job.outputs if o.position == body.position), None) if job.status == "succeeded" else None
    if (job.options or {}).get("fase", "preparar") != "preparar" or output is None or not Path(output.path).is_file():
        raise AppError(ErrorCode.NOT_FOUND, status=404, detail="request_job")
    if output.size > signreq.MAX_MB * 1024 * 1024:
        raise AppError(ErrorCode.LIMIT_EXCEEDED, status=413, detail=f"seal_size:{output.size // 1048576}>{signreq.MAX_MB}")
    planned = (job.options or {}).get("firmantes") or []
    limit = signreq.MAX_SIGNERS if owner.is_pro else signreq.FREE_MAX_SIGNERS
    if len(body.signers) > limit:
        raise AppError(ErrorCode.LIMIT_EXCEEDED, status=422, detail=f"request_signers:{len(body.signers)}>{limit}")
    if len(planned) != len(body.signers) or any(" ".join(str(p.get("nombre", "")).split()) != s.name for p, s in zip(planned, body.signers)):
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422, detail="request_mismatch")
    if len({s.email for s in body.signers}) != len(body.signers):
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422, detail="request_duplicate_email")
    if not VERIFY["fn"](settings.TURNSTILE_SECRET_KEY, body.turnstile_token, client_ip(request, settings)):
        raise AppError(ErrorCode.TURNSTILE_FAILED, status=403)
    from core import disk

    if disk.status(r, Path(settings.FILESTORE_PATH), settings.DISK_MAX_USAGE_PERCENT, settings.DISK_MIN_FREE_GB).guard_active:
        raise AppError(ErrorCode.DISK_FULL, status=503)
    # Solicitudes abiertas a la vez (el disco de requests/ no pasa por la reserva de los trabajos).
    session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"signreq:{owner.id}"))))
    open_now = int(session.execute(select(func.count()).select_from(SignatureRequest).where(
        SignatureRequest.owner_id == owner.id, SignatureRequest.status.in_(signreq.ACTIVE))).scalar_one())
    max_open = signreq.MAX_ACTIVE["pro" if owner.is_pro else "free"]
    if open_now >= max_open:
        raise AppError(ErrorCode.QUOTA_EXCEEDED, status=429, detail=f"request_open:{max_open}>{max_open}")
    daily = settings.SIGN_REQUEST_DAILY_LIMIT if owner.is_pro else signreq.FREE_SIGN_REQUESTS_PER_DAY
    if not _take(r, f"signreq:day:{owner.id}:{_day()}", daily):
        raise AppError(ErrorCode.QUOTA_EXCEEDED, status=429, detail=f"request_limit:{daily}>{daily}")
    first = body.signers if not body.sequential else body.signers[:1]
    for s in first:
        if not _take(r, _recipient_key(s.email), signreq.INVITES_PER_RECIPIENT_DAY):
            raise AppError(ErrorCode.RATE_LIMITED, status=429, detail="request_recipient")
    # Los sellos de la solicitud (uno por firmante, el final y el del certificado) cuentan para la cuenta desde ya.
    from tools.sign import firmar

    seals = len(body.signers) + 2
    try:
        firmar.reserve_account(settings, ("user", owner.id), seals)
    except AppError as exc:
        raise AppError(ErrorCode.QUOTA_EXCEEDED, status=429, detail="seal_account_limit") from exc

    now = datetime.now(timezone.utc)
    filename = sanitize_filename(output.filename or "documento.pdf")
    req = SignatureRequest(
        id=uuid.uuid4(), owner_id=owner.id, job_output_id=output.id, status="pending", created_at=now,
        expires_at=now + timedelta(days=body.days), document_name=(output.name or filename)[:200], filename=filename,
        message=body.message.strip() or None, sequential=body.sequential, locale=body.locale, owner_email=owner.email.lower(),
        original_sha256=job.inputs[0].sha256 if job.inputs else None, document_sha256=output.sha256, final_files=[],
        final_attempts=0)
    session.add(req)
    session.flush()
    folder = signreq.request_dir(settings, req)
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(output.path, folder / filename)
    effects = signreq.Effects()
    try:
        signers = []
        for i, (planned_signer, s) in enumerate(zip(planned, body.signers)):
            signer = Signer(id=uuid.uuid4(), request_id=req.id, email=s.email, name=s.name, sign_order=i,
                            token_hash=hash_token(secrets.token_urlsafe(32)), status="waiting",
                            field=signreq.field_name(i, str(planned_signer.get("campo", ""))), job_attempts=0, code_attempts=0)
            session.add(signer)
            signers.append(signer)
        session.flush()
        signreq.audit(session, req, "created", req.owner_email, sha256=req.document_sha256,
                      detail=f"{len(signers)} firmantes, {'en orden' if req.sequential else 'en paralelo'}", **_audit_from(request, settings))
        for signer in signers if not req.sequential else signers[:1]:
            signreq.invite(effects, session, settings, req, signer)
        _send_now(effects, settings)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        firmar.release_account(("user", owner.id), seals)
        raise
    # El documento preparado ya está en la solicitud: el trabajo no sirve para crear otra.
    from core.storage import Store

    Store(settings.FILESTORE_PATH).remove_job(str(job.id))
    job.status = "expired"
    session.commit()
    log.info("solicitud de firmas creada", extra={"request_id": str(req.id), "signers": len(signers)})
    return _owner_view(session, settings, req)


def _refresh(session: Session, settings: Settings, registry: Registry, req: SignatureRequest, effects: signreq.Effects) -> None:
    if req.status in signreq.ACTIVE:
        signreq.advance(effects, session, settings, registry, req)


@router.get("/signature-requests")
def list_requests(owner: Owner = Depends(current_user), session: Session = Depends(db), settings: Settings = Depends(settings_dep),
                  registry: Registry = Depends(registry_dep)):
    _require_account(owner)
    ids = list(session.scalars(select(SignatureRequest.id).where(SignatureRequest.owner_id == owner.id)
                               .order_by(SignatureRequest.created_at.desc()).limit(50)))
    effects = signreq.Effects()
    views = []
    for request_id in ids:
        req = _mine(session, owner, request_id)
        try:
            with session.begin_nested():  # una solicitud que falla al avanzar no rompe la lista
                _refresh(session, settings, registry, req, effects)
        except Exception:  # noqa: BLE001
            log.exception("no se ha podido avanzar la solicitud", extra={"request_id": str(request_id)})
            session.refresh(req)
        views.append(_owner_view(session, settings, req))
    session.commit()
    signreq.deliver(effects, settings)
    return {"requests": views}


@router.get("/signature-requests/{request_id}")
def get_request(request_id: uuid.UUID, owner: Owner = Depends(current_user), session: Session = Depends(db),
                settings: Settings = Depends(settings_dep), registry: Registry = Depends(registry_dep)):
    req = _mine(session, owner, request_id)
    effects = signreq.Effects()
    _refresh(session, settings, registry, req, effects)
    view = _owner_view(session, settings, req, events=True)
    session.commit()
    signreq.deliver(effects, settings)
    return view


@router.delete("/signature-requests/{request_id}")
def cancel_request(request_id: uuid.UUID, owner: Owner = Depends(current_user), session: Session = Depends(db),
                   settings: Settings = Depends(settings_dep)):
    """Activa: se cancela, se avisa a quien ya la conocía y se borra el documento. Cerrada: se borra del todo (también
    su auditoría y sus archivos)."""
    req = _mine(session, owner, request_id)
    effects = signreq.Effects()
    if req.status == "finalizing":
        # Han firmado todos y se está sellando: se puede borrar cuando termine.
        raise AppError(ErrorCode.INVALID_OPTIONS, status=409, detail="request_finalizing")
    if req.status in signreq.ACTIVE:
        signers = signreq.signers_of(session, req)
        signreq.audit(session, req, "cancelled", req.owner_email)
        signreq.close(session, settings, req, "cancelled")
        for s in signers:
            if s.status in ("invited", "queued", "signing", "signed"):
                signreq.mail(effects, settings, req, "cancelled_signer", [s.email], name=s.name)
        view = _owner_view(session, settings, req)
    else:
        shutil.rmtree(signreq.request_dir(settings, req), ignore_errors=True)
        signreq.drop_jobs(session, settings, req)
        session.delete(req)
        view = {"id": str(request_id), "deleted": True}
    session.commit()
    signreq.deliver(effects, settings)
    return view


@router.post("/signature-requests/{request_id}/remind")
def remind(request_id: uuid.UUID, owner: Owner = Depends(current_user), session: Session = Depends(db),
           settings: Settings = Depends(settings_dep), r=Depends(valkey_dep)):
    """Recordatorio a quien tiene que firmar ahora: como mucho uno por firmante y día y tres en total, y dentro del tope
    de correos por destinatario. Lleva un enlace nuevo: solo se guarda el hash del token y el anterior deja de valer."""
    req = _mine(session, owner, request_id)
    if req.status != "pending":
        raise AppError(ErrorCode.INVALID_OPTIONS, status=409, detail="request_closed")
    effects = signreq.Effects()
    limit = datetime.now(timezone.utc) - timedelta(minutes=signreq.REMIND_MINUTES)
    count = 0
    for s in signreq.signers_of(session, req):
        if s.status != "invited" or (s.invited_at is not None and s.invited_at >= limit):
            continue
        if _count_events(session, req, "reminded", s.email) >= signreq.MAX_REMINDERS:
            continue
        if not _take(r, _recipient_key(s.email), signreq.INVITES_PER_RECIPIENT_DAY):
            continue
        signreq.invite(effects, session, settings, req, s, kind="remind")
        count += 1
    session.commit()
    signreq.deliver(effects, settings)
    return {"reminded": count}


def _count_events(session: Session, req: SignatureRequest, event: str, actor: str) -> int:
    from core.models import AuditEvent

    return int(session.execute(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.request_id == req.id, AuditEvent.event == event, AuditEvent.actor == actor)).scalar_one())


# --- Firmante ----------------------------------------------------------------------------------------------------------


def _by_token(session: Session, token: str) -> tuple[Signer, SignatureRequest]:
    """El firmante del enlace y su solicitud, bloqueada (todas las operaciones del firmante la modifican)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", token or ""):
        raise AppError(ErrorCode.NOT_FOUND, status=404, detail="sign_link")
    signer = session.scalars(select(Signer).where(Signer.token_hash == hash_token(token))).first()
    if signer is None:
        raise AppError(ErrorCode.NOT_FOUND, status=404, detail="sign_link")
    req = signreq.lock(session, signer.request_id)
    if req is None:
        raise AppError(ErrorCode.NOT_FOUND, status=404, detail="sign_link")
    session.refresh(signer)
    if signer.token_hash != hash_token(token):  # un recordatorio lo ha cambiado mientras se esperaba el bloqueo
        raise AppError(ErrorCode.NOT_FOUND, status=404, detail="sign_link")
    return signer, req


def _signer_view(session: Session, settings: Settings, req: SignatureRequest, signer: Signer, token: str) -> dict:
    folder = signreq.request_dir(settings, req)
    active = req.status in signreq.ACTIVE and req.purged_at is None
    now = datetime.now(timezone.utc)
    view = {
        "request": {"document_name": req.document_name, "owner_email": req.owner_email, "message": req.message or "",
                    "status": req.status, "sequential": req.sequential, "expires_at": _iso(req.expires_at),
                    "locale": req.locale},
        "signer": {"name": signer.name, "email": signer.email, "status": signer.status, "signed_at": _iso(signer.signed_at),
                   "can_sign": req.status == "pending" and signer.status == "invited",
                   "code_sent": bool(signer.code_hash and signer.code_expires_at and signer.code_expires_at > now)},
        "signers": [{"name": s.name, "status": s.status, "me": s.id == signer.id} for s in signreq.signers_of(session, req)],
        "consent": CONSENT.get(req.locale, CONSENT["es"]).format(doc=req.document_name),
        "document_url": (f"{settings.PUBLIC_FILES_URL.rstrip('/')}/r/{req.id}/{req.filename}?t={token}"
                         if active and (folder / req.filename).is_file() else None),
        "files": signreq.file_links(settings, req, str(signer.id).replace("-", "")[:16]),
    }
    return view


@router.get("/sign/{token}")
def signer_get(token: str, request: Request, session: Session = Depends(db), settings: Settings = Depends(settings_dep),
               registry: Registry = Depends(registry_dep)):
    signer, req = _by_token(session, token)
    effects = signreq.Effects()
    _refresh(session, settings, registry, req, effects)
    if req.status == "pending" and signer.status == "invited":
        # Cada vez que abre la página (el certificado las resume); que ha descargado el documento lo anota files/authorize.
        signreq.audit(session, req, "opened", signer.email, sha256=req.document_sha256, **_audit_from(request, settings))
    view = _signer_view(session, settings, req, signer, token)
    session.commit()
    signreq.deliver(effects, settings)
    return view


class CodeIn(BaseModel):
    turnstile_token: str = Field(min_length=1, max_length=4096)


def _can_sign(req: SignatureRequest, signer: Signer) -> None:
    if req.status != "pending" or req.expires_at <= datetime.now(timezone.utc):
        raise AppError(ErrorCode.INVALID_OPTIONS, status=409, detail="sign_closed")
    if signer.status != "invited":
        raise AppError(ErrorCode.INVALID_OPTIONS, status=409, detail="sign_not_now")


@router.post("/sign/{token}/code")
def signer_code(token: str, body: CodeIn, request: Request, session: Session = Depends(db), r=Depends(valkey_dep),
                settings: Settings = Depends(settings_dep)):
    """Código de 6 cifras al correo del firmante: 15 minutos, 5 intentos y como mucho 5 códigos por hora."""
    signer, req = _by_token(session, token)
    _can_sign(req, signer)
    if not VERIFY["fn"](settings.TURNSTILE_SECRET_KEY, body.turnstile_token, client_ip(request, settings)):
        raise AppError(ErrorCode.TURNSTILE_FAILED, status=403)
    key = f"signcode:{signer.id}:{int(datetime.now(timezone.utc).timestamp() // 3600)}"
    n = r.incr(key)
    if n == 1:
        r.expire(key, 3700)
    if n > signreq.CODES_PER_HOUR or _count_events(session, req, "code_sent", signer.email) >= signreq.MAX_CODES:
        raise AppError(ErrorCode.RATE_LIMITED, status=429, detail="sign_code_rate")
    code = f"{secrets.randbelow(10 ** 6):06d}"
    signer.code_hash = signreq.code_hash(settings, signer.id, code)
    signer.code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=signreq.CODE_MINUTES)
    signer.code_attempts = 0
    signreq.audit(session, req, "code_sent", signer.email, **_audit_from(request, settings))
    effects = signreq.Effects()
    signreq.mail(effects, settings, req, "code", [signer.email], code=code, minutes=signreq.CODE_MINUTES)
    _send_now(effects, settings)
    session.commit()
    return {"sent": True, "expires_at": _iso(signer.code_expires_at)}


def _check_code(session: Session, settings: Settings, req: SignatureRequest, signer: Signer, code: str, meta: dict) -> None:
    import hmac

    if not signer.code_hash or not signer.code_expires_at or signer.code_expires_at < datetime.now(timezone.utc):
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422, detail="sign_code_expired")
    if signer.code_attempts >= signreq.CODE_ATTEMPTS:
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422, detail="sign_code_locked")
    if not hmac.compare_digest(signer.code_hash, signreq.code_hash(settings, signer.id, code)):
        signer.code_attempts += 1
        signreq.audit(session, req, "code_failed", signer.email, **meta)
        left = max(0, signreq.CODE_ATTEMPTS - signer.code_attempts)
        session.commit()  # el intento cuenta aunque la respuesta sea un error
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422, detail="sign_code_invalid" if left else "sign_code_locked",
                       extra={"attempts_left": left})


class SignIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    image: str = Field(min_length=30, max_length=MAX_IMAGE_BYTES * 4 // 3 + 64)
    consent: Literal[True]


def _png(data_url: str) -> bytes:
    """La imagen de la firma, comprobada y vuelta a codificar (sin metadatos ni nada que no sea la imagen)."""
    from PIL import Image

    prefix = "data:image/png;base64,"
    if not data_url.startswith(prefix):
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422, detail="request_image")
    try:
        raw = base64.b64decode(data_url[len(prefix):], validate=True)
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("grande")
        with Image.open(io.BytesIO(raw)) as img:
            if img.format != "PNG" or img.width > 2000 or img.height > 1000 or img.width < 20 or img.height < 10:
                raise ValueError("tamaño")
            rgba = img.convert("RGBA")
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001 - base64 o PNG rotos
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422, detail="request_image") from exc
    if rgba.getchannel("A").getbbox() is None:  # transparente del todo: no hay firma
        raise AppError(ErrorCode.INVALID_OPTIONS, status=422, detail="request_image")
    out = io.BytesIO()
    rgba.save(out, format="PNG", optimize=True)
    return out.getvalue()


@router.post("/sign/{token}")
def signer_sign(token: str, body: SignIn, request: Request, session: Session = Depends(db), settings: Settings = Depends(settings_dep),
                registry: Registry = Depends(registry_dep)):
    """Con el código, la imagen y el consentimiento, el firmante queda en cola y se sella en cuanto no haya otro."""
    signer, req = _by_token(session, token)
    _can_sign(req, signer)
    meta = _audit_from(request, settings)
    _check_code(session, settings, req, signer, body.code, meta)
    png = _png(body.image)
    image = signreq.signature_image(settings, req, signer)
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(png)
    signer.code_hash, signer.code_expires_at, signer.status = None, None, "queued"
    signreq.audit(session, req, "code_verified", signer.email, **meta)
    signreq.audit(session, req, "consented", signer.email, sha256=req.document_sha256,
                  detail=CONSENT.get(req.locale, CONSENT["es"]).format(doc=req.document_name), **meta)
    effects = signreq.Effects()
    signreq.advance(effects, session, settings, registry, req)
    view = _signer_view(session, settings, req, signer, token)
    session.commit()
    signreq.deliver(effects, settings)
    return view


class DeclineIn(BaseModel):
    """Rechazar también pide el código: con el enlace solo (un correo reenviado, un registro) no se cierra la solicitud."""

    code: str = Field(pattern=r"^\d{6}$")
    reason: str = Field("", max_length=500)


@router.post("/sign/{token}/decline")
def signer_decline(token: str, body: DeclineIn, request: Request, session: Session = Depends(db),
                   settings: Settings = Depends(settings_dep)):
    signer, req = _by_token(session, token)
    _can_sign(req, signer)
    meta = _audit_from(request, settings)
    _check_code(session, settings, req, signer, body.code, meta)
    reason = " ".join(body.reason.split())[:500]
    signer.code_hash, signer.code_expires_at = None, None
    others = signreq.signers_of(session, req)
    signer.status = "declined"
    signreq.audit(session, req, "declined", signer.email, detail=reason or None, **meta)
    signreq.close(session, settings, req, "declined")
    effects = signreq.Effects()
    t = signreq.MAILS.get(req.locale, signreq.MAILS["es"])
    signreq.mail(effects, settings, req, "declined_owner", [req.owner_email], name=signer.name, email=signer.email,
                 reason=reason or t["none"])
    signreq.notify_closed(effects, settings, req, [s for s in others if s.id != signer.id], "declined")
    view = _signer_view(session, settings, req, signer, token)
    session.commit()
    signreq.deliver(effects, settings)
    return view
