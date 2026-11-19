"""Pruebas de efecto de las herramientas de servidor (16.5 y 16.6), llamando a su implementación."""
from __future__ import annotations

import json
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path

import pikepdf
import pytest
import respx
from httpx import Response

from core.plans import load_plans_file
from core.registry import load_registry
from core.settings import get_settings
from core.storage import Store
from tools.base import InputFile, ToolContext, sha256_file


@pytest.fixture()
def make_ctx(tmp_path):
    settings = get_settings()

    def make(tool: str, files: list[Path], options: dict | None = None, secrets: dict | None = None, plan: str = "pro") -> ToolContext:
        spec = load_registry().require(tool)
        store = Store(tmp_path / "files")
        job_id = str(uuid.uuid4())
        store.ensure_job_dirs(job_id)
        inputs = []
        for f in files:
            dst = store.in_dir(job_id) / f.name
            shutil.copyfile(f, dst)
            inputs.append(InputFile(dst, f.name, f.suffix.lstrip(".").lower().replace("jpeg", "jpg"), dst.stat().st_size, sha256_file(dst)))
        return ToolContext(job_id=job_id, tool=spec.slug_es, inputs=inputs, work=store.work_dir(job_id), out=store.out_dir(job_id),
                           options=spec.options.model_validate(options or {}), secrets=secrets or {},
                           plan=load_plans_file(settings.PLANS_FILE)[plan], settings=settings, store=store, threads=2)

    return make


def run(tool: str, ctx: ToolContext) -> list[dict]:
    from core.registry import load_impl

    return load_impl(load_registry().require(tool))(ctx)


def test_compress_never_bigger_and_smaller_with_photos(make_ctx, fixtures_dir):
    out = run("comprimir-pdf", make_ctx("comprimir-pdf", [fixtures_dir / "fotos.pdf"]))
    path = Path(out[0]["path"])
    assert path.stat().st_size < (fixtures_dir / "fotos.pdf").stat().st_size
    out = run("comprimir-pdf", make_ctx("comprimir-pdf", [fixtures_dir / "texto.pdf"], {"nivel": "sin_perdida"}))
    assert Path(out[0]["path"]).stat().st_size <= (fixtures_dir / "texto.pdf").stat().st_size
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(out[0]["path"])
    assert "Hola mundo" in doc[0].get_textpage().get_text_range()


def test_compress_batch_has_zip(make_ctx, fixtures_dir):
    out = run("comprimir-pdf", make_ctx("comprimir-pdf", [fixtures_dir / "fotos.pdf", fixtures_dir / "texto.pdf"]))
    assert out[-1]["name"].endswith(".zip")
    with zipfile.ZipFile(out[-1]["path"]) as zf:
        assert len(zf.namelist()) == 2


def test_compress_removal_options(make_ctx, fixtures_dir):
    out = run("comprimir-pdf", make_ctx("comprimir-pdf", [fixtures_dir / "texto.pdf"], {"quitar_metadatos": True, "nivel": "sin_perdida"}))
    with pikepdf.open(out[0]["path"]) as pdf:
        assert "/Title" not in pdf.docinfo


def test_protect_permissions_and_aes256(make_ctx, fixtures_dir):
    ctx = make_ctx("proteger-pdf", [fixtures_dir / "texto.pdf"], {"permitir_imprimir": False, "permitir_copiar": False},
                   {"contrasena_apertura": "abrir1234", "contrasena_propietario": "dueno5678"})
    out = run("proteger-pdf", ctx)
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(out[0]["path"])
    with pikepdf.open(out[0]["path"], password="abrir1234") as pdf:
        assert pdf.is_encrypted
        assert pdf.encryption.R == 6
        assert not pdf.allow.print_highres and not pdf.allow.extract


def test_unlock_requires_right_password(make_ctx, fixtures_dir):
    from core.errors import ToolError

    with pytest.raises(ToolError) as err:
        run("desbloquear-pdf", make_ctx("desbloquear-pdf", [fixtures_dir / "cifrado.pdf"], {}, {}))
    assert err.value.code == "PASSWORD_REQUIRED"
    out = run("desbloquear-pdf", make_ctx("desbloquear-pdf", [fixtures_dir / "cifrado.pdf"], {}, {"contrasena": "secreto123"}))
    with pikepdf.open(out[0]["path"]) as pdf:
        assert not pdf.is_encrypted


def test_images_to_pdf_keeps_jpeg_bytes(make_ctx, fixtures_dir):
    out = run("jpg-a-pdf", make_ctx("jpg-a-pdf", [fixtures_dir / "foto.jpg"], {"tamano_pagina": "A4", "margen": "10"}))
    original = (fixtures_dir / "foto.jpg").read_bytes()
    with pikepdf.open(out[0]["path"]) as pdf:
        assert len(pdf.pages) == 1
        images = list(pdf.pages[0].images.values())
        assert images[0].read_raw_bytes() == original
        box = pdf.pages[0].mediabox
        dims = sorted(float(v) / 72 * 25.4 for v in (box[2], box[3]))
        assert abs(dims[0] - 210) < 1 and abs(dims[1] - 297) < 1


def test_tiff_multipage_and_bookmarks(make_ctx, fixtures_dir):
    ctx = make_ctx("imagenes-a-pdf", [fixtures_dir / "multipagina.tiff", fixtures_dir / "imagen.webp"], {"marcadores": True})
    out = run("imagenes-a-pdf", ctx)
    with pikepdf.open(out[0]["path"]) as pdf:
        assert len(pdf.pages) == 4
        with pdf.open_outline() as outline:
            assert [i.title for i in outline.root] == ["multipagina", "imagen"]


def test_pdf_to_images_ranges_and_zip(make_ctx, fixtures_dir):
    out = run("pdf-a-jpg", make_ctx("pdf-a-jpg", [fixtures_dir / "texto.pdf"], {"paginas": "1, 3", "dpi": 72}))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        assert sorted(zf.namelist()) == ["texto-1.jpg", "texto-3.jpg"]
    single = run("pdf-a-png", make_ctx("pdf-a-png", [fixtures_dir / "texto.pdf"], {"paginas": "2", "dpi": 72, "color": "gris"}))
    assert single[0]["name"].endswith(".png")


def test_render_pixel_limit(make_ctx, fixtures_dir, monkeypatch):
    from PIL import Image

    ctx = make_ctx("pdf-a-png", [fixtures_dir / "texto.pdf"], {"paginas": "1", "dpi": 600})
    monkeypatch.setattr(ctx.settings, "RENDER_MAX_PIXELS", 200_000)
    out = run("pdf-a-png", ctx)
    with Image.open(out[0]["path"]) as img:
        assert img.width * img.height <= 200_000 * 1.01


def _ffprobe(path: str) -> dict:
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name", "-of", "json", path],
                         capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg no instalado")


@needs_ffmpeg
@pytest.mark.parametrize("tool,name", [("ogg-a-mp3", "voz.ogg"), ("opus-a-mp3", "voz.opus"), ("m4a-a-mp3", "audio.m4a"), ("mp4-a-mp3", "video.mp4")])
def test_audio_to_mp3(make_ctx, fixtures_dir, tool, name):
    src = fixtures_dir / name
    out = run(tool, make_ctx(tool, [src], {"calidad": "128", "canales": "mono"}))
    info = _ffprobe(out[0]["path"])
    assert info["streams"][0]["codec_name"] == "mp3"
    expected = float(_ffprobe(str(src))["format"]["duration"])
    assert abs(float(info["format"]["duration"]) - expected) < 0.1


@needs_ffmpeg
def test_audio_duration_limit(make_ctx, fixtures_dir):
    from core.errors import ToolError

    ctx = make_ctx("ogg-a-mp3", [fixtures_dir / "voz.ogg"], plan="anon")
    ctx.plan.audio_minutes = 0
    with pytest.raises(ToolError) as err:
        run("ogg-a-mp3", ctx)
    assert err.value.code == "LIMIT_EXCEEDED"


def _gotenberg(path: str) -> str:
    return f"{get_settings().GOTENBERG_URL.rstrip('/')}{path}"


@respx.mock
def test_office_via_gotenberg_fields_and_ranges(make_ctx, fixtures_dir):
    pdf_bytes = (fixtures_dir / "texto.pdf").read_bytes()
    route = respx.post(_gotenberg("/forms/libreoffice/convert")).mock(return_value=Response(200, content=pdf_bytes))
    src = fixtures_dir / "carta.docx" if (fixtures_dir / "carta.docx").exists() else fixtures_dir / "texto.pdf"
    ctx = make_ctx("word-a-pdf", [src], {"formato": "pdfa", "paginas": "2-"}, {"contrasena": "doc-secreta"})
    out = run("word-a-pdf", ctx)
    body = route.calls.last.request.content.decode("latin-1")
    assert 'name="pdfa"' in body and "PDF/A-2b" in body
    assert 'name="password"' in body
    # PDF/A con rango: lo aplica LibreOffice en una segunda conversión, para no perder el XMP ni el OutputIntent (D-182).
    assert route.call_count == 2 and 'name="nativePageRanges"\r\n\r\n2-3' in body
    # El resultado es la segunda conversión tal cual (sin pasar por pikepdf), con las 3 páginas que devuelve el simulado.
    assert Path(out[0]["path"]).read_bytes() == pdf_bytes


@respx.mock
def test_gotenberg_busy_is_transient(make_ctx, fixtures_dir):
    from core.errors import ToolError

    respx.post(_gotenberg("/forms/libreoffice/convert")).mock(return_value=Response(503))
    with pytest.raises(ToolError) as err:
        run("excel-a-pdf", make_ctx("excel-a-pdf", [fixtures_dir / "texto.pdf"]))
    assert err.value.transient


def test_convertir_a_pdf_images_without_gotenberg(make_ctx, fixtures_dir):
    out = run("convertir-a-pdf", make_ctx("convertir-a-pdf", [fixtures_dir / "foto.jpg"]))
    with pikepdf.open(out[0]["path"]) as pdf:
        assert len(pdf.pages) == 1


@pytest.mark.needs_tesseract
@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no instalado")
def test_ocr_makes_text_searchable(make_ctx, fixtures_dir):
    import pypdfium2 as pdfium

    out = run("ocr-pdf", make_ctx("ocr-pdf", [fixtures_dir / "escaneado.pdf"], {"idiomas": ["spa"]}))
    text = pdfium.PdfDocument(out[0]["path"])[0].get_textpage().get_text_range()
    assert "Factura" in text and "Madrid" in text


@pytest.mark.needs_tesseract
@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no instalado")
def test_ocr_pdfa_output_without_ghostscript(make_ctx, fixtures_dir):
    out = run("ocr-pdf", make_ctx("ocr-pdf", [fixtures_dir / "escaneado.pdf"], {"idiomas": ["spa"], "salida": "pdfa"}))
    with pikepdf.open(out[0]["path"]) as pdf:
        meta = pdf.open_metadata()
        assert meta.pdfa_status.startswith("2")


@pytest.mark.needs_tesseract
@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no instalado")
def test_ocr_txt_output(make_ctx, fixtures_dir):
    out = run("ocr-pdf", make_ctx("ocr-pdf", [fixtures_dir / "escaneado.pdf"], {"idiomas": ["spa"], "salida": "txt"}))
    assert "Madrid" in Path(out[0]["path"]).read_text(encoding="utf-8")


@pytest.mark.needs_soffice
@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice no instalado")
def test_pdf_to_word_faithful_with_libreoffice(make_ctx, fixtures_dir):
    out = run("pdf-a-word", make_ctx("pdf-a-word", [fixtures_dir / "texto.pdf"], {"modo": "fiel", "paginas": "1"}))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        assert "Hola mundo" in zf.read("word/document.xml").decode("utf-8")
