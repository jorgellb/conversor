"""Paquetes de Debian que no pueden entrar en ninguna imagen (11, D-49, D-111 y D-267).

``scripts/check_images.sh`` lo comprueba sobre las imágenes construidas; esto lo adelanta sobre el Dockerfile, sin
Docker. pst-utils depende de libgd3, que trae libheif1 y con ella libx265 (GPL): de pst-utils solo se copia readpst.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNED = {"pst-utils", "libgd3", "libheif1", "libheif-dev", "libx264-dev", "libx265-dev", "ghostscript", "mupdf-tools",
          "ffmpeg", "libavcodec-dev", "python3-fitz", "python3-pymupdf"}
BANNED_PREFIX = ("libx264-", "libx265-", "libavcodec", "libgs10", "libgs-")  # libgs es Ghostscript; libgsf no


def _installed(dockerfile: str) -> set[str]:
    text = re.sub(r"\\\n", " ", dockerfile)
    pkgs: set[str] = set()
    for m in re.finditer(r"apt-get install ([^&;]+)", text):
        pkgs |= {w for w in m.group(1).split() if not w.startswith("-") and not w.startswith("$")}
    return pkgs


def test_no_banned_debian_packages_are_installed():
    pkgs = set()
    for f in ("workers/Dockerfile", "apps/web/Dockerfile"):
        pkgs |= _installed((ROOT / f).read_text(encoding="utf-8"))
    assert "libpst4" in pkgs and "djvulibre-bin" in pkgs  # el analizador ve los paquetes de verdad
    bad = sorted(p for p in pkgs if p in BANNED or p.startswith(BANNED_PREFIX))
    assert bad == []


def test_readpst_comes_alone_from_its_own_stage():
    text = (ROOT / "workers/Dockerfile").read_text(encoding="utf-8")
    assert "apt-get download pst-utils" in text and "COPY --from=readpst /out/readpst /usr/bin/readpst" in text
