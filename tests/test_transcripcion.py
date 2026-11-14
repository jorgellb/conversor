"""Transcripción local (7.10): transcribir-audio y video-a-subtitulos con faster-whisper en CPU y FFmpeg aparte.

Las pruebas reales necesitan un modelo en `WHISPER_HOME` (la CI baja tiny con su SHA-256 con infra/whisper/fetch-models.sh);
sin él se omiten. La voz de prueba es el fragmento del discurso inaugural de Kennedy (dominio público, tests/fixtures).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

from core.errors import ErrorCode, ToolError
from core.registry import load_registry
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida
from tools.av import transcribe as tr

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg no instalado")

SPEECH = Path(__file__).parent / "fixtures" / "jfk.ogg"
PHRASE = "ask not what your country can do for you"


def home() -> Path:
    return Path(os.environ.get("WHISPER_HOME", "/opt/models/whisper"))


def local_model() -> str | None:
    for name in ("tiny", "small"):
        if (home() / f"faster-whisper-{name}" / "model.bin").is_file():
            return name
    return None


needs_model = pytest.mark.skipif(local_model() is None, reason="Sin modelo de faster-whisper en WHISPER_HOME")


def with_model(ctx):
    ctx.settings = ctx.settings.model_copy(update={"WHISPER_HOME": home(), "WHISPER_MODEL": local_model()})
    return ctx


def words(text: str) -> str:
    return re.sub(r"[^a-z ]", "", text.lower().replace("\n", " "))


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", *args], check=True)


# ——— Sin modelo ———

def test_timestamps_and_clock():
    assert tr.timestamp(3723.4567) == "01:02:03,457"
    assert tr.timestamp(0.5, ".") == "00:00:00.500"
    assert tr.timestamp(-1) == "00:00:00,000"
    assert tr.clock(65.9) == "01:05"
    assert tr.clock(3725) == "1:02:05"


def test_paragraphs_split_on_pauses_and_long_sentences():
    segs = [tr.Segment(0, 2, "Hola."), tr.Segment(2.2, 4, "Qué tal."), tr.Segment(6.5, 8, "Otro tema.")]
    assert tr.paragraphs(segs) == [(0, "Hola. Qué tal."), (6.5, "Otro tema.")]
    long = [tr.Segment(i * 2, i * 2 + 1.9, f"Frase número {i} bastante larga para llenar el párrafo.") for i in range(30)]
    paras = tr.paragraphs(long, max_chars=200)
    assert len(paras) > 3 and all(p.endswith(".") for _, p in paras)
    assert tr.as_text([(65, "Hola.")], True) == "[01:05] Hola.\n"
    assert tr.as_text([(0, "A."), (3, "B.")], False) == "A.\n\nB.\n"


def test_cues_respect_width_lines_duration_and_pauses():
    text = ("Esta es una frase de prueba bastante larga que tiene que repartirse en varios subtítulos sin pasar de dos líneas "
            "ni de cuarenta y dos caracteres por línea. Después de una pausa larga empieza otra parte.").split()
    ws, t = [], 0.0
    for i, w in enumerate(text):
        if w == "Después":
            t += 2.0
        ws.append(tr.Word(t, t + 0.3, w))
        t += 0.35
    items = tr.cues([tr.Segment(ws[0].start, ws[-1].end, " ".join(text), ws)])
    assert len(items) >= 3
    for i, c in enumerate(items):
        assert 1 <= len(c.lines) <= 2 and all(len(line) <= 42 for line in c.lines)
        assert c.end > c.start and c.end - c.start <= 7.5
        if i + 1 < len(items):
            assert c.end <= items[i + 1].start
    # La pausa larga corta el subtítulo: «Después» empieza uno nuevo.
    assert any(c.lines[0].startswith("Después") for c in items)
    assert " ".join(" ".join(c.lines) for c in items).split() == text


def test_words_fallback_and_subtitle_formats():
    seg = tr.Segment(1.0, 3.0, "uno dos tres")
    ws = tr.words_of(seg)
    assert [w.text for w in ws] == ["uno", "dos", "tres"]
    assert ws[0].start == 1.0 and abs(ws[-1].end - 3.0) < 1e-9
    items = [tr.Cue(0.0, 1.5, ["Hola,", "¿qué tal?"]), tr.Cue(2.0, 3.25, ["Bien."])]
    assert tr.as_srt(items) == "1\n00:00:00,000 --> 00:00:01,500\nHola,\n¿qué tal?\n\n2\n00:00:02,000 --> 00:00:03,250\nBien.\n\n"
    assert tr.as_vtt(items).startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nHola,\n¿qué tal?\n\n")
    # Lo corto dura al menos un segundo si cabe antes del siguiente.
    short = tr.cues([tr.Segment(0, 0.3, "Sí", [tr.Word(0, 0.3, "Sí")]), tr.Segment(5, 5.5, "No", [tr.Word(5, 5.5, "No")])])
    assert short[0].end == pytest.approx(1.0) and short[1].end == pytest.approx(6.0)


def test_long_audio_is_cut_in_the_quietest_moment():
    rate = 1000
    rng = np.random.default_rng(1)
    samples = (rng.normal(0, 3000, 50 * rate)).astype(np.int16)
    samples[22_000:22_500] = 0
    bounds = tr.chunk_bounds(samples, rate=rate, chunk=20, search=5)
    assert bounds[0][0] == 0 and bounds[-1][1] == len(samples)
    assert all(a[1] == b[0] for a, b in zip(bounds, bounds[1:]))
    assert 22_000 <= bounds[0][1] <= 22_500
    assert tr.chunk_bounds(samples[:21 * rate], rate=rate, chunk=20) == [(0, 21 * rate)]


def test_faster_whisper_loads_without_pyav():
    pytest.importorskip("ctranslate2")
    import importlib.util

    # Otra prueba (pdf-a-audio, que comprueba la voz con faster-whisper) puede haber registrado ya el módulo vacío.
    if "av" not in sys.modules and importlib.util.find_spec("av") is not None:
        pytest.skip("PyAV instalado en este entorno (en la imagen no está, D-111)")
    whisper = tr._whisper_class()
    assert whisper.__name__ == "WhisperModel"
    assert "x265" in (sys.modules["av"].__doc__ or "")


def test_model_guard_and_fallback_note(make_ctx, tmp_path):
    from core.settings import Settings

    with pytest.raises(ToolError):
        tr.model_dir(Settings(WHISPER_HOME=tmp_path), "../../etc")
    with pytest.raises(ToolError) as err:
        tr.load_model(Settings(WHISPER_HOME=tmp_path, WHISPER_MODEL="small"), "small", 1)
    assert err.value.code == ErrorCode.TOOL_DISABLED
    ctx = make_ctx("transcribir-audio", [SPEECH], {"precision": "alta"})
    ctx.settings = ctx.settings.model_copy(update={"WHISPER_HOME": tmp_path, "WHISPER_MODEL": "small"})
    notes: list[str] = []
    assert tr.pick_model(ctx, "alta", notes) == "small"
    assert "medium" in notes[0]
    (tmp_path / "faster-whisper-medium").mkdir()
    (tmp_path / "faster-whisper-medium" / "model.bin").write_bytes(b"x")
    assert tr.pick_model(ctx, "alta", []) == "medium"
    assert tr.pick_model(ctx, "normal", []) == "small"


def test_specs_go_to_the_heavy_av_queue():
    reg = load_registry()
    for slug, outputs in (("transcribir-audio", {"txt", "docx", "srt", "zip"}), ("video-a-subtitulos", {"srt", "vtt", "zip"})):
        spec = reg.require(slug)
        assert (spec.worker_group, spec.cost_class, spec.queue_kind, spec.where) == ("av", "heavy", "heavy", "server")
        assert set(spec.outputs) == outputs and spec.time_limit == 4 * 3600
    opts = reg.require("video-a-subtitulos").options
    assert opts.model_validate({}).caracteres_por_linea == 42
    with pytest.raises(Exception):
        opts.model_validate({"caracteres_por_linea": 200})
    assert reg.require("transcribir-audio").options.model_validate({}).idioma == "auto"


def test_video_without_audio_and_too_long_audio_are_rejected(make_ctx, tmp_path):
    mute = tmp_path / "mudo.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=2", "-c:v", "mpeg4", "-y", str(mute))
    with pytest.raises(ToolError) as err:
        run("video-a-subtitulos", make_ctx("video-a-subtitulos", [mute]))
    assert err.value.code == ErrorCode.UNSUPPORTED_FORMAT
    # 11 minutos en el plan anónimo (10 minutos de audio): se rechaza antes de transcribir.
    long = tmp_path / "largo.ogg"
    ffmpeg("-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono", "-t", "660", "-c:a", "libopus", "-b:a", "6k", "-y", str(long))
    with pytest.raises(ToolError) as err:
        run("transcribir-audio", make_ctx("transcribir-audio", [long], plan="anon"))
    assert err.value.code == ErrorCode.LIMIT_EXCEEDED


# ——— Con modelo ———

@needs_model
def test_transcribe_speech_to_txt_docx_and_srt(make_ctx):
    ctx = with_model(make_ctx("transcribir-audio", [SPEECH], {"formato": "todos", "marcas_de_tiempo": True}))
    out = run("transcribir-audio", ctx)
    names = [o["name"] for o in out]
    assert names == ["jfk.txt", "jfk.docx", "jfk.srt", "transcripciones.zip"]
    txt = Path(out[0]["path"]).read_text(encoding="utf-8")
    assert txt.startswith("[00:00] ") and PHRASE in words(txt)
    assert "inglés (detectado" in out[0]["note"]
    from docx import Document

    doc = Document(out[1]["path"])
    body = " ".join(p.text for p in doc.paragraphs)
    assert PHRASE in words(body) and doc.paragraphs[0].text == "jfk"
    assert doc.core_properties.author == ""
    srt = Path(out[2]["path"]).read_text(encoding="utf-8")
    blocks = [b.split("\n") for b in srt.strip().split("\n\n")]
    assert [b[0] for b in blocks] == [str(i) for i in range(1, len(blocks) + 1)]
    times = [re.match(r"(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})", b[1]) for b in blocks]
    assert all(times)
    ends = [int(m[6]) * 60 + int(m[7]) + int(m[8]) / 1000 for m in times]
    assert max(ends) <= 11.5
    assert all(len(line) <= 42 for b in blocks for line in b[2:])
    with zipfile.ZipFile(out[-1]["path"]) as zf:
        assert sorted(zf.namelist()) == ["jfk.docx", "jfk.srt", "jfk.txt"]


@needs_model
def test_subtitles_from_a_video_in_srt_and_vtt(make_ctx, tmp_path):
    video = tmp_path / "discurso.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=11", "-i", str(SPEECH), "-shortest", "-c:v", "mpeg4",
           "-c:a", "aac", "-y", str(video))
    ctx = with_model(make_ctx("video-a-subtitulos", [video], {"formato": "ambos", "idioma": "en", "caracteres_por_linea": 32}))
    out = run("video-a-subtitulos", ctx)
    assert [o["name"] for o in out] == ["discurso.srt", "discurso.vtt", "subtitulos.zip"]
    vtt = Path(out[1]["path"]).read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT\n\n") and "-->" in vtt and "." in vtt.split("-->")[0]
    lines = [line for line in vtt.split("\n") if line and "-->" not in line and line != "WEBVTT"]
    assert all(len(line) <= 32 for line in lines)
    assert PHRASE in words(" ".join(lines))
    # Idioma elegido: no se dice «detectado».
    assert "inglés" in out[0]["note"] and "detectado" not in out[0]["note"]


@needs_model
def test_long_audio_by_chunks_keeps_text_and_times(make_ctx, monkeypatch):
    # Tramos de 4 s cortados en silencio: los tiempos siguen el audio entero y la frase se conserva.
    monkeypatch.setattr(tr, "CHUNK_SECONDS", 4)
    monkeypatch.setattr(tr, "SEARCH_SECONDS", 1)
    out = run("transcribir-audio", with_model(make_ctx("transcribir-audio", [SPEECH], {"formato": "srt", "idioma": "en"})))
    srt = Path(out[0]["path"]).read_text(encoding="utf-8")
    starts = [int(m[0]) * 3600 + int(m[1]) * 60 + int(m[2]) + int(m[3]) / 1000
              for m in re.findall(r"(\d\d):(\d\d):(\d\d),(\d{3}) -->", srt)]
    assert len(starts) >= 2 and starts == sorted(starts) and starts[-1] > 4
    text = words(" ".join(line for line in srt.split("\n") if line and "-->" not in line and not line.isdigit()))
    assert "fellow americans" in text and "your country" in text


@needs_model
def test_silence_is_no_speech(make_ctx, tmp_path):
    quiet = tmp_path / "silencio.wav"
    ffmpeg("-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "5", "-c:a", "pcm_s16le", "-y", str(quiet))
    with pytest.raises(ToolError) as err:
        run("transcribir-audio", with_model(make_ctx("transcribir-audio", [quiet])))
    assert err.value.code == ErrorCode.NO_SPEECH
