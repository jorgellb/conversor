"""heic-a-pdf (A.8), cbz-a-pdf, cbr-a-pdf y djvu-a-pdf (7.3) en `workermedia`."""
from __future__ import annotations

import dataclasses
import re
import shutil
from pathlib import Path

import img2pdf
import libarchive
import pikepdf

from core.errors import ErrorCode, ToolError
from core.zipguard import MAX_MEMBERS, MAX_UNCOMPRESSED
from tools.base import InputFile, ToolContext, derived_name, open_image, run_engine, sha256_file
from tools.pdf.common import with_batch_zip

COMIC_IMAGES = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff"}
PAPERS_MM = {"A4": (210, 297), "A5": (148, 210), "Letter": (215.9, 279.4)}


def _natural(name: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


# --- heic-a-pdf ---------------------------------------------------------------------------------------------------


def _heif_decoder() -> str:
    for name in ("heif-dec", "heif-convert"):
        path = shutil.which(name)
        if path:
            return path
    raise ToolError(ErrorCode.ENGINE_FAILED, "Falta el decodificador de libheif")


def run_heic(ctx: ToolContext) -> list[dict]:
    """Decodifica con libheif (solo decodificación, sin x265; D-49) y monta el PDF como imagenes-a-pdf."""
    from tools.pdf.imagenes_a_pdf import run as images_run

    decoder = _heif_decoder()
    pngs: list[InputFile] = []
    for n, inp in enumerate(ctx.inputs):
        out_dir = ctx.work / f"heic-{n}"
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{Path(inp.name).stem}.png"
        run_engine([decoder, str(inp.path), str(target)], cwd=out_dir, timeout=120, mem_mb=1536)
        produced = sorted(out_dir.glob("*.png"), key=lambda p: _natural(p.name))
        if not produced:
            raise ToolError(ErrorCode.CORRUPT_FILE, inp.name)
        for k, png in enumerate(produced):
            name = f"{Path(inp.name).stem}.png" if len(produced) == 1 else f"{Path(inp.name).stem}-{k + 1}.png"
            pngs.append(InputFile(png, name, "png", png.stat().st_size, sha256_file(png)))
    return images_run(dataclasses.replace(ctx, inputs=pngs))


# --- cbz-a-pdf y cbr-a-pdf ----------------------------------------------------------------------------------------


def comic_pages(path: Path, work: Path) -> list[Path]:
    """Imágenes del cómic en orden natural, con los límites de bombas de compresión (12.3)."""
    entries: list[tuple[str, Path]] = []
    total = 0
    count = 0
    try:
        with libarchive.file_reader(str(path)) as archive:
            for entry in archive:
                count += 1
                if count > MAX_MEMBERS:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Demasiadas entradas")
                name = entry.pathname.replace("\\", "/")
                parts = [p for p in name.split("/") if p]
                if entry.isdir or not parts or ".." in parts or parts[0] == "__MACOSX" or parts[-1].startswith("."):
                    continue
                if parts[-1].rsplit(".", 1)[-1].lower() not in COMIC_IMAGES:
                    continue
                dst = work / f"pagina-{len(entries):05d}.{parts[-1].rsplit('.', 1)[-1].lower()}"
                with open(dst, "wb") as f:
                    for block in entry.get_blocks():
                        total += len(block)
                        if total > MAX_UNCOMPRESSED:
                            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Archivo descomprimido demasiado grande")
                        f.write(block)
                entries.append((name, dst))
    except libarchive.ArchiveError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "Archivo de cómic ilegible") from exc
    if not entries:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "El cómic no tiene imágenes")
    entries.sort(key=lambda e: _natural(e[0]))
    return [p for _, p in entries]


def run_comic(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        work = ctx.work / f"comic-{n}"
        work.mkdir(parents=True, exist_ok=True)
        blobs = []
        for page in comic_pages(inp.path, work):
            ext = page.suffix.lstrip(".")
            with open_image(page, ctx.settings.IMAGE_MAX_PIXELS) as img:
                if ext in ("jpg", "jpeg", "png", "gif", "tif", "tiff"):
                    blobs.append(page.read_bytes())
                else:
                    conv = page.with_suffix(".png")
                    img.convert("RGB").save(conv, format="PNG")
                    blobs.append(conv.read_bytes())
        if len(blobs) > ctx.plan.pdf_pages:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{len(blobs)} páginas")
        if o.tamano == "segun_imagen":
            layout = None
        else:
            w, h = PAPERS_MM[o.tamano]
            layout = img2pdf.get_layout_fun(pagesize=(img2pdf.mm_to_pt(w), img2pdf.mm_to_pt(h)), fit=img2pdf.FitMode.into, auto_orient=True)
        name = derived_name(inp.name, "", "pdf")
        dst = ctx.output(name)
        dst.write_bytes(img2pdf.convert(blobs, layout_fun=layout) if layout else img2pdf.convert(blobs))
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "comics-pdf.zip")


# --- djvu-a-pdf ---------------------------------------------------------------------------------------------------


def run_djvu(ctx: ToolContext) -> list[dict]:
    """ddjvu como subproceso con entorno vacío y límites (12.1)."""
    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        name = derived_name(inp.name, "", "pdf")
        dst = ctx.output(name)
        tmp = ctx.work / f"djvu-{n}.pdf"
        args = ["ddjvu", "-format=pdf", f"-quality={o.calidad}"]
        if o.modo != "color":
            args.append(f"-mode={o.modo}")
        run_engine([*args, str(inp.path), str(tmp)], cwd=ctx.work, timeout=600, mem_mb=2048)
        with pikepdf.open(tmp) as pdf:
            if len(pdf.pages) > ctx.plan.pdf_pages:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{len(pdf.pages)} páginas")
            pdf.save(dst)
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "djvu-pdf.zip")
