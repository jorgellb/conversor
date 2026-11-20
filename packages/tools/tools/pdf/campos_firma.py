"""hacer-pdf-rellenable y crear-formulario-pdf, parte de servidor (A.3, F4-B1): campos de firma con pyHanko.

El navegador crea los demás campos con pdf-lib y manda aquí el PDF con la lista de campos de firma (nombre, página y
rectángulo en el espacio de usuario de la página). pyHanko los añade en una actualización incremental, vacíos y listos
para firmar con firmar-pdf o con cualquier lector (A.3: «compatibles con firmar-pdf»). Corre en `workerpdf`, sin red ni
secretos: no firma nada.
"""
from __future__ import annotations

import io

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name


def _existing(reader) -> set[str]:
    from pyhanko.sign.fields import enumerate_sig_fields

    names = set()
    try:
        form = reader.root["/AcroForm"]
        fields = form.get("/Fields") or []
    except (KeyError, TypeError):
        return names
    for field in fields:
        try:
            name = field.get_object().get("/T")
        except Exception:  # noqa: BLE001 - campo roto
            continue
        if name is not None:
            names.add(str(name))
    names |= {name for name, _value, _ref in enumerate_sig_fields(reader, filled_status=None)}
    return names


def run(ctx: ToolContext) -> list[dict]:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.pdf_utils.misc import PdfError
    from pyhanko.sign.fields import SigFieldSpec, append_signature_field

    campos = ctx.options.firmas
    if not campos:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "no hay campos de firma que añadir")
    inp = ctx.inputs[0]
    try:
        writer = IncrementalPdfFileWriter(io.BytesIO(inp.path.read_bytes()), strict=False)
    except (PdfError, ValueError, KeyError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "pdf") from exc
    if writer.security_handler is not None:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "el PDF del formulario no debe estar cifrado")
    try:
        pages = int(writer.root["/Pages"]["/Count"])
        taken = _existing(writer.prev)
    except Exception as exc:  # noqa: BLE001 - árbol de páginas o AcroForm rotos (12.3)
        raise ToolError(ErrorCode.CORRUPT_FILE, "pdf") from exc
    if pages > ctx.plan.pdf_pages:  # 12.3: el límite de páginas del plan antes de procesar
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"{pages} páginas; límite {ctx.plan.pdf_pages}")
    for campo in campos:
        if campo.pagina > pages:
            raise ToolError(ErrorCode.INVALID_OPTIONS, f"página {campo.pagina} de {pages}")
        if campo.nombre in taken:
            raise ToolError(ErrorCode.INVALID_OPTIONS, f"ya hay un campo llamado {campo.nombre}")
        taken.add(campo.nombre)
        box = tuple(round(v) for v in (min(campo.x1, campo.x2), min(campo.y1, campo.y2), max(campo.x1, campo.x2), max(campo.y1, campo.y2)))
        try:
            append_signature_field(writer, SigFieldSpec(sig_field_name=campo.nombre, on_page=campo.pagina - 1, box=box))
        except (PdfError, ValueError) as exc:
            raise ToolError(ErrorCode.INVALID_OPTIONS, f"campo {campo.nombre}") from exc
        except Exception as exc:  # noqa: BLE001 - AcroForm mal formado (p. ej. /Fields que no es una lista)
            raise ToolError(ErrorCode.CORRUPT_FILE, "pdf") from exc
    ctx.report(0.8, None)
    name = inp.name if inp.name.lower().endswith(".pdf") else derived_name(inp.name, "", "pdf")
    dst = ctx.output(name)
    with dst.open("wb") as fh:
        writer.write(fh)
    for i in ctx.inputs:
        i.path.unlink(missing_ok=True)
    return [{"path": str(dst), "name": name, "note": None}]
