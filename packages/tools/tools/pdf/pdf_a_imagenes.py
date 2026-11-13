"""Parte de servidor de pdf-a-jpg, pdf-a-png, pdf-a-webp y pdf-a-imagenes (A.9): pypdfium2 y Pillow."""
from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from core.errors import ErrorCode, ToolError
from core.options import parse_page_ranges
from tools.base import ToolContext, zip_files

FORCED = {"pdf-a-jpg": "jpg", "pdf-a-png": "png", "pdf-a-webp": "webp"}


def _scale_for(page, dpi: int, max_pixels: int) -> float:
    w, h = page.get_size()
    scale = dpi / 72
    pixels = (w * scale) * (h * scale)
    if pixels > max_pixels:
        scale *= (max_pixels / pixels) ** 0.5
    return scale


def _convert(img: Image.Image, color: str, fmt: str, profile: str) -> tuple[Image.Image, bytes | None]:
    if color == "gris":
        return img.convert("L"), None
    if color == "bn" and fmt == "png":
        return img.convert("L").point(lambda v: 255 if v > 160 else 0, mode="1"), None
    if color == "cmyk" and fmt == "jpg":
        from tools.pdf.desde_pdf import to_cmyk

        return to_cmyk(img, profile)  # A.9: CMYK de 32 bits con perfil ICC (LittleCMS)
    return img.convert("RGB"), None


def _save(img: Image.Image, path: Path, fmt: str, quality: int, icc: bytes | None = None) -> None:
    if fmt == "jpg":
        img.save(path, format="JPEG", quality=quality, optimize=True, **({"icc_profile": icc} if icc else {}))
    elif fmt == "webp":
        img.save(path, format="WEBP", quality=quality, method=4)
    else:
        img.save(path, format="PNG", optimize=True)


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    fmt = FORCED.get(ctx.tool, o.formato)
    files: list[tuple[Path, str]] = []
    total_inputs = len(ctx.inputs)
    for n, inp in enumerate(ctx.inputs):
        try:
            doc = pdfium.PdfDocument(str(inp.path), password=ctx.secrets.get("contrasena"))
        except pdfium.PdfiumError as exc:
            raise ToolError(ErrorCode.PASSWORD_REQUIRED if "password" in str(exc).lower() else ErrorCode.CORRUPT_FILE) from exc
        try:
            if len(doc) > ctx.plan.pdf_pages:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED)
            try:
                pages = parse_page_ranges(o.paginas, len(doc))
            except ValueError as exc:
                raise ToolError(ErrorCode.INVALID_OPTIONS, str(exc)) from exc
            stem = Path(inp.name).stem or "documento"
            rendered: list[Image.Image] = []
            for k, idx in enumerate(pages):
                page = doc[idx]
                bitmap = page.render(scale=_scale_for(page, o.dpi, ctx.settings.RENDER_MAX_PIXELS))
                img, icc = _convert(bitmap.to_pil(), o.color, fmt, ctx.settings.CMYK_ICC_PROFILE)
                if o.salida == "una_sola":
                    rendered.append(img)
                else:
                    path = ctx.work / f"{n:03d}-{idx + 1:05d}.{fmt}"
                    _save(img, path, fmt, o.calidad, icc)
                    arc = f"{stem}/{stem}-{idx + 1}.{fmt}" if o.organizacion == "carpeta_por_archivo" and total_inputs > 1 else f"{stem}-{idx + 1}.{fmt}"
                    files.append((path, arc))
                ctx.report((n + (k + 1) / len(pages)) / total_inputs, None)
            if rendered:
                width = max(i.width for i in rendered)
                height = sum(i.height for i in rendered)
                if width * height > ctx.settings.RENDER_MAX_PIXELS * 2:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, "La imagen única sería demasiado grande")
                mode = rendered[0].mode if rendered[0].mode != "1" else "L"
                sheet = Image.new(mode, (width, height), (0, 0, 0, 0) if mode == "CMYK" else "white")
                y = 0
                for img in rendered:
                    sheet.paste(img, (0, y))
                    y += img.height
                path = ctx.work / f"{n:03d}-todas.{fmt}"
                _save(sheet, path, fmt, o.calidad, icc)
                files.append((path, f"{stem}.{fmt}"))
        finally:
            doc.close()
    if len(files) == 1:
        path, arc = files[0]
        dst = ctx.output(Path(arc).name)
        path.replace(dst)
        return [{"path": str(dst), "name": Path(arc).name}]
    zip_name = f"{Path(ctx.inputs[0].name).stem or 'imagenes'}-{fmt}.zip" if total_inputs == 1 else f"imagenes-{fmt}.zip"
    zip_path = ctx.output(zip_name)
    zip_files(files, zip_path)
    return [{"path": str(zip_path), "name": zip_name}]
