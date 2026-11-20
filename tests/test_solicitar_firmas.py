"""F4-C2: solicitar-firmas, la parte de los workers (7.7, D-202).

Las fases `firmante` y `final` sellan con el firmante de archivo de la PKI de pruebas y la TSA y el OCSP del
«illusionist» de certomancer, sin red; cada resultado se comprueba con la verificación de verificar-firmas-pdf.
"""
from __future__ import annotations

import io
import sys
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

import pikepdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "fixtures"))

from test_firmas import _signer, analyse, arch  # noqa: E402,F401 - fixtures compartidas
from test_tools import make_ctx, run  # noqa: E402,F401

TOOL = "solicitar-firmas"
TSA = "http://certomancer.test/conversor-pruebas/tsa/tsa"


def _pdf(tmp_path: Path, pages: int = 2, name: str = "contrato.pdf", size=(595, 842)) -> Path:
    pdf = pikepdf.new()
    for _ in range(pages):
        pdf.add_blank_page(page_size=size)
    path = tmp_path / name
    pdf.save(path)
    return path


def _png(tmp_path: Path) -> Path:
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (400, 150), (255, 255, 255, 0))
    ImageDraw.Draw(img).line([(20, 120), (120, 30), (220, 110), (380, 40)], fill=(10, 20, 120, 255), width=6)
    path = tmp_path / "firma.png"
    img.save(path)
    return path


def _chain(arch):
    return [arch.get_cert("seal"), arch.get_cert("interm"), arch.get_cert("root")]


@pytest.fixture()
def sealing(arch, monkeypatch):
    """Sello de archivo, TSA y OCSP de certomancer y sin base de datos para el registro de sellos."""
    from certomancer.integrations.aiohttp_illusionist import AsyncIllusionist
    from pyhanko.sign.timestamps import HTTPTimeStamper

    from tools.sign import firmar, solicitar

    @contextmanager
    def file_signer(_settings):
        yield _signer(arch, "seal"), _chain(arch)

    @asynccontextmanager
    async def clients(_settings):
        async with AsyncIllusionist(arch).serving_session() as session:
            yield session, HTTPTimeStamper(TSA, session=session)

    recorded: list[tuple] = []
    monkeypatch.setattr(firmar, "seal_signer", file_signer)
    monkeypatch.setattr(firmar, "seals_today", lambda: 0)
    monkeypatch.setattr(firmar, "record_seal", lambda job, sha, level: recorded.append((job, sha, level)))
    monkeypatch.setattr(solicitar, "tsa_clients", clients)
    return recorded


def _ctx(make_ctx, files, options, owner=("request", "r1"), locale="es", plan="pro"):
    from core.settings import get_settings

    ctx = make_ctx(TOOL, files, options, plan=plan)
    ctx.owner = owner
    ctx.locale = locale
    ctx.settings = get_settings().model_copy(update={"TSA_URL": TSA, "SEAL_ENABLED": True})
    return ctx


def _sig_fields(data: bytes) -> dict[str, bool]:
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.fields import enumerate_sig_fields

    reader = PdfFileReader(io.BytesIO(data), strict=False)
    return {name: value is not None for name, value, _ref in enumerate_sig_fields(reader, filled_status=None)}


# --- preparar ---------------------------------------------------------------------------------------------------------


def test_prepare_adds_a_signature_page_with_one_field_per_signer(make_ctx, tmp_path):
    ctx = _ctx(make_ctx, [_pdf(tmp_path)], {"firmantes": [{"nombre": "Ana Pérez"}, {"nombre": "Luis (RR. HH.)"}, {"nombre": "Émile"}]},
               owner=("user", "u1"))
    [out] = run(TOOL, ctx)
    data = Path(out["path"]).read_bytes()
    assert out["name"] == "contrato.pdf"
    assert _sig_fields(data) == {"Firmante1": False, "Firmante2": False, "Firmante3": False}
    with pikepdf.open(io.BytesIO(data)) as pdf:
        assert len(pdf.pages) == 3
        page = pdf.pages[2]
        widgets = [a for a in page.obj.get("/Annots") or [] if a.get("/FT") == "/Sig" or a.get("/Parent", {}).get("/FT") == "/Sig"]
        assert len(widgets) == 3
        content = page.obj.Contents.read_bytes()
        assert b"(Firmas)" in content and b"Firma de Ana P\xe9rez" in content and b"Luis \\(RR. HH.\\)" in content


def test_prepare_uses_existing_empty_fields_and_rejects_bad_choices(make_ctx, tmp_path):
    from core.errors import ToolError

    base = Path(run(TOOL, _ctx(make_ctx, [_pdf(tmp_path)], {"firmantes": [{"nombre": "A"}]}, owner=("user", "u1")))[0]["path"])
    src = tmp_path / "con-campo.pdf"
    src.write_bytes(base.read_bytes())
    # El campo «Firmante1» ya existe y está vacío: se elige; el nuevo es Firmante2, sin página nueva.
    [out] = run(TOOL, _ctx(make_ctx, [src], {"firmantes": [{"nombre": "B", "campo": "Firmante1"}, {"nombre": "C"}]}, owner=("user", "u1")))
    data = Path(out["path"]).read_bytes()
    assert _sig_fields(data) == {"Firmante1": False, "Firmante2": False}
    with pikepdf.open(io.BytesIO(data)) as pdf:
        assert len(pdf.pages) == 4  # la del primer paso y otra nueva para Firmante2
    for options, detail in (({"firmantes": [{"nombre": "B", "campo": "NoExiste"}]}, "seal_field_missing"),
                            ({"firmantes": [{"nombre": "B", "campo": "Firmante1"}, {"nombre": "C", "campo": "Firmante1"}]}, "request_field_repeated"),
                            ({"firmantes": [{"nombre": "B"}]}, "request_field_taken:Firmante1")):
        with pytest.raises(ToolError) as err:
            run(TOOL, _ctx(make_ctx, [src], options, owner=("user", "u1")))
        assert err.value.detail == detail


def test_prepare_limits_and_precheck(make_ctx, tmp_path):
    from core.errors import AppError, ToolError
    from core.plans import load_plans_file
    from core.settings import get_settings
    from tools.sign import solicitar

    settings = get_settings()
    plans = load_plans_file(settings.PLANS_FILE)
    four = {"firmantes": [{"nombre": str(i)} for i in range(4)]}
    with pytest.raises(ToolError) as err:
        run(TOOL, _ctx(make_ctx, [_pdf(tmp_path)], four, owner=("user", "u1"), plan="free"))
    assert err.value.code == "LIMIT_EXCEEDED"
    pdf = _pdf(tmp_path, name="p.pdf")
    with pytest.raises(AppError) as aerr:
        solicitar.precheck(settings, plans["free"], "user", four, [pdf])
    assert aerr.value.code == "LIMIT_EXCEEDED"
    solicitar.precheck(settings, plans["pro"], "user", four, [pdf])
    for owner, options, code in (("anon", four, "UNAUTHORIZED"), ("user", {"firmantes": []}, "INVALID_OPTIONS"),
                                 ("user", {**four, "fase": "firmante"}, "INVALID_OPTIONS"),
                                 ("user", {**four, "fase": "final"}, "INVALID_OPTIONS")):
        with pytest.raises(AppError) as aerr:
            solicitar.precheck(settings, plans["pro"], owner, options, [pdf])
        assert aerr.value.code == code


def test_prepare_refuses_encrypted_and_new_pages_after_a_signature(arch, make_ctx, tmp_path, sealing):
    from core.errors import ToolError

    secret = tmp_path / "cifrado.pdf"
    with pikepdf.open(_pdf(tmp_path)) as pdf:
        pdf.save(secret, encryption=pikepdf.Encryption(owner="o", user="u"))
    with pytest.raises(ToolError) as err:
        run(TOOL, _ctx(make_ctx, [secret], {"firmantes": [{"nombre": "A"}]}, owner=("user", "u1")))
    assert err.value.code in ("INVALID_OPTIONS", "CORRUPT_FILE")
    signed = tmp_path / "firmado.pdf"
    signed.write_bytes(_sign_one(make_ctx, tmp_path, "A"))
    with pytest.raises(ToolError) as err:
        run(TOOL, _ctx(make_ctx, [signed], {"firmantes": [{"nombre": "B"}]}, owner=("user", "u1")))
    assert err.value.detail == "request_field_taken:Firmante1"
    with pytest.raises(ToolError) as err:
        run(TOOL, _ctx(make_ctx, [signed], {"firmantes": [{"nombre": "B", "campo": "Otro"}, {"nombre": "C", "campo": ""}]},
                       owner=("user", "u1")))
    assert err.value.detail in ("seal_field_missing", "request_signed_needs_fields")


def test_layout_fits_ten_signers_and_small_pages():
    from tools.sign.solicitar import _layout

    pages = _layout(595, 842, 10)
    assert sum(len(p) for p in pages) == 10
    for boxes in pages:
        for x0, y0, x1, y1 in boxes:
            assert 0 < x0 < x1 <= 595 and 0 < y0 < y1 <= 842
    small = _layout(300, 300, 3)
    assert sum(len(p) for p in small) == 3 and len(small) >= 2


# --- firmante y final ---------------------------------------------------------------------------------------------------


def _prepared(make_ctx, tmp_path, names=("Ana", "Luis")) -> Path:
    [out] = run(TOOL, _ctx(make_ctx, [_pdf(tmp_path)], {"firmantes": [{"nombre": n} for n in names]}, owner=("user", "u1")))
    path = tmp_path / "preparado.pdf"
    path.write_bytes(Path(out["path"]).read_bytes())
    return path


def _sign_one(make_ctx, tmp_path, name: str, src: Path | None = None, field: str = "Firmante1") -> bytes:
    doc = src or _prepared(make_ctx, tmp_path, (name,))
    ctx = _ctx(make_ctx, [doc, _png(tmp_path)], {"fase": "firmante", "campo": field, "nombre": name, "correo": "ana@ejemplo.test"})
    [out] = run(TOOL, ctx)
    return Path(out["path"]).read_bytes()


def test_signer_step_seals_the_field_with_image_and_text(arch, make_ctx, tmp_path, sealing):
    data = _sign_one(make_ctx, tmp_path, "Ana Pérez")
    [sig] = analyse(data, roots=[arch.get_cert("root"), arch.get_cert("seal")])
    assert (sig.field, sig.intact, sig.valid, sig.pades, sig.level) == ("Firmante1", True, True, "B-T", "plataforma")
    assert sig.reason == "Firmado por Ana Pérez (ana@ejemplo.test), verificado por correo"
    with pikepdf.open(io.BytesIO(data)) as pdf:
        widget = next(a for p in pdf.pages for a in (p.obj.get("/Annots") or []) if a.get("/T") == "Firmante1")
        ap = widget.AP.N
        xobjects = [ap.Resources.XObject[k] for k in ap.Resources.XObject.keys()] if "/XObject" in ap.Resources else []
        images = []
        for xo in xobjects:  # la imagen va dentro de un XObject de forma (fondo) o directamente
            if xo.get("/Subtype") == "/Image":
                images.append(xo)
            elif "/Resources" in xo and "/XObject" in xo.Resources:
                images += [xo.Resources.XObject[k] for k in xo.Resources.XObject.keys() if xo.Resources.XObject[k].get("/Subtype") == "/Image"]
        assert images and "/SMask" in images[0]
    assert len(sealing) == 1 and sealing[0][2] == "B-T"


def test_two_signers_then_final_seal_and_audit_certificate(arch, make_ctx, tmp_path, sealing, monkeypatch):
    from tools.sign import solicitar

    pages: list[str] = []

    def fake_render(_settings, page: str) -> bytes:
        pages.append(page)
        pdf = pikepdf.new()
        pdf.add_blank_page(page_size=(595, 842))
        buf = io.BytesIO()
        pdf.save(buf)
        return buf.getvalue()

    monkeypatch.setattr(solicitar, "render_certificate", fake_render)
    prepared = _prepared(make_ctx, tmp_path)
    first = tmp_path / "uno.pdf"
    first.write_bytes(_sign_one(make_ctx, tmp_path, "Ana", src=prepared, field="Firmante1"))
    second = tmp_path / "dos.pdf"
    second.write_bytes(_sign_one(make_ctx, tmp_path, "Luis <b>", src=first, field="Firmante2"))
    options = {"fase": "final", "documento": "Contrato <script>", "solicitud": "abc", "propietario": "pide@ejemplo.test",
               "creada": "2026-11-20T10:00:00+00:00", "original_sha256": "a" * 64,
               "firmantes": [{"nombre": "Ana", "correo": "ana@ejemplo.test", "campo": "Firmante1", "firmado": "2026-11-20T10:05:00+00:00"},
                             {"nombre": "Luis <b>", "correo": "luis@ejemplo.test", "campo": "Firmante2", "firmado": "2026-11-20T10:09:00+00:00"}],
               "eventos": [{"evento": "created", "actor": "pide@ejemplo.test", "fecha": "2026-11-20T10:00:00+00:00", "sha256": "b" * 64},
                           {"evento": "signed", "actor": "luis@ejemplo.test", "fecha": "2026-11-20T10:09:00+00:00", "ip": "1234",
                            "agente": "Mozilla/5.0 <x>", "detalle": "Firmante2"}]}
    ctx = _ctx(make_ctx, [second], options)
    second_ctx_name = ctx.inputs[0].name
    out = run(TOOL, ctx)
    assert [o["name"] for o in out] == [second_ctx_name.replace(".pdf", "-firmado.pdf"), "certificado-auditoria.pdf"]
    final = Path(out[0]["path"]).read_bytes()
    items = analyse(final, roots=[arch.get_cert("root"), arch.get_cert("seal")])
    assert [s.field for s in items] == ["Firmante1", "Firmante2", "SelloFinal1"]
    assert all(s.intact and s.valid for s in items)
    assert items[-1].pades == "B-LT" and items[0].changes_ok and items[1].changes_ok
    assert final.count(b"/ByteRange") == 3  # sin comprimir: la e2e de servidor cuenta así las firmas
    [cert] = analyse(Path(out[1]["path"]).read_bytes(), roots=[arch.get_cert("root"), arch.get_cert("seal")])
    assert cert.pades == "B-LT" and cert.valid
    import hashlib

    page = pages[0]
    assert hashlib.sha256(final).hexdigest() in page and "a" * 64 in page
    assert "<script>" not in page and "Contrato &lt;script&gt;" in page and "Luis &lt;b&gt;" in page
    assert "Firmado" in page and "Solicitud creada" in page and "Mozilla/5.0 &lt;x&gt;" in page
    assert [r[2] for r in sealing] == ["B-T", "B-T", "B-LT", "B-LT"]


def test_internal_steps_refuse_user_jobs_and_missing_tsa(make_ctx, tmp_path, sealing):
    from core.errors import ToolError

    prepared = _prepared(make_ctx, tmp_path, ("Ana",))
    for owner in (("user", "u1"), ("anon", "a1")):
        with pytest.raises(ToolError) as err:
            run(TOOL, _ctx(make_ctx, [prepared, _png(tmp_path)], {"fase": "firmante", "campo": "Firmante1", "nombre": "X"}, owner=owner))
        assert (err.value.code, err.value.detail) == ("FORBIDDEN", "request_stage")
        with pytest.raises(ToolError) as err:
            run(TOOL, _ctx(make_ctx, [prepared], {"fase": "final"}, owner=owner))
        assert err.value.code == "FORBIDDEN"
    ctx = _ctx(make_ctx, [prepared, _png(tmp_path)], {"fase": "firmante", "campo": "Firmante1", "nombre": "X"})
    ctx.settings = ctx.settings.model_copy(update={"TSA_URL": ""})
    with pytest.raises(ToolError) as err:
        run(TOOL, ctx)
    assert err.value.detail == "seal_config"
    with pytest.raises(ToolError) as err:
        run(TOOL, _ctx(make_ctx, [prepared, _png(tmp_path)], {"fase": "firmante", "campo": "Otro", "nombre": "X"}))
    assert err.value.detail == "seal_field_missing"



def test_stamp_font_has_1000_units_per_em(arch, make_ctx, tmp_path, sealing):
    """pyHanko 0.38 escribe /W y los ajustes de TJ en unidades de la fuente: con 2048 por em (DejaVu) el texto del
    sello salía espaciado y cortado. La fuente del paquete tiene 1000 y su SHA-256 anotado."""
    import hashlib

    from fontTools.ttLib import TTFont

    from tools.sign import firmar

    font = Path(firmar.FONT)
    assert TTFont(font)["head"].unitsPerEm == 1000
    expected = (font.parent / "SHA256SUMS").read_text().split()[0]
    assert hashlib.sha256(font.read_bytes()).hexdigest() == expected
    data = _sign_one(make_ctx, tmp_path, "Ana")
    with pikepdf.open(io.BytesIO(data)) as pdf:
        widget = next(a for p in pdf.pages for a in (p.obj.get("/Annots") or []) if a.get("/T") == "Firmante1")
        fonts = []

        def walk(xobj, depth=0):
            res = xobj.get("/Resources") or {}
            fonts.extend(res.get("/Font", {}).values() if "/Font" in res else [])
            if "/XObject" in res and depth < 4:
                for k in res.XObject.keys():
                    walk(res.XObject[k], depth + 1)

        walk(widget.AP.N)
        widths = [w for f in fonts for w in f.DescendantFonts[0].W if isinstance(w, pikepdf.Array) for w in w]
        assert widths and max(float(w) for w in widths) < 1000


def test_retry_policy_waits_on_seal_limit_and_outages():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from core import signreq

    now = datetime.now(timezone.utc)
    job = lambda code, minutes: SimpleNamespace(error_code=code, finished_at=now - timedelta(minutes=minutes))  # noqa: E731
    assert signreq._job_failed(None, None, job("QUOTA_EXCEEDED", 5), 7, now) == "wait"
    assert signreq._job_failed(None, None, job("QUOTA_EXCEEDED", 31), 99, now) == "retry_free"  # no gasta intentos
    assert signreq._job_failed(None, None, job("TOOL_DISABLED", 3), 1, now) == "retry"  # el sello apagado un rato no cierra
    assert signreq._job_failed(None, None, job("ENGINE_FAILED", 10), 4, now) == "wait"  # 2^4 = 16 minutos
    assert signreq._job_failed(None, None, job("ENGINE_FAILED", 121), 7, now) == "retry"
    assert signreq._job_failed(None, None, job("ENGINE_FAILED", 200), signreq.JOB_RETRIES, now) == "fail"
    assert signreq._job_failed(None, None, job("CORRUPT_FILE", 0), 1, now) == "fail"
    assert signreq.final_names("x" * 112 + ".pdf", ["x" * 112 + ".pdf", "certificado-auditoria.pdf"]) == \
        ["documento-firmado.pdf", "certificado-auditoria.pdf"]


def test_certificate_summary_keeps_key_events():
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from core import signreq

    at = datetime(2026, 11, 20, tzinfo=timezone.utc)
    ev = lambda e, who="a@x.test": SimpleNamespace(event=e, actor=who, created_at=at, ip_hash=None, user_agent=None,  # noqa: E731
                                                   document_sha256=None, detail=None)
    events = [ev("created", "o@x.test"), ev("invited")] + [ev("code_failed") for _ in range(500)] + [ev("code_verified"), ev("signed")]
    rows = signreq.summarize(events)
    assert [r["evento"] for r in rows] == ["created", "invited", "code_failed", "code_failed", "code_verified", "signed"]
    assert rows[3]["detalle"] == "500×"
