"""comprimir-video, recortar-video, rotar-video y quitar-audio-video (7.9, F5-V2, D-242) con FFmpeg LGPL; solo Pro.

Sin recodificar cuando la operación lo permite:
- quitar-audio-video copia la imagen siempre (`-an -c:v copy`).
- recortar-video en modo rápido corta con `-c copy` desde el fotograma clave anterior al inicio (el vídeo puede empezar
  un poco antes); en modo preciso recodifica y corta en el fotograma exacto.
- rotar-video en MP4 y MOV solo cambia la matriz de presentación (`-display_rotation`, `-display_hflip`/`vflip`) sumada
  al giro que ya tuviera; en MKV, WebM y AVI, o en modo «recodificar» para reproductores que ignoran la matriz, gira los
  píxeles con `transpose`.
- comprimir-video siempre recodifica (VP9 en WebM; H.264 con su interruptor o AV1 en el resto, que sale en MP4) con tres
  niveles de calidad constante y una resolución máxima; si el resultado no pesa menos que el original, se devuelve el
  original y se dice.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.flags import thematic_enabled
from tools.av.audio import BASE, ffmpeg
from tools.av.specs import parse_time
from tools.av.video import AV1_PAD, EVEN, FFMPEG_STACK_MB, av1 as av1_args, cap, checked, ensure_time, h264_encoder, memory_mb, threads
from tools.base import InputFile, ToolContext, derived_name, run_engine
from tools.pdf.common import with_batch_zip

SAME = {"mp4": "mp4", "m4v": "mp4", "mov": "mov", "mkv": "mkv", "webm": "webm", "avi": "avi"}
DISPLAY_MATRIX = {"mp4", "mov"}  # contenedores donde FFmpeg escribe la matriz de presentación al copiar
CRF = {  # calidad constante por nivel: (VP9, AV1 de SVT, x264) y kbps del sonido (Opus, AAC)
    "ligera": (33, 34, 24, 96, 128),
    "media": (38, 40, 28, 64, 96),
    "fuerte": (44, 47, 32, 48, 64),
}

TEXTS = {
    "es": {"copy": "Sin recodificar: la imagen y el sonido son los del original.",
           "fast_cut": "Corte rápido sin recodificar: el vídeo empieza en el fotograma clave anterior al inicio elegido, "
                       "hasta unos segundos antes.",
           "precise": "Corte exacto: se ha recodificado ({codec}).",
           "matrix": "Giro sin recodificar: se ha cambiado la orientación guardada en el vídeo, que respetan los móviles, "
                     "los navegadores y los reproductores actuales.",
           "pixels": "Giro recodificado ({codec}): la imagen está girada de verdad y se ve bien en cualquier reproductor.",
           "compressed": "Comprimido con {codec}: {before} → {after} ({pct} % menos).",
           "not_smaller": "Este vídeo ya estaba bien comprimido: el resultado no pesaba menos, así que se devuelve el original.",
           "no_audio": "El vídeo ya no tenía sonido.",
           "mp4": "Sale en MP4 porque el formato original no admite el códec del resultado."},
    "en": {"copy": "Not re-encoded: picture and sound are the original's.",
           "fast_cut": "Fast cut without re-encoding: the video starts at the keyframe before the chosen start, up to a few "
                       "seconds earlier.",
           "precise": "Exact cut: re-encoded ({codec}).",
           "matrix": "Rotation without re-encoding: the orientation stored in the video was changed, which phones, browsers and "
                     "current players respect.",
           "pixels": "Rotation re-encoded ({codec}): the picture is truly rotated and looks right in any player.",
           "compressed": "Compressed with {codec}: {before} → {after} ({pct}% smaller).",
           "not_smaller": "This video was already well compressed: the result was not smaller, so the original is returned.",
           "no_audio": "The video already had no sound.",
           "mp4": "It comes out as MP4 because the original format does not support the result's codec."},
}
CODEC_NAME = {"vp9": "VP9", "h264": "H.264", "av1": "AV1"}


def _t(ctx: ToolContext) -> dict:
    return TEXTS.get(ctx.locale, TEXTS["es"])


def _ext(inp: InputFile) -> str:
    return (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()


def _size(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{max(1, n // 1024)} KB"


def encoder(ext: str, level: str = "ligera", video: dict | None = None) -> tuple[str, list[str], list[str], str]:
    """(extensión de salida, argumentos de imagen, de sonido, códec) al recodificar: VP9 y Opus en WebM; H.264 (con su
    interruptor) o AV1 con AAC en MP4 para el resto (MOV, MKV y AVI salen en MP4)."""
    vp9, av1, x264, opus_k, aac_k = CRF[level]
    if ext == "webm":
        return "webm", ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(vp9), "-row-mt", "1", "-deadline", "good", "-cpu-used", "4"], \
            ["-c:a", "libopus", "-b:a", f"{opus_k}k"], "vp9"
    if (enc := h264_encoder()) is not None:
        rate = ["-crf", str(x264), "-preset", "medium"] if enc == "libx264" else ["-b:v", {"ligera": "3M", "media": "1800k", "fuerte": "900k"}[level]]
        return "mp4", ["-c:v", enc, *rate], ["-c:a", "aac", "-b:a", f"{aac_k}k"], "h264"
    return "mp4", av1_args(av1, video), ["-c:a", "aac", "-b:a", f"{aac_k}k"], "av1"


def _needs_hevc(video: dict) -> None:
    if video.get("codec_name") == "hevc" and not thematic_enabled("HEVC_DECODE_ENABLED"):
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "video_hevc")


def _run(ctx: ToolContext, args: list[str], duration: float, recode: bool, video: dict) -> None:
    ensure_time(ctx, duration, video, recode)
    # Memoria de datos y no virtual (SVT-AV1 y libvpx reservan mucho espacio de direcciones, D-237), más por encima de
    # 1080p (D-245).
    run_engine(args, cwd=ctx.work, timeout=int(max(300, duration * (8 if recode else 2) + 120)), mem_mb=memory_mb(video),
               limit_data=True, stack_mb=FFMPEG_STACK_MB, max_file_mb=4096)


def _finish(ctx: ToolContext, tmp: Path, inp: InputFile, suffix: str, ext: str) -> tuple[Path, str]:
    if not tmp.exists() or not tmp.stat().st_size:
        raise ToolError(ErrorCode.ENGINE_FAILED, "FFmpeg no generó el vídeo")
    name = derived_name(inp.name, suffix, ext)
    dst = ctx.output(name)
    shutil.move(tmp, dst)
    return dst, name


def _common(target: str) -> list[str]:
    return ["-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1", *(["-movflags", "+faststart"] if target in {"mp4", "mov"} else [])]


def _streams(audio: dict | None, keep_audio: bool = True) -> list[str]:
    return ["-map", "0:V:0", *(["-map", "0:a:0"] if audio and keep_audio else [])]  # V: sin carátulas (D-245)


def _even_scale(extra: str = "", codec: str = "") -> list[str]:
    chain = ",".join(filter(None, [extra, EVEN, AV1_PAD if codec == "av1" else ""]))
    return ["-vf", chain, "-pix_fmt", "yuv420p"]


def _batch(ctx: ToolContext, each, zip_name: str) -> list[dict]:
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        outputs.append(each(n, inp))
    return with_batch_zip(ctx, outputs, zip_name)


# ——— quitar-audio-video ———

def run_mute(ctx: ToolContext) -> list[dict]:
    t = _t(ctx)

    def each(n: int, inp: InputFile) -> dict:
        demuxer, _info, duration, video, audio = checked(ctx, inp)
        ext = SAME[_ext(inp)]
        tmp = ctx.work / f"mudo-{n}.{ext}"
        _run(ctx, [ffmpeg(), *BASE, *threads(ctx), "-f", demuxer, "-i", str(inp.path), "-map", "0:V:0", "-an", "-c:v", "copy",
                   *cap(ctx), *_common(ext), "-y", tmp.name], duration, False, video)
        dst, name = _finish(ctx, tmp, inp, "-sin-audio" if ctx.locale != "en" else "-no-audio", ext)
        return {"path": str(dst), "name": name, "note": t["copy"] if audio else t["no_audio"]}

    return _batch(ctx, each, "videos-sin-audio.zip")


# ——— recortar-video ———

def run_trim(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    t = _t(ctx)
    start = parse_time(o.inicio) or 0.0
    end = parse_time(o.fin)

    def each(n: int, inp: InputFile) -> dict:
        demuxer, _info, duration, video, audio = checked(ctx, inp)
        stop = min(end, duration) if end is not None else duration
        if start >= duration or stop - start < 0.1:
            raise ToolError(ErrorCode.INVALID_OPTIONS, "video_cut_range")
        length = stop - start
        ext = SAME[_ext(inp)]
        if o.modo == "rapido":
            tmp = ctx.work / f"corte-{n}.{ext}"
            args = [ffmpeg(), *BASE, *threads(ctx), "-ss", f"{start:.3f}", "-f", demuxer, "-i", str(inp.path), "-t", f"{length:.3f}",
                    *_streams(audio), "-c", "copy", "-avoid_negative_ts", "make_zero", *_common(ext), "-y", tmp.name]
            note = t["fast_cut"] if start > 0 else t["copy"]
            recode = False
        else:
            _needs_hevc(video)
            out_ext, vargs, aargs, codec = encoder(ext, video=video)
            ext = out_ext
            tmp = ctx.work / f"corte-{n}.{ext}"
            args = [ffmpeg(), *BASE, *threads(ctx), "-ss", f"{start:.3f}", "-f", demuxer, "-i", str(inp.path), "-t", f"{length:.3f}",
                    *_streams(audio), *vargs, *_even_scale(codec=codec), *(aargs if audio else []), *_common(ext), "-y", tmp.name]
            note = t["precise"].format(codec=CODEC_NAME[codec]) + (f" {t['mp4']}" if SAME[_ext(inp)] != ext else "")
            recode = True
        _run(ctx, args, length, recode, video)
        dst, name = _finish(ctx, tmp, inp, "-recortado" if ctx.locale != "en" else "-trimmed", ext)
        return {"path": str(dst), "name": name, "note": note}

    return _batch(ctx, each, "videos-recortados.zip")


# ——— rotar-video ———

def _rotation(video: dict) -> float:
    for side in video.get("side_data_list") or []:
        if "rotation" in side:
            try:
                return float(side["rotation"])
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _flipped(video: dict) -> bool:
    for side in video.get("side_data_list") or []:
        matrix = side.get("displaymatrix")
        if isinstance(matrix, str):
            rows = [[int(x) for x in re.findall(r"-?\d+", line.split(":", 1)[1])] for line in matrix.strip().splitlines() if ":" in line]
            if len(rows) >= 2 and len(rows[0]) >= 2 and len(rows[1]) >= 2:
                return rows[0][0] * rows[1][1] - rows[0][1] * rows[1][0] < 0
    return False


def _normalize(deg: float) -> float:
    deg = deg % 360
    return deg - 360 if deg > 180 else deg


TRANSPOSE = {90: "transpose=clock", 180: "transpose=clock,transpose=clock", 270: "transpose=cclock"}


def run_rotate(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    t = _t(ctx)
    angle = int(o.angulo)

    def each(n: int, inp: InputFile) -> dict:
        demuxer, _info, duration, video, audio = checked(ctx, inp)
        ext = SAME[_ext(inp)]
        if angle == 0 and o.voltear == "no":
            raise ToolError(ErrorCode.INVALID_OPTIONS, "video_rotate_nothing")
        # Un vídeo ya volteado (matriz con determinante negativo) no se puede girar sumando grados: se giran los píxeles.
        if o.modo == "rapido" and ext in DISPLAY_MATRIX and not _flipped(video):
            # La matriz es en grados antihorarios: girar «angle» en sentido horario sobre el giro que ya tuviera.
            rotation = _normalize(_rotation(video) - angle)
            flips = (["-display_hflip"] if o.voltear == "horizontal" else ["-display_vflip"] if o.voltear == "vertical" else [])
            tmp = ctx.work / f"giro-{n}.{ext}"
            args = [ffmpeg(), *BASE, *threads(ctx), "-display_rotation:V:0", f"{rotation:g}", *[f"{f}:V:0" for f in flips], "-f", demuxer,
                    "-i", str(inp.path), *_streams(audio), "-c", "copy", *cap(ctx), *_common(ext), "-y", tmp.name]
            note, recode = t["matrix"], False
        else:
            _needs_hevc(video)
            out_ext, vargs, aargs, codec = encoder(ext, video=video)
            flip = {"horizontal": "hflip", "vertical": "vflip"}.get(o.voltear, "")
            # FFmpeg ya aplica al decodificar el giro guardado (autorotate); aquí se suma el pedido.
            chain = ",".join(filter(None, [TRANSPOSE.get(angle, ""), flip]))
            tmp = ctx.work / f"giro-{n}.{out_ext}"
            args = [ffmpeg(), *BASE, *threads(ctx), "-f", demuxer, "-i", str(inp.path), *_streams(audio), *vargs, *_even_scale(chain, codec), *cap(ctx),
                    *(["-c:a", "copy"] if audio and _audio_fits(out_ext, audio) else aargs if audio else []), *_common(out_ext), "-y", tmp.name]
            note = t["pixels"].format(codec=CODEC_NAME[codec]) + (f" {t['mp4']}" if out_ext != ext else "")
            ext, recode = out_ext, True
        _run(ctx, args, duration, recode, video)
        dst, name = _finish(ctx, tmp, inp, "-girado" if ctx.locale != "en" else "-rotated", ext)
        return {"path": str(dst), "name": name, "note": note}

    return _batch(ctx, each, "videos-girados.zip")


def _audio_fits(ext: str, audio: dict) -> bool:
    from tools.av.video import COPY_OK

    return audio.get("codec_name") in COPY_OK["webm" if ext == "webm" else "mp4"][1]


# ——— comprimir-video ———

def _remux_original(ctx: ToolContext, n: int, inp: InputFile, demuxer: str, video: dict, audio: dict | None, duration: float,
                    ext: str, suffix: str, note: str) -> dict:
    """El original copiado sin recodificar pero sin metadatos (fecha, GPS) ni, si se pidió, sonido."""
    tmp = ctx.work / f"original-{n}.{ext}"
    _run(ctx, [ffmpeg(), *BASE, "-f", demuxer, "-i", str(inp.path), *_streams(audio, ctx.options.sonido), "-c", "copy",
               *cap(ctx), *_common(ext), "-y", tmp.name], duration, False, video)
    dst, name = _finish(ctx, tmp, inp, suffix, ext)
    return {"path": str(dst), "name": name, "note": note}

def run_compress(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    t = _t(ctx)

    def each(n: int, inp: InputFile) -> dict:
        demuxer, _info, duration, video, audio = checked(ctx, inp)
        _needs_hevc(video)
        ext = SAME[_ext(inp)]
        out_ext, vargs, aargs, codec = encoder(ext, o.nivel, video)
        suffix = "-comprimido" if ctx.locale != "en" else "-compressed"
        if codec == "av1" and min(int(video.get("width") or 0), int(video.get("height") or 0)) < 64:
            # Demasiado pequeño para AV1 (y para ganar nada): el original sin metadatos (y sin sonido, si se pidió).
            return _remux_original(ctx, n, inp, demuxer, video, audio, duration, ext, suffix, t["not_smaller"])
        scale = ""
        if o.resolucion != "original":
            top = int(o.resolucion)
            # El lado corto, al máximo elegido, decidido dentro del filtro: FFmpeg gira antes la imagen según su
            # orientación guardada, así que un vídeo vertical del móvil (1280 × 720 girado) a «480» queda en 480 × 854.
            # Nunca se amplía.
            scale = (f"scale=w='if(gte(iw,ih),-2,min(iw,{top}))':h='if(gte(iw,ih),min(ih,{top}),-2)'")
        fps = "fps=30" if o.fps_30 else ""
        tmp = ctx.work / f"comprimido-{n}.{out_ext}"
        args = [ffmpeg(), *BASE, *threads(ctx), "-f", demuxer, "-i", str(inp.path), *_streams(audio, o.sonido), *vargs,
                *_even_scale(",".join(filter(None, [scale, fps])), codec), *(aargs if audio and o.sonido else ["-an"]), *cap(ctx),
                *_common(out_ext), *threads(ctx), "-y", tmp.name]
        _run(ctx, args, duration, True, video)
        if not tmp.exists() or not tmp.stat().st_size:
            raise ToolError(ErrorCode.ENGINE_FAILED, "FFmpeg no generó el vídeo")
        before, after = inp.path.stat().st_size, tmp.stat().st_size
        # Si no pesa menos y no se pidió nada más que comprimir, el original (sin metadatos); si se pidió quitar el
        # sonido, bajar la resolución o los fotogramas, el resultado aunque no pese menos (D-245).
        asked = not o.sonido or o.resolucion != "original" or o.fps_30
        if after >= before and not asked:
            tmp.unlink()
            return _remux_original(ctx, n, inp, demuxer, video, audio, duration, ext, suffix, t["not_smaller"])
        dst, name = _finish(ctx, tmp, inp, suffix, out_ext)
        note = t["compressed"].format(codec=CODEC_NAME[codec], before=_size(before), after=_size(after),
                                      pct=round(100 * (1 - after / before)))
        return {"path": str(dst), "name": name, "note": note + (f" {t['mp4']}" if out_ext != ext else "")}

    return _batch(ctx, each, "videos-comprimidos.zip")
