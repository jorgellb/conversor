"""Voz local (6.4): Kokoro-82M v1.0 en ONNX Runtime con los fonemas de espeak-ng, que se ejecuta como programa externo.

Nunca los paquetes `kokoro`, `kokoro-onnx`, `misaki` ni `phonemizer-fork` (11): `misaki[en]` y `phonemizer-fork` son
GPL y cargarían espeak-ng dentro del proceso de Python. Aquí el paso de texto a fonemas es propio:

1. espeak-ng (GPL-3.0, con `run_engine`: entorno vacío, tiempo y memoria limitados) escribe el IPA de cada trozo de
   texto con `--ipa --tie=^`; los trozos van separados por una línea en blanco, que espeak-ng siempre trata como fin de
   cláusula, así que cada trozo da una línea (si alguno da más, ese lote se repite trozo a trozo).
2. El IPA pasa al alfabeto de Kokoro: los diptongos y africadas que espeak-ng une con «^» son un solo símbolo («a^ɪ» →
   «I», «t^ʃ» → «ʧ»…), se quitan las marcas de cambio de idioma («(en)») y, en inglés de EE. UU., «ɚ» → «əɹ», «r» → «ɹ»
   y sin «ː»; lo que no está en el vocabulario del modelo (`tokenizer.json`) se descarta.
3. Los fonemas, con la puntuación de cada trozo, se agrupan en entradas de hasta `CHUNK_TOKENS` símbolos (el modelo
   admite 510) y ONNX Runtime genera la onda a 24 kHz con el vector de estilo de la voz para esa longitud.

El modelo, el vocabulario y las voces están en la imagen (`KOKORO_HOME`), descargados al construirla con su revisión y
su SHA-256 (infra/kokoro/fetch-model.sh); nunca se descargan al ejecutar.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.settings import Settings
from tools.av.lectura import Clause
from tools.base import SAFE_PATH, run_engine

SAMPLE_RATE = 24_000
MAX_TOKENS = 510
CHUNK_TOKENS = 400
BATCH_CLAUSES = 400  # trozos por llamada a espeak-ng
ESPEAK_VOICE = {"es": "es", "en": "en-us"}
# Prefijo de las voces de Kokoro por idioma: «e» español, «a» inglés de EE. UU. (las «b», británicas, no: los fonemas
# son los de en-us).
VOICE_PREFIX = {"es": "e", "en": "a"}
VOICE_NAME = re.compile(r"^[a-z]{2}_[a-z]{2,20}$")
TIES = (("a^ɪ", "I"), ("a^ʊ", "W"), ("e^ɪ", "A"), ("o^ʊ", "O"), ("ə^ʊ", "Q"), ("ɔ^ɪ", "Y"), ("t^ʃ", "ʧ"), ("d^ʒ", "ʤ"),
        ("t^s", "ʦ"), ("d^z", "ʣ"), ("t^ɕ", "ʨ"), ("d^ʑ", "ʥ"))
ENGLISH = (("ɚ", "əɹ"), ("r", "ɹ"), ("x", "k"), ("ç", "k"), ("ɬ", "l"), ("ʔ", "t"), ("ː", ""))
LANGUAGE_FLAG = re.compile(r"\([a-z]{2,3}(?:-[a-z0-9]+)?\)")


@dataclass
class Model:
    session: object
    vocab: dict[str, int]
    inputs: tuple[str, str, str]  # nombres de las entradas: fonemas, estilo y velocidad


_MODELS: dict[tuple, Model] = {}
_VOICES: dict[str, object] = {}
_LOCK = threading.Lock()


def home(settings: Settings) -> Path:
    return Path(settings.KOKORO_HOME)


def available(settings: Settings) -> bool:
    return (home(settings) / "model.onnx").is_file() and (home(settings) / "tokenizer.json").is_file()


def espeak() -> str:
    path = shutil.which("espeak-ng", path=SAFE_PATH)
    if not path:
        raise ToolError(ErrorCode.TOOL_DISABLED, "espeak-ng no está instalado")
    return path


def release() -> None:
    """Suelta el modelo de la memoria (lo pide la transcripción, que comparte los 3 GB de `workeravheavy`)."""
    with _LOCK:
        _MODELS.clear()
        _VOICES.clear()


def load_model(settings: Settings, threads: int) -> Model:
    """La sesión de ONNX Runtime se reutiliza entre trabajos del mismo proceso (cargarla tarda unos segundos). Antes se
    suelta el modelo de faster-whisper, si estaba cargado: los dos a la vez no caben con holgura en `workeravheavy`."""
    if settings.TTS_ENGINE != "kokoro":
        raise ToolError(ErrorCode.TOOL_DISABLED, f"Motor de voz no admitido: {settings.TTS_ENGINE}")
    base = home(settings)
    if not available(settings):
        raise ToolError(ErrorCode.TOOL_DISABLED, f"Falta el modelo de Kokoro en {base}")
    key = (str(base), max(1, threads))
    if key not in _MODELS:
        from tools.av import transcribe

        transcribe.release()  # fuera del cerrojo de aquí: nunca se esperan los dos a la vez
    with _LOCK:
        model = _MODELS.get(key)
        if model is None:
            import onnxruntime as ort

            vocab = json.loads((base / "tokenizer.json").read_text(encoding="utf-8"))["model"]["vocab"]
            options = ort.SessionOptions()
            options.intra_op_num_threads = max(1, threads)
            options.inter_op_num_threads = 1
            session = ort.InferenceSession(str(base / "model.onnx"), options, providers=["CPUExecutionProvider"])
            names = [i.name for i in session.get_inputs()]
            ids = "input_ids" if "input_ids" in names else "tokens"
            if ids not in names or "style" not in names or "speed" not in names:
                raise ToolError(ErrorCode.TOOL_DISABLED, f"El modelo de Kokoro no tiene las entradas esperadas: {names}")
            _MODELS.clear()
            model = _MODELS[key] = Model(session, vocab, (ids, "style", "speed"))
    return model


def voice_path(settings: Settings, name: str, lang: str) -> Path:
    """Archivo de la voz, solo si el nombre es de una voz de Kokoro de ese idioma y está en la imagen."""
    if not VOICE_NAME.match(name or "") or not name.startswith(VOICE_PREFIX[lang]):
        raise ToolError(ErrorCode.TOOL_DISABLED, f"tts_voice_{lang}")
    path = home(settings) / "voices" / f"{name}.bin"
    if not path.is_file():
        raise ToolError(ErrorCode.TOOL_DISABLED, f"tts_voice_{lang}")
    return path


def load_voice(path: Path):
    import numpy as np

    key = str(path)
    with _LOCK:
        voice = _VOICES.get(key)
        if voice is None:
            data = np.fromfile(path, dtype=np.float32)
            if data.size % 256 or data.size < 256 * MAX_TOKENS:
                raise ToolError(ErrorCode.TOOL_DISABLED, f"Voz de Kokoro no válida: {path.name}")
            voice = _VOICES[key] = data.reshape(-1, 1, 256)
    return voice


# ——— Fonemas ———

def to_kokoro(ipa: str, lang: str) -> str:
    """IPA de espeak-ng (con «^» entre los fonemas de dos letras) en los símbolos de Kokoro."""
    text = LANGUAGE_FLAG.sub("", ipa)
    for old, new in TIES:
        text = text.replace(old, new)
    text = text.replace("^", "")
    if lang == "en":
        for old, new in ENGLISH:
            text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def _espeak(texts: list[str], lang: str, work: Path, name: str) -> list[str]:
    src = work / f"{name}.txt"
    src.write_text("\n\n".join(texts) + "\n", encoding="utf-8")
    try:
        res = run_engine([espeak(), "-q", "-b", "1", "--ipa", "--tie=^", "-v", ESPEAK_VOICE[lang], "-f", str(src)], cwd=work,
                         timeout=max(60, len(texts) // 2), mem_mb=512)
    finally:
        src.unlink(missing_ok=True)
    return [ln.strip() for ln in res.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]


def phonemes(clauses: list[Clause], lang: str, work: Path) -> list[str]:
    """El IPA (ya en los símbolos de Kokoro) de cada trozo, en el mismo orden."""
    out: list[str] = []
    for start in range(0, len(clauses), BATCH_CLAUSES):
        texts = [c.text for c in clauses[start:start + BATCH_CLAUSES]]
        lines = _espeak(texts, lang, work, "fonemas")
        if len(lines) != len(texts):
            # Algún trozo ha salido en más de una línea: este lote, uno a uno (el resultado es el mismo, más lento).
            lines = [" ".join(_espeak([t], lang, work, "fonema")) for t in texts]
        out.extend(to_kokoro(line, lang) for line in lines)
    return out


def tokens(model: Model, text: str) -> list[int]:
    return [model.vocab[c] for c in text if c in model.vocab]


def chunks(model: Model, sentences: list[list[tuple[str, str]]]) -> list[list[int]]:
    """Entradas del modelo para un párrafo: frases enteras juntas mientras quepan en `CHUNK_TOKENS`; una frase más larga
    se parte entre trozos y un trozo más largo que el modelo, entre palabras."""
    pieces: list[str] = []
    for sentence in sentences:
        text = " ".join(f"{ps}{mark}" for ps, mark in sentence if ps)
        if len(tokens(model, text)) <= CHUNK_TOKENS:
            pieces.append(text)
            continue
        for ps, mark in sentence:
            if not ps:
                continue
            words = f"{ps}{mark}".split()
            part: list[str] = []
            for w in words:
                if part and len(tokens(model, " ".join([*part, w]))) > MAX_TOKENS - 10:
                    pieces.append(" ".join(part))
                    part = []
                part.append(w)
            if part:
                pieces.append(" ".join(part))
    out: list[list[int]] = []
    current = ""
    for piece in pieces:
        joined = f"{current} {piece}" if current else piece
        if current and len(tokens(model, joined)) > CHUNK_TOKENS:
            out.append(tokens(model, current))
            current = piece
        else:
            current = joined
    if current:
        out.append(tokens(model, current))
    return [t[:MAX_TOKENS] for t in out if t]


def synthesize(model: Model, voice, ids: list[int], speed: float):
    """La onda (float32, 24 kHz) de una entrada de hasta 510 símbolos."""
    import numpy as np

    style = voice[min(len(ids), voice.shape[0] - 1)]
    name_ids, name_style, name_speed = model.inputs
    feed = {name_ids: np.array([[0, *ids, 0]], dtype=np.int64), name_style: style.astype(np.float32),
            name_speed: np.array([speed], dtype=np.float32)}
    try:
        audio = model.session.run(None, feed)[0]
    except Exception as exc:  # noqa: BLE001 - un fallo de ONNX Runtime es un fallo del motor
        raise ToolError(ErrorCode.ENGINE_FAILED, f"Kokoro: {type(exc).__name__}") from exc
    return np.asarray(audio, dtype=np.float32).reshape(-1)
