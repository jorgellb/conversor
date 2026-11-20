"""midi-a-mp3 y midi-a-wav (7.13, F6-L, D-228): FluidSynth (LGPL, programa externo) con el banco FluidR3_GM (MIT) y
FFmpeg LGPL para el MP3.

La duración del MIDI se calcula antes de sintetizar (cabecera, pistas y mapa de tempo), con el límite de minutos de
audio del plan (9.3): un MIDI de pocos bytes con notas larguísimas o un tempo lentísimo daría horas de WAV.
"""
from __future__ import annotations

import shutil
import signal
import struct
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.av.audio import BITRATE, encode
from tools.base import ToolContext, derived_name, run_engine
from tools.pdf.common import with_batch_zip

MAX_MIDI_BYTES = 5 * 1024 * 1024
TAIL_SECONDS = 3  # la cola de la reverberación de la última nota
MIN_FILE_MB = 128


def _vlq(data: bytes, i: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if i >= len(data):
            raise ToolError(ErrorCode.CORRUPT_FILE, "midi")
        byte = data[i]
        i += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, i
    raise ToolError(ErrorCode.CORRUPT_FILE, "midi")


def duration(data: bytes, playable: bool = True) -> float:
    """Segundos de un MIDI con su mapa de tempo. Con `playable`, solo lo que FluidSynth sabe tocar (D-233): ni el formato
    2 ni la división SMPTE (los ignora y daría un archivo mudo) ni una división 0 (la toca unas cuatro veces más lenta
    de lo que dice el archivo, y el límite de minutos del plan no valdría)."""
    if len(data) > MAX_MIDI_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "MIDI de más de 5 MB")
    if data[:4] != b"MThd" or len(data) < 14:
        raise ToolError(ErrorCode.CORRUPT_FILE, "midi")
    try:
        return _duration(data, playable)
    except (struct.error, IndexError) as exc:  # pista cortada justo tras «MTrk»
        raise ToolError(ErrorCode.CORRUPT_FILE, "midi") from exc


def _duration(data: bytes, playable: bool) -> float:
    length, fmt, ntracks, division = struct.unpack(">IHHH", data[4:14])
    if division == 0:
        raise ToolError(ErrorCode.CORRUPT_FILE, "midi")
    if playable and (fmt == 2 or division & 0x8000):
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "midi_unsupported")
    pos = 8 + length
    events: list[tuple[int, int]] = []  # (tick, tempo) de los cambios de tempo
    end_tick = 0
    for _ in range(min(ntracks, 512)):
        if data[pos:pos + 4] != b"MTrk":
            break
        (size,) = struct.unpack(">I", data[pos + 4:pos + 8])
        track, pos = data[pos + 8:pos + 8 + size], pos + 8 + size
        i = tick = 0
        status = 0
        while i < len(track):
            delta, i = _vlq(track, i)
            tick += delta
            if i >= len(track):
                break
            byte = track[i]
            if byte == 0xFF:
                kind = track[i + 1] if i + 1 < len(track) else 0
                meta_len, j = _vlq(track, i + 2)
                if kind == 0x51 and meta_len == 3:
                    events.append((tick, int.from_bytes(track[j:j + 3], "big") or 500_000))
                i = j + meta_len
                if kind == 0x2F:
                    break
            elif byte in (0xF0, 0xF7):
                sysex_len, j = _vlq(track, i + 1)
                i = j + sysex_len
            else:
                if byte & 0x80:
                    status, i = byte, i + 1
                if not status:
                    raise ToolError(ErrorCode.CORRUPT_FILE, "midi")
                i += 1 if status & 0xF0 in (0xC0, 0xD0) else 2
                if i > len(track):  # evento cortado a mitad: el archivo está truncado
                    raise ToolError(ErrorCode.CORRUPT_FILE, "midi")
        end_tick = max(end_tick, tick)
    if division & 0x8000:  # SMPTE: fotogramas por segundo y subdivisiones por fotograma
        fps = 256 - (division >> 8)
        return end_tick / (fps * (division & 0xFF) or 1)
    ppq = division
    seconds, last_tick, tempo = 0.0, 0, 500_000
    for tick, new_tempo in sorted(events):
        if tick > end_tick:
            break
        seconds += (tick - last_tick) * tempo / ppq / 1_000_000
        last_tick, tempo = tick, new_tempo
    return seconds + (end_tick - last_tick) * tempo / ppq / 1_000_000


def synth(ctx: ToolContext, src: Path, rate: str, dst: Path, seconds: float) -> None:
    """WAV estéreo de 16 bits. Su tamaño queda limitado por lo que dura según el lector (más la cola y un margen), aunque
    FluidSynth y el lector no coincidan; y un WAV casi vacío de un MIDI con notas es un MIDI que FluidSynth no ha
    entendido, no un resultado (D-233)."""
    exe = Path(ctx.settings.FLUIDSYNTH_BIN)
    font = Path(ctx.settings.SOUNDFONT)
    if not exe.is_file() or not font.is_file():
        raise ToolError(ErrorCode.ENGINE_FAILED, "fluidsynth no está instalado")
    env = {"LD_LIBRARY_PATH": ctx.settings.ENGINES_LIBRARY_PATH} if ctx.settings.ENGINES_LIBRARY_PATH else None
    # Con menos de unos 64 MB, FluidSynth muere al arrancar (SIGXFSZ antes de crear el WAV): el tope nunca baja de 128 MB.
    budget_mb = max(MIN_FILE_MB, int((seconds * 1.25 + TAIL_SECONDS + 30) * int(rate) * 4 / 1024 / 1024) + 2)
    result = run_engine([str(exe), "-n", "-i", "-q", "-g", "0.7", "-r", rate, "-T", "wav", "-F", str(dst.name), str(font), str(src.name)],
                        cwd=ctx.work, timeout=int(max(120, seconds * 2 + 60)), mem_mb=1536, extra_env=env, max_file_mb=budget_mb,
                        ok_codes=(0, -signal.SIGXFSZ))
    if result.returncode == -signal.SIGXFSZ:  # el WAV llegó al tope: el MIDI suena más de lo que dice
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "El MIDI suena más de lo que dice")
    frames = (dst.stat().st_size - 44) // 4 if dst.exists() else 0
    if frames < int(rate) * min(seconds, 0.5) * 0.5 or b"error:" in result.stderr.lower():
        raise ToolError(ErrorCode.CORRUPT_FILE, "midi_unsupported")


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    wav = ctx.tool == "midi-a-wav"
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        seconds = duration(inp.path.read_bytes())
        if seconds + TAIL_SECONDS > ctx.plan.audio_minutes * 60:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{seconds:.0f} s")
        ctx.work.mkdir(parents=True, exist_ok=True)
        src = ctx.work / f"midi-{n}.mid"
        shutil.copyfile(inp.path, src)
        raw = ctx.work / f"midi-{n}.wav"
        synth(ctx, src, o.frecuencia if wav else "44100", raw, seconds)
        name = derived_name(inp.name, "", "wav" if wav else "mp3")
        dst = ctx.output(name)
        if wav:
            shutil.move(raw, dst)
        else:
            out = ctx.work / f"midi-{n}.mp3"
            encode(ctx, ["-f", "wav", "-i", str(raw)], [], ["-c:a", "libmp3lame", *BITRATE[o.calidad]], out, seconds + TAIL_SECONDS)
            shutil.move(out, dst)
        outputs.append({"path": str(dst), "name": name, "note": None})
    return with_batch_zip(ctx, outputs, f"{ctx.tool}.zip")
