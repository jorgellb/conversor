"""F3, lote E: traducir-subtitulos y resumir-reunion (7.10), con el proveedor falso (D-126 y D-133).

- Sin servicios: lectura y escritura de subtítulos con pysubs2, alineación de un elemento JSON por subtítulo, ancho de
  línea, tiempos intactos, acta de la reunión y tramos.
- Con PostgreSQL y Valkey (`integration`): de extremo a extremo por la API, las colas encadenadas `av.heavy` → `ai`,
  la caché, el límite de peticiones por tarea y las reservas devueltas cuando la cadena falla a mitad (D-121).
  Las que transcriben de verdad necesitan FFmpeg y un modelo de faster-whisper en `WHISPER_HOME` (la CI baja tiny); la
  reunión con voz sintética necesita además espeak-ng y Kokoro en `KOKORO_HOME` (D-172). Sin ellos, se saltan. Las que
  no transcriben guardan antes la transcripción en `document_texts`, como la dejaría la etapa de `av.heavy`.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from core.errors import ErrorCode, ToolError
from core.registry import load_registry
from helpers import auth
from test_ia import _models, _set_plan, ai  # noqa: F401 - fixture compartida
from tools.ai import grabacion, reunion
from tools.ai import subtitulos as st

FIXTURES = Path(__file__).resolve().parents[1] / "scripts" / "fixtures"
SPEECH = Path(__file__).parent / "fixtures" / "jfk.ogg"
sys.path.insert(0, str(FIXTURES))


def whisper_home() -> Path:
    return Path(os.environ.get("WHISPER_HOME", "/opt/models/whisper"))


def kokoro_home() -> Path:
    return Path(os.environ.get("KOKORO_HOME", "/opt/models/kokoro"))


def whisper_model() -> str | None:
    for name in ("tiny", "small"):
        if (whisper_home() / f"faster-whisper-{name}" / "model.bin").is_file():
            return name
    return None


needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg no instalado")
needs_whisper = pytest.mark.skipif(shutil.which("ffmpeg") is None or whisper_model() is None,
                                   reason="Sin FFmpeg o sin modelo de faster-whisper en WHISPER_HOME")
needs_voice = pytest.mark.skipif(not ((kokoro_home() / "model.onnx").is_file() and shutil.which("espeak-ng")),
                                 reason="Sin espeak-ng o sin el modelo de Kokoro en KOKORO_HOME")


@pytest.fixture(scope="module")
def subs_dir(tmp_path_factory):
    from subtitulos import generate

    out = tmp_path_factory.mktemp("subtitulos")
    generate(out)
    return out


# ——— Sin servicios ———


def test_options_contract_and_registry():
    reg = load_registry()
    sub = reg.require("traducir-subtitulos")
    meet = reg.require("resumir-reunion")
    assert sub.slug_en == "translate-subtitles" and meet.slug_en == "summarize-meeting"
    assert sub.queue == "ai" and meet.queue == "av.heavy" and meet.cost_for({}) == "heavy" and sub.cost_for({}) == "ai"
    assert {"srt", "vtt", "ass", "mp3", "mp4"} <= set(sub.inputs) and "srt" not in meet.inputs
    o = sub.options.model_validate({})
    assert (o.destino, o.salida, o.bilingue, o.origen, o.caracteres_por_linea, o.desde, o.hasta) == ("es", "mismo", False, "auto", 42, "0:00", "")
    m = meet.options.model_validate({})
    assert (m.idioma, m.longitud, m.idioma_resumen, m.formato, m.transcripcion) == ("auto", "media", "reunion", "docx", False)
    assert m.temas and m.decisiones and m.tareas and m.preguntas
    for bad in ({"caracteres_por_linea": 29}, {"caracteres_por_linea": 61}, {"desde": "1:00", "hasta": "0:30"}, {"hasta": "ayer"},
                {"destino": "xx"}, {"glosario": "x" * 1001}):
        with pytest.raises(ValueError):
            sub.options.model_validate(bad)
    assert sub.options.model_validate({"desde": "1:30", "hasta": "1:00:00"}).hasta == "1:00:00"


def test_decoding_and_webvtt_blocks(subs_dir):
    assert st.decode("Canción".encode("cp1252")) == "Canción"
    assert st.decode("﻿Año".encode("utf-8")) == "Año"
    assert st.decode("Niño".encode("utf-16")) == "Niño"
    subs = st.parse(subs_dir / "reunion.vtt", "vtt")
    # Sin la nota ni el estilo: tres subtítulos y ninguno con «NOTE» pegado.
    assert [e.plaintext for e in subs] == ["Bienvenidos a la reunión.", "La señal empieza a las diez.", "¿Alguna pregunta?"]
    old = st.parse(subs_dir / "antiguo.srt", "srt")
    assert "Muñoz" in old.events[4].plaintext
    # SSA (v4.00) se lee como ASS; un SRT con extensión .ass no se adivina como SRT: no tiene subtítulos.
    ssa = st.parse_text("[Script Info]\nScriptType: v4.00\n\n[Events]\nFormat: Marked, Start, End, Style, Name, MarginL, "
                        "MarginR, MarginV, Effect, Text\nDialogue: Marked=0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hola\n", "ass")
    assert [e.plaintext for e in ssa] == ["Hola"]
    assert len(st.parse_text("1\n00:00:01,000 --> 00:00:02,000\nHola\n", "ass").events) == 0


def test_items_keep_markup_dialogue_and_skip_what_is_not_text(subs_dir):
    subs = st.parse(subs_dir / "reunion.srt", "srt")
    items, outside = st.items_of(subs)
    assert outside == 0
    assert [i.index for i in items] == [0, 1, 2, 4, 5]  # la nota musical no se manda
    assert items[0].prefix == "{\\i1}" and items[0].suffix == "{\\i0}" and items[0].source == "Buenos días a todos."
    assert items[1].source == "Hoy vamos a hablar del presupuesto y de la nueva página web."
    assert items[2].dialogue and items[2].source == "- ¿Llegará a tiempo?\n- Sí, el viernes."
    assert items[3].inner_tags and items[3].source == "El diseño tiene que ser más sencillo, señor Muñoz."
    ass = st.parse(subs_dir / "reunion.ass", "ass")
    items, _ = st.items_of(ass)
    assert [i.source for i in items] == ["Bienvenidos a la reunión anual.", "Sala de juntas", "Empezamos con el primer punto."]
    assert items[1].prefix == "{\\an8}"  # la posición del cartel se conserva
    # Tramo de 5 s a 60 s: los dos primeros y el último (1:05) quedan fuera.
    inside, outside = st.items_of(subs, 5000, 60000)
    assert [i.index for i in inside] == [2, 4] and outside == 3


def test_wrap_balances_two_lines_and_never_cuts_text():
    assert st.wrap("Hola", 42) == ["Hola"]
    two = st.wrap("Hoy vamos a hablar del presupuesto y de la nueva página web", 42)
    assert len(two) == 2 and all(len(x) <= 42 for x in two) and abs(len(two[0]) - len(two[1])) < 12
    long = "Esta es una traducción bastante larga que no cabe en dos líneas de treinta caracteres ni de lejos"
    lines = st.wrap(long, 30)
    assert len(lines) > 2 and all(len(x) <= 30 for x in lines) and " ".join(lines) == long
    assert st.render("- Will it be on time?\n- Yes, on Friday.", True, 42) == ["- Will it be on time?", "- Yes, on Friday."]
    assert st.safe("a {b} c\\N") == "a (b) c/N"


def test_translation_keeps_every_time_and_format(subs_dir):
    for name, ext in (("reunion.srt", "srt"), ("reunion.vtt", "vtt"), ("reunion.ass", "ass")):
        subs = st.parse(subs_dir / name, ext)
        times = [(e.start, e.end, e.type) for e in subs]
        items, _ = st.items_of(subs)
        st.apply(subs, items, {i.source: f"Traducción número {k} de la prueba" for k, i in enumerate(items)}, 30, False)
        again = st.parse_text(subs.to_string(ext), ext)
        assert [(e.start, e.end, e.type) for e in again] == times
        for i in items:
            lines = [x for x in again.events[i.index].plaintext.split("\n") if x]
            assert all(len(x) <= 30 for x in lines) and " ".join(lines).startswith("Traducción número")
    ass = st.parse(subs_dir / "reunion.ass", "ass")
    items, _ = st.items_of(ass)
    st.apply(ass, items, {i.source: "Board room" for i in items}, 42, True)
    out = ass.to_string("ass")
    assert "Style: Cartel,Georgia,40" in out and "{\\an8}Sala de juntas\\NBoard room" in out
    assert "Comment: 0,0:00:05.00,0:00:06.00,Default,,0,0,0,,Nota del traductor: no traducir" in out
    assert "{\\p1}m 0 0 l 100 0 100 100 0 100{\\p0}" in out
    srt = st.parse(subs_dir / "reunion.srt", "srt")
    items, _ = st.items_of(srt)
    st.apply(srt, items, {i.source: "Good morning, everyone." for i in items}, 42, False)
    assert "<i>Good morning, everyone.</i>" in srt.to_string("srt")


def test_output_names_and_limits(subs_dir, tmp_path, monkeypatch):
    from tools.base import InputFile

    def inp(name: str) -> InputFile:
        return InputFile(Path(name), name, Path(name).suffix[1:], 0, "")

    assert st.output_name(inp("Película.en.srt"), "es", "srt") == "Película.es.srt"
    assert st.output_name(inp("reunión.mp4"), "fr", "srt") == "reunión.fr.srt"
    assert st.output_name(inp("capítulo 1.ass"), "en", "vtt") == "capítulo 1.en.vtt"
    monkeypatch.setattr(st, "MAX_BYTES", 100)
    with pytest.raises(ToolError) as exc:
        st.parse(subs_dir / "reunion.srt", "srt")
    assert exc.value.code == ErrorCode.LIMIT_EXCEEDED
    monkeypatch.setattr(st, "MAX_BYTES", 10**6)
    monkeypatch.setattr(st, "MAX_EVENTS", 3)
    with pytest.raises(ToolError) as exc:
        st.parse(subs_dir / "reunion.srt", "srt")
    assert exc.value.code == ErrorCode.LIMIT_EXCEEDED


def test_meeting_minutes_are_cleaned_and_written():
    with pytest.raises(ValueError):
        reunion.clean({"resumen": " ", "temas": [], "decisiones": [], "tareas": [], "preguntas": []})
    acta = reunion.clean({"resumen": "Se habló del presupuesto.", "temas": ["Presupuesto", "Presupuesto", ""],
                          "decisiones": ["Lanzar la web el viernes"],
                          "tareas": [{"tarea": "Preparar | el presupuesto", "responsable": "Ana", "fecha": ""}, {"tarea": " "}],
                          "preguntas": "no es una lista"})
    assert acta["temas"] == ["Presupuesto"] and acta["preguntas"] == [] and len(acta["tareas"]) == 1
    t = reunion.TEXTS["es"]
    md = reunion.as_text("Resumen de la reunión «x»", "Grabación", acta, ["temas", "tareas", "preguntas"], [[65, "Hola."]], t, "Nota", True)
    assert "## Tareas\n\n| Tarea | Responsable | Fecha |\n| --- | --- | --- |\n| Preparar \\| el presupuesto | Ana | — |" in md
    assert "## Preguntas abiertas\n\nNo se ha mencionado ninguna." in md and "[01:05] Hola." in md and "Decisiones" not in md
    txt = reunion.as_text("Título", "Info", acta, ["tareas"], None, t, "Nota", False)
    assert "TAREAS\n\n- Preparar | el presupuesto (Responsable: Ana)" in txt and "Transcripción" not in txt
    assert reunion.requests_for(1) == 1 and reunion.requests_for(3) == 4


def test_span_and_language_labels():
    o = load_registry().require("resumir-reunion").options.model_validate({"desde": "1:30", "hasta": "10:00"})
    assert grabacion.span_of(o) == (90.0, 600.0)
    assert grabacion.span_of(load_registry().require("resumir-reunion").options.model_validate({})) == (0.0, None)
    assert grabacion.language_label("en", "es") == "inglés" and grabacion.language_label("en", "en") == "English"


# ——— De extremo a extremo (PostgreSQL y Valkey) ———


@pytest.fixture()
def hops(monkeypatch):
    """Las etapas encadenadas (ai → av.heavy → ai) se ejecutan en el momento, apuntando la cola de cada una."""
    from tools import tasks

    seen: list[str] = []

    def send_task(name, args=None, queue=None, **kw):
        seen.append(queue)
        return tasks.execute(*args)

    monkeypatch.setattr(tasks.celery_app, "send_task", send_task)
    return seen


@pytest.fixture()
def whisper_env(monkeypatch):
    from core.settings import get_settings

    monkeypatch.setenv("WHISPER_HOME", str(whisper_home()))
    monkeypatch.setenv("WHISPER_MODEL", whisper_model() or "small")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _user(api, user_token, uid: str, services=None, plan: str | None = None) -> str:
    token = user_token(user_id=uid)
    api.get("/v1/me", headers=auth(token))
    if plan:
        _set_plan(services, uid, plan)
    return token


def _job(api, token, tus_upload, tool: str, path: Path, options: dict | None = None, consent: bool | None = True):
    uid, _ = tus_upload(token, tool, path)
    body = {"tool": tool, "upload_ids": [uid], "options": options or {}}
    if consent is not None:
        body["ai_consent"] = consent
    resp = api.post("/v1/jobs", json=body, headers=auth(token))
    if resp.status_code != 201:
        return resp
    return api.get(f"/v1/jobs/{resp.json()['id']}", headers=auth(token)).json()


def _out(services, job: dict, n: int = 0) -> Path:
    folder = Path(services["files"]) / "jobs" / job["id"] / "out"
    target = job["outputs"][n]["name"]
    return next(f for f in sorted(folder.iterdir()) if f.name == target or f.name.startswith(Path(target).stem))


def _used(api, token) -> int:
    return api.get("/v1/ai/budget", headers=auth(token)).json()["user"]["used"]


def _tasks(services, owner: str, cost_class: str) -> int:
    from sqlalchemy import create_engine, text

    with create_engine(services["db_url"]).begin() as conn:
        return conn.execute(text("SELECT COALESCE(SUM(tasks), 0) FROM usage_daily WHERE owner_id=:o AND cost_class=:c"),
                            {"o": owner, "c": cost_class}).scalar()


def _seed(owner: str, path: Path, tool: str, params: dict, payload: dict) -> None:
    """La transcripción que dejaría la etapa de `av.heavy` (para probar la de `ai` sin FFmpeg ni Whisper)."""
    from datetime import datetime, timedelta, timezone

    from core.ai.store import texts_put
    from core.db import session_scope
    from tools.base import InputFile

    inp = InputFile(path, path.name, path.suffix[1:], path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
    with session_scope() as s:
        texts_put(s, "user", owner, grabacion.key(inp, tool, params), [payload], "faster-whisper-tiny",
                  datetime.now(timezone.utc) + timedelta(hours=2))


SUB_PARAMS = {"idioma": "auto", "precision": "normal", "desde": "0:00", "hasta": "", "ancho": 42}
MEET_PARAMS = {"idioma": "auto", "precision": "normal", "desde": "0:00", "hasta": ""}


@pytest.mark.integration
def test_srt_translated_one_item_per_cue_keeping_times_and_cached(api, ai, user_token, tus_upload, services, subs_dir, hops):
    token = _user(api, user_token, "subs-srt")
    job = _job(api, token, tus_upload, "traducir-subtitulos", subs_dir / "reunion.srt", {"destino": "en"})
    assert job["status"] == "succeeded", job
    out = job["outputs"][0]
    assert out["name"] == "reunion.en.srt" and "usadas: 1" in out["note"] and "no se conservan" in out["note"]
    assert hops == []  # los subtítulos van directos a `ai`
    sent = ai.calls[-1]
    schema = sent["response_format"]["json_schema"]["schema"]["properties"]["traducciones"]
    assert schema["minItems"] == schema["maxItems"] == 5  # un elemento por subtítulo con texto
    original = st.parse(subs_dir / "reunion.srt", "srt")
    result = st.parse(_out(services, job), "srt")
    assert [(e.start, e.end) for e in result] == [(e.start, e.end) for e in original]
    assert result.events[3].plaintext == "♪ ♪"
    assert result.events[0].text.startswith("{\\i1}[inglés] Buenos días")
    assert result.events[2].plaintext.split("\n")[0].startswith("[inglés] - ¿Llegará")
    assert all(len(x) <= 42 for e in result for x in e.plaintext.split("\n"))
    assert _used(api, token) == 1
    # El mismo archivo en VTT y bilingüe: de la caché del propietario, sin gastar.
    again = _job(api, token, tus_upload, "traducir-subtitulos", subs_dir / "reunion.srt",
                 {"destino": "en", "salida": "vtt", "bilingue": True})
    assert again["status"] == "succeeded" and "no ha gastado" in again["outputs"][0]["note"] and len(ai.calls) == 1
    vtt = _out(services, again).read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT") and "<i>Buenos días a todos.\n[inglés] Buenos días a todos.</i>" in vtt


@pytest.mark.integration
def test_vtt_ass_range_and_old_encoding(api, ai, user_token, tus_upload, services, subs_dir):
    token = _user(api, user_token, "subs-formatos")
    job = _job(api, token, tus_upload, "traducir-subtitulos", subs_dir / "reunion.vtt", {"destino": "fr"})
    assert job["status"] == "succeeded", job
    body = _out(services, job).read_text(encoding="utf-8")
    assert job["outputs"][0]["name"] == "reunion.fr.vtt" and body.startswith("WEBVTT") and "[francés] La señal" in body
    assert "NOTE" not in body
    job = _job(api, token, tus_upload, "traducir-subtitulos", subs_dir / "reunion.ass", {"destino": "en"})
    assert job["status"] == "succeeded", job
    ass = _out(services, job).read_text(encoding="utf-8")
    assert "Style: Cartel,Georgia,40" in ass and "{\\an8}[inglés] Sala de juntas" in ass and "no traducir" in ass
    job = _job(api, token, tus_upload, "traducir-subtitulos", subs_dir / "antiguo.srt",
               {"destino": "en", "desde": "0:05", "hasta": "1:00", "salida": "srt"})
    assert job["status"] == "succeeded", job
    assert "fuera del tramo elegido sin traducir: 3" in job["outputs"][0]["note"]
    result = st.parse(_out(services, job), "srt")
    assert result.events[0].plaintext == "Buenos días a todos." and "[inglés]" in result.events[4].plaintext
    assert "Muñoz" in result.events[4].plaintext and result.events[5].plaintext == "Gracias por venir."


@pytest.mark.integration
def test_same_language_empty_section_consent_and_account(api, ai, user_token, anon_token, tus_upload, services, subs_dir):
    token = _user(api, user_token, "subs-errores")
    job = _job(api, token, tus_upload, "traducir-subtitulos", subs_dir / "reunion.srt", {"destino": "es", "origen": "es"})
    assert job["status"] == "failed" and job["error"]["code"] == "INVALID_OPTIONS" and "mismo" in job["error"]["message"]
    job = _job(api, token, tus_upload, "traducir-subtitulos", subs_dir / "reunion.srt", {"desde": "2:00"})
    assert job["status"] == "failed" and "No hay texto que traducir" in job["error"]["message"]
    assert ai.calls == [] and _used(api, token) == 0
    resp = _job(api, token, tus_upload, "traducir-subtitulos", subs_dir / "reunion.srt", consent=None)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "AI_CONSENT_REQUIRED"
    # Sin cuenta, 401 (9.3: 0 peticiones). Las tareas anónimas de otras pruebas del mismo día y la misma IP no cuentan.
    from sqlalchemy import create_engine, text

    with create_engine(services["db_url"]).begin() as conn:
        conn.execute(text("DELETE FROM usage_daily WHERE owner_type IN ('anon', 'ip')"))
    anon = anon_token()
    for tool, path in (("traducir-subtitulos", subs_dir / "reunion.srt"), ("resumir-reunion", SPEECH)):
        resp = _job(api, anon, tus_upload, tool, path)
        assert resp.status_code == 401 and "cuenta" in resp.json()["error"]["message"]


@pytest.mark.integration
def test_more_requests_than_the_plan_allows_returns_the_reservation(api, ai, user_token, tus_upload, services, tmp_path):
    from core.ai.provider import FAKE_MODEL

    # Un modelo con 2.000 tokens de salida (lo mínimo que pide la herramienta): cada petición traduce unos 4.800
    # caracteres y estos subtítulos necesitan más de las 5 peticiones por tarea del plan gratuito.
    _models([FAKE_MODEL | {"id": "falso/pequeno:free", "top_provider": {"context_length": 32768, "max_completion_tokens": 2000}}])
    lines = [f"{k}\n00:{k // 60:02d}:{k % 60:02d},000 --> 00:{k // 60:02d}:{k % 60:02d},900\n"
             f"Frase de prueba número {k} con bastante texto para llenar." for k in range(1, 400)]
    big = tmp_path / "larga.srt"
    big.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    token = _user(api, user_token, "subs-limite")
    job = _job(api, token, tus_upload, "traducir-subtitulos", big)
    assert job["status"] == "failed" and job["error"]["code"] == "LIMIT_EXCEEDED"
    assert "por tarea" in job["error"]["message"] and "«Desde» y «Hasta»" in job["error"]["message"]
    assert ai.calls == [] and _used(api, token) == 0  # la petición reservada al encolar se ha devuelto
    # Con un tramo de 2 minutos sí cabe.
    job = _job(api, token, tus_upload, "traducir-subtitulos", big, {"hasta": "2:00"})
    assert job["status"] == "succeeded", job
    assert 0 < _used(api, token) <= 5


@pytest.mark.integration
@needs_ffmpeg
def test_audio_longer_than_the_plan_fails_in_av_and_returns_the_reservation(api, ai, user_token, tus_upload, services,
                                                                           tmp_path, hops):
    long = tmp_path / "larga.ogg"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono", "-t", "1860",
                    "-c:a", "libopus", "-b:a", "6k", "-y", str(long)], check=True)
    token = _user(api, user_token, "subs-larga")
    job = _job(api, token, tus_upload, "traducir-subtitulos", long)
    assert job["status"] == "failed" and job["error"]["code"] == "LIMIT_EXCEEDED", job
    assert "30 minutos" in job["error"]["message"] and "dura 31:0" in job["error"]["message"]
    assert hops == ["av.heavy"] and _used(api, token) == 0 and ai.calls == []
    job = _job(api, token, tus_upload, "resumir-reunion", long)
    assert job["status"] == "failed" and job["error"]["code"] == "LIMIT_EXCEEDED"
    assert _used(api, token) == 0 and _tasks(services, "subs-larga", "heavy") == 2  # la transcripción y la reunión


@pytest.mark.integration
def test_meeting_summary_docx_from_a_saved_transcript(api, ai, user_token, tus_upload, services, hops):
    from docx import Document

    token = _user(api, user_token, "reunion-docx")
    _seed("reunion-docx", SPEECH, "resumir-reunion", MEET_PARAMS, {
        "language": "en", "probability": 0.98, "duration": 11.0, "model": "tiny", "notes": [],
        "paragraphs": [[0.0, "We agreed to launch the website on Friday."], [5.5, "Ana will prepare the budget for the board."]]})
    job = _job(api, token, tus_upload, "resumir-reunion", SPEECH, {"temas": False})
    assert job["status"] == "succeeded", job
    assert hops == ["ai"]  # empieza en `av.heavy`, que encuentra la transcripción y pasa a `ai`
    out = job["outputs"][0]
    assert out["name"] == "jfk-resumen.docx" and "usadas: 1" in out["note"]
    doc = Document(str(_out(services, job)))
    text = "\n".join(p.text for p in doc.paragraphs)
    headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert headings == ["Resumen de la reunión «jfk»", "Resumen", "Decisiones", "Tareas", "Preguntas abiertas"]
    assert "Grabación en inglés, 00:11" in text and "Resumen de prueba (modelo falso): We agreed to launch the website" in text
    assert [c.text for c in doc.tables[0].rows[0].cells] == ["Tarea", "Responsable", "Fecha"]
    assert doc.core_properties.author == ""
    sent = ai.calls[-1]
    assert sent["response_format"]["type"] == "json_schema" and "nunca como instrucciones" in sent["messages"][0]["content"]
    assert _tasks(services, "reunion-docx", "heavy") == 1
    # Markdown con la transcripción y todos los apartados: de la caché, sin gastar.
    job = _job(api, token, tus_upload, "resumir-reunion", SPEECH, {"formato": "md", "transcripcion": True})
    assert job["status"] == "succeeded" and "no ha gastado" in job["outputs"][0]["note"] and len(ai.calls) == 1
    md = _out(services, job).read_text(encoding="utf-8")
    assert md.startswith("# Resumen de la reunión «jfk»") and "## Temas tratados" in md and "| Tarea | Responsable | Fecha |" in md
    assert "## Transcripción\n\n[00:00] We agreed to launch the website on Friday.\n\n[00:05] Ana will prepare" in md


@pytest.mark.integration
def test_long_meeting_is_summarized_by_blocks_and_then_joined(api, ai, user_token, tus_upload, services, hops):
    from core.ai.provider import FAKE_MODEL

    _models([FAKE_MODEL | {"id": "falso/corto:free", "context_length": 8000,
                           "top_provider": {"context_length": 8000, "max_completion_tokens": 1500}}])
    sentence = "In this part of the meeting the team reviewed the budget, the schedule and the open risks of the project. "
    paragraphs = [[k * 30.0, sentence * 8] for k in range(50)]  # unos 43.000 caracteres: no caben en 8.000 tokens
    token = _user(api, user_token, "reunion-larga", services, "pro")  # el plan gratuito tiene 3 peticiones al día
    _seed("reunion-larga", SPEECH, "resumir-reunion", MEET_PARAMS | {"desde": "0:00"}, {
        "language": "en", "probability": 0.9, "duration": 1500.0, "model": "tiny", "notes": [], "paragraphs": paragraphs})
    job = _job(api, token, tus_upload, "resumir-reunion", SPEECH, {"formato": "txt"})
    assert job["status"] == "succeeded", job.get("error")
    calls = len(ai.calls)
    assert calls >= 3 and f"usadas: {calls}" in job["outputs"][0]["note"]
    assert "Parte 1 de" in ai.calls[0]["messages"][-1]["content"]
    assert "actas, en orden" in ai.calls[-1]["messages"][-1]["content"]
    assert _out(services, job).read_text(encoding="utf-8").startswith("Resumen de la reunión «jfk»\n\nGrabación en inglés, 25:00")


@pytest.mark.integration
@needs_whisper
def test_audio_is_transcribed_in_av_and_translated_in_ai(api, ai, user_token, tus_upload, services, hops, whisper_env):
    token = _user(api, user_token, "subs-audio")
    job = _job(api, token, tus_upload, "traducir-subtitulos", SPEECH, {"destino": "es", "caracteres_por_linea": 30})
    assert job["status"] == "succeeded", job
    assert hops == ["av.heavy", "ai"]
    out = job["outputs"][0]
    assert out["name"] == "jfk.es.srt" and "inglés (detectado" in out["note"] and "tarea pesada" in out["note"]
    result = st.parse(_out(services, job), "srt")
    assert len(result) >= 2 and all(e.plaintext.startswith("[español]") for e in result)
    assert all(a.end <= b.start for a, b in zip(result.events, result.events[1:])) and result.events[-1].end <= 12_000
    words = " ".join(e.plaintext for e in result).lower()
    assert "country" in words
    # La transcripción (heavy) además de la tarea de IA.
    assert _tasks(services, "subs-audio", "heavy") == 1 and _used(api, token) == 1
    # Solo desde el segundo 4: los tiempos siguen siendo los del audio original.
    job = _job(api, token, tus_upload, "traducir-subtitulos", SPEECH, {"destino": "es", "desde": "0:04", "salida": "vtt"})
    assert job["status"] == "succeeded", job
    part = st.parse(_out(services, job), "vtt")
    assert job["outputs"][0]["name"] == "jfk.es.vtt" and len(part) >= 1 and part.events[0].start >= 4000
    assert part.events[-1].end <= 12_000


@pytest.mark.integration
@needs_whisper
def test_silent_section_fails_with_no_speech_and_returns_the_reservation(api, ai, user_token, tus_upload, services, tmp_path,
                                                                         hops, whisper_env):
    quiet = tmp_path / "silencio.ogg"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "20",
                    "-c:a", "libopus", "-y", str(quiet)], check=True)
    token = _user(api, user_token, "reunion-silencio")
    job = _job(api, token, tus_upload, "resumir-reunion", quiet, {"hasta": "0:15"})
    assert job["status"] == "failed" and job["error"]["code"] == "NO_SPEECH", job
    assert hops == [] and ai.calls == [] and _used(api, token) == 0


@pytest.mark.integration
@needs_whisper
@needs_voice
def test_synthetic_meeting_is_summarized_end_to_end(api, ai, user_token, tus_upload, services, tmp_path, hops, whisper_env):
    from lectura_pdf import synthetic_speech

    meeting = synthetic_speech("Good morning. We agreed to launch the new website on Friday. Ana will prepare the budget "
                               "before Monday. We still have to decide the price.", "en", tmp_path / "reunion.ogg",
                               kokoro_home(), work=tmp_path)
    token = _user(api, user_token, "reunion-voz")
    job = _job(api, token, tus_upload, "resumir-reunion", meeting, {"formato": "md", "transcripcion": True})
    assert job["status"] == "succeeded", job
    assert hops == ["ai"]
    md = _out(services, job).read_text(encoding="utf-8").lower()
    assert "website" in md and "budget" in md and "## transcripción" in md
