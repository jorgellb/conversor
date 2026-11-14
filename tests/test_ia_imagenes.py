"""F3, lote C: imagen-a-excel y ticket-a-excel de extremo a extremo (API, colas encadenadas y proveedor falso) y las
pruebas de 16.3 que les tocan: consentimiento, cuenta, AI_UNAVAILABLE, reservas devueltas, límite por tarea y caché.

La etapa de Docling de imagen-a-excel se sustituye aquí por su resultado (con tabla o sin ella): Docling real se prueba
en tests/test_imagen_excel_docling.py, en el job `docling` de la CI. El OCR de los tickets usa Tesseract real.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from helpers import auth
from test_ia import _model, _models, _set_plan, ai  # noqa: F401 - fixture compartida
from test_tools import make_ctx  # noqa: F401 - fixture compartida

pytestmark = [pytest.mark.integration, pytest.mark.needs_tesseract,
              pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no instalado")]
TABLE = {"titulo": "", "header": ["Producto", "Unidades", "Precio"], "rows": [["Manzanas", "12", "3,50"], ["Peras", "7", "2,10"]]}


@pytest.fixture()
def hops(monkeypatch):
    """Las etapas encadenadas (convert u ocr → ai) se ejecutan en el momento, apuntando la cola de cada una."""
    from tools import tasks

    seen: list[str] = []

    def send_task(name, args=None, queue=None, **kw):
        seen.append(queue)
        return tasks.execute(*args)

    monkeypatch.setattr(tasks.celery_app, "send_task", send_task)
    return seen


def _job(api, token, tus_upload, tool: str, paths: list[Path], options: dict | None = None, consent: bool | None = True):
    uids = [tus_upload(token, tool, p)[0] for p in paths]
    body = {"tool": tool, "upload_ids": uids, "options": options or {}}
    if consent is not None:
        body["ai_consent"] = consent
    resp = api.post("/v1/jobs", json=body, headers=auth(token))
    if resp.status_code != 201:
        return resp
    return api.get(f"/v1/jobs/{resp.json()['id']}", headers=auth(token)).json()


def _user(api, user_token, uid: str, plan: str | None = None, services=None) -> str:
    token = user_token(user_id=uid)
    api.get("/v1/me", headers=auth(token))
    if plan:
        _set_plan(services, uid, plan)
    return token


def _out(services, job: dict, n: int = 0) -> Path:
    folder = Path(services["files"]) / "jobs" / job["id"] / "out"
    target = job["outputs"][n]["name"]
    return next(f for f in sorted(folder.iterdir()) if f.name == target or f.name.startswith(Path(target).stem))


def _sheets(path: Path) -> dict[str, list[list]]:
    from openpyxl import load_workbook

    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in load_workbook(path).worksheets}


def _used(api, token) -> int:
    return api.get("/v1/ai/budget", headers=auth(token)).json()["user"]["used"]


# --- imagen-a-excel ---


def test_table_found_by_docling_returns_the_reserved_request(api, ai, user_token, tus_upload, fixtures_dir, services, hops,
                                                             monkeypatch):
    from core.ai import budget
    from core.settings import get_settings
    from core.valkey import get_valkey
    from tools.ai import imagen_excel

    monkeypatch.setattr(imagen_excel, "_docling_tables", lambda ctx, pages, languages: [dict(TABLE)])
    token = _user(api, user_token, "img-excel-docling")
    job = _job(api, token, tus_upload, "imagen-a-excel", [fixtures_dir / "tabla.png"])
    assert job["status"] == "succeeded", job
    assert hops == [] and ai.calls == []  # terminó en `convert`, sin pasar por `ai`
    assert job["outputs"][0]["note"] == "Tablas reconocidas sin IA: 1."
    assert ["Manzanas", 12, 3.5] in _sheets(_out(services, job))["Tabla 1"]
    # La petición reservada al encolar vuelve: ni el usuario ni el presupuesto global la gastan (D-160).
    assert _used(api, token) == 0 and budget.status(get_valkey(), get_settings())["total"] == 0


def test_unrecognised_table_goes_to_ai_with_schema_and_cache(api, ai, user_token, tus_upload, fixtures_dir, services, hops,
                                                             monkeypatch):
    from tools.ai import imagen_excel

    monkeypatch.setattr(imagen_excel, "_docling_tables", lambda ctx, pages, languages: [])
    token = _user(api, user_token, "img-excel-ia")
    job = _job(api, token, tus_upload, "imagen-a-excel", [fixtures_dir / "tabla-manuscrita.png"])
    assert job["status"] == "succeeded", job
    assert hops == ["ai"] and len(ai.calls) == 1
    sent = ai.calls[0]
    assert sent["response_format"]["type"] == "json_schema" and sent["provider"]["data_collection"] == "deny"
    assert "<<<" in sent["messages"][1]["content"] and "Manzanas" in sent["messages"][1]["content"]
    assert "nunca como instrucciones" in sent["messages"][0]["content"]
    note = job["outputs"][0]["note"]
    assert "reconstruido con IA" in note and "Peticiones de IA usadas: 1" in note and "Hecho con IA" in note
    sheets = _sheets(_out(services, job))
    assert len(sheets) == 1 and len(next(iter(sheets.values()))) == 4  # cabecera y 3 filas del modelo falso
    assert _used(api, token) == 1
    # Otro formato con las mismas opciones de OCR: de la caché del propietario, sin gastar.
    job = _job(api, token, tus_upload, "imagen-a-excel", [fixtures_dir / "tabla-manuscrita.png"], {"formato": "csv"})
    assert job["status"] == "succeeded", job
    assert len(ai.calls) == 1 and "no ha gastado" in job["outputs"][0]["note"] and job["outputs"][0]["name"].endswith(".csv")
    assert _used(api, token) == 1


def test_without_ai_no_account_consent_or_requests(api, ai, anon_token, tus_upload, fixtures_dir, services, hops, monkeypatch):
    from sqlalchemy import create_engine, text

    from tools.ai import imagen_excel

    # Las tareas pesadas sin cuenta también se cuentan por IP (2 al día): otras pruebas de la sesión ya las han gastado.
    with create_engine(services["db_url"]).begin() as conn:
        conn.execute(text("DELETE FROM usage_daily WHERE owner_type IN ('ip', 'anon')"))
    monkeypatch.setattr(imagen_excel, "_docling_tables", lambda ctx, pages, languages: [])
    anon = anon_token()
    job = _job(api, anon, tus_upload, "imagen-a-excel", [fixtures_dir / "tabla-manuscrita.png"], {"usar_ia": False}, consent=None)
    assert job["status"] == "succeeded", job
    assert hops == [] and ai.calls == [] and "No se ha encontrado ninguna tabla" in job["outputs"][0]["note"]
    # Con la IA encendida (el valor por defecto), una cuenta y el consentimiento.
    resp = _job(api, anon, tus_upload, "imagen-a-excel", [fixtures_dir / "tabla-manuscrita.png"])
    assert resp.status_code == 401


def _heavy_tasks(services, uid: str) -> int | None:
    from sqlalchemy import create_engine, text

    with create_engine(services["db_url"]).begin() as conn:
        return conn.execute(text("SELECT tasks FROM usage_daily WHERE owner_id = :u AND cost_class = 'heavy'"), {"u": uid}).scalar()


def test_with_ai_on_it_still_counts_as_a_heavy_task(api, ai, user_token, tus_upload, fixtures_dir, services, hops, monkeypatch):
    """9.3: Docling y Tesseract corren siempre en `workerconvert`, así que la tarea es pesada aunque «usar IA» esté
    encendida y Docling devuelva la petición reservada; agotadas las pesadas del día, no se encola nada (D-161)."""
    from sqlalchemy import create_engine, text

    from core.plans import load_plans_file
    from core.quotas import today
    from core.settings import get_settings
    from tools.ai import imagen_excel

    monkeypatch.setattr(imagen_excel, "_docling_tables", lambda ctx, pages, languages: [dict(TABLE)])
    uid = "img-excel-pesada"
    token = _user(api, user_token, uid)
    job = _job(api, token, tus_upload, "imagen-a-excel", [fixtures_dir / "tabla.png"])
    assert job["status"] == "succeeded", job
    assert _heavy_tasks(services, uid) == 1 and _used(api, token) == 0
    uploaded, _ = tus_upload(token, "imagen-a-excel", fixtures_dir / "tabla.png")
    limit = load_plans_file(get_settings().PLANS_FILE)["free"].heavy_tasks_day
    with create_engine(services["db_url"]).begin() as conn:
        conn.execute(text("UPDATE usage_daily SET tasks = :n WHERE owner_id = :u AND cost_class = 'heavy' AND date = :d"),
                     {"n": limit, "u": uid, "d": today()})
    # Subido antes de agotarlas: lo para POST /v1/jobs. Después, ya la subida (pre-create de tusd).
    resp = api.post("/v1/jobs", json={"tool": "imagen-a-excel", "upload_ids": [uploaded], "options": {"formato": "csv"},
                                      "ai_consent": True},
                    headers=auth(token))
    assert resp.status_code == 429 and resp.json()["error"]["code"] == "QUOTA_EXCEEDED", resp.json()
    assert _used(api, token) == 0  # ni se ha reservado la petición
    upload_id, hook = tus_upload(token, "imagen-a-excel", fixtures_dir / "tabla.png")
    assert upload_id is None and hook["RejectUpload"] and hook["HTTPResponse"]["StatusCode"] == 429
    from core.registry import load_registry

    spec = load_registry().require("imagen-a-excel")
    assert spec.cost_class == "ai" and spec.to_public()["task_class"] == "heavy"


def test_ocr_languages_change_the_text_sent_to_the_model(api, ai, user_token, tus_upload, fixtures_dir, services, hops,
                                                         monkeypatch):
    """«Idiomas del OCR» (avanzada) cambia el texto que lee Tesseract y que recibe el modelo; la caché va por idiomas,
    así que cada combinación es una petición. Un idioma que `workerconvert` no tiene se rechaza antes de encolar."""
    from tools.ai import imagen_excel

    monkeypatch.setattr(imagen_excel, "_docling_tables", lambda ctx, pages, languages: [])
    token = _user(api, user_token, "img-excel-idiomas")
    sample = fixtures_dir / "ocr-documento.jpg"
    for languages in (["spa"], ["eng"]):
        job = _job(api, token, tus_upload, "imagen-a-excel", [sample], {"idiomas": languages})
        assert job["status"] == "succeeded", job
    assert len(ai.calls) == 2 and _used(api, token) == 2
    spanish, english = (c["messages"][1]["content"] for c in ai.calls)
    assert "Logroño" in spanish and "Logroño" not in english and spanish != english
    resp = _job(api, token, tus_upload, "imagen-a-excel", [sample], {"idiomas": ["jpn"]})
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "INVALID_OPTIONS"
    assert len(ai.calls) == 2 and _used(api, token) == 2


def test_consent_and_unavailable_models(api, ai, user_token, tus_upload, fixtures_dir):
    token = _user(api, user_token, "img-excel-consentimiento")
    resp = _job(api, token, tus_upload, "imagen-a-excel", [fixtures_dir / "tabla.png"], consent=None)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "AI_CONSENT_REQUIRED"
    resp = _job(api, token, tus_upload, "ticket-a-excel", [fixtures_dir / "ticket.png"], consent=None)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "AI_CONSENT_REQUIRED"
    _models([_model("pequeno/modelo:free", 4096, 512)])  # no llega a lo que piden
    for tool, sample in (("imagen-a-excel", "tabla.png"), ("ticket-a-excel", "ticket.png")):
        resp = _job(api, token, tus_upload, tool, [fixtures_dir / sample])
        assert resp.status_code == 503 and resp.json()["error"]["code"] == "AI_UNAVAILABLE"
    state = api.get("/v1/ai/budget", headers=auth(token)).json()
    assert state["tools"]["imagen-a-excel"] is False and state["tools"]["ticket-a-excel"] is False
    assert ai.calls == [] and state["user"]["used"] == 0


# --- ticket-a-excel ---


class TicketProvider:
    """Como el proveedor falso, pero responde con los datos de los tickets de las muestras según el texto del OCR."""

    def __init__(self, fake, wrong_total: bool = False):
        self.fake, self.wrong_total, self.calls = fake, wrong_total, fake.calls

    def chat(self, *, models, messages, max_tokens, json_schema=None, temperature=0.2):
        from core.ai.provider import LLMResult, request_body

        self.calls.append(request_body(models, messages, max_tokens, json_schema, temperature))
        text = messages[-1]["content"]
        if "FRUTERIA" in text:
            data = {"es_ticket": True, "comercio": "FRUTERIA LA HUERTA S.L.", "nif": "B12345678", "fecha": "2026-11-14",
                    "hora": "10:32", "moneda": "EUR", "forma_pago": "Tarjeta",
                    "lineas": [{"concepto": "Pan de barra", "cantidad": 1, "importe": 1.2},
                               {"concepto": "Leche entera 1L", "cantidad": 2, "importe": 2.3},
                               {"concepto": "Manzanas 1kg", "cantidad": 1, "importe": 2.49}],
                    "impuestos": [{"tipo": 4, "base": 3.37, "cuota": 0.13}, {"tipo": 10, "base": 2.26, "cuota": 0.23}],
                    "total": 6.99 if self.wrong_total else 5.99}
        elif "CORNER" in text:
            data = {"es_ticket": True, "comercio": "CORNER BAKERY LTD", "nif": "GB123456789", "fecha": "2026-11-14",
                    "hora": "08:15", "moneda": "GBP", "forma_pago": "Cash",
                    "lineas": [{"concepto": "Coffee latte", "cantidad": 1, "importe": 3.2},
                               {"concepto": "Croissant", "cantidad": 2, "importe": 4.4}],
                    "impuestos": [{"tipo": 20, "base": 6.33, "cuota": 1.27}], "total": 7.6}
        else:
            data = {"es_ticket": False, "comercio": "", "nif": "", "fecha": "", "hora": "", "moneda": "", "forma_pago": "",
                    "lineas": [], "impuestos": [], "total": None}
        return LLMResult(json.dumps(data), models[0], 100, 100)

    def list_models(self):
        return self.fake.list_models()


def test_receipts_batch_one_request_each_and_totals_checked(api, ai, user_token, tus_upload, fixtures_dir, services, hops):
    from core.ai.provider import set_provider

    set_provider(TicketProvider(ai))
    token = _user(api, user_token, "tickets-lote")
    files = [fixtures_dir / "ticket.png", fixtures_dir / "ticket-en.png", fixtures_dir / "ocr-sin-texto.png"]
    job = _job(api, token, tus_upload, "ticket-a-excel", files)
    assert job["status"] == "succeeded", job
    assert hops == ["ai"]  # empezó en `ocr` (Tesseract) y siguió en `ai`
    # 6.3: una petición por ticket con texto; la imagen sin texto no gasta, y se devuelve lo reservado de más.
    assert len(ai.calls) == 2 and _used(api, token) == 2
    assert all(c["response_format"]["type"] == "json_schema" for c in ai.calls)
    assert "FRUTERIA" in ai.calls[0]["messages"][1]["content"] and "5,99" in ai.calls[0]["messages"][1]["content"]
    out = job["outputs"][0]
    assert out["name"] == "tickets.xlsx" and "usadas: 2" in out["note"] and "ocr-sin-texto.png" in out["note"]
    sheets = _sheets(_out(services, job))
    tickets, items = sheets["Tickets"], sheets["Conceptos"]
    assert tickets[0][:3] == ["Archivo", "Comercio", "NIF"] and tickets[0][-1] == "Cuadra"
    assert "Base 20 %" in tickets[0] and "IVA 4 %" in tickets[0]
    first = dict(zip(tickets[0], tickets[1]))
    assert first["Comercio"] == "FRUTERIA LA HUERTA S.L." and first["Total"] == 5.99 and first["Suma de conceptos"] == 5.99
    assert first["Fecha"].date().isoformat() == "2026-11-14" and first["Cuadra"] == "Sí" and first["IVA 10 %"] == 0.23
    assert dict(zip(tickets[0], tickets[2]))["Moneda"] == "GBP" and len(items) == 1 + 3 + 2


def test_receipt_that_does_not_add_up_csv_per_item_and_cache(api, ai, user_token, tus_upload, fixtures_dir, services, hops):
    from core.ai.provider import set_provider

    set_provider(TicketProvider(ai, wrong_total=True))
    token = _user(api, user_token, "tickets-no-cuadra")
    options = {"formato": "csv", "filas": "concepto", "delimitador": "punto_y_coma"}
    job = _job(api, token, tus_upload, "ticket-a-excel", [fixtures_dir / "ticket-torcido.jpg"], options)
    assert job["status"] == "succeeded", job
    out = job["outputs"][0]
    assert out["name"] == "ticket-torcido.csv" and "No cuadran (revisa el ticket): ticket-torcido.jpg." in out["note"]
    body = _out(services, job).read_bytes().decode("utf-8")
    assert body.startswith("﻿") and "Archivo;Comercio;Fecha;Concepto;Cantidad;Importe" in body
    assert "ticket-torcido.jpg;FRUTERIA LA HUERTA S.L.;2026-11-14;Leche entera 1L;2;2,30" in body
    # Una fila por ticket, del mismo resultado guardado: sin peticiones nuevas.
    job = _job(api, token, tus_upload, "ticket-a-excel", [fixtures_dir / "ticket-torcido.jpg"], {"formato": "csv"})
    assert job["status"] == "succeeded" and len(ai.calls) == 1 and "no ha gastado" in job["outputs"][0]["note"]
    lines = _out(services, job).read_bytes().decode("utf-8").splitlines()
    assert len(lines) == 2 and lines[1].endswith(";No")


def test_receipt_language_picks_tesseract_languages_and_csv_delimiter(api, ai, user_token, tus_upload, fixtures_dir, services,
                                                                    hops, monkeypatch):
    """«Idioma de los tickets» elige los idiomas de Tesseract (es → spa, en → eng) y forma parte de la clave de la
    caché: cada idioma es una petición. El separador del CSV cambia los bytes (tabulador y coma)."""
    from core.ai.provider import set_provider
    from tools.ocr import imagen

    seen: list[str] = []
    engine = imagen.run_engine

    def spy(args, **kw):
        if "-l" in args:
            seen.append(args[args.index("-l") + 1])
        return engine(args, **kw)

    monkeypatch.setattr(imagen, "run_engine", spy)
    set_provider(TicketProvider(ai))
    token = _user(api, user_token, "tickets-idioma")
    sample = [fixtures_dir / "ticket-acentos.png"]
    job = _job(api, token, tus_upload, "ticket-a-excel", sample, {"idioma_ticket": "es", "formato": "csv", "delimitador": "tabulador"})
    assert job["status"] == "succeeded", job
    body = _out(services, job).read_bytes().decode("utf-8")
    assert "Archivo\tComercio\tNIF\tFecha" in body and "\t5,99\t" in body and ";" not in body
    job = _job(api, token, tus_upload, "ticket-a-excel", sample, {"idioma_ticket": "en"})
    assert job["status"] == "succeeded", job
    assert seen == ["spa", "eng"] and len(ai.calls) == 2 and _used(api, token) == 2
    spanish, english = (c["messages"][1]["content"] for c in ai.calls)
    assert "PIÑA" in spanish and "JAMÓN" in spanish and "PIÑA" not in english and spanish != english
    # Mismo idioma, otro separador: de la caché, sin OCR ni peticiones nuevas.
    job = _job(api, token, tus_upload, "ticket-a-excel", sample, {"idioma_ticket": "es", "formato": "csv", "delimitador": "coma"})
    assert job["status"] == "succeeded" and len(ai.calls) == 2 and seen == ["spa", "eng"]
    lines = _out(services, job).read_bytes().decode("utf-8").splitlines()
    assert lines[0].startswith("\ufeffArchivo,Comercio,NIF,Fecha") and lines[1].count('"') >= 2  # «5,99» va entre comillas


def test_receipt_language_mapping():
    from core.registry import load_registry
    from tools.ai import ticket
    from tools.ai.specs import TicketOptions

    class Ctx:
        def __init__(self, value):
            self.options = TicketOptions(idioma_ticket=value)

    expected = {"auto": ["spa", "eng"], "es": ["spa"], "en": ["eng"], "fr": ["fra"], "de": ["deu"], "it": ["ita"],
                "pt": ["por"], "ca": ["cat"]}
    schema = load_registry().require("ticket-a-excel").options.model_json_schema()["properties"]["idioma_ticket"]
    assert set(schema["enum"]) == set(expected)
    assert {value: ticket.languages(Ctx(value)) for value in expected} == expected


def test_not_a_receipt_fails_clearly(api, ai, user_token, tus_upload, fixtures_dir, hops):
    from core.ai.provider import set_provider

    set_provider(TicketProvider(ai))
    token = _user(api, user_token, "tickets-no-es")
    job = _job(api, token, tus_upload, "ticket-a-excel", [fixtures_dir / "ocr-documento.jpg"])
    assert job["status"] == "failed" and "no parece un ticket" in job["error"]["message"]
    assert len(ai.calls) == 1


def test_too_many_receipts_for_the_plan_is_said_before_queueing(api, ai, user_token, tus_upload, fixtures_dir, tmp_path):
    token = _user(api, user_token, "tickets-muchos")
    files = []
    for i in range(6):  # el plan gratuito permite 5 peticiones por tarea
        dst = tmp_path / f"ticket-{i}.png"
        shutil.copyfile(fixtures_dir / "ticket.png", dst)
        files.append(dst)
    resp = _job(api, token, tus_upload, "ticket-a-excel", files)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "LIMIT_EXCEEDED"
    assert "una por archivo" in resp.json()["error"]["message"] and ai.calls == []


def test_receipt_pixel_bomb_fails_in_ocr_stage(make_ctx, fixtures_dir, services):
    from core.errors import ErrorCode, ToolError
    from tools.ai import ticket

    ctx = make_ctx("ticket-a-excel", [fixtures_dir / "gigante.png"])
    with pytest.raises(ToolError) as err:
        ticket.run(ctx)
    assert err.value.code == ErrorCode.LIMIT_EXCEEDED


def test_clean_and_adds_up_rules():
    from tools.ai import imagen_excel, ticket

    data = {"es_ticket": True, "comercio": "  Bar   Pepe ", "nif": "B1", "fecha": "14/11/2026", "hora": "9:05", "moneda": "eur",
            "forma_pago": "", "lineas": [{"concepto": "Café", "cantidad": 2, "importe": 2.4},
                                        {"concepto": "", "cantidad": None, "importe": 1}],
            "impuestos": [{"tipo": 10, "base": 2.18, "cuota": 0.22}], "total": 2.4}
    clean = ticket.clean(data)
    assert clean["comercio"] == "Bar Pepe" and clean["fecha"] == "2026-11-14" and clean["moneda"] == "EUR"
    assert len(clean["lineas"]) == 1 and ticket.adds_up(clean) is True
    assert ticket.adds_up({**clean, "total": 3.0}) is False and ticket.adds_up({**clean, "lineas": []}) is None
    with pytest.raises(ValueError):  # la mitad de los conceptos no sirven: se pide reparación
        ticket.clean({**data, "lineas": [{"concepto": "", "importe": None}, {"concepto": "x", "importe": "uno"}]})
    assert ticket.clean({"es_ticket": False}) == {"es_ticket": False}
    tables = imagen_excel.clean({"tablas": [{"titulo": "T", "columnas": ["a", "b"], "filas": [["1"], ["2", "3", "4"], []]}]})
    assert tables == [{"titulo": "T", "header": ["a", "b", ""], "rows": [["1", "", ""], ["2", "3", "4"]]}]
    assert imagen_excel.clean({"tablas": []}) == []
    with pytest.raises(ValueError):
        imagen_excel.clean({"tablas": [{"titulo": "", "columnas": [], "filas": [["solo"]]}]})
