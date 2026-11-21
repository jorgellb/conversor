"""Grabaciones que pasan de `av.heavy` a `ai` (F3-E: traducir-subtitulos y resumir-reunion).

`workerav` transcribe con faster-whisper (6.4) y no tiene la clave de OpenRouter; `workerai` tiene la clave y no tiene
FFmpeg ni Whisper (12.2). Por eso el trabajo se encadena (D-174):

1. En `av.heavy`, FFmpeg comprueba la duración del tramo elegido contra el plan (9.3), se estiman las peticiones de IA
   que hará la segunda etapa y se reservan antes de transcribir (si no caben en el plan, falla sin gastar nada ni
   transcribir horas de audio). Después se transcribe solo ese tramo y lo que necesita la etapa de IA (subtítulos o
   párrafos) se guarda en `document_texts` del propietario, con la caducidad de sus archivos.
2. En `ai`, se lee eso y se hacen las peticiones. Si algo falla en cualquiera de las dos, `tools.tasks` devuelve las
   peticiones reservadas que no se han usado (D-121).

La clave del texto guardado incluye la herramienta y las opciones que cambian la transcripción (idioma, precisión,
tramo y ancho de línea), para que otra herramienta u otras opciones no reutilicen una transcripción que no les sirve.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from pathlib import Path

from core.ai.store import texts_get, texts_put
from core.db import session_scope
from core.errors import ErrorCode, ToolError
from tools.av.specs import AUDIO_INPUTS, LANGUAGES, VIDEO_INPUTS, parse_time
from tools.base import InputFile, ToolContext

MEDIA_INPUTS = (*AUDIO_INPUTS, *VIDEO_INPUTS)
EXTRACTOR = "faster-whisper"
# Caracteres por minuto de una conversación a ritmo normal (unas 150 palabras de 6 caracteres con el espacio). Solo
# sirve para avisar y reservar antes de transcribir; después se cuenta el texto de verdad (D-174).
SPEECH_CHARS_PER_MINUTE = 900
MESSAGES = {
    "transcribe": {"es": "Transcribiendo el audio…", "en": "Transcribing the audio…"},
    "ai": {"es": "Preparando la petición a la IA…", "en": "Preparing the AI request…"},
}


def is_media(inp: InputFile) -> bool:
    return inp.ext in MEDIA_INPUTS


def message(kind: str, locale: str) -> str:
    return MESSAGES[kind].get(locale, MESSAGES[kind]["es"])


def span_of(options) -> tuple[float, float | None]:
    """El tramo elegido en segundos: (desde, hasta o None hasta el final)."""
    start = parse_time(options.desde) or 0.0
    end = parse_time(options.hasta)
    if end is not None and end <= start:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "subs_range")
    return start, end


def key(inp: InputFile, tool: str, params: dict) -> str:
    material = json.dumps([inp.sha256, tool, params], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()


def load(ctx: ToolContext, inp: InputFile, tool: str, params: dict) -> dict | None:
    with session_scope() as s:
        row = texts_get(s, ctx.owner[0], ctx.owner[1], key(inp, tool, params), ctx.now())
        return dict(row.pages[0]) if row is not None and row.pages else None


def save(ctx: ToolContext, inp: InputFile, tool: str, params: dict, payload: dict) -> None:
    with session_scope() as s:
        texts_put(s, ctx.owner[0], ctx.owner[1], key(inp, tool, params), [payload], f"{EXTRACTOR}-{payload.get('model', '')}"[:40],
                  ctx.expires_at)


def check_requests(ctx: ToolContext, needed: int) -> None:
    """Más peticiones que el máximo por tarea: se pide un tramo más corto (6.3). Si caben, se reservan todas antes de
    empezar; si el plan no tiene tantas hoy, falla sin gastar ninguna."""
    budget = ctx.ai.budget
    top = budget.max_task
    # Margen para los reintentos (un 429, un JSON que hay que reparar) y, si el trabajo se vuelve a poner en cola, lo que
    # ya se gastó: si no, la tarea podía quedarse sin peticiones a mitad, con todo lo anterior gastado (D-263).
    headroom = max(1, top // 10)
    if budget.used + needed > top - headroom:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"ai_span:{needed}>{max(1, top - headroom - budget.used)}")
    budget.ensure(budget.used + needed)


def probe_span(ctx: ToolContext, inp: InputFile, start: float, end: float | None) -> tuple[str, float]:
    """Demultiplexor y duración del tramo elegido, que es lo que cuenta para el límite de minutos del plan (9.3)."""
    from tools.av.audio import DEMUXER, probe

    demuxer = DEMUXER.get(inp.ext)
    if not demuxer:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT)
    info = probe(inp.path, demuxer, ctx.work)
    if not any(st.get("codec_type") == "audio" for st in info.get("streams", [])):
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "Sin pista de audio")
    duration = float(info.get("format", {}).get("duration") or 0)
    if duration <= 0:  # sin duración en la cabecera (WebM grabado con MediaRecorder): la de la pista, si la hay
        duration = max((float(st.get("duration") or 0) for st in info.get("streams", []) if st.get("codec_type") == "audio"), default=0.0)
    limit = ctx.plan.audio_minutes * 60
    if duration <= 0:
        # Sin ninguna duración: se calcula con el peor caso (el máximo del plan) y decode_pcm mide lo que hay de verdad (D-263).
        length = (end - start) if end is not None else limit
        if length > limit:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"audio_minutes:{clock(length)}>{ctx.plan.audio_minutes}")
        return demuxer, length
    if start >= duration:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "subs_range")
    length = min(end, duration) - start if end is not None else duration - start
    if length > limit:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"audio_minutes:{clock(length)}>{ctx.plan.audio_minutes}")
    return demuxer, length


def transcribe_stage(ctx: ToolContext, tool: str, params: dict, estimate: Callable[[int], int],
                     build: Callable[[object], dict], words: bool) -> None:
    """Etapa de `av.heavy`: transcribe el tramo (si no estaba ya guardado) y pasa el trabajo a `ai`.

    `estimate(caracteres)` da las peticiones que se harían con ese texto; `build(transcripción)` da lo que se guarda."""
    from tools.av import transcribe as tr

    inp = ctx.inputs[0]
    if load(ctx, inp, tool, params) is None:
        o = ctx.options
        start, end = span_of(o)
        demuxer, length = probe_span(ctx, inp, start, end)
        check_requests(ctx, estimate(max(1, math.ceil(length / 60 * SPEECH_CHARS_PER_MINUTE))))
        notes: list[str] = []
        model = tr.pick_model(ctx, o.precision, notes)
        pcm_path = ctx.work / "audio.pcm"
        pcm = tr.decode_pcm(ctx, inp, demuxer, start + length, pcm_path, start=start, length=length)
        try:
            language = params.get("idioma") or "auto"
            result = tr.transcribe(ctx, pcm, None if language == "auto" else language, model, (0.0, 0.8), words)
        finally:
            del pcm
            pcm_path.unlink(missing_ok=True)
        if not result.segments:
            raise ToolError(ErrorCode.NO_SPEECH)
        if start:
            for seg in result.segments:
                seg.start, seg.end = seg.start + start, seg.end + start
                for w in seg.words:
                    w.start, w.end = w.start + start, w.end + start
        payload = {"language": result.language, "probability": round(result.probability, 3), "duration": round(length, 3),
                   "model": result.model, "notes": notes, **build(result)}
        save(ctx, inp, tool, params, payload)
    ctx.handoff("ai", "ai", message("ai", ctx.locale))


def clock(seconds: float) -> str:
    """«05:30» o «1:02:03» (sin redondear hacia arriba: 30 min y 2 s son «30:02»)."""
    s = int(seconds)
    h, rest = divmod(s, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def language_label(code: str, locale: str) -> str:
    """Nombre del idioma que ha detectado (o que se ha elegido para) la transcripción, para las notas del resultado."""
    names = LANGUAGES.get(code)
    if not names or code == "auto":
        return code or "?"
    return names[1] if locale == "en" else names[0].lower()


def stem_of(name: str) -> str:
    return Path(name).stem or "grabacion"
