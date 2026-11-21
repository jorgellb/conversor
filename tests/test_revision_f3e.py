"""Revisión externa de F3-E (D-263): traducir-subtitulos, resumir-reunion y la decodificación de audio compartida."""
from __future__ import annotations

import dataclasses
import shutil
import subprocess
import time

import pytest

from core.errors import ToolError
from test_tools import make_ctx, run  # noqa: F401  (fixture)


def test_subtitle_with_thousands_of_tags_is_refused_fast():
    from tools.subs import parse_text

    srt = "1\n00:00:01,000 --> 00:00:02,000\nHola " + "<i>" * 20_000 + "\n"
    t0 = time.time()
    with pytest.raises(ToolError) as err:
        parse_text(srt, "srt")
    assert err.value.detail == "subs_cue_tags" and time.time() - t0 < 5
    ass = ("[Script Info]\nScriptType: v4.00+\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
           "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,," + "{\\i1}" * 20_000 + "x\n")
    with pytest.raises(ToolError):
        parse_text(ass, "ass")


def test_translation_cannot_inject_cues_and_vtt_is_escaped():
    import pysubs2

    from tools.ai.subtitulos import apply, items_of, parse_text, safe

    assert "-->" not in safe("Hola 00:00:01,000 --> 00:09:00,000 x")
    subs = parse_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nTom &amp; Jerry &lt;3\n\n00:00:03.000 --> 00:00:04.000\nAdiós amigos\n", "vtt")
    import html

    for ev in subs.events:
        ev.text = html.unescape(ev.text)
    items, _ = items_of(subs)
    assert items[0].source == "Tom & Jerry <3"
    missing = apply(subs, items, {items[0].source: "Tom y Jerry <3 --> 00:09:00.000", items[1].source: ""}, 42, False, vtt=True)
    assert missing == 1  # el segundo se quedó sin traducir y se avisa
    out = subs.to_string("vtt")
    assert "Tom y Jerry &lt;3 → 00:09:00.000" in out  # entidad en VTT y sin una línea de tiempos falsa
    again = pysubs2.SSAFile.from_string(out, format_="vtt")
    assert len(again.events) == 2


def test_output_name_keeps_non_language_suffixes():
    from types import SimpleNamespace

    from tools.ai.subtitulos import output_name

    assert output_name(SimpleNamespace(name="Serie.S01E01.web.srt"), "es", "srt") == "Serie.S01E01.web.es.srt"
    assert output_name(SimpleNamespace(name="pelicula.eng.srt"), "es", "srt") == "pelicula.es.srt"
    assert output_name(SimpleNamespace(name="pelicula.pt-BR.srt"), "es", "srt") == "pelicula.es.srt"


def test_minutes_without_control_characters_and_markdown_is_escaped(tmp_path):
    from tools.ai import reunion

    acta = reunion.clean({"resumen": "Resumen\x01 del día\n# Falso título\n\nSegundo párrafo", "temas": ["<img src=x onerror=alert(1)>"],
                          "decisiones": ["[pincha](javascript:alert(1))"], "preguntas": [], "tareas": []})
    assert "\x01" not in acta["resumen"]
    t = reunion.TEXTS["es"] if hasattr(reunion, "TEXTS") else None
    if t is None:
        pytest.skip("sin textos")
    md = reunion.as_text("Reunión", "Grabación", acta, ["temas", "decisiones"], [(65, "Hola <b>")], t, "Nota", md=True)
    # Escapado: se ve como texto, no como HTML, enlace ni título.
    assert "\\<img" in md and "\\](javascript" in md and "\n# Falso" not in md and "\\# Falso" in md
    assert "[01:05] Hola \\<b\\>" in md


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sin ffmpeg")
def test_decoding_never_exceeds_the_plan_even_if_the_container_lies(make_ctx, tmp_path):
    from tools.av import transcribe as tr
    from tools.base import InputFile

    wav = tmp_path / "largo.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=90", "-ac", "1", "-ar", "16000", "-y", str(wav)],
                   check=True)
    ctx = make_ctx("transcribir-audio", [wav])
    ctx = dataclasses.replace(ctx, plan=ctx.plan.model_copy(update={"audio_minutes": 1}))
    inp = InputFile(wav, wav.name, "wav", wav.stat().st_size, "")
    # Sin duración conocida (0): se decodifica como mucho el límite y un segundo; como había más, LIMIT_EXCEEDED.
    with pytest.raises(ToolError) as err:
        tr.decode_pcm(ctx, inp, "wav", 0.0, tmp_path / "a.pcm")
    assert str(err.value.detail).startswith("audio_minutes")
    # Una duración falsa de 10 s: solo sale eso (y el segundo de margen), no los 90 s de verdad.
    pcm = tr.decode_pcm(ctx, inp, "wav", 10.0, tmp_path / "b.pcm")
    assert len(pcm) / tr.RATE <= 11.01
