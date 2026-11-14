"""F3, lote C: imagen-a-texto (7.6) con Tesseract y OCRmyPDF reales, sin IA (6.3: 0 peticiones).

Efecto de cada opción sobre el resultado (16.6), lotes con ZIP (A.0), TIFF de varias páginas, imagen sin texto y la
bomba de píxeles de 16.4. Las muestras las genera scripts/fixtures/imagenes_ocr.py.
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

from core.errors import ErrorCode, ToolError
from core.registry import load_registry
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida

pytest.importorskip("ocrmypdf")
pytestmark = [pytest.mark.needs_tesseract,
              pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no instalado")]
TOOL = "imagen-a-texto"


def _text(out: list[dict]) -> str:
    return Path(out[0]["path"]).read_text(encoding="utf-8")


def test_spec_is_local_ocr_without_ai():
    spec = load_registry().require(TOOL)
    assert spec.ai is None and spec.category == "ai" and spec.cost_class == "heavy" and spec.queue == "ocr"
    assert "zip" in spec.outputs and set(spec.inputs) == {"jpg", "png", "webp", "tiff", "bmp", "gif"}


def test_photo_of_a_document_keeps_accents_and_enye(make_ctx, fixtures_dir):
    out = run(TOOL, make_ctx(TOOL, [fixtures_dir / "ocr-documento.jpg"]))
    assert out[0]["name"] == "ocr-documento.txt" and out[0]["note"] is None
    text = _text(out)
    for word in ("señor", "Muñoz", "canción", "pequeña", "Logroño", "información", "útil", "rápida"):
        assert word in text, (word, text)


def test_languages_change_the_result(make_ctx, fixtures_dir):
    spanish = _text(run(TOOL, make_ctx(TOOL, [fixtures_dir / "ocr-documento.jpg"], {"idiomas": ["spa"]})))
    english = _text(run(TOOL, make_ctx(TOOL, [fixtures_dir / "ocr-documento.jpg"], {"idiomas": ["eng"]})))
    assert "Logroño" in spanish and spanish != english


def test_screenshot_with_transparency(make_ctx, fixtures_dir):
    text = _text(run(TOOL, make_ctx(TOOL, [fixtures_dir / "ocr-captura.png"])))
    assert "Configuración de la cuenta" in text and "Last login" in text


def test_output_docx_and_searchable_pdf(make_ctx, fixtures_dir):
    import pypdfium2 as pdfium
    from docx import Document

    out = run(TOOL, make_ctx(TOOL, [fixtures_dir / "ocr-documento.jpg"], {"salida": "docx"}))
    assert out[0]["name"] == "ocr-documento.docx"
    assert "Logroño" in "\n".join(p.text for p in Document(out[0]["path"]).paragraphs)
    out = run(TOOL, make_ctx(TOOL, [fixtures_dir / "ocr-documento.jpg"], {"salida": "pdf"}))
    assert out[0]["name"] == "ocr-documento-ocr.pdf"
    doc = pdfium.PdfDocument(out[0]["path"])
    assert len(doc) == 1 and "Logroño" in doc[0].get_textpage().get_text_range()


def test_deskew_straightens_the_page(make_ctx, fixtures_dir):
    """Con «Enderezar», la página del PDF queda recta (la muestra está girada 4 grados); sin él, sigue torcida."""
    import pypdfium2 as pdfium

    from tools.ocr.imagen import skew_angle

    def page_skew(options: dict) -> float:
        out = run(TOOL, make_ctx(TOOL, [fixtures_dir / "ocr-inclinada.png"], {"salida": "pdf", **options}))
        return skew_angle(pdfium.PdfDocument(out[0]["path"])[0].render(scale=1).to_pil())

    assert abs(page_skew({"enderezar": True})) <= 0.3
    assert abs(page_skew({"enderezar": False})) >= 3.5


def test_autorotate_reads_a_sideways_page(make_ctx, fixtures_dir):
    plain = _text(run(TOOL, make_ctx(TOOL, [fixtures_dir / "ocr-de-lado.png"], {"autorrotar": False})))
    rotated = _text(run(TOOL, make_ctx(TOOL, [fixtures_dir / "ocr-de-lado.png"], {"autorrotar": True})))
    assert "Logroño" in rotated and "Logroño" not in plain


def test_multipage_tiff_keeps_pages_apart(make_ctx, fixtures_dir):
    from docx import Document

    text = _text(run(TOOL, make_ctx(TOOL, [fixtures_dir / "ocr-paginas.tiff"])))
    first, second = text.split("\f")
    assert "Primera página" in first and "Segunda página" in second
    out = run(TOOL, make_ctx(TOOL, [fixtures_dir / "ocr-paginas.tiff"], {"salida": "docx"}))
    assert 'w:br w:type="page"' in Document(out[0]["path"]).element.xml


def test_batch_gives_a_zip_or_one_joined_file(make_ctx, fixtures_dir):
    files = [fixtures_dir / "ocr-documento.jpg", fixtures_dir / "ocr-captura.png"]
    out = run(TOOL, make_ctx(TOOL, files))
    assert [o["name"] for o in out] == ["ocr-documento.txt", "ocr-captura.txt", "imagenes-texto.zip"]
    assert sorted(zipfile.ZipFile(out[-1]["path"]).namelist()) == ["ocr-captura.txt", "ocr-documento.txt"]
    joined = run(TOOL, make_ctx(TOOL, files, {"unir": True, "salida": "pdf"}))
    import pypdfium2 as pdfium

    assert len(joined) == 1 and joined[0]["name"] == "imagenes-texto-ocr.pdf"
    assert len(pdfium.PdfDocument(joined[0]["path"])) == 2


def test_image_without_text_says_so(make_ctx, fixtures_dir):
    out = run(TOOL, make_ctx(TOOL, [fixtures_dir / "ocr-sin-texto.png"]))
    assert out[0]["note"] == "No se ha encontrado texto en ocr-sin-texto.png."


def test_pixel_bomb_and_missing_language(make_ctx, fixtures_dir):
    """16.4: un PNG que dice medir 40.000 × 40.000 se rechaza sin descomprimirlo; un idioma sin instalar, antes del OCR."""
    with pytest.raises(ToolError) as err:
        run(TOOL, make_ctx(TOOL, [fixtures_dir / "gigante.png"]))
    assert err.value.code == ErrorCode.LIMIT_EXCEEDED
    with pytest.raises(ToolError) as err:
        run(TOOL, make_ctx(TOOL, [fixtures_dir / "ocr-documento.jpg"], {"idiomas": ["zzz"]}))
    assert err.value.code == ErrorCode.INVALID_OPTIONS
