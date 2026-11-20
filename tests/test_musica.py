"""F6-L (7.13, D-228): MIDI a MP3 y WAV con FluidSynth y FluidR3_GM, y MusicXML y MIDI a PDF con MuseScore 3."""
from __future__ import annotations

import struct
import wave
import zipfile
from pathlib import Path

import pytest

from core.errors import ToolError
from core.settings import get_settings
from test_tools import make_ctx, run  # noqa: F401  (fixture)

needs_fluidsynth = pytest.mark.skipif(not (Path(get_settings().FLUIDSYNTH_BIN).is_file() and Path(get_settings().SOUNDFONT).is_file()),
                                      reason="sin FluidSynth o FluidR3_GM")
needs_mscore = pytest.mark.skipif(not Path(get_settings().MSCORE_BIN).is_file(), reason="sin MuseScore 3")


def midi(notes: list[tuple[int, int]], ppq: int = 480, tempo: int = 500_000) -> bytes:
    """Un MIDI de formato 0 con (nota, duración en negras) en el canal 1 y un cambio de tempo."""
    def vlq(n: int) -> bytes:
        out = [n & 0x7F]
        n >>= 7
        while n:
            out.append((n & 0x7F) | 0x80)
            n >>= 7
        return bytes(reversed(out))

    track = b"\x00\xff\x51\x03" + tempo.to_bytes(3, "big") + b"\x00\xc0\x00"
    for note, beats in notes:
        track += b"\x00\x90" + bytes([note, 100]) + vlq(beats * ppq) + b"\x80" + bytes([note, 0])
    track += b"\x00\xff\x2f\x00"
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, ppq) + b"MTrk" + struct.pack(">I", len(track)) + track


SCALE = [(60, 1), (62, 1), (64, 1), (65, 1), (67, 2)]  # 6 negras a 120 por minuto: 3 s


def _write(tmp_path: Path, name: str, data: bytes | str) -> Path:
    path = tmp_path / name
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def test_midi_duration_and_limits():
    from tools.av.midi import duration

    assert duration(midi(SCALE)) == pytest.approx(3.0)
    assert duration(midi(SCALE, tempo=1_000_000)) == pytest.approx(6.0)
    with pytest.raises(ToolError):
        duration(b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x01\xe0MTrk\x00\x00\x00\x02\x00\x90")


@needs_fluidsynth
def test_midi_to_wav_and_mp3(make_ctx, tmp_path):
    src = _write(tmp_path, "escala.mid", midi(SCALE))
    out = run("midi-a-wav", make_ctx("midi-a-wav", [src]))
    with wave.open(out[0]["path"]) as w:
        seconds = w.getnframes() / w.getframerate()
        frames = w.readframes(w.getnframes())
    assert out[0]["name"] == "escala.wav" and 2.5 < seconds < 8 and any(frames[i] for i in range(0, len(frames), 997))
    mp3 = run("midi-a-mp3", make_ctx("midi-a-mp3", [src], {"calidad": "128"}))
    data = Path(mp3[0]["path"]).read_bytes()
    assert mp3[0]["name"] == "escala.mp3" and (data[:3] == b"ID3" or data[0] == 0xFF)


def test_midi_too_long_for_the_plan(make_ctx, tmp_path):
    long = _write(tmp_path, "largo.mid", midi([(60, 100_000)]))  # 50 000 s
    with pytest.raises(ToolError) as err:
        run("midi-a-wav", make_ctx("midi-a-wav", [long], plan="anon"))
    assert err.value.code == "LIMIT_EXCEEDED"


MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1"><work><work-title>Canción de prueba</work-title></work>
<part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths></key>
<time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note></measure></part>
</score-partwise>
"""


@needs_mscore
def test_musicxml_mxl_and_midi_to_pdf(make_ctx, tmp_path):
    import pypdfium2 as pdfium

    out = run("musicxml-a-pdf", make_ctx("musicxml-a-pdf", [_write(tmp_path, "cancion.musicxml", MUSICXML)]))
    doc = pdfium.PdfDocument(out[0]["path"])
    import unicodedata

    text = unicodedata.normalize("NFC", doc[0].get_textpage().get_text_range())
    assert out[0]["name"] == "cancion.pdf" and "Canción de prueba" in text
    mxl = tmp_path / "cancion2.mxl"
    with zipfile.ZipFile(mxl, "w") as zf:
        zf.writestr("META-INF/container.xml", '<?xml version="1.0"?><container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>')
        zf.writestr("score.xml", MUSICXML)
    assert run("musicxml-a-pdf", make_ctx("musicxml-a-pdf", [mxl]))[0]["name"] == "cancion2.pdf"
    out = run("midi-a-pdf", make_ctx("midi-a-pdf", [_write(tmp_path, "escala.mid", midi(SCALE))]))
    assert len(pdfium.PdfDocument(out[0]["path"])) >= 1


def test_musicxml_entities_rejected(make_ctx, tmp_path):
    if not Path(get_settings().MSCORE_BIN).is_file():
        pytest.skip("sin MuseScore 3")
    xxe = '<?xml version="1.0"?><!DOCTYPE s [<!ENTITY x SYSTEM "file:///etc/passwd">]><score-partwise>&x;</score-partwise>'
    with pytest.raises(ToolError) as err:
        run("musicxml-a-pdf", make_ctx("musicxml-a-pdf", [_write(tmp_path, "x.musicxml", xxe)]))
    assert err.value.detail == "xml_entities"
