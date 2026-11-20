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


def test_gif_start_past_the_end_is_clamped(make_ctx, tmp_path):
    src = _clip(tmp_path, "corto.mp4", "libx264", seconds=2)
    out = run("video-a-gif", make_ctx("video-a-gif", [src], {"inicio": 60, "duracion": 5}))
    assert Path(out[0]["path"]).stat().st_size > 0 and out[0]["note"]


@pytest.mark.integration
def test_api_rejects_video_without_a_video_plan(api, user_token, tus_upload, tmp_path):
    from helpers import auth

    src = _clip(tmp_path, "corto.mp4", "libx264")
    token = user_token(user_id="video-gratis")
    api.get("/v1/me", headers=auth(token))
    uid, _ = tus_upload(token, "mp4-a-webm", src)
    res = api.post("/v1/jobs", json={"tool": "mp4-a-webm", "upload_ids": [uid], "options": {}}, headers=auth(token))
    assert res.status_code == 403 and res.json()["error"]["code"] == "LIMIT_EXCEEDED"
    tools = {t["slug_es"]: t for t in json.loads((Path(__file__).resolve().parents[1] / "packages/registry/registry.json").read_text())["tools"]}
    assert tools["mp4-a-webm"]["needs_video"] and tools["pptx-a-video"]["needs_video"] and not tools["srt-a-vtt"]["needs_video"]
