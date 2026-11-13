"""transcribir-audio y video-a-subtitulos (7.10): faster-whisper local en CPU (6.4), sin red y sin PyAV.

- FFmpeg (proceso aparte, la compilación LGPL de la imagen) decodifica la pista de audio a PCM mono de 16 kHz en el
  disco de trabajo; faster-whisper recibe las muestras. Así no hace falta PyAV, cuyas ruedas traen x264 y x265 (GPL)
  dentro de libavcodec (D-111).
- El modelo (`WHISPER_MODEL`, small en int8 por defecto; medium opcional) está en la imagen, en `WHISPER_HOME`, con su
  SHA-256 comprobado al construirla; nunca se descarga al ejecutar.
- El audio largo se transcribe por tramos de unos 20 minutos cortados en el momento más silencioso, para que la memoria
  no crezca con la duración (4 h de audio son 460 MB en PCM de 16 bits).
"""
from __future__ import annotations

import re
import sys
import threading
import types
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from core.errors import ErrorCode, ToolError
from core.settings import Settings
from tools.av.audio import BASE, checked_input, ffmpeg
from tools.base import InputFile, ToolContext, derived_name, run_engine
from tools.pdf.common import with_batch_zip

RATE = 16_000
CHUNK_SECONDS = 20 * 60
SEARCH_SECONDS = 15
MODELS = ("tiny", "base", "small", "medium")

LANGUAGE_NAMES = {
    "es": ("español", "Spanish"), "en": ("inglés", "English"), "ca": ("catalán", "Catalan"), "eu": ("euskera", "Basque"),
    "gl": ("gallego", "Galician"), "fr": ("francés", "French"), "de": ("alemán", "German"), "it": ("italiano", "Italian"),
    "pt": ("portugués", "Portuguese"), "nl": ("neerlandés", "Dutch"), "pl": ("polaco", "Polish"), "ro": ("rumano", "Romanian"),
    "ru": ("ruso", "Russian"), "uk": ("ucraniano", "Ukrainian"), "ar": ("árabe", "Arabic"), "zh": ("chino", "Chinese"),
    "ja": ("japonés", "Japanese"), "ko": ("coreano", "Korean"), "hi": ("hindi", "Hindi"), "tr": ("turco", "Turkish"),
}


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Cue:
    start: float
    end: float
    lines: list[str]


@dataclass
class Transcript:
    segments: list[Segment]
    language: str
    probability: float
    duration: float
    model: str


# ——— Modelo ———

_MODELS: dict[tuple, object] = {}
_LOCK = threading.Lock()


def _whisper_class():
    """faster-whisper sin PyAV: su `audio.py` hace `import av`, que aquí no se usa (decodifica FFmpeg aparte)."""
    if "av" not in sys.modules:
        stub = types.ModuleType("av")
        stub.__doc__ = "Sustituto vacío: PyAV no se instala (sus ruedas traen x264 y x265, GPL; D-111)."
        sys.modules["av"] = stub
    from faster_whisper import WhisperModel

    return WhisperModel


def model_dir(settings: Settings, name: str) -> Path:
    if name not in MODELS:
        raise ToolError(ErrorCode.INTERNAL, f"Modelo de transcripción desconocido: {name}")
    return Path(settings.WHISPER_HOME) / f"faster-whisper-{name}"


def available(settings: Settings, name: str) -> bool:
    try:
        return (model_dir(settings, name) / "model.bin").is_file()
    except ToolError:
        return False


def load_model(settings: Settings, name: str, threads: int):
    """El modelo en memoria se reutiliza entre trabajos del mismo proceso (cargarlo tarda unos segundos)."""
    path = model_dir(settings, name)
    if not (path / "model.bin").is_file():
        raise ToolError(ErrorCode.TOOL_DISABLED, f"Falta el modelo de transcripción {name} en {path}")
    key = (str(path), settings.WHISPER_DEVICE, settings.WHISPER_COMPUTE_TYPE, max(1, threads))
    with _LOCK:
        model = _MODELS.get(key)
        if model is None:
            whisper = _whisper_class()
            _MODELS.clear()
            model = whisper(str(path), device=settings.WHISPER_DEVICE, compute_type=settings.WHISPER_COMPUTE_TYPE,
                            cpu_threads=max(1, threads), num_workers=1, local_files_only=True)
            _MODELS[key] = model
    return model


# ——— Audio ———

def decode_pcm(ctx: ToolContext, inp: InputFile, demuxer: str, duration: float, dst: Path) -> np.ndarray:
    """La primera pista de audio en PCM de 16 bits, mono y 16 kHz, en el disco (se lee por tramos con memmap)."""
    run_engine([ffmpeg(), *BASE, "-f", demuxer, "-i", str(inp.path), "-map", "0:a:0", "-vn", "-sn", "-dn", "-ac", "1",
                "-ar", str(RATE), "-c:a", "pcm_s16le", "-f", "s16le", "-threads", str(max(1, ctx.threads)), "-y", str(dst)],
               cwd=ctx.work, timeout=int(max(120, duration + 120)), mem_mb=1024)
    if not dst.exists() or dst.stat().st_size < 2:
        raise ToolError(ErrorCode.CORRUPT_FILE, "Sin audio que transcribir")
    return np.memmap(dst, dtype=np.int16, mode="r")


def chunk_bounds(samples: np.ndarray, rate: int = RATE, chunk: int = CHUNK_SECONDS, search: int = SEARCH_SECONDS) -> list[tuple[int, int]]:
    """Tramos de unos `chunk` segundos que terminan en el cuarto de segundo más silencioso cerca de cada corte."""
    n = len(samples)
    bounds: list[tuple[int, int]] = []
    start = 0
    window = rate // 4
    while n - start > int(chunk * rate * 1.1):
        target = start + chunk * rate
        lo = max(start + rate, target - search * rate)
        hi = min(n - rate, target + search * rate)
        frames = max(1, (hi - lo) // window)
        seg = np.asarray(samples[lo:lo + frames * window], dtype=np.float32).reshape(frames, window)
        cut = lo + int(np.argmin((seg * seg).mean(axis=1))) * window + window // 2
        bounds.append((start, cut))
        start = cut
    bounds.append((start, n))
    return bounds


def transcribe(ctx: ToolContext, pcm: np.ndarray, language: str | None, model_name: str, share: tuple[float, float] = (0.0, 1.0),
               words: bool = True) -> Transcript:
    """Transcribe las muestras con el filtro de silencios de Silero (y marcas por palabra si hacen falta para los
    subtítulos) e informa del avance."""
    model = load_model(ctx.settings, model_name, ctx.threads)
    total = len(pcm) / RATE
    segments: list[Segment] = []
    detected: str | None = language
    probability = 1.0 if language else 0.0
    begin, span = share
    for a, b in chunk_bounds(pcm, chunk=CHUNK_SECONDS, search=SEARCH_SECONDS):
        audio = np.asarray(pcm[a:b], dtype=np.float32) / 32768.0
        offset = a / RATE
        parts, info = model.transcribe(audio, language=detected, task="transcribe", vad_filter=True, word_timestamps=words,
                                       beam_size=5, condition_on_previous_text=True)
        if detected is None:
            detected, probability = info.language, float(info.language_probability)
        for s in parts:
            words = [Word(offset + float(w.start), offset + float(w.end), w.word.strip()) for w in (s.words or []) if w.word.strip()]
            text = re.sub(r"\s+", " ", s.text).strip()
            if text:
                segments.append(Segment(offset + float(s.start), offset + float(s.end), text, words))
            ctx.report(begin + span * min(0.99, (offset + float(s.end)) / max(total, 1e-6)), None)
    return Transcript(segments, detected or "", probability, total, model_name)


# ——— Texto ———

def clock(seconds: float) -> str:
    s = int(seconds)
    h, rest = divmod(s, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def timestamp(seconds: float, sep: str = ",") -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def paragraphs(segments: list[Segment], pause: float = 1.5, max_chars: int = 700) -> list[tuple[float, str]]:
    """Párrafos: se empieza otro tras una pausa larga o cuando el párrafo ya es largo y acaba una frase."""
    out: list[tuple[float, str]] = []
    current: list[str] = []
    start = 0.0
    last_end = 0.0
    length = 0
    for s in segments:
        sentence_end = bool(current) and current[-1][-1:] in ".?!…"
        if current and (s.start - last_end >= pause or (length >= max_chars and sentence_end)):
            out.append((start, " ".join(current)))
            current, length = [], 0
        if not current:
            start = s.start
        current.append(s.text)
        length += len(s.text) + 1
        last_end = s.end
    if current:
        out.append((start, " ".join(current)))
    return out


def as_text(paras: list[tuple[float, str]], stamps: bool) -> str:
    return "\n\n".join(f"[{clock(t)}] {p}" if stamps else p for t, p in paras) + "\n"


def words_of(segment: Segment) -> list[Word]:
    """Las palabras con su tiempo; si el modelo no las dio, se reparte el del segmento según la longitud de cada una."""
    if segment.words:
        return segment.words
    tokens = segment.text.split()
    if not tokens:
        return []
    total = sum(len(t) for t in tokens)
    out, t = [], segment.start
    for tok in tokens:
        d = (segment.end - segment.start) * len(tok) / total
        out.append(Word(t, t + d, tok))
        t += d
    return out


def _balance(words: list[str], max_chars: int) -> list[str]:
    """Una o dos líneas; con dos, el corte más cercano a la mitad que deja las dos dentro del ancho."""
    text = " ".join(words)
    if len(text) <= max_chars:
        return [text]
    best: tuple[int, int] | None = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if len(a) <= max_chars and len(b) <= max_chars:
            score = abs(len(a) - len(b))
            if best is None or score < best[0]:
                best = (score, i)
    if best is None:
        return [text]
    return [" ".join(words[:best[1]]), " ".join(words[best[1]:])]


def cues(segments: list[Segment], max_chars: int = 42, max_lines: int = 2, max_duration: float = 7.0,
         min_duration: float = 1.0, pause: float = 1.0) -> list[Cue]:
    """Subtítulos de hasta `max_lines` líneas de `max_chars` caracteres y `max_duration` segundos, cortados en pausas
    y finales de frase; cada uno dura al menos `min_duration` si cabe antes del siguiente."""
    groups: list[list[Word]] = []
    current: list[Word] = []
    capacity = max_chars * max_lines
    for w in (w for s in segments for w in words_of(s)):
        if current:
            joined = len(" ".join(x.text for x in current)) + 1 + len(w.text)
            too_long = joined > capacity or len(_balance([x.text for x in current] + [w.text], max_chars)) > max_lines
            sentence = current[-1].text[-1:] in ".?!…" and (w.start - current[0].start) > 1.5
            if too_long or w.start - current[-1].end >= pause or w.end - current[0].start > max_duration or sentence:
                groups.append(current)
                current = []
        current.append(w)
    if current:
        groups.append(current)
    out = [Cue(g[0].start, g[-1].end, _balance([w.text for w in g], max_chars)) for g in groups]
    for i, c in enumerate(out):
        # Al menos `min_duration`, sin pisar el siguiente (con 50 ms entre los dos).
        want = max(c.end, c.start + min_duration)
        nxt = out[i + 1].start - 0.05 if i + 1 < len(out) else None
        c.end = min(want, nxt) if nxt is not None and nxt > c.start else want
    return out


def as_srt(items: list[Cue]) -> str:
    return "".join(f"{i}\n{timestamp(c.start)} --> {timestamp(c.end)}\n" + "\n".join(c.lines) + "\n\n" for i, c in enumerate(items, 1))


def as_vtt(items: list[Cue]) -> str:
    return "WEBVTT\n\n" + "".join(f"{timestamp(c.start, '.')} --> {timestamp(c.end, '.')}\n" + "\n".join(c.lines) + "\n\n" for c in items)


def write_docx(dst: Path, title: str, paras: list[tuple[float, str]], stamps: bool, subtitle: str) -> None:
    """DOCX con un título, una línea con el idioma y la duración, y los párrafos (con su minuto, si se pide)."""
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()
    props = doc.core_properties
    props.author = ""
    props.last_modified_by = ""
    props.comments = ""
    props.title = title
    doc.add_heading(title, level=1)
    info = doc.add_paragraph()
    run = info.add_run(subtitle)
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
    for t, text in paras:
        p = doc.add_paragraph()
        if stamps:
            r = p.add_run(f"[{clock(t)}] ")
            r.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
        p.add_run(text)
    doc.save(str(dst))


# ——— Herramientas ———

def language_label(code: str, locale: str) -> str:
    names = LANGUAGE_NAMES.get(code)
    return (names[0] if locale == "es" else names[1]) if names else code


def pick_model(ctx: ToolContext, precision: str, notes: list[str]) -> str:
    """«Alta» usa medium si la imagen lo trae (es opcional, 6.4); si no, el de siempre, con un aviso."""
    default = ctx.settings.WHISPER_MODEL
    if precision != "alta" or default == "medium":
        return default
    if available(ctx.settings, "medium"):
        return "medium"
    notes.append("La precisión alta (modelo medium) no está instalada en este servidor: se ha usado la normal."
                 if ctx.locale == "es" else "High accuracy (medium model) is not installed on this server: normal accuracy was used.")
    return default


def _prepare(ctx: ToolContext, n: int, inp: InputFile, language: str, model: str, words: bool) -> Transcript:
    demuxer, duration, _ = checked_input(ctx, inp)
    pcm_path = ctx.work / f"audio-{n}.pcm"
    pcm = decode_pcm(ctx, inp, demuxer, duration, pcm_path)
    try:
        share = (n / len(ctx.inputs), 1 / len(ctx.inputs))
        result = transcribe(ctx, pcm, None if language == "auto" else language, model, share, words)
    finally:
        del pcm
        pcm_path.unlink(missing_ok=True)
    if not result.segments:
        raise ToolError(ErrorCode.NO_SPEECH)
    return result


def _summary(ctx: ToolContext, inp: InputFile, t: Transcript, detected: bool) -> str:
    lang = language_label(t.language, ctx.locale)
    if ctx.locale == "es":
        return f"{inp.name}: {lang}{f' (detectado, {t.probability:.0%})' if detected else ''}, {clock(t.duration)}."
    return f"{inp.name}: {lang}{f' (detected, {t.probability:.0%})' if detected else ''}, {clock(t.duration)}."


def run_transcribe(ctx: ToolContext) -> list[dict]:
    """transcribir-audio: TXT, DOCX o SRT (o los tres), con el minuto de cada párrafo si se pide."""
    o = ctx.options
    notes: list[str] = []
    model = pick_model(ctx, o.precision, notes)
    formats = ["txt", "docx", "srt"] if o.formato == "todos" else [o.formato]
    outputs: list[dict] = []
    for n, inp in enumerate(ctx.inputs):
        t = _prepare(ctx, n, inp, o.idioma, model, words="srt" in formats)
        note = " ".join([*notes, _summary(ctx, inp, t, o.idioma == "auto")])
        paras = paragraphs(t.segments)
        for fmt in formats:
            name = derived_name(inp.name, "", fmt)
            dst = ctx.output(name)
            if fmt == "txt":
                dst.write_text(as_text(paras, o.marcas_de_tiempo), encoding="utf-8")
            elif fmt == "srt":
                dst.write_text(as_srt(cues(t.segments)), encoding="utf-8")
            else:
                subtitle = (f"Transcripción automática · {language_label(t.language, 'es')} · {clock(t.duration)}" if ctx.locale == "es"
                            else f"Automatic transcription · {language_label(t.language, 'en')} · {clock(t.duration)}")
                write_docx(dst, Path(inp.name).stem, paras, o.marcas_de_tiempo, subtitle)
            outputs.append({"path": str(dst), "name": name, "note": note})
    return with_batch_zip(ctx, outputs, "transcripciones.zip")


def run_subtitles(ctx: ToolContext) -> list[dict]:
    """video-a-subtitulos: SRT o VTT (o los dos) con líneas del ancho pedido."""
    o = ctx.options
    notes: list[str] = []
    model = pick_model(ctx, o.precision, notes)
    formats = ["srt", "vtt"] if o.formato == "ambos" else [o.formato]
    outputs: list[dict] = []
    for n, inp in enumerate(ctx.inputs):
        t = _prepare(ctx, n, inp, o.idioma, model, words=True)
        note = " ".join([*notes, _summary(ctx, inp, t, o.idioma == "auto")])
        items = cues(t.segments, max_chars=o.caracteres_por_linea)
        for fmt in formats:
            name = derived_name(inp.name, "", fmt)
            dst = ctx.output(name)
            dst.write_text(as_srt(items) if fmt == "srt" else as_vtt(items), encoding="utf-8")
            outputs.append({"path": str(dst), "name": name, "note": note})
    return with_batch_zip(ctx, outputs, "subtitulos.zip")
