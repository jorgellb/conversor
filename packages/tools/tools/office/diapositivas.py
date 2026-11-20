"""pptx-a-imagenes y pptx-a-video (7.13, F6-C, D-237): la presentación a PDF con el LibreOffice de Gotenberg y cada
diapositiva a imagen con pypdfium2; el vídeo, con FFmpeg LGPL (VP9 en WebM o AV1 en MP4: sin H.264, que va detrás de
VIDEO_H264_ENCODING_ENABLED, 11). PowerPoint, Keynote exportado a PPTX, ODP y PPT.
"""
from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

import pypdfium2 as pdfium

from core.errors import ErrorCode, ToolError
from core.options import parse_page_ranges
from core.zipguard import check_zip
from tools.base import ToolContext, derived_name, run_engine
from tools.office import gotenberg
from tools.office.office_a_pdf import lo_fields
from tools.office.specs import OfficeOptions
from tools.pdf.common import with_batch_zip

MAX_SLIDES_VIDEO = 150
MAX_PIXELS = 40_000_000
VIDEO_SIZES = {"720": (1280, 720), "1080": (1920, 1080)}


def slides_pdf(ctx: ToolContext, inp, n: int) -> Path:
    ext = (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()
    if zipfile.is_zipfile(inp.path):
        check_zip(inp.path)
    data = gotenberg.libreoffice(ctx.settings.GOTENBERG_URL, inp.path, f"presentacion.{ext}", lo_fields(OfficeOptions(), None))
    dst = ctx.work / f"diapositivas-{n}.pdf"
    dst.write_bytes(data)
    return dst


def _selected(pdf: pdfium.PdfDocument, spec: str, limit: int) -> list[int]:
    """Las diapositivas elegidas; el límite cuenta las elegidas, no la presentación entera (D-243)."""
    total = len(pdf)
    if total == 0:
        raise ToolError(ErrorCode.CORRUPT_FILE, "Presentación sin diapositivas")
    try:
        pages = parse_page_ranges(spec, total) if spec.strip() else list(range(total))
    except ValueError as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, str(exc)) from exc
    if not pages:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "Ninguna diapositiva elegida")
    if len(pages) > limit:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{len(pages)} diapositivas")
    return pages


def run_images(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        pdf = pdfium.PdfDocument(str(slides_pdf(ctx, inp, n)))
        try:
            pages = _selected(pdf, o.diapositivas, ctx.plan.pdf_pages)
            stem = Path(inp.name).stem or "diapositiva"
            files = []
            for k, index in enumerate(pages):
                page = pdf[index]
                scale = o.resolucion / 72
                w, h = page.get_size()
                cap = min(MAX_PIXELS, ctx.settings.RENDER_MAX_PIXELS)
                if w * h * scale * scale > cap:
                    scale = (cap / (w * h)) ** 0.5
                image = page.render(scale=scale).to_pil()
                page.close()
                buf = io.BytesIO()
                if o.formato == "jpg":
                    image.convert("RGB").save(buf, "JPEG", quality=92, dpi=(o.resolucion, o.resolucion))
                else:
                    image.save(buf, "PNG", dpi=(o.resolucion, o.resolucion))
                name = f"{stem}-{index + 1:03d}.{o.formato}"
                dst = ctx.output(name)
                dst.write_bytes(buf.getvalue())
                files.append({"path": str(dst), "name": name})
                ctx.report((n + (k + 1) / len(pages)) / len(ctx.inputs), None)
        finally:
            pdf.close()
        outputs += files
    return with_batch_zip(ctx, outputs, "diapositivas.zip")


def run_video(ctx: ToolContext) -> list[dict]:
    from tools.av.audio import BASE, ffmpeg
    from tools.av.video import av1

    o = ctx.options
    if not ctx.plan.video:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "video_plan")
    width, height = VIDEO_SIZES.get(o.resolucion, VIDEO_SIZES["1080"])
    outputs = []
    minutes_left = ctx.plan.video_minutes * 60  # los minutos del plan cuentan para todos los archivos de la tarea
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        pdf = pdfium.PdfDocument(str(slides_pdf(ctx, inp, n)))
        folder = ctx.work / f"video-{n}"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            pages = _selected(pdf, o.diapositivas, MAX_SLIDES_VIDEO)
            total = len(pages) * o.segundos
            if total > minutes_left:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{total} s de vídeo")
            minutes_left -= total
            frames = []
            for k, index in enumerate(pages):
                page = pdf[index]
                w, h = page.get_size()
                scale = min(width / w, height / h)
                image = page.render(scale=scale).to_pil().convert("RGB")
                page.close()
                # Centrada en un fondo negro del tamaño del vídeo (las diapositivas 4:3 quedan con bandas).
                from PIL import Image

                canvas = Image.new("RGB", (width, height), "black")
                canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
                frame = folder / f"d{k:04d}.png"
                canvas.save(frame, "PNG")
                frames.append(frame)
        finally:
            pdf.close()
        # Lista del demultiplexor concat: cada diapositiva su tiempo; la última se repite para que dure lo suyo.
        lines = []
        for frame in frames:
            lines += [f"file '{frame.name}'", f"duration {o.segundos}"]
        lines.append(f"file '{frames[-1].name}'")
        (folder / "lista.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        # Diapositivas quietas: 5 fotogramas por segundo bastan; con fundidos, 15 para que sean suaves.
        vf = ["fps=5", "format=yuv420p"]
        if o.transicion and len(frames) > 1:
            # Fundido a negro al entrar y al salir de cada diapositiva. Cada filtro solo actúa en su ventana (`enable`):
            # sin ella, `fade` deja en negro todo lo de antes de su entrada y lo de después de su salida, y con varias
            # diapositivas el vídeo entero salía negro (D-243).
            fades = []
            for k in range(len(frames)):
                start, end = k * o.segundos, (k + 1) * o.segundos
                fades += [f"fade=t=in:st={start}:d=0.4:enable='between(t,{start},{start + 0.4})'",
                          f"fade=t=out:st={end - 0.4}:d=0.4:enable='between(t,{end - 0.4},{end})'"]
            vf = ["fps=15", *fades, "format=yuv420p"]
        ext = "webm" if o.formato == "webm" else "mp4"
        # Diapositivas casi siempre quietas: VP9 en tiempo real y AV1 con un preset rápido dan el mismo resultado mucho antes.
        codec = (["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-row-mt", "1", "-deadline", "realtime", "-cpu-used", "8"] if ext == "webm"
                 else [*av1(36), "-movflags", "+faststart"])
        out = folder / f"salida.{ext}"
        args = [ffmpeg(), *BASE, "-f", "concat", "-safe", "0", "-i", "lista.txt", "-vf", ",".join(vf), "-an", *codec,
                "-t", str(total), "-threads", str(max(1, ctx.threads)), "-y", out.name]
        # Memoria de datos y no virtual: SVT-AV1 reserva mucho espacio de direcciones y con RLIMIT_AS se cae (como Calibre, D-52).
        run_engine(args, cwd=folder, timeout=int(max(300, total * 4 + 120)), mem_mb=1400, limit_data=True, max_file_mb=4096)
        if not out.exists() or not out.stat().st_size:
            raise ToolError(ErrorCode.ENGINE_FAILED, "FFmpeg no generó el vídeo")
        name = derived_name(inp.name, "", ext)
        dst = ctx.output(name)
        shutil.move(out, dst)
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, f"presentaciones-{ext}.zip")
