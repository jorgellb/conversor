"""metadatos-pdf, eliminar-metadatos-pdf (A.3 y A.6) y preferencias-visor-pdf (A.7) con pikepdf."""
from __future__ import annotations

from datetime import datetime, timezone

import pikepdf
from pikepdf import Name

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.pdf.common import open_pdf, with_batch_zip

LABELS = {"/Title": "Título", "/Author": "Autor", "/Subject": "Asunto", "/Keywords": "Palabras clave", "/Creator": "Creador",
          "/Producer": "Productor", "/CreationDate": "Fecha de creación", "/ModDate": "Fecha de modificación"}
LABELS_EN = {"/Title": "Title", "/Author": "Author", "/Subject": "Subject", "/Keywords": "Keywords", "/Creator": "Creator",
             "/Producer": "Producer", "/CreationDate": "Creation date", "/ModDate": "Modification date"}

# Avisos del resultado en el idioma de la página (D-42, D-54 y D-151).
NOTES = {
    "es": {"removed": "Quitado: {items}.", "none": "No tenía metadatos."},
    "en": {"removed": "Removed: {items}.", "none": "It had no metadata."},
}


def parse_date(value: str) -> datetime:
    text = value.strip().replace(" ", "T")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, f"Fecha no válida: {value}") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def run_edit(ctx: ToolContext) -> list[dict]:
    """Edita Info y XMP a la vez (`open_metadata` mantiene los dos sincronizados). Vacío = sin cambios."""
    o = ctx.options
    xmp_fields = {"dc:title": o.titulo, "dc:description": o.asunto, "pdf:Keywords": o.palabras_clave,
                  "xmp:CreatorTool": o.creador, "pdf:Producer": o.productor}
    dates = {"xmp:CreateDate": o.fecha_creacion, "xmp:ModifyDate": o.fecha_modificacion}
    outputs = []
    for inp in ctx.inputs:
        name = derived_name(inp.name, "", "pdf")
        dst = ctx.output(name)
        with open_pdf(inp.path, None, ctx.plan.pdf_pages) as pdf:
            with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=True) as meta:
                for key, value in xmp_fields.items():
                    if value.strip():
                        meta[key] = value.strip()
                if o.autor.strip():
                    meta["dc:creator"] = [o.autor.strip()]
                for key, value in dates.items():
                    if value.strip():
                        meta[key] = parse_date(value).isoformat()
            pdf.save(dst)
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "pdf-metadatos.zip")


def run_remove(ctx: ToolContext) -> list[dict]:
    """Quita el diccionario Info, el XMP del documento y de las páginas y los datos privados de programas (PieceInfo)."""
    outputs = []
    for inp in ctx.inputs:
        name = derived_name(inp.name, "-sin-metadatos", "pdf")
        dst = ctx.output(name)
        removed: list[str] = []
        labels = LABELS_EN if ctx.locale == "en" else LABELS
        notes = NOTES.get(ctx.locale, NOTES["es"])
        with open_pdf(inp.path, None, ctx.plan.pdf_pages) as pdf:
            info = pdf.trailer.get("/Info")
            if isinstance(info, pikepdf.Dictionary):
                removed += [labels.get(str(k), str(k).lstrip("/")) for k in info.keys()]
                del pdf.trailer["/Info"]
            for holder in [pdf.Root, *[p.obj for p in pdf.pages]]:
                for key in ("/Metadata", "/PieceInfo"):
                    if key in holder:
                        if key == "/Metadata" and "XMP" not in removed:
                            removed.append("XMP")
                        del holder[key]
            pdf.save(dst, fix_metadata_version=False)
        note = notes["removed"].format(items=", ".join(removed)) if removed else notes["none"]
        outputs.append({"path": str(dst), "name": name, "note": note})
    return with_batch_zip(ctx, outputs, "pdf-sin-metadatos.zip")


VIEWER_BOOLS = {"centrar_ventana": "/CenterWindow", "ajustar_ventana": "/FitWindow", "mostrar_titulo": "/DisplayDocTitle",
                "ocultar_menu": "/HideMenubar", "ocultar_barra": "/HideToolbar", "ocultar_controles": "/HideWindowUI"}
VIEWER_NAMES = {"modo_no_pantalla_completa": "/NonFullScreenPageMode", "duplex": "/Duplex", "area_impresion": "/PrintArea",
                "recorte_impresion": "/PrintClip", "area_vista": "/ViewArea", "recorte_vista": "/ViewClip",
                "escalado_impresion": "/PrintScaling", "direccion": "/Direction"}


def run_viewer(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    outputs = []
    for inp in ctx.inputs:
        name = derived_name(inp.name, "", "pdf")
        dst = ctx.output(name)
        with open_pdf(inp.path, None, ctx.plan.pdf_pages) as pdf:
            root = pdf.Root
            if o.quitar_todas:
                for key in ("/ViewerPreferences", "/PageLayout", "/PageMode", "/OpenAction"):
                    if key in root:
                        del root[key]
            if o.diseno != "no_cambiar":
                root.PageLayout = Name("/" + o.diseno)
            if o.modo != "no_cambiar":
                root.PageMode = Name("/" + o.modo)
            if o.pagina_inicial or o.zoom_inicial != "no_cambiar":
                index = min(max(1, o.pagina_inicial or 1), len(pdf.pages)) - 1
                page = pdf.pages[index].obj
                zoom = o.zoom_inicial if o.zoom_inicial != "no_cambiar" else "Fit"
                if zoom == "personalizado":
                    dest = [page, Name.XYZ, None, None, o.zoom_porcentaje / 100]
                elif zoom == "FitH":
                    dest = [page, Name.FitH, None]
                elif zoom == "FitV":
                    dest = [page, Name.FitV, None]
                else:
                    dest = [page, Name.Fit]
                root.OpenAction = pikepdf.Array(dest)
            prefs = root.get("/ViewerPreferences")
            if not isinstance(prefs, pikepdf.Dictionary):
                prefs = pikepdf.Dictionary()
            for field, key in VIEWER_BOOLS.items():
                value = getattr(o, field)
                if value != "no_cambiar":
                    prefs[key] = value == "si"
            for field, key in VIEWER_NAMES.items():
                value = getattr(o, field)
                if value != "no_cambiar":
                    prefs[key] = Name("/" + value)
            if len(prefs):
                root.ViewerPreferences = prefs
            pdf.save(dst)
        outputs.append({"path": str(dst), "name": name})
    return with_batch_zip(ctx, outputs, "pdf-preferencias.zip")
