"""imagen-a-texto (7.6): OCR local con Tesseract en `workerocr`, sin IA externa (6.3: 0 peticiones).

Las imágenes se normalizan con Pillow (límite de píxeles, 12.3; páginas de TIFF; sin transparencia), se giran con la
orientación de Tesseract y se enderezan con un perfil de proyección propio, se pasan a PDF con img2pdf y OCRmyPDF
(rasterizador pypdfium2, nunca Ghostscript) reconoce el texto con Tesseract. La salida es TXT, DOCX o PDF con capa de
texto (D-159). Las piezas de lectura de imágenes (`frames`, `straighten`, `tesseract_text`) también las usan
imagen-a-excel y ticket-a-excel en `workerconvert` y `workerocr`.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import InputFile, ToolContext, derived_name, open_image, run_engine
from tools.pdf.common import with_batch_zip

IMAGE_INPUTS = ("jpg", "png", "webp", "tiff", "bmp", "gif")
DEFAULT_DPI = 300
TEXTS = {
    "es": {"empty": "No se ha encontrado texto en {name}.", "joined": "imagenes-texto"},
    "en": {"empty": "No text was found in {name}.", "joined": "images-text"},
}


def texts(ctx: ToolContext) -> dict[str, str]:
    return TEXTS.get(ctx.locale, TEXTS["es"])


def check_languages(ctx: ToolContext, codes: list[str]) -> list[str]:
    """Los idiomas pedidos, si Tesseract los tiene instalados (si no, INVALID_OPTIONS sin llamar al motor)."""
    from tools.ocr.ocr_pdf import installed_languages

    if len(codes) > ctx.settings.OCR_MAX_LANGUAGES:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "Demasiados idiomas")
    missing = [c for c in codes if c not in installed_languages()]
    if missing:
        raise ToolError(ErrorCode.INVALID_OPTIONS, f"Idiomas no instalados: {', '.join(missing)}")
    return list(codes)


def _dpi(img) -> int:
    value = img.info.get("dpi")
    try:
        dpi = round(float(value[0])) if value else 0
    except (TypeError, ValueError, IndexError):
        dpi = 0
    return dpi if 70 <= dpi <= 1200 else DEFAULT_DPI


def frames(ctx: ToolContext, inp: InputFile, n: int, max_frames: int | None = None) -> list[tuple[Path, int]]:
    """Cada página de la imagen (los TIFF pueden tener varias) como PNG o JPEG listo para OCR, con su resolución.

    Comprueba el límite de píxeles antes de descomprimir nada y el de páginas del plan; quita la transparencia sobre
    blanco y aplica la orientación EXIF de las fotos. Un JPEG normal se usa tal cual (img2pdf no lo recomprime).
    """
    from PIL import Image, ImageOps, ImageSequence

    limit = max_frames if max_frames is not None else ctx.plan.pdf_pages
    out: list[tuple[Path, int]] = []
    with open_image(inp.path, ctx.settings.IMAGE_MAX_PIXELS) as img:
        count = getattr(img, "n_frames", 1) if img.format == "TIFF" else 1
        if count > limit:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{count} páginas")
        dpi = _dpi(img)
        orientation = img.getexif().get(0x0112, 1) if img.format == "JPEG" else 1
        if img.format == "JPEG" and img.mode in ("RGB", "L") and orientation == 1:
            dst = ctx.work / f"img-{n}-0.jpg"
            shutil.copyfile(inp.path, dst)
            return [(dst, dpi)]
        sequence = ImageSequence.Iterator(img) if count > 1 else [img]
        for k, frame in enumerate(sequence):
            if frame.width * frame.height > ctx.settings.IMAGE_MAX_PIXELS:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Imagen demasiado grande")
            try:
                page = ImageOps.exif_transpose(frame) if orientation != 1 else frame.copy()
                if page.mode in ("RGBA", "LA", "P", "PA") or "transparency" in page.info:
                    rgba = page.convert("RGBA")
                    page = Image.new("RGB", rgba.size, "white")
                    page.paste(rgba, mask=rgba.getchannel("A"))
                elif page.mode not in ("RGB", "L", "1"):
                    page = page.convert("RGB")
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                raise ToolError(ErrorCode.CORRUPT_FILE, "Imagen no válida") from exc
            dst = ctx.work / f"img-{n}-{k}.png"
            page.save(dst, format="PNG", dpi=(dpi, dpi))
            out.append((dst, dpi))
    return out


def tesseract_text(ctx: ToolContext, image: Path, languages: list[str], psm: int = 6) -> str:
    """Texto de una imagen con Tesseract por línea de comandos (entorno vacío y límites), conservando los espacios entre
    columnas: así un ticket o una tabla sin rejilla siguen alineados para leerlos después."""
    exe = shutil.which("tesseract") or "tesseract"
    result = run_engine([exe, str(image), "stdout", "-l", "+".join(languages), "--psm", str(psm),
                         "-c", "preserve_interword_spaces=1"], cwd=ctx.work, timeout=600, mem_mb=2048,
                        extra_env={"OMP_THREAD_LIMIT": "1"})
    return result.stdout.decode("utf-8", errors="replace").replace("\f", "").strip()


MAX_SKEW = 15.0  # grados que se buscan a cada lado


def skew_angle(img) -> float:
    """Ángulo (en grados, sentido antihorario de Pillow) que pone horizontales las líneas de texto.

    Perfil de proyección: con la imagen reducida y binarizada, el giro bueno es el que hace más distinta la tinta de
    cada fila (filas de texto y filas en blanco). Primero de medio en medio grado y luego de décima en décima. El
    `--deskew` de OCRmyPDF 17 usa el ángulo de Tesseract, que en imágenes limpias sale 0 aunque estén torcidas (D-159).
    """
    from PIL import Image, ImageOps

    gray = img.convert("L")
    scale = 1000 / max(gray.size)
    if scale < 1:
        gray = gray.resize((max(1, int(gray.width * scale)), max(1, int(gray.height * scale))))
    ink = ImageOps.invert(gray).point(lambda v: 255 if v > 96 else 0)

    def score(angle: float) -> float:
        turned = ink.rotate(angle, resample=Image.BILINEAR, fillcolor=0)
        rows = turned.resize((1, turned.height), Image.BOX).tobytes()
        mean = sum(rows) / len(rows)
        return sum((v - mean) ** 2 for v in rows)

    steps = int(MAX_SKEW * 2)
    _, coarse = max((score(a / 2), a / 2) for a in range(-steps, steps + 1))
    _, fine = max((score(coarse + d / 10), coarse + d / 10) for d in range(-5, 6))
    return round(fine, 1)


def straighten(ctx: ToolContext, page: tuple[Path, int], rotate: bool, deskew: bool) -> tuple[Path, int]:
    """Gira la página que está de lado o del revés (orientación de Tesseract, `--psm 0`) y la endereza."""
    from PIL import Image

    path, dpi = page
    turn = osd_rotation(ctx, path) if rotate else 0
    with Image.open(path) as img:
        img.load()
        work = img.rotate(-turn, expand=True) if turn else img
        angle = skew_angle(work) if deskew else 0.0
        if not turn and abs(angle) < 0.2:
            return page
        fill = 255 if work.mode in ("L", "1") else (255, 255, 255)
        if abs(angle) >= 0.2:
            work = work.convert("L" if work.mode == "1" else work.mode).rotate(angle, resample=Image.BICUBIC, expand=True,
                                                                                fillcolor=fill)
        dst = path.with_name(f"{path.stem}-recta.png")
        work.save(dst, format="PNG", dpi=(dpi, dpi))
    return dst, dpi


def osd_rotation(ctx: ToolContext, image: Path) -> int:
    """Grados (0, 90, 180 o 270, en sentido horario) que hay que girar la imagen según Tesseract; 0 si no está seguro."""
    import re

    exe = shutil.which("tesseract") or "tesseract"
    try:
        result = run_engine([exe, str(image), "stdout", "--psm", "0"], cwd=ctx.work, timeout=120, mem_mb=1024,
                            extra_env={"OMP_THREAD_LIMIT": "1"}, ok_codes=(0, 1))
    except ToolError:
        return 0
    out = result.stdout.decode("utf-8", errors="replace")
    rotate = re.search(r"Rotate:\s*(\d+)", out)
    confidence = re.search(r"Orientation confidence:\s*([\d.]+)", out)
    if not rotate or not confidence or float(confidence.group(1)) < 2.0:
        return 0
    return int(rotate.group(1)) % 360


def _ocr(ctx: ToolContext, pages: list[tuple[Path, int]], k: int, pdf: bool) -> tuple[list[str], Path | None]:
    """OCRmyPDF sobre las páginas: texto de cada una y, si se pide, el PDF con capa de texto."""
    import img2pdf
    import ocrmypdf
    from ocrmypdf import exceptions as ocr_exc

    o = ctx.options
    src = ctx.work / f"entrada-{k}.pdf"
    layouts = [img2pdf.convert(str(p), layout_fun=img2pdf.get_fixed_dpi_layout_fun((dpi, dpi))) for p, dpi in pages]
    if len(layouts) == 1:
        src.write_bytes(layouts[0])
    else:
        import pikepdf

        merged = pikepdf.Pdf.new()
        parts = []
        for i, data in enumerate(layouts):
            part = ctx.work / f"parte-{k}-{i}.pdf"
            part.write_bytes(data)
            parts.append(pikepdf.open(part))
            merged.pages.extend(parts[-1].pages)
        merged.save(src)
        for part in parts:
            part.close()
    sidecar = ctx.work / f"texto-{k}.txt"
    dst = ctx.work / f"salida-{k}.pdf" if pdf else None
    try:
        ocrmypdf.ocr(str(src), str(dst) if dst else "-", language=o.idiomas, mode="force", output_type="pdf" if pdf else "none", sidecar=str(sidecar), rasterizer="pypdfium",
                     pdfa_backend="internal", jobs=max(1, ctx.threads), progress_bar=False,
                     max_image_mpixels=ctx.settings.IMAGE_MAX_PIXELS / 1_000_000)
    except ocr_exc.ExitCodeException as exc:
        raise ToolError(ErrorCode.ENGINE_FAILED, type(exc).__name__) from exc
    chunks = sidecar.read_text(encoding="utf-8", errors="replace").split("\f")
    # OCRmyPDF marca así las páginas en las que no ha encontrado nada.
    clean = [("" if c.strip() == "[OCR skipped on page(s) 1]" else c.strip()) for c in chunks]
    return (clean + [""] * len(pages))[: len(pages)], dst


def _docx(dst: Path, pages: list[str], title: str, language: str) -> None:
    from docx import Document
    from docx.enum.text import WD_BREAK

    from tools.ai.salida import set_language

    doc = Document()
    doc.core_properties.title = title
    doc.core_properties.author = ""
    set_language(doc, language)
    for i, text in enumerate(pages):
        if i:
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        for block in text.split("\n\n"):
            if block.strip():
                doc.add_paragraph(" ".join(line.strip() for line in block.splitlines() if line.strip()))
    doc.save(str(dst))


WORD_LANG = {"spa": "es-ES", "eng": "en-GB", "fra": "fr-FR", "deu": "de-DE", "ita": "it-IT", "por": "pt-PT", "cat": "ca-ES",
             "glg": "gl-ES", "eus": "eu-ES"}


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    t = texts(ctx)
    check_languages(ctx, o.idiomas)
    groups: list[tuple[str, list[tuple[Path, int]]]] = []
    total = 0
    for n, inp in enumerate(ctx.inputs):
        pages = frames(ctx, inp, n)
        total += len(pages)
        if total > ctx.plan.pdf_pages:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{total} páginas")
        groups.append((inp.name, pages))
    if o.unir and len(groups) > 1:
        groups = [(f"{t['joined']}.png", [p for _, pages in groups for p in pages])]
    ext = {"txt": "txt", "docx": "docx", "pdf": "pdf"}[o.salida]
    outputs = []
    for k, (name, pages) in enumerate(groups):
        ctx.report(k / len(groups), None)
        if o.enderezar or o.autorrotar:
            pages = [straighten(ctx, page, o.autorrotar, o.enderezar) for page in pages]
        found, pdf = _ocr(ctx, pages, k, o.salida == "pdf")
        note = None if any(found) else t["empty"].format(name=name)
        out_name = derived_name(name, "-ocr" if o.salida == "pdf" else "", ext)
        dst = ctx.output(out_name)
        if o.salida == "txt":
            dst.write_text("\n\f\n".join(found).strip() + "\n", encoding="utf-8")
        elif o.salida == "docx":
            _docx(dst, found, Path(name).stem, WORD_LANG.get(o.idiomas[0], "es-ES"))
        else:
            shutil.copyfile(pdf, dst)
        outputs.append({"path": str(dst), "name": out_name, "note": note})
    return with_batch_zip(ctx, outputs, "imagenes-texto.zip")
