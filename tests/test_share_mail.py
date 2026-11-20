"""Enviar un resultado por correo (8.2.4): enlace de 24 h, límites por plan y por día, Turnstile y abuso."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

import pytest

from helpers import auth

pytestmark = pytest.mark.integration


@pytest.fixture()
def outbox(monkeypatch):
    from app.routers import share

    sent: list[dict] = []
    monkeypatch.setitem(share.SEND, "fn", lambda smtp, sender, to, subject, body: sent.append({"to": to, "subject": subject, "body": body}))
    monkeypatch.setitem(share.VERIFY, "fn", lambda secret, token, ip: token == "ok")
    return sent


def _job(api, token, tus_upload, fixtures_dir) -> dict:
    uid, _ = tus_upload(token, "comprimir-pdf", fixtures_dir / "fotos.pdf")
    job = api.post("/v1/jobs", json={"tool": "comprimir-pdf", "upload_ids": [uid]}, headers=auth(token)).json()
    assert job["status"] == "succeeded", job
    return job


def _set_plan(services, user_id: str, plan: str) -> None:
    from sqlalchemy import create_engine, text

    with create_engine(services["db_url"]).begin() as conn:
        conn.execute(text("UPDATE profiles SET plan_id = :p WHERE user_id = :u"), {"p": plan, "u": user_id})


def test_free_plan_sends_signed_link_to_own_address(api, internal, user_token, tus_upload, fixtures_dir, services, outbox):
    token = user_token(user_id="correo-libre", email="Ana@Ejemplo.test")
    job = _job(api, token, tus_upload, fixtures_dir)
    url = f"/v1/jobs/{job['id']}/outputs/0/mail"
    other = api.post(url, json={"to": ["otra@ejemplo.test"], "turnstile_token": "ok"}, headers=auth(token))
    assert other.status_code == 403 and other.json()["error"]["code"] == "FORBIDDEN"
    bad_captcha = api.post(url, json={"to": ["ana@ejemplo.test"], "turnstile_token": "malo"}, headers=auth(token))
    assert bad_captcha.status_code == 403 and bad_captcha.json()["error"]["code"] == "TURNSTILE_FAILED"
    ok = api.post(url, json={"to": ["ana@ejemplo.test"], "turnstile_token": "ok", "locale": "es"}, headers=auth(token))
    assert ok.status_code == 200, ok.text
    assert ok.json()["sent"] == 1
    mail = outbox[-1]
    assert mail["to"] == ["ana@ejemplo.test"] and "Tu archivo" in mail["subject"]
    link = re.search(r"https?://\S+/s/\S+", mail["body"]).group(0)
    assert "/es/contacto?abuso=" in mail["body"] and ".pdf" not in mail["subject"].split(":")[0]
    # Nunca se adjunta: solo el enlace, que Caddy autoriza con el token y no sin él.
    parts = urlsplit(link)
    path = f"{parts.path}?{parts.query}"
    assert internal.get("/files/authorize", headers={"X-Forwarded-Uri": path, "X-Forwarded-Method": "GET"}).status_code == 200
    bad = path.replace(parse_qs(parts.query)["t"][0], "otro")
    assert internal.get("/files/authorize", headers={"X-Forwarded-Uri": bad, "X-Forwarded-Method": "GET"}).status_code == 403
    share_id = parts.path.split("/")[2]
    from pathlib import Path

    assert (Path(services["files"]) / "shares" / share_id).is_dir()


def test_pro_up_to_three_recipients_and_daily_limit(api, user_token, tus_upload, fixtures_dir, services, outbox, monkeypatch):
    from core.settings import get_settings

    token = user_token(user_id="correo-pro", email="pro@ejemplo.test")
    api.get("/v1/me", headers=auth(token))
    _set_plan(services, "correo-pro", "pro")
    job = _job(api, token, tus_upload, fixtures_dir)
    url = f"/v1/jobs/{job['id']}/outputs/0/mail"
    three = ["a@ejemplo.test", "b@ejemplo.test", "c@ejemplo.test"]
    ok = api.post(url, json={"to": three, "turnstile_token": "ok", "locale": "en"}, headers=auth(token))
    assert ok.status_code == 200, ok.text
    assert outbox[-1]["to"] == three and "pro@ejemplo.test sent you a file" in outbox[-1]["subject"]
    four = api.post(url, json={"to": three + ["d@ejemplo.test"], "turnstile_token": "ok"}, headers=auth(token))
    assert four.status_code == 422
    monkeypatch.setattr(get_settings(), "MAIL_SHARE_DAILY_LIMIT", 2)
    assert api.post(url, json={"to": ["a@ejemplo.test"], "turnstile_token": "ok"}, headers=auth(token)).status_code == 200
    limited = api.post(url, json={"to": ["a@ejemplo.test"], "turnstile_token": "ok"}, headers=auth(token))
    assert limited.status_code == 429 and limited.json()["error"]["code"] == "QUOTA_EXCEEDED"


def test_anonymous_and_strangers_cannot_send(api, anon_token, user_token, tus_upload, fixtures_dir, outbox):
    anon = anon_token()
    job = _job(api, anon, tus_upload, fixtures_dir)
    url = f"/v1/jobs/{job['id']}/outputs/0/mail"
    assert api.post(url, json={"to": ["x@ejemplo.test"], "turnstile_token": "ok"}, headers=auth(anon)).status_code == 401
    stranger = user_token(email="x@ejemplo.test")
    assert api.post(url, json={"to": ["x@ejemplo.test"], "turnstile_token": "ok"}, headers=auth(stranger)).status_code == 404
    assert outbox == []


def test_smtp_failure_is_reported_and_leaves_nothing(api, user_token, tus_upload, fixtures_dir, services, monkeypatch, outbox):
    from pathlib import Path

    from app.routers import share

    def boom(*_args):
        raise OSError("SMTP caído")

    monkeypatch.setitem(share.SEND, "fn", boom)
    token = user_token(user_id="correo-fallo", email="fallo@ejemplo.test")
    job = _job(api, token, tus_upload, fixtures_dir)
    before = set((Path(services["files"]) / "shares").glob("*"))
    resp = api.post(f"/v1/jobs/{job['id']}/outputs/0/mail", json={"to": ["fallo@ejemplo.test"], "turnstile_token": "ok"}, headers=auth(token))
    assert resp.status_code == 502 and resp.json()["error"]["code"] == "MAIL_FAILED"
    assert set((Path(services["files"]) / "shares").glob("*")) == before


# --- compartir-pdf (F4-C1, D-200) ---------------------------------------------------------------------------------


def _authorized(internal, url: str) -> int:
    parts = urlsplit(url)
    return internal.get("/files/authorize", headers={"X-Forwarded-Uri": f"{parts.path}?{parts.query}", "X-Forwarded-Method": "GET"}).status_code


def test_share_link_hours_per_plan_revoke_and_list(api, internal, user_token, tus_upload, fixtures_dir, services, outbox):
    token = user_token(user_id="enlace-libre", email="libre@ejemplo.test")
    uid, _ = tus_upload(token, "compartir-pdf", fixtures_dir / "fotos.pdf")
    job = api.post("/v1/jobs", json={"tool": "compartir-pdf", "upload_ids": [uid]}, headers=auth(token)).json()
    assert job["status"] == "succeeded", job
    body = {"job_id": job["id"], "position": 0, "turnstile_token": "ok"}
    week = api.post("/v1/shares", json={**body, "hours": 168}, headers=auth(token))
    assert week.status_code == 422 and week.json()["error"]["message"] == "Con tu plan el enlace puede durar como mucho 24 horas."
    assert api.post("/v1/shares", json={**body, "hours": 5}, headers=auth(token)).status_code == 422
    assert api.post("/v1/shares", json={**body, "hours": 24, "turnstile_token": "malo"}, headers=auth(token)).status_code == 403
    ok = api.post("/v1/shares", json={**body, "hours": 24}, headers=auth(token))
    assert ok.status_code == 200, ok.text
    link = ok.json()
    assert _authorized(internal, link["url"]) == 200 and _authorized(internal, link["url"] + "x") == 403
    listed = api.get("/v1/shares", headers=auth(token)).json()["shares"]
    assert [(s["id"], s["downloads"], "url" in s) for s in listed] == [(link["id"], 1, False)]
    other = user_token(user_id="enlace-otro", email="otro@ejemplo.test")
    assert api.delete(f"/v1/shares/{link['id']}", headers=auth(other)).status_code == 404
    revoked = api.delete(f"/v1/shares/{link['id']}", headers=auth(token))
    assert revoked.status_code == 200 and revoked.json()["revoked"] is True
    assert _authorized(internal, link["url"]) == 403
    from pathlib import Path

    assert not (Path(services["files"]) / "shares" / link["id"]).exists()
    _set_plan(services, "enlace-libre", "pro")
    assert api.post("/v1/shares", json={**body, "hours": 168}, headers=auth(token)).status_code == 200


def test_share_needs_an_account(api, anon_token, tus_upload, fixtures_dir):
    token = anon_token()
    uid, _ = tus_upload(token, "compartir-pdf", fixtures_dir / "fotos.pdf")
    job = api.post("/v1/jobs", json={"tool": "compartir-pdf", "upload_ids": [uid]}, headers=auth(token))
    assert job.status_code == 401 and job.json()["error"]["code"] == "UNAUTHORIZED"
