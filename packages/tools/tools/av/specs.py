"""Audio con FFmpeg (7.8): conversiones a MP3 y WAV, cortar, unir, normalizar y cambiar la velocidad."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, field_validator

from core.options import opt
from core.registry import ToolSpec

CHANNELS = {"original": ("Como el original", "As original"), "mono": ("Mono", "Mono"), "estereo": ("Estéreo", "Stereo")}
OUTPUTS = {"mismo": ("Mismo formato que el original", "Same format as the original"), "mp3": ("MP3", "MP3"), "wav": ("WAV", "WAV")}
TIME = re.compile(r"^\s*(?:(\d+):)?(?:(\d{1,2}):)?(\d+(?:[.,]\d+)?)\s*$")


def parse_time(text: str) -> float | None:
    """«90», «1:30», «01:01:30,5» → segundos; cadena vacía → None."""
    if not text or not text.strip():
        return None
    m = TIME.match(text)
    if not m:
        raise ValueError(f"Tiempo no válido: {text}")
    a, b, c = m.groups()
    seconds = float(c.replace(",", "."))
    if b is not None:  # h:mm:ss
        return int(a) * 3600 + int(b) * 60 + seconds
    if a is not None:  # mm:ss
        return int(a) * 60 + seconds
    return seconds


class AudioOptions(BaseModel):
    calidad: Literal["128", "192", "320", "vbr"] = opt("192", "Calidad MP3", "MP3 quality",
                                                      labels={"128": ("128 kbps", "128 kbps"), "192": ("192 kbps", "192 kbps"),
                                                              "320": ("320 kbps", "320 kbps"), "vbr": ("VBR (variable)", "VBR (variable)")})
    canales: Literal["original", "mono", "estereo"] = opt("original", "Canales", "Channels", labels=CHANNELS)
    normalizar: bool = opt(False, "Normalizar volumen", "Normalize volume", advanced=True)


class WavOptions(BaseModel):
    frecuencia: Literal["44100", "48000"] = opt("44100", "Frecuencia de muestreo", "Sample rate",
                                                labels={"44100": ("44,1 kHz", "44.1 kHz"), "48000": ("48 kHz", "48 kHz")})
    canales: Literal["original", "mono", "estereo"] = opt("original", "Canales", "Channels", labels=CHANNELS)
    normalizar: bool = opt(False, "Normalizar volumen", "Normalize volume", advanced=True)


class CortarAudioOptions(BaseModel):
    inicio: str = opt("0:00", "Inicio (h:mm:ss)", "Start (h:mm:ss)", max_length=20)
    fin: str = opt("", "Final (vacío: hasta el final)", "End (empty: until the end)", max_length=20)
    fundido_entrada: float = opt(0, "Fundido de entrada (s)", "Fade in (s)", ge=0, le=10, advanced=True)
    fundido_salida: float = opt(0, "Fundido de salida (s)", "Fade out (s)", ge=0, le=10, advanced=True)
    salida: Literal["mismo", "mp3", "wav"] = opt("mismo", "Formato de salida", "Output format", labels=OUTPUTS, advanced=True)

    @field_validator("inicio", "fin")
    @classmethod
    def _time(cls, v: str) -> str:
        parse_time(v)
        return v


class UnirAudiosOptions(BaseModel):
    pausa: float = opt(0, "Silencio entre pistas (s)", "Silence between tracks (s)", ge=0, le=10)
    fundido_cruzado: float = opt(0, "Fundido cruzado (s; sustituye al silencio)", "Crossfade (s; replaces the silence)", ge=0, le=10,
                                 advanced=True)
    normalizar: bool = opt(False, "Normalizar el volumen del resultado", "Normalize the result's volume", advanced=True)
    salida: Literal["mismo", "mp3", "wav"] = opt("mp3", "Formato de salida", "Output format",
                                                 labels={**OUTPUTS, "mismo": ("Mismo formato que el primero", "Same format as the first")})


class NormalizarOptions(BaseModel):
    objetivo: Literal["-16", "-14", "-23"] = opt(
        "-16", "Volumen objetivo", "Target loudness",
        labels={"-16": ("Web y pódcast (−16 LUFS)", "Web and podcasts (−16 LUFS)"),
                "-14": ("Música en plataformas (−14 LUFS)", "Music on streaming platforms (−14 LUFS)"),
                "-23": ("Radio y televisión, EBU R128 (−23 LUFS)", "Radio and TV, EBU R128 (−23 LUFS)")})
    salida: Literal["mismo", "mp3", "wav"] = opt("mismo", "Formato de salida", "Output format", labels=OUTPUTS, advanced=True)


class VelocidadOptions(BaseModel):
    velocidad: float = opt(1.5, "Velocidad (1 = igual; 2 = el doble de rápido)", "Speed (1 = same; 2 = twice as fast)", ge=0.25, le=4)
    conservar_tono: bool = opt(True, "Conservar el tono de voz", "Keep the pitch")
    salida: Literal["mismo", "mp3", "wav"] = opt("mismo", "Formato de salida", "Output format", labels=OUTPUTS, advanced=True)


AUDIO_INPUTS = ("mp3", "wav", "ogg", "opus", "m4a", "aac", "flac", "aiff", "wma", "amr")
VIDEO_INPUTS = ("mp4", "mov", "mkv", "webm", "avi")

# ——— Transcripción local (7.10): faster-whisper en CPU, sin IA externa ni consentimiento (6.3: 0 peticiones) ———

Language = Literal["auto", "es", "en", "ca", "eu", "gl", "fr", "de", "it", "pt", "nl", "pl", "ro", "ru", "uk", "ar", "zh", "ja", "ko",
                   "hi", "tr"]
LANGUAGES = {
    "auto": ("Detectar el idioma", "Detect the language"), "es": ("Español", "Spanish"), "en": ("Inglés", "English"),
    "ca": ("Catalán", "Catalan"), "eu": ("Euskera", "Basque"), "gl": ("Gallego", "Galician"), "fr": ("Francés", "French"),
    "de": ("Alemán", "German"), "it": ("Italiano", "Italian"), "pt": ("Portugués", "Portuguese"), "nl": ("Neerlandés", "Dutch"),
    "pl": ("Polaco", "Polish"), "ro": ("Rumano", "Romanian"), "ru": ("Ruso", "Russian"), "uk": ("Ucraniano", "Ukrainian"),
    "ar": ("Árabe", "Arabic"), "zh": ("Chino", "Chinese"), "ja": ("Japonés", "Japanese"), "ko": ("Coreano", "Korean"),
    "hi": ("Hindi", "Hindi"), "tr": ("Turco", "Turkish"),
}
PRECISION = {"normal": ("Normal (modelo small)", "Normal (small model)"),
             "alta": ("Alta, más lenta (modelo medium, si está instalado)", "High, slower (medium model, if installed)")}


class TranscribirOptions(BaseModel):
    idioma: Language = opt("auto", "Idioma del audio", "Audio language", labels=LANGUAGES)
    formato: Literal["txt", "docx", "srt", "todos"] = opt(
        "txt", "Formato", "Format",
        labels={"txt": ("Texto (TXT)", "Text (TXT)"), "docx": ("Word (DOCX)", "Word (DOCX)"), "srt": ("Subtítulos (SRT)", "Subtitles (SRT)"),
                "todos": ("Los tres: TXT, DOCX y SRT", "All three: TXT, DOCX and SRT")})
    marcas_de_tiempo: bool = opt(False, "Minuto de cada párrafo", "Time of each paragraph", show_if={"formato": ("txt", "docx", "todos")})
    precision: Literal["normal", "alta"] = opt("normal", "Precisión", "Accuracy", labels=PRECISION, advanced=True)


class SubtitulosOptions(BaseModel):
    idioma: Language = opt("auto", "Idioma del vídeo", "Video language", labels=LANGUAGES)
    formato: Literal["srt", "vtt", "ambos"] = opt("srt", "Formato", "Format",
                                                  labels={"srt": ("SRT", "SRT"), "vtt": ("WebVTT (VTT)", "WebVTT (VTT)"),
                                                          "ambos": ("SRT y VTT", "SRT and VTT")})
    caracteres_por_linea: int = opt(42, "Caracteres por línea (dos líneas como mucho)", "Characters per line (two lines at most)",
                                    ge=30, le=60, advanced=True)
    precision: Literal["normal", "alta"] = opt("normal", "Precisión", "Accuracy", labels=PRECISION, advanced=True)


def transcription(slug_es, slug_en, name_es, name_en, category, inputs, outputs, options, impl, summary_es, summary_en, related) -> ToolSpec:
    # Cola `av.heavy` (5.4): con `small` en int8 y 2 hilos va a unos 0,7 veces la duración (D-112), así que 4 h de
    # audio del plan Pro tardan unas 3 h; el límite de tiempo deja margen.
    return ToolSpec(slug_es=slug_es, slug_en=slug_en, name_es=name_es, name_en=name_en, category=category, where="server",
                    inputs=inputs, outputs=outputs, options=options, worker_group="av", cost_class="heavy", queue_kind="heavy",
                    impl=impl, launch=True, phase="F5", time_limit=4 * 3600, summary_es=summary_es, summary_en=summary_en,
                    related=related)


def audio(slug_es, slug_en, name_es, name_en, inputs, summary_es, summary_en, options=AudioOptions, outputs=("mp3", "zip"),
          impl="tools.av.audio:run", **kw) -> ToolSpec:
    return ToolSpec(slug_es=slug_es, slug_en=slug_en, name_es=name_es, name_en=name_en, category="audio", where="server",
                    inputs=inputs, outputs=outputs, options=options, worker_group="av", cost_class="light",
                    queue_kind="light", impl=impl, launch=True, phase="F5", time_limit=kw.pop("time_limit", 900),
                    summary_es=summary_es, summary_en=summary_en, related=kw.pop("related", ("ogg-a-mp3", "m4a-a-mp3")), **kw)


SPECS: list[ToolSpec] = [
    audio("ogg-a-mp3", "ogg-to-mp3", "OGG a MP3", "OGG to MP3", ("ogg", "opus", "oga"),
          "Convierte audios OGG, como las notas de voz de WhatsApp, a MP3.", "Convert OGG audio, like WhatsApp voice notes, to MP3."),
    audio("opus-a-mp3", "opus-to-mp3", "OPUS a MP3", "OPUS to MP3", ("opus", "ogg"),
          "Convierte notas de voz OPUS de WhatsApp a MP3.", "Convert WhatsApp OPUS voice notes to MP3."),
    audio("m4a-a-mp3", "m4a-to-mp3", "M4A a MP3", "M4A to MP3", ("m4a",),
          "Convierte audios M4A del móvil a MP3.", "Convert M4A phone recordings to MP3."),
    audio("mp4-a-mp3", "mp4-to-mp3", "MP4 a MP3", "MP4 to MP3", ("mp4", "m4a"),
          "Extrae el audio de un vídeo MP4 en MP3.", "Extract the audio of an MP4 video as MP3."),
    audio("aac-a-mp3", "aac-to-mp3", "AAC a MP3", "AAC to MP3", ("aac", "m4a"),
          "Convierte audios AAC a MP3.", "Convert AAC audio to MP3."),
    audio("flac-a-mp3", "flac-to-mp3", "FLAC a MP3", "FLAC to MP3", ("flac",),
          "Convierte música FLAC sin pérdida a MP3 para el móvil o el coche.", "Convert lossless FLAC music to MP3 for your phone or car."),
    audio("wav-a-mp3", "wav-to-mp3", "WAV a MP3", "WAV to MP3", ("wav",),
          "Convierte grabaciones WAV a MP3, que ocupan mucho menos.", "Convert WAV recordings to MP3, which take far less space."),
    audio("wma-a-mp3", "wma-to-mp3", "WMA a MP3", "WMA to MP3", ("wma",),
          "Convierte audios WMA de Windows a MP3.", "Convert Windows WMA audio to MP3."),
    audio("amr-a-mp3", "amr-to-mp3", "AMR a MP3", "AMR to MP3", ("amr",),
          "Convierte grabaciones de voz AMR de móviles antiguos a MP3.", "Convert AMR voice recordings from older phones to MP3."),
    audio("aiff-a-mp3", "aiff-to-mp3", "AIFF a MP3", "AIFF to MP3", ("aiff", "aif"),
          "Convierte audios AIFF de Mac a MP3.", "Convert Mac AIFF audio to MP3."),
    audio("ogg-a-wav", "ogg-to-wav", "OGG a WAV", "OGG to WAV", ("ogg", "opus", "oga"),
          "Convierte audios OGG y OPUS a WAV sin compresión para editarlos.", "Convert OGG and OPUS audio to uncompressed WAV for editing.",
          options=WavOptions, outputs=("wav", "zip"), related=("mp3-a-wav", "ogg-a-mp3")),
    audio("mp3-a-wav", "mp3-to-wav", "MP3 a WAV", "MP3 to WAV", ("mp3",),
          "Convierte MP3 a WAV PCM de 16 bits, a 44,1 o 48 kHz.", "Convert MP3 to 16-bit PCM WAV, at 44.1 or 48 kHz.",
          options=WavOptions, outputs=("wav", "zip"), related=("wav-a-mp3", "ogg-a-wav")),
    audio("cortar-audio", "cut-audio", "Cortar audio", "Cut audio", AUDIO_INPUTS,
          "Recorta un audio entre dos momentos, con fundido de entrada y de salida si quieres.",
          "Trim an audio file between two points, with fade in and fade out if you like.",
          options=CortarAudioOptions, outputs=(*AUDIO_INPUTS, "zip"), impl="tools.av.edicion:run_cut",
          related=("unir-audios", "normalizar-volumen")),
    audio("unir-audios", "merge-audio", "Unir audios", "Merge audio files", AUDIO_INPUTS,
          "Une varios audios en uno, en el orden que elijas, con silencio o fundido entre pistas.",
          "Join several audio files into one, in the order you choose, with silence or a crossfade between tracks.",
          options=UnirAudiosOptions, outputs=AUDIO_INPUTS, impl="tools.av.edicion:run_join", related=("cortar-audio",)),
    audio("normalizar-volumen", "normalize-audio", "Normalizar volumen", "Normalize audio volume", AUDIO_INPUTS,
          "Iguala el volumen de tus audios al nivel de la web, las plataformas de música o la radio (EBU R128).",
          "Even out the loudness of your audio to the level of the web, music platforms or radio (EBU R128).",
          options=NormalizarOptions, outputs=(*AUDIO_INPUTS, "zip"), impl="tools.av.edicion:run_normalize",
          related=("unir-audios", "cortar-audio")),
    audio("cambiar-velocidad-audio", "change-audio-speed", "Cambiar velocidad de audio", "Change audio speed", AUDIO_INPUTS,
          "Acelera o ralentiza un audio conservando el tono de voz.", "Speed up or slow down audio while keeping the pitch.",
          options=VelocidadOptions, outputs=(*AUDIO_INPUTS, "zip"), impl="tools.av.edicion:run_speed", related=("cortar-audio",)),
    transcription("transcribir-audio", "transcribe-audio", "Transcribir audio", "Transcribe audio", "audio", (*AUDIO_INPUTS, "mp4", "webm"),
                  ("txt", "docx", "srt", "zip"), TranscribirOptions, "tools.av.transcribe:run_transcribe",
                  "Pasa a texto entrevistas, clases, reuniones y notas de voz en TXT, Word o SRT. Se transcribe en nuestro servidor, sin IA externa.",
                  "Turn interviews, lectures, meetings and voice notes into text as TXT, Word or SRT. Transcribed on our server, with no external AI.",
                  ("video-a-subtitulos", "ogg-a-mp3")),
    transcription("video-a-subtitulos", "video-to-subtitles", "Vídeo a subtítulos", "Video to subtitles", "video", VIDEO_INPUTS,
                  ("srt", "vtt", "zip"), SubtitulosOptions, "tools.av.transcribe:run_subtitles",
                  "Crea los subtítulos SRT o VTT de un vídeo a partir de lo que se dice, con sus tiempos.",
                  "Create SRT or VTT subtitles for a video from what is said, with their timings.",
                  ("transcribir-audio", "mp4-a-mp3")),
]
