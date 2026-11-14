"""Muestras de subtítulos para traducir-subtitulos (F3, lote E): SRT, WebVTT y ASS escritos a mano aquí (01-1, regla 8),
con tildes y eñes, etiquetas de estilo, un diálogo con guiones, una nota musical sin texto, un SRT en Windows-1252 y,
en el ASS, estilos, una posición fija, un comentario y un dibujo vectorial que no se traducen."""
from __future__ import annotations

import sys
from pathlib import Path

SRT = """1
00:00:01,000 --> 00:00:03,200
<i>Buenos días a todos.</i>

2
00:00:03,500 --> 00:00:06,000
Hoy vamos a hablar del presupuesto
y de la nueva página web.

3
00:00:06,400 --> 00:00:08,000
- ¿Llegará a tiempo?
- Sí, el viernes.

4
00:00:08,500 --> 00:00:09,500
♪ ♪

5
00:00:10,000 --> 00:00:12,750
El diseño tiene que ser <b>más</b> sencillo, señor Muñoz.

6
00:01:05,000 --> 00:01:07,000
Gracias por venir.

"""

VTT = """WEBVTT
Kind: captions

NOTE Muestra de traducir-subtitulos: esta nota no es un subtítulo.

STYLE
::cue { color: yellow }

intro
00:00.500 --> 00:02.000 align:start position:10%
Bienvenidos a la reunión.

00:02.500 --> 00:04.000
La señal empieza a las diez.

00:04.500 --> 00:06.000
¿Alguna pregunta?

"""

ASS = """[Script Info]
; Muestra de traducir-subtitulos
Title: Prueba
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1
Style: Cartel,Georgia,40,&H0000FFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,2,8,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Bienvenidos a la reunión anual.
Dialogue: 0,0:00:03.50,0:00:05.00,Cartel,,0,0,0,,{\\an8}Sala de juntas
Comment: 0,0:00:05.00,0:00:06.00,Default,,0,0,0,,Nota del traductor: no traducir
Dialogue: 0,0:00:05.50,0:00:07.00,Default,,0,0,0,,{\\p1}m 0 0 l 100 0 100 100 0 100{\\p0}
Dialogue: 0,0:00:07.50,0:00:09.00,Default,,0,0,0,,{\\i1}Empezamos con el primer punto.{\\i0}
"""


def generate(out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    files = {"reunion.srt": out / "reunion.srt", "reunion.vtt": out / "reunion.vtt", "reunion.ass": out / "reunion.ass",
             "antiguo.srt": out / "antiguo.srt"}
    files["reunion.srt"].write_text(SRT, encoding="utf-8")
    files["reunion.vtt"].write_text(VTT, encoding="utf-8")
    files["reunion.ass"].write_text(ASS, encoding="utf-8-sig")
    files["antiguo.srt"].write_bytes(SRT.replace("\n", "\r\n").encode("cp1252", errors="replace"))
    return files


if __name__ == "__main__":
    for name, path in generate(Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/generated")).items():
        print(f"{name}: {path}")
