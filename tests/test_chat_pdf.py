"""chat-pdf (7.6, 6.3, 6.5 y 9.1): preparar el documento, fragmentos con vectores en pgvector y respuestas por eventos.

Las pruebas con vectores reales necesitan el modelo de embeddings en `EMBEDDINGS_HOME` (la CI lo baja con
infra/embeddings/fetch-model.sh); sin él se omiten.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from helpers import auth
from test_ia import _client, _budget, _model, _models, _openrouter, ai  # noqa: F401 - fixture compartida

pytestmark = pytest.mark.integration


def _embeddings_home() -> Path:
    return Path(os.environ.get("EMBEDDINGS_HOME", "/opt/models/embeddings"))


needs_model = pytest.mark.skipif(
    not (_embeddings_home() / "paraphrase-multilingual-MiniLM-L12-v2" / "model_optimized.onnx").is_file(),
    reason="Modelo de embeddings no disponible (infra/embeddings/fetch-model.sh)")


QUEUES: list[str] = []


@pytest.fixture()
def chat_api(api, monkeypatch):
    """Las dos tareas (búsqueda en `ai.embed` y respuesta en `ai`) se ejecutan en el mismo proceso, en orden: los
    eventos ya están en Valkey cuando la API los lee. `QUEUES` guarda por qué colas ha pasado cada pregunta."""
    from app.routers import ai as ai_router
    from core.settings import get_settings
    from tools.ai import chat

    def dispatch(name: str, args: list, queue: str) -> None:
        QUEUES.append(queue)
        if name == "tools.ai.chat.retrieve":
            chat.run_retrieve(*args)
        else:
            chat.run_answer(*args, sleep=lambda s: None)

    QUEUES.clear()
    monkeypatch.setattr(get_settings(), "EMBEDDINGS_HOME", _embeddings_home())
    monkeypatch.setitem(ai_router.CHAT_ENQUEUE, "fn", dispatch)
    monkeypatch.setitem(chat.SEND, "fn", dispatch)
    return api


def _events(resp) -> list[dict]:
    out, kind = [], None
    for line in resp.iter_lines():
        if line.startswith("event: "):
            kind = line[7:]
        elif line.startswith("data: "):
            out.append({"event": kind, **json.loads(line[6:])})
    return out


def _ask(api, token: str, job_id: str, question: str, history: list | None = None, consent: bool = True):
    body = {"job_id": job_id, "message": question, "history": history or [], "ai_consent": consent}
    with api.stream("POST", "/v1/ai/chat", json=body, headers=auth(token)) as resp:
        if resp.status_code != 200:
            resp.read()
            return resp.status_code, resp.json()
        return 200, _events(resp)


def _prepare(api, user_token, tus_upload, path: Path, user: str, options: dict | None = None) -> tuple[str, dict]:
    token = user_token(user_id=user)
    api.get("/v1/me", headers=auth(token))
    uid, _ = tus_upload(token, "chat-pdf", path)
    job = api.post("/v1/jobs", json={"tool": "chat-pdf", "upload_ids": [uid], "ai_consent": True, "options": options or {}},
                   headers=auth(token)).json()
    return token, job


def test_short_document_goes_whole_and_answer_streams_with_pages(chat_api, ai, user_token, tus_upload, fixtures_dir, services):
    from sqlalchemy import create_engine, text

    token, job = _prepare(chat_api, user_token, tus_upload, fixtures_dir / "texto.pdf", "chat-corto")
    assert job["status"] == "succeeded" and job["outputs"] == [], job
    assert ai.calls == []  # preparar no gasta peticiones
    info = chat_api.get(f"/v1/ai/chat/{job['id']}", headers=auth(token)).json()
    assert info["pages"] == [1, 2, 3] and info["chunks"] == 0 and info["name"] == "texto.pdf"
    status, events = _ask(chat_api, token, job["id"], "¿Qué dice la página 2?")
    assert status == 200, events
    kinds = [e["event"] for e in events]
    assert kinds[0] == "start" and kinds[-1] == "done" and kinds.count("delta") >= 2
    answer = "".join(e["text"] for e in events if e["event"] == "delta")
    assert "Respuesta de prueba" in answer and "¿Qué dice la página 2?" in answer
    assert events[-1]["mode"] == "completo" and events[-1]["pages"] == [1]
    assert QUEUES == ["ai"]  # documento corto: directo a workerai, sin pasar por los embeddings
    sent = ai.calls[-1]
    assert sent["stream"] is True and sent["provider"]["data_collection"] == "deny"
    assert "Hola mundo pagina 3" in sent["messages"][-1]["content"]  # el documento entero
    with create_engine(services["db_url"]).begin() as conn:
        assert conn.execute(text("SELECT ai_requests FROM usage_daily WHERE owner_id='chat-corto' AND cost_class='ai'")).scalar() == 1
        assert conn.execute(text("SELECT status FROM ai_requests WHERE owner_id='chat-corto'")).scalars().all() == ["ok"]
    from core.valkey import get_valkey

    assert get_valkey().zcard("ai:rpm:chat") == 1  # el chat usa su parte del límite por minuto
    # La conversación anterior viaja con la pregunta (los últimos turnos que caben).
    history = [{"role": "user", "content": "¿Qué dice la página 2?"}, {"role": "assistant", "content": answer}]
    status, events = _ask(chat_api, token, job["id"], "¿Y la 3?", history)
    assert status == 200 and events[-1]["event"] == "done"
    assert [m["role"] for m in ai.calls[-1]["messages"]] == ["system", "user", "assistant", "user"]


@needs_model
def test_long_document_is_searched_with_pgvector(chat_api, ai, user_token, tus_upload, services, tmp_path):
    from sqlalchemy import create_engine, text

    from generate import text_pdf

    filler = " ".join(["Informe anual de actividad con datos generales del ejercicio y comentarios del equipo."] * 40)
    pdf = text_pdf(tmp_path / "largo.pdf", pages=12, text=filler[:3200])
    # Una página con el dato que se va a preguntar.
    import pikepdf

    doc = pikepdf.open(pdf, allow_overwriting_input=True)
    page = doc.pages[7]
    page.Contents = doc.make_stream(b"BT /F1 12 Tf 72 720 Td (El contrato de mantenimiento vence el 31 de marzo de 2027.) Tj ET")
    doc.save(pdf)
    token, job = _prepare(chat_api, user_token, tus_upload, pdf, "chat-largo")
    assert job["status"] == "succeeded", job
    info = chat_api.get(f"/v1/ai/chat/{job['id']}", headers=auth(token)).json()
    assert info["chunks"] > 12 and info["tokens"] > 3000
    with create_engine(services["db_url"]).begin() as conn:
        dims = conn.execute(text("SELECT vector_dims(embedding) FROM document_chunks WHERE owner_id='chat-largo' LIMIT 1")).scalar()
    assert dims == 384
    _models([_model("chico/modelo:free", 9000, 2000)])  # el documento no cabe entero: hay que buscar
    status, events = _ask(chat_api, token, job["id"], "¿Cuándo vence el contrato de mantenimiento?")
    assert status == 200 and events[-1]["event"] == "done", events
    assert events[-1]["mode"] == "busqueda" and QUEUES == ["ai.embed", "ai"]
    context = ai.calls[-1]["messages"][-1]["content"]
    # La búsqueda trae el fragmento de la página 8 (con sus vecinos), no el documento entero.
    assert "31 de marzo de 2027" in context and "[Página 8]" in context
    assert len(context) < 11 * 3200 / 2


def test_chat_errors_cost_nothing(chat_api, ai, user_token, anon_token, tus_upload, fixtures_dir, services):
    from core.ai import budget
    from core.settings import get_settings
    from core.valkey import get_valkey

    token, job = _prepare(chat_api, user_token, tus_upload, fixtures_dir / "texto.pdf", "chat-errores")
    status, body = _ask(chat_api, token, job["id"], "¿Hola?", consent=False)
    assert status == 400 and body["error"]["code"] == "AI_CONSENT_REQUIRED"
    other = user_token(user_id="chat-otro")
    chat_api.get("/v1/me", headers=auth(other))
    assert _ask(chat_api, other, job["id"], "¿Hola?")[0] == 404  # el documento es de otro usuario
    assert _ask(chat_api, anon_token(), job["id"], "¿Hola?")[0] == 401
    _models([_model("pequeno/modelo:free", 4096, 512)])
    status, body = _ask(chat_api, token, job["id"], "¿Hola?")
    assert status == 503 and body["error"]["code"] == "AI_UNAVAILABLE"
    assert budget.status(get_valkey(), get_settings())["total"] == 0 and ai.calls == []
    from core.ai.provider import FAKE_MODEL

    _models([FAKE_MODEL])
    budget.reserve(get_valkey(), get_settings(), 550, pro=False)  # cupo gratuito del día agotado
    status, body = _ask(chat_api, token, job["id"], "¿Hola?")
    assert status == 429 and body["error"]["code"] == "AI_BUDGET_EXHAUSTED" and "hora de Madrid" in body["error"]["message"]


def _sse(chunks: list[dict]) -> bytes:
    lines = [": OPENROUTER PROCESSING\n\n"] + [f"data: {json.dumps(c)}\n\n" for c in chunks] + ["data: [DONE]\n\n"]
    return "".join(lines).encode()


def test_openrouter_stream_parsing_retry_and_mid_stream_failure(ai):
    from core.ai.catalog import Needs
    from core.errors import ToolError

    _models([_model("a/primero:free", 65536), _model("b/segundo:free", 32768)])
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if body["model"] == "a/primero:free":
            return httpx.Response(429, json={"error": {"code": 429, "message": "límite"}})
        chunks = [{"model": "b/segundo:free", "choices": [{"delta": {"content": "Hola "}}]},
                  {"model": "b/segundo:free", "choices": [{"delta": {"content": "mundo"}}]},
                  {"model": "b/segundo:free", "choices": [], "usage": {"prompt_tokens": 20, "completion_tokens": 2}}]
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=_sse(chunks))

    pieces: list[str] = []
    client = _client(_openrouter(handler), _budget(owner="chat-stream"), chat=True)
    result = client.stream([{"role": "user", "content": "x"}], needs=Needs(), max_tokens=50, on_delta=pieces.append)
    assert pieces == ["Hola ", "mundo"] and result.text == "Hola mundo" and result.model == "b/segundo:free"
    assert result.prompt_tokens == 20 and len(bodies) == 2
    assert all(b["stream"] is True and b["provider"]["data_collection"] == "deny" for b in bodies)
    # Si falla a mitad, no se repite: el usuario ya ha visto parte de la respuesta.
    bodies.clear()

    def broken(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        chunks = [{"model": "a/primero:free", "choices": [{"delta": {"content": "Empieza "}}]},
                  {"error": {"code": 502, "message": "proveedor caído"}}]
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=_sse(chunks))

    pieces.clear()
    with pytest.raises(ToolError) as err:
        _client(_openrouter(broken), _budget(owner="chat-roto"), chat=True).stream(
            [{"role": "user", "content": "x"}], needs=Needs(), max_tokens=50, on_delta=pieces.append)
    assert err.value.code == "AI_UNAVAILABLE" and pieces == ["Empieza "] and len(bodies) == 1


def test_deleting_the_account_removes_document_texts_chunks_and_cache(chat_api, ai, user_token, tus_upload, fixtures_dir, services):
    from sqlalchemy import create_engine, text

    token, job = _prepare(chat_api, user_token, tus_upload, fixtures_dir / "texto.pdf", "chat-borrar")
    engine = create_engine(services["db_url"])
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM document_texts WHERE owner_id='chat-borrar'")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM ai_cache WHERE owner_id='chat-borrar'")).scalar() == 1
    assert chat_api.delete("/v1/me", headers=auth(token)).status_code == 200
    with engine.begin() as conn:
        for table in ("document_texts", "ai_cache", "document_chunks"):
            assert conn.execute(text(f"SELECT count(*) FROM {table} WHERE owner_id='chat-borrar'")).scalar() == 0
