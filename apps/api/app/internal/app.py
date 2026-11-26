"""API interna (`apiint:8001`, sin dominio): ganchos de tusd, autorización de descargas y métricas."""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app import auth
from app.deps import KEY_RESOLVER, db, registry_dep, settings_dep, valkey_dep
from app.routers import health
from app.routers.admin import overview_data
from core import disk
from core.errors import AppError, ErrorCode, message
from core.filetype import detect, matches, normalize_ext
from core.jobs import load_plan
from core.logs import setup_logging
from core.models import SignatureRequest, Share, Signer, Upload
from core.quotas import usage
from core.registry import Registry
from core.settings import Settings, get_settings
from core.storage import Store
from core.tokens import hash_token, verify_download, verify_request_file
from tools.base import sha256_file

DOWNLOAD_RE = re.compile(r"^/d/([0-9a-f-]{36})/([A-Za-z0-9._-]{1,130})$")
SHARE_RE = re.compile(r"^/s/([0-9a-f-]{36})/([A-Za-z0-9._-]{1,130})$")
REQUEST_RE = re.compile(r"^/r/([0-9a-f-]{36})/([A-Za-z0-9._-]{1,130})$")


def _first(headers: dict, name: str) -> str | None:
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v[0] if isinstance(v, list) and v else v
    return None


def _reject(status: int, code: str, locale: str = "es") -> dict:
    return {
        "RejectUpload": True,
        "HTTPResponse": {
            "StatusCode": status,
            "Body": json.dumps({"error": {"code": code, "message": message(code, locale)}}, ensure_ascii=False),
            "Header": {"Content-Type": "application/json"},
        },
    }


def _upload_rate_ok(r, settings: Settings, http: dict, headers: dict, owner_key: str) -> bool:
    """Límite por minuto de subidas por IP y por usuario (12.4)."""
    from core.clientip import real_ip
    from core.tokens import hash_ip

    remote = (http.get("RemoteAddr") or "").rsplit(":", 1)[0] or None
    ip = real_ip(remote, {k.lower(): v for k, v in headers.items()}, settings.TRUST_CF_CONNECTING_IP, settings.CLOUDFLARE_IP_RANGES)
    minute = int(time.time() // 60)
    for key in (f"rlu:ip:{hash_ip(settings.ANON_TOKEN_SECRET or 'x', ip)}:{minute}", f"rlu:own:{owner_key}:{minute}"):
        n = r.incr(key)
        if n == 1:
            r.expire(key, 70)
        if n > settings.RATE_LIMIT_PER_MINUTE:
            return False
    return True


def pre_create(event: dict, session: Session, r, settings: Settings, registry: Registry) -> dict:
    up = event.get("Upload", {})
    http = event.get("HTTPRequest", {})
    headers = http.get("Header", {}) or {}
    locale = "en" if (_first(headers, "Accept-Language") or "es").lower().startswith("en") else "es"
    try:
        owner = auth.resolve_owner(_first(headers, "Authorization"), session, settings, key_resolver=KEY_RESOLVER["fn"])
    except AppError:
        return _reject(401, ErrorCode.UNAUTHORIZED, locale)
    if not _upload_rate_ok(r, settings, http, headers, owner.key):
        return _reject(429, ErrorCode.RATE_LIMITED, locale)
    if up.get("SizeIsDeferred") or up.get("Size") is None:
        return _reject(400, ErrorCode.FILE_TOO_LARGE, locale)
    size = int(up["Size"])
    meta = up.get("MetaData", {}) or {}
    filename = (meta.get("filename") or meta.get("name") or "archivo")[:300]
    spec = registry.get(meta.get("tool", ""))
    if spec is None or not spec.runs_on_server:
        return _reject(400, ErrorCode.UNSUPPORTED_FORMAT, locale)
    ext = normalize_ext(Path(filename).suffix)
    if ext not in {normalize_ext(e) for e in spec.inputs}:
        return _reject(415, ErrorCode.UNSUPPORTED_FORMAT, locale)
    plan = load_plan(session, owner.plan_id, settings)
    # Vídeo (9.3, D-245): sin plan con vídeo ni siquiera se sube, para no ocupar disco con algo que no se va a procesar.
    if spec.needs_video and not plan.video:
        return _reject(403, ErrorCode.LIMIT_EXCEEDED, locale)
    if size > plan.max_file_bytes or size > settings.UPLOAD_MAX_BYTES:
        return _reject(413, ErrorCode.FILE_TOO_LARGE, locale)
    task_class = spec.cost_for({})
    used = usage(session, owner.type, owner.id).get(task_class, 0)
    if used >= plan.tasks_for(task_class):
        return _reject(429, ErrorCode.QUOTA_EXCEEDED, locale)
    upload_id = uuid.uuid4().hex
    root = Path(settings.FILESTORE_PATH)
    if not disk.try_reserve(r, root, upload_id, size, settings.DISK_RESERVE_FACTOR, settings.DISK_MAX_USAGE_PERCENT, settings.DISK_MIN_FREE_GB):
        return _reject(503, ErrorCode.DISK_FULL, locale)
    store = Store(root)
    session.add(Upload(
        id=upload_id, owner_type=owner.type, owner_id=owner.id, tool=spec.slug_es, path=str(store.upload_path(upload_id)),
        size=size, reserved_bytes=int(size * settings.DISK_RESERVE_FACTOR), original_name=filename, state="uploading",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    ))
    return {"ChangeFileInfo": {"ID": upload_id}}


def pre_finish(event: dict, session: Session, settings: Settings, registry: Registry) -> dict:
    up = event.get("Upload", {})
    upload_id = up.get("ID", "")
    row = session.get(Upload, upload_id)
    if row is None:
        return {}
    store = Store(Path(settings.FILESTORE_PATH))
    path = store.upload_path(upload_id)
    spec = registry.get(row.tool)
    detected = detect(path, Path(row.original_name).suffix) if path.exists() else None
    row.size = path.stat().st_size if path.exists() else row.size
    row.sha256 = sha256_file(path) if path.exists() else None
    row.detected_ext = detected.ext if detected else None
    row.detected_mime = detected.mime if detected else None
    ok = spec is not None and matches(detected, Path(row.original_name).suffix, spec.inputs)
    row.state = "ready" if ok else "rejected"
    plan = load_plan(session, "anon" if row.owner_type == "anon" else _plan_id(session, row.owner_id), settings)
    row.expires_at = datetime.now(timezone.utc) + timedelta(hours=plan.retention_hours)
    return {"HTTPResponse": {"Header": {"Upload-State": row.state}}}


def _plan_id(session: Session, user_id: str) -> str:
    from core.models import Profile

    p = session.get(Profile, user_id)
    return p.plan_id if p else "free"


def post_terminate(event: dict, session: Session, r, settings: Settings) -> dict:
    upload_id = event.get("Upload", {}).get("ID", "")
    row = session.get(Upload, upload_id)
    if row is not None:
        session.delete(row)
    disk.release(r, upload_id)
    try:
        Store(Path(settings.FILESTORE_PATH)).remove_upload(upload_id)
    except ValueError:
        pass
    return {}


def authorize_uri(uri: str, method: str, session: Session, settings: Settings) -> bool:
    if method not in ("GET", "HEAD"):
        return False
    parts = urlsplit(uri)
    token = (parse_qs(parts.query).get("t") or [""])[0]
    m = DOWNLOAD_RE.match(parts.path)
    if m:
        return bool(token) and verify_download(settings.FILE_TOKEN_SECRET, m.group(1), m.group(2), token)
    m = SHARE_RE.match(parts.path)
    if m and token:
        share = session.get(Share, m.group(1))
        now = datetime.now(timezone.utc)
        if share is None or share.revoked_at is not None or share.expires_at < now or share.filename != m.group(2):
            return False
        if share.token_hash != hash_token(token):
            return False
        share.downloads += 1
        return True
    m = REQUEST_RE.match(parts.path)
    if m and token:
        return _authorize_request(session, settings, m.group(1), m.group(2), token)
    return False


def _authorize_request(session: Session, settings: Settings, request_id: str, name: str, token: str) -> bool:
    """solicitar-firmas (F4-C2, D-202): el documento en curso con el token del firmante mientras la solicitud sigue
    abierta, y el documento firmado y el certificado con los enlaces firmados (HMAC) del correo final."""
    from sqlalchemy import select

    from core.signreq import ACTIVE

    try:
        req = session.get(SignatureRequest, uuid.UUID(request_id))
    except ValueError:
        return False
    if req is None or req.purged_at is not None:
        return False
    if token.count(".") == 2:
        return (req.status == "completed" and name in (req.final_files or [])
                and verify_request_file(settings.FILE_TOKEN_SECRET, str(req.id), name, token))
    if req.status not in ACTIVE or name != req.filename:
        return False
    signer = session.scalars(select(Signer).where(Signer.request_id == req.id, Signer.token_hash == hash_token(token))).first()
    if signer is None or signer.status == "declined":
        return False
    if signer.viewed_at is None:
        # El certificado distingue abrir la página de descargar el documento (la primera vez).
        from core.signreq import audit

        signer.viewed_at = datetime.now(timezone.utc)
        audit(session, req, "viewed", signer.email, sha256=req.document_sha256)
    return True


def create_internal_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    app = FastAPI(title="API interna", docs_url=None, redoc_url=None)

    @app.post("/tusd-hooks")
    async def tusd_hooks(request: Request, session: Session = Depends(db, scope="function"), r=Depends(valkey_dep),
                         settings: Settings = Depends(settings_dep), registry: Registry = Depends(registry_dep)):
        body = await request.json()
        kind = body.get("Type")
        event = body.get("Event", {})
        if kind == "pre-create":
            return JSONResponse(pre_create(event, session, r, settings, registry))
        if kind == "pre-finish":
            return JSONResponse(pre_finish(event, session, settings, registry))
        if kind == "post-terminate":
            return JSONResponse(post_terminate(event, session, r, settings))
        return JSONResponse({})

    @app.get("/files/authorize")
    def files_authorize(request: Request, session: Session = Depends(db, scope="function"), settings: Settings = Depends(settings_dep)):
        uri = request.headers.get("x-forwarded-uri", "")
        method = request.headers.get("x-forwarded-method", "GET").upper()
        return Response(status_code=200 if authorize_uri(uri, method, session, settings) else 403)

    @app.get("/ops/metrics")
    def metrics(session: Session = Depends(db, scope="function"), r=Depends(valkey_dep), settings: Settings = Depends(settings_dep),
                registry: Registry = Depends(registry_dep)):
        return overview_data(session, r, settings, registry)

    app.include_router(health.router)
    return app


app = create_internal_app()
