"""F6-C (7.13, D-237): epub-a-mobi, epub-a-azw3, mobi-a-epub y azw3-a-epub con Calibre (simulado aquí; real en la CI) y
con el DRM detectado antes; pptx-a-imagenes y pptx-a-video con Gotenberg (simulado) y el FFmpeg real (16.5: duración y códec
con ffprobe)."""
from __future__ import annotations

import json
import sys
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

import pikepdf
import pytest
import respx
from httpx import Response

from core.errors import ToolError
from test_media_tools import _gotenberg
from test_tools import make_ctx, run  # noqa: F401  (fixture)


def _epub(tmp_path: Path, name: str = "libro.epub", encryption: str | None = None) -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", '<?xml version="1.0"?><container><rootfiles><rootfile full-path="c.opf"/></rootfiles></container>')
        zf.writestr("c.opf", '<?xml version="1.0"?><package><metadata/></package>')
        zf.writestr("c1.xhtml", "<html><body><p>Hola</p></body></html>")
        if encryption:
            zf.writestr("META-INF/encryption.xml", encryption)
    return path


def _mobi(tmp_path: Path, encryption: int) -> Path:
    header = bytearray(78)
    header[0:4] = b"Libr"
    header[60:68] = b"BOOKMOBI"
    header[76:78] = struct.pack(">H", 1)
    record_offset = 78 + 8 + 2
    record0 = struct.pack(">HHIHHH", 1, 0, 100, 1, 4096, encryption) + bytes(200)
    path = tmp_path / f"libro-{encryption}.mobi"
    path.write_bytes(bytes(header) + struct.pack(">II", record_offset, 0) + b"\x00\x00" + record0)
    return path


def test_drm_detection(tmp_path):
    from tools.office.libros_formato import has_drm

    fonts = '<encryption><EncryptedData><EncryptionMethod Algorithm="http://www.idpf.org/2008/embedding"/></EncryptedData></encryption>'
    adept = '<encryption><EncryptedData><EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/></EncryptedData></encryption>'
    assert not has_drm(_epub(tmp_path), "epub")
    assert not has_drm(_epub(tmp_path, "f.epub", fonts), "epub")
    assert has_drm(_epub(tmp_path, "d.epub", adept), "epub")
    assert not has_drm(_mobi(tmp_path, 0), "mobi") and has_drm(_mobi(tmp_path, 2), "mobi")
    with pytest.raises(ToolError):
        has_drm(_write(tmp_path, "x.mobi", b"nada"), "mobi")


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_calibre_conversion_args_and_drm_refusal(make_ctx, tmp_path, monkeypatch):
    from tools.office import libros_formato

    seen = {}

    def fake(args, cwd, **kw):
        seen["args"] = args
        Path(args[2]).write_bytes(b"BOOKMOBI convertido")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(libros_formato, "run_engine", fake)
    out = run("epub-a-mobi", make_ctx("epub-a-mobi", [_epub(tmp_path)], {"titulo": "Mi libro", "autor": "Ana"}))
    assert out[0]["name"] == "libro.mobi" and seen["args"][0] == "ebook-convert"
    assert seen["args"][3:7] == ["--title", "Mi libro", "--authors", "Ana"] and "--mobi-file-type" in seen["args"]
    out = run("mobi-a-epub", make_ctx("mobi-a-epub", [_mobi(tmp_path, 0)], {"epub3": False}))
    assert out[0]["name"] == "libro-0.epub" and seen["args"][-2:] == ["--epub-version", "2"]
    with pytest.raises(ToolError) as err:
        run("azw3-a-epub", make_ctx("azw3-a-epub", [_mobi(tmp_path, 2).rename(tmp_path / "x.azw3")]))
    assert err.value.detail == "libro_drm"


def _slides_pdf(tmp_path: Path, pages: int = 3) -> bytes:
    pdf = pikepdf.new()
    for _ in range(pages):
        pdf.add_blank_page(page_size=(720, 405))  # 16:9 en puntos
    path = tmp_path / "s.pdf"
    pdf.save(path)
    return path.read_bytes()


@respx.mock
def test_slides_to_images(make_ctx, tmp_path):
    respx.post(_gotenberg("/forms/libreoffice/convert")).mock(return_value=Response(200, content=_slides_pdf(tmp_path)))
    src = _write(tmp_path, "charla.pptx", b"PK\x03\x04falso")
    out = run("pptx-a-imagenes", make_ctx("pptx-a-imagenes", [src], {"formato": "jpg", "resolucion": 96, "diapositivas": "1,3"}))
    names = [o["name"] for o in out]
    assert names[:2] == ["charla-001.jpg", "charla-003.jpg"] and names[-1] == "diapositivas.zip"
    from PIL import Image

    with Image.open(out[0]["path"]) as img:
        assert img.size == (960, 540) and round(img.info["dpi"][0]) == 96


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="sin FFmpeg")
@pytest.mark.parametrize("fmt,codec", [("webm", "vp9"), ("mp4", "av1")])
@respx.mock
def test_slides_to_video_duration_and_codec(make_ctx, tmp_path, fmt, codec):
    respx.post(_gotenberg("/forms/libreoffice/convert")).mock(return_value=Response(200, content=_slides_pdf(tmp_path)))
    src = _write(tmp_path, "charla.pptx", b"PK\x03\x04falso")
    out = run("pptx-a-video", make_ctx("pptx-a-video", [src], {"segundos": 2, "resolucion": "720", "formato": fmt}))
    assert out[0]["name"] == f"charla.{fmt}"
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height:format=duration", "-of", "json",
                                      out[0]["path"]], capture_output=True, text=True, check=True).stdout)
    stream = info["streams"][0]
    assert stream["codec_name"] == codec and (stream["width"], stream["height"]) == (1280, 720)
    assert abs(float(info["format"]["duration"]) - 6.0) < 0.15


@respx.mock
def test_video_needs_pro_and_slide_limit(make_ctx, tmp_path):
    src = _write(tmp_path, "charla.pptx", b"PK\x03\x04falso")
    with pytest.raises(ToolError) as err:
        run("pptx-a-video", make_ctx("pptx-a-video", [src], plan="free"))
    assert err.value.detail == "video_plan"
    # 61 diapositivas de 60 s pasan de los 60 minutos de vídeo del plan Pro.
    respx.post(_gotenberg("/forms/libreoffice/convert")).mock(return_value=Response(200, content=_slides_pdf(tmp_path, 61)))
    with pytest.raises(ToolError) as err:
        run("pptx-a-video", make_ctx("pptx-a-video", [src], {"segundos": 60}, plan="pro"))
    assert err.value.code == "LIMIT_EXCEEDED"


def _brightness(path: str, at: float) -> float:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", path, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray",
                          "-s", "32x18", "-"], capture_output=True, check=True).stdout
    return sum(raw) / max(1, len(raw))


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="sin FFmpeg")
@pytest.mark.parametrize("fmt,resolution", [("webm", "720"), ("mp4", "1080")])
@respx.mock
def test_slides_with_fades_are_visible_and_av1_fits_at_1080(make_ctx, tmp_path, fmt, resolution):
    """D-243: cada fundido solo actúa en su ventana (antes el vídeo entero salía negro) y AV1 a 1080p cabe en su memoria."""
    respx.post(_gotenberg("/forms/libreoffice/convert")).mock(return_value=Response(200, content=_slides_pdf(tmp_path)))
    src = _write(tmp_path, "charla.pptx", b"PK\x03\x04falso")
    out = run("pptx-a-video", make_ctx("pptx-a-video", [src], {"segundos": 2, "resolucion": resolution, "formato": fmt, "transicion": True}))
    for at in (1.0, 3.0, 5.0):  # mitad de cada diapositiva (blancas)
        assert _brightness(out[0]["path"], at) > 200, at
    assert _brightness(out[0]["path"], 2.0) < 120  # en el cambio, fundido a negro


@respx.mock
def test_slide_limit_counts_only_the_selected_slides(make_ctx, tmp_path):
    from tools.office import diapositivas

    respx.post(_gotenberg("/forms/libreoffice/convert")).mock(return_value=Response(200, content=_slides_pdf(tmp_path, pages=5)))
    src = _write(tmp_path, "charla.pptx", b"PK\x03\x04falso")
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(_slides_pdf(tmp_path, pages=5))
    assert diapositivas._selected(pdf, "1-2", 3) == [0, 1]
    with pytest.raises(ToolError):
        diapositivas._selected(pdf, "", 3)
    pdf.close()


# ——— D-243: correcciones de la revisión de F6-C ———

def _epub_with(tmp_path: Path, name: str, member: str, data: bytes) -> Path:
    path = _epub(tmp_path, name)
    with zipfile.ZipFile(path, "a") as zf:
        zf.writestr(member, data)
    return path


@pytest.mark.parametrize("member,data", [
    ("c2.html", b"<html><body><img src=file:///etc/passwd></body></html>"),
    ("estilo.css", b'@import "/etc/passwd";'),
    ("c3.xhtml", '<html><body><img src="/etc/hostname"/></body></html>'.encode("utf-16")),
    ("c4.xhtml", b'<html><body><a href="%2e%2e/%2e%2e/etc/passwd">x</a></body></html>'),
    ("capitulo.dat", b'<html><body><img src="/proc/1/environ"/></body></html>'),
])
def test_book_check_catches_the_bypasses(tmp_path, member, data):
    from tools.office.libros import check_book

    with pytest.raises(ToolError):
        check_book(_epub_with(tmp_path, f"{member}.epub", member, data), "epub")


def test_drm_detection_variants(tmp_path):
    from tools.office.libros_formato import has_drm

    single = "<encryption><EncryptionMethod Algorithm='http://www.w3.org/2001/04/xmlenc#aes128-cbc'/></encryption>"
    assert has_drm(_epub(tmp_path, "s.epub", single), "epub")
    path = _epub(tmp_path, "u.epub")
    with zipfile.ZipFile(path, "a") as zf:
        zf.writestr("META-INF/Encryption.xml", single.replace("'", '"').encode("utf-16"))
    assert has_drm(path, "epub")


def test_calibre_runs_under_landlock(make_ctx, tmp_path, monkeypatch):
    from tools.office import libros_formato

    seen = {}

    def fake(args, cwd, **kw):
        seen.update(kw)
        Path(args[2]).write_bytes(b"BOOKMOBI convertido")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(libros_formato, "run_engine", fake)
    ctx = make_ctx("mobi-a-epub", [_mobi(tmp_path, 0)])
    run("mobi-a-epub", ctx)
    rules = dict(seen["landlock"])
    assert rules[Path("/usr")] == "rx" and Path("/dev") in rules
    assert not any(str(ctx.settings.FILESTORE_PATH).startswith(str(p)) and p != Path("/") for p in rules if rules[p] != "rw" and str(p) != "/")
    assert all(not str(p).startswith(("/data", "/app", "/run", "/home")) for p in rules if "libro-" not in str(p))


def test_landlock_rules_for_calibre_allow_system_but_not_other_files(tmp_path):
    from tools import sandbox
    from tools.base import run_engine
    from tools.office.libros import calibre_landlock

    try:
        sandbox.abi()
    except Exception:
        pytest.skip("núcleo sin Landlock")
    if sandbox.abi() < 1:
        pytest.skip("núcleo sin Landlock")
    secret = tmp_path / "ajeno" / "secreto.txt"
    secret.parent.mkdir()
    secret.write_text("de otro usuario")
    work = tmp_path / "trabajo"
    work.mkdir()
    script = ("import sys\nprint(open('/etc/hostname').read() != '')\n"
              f"try:\n    open({str(secret)!r}).read(); print('LEAK')\nexcept PermissionError:\n    print('denied')\n")
    res = run_engine(["/usr/bin/python3", "-I", "-c", script], cwd=work, timeout=60, landlock=calibre_landlock(work))
    assert b"denied" in res.stdout and b"LEAK" not in res.stdout
