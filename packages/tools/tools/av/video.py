"""mp4-a-webm, webm-a-mp4, mov-a-mp4, mkv-a-mp4, avi-a-mp4, video-a-gif y gif-a-mp4 (7.9, F5-V1, D-241) con FFmpeg LGPL.

- Solo con vídeo en el plan (9.3: Pro, hasta 1 h y 1 GB) y dentro de sus minutos.
- Si los códecs de entrada caben en el contenedor de salida (H.264, HEVC o AV1 con AAC, MP3, Opus o AC-3 en MP4; VP8,
  VP9 o AV1 con Opus o Vorbis en WebM), se remultiplexa con `-c copy`: tarda segundos y no se codifica nada.
- Si no, se recodifica: a WebM con VP9 y Opus; a MP4 con H.264 solo si `VIDEO_H264_ENCODING_ENABLED` está encendido (y el
  FFmpeg tiene codificador de H.264: la compilación LGPL no trae x264) y, si no, con AV1 (SVT-AV1) y AAC, y se avisa.
- Recodificar un vídeo HEVC (iPhone) es decodificar HEVC: necesita `HEVC_DECODE_ENABLED` (11); remultiplexarlo, no.
- Se quitan los metadatos globales (fecha, GPS, aplicación) y se conservan el giro y el resto de la pista.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.flags import thematic_enabled
from tools.av.audio import BASE, ffmpeg
from tools.base import InputFile, ToolContext, derived_name, run_engine
from tools.pdf.common import with_batch_zip

DEMUXER = {"mp4": "mov", "mov": "mov", "m4v": "mov", "mkv": "matroska", "webm": "matroska", "avi": "avi", "gif": "gif"}
COPY_OK = {
    "mp4": ({"h264", "hevc", "av1", "mpeg4"}, {"aac", "mp3", "opus", "ac3", "eac3", "alac", "flac"}),
    "webm": ({"vp8", "vp9", "av1"}, {"opus", "vorbis"}),
}
TARGET = {"mp4-a-webm": "webm", "webm-a-mp4": "mp4", "mov-a-mp4": "mp4", "mkv-a-mp4": "mp4", "avi-a-mp4": "mp4"}
MAX_GIF_SECONDS = 30
MAX_GIF_BYTES = 80 * 1024 * 1024

TEXTS = {
    "es": {"copy": "Remultiplexado sin recodificar: la imagen y el sonido son los mismos del original.",
           "av1": "Recodificado a AV1: el MP4 con H.264 no está disponible. Se reproduce en los navegadores, en Windows 10 y 11, en "
                  "Android y en los Mac y iPhone recientes.",
           "h264": "Recodificado a H.264 y AAC.", "vp9": "Recodificado a VP9 y Opus.",
           "audio": "La imagen va sin recodificar; solo se ha recodificado el sonido, que no cabe en el nuevo formato.",
           "noaudio": "El vídeo no tiene sonido.", "cut": "El GIF tiene los {s} primeros segundos desde el inicio elegido."},
    "en": {"copy": "Remuxed without re-encoding: picture and sound are the same as the original.",
           "av1": "Re-encoded to AV1: MP4 with H.264 is not available. It plays in browsers, on Windows 10 and 11, Android and recent "
                  "Macs and iPhones.",
           "h264": "Re-encoded to H.264 and AAC.", "vp9": "Re-encoded to VP9 and Opus.",
           "audio": "The picture is not re-encoded; only the sound was, because it does not fit the new format.",
           "noaudio": "The video has no sound.", "cut": "The GIF has the first {s} seconds from the chosen start."},
}


def _t(ctx: ToolContext) -> dict:
    return TEXTS.get(ctx.locale, TEXTS["es"])


def probe(path: Path, demuxer: str, cwd: Path) -> dict:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    res = run_engine([ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe", "-f", demuxer, "-show_entries",
                      "format=duration:stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames:stream_side_data=rotation", "-of", "json", str(path)],
                     cwd=cwd, timeout=120, mem_mb=512)
    try:
        return json.loads(res.stdout or b"{}")
    except json.JSONDecodeError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE) from exc


@lru_cache(maxsize=1)
def encoders() -> frozenset[str]:
    try:
        out = subprocess.run([ffmpeg(), "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    return frozenset(line.split()[1] for line in out.splitlines() if line.startswith(" V") or line.startswith(" A"))


# SVT-AV1 no acepta lados de menos de 64 px: se rellena con negro hasta 64 (un GIF de 48 × 48, por ejemplo).
AV1_PAD = "pad=w='max(iw,64)':h='max(ih,64)':x='(ow-iw)/2':y='(oh-ih)/2'"
EVEN = "scale=trunc(iw/2)*2:trunc(ih/2)*2"


def av1(crf: int) -> list[str]:
    """SVT-AV1 con el paralelismo acotado: sin `lp` dimensiona sus búferes por los núcleos de la máquina y a 1080p no cabe
    en 1400 MB de datos (D-242; `-threads` no lo limita)."""
    return ["-c:v", "libsvtav1", "-crf", str(crf), "-preset", "8", "-svtav1-params", "lp=2"]


def h264_encoder() -> str | None:
    """El codificador de H.264, solo con VIDEO_H264_ENCODING_ENABLED y si el FFmpeg lo trae (11)."""
    if not thematic_enabled("VIDEO_H264_ENCODING_ENABLED"):
        return None
    return next((e for e in ("libx264", "libopenh264") if e in encoders()), None)


def checked(ctx: ToolContext, inp: InputFile) -> tuple[str, dict, float, dict | None, dict | None]:
    if not ctx.plan.video:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "video_plan")
    ext = (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()
    demuxer = DEMUXER.get(ext)
    if not demuxer:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT)
    info = probe(inp.path, demuxer, ctx.work)
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "video_sin_imagen")
    duration = float(info.get("format", {}).get("duration") or 0)
    if duration > ctx.plan.video_minutes * 60:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{duration:.0f} s de vídeo")
    return demuxer, info, duration, video, audio


def _encode_args(target: str, video: dict, audio: dict | None) -> tuple[list[str], str]:
    """Argumentos de códec y la nota: copia si cabe en el contenedor; si no, VP9/Opus, H.264/AAC o AV1/AAC."""
    vcodecs, acodecs = COPY_OK[target]
    copy_video = video.get("codec_name") in vcodecs
    copy_audio = audio is None or audio.get("codec_name") in acodecs
    if copy_video and copy_audio:
        args = ["-c", "copy"] + (["-tag:v", "hvc1"] if target == "mp4" and video.get("codec_name") == "hevc" else [])
        return args, "copy"
    if video.get("codec_name") == "hevc" and not copy_video and not thematic_enabled("HEVC_DECODE_ENABLED"):
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "video_hevc")
    even = ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-pix_fmt", "yuv420p"]
    if copy_video:
        vargs, note = ["-c:v", "copy"], "copy"
    elif target == "webm":
        vargs, note = ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", *even], "vp9"
    elif (enc := h264_encoder()) is not None:
        vargs, note = ["-c:v", enc, *(["-crf", "23", "-preset", "medium"] if enc == "libx264" else ["-b:v", "4M"]), *even], "h264"
    else:
        vargs, note = [*av1(32), "-vf", f"{EVEN},{AV1_PAD}", "-pix_fmt", "yuv420p"], "av1"
    if audio is None:
        aargs = []
    elif copy_audio:
        aargs = ["-c:a", "copy"]
    else:
        aargs = ["-c:a", "libopus", "-b:a", "128k"] if target == "webm" else ["-c:a", "aac", "-b:a", "160k"]
    # La imagen se copia y solo se recodifica el sonido: «audio».
    return vargs + aargs, ("audio" if copy_video else note)


def run(ctx: ToolContext) -> list[dict]:
    t = _t(ctx)
    target = TARGET[ctx.tool]
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        demuxer, _info, duration, video, audio = checked(ctx, inp)
        codec, note = _encode_args(target, video, audio)
        tmp = ctx.work / f"video-{n}.{target}"
        args = [ffmpeg(), *BASE, "-f", demuxer, "-i", str(inp.path), "-map", "0:v:0", *(["-map", "0:a:0"] if audio else []),
                "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1", *codec,
                *(["-movflags", "+faststart"] if target == "mp4" else []), "-threads", str(max(1, ctx.threads)), "-y", tmp.name]
        # Memoria de datos y no virtual (SVT-AV1 y libvpx reservan mucho espacio de direcciones, D-237).
        run_engine(args, cwd=ctx.work, timeout=int(max(300, duration * (2 if note == "copy" else 8) + 120)), mem_mb=1400, limit_data=True,
                   max_file_mb=4096)
        if not tmp.exists() or not tmp.stat().st_size:
            raise ToolError(ErrorCode.ENGINE_FAILED, "FFmpeg no generó el vídeo")
        name = derived_name(inp.name, "", target)
        dst = ctx.output(name)
        shutil.move(tmp, dst)
        notes = [t[note]] + ([t["noaudio"]] if audio is None else [])
        outputs.append({"path": str(dst), "name": name, "note": " ".join(notes)})
    return with_batch_zip(ctx, outputs, f"videos-{target}.zip")


def run_gif(ctx: ToolContext) -> list[dict]:
    """video-a-gif: paleta propia en dos pasadas (palettegen y paletteuse), con los fotogramas por segundo y el ancho."""
    o = ctx.options
    t = _t(ctx)
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        demuxer, _info, duration, video, _audio = checked(ctx, inp)
        if video.get("codec_name") == "hevc" and not thematic_enabled("HEVC_DECODE_ENABLED"):
            raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "video_hevc")
        start = max(0.0, min(o.inicio, max(0.0, duration - 0.1)))
        length = min(o.duracion, MAX_GIF_SECONDS, max(0.1, duration - start))
        dither = "bayer:bayer_scale=3" if o.calidad == "ligera" else "sierra2_4a"
        graph = (f"fps={o.fps},scale={o.ancho}:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors={128 if o.calidad == 'ligera' else 256}"
                 f":stats_mode=diff[p];[b][p]paletteuse=dither={dither}:diff_mode=rectangle")
        tmp = ctx.work / f"video-{n}.gif"
        args = [ffmpeg(), *BASE, "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-f", demuxer, "-i", str(inp.path),
                "-filter_complex", graph, "-loop", "0" if o.bucle else "-1", "-map_metadata", "-1", "-y", tmp.name]
        run_engine(args, cwd=ctx.work, timeout=600, mem_mb=1400, limit_data=True, max_file_mb=MAX_GIF_BYTES // (1024 * 1024))
        if not tmp.exists() or not tmp.stat().st_size:
            raise ToolError(ErrorCode.ENGINE_FAILED, "FFmpeg no generó el GIF")
        name = derived_name(inp.name, "", "gif")
        dst = ctx.output(name)
        shutil.move(tmp, dst)
        note = t["cut"].format(s=f"{length:g}") if length < o.duracion or duration - start > length + 0.05 else None
        outputs.append({"path": str(dst), "name": name, "note": note})
    return with_batch_zip(ctx, outputs, "gifs.zip")


def run_gif_mp4(ctx: ToolContext) -> list[dict]:
    """gif-a-mp4: H.264 con su interruptor o AV1, en yuv420p, con lados pares y con +faststart."""
    t = _t(ctx)
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        _demuxer, _info, duration, _video, _audio = checked(ctx, inp)
        enc = h264_encoder()
        codec = (["-c:v", enc, *(["-crf", "20"] if enc == "libx264" else ["-b:v", "3M"])] if enc
                 else av1(30))
        tmp = ctx.work / f"gif-{n}.mp4"
        args = [ffmpeg(), *BASE, "-f", "gif", "-i", str(inp.path), "-vf", f"{EVEN},{'' if enc else AV1_PAD + ','}format=yuv420p",
                "-an", "-map_metadata", "-1", *codec, "-movflags", "+faststart", "-y", tmp.name]
        run_engine(args, cwd=ctx.work, timeout=int(max(300, duration * 8 + 120)), mem_mb=1400, limit_data=True, max_file_mb=2048)
        if not tmp.exists() or not tmp.stat().st_size:
            raise ToolError(ErrorCode.ENGINE_FAILED, "FFmpeg no generó el vídeo")
        name = derived_name(inp.name, "", "mp4")
        dst = ctx.output(name)
        shutil.move(tmp, dst)
        outputs.append({"path": str(dst), "name": name, "note": t["h264" if enc else "av1"]})
    return with_batch_zip(ctx, outputs, "gifs-mp4.zip")
