"""Muestras de pdf-a-audio (F3, lote D) y la voz sintética de las pruebas de transcripción (D-114).

Los PDF se hacen con fpdf2 (LGPL-3.0, lo instala OCRmyPDF; solo para las muestras, 01-1 regla 8) y la fuente DejaVu:
texto en español y en inglés con cabecera repetida y número de página en cada hoja, uno largo que pasa del límite de
caracteres del plan gratuito (9.3) y uno escaneado (una imagen sin capa de texto) que tiene que pasar por el OCR.

`synthetic_speech` lee un texto con el mismo motor que pdf-a-audio (espeak-ng y Kokoro) y lo guarda como OGG Opus: es la
voz sintética que piden las muestras de transcribir-audio, traducir-subtitulos y resumir-reunion (D-114). Necesita
espeak-ng, FFmpeg y el modelo en `KOKORO_HOME` (infra/kokoro/fetch-model.sh).

Uso: python scripts/fixtures/lectura_pdf.py <directorio>   ·   python scripts/fixtures/lectura_pdf.py --voz <es|en> <texto> <salida.ogg>
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]

ES = [
    ["El informe anual resume la actividad de la cooperativa durante el último ejercicio. Las ventas crecieron un doce "
     "por ciento y la plantilla pasó de cuarenta a cincuenta y dos personas.",
     "La nueva planta de Zaragoza empezó a funcionar en marzo. Desde entonces, los pedidos se preparan en la mitad de "
     "tiempo y los envíos llegan antes a los clientes del norte."],
    ["¿Qué esperamos del año que viene? Abrir dos tiendas en Valencia y en Sevilla, y reducir el consumo de energía con "
     "placas solares en todas las naves.",
     "El consejo propone repartir una parte de los beneficios entre los socios y reservar el resto para inversiones."],
    ["Por último, queremos dar las gracias a todas las personas que han hecho posible este año tan bueno para la "
     "cooperativa."],
]
EN = [
    ["The annual report summarises the work of the cooperative during the last financial year. Sales grew by twelve "
     "percent and the team went from forty to fifty two people.",
     "The new warehouse in Leeds opened in March. Since then, orders are packed in half the time and parcels reach "
     "customers in the north sooner."],
    ["What do we expect next year? We plan to open two shops in Bristol and York, and to cut our energy use with solar "
     "panels on every building.",
     "The board proposes to share part of the profit among the members and to keep the rest for new investments."],
    ["Finally, we would like to thank everyone who made this such a good year for the cooperative."],
]


def _font_path() -> str:
    for p in FONTS:
        if Path(p).exists():
            return p
    raise FileNotFoundError("Sin fuente TrueType para las muestras (fonts-dejavu)")


def prose_pdf(path: Path, pages: list[list[str]], header: str | None = None, numbers: str | None = None,
              title: str | None = None) -> Path:
    """Un PDF con varios párrafos por página, separados por un espacio; `numbers` es el formato del pie («{n}»,
    «Página {n} de {total}»)."""
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_font("dejavu", "", _font_path())
    for i, paragraphs in enumerate(pages):
        pdf.add_page()
        pdf.set_font("dejavu", size=9)
        if header:
            pdf.set_xy(20, 12)
            pdf.cell(0, 6, header)
        pdf.set_xy(20, 30)
        if title and i == 0:
            pdf.set_font("dejavu", size=16)
            pdf.multi_cell(170, 9, title)
            pdf.ln(6)
        pdf.set_font("dejavu", size=11)
        for para in paragraphs:
            pdf.set_x(20)
            pdf.multi_cell(170, 6, para)
            pdf.ln(5)
        if numbers:
            pdf.set_xy(20, 280)
            pdf.set_font("dejavu", size=9)
            pdf.cell(170, 6, numbers.format(n=i + 1, total=len(pages)), align="C")
    pdf.output(str(path))
    return path


def scanned_reading_pdf(path: Path, work: Path) -> Path:
    """Una página escaneada (imagen sin texto) con dos frases en inglés, para la etapa de OCR."""
    import img2pdf
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("L", (2480, 1754), 255)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(_font_path(), 90)
    draw.text((180, 420), "The library opens every morning at nine.", fill=0, font=font)
    draw.text((180, 700), "Children can borrow three books each week.", fill=0, font=font)
    png = work / "lectura-escaneada.png"
    img.save(png, dpi=(300, 300))
    path.write_bytes(img2pdf.convert(str(png)))
    png.unlink()
    return path


def generate(out: Path) -> dict[str, Path]:
    work = out / "_tmp"
    work.mkdir(parents=True, exist_ok=True)
    long_page = [" ".join([EN[0][0], EN[0][1], EN[1][0], EN[1][1]]) for _ in range(2)]
    return {
        "lectura-es.pdf": prose_pdf(out / "lectura-es.pdf", ES, "Cooperativa del Norte · Informe anual 2026", "Página {n} de {total}",
                                    "Informe anual"),
        "lectura-en.pdf": prose_pdf(out / "lectura-en.pdf", EN, "Northern Cooperative · Annual report 2026", "{n}", "Annual report"),
        # Unos 22.000 caracteres en inglés: más que los 20.000 por tarea del plan gratuito (9.3).
        "lectura-larga.pdf": prose_pdf(out / "lectura-larga.pdf", [long_page] * 25, None, "{n}"),
        "lectura-escaneada.pdf": scanned_reading_pdf(out / "lectura-escaneada.pdf", work),
    }


def synthetic_speech(text: str, lang: str, dst: Path, kokoro_home: Path, voice: str | None = None, work: Path | None = None) -> Path:
    """Voz sintética de `text` en OGG Opus mono de 24 kbps, con espeak-ng y Kokoro (el motor de pdf-a-audio)."""
    root = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(root / "packages/core"), str(root / "packages/tools")]
    import numpy as np

    from core.settings import Settings
    from tools.av import kokoro, lectura

    settings = Settings(KOKORO_HOME=kokoro_home)
    work = work or dst.parent
    name = voice or {"es": "ef_dora", "en": "af_heart"}[lang]
    model = kokoro.load_model(settings, 2)
    style = kokoro.load_voice(kokoro.voice_path(settings, name, lang))
    audio = []
    for para in lectura.paragraphs([text], skip_furniture=False):
        sentences = [lectura.clauses(s) for s in lectura.sentences(para)]
        ps = iter(kokoro.phonemes([c for s in sentences for c in s], lang, work))
        for ids in kokoro.chunks(model, [[(next(ps), c.mark) for c in s] for s in sentences]):
            audio.append(kokoro.synthesize(model, style, ids, 1.0))
            audio.append(np.zeros(int(0.3 * kokoro.SAMPLE_RATE), dtype=np.float32))
    pcm = work / f"{dst.stem}.pcm"
    pcm.write_bytes((np.clip(np.concatenate(audio), -1, 1) * 32767).astype("<i2").tobytes())
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "s16le", "-ar", str(kokoro.SAMPLE_RATE), "-ac", "1", "-i",
                    str(pcm), "-c:a", "libopus", "-b:a", "24k", "-y", str(dst)], check=True)
    pcm.unlink()
    return dst


if __name__ == "__main__":
    import os

    if sys.argv[1:2] == ["--voz"]:
        print(synthetic_speech(sys.argv[3], sys.argv[2], Path(sys.argv[4]), Path(os.environ.get("KOKORO_HOME", "/opt/models/kokoro"))))
    else:
        target = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/generated")
        target.mkdir(parents=True, exist_ok=True)
        for k, v in generate(target).items():
            print(f"{k}: {v}")
