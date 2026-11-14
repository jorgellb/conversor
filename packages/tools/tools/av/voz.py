"""pdf-a-audio (7.6): lee un PDF en voz alta con Kokoro en local (6.4) y entrega un MP3 hecho con el FFmpeg LGPL.

Flujo (cola `av.heavy`, D-166 a D-172):

- La API, antes de encolar, cuenta en un proceso aparte los caracteres que se van a leer (`precheck`): sin cuenta no
  hay acceso (9.3: 0 caracteres), más de `tts_chars_task` se rechaza sin gastar la tarea y la voz española, mientras
  `TTS_VOICE_ES` esté vacía (6.4, a la espera de la escucha del propietario), tampoco se encola.
- El worker saca el texto con pypdfium2 (`document_texts`, como las herramientas de IA); las páginas escaneadas pasan
  por `workerocr` y vuelven (D-124). Quita cabeceras, pies y números de página, arma los párrafos, vuelve a comprobar
  el límite de caracteres (ya con el texto del OCR) y detecta el idioma si se pidió.
- espeak-ng da los fonemas, Kokoro la voz por frases y FFmpeg (LGPL, libmp3lame) el MP3: el audio se codifica por
  tramos de unos 10 minutos que se cortan en una pausa entre párrafos, para que ni la memoria ni el disco crezcan con
  el documento (300.000 caracteres son unas 5 h de voz).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from core.errors import AppError, ErrorCode, ToolError
from core.plans import PlanLimits
from core.settings import Settings
from tools.av import lectura
from tools.base import ToolContext, derived_name, run_engine

SEGMENT_SECONDS = 600
SENTENCE_GAP = 0.12  # segundos de silencio entre dos entradas del modelo dentro de un párrafo
OCR_LANGS = {"auto": ["spa", "eng"], "es": ["spa"], "en": ["eng"]}
VOICES = {"es": {"mujer": "ef_dora", "hombre": "em_alex"}, "en": {"mujer": "af_heart", "hombre": "am_michael"}}
BITRATE = {"128": "128k", "192": "192k"}
NOTES = {
    "es": {"lang": {"es": "español", "en": "inglés"}, "detected": " (detectado)",
           "done": "Leído en {lang}{detected} con la voz {voice} de Kokoro: {duration} de audio, {chars} caracteres.",
           "ocr": "Las páginas escaneadas se han leído con OCR."},
    "en": {"lang": {"es": "Spanish", "en": "English"}, "detected": " (detected)",
           "done": "Read in {lang}{detected} with Kokoro's {voice} voice: {duration} of audio, {chars} characters.",
           "ocr": "Scanned pages were read with OCR."},
}
MESSAGES = {"es": "Generando la voz…", "en": "Generating the voice…"}


def configured_voice(settings: Settings, lang: str) -> str:
    return (settings.TTS_VOICE_ES if lang == "es" else settings.TTS_VOICE_EN).strip()


def voice_for(settings: Settings, lang: str, choice: str) -> str:
    """Voz de Kokoro para el idioma: la configurada o la de mujer u hombre. Un idioma sin voz configurada está apagado
    (la española, hasta la escucha del propietario: 6.4)."""
    default = configured_voice(settings, lang)
    if not default:
        raise ToolError(ErrorCode.TOOL_DISABLED, f"tts_voice_{lang}")
    return default if choice == "predeterminada" else VOICES[lang][choice]


def clock(seconds: float) -> str:
    s = int(round(seconds))
    h, rest = divmod(s, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def thousands(n: int, locale: str) -> str:
    text = f"{n:,}"
    return text.replace(",", ".") if locale == "es" else text


# ——— Antes de encolar (API) ———

def count(path: Path, paginas: str, skip: bool, max_pages: int, timeout: int = 90) -> dict | None:
    """Cuenta en un proceso aparte (`contar_texto.py`); None si no ha podido (el worker volverá a comprobarlo todo).

    Antes, la API se marca con PR_SET_DUMPABLE=0 (como los workers): el proceso que abre el PDF corre con el mismo usuario
    y, sin eso, podría leer los secretos de la API en /proc/<pid>/environ."""
    from core.envguard import harden_process

    harden_process()
    script = Path(__file__).with_name("contar_texto.py")
    with tempfile.TemporaryDirectory(prefix="contar-") as tmp:
        try:
            res = run_engine([sys.executable, "-I", str(script), str(path), paginas, "1" if skip else "0", str(max_pages)],
                             cwd=Path(tmp), timeout=timeout, mem_mb=1024)
            return json.loads(res.stdout or b"null")
        except (ToolError, ValueError, OSError):
            return None


def precheck(settings: Settings, plan: PlanLimits, owner_type: str, options: dict, paths: list[Path]) -> None:
    """9.3 y 6.4 antes de encolar: cuenta, caracteres por tarea y voz del idioma."""
    limit = plan.tts_chars_task
    if limit <= 0:
        raise AppError(ErrorCode.UNAUTHORIZED if owner_type == "anon" else ErrorCode.QUOTA_EXCEEDED,
                       status=401 if owner_type == "anon" else 403, detail="tts_account")
    lang = options.get("idioma", "auto")
    if lang in ("es", "en") and not configured_voice(settings, lang):
        raise AppError(ErrorCode.TOOL_DISABLED, status=400, detail=f"tts_voice_{lang}")
    for path in paths:
        info = count(path, options.get("paginas", "todas"), bool(options.get("saltar_cabeceras", True)), plan.pdf_pages)
        if not info:
            continue
        error = info.get("error")
        if error == "password":
            raise AppError(ErrorCode.PASSWORD_REQUIRED, status=400)
        if error == "corrupt":
            raise AppError(ErrorCode.CORRUPT_FILE, status=422)
        if error == "pages":
            raise AppError(ErrorCode.LIMIT_EXCEEDED, status=400, detail=f"{info.get('pages')} páginas; límite {plan.pdf_pages}")
        if error == "range":
            raise AppError(ErrorCode.INVALID_OPTIONS, status=400, detail="paginas")
        if info["chars"] > limit:
            raise AppError(ErrorCode.LIMIT_EXCEEDED, status=400, detail=f"tts_chars:{info['chars']}>{limit}",
                           extra={"chars": info["chars"], "max": limit})
        if not info["scanned"] and not info["chars"]:
            raise AppError(ErrorCode.INVALID_OPTIONS, status=400, detail="tts_empty")
        detected = info.get("language")
        if lang == "auto" and detected and not configured_voice(settings, detected):
            raise AppError(ErrorCode.TOOL_DISABLED, status=400, detail=f"tts_voice_{detected}")


# ——— En el worker ———

class Mp3Writer:
    """Recibe la voz por trozos y la va pasando a MP3 por tramos de `SEGMENT_SECONDS`: PCM de 16 bits en el disco de
    trabajo, un MP3 por tramo (sin cabecera Xing) añadido al final del resultado y, al acabar, una copia sin recodificar
    que escribe la cabecera con la duración exacta."""

    def __init__(self, ctx: ToolContext, bitrate: str):
        self.ctx = ctx
        self.bitrate = bitrate
        self.pcm = ctx.work / "voz.pcm"
        self.joined = ctx.work / "voz-tramos.mp3"
        self.samples = 0
        self.pending = 0
        self.parts = 0
        self._file = open(self.pcm, "wb")  # noqa: SIM115 - se cierra en flush()

    @property
    def seconds(self) -> float:
        return self.samples / 24_000

    def add(self, audio) -> None:
        import numpy as np

        data = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
        self._file.write(data.tobytes())
        self.samples += data.size
        self.pending += data.size

    def silence(self, seconds: float) -> None:
        import numpy as np

        if seconds > 0:
            self.add(np.zeros(int(24_000 * seconds), dtype=np.float32))

    def flush(self) -> None:
        """Codifica lo pendiente como un tramo más (se llama en una pausa entre párrafos)."""
        from tools.av.audio import BASE, ffmpeg

        self._file.close()
        if self.pending:
            part = self.ctx.work / "voz-tramo.mp3"
            run_engine([ffmpeg(), *BASE, "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(self.pcm), "-ar", "44100",
                        "-c:a", "libmp3lame", "-b:a", BITRATE[self.bitrate], "-write_xing", "0", "-id3v2_version", "0",
                        "-map_metadata", "-1", "-threads", "1", "-f", "mp3", "-y", str(part)],
                       cwd=self.ctx.work, timeout=int(120 + self.pending / 24_000), mem_mb=1024)
            with open(self.joined, "ab") as out, open(part, "rb") as src:
                shutil.copyfileobj(src, out)
            part.unlink(missing_ok=True)
            self.parts += 1
        self.pending = 0
        self._file = open(self.pcm, "wb")  # noqa: SIM115

    def finish(self, dst: Path, title: str) -> None:
        from tools.av.audio import BASE, ffmpeg

        self.flush()
        self._file.close()
        self.pcm.unlink(missing_ok=True)
        if not self.parts:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "tts_empty")
        run_engine([ffmpeg(), *BASE, "-f", "mp3", "-i", str(self.joined), "-map", "0:a:0", "-c:a", "copy", "-map_metadata", "-1",
                    "-metadata", f"title={title[:200]}", "-id3v2_version", "3", "-f", "mp3", "-y", str(dst)],
                   cwd=self.ctx.work, timeout=int(120 + self.seconds / 20), mem_mb=1024)
        self.joined.unlink(missing_ok=True)

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()


def text_of(ctx: ToolContext) -> tuple[list[str], bool]:
    """Párrafos que se leen y si alguna página ha pasado por el OCR (el trabajo vuelve de `ocr` con la etapa «av»)."""
    from tools.ai import documento

    o = ctx.options
    _, pages = documento.text_of(ctx, ctx.inputs[0], ai_pages=False, ocr_langs=OCR_LANGS[o.idioma])
    # Todas las páginas (ya leídas y guardadas), para reconocer las cabeceras aunque solo se pida un rango.
    everything = [p or "" for p in documento.load(ctx, ctx.inputs[0])]
    return lectura.paragraphs(pages, o.saltar_cabeceras, everything), ctx.stage == "av"


def run(ctx: ToolContext) -> list[dict]:
    from tools.av import kokoro

    o = ctx.options
    inp = ctx.inputs[0]
    limit = ctx.plan.tts_chars_task
    if limit <= 0:
        raise ToolError(ErrorCode.UNAUTHORIZED, "tts_account")
    if ctx.stage != "ocr":
        # Antes de leer nada (y antes de pasar por el OCR): sin motor no hay trabajo que hacer.
        kokoro.espeak()
        if not kokoro.available(ctx.settings):
            raise ToolError(ErrorCode.TOOL_DISABLED, f"Falta el modelo de Kokoro en {ctx.settings.KOKORO_HOME}")
    paras, ocr = text_of(ctx)
    total = lectura.chars(paras)
    if not total:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "tts_empty")
    if total > limit:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"tts_chars:{total}>{limit}")
    detected = o.idioma == "auto"
    lang = lectura.detect_language(" ".join(paras), "en" if ctx.locale == "en" else "es") if detected else o.idioma
    if lang is None:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "tts_language")
    voice_name = voice_for(ctx.settings, lang, o.voz)
    voice = kokoro.load_voice(kokoro.voice_path(ctx.settings, voice_name, lang))
    model = kokoro.load_model(ctx.settings, ctx.threads)
    ctx.report(0.0, MESSAGES.get(ctx.locale, MESSAGES["es"]))

    name = derived_name(inp.name, "", "mp3")
    writer = Mp3Writer(ctx, o.calidad)
    done = 0
    try:
        for n, para in enumerate(paras):
            sentences = [lectura.clauses(s) for s in lectura.sentences(para)]
            flat = [c for s in sentences for c in s]
            if not flat:
                continue
            ps = iter(kokoro.phonemes(flat, lang, ctx.work))
            grouped = [[(next(ps), c.mark) for c in s] for s in sentences]
            for k, ids in enumerate(kokoro.chunks(model, grouped)):
                if k:
                    writer.silence(SENTENCE_GAP)
                    if writer.pending >= 2 * SEGMENT_SECONDS * 24_000:
                        writer.flush()  # un párrafo larguísimo: el tramo se corta entre dos frases
                writer.add(kokoro.synthesize(model, voice, ids, o.velocidad))
            done += len(para)
            if n + 1 < len(paras):
                writer.silence(o.pausa)
                if writer.pending >= SEGMENT_SECONDS * 24_000:
                    writer.flush()
            ctx.report(min(0.98, done / total), None)
        dst = ctx.output(name)
        writer.finish(dst, Path(inp.name).stem)
    finally:
        writer.close()
        writer.pcm.unlink(missing_ok=True)
    t = NOTES.get(ctx.locale, NOTES["es"])
    note = t["done"].format(lang=t["lang"][lang], detected=t["detected"] if detected else "", voice=voice_name,
                            duration=clock(writer.seconds), chars=thousands(total, ctx.locale))
    if ocr:
        note = f"{note} {t['ocr']}"
    return [{"path": str(dst), "name": name, "note": note}]
