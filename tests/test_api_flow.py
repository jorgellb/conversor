"""Flujo completo de servidor: sesión anónima, subida por tus, trabajo, descarga y cuotas."""
from __future__ import annotations

import os

import pikepdf
import pytest

from helpers import auth, download_path, local_file

pytestmark = pytest.mark.integration


def test_tools_catalog(api):
    data = api.get("/v1/tools").json()
    slugs = {t["slug_es"] for t in data["tools"]}
    assert {"comprimir-pdf", "unir-pdf", "ocr-pdf", "ogg-a-mp3"} <= slugs
    assert data["plans"]["anon"]["heavy_tasks_day"] == 2


def test_anon_session_requires_turnstile(api):
    assert api.post("/v1/session/anon", json={"turnstile_token": "malo"}).status_code == 403


def test_precreate_rejections(anon_token, tus_upload, fixtures_dir, internal):
    token = anon_token()
    uid, resp = tus_upload("sin-token", "comprimir-pdf", fixtures_dir / "texto.pdf")
    assert uid is None and resp["HTTPResponse"]["StatusCode"] == 401
    uid, resp = tus_upload(token, "comprimir-pdf", fixtures_dir / "foto.jpg")
    assert uid is None and resp["HTTPResponse"]["StatusCode"] == 415
    uid, resp = tus_upload(token, "comprimir-pdf", fixtures_dir / "texto.pdf", size=60 * 1024 * 1024)
    assert uid is None and resp["HTTPResponse"]["StatusCode"] == 413
    deferred = {"Type": "pre-create", "Event": {"Upload": {"SizeIsDeferred": True, "MetaData": {"filename": "a.pdf", "tool": "comprimir-pdf"}},
                                               "HTTPRequest": {"Header": {"Authorization": [f"Bearer {token}"]}}}}
    assert internal.post("/tusd-hooks", json=deferred).json()["RejectUpload"] is True


def test_fake_pdf_is_rejected(api, anon_token, tus_upload, fixtures_dir):
    token = anon_token()
    uid, fin = tus_upload(token, "comprimir-pdf", fixtures_dir / "falso.pdf")
    assert fin["HTTPResponse"]["Header"]["Upload-State"] == "rejected"
    resp = api.post("/v1/jobs", json={"tool": "comprimir-pdf", "upload_ids": [uid]}, headers=auth(token))
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FORMAT"


def test_compress_end_to_end_and_download(api, internal, anon_token, tus_upload, fixtures_dir, services):
    token = anon_token()
    uid, _ = tus_upload(token, "comprimir-pdf", fixtures_dir / "fotos.pdf")
    resp = api.post("/v1/jobs", json={"tool": "comprimir-pdf", "upload_ids": [uid], "options": {"nivel": "fuerte"}}, headers=auth(token))
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["status"] == "succeeded", job
    out = job["outputs"][0]
    assert out["size"] < (fixtures_dir / "fotos.pdf").stat().st_size
    path = local_file(services, out["url"])
    with pikepdf.open(path) as pdf:
        assert len(pdf.pages) == 3
    ok = internal.get("/files/authorize", headers={"X-Forwarded-Uri": download_path(out["url"]), "X-Forwarded-Method": "GET"})
    assert ok.status_code == 200
    tampered = download_path(out["url"]).replace("t=", "t=1")
    assert internal.get("/files/authorize", headers={"X-Forwarded-Uri": tampered}).status_code == 403
    assert internal.get("/files/authorize", headers={"X-Forwarded-Uri": "/d/../../etc/passwd?t=x"}).status_code == 403
    assert internal.get("/files/authorize", headers={"X-Forwarded-Uri": download_path(out["url"]), "X-Forwarded-Method": "POST"}).status_code == 403
    again = api.get(f"/v1/jobs/{job['id']}", headers=auth(token)).json()
    assert again["status"] == "succeeded"
    other = anon_token()
    assert api.get(f"/v1/jobs/{job['id']}", headers=auth(other)).status_code == 404


def test_idempotency_reuses_result(api, anon_token, tus_upload, fixtures_dir):
    token = anon_token()
    first, _ = tus_upload(token, "comprimir-pdf", fixtures_dir / "texto.pdf")
    j1 = api.post("/v1/jobs", json={"tool": "comprimir-pdf", "upload_ids": [first]}, headers=auth(token)).json()
    second, _ = tus_upload(token, "comprimir-pdf", fixtures_dir / "texto.pdf")
    j2 = api.post("/v1/jobs", json={"tool": "comprimir-pdf", "upload_ids": [second]}, headers=auth(token)).json()
    assert j1["id"] == j2["id"]
    usage = api.get("/v1/me/usage", headers=auth(token)).json()
    assert usage["light"]["used"] == 1


def test_invalid_options(api, anon_token, tus_upload, fixtures_dir):
    token = anon_token()
    uid, _ = tus_upload(token, "comprimir-pdf", fixtures_dir / "texto.pdf")
    resp = api.post("/v1/jobs", json={"tool": "comprimir-pdf", "upload_ids": [uid], "options": {"dpi": 5000}}, headers=auth(token))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_OPTIONS"


def test_heavy_quota_for_anonymous(api, anon_token, tus_upload, fixtures_dir, monkeypatch):
    """Anónimos: 2 tareas pesadas al día. La tercera falla con QUOTA_EXCEEDED antes de procesar."""
    from app.routers import jobs as jobs_router

    calls = []
    monkeypatch.setitem(jobs_router.ENQUEUE, "fn", lambda job, sealed, spec: calls.append(job.id))
    token = anon_token()
    codes = []
    for i in range(3):
        uid, _ = tus_upload(token, "ocr-pdf", fixtures_dir / "escaneado.pdf", filename=f"escaneo-{i}.pdf")
        if uid is None:
            codes.append(429)
            continue
        resp = api.post("/v1/jobs", json={"tool": "ocr-pdf", "upload_ids": [uid], "options": {"idiomas": ["spa"], "titulo": str(i)}},
                        headers=auth(token))
        codes.append(resp.status_code)
    assert codes[:2] == [201, 201]
    assert codes[2] == 429
    assert len(calls) == 2


def test_tool_disabled_by_env(api, anon_token, tus_upload, fixtures_dir, monkeypatch):
    token = anon_token()
    uid, _ = tus_upload(token, "comprimir-pdf", fixtures_dir / "texto.pdf", filename="otro.pdf")
    monkeypatch.setenv("TOOL_COMPRIMIR_PDF_ENABLED", "false")
    resp = api.post("/v1/jobs", json={"tool": "comprimir-pdf", "upload_ids": [uid], "options": {"calidad": 40, "nivel": "personalizado"}},
                    headers=auth(token))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "TOOL_DISABLED"


def test_password_never_stored(api, user_token, tus_upload, fixtures_dir, services):
    token = user_token()
    uid, _ = tus_upload(token, "desbloquear-pdf", fixtures_dir / "cifrado.pdf")
    resp = api.post("/v1/jobs", json={"tool": "desbloquear-pdf", "upload_ids": [uid], "options": {"contrasena": "secreto123"}},
                    headers=auth(token))
    job = resp.json()
    assert job["status"] == "succeeded", job
    from sqlalchemy import create_engine, text

    with create_engine(services["db_url"]).connect() as conn:
        dump = " ".join(str(r) for r in conn.execute(text("SELECT options, message FROM jobs")).all())
    assert "secreto123" not in dump
    with pikepdf.open(local_file(services, job["outputs"][0]["url"])) as pdf:
        assert not pdf.is_encrypted


def test_wrong_password(api, user_token, tus_upload, fixtures_dir):
    token = user_token()
    uid, _ = tus_upload(token, "desbloquear-pdf", fixtures_dir / "cifrado.pdf")
    job = api.post("/v1/jobs", json={"tool": "desbloquear-pdf", "upload_ids": [uid], "options": {"contrasena": "mala"}},
                   headers=auth(token)).json()
    assert job["status"] == "failed"
    assert job["error"]["code"] == "WRONG_PASSWORD"


def test_admin_requires_role(api, user_token):
    assert api.get("/v1/admin/overview", headers=auth(user_token())).status_code == 403
    admin = user_token(role="admin")
    data = api.get("/v1/admin/overview", headers=auth(admin)).json()
    assert "disk" in data and "queues" in data
    assert api.put("/v1/admin/flags/comprimir-pdf", json={"enabled": False}, headers=auth(admin)).status_code == 200
    tools = {t["slug_es"]: t for t in api.get("/v1/tools").json()["tools"]}
    assert tools["comprimir-pdf"]["enabled"] is False
    api.put("/v1/admin/flags/comprimir-pdf", json={"enabled": True}, headers=auth(admin))


def test_fake_checkout_upgrades_to_pro(api, user_token):
    uid = "usuario-pago"
    token = user_token(user_id=uid)
    assert api.get("/v1/me", headers=auth(token)).json()["plan"] == "free"
    url = api.post("/v1/billing/checkout", json={"interval": "monthly"}, headers=auth(token)).json()["url"]
    path = url.split("api.ejemplo.test", 1)[1]
    resp = api.get(path, follow_redirects=False)
    assert resp.status_code == 303
    assert api.get("/v1/me", headers=auth(token)).json()["plan"] == "pro"


def test_readyz(api):
    data = api.get("/readyz").json()
    assert data["checks"]["database"] == "ok"
    assert data["checks"]["valkey"] == "ok"


def test_rate_limit(api, monkeypatch):
    from core.settings import get_settings

    monkeypatch.setattr(get_settings(), "RATE_LIMIT_PER_MINUTE", 3)
    codes = [api.get("/v1/tools", headers={"X-Forwarded-For": "203.0.113.9"}).status_code for _ in range(5)]
    assert codes[-1] == 429


def test_job_keeps_the_page_language(api, anon_token, tus_upload, fixtures_dir, monkeypatch):
    """El idioma de la página llega al trabajo: los textos dentro del resultado salen en ese idioma (F2, lote C)."""
    from core.db import session_scope
    from core.models import Job
    from tools import tasks

    seen: dict = {}
    real = tasks.load_impl

    def spy(spec):
        impl = real(spec)

        def wrapped(ctx):
            seen["locale"] = ctx.locale
            return impl(ctx)

        return wrapped

    monkeypatch.setattr(tasks, "load_impl", spy)
    token = anon_token()
    uid, _ = tus_upload(token, "comprimir-pdf", fixtures_dir / "texto.pdf")
    resp = api.post("/v1/jobs", json={"tool": "comprimir-pdf", "upload_ids": [uid]},
                    headers={**auth(token), "Accept-Language": "en-GB,en;q=0.9"})
    assert resp.status_code == 201, resp.text
    with session_scope() as s:
        assert s.get(Job, resp.json()["id"]).locale == "en"
    assert seen["locale"] == "en"


@pytest.mark.skipif(__import__("shutil").which("tesseract") is None, reason="Tesseract no instalado")
def test_txt_with_automatic_ocr_counts_as_an_ocr_task(api, anon_token, tus_upload, fixtures_dir):
    """A.9: el OCR automático de pdf-a-txt cuenta como tarea de OCR, pero solo si de verdad hace falta."""
    from core import quotas
    from core.db import session_scope
    from core.models import Job

    token = anon_token()
    uid, _ = tus_upload(token, "pdf-a-txt", fixtures_dir / "escaneado.pdf")
    resp = api.post("/v1/jobs", json={"tool": "pdf-a-txt", "upload_ids": [uid]}, headers=auth(token))
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["status"] == "succeeded", job
    with session_scope() as s:
        row = s.get(Job, job["id"])
        assert row.queue == "ocr"
        used = quotas.usage(s, row.owner_type, row.owner_id)
    assert used.get("light") == 1 and used.get("heavy") == 1
    uid, _ = tus_upload(token, "pdf-a-txt", fixtures_dir / "texto.pdf")
    job = api.post("/v1/jobs", json={"tool": "pdf-a-txt", "upload_ids": [uid]}, headers=auth(token)).json()
    with session_scope() as s:
        row = s.get(Job, job["id"])
        used = quotas.usage(s, row.owner_type, row.owner_id)
    assert job["status"] == "succeeded" and used.get("light") == 2 and used.get("heavy") == 1
