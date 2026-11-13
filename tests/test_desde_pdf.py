"""F2, lote D1: desde PDF sin Docling (A.5, A.6 y A.9).

pdf-a-tiff, pdf-a-svg, pdf-a-webp, CMYK, pdf-a-txt, pdf-a-pdfa y validar-pdfa. veraPDF se simula con un informe MRR
cuando no está instalado; la prueba con veraPDF real se omite y la ejecuta la CI.
"""
from __future__ import annotations

import dataclasses
import os
import re
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path

import pikepdf
import pytest
from PIL import Image

from core.errors import ToolError
from core.registry import load_registry
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida

needs_tiff = pytest.mark.skipif(not (shutil.which("tiffcp") and shutil.which("tiffinfo")), reason="libtiff-tools no instalado")
needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no instalado")
CMYK_PROFILE = Path("/usr/share/color/icc/colord/FOGRA39L_coated.icc")


def _tiffinfo(path: str) -> str:
    return subprocess.run(["tiffinfo", path], capture_output=True, text=True, check=True).stdout


def _pages(path: str) -> int:
    with pikepdf.open(path) as pdf:
        return len(pdf.pages)


# --- pdf-a-tiff ---------------------------------------------------------------------------------------------------


@needs_tiff
def test_tiff_black_and_white_g4_multipage(make_ctx, fixtures_dir):
    src = fixtures_dir / "texto.pdf"
    out = run("pdf-a-tiff", make_ctx("pdf-a-tiff", [src], {"color": "bn", "dpi": 100}))
    assert out[0]["name"] == "texto.tif"
    info = _tiffinfo(out[0]["path"])
    assert info.count("Compression Scheme: CCITT Group 4") == _pages(src)
    assert "Photometric Interpretation: min-is-white" in info and "Resolution: 100, 100 pixels/inch" in info
    with Image.open(out[0]["path"]) as img:
        gray = img.convert("L")
        histogram = gray.histogram()
        assert histogram[255] > histogram[0] > 0  # texto negro sobre fondo blanco, no al revés


@needs_tiff
@pytest.mark.parametrize(("mode", "expected"), [("g3_2d", "CCITT Group 3"), ("g3_1d_eol", "CCITT Group 3"), ("packbits", "PackBits"),
                                                ("lzw", "LZW")])
def test_tiff_black_and_white_compressions(make_ctx, fixtures_dir, mode, expected):
    out = run("pdf-a-tiff", make_ctx("pdf-a-tiff", [fixtures_dir / "texto.pdf"], {"color": "bn", "compresion_bn": mode, "paginas": "1"}))
    info = _tiffinfo(out[0]["path"])
    assert f"Compression Scheme: {expected}" in info
    if mode == "g3_2d":
        assert re.search(r"Group 3 Options:.*2-d encoding", info)
    if mode == "g3_1d_eol":
        assert re.search(r"Group 3 Options:.*EOL padding", info)


@needs_tiff
@pytest.mark.skipif(not CMYK_PROFILE.exists(), reason="colord-data no instalado")
def test_tiff_cmyk_with_icc_profile(make_ctx, fixtures_dir, monkeypatch):
    ctx = make_ctx("pdf-a-tiff", [fixtures_dir / "fotos.pdf"], {"color": "cmyk", "paginas": "1", "dpi": 72})
    out = run("pdf-a-tiff", dataclasses.replace(ctx, settings=ctx.settings.model_copy(update={"CMYK_ICC_PROFILE": str(CMYK_PROFILE)})))
    info = _tiffinfo(out[0]["path"])
    assert "Photometric Interpretation: separated" in info and "Compression Scheme: LZW" in info and "ICC Profile" in info
    with Image.open(out[0]["path"]) as img:
        assert img.mode == "CMYK" and img.info["icc_profile"] == CMYK_PROFILE.read_bytes()


@needs_tiff
def test_tiff_one_file_per_page_or_one_tall_image(make_ctx, fixtures_dir):
    src = fixtures_dir / "texto.pdf"
    out = run("pdf-a-tiff", make_ctx("pdf-a-tiff", [src], {"multipagina": False, "color": "gris", "dpi": 72}))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        assert sorted(zf.namelist()) == sorted(f"texto-{i}.tif" for i in range(1, _pages(src) + 1))
    out = run("pdf-a-tiff", make_ctx("pdf-a-tiff", [src], {"salida": "una_sola", "dpi": 72}))
    with Image.open(out[0]["path"]) as img, pikepdf.open(src) as pdf:
        heights = sum(round(float(p.mediabox[3] - p.mediabox[1])) for p in pdf.pages)
        assert img.n_frames == 1 and abs(img.height - heights) <= len(pdf.pages)


# --- pdf-a-svg, pdf-a-webp y CMYK en JPG ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("pdftocairo") is None, reason="poppler-utils no instalado")
def test_svg_one_file_per_page(make_ctx, fixtures_dir):
    src = fixtures_dir / "texto.pdf"
    out = run("pdf-a-svg", make_ctx("pdf-a-svg", [src]))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        names = sorted(zf.namelist())
        assert names == sorted(f"texto-{i}.svg" for i in range(1, _pages(src) + 1))
        assert zf.read(names[0]).lstrip().startswith(b"<?xml") and b"<svg" in zf.read(names[0])
    out = run("pdf-a-svg", make_ctx("pdf-a-svg", [src], {"paginas": "2"}))
    assert out[0]["name"] == "texto-2.svg"


def test_webp_server_side_and_registry(make_ctx, fixtures_dir):
    out = run("pdf-a-webp", make_ctx("pdf-a-webp", [fixtures_dir / "texto.pdf"], {"paginas": "1", "dpi": 72}))
    with Image.open(out[0]["path"]) as img:
        assert img.format == "WEBP"
    spec = load_registry().require("pdf-a-webp")
    assert spec.where == "hybrid" and spec.outputs[0] == "webp"


@pytest.mark.skipif(not CMYK_PROFILE.exists(), reason="colord-data no instalado")
def test_jpg_cmyk_embeds_the_profile(make_ctx, fixtures_dir):
    ctx = make_ctx("pdf-a-jpg", [fixtures_dir / "fotos.pdf"], {"color": "cmyk", "paginas": "1", "dpi": 72})
    out = run("pdf-a-jpg", dataclasses.replace(ctx, settings=ctx.settings.model_copy(update={"CMYK_ICC_PROFILE": str(CMYK_PROFILE)})))
    with Image.open(out[0]["path"]) as img:
        assert img.mode == "CMYK" and img.info.get("icc_profile") == CMYK_PROFILE.read_bytes()


# --- pdf-a-txt ----------------------------------------------------------------------------------------------------


def test_txt_from_text_layer_and_routes(make_ctx, fixtures_dir):
    out = run("pdf-a-txt", make_ctx("pdf-a-txt", [fixtures_dir / "texto.pdf"], {"ocr_si_no_hay_texto": False}))
    text = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert "Hola mundo" in text and "\f" in text and out[0]["note"] is None
    out = run("pdf-a-txt", make_ctx("pdf-a-txt", [fixtures_dir / "texto.pdf"], {"separador": "linea", "ocr_si_no_hay_texto": False}))
    assert "--- Página 2 ---" in Path(out[0]["path"]).read_text(encoding="utf-8")
    spec = load_registry().require("pdf-a-txt")
    assert spec.target({"ocr_si_no_hay_texto": True}) == ("ocr", "ocr")
    assert spec.target({"ocr_si_no_hay_texto": False}) == ("pdf", "pdf")


def test_txt_without_ocr_points_to_ocr(make_ctx, fixtures_dir):
    out = run("pdf-a-txt", make_ctx("pdf-a-txt", [fixtures_dir / "escaneado.pdf"], {"ocr_si_no_hay_texto": False}))
    assert out[0]["note"].startswith("Páginas sin texto: 1.")


@needs_tesseract
def test_txt_ocr_only_on_scanned_pages_counts_as_ocr_task(make_ctx, fixtures_dir):
    charged: list[str] = []
    ctx = dataclasses.replace(make_ctx("pdf-a-txt", [fixtures_dir / "escaneado.pdf", fixtures_dir / "texto.pdf"]), charge=charged.append)
    out = run("pdf-a-txt", ctx)
    assert charged == ["heavy"]  # una tarea de OCR por trabajo, aunque haya varios archivos
    assert "Factura" in Path(out[0]["path"]).read_text(encoding="utf-8") and out[0]["note"] == "Páginas leídas con OCR: 1."
    assert out[1]["note"] is None and out[-1]["name"] == "pdf-txt.zip"


def test_txt_without_ocr_quota_delivers_text_with_note(make_ctx, fixtures_dir):
    def no_quota(cost_class: str) -> None:
        raise ToolError("QUOTA_EXCEEDED")

    ctx = dataclasses.replace(make_ctx("pdf-a-txt", [fixtures_dir / "escaneado.pdf"]), charge=no_quota, locale="en")
    out = run("pdf-a-txt", ctx)
    assert out[0]["note"] == "No OCR on pages 1: you reached the daily limit of OCR tasks."


# --- veraPDF simulado ---------------------------------------------------------------------------------------------


def mrr(compliant: bool, flavour_name: str = "PDF/A-2B validation profile", rules: list[dict] | None = None) -> bytes:
    """Informe MRR como el que escribe `verapdf --format mrr`."""
    rules = rules or []
    body = ""
    for r in rules:
        checks = "".join(f'<check status="failed"><context>root/document[0]/pages[{p}](3 0 obj PDPage)/contentStream[0]</context>'
                         f"<errorMessage>{r.get('message', 'Fallo')}</errorMessage></check>" for p in r.get("pages", []))
        body += (f'<rule specification="{r.get("spec", "ISO 19005-2:2011")}" clause="{r["clause"]}" testNumber="1" status="failed" '
                 f'failedChecks="{r["failed"]}" tags="{r.get("tags", "")}"><description>{r["description"]}</description>'
                 f"<object>{r.get('object', 'PDFont')}</object><test>x</test>{checks}</rule>")
    passed = 140 - len(rules)
    return (f'<?xml version="1.0" encoding="utf-8"?><report><buildInformation><releaseDetails id="core" version="1.30.3" '
            f'buildDate="2026-10-07T13:48:00Z"/></buildInformation><jobs><job><item size="1000"><name>/tmp/x.pdf</name></item>'
            f'<validationReport jobEndStatus="normal" profileName="{flavour_name}" statement="x" isCompliant="{str(compliant).lower()}">'
            f'<details passedRules="{passed}" failedRules="{len(rules)}" passedChecks="900" failedChecks="{sum(r["failed"] for r in rules)}">'
            f"{body}</details></validationReport></job></jobs></report>").encode()


FONT_RULE = {"clause": "6.2.11.4.1", "failed": 3, "pages": [0, 2], "message": "The font program is not embedded",
             "description": "The font programs for all fonts used for rendering within a conforming file shall be embedded"}
META_RULE = {"clause": "6.6.4", "failed": 1, "object": "MainXMPPackage", "tags": "metadata",
             "description": "The PDF/A version and conformance level of a file shall be specified using the PDF/A Identification extension schema"}


@pytest.fixture()
def fake_verapdf(monkeypatch):
    """Sustituye la ejecución de veraPDF (Java) y anota con qué nivel se llamó."""
    calls: list[tuple[str, str]] = []
    result = {"xml": mrr(True)}

    def fake(path: Path, flavour: str, cwd: Path) -> bytes:
        calls.append((Path(path).name, flavour))
        return result["xml"]

    monkeypatch.setattr("tools.ocr.verapdf.run_verapdf", fake)
    return calls, result


@pytest.fixture()
def no_ghostscript(tmp_path, monkeypatch):
    """Un `gs` falso delante en el PATH que deja constancia si alguien lo ejecuta."""
    bindir = tmp_path / "bin-gs"
    bindir.mkdir()
    marker = tmp_path / "gs-ejecutado"
    script = bindir / "gs"
    script.write_text(f"#!/bin/sh\necho \"$@\" >> {marker}\nexit 1\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    return marker


def test_verapdf_report_parsing_and_plain_explanations():
    from tools.ocr import verapdf

    report = verapdf.parse_report(mrr(False, rules=[FONT_RULE, META_RULE]))
    assert not report.compliant and report.failed_rules == 2 and report.failed_checks == 4 and report.version == "1.30.3"
    font = report.rules[0]
    assert font.clause == "6.2.11.4.1" and font.pages == {1, 3} and font.messages == ["The font program is not embedded"]
    assert verapdf.category(font) == "font" and verapdf.category(report.rules[1]) == "metadata"
    page = verapdf.render_html(report, "factura <1>.pdf", "2b", "es")
    assert "Hay fuentes sin incrustar" in page and "factura &lt;1&gt;.pdf" in page and "<td>1, 3</td>" in page
    assert "No cumple" in page and "PDF/A-2b" in page
    english = verapdf.render_html(report, "a.pdf", "2b", "en")
    assert "Some fonts are not embedded" in english and 'lang="en"' in english
    with pytest.raises(ToolError) as err:
        verapdf.parse_report(b"no es XML")
    assert err.value.code == "ENGINE_FAILED"
    encrypted = verapdf.parse_report(b"<report><jobs><job><taskException><exceptionMessage>The PDF is encrypted</exceptionMessage>"
                                     b"</taskException></job></jobs></report>")
    assert not encrypted.compliant and verapdf.category(encrypted.rules[0]) == "security"


# --- pdf-a-pdfa ---------------------------------------------------------------------------------------------------


@needs_tesseract
def test_pdfa_with_unembedded_fonts_fails_with_report_and_never_runs_ghostscript(make_ctx, fixtures_dir, fake_verapdf, no_ghostscript):
    calls, result = fake_verapdf
    result["xml"] = mrr(False, rules=[FONT_RULE])
    out = run("pdf-a-pdfa", make_ctx("pdf-a-pdfa", [fixtures_dir / "texto.pdf"]))
    assert [o["name"] for o in out] == ["informe-texto.html"]
    assert "rasterizar las páginas" in out[0]["note"] and calls == [("texto.pdf", "2b")]
    assert "Hay fuentes sin incrustar" in Path(out[0]["path"]).read_text(encoding="utf-8")
    result["xml"] = mrr(True)
    out = run("pdf-a-pdfa", make_ctx("pdf-a-pdfa", [fixtures_dir / "texto.pdf"], {"rasterizar_si_falla": True}))
    names = [o["name"] for o in out]
    assert names == ["texto-pdfa.pdf", "informe-texto.html", "pdfa.zip"]
    with pikepdf.open(out[0]["path"]) as pdf:
        assert pdf.open_metadata().pdfa_status == "2B"
    assert "rasterizado" in out[0]["note"] and out[0]["note"].endswith("Cumple: PDF/A-2b.")
    assert not no_ghostscript.exists()


@needs_tesseract
def test_pdfa_levels_u_and_a_need_what_they_need(make_ctx, fixtures_dir, fake_verapdf, no_ghostscript):
    calls, _ = fake_verapdf
    out = run("pdf-a-pdfa", make_ctx("pdf-a-pdfa", [fixtures_dir / "escaneado.pdf"], {"nivel": "2u"}))
    with pikepdf.open(out[0]["path"]) as pdf:
        assert pdf.open_metadata().pdfa_status == "2U"
    out = run("pdf-a-pdfa", make_ctx("pdf-a-pdfa", [fixtures_dir / "escaneado.pdf"], {"nivel": "3a"}))
    assert out[0]["note"].startswith("El PDF no está etiquetado: se ha hecho PDF/A-3b en lugar de PDF/A-3a.")
    with pikepdf.open(out[0]["path"]) as pdf:
        assert pdf.open_metadata().pdfa_status == "3B"
    assert calls[-1] == ("escaneado-pdfa.pdf", "3b") and not no_ghostscript.exists()


# --- validar-pdfa -------------------------------------------------------------------------------------------------


def test_validate_uses_declared_level_or_reports_none(make_ctx, fixtures_dir, tmp_path, fake_verapdf):
    calls, result = fake_verapdf
    declared = tmp_path / "declarado.pdf"
    with pikepdf.open(fixtures_dir / "texto.pdf") as pdf:
        with pdf.open_metadata() as meta:
            meta["pdfaid:part"] = "3"
            meta["pdfaid:conformance"] = "U"
        pdf.save(declared)
    result["xml"] = mrr(True)
    out = run("validar-pdfa", make_ctx("validar-pdfa", [declared]))
    assert calls[-1] == ("declarado.pdf", "3u") and out[0]["note"] == "Cumple: PDF/A-3u."
    result["xml"] = mrr(False, rules=[FONT_RULE, META_RULE])
    out = run("validar-pdfa", make_ctx("validar-pdfa", [fixtures_dir / "texto.pdf"]))
    assert calls[-1] == ("texto.pdf", "2b")
    assert out[0]["note"].startswith("El archivo no declara ningún nivel PDF/A ni PDF/UA; se ha comprobado como PDF/A-2b.")
    assert "No cumple: PDF/A-2b (reglas incumplidas: 2; incumplimientos: 4)." in out[0]["note"]
    page = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert "Nivel que declara el archivo" in page and "ninguno" in page
    out = run("validar-pdfa", make_ctx("validar-pdfa", [fixtures_dir / "texto.pdf"], {"perfil": "ua1"}))
    assert calls[-1] == ("texto.pdf", "ua1") and "PDF/UA-1" in out[0]["note"]


@pytest.mark.skipif(shutil.which("verapdf") is None, reason="veraPDF no instalado (la CI lo instala)")
@needs_tesseract
def test_real_verapdf_accepts_the_pdfa_we_produce(make_ctx, fixtures_dir):
    out = run("pdf-a-pdfa", make_ctx("pdf-a-pdfa", [fixtures_dir / "escaneado.pdf"]))
    assert out[0]["note"].endswith("Cumple: PDF/A-2b."), out[0]["note"]
    out = run("validar-pdfa", make_ctx("validar-pdfa", [fixtures_dir / "texto.pdf"], {"perfil": "2b"}))
    assert out[0]["note"].startswith("No cumple: PDF/A-2b")
