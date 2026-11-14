"""Notas de resultado en el idioma de la página (D-42, D-54 y D-151): las herramientas de servidor de F1 y del lote A
de F2 escriben sus avisos con `ctx.locale`, en español por defecto y en inglés para la web en inglés."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pikepdf
import pytest

from test_pdf_f2 import colorful_pdf
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida
from tools.pdf import colores_tools, comprimir_pdf, documento, mantenimiento, proteger_pdf


def _en(ctx):
    return dataclasses.replace(ctx, locale="en")


@pytest.mark.parametrize("module", [documento, colores_tools, mantenimiento, proteger_pdf])
def test_notes_have_the_same_keys_in_both_languages(module):
    assert set(module.NOTES["es"]) == set(module.NOTES["en"])
    assert set(comprimir_pdf.NOTES) == {"es", "en"}


def test_metadata_note_in_english(make_ctx, tmp_path, fixtures_dir):
    src = tmp_path / "meta.pdf"
    with pikepdf.open(fixtures_dir / "texto.pdf") as pdf:
        pdf.docinfo["/Title"] = "Secreto"
        pdf.save(src)
    out = run("eliminar-metadatos-pdf", _en(make_ctx("eliminar-metadatos-pdf", [src])))[0]
    assert out["note"].startswith("Removed: ") and "Title" in out["note"] and "Título" not in out["note"]
    es = run("eliminar-metadatos-pdf", make_ctx("eliminar-metadatos-pdf", [src]))[0]
    assert es["note"].startswith("Quitado: ") and "Título" in es["note"]


def test_compress_note_is_readable_in_both_languages(make_ctx, fixtures_dir):
    en = run("comprimir-pdf", _en(make_ctx("comprimir-pdf", [fixtures_dir / "fotos.pdf"])))[0]
    assert en["note"].startswith("From ") and "% smaller" in en["note"] and "->" not in en["note"]
    es = run("comprimir-pdf", make_ctx("comprimir-pdf", [fixtures_dir / "fotos.pdf"]))[0]
    assert es["note"].startswith("De ") and "% menos" in es["note"]


def test_compress_size_format():
    assert comprimir_pdf._size(1536, "es") == "1,5 KB"
    assert comprimir_pdf._size(3 * 1024 * 1024, "en") == "3.0 MB"
    assert comprimir_pdf._size(900, "es") == "900 B"


def test_protect_note_is_a_sentence_not_a_code(make_ctx, fixtures_dir):
    opts = {"permitir_imprimir": False}
    secrets = {"contrasena_apertura": "abrir123"}
    en = run("proteger-pdf", _en(make_ctx("proteger-pdf", [fixtures_dir / "texto.pdf"], opts, secrets)))[0]
    assert en["note"].startswith("No owner password") and "owner_password_not_kept" not in en["note"]
    es = run("proteger-pdf", make_ctx("proteger-pdf", [fixtures_dir / "texto.pdf"], opts, secrets))[0]
    assert es["note"].startswith("Sin contraseña de propietario")


def test_dark_mode_and_grayscale_notes_in_english(make_ctx, tmp_path):
    src = colorful_pdf(tmp_path / "claro.pdf")
    with pikepdf.open(src, allow_overwriting_input=True) as pdf:
        pdf.add_blank_page(page_size=(400, 400))
        pdf.pages[1].obj.Contents = pdf.make_stream(b"0 0 0 rg 0 0 400 400 re f")
        pdf.save(src)
    dark = run("pdf-modo-oscuro", _en(make_ctx("pdf-modo-oscuro", [src])))[0]
    assert "already dark" in dark["note"] and "2" in dark["note"]
    sep = colorful_pdf(tmp_path / "sep.pdf", separation=True)
    gray = run("pdf-escala-de-grises", _en(make_ctx("pdf-escala-de-grises", [sep])))[0]
    assert gray["note"].startswith("Pages rasterised in grey")


def test_repair_and_extract_images_notes_in_english(make_ctx, tmp_path, fixtures_dir):
    data = (fixtures_dir / "texto.pdf").read_bytes()
    broken = tmp_path / "roto.pdf"
    head, _, _ = data.rpartition(b"startxref")
    broken.write_bytes(head + b"startxref\n999999\n%%EOF\n")
    repaired = run("reparar-pdf", _en(make_ctx("reparar-pdf", [broken])))[0]
    assert repaired["note"].startswith("Rebuilt with qpdf and pikepdf")
    images = run("extraer-imagenes-pdf", _en(make_ctx("extraer-imagenes-pdf", [fixtures_dir / "fotos.pdf"])))
    assert images[-1]["note"].endswith("images extracted.") or "images extracted." in images[-1]["note"]
    assert Path(images[-1]["path"]).exists()
