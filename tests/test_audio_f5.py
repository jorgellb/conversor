"""F5, lote A: audio con FFmpeg real (7.8): conversiones a MP3 y WAV, cortar, unir, normalizar y cambiar velocidad."""
from __future__ import annotations

import dataclasses
import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from core.errors import ToolError
from core.filetype import detect
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg no instalado")

ENCODE = {"aac": ["-c:a", "aac", "-f", "adts"], "flac": ["-c:a", "flac"], "wav": ["-c:a", "pcm_s16le"], "wma": ["-c:a", "wmav2", "-f", "asf"],
          "aiff": ["-c:a", "pcm_s16be", "-f", "aiff"], "mp3": ["-c:a", "libmp3lame", "-b:a", "128k"], "ogg": ["-c:a", "libvorbis"]}


def tone(path: Path, seconds: float = 4.0, freq: int = 440, volume_db: float = -6.0, rate: int = 44100) -> Path:
    fmt = path.suffix.lstrip(".")
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}:sample_rate={rate}",
                    "-af", f"volume={volume_db}dB", *ENCODE[fmt], "-y", str(path)], check=True)
    return path


def amr(path: Path, frames: int = 250) -> Path:
    """AMR-NB de 5 s hecho a mano (el FFmpeg de pruebas no tiene codificador AMR): tramas de 12,2 kbps a cero."""
    path.write_bytes(b"#!AMR\n" + (bytes([0x3C]) + bytes(31)) * frames)
    return path


def info(path: str) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,format_name:stream=codec_name,sample_rate,channels",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    stream = data["streams"][0]
    return {"duration": float(data["format"]["duration"]), "format": data["format"]["format_name"], "codec": stream["codec_name"],
            "rate": int(stream["sample_rate"]), "channels": int(stream["channels"])}


def decoded_seconds(path: str, rate: int = 8000) -> float:
    """Duración contando las muestras decodificadas (FFmpeg quita el relleno del codificador MP3 con la etiqueta LAME)."""
    raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return len(raw) / 2 / rate


def dominant_hz(path: str, rate: int = 44100) -> float:
    raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    return float(np.fft.rfftfreq(len(samples), 1 / rate)[np.argmax(spectrum)])


def loudness(path: str) -> float:
    err = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(json.loads(re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", err)[-1])["input_i"])


@pytest.mark.parametrize(("tool", "fmt"), [("aac-a-mp3", "aac"), ("flac-a-mp3", "flac"), ("wav-a-mp3", "wav"), ("wma-a-mp3", "wma"),
                                           ("aiff-a-mp3", "aiff")])
def test_conversions_to_mp3(make_ctx, tmp_path, tool, fmt):
    src = tone(tmp_path / f"tono.{fmt}")
    assert detect(src, fmt).ext == fmt
    out = run(tool, make_ctx(tool, [src], {"calidad": "128"}))
    meta = info(out[0]["path"])
    assert out[0]["name"] == "tono.mp3" and meta["codec"] == "mp3" and abs(meta["duration"] - 4.0) < 0.2


def test_adts_is_not_mistaken_for_mp3_and_amr_converts(make_ctx, tmp_path):
    assert detect(tone(tmp_path / "a.mp3"), "mp3").ext == "mp3"
    assert detect(tone(tmp_path / "b.aac"), "aac").ext == "aac"
    src = amr(tmp_path / "nota.amr")
    assert detect(src, "amr").ext == "amr"
    meta = info(run("amr-a-mp3", make_ctx("amr-a-mp3", [src]))[0]["path"])
    assert meta["codec"] == "mp3" and abs(meta["duration"] - 5.0) < 0.2


def test_to_wav_with_rate_and_channels(make_ctx, tmp_path):
    out = run("ogg-a-wav", make_ctx("ogg-a-wav", [tone(tmp_path / "voz.ogg")], {"frecuencia": "48000", "canales": "mono"}))
    meta = info(out[0]["path"])
    assert out[0]["name"] == "voz.wav" and meta["codec"] == "pcm_s16le" and meta["rate"] == 48000 and meta["channels"] == 1
    out = run("mp3-a-wav", make_ctx("mp3-a-wav", [tone(tmp_path / "musica.mp3")]))
    assert info(out[0]["path"])["rate"] == 44100


def test_cut_keeps_format_and_validates_times(make_ctx, tmp_path):
    src = tone(tmp_path / "pista.flac")
    out = run("cortar-audio", make_ctx("cortar-audio", [src], {"inicio": "0:01", "fin": "0:03,5", "fundido_entrada": 0.5}))
    meta = info(out[0]["path"])
    assert out[0]["name"] == "pista-recortado.flac" and meta["codec"] == "flac" and abs(meta["duration"] - 2.5) < 0.05
    out = run("cortar-audio", make_ctx("cortar-audio", [amr(tmp_path / "nota.amr")], {"inicio": "2"}))
    assert out[0]["name"] == "nota-recortado.mp3" and out[0]["note"] == "No se puede guardar en AMR: va en MP3."
    assert abs(decoded_seconds(out[0]["path"]) - 3.0) < 0.1
    with pytest.raises(ValidationError):
        make_ctx("cortar-audio", [src], {"inicio": "uno"})
    with pytest.raises(ToolError) as err:
        run("cortar-audio", make_ctx("cortar-audio", [src], {"inicio": "0:03", "fin": "0:02"}))
    assert err.value.code == "INVALID_OPTIONS"


def test_join_with_silence_or_crossfade(make_ctx, tmp_path):
    a, b = tone(tmp_path / "uno.wav", 2.0, 440), tone(tmp_path / "dos.mp3", 3.0, 660)
    out = run("unir-audios", make_ctx("unir-audios", [a, b], {"pausa": 1}))
    meta = info(out[0]["path"])
    assert out[0]["name"] == "uno-unido.mp3" and abs(meta["duration"] - 6.0) < 0.15 and meta["channels"] == 2
    out = run("unir-audios", make_ctx("unir-audios", [a, b], {"fundido_cruzado": 1, "salida": "wav"}))
    assert abs(info(out[0]["path"])["duration"] - 4.0) < 0.15
    with pytest.raises(ToolError):
        run("unir-audios", make_ctx("unir-audios", [a]))


def test_normalize_reaches_the_target_loudness(make_ctx, tmp_path):
    src = tone(tmp_path / "bajo.wav", 6.0, volume_db=-30)
    assert loudness(str(src)) < -30
    out = run("normalizar-volumen", make_ctx("normalizar-volumen", [src]))
    assert abs(loudness(out[0]["path"]) - (-16)) < 1.0 and info(out[0]["path"])["rate"] == 44100
    assert re.fullmatch(r"Volumen integrado: -\d+(\.\d+)? → -16 LUFS\.", out[0]["note"])
    english = run("normalizar-volumen", dataclasses.replace(make_ctx("normalizar-volumen", [src], {"objetivo": "-23", "salida": "mp3"}), locale="en"))
    assert abs(loudness(english[0]["path"]) - (-23)) < 1.0 and english[0]["note"].startswith("Integrated loudness:")


def test_speed_with_and_without_pitch(make_ctx, tmp_path):
    src = tone(tmp_path / "voz.wav", 4.0, 440)
    out = run("cambiar-velocidad-audio", make_ctx("cambiar-velocidad-audio", [src], {"velocidad": 2}))
    assert out[0]["name"] == "voz-x2.wav" and abs(info(out[0]["path"])["duration"] - 2.0) < 0.1
    assert abs(dominant_hz(out[0]["path"]) - 440) < 10  # mismo tono
    out = run("cambiar-velocidad-audio", make_ctx("cambiar-velocidad-audio", [src], {"velocidad": 2, "conservar_tono": False}))
    assert abs(dominant_hz(out[0]["path"]) - 880) < 15  # una octava más aguda
    out = run("cambiar-velocidad-audio", make_ctx("cambiar-velocidad-audio", [src], {"velocidad": 0.25}))
    assert out[0]["name"] == "voz-x0,25.wav" and abs(info(out[0]["path"])["duration"] - 16.0) < 0.3
