"""F3, lote B: generador-de-preguntas, pdf-a-fichas, pdf-a-presentacion y traducir-pdf de extremo a extremo con el
proveedor falso (JSON con esquema), más las piezas sueltas: párrafos, GIFT, lotes de traducción y límites por tarea."""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

import httpx
import pytest
import respx

from helpers import auth
from test_ia import _model, _models, ai  # noqa: F401 - fixture compartida

pytestmark = pytest.mark.integration


def _run(api, user_token, tus_upload, path: Path, user: str, tool: str, options: dict | None = None, plan: str | None = None):
    token = user_token(user_id=user)
    api.get("/v1/me", headers=auth(token))
    uid, _ = tus_upload(token, tool, path)
    job = api.post("/v1/jobs", json={"tool": tool, "upload_ids": [uid], "ai_consent": True, "options": options or {}},
                   headers=auth(token)).json()
    return token, job


def _out(services, job: dict, n: int = 0) -> Path:
    folder = Path(services["files"]) / "jobs" / job["id"] / "out"
    files = sorted(folder.iterdir())
    target = job["outputs"][n]["name"]
    return next(f for f in files if f.name == target or f.name.startswith(Path(target).stem))


def _lecture(tmp_path: Path, pages: int = 4) -> Path:
    from generate import text_pdf

    return text_pdf(tmp_path / "tema.pdf", pages=pages,
                    text="La fotosintesis convierte la luz en energia quimica en los cloroplastos de las plantas verdes.")


# --- generador-de-preguntas ---


def test_question_generator_docx_with_answers_and_moodle_gift(api, ai, user_token, tus_upload, services, tmp_path):
    from docx import Document

    pdf = _lecture(tmp_path)
    token, job = _run(api, user_token, tus_upload, pdf, "ia-preguntas", "generador-de-preguntas", {"numero": 6})
    assert job["status"] == "succeeded", job
    assert job["outputs"][0]["name"] == "tema-preguntas.docx" and "usadas: 1" in job["outputs"][0]["note"]
    doc = Document(str(_out(services, job)))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Preguntas sobre tema" in text and "Soluciones" in text
    assert len(re.findall(r"^\d+\. ", text, re.M)) == 12  # 6 preguntas y 6 soluciones
    assert "a) " in text and "d) " in text  # 4 opciones por pregunta
    sent = ai.calls[-1]
    assert sent["response_format"]["type"] == "json_schema" and "exactamente 6" in sent["messages"][0]["content"]
    # Moodle (GIFT): mismas preguntas desde la caché del propietario, sin gastar.
    uid, _ = tus_upload(token, "generador-de-preguntas", pdf)
    gift = api.post("/v1/jobs", json={"tool": "generador-de-preguntas", "upload_ids": [uid], "ai_consent": True,
                                      "options": {"numero": 6, "formato": "gift"}}, headers=auth(token)).json()
    assert gift["status"] == "succeeded" and "no ha gastado" in gift["outputs"][0]["note"] and len(ai.calls) == 1
    body = _out(services, gift).read_text(encoding="utf-8")
    assert body.count("::P") == 6 and body.count("\n=") == 6 and "~" in body


def test_gift_escapes_special_characters():
    from tools.ai.generador import gift

    q = [{"tipo": "test", "enunciado": "¿Cuánto es 2+2? {ojo: a=b}", "opciones": ["4", "5 ~ 6"], "correcta": 0, "respuesta": "",
          "explicacion": "Suma #básica", "pagina": 1},
         {"tipo": "verdadero_falso", "enunciado": "El agua hierve a 100 ºC", "opciones": [], "correcta": 0, "respuesta": "",
          "explicacion": "", "pagina": None},
         {"tipo": "corta", "enunciado": "Capital de Francia", "opciones": [], "correcta": -1, "respuesta": "París",
          "explicacion": "", "pagina": None}]
    out = gift(q)
    assert "\\{ojo\\: a\\=b\\}" in out and "~5 \\~ 6" in out and "#Suma \\#básica" in out
    assert "::P2:: El agua hierve a 100 ºC {T}" in out and "::P3:: Capital de Francia {=París}" in out


def test_many_questions_on_a_small_model_need_several_requests_and_respect_the_task_limit(api, ai, user_token, tus_upload, services, tmp_path):
    _models([_model("chico/salida-corta:free", 16000, 1600)])  # 5 preguntas por petición como mucho
    pdf = _lecture(tmp_path)
    token, job = _run(api, user_token, tus_upload, pdf, "ia-preguntas-limite", "generador-de-preguntas", {"numero": 30})
    assert job["status"] == "failed" and job["error"]["code"] == "LIMIT_EXCEEDED" and ai.calls == []  # 6 > 5 del plan gratuito
    token, job = _run(api, user_token, tus_upload, pdf, "ia-preguntas-tandas", "generador-de-preguntas", {"numero": 12})
    assert job["status"] == "succeeded", job
    assert len(ai.calls) == 3 and "Ya hay estas preguntas" in ai.calls[-1]["messages"][0]["content"]
    assert all(c["max_tokens"] <= 1600 for c in ai.calls)


# --- pdf-a-fichas ---


def test_flashcards_for_anki_csv_and_printable_word(api, ai, user_token, tus_upload, services, tmp_path):
    from docx import Document

    pdf = _lecture(tmp_path)
    token, job = _run(api, user_token, tus_upload, pdf, "ia-fichas", "pdf-a-fichas", {"numero": 8})
    assert job["status"] == "succeeded", job
    lines = _out(services, job).read_text(encoding="utf-8").splitlines()
    assert job["outputs"][0]["name"] == "tema-fichas.txt" and len(lines) == 8 and all(line.count("\t") == 1 for line in lines)
    uid, _ = tus_upload(token, "pdf-a-fichas", pdf)
    as_csv = api.post("/v1/jobs", json={"tool": "pdf-a-fichas", "upload_ids": [uid], "ai_consent": True,
                                        "options": {"numero": 8, "formato": "csv"}}, headers=auth(token)).json()
    raw = _out(services, as_csv).read_text(encoding="utf-8")
    assert raw.startswith("﻿")
    rows = list(csv.reader(io.StringIO(raw.lstrip("﻿")), delimiter=";"))
    assert rows[0] == ["Anverso", "Reverso", "Página"] and len(rows) == 9 and rows[1][2] == "1"
    uid, _ = tus_upload(token, "pdf-a-fichas", pdf)
    as_docx = api.post("/v1/jobs", json={"tool": "pdf-a-fichas", "upload_ids": [uid], "ai_consent": True,
                                         "options": {"numero": 8, "formato": "docx"}}, headers=auth(token)).json()
    table = Document(str(_out(services, as_docx))).tables[0]
    assert len(table.rows) == 9 and table.rows[0].cells[0].text == "Anverso"
    assert len(ai.calls) == 1  # los tres formatos salen de la misma respuesta guardada


# --- pdf-a-presentacion ---


def test_presentation_two_requests_slides_notes_and_theme(api, ai, user_token, tus_upload, services, tmp_path):
    from pptx import Presentation
    from pptx.util import Inches

    pdf = _lecture(tmp_path, pages=6)
    token, job = _run(api, user_token, tus_upload, pdf, "ia-presentacion", "pdf-a-presentacion",
                      {"diapositivas": 6, "estilo": "oscuro"})
    assert job["status"] == "succeeded", job
    assert len(ai.calls) == 2  # esquema y diapositivas (6.3)
    assert "esquema" in ai.calls[0]["messages"][0]["content"] and "exactamente 5 diapositivas" in ai.calls[1]["messages"][0]["content"]
    prs = Presentation(str(_out(services, job)))
    assert len(prs.slides) == 6 and prs.slide_width == Inches(13.333)
    second = prs.slides[1]
    assert second.has_notes_slide and second.notes_slide.notes_text_frame.text
    assert str(second.background.fill.fore_color.rgb) == "1E2430"
    texts = [sh.text_frame.text for sh in second.shapes if sh.has_text_frame]
    assert any(t.startswith("•  ") for t in texts) and any(t == "2 / 6" for t in texts) and any(t.startswith("Pág.") for t in texts)


# --- traducir-pdf ---


def test_paragraphs_join_lines_hyphens_titles_and_bullets():
    from tools.ai.parrafos import paragraphs

    text = ("1. INTRODUCCIÓN\nEl presente informe recoge los datos del ejercicio y los resul-\ntados obtenidos durante el año pasado en\n"
            "todas las sedes.\nLa segunda idea empieza aquí y sigue en la línea de\nabajo hasta terminar.\n\n"
            "- primer punto de la lista\n- segundo punto\nResumen final")
    out = paragraphs(text)
    assert out[0] == ("t", "1. INTRODUCCIÓN")
    assert out[1] == ("p", "El presente informe recoge los datos del ejercicio y los resultados obtenidos durante el año pasado en todas las sedes.")
    assert out[2][1].startswith("La segunda idea") and out[2][1].endswith("hasta terminar.")
    assert ("p", "- primer punto de la lista") in out and ("p", "- segundo punto Resumen final") in out


def test_translation_batches_fit_the_model_output_and_split_long_paragraphs(ai):
    from core.ai.translate import LLMTranslator, split_long
    from test_ia import _client

    _models([_model("chico/traductor:free", 16000, 1000)])
    client = _client(ai)
    translator = LLMTranslator(client)
    assert translator.out_tokens == 1000 and translator.batch_tokens == 800
    paragraphs = ["Párrafo corto número %d con algunas palabras." % i for i in range(60)] + ["Frase larga. " * 400]
    batches = translator.plan(paragraphs)
    assert len(batches) > 2 and sorted(k for b in batches for k in b) == list(range(len(translator.units(paragraphs))))
    assert len(split_long("Frase larga. " * 400, 2400)) >= 2
    out = translator.translate(paragraphs, "en")
    assert len(out) == 61 and out[0] == "[inglés] Párrafo corto número 0 con algunas palabras."
    assert out[-1].startswith("[inglés] Frase larga.") and len(ai.calls) == len(batches)


@respx.mock
def test_translate_pdf_to_word_and_pdf_with_glossary(api, ai, user_token, tus_upload, services, tmp_path, fixtures_dir):
    from docx import Document

    chromium = respx.post("http://gotenberg.test/forms/chromium/convert/html").mock(
        return_value=httpx.Response(200, content=(fixtures_dir / "texto.pdf").read_bytes()))
    pdf = _lecture(tmp_path, pages=3)
    token, job = _run(api, user_token, tus_upload, pdf, "ia-traducir", "traducir-pdf",
                      {"destino": "en", "glosario": "cloroplastos\nFotosintesis"})
    assert job["status"] == "succeeded", job
    names = [o["name"] for o in job["outputs"]]
    assert names == ["tema-traducido-en.docx", "tema-traducido-en.pdf"]
    doc = Document(str(_out(services, job, 0)))
    text = [p.text for p in doc.paragraphs]
    assert text[0] == "tema (traducción al inglés)" and "Página 2 del original" in text
    assert sum(t.startswith("[inglés] La fotosintesis convierte") for t in text) == 3
    system = ai.calls[-1]["messages"][0]["content"]
    assert "No traduzcas estos términos" in system and "cloroplastos; Fotosintesis" in system
    page = chromium.calls.last.request.content.decode("utf-8", "replace")
    assert 'lang="en-GB"' in page and page.count('class="pagina"') == 3 and "[inglés] La fotosintesis" in page
    token2 = user_token(user_id="ia-traducir-igual")
    api.get("/v1/me", headers=auth(token2))
    uid, _ = tus_upload(token2, "traducir-pdf", pdf)
    same = api.post("/v1/jobs", json={"tool": "traducir-pdf", "upload_ids": [uid], "ai_consent": True,
                                      "options": {"destino": "es", "origen": "es", "formato": "docx"}}, headers=auth(token2)).json()
    assert same["status"] == "failed" and "mismo" in same["error"]["message"]


def test_translated_html_escapes_the_model_output():
    from tools.ai.traducir import TEXTS, html_of

    page = html_of("Título <b>", [(1, [("t", "<script>alert(1)</script>"), ("p", "a & b")])], "es-ES", TEXTS["es"], "nota")
    assert "<script>" not in page and "&lt;script&gt;" in page and "a &amp; b" in page and "Título &lt;b&gt;" in page
