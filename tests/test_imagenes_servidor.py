"""F5, lote C: imágenes en el servidor (7.11) con los motores reales: libheif, LibRaw (rawpy), psd-tools, vtracer y rembg.

rembg necesita el modelo descargado (`REMBG_HOME`, por defecto /opt/rembg como en la imagen): la CI lo baja con su
SHA-256; si no está, esas pruebas se omiten.
"""
from __future__ import annotations

import dataclasses
import io
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import ExifTags, Image

from core.errors import ToolError
from core.filetype import detect, matches
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida

pytest.importorskip("rawpy")
pytest.importorskip("psd_tools")
pytest.importorskip("vtracer")


def _exif(gps: bool = True, orientation: int = 6) -> Image.Exif:
    e = Image.Exif()
    e[0x010F] = "Producto Demo"
    e[0x0110] = "Movil de prueba"
    e[0x0112] = orientation
    if gps:
        e[ExifTags.IFD.GPSInfo] = {1: "N", 2: (40.0, 25.0, 0.0), 3: "W", 4: (3.0, 42.0, 0.0)}
    return e


def two_colours(w: int = 64, h: int = 48) -> Image.Image:
    img = Image.new("RGB", (w, h), (200, 30, 30))
    img.paste((30, 30, 200), (w // 2, 0, w, h))
    return img


def dng(path: Path, w: int = 64, h: int = 48) -> Path:
    """DNG mínimo (Bayer RGGB de 16 bits sin comprimir) con tifffile: mitad izquierda roja y derecha azul."""
    import tifffile

    cfa = np.zeros((h, w), dtype=np.uint16)
    for y in range(h):
        for x in range(w):
            left = x < w // 2
            r, g, b = (40000, 8000, 4000) if left else (4000, 8000, 40000)
            cfa[y, x] = r if (y % 2 == 0 and x % 2 == 0) else b if (y % 2 == 1 and x % 2 == 1) else g
    identity = (10000, 10000, 0, 10000, 0, 10000, 0, 10000, 10000, 10000, 0, 10000, 0, 10000, 0, 10000, 10000, 10000)
    extratags = [
        (50706, "B", 4, (1, 4, 0, 0), True), (50707, "B", 4, (1, 1, 0, 0), True), (50708, "s", 0, "Producto Demo Cam", True),
        (33421, "H", 2, (2, 2), True), (33422, "B", 4, (0, 1, 1, 2), True), (50714, "H", 1, 0, True), (50717, "H", 1, 65535, True),
        (50721, "2i", 9, identity, True), (50778, "H", 1, 21, True), (50728, "2I", 3, (1, 1, 1, 1, 1, 1), True),
        (271, "s", 0, "Producto Demo", True), (272, "s", 0, "Camara de prueba", True), (274, "H", 1, 1, True),
    ]
    tifffile.imwrite(path, cfa, photometric=32803, extratags=extratags, metadata=None)
    return path


def tiff_with_make(path: Path, make: str) -> Path:
    import tifffile

    tifffile.imwrite(path, np.zeros((8, 8), dtype=np.uint8), extratags=[(271, "s", 0, make, True)], metadata=None)
    return path


# --- Tipo real ------------------------------------------------------------------------------------------------------


def test_detects_psd_psb_and_tiff_raws_only_with_their_signature(tmp_path):
    from psd_tools import PSDImage

    psd = tmp_path / "a.psd"
    PSDImage.frompil(two_colours()).save(psd)
    assert detect(psd, "psd").ext == "psd"
    psb = tmp_path / "b.psb"
    data = bytearray(psd.read_bytes())
    data[5] = 2  # versión 2 = PSB (solo la cabecera)
    psb.write_bytes(bytes(data))
    assert detect(psb, "psb").ext == "psb"
    raw = dng(tmp_path / "foto.dng")
    assert detect(raw, "dng").ext == "dng"
    assert detect(raw, "tiff").ext == "tiff"  # un DNG declarado como TIFF sigue siendo TIFF
    cr2 = tmp_path / "foto.cr2"
    cr2.write_bytes(b"II*\x00\x10\x00\x00\x00CR\x02\x00" + bytes(64))
    assert detect(cr2, "cr2").ext == "cr2"
    nef = tiff_with_make(tmp_path / "foto.nef", "NIKON CORPORATION")
    assert detect(nef, "nef").ext == "nef"
    arw = tiff_with_make(tmp_path / "foto.arw", "SONY")
    assert detect(arw, "arw").ext == "arw"
    fake = tiff_with_make(tmp_path / "falso.nef", "Producto Demo")
    assert detect(fake, "nef").ext == "tiff"
    assert not matches(detect(fake, "nef"), "nef", ("cr2", "nef", "arw", "dng"))


# --- HEIC -----------------------------------------------------------------------------------------------------------

HEIF_TOOLS = shutil.which("heif-enc") and (shutil.which("heif-dec") or shutil.which("heif-convert"))


def heic(tmp_path: Path, name: str = "movil") -> Path | None:
    src = tmp_path / f"{name}.jpg"
    two_colours().save(src, quality=95, exif=_exif())
    dst = tmp_path / f"{name}.heic"
    proc = subprocess.run(["heif-enc", "-q", "80", "-o", str(dst), str(src)], capture_output=True)
    return dst if proc.returncode == 0 and dst.exists() else None


@pytest.mark.skipif(not HEIF_TOOLS, reason="libheif no instalado")
def test_heic_to_jpg_keeps_exif_without_gps_and_with_the_rotation_applied(make_ctx, tmp_path):
    src = heic(tmp_path)
    if src is None:
        pytest.skip("libheif sin codificador HEVC: no se puede crear la muestra")
    out = run("heic-a-jpg", make_ctx("heic-a-jpg", [src], {"calidad": 80}))
    assert out[0]["name"] == "movil.jpg"
    with Image.open(out[0]["path"]) as img:
        assert img.format == "JPEG"
        assert img.size == (48, 64)  # la foto 64×48 con orientación 6 ya viene girada
        exif = img.getexif()
        assert exif[0x010F] == "Producto Demo"
        assert exif.get(0x0112) == 1
        assert not exif.get_ifd(0x8825)
        left = img.convert("RGB").getpixel((24, 4))
        assert left[0] > left[2]  # la mitad roja queda arriba tras el giro
    out = run("heic-a-jpg", make_ctx("heic-a-jpg", [src], {"quitar_gps": False}))
    with Image.open(out[0]["path"]) as img:
        assert img.getexif().get_ifd(0x8825)[1] == "N"
    out = run("heic-a-png", make_ctx("heic-a-png", [src], {"conservar_exif": False}))
    with Image.open(out[0]["path"]) as img:
        assert img.format == "PNG" and img.size == (48, 64)
        assert "exif" not in img.info


# --- RAW ------------------------------------------------------------------------------------------------------------


def test_raw_to_jpg_develops_a_dng_with_libraw_in_a_separate_process(make_ctx, tmp_path):
    src = dng(tmp_path / "toma.dng")
    out = run("raw-a-jpg", make_ctx("raw-a-jpg", [src], {"calidad": 85}))
    assert out[0]["name"] == "toma.jpg"
    with Image.open(out[0]["path"]) as img:
        assert img.format == "JPEG" and img.size == (64, 48)
        rgb = img.convert("RGB")
        left, right = rgb.getpixel((8, 24)), rgb.getpixel((56, 24))
        assert left[0] > left[2] and right[2] > right[0]
        assert img.getexif()[0x0110] == "Camara de prueba"
    half = run("raw-a-jpg", make_ctx("raw-a-jpg", [src], {"tamano": "mitad", "conservar_exif": False}))
    with Image.open(half[0]["path"]) as img:
        assert img.size == (32, 24)
        assert 0x0110 not in img.getexif()


def test_raw_that_libraw_cannot_read_is_corrupt_file(make_ctx, tmp_path):
    bad = tmp_path / "mal.dng"
    bad.write_bytes(b"II*\x00\x08\x00\x00\x00" + bytes(200))
    with pytest.raises(ToolError) as exc:
        run("raw-a-jpg", make_ctx("raw-a-jpg", [bad]))
    assert exc.value.code == "CORRUPT_FILE"


# --- PSD ------------------------------------------------------------------------------------------------------------


def layered_psd(path: Path) -> Path:
    from psd_tools import PSDImage
    from psd_tools.api.layers import PixelLayer

    psd = PSDImage.new("RGBA", (64, 48))
    psd.append(PixelLayer.frompil(Image.new("RGBA", (64, 48), (0, 0, 255, 255)), psd, "Fondo azul"))
    psd.append(PixelLayer.frompil(Image.new("RGBA", (20, 20), (255, 255, 0, 255)), psd, "Cuadro amarillo", top=10, left=10))
    hidden = PixelLayer.frompil(Image.new("RGBA", (8, 8), (0, 255, 0, 255)), psd, "Oculta")
    hidden.visible = False
    psd.append(hidden)
    psd.save(path)
    return path


def test_psd_to_png_whole_image_and_each_visible_layer(make_ctx, tmp_path):
    src = layered_psd(tmp_path / "cartel.psd")
    out = run("psd-a-png", make_ctx("psd-a-png", [src]))
    with Image.open(out[0]["path"]) as img:
        assert img.size == (64, 48)
        assert img.convert("RGB").getpixel((15, 15)) == (255, 255, 0)
        assert img.convert("RGB").getpixel((2, 2)) == (0, 0, 255)
    layers = run("psd-a-png", make_ctx("psd-a-png", [src], {"salida": "capas"}))
    assert layers[0]["name"] == "cartel-capas.zip"
    with zipfile.ZipFile(layers[0]["path"]) as zf:
        assert sorted(zf.namelist()) == ["Cuadro-amarillo.png", "Fondo-azul.png"]  # la capa oculta no va
        with Image.open(io.BytesIO(zf.read("Cuadro-amarillo.png"))) as layer:
            assert layer.size == (20, 20)


# --- Vectorizar -----------------------------------------------------------------------------------------------------


def test_png_and_jpg_to_svg_with_vtracer(make_ctx, tmp_path):
    logo = Image.new("RGBA", (120, 80), (0, 0, 0, 0))
    logo.paste((200, 20, 20, 255), (20, 15, 100, 65))
    src = tmp_path / "logo.png"
    logo.save(src)
    out = run("png-a-svg", make_ctx("png-a-svg", [src]))
    svg = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert out[0]["name"] == "logo.svg"
    assert svg.lstrip().startswith("<?xml") and "<svg" in svg and "<path" in svg
    assert "#C81414" in svg.upper()
    jpg = tmp_path / "foto.jpg"
    two_colours(3000, 1000).save(jpg, quality=90)
    out = run("jpg-a-svg", make_ctx("jpg-a-svg", [jpg], {"colores": "blanco_y_negro", "detalle": "bajo"}))
    svg = Path(out[0]["path"]).read_text(encoding="utf-8")
    fills = {f.upper() for f in __import__("re").findall(r'fill="(#[0-9A-Fa-f]{6})"', svg)}
    assert fills <= {"#000000", "#FFFFFF"}
    assert 'width="2000"' in svg  # se reduce a 2000 px de lado mayor
    assert "2000×667" in out[0]["note"]


# --- Quitar fondo ---------------------------------------------------------------------------------------------------


def _model_home() -> Path | None:
    home = Path(os.environ.get("REMBG_HOME", "/opt/rembg"))
    return home if (home / "models" / "u2net" / "u2net.onnx").is_file() else None


needs_model = pytest.mark.skipif(_model_home() is None, reason="modelo u2net de rembg no descargado")


def subject(path: Path) -> Path:
    """Un disco rojo oscuro sobre un fondo claro con textura suave: objeto destacado y fondo uniforme."""
    rng = np.random.default_rng(7)
    bg = (220 + rng.integers(-8, 8, size=(240, 320, 3))).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(bg, "RGB")
    from PIL import ImageDraw

    ImageDraw.Draw(img).ellipse((100, 60, 220, 180), fill=(150, 20, 20))
    img.save(path, quality=95)
    return path


def test_rembg_refuses_bria_and_missing_models(make_ctx, tmp_path):
    from tools.media import fondo

    from core.settings import Settings

    with pytest.raises(ToolError) as exc:
        fondo.model_path(Settings(REMBG_MODEL="bria-rmbg", REMBG_HOME=tmp_path))
    assert "no admitido" in exc.value.detail
    with pytest.raises(ToolError) as exc:
        fondo.model_path(Settings(REMBG_MODEL="u2net", REMBG_HOME=tmp_path))
    assert "Falta el modelo" in exc.value.detail


@needs_model
def test_remove_background_with_the_configured_model(make_ctx, tmp_path, monkeypatch):
    pytest.importorskip("rembg")
    from core.settings import Settings
    from tools.media import fondo

    settings = Settings(REMBG_MODEL="u2net", REMBG_HOME=_model_home())
    src = subject(tmp_path / "taza.jpg")
    ctx = make_ctx("quitar-fondo", [src], {"recortar": True})
    ctx = dataclasses.replace(ctx, settings=settings)
    out = run("quitar-fondo", ctx)
    assert out[0]["name"] == "taza-sin-fondo.png"
    sess = fondo.session(settings)
    # 16.6: el modelo cargado es el de REMBG_MODEL, nunca bria-rmbg.
    assert sess.__class__.name() == "u2net"
    assert Path(sess.__class__.download_models()).resolve() == (_model_home() / "models/u2net/u2net.onnx").resolve()
    with Image.open(out[0]["path"]) as img:
        assert img.mode == "RGBA"
        w, h = img.size
        assert 120 <= w <= 140 and 120 <= h <= 140  # recortado al disco (120 px) con un pequeño margen
        alpha = img.getchannel("A")
        assert alpha.getpixel((w // 2, h // 2)) > 200
        assert alpha.getpixel((1, 1)) < 60
    coloured = run("quitar-fondo", dataclasses.replace(make_ctx("quitar-fondo", [src], {"formato": "jpg"}), settings=settings))
    assert coloured[0]["name"] == "taza-sin-fondo.jpg"
    assert "fondo va en #FFFFFF" in coloured[0]["note"]
    with Image.open(coloured[0]["path"]) as img:
        assert img.mode == "RGB"
        assert min(img.getpixel((5, 5))) > 235
