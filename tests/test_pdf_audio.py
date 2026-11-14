"""pdf-a-audio (7.6, F3 lote D): texto del PDF, fonemas de espeak-ng, voz de Kokoro y MP3 con FFmpeg.

Las pruebas con voz necesitan espeak-ng, FFmpeg y el modelo en `KOKORO_HOME` (la CI lo baja con
infra/kokoro/fetch-model.sh); sin ellos se omiten. Las que comprueban lo que se ha dicho necesitan además un modelo de
faster-whisper en `WHISPER_HOME`. Las de la API (`integration`) necesitan PostgreSQL y Valkey.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from core.errors import AppError, ErrorCode, ToolError, message
from core.plans import load_plans_file
from core.registry import load_registry
from core.settings import Settings, get_settings
from helpers import auth
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida
from tools.av import kokoro, lectura, voz

FIXTURES = Path(__file__).resolve().parents[1] / "scripts" / "fixtures"


def kokoro_home() -> Path:
    return Path(os.environ.get("KOKORO_HOME", "/opt/models/kokoro"))


def whisper_home() -> Path:
    return Path(os.environ.get("WHISPER_HOME", "/opt/models/whisper"))


def whisper_model() -> str | None:
    for name in ("small", "tiny"):
        if (whisper_home() / f"faster-whisper-{name}" / "model.bin").is_file():
            return name
    return None


VOICE_READY = bool((kokoro_home() / "model.onnx").is_file() and shutil.which("espeak-ng") and shutil.which("ffmpeg"))
needs_voice = pytest.mark.skipif(not VOICE_READY, reason="Sin espeak-ng, FFmpeg o el modelo de Kokoro en KOKORO_HOME")
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg no instalado")
needs_whisper = pytest.mark.skipif(whisper_model() is None, reason="Sin modelo de faster-whisper en WHISPER_HOME")
PLANS = load_plans_file(get_settings().PLANS_FILE)
FRENCH = ("Le rapport annuel montre une croissance des ventes cette année chez nous, avec beaucoup de nouveaux clients "
          "dans toutes les villes du pays et une équipe plus grande.")


@pytest.fixture()
def no_db(monkeypatch):
    """Las pruebas directas leen el PDF sin `document_texts` (PostgreSQL): el texto sale igual, de pypdfium2."""
    from tools.ai import documento

    monkeypatch.setattr(documento, "load", lambda ctx, inp: documento._extract(ctx, inp))


def voiced(ctx, **extra):
    ctx.settings = ctx.settings.model_copy(update={"KOKORO_HOME": kokoro_home(), "TTS_VOICE_ES": "ef_dora", **extra})
    return ctx


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,bit_rate,format_name:stream=codec_name,"
                          "sample_rate,channels", "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    stream = data["streams"][0]
    return {"codec": stream["codec_name"], "rate": int(stream["sample_rate"]), "channels": stream["channels"],
            "duration": float(data["format"]["duration"]), "bitrate": int(data["format"]["bit_rate"]),
            "format": data["format"]["format_name"]}


def heard(path: Path, lang: str) -> str:
    """Lo que entiende faster-whisper del MP3 (para comprobar que la voz dice el texto)."""
    from core.settings import Settings as S
    from tools.av import transcribe as tr

    pcm = path.with_suffix(".pcm")
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-y",
                    str(pcm)], check=True)
    samples = np.fromfile(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    model = tr.load_model(S(WHISPER_HOME=whisper_home()), whisper_model(), 2)
    parts, _ = model.transcribe(samples, language=lang, beam_size=5)
    return re.sub(r"[^a-záéíóúñü0-9 ]", "", " ".join(p.text for p in parts).lower())


# ——— Texto (sin motores) ———

def test_headers_footers_and_page_numbers_are_skipped():
    pages = [f"Informe anual 2026\nTexto de la página {n}, que es distinto en cada una.\nPágina {n} de 4" for n in range(1, 5)]
    paras = lectura.paragraphs(pages)
    assert all("Informe anual" not in p and "Página" not in p for p in paras)
    assert lectura.paragraphs(pages, skip_furniture=False)[0].startswith("Informe anual 2026")
    # Con menos de 3 páginas no se sabe si una línea repetida es cabecera: solo se quitan los números.
    body = "Una frase bastante más larga que el título de la página, para que se vea la diferencia."
    two = lectura.paragraphs([f"Título\n{body}\n- 1 -", f"Título\n{body}\n- 2 -"])
    assert two == ["Título", body, "Título", body]


def test_paragraphs_join_hyphenated_words_and_continue_across_pages():
    pages = ["Una frase que se parte en dos lí-\nneas y sigue en la página", "siguiente sin punto. Fin del párrafo.\n\nOtro párrafo."]
    assert lectura.paragraphs(pages) == ["Una frase que se parte en dos líneas y sigue en la página siguiente sin punto. Fin del párrafo.",
                                         "Otro párrafo."]
    assert lectura.paragraphs(["• Primero\n• Segundo, con coma"]) == ["Primero", "Segundo, con coma"]
    # Un guion blando (\x02 de PDFium) en una línea suelta y una palabra partida justo después.
    assert lectura.paragraphs(["Una pala\x02\nbra y otra par-\nte que sigue sin punto"]) == [
        "Una palabra y otra parte que sigue sin punto"]


def test_paragraphs_take_linear_time():
    """Un PDF de párrafos larguísimos (sin puntos ni líneas en blanco) no puede tardar horas en contarse: armar el
    párrafo solo mira el final de la última línea. Con la unión cuadrática, 40 páginas así tardaban más de 2 minutos."""
    import time

    line = ("palabra " * 40)[:318]
    pages = ["\n".join([line] * 190) for _ in range(40)]
    start = time.monotonic()
    paras = lectura.paragraphs(pages)
    assert time.monotonic() - start < 10
    assert len(paras) == 1 and lectura.chars(paras) == 40 * 190 * (318 + 1) - 1  # las líneas, unidas por un espacio


def test_sentences_keep_abbreviations_and_clauses_carry_punctuation():
    text = "El Sr. García llegó a las 3.30 con J. F. Kennedy. ¿Qué pasó después? Mucho, la verdad: todo."
    assert lectura.sentences(text) == ["El Sr. García llegó a las 3.30 con J. F. Kennedy.", "¿Qué pasó después?",
                                       "Mucho, la verdad: todo."]
    cl = lectura.clauses("Mucho, la verdad: todo — o casi (eso dicen)…")
    assert [(c.text, c.mark) for c in cl] == [("Mucho", ","), ("la verdad", ":"), ("todo", "—"), ("o casi eso dicen", "…")]
    # Decimales y miles se quedan juntos; un trozo larguísimo se parte por palabras.
    assert lectura.clauses("Subió un 3,5 % hasta 1.000 euros.")[0].text == "Subió un 3,5 % hasta 1.000 euros"
    long = lectura.clauses(" ".join(["palabra"] * 100) + ".")
    assert len(long) >= 3 and all(len(c.text.split()) <= lectura.MAX_WORDS and len(c.text) <= lectura.MAX_CHARS for c in long)
    assert long[-1].mark == "." and all(c.mark == "" for c in long[:-1])


def test_language_detection_and_char_count():
    assert lectura.detect_language("El informe de la empresa dice que las ventas crecieron en el norte del país.") == "es"
    assert lectura.detect_language("The report of the company says that sales grew in the north of the country.") == "en"
    french = FRENCH
    assert lectura.detect_language(french) is None and lectura.detect_language(french, "es") is None
    assert lectura.detect_language("Informe anual 2026", "en") == "en"  # muy poco texto: el idioma de la página
    assert lectura.chars(["abc", "de f"]) == 7


def test_ipa_to_kokoro_symbols():
    assert kokoro.to_kokoro("həlˈo^ʊ wˈɜːld", "en") == "həlˈO wˈɜld"
    assert kokoro.to_kokoro("ðə kwˈɔː^ɹɾɚli", "en") == "ðə kwˈɔɹɾəɹli"
    assert kokoro.to_kokoro("mˈutʃo t^ʃˈiko (en)sˈɒftweə(es)", "es") == "mˈutʃo ʧˈiko sˈɒftweə"
    assert kokoro.to_kokoro("rˈosa", "es") == "rˈosa"  # la «r» múltiple del español no se toca


def test_voice_names_are_checked(tmp_path):
    settings = Settings(KOKORO_HOME=tmp_path)
    for bad in ("../../etc/passwd", "af_heart", "ef_dora.bin", ""):
        with pytest.raises(ToolError) as exc:
            kokoro.voice_path(settings, bad, "es")
        assert exc.value.code == ErrorCode.TOOL_DISABLED
    with pytest.raises(ToolError):
        kokoro.voice_path(settings, "ef_dora", "es")  # bien escrita, pero no está en la imagen
    with pytest.raises(ToolError) as exc:
        voz.voice_for(Settings(TTS_VOICE_ES=""), "es", "mujer")
    assert exc.value.detail == "tts_voice_es"
    assert voz.voice_for(Settings(TTS_VOICE_ES="ef_dora"), "es", "hombre") == "em_alex"
    assert voz.voice_for(Settings(TTS_VOICE_EN="af_bella"), "en", "predeterminada") == "af_bella"


def test_error_messages_explain_the_limits():
    assert "20000 caracteres" in message("LIMIT_EXCEEDED", "es", "tts_chars:22417>20000")
    assert "22417" in message("LIMIT_EXCEEDED", "en", "tts_chars:22417>20000")
    assert "cuenta" in message("UNAUTHORIZED", "es", "tts_account")
    assert "Dividir PDF" in message("LIMIT_EXCEEDED", "es", "tts_count")
    assert "Split PDF" in message("LIMIT_EXCEEDED", "en", "tts_count")
    assert "español" in message("TOOL_DISABLED", "es", "tts_voice_es")


def test_options_contract():
    spec = load_registry().require("pdf-a-audio")
    assert spec.queue == "av.heavy" and spec.cost_class == "heavy" and spec.ai is None and spec.max_files == 1
    o = spec.options.model_validate({})
    assert (o.paginas, o.idioma, o.voz, o.velocidad, o.calidad, o.pausa, o.saltar_cabeceras, o.ocr) == (
        "todas", "auto", "predeterminada", 1.0, "128", 0.6, True, True)
    for bad in ({"velocidad": 0.4}, {"velocidad": 2.1}, {"pausa": 3.5}, {"calidad": "320"}, {"idioma": "fr"}, {"voz": "robot"}):
        with pytest.raises(Exception):
            spec.options.model_validate(bad)


# ——— Comprobación de la API antes de encolar (proceso aparte) ———

def test_count_matches_what_the_worker_reads(fixtures_dir):
    info = voz.count(fixtures_dir / "lectura-en.pdf", "todas", True, 300)
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(fixtures_dir / "lectura-en.pdf"))
    pages = [lectura.page_text(doc[i].get_textpage()) for i in range(len(doc))]
    assert info["chars"] == lectura.chars(lectura.paragraphs(pages)) and info["language"] == "en" and info["scanned"] == 0
    assert voz.count(fixtures_dir / "lectura-en.pdf", "todas", False, 300)["chars"] > info["chars"]
    assert voz.count(fixtures_dir / "lectura-en.pdf", "2", True, 300)["chars"] < info["chars"]
    assert voz.count(fixtures_dir / "lectura-escaneada.pdf", "todas", True, 300) == {
        "pages": 1, "selected": 1, "chars": 0, "scanned": 1, "language": None}
    assert voz.count(fixtures_dir / "cifrado.pdf", "todas", True, 300) == {"error": "password"}
    assert voz.count(fixtures_dir / "falso.pdf", "todas", True, 300) == {"error": "corrupt"}
    assert voz.count(fixtures_dir / "lectura-en.pdf", "todas", True, 2)["error"] == "pages"


def test_precheck_rejects_before_enqueueing(fixtures_dir):
    s = Settings(TTS_VOICE_ES="", TTS_VOICE_EN="af_heart")
    en, es, larga = (fixtures_dir / f"lectura-{n}.pdf" for n in ("en", "es", "larga"))
    with pytest.raises(AppError) as exc:
        voz.precheck(s, PLANS["anon"], "anon", {}, [en])
    assert (exc.value.status, exc.value.detail) == (401, "tts_account")
    with pytest.raises(AppError) as exc:
        voz.precheck(s, PLANS["free"], "user", {}, [larga])
    assert exc.value.code == ErrorCode.LIMIT_EXCEEDED and exc.value.detail.startswith("tts_chars:") and exc.value.detail.endswith(">20000")
    voz.precheck(s, PLANS["pro"], "user", {}, [larga])  # 300.000 en Pro
    voz.precheck(s, PLANS["free"], "user", {"paginas": "1-10"}, [larga])  # un rango que cabe
    # Español apagado mientras TTS_VOICE_ES esté vacía (6.4): pedido o detectado.
    for options in ({"idioma": "es"}, {}):
        with pytest.raises(AppError) as exc:
            voz.precheck(s, PLANS["free"], "user", options, [es])
        assert (exc.value.code, exc.value.detail) == (ErrorCode.TOOL_DISABLED, "tts_voice_es")
    voz.precheck(Settings(TTS_VOICE_ES="ef_dora"), PLANS["free"], "user", {}, [es])
    voz.precheck(s, PLANS["free"], "user", {}, [en])
    voz.precheck(s, PLANS["free"], "user", {}, [fixtures_dir / "lectura-escaneada.pdf"])  # lo decide el worker tras el OCR
    with pytest.raises(AppError) as exc:
        voz.precheck(s, PLANS["free"], "user", {}, [fixtures_dir / "cifrado.pdf"])
    assert exc.value.code == ErrorCode.PASSWORD_REQUIRED
    with pytest.raises(AppError) as exc:
        voz.precheck(s, PLANS["free"], "user", {"paginas": "9"}, [en])
    assert exc.value.code == ErrorCode.INVALID_OPTIONS


def test_precheck_detects_the_language_like_the_worker(fixtures_dir, tmp_path):
    """Con muy poco texto, la API decide el idioma como el worker (el de la página), para no encolar una lectura que el
    worker rechazaría con la tarea ya gastada. Con páginas escaneadas decide el worker, después del OCR."""
    import sys

    sys.path.insert(0, str(FIXTURES))
    from lectura_pdf import prose_pdf

    short = prose_pdf(tmp_path / "portada.pdf", [["Annual Report 2026 Summary"]])
    s = Settings(TTS_VOICE_ES="", TTS_VOICE_EN="af_heart")
    assert voz.count(short, "todas", True, 300, "es")["language"] == "es"
    assert voz.count(short, "todas", True, 300, "en")["language"] == "en"
    assert voz.count(short, "todas", True, 300)["language"] is None
    with pytest.raises(AppError) as exc:
        voz.precheck(s, PLANS["free"], "user", {}, [short], locale="es")
    assert (exc.value.code, exc.value.detail) == (ErrorCode.TOOL_DISABLED, "tts_voice_es")
    voz.precheck(s, PLANS["free"], "user", {}, [short], locale="en")
    voz.precheck(s, PLANS["free"], "user", {"idioma": "en"}, [short], locale="es")
    assert voz.count(fixtures_dir / "lectura-escaneada.pdf", "todas", True, 300, "es")["language"] is None
    voz.precheck(s, PLANS["free"], "user", {}, [fixtures_dir / "lectura-escaneada.pdf"], locale="es")


def test_precheck_rejects_when_the_count_does_not_finish(fixtures_dir, monkeypatch):
    """Un recuento que no termina a tiempo (o falla) no se encola: el worker tardaría lo mismo con la tarea gastada."""
    s = Settings(TTS_VOICE_ES="", TTS_VOICE_EN="af_heart")
    en = fixtures_dir / "lectura-en.pdf"
    assert voz.count(en, "todas", True, 300, timeout=0.001) == {"error": "timeout"}
    cases = ((ErrorCode.TIMEOUT, (ErrorCode.LIMIT_EXCEEDED, "tts_count")), (ErrorCode.ENGINE_FAILED, (ErrorCode.ENGINE_FAILED, None)))
    for code, expected in cases:
        def fail(*args, code=code, **kwargs):
            raise ToolError(code, "contar_texto.py")

        monkeypatch.setattr(voz, "run_engine", fail)
        with pytest.raises(AppError) as exc:
            voz.precheck(s, PLANS["free"], "user", {}, [en])
        assert (exc.value.code, exc.value.detail) == expected


# ——— MP3 por tramos (FFmpeg, 16.5) ———

@needs_ffmpeg
def test_mp3_segments_join_with_the_exact_duration(make_ctx, fixtures_dir, monkeypatch):
    ctx = make_ctx("pdf-a-audio", [fixtures_dir / "lectura-en.pdf"])
    writer = voz.Mp3Writer(ctx, "192")
    t = np.arange(24_000 * 3) / 24_000
    for _ in range(4):
        writer.add(0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32))
        writer.silence(0.5)
        writer.flush()
    dst = ctx.work / "tono.mp3"
    writer.finish(dst, "Tono")
    info = probe(dst)
    assert writer.parts == 4 and info["codec"] == "mp3" and info["rate"] == 44100 and info["channels"] == 1
    # 4 × 3,5 s; cada tramo añade como mucho el relleno de un cuadro de MP3 al principio y al final.
    assert abs(info["duration"] - 14.0) < 0.06 * writer.parts + 0.05
    assert 185_000 < info["bitrate"] < 200_000
    assert not (ctx.work / "voz.pcm").exists() and not (ctx.work / "voz-tramos.mp3").exists()


# ——— Con voz (espeak-ng y Kokoro) ———

RESULTS: dict[str, tuple[Path, str, dict]] = {}


def speak(make_ctx, fixtures_dir, name: str, options: dict, **settings) -> tuple[Path, str, dict]:
    key = json.dumps([name, options, settings], sort_keys=True)
    if key not in RESULTS:
        ctx = voiced(make_ctx("pdf-a-audio", [fixtures_dir / name], options), **settings)
        out = run("pdf-a-audio", ctx)
        assert len(out) == 1 and out[0]["name"] == name.replace(".pdf", ".mp3")
        keep = Path(out[0]["path"]).with_name(f"r{len(RESULTS)}.mp3")
        shutil.copyfile(out[0]["path"], keep)
        RESULTS[key] = (keep, out[0]["note"], probe(keep))
    return RESULTS[key]


@needs_voice
def test_english_pdf_becomes_an_mp3_that_says_the_text(make_ctx, fixtures_dir, no_db):
    path, note, info = speak(make_ctx, fixtures_dir, "lectura-en.pdf", {"paginas": "3"})
    assert info["codec"] == "mp3" and info["format"] == "mp3" and info["rate"] == 44100 and info["channels"] == 1
    assert 3 < info["duration"] < 15 and 120_000 < info["bitrate"] < 136_000
    assert note.startswith("Leído en inglés (detectado) con la voz af_heart de Kokoro") and "caracteres" in note
    chars = voz.count(fixtures_dir / "lectura-en.pdf", "3", True, 300)["chars"]
    assert f"{chars} caracteres" in note
    if whisper_model():
        text = heard(path, "en")
        assert "thank everyone" in text and "cooperative" in text
        assert "northern" not in text  # la cabecera repetida no se lee


@needs_voice
def test_speed_quality_and_voice_change_the_audio(make_ctx, fixtures_dir, no_db):
    _, _, normal = speak(make_ctx, fixtures_dir, "lectura-en.pdf", {"paginas": "3"})
    fast_path, fast_note, fast = speak(make_ctx, fixtures_dir, "lectura-en.pdf", {"paginas": "3", "velocidad": 2.0, "calidad": "192"})
    assert fast["duration"] < 0.7 * normal["duration"]
    assert 185_000 < fast["bitrate"] < 200_000
    male_path, male_note, _ = speak(make_ctx, fixtures_dir, "lectura-en.pdf", {"paginas": "3", "velocidad": 2.0, "calidad": "192",
                                                                               "voz": "hombre"})
    assert "am_michael" in male_note and "af_heart" in fast_note
    assert male_path.read_bytes() != fast_path.read_bytes()


@needs_voice
def test_pause_and_header_options_change_the_duration(make_ctx, fixtures_dir, no_db):
    base = {"paginas": "1", "velocidad": 2.0}
    _, note, short = speak(make_ctx, fixtures_dir, "lectura-en.pdf", {**base, "pausa": 0})
    _, _, paused = speak(make_ctx, fixtures_dir, "lectura-en.pdf", {**base, "pausa": 3})
    # Página 1: título y dos párrafos, así que dos pausas de 3 s.
    assert 5.0 < paused["duration"] - short["duration"] < 7.0
    _, note_all, everything = speak(make_ctx, fixtures_dir, "lectura-en.pdf", {**base, "pausa": 0, "saltar_cabeceras": False})
    assert everything["duration"] > short["duration"] + 1.0
    chars = [int(re.search(r"(\d[\d,.]*) caracteres", n).group(1).replace(".", "").replace(",", "")) for n in (note, note_all)]
    assert chars[1] > chars[0]


@needs_voice
def test_spanish_needs_its_voice_and_auto_detects_it(make_ctx, fixtures_dir, no_db):
    ctx = voiced(make_ctx("pdf-a-audio", [fixtures_dir / "lectura-es.pdf"], {"paginas": "3"}), TTS_VOICE_ES="")
    with pytest.raises(ToolError) as exc:
        run("pdf-a-audio", ctx)
    assert (exc.value.code, exc.value.detail) == (ErrorCode.TOOL_DISABLED, "tts_voice_es")
    path, note, info = speak(make_ctx, fixtures_dir, "lectura-es.pdf", {"paginas": "3"})
    assert note.startswith("Leído en español (detectado) con la voz ef_dora") and info["duration"] > 3
    _, forced, _ = speak(make_ctx, fixtures_dir, "lectura-es.pdf", {"paginas": "3", "idioma": "es", "velocidad": 2.0})
    assert "(detectado)" not in forced
    if whisper_model():
        assert "gracias" in heard(path, "es")


@needs_voice
def test_forced_language_changes_the_voice_and_the_phonemes(make_ctx, fixtures_dir, no_db, monkeypatch):
    """«Idioma» pedido en vez de detectado: el PDF español leído como inglés usa la voz y los fonemas ingleses."""
    base = {"paginas": "3", "velocidad": 2.0}
    auto_path, auto_note, auto = speak(make_ctx, fixtures_dir, "lectura-es.pdf", base)
    langs: list[str] = []
    original = kokoro.phonemes

    def spy(clauses, lang, work):
        langs.append(lang)
        return original(clauses, lang, work)

    monkeypatch.setattr(kokoro, "phonemes", spy)
    ctx = voiced(make_ctx("pdf-a-audio", [fixtures_dir / "lectura-es.pdf"], {**base, "idioma": "en"}), TTS_VOICE_ES="")
    out = run("pdf-a-audio", ctx)
    en_path = Path(out[0]["path"])
    assert auto_note.startswith("Leído en español (detectado) con la voz ef_dora")
    assert out[0]["note"].startswith("Leído en inglés con la voz af_heart") and "(detectado)" not in out[0]["note"]
    assert langs and set(langs) == {"en"}
    assert en_path.read_bytes() != auto_path.read_bytes()
    assert abs(probe(en_path)["duration"] - auto["duration"]) > 0.2


@needs_voice
def test_long_audio_is_encoded_in_segments(make_ctx, fixtures_dir, no_db, monkeypatch):
    monkeypatch.setattr(voz, "SEGMENT_SECONDS", 1)
    ctx = voiced(make_ctx("pdf-a-audio", [fixtures_dir / "lectura-en.pdf"], {"paginas": "1", "velocidad": 2.0, "pausa": 0.2}))
    parts: list[int] = []
    original = voz.Mp3Writer.finish

    def finish(self, dst, title):
        original(self, dst, title)
        parts.append(self.parts)
        parts.append(self.samples)

    monkeypatch.setattr(voz.Mp3Writer, "finish", finish)
    out = run("pdf-a-audio", ctx)
    info = probe(Path(out[0]["path"]))
    assert parts[0] >= 3  # un tramo por párrafo
    assert abs(info["duration"] - parts[1] / 24_000) < 0.06 * parts[0] + 0.05


@needs_voice
def test_worker_checks_limits_language_and_scans(make_ctx, fixtures_dir, no_db, tmp_path):
    ctx = voiced(make_ctx("pdf-a-audio", [fixtures_dir / "lectura-larga.pdf"], plan="free"))
    with pytest.raises(ToolError) as exc:
        run("pdf-a-audio", ctx)
    chars = voz.count(fixtures_dir / "lectura-larga.pdf", "todas", True, 300)["chars"]
    assert exc.value.code == ErrorCode.LIMIT_EXCEEDED and exc.value.detail == f"tts_chars:{chars}>20000" and chars > 20000
    ctx = voiced(make_ctx("pdf-a-audio", [fixtures_dir / "lectura-escaneada.pdf"], {"ocr": False}))
    with pytest.raises(ToolError) as exc:
        run("pdf-a-audio", ctx)
    assert exc.value.code == ErrorCode.INVALID_OPTIONS and exc.value.detail == "ai_scanned:1"
    import sys

    sys.path.insert(0, str(FIXTURES))
    from lectura_pdf import prose_pdf

    french = prose_pdf(tmp_path / "rapport.pdf", [[FRENCH]])
    with pytest.raises(ToolError) as exc:
        run("pdf-a-audio", voiced(make_ctx("pdf-a-audio", [french])))
    assert exc.value.detail == "tts_language"
    ctx = voiced(make_ctx("pdf-a-audio", [fixtures_dir / "lectura-en.pdf"]), KOKORO_HOME=tmp_path)
    with pytest.raises(ToolError) as exc:
        run("pdf-a-audio", ctx)
    assert exc.value.code == ErrorCode.TOOL_DISABLED


@needs_voice
@needs_whisper
def test_synthetic_speech_for_the_transcription_samples(tmp_path):
    """D-114: la voz sintética de las muestras de transcripción se entiende con faster-whisper."""
    import sys

    sys.path.insert(0, str(FIXTURES))
    from lectura_pdf import synthetic_speech

    dst = synthetic_speech("The meeting starts at ten. We will review the budget and the new website.", "en",
                           tmp_path / "reunion.ogg", kokoro_home(), work=tmp_path)
    info = probe(dst)
    assert info["codec"] == "opus" and info["duration"] > 2
    text = heard(dst, "en")
    assert "meeting" in text and "budget" in text


# ——— De extremo a extremo con la API (PostgreSQL y Valkey) ———

@pytest.fixture()
def tts_env(monkeypatch):
    monkeypatch.setenv("KOKORO_HOME", str(kokoro_home()))
    monkeypatch.setenv("TTS_VOICE_ES", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _heavy_tasks(services, owner: str) -> int:
    from sqlalchemy import create_engine, text

    with create_engine(services["db_url"]).begin() as conn:
        return conn.execute(text("SELECT COALESCE(SUM(tasks), 0) FROM usage_daily WHERE owner_id=:o AND cost_class='heavy'"),
                            {"o": owner}).scalar()


@pytest.mark.integration
def test_api_rejects_anonymous_long_and_spanish_without_spending(api, anon_token, user_token, tus_upload, fixtures_dir,
                                                                 services, tts_env):
    token = anon_token()
    uid, _ = tus_upload(token, "pdf-a-audio", fixtures_dir / "lectura-en.pdf")
    resp = api.post("/v1/jobs", json={"tool": "pdf-a-audio", "upload_ids": [uid], "options": {}}, headers=auth(token))
    assert resp.status_code == 401 and "cuenta" in resp.json()["error"]["message"]
    token = user_token(user_id="voz-larga")
    api.get("/v1/me", headers=auth(token))
    uid, _ = tus_upload(token, "pdf-a-audio", fixtures_dir / "lectura-larga.pdf")
    resp = api.post("/v1/jobs", json={"tool": "pdf-a-audio", "upload_ids": [uid], "options": {}}, headers=auth(token))
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "LIMIT_EXCEEDED"
    assert "20000 caracteres" in resp.json()["error"]["message"]
    uid, _ = tus_upload(token, "pdf-a-audio", fixtures_dir / "lectura-es.pdf")
    resp = api.post("/v1/jobs", json={"tool": "pdf-a-audio", "upload_ids": [uid], "options": {}}, headers=auth(token))
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "TOOL_DISABLED"
    assert _heavy_tasks(services, "voz-larga") == 0


@pytest.mark.integration
@needs_voice
@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no instalado")
def test_scanned_pdf_goes_through_ocr_and_back_to_av(api, user_token, tus_upload, fixtures_dir, services, tts_env, monkeypatch):
    from tools import tasks

    hops: list[str] = []

    def send_task(name, args=None, queue=None, **kw):
        hops.append(queue)
        return tasks.execute(*args)

    monkeypatch.setattr(tasks.celery_app, "send_task", send_task)
    token = user_token(user_id="voz-escaneo")
    api.get("/v1/me", headers=auth(token))
    uid, _ = tus_upload(token, "pdf-a-audio", fixtures_dir / "lectura-escaneada.pdf")
    job = api.post("/v1/jobs", json={"tool": "pdf-a-audio", "upload_ids": [uid], "options": {"velocidad": 1.5}},
                   headers=auth(token)).json()
    job = api.get(f"/v1/jobs/{job['id']}", headers=auth(token)).json()
    assert job["status"] == "succeeded", job
    assert hops == ["ocr", "av.heavy"]
    out = job["outputs"][0]
    assert out["name"] == "lectura-escaneada.mp3" and out["mime"] == "audio/mpeg"
    assert "OCR" in out["note"] and "inglés" in out["note"]
    # La lectura (heavy) y el OCR de las páginas escaneadas (otra heavy, como en las herramientas de IA).
    assert _heavy_tasks(services, "voz-escaneo") == 2
