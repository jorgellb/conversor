"""quitar-fondo (7.11): rembg con el modelo de `REMBG_MODEL` (6.4), ya descargado en la imagen; nunca bria-rmbg.

rembg usa `bria-rmbg` (licencia comercial de pago) si no se le da una sesión: aquí siempre se crea con el modelo
configurado y se comprueba que el archivo está en el disco, porque los workers no tienen salida a internet.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.settings import Settings
from tools.base import ToolContext, derived_name, open_image
from tools.pdf.common import with_batch_zip

ALLOWED_MODELS = ("u2net", "isnet-general-use")
_sessions: dict[str, object] = {}
_lock = threading.Lock()

# El refinado de bordes (matting de pymatting) crece mucho con los píxeles: por encima de esto se hace el recorte normal.
MATTING_MAX_PIXELS = 4_000_000

NOTES = {
    "es": {"jpg_background": "El JPG no admite transparencia: el fondo va en {color}.",
           "matting": "{name}: el refinado de bordes llega hasta 4 MP; se ha hecho el recorte normal."},
    "en": {"jpg_background": "JPG has no transparency: the background is {color}.",
           "matting": "{name}: edge refinement works up to 4 MP; the normal cut-out was used."},
}


def model_path(settings: Settings) -> Path:
    name = settings.REMBG_MODEL.strip()
    if "bria" in name.lower() or name not in ALLOWED_MODELS:
        # 11 y 6.4: bria-rmbg exige un acuerdo de pago para uso comercial; solo se admiten u2net e isnet-general-use.
        raise ToolError(ErrorCode.ENGINE_FAILED, f"Modelo de rembg no admitido: {name}")
    path = Path(settings.REMBG_HOME) / "models" / name / f"{name}.onnx"
    if not path.is_file():
        raise ToolError(ErrorCode.ENGINE_FAILED, f"Falta el modelo {name} en {settings.REMBG_HOME}")
    return path


def session(settings: Settings):
    """Sesión de onnxruntime por proceso con el modelo configurado (cargarlo cuesta segundos)."""
    path = model_path(settings)
    name = settings.REMBG_MODEL.strip()
    with _lock:
        if name not in _sessions:
            os.environ["REMBG_HOME"] = str(settings.REMBG_HOME)
            os.environ.pop("U2NET_HOME", None)
            from rembg import new_session

            created = new_session(name)
            # Comprobación de 16.6: la sesión carga exactamente el archivo del modelo configurado.
            if Path(created.__class__.download_models()).resolve() != path.resolve():
                raise ToolError(ErrorCode.ENGINE_FAILED, "rembg no ha cargado el modelo configurado")
            _sessions[name] = created
        return _sessions[name]


def _hex(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def run(ctx: ToolContext) -> list[dict]:
    from PIL import Image, ImageOps
    from rembg import remove

    o = ctx.options
    sess = session(ctx.settings)
    color = o.color if (o.fondo == "color" or o.formato == "jpg") else None
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        notes = []
        with open_image(inp.path, ctx.settings.IMAGE_MAX_PIXELS) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            matting = o.bordes_finos and img.width * img.height <= MATTING_MAX_PIXELS
            if o.bordes_finos and not matting:
                notes.append(NOTES.get(ctx.locale, NOTES["es"])["matting"].format(name=inp.name))
            cut = remove(img, session=sess, alpha_matting=matting, post_process_mask=True)
        if cut.mode != "RGBA":
            cut = cut.convert("RGBA")
        if o.recortar:
            box = cut.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
            if box:
                pad = max(2, round(max(cut.size) * 0.02))
                box = (max(0, box[0] - pad), max(0, box[1] - pad), min(cut.width, box[2] + pad), min(cut.height, box[3] + pad))
                cut = cut.crop(box)
        if color:
            flat = Image.new("RGBA", cut.size, (*_hex(color), 255))
            flat.alpha_composite(cut)
            cut = flat
        ext = o.formato
        name = derived_name(inp.name, "-sin-fondo", ext)
        dst = ctx.output(name)
        if ext == "jpg":
            cut.convert("RGB").save(dst, format="JPEG", quality=92, optimize=True)
        elif ext == "webp":
            cut.save(dst, format="WEBP", lossless=True)
        else:
            cut.save(dst, format="PNG")
        entry = {"path": str(dst), "name": name}
        if ext == "jpg" and o.fondo != "color":
            notes.append(NOTES.get(ctx.locale, NOTES["es"])["jpg_background"].format(color=o.color))
        if notes:
            entry["note"] = " ".join(notes)
        outputs.append(entry)
    return with_batch_zip(ctx, outputs, "imagenes-sin-fondo.zip")
