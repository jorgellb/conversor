"""solicitar-firmas (7.7, F4-C2, D-202): estados, trabajos internos, correos y avance de una solicitud de firmas.

Lo usan la API (al crear la solicitud, al firmar y al consultarla) y beat (`core.maintenance.signature_requests`, cada
minuto). Solo ellos escriben en `signature_requests`, `signers` y `audit_events`; los workers no tienen permisos sobre
esas tablas y reciben por las opciones de su trabajo lo que necesitan.

- El documento vive en `requests/<id>/` (desviación de 4.1): la retención de 24 h de los trabajos no basta.
- Los trabajos de cada firmante (fase `firmante`) y el final (fase `final`) son de la solicitud (`owner_type` «request»):
  nadie puede crearlos con POST /v1/jobs, que solo admite la fase `preparar`.
- Una sola firma a la vez por solicitud: cada firma es una actualización incremental sobre la anterior, y dos trabajos
  a la vez sobre la misma versión perderían una de las dos. En paralelo, los firmantes que confirman mientras otro se
  sella esperan en `queued`.
- Los tokens de los firmantes solo se guardan como hash (12.6): un recordatorio emite uno nuevo y el anterior deja de
  valer. Los enlaces de descarga del final son tokens HMAC con caducidad (`sign_request_file`).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import AuditEvent, Job, JobInput, SignatureRequest, Signer
from core.settings import Settings
from core.storage import Store, sanitize_filename
from core.tokens import new_share_token, sign_request_file

log = logging.getLogger("conversor.signreq")

TOOL = "solicitar-firmas"
OWNER_TYPE = "request"
MAX_SIGNERS = 10
FREE_MAX_SIGNERS = 3
FREE_SIGN_REQUESTS_PER_DAY = 3
MAX_DAYS = 30
CODE_MINUTES = 15
CODE_ATTEMPTS = 5
CODES_PER_HOUR = 5
REMIND_MINUTES = 24 * 60  # un recordatorio por firmante y día…
MAX_REMINDERS = 3  # …y tres en total (D-202, revisión: el correo de la plataforma no puede servir para mandar spam)
MAX_CODES = 20  # códigos por firmante en toda la solicitud (además de CODES_PER_HOUR)
INVITES_PER_RECIPIENT_DAY = 10  # invitaciones y recordatorios que recibe una misma dirección al día, de cualquier cuenta
MAX_ACTIVE = {"free": 5, "pro": 50}  # solicitudes abiertas a la vez por cuenta (disco: requests/ no pasa por la reserva)
MAX_MB = 25  # tamaño del PDF de una solicitud (cada firma lo copia; 25 MB bastan para un contrato escaneado)
KEEP_DAYS = 30
JOB_RETRIES = 8  # con espera creciente (2, 4, 8… minutos, hasta 2 h): una caída de la TSA o del OCSP no la cierra
ACTIVE = ("pending", "finalizing")
# Errores del documento, que no se arreglan reintentando. TOOL_DISABLED (sello apagado o mal configurado un rato) y
# QUOTA_EXCEEDED (límite de sellos del día) se reintentan.
PERMANENT = {"INVALID_OPTIONS", "CORRUPT_FILE", "PASSWORD_REQUIRED", "LIMIT_EXCEEDED", "UNSUPPORTED_FORMAT"}
NOISY = ("opened", "viewed", "code_sent", "code_failed", "reminded")  # eventos que se resumen en el certificado
SIGNER_PAGE = {"es": "firmar-documento", "en": "sign-document"}
OWNER_PAGE = {"es": "solicitar-firmas", "en": "request-signatures"}
CONTACT_PAGE = {"es": "contacto", "en": "contact"}

# Sustituibles en pruebas: el envío de correo y el encolado (por defecto, Celery).
SEND = {"fn": None}
ENQUEUE = {"fn": None}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def field_name(index: int, campo: str = "") -> str:
    """Campo del firmante `index` (desde 0): el vacío que eligió en el PDF o uno nuevo de la página de firmas. La fase
    `preparar` del worker y la API lo calculan igual."""
    return campo.strip() or f"Firmante{index + 1}"


# --- Correos ----------------------------------------------------------------------------------------------------------

FOOTER = {
    "es": "\n\nNo respondas a este correo. Si no esperabas esta solicitud o crees que es un abuso, avísanos:\n{abuse}\nIndica este código: {code}\n",
    "en": "\n\nDo not reply to this email. If you did not expect this request or think it is abuse, let us know:\n{abuse}\nQuote this code: {code}\n",
}
MAILS = {
    "es": {
        "invite": ("{owner} te pide que firmes «{doc}»",
                   "Hola, {name}:\n\n{owner} te pide que firmes el documento «{doc}» con {site}.{message}\n\n"
                   "Ábrelo y fírmalo aquí (el enlace es personal y caduca el {expires} UTC):\n{url}\n\n"
                   "Para firmar te enviaremos un código a esta dirección. Tu firma lleva el sello de {site}, que acredita "
                   "la integridad del documento, la fecha y que se firmó desde esta dirección de correo."),
        "remind": ("Recordatorio: {owner} espera tu firma en «{doc}»",
                   "Hola, {name}:\n\nTe recordamos que {owner} te pide que firmes «{doc}» con {site}.{message}\n\n"
                   "Ábrelo y fírmalo aquí (caduca el {expires} UTC). Los enlaces de correos anteriores ya no valen:\n{url}"),
        "code": ("Tu código para firmar «{doc}»",
                 "Tu código para firmar «{doc}» es:\n\n{code}\n\nCaduca en {minutes} minutos. Si no lo has pedido tú, "
                 "ignora este correo: nadie puede firmar en tu nombre sin él."),
        "signed_owner": ("{name} ha firmado «{doc}»",
                         "{name} ({email}) ha firmado «{doc}». Firmas: {done} de {total}.\n\nSigue la solicitud aquí:\n{page}"),
        "completed_owner": ("«{doc}» ya está firmado por todos",
                            "Todos los firmantes han firmado «{doc}». El documento lleva el sello final PAdES B-LT de "
                            "{site} y va acompañado de su certificado de auditoría.\n\nDocumento firmado:\n{doc_url}\n\n"
                            "Certificado de auditoría:\n{cert_url}\n\nLos enlaces caducan el {until} UTC; después se "
                            "borran los archivos. Descárgalos y guárdalos."),
        "completed_signer": ("«{doc}» ya está firmado por todos",
                             "Hola, {name}:\n\nTodos los firmantes han firmado «{doc}», que te envió {owner}. Aquí tienes "
                             "tu copia y el certificado de auditoría.\n\nDocumento firmado:\n{doc_url}\n\n"
                             "Certificado de auditoría:\n{cert_url}\n\nLos enlaces caducan el {until} UTC."),
        "declined_owner": ("{name} ha rechazado firmar «{doc}»",
                           "{name} ({email}) ha rechazado firmar «{doc}».\nMotivo: {reason}\n\nLa solicitud se ha cerrado "
                           "y el documento se ha borrado de {site}."),
        "cancelled_signer": ("Se ha cancelado la solicitud de firma de «{doc}»",
                             "Hola, {name}:\n\n{owner} ha cancelado la solicitud de firma de «{doc}». Ya no tienes que "
                             "firmar nada y el documento se ha borrado de {site}."),
        "expired_owner": ("Ha caducado la solicitud de firma de «{doc}»",
                          "La solicitud de firma de «{doc}» ha caducado. Firmas: {done} de {total}.\n\nEl documento se ha "
                          "borrado de {site}; si todavía hace falta, crea una solicitud nueva."),
        "failed_owner": ("No se ha podido terminar la solicitud de firma de «{doc}»",
                         "No se ha podido sellar «{doc}» ({reason}). La solicitud se ha cerrado y el documento se ha "
                         "borrado de {site}. Vuelve a crearla y, si se repite, escríbenos."),
        "closed_signer": ("Se ha cerrado la solicitud de firma de «{doc}»",
                          "Hola, {name}:\n\nLa solicitud de firma de «{doc}» que te envió {owner} se ha cerrado sin "
                          "completarse ({why}). Ya no tienes que firmar nada y el documento se ha borrado de {site}."),
        "why_expired": "ha caducado",
        "why_failed": "no se ha podido sellar",
        "why_declined": "otro firmante ha rechazado firmar",
        "no_message": "",
        "with_message": "\n\nSu mensaje:\n«{message}»",
        "none": "sin motivo",
    },
    "en": {
        "invite": ("{owner} asks you to sign “{doc}”",
                   "Hello {name},\n\n{owner} asks you to sign the document “{doc}” with {site}.{message}\n\n"
                   "Open and sign it here (the link is personal and expires on {expires} UTC):\n{url}\n\n"
                   "To sign, we will send a code to this address. Your signature carries the {site} seal, which proves "
                   "the integrity of the document, the date and that it was signed from this email address."),
        "remind": ("Reminder: {owner} is waiting for your signature on “{doc}”",
                   "Hello {name},\n\nA reminder that {owner} asks you to sign “{doc}” with {site}.{message}\n\n"
                   "Open and sign it here (it expires on {expires} UTC). Links in earlier emails no longer work:\n{url}"),
        "code": ("Your code to sign “{doc}”",
                 "Your code to sign “{doc}” is:\n\n{code}\n\nIt expires in {minutes} minutes. If you did not ask for it, "
                 "ignore this email: nobody can sign on your behalf without it."),
        "signed_owner": ("{name} has signed “{doc}”",
                         "{name} ({email}) has signed “{doc}”. Signatures: {done} of {total}.\n\nFollow the request here:\n{page}"),
        "completed_owner": ("“{doc}” has been signed by everyone",
                            "Every signer has signed “{doc}”. The document carries the final {site} PAdES B-LT seal and "
                            "comes with its audit certificate.\n\nSigned document:\n{doc_url}\n\nAudit certificate:\n"
                            "{cert_url}\n\nThe links expire on {until} UTC; the files are deleted afterwards. Download "
                            "and keep them."),
        "completed_signer": ("“{doc}” has been signed by everyone",
                             "Hello {name},\n\nEvery signer has signed “{doc}”, sent to you by {owner}. Here are your copy "
                             "and the audit certificate.\n\nSigned document:\n{doc_url}\n\nAudit certificate:\n{cert_url}"
                             "\n\nThe links expire on {until} UTC."),
        "declined_owner": ("{name} has declined to sign “{doc}”",
                           "{name} ({email}) has declined to sign “{doc}”.\nReason: {reason}\n\nThe request has been "
                           "closed and the document deleted from {site}."),
        "cancelled_signer": ("The signature request for “{doc}” has been cancelled",
                             "Hello {name},\n\n{owner} has cancelled the signature request for “{doc}”. You do not need "
                             "to sign anything and the document has been deleted from {site}."),
        "expired_owner": ("The signature request for “{doc}” has expired",
                          "The signature request for “{doc}” has expired. Signatures: {done} of {total}.\n\nThe document "
                          "has been deleted from {site}; if you still need it, create a new request."),
        "failed_owner": ("The signature request for “{doc}” could not be completed",
                         "“{doc}” could not be sealed ({reason}). The request has been closed and the document deleted "
                         "from {site}. Create it again and, if it happens again, write to us."),
        "closed_signer": ("The signature request for “{doc}” has been closed",
                          "Hello {name},\n\nThe signature request for “{doc}” sent to you by {owner} has been closed "
                          "without being completed ({why}). You do not need to sign anything and the document has been "
                          "deleted from {site}."),
        "why_expired": "it expired",
        "why_failed": "it could not be sealed",
        "why_declined": "another signer declined to sign",
        "no_message": "",
        "with_message": "\n\nTheir message:\n“{message}”",
        "none": "no reason given",
    },
}


@dataclass
class Effects:
    """Lo que hay que hacer después de confirmar la transacción: correos y trabajos que encolar."""

    mails: list[tuple[list[str], str, str]] = field(default_factory=list)
    jobs: list[tuple[str, str, int, int]] = field(default_factory=list)  # (id, cola, prioridad, límite de tiempo)


def _texts(req: SignatureRequest) -> dict:
    return MAILS.get(req.locale, MAILS["es"])


def _web(settings: Settings) -> str:
    return settings.PUBLIC_WEB_URL.rstrip("/")


def signer_url(settings: Settings, req: SignatureRequest, token: str) -> str:
    """El token va en el fragmento: el navegador no lo manda al servidor web ni queda en sus registros."""
    return f"{_web(settings)}/{req.locale}/{SIGNER_PAGE.get(req.locale, SIGNER_PAGE['es'])}#{token}"


def owner_url(settings: Settings, req: SignatureRequest) -> str:
    return f"{_web(settings)}/{req.locale}/{OWNER_PAGE.get(req.locale, OWNER_PAGE['es'])}"


def _fmt(when: datetime | None) -> str:
    return when.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M") if when else ""


def mail(effects: Effects, settings: Settings, req: SignatureRequest, kind: str, to: list[str], footer: bool = False, **values) -> None:
    t = _texts(req)
    subject, body = t[kind]
    data = {"site": settings.APP_NAME, "doc": req.document_name, "owner": req.owner_email, **values}
    text = body.format(**data)
    if footer:
        abuse = f"{_web(settings)}/{req.locale}/{CONTACT_PAGE.get(req.locale, 'contacto')}?abuso={req.id}"
        text += FOOTER.get(req.locale, FOOTER["es"]).format(abuse=abuse, code=req.id)
    else:
        text += "\n"
    effects.mails.append((to, subject.format(**data)[:200], text))


def message_block(req: SignatureRequest) -> str:
    t = _texts(req)
    return t["with_message"].format(message=req.message.strip()) if (req.message or "").strip() else t["no_message"]


def deliver(effects: Effects, settings: Settings) -> None:
    """Después del commit: un correo que falla no deshace la solicitud (el propietario puede mandar un recordatorio)."""
    from core import external

    send = SEND["fn"] or external.send_mail
    for to, subject, body in effects.mails:
        try:
            send(settings.SMTP_URL, settings.MAIL_FROM, to, subject, body)
        except Exception as exc:  # noqa: BLE001 - SMTP caído o mal configurado
            log.warning("correo de solicitud de firmas fallido", extra={"error": type(exc).__name__})
    for job_id, queue, priority, time_limit in effects.jobs:
        if ENQUEUE["fn"] is not None:
            ENQUEUE["fn"](job_id)
            continue
        from core import queueguard
        from core.celeryapp import celery_app
        from core.valkey import get_valkey

        celery_app.send_task("tools.tasks.run_job", args=[job_id, 1, ""], queue=queue, priority=priority,
                             soft_time_limit=time_limit, time_limit=time_limit + 60)
        queueguard.on_enqueue(get_valkey(), queue)
    effects.mails.clear()
    effects.jobs.clear()


# --- Auditoría, firmantes y archivos -----------------------------------------------------------------------------------


def audit(session: Session, req: SignatureRequest, event: str, actor: str, ip_hash: str | None = None,
          user_agent: str | None = None, sha256: str | None = None, detail: str | None = None) -> None:
    session.add(AuditEvent(request_id=req.id, event=event, actor=actor[:320], ip_hash=ip_hash,
                           user_agent=(user_agent or None) and user_agent[:400], document_sha256=sha256,
                           detail=(detail or None) and detail[:500], created_at=utcnow()))


def signers_of(session: Session, req: SignatureRequest) -> list[Signer]:
    return list(session.scalars(select(Signer).where(Signer.request_id == req.id).order_by(Signer.sign_order, Signer.id)))


def code_hash(settings: Settings, signer_id: uuid.UUID | str, code: str) -> str:
    """Un código de 6 cifras se adivina en un millón de pruebas: el hash lleva un secreto del servidor."""
    return hmac.new(settings.FILE_TOKEN_SECRET.encode(), f"c|{signer_id}|{code}".encode(), hashlib.sha256).hexdigest()


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def request_dir(settings: Settings, req: SignatureRequest) -> Path:
    return Store(settings.FILESTORE_PATH).request_dir(str(req.id))


def signature_image(settings: Settings, req: SignatureRequest, signer: Signer) -> Path:
    return request_dir(settings, req) / f"firma-{signer.id}.png"


def invite(effects: Effects, session: Session, settings: Settings, req: SignatureRequest, signer: Signer, kind: str = "invite") -> None:
    """Invitación o recordatorio: un token nuevo (solo su hash queda en la base de datos)."""
    token, token_hash = new_share_token()
    signer.token_hash = token_hash
    if signer.status == "waiting":
        signer.status = "invited"
    signer.invited_at = utcnow()
    audit(session, req, "invited" if kind == "invite" else "reminded", signer.email)
    mail(effects, settings, req, kind, [signer.email], footer=True, name=signer.name, url=signer_url(settings, req, token),
         expires=_fmt(req.expires_at), message=message_block(req))


def close(session: Session, settings: Settings, req: SignatureRequest, status: str) -> None:
    """Cierra la solicitud y borra sus archivos (rechazada, cancelada, caducada o fallida)."""
    req.status = status
    req.purged_at = utcnow()
    req.final_files = []
    shutil.rmtree(request_dir(settings, req), ignore_errors=True)
    drop_jobs(session, settings, req)


def drop_jobs(session: Session, settings: Settings, req: SignatureRequest, keep: set | None = None) -> None:
    """Borra los trabajos terminados de la solicitud (sus opciones llevan nombres, correos y la auditoría) y sus
    carpetas. Los que siguen en cola o en marcha los quita beat cuando acaban (`tick`)."""
    store = Store(settings.FILESTORE_PATH)
    for job in session.scalars(select(Job).where(Job.owner_type == OWNER_TYPE, Job.owner_id == str(req.id))).all():
        if job.status in ("queued", "running") or (keep and job.id in keep):
            continue
        store.remove_job(str(job.id))
        session.delete(job)


def notify_closed(effects: Effects, settings: Settings, req: SignatureRequest, signers: list[Signer], why: str) -> None:
    """Avisa a los firmantes que ya conocían la solicitud de que se ha cerrado sin terminar."""
    t = _texts(req)
    for s in signers:
        if s.status in ("invited", "queued", "signing", "signed"):
            mail(effects, settings, req, "closed_signer", [s.email], name=s.name, why=t[f"why_{why}"])

def _copy_into(src: Path, dst: Path) -> None:
    """Copia y renombra: quien lee el documento a la vez nunca ve un archivo a medias."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{uuid.uuid4().hex}.tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def internal_job(session: Session, settings: Settings, registry, req: SignatureRequest, options: dict,
                 files: list[tuple[Path, str]]) -> Job:
    """Trabajo de la solicitud (fase `firmante` o `final`), con sus entradas copiadas de requests/<id>/."""
    spec = registry.require(TOOL)
    data = spec.options.model_validate(options).model_dump(mode="json")
    group, queue = spec.target(data)
    job = Job(id=uuid.uuid4(), owner_type=OWNER_TYPE, owner_id=str(req.id), tool=TOOL, options=data, status="queued",
              worker_group=group, queue=queue, priority=5, cost_class=spec.cost_for(data),
              idempotency_key=hashlib.sha256(uuid.uuid4().bytes).hexdigest(), attempts=0, has_secrets=False,
              locale=req.locale, expires_at=utcnow() + timedelta(hours=24), ai_reserved=0, ai_used=0)
    session.add(job)
    session.flush()
    store = Store(settings.FILESTORE_PATH)
    store.ensure_job_dirs(str(job.id))
    for i, (src, name) in enumerate(files):
        dst = store.in_dir(str(job.id)) / f"{i:03d}-{sanitize_filename(name)}"
        shutil.copyfile(src, dst)
        ext = Path(name).suffix.lower().lstrip(".")
        session.add(JobInput(job_id=job.id, position=i, name=name, path=str(dst), size=dst.stat().st_size,
                             mime="image/png" if ext == "png" else "application/pdf", ext=ext, sha256=sha256_path(dst)))
    return job


def _queue_job(effects: Effects, registry, job: Job) -> None:
    effects.jobs.append((str(job.id), job.queue, job.priority, registry.require(TOOL).time_limit))


def _drop_job(settings: Settings, job: Job) -> None:
    """Los archivos del trabajo ya están en la solicitud: no hace falta esperar a su caducidad."""
    Store(settings.FILESTORE_PATH).remove_job(str(job.id))
    job.status = "expired"


def file_links(settings: Settings, req: SignatureRequest, who: str) -> list[dict]:
    if req.status != "completed" or req.purged_at is not None or not req.completed_at:
        return []
    until = req.completed_at + timedelta(days=KEEP_DAYS)
    ttl = max(60, int((until - utcnow()).total_seconds()))
    base = settings.PUBLIC_FILES_URL.rstrip("/")
    return [{"name": name, "url": f"{base}/r/{req.id}/{name}?t={sign_request_file(settings.FILE_TOKEN_SECRET, str(req.id), name, who, ttl)}"}
            for name in req.final_files]


# --- Avance --------------------------------------------------------------------------------------------------------------


def _job_failed(settings: Settings, req: SignatureRequest, job: Job | None, attempts: int, now: datetime) -> str:
    """«retry», «wait» o «fail» para un trabajo que no ha terminado bien."""
    code = job.error_code if job is not None else "WORKER_LOST"
    finished = job.finished_at if job is not None else None
    if code == "QUOTA_EXCEEDED":
        # Límite de sellos de la plataforma del día: se espera sin gastar intentos (la solicitud caduca si no llega).
        return "wait" if finished is not None and now - finished < timedelta(minutes=30) else "retry_free"
    if code in PERMANENT or attempts >= JOB_RETRIES:
        return "fail"
    if finished is not None and now - finished < timedelta(minutes=min(120, 2 ** attempts)):
        return "wait"
    return "retry"


def _fail(effects: Effects, session: Session, settings: Settings, req: SignatureRequest, reason: str) -> None:
    signers = signers_of(session, req)
    audit(session, req, "failed", "sistema", detail=reason)
    close(session, settings, req, "failed")
    mail(effects, settings, req, "failed_owner", [req.owner_email], reason=reason)
    notify_closed(effects, settings, req, signers, "failed")


def _final_options(session: Session, req: SignatureRequest, signers: list[Signer]) -> dict:
    events = session.scalars(select(AuditEvent).where(AuditEvent.request_id == req.id).order_by(AuditEvent.id)).all()
    return {
        "fase": "final", "documento": req.document_name[:200], "solicitud": str(req.id), "propietario": req.owner_email,
        "creada": req.created_at.isoformat() if req.created_at else "", "original_sha256": req.original_sha256 or "",
        "firmantes": [{"nombre": s.name, "correo": s.email, "campo": s.field,
                       "firmado": s.signed_at.isoformat() if s.signed_at else ""} for s in signers],
        "eventos": summarize(events),
    }


def summarize(events) -> list[dict]:
    """Eventos para el certificado: todos los importantes y, de los repetibles (aperturas, códigos, recordatorios), el
    primero y el último de cada persona con cuántos hubo, para que el ruido no desplace a los que cuentan."""
    groups: dict[tuple[str, str], list] = {}
    for e in events:
        if e.event in NOISY:
            groups.setdefault((e.event, e.actor), []).append(e)
    keep = []
    for e in events:
        if e.event not in NOISY:
            keep.append((e, ""))
            continue
        group = groups[(e.event, e.actor)]
        if e is group[0]:
            keep.append((e, ""))
        elif e is group[-1]:
            keep.append((e, f"{len(group)}×" if len(group) > 2 else ""))
    def row(e, count: str) -> dict:
        detail = " ".join(x for x in (count, (e.detail or "")[:200]) if x)
        return {"evento": e.event, "actor": e.actor, "fecha": e.created_at.isoformat() if e.created_at else "",
                "ip": (e.ip_hash or "")[:16], "agente": (e.user_agent or "")[:200], "sha256": e.document_sha256 or "",
                "detalle": detail[:200]}
    rows = [row(e, c) for e, c in keep]
    return rows[:300]


def advance(effects: Effects, session: Session, settings: Settings, registry, req: SignatureRequest, now: datetime | None = None) -> None:
    """Lleva la solicitud tan lejos como se pueda ahora. El llamador la ha bloqueado con FOR UPDATE."""
    now = now or utcnow()
    if req.status not in ACTIVE:
        return
    folder = request_dir(settings, req)
    signers = signers_of(session, req)
    if req.status == "finalizing":
        _advance_final(effects, session, settings, registry, req, signers, folder, now)
        return
    if not (folder / req.filename).is_file():
        _fail(effects, session, settings, req, "document_missing")
        return
    current = next((s for s in signers if s.status == "signing"), None)
    if current is not None:
        job = session.get(Job, current.job_id) if current.job_id else None
        if job is not None and job.status in ("queued", "running"):
            _requeue_if_lost(effects, registry, job, now)
            return
        output = job.outputs[0] if job is not None and job.status == "succeeded" and job.outputs else None
        if output is not None and Path(output.path).is_file():
            _copy_into(Path(output.path), folder / req.filename)
            req.document_sha256 = sha256_path(folder / req.filename)
            current.status, current.signed_at, current.job_id = "signed", job.finished_at or now, None
            signature_image(settings, req, current).unlink(missing_ok=True)
            audit(session, req, "signed", current.email, sha256=req.document_sha256, detail=current.field)
            _drop_job(settings, job)
            done = sum(1 for s in signers if s.status == "signed")
            mail(effects, settings, req, "signed_owner", [req.owner_email], name=current.name, email=current.email,
                 done=done, total=len(signers), page=owner_url(settings, req))
        else:
            verdict = _job_failed(settings, req, job, current.job_attempts, now)
            if verdict == "wait":
                return
            if verdict == "fail":
                _fail(effects, session, settings, req, (job.error_code if job is not None else None) or "WORKER_LOST")
                return
            if verdict == "retry_free":
                current.job_attempts -= 1
            current.status, current.job_id = "queued", None
    queued = [s for s in signers if s.status == "queued"]
    if queued:
        nxt = queued[0]
        image = signature_image(settings, req, nxt)
        if not image.is_file():  # la imagen se ha perdido: tiene que volver a firmar
            nxt.status = "invited"
        else:
            job = internal_job(session, settings, registry, req, {"fase": "firmante", "campo": nxt.field, "nombre": nxt.name,
                                                                   "correo": nxt.email},
                               [(folder / req.filename, req.filename), (image, "firma.png")])
            nxt.status, nxt.job_id, nxt.job_attempts = "signing", job.id, nxt.job_attempts + 1
            _queue_job(effects, registry, job)
            return
    if signers and all(s.status == "signed" for s in signers):
        job = internal_job(session, settings, registry, req, _final_options(session, req, signers),
                           [(folder / req.filename, req.filename)])
        req.status, req.final_job_id, req.final_attempts = "finalizing", job.id, req.final_attempts + 1
        _queue_job(effects, registry, job)
        return
    if now >= req.expires_at:
        audit(session, req, "expired", "sistema")
        done = sum(1 for s in signers if s.status == "signed")
        close(session, settings, req, "expired")
        mail(effects, settings, req, "expired_owner", [req.owner_email], done=done, total=len(signers))
        notify_closed(effects, settings, req, signers, "expired")
        return
    if req.sequential:
        # El siguiente en el orden, cuando todos los anteriores han firmado.
        for s in signers:
            if s.status == "signed":
                continue
            if s.status == "waiting":
                invite(effects, session, settings, req, s)
            break


def _advance_final(effects: Effects, session: Session, settings: Settings, registry, req: SignatureRequest,
                   signers: list[Signer], folder: Path, now: datetime) -> None:
    job = session.get(Job, req.final_job_id) if req.final_job_id else None
    if job is not None and job.status in ("queued", "running"):
        _requeue_if_lost(effects, registry, job, now)
        return
    outputs = [o for o in job.outputs if Path(o.path).is_file()] if job is not None and job.status == "succeeded" else []
    if len(outputs) >= 2:
        names = final_names(req.filename, [o.name for o in outputs[:2]])
        for o, name in zip(outputs[:2], names):
            _copy_into(Path(o.path), folder / name)
        if req.filename not in names:
            (folder / req.filename).unlink(missing_ok=True)
        req.filename = names[0]
        req.final_files = names
        req.document_sha256 = sha256_path(folder / names[0])
        req.status, req.completed_at = "completed", now
        audit(session, req, "completed", "sistema", sha256=req.document_sha256)
        _drop_job(settings, job)
        until = _fmt(now + timedelta(days=KEEP_DAYS))
        links = file_links(settings, req, "owner")
        drop_jobs(session, settings, req)
        mail(effects, settings, req, "completed_owner", [req.owner_email], doc_url=links[0]["url"], cert_url=links[1]["url"], until=until)
        for s in signers:
            mine = file_links(settings, req, str(s.id).replace("-", "")[:16])
            mail(effects, settings, req, "completed_signer", [s.email], name=s.name, doc_url=mine[0]["url"],
                 cert_url=mine[1]["url"], until=until)
        return
    if not (folder / req.filename).is_file():
        _fail(effects, session, settings, req, "document_missing")
        return
    verdict = _job_failed(settings, req, job, req.final_attempts, now)
    if verdict == "wait":
        return
    if verdict == "fail":
        _fail(effects, session, settings, req, (job.error_code if job is not None else None) or "WORKER_LOST")
        return
    if verdict == "retry_free":
        req.final_attempts -= 1
    job = internal_job(session, settings, registry, req, _final_options(session, req, signers), [(folder / req.filename, req.filename)])
    req.final_job_id, req.final_attempts = job.id, req.final_attempts + 1
    _queue_job(effects, registry, job)


def final_names(current: str, names: list[str]) -> list[str]:
    """Nombres del documento firmado y del certificado, distintos entre sí y del documento en curso (con un nombre muy
    largo, el sufijo «-firmado» se recortaba y el resultado pisaba y luego borraba el documento)."""
    out: list[str] = []
    for i, name in enumerate(names):
        candidate = sanitize_filename(name)
        if candidate == current or candidate in out:
            candidate = ("documento-firmado.pdf", "certificado-auditoria.pdf")[min(i, 1)]
            if candidate == current or candidate in out:
                candidate = f"final-{i + 1}.pdf"
        out.append(candidate)
    return out


def _requeue_if_lost(effects: Effects, registry, job: Job, now: datetime) -> None:
    """Un trabajo de la solicitud que sigue en cola a los 10 minutos se vuelve a encolar (si Valkey perdió el mensaje,
    nadie más lo haría: requeue_stale solo mira los que están en marcha). start_attempt descarta el duplicado."""
    if job.status != "queued" or job.attempts != 0 or not job.created_at or now - job.created_at < timedelta(minutes=10):
        return
    try:
        from core.valkey import get_valkey

        if not get_valkey().set(f"signreq:requeue:{job.id}", "1", nx=True, ex=600):
            return
    except Exception:  # noqa: BLE001 - sin Valkey tampoco se podría encolar
        return
    _queue_job(effects, registry, job)


def lock(session: Session, request_id) -> SignatureRequest | None:
    return session.scalars(select(SignatureRequest).where(SignatureRequest.id == request_id).with_for_update()).first()


def tick(settings: Settings, registry, now: datetime | None = None) -> dict:
    """beat, cada minuto: avanza las solicitudes activas y borra los archivos de las terminadas hace KEEP_DAYS días."""
    from core.db import session_scope

    now = now or utcnow()
    counts = {"advanced": 0, "purged": 0}
    with session_scope() as s:
        ids = list(s.scalars(select(SignatureRequest.id).where(SignatureRequest.status.in_(ACTIVE))))
    for request_id in ids:
        effects = Effects()
        try:
            with session_scope() as s:
                req = s.scalars(select(SignatureRequest).where(SignatureRequest.id == request_id)
                                .with_for_update(skip_locked=True)).first()
                if req is None:
                    continue
                advance(effects, s, settings, registry, req, now)
            counts["advanced"] += 1
            deliver(effects, settings)
        except Exception:  # noqa: BLE001 - una solicitud rota (o Valkey caído al encolar) no para las demás
            log.exception("no se ha podido avanzar la solicitud", extra={"request_id": str(request_id)})
            continue
    with session_scope() as s:
        old = s.scalars(select(SignatureRequest).where(SignatureRequest.status == "completed", SignatureRequest.purged_at.is_(None),
                                                       SignatureRequest.completed_at < now - timedelta(days=KEEP_DAYS))).all()
        for req in old:
            shutil.rmtree(request_dir(settings, req), ignore_errors=True)
            req.purged_at, req.final_files = now, []
            counts["purged"] += 1
    counts["jobs"] = _drop_orphan_jobs(settings)
    return counts


def _drop_orphan_jobs(settings: Settings) -> int:
    """Trabajos de solicitudes ya cerradas o borradas que seguían en marcha cuando se cerraron: fuera, con sus opciones
    (nombres, correos, auditoría) y su carpeta. Se quedan los que la solicitud abierta todavía mira."""
    from core.db import session_scope
    from core.models import Signer as SignerRow

    store = Store(settings.FILESTORE_PATH)
    n = 0
    with session_scope() as s:
        active = {str(i) for i in s.scalars(select(SignatureRequest.id).where(SignatureRequest.status.in_(ACTIVE)))}
        refs = set(s.scalars(select(SignerRow.job_id).where(SignerRow.job_id.is_not(None))))
        refs |= set(s.scalars(select(SignatureRequest.final_job_id).where(SignatureRequest.status.in_(ACTIVE),
                                                                          SignatureRequest.final_job_id.is_not(None))))
        for job in s.scalars(select(Job).where(Job.owner_type == OWNER_TYPE, Job.status.not_in(("queued", "running")))).all():
            if job.owner_id in active and job.id in refs:
                continue
            if job.owner_id in active and job.status == "failed":
                continue  # el último fallo decide la espera del reintento
            store.remove_job(str(job.id))
            s.delete(job)
            n += 1
    return n
