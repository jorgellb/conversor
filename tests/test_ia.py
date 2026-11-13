"""IA (sección 6 y pruebas de 16.3): presupuesto, limitador, candidatos, descubrimiento, reconciliación,
consentimiento, herramientas excluidas, caché y resumir-pdf de extremo a extremo con el proveedor falso."""
from __future__ import annotations

import dataclasses
import json
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

from helpers import auth
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida

pytestmark = pytest.mark.integration


def _set_plan(services, user_id: str, plan: str) -> None:
    from sqlalchemy import create_engine, text

    with create_engine(services["db_url"]).begin() as conn:
        conn.execute(text("UPDATE profiles SET plan_id = :p WHERE user_id = :u"), {"p": plan, "u": user_id})


def _models(rows: list[dict]) -> None:
    """Deja en `llm_models` exactamente estos modelos (con el formato de `/models`)."""
    from sqlalchemy import delete

    from core.ai import catalog
    from core.db import session_scope
    from core.models import LlmModel

    with session_scope() as s:
        s.execute(delete(LlmModel))
        catalog.upsert_models(s, catalog.parse_models(rows))


def _model(mid: str, context: int = 32768, out: int | None = 4096, json_ok: bool = True, images: bool = False) -> dict:
    return {"id": mid, "context_length": context, "pricing": {"prompt": "0", "completion": "0"},
            "top_provider": {"context_length": context, "max_completion_tokens": out},
            "supported_parameters": ["max_tokens"] + (["response_format", "structured_outputs"] if json_ok else []),
            "architecture": {"input_modalities": ["text"] + (["image"] if images else [])}}


@pytest.fixture()
def ai(services):
    """Valkey sin contadores de IA, un modelo falso disponible y un proveedor falso nuevo en cada prueba."""
    from core.ai.provider import FAKE_MODEL, FakeProvider, set_provider
    from core.valkey import get_valkey

    r = get_valkey()
    for key in r.scan_iter("ai:*"):
        r.delete(key)
    _models([FAKE_MODEL])
    fake = FakeProvider()
    set_provider(fake)
    yield fake
    set_provider(None)


def _budget(plan: str = "pro", owner: str = "ia-presupuesto", reserved: int = 0):
    from core.ai.client import JobBudget
    from core.plans import load_plans_file
    from core.settings import get_settings
    from core.valkey import get_valkey

    settings = get_settings()
    return JobBudget(settings=settings, r=get_valkey(), owner_type="user", owner_id=owner,
                     plan=load_plans_file(settings.PLANS_FILE)[plan], reserved=reserved)


def _client(provider, budget=None, tool: str = "resumir-pdf", category: str = "ai", chat: bool = False):
    from core.ai.client import AIClient
    from core.settings import get_settings
    from core.valkey import get_valkey

    return AIClient(settings=get_settings(), r=get_valkey(), tool=tool, category=category, budget=budget or _budget(),
                    chat=chat, provider=provider, sleep=lambda s: None)


# --- 16.3: presupuesto y limitador ---


def test_request_951_of_the_day_is_blocked(ai):
    from core.ai import budget
    from core.settings import get_settings
    from core.valkey import get_valkey

    settings, r = get_settings(), get_valkey()
    assert budget.reserve(r, settings, 950, pro=True)
    assert not budget.reserve(r, settings, 1, pro=True)  # la 951
    assert budget.status(r, settings)["remaining_pro"] == 0
    budget.release(r, settings, 1)
    assert budget.reserve(r, settings, 1, pro=True)


def test_free_user_does_not_use_the_pro_reserve(ai):
    from core.ai import budget
    from core.settings import get_settings
    from core.valkey import get_valkey

    settings, r = get_settings(), get_valkey()
    assert budget.reserve(r, settings, 550, pro=False)
    assert not budget.reserve(r, settings, 1, pro=False)  # 950 - 400 de reserva Pro
    assert budget.reserve(r, settings, 400, pro=True)
    assert not budget.reserve(r, settings, 1, pro=True)


def test_rpm_limit_18_per_minute_and_chat_share(ai):
    from core.ai import budget
    from core.settings import get_settings
    from core.valkey import get_valkey

    settings, r = get_settings(), get_valkey()
    t0 = 1_800_000_000_000
    for i in range(9):  # el chat solo usa la mitad del minuto
        assert budget.acquire_rpm(r, settings, chat=True, now_ms=t0 + i) == 0
    assert budget.acquire_rpm(r, settings, chat=True, now_ms=t0 + 10) > 0
    for i in range(9):  # las tareas siguen teniendo su parte
        assert budget.acquire_rpm(r, settings, chat=False, now_ms=t0 + 20 + i) == 0
    wait = budget.acquire_rpm(r, settings, chat=False, now_ms=t0 + 40)  # la 19 del minuto espera
    assert 59_000 < wait <= 60_000
    assert budget.acquire_rpm(r, settings, chat=False, now_ms=t0 + 60_001) == 0  # ventana deslizante


def test_client_waits_for_the_minute_window_and_counts_it(ai):
    from core.ai import budget
    from core.ai.catalog import Needs
    from core.settings import get_settings
    from core.valkey import get_valkey

    settings, r = get_settings(), get_valkey()
    now = int(__import__("time").time() * 1000)
    for i in range(18):
        budget.acquire_rpm(r, settings, now_ms=now + i)
    waits: list[float] = []
    client = _client(ai)
    client.sleep = lambda s: (waits.append(s), r.delete("ai:rpm"))
    client.complete([{"role": "user", "content": "hola"}], needs=Needs(), max_tokens=50)
    assert waits and waits[0] > 50 and len(ai.calls) == 1


# --- 16.3: candidatos, reintentos y data_collection ---


def _openrouter(handler):
    from core.ai.provider import OpenRouterProvider

    return OpenRouterProvider("https://openrouter.test/api/v1", "clave-de-prueba", transport=httpx.MockTransport(handler))


def _ok(model: str, text: str = "hecho") -> httpx.Response:
    return httpx.Response(200, json={"model": model, "choices": [{"message": {"content": text}}],
                                     "usage": {"prompt_tokens": 12, "completion_tokens": 3}})


def test_429_on_first_model_is_solved_by_the_next_candidate(ai):
    from core.ai.catalog import Needs
    from core.db import session_scope
    from core.models import AiRequest

    _models([_model("a/primero:free", 65536), _model("b/segundo:free", 32768)])
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        assert request.headers["authorization"] == "Bearer clave-de-prueba"
        if body["model"] == "a/primero:free":
            return httpx.Response(429, headers={"Retry-After": "1"}, json={"error": {"code": 429, "message": "límite"}})
        return _ok(body["model"])

    budget = _budget(owner="ia-429")
    result = _client(_openrouter(handler), budget).complete([{"role": "user", "content": "x"}], needs=Needs(), max_tokens=50)
    assert result.model == "b/segundo:free" and result.text == "hecho"
    assert [b["model"] for b in bodies] == ["a/primero:free", "b/segundo:free"]
    assert bodies[0]["models"] == ["a/primero:free", "b/segundo:free"]
    assert budget.used == 2  # el intento fallido también cuenta (6.3)
    with session_scope() as s:
        rows = s.query(AiRequest).filter(AiRequest.owner_id == "ia-429").order_by(AiRequest.id).all()
        assert [(x.status, x.model) for x in rows] == [("rate_limited", "a/primero:free"), ("ok", "b/segundo:free")]
        assert rows[1].prompt_tokens == 12 and rows[1].completion_tokens == 3


def test_every_request_sends_data_collection_deny_also_retries_json_and_router(ai):
    from core.ai.catalog import Needs
    from core.errors import ToolError

    _models([_model("a/uno:free"), _model("b/dos:free", json_ok=False)])
    bodies: list[dict] = []

    def failing(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(503, json={"error": {"code": 503, "message": "sin proveedor"}})

    with pytest.raises(ToolError) as err:
        _client(_openrouter(failing), _budget(owner="ia-deny")).complete([{"role": "user", "content": "x"}], needs=Needs(), max_tokens=50)
    assert err.value.code == "AI_UNAVAILABLE" and len(bodies) == 3  # 1 + 2 reintentos
    assert bodies[-1]["models"][-1] == "openrouter/free"  # último recurso
    bodies.clear()

    def json_ok(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return _ok("a/uno:free", '{"titulo": "Hola"}')

    schema = {"type": "object", "properties": {"titulo": {"type": "string"}}, "required": ["titulo"]}
    data, _ = _client(_openrouter(json_ok), _budget(owner="ia-deny-json")).complete_json(
        [{"role": "user", "content": "x"}], needs=Needs(), max_tokens=50, schema=schema)
    assert data == {"titulo": "Hola"}
    assert bodies[0]["response_format"]["type"] == "json_schema" and bodies[0]["provider"]["require_parameters"] is True
    assert bodies[0]["models"] if len(bodies[0].get("models", [])) > 1 else bodies[0]["model"] == "a/uno:free"
    for body in ai.calls + bodies:
        assert body["provider"]["data_collection"] == "deny"


def test_json_without_native_support_is_repaired_once(ai):
    from core.ai.catalog import Needs

    _models([_model("c/sin-json:free", json_ok=False)])
    answers = iter(["Claro, aquí va: {titulo: mal}", '```json\n{"titulo": "Bien"}\n```'])
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return _ok("c/sin-json:free", next(answers))

    schema = {"type": "object", "properties": {"titulo": {"type": "string"}}}
    data, _ = _client(_openrouter(handler), _budget(owner="ia-repara")).complete_json(
        [{"role": "user", "content": "x"}], needs=Needs(), max_tokens=50, schema=schema)
    assert data == {"titulo": "Bien"} and len(bodies) == 2
    assert "response_format" not in bodies[0] and "JSON" in bodies[0]["messages"][0]["content"]


def test_data_policy_failure_pauses_the_model_24h(ai):
    from core.ai.catalog import Needs
    from core.db import session_scope
    from core.models import LlmModel

    _models([_model("d/recoge:free"), _model("e/limpio:free", 16384)])

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["model"] == "d/recoge:free":
            return httpx.Response(404, json={"error": {"code": 404, "message": "No endpoints found matching your data policy"}})
        return _ok(body["model"])

    result = _client(_openrouter(handler), _budget(owner="ia-politica")).complete([{"role": "user", "content": "x"}],
                                                                                  needs=Needs(), max_tokens=50)
    assert result.model == "e/limpio:free"
    with session_scope() as s:
        assert s.get(LlmModel, "d/recoge:free").disabled_until is not None
        from core.ai import catalog
        from core.settings import get_settings

        assert [c.id for c in catalog.usable(s, get_settings())] == ["e/limpio:free"]


# --- 16.3: descubrimiento y reconciliación ---


def test_discovery_keeps_price_zero_models_with_their_max_completion_tokens(ai):
    from core.ai.tasks import refresh_models
    from core.db import session_scope
    from core.models import LlmModel

    listing = [
        _model("gratis/con-sufijo:free", 131072, 8192, images=True),
        {**_model("gratis/sin-sufijo", 65536, None, json_ok=False)},
        {**_model("pago/modelo", 200000, 8192), "pricing": {"prompt": "0.000003", "completion": "0.000015"}},
        {**_model("gratis/por-peticion", 8192, 1024), "pricing": {"prompt": "0", "completion": "0", "request": "0.01"}},
    ]

    class Lister:
        def list_models(self):
            return listing

    from core.ai.provider import set_provider

    set_provider(Lister())
    assert refresh_models() == 2
    with session_scope() as s:
        rows = {m.id: m for m in s.query(LlmModel).all()}
    assert set(rows) >= {"gratis/con-sufijo:free", "gratis/sin-sufijo"} and "pago/modelo" not in rows
    assert "gratis/por-peticion" not in rows
    one = rows["gratis/con-sufijo:free"]
    assert (one.context_length, one.max_completion_tokens, one.supports_json, one.supports_images) == (131072, 8192, True, True)
    two = rows["gratis/sin-sufijo"]
    assert two.max_completion_tokens is None and not two.supports_json


def test_reconciliation_raises_own_counter_and_leaves_ai_to_pro(ai):
    from core.ai import budget
    from core.ai.provider import set_provider
    from core.ai.tasks import reconcile
    from core.settings import get_settings
    from core.valkey import get_valkey

    settings, r = get_settings(), get_valkey()
    assert budget.reserve(r, settings, 5, pro=False)
    budget.count_used(r, settings, 5)

    class Key:
        def key_info(self):
            return {"usage": 0, "limit": None, "is_free_tier": False,
                    "free_model_daily_requests": {"used": 12, "limit": 1000, "remaining": 15}}

    set_provider(Key())
    snap = reconcile()
    st = budget.status(r, settings)
    assert (st["used"], st["total"], snap["raised_by"]) == (12, 12, 7)
    assert st["pro_only"] and not budget.reserve(r, settings, 1, pro=False) and budget.reserve(r, settings, 1, pro=True)
    assert budget.key_snapshot(r)["free_model_daily_requests"]["remaining"] == 15


# --- 16.3: API: sin modelos, consentimiento y caché ---


def test_without_valid_models_the_tool_is_unavailable_without_spending(api, ai, user_token, tus_upload, fixtures_dir, services):
    from core.ai import budget
    from core.settings import get_settings
    from core.valkey import get_valkey

    _models([_model("pequeno/modelo:free", 4096, 512)])  # no llega a lo que pide resumir-pdf
    token = user_token(user_id="ia-sin-modelos")
    api.get("/v1/me", headers=auth(token))
    uid, _ = tus_upload(token, "resumir-pdf", fixtures_dir / "texto.pdf")
    resp = api.post("/v1/jobs", json={"tool": "resumir-pdf", "upload_ids": [uid], "ai_consent": True}, headers=auth(token))
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "AI_UNAVAILABLE"
    assert budget.status(get_valkey(), get_settings())["total"] == 0 and ai.calls == []
    state = api.get("/v1/ai/budget", headers=auth(token)).json()
    assert state["tools"]["resumir-pdf"] is False and state["user"] == {"used": 0, "limit": 3, "remaining": 3}


def test_without_consent_400_and_anonymous_users_need_an_account(api, ai, user_token, anon_token, tus_upload, fixtures_dir):
    token = user_token(user_id="ia-sin-consentimiento")
    api.get("/v1/me", headers=auth(token))
    uid, _ = tus_upload(token, "resumir-pdf", fixtures_dir / "texto.pdf")
    resp = api.post("/v1/jobs", json={"tool": "resumir-pdf", "upload_ids": [uid]}, headers=auth(token))
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "AI_CONSENT_REQUIRED"
    assert resp.json()["error"]["consent_version"]
    anon = anon_token()
    uid, _ = tus_upload(anon, "resumir-pdf", fixtures_dir / "texto.pdf")
    resp = api.post("/v1/jobs", json={"tool": "resumir-pdf", "upload_ids": [uid], "ai_consent": True}, headers=auth(anon))
    assert resp.status_code == 401 and "cuenta" in resp.json()["error"]["message"] and ai.calls == []


def test_summary_end_to_end_with_fake_llm_and_cache_per_owner(api, ai, user_token, tus_upload, fixtures_dir, services):
    from docx import Document
    from sqlalchemy import create_engine, text

    from core.ai import budget
    from core.settings import get_settings
    from core.valkey import get_valkey

    token = user_token(user_id="ia-resumen")
    api.get("/v1/me", headers=auth(token))
    uid, _ = tus_upload(token, "resumir-pdf", fixtures_dir / "texto.pdf")
    job = api.post("/v1/jobs", json={"tool": "resumir-pdf", "upload_ids": [uid], "ai_consent": True}, headers=auth(token)).json()
    assert job["status"] == "succeeded", job
    assert job["outputs"][0]["name"] == "texto-resumen.docx" and "Peticiones de IA usadas: 1" in job["outputs"][0]["note"]
    path = Path(services["files"]) / "jobs" / job["id"] / "out"
    doc = Document(str(next(path.iterdir())))
    paragraphs = [p.text for p in doc.paragraphs]
    assert paragraphs[0] == "Resumen de texto" and any("Hola mundo pagina 1" in p for p in paragraphs)
    assert "Resumen hecho con IA (falso/modelo-de-prueba:free)" in paragraphs[-1]
    assert len(ai.calls) == 1 and "<<<" in ai.calls[0]["messages"][1]["content"]
    engine = create_engine(services["db_url"])
    with engine.begin() as conn:
        assert conn.execute(text("SELECT ai_requests FROM usage_daily WHERE owner_id='ia-resumen' AND cost_class='ai'")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM ai_consents WHERE owner_id='ia-resumen'")).scalar() == 1
        assert conn.execute(text("SELECT status FROM ai_requests WHERE owner_id='ia-resumen'")).scalars().all() == ["ok"]
        assert conn.execute(text("SELECT extractor FROM document_texts WHERE owner_id='ia-resumen'")).scalar() == "pdfium"
    assert budget.status(get_valkey(), get_settings())["total"] == 1
    # El mismo resumen en otro formato sale de la caché del propietario: no gasta peticiones.
    uid, _ = tus_upload(token, "resumir-pdf", fixtures_dir / "texto.pdf")
    again = api.post("/v1/jobs", json={"tool": "resumir-pdf", "upload_ids": [uid], "ai_consent": True,
                                       "options": {"formato": "txt"}}, headers=auth(token)).json()
    assert again["status"] == "succeeded" and "no ha gastado" in again["outputs"][0]["note"] and len(ai.calls) == 1
    with engine.begin() as conn:  # lo reservado y no usado se devuelve al terminar
        assert conn.execute(text("SELECT ai_requests FROM usage_daily WHERE owner_id='ia-resumen' AND cost_class='ai'")).scalar() == 1
    # Otro usuario con el mismo documento y las mismas opciones no recibe la caché del primero.
    other = user_token(user_id="ia-resumen-otro")
    api.get("/v1/me", headers=auth(other))
    uid, _ = tus_upload(other, "resumir-pdf", fixtures_dir / "texto.pdf")
    third = api.post("/v1/jobs", json={"tool": "resumir-pdf", "upload_ids": [uid], "ai_consent": True,
                                       "options": {"formato": "txt"}}, headers=auth(other)).json()
    assert third["status"] == "succeeded" and "usadas: 1" in third["outputs"][0]["note"] and len(ai.calls) == 2


def test_long_document_uses_blocks_and_too_many_requests_fail_before_spending(api, ai, user_token, tus_upload, services, tmp_path):
    from generate import text_pdf

    _models([_model("chico/modelo:free", 9000, 2000)])
    long_text = " ".join(["Contenido extenso sobre presupuestos municipales y obras publicas."] * 60)
    pdf = text_pdf(tmp_path / "largo.pdf", pages=40, text=long_text[:3500])
    token = user_token(user_id="ia-largo")
    api.get("/v1/me", headers=auth(token))
    _set_plan(services, "ia-largo", "pro")
    uid, _ = tus_upload(token, "resumir-pdf", pdf)
    job = api.post("/v1/jobs", json={"tool": "resumir-pdf", "upload_ids": [uid], "ai_consent": True,
                                     "options": {"formato": "md", "longitud": "breve"}}, headers=auth(token)).json()
    assert job["status"] == "succeeded", job
    blocks = len(ai.calls) - 1
    assert blocks >= 2 and "Únelos" in ai.calls[-1]["messages"][1]["content"]
    assert f"usadas: {blocks + 1}" in job["outputs"][0]["note"]
    # Un plan gratuito (5 peticiones por tarea y 30 páginas) no puede con las 40 páginas: falla antes de pedir nada.
    token = user_token(user_id="ia-largo-gratis")
    api.get("/v1/me", headers=auth(token))
    calls = len(ai.calls)
    uid, _ = tus_upload(token, "resumir-pdf", pdf)
    job = api.post("/v1/jobs", json={"tool": "resumir-pdf", "upload_ids": [uid], "ai_consent": True}, headers=auth(token)).json()
    assert job["status"] == "failed" and job["error"]["code"] == "LIMIT_EXCEEDED"
    assert "30 páginas por tarea de IA" in job["error"]["message"] and len(ai.calls) == calls
    uid, _ = tus_upload(token, "resumir-pdf", pdf)
    job = api.post("/v1/jobs", json={"tool": "resumir-pdf", "upload_ids": [uid], "ai_consent": True,
                                     "options": {"paginas": "1-30"}}, headers=auth(token)).json()
    assert job["status"] == "failed" and job["error"]["code"] == "LIMIT_EXCEEDED"
    assert "peticiones de IA" in job["error"]["message"] and len(ai.calls) == calls
    from sqlalchemy import create_engine, text

    with create_engine(services["db_url"]).begin() as conn:  # nada gastado, nada retenido
        used = conn.execute(text("SELECT ai_requests FROM usage_daily WHERE owner_id='ia-largo-gratis' AND cost_class='ai'")).scalar()
    assert used == 0


# --- 16.3: herramientas excluidas ---


def test_excluded_tools_never_reach_openrouter(ai, make_ctx, tmp_path, fixtures_dir):
    from core.ai import is_excluded
    from core.ai.provider import set_provider
    from core.errors import ToolError
    from core.registry import load_registry

    for spec in load_registry().specs:
        if is_excluded(spec.slug_es, spec.category):
            assert spec.ai is None and spec.cost_class != "ai", spec.slug_es

    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("una herramienta excluida ha llamado a OpenRouter")

    provider = _openrouter(explode)
    set_provider(provider)
    with pytest.raises(ToolError) as err:
        _client(provider, tool="firmar-pdf", category="sign")
    assert err.value.code == "AI_UNAVAILABLE"
    with pytest.raises(ToolError):
        _client(provider, tool="eml-a-pdf", category="pdf")
    # eml-a-pdf entera con un transporte que falla si se usa: termina sin tocar el proveedor.
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = "Ana <ana@ejemplo.test>", "Luis <luis@ejemplo.test>", "Contrato"
    msg.set_content("Texto del correo con datos personales")
    eml = tmp_path / "contrato.eml"
    eml.write_bytes(msg.as_bytes())
    with respx.mock:
        respx.route(host="openrouter.ai").mock(side_effect=AssertionError("OpenRouter"))
        respx.post(url__regex=r"http://gotenberg\.test/.*").mock(
            return_value=httpx.Response(200, content=(fixtures_dir / "texto.pdf").read_bytes()))
        out = run("eml-a-pdf", make_ctx("eml-a-pdf", [eml]))
    assert Path(out[0]["path"]).exists()


# --- texto de escaneos: la etapa de OCR en `workerocr` ---


@pytest.mark.needs_tesseract
def test_scanned_pdf_goes_to_ocr_queue_and_back(api, ai, user_token, tus_upload, fixtures_dir, services, monkeypatch):
    import shutil

    if shutil.which("tesseract") is None:
        pytest.skip("Tesseract no instalado")
    from sqlalchemy import create_engine, text

    from tools import tasks

    hops: list[str] = []

    def send_task(name, args=None, queue=None, **kw):
        hops.append(queue)
        return tasks.execute(*args)

    monkeypatch.setattr(tasks.celery_app, "send_task", send_task)
    token = user_token(user_id="ia-escaneo")
    api.get("/v1/me", headers=auth(token))
    uid, _ = tus_upload(token, "resumir-pdf", fixtures_dir / "escaneado.pdf")
    job = api.post("/v1/jobs", json={"tool": "resumir-pdf", "upload_ids": [uid], "ai_consent": True,
                                     "options": {"formato": "txt", "idioma_documento": "es"}}, headers=auth(token)).json()
    job = api.get(f"/v1/jobs/{job['id']}", headers=auth(token)).json()
    assert job["status"] == "succeeded", job
    assert hops == ["ocr", "ai"]
    assert "Factura" in ai.calls[0]["messages"][1]["content"]
    with create_engine(services["db_url"]).begin() as conn:
        assert conn.execute(text("SELECT extractor FROM document_texts WHERE owner_id='ia-escaneo'")).scalar() == "pdfium+tesseract"
        assert conn.execute(text("SELECT tasks FROM usage_daily WHERE owner_id='ia-escaneo' AND cost_class='heavy'")).scalar() == 1
    # Sin OCR (y sin texto ya leído de ese documento), el trabajo dice qué páginas son imágenes y no gasta peticiones.
    calls = len(ai.calls)
    token = user_token(user_id="ia-escaneo-sin-ocr")
    api.get("/v1/me", headers=auth(token))
    uid, _ = tus_upload(token, "resumir-pdf", fixtures_dir / "escaneado.pdf")
    other = api.post("/v1/jobs", json={"tool": "resumir-pdf", "upload_ids": [uid], "ai_consent": True,
                                       "options": {"ocr": False}}, headers=auth(token)).json()
    assert other["status"] == "failed" and "son imágenes sin texto" in other["error"]["message"]
    assert len(ai.calls) == calls and hops == ["ocr", "ai"]


def test_settings_force_consent_in_production(services, monkeypatch):
    from core.settings import Settings

    assert Settings(APP_ENV="production", AI_REQUIRE_CONSENT=False).ai_consent_required
    assert not Settings(APP_ENV="development", AI_REQUIRE_CONSENT=False, OPENROUTER_API_KEY="").ai_consent_required
    assert Settings(APP_ENV="development", OPENROUTER_API_KEY="").ai_fake
    assert not Settings(APP_ENV="production", OPENROUTER_API_KEY="").ai_fake
