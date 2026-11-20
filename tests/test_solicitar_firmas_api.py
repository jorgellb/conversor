"""F4-C2: solicitar-firmas de extremo a extremo en la API (7.7 y 9.1, D-202), con PostgreSQL y Valkey reales.

Los trabajos se ejecutan en el propio proceso (preparar en `pdf`; firmante y final con el firmante de archivo y la TSA y
el OCSP del «illusionist» de certomancer); el correo se recoge en una lista. El E2E con Mailpit y los contenedores, en la
CI (17).
"""
from __future__ import annotations

import base64
import io
import re
import sys
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pikepdf
import pytest

from helpers import auth

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "fixtures"))

from test_firmas import _signer, analyse, arch  # noqa: E402,F401

pytestmark = pytest.mark.integration
TSA = "http://certomancer.test/conversor-pruebas/tsa/tsa"


def _png_url(transparent: bool = False) -> str:
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (300, 100), (255, 255, 255, 0))
    if not transparent:
        ImageDraw.Draw(img).line([(10, 80), (150, 20), (290, 70)], fill=(0, 0, 120, 255), width=5)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@pytest.fixture()
def flow(api, arch, monkeypatch, services):
    """Correo recogido, Turnstile de pruebas, trabajos internos ejecutados al momento y el sello de archivo."""
    from certomancer.integrations.aiohttp_illusionist import AsyncIllusionist
    from pyhanko.sign.timestamps import HTTPTimeStamper

    from app.routers import signreq as router
    from core import signreq
    from core.settings import get_settings
    from tools.sign import firmar, solicitar
    from tools.tasks import execute

    outbox: list[dict] = []
    monkeypatch.setitem(signreq.SEND, "fn", lambda smtp, sender, to, subject, body: outbox.append({"to": to, "subject": subject, "body": body}))
    monkeypatch.setitem(router.VERIFY, "fn", lambda secret, token, ip: token == "ok")
    monkeypatch.setitem(signreq.ENQUEUE, "fn", lambda job_id: execute(job_id, 1, ""))

    @contextmanager
    def file_signer(_settings):
        yield _signer(arch, "seal"), [arch.get_cert("seal"), arch.get_cert("interm"), arch.get_cert("root")]

    @asynccontextmanager
    async def clients(_settings):
        async with AsyncIllusionist(arch).serving_session() as session:
            yield session, HTTPTimeStamper(TSA, session=session)

    def fake_render(_settings, page: str) -> bytes:
        pdf = pikepdf.new()
        pdf.add_blank_page(page_size=(595, 842))
        buf = io.BytesIO()
        pdf.save(buf)
        outbox.append({"to": ["<certificado>"], "subject": "html", "body": page})
        return buf.getvalue()

    monkeypatch.setattr(firmar, "seal_signer", file_signer)
    monkeypatch.setattr(solicitar, "tsa_clients", clients)
    monkeypatch.setattr(solicitar, "render_certificate", fake_render)
    monkeypatch.setattr(get_settings(), "TSA_URL", TSA)
    return outbox


def _pdf(tmp_path: Path, name: str = "contrato.pdf") -> Path:
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    path = tmp_path / name
    pdf.save(path)
    return path


def _prepare(api, token, tus_upload, tmp_path, names: list[str]) -> dict:
    uid, _ = tus_upload(token, "solicitar-firmas", _pdf(tmp_path))
    job = api.post("/v1/jobs", json={"tool": "solicitar-firmas", "upload_ids": [uid],
                                     "options": {"firmantes": [{"nombre": n} for n in names]}}, headers=auth(token)).json()
    assert job["status"] == "succeeded", job
    return job


def _create(api, token, job, signers, **extra):
    body = {"job_id": job["id"], "signers": [{"name": n, "email": e} for n, e in signers], "turnstile_token": "ok", **extra}
    return api.post("/v1/signature-requests", json=body, headers=auth(token))


def _token(mail: dict) -> str:
    return re.search(r"/(?:firmar-documento|sign-document)#([A-Za-z0-9_-]+)", mail["body"]).group(1)


def _mails_to(outbox, email):
    return [m for m in outbox if m["to"] == [email]]


def _sign(api, outbox, token, email, image=None):
    assert api.post(f"/v1/sign/{token}/code", json={"turnstile_token": "ok"}).status_code == 200
    code = re.search(r"\b(\d{6})\b", _mails_to(outbox, email)[-1]["body"]).group(1)
    return api.post(f"/v1/sign/{token}", json={"code": code, "image": image or _png_url(), "consent": True})


def _authorize(internal, url: str) -> int:
    parts = urlsplit(url)
    return internal.get("/files/authorize", headers={"X-Forwarded-Uri": f"{parts.path}?{parts.query}", "X-Forwarded-Method": "GET"}).status_code


def _file(services, url: str) -> Path:
    _, _, request_id, name = urlsplit(url).path.split("/")
    return Path(services["files"]) / "requests" / request_id / name


def test_sequential_request_end_to_end(api, internal, user_token, tus_upload, tmp_path, flow, services, arch):
    outbox = flow
    owner = user_token(user_id="pide-firmas", email="Pide@Ejemplo.test")
    job = _prepare(api, owner, tus_upload, tmp_path, ["Luis Gómez", "Eva"])
    resp = _create(api, owner, job, [("Luis Gómez", "luis@ejemplo.test"), ("Eva", "eva@ejemplo.test")],
                   message="Firma antes del viernes", days=7, locale="es")
    assert resp.status_code == 201, resp.text
    view = resp.json()
    assert view["status"] == "pending" and [s["status"] for s in view["signers"]] == ["invited", "waiting"]
    invite = _mails_to(outbox, "luis@ejemplo.test")[-1]
    assert "pide@ejemplo.test te pide que firmes «contrato.pdf»" == invite["subject"]
    assert "Firma antes del viernes" in invite["body"] and "/es/contacto?abuso=" in invite["body"]
    assert not _mails_to(outbox, "eva@ejemplo.test")
    luis = _token(invite)

    page = api.get(f"/v1/sign/{luis}").json()
    assert page["signer"]["can_sign"] and page["request"]["owner_email"] == "pide@ejemplo.test"
    assert [s["name"] for s in page["signers"]] == ["Luis Gómez", "Eva"] and "email" not in page["signers"][0]
    assert _authorize(internal, page["document_url"]) == 200
    assert _authorize(internal, page["document_url"].replace(luis, "x" * 43)) == 403
    assert api.get("/v1/sign/" + "x" * 43).status_code == 404

    # Código incorrecto: cuenta el intento; el bueno, con la imagen y el consentimiento, deja la firma en marcha.
    assert api.post(f"/v1/sign/{luis}/code", json={"turnstile_token": "malo"}).status_code == 403
    assert api.post(f"/v1/sign/{luis}/code", json={"turnstile_token": "ok"}).status_code == 200
    code = re.search(r"\b(\d{6})\b", _mails_to(outbox, "luis@ejemplo.test")[-1]["body"]).group(1)
    wrong = f"{(int(code) + 1) % 10 ** 6:06d}"
    bad = api.post(f"/v1/sign/{luis}", json={"code": wrong, "image": _png_url(), "consent": True})
    assert bad.status_code == 422 and bad.json()["error"]["attempts_left"] == 4
    assert "no es correcto" in bad.json()["error"]["message"]
    assert api.post(f"/v1/sign/{luis}", json={"code": code, "image": _png_url(), "consent": False}).status_code == 422
    ok = api.post(f"/v1/sign/{luis}", json={"code": code, "image": _png_url(), "consent": True})
    assert ok.status_code == 200, ok.text
    assert ok.json()["signer"]["status"] == "signing"

    # La consulta siguiente recoge el resultado, avisa al propietario e invita a Eva.
    page = api.get(f"/v1/sign/{luis}").json()
    assert page["signer"]["status"] == "signed" and not page["signer"]["can_sign"]
    assert any("Luis Gómez ha firmado" in m["subject"] for m in _mails_to(outbox, "pide@ejemplo.test"))
    eva = _token(_mails_to(outbox, "eva@ejemplo.test")[-1])
    assert _sign(api, outbox, eva, "eva@ejemplo.test").status_code == 200

    # Eva firmada → trabajo final → completada (dos consultas: la primera crea y ejecuta el final; la segunda lo recoge).
    api.get(f"/v1/sign/{eva}")
    done = api.get(f"/v1/sign/{eva}").json()
    assert done["request"]["status"] == "completed", done
    assert [f["name"] for f in done["files"]] == ["contrato-firmado.pdf", "certificado-auditoria.pdf"]
    assert done["document_url"] is None
    for f in done["files"]:
        assert _authorize(internal, f["url"]) == 200
    assert _authorize(internal, page["document_url"]) == 403  # el documento en curso ya no está
    signed = _file(services, done["files"][0]["url"]).read_bytes()
    items = analyse(signed, roots=[arch.get_cert("root"), arch.get_cert("seal")])
    assert [s.field for s in items] == ["Firmante1", "Firmante2", "SelloFinal1"]
    assert all(s.intact and s.valid for s in items) and items[-1].pades == "B-LT"
    assert items[0].reason == "Firmado por Luis Gómez (luis@ejemplo.test), verificado por correo"

    completed = [m for m in outbox if "ya está firmado por todos" in m["subject"]]
    assert sorted(m["to"][0] for m in completed) == ["eva@ejemplo.test", "luis@ejemplo.test", "pide@ejemplo.test"]
    link = re.search(r"https://files\.ejemplo\.test/r/\S+", completed[0]["body"]).group(0)
    assert _authorize(internal, link) == 200
    certificate = next(m["body"] for m in outbox if m["subject"] == "html")
    assert "luis@ejemplo.test" in certificate and "Código verificado" in certificate and "Código incorrecto" in certificate

    detail = api.get(f"/v1/signature-requests/{view['id']}", headers=auth(owner)).json()
    events = [e["event"] for e in detail["events"]]
    for event in ("created", "invited", "opened", "code_sent", "code_failed", "code_verified", "consented", "signed", "completed"):
        assert event in events, event
    assert detail["status"] == "completed" and len(detail["files"]) == 2
    listed = api.get("/v1/signature-requests", headers=auth(owner)).json()["requests"]
    assert listed[0]["id"] == view["id"]

    # Borrar una solicitud terminada la quita del todo, con sus archivos.
    folder = Path(services["files"]) / "requests" / view["id"]
    assert folder.is_dir()
    assert api.delete(f"/v1/signature-requests/{view['id']}", headers=auth(owner)).json()["deleted"]
    assert not folder.exists() and api.get(f"/v1/signature-requests/{view['id']}", headers=auth(owner)).status_code == 404


def test_parallel_signers_are_sealed_one_after_another(api, user_token, tus_upload, tmp_path, flow, services, arch):
    outbox = flow
    owner = user_token(user_id="paralelo", email="jefa@ejemplo.test")
    job = _prepare(api, owner, tus_upload, tmp_path, ["Ana", "Bea"])
    view = _create(api, owner, job, [("Ana", "ana@ejemplo.test"), ("Bea", "bea@ejemplo.test")], sequential=False).json()
    assert [s["status"] for s in view["signers"]] == ["invited", "invited"]
    ana, bea = _token(_mails_to(outbox, "ana@ejemplo.test")[-1]), _token(_mails_to(outbox, "bea@ejemplo.test")[-1])
    # Bea firma antes que Ana: el orden de la lista no importa en paralelo.
    assert _sign(api, outbox, bea, "bea@ejemplo.test").status_code == 200
    assert _sign(api, outbox, ana, "ana@ejemplo.test").status_code == 200
    for _ in range(3):
        api.get(f"/v1/sign/{ana}")
    done = api.get(f"/v1/signature-requests/{view['id']}", headers=auth(owner)).json()
    assert done["status"] == "completed", done
    signed = _file(services, done["files"][0]["url"]).read_bytes()
    items = analyse(signed, roots=[arch.get_cert("root"), arch.get_cert("seal")])
    assert [s.field for s in items] == ["Firmante2", "Firmante1", "SelloFinal1"] and all(s.valid for s in items)


def test_validation_limits_and_ownership(api, user_token, tus_upload, tmp_path, flow, monkeypatch):
    from core import signreq

    owner = user_token(user_id="valida", email="v@ejemplo.test")
    other = user_token(user_id="otro-valida", email="o@ejemplo.test")
    job = _prepare(api, owner, tus_upload, tmp_path, ["Ana"])
    checks = [
        (_create(api, owner, job, [("Otra", "a@ejemplo.test")]), 422, "request_mismatch"),
        (_create(api, owner, job, [("Ana", "a@ejemplo.test"), ("B", "a@ejemplo.test")]), 422, None),
        (_create(api, other, job, [("Ana", "a@ejemplo.test")]), 404, None),
        (api.post("/v1/signature-requests", json={"job_id": job["id"], "signers": [{"name": "Ana", "email": "a@ejemplo.test"}],
                                                  "turnstile_token": "malo"}, headers=auth(owner)), 403, None),
        (_create(api, owner, job, [("Ana", "no-es-un-correo")]), 422, None),
        (_create(api, owner, job, [("Ana", "a@ejemplo.test")], days=31), 422, None),
    ]
    for resp, status, _detail in checks:
        assert resp.status_code == status, resp.text
    assert "no coinciden" in checks[0][0].json()["error"]["message"]
    # Las fases internas no se pueden crear desde fuera.
    uid, _ = tus_upload(owner, "solicitar-firmas", _pdf(tmp_path, "x.pdf"))
    resp = api.post("/v1/jobs", json={"tool": "solicitar-firmas", "upload_ids": [uid],
                                      "options": {"fase": "firmante", "campo": "Firmante1", "nombre": "Ana"}}, headers=auth(owner))
    assert resp.status_code == 400 and "la propia solicitud" in resp.json()["error"]["message"]
    # Gratis: hasta 3 firmantes y 3 solicitudes al día.
    uid, _ = tus_upload(owner, "solicitar-firmas", _pdf(tmp_path, "y.pdf"))
    resp = api.post("/v1/jobs", json={"tool": "solicitar-firmas", "upload_ids": [uid],
                                      "options": {"firmantes": [{"nombre": str(i)} for i in range(4)]}}, headers=auth(owner))
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "LIMIT_EXCEEDED"
    monkeypatch.setattr(signreq, "FREE_SIGN_REQUESTS_PER_DAY", 1)
    created = _create(api, owner, job, [("Ana", "a@ejemplo.test")])
    assert created.status_code == 201
    # El documento preparado es de un solo uso.
    assert _create(api, owner, job, [("Ana", "a@ejemplo.test")]).status_code == 404
    # Crear, cancelar y borrar no devuelve el cupo del día (revisión de F4-C2).
    rid = created.json()["id"]
    assert api.delete(f"/v1/signature-requests/{rid}", headers=auth(owner)).json()["status"] == "cancelled"
    assert api.delete(f"/v1/signature-requests/{rid}", headers=auth(owner)).json()["deleted"]
    again = _create(api, owner, _prepare(api, owner, tus_upload, tmp_path, ["Ana"]), [("Ana", "a@ejemplo.test")])
    assert again.status_code == 429 and again.json()["error"]["code"] == "QUOTA_EXCEEDED"
    anon = api.post("/v1/session/anon", json={"turnstile_token": "ok"}).json()["token"]
    assert api.get("/v1/signature-requests", headers=auth(anon)).status_code == 401


def test_code_limits_image_checks_and_decline(api, internal, user_token, tus_upload, tmp_path, flow, services):
    from sqlalchemy import create_engine, text

    outbox = flow
    owner = user_token(user_id="rechazo", email="r@ejemplo.test")
    job = _prepare(api, owner, tus_upload, tmp_path, ["Ana"])
    view = _create(api, owner, job, [("Ana", "ana2@ejemplo.test")]).json()
    ana = _token(_mails_to(outbox, "ana2@ejemplo.test")[-1])
    # Sin pedir código, caducado o tras 5 fallos: hay que pedir otro.
    resp = api.post(f"/v1/sign/{ana}", json={"code": "000000", "image": _png_url(), "consent": True})
    assert resp.status_code == 422 and "caducado" in resp.json()["error"]["message"]
    api.post(f"/v1/sign/{ana}/code", json={"turnstile_token": "ok"})
    code = re.search(r"\b(\d{6})\b", _mails_to(outbox, "ana2@ejemplo.test")[-1]["body"]).group(1)
    wrong = f"{(int(code) + 1) % 10 ** 6:06d}"
    for left in (4, 3, 2, 1):
        assert api.post(f"/v1/sign/{ana}", json={"code": wrong, "image": _png_url(), "consent": True}).json()["error"]["attempts_left"] == left
    locked = api.post(f"/v1/sign/{ana}", json={"code": wrong, "image": _png_url(), "consent": True})
    assert locked.json()["error"]["attempts_left"] == 0 and "Demasiados intentos" in locked.json()["error"]["message"]
    assert api.post(f"/v1/sign/{ana}", json={"code": code, "image": _png_url(), "consent": True}).status_code == 422
    # Imagen no válida (transparente, JPEG o base64 roto) con un código bueno: no gasta el código.
    api.post(f"/v1/sign/{ana}/code", json={"turnstile_token": "ok"})
    code = re.search(r"\b(\d{6})\b", _mails_to(outbox, "ana2@ejemplo.test")[-1]["body"]).group(1)
    for image in (_png_url(transparent=True), "data:image/jpeg;base64,AAAA" + "A" * 40, "data:image/png;base64,!!!" + "A" * 40):
        resp = api.post(f"/v1/sign/{ana}", json={"code": code, "image": image, "consent": True})
        assert resp.status_code == 422 and "imagen de la firma" in resp.json()["error"]["message"], resp.text
    # Tope de códigos por hora.
    for _ in range(3):
        api.post(f"/v1/sign/{ana}/code", json={"turnstile_token": "ok"})
    resp = api.post(f"/v1/sign/{ana}/code", json={"turnstile_token": "ok"})
    assert resp.status_code == 429
    code = re.search(r"\b(\d{6})\b", _mails_to(outbox, "ana2@ejemplo.test")[-1]["body"]).group(1)
    # Rechazo: se cierra, se avisa al propietario y se borra el documento.
    doc_url = api.get(f"/v1/sign/{ana}").json()["document_url"]
    assert api.post(f"/v1/sign/{ana}/decline", json={"reason": "sin código"}).status_code == 422
    resp = api.post(f"/v1/sign/{ana}/decline", json={"code": code, "reason": "  No estoy de acuerdo  "})
    assert resp.status_code == 200 and resp.json()["request"]["status"] == "declined"
    mail = _mails_to(outbox, "r@ejemplo.test")[-1]
    assert "ha rechazado" in mail["subject"] and "Motivo: No estoy de acuerdo" in mail["body"]
    assert _authorize(internal, doc_url) == 403
    assert not (Path(services["files"]) / "requests" / view["id"]).exists()
    assert api.post(f"/v1/sign/{ana}/code", json={"turnstile_token": "ok"}).status_code == 409
    with create_engine(services["db_url"]).begin() as conn:
        assert conn.execute(text("SELECT status FROM signature_requests WHERE id = :i"), {"i": view["id"]}).scalar() == "declined"


def test_reminder_rotates_link_cancel_and_expiry(api, user_token, tus_upload, tmp_path, flow, services):
    from sqlalchemy import create_engine, text

    from core import signreq
    from core.registry import load_registry
    from core.settings import get_settings

    outbox = flow
    owner = user_token(user_id="recuerda", email="rec@ejemplo.test")
    job = _prepare(api, owner, tus_upload, tmp_path, ["Ana"])
    view = _create(api, owner, job, [("Ana", "ana3@ejemplo.test")]).json()
    old = _token(_mails_to(outbox, "ana3@ejemplo.test")[-1])
    assert api.post(f"/v1/signature-requests/{view['id']}/remind", headers=auth(owner)).json() == {"reminded": 0}
    with create_engine(services["db_url"]).begin() as conn:
        conn.execute(text("UPDATE signers SET invited_at = now() - interval '25 hours' WHERE request_id = :i"), {"i": view["id"]})
    assert api.post(f"/v1/signature-requests/{view['id']}/remind", headers=auth(owner)).json() == {"reminded": 1}
    reminder = _mails_to(outbox, "ana3@ejemplo.test")[-1]
    assert reminder["subject"].startswith("Recordatorio")
    new = _token(reminder)
    assert api.get(f"/v1/sign/{old}").status_code == 404 and api.get(f"/v1/sign/{new}").status_code == 200

    # Cancelar: avisa a la firmante y la página lo muestra.
    resp = api.delete(f"/v1/signature-requests/{view['id']}", headers=auth(owner))
    assert resp.json()["status"] == "cancelled"
    assert "cancelado" in _mails_to(outbox, "ana3@ejemplo.test")[-1]["subject"]
    page = api.get(f"/v1/sign/{new}").json()
    assert page["request"]["status"] == "cancelled" and not page["signer"]["can_sign"] and page["document_url"] is None

    # Caducidad por beat.
    job = _prepare(api, owner, tus_upload, tmp_path, ["Ana"])
    view = _create(api, owner, job, [("Ana", "ana4@ejemplo.test")], days=1).json()
    signreq.tick(get_settings(), load_registry(), now=datetime.now(timezone.utc) + timedelta(days=2))
    detail = api.get(f"/v1/signature-requests/{view['id']}", headers=auth(owner)).json()
    assert detail["status"] == "expired"
    assert "caducado" in _mails_to(outbox, "rec@ejemplo.test")[-1]["subject"]
    assert "Se ha cerrado" in _mails_to(outbox, "ana4@ejemplo.test")[-1]["subject"]
    assert not (Path(services["files"]) / "requests" / view["id"]).exists()


def test_failed_signer_job_is_retried_then_closes_the_request(api, user_token, tus_upload, tmp_path, flow, monkeypatch, services):
    services_url = lambda: services["db_url"]  # noqa: E731
    from core import signreq
    from core.errors import ErrorCode, ToolError
    from core.registry import load_registry
    from core.settings import get_settings
    from tools.sign import solicitar

    outbox = flow
    calls = []

    def broken(ctx):
        calls.append(ctx.job_id)
        raise ToolError(ErrorCode.ENGINE_FAILED, "seal_invalid")

    monkeypatch.setattr(solicitar, "_signer_step", broken)
    owner = user_token(user_id="falla", email="f@ejemplo.test")
    job = _prepare(api, owner, tus_upload, tmp_path, ["Ana"])
    view = _create(api, owner, job, [("Ana", "ana5@ejemplo.test")]).json()
    ana = _token(_mails_to(outbox, "ana5@ejemplo.test")[-1])
    assert _sign(api, outbox, ana, "ana5@ejemplo.test").status_code == 200
    settings, registry = get_settings(), load_registry()
    now = datetime.now(timezone.utc)
    signreq.tick(settings, registry, now=now + timedelta(seconds=30))  # todavía en espera: no reintenta
    assert len(calls) == 1
    for k in range(1, 12):  # espera creciente (2, 4, 8… minutos, hasta 2 h) y ocho intentos en total
        signreq.tick(settings, registry, now=now + timedelta(hours=3 * k))
    assert len(calls) == signreq.JOB_RETRIES
    detail = api.get(f"/v1/signature-requests/{view['id']}", headers=auth(owner)).json()
    assert detail["status"] == "failed"
    assert "No se ha podido terminar" in _mails_to(outbox, "f@ejemplo.test")[-1]["subject"]
    assert "Se ha cerrado" in _mails_to(outbox, "ana5@ejemplo.test")[-1]["subject"]
    from sqlalchemy import create_engine, text

    from core.settings import get_settings as gs
    signreq.tick(settings, registry, now=now + timedelta(hours=40))
    with create_engine(services_url()).begin() as conn:  # sus trabajos (con nombres y correos) ya no están
        assert conn.execute(text("SELECT count(*) FROM jobs WHERE owner_type = 'request' AND owner_id = :i"), {"i": view["id"]}).scalar() == 0
    assert gs() is settings


def test_account_export_and_deletion_include_requests(api, user_token, tus_upload, tmp_path, flow, services):
    owner = user_token(user_id="borra-firmas", email="b@ejemplo.test")
    job = _prepare(api, owner, tus_upload, tmp_path, ["Ana"])
    view = _create(api, owner, job, [("Ana", "ana6@ejemplo.test")]).json()
    export = api.get("/v1/me/export", headers=auth(owner)).json()
    [req] = export["signature_requests"]
    assert req["id"] == view["id"] and req["signers"][0]["email"] == "ana6@ejemplo.test"
    assert "token_hash" not in str(export) and req["events"][0]["event"] == "created"
    assert api.delete("/v1/me", headers=auth(owner)).status_code == 200
    assert not (Path(services["files"]) / "requests" / view["id"]).exists()
    from sqlalchemy import create_engine, text

    with create_engine(services["db_url"]).begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM signature_requests WHERE id = :i"), {"i": view["id"]}).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM audit_events WHERE request_id = :i"), {"i": view["id"]}).scalar() == 0


def test_long_name_does_not_lose_the_signed_document(api, user_token, tus_upload, tmp_path, flow, services, arch):
    """Revisión de F4-C2: con un nombre muy largo, «-firmado» se recortaba y el final pisaba y borraba el documento."""
    outbox = flow
    owner = user_token(user_id="largo", email="largo@ejemplo.test")
    long_pdf = _pdf(tmp_path, "Contrato de arrendamiento de vivienda habitual entre las partes firmantes con domicilio en la calle mayor.pdf")
    uid, _ = tus_upload(owner, "solicitar-firmas", long_pdf)
    job = api.post("/v1/jobs", json={"tool": "solicitar-firmas", "upload_ids": [uid], "options": {"firmantes": [{"nombre": "Ana"}]}},
                   headers=auth(owner)).json()
    view = _create(api, owner, job, [("Ana", "ana7@ejemplo.test")]).json()
    ana = _token(_mails_to(outbox, "ana7@ejemplo.test")[-1])
    assert _sign(api, outbox, ana, "ana7@ejemplo.test").status_code == 200
    for _ in range(3):
        api.get(f"/v1/sign/{ana}")
    done = api.get(f"/v1/signature-requests/{view['id']}", headers=auth(owner)).json()
    assert done["status"] == "completed", done
    names = [f["name"] for f in done["files"]]
    assert len(set(names)) == 2
    items = analyse(_file(services, done["files"][0]["url"]).read_bytes(), roots=[arch.get_cert("root"), arch.get_cert("seal")])
    assert [s.field for s in items] == ["Firmante1", "SelloFinal1"]
    assert api.get("/v1/signature-requests", headers=auth(owner)).status_code == 200


def test_reminders_recipients_and_finalizing_limits(api, user_token, tus_upload, tmp_path, flow, services, monkeypatch):
    from sqlalchemy import create_engine, text

    from core import signreq

    outbox = flow
    owner = user_token(user_id="topes", email="topes@ejemplo.test")
    job = _prepare(api, owner, tus_upload, tmp_path, ["Ana"])
    view = _create(api, owner, job, [("Ana", "ana8@ejemplo.test")]).json()
    sent = 0
    for _ in range(5):
        with create_engine(services["db_url"]).begin() as conn:
            conn.execute(text("UPDATE signers SET invited_at = now() - interval '25 hours' WHERE request_id = :i"), {"i": view["id"]})
        sent += api.post(f"/v1/signature-requests/{view['id']}/remind", headers=auth(owner)).json()["reminded"]
    assert sent == signreq.MAX_REMINDERS
    # Una misma dirección no recibe más de INVITES_PER_RECIPIENT_DAY invitaciones al día, de ninguna cuenta.
    monkeypatch.setattr(signreq, "INVITES_PER_RECIPIENT_DAY", 4)  # ya lleva 1 invitación y 3 recordatorios
    other = user_token(user_id="topes-2", email="topes2@ejemplo.test")
    resp = _create(api, other, _prepare(api, other, tus_upload, tmp_path, ["Ana"]), [("Ana", "ana8@ejemplo.test")])
    assert resp.status_code == 429 and "demasiadas solicitudes" in resp.json()["error"]["message"]
    # Rechazar con el enlace y sin código, no; cancelar mientras se sella, tampoco.
    with create_engine(services["db_url"]).begin() as conn:
        conn.execute(text("UPDATE signature_requests SET status = 'finalizing' WHERE id = :i"), {"i": view["id"]})
    assert api.delete(f"/v1/signature-requests/{view['id']}", headers=auth(owner)).status_code == 409


def test_access_log_hides_signer_tokens():
    import logging

    from core.logs import RedactSignTokens

    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', ("1.2.3.4", "GET", "/v1/sign/" + "x" * 43 + "/code", "1.1", 200), None)
    RedactSignTokens().filter(record)
    assert "x" * 43 not in record.getMessage() and "/v1/sign/***/code" in record.getMessage()
