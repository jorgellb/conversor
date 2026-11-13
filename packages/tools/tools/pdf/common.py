"""Utilidades PDF comunes: apertura con contraseña, límites de páginas y lotes."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pikepdf

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, zip_files


@contextmanager
def open_pdf(path: Path, password: str | None, max_pages: int | None = None):
    try:
        pdf = pikepdf.open(path, password=password or "")
    except pikepdf.PasswordError as exc:
        raise ToolError(ErrorCode.WRONG_PASSWORD if password else ErrorCode.PASSWORD_REQUIRED) from exc
    except pikepdf.PdfError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE) from exc
    try:
        if max_pages is not None and len(pdf.pages) > max_pages:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{len(pdf.pages)} páginas; límite {max_pages}")
        yield pdf
    finally:
        pdf.close()


def with_batch_zip(ctx: ToolContext, outputs: list[dict], zip_name: str) -> list[dict]:
    """Lotes (A.0): un archivo por entrada más un ZIP con todo, si hay más de uno."""
    if len(outputs) > 1:
        zip_path = ctx.output(zip_name)
        zip_files([(Path(o["path"]), o["name"]) for o in outputs], zip_path)
        outputs = outputs + [{"path": str(zip_path), "name": zip_name, "note": "zip"}]
    return outputs
