"""Conversión de audio con FFmpeg (7.8): a MP3 (128, 192 o 320 kbps o VBR) y a WAV (PCM de 16 bits a 44,1 o 48 kHz).

Seguridad (12.3): `-nostdin`, `-protocol_whitelist file,pipe`, demultiplexor fijado por el tipo real
(nunca listas HLS, concat ni playlists), `ffprobe` previo y límites de duración y de tiempo.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import InputFile, ToolContext, derived_name, run_engine
from tools.pdf.common import with_batch_zip

DEMUXER = {"ogg": "ogg", "opus": "ogg", "m4a": "mov", "mp4": "mov", "mov": "mov", "mp3": "mp3", "wav": "wav",
           "flac": "flac", "aiff": "aiff", "amr": "amr", "wma": "asf", "webm": "matroska", "mkv": "matroska", "aac": "aac", "avi": "avi"}
BITRATE = {"128": ["-b:a", "128k"], "192": ["-b:a", "192k"], "320": ["-b:a", "320k"], "vbr": ["-q:a", "2"]}
WAV_TOOLS = {"ogg-a-wav", "mp3-a-wav"}
BASE = ["-nostdin", "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file,pipe"]


def ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def probe(path, demuxer: str, cwd) -> dict:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    res = run_engine([ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe", "-f", demuxer, "-show_entries",
                      "format=duration:stream=codec_type,codec_name,channels,sample_rate", "-of", "json", str(path)],
                     cwd=cwd, timeout=60, mem_mb=512)
    try:
        return json.loads(res.stdout or b"{}")
    except json.JSONDecodeError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE) from exc


def checked_input(ctx: ToolContext, inp: InputFile) -> tuple[str, float, dict]:
    """Demultiplexor por el tipo real, pista de audio presente y duración dentro del plan."""
    demuxer = DEMUXER.get(inp.ext)
    if not demuxer:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT)
    info = probe(inp.path, demuxer, ctx.work)
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not streams:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "Sin pista de audio")
    duration = float(info.get("format", {}).get("duration") or 0)
    if duration > ctx.plan.audio_minutes * 60:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{duration:.0f} s")
    return demuxer, duration, streams[0]


def channel_args(canales: str) -> list[str]:
    return ["-ac", "1"] if canales == "mono" else ["-ac", "2"] if canales == "estereo" else []


def encode(ctx: ToolContext, inputs: list[str], filters: list[str], codec: list[str], dst: Path, duration: float) -> None:
    args = [ffmpeg(), *BASE, *inputs, "-map", "0:a:0", "-vn", "-sn", "-dn", "-map_metadata", "-1"]
    if filters:
        args += ["-af", ",".join(filters)]
    args += [*codec, "-threads", str(max(1, ctx.threads)), "-y", str(dst)]
    run_engine(args, cwd=ctx.work, timeout=int(max(120, duration * 3 + 60)), mem_mb=1024)


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    wav = ctx.tool in WAV_TOOLS
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        demuxer, duration, _ = checked_input(ctx, inp)
        ext = "wav" if wav else "mp3"
        name = derived_name(inp.name, "", ext)
        tmp = ctx.work / f"audio-{n}.{ext}"
        codec = (["-c:a", "pcm_s16le", "-ar", o.frecuencia] if wav else ["-c:a", "libmp3lame", *BITRATE[o.calidad]]) + channel_args(o.canales)
        filters = ["loudnorm=I=-16:TP=-1.5:LRA=11"] if o.normalizar else []
        encode(ctx, ["-f", demuxer, "-i", str(inp.path)], filters, codec, tmp, duration)
        dst = ctx.output(name)
        shutil.move(tmp, dst)
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, f"audios-{'wav' if wav else 'mp3'}.zip")
