"""Muestras de F3, lote C (1.8): imágenes con texto, tablas y tickets generadas con Pillow y las fuentes Noto del
repositorio (OFL). No hay datos reales de nadie: comercios, NIF e importes son inventados para las pruebas.

Uso: python scripts/fixtures/imagenes_ocr.py <directorio>
"""
from __future__ import annotations

import random
import struct
import sys
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = Path(__file__).resolve().parents[2] / "apps" / "web" / "public" / "fonts"

DOCUMENTO = ["El señor Muñoz pidió una canción", "en la pequeña aldea de Logroño.", "Año 2026: información útil y rápida."]
CAPTURA = ["Configuración de la cuenta", "Correo electrónico verificado", "Last login: Monday 14 November"]
TABLA = [["Producto", "Unidades", "Precio"], ["Manzanas", "12", "3,50"], ["Peras", "7", "2,10"], ["Naranjas", "1.230", "15,00"]]
# Con tildes y eñes (el idioma del OCR cambia lo que se lee) y códigos postales con un cero delante (se quedan en texto).
TABLA_ACENTOS = [["Población", "Código", "Región"], ["Logroño", "26001", "La Rioja"], ["Cádiz", "11001", "Andalucía"],
                 ["Almería", "04001", "Andalucía"]]
TICKET_ES = {
    "comercio": "FRUTERIA LA HUERTA S.L.", "nif": "B12345678", "fecha": "14/11/2026", "hora": "10:32",
    "lineas": [("PAN DE BARRA", "1", "1,20"), ("LECHE ENTERA 1L", "2", "2,30"), ("MANZANAS 1KG", "1", "2,49")],
    "impuestos": [("4%", "3,37", "0,13"), ("10%", "2,26", "0,23")], "total": "5,99", "pago": "TARJETA",
}
# El de la frutería con conceptos con tildes y eñes: el idioma del OCR cambia lo que se lee (ticket-a-excel).
TICKET_ACENTOS = {
    **TICKET_ES, "comercio": "FRUTERIA LA HUERTA S.L. - LOGROÑO",
    "lineas": [("PIÑA TROPICAL", "1", "1,20"), ("JAMÓN COCIDO", "2", "2,30"), ("LIMÓN ECOLÓGICO", "1", "2,49")],
}
TICKET_EN = {
    "comercio": "CORNER BAKERY LTD", "nif": "VAT GB123456789", "fecha": "11/14/2026", "hora": "08:15",
    "lineas": [("COFFEE LATTE", "1", "3.20"), ("CROISSANT", "2", "4.40")],
    "impuestos": [("20%", "6.33", "1.27")], "total": "7.60", "pago": "CASH",
}


def font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / ("NotoSansMono-Regular.ttf" if mono else "NotoSans-Regular.ttf")), size)


def text_image(lines: list[str], size=(1700, 600), font_size=48, background=255) -> Image.Image:
    img = Image.new("L", size, background)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((100, 100 + i * int(font_size * 2.2)), line, fill=0, font=font(font_size))
    return img


def documento(path: Path) -> Path:
    """Foto de un documento: algo de grano y desenfoque, en JPEG."""
    rnd = random.Random(7)
    img = text_image(DOCUMENTO, size=(1800, 700)).convert("RGB")
    px = img.load()
    for _ in range(6000):
        x, y = rnd.randrange(img.width), rnd.randrange(img.height)
        v = rnd.randint(150, 230)
        px[x, y] = (v, v, v)
    img.filter(ImageFilter.GaussianBlur(0.6)).save(path, format="JPEG", quality=88, dpi=(200, 200))
    return path


def captura(path: Path) -> Path:
    """Captura de pantalla en PNG con transparencia y sin resolución declarada."""
    img = Image.new("RGBA", (1400, 520), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 1400, 520], fill=(250, 250, 252, 255))
    for i, line in enumerate(CAPTURA):
        draw.text((60, 60 + i * 120), line, fill=(20, 20, 30, 255), font=font(44))
    img.save(path, format="PNG")
    return path


def inclinada(path: Path, degrees: float = 4.0) -> Path:
    text_image(DOCUMENTO).rotate(degrees, expand=True, fillcolor=255).save(path, format="PNG")
    return path


def de_lado(path: Path) -> Path:
    """El documento girado 90 grados, para autorrotar."""
    text_image(DOCUMENTO + ["Segunda parte del documento de prueba con más texto."], size=(1800, 800)).rotate(
        90, expand=True, fillcolor=255).save(path, format="PNG")
    return path


def gris_16(path: Path) -> Path:
    """El documento escaneado en gris de 16 bits (I;16), como lo guardan algunos escáneres: tinta gris oscura (no negro
    puro) sobre papel algo gris, valor de 8 bits × 257."""
    img = text_image(DOCUMENTO, size=(1800, 700)).filter(ImageFilter.GaussianBlur(0.6)).point(lambda v: 45 + v * 190 // 255)
    img.convert("I").point(lambda v: v * 257).convert("I;16").save(path, format="PNG", dpi=(300, 300))
    return path


def movil_mpo(path: Path) -> Path:
    """Foto de móvil con mapa de ganancia HDR: un MPO (JPEG con una segunda imagen) guardada de lado con la orientación
    EXIF 6 (hay que girarla 90° en sentido horario para verla derecha)."""
    from PIL import Image as Img

    upright = text_image(DOCUMENTO, size=(1800, 700)).convert("RGB")
    stored = upright.transpose(Img.Transpose.ROTATE_90)  # lo que guarda el sensor; la orientación 6 lo deshace
    exif = Img.Exif()
    exif[0x0112] = 6
    gain = stored.resize((stored.width // 4, stored.height // 4))
    stored.save(path, format="MPO", save_all=True, append_images=[gain], exif=exif, quality=90, dpi=(200, 200))
    return path


def paginas_tiff(path: Path) -> Path:
    pages = [text_image([f"Primera página del fax número {n}"], size=(1600, 400)) for n in (1,)]
    pages.append(text_image(["Segunda página: acción y corrección"], size=(1600, 400)))
    pages[0].save(path, save_all=True, append_images=pages[1:], compression="tiff_deflate", dpi=(300, 300))
    return path


def sin_texto(path: Path) -> Path:
    img = Image.new("RGB", (900, 600))
    draw = ImageDraw.Draw(img)
    for y in range(600):
        draw.line([(0, y), (900, y)], fill=(40 + y // 5, 120, 200 - y // 4))
    img.save(path, format="PNG")
    return path


def tabla(path: Path, grid: bool = True, screenshot: bool = False, rows: list[list[str]] = TABLA) -> Path:
    """Tabla impresa con rejilla (o captura de hoja de cálculo con cabecera gris; o sin líneas)."""
    TABLA = rows  # noqa: N806 - la misma tabla de siempre salvo que se pida otra
    cw, rh, x0, y0 = 380, 90, 80, 160
    img = Image.new("RGB", (x0 * 2 + cw * 3, y0 + rh * len(TABLA) + 120), "white")
    draw = ImageDraw.Draw(img)
    if not screenshot:
        draw.text((x0, 50), "Informe de ventas", fill="black", font=font(52))
    for r, row in enumerate(TABLA):
        top = y0 + r * rh
        if screenshot and r == 0:
            draw.rectangle([x0, top, x0 + cw * 3, top + rh], fill=(225, 225, 225))
        for c, cell in enumerate(row):
            draw.text((x0 + c * cw + 20, top + 20), cell, fill="black", font=font(40))
    if grid:
        for r in range(len(TABLA) + 1):
            draw.line([(x0, y0 + r * rh), (x0 + cw * 3, y0 + r * rh)], fill="black", width=3)
        for c in range(4):
            draw.line([(x0 + c * cw, y0), (x0 + c * cw, y0 + rh * len(TABLA))], fill="black", width=3)
    img.save(path, format="PNG", dpi=(150, 150))
    return path


def tabla_torcida(path: Path) -> Path:
    """La tabla sin rejilla girada 12 grados: Docling no la reconoce y hace falta la IA (imagen-a-excel)."""
    with Image.open(tabla(path.with_name("_tabla-plana.png"), grid=False)) as flat:
        flat.convert("L").rotate(12, expand=True, fillcolor=255).save(path, format="PNG")
    path.with_name("_tabla-plana.png").unlink()
    return path


def tabla_manuscrita(path: Path) -> Path:
    """La misma tabla como escrita a mano: letra cursiva, cada celda girada hasta 14 grados y descolocada, sin líneas.
    Docling no la reconoce como tabla (ni enderezada) e imagen-a-excel tiene que usar la IA."""
    rnd = random.Random(5)
    img = Image.new("L", (1500, 760), 250)
    for r, row in enumerate(TABLA):
        for c, cell in enumerate(row):
            word = Image.new("L", (420, 100), 0)
            ImageDraw.Draw(word).text((10, 20), cell, fill=255, font=ImageFont.truetype(str(FONTS / "NotoSerif-Italic.ttf"),
                                                                                       rnd.randint(38, 54)))
            word = word.rotate(rnd.uniform(-14, 14), expand=True, resample=Image.BICUBIC)
            img.paste(40, (60 + c * 430 + rnd.randint(-90, 90), 120 + r * 140 + rnd.randint(-45, 45)), word)
    img.save(path, format="PNG")
    return path


def ticket(path: Path, data: dict, rotate: float = 0.0, noise: bool = False, labels: dict | None = None) -> Path:
    """Ticket térmico estrecho con letra monoespaciada, IVA desglosado y total."""
    lab = labels or {"qty": "UDS", "total": "TOTAL", "base": "BASE", "tax": "IVA", "pay": "PAGO"}
    lines = [data["comercio"], f"NIF: {data['nif']}", f"{data['fecha']}  {data['hora']}", "-" * 30]
    for name, qty, amount in data["lineas"]:
        lines.append(f"{qty} x {name:<17}{amount:>7}")
    lines.append("-" * 30)
    for rate, base, tax in data["impuestos"]:
        lines.append(f"{lab['tax']} {rate:<4} {lab['base']} {base:>6} {tax:>6}")
    lines += [f"{lab['total']:<22}{data['total']:>8}", f"{lab['pay']}: {data['pago']}"]
    f = font(30, mono=True)
    img = Image.new("L", (640, 120 + 52 * len(lines)), 255)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((30, 50 + i * 52), line, fill=0, font=f)
    if noise:
        rnd = random.Random(3)
        px = img.load()
        for _ in range(4000):
            px[rnd.randrange(img.width), rnd.randrange(img.height)] = rnd.randint(170, 235)
    if rotate:
        img = img.rotate(rotate, expand=True, fillcolor=255)
    img.convert("RGB").save(path, format="JPEG" if path.suffix == ".jpg" else "PNG", **({"quality": 90} if path.suffix == ".jpg" else {}))
    return path


def png_gigante(path: Path, width: int = 40000, height: int = 40000) -> Path:
    """PNG válido que dice medir 40.000 × 40.000 píxeles (1.600 megapíxeles) y ocupa unos kilobytes (16.4)."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = zlib.compressobj(9)
    body = b""
    row = b"\x00" + b"\x00" * width  # gris de 8 bits, filtro 0
    for _ in range(64):  # solo las primeras filas: basta con la cabecera para la bomba
        body += raw.compress(row)
    body += raw.flush()
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", body) + chunk(b"IEND", b""))
    return path


def generate(out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    return {
        "ocr-documento.jpg": documento(out / "ocr-documento.jpg"),
        "ocr-captura.png": captura(out / "ocr-captura.png"),
        "ocr-inclinada.png": inclinada(out / "ocr-inclinada.png"),
        "ocr-de-lado.png": de_lado(out / "ocr-de-lado.png"),
        "ocr-paginas.tiff": paginas_tiff(out / "ocr-paginas.tiff"),
        "ocr-16bits.png": gris_16(out / "ocr-16bits.png"),
        "ocr-movil.jpg": movil_mpo(out / "ocr-movil.jpg"),
        "ocr-sin-texto.png": sin_texto(out / "ocr-sin-texto.png"),
        "tabla.png": tabla(out / "tabla.png"),
        "tabla-hoja.png": tabla(out / "tabla-hoja.png", grid=True, screenshot=True),
        "tabla-acentos.png": tabla(out / "tabla-acentos.png", rows=TABLA_ACENTOS),
        "tabla-sin-rejilla.png": tabla(out / "tabla-sin-rejilla.png", grid=False),
        "tabla-torcida.png": tabla_torcida(out / "tabla-torcida.png"),
        "tabla-manuscrita.png": tabla_manuscrita(out / "tabla-manuscrita.png"),
        "ticket.png": ticket(out / "ticket.png", TICKET_ES),
        "ticket-acentos.png": ticket(out / "ticket-acentos.png", TICKET_ACENTOS),
        "ticket-torcido.jpg": ticket(out / "ticket-torcido.jpg", TICKET_ES, rotate=3, noise=True),
        "ticket-en.png": ticket(out / "ticket-en.png", TICKET_EN, labels={"qty": "QTY", "total": "TOTAL", "base": "NET",
                                                                            "tax": "VAT", "pay": "PAID"}),
        "gigante.png": png_gigante(out / "gigante.png"),
    }


if __name__ == "__main__":
    for name, p in generate(Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/generated")).items():
        print(f"{name}: {p}")
