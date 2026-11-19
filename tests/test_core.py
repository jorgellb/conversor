"""Pruebas unitarias del núcleo (sin servicios)."""
from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path
import sys

import pytest

from core import secretbox, tokens
from core.envguard import violations
from core.filetype import detect, matches
from core.flags import is_tool_enabled
from core.options import parse_page_ranges
from core.storage import sanitize_filename

ROOT = Path(__file__).resolve().parents[1]


def test_sanitize_filename():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("Factura de Niño (1).pdf") == "Factura-de-Nino-1.pdf"
    name = sanitize_filename("a" * 300 + ".pdf")
    assert len(name) <= 120 and name.endswith(".pdf")
    assert all(c.isalnum() or c in "._-" for c in sanitize_filename("informe final ñ €.docx"))


@pytest.mark.parametrize("spec,total,expected", [
    ("1-3, 5, 8-", 9, [0, 1, 2, 4, 7, 8]),
    ("impares", 5, [0, 2, 4]),
    ("pares", 5, [1, 3]),
    ("todas", 3, [0, 1, 2]),
    ("2", 3, [1]),
])
def test_page_ranges(spec, total, expected):
    assert parse_page_ranges(spec, total) == expected


@pytest.mark.parametrize("spec", ["0", "5-2", "abc", "10"])
def test_page_ranges_invalid(spec):
    with pytest.raises(ValueError):
        parse_page_ranges(spec, 3)


def test_download_tokens():
    t = tokens.sign_download("s", "j", "f.pdf", "own", 60, now=1000)
    assert tokens.verify_download("s", "j", "f.pdf", t, now=1001)
    assert not tokens.verify_download("s", "j", "otro.pdf", t, now=1001)
    assert not tokens.verify_download("s", "j", "f.pdf", t, now=2000)
    assert not tokens.verify_download("otro", "j", "f.pdf", t, now=1001)
    assert not tokens.verify_download("s", "j", "f.pdf", t.replace(".", "x", 1), now=1001)
    # Misma caducidad escrita de otra forma: con la misma firma no vale (la manipulación de e2e-compose, «t=0…»).
    exp, rest = t.split(".", 1)
    for variant in ("0" + t, "+" + t, " " + t, f"{exp[:-1]}_{exp[-1]}.{rest}", f"{exp}.0.{rest}"[: len(t) + 2]):
        assert not tokens.verify_download("s", "j", "f.pdf", variant, now=1001)


def test_anon_tokens():
    t = tokens.issue_anon_token("s", "cliente", 60, now=1000)
    assert tokens.verify_anon_token("s", t, now=1010) == "cliente"
    assert tokens.verify_anon_token("s", t, now=5000) is None
    assert tokens.verify_anon_token("x", t, now=1010) is None


def test_ipv6_grouped_by_64():
    assert tokens.normalize_ip("2001:db8::1") == tokens.normalize_ip("2001:db8::ffff")
    assert tokens.normalize_ip("2001:db8:0:1::1") != tokens.normalize_ip("2001:db8::1")


def test_secretbox_roundtrip():
    sealed = secretbox.seal("k", {"contrasena": "1234"})
    assert "1234" not in sealed
    assert secretbox.open_sealed("k", sealed) == {"contrasena": "1234"}


def test_flags_precedence():
    assert is_tool_enabled("comprimir-pdf", {}, env={})
    assert not is_tool_enabled("comprimir-pdf", {"comprimir-pdf": False}, env={})
    assert not is_tool_enabled("comprimir-pdf", {"comprimir-pdf": True}, env={"TOOL_COMPRIMIR_PDF_ENABLED": "false"})
    assert is_tool_enabled("comprimir-pdf", {"comprimir-pdf": False}, env={"TOOL_COMPRIMIR_PDF_ENABLED": "true"})
    assert not is_tool_enabled("heic-a-pdf", {}, env={})
    assert is_tool_enabled("heic-a-pdf", {}, env={"HEVC_DECODE_ENABLED": "true"})
    # Espacios y mayúsculas como en envFlag de la web (apps/web/test/flags.test.ts); solo espacios es «sin valor».
    assert is_tool_enabled("heic-a-pdf", {}, env={"HEVC_DECODE_ENABLED": " True "})
    assert not is_tool_enabled("comprimir-pdf", {}, env={"TOOL_COMPRIMIR_PDF_ENABLED": "false "})
    assert not is_tool_enabled("comprimir-pdf", {"comprimir-pdf": False}, env={"TOOL_COMPRIMIR_PDF_ENABLED": "   "})


def test_flags_default_enabled_false():
    """D-134: apagada por defecto, la fila de feature_flags no la enciende; solo el entorno."""
    assert not is_tool_enabled("udf-a-pdf", {}, env={}, default=False)
    assert not is_tool_enabled("udf-a-pdf", {"udf-a-pdf": True}, env={}, default=False)
    assert is_tool_enabled("udf-a-pdf", {}, env={"TOOL_UDF_A_PDF_ENABLED": "true"}, default=False)
    assert not is_tool_enabled("udf-a-pdf", {}, env={"TOOL_UDF_A_PDF_ENABLED": "false"}, default=False)
    # Los flags temáticos siguen mandando sobre el entorno de la herramienta.
    assert not is_tool_enabled("crear-factura", {}, env={"TOOL_CREAR_FACTURA_ENABLED": "true"}, default=False)
    # Sin `default`, se lee del registro (todas las de hoy están encendidas por defecto).
    from core.registry import load_registry

    for spec in load_registry().specs:
        assert is_tool_enabled(spec.slug_es, {}, env={}) == (spec.default_enabled and spec.slug_es not in
                                                            {"heic-a-pdf", "heic-a-jpg", "heic-a-png"})


def test_secret_matrix():
    env = {"FILE_TOKEN_SECRET": "x", "JOB_SECRETS_KEY": "y", "OPENROUTER_API_KEY": "z"}
    assert violations("worker-pdf", env) == ["FILE_TOKEN_SECRET", "OPENROUTER_API_KEY"]
    assert violations("worker-ai", {"OPENROUTER_API_KEY": "z"}) == []
    assert violations("api", {"FILE_TOKEN_SECRET": "x"}) == []


def test_registry_does_not_import_engines():
    for mod in ("torch", "docling", "ocrmypdf", "pypdfium2"):
        sys.modules.pop(mod, None)
    from core.registry import load_registry

    load_registry.cache_clear()
    reg = load_registry()
    assert reg.require("comprimir-pdf").runs_on_server
    assert reg.require("compress-pdf") is reg.require("comprimir-pdf")
    for mod in ("torch", "docling", "ocrmypdf"):
        assert mod not in sys.modules



def test_celery_includes_import_without_pdf_or_ai_engines():
    """Todos los workers cargan los include de celeryapp; workerav no trae pikepdf, pypdfium2 ni fastembed."""
    code = textwrap.dedent("""
        import sys
        from importlib.abc import MetaPathFinder

        BLOCKED = {"pikepdf", "pypdfium2", "fastembed", "onnxruntime", "docling", "ocrmypdf"}

        class Block(MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in BLOCKED:
                    raise ModuleNotFoundError(name)

        sys.meta_path.insert(0, Block())
        from core.celeryapp import celery_app
        for mod in celery_app.conf.include:
            __import__(mod)
    """)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(str(ROOT / p) for p in ("packages/core", "packages/tools", "apps/api"))}
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]

def test_filetype_detection(fixtures_dir):
    assert detect(fixtures_dir / "texto.pdf").ext == "pdf"
    assert detect(fixtures_dir / "foto.jpg").ext == "jpg"
    assert detect(fixtures_dir / "imagen.webp").ext == "webp"
    assert detect(fixtures_dir / "multipagina.tiff").ext == "tiff"
    fake = detect(fixtures_dir / "falso.pdf", ".pdf")
    assert not matches(fake, ".pdf", ("pdf",))
    hls = detect(fixtures_dir / "hls.m3u8", ".ogg")
    assert not matches(hls, ".ogg", ("ogg", "opus"))
    if (fixtures_dir / "carta.docx").exists():
        assert detect(fixtures_dir / "carta.docx").ext == "docx"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg no instalado: sin muestras de audio (D-156)")
def test_filetype_detection_audio(fixtures_dir):
    # Con FFmpeg, scripts/fixtures/generate.py tiene que haber creado las muestras: si faltan, la prueba falla.
    assert (fixtures_dir / "voz.ogg").exists() and (fixtures_dir / "voz.opus").exists()
    assert detect(fixtures_dir / "voz.opus").ext == "opus"
    assert detect(fixtures_dir / "voz.ogg").ext == "ogg"


def test_ai_excluded_by_name():
    """6.6 y 16.3: firma, verificación de firmas, contactos, calendario, correo y certificados nunca llegan a la IA."""
    from core.ai import is_excluded

    for slug in ("verificar-firmas-pdf", "solicitar-firmas", "firmar-pdf", "verificar-firma", "csig-a-pdf", "p7m-a-pdf",
                 "xsig-a-pdf", "vcf-a-csv", "ics-a-excel", "mbox-a-pdf", "pst-a-mbox", "eml-a-pdf", "msg-a-pdf"):
        assert is_excluded(slug, "pdf"), slug
    assert is_excluded("cualquiera", "sign")
    for slug in ("resumir-pdf", "traducir-pdf", "chat-pdf", "pdf-a-fichas"):
        assert not is_excluded(slug, "ai"), slug
