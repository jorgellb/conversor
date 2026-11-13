"""cortar-audio, unir-audios, normalizar-volumen y cambiar-velocidad-audio (7.8) con FFmpeg.

La salida puede ser MP3, WAV o el mismo formato que la entrada (si FFmpeg tiene su codificador; si no, MP3 y aviso).
`loudnorm` va en dos pasadas: la primera mide y la segunda aplica una ganancia lineal, que no deforma el sonido (D-78).
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.av.audio import BASE, checked_input, ffmpeg
from tools.av.specs import parse_time
from tools.base import ToolContext, derived_name, run_engine
from tools.pdf.common import with_batch_zip

# Formato de entrada → (contenedor, codificación, extensión) para «mismo formato».
SAME: dict[str, tuple[str, list[str], str]] = {
    "mp3": ("mp3", ["-c:a", "libmp3lame", "-q:a", "2"], "mp3"),
    "ogg": ("ogg", ["-c:a", "libvorbis", "-q:a", "5"], "ogg"),
    "opus": ("ogg", ["-c:a", "libopus", "-b:a", "96k"], "opus"),
    "m4a": ("ipod", ["-c:a", "aac", "-b:a", "192k"], "m4a"),
    "mp4": ("ipod", ["-c:a", "aac", "-b:a", "192k"], "m4a"),
    "aac": ("adts", ["-c:a", "aac", "-b:a", "192k"], "aac"),
    "wav": ("wav", ["-c:a", "pcm_s16le"], "wav"),
    "flac": ("flac", ["-c:a", "flac"], "flac"),
    "aiff": ("aiff", ["-c:a", "pcm_s16be"], "aiff"),
    "wma": ("asf", ["-c:a", "wmav2", "-b:a", "192k"], "wma"),
}
MP3 = ("mp3", ["-c:a", "libmp3lame", "-q:a", "2"], "mp3")
WAV = ("wav", ["-c:a", "pcm_s16le", "-ar", "44100"], "wav")
NOTES = {
    "es": {"as_mp3": "No se puede guardar en {fmt}: va en MP3.", "loudness": "Volumen integrado: {before} → {after} LUFS."},
    "en": {"as_mp3": "It cannot be saved as {fmt}: it is in MP3.", "loudness": "Integrated loudness: {before} → {after} LUFS."},
}


def output_spec(ext: str, salida: str) -> tuple[tuple[str, list[str], str], bool]:
    """(contenedor, codificación, extensión) y si hubo que cambiar a MP3."""
    if salida == "mp3":
        return MP3, False
    if salida == "wav":
        return WAV, False
    return (SAME[ext], False) if ext in SAME else (MP3, True)


def _labels(ctx: ToolContext) -> dict[str, str]:
    return NOTES.get(ctx.locale, NOTES["es"])


def _encode(ctx: ToolContext, args: list[str], spec: tuple[str, list[str], str], dst: Path, seconds: float) -> None:
    muxer, codec, _ = spec
    run_engine([ffmpeg(), *BASE, *args, "-vn", "-sn", "-dn", "-map_metadata", "-1", *codec, "-f", muxer,
                "-threads", str(max(1, ctx.threads)), "-y", str(dst)], cwd=ctx.work, timeout=int(max(120, seconds * 3 + 60)), mem_mb=1024)


def _deliver(ctx: ToolContext, tmp: Path, name: str, notes: list[str]) -> dict:
    dst = ctx.output(name)
    shutil.move(tmp, dst)
    return {"path": str(dst), "name": name, "note": " ".join(notes) or None}


def run_cut(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        demuxer, duration, _ = checked_input(ctx, inp)
        start = parse_time(o.inicio) or 0.0
        end = parse_time(o.fin) if o.fin.strip() else duration
        end = min(end, duration)
        if start >= end:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "El inicio tiene que ir antes del final")
        length = end - start
        filters = [f"atrim=start={start:.3f}:end={end:.3f}", "asetpts=PTS-STARTPTS"]
        if o.fundido_entrada > 0:
            filters.append(f"afade=t=in:st=0:d={min(o.fundido_entrada, length / 2):.3f}")
        if o.fundido_salida > 0:
            fade = min(o.fundido_salida, length / 2)
            filters.append(f"afade=t=out:st={length - fade:.3f}:d={fade:.3f}")
        spec, as_mp3 = output_spec(inp.ext, o.salida)
        tmp = ctx.work / f"corte-{n}.{spec[2]}"
        _encode(ctx, ["-f", demuxer, "-i", str(inp.path), "-map", "0:a:0", "-af", ",".join(filters)], spec, tmp, length)
        notes = [_labels(ctx)["as_mp3"].format(fmt=inp.ext.upper())] if as_mp3 else []
        outputs.append(_deliver(ctx, tmp, derived_name(inp.name, "-recortado", spec[2]), notes))
    return with_batch_zip(ctx, outputs, "audios-recortados.zip")


def run_join(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    if len(ctx.inputs) < 2:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "Hacen falta al menos dos audios")
    args: list[str] = []
    total = 0.0
    for inp in ctx.inputs:
        demuxer, duration, _ = checked_input(ctx, inp)
        total += duration
        args += ["-f", demuxer, "-i", str(inp.path)]
    if total > ctx.plan.audio_minutes * 60:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{total:.0f} s")
    n = len(ctx.inputs)
    graph = [f"[{i}:a:0]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]" for i in range(n)]
    if o.fundido_cruzado > 0:
        last = "a0"
        for i in range(1, n):
            graph.append(f"[{last}][a{i}]acrossfade=d={o.fundido_cruzado:.3f}[x{i}]")
            last = f"x{i}"
        final = last
    else:
        labels = []
        for i in range(n):
            labels.append(f"[a{i}]")
            if o.pausa > 0 and i < n - 1:
                graph.append(f"anullsrc=r=44100:cl=stereo,atrim=duration={o.pausa:.3f}[s{i}]")
                labels.append(f"[s{i}]")
        graph.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[j]")
        final = "j"
    if o.normalizar:
        graph.append(f"[{final}]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100[out]")
        final = "out"
    spec, as_mp3 = output_spec(ctx.inputs[0].ext, o.salida)
    tmp = ctx.work / f"unido.{spec[2]}"
    _encode(ctx, [*args, "-filter_complex", ";".join(graph), "-map", f"[{final}]"], spec, tmp, total)
    notes = [_labels(ctx)["as_mp3"].format(fmt=ctx.inputs[0].ext.upper())] if as_mp3 else []
    return [_deliver(ctx, tmp, f"{Path(ctx.inputs[0].name).stem or 'audio'}-unido.{spec[2]}", notes)]


def _measure(ctx: ToolContext, demuxer: str, path: Path, target: str, seconds: float) -> dict:
    """Primera pasada de loudnorm: lo que mide del audio (JSON en la salida de errores)."""
    res = run_engine([ffmpeg(), "-nostdin", "-hide_banner", "-protocol_whitelist", "file,pipe", "-f", demuxer, "-i", str(path),
                      "-map", "0:a:0", "-af", f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                     cwd=ctx.work, timeout=int(max(120, seconds * 2 + 60)), mem_mb=1024)
    text = (res.stderr or b"").decode("utf-8", "replace")
    found = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", text)
    if not found:
        raise ToolError(ErrorCode.ENGINE_FAILED, "loudnorm sin medida")
    return json.loads(found[-1])


def run_normalize(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        demuxer, duration, stream = checked_input(ctx, inp)
        m = _measure(ctx, demuxer, inp.path, o.objetivo, duration)
        rate = str(stream.get("sample_rate") or "48000")
        loudnorm = (f"loudnorm=I={o.objetivo}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
                    f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
        spec, as_mp3 = output_spec(inp.ext, o.salida)
        tmp = ctx.work / f"normalizado-{n}.{spec[2]}"
        _encode(ctx, ["-f", demuxer, "-i", str(inp.path), "-map", "0:a:0", "-af", f"{loudnorm},aresample={rate}"], spec, tmp, duration)
        notes = [_labels(ctx)["loudness"].format(before=m["input_i"], after=o.objetivo)]
        if as_mp3:
            notes.append(_labels(ctx)["as_mp3"].format(fmt=inp.ext.upper()))
        outputs.append(_deliver(ctx, tmp, derived_name(inp.name, "-normalizado", spec[2]), notes))
    return with_batch_zip(ctx, outputs, "audios-normalizados.zip")


def tempo_chain(factor: float) -> list[str]:
    """atempo admite 0,5–2,0 por filtro en FFmpeg antiguos: se encadena para ir más allá conservando el tono."""
    chain = []
    while factor > 2.0:
        chain.append("atempo=2.0")
        factor /= 2.0
    while factor < 0.5:
        chain.append("atempo=0.5")
        factor /= 0.5
    chain.append(f"atempo={factor:.6f}")
    return chain


def run_speed(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        demuxer, duration, stream = checked_input(ctx, inp)
        rate = int(stream.get("sample_rate") or 44100)
        filters = tempo_chain(o.velocidad) if o.conservar_tono else [f"asetrate={round(rate * o.velocidad)}", f"aresample={rate}"]
        spec, as_mp3 = output_spec(inp.ext, o.salida)
        tmp = ctx.work / f"velocidad-{n}.{spec[2]}"
        _encode(ctx, ["-f", demuxer, "-i", str(inp.path), "-map", "0:a:0", "-af", ",".join(filters)], spec, tmp, duration / o.velocidad)
        notes = [_labels(ctx)["as_mp3"].format(fmt=inp.ext.upper())] if as_mp3 else []
        outputs.append(_deliver(ctx, tmp, derived_name(inp.name, f"-x{o.velocidad:g}".replace(".", ","), spec[2]), notes))
    return with_batch_zip(ctx, outputs, "audios-velocidad.zip")
