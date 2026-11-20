"""F5-V1 (7.9, D-241): conversores de vídeo con el FFmpeg real. Se comprueba con ffprobe que se remultiplexa sin recodificar
cuando los códecs caben, que se recodifica a VP9, H.264 (con su interruptor) o AV1 cuando no, que HEVC necesita su
interruptor para recodificarse, que el vídeo es solo para Pro y dentro de sus minutos, y video-a-gif y gif-a-mp4."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core.errors import ToolError
from test_tools import make_ctx, run  # noqa: F401  (fixture)

FFMPEG = shutil.which("ffmpeg")
pytestmark = pytest.mark.skipif(not FFMPEG, reason="sin ffmpeg")


def _clip(tmp_path: Path, name: str, vcodec: str, acodec: str | None = "aac", seconds: float = 2, size: str = "320x240") -> Path:
    path = tmp_path / name
    args = [FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=15:duration={seconds}"]
    if acodec:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", acodec]
    args += ["-c:v", vcodec, *(["-pix_fmt", "yuv420p"] if vcodec != "gif" else []),
             "-metadata", "title=Vacaciones", "-metadata", "location=+40.4168-003.7038/", "-shortest", "-y", str(path)]
    subprocess.run(args, check=True)
    return path


def _probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:format_tags:stream=codec_type,codec_name",
                          "-of", "json", str(path)], capture_output=True, check=True).stdout
    info = json.loads(out)
    info["codecs"] = {s["codec_type"]: s["codec_name"] for s in info["streams"]}
    return info


def test_mkv_with_h264_and_aac_is_remuxed(make_ctx, tmp_path):
    src = _clip(tmp_path, "viaje.mkv", "libx264")
    out = run("mkv-a-mp4", make_ctx("mkv-a-mp4", [src]))
    assert out[0]["name"] == "viaje.mp4" and "sin recodificar" in out[0]["note"]
    info = _probe(Path(out[0]["path"]))
    assert info["codecs"] == {"video": "h264", "audio": "aac"}
    assert abs(float(info["format"]["duration"]) - 2) < 0.3
    tags = {k.lower() for k in info["format"].get("tags", {})}
    assert "title" not in tags and "location" not in tags  # metadatos globales fuera


def test_webm_to_mp4_reencodes_to_av1_without_h264_flag(make_ctx, tmp_path, monkeypatch):
    monkeypatch.delenv("VIDEO_H264_ENCODING_ENABLED", raising=False)
    src = _clip(tmp_path, "clase.webm", "libvpx-vp9", "libopus")
    out = run("webm-a-mp4", make_ctx("webm-a-mp4", [src]))
    info = _probe(Path(out[0]["path"]))
    # VP9 no cabe en el MP4 que se pide: AV1; Opus sí cabe y se copia.
    assert info["codecs"] == {"video": "av1", "audio": "opus"} and "AV1" in out[0]["note"]


def test_webm_to_mp4_uses_h264_with_its_flag(make_ctx, tmp_path, monkeypatch):
    from tools.av import video

    monkeypatch.setenv("VIDEO_H264_ENCODING_ENABLED", "true")
    if not video.h264_encoder():
        pytest.skip("FFmpeg sin codificador de H.264")
    src = _clip(tmp_path, "clase.webm", "libvpx-vp9", "libvorbis")
    out = run("webm-a-mp4", make_ctx("webm-a-mp4", [src]))
    assert _probe(Path(out[0]["path"]))["codecs"] == {"video": "h264", "audio": "aac"}


def test_mp4_to_webm_reencodes_to_vp9_and_opus(make_ctx, tmp_path):
    src = _clip(tmp_path, "demo.mp4", "libx264")
    out = run("mp4-a-webm", make_ctx("mp4-a-webm", [src]))
    assert out[0]["name"] == "demo.webm" and "VP9" in out[0]["note"]
    assert _probe(Path(out[0]["path"]))["codecs"] == {"video": "vp9", "audio": "opus"}


def test_avi_with_mpeg4_and_mp3_is_remuxed_and_video_without_sound(make_ctx, tmp_path):
    src = _clip(tmp_path, "viejo.avi", "mpeg4", "libmp3lame")
    out = run("avi-a-mp4", make_ctx("avi-a-mp4", [src]))
    assert _probe(Path(out[0]["path"]))["codecs"] == {"video": "mpeg4", "audio": "mp3"}
    mute = _clip(tmp_path, "mudo.mov", "libx264", None)
    out = run("mov-a-mp4", make_ctx("mov-a-mp4", [mute]))
    assert _probe(Path(out[0]["path"]))["codecs"] == {"video": "h264"} and "no tiene sonido" in out[0]["note"]


def test_hevc_is_remuxed_but_needs_its_flag_to_reencode(make_ctx, tmp_path, monkeypatch):
    from tools.av import video

    if "libx265" not in video.encoders():
        pytest.skip("FFmpeg sin libx265 para crear la muestra")
    monkeypatch.delenv("HEVC_DECODE_ENABLED", raising=False)
    src = _clip(tmp_path, "iphone.mov", "libx265")
    out = run("mov-a-mp4", make_ctx("mov-a-mp4", [src]))
    assert _probe(Path(out[0]["path"]))["codecs"]["video"] == "hevc"
    with pytest.raises(ToolError) as err:
        run("mp4-a-webm", make_ctx("mp4-a-webm", [_clip(tmp_path, "iphone.mp4", "libx265")]))
    assert err.value.detail == "video_hevc"


def test_video_is_pro_only_and_within_its_minutes(make_ctx, tmp_path):
    src = _clip(tmp_path, "corto.mp4", "libx264")
    with pytest.raises(ToolError) as err:
        run("mp4-a-webm", make_ctx("mp4-a-webm", [src], plan="free"))
    assert err.value.detail == "video_plan"
    ctx = make_ctx("mp4-a-webm", [src])
    ctx.plan = ctx.plan.model_copy(update={"video_minutes": 0})
    with pytest.raises(ToolError) as err:
        run("mp4-a-webm", ctx)
    assert err.value.code == "LIMIT_EXCEEDED"


def test_not_a_video_is_rejected(make_ctx, tmp_path):
    fake = tmp_path / "falso.mp4"
    fake.write_bytes(b"\x00" * 4096)
    with pytest.raises(ToolError):
        run("mp4-a-webm", make_ctx("mp4-a-webm", [fake]))


def test_video_to_gif_and_back(make_ctx, tmp_path):
    from PIL import Image

    src = _clip(tmp_path, "baile.mp4", "libx264", seconds=4, size="640x360")
    out = run("video-a-gif", make_ctx("video-a-gif", [src], {"inicio": 1, "duracion": 2, "fps": 10, "ancho": 320}))
    gif = Path(out[0]["path"])
    assert out[0]["name"] == "baile.gif"
    with Image.open(gif) as im:
        assert im.size == (320, 180) and im.n_frames == 20 and im.info.get("loop") == 0
    out = run("gif-a-mp4", make_ctx("gif-a-mp4", [gif]))
    info = _probe(Path(out[0]["path"]))
    assert info["codecs"]["video"] in {"av1", "h264"} and "audio" not in info["codecs"]
    assert abs(float(info["format"]["duration"]) - 2) < 0.3


def test_gif_start_past_the_end_is_an_error_and_it_never_upscales(make_ctx, tmp_path):
    from PIL import Image

    src = _clip(tmp_path, "corto.mp4", "libx264", seconds=2)
    with pytest.raises(ToolError) as err:
        run("video-a-gif", make_ctx("video-a-gif", [src], {"inicio": 60, "duracion": 5}))
    assert err.value.detail == "video_cut_range"
    out = run("video-a-gif", make_ctx("video-a-gif", [src], {"inicio": 1, "duracion": 5, "ancho": 800}))
    with Image.open(out[0]["path"]) as im:
        assert im.size == (320, 240)  # 320 px de origen: no se amplía a 800
    assert "dura 1 s" in out[0]["note"]


@pytest.mark.integration
def test_api_rejects_video_without_a_video_plan(api, user_token, tus_upload, tmp_path):
    from helpers import auth

    src = _clip(tmp_path, "corto.mp4", "libx264")
    import uuid

    token = user_token(user_id=f"video-gratis-{uuid.uuid4().hex[:8]}")
    api.get("/v1/me", headers=auth(token))
    uid, resp = tus_upload(token, "mp4-a-webm", src)
    # Ni siquiera se sube (D-245); la API lo vuelve a comprobar al crear el trabajo.
    assert uid is None and resp["HTTPResponse"]["StatusCode"] == 403 and "LIMIT_EXCEEDED" in resp["HTTPResponse"]["Body"]
    tools = {t["slug_es"]: t for t in json.loads((Path(__file__).resolve().parents[1] / "packages/registry/registry.json").read_text(encoding="utf-8"))["tools"]}
    assert tools["mp4-a-webm"]["needs_video"] and tools["pptx-a-video"]["needs_video"] and not tools["srt-a-vtt"]["needs_video"]


# ——— F5-V2 (D-242): comprimir, recortar, rotar y quitar el audio ———

def _streams_info(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height:stream_disposition=attached_pic"
                          ":stream_side_data=rotation",
                          "-of", "json", str(path)], capture_output=True, check=True).stdout
    return {s["codec_type"]: s for s in json.loads(out)["streams"] if not (s.get("disposition") or {}).get("attached_pic")}


def test_remove_audio_copies_the_picture(make_ctx, tmp_path):
    src = _clip(tmp_path, "charla.mkv", "libx264")
    out = run("quitar-audio-video", make_ctx("quitar-audio-video", [src]))
    assert out[0]["name"] == "charla-sin-audio.mkv" and "Sin recodificar" in out[0]["note"]
    assert _probe(Path(out[0]["path"]))["codecs"] == {"video": "h264"}


def test_trim_fast_and_precise(make_ctx, tmp_path, monkeypatch):
    monkeypatch.delenv("VIDEO_H264_ENCODING_ENABLED", raising=False)
    src = _clip(tmp_path, "partido.mp4", "libx264", seconds=6)
    out = run("recortar-video", make_ctx("recortar-video", [src], {"inicio": "0:02", "fin": "0:04"}))
    info = _probe(Path(out[0]["path"]))
    assert info["codecs"] == {"video": "h264", "audio": "aac"} and "fotograma clave" in out[0]["note"]
    assert 1.8 <= float(info["format"]["duration"]) <= 4.3  # desde el fotograma clave anterior
    out = run("recortar-video", make_ctx("recortar-video", [src], {"inicio": "2", "fin": "4", "modo": "preciso"}))
    info = _probe(Path(out[0]["path"]))
    assert info["codecs"]["video"] == "av1" and abs(float(info["format"]["duration"]) - 2) < 0.15
    with pytest.raises(ToolError) as err:
        run("recortar-video", make_ctx("recortar-video", [src], {"inicio": "0:30"}))
    assert err.value.detail == "video_cut_range"
    with pytest.raises(Exception):
        make_ctx("recortar-video", [src], {"inicio": "5", "fin": "3"})


def test_rotate_mp4_without_reencoding_adds_to_existing_rotation(make_ctx, tmp_path):
    src = _clip(tmp_path, "movil.mp4", "libx264")
    out = run("rotar-video", make_ctx("rotar-video", [src], {"angulo": "90"}))
    rotated = Path(out[0]["path"])
    info = _streams_info(rotated)
    assert info["video"]["codec_name"] == "h264" and info["video"]["side_data_list"][0]["rotation"] == -90
    assert "sin recodificar" in out[0]["note"].lower()
    again = run("rotar-video", make_ctx("rotar-video", [rotated], {"angulo": "90"}))
    assert abs(_streams_info(Path(again[0]["path"]))["video"]["side_data_list"][0]["rotation"]) == 180


def test_rotate_webm_rotates_the_pixels(make_ctx, tmp_path):
    src = _clip(tmp_path, "clip.webm", "libvpx-vp9", "libopus")
    out = run("rotar-video", make_ctx("rotar-video", [src], {"angulo": "270", "voltear": "horizontal"}))
    info = _streams_info(Path(out[0]["path"]))
    assert (info["video"]["width"], info["video"]["height"]) == (240, 320) and info["video"]["codec_name"] == "vp9"
    assert info["audio"]["codec_name"] == "opus"
    with pytest.raises(ToolError):
        run("rotar-video", make_ctx("rotar-video", [src], {"angulo": "0"}))


def test_compress_reduces_size_and_resolution_and_never_grows(make_ctx, tmp_path, monkeypatch):
    monkeypatch.delenv("VIDEO_H264_ENCODING_ENABLED", raising=False)
    big = tmp_path / "grande.mov"
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=3", "-f", "lavfi",
                    "-i", "sine=duration=3", "-c:v", "libx264", "-crf", "8", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", str(big)],
                   check=True)
    out = run("comprimir-video", make_ctx("comprimir-video", [big], {"nivel": "fuerte", "resolucion": "480"}))
    path = Path(out[0]["path"])
    info = _streams_info(path)
    assert path.suffix == ".mp4" and path.stat().st_size < big.stat().st_size
    assert info["video"]["codec_name"] == "av1" and info["video"]["height"] == 480 and info["video"]["width"] == 854
    assert "menos" in out[0]["note"] and "MP4" in out[0]["note"]
    # Un vídeo ya diminuto: se devuelve el original.
    tiny = _clip(tmp_path, "mini.mp4", "libx264", None, seconds=1, size="64x48")
    out = run("comprimir-video", make_ctx("comprimir-video", [tiny], {"nivel": "ligera"}))
    assert "ya estaba" in out[0]["note"]  # se devuelve el original sin recodificar
    assert _probe(Path(out[0]["path"]))["codecs"] == {"video": "h264"}


def test_tiny_gif_to_av1_is_padded(make_ctx, tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.delenv("VIDEO_H264_ENCODING_ENABLED", raising=False)
    gif = tmp_path / "icono.gif"
    frames = [Image.new("RGB", (40, 30), c) for c in ("red", "blue", "green")]
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=200, loop=0)
    out = run("gif-a-mp4", make_ctx("gif-a-mp4", [gif]))
    info = _streams_info(Path(out[0]["path"]))
    assert info["video"]["codec_name"] == "av1" and (info["video"]["width"], info["video"]["height"]) == (64, 64)



# ——— D-245: correcciones de la revisión de F5-V1 y F5-V2 ———

def _with_cover(tmp_path: Path) -> Path:
    """MP4 con carátula PNG como primera pista (la que ffprobe lista primero)."""
    from PIL import Image

    cover = tmp_path / "portada.png"
    Image.new("RGB", (300, 300), "red").save(cover)
    clip = _clip(tmp_path, "con-portada-base.mp4", "libx264")
    out = tmp_path / "con-portada.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-i", str(cover), "-i", str(clip), "-map", "0", "-map", "1", "-c", "copy",
                    "-disposition:v:0", "attached_pic", "-y", str(out)], check=True)
    return out


def test_cover_art_is_never_taken_as_the_video(make_ctx, tmp_path):
    src = _with_cover(tmp_path)
    out = run("mp4-a-webm", make_ctx("mp4-a-webm", [src]))
    info = _streams_info(Path(out[0]["path"]))
    assert (info["video"]["width"], info["video"]["height"]) == (320, 240) and info["video"]["codec_name"] == "vp9"
    out = run("quitar-audio-video", make_ctx("quitar-audio-video", [src]))
    info = _streams_info(Path(out[0]["path"]))
    assert info["video"]["codec_name"] == "h264" and (info["video"]["width"], info["video"]["height"]) == (320, 240)


def test_compress_caps_the_short_side_of_rotated_phone_videos(make_ctx, tmp_path, monkeypatch):
    monkeypatch.delenv("VIDEO_H264_ENCODING_ENABLED", raising=False)
    flat = _clip(tmp_path, "vertical-base.mp4", "libx264", size="1280x720", seconds=1)
    rotated = tmp_path / "vertical.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-display_rotation", "-90", "-i", str(flat), "-c", "copy", "-y", str(rotated)], check=True)
    out = run("comprimir-video", make_ctx("comprimir-video", [rotated], {"resolucion": "480"}))
    info = _streams_info(Path(out[0]["path"]))
    assert (info["video"]["width"], info["video"]["height"]) == (480, 854)


def test_compress_fallback_respects_choices_and_drops_metadata(make_ctx, tmp_path):
    tiny = _clip(tmp_path, "mini.mp4", "libx264", seconds=1, size="48x48")
    out = run("comprimir-video", make_ctx("comprimir-video", [tiny], {"sonido": False}))
    info = _probe(Path(out[0]["path"]))
    assert "ya estaba" in out[0]["note"] and info["codecs"] == {"video": "h264"}
    assert "location" not in {k.lower() for k in info["format"].get("tags", {})}


def test_unknown_duration_is_capped_by_the_plan(make_ctx, tmp_path):
    # Un MKV escrito a una tubería no guarda su duración.
    streamed = tmp_path / "directo.mkv"
    with open(streamed, "wb") as f:
        subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=90", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-f", "matroska", "-"], stdout=f, check=True)
    ctx = make_ctx("mkv-a-mp4", [streamed])
    ctx.plan = ctx.plan.model_copy(update={"video_minutes": 1})
    out = run("mkv-a-mp4", ctx)
    assert float(_probe(Path(out[0]["path"]))["format"]["duration"]) <= 60.5


def test_minutes_count_for_the_whole_task_and_the_work_must_fit_the_time_limit(make_ctx, tmp_path):
    a = _clip(tmp_path, "a.mp4", "libx264", seconds=2)
    b = _clip(tmp_path, "b.mp4", "libx264", seconds=2)
    ctx = make_ctx("mp4-a-webm", [a, b])
    ctx.plan = ctx.plan.model_copy(update={"video_minutes": 0.05})  # 3 s para toda la tarea
    with pytest.raises(ToolError) as err:
        run("mp4-a-webm", ctx)
    assert err.value.code == "LIMIT_EXCEEDED"
    from tools.av import video

    ctx = make_ctx("mp4-a-webm", [a])
    with pytest.raises(ToolError) as err:
        video.ensure_time(ctx, 4 * 3600, {"width": 1920, "height": 1080}, True)
    assert err.value.detail == "video_too_long"
    video.ensure_time(make_ctx("mp4-a-webm", [a]), 3600, {"width": 1920, "height": 1080}, True)  # 1 h de 1080p sí cabe
    assert video.memory_mb({"width": 3840, "height": 2160}) > video.memory_mb({"width": 1920, "height": 1080})


def test_4k_reencode_fits_its_memory(make_ctx, tmp_path, monkeypatch):
    monkeypatch.delenv("VIDEO_H264_ENCODING_ENABLED", raising=False)
    src = _clip(tmp_path, "4k.mp4", "libx264", seconds=0.4, size="3840x2160", acodec=None)
    out = run("webm-a-mp4", make_ctx("webm-a-mp4", [_clip(tmp_path, "4k.webm", "libvpx-vp9", None, seconds=0.4, size="3840x2160")]))
    assert _streams_info(Path(out[0]["path"]))["video"]["codec_name"] == "av1"
    out = run("mp4-a-webm", make_ctx("mp4-a-webm", [src]))
    assert _streams_info(Path(out[0]["path"]))["video"]["width"] == 3840


def test_m4v_and_quicktime_branded_mp4_are_accepted(tmp_path):
    from core.filetype import detect, matches

    m4v = _clip(tmp_path, "clip.m4v", "libx264")
    subprocess.run([FFMPEG, "-v", "error", "-i", str(m4v), "-c", "copy", "-brand", "M4V ", "-f", "mp4", "-y", str(tmp_path / "b.m4v")], check=True)
    assert matches(detect(tmp_path / "b.m4v", ".m4v"), ".m4v", ("mov", "m4v"))
    mov = _clip(tmp_path, "clip.mov", "libx264")
    renamed = tmp_path / "clip-qt.mp4"
    renamed.write_bytes(mov.read_bytes())
    assert matches(detect(renamed, ".mp4"), ".mp4", ("mp4",))
