"""Revelado de un RAW con LibRaw (rawpy) en un proceso aparte, con límites de memoria y tiempo (12.1 y 12.3).

LibRaw es código C que lee archivos de terceros: si falla, solo cae este proceso. Uso:
    python -I raw_runner.py ENTRADA SALIDA.png OPCIONES_JSON
"""
import json
import sys

import numpy as np
import rawpy
from PIL import Image


def main() -> int:
    src, dst, raw_options = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
    try:
        raw = rawpy.imread(src)
    except (rawpy.LibRawError, OSError) as exc:  # archivo que LibRaw no reconoce o dañado
        print(f"LIBRAW:{type(exc).__name__}", file=sys.stderr)
        return 3
    with raw:
        w, h = raw.sizes.width, raw.sizes.height
        if w * h > int(raw_options.get("max_pixels", 100_000_000)):
            print("LIMIT", file=sys.stderr)
            return 4
        rgb = raw.postprocess(
            use_camera_wb=raw_options.get("balance") == "camara",
            use_auto_wb=raw_options.get("balance") == "automatico",
            no_auto_bright=not raw_options.get("brillo_automatico", True),
            half_size=raw_options.get("tamano") == "mitad",
            output_bps=8,
        )
    Image.fromarray(np.ascontiguousarray(rgb)).save(dst, format="PNG", compress_level=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
