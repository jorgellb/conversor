"""ocr-pdf (A.5): OCRmyPDF 17 con rasterizador pypdfium2 y `--pdfa-backend internal` (nunca Ghostscript)."""
from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import pikepdf

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.pdf.common import open_pdf, with_batch_zip


@lru_cache
def installed_languages() -> set[str]:
    exe = shutil.which("tesseract")
    if not exe:
        return set()
    out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=30, env={"PATH": "/usr/bin:/bin"}).stdout
    return {line.strip() for line in out.splitlines()[1:] if line.strip()}


def _merge(inputs: list[Path], dst: Path, max_pages: int) -> None:
    merged = pikepdf.Pdf.new()
    for p in inputs:
        with open_pdf(p, None, max_pages) as src:
            merged.pages.extend(src.pages)
    if len(merged.pages) > max_pages:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED)
    merged.save(dst)


def _ocr_one(ctx: ToolContext, src: Path, dst: Path, sidecar: Path | None, force: bool) -> None:
    import ocrmypdf
    from ocrmypdf import exceptions as ocr_exc

    o = ctx.options
    kwargs = dict(
        language=o.idiomas,
        deskew=o.enderezar,
        rotate_pages=o.autorrotar,
        remove_background=o.quitar_fondo,
        clean=o.limpiar,
        mode="force" if (force or o.texto_existente == "forzar") else "skip",
        output_type="pdfa-2" if o.salida == "pdfa" else "pdf",
        pdfa_backend="internal",
        rasterizer="pypdfium",
        jobs=max(1, ctx.threads),
        progress_bar=False,
        max_image_mpixels=ctx.settings.IMAGE_MAX_PIXELS / 1_000_000,
    )
    for key, value in (("title", o.titulo), ("author", o.autor), ("subject", o.asunto), ("keywords", o.palabras_clave)):
        if value:
            kwargs[key] = value
    if sidecar is not None:
        kwargs["sidecar"] = str(sidecar)
    try:
        ocrmypdf.ocr(str(src), str(dst), **kwargs)
    except ocr_exc.EncryptedPdfError as exc:
        raise ToolError(ErrorCode.PASSWORD_REQUIRED) from exc
    except ocr_exc.InputFileError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE) from exc
    except ocr_exc.ExitCodeException as exc:
        if getattr(exc, "exit_code", None) == 10 or "pdf/a" in str(exc).lower():
            raise ToolError(ErrorCode.PDFA_NEEDS_GHOSTSCRIPT) from exc
        raise ToolError(ErrorCode.ENGINE_FAILED, type(exc).__name__) from exc


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    available = installed_languages()
    missing = [code for code in o.idiomas if code not in available]
    if missing:
        raise ToolError(ErrorCode.INVALID_OPTIONS, f"Idiomas no instalados: {', '.join(missing)}")
    if len(o.idiomas) > ctx.settings.OCR_MAX_LANGUAGES:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "Demasiados idiomas")
    sources: list[tuple[Path, str]] = [(i.path, i.name) for i in ctx.inputs]
    if o.unir and len(sources) > 1:
        merged = ctx.work / "unidos.pdf"
        _merge([p for p, _ in sources], merged, ctx.plan.pdf_pages)
        sources = [(merged, "documentos-unidos.pdf")]
    outputs = []
    for n, (src, name) in enumerate(sources):
        ctx.report(n / len(sources), None)
        with open_pdf(src, None, ctx.plan.pdf_pages):
            pass
        pdf_out = ctx.work / f"ocr-{n}.pdf"
        sidecar = ctx.work / f"ocr-{n}.txt" if o.salida == "txt" else None
        try:
            _ocr_one(ctx, src, pdf_out, sidecar, force=False)
        except ToolError as err:
            if err.code == ErrorCode.PDFA_NEEDS_GHOSTSCRIPT and o.rasterizar_si_falla_pdfa:
                _ocr_one(ctx, src, pdf_out, sidecar, force=True)
            else:
                raise
        if o.salida == "txt":
            final = ctx.output(derived_name(name, "", "txt"))
            shutil.copyfile(sidecar, final)
            outputs.append({"path": str(final), "name": derived_name(name, "", "txt")})
        else:
            final = ctx.output(derived_name(name, "-ocr", "pdf"))
            shutil.copyfile(pdf_out, final)
            outputs.append({"path": str(final), "name": derived_name(name, "-ocr", "pdf")})
    return with_batch_zip(ctx, outputs, "ocr.zip")
