"""Genera las muestras de prueba (1.8): se crean con herramientas locales y no se distribuyen con el producto.

Uso: python scripts/fixtures/generate.py <directorio>
"""
from __future__ import annotations

import io
import random
import shutil
import subprocess
import sys
from pathlib import Path

import img2pdf
import pikepdf
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
]


def _font(size: int):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def text_pdf(path: Path, pages: int = 3, text: str = "Hola mundo") -> Path:
    pdf = pikepdf.Pdf.new()
    font = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))
    for i in range(pages):
        content = f"BT /F1 24 Tf 72 720 Td ({text} pagina {i + 1}) Tj ET".encode("latin-1")
        page = pikepdf.Page(pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, 595, 842],
                                               Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font)),
                                               Contents=pdf.make_stream(content)))
        pdf.pages.append(page)
    pdf.docinfo["/Title"] = "Documento de prueba"
    pdf.docinfo["/Author"] = "Autor de prueba"
    pdf.save(path)
    return path


def photo(path: Path, size=(2400, 1800), fmt="JPEG", quality=95) -> Path:
    rnd = random.Random(42)
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    for y in range(0, size[1], 6):
        for x in range(0, size[0], 6):
            r = (x * 255 // size[0] + rnd.randint(-40, 40)) % 256
            g = (y * 255 // size[1] + rnd.randint(-40, 40)) % 256
            b = rnd.randint(0, 255)
            draw.rectangle([x, y, x + 6, y + 6], fill=(r, g, b))
    kwargs = {"quality": quality} if fmt in ("JPEG", "WEBP") else {}
    img.save(path, format=fmt, **kwargs)
    return path


def photo_pdf(path: Path, work: Path) -> Path:
    jpgs = [photo(work / f"foto{i}.jpg", fmt="JPEG", quality=97) for i in range(3)]
    path.write_bytes(img2pdf.convert([str(p) for p in jpgs]))
    return path


def scanned_pdf(path: Path, work: Path, text: str = "Factura numero 2026 Madrid") -> Path:
    img = Image.new("L", (2480, 1754), 255)
    draw = ImageDraw.Draw(img)
    draw.text((200, 400), text, fill=0, font=_font(96))
    draw.text((200, 700), "Documento escaneado de prueba", fill=0, font=_font(80))
    png = work / "escaneo.png"
    img.save(png, dpi=(300, 300))
    path.write_bytes(img2pdf.convert(str(png)))
    return path


def encrypted_pdf(path: Path, src: Path, password: str = "secreto123") -> Path:
    with pikepdf.open(src) as pdf:
        pdf.save(path, encryption=pikepdf.Encryption(owner=password + "x", user=password, R=6))
    return path


def audio(path: Path, codec_args: list[str], seconds: int = 3) -> Path:
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    *codec_args, "-y", str(path)], check=True)
    return path


def video_with_audio(path: Path, seconds: int = 2) -> Path:
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=320x240:rate=10",
                    "-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}", "-c:v", "mpeg4", "-c:a", "aac",
                    "-shortest", "-y", str(path)], check=True)
    return path


def docx_with_libreoffice(path: Path, work: Path) -> Path | None:
    soffice = shutil.which("soffice")
    if not soffice:
        return None
    txt = work / "carta.txt"
    txt.write_text("Carta de prueba\n\nEste documento se generó con LibreOffice para las pruebas.\n", encoding="utf-8")
    subprocess.run([soffice, f"-env:UserInstallation=file://{work}/lo", "--headless", "--convert-to", "docx", "--outdir", str(work), str(txt)],
                   check=True, capture_output=True, timeout=180)
    produced = work / "carta.docx"
    if not produced.exists():  # LibreOffice sin Writer (solo libreoffice-core o -calc): sin muestra DOCX, como sin soffice
        return None
    shutil.move(produced, path)
    return path


def generate(out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    work = out / "_tmp"
    work.mkdir(exist_ok=True)
    files = {
        "texto.pdf": text_pdf(out / "texto.pdf"),
        "fotos.pdf": photo_pdf(out / "fotos.pdf", work),
        "escaneado.pdf": scanned_pdf(out / "escaneado.pdf", work),
        "foto.jpg": photo(out / "foto.jpg", size=(1200, 900)),
        "imagen.png": photo(out / "imagen.png", size=(800, 600), fmt="PNG"),
        "imagen.webp": photo(out / "imagen.webp", size=(640, 480), fmt="WEBP", quality=80),
    }
    # Audio y vídeo solo con FFmpeg: el trabajo docling de la CI no lo instala y sus pruebas no los usan; las que sí,
    # se saltan sin FFmpeg (D-156).
    if shutil.which("ffmpeg"):
        files.update({
            "voz.ogg": audio(out / "voz.ogg", ["-c:a", "libvorbis"]),
            "voz.opus": audio(out / "voz.opus", ["-c:a", "libopus"]),
            "audio.m4a": audio(out / "audio.m4a", ["-c:a", "aac"]),
            "video.mp4": video_with_audio(out / "video.mp4"),
        })
    files["cifrado.pdf"] = encrypted_pdf(out / "cifrado.pdf", files["texto.pdf"])
    tiff = out / "multipagina.tiff"
    frames = [Image.new("RGB", (400, 300), c) for c in ("red", "green", "blue")]
    frames[0].save(tiff, save_all=True, append_images=frames[1:], compression="tiff_deflate")
    files["multipagina.tiff"] = tiff
    docx = docx_with_libreoffice(out / "carta.docx", work)
    if docx:
        files["carta.docx"] = docx
    # F4, lote F: DOCX accesible y sin texto alternativo, y un PDF etiquetado, para word-a-pdf-accesible. Solo con
    # python-docx (extra ocr): el paso de muestras de e2e-compose instala pdf y dev, y no las usa (como FFmpeg, D-156).
    try:
        from accesible import generate as accessible_docs
    except ImportError:
        accessible_docs = None
    if accessible_docs is not None:
        files.update(accessible_docs(out))
    # F3, lote C: imágenes con texto, tablas y tickets para imagen-a-texto, imagen-a-excel y ticket-a-excel.
    from imagenes_ocr import generate as ocr_images

    files.update(ocr_images(out))
    # F3, lote D: PDF para leer en voz alta (pdf-a-audio), con cabeceras, números de página, uno largo y uno escaneado.
    from lectura_pdf import generate as reading_pdfs

    files.update(reading_pdfs(out))
    # F3, lote E: subtítulos SRT, VTT y ASS para traducir-subtitulos.
    from subtitulos import generate as subtitle_samples

    files.update(subtitle_samples(out))
    (out / "falso.pdf").write_bytes(b"esto no es un PDF, es texto")
    files["falso.pdf"] = out / "falso.pdf"
    (out / "hls.m3u8").write_text("#EXTM3U\n#EXTINF:1,\nfile:///etc/passwd\n", encoding="utf-8")
    files["hls.m3u8"] = out / "hls.m3u8"
    shutil.rmtree(work, ignore_errors=True)
    return files


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/generated")
    for name, path in generate(target).items():
        print(f"{name}: {path}")
