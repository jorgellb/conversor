"""png-a-svg y jpg-a-svg (7.11): vectorizar con vtracer (Rust, MIT) en `workermedia`."""
from __future__ import annotations

import io

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name, open_image
from tools.pdf.common import with_batch_zip

# Lado mayor con el que se vectoriza: más píxeles solo dan más trazados (y archivos enormes) sin ganar forma.
MAX_SIDE = 2000

DETAIL = {
    # filter_speckle (motas que se ignoran, px), color_precision (bits por canal), layer_difference (separación de capas)
    "alto": (2, 8, 8),
    "medio": (4, 6, 16),
    "bajo": (10, 5, 32),
}
MODE = {"curvas": "spline", "poligonos": "polygon", "pixeles": "none"}
NOTES = {
    "es": "{name}: se ha reducido a {w}×{h} px para vectorizarla.",
    "en": "{name}: it was scaled down to {w}×{h} px for tracing.",
}


def run(ctx: ToolContext) -> list[dict]:
    import vtracer
    from PIL import Image

    o = ctx.options
    speckle, precision, difference = DETAIL[o.detalle]
    outputs, notes = [], []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        with open_image(inp.path, ctx.settings.IMAGE_MAX_PIXELS) as img:
            from PIL import ImageOps

            img = ImageOps.exif_transpose(img)
            img = img.convert("RGBA")
            if max(img.size) > MAX_SIDE:
                scale = MAX_SIDE / max(img.size)
                img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.Resampling.LANCZOS)
                notes.append(NOTES.get(ctx.locale, NOTES["es"]).format(name=inp.name, w=img.width, h=img.height))
            if o.colores == "blanco_y_negro":
                # Umbral sobre la luminancia; lo transparente cuenta como fondo blanco.
                flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
                flat.alpha_composite(img)
                img = flat.convert("L").point(lambda v: 255 if v >= 128 else 0).convert("RGBA")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
        try:
            svg = vtracer.convert_raw_image_to_svg(
                buf.getvalue(), img_format="png", colormode="binary" if o.colores == "blanco_y_negro" else "color",
                hierarchical="stacked", mode=MODE[o.trazado], filter_speckle=speckle, color_precision=precision,
                layer_difference=difference, corner_threshold=60, length_threshold=4.0, max_iterations=10, splice_threshold=45,
                path_precision=2)
        except Exception as exc:  # noqa: BLE001 — vtracer devuelve errores como excepciones genéricas
            raise ToolError(ErrorCode.ENGINE_FAILED, "vtracer") from exc
        name = derived_name(inp.name, "", "svg")
        dst = ctx.output(name)
        dst.write_text(svg, encoding="utf-8")
        outputs.append({"path": str(dst), "name": name})
    if notes and outputs:
        outputs[0]["note"] = " ".join(notes)
    return with_batch_zip(ctx, outputs, "imagenes-svg.zip")
