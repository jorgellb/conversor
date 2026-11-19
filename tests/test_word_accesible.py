"""F4, lote F: word-a-pdf-accesible (7.5) y el rango de páginas de PDF/A y PDF/UA en la ruta de LibreOffice (D-182).

Gotenberg se simula con respx (devuelve un PDF etiquetado de muestra; el PDF/UA real de LibreOffice solo sale en la CI,
donde hay Writer) y veraPDF con el informe MRR de `test_desde_pdf.mrr` (veraPDF real necesita Java: job de la CI).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pikepdf
import pytest
import respx
from httpx import Response

from core.settings import get_settings
from helpers import auth
from test_desde_pdf import fake_verapdf, mrr  # noqa: F401 - fixture compartida
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida

TOOL = "word-a-pdf-accesible"
CONVERT = "/forms/libreoffice/convert"
ALT_RULE = {"spec": "ISO 14289-1:2014", "clause": "7.3", "failed": 1, "object": "SEFigure", "pages": [0],
            "description": "Figure tags shall include an alternative representation or replacement text",
            "message": "Figure structure element neither has an alternate description nor a replacement text"}
TITLE_RULE = {"spec": "ISO 14289-1:2014", "clause": "7.1", "failed": 1, "object": "CosDocument", "tags": "metadata",
              "description": "The document catalog dictionary shall include a ViewerPreferences dictionary containing a "
                             "DisplayDocTitle key, whose value shall be true"}


def _url(path: str) -> str:
    return f"{get_settings().GOTENBERG_URL.rstrip('/')}{path}"


def _fields(request) -> dict[str, str]:
    """Campos del multipart que recibe Gotenberg (partes sin nombre de archivo)."""
    body = request.content.decode("latin-1")
    out = {}
    for part in body.split("Content-Disposition: form-data; ")[1:]:
        head, _, value = part.partition("\r\n\r\n")
        if "filename=" in head.split("\r\n")[0]:
            continue
        name = head.split('name="', 1)[1].split('"', 1)[0]
        out[name] = value.rsplit("\r\n--", 1)[0]
    return out


def _office_stage(make_ctx, files: list[Path], options: dict | None = None, secrets: dict | None = None):
    from tools.base import Handoff

    ctx = make_ctx(TOOL, files, options, secrets)
    with pytest.raises(Handoff) as step:
        run(TOOL, ctx)
    return ctx, step.value


def _stage_pdf(ctx, n: int = 0) -> Path:
    return ctx.store.job_dir(ctx.job_id) / "stage" / f"{n}.pdf"


def test_spec_fixes_pdfua_and_keeps_only_word_options():
    from core.registry import load_registry

    spec = load_registry().require(TOOL)
    assert spec.slug_en == "accessible-word-to-pdf" and spec.worker_group == "office" and spec.phase == "F4"
    assert set(spec.inputs) == {"doc", "docx", "odt", "rtf"} and spec.outputs == ("pdf", "html", "zip")
    fields = spec.options.model_fields
    assert "formato" not in fields and "hoja_una_pagina" not in fields and "diapositivas_ocultas" not in fields
    defaults = spec.options().model_dump()
    assert defaults["paginas"] == "todas" and defaults["marcadores"] and defaults["campos_formulario"]
    assert defaults["calidad_imagenes"] == 90 and defaults["resolucion_maxima"] == 300 and defaults["idioma"] == "documento"
    assert spec.secret_fields == ("contrasena",)


@respx.mock
def test_office_stage_sends_pdfua_and_hands_off_to_verapdf_without_secrets(make_ctx, fixtures_dir):
    route = respx.post(_url(CONVERT)).mock(return_value=Response(200, content=(fixtures_dir / "etiquetado.pdf").read_bytes()))
    ctx, step = _office_stage(make_ctx, [fixtures_dir / "accesible.docx"], {"comentarios_margen": True, "calidad_imagenes": 70},
                              {"contrasena": "abre"})
    fields = _fields(route.calls.last.request)
    assert fields["pdfua"] == "true" and fields["generateTaggedPdf"] == "true" and "pdfa" not in fields
    assert fields["exportNotesInMargin"] == "true" and fields["quality"] == "70" and fields["password"] == "abre"
    assert fields["singlePageSheets"] == "false" and fields["exportNotesPages"] == "false"
    assert "nativePageRanges" not in fields and route.call_count == 1
    # Sigue en `ocr` (veraPDF solo está en worker-ocr) y la contraseña no viaja a una cola sin JOB_SECRETS_KEY.
    assert (step.group, step.queue, step.stage, step.keep_secrets) == ("ocr", "ocr", "verapdf", False)
    assert step.message == "Comprobando la accesibilidad con veraPDF…"
    assert _stage_pdf(ctx).exists() and not any(ctx.out.iterdir())


@respx.mock
def test_metadata_fixes_title_display_title_pdfuaid_and_language(make_ctx, fixtures_dir):
    respx.post(_url(CONVERT)).mock(return_value=Response(200, content=(fixtures_dir / "etiquetado.pdf").read_bytes()))
    ctx, _ = _office_stage(make_ctx, [fixtures_dir / "sin-alternativo.docx"])
    with pikepdf.open(_stage_pdf(ctx)) as pdf, pdf.open_metadata() as meta:
        assert str(meta["dc:title"]) == "sin-alternativo"  # sin título: el nombre del archivo
        assert str(meta["{http://www.aiim.org/pdfua/ns/id/}part"]) == "1"
        assert bool(pdf.Root.ViewerPreferences.DisplayDocTitle) is True
        assert "/Lang" not in pdf.Root and "/StructTreeRoot" in pdf.Root
    notes = json.loads((_stage_pdf(ctx).parent / "accesible.json").read_text())[0]["notes"]
    assert [k for k, _ in notes] == ["title_name", "lang_missing"]

    ctx, _ = _office_stage(make_ctx, [fixtures_dir / "sin-alternativo.docx"], {"titulo": "Memoria 2026", "idioma": "ca-ES"})
    with pikepdf.open(_stage_pdf(ctx)) as pdf, pdf.open_metadata() as meta:
        assert str(meta["dc:title"]) == "Memoria 2026" and str(pdf.Root.Lang) == "ca-ES"


@respx.mock
def test_title_option_does_not_replace_the_document_title(make_ctx, fixtures_dir, tmp_path):
    titled = tmp_path / "con-titulo.pdf"
    with pikepdf.open(fixtures_dir / "etiquetado.pdf") as pdf:
        with pdf.open_metadata() as meta:
            meta["dc:title"] = "Título de Word"
        pdf.Root.Lang = pikepdf.String("es-ES")
        pdf.save(titled)
    respx.post(_url(CONVERT)).mock(return_value=Response(200, content=titled.read_bytes()))
    ctx, _ = _office_stage(make_ctx, [fixtures_dir / "accesible.docx"], {"titulo": "Otro"})
    with pikepdf.open(_stage_pdf(ctx)) as pdf, pdf.open_metadata() as meta:
        assert str(meta["dc:title"]) == "Título de Word" and str(pdf.Root.Lang) == "es-ES"
    assert json.loads((_stage_pdf(ctx).parent / "accesible.json").read_text())[0]["notes"] == []


@respx.mock
def test_page_range_is_applied_by_libreoffice_so_tags_survive(make_ctx, fixtures_dir):
    """Copiar páginas a un PDF nuevo pierde el árbol de estructura: con un rango se pide otra vez a LibreOffice."""
    full = (fixtures_dir / "texto.pdf").read_bytes()  # 3 páginas
    tagged = (fixtures_dir / "etiquetado.pdf").read_bytes()
    route = respx.post(_url(CONVERT)).mock(side_effect=[Response(200, content=full), Response(200, content=tagged)])
    ctx, _ = _office_stage(make_ctx, [fixtures_dir / "accesible.docx"], {"paginas": "impares"})
    assert route.call_count == 2
    assert "nativePageRanges" not in _fields(route.calls[0].request)
    assert _fields(route.calls[1].request)["nativePageRanges"] == "1,3"
    with pikepdf.open(_stage_pdf(ctx)) as pdf:
        assert "/StructTreeRoot" in pdf.Root


@respx.mock
def test_bad_range_and_page_limit(make_ctx, fixtures_dir):
    from core.errors import ToolError

    respx.post(_url(CONVERT)).mock(return_value=Response(200, content=(fixtures_dir / "texto.pdf").read_bytes()))
    with pytest.raises(ToolError) as err:
        run(TOOL, make_ctx(TOOL, [fixtures_dir / "accesible.docx"], {"paginas": "9-2"}))
    assert err.value.code == "INVALID_OPTIONS"
    ctx = make_ctx(TOOL, [fixtures_dir / "accesible.docx"], plan="anon")
    ctx.plan.pdf_pages = 2
    with pytest.raises(ToolError) as err:
        run(TOOL, ctx)
    assert err.value.code == "LIMIT_EXCEEDED"


def test_native_range_syntax():
    from tools.office.office_a_pdf import native_range

    assert native_range("todas", 5) is None and native_range("1-5", 5) is None
    assert native_range("2-", 5) == "2-5" and native_range("pares", 6) == "2,4,6"
    assert native_range("5, 1-2, 3", 9) == "1-3,5"


@respx.mock
def test_word_a_pdf_pdfua_and_pdfa_with_range_keep_structure(make_ctx, fixtures_dir):
    """Mismo fallo en word-a-pdf: con PDF/A o PDF/UA y un rango, `select_pages` perdía etiquetas y metadatos."""
    full = (fixtures_dir / "texto.pdf").read_bytes()
    tagged = (fixtures_dir / "etiquetado.pdf").read_bytes()
    for formato in ("pdfua", "pdfa"):
        route = respx.post(_url(CONVERT)).mock(side_effect=[Response(200, content=full), Response(200, content=tagged)])
        before = route.call_count
        out = run("word-a-pdf", make_ctx("word-a-pdf", [fixtures_dir / "accesible.docx"], {"formato": formato, "paginas": "2-"}))
        assert route.call_count - before == 2
        assert _fields(route.calls.last.request)["nativePageRanges"] == "2-3"
        with pikepdf.open(out[0]["path"]) as pdf:
            assert "/StructTreeRoot" in pdf.Root
    # PDF normal: una sola conversión y el rango con pikepdf, como antes.
    route = respx.post(_url(CONVERT)).mock(return_value=Response(200, content=full))
    before = route.call_count
    out = run("word-a-pdf", make_ctx("word-a-pdf", [fixtures_dir / "accesible.docx"], {"paginas": "2-"}))
    assert route.call_count - before == 1
    with pikepdf.open(out[0]["path"]) as pdf:
        assert len(pdf.pages) == 2


@respx.mock
def test_verapdf_stage_reports_pdfua_failures_with_word_fixes(make_ctx, fixtures_dir, fake_verapdf):
    calls, result = fake_verapdf
    respx.post(_url(CONVERT)).mock(return_value=Response(200, content=(fixtures_dir / "etiquetado.pdf").read_bytes()))
    ctx, step = _office_stage(make_ctx, [fixtures_dir / "sin-alternativo.docx"])
    result["xml"] = mrr(False, "PDF/UA-1 validation profile", rules=[ALT_RULE, TITLE_RULE])
    ctx.stage = step.stage
    out = run(TOOL, ctx)
    assert calls == [("sin-alternativo.pdf", "ua1")]
    pdf_out, report_out, bundle = out
    assert bundle["name"] == "documentos-accesibles.zip"
    assert pdf_out["name"] == "sin-alternativo.pdf" and report_out["name"] == "informe-sin-alternativo.html"
    assert "se ha puesto «sin-alternativo», el nombre del archivo" in pdf_out["note"]
    assert "No cumple: PDF/UA-1 (reglas incumplidas: 2; incumplimientos: 2)." in pdf_out["note"]
    page = Path(report_out["path"]).read_text(encoding="utf-8")
    assert "«Ver texto alternativo»" in page and "Archivo → Información → Propiedades → Título" in page
    assert "PDF/UA-1" in page
    assert pdf_out["note"].endswith("El título puesto es provisional: cámbialo por uno que describa el documento.")
    # stage/ se queda para un posible reintento; se borra con el trabajo.
    assert (ctx.store.job_dir(ctx.job_id) / "stage" / "0.pdf").exists()


@respx.mock
def test_verapdf_stage_compliant_batch_and_english(make_ctx, fixtures_dir, fake_verapdf):
    calls, _ = fake_verapdf
    respx.post(_url(CONVERT)).mock(return_value=Response(200, content=(fixtures_dir / "etiquetado.pdf").read_bytes()))
    ctx, step = _office_stage(make_ctx, [fixtures_dir / "accesible.docx", fixtures_dir / "sin-alternativo.docx"], {"idioma": "en-GB"})
    ctx.stage, ctx.locale = step.stage, "en"
    out = run(TOOL, ctx)
    assert [c[1] for c in calls] == ["ua1", "ua1"]
    assert out[-1]["name"] == "accessible-documents.zip"
    names = [o["name"] for o in out[:-1]]
    assert names == ["accesible.pdf", "report-accesible.html", "sin-alternativo.pdf", "report-sin-alternativo.html"]
    assert "Compliant: PDF/UA-1." in out[0]["note"] and "Main text language: en-GB." in out[0]["note"]
    assert out[0]["note"].endswith("The title set is provisional: replace it with one that describes the document.")


def test_ua_explanations_in_validar_pdfa():
    """Las explicaciones de PDF/UA también llegan a validar-pdfa con el perfil ua1 (cláusula más larga primero)."""
    from tools.ocr import verapdf

    report = verapdf.parse_report(mrr(False, "PDF/UA-1 validation profile", rules=[
        ALT_RULE, {**TITLE_RULE, "clause": "7.18.5", "description": "Links shall contain an alternate description"},
        {**TITLE_RULE, "clause": "7.4.2", "description": "Heading levels shall not be skipped"},
        {**TITLE_RULE, "clause": "7.4.4", "description": "A node shall contain at most one child H tag"},
        {**TITLE_RULE, "clause": "6.2", "description": "The document catalog dictionary shall include a MarkInfo dictionary"}]))
    by_clause = {r.clause: verapdf.explain(r, "es") for r in report.rules}
    assert "texto alternativo" in by_clause["7.3"]
    assert "Editar hipervínculo" in by_clause["7.18.5"]
    assert "sin saltar niveles" in by_clause["7.4.2"] and "H1–H6" in by_clause["7.4.4"]
    assert "etiquetado (MarkInfo)" in by_clause["6.2"]
    # 7.2 es sobre todo anidamiento de tablas y listas; solo sus reglas de `Lang` hablan del idioma.
    rule = verapdf.Rule("ISO 14289-1:2014", "7.2", "42", "Table rows shall have the same number of columns", "SETR", "", 1)
    assert "celdas combinadas" in verapdf.explain(rule, "es") and "Idioma" not in verapdf.explain(rule, "es")
    rule.test = "21"
    assert "Establecer idioma de corrección" in verapdf.explain(rule, "es")
    # PDF/UA-2 numera de otra forma: explicación por categoría, no la de PDF/UA-1.
    ua2 = verapdf.Rule("ISO 14289-2:2024", "5", "1", "The PDF/UA version shall be identified", "MainXMPPackage", "metadata", 1)
    assert "PDF/UA-1" not in verapdf.explain(ua2, "es")
    assert "Edit Hyperlink" in verapdf.explain(next(r for r in report.rules if r.clause == "7.18.5"), "en")
    # Una regla de PDF/A sigue con su explicación por categoría.
    pdfa = verapdf.parse_report(mrr(False, rules=[{"clause": "6.2.11.4.1", "failed": 1, "description": "font not embedded"}]))
    assert verapdf.explain(pdfa.rules[0], "es").startswith("Hay fuentes sin incrustar")


@pytest.mark.integration
def test_end_to_end_office_then_ocr_without_the_password(api, user_token, tus_upload, fixtures_dir, services, fake_verapdf,
                                                         monkeypatch):
    """API → office (Gotenberg) → ocr (veraPDF): el segundo envío no lleva el sobre de secretos."""
    from tools import tasks

    hops: list[tuple[str, str]] = []

    def send_task(name, args=None, queue=None, **kw):
        hops.append((queue, args[2]))
        return tasks.execute(*args)

    monkeypatch.setattr(tasks.celery_app, "send_task", send_task)
    token = user_token(user_id="word-accesible")
    api.get("/v1/me", headers=auth(token))
    uid = tus_upload(token, TOOL, fixtures_dir / "accesible.docx")[0]
    with respx.mock(assert_all_called=False) as router:
        router.route(host__regex=r"^(127\.0\.0\.1|localhost|testserver)$").pass_through()
        convert = router.post(url__regex=r".*/forms/libreoffice/convert$").mock(
            return_value=Response(200, content=(fixtures_dir / "etiquetado.pdf").read_bytes()))
        resp = api.post("/v1/jobs", json={"tool": TOOL, "upload_ids": [uid], "options": {"contrasena": "abre"}}, headers=auth(token))
    assert resp.status_code == 201, resp.text
    job = api.get(f"/v1/jobs/{resp.json()['id']}", headers=auth(token)).json()
    assert job["status"] == "succeeded", job
    assert hops == [("ocr", "")]
    assert _fields(convert.calls.last.request)["password"] == "abre"  # la primera etapa sí tenía la contraseña
    assert [o["name"] for o in job["outputs"]] == ["accesible.pdf", "informe-accesible.html", "documentos-accesibles.zip"]
    assert fake_verapdf[0] == [("accesible.pdf", "ua1")]


@respx.mock
def test_title_only_in_info_is_copied_to_xmp(make_ctx, fixtures_dir, tmp_path):
    info_only = tmp_path / "info.pdf"
    with pikepdf.open(fixtures_dir / "etiquetado.pdf") as pdf:
        pdf.docinfo["/Title"] = "Título en Info"
        pdf.save(info_only)
    respx.post(_url(CONVERT)).mock(return_value=Response(200, content=info_only.read_bytes()))
    ctx, _ = _office_stage(make_ctx, [fixtures_dir / "accesible.docx"])
    with pikepdf.open(_stage_pdf(ctx)) as pdf, pdf.open_metadata() as meta:
        assert str(meta["dc:title"]) == "Título en Info"
    notes = json.loads((_stage_pdf(ctx).parent / "accesible.json").read_text())[0]["notes"]
    assert [k for k, _ in notes] == ["lang_missing"]


@respx.mock
def test_errors_wrong_password_unreadable_pdf_and_missing_stage(make_ctx, fixtures_dir):
    from core.errors import ToolError

    route = respx.post(_url(CONVERT)).mock(return_value=Response(400, text="the document is password protected"))
    with pytest.raises(ToolError) as err:
        run(TOOL, make_ctx(TOOL, [fixtures_dir / "accesible.docx"], secrets={"contrasena": "mal"}))
    assert err.value.code == "WRONG_PASSWORD"
    route.mock(return_value=Response(200, content=b"%PDF-1.7 no es un PDF"))
    with pytest.raises(ToolError) as err:
        run(TOOL, make_ctx(TOOL, [fixtures_dir / "accesible.docx"]))
    assert err.value.code == "ENGINE_FAILED"
    ctx = make_ctx(TOOL, [fixtures_dir / "accesible.docx"])
    ctx.stage = "verapdf"
    with pytest.raises(ToolError) as err:
        run(TOOL, ctx)
    assert err.value.code == "INTERNAL"


def test_ranges_checked_before_converting(make_ctx, fixtures_dir):
    """Con PDF/A o PDF/UA, un rango mal escrito o desordenado falla antes de llamar a Gotenberg (sin respx: no hay red)."""
    from core.errors import ToolError, message

    for spec in ("9-2", "x", "0-3"):
        with pytest.raises(ToolError) as err:
            run(TOOL, make_ctx(TOOL, [fixtures_dir / "accesible.docx"], {"paginas": spec}))
        assert err.value.code == "INVALID_OPTIONS"
    for spec in ("5,1-2", "2-4,3", "3-,7"):
        with pytest.raises(ToolError) as err:
            run(TOOL, make_ctx(TOOL, [fixtures_dir / "accesible.docx"], {"paginas": spec}))
        assert err.value.detail == "range_order"
    assert "Organizar PDF" in message("INVALID_OPTIONS", "es", "range_order")
    with pytest.raises(ToolError) as err:
        run("ppt-a-pdf", make_ctx("ppt-a-pdf", [fixtures_dir / "accesible.docx"],
                                   {"formato": "pdfa", "paginas": "1-2", "paginas_notas": True}))
    assert err.value.detail == "range_slides"
    assert "páginas de notas" in message("INVALID_OPTIONS", "es", "range_slides")


@pytest.mark.skipif(shutil.which("verapdf") is None, reason="veraPDF (Java) no instalado: job python de la CI")
def test_real_libreoffice_pdfua_with_fixes_against_verapdf(fixtures_dir, tmp_path):
    """El PDF/UA real de LibreOffice, con los arreglos, cumple las reglas de identificación y título de PDF/UA-1; el
    documento con una imagen sin texto alternativo falla 7.3."""
    from tools.ocr import verapdf
    from tools.office.accesible import fix_metadata

    if not (fixtures_dir / "accesible-ua.pdf").exists():
        pytest.skip("LibreOffice sin Writer: no hay PDF/UA de muestra")
    failed = {}
    for name in ("accesible", "sin-alternativo"):
        dst = tmp_path / f"{name}.pdf"
        shutil.copyfile(fixtures_dir / f"{name}-ua.pdf", dst)
        fix_metadata(dst, "", name, "documento")
        work = tmp_path / f"v-{name}"
        work.mkdir()
        report = verapdf.parse_report(verapdf.run_verapdf(dst, "ua1", work))
        failed[name] = {(r.clause, r.test) for r in report.rules}
    for name in failed:
        assert not any(clause == "5" for clause, _ in failed[name]), failed[name]
        assert not {("7.1", "8"), ("7.1", "9"), ("7.1", "10")} & failed[name], failed[name]
        assert ("6.2", "1") not in failed[name]
    assert any(clause == "7.3" for clause, _ in failed["sin-alternativo"]), failed["sin-alternativo"]
    assert not any(clause == "7.3" for clause, _ in failed["accesible"]), failed["accesible"]
