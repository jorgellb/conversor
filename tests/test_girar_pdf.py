"""girar-pdf en el servidor (A.4, D-261): el giro manual igual que en el navegador y «autoorientar» con Tesseract."""
from __future__ import annotations

import shutil

import pikepdf
import pytest

from test_tools import make_ctx, run  # noqa: F401  (fixture)


def _rotations(path) -> list[int]:
    with pikepdf.open(path) as pdf:
        return [int(p.obj.get("/Rotate", 0)) % 360 for p in pdf.pages]


def test_manual_rotation_matches_the_browser(make_ctx, fixtures_dir, tmp_path):
    out = run("girar-pdf", make_ctx("girar-pdf", [fixtures_dir / "escaneado.pdf"], {"angulo": -90, "por_pagina": {"1": 180}}))
    rotations = _rotations(out[0]["path"])
    assert rotations[0] == 180 and all(r == 270 for r in rotations[1:])
    assert out[0]["note"] is None


@pytest.mark.skipif(not shutil.which("tesseract"), reason="sin Tesseract")
def test_autoorient_straightens_sideways_and_upside_down_pages(make_ctx, fixtures_dir, tmp_path):
    src = tmp_path / "torcido.pdf"
    with pikepdf.open(fixtures_dir / "escaneado.pdf") as pdf:
        pdf.pages[0].rotate(90, relative=True)  # de lado
        if len(pdf.pages) > 1:
            pdf.pages[1].rotate(180, relative=True)  # del revés
        pdf.save(src)
    before = _rotations(src)
    out = run("girar-pdf", make_ctx("girar-pdf", [src], {"autoorientar": True}))
    after = _rotations(out[0]["path"])
    assert after[0] == 0, (before, after)
    if len(after) > 1:
        assert after[1] == 0, (before, after)
    assert "Autoorientar" in out[0]["note"]
    again = run("girar-pdf", make_ctx("girar-pdf", [__import__("pathlib").Path(out[0]["path"])], {"autoorientar": True}))
    assert again[0]["note"].startswith("Autoorientar: todas las páginas ya estaban derechas")
