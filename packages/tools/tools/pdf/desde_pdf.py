"""pdf-a-tiff y pdf-a-svg (A.9): pypdfium2 y Pillow para renderizar, tiffcp para comprimir y pdftocairo para SVG.

CMYK con LittleCMS (Pillow ImageCms) y el perfil FOGRA39 de colord-data (CC0, D-60). pdftocairo es GPL y solo corre
como proceso externo en el servidor (11).
"""
from __future__ import annotations

import shutil
from functools import lru_cache
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from core.errors import ErrorCode, ToolError
from core.options import parse_page_ranges
from tools.base import ToolContext, derived_name, run_engine, zip_files
from tools.pdf.common import open_pdf, with_batch_zip

BW_THRESHOLD = 160
# Compresión de tiffcp en blanco y negro (A.9). «G3 1D con EOL» alinea cada fin de línea a byte (fill).
TIFFCP_BW = {"g4": "g4", "g3_1d": "g3:1d", "g3_1d_eol": "g3:1d:fill", "g3_2d": "g3:2d", "lzw": "lzw", "packbits": "packbits"}


def render_scale(page, dpi: int, max_pixels: int) -> float:
    w, h = page.get_size()
    scale = dpi / 72
    pixels = (w * scale) * (h * scale)
    if pixels > max_pixels:
        scale *= (max_pixels / pixels) ** 0.5
    return scale


@lru_cache(maxsize=4)
def _cmyk_transform(profile_path: str):
    from PIL import ImageCms

    try:
        cmyk = ImageCms.getOpenProfile(profile_path)
    except (OSError, ImageCms.PyCMSError) as exc:
        raise ToolError(ErrorCode.ENGINE_FAILED, "Falta el perfil CMYK") from exc
    transform = ImageCms.buildTransform(ImageCms.createProfile("sRGB"), cmyk, "RGB", "CMYK",
                                       renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC)
    return transform, cmyk.tobytes()


def to_cmyk(img: Image.Image, profile_path: str) -> tuple[Image.Image, bytes]:
    """RGB a CMYK con LittleCMS; devuelve la imagen y el perfil ICC para incrustarlo."""
    from PIL import ImageCms

    transform, icc = _cmyk_transform(profile_path)
    return ImageCms.applyTransform(img.convert("RGB"), transform), icc


def convert_color(img: Image.Image, color: str, profile_path: str) -> tuple[Image.Image, bytes | None]:
    if color == "gris":
        return img.convert("L"), None
    if color == "bn":
        return img.convert("L").point(lambda v: 255 if v > BW_THRESHOLD else 0, mode="1"), None
    if color == "cmyk":
        return to_cmyk(img, profile_path)
    return img.convert("RGB"), None


def _open(ctx: ToolContext, path: Path) -> pdfium.PdfDocument:
    with open_pdf(path, None, ctx.plan.pdf_pages):
        pass  # contraseña, daño y límite de páginas con los mismos errores que el resto
    return pdfium.PdfDocument(str(path))


def _pages(spec: str, total: int) -> list[int]:
    try:
        return parse_page_ranges(spec, total)
    except ValueError as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, str(exc)) from exc


def _save_tiff(img: Image.Image, path: Path, dpi: int, icc: bytes | None) -> None:
    """TIFF sin comprimir para tiffcp. El blanco y negro va como «min-is-white», lo habitual con G3 y G4 (Pillow
    invierte los bits él mismo al indicarle esa fotometría)."""
    extra: dict = {"icc_profile": icc} if icc else {}
    if img.mode == "1":
        extra["tiffinfo"] = {262: 0}
    img.save(path, format="TIFF", compression=None, dpi=(dpi, dpi), **extra)


def _tiffcp(sources: list[Path], dst: Path, compression: str, cwd: Path) -> None:
    exe = shutil.which("tiffcp") or "tiffcp"
    run_engine([exe, "-c", compression, *[str(s) for s in sources], str(dst)], cwd=cwd, timeout=600, mem_mb=1024)
    if not dst.exists():
        raise ToolError(ErrorCode.ENGINE_FAILED, "tiffcp no generó el TIFF")


def run_tiff(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    compression = TIFFCP_BW[o.compresion_bn] if o.color == "bn" else "lzw"
    profile = ctx.settings.CMYK_ICC_PROFILE
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        doc = _open(ctx, inp.path)
        work = ctx.work / f"tiff-{n}"
        work.mkdir(parents=True, exist_ok=True)
        stem = Path(inp.name).stem or "documento"
        try:
            pages = _pages(o.paginas, len(doc))
            singles: list[Path] = []
            stacked: list[Image.Image] = []
            icc: bytes | None = None
            for k, idx in enumerate(pages):
                page = doc[idx]
                img = page.render(scale=render_scale(page, o.dpi, ctx.settings.RENDER_MAX_PIXELS)).to_pil()
                img, icc = convert_color(img, o.color, profile)
                if o.salida == "una_sola":
                    stacked.append(img)
                else:
                    raw = work / f"p{idx + 1:05d}.tif"
                    _save_tiff(img, raw, o.dpi, icc)
                    singles.append(raw)
                ctx.report((n + (k + 1) / len(pages)) / len(ctx.inputs), None)
        finally:
            doc.close()
        if stacked:
            width, height = max(i.width for i in stacked), sum(i.height for i in stacked)
            if width * height > ctx.settings.RENDER_MAX_PIXELS * 2:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "La imagen única sería demasiado grande")
            sheet = Image.new(stacked[0].mode, (width, height), "white" if stacked[0].mode != "CMYK" else (0, 0, 0, 0))
            y = 0
            for img in stacked:
                sheet.paste(img, (0, y))
                y += img.height
            raw = work / "todas.tif"
            _save_tiff(sheet, raw, o.dpi, icc)
            singles = [raw]
        if len(singles) == 1 or o.multipagina or o.salida == "una_sola":
            name = derived_name(inp.name, "", "tif")
            dst = ctx.output(name)
            _tiffcp(singles, dst, compression, work)
            outputs.append({"path": str(dst), "name": name})
        else:
            compressed = []
            for raw in singles:
                out = raw.with_name(f"{stem}-{int(raw.stem[1:])}.tif")
                _tiffcp([raw], out, compression, work)
                compressed.append((out, out.name))
            name = f"{stem}-tiff.zip"
            dst = ctx.output(name)
            zip_files(compressed, dst)
            outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "pdf-tiff.zip")


def run_svg(ctx: ToolContext) -> list[dict]:
    """Una página por SVG con pdftocairo; el texto sale como trazados, igual que se ve."""
    o = ctx.options
    exe = shutil.which("pdftocairo") or "pdftocairo"
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        doc = _open(ctx, inp.path)
        try:
            pages = _pages(o.paginas, len(doc))
        finally:
            doc.close()
        work = ctx.work / f"svg-{n}"
        work.mkdir(parents=True, exist_ok=True)
        local = work / "entrada.pdf"
        shutil.copyfile(inp.path, local)
        stem = Path(inp.name).stem or "documento"
        files = []
        for k, idx in enumerate(pages):
            out = work / f"{stem}-{idx + 1}.svg"
            run_engine([exe, "-svg", "-f", str(idx + 1), "-l", str(idx + 1), str(local), str(out)], cwd=work, timeout=300, mem_mb=1536)
            if not out.exists():
                raise ToolError(ErrorCode.ENGINE_FAILED, "pdftocairo no generó el SVG")
            files.append((out, out.name))
            ctx.report((n + (k + 1) / len(pages)) / len(ctx.inputs), None)
        if len(files) == 1:
            dst = ctx.output(files[0][1])
            shutil.move(files[0][0], dst)
            outputs.append({"path": str(dst), "name": files[0][1]})
        else:
            name = f"{stem}-svg.zip"
            dst = ctx.output(name)
            zip_files(files, dst)
            outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "pdf-svg.zip")
