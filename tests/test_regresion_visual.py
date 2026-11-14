"""Regresión visual de 16.1: los PDF de folleto-pdf, varias-paginas-por-hoja, numerar-paginas-pdf y marca-de-agua-pdf.

Las cuatro herramientas se ejecutan en el navegador (pdf-lib), así que los PDF salen del mismo código con Vitest
(packages/client-tools/test/visual-pdfs.test.ts, muestra fija y fuentes Noto de la web). Aquí se pasan a PNG con
pypdfium2 y se comparan píxel a píxel con las referencias de tests/visual/pdf/ con un umbral (D-144).

Para regenerar las referencias después de un cambio querido: ACTUALIZAR_CAPTURAS=1 .venv/bin/pytest tests/test_regresion_visual.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

pdfium = pytest.importorskip("pypdfium2")

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "packages" / "client-tools"
VITEST = ROOT / "node_modules" / ".bin" / "vitest"
REFS = ROOT / "tests" / "visual" / "pdf"
SLUGS = ["folleto-pdf", "varias-paginas-por-hoja", "numerar-paginas-pdf", "marca-de-agua-pdf"]

# 108 ppp (escala 1,5): los números de página de 14 pt ocupan varios cientos de píxeles.
SCALE = 1.5
# Un píxel cuenta como distinto si algún canal cambia más de 32 de 255 (suavizado de bordes aparte).
CHANNEL_TOLERANCE = 32
# Proporción máxima de píxeles distintos por página: 0,01 % (unos 120 píxeles en una cara A4).
MAX_DIFF_RATIO = 0.0001

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not VITEST.exists(),
    reason="sin Node o sin node_modules (npm ci) para generar los PDF con el código del navegador",
)


def diff_ratio(a: Image.Image, b: Image.Image) -> float:
    """Proporción de píxeles con algún canal que difiere más de CHANNEL_TOLERANCE (1.0 si cambia el tamaño)."""
    if a.size != b.size:
        return 1.0
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    channels = [c.point(lambda v: 255 if v > CHANNEL_TOLERANCE else 0) for c in diff.split()]
    mask = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    changed = mask.histogram()[255]
    return changed / (a.size[0] * a.size[1])


def render(pdf: Path) -> list[Image.Image]:
    doc = pdfium.PdfDocument(str(pdf))
    try:
        return [doc[i].render(scale=SCALE).to_pil().convert("RGB") for i in range(len(doc))]
    finally:
        doc.close()


@pytest.fixture(scope="module")
def generated(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("visual-pdf")
    env = {**os.environ, "VISUAL_PDF_DIR": str(out)}
    proc = subprocess.run([str(VITEST), "run", "test/visual-pdfs.test.ts"], cwd=CLIENT, env=env,
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    return out


@pytest.mark.parametrize("slug", SLUGS)
def test_pdf_como_la_referencia(generated: Path, slug: str):
    pages = render(generated / f"{slug}.pdf")
    if os.environ.get("ACTUALIZAR_CAPTURAS") == "1":
        REFS.mkdir(parents=True, exist_ok=True)
        for old in REFS.glob(f"{slug}-p*.png"):
            old.unlink()
        for i, img in enumerate(pages, start=1):
            img.save(REFS / f"{slug}-p{i}.png", optimize=True)
    refs = sorted(REFS.glob(f"{slug}-p*.png"), key=lambda p: int(p.stem.rsplit("-p", 1)[1]))
    assert refs, f"faltan las referencias de {slug} en {REFS}"
    assert len(pages) == len(refs), f"{slug}: {len(pages)} páginas y {len(refs)} referencias"
    for img, ref in zip(pages, refs):
        ratio = diff_ratio(img, Image.open(ref))
        assert ratio <= MAX_DIFF_RATIO, f"{ref.name}: {ratio:.4%} de píxeles distintos (máximo {MAX_DIFF_RATIO:.2%})"


def test_el_umbral_detecta_un_cambio_pequeno():
    """El comparador no es tan permisivo como para dejar pasar un número de página movido o ausente."""
    ref = Image.open(REFS / "numerar-paginas-pdf-p1.png").convert("RGB")
    assert diff_ratio(ref, ref.copy()) == 0
    changed = ref.copy()
    # Un recuadro de 12 × 12 píxeles (como un dígito de 14 pt a 108 ppp) basta para fallar.
    ImageDraw.Draw(changed).rectangle([100, 100, 111, 111], fill=(0, 0, 0))
    assert diff_ratio(ref, changed) > MAX_DIFF_RATIO
    assert diff_ratio(ref, ref.resize((ref.width - 1, ref.height))) == 1.0
