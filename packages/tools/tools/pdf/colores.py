"""Reescritura de colores en los flujos de contenido (pdf-escala-de-grises y pdf-modo-oscuro, A.5).

Cambia los operadores de color (`g`, `rg`, `k`, `sc`, `scn` y sus versiones de trazo) de páginas, formularios XObject,
patrones de mosaico y apariencias de anotaciones, además de degradados con funciones exponenciales o por tramos. El
texto y los vectores siguen siendo vectoriales. Lo que no se sabe convertir con seguridad (sombreados por función o de
malla, espacios Separation, DeviceN, Indexed o Lab en operadores, imágenes en línea al pasar a gris…) marca la página
como «insegura» para que la herramienta decida (rasterizarla o dejarla igual y avisar).
"""
from __future__ import annotations

import colorsys
import io
import re
import zlib
from collections.abc import Callable

import pikepdf
from pikepdf import Name, Operator
from PIL import Image, ImageOps

RGB = tuple[float, float, float]
DEVICE = {"/DeviceGray": "gray", "/G": "gray", "/DeviceRGB": "rgb", "/RGB": "rgb", "/DeviceCMYK": "cmyk", "/CMYK": "cmyk"}
OPS_FILL = {"g": "gray", "rg": "rgb", "k": "cmyk"}
OPS_STROKE = {"G": "gray", "RG": "rgb", "K": "cmyk"}


def luminance(r: float, g: float, b: float) -> float:
    return 0.299 * r + 0.587 * g + 0.114 * b


def cmyk_to_rgb(c: float, m: float, y: float, k: float) -> RGB:
    return (1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)


def rgb_to_cmyk(r: float, g: float, b: float) -> tuple[float, float, float, float]:
    k = 1 - max(r, g, b)
    if k >= 1:
        return 0.0, 0.0, 0.0, 1.0
    return (1 - r - k) / (1 - k), (1 - g - k) / (1 - k), (1 - b - k) / (1 - k), k


def to_gray(rgb: RGB) -> RGB:
    y = luminance(*rgb)
    return y, y, y


def dark_keep_hue(rgb: RGB) -> RGB:
    """Invierte la luminosidad y conserva el tono y la saturación (texto negro → blanco, rojo sigue siendo rojo)."""
    h, l, s = colorsys.rgb_to_hls(*rgb)
    return colorsys.hls_to_rgb(h, 1 - l, s)


def negative(rgb: RGB) -> RGB:
    return 1 - rgb[0], 1 - rgb[1], 1 - rgb[2]


def _clamp(v: float) -> float:
    return round(min(1.0, max(0.0, v)), 4)


def space_kind(cs, resources: pikepdf.Dictionary | None, depth: int = 0) -> str:
    """«gray», «rgb», «cmyk», «pattern» u «other» para un espacio de color (nombre o arreglo)."""
    if depth > 4 or cs is None:
        return "other"
    if isinstance(cs, Name):
        name = str(cs)
        if name in DEVICE:
            return DEVICE[name]
        if name == "/Pattern":
            return "pattern"
        spaces = resources.get("/ColorSpace") if isinstance(resources, pikepdf.Dictionary) else None
        if isinstance(spaces, pikepdf.Dictionary) and name in spaces:
            return space_kind(spaces[name], resources, depth + 1)
        return "other"
    if isinstance(cs, pikepdf.Array) and len(cs):
        family = str(cs[0])
        if family == "/ICCBased":
            n = int(cs[1].get("/N", 0)) if isinstance(cs[1], pikepdf.Stream) else 0
            return {1: "gray", 3: "rgb", 4: "cmyk"}.get(n, "other")
        if family == "/CalGray":
            return "gray"
        if family == "/CalRGB":
            return "rgb"
        if family == "/Pattern":
            return "pattern"
        if family in DEVICE:
            return DEVICE[family]
    return "other"


class Rewriter:
    """Aplica `fn` (sobre RGB 0-1) a todos los colores que sabe convertir. `images`: «gris», «invertir» o «igual»."""

    def __init__(self, pdf: pikepdf.Pdf, fn: Callable[[RGB], RGB], images: str, inline_images_safe: bool):
        self.pdf = pdf
        self.fn = fn
        self.images = images
        self.inline_images_safe = inline_images_safe
        self.done: set[tuple[int, int]] = set()
        self.reasons: list[str] = []

    # --- valores de color ------------------------------------------------------------------------------------
    def convert(self, kind: str, values: list[float]) -> list[float]:
        if kind == "gray" and len(values) == 1:
            return [_clamp(luminance(*self.fn((values[0],) * 3)))]
        if kind == "rgb" and len(values) == 3:
            return [_clamp(v) for v in self.fn((values[0], values[1], values[2]))]
        if kind == "cmyk" and len(values) == 4:
            return [_clamp(v) for v in rgb_to_cmyk(*self.fn(cmyk_to_rgb(*values)))]
        raise ValueError(kind)

    def convert_array(self, arr) -> pikepdf.Array | None:
        try:
            values = [float(v) for v in arr]
        except (TypeError, ValueError):
            return None
        kind = {1: "gray", 3: "rgb", 4: "cmyk"}.get(len(values))
        return pikepdf.Array(self.convert(kind, values)) if kind else None

    def convert_da(self, da: str) -> str:
        """Colores de las cadenas /DA de formularios («0 0 1 rg /Helv 12 Tf»)."""
        def sub(m: re.Match, kind: str) -> str:
            vals = [float(x) for x in m.group(1).split()]
            return " ".join(f"{v:g}" for v in self.convert(kind, vals)) + m.group(2)
        n = r"-?\d*\.?\d+"
        da = re.sub(rf"((?:{n}\s+){{3}}{n})(\s+k\b)", lambda m: sub(m, "cmyk"), da)
        da = re.sub(rf"((?:{n}\s+){{2}}{n})(\s+rg\b)", lambda m: sub(m, "rgb"), da)
        return re.sub(rf"(?<![\d.])({n})(\s+g\b)", lambda m: sub(m, "gray"), da)

    # --- objetos ---------------------------------------------------------------------------------------------
    def _first(self, obj) -> bool:
        key = obj.objgen
        if key != (0, 0) and key in self.done:
            return False
        if key != (0, 0):
            self.done.add(key)
        return True

    def function(self, f, kind: str) -> bool:
        if isinstance(f, pikepdf.Array):
            return False  # una función por componente: no se puede convertir el color como un todo
        if not isinstance(f, (pikepdf.Dictionary, pikepdf.Stream)):
            return False
        ftype = int(f.get("/FunctionType", -1))
        if ftype == 2:
            if not self._first(f):
                return True
            n = {"gray": 1, "rgb": 3, "cmyk": 4}[kind]
            c0 = [float(v) for v in f.get("/C0", [0.0] * n)]
            c1 = [float(v) for v in f.get("/C1", [1.0] * n)]
            if len(c0) != n or len(c1) != n:
                return False
            f.C0 = pikepdf.Array(self.convert(kind, c0))
            f.C1 = pikepdf.Array(self.convert(kind, c1))
            return True
        if ftype == 3:
            return all(self.function(sub, kind) for sub in f.get("/Functions", []))
        return False

    def shading(self, sh, resources) -> bool:
        if not isinstance(sh, (pikepdf.Dictionary, pikepdf.Stream)):
            return False
        if int(sh.get("/ShadingType", 0)) not in (2, 3):
            self.reasons.append("sombreado por función o de malla")
            return False
        kind = space_kind(sh.get("/ColorSpace"), resources)
        if kind not in ("gray", "rgb", "cmyk") or not self.function(sh.get("/Function"), kind):
            self.reasons.append("sombreado con un espacio o una función no convertibles")
            return False
        if "/Background" in sh:
            bg = self.convert_array(sh.Background)
            if bg is not None:
                sh.Background = bg
        return True

    def image(self, xobj: pikepdf.Stream) -> bool:
        if self.images == "igual" or xobj.get("/ImageMask") or not self._first(xobj):
            return True
        try:
            pil = pikepdf.PdfImage(xobj).as_pil_image()
        except Exception:  # noqa: BLE001 - JBIG2, JPX sin códec, espacios exóticos
            self.reasons.append("imagen que no se puede decodificar")
            return False
        if self.images == "gris":
            out = pil.convert("L")
        else:
            out = ImageOps.invert(pil.convert("L" if pil.mode in ("1", "L", "LA", "I", "I;16") else "RGB"))
        jpeg = xobj.get("/Filter") == Name.DCTDecode
        if jpeg:
            buf = io.BytesIO()
            out.save(buf, format="JPEG", quality=90)
            xobj.write(buf.getvalue(), filter=Name.DCTDecode)
        else:
            xobj.write(zlib.compress(out.tobytes(), 9), filter=Name.FlateDecode)
        xobj.ColorSpace = Name.DeviceGray if out.mode == "L" else Name.DeviceRGB
        xobj.BitsPerComponent = 8
        for key in ("/Decode", "/DecodeParms", "/Intent"):
            if key in xobj:
                del xobj[key]
        return True

    def form(self, xobj: pikepdf.Stream, inherited) -> bool:
        if not self._first(xobj):
            return True
        res = xobj.get("/Resources") or inherited
        try:
            data = self.rewrite(xobj, res)
        except pikepdf.PdfError:
            self.reasons.append("formulario XObject ilegible")
            return False
        xobj.write(data)
        return True

    def pattern(self, pat, resources) -> bool:
        if isinstance(pat, pikepdf.Stream) and int(pat.get("/PatternType", 0)) == 1:
            if int(pat.get("/PaintType", 1)) == 2:
                self.reasons.append("patrón sin color propio")
                return False
            return self.form(pat, resources)
        if isinstance(pat, (pikepdf.Dictionary, pikepdf.Stream)) and int(pat.get("/PatternType", 0)) == 2:
            if not self._first(pat):
                return True
            return self.shading(pat.get("/Shading"), resources)
        return False

    def annotation(self, annot) -> None:
        if not isinstance(annot, pikepdf.Dictionary):
            return
        for key in ("/C", "/IC"):
            if key in annot:
                arr = self.convert_array(annot[key])
                if arr is not None:
                    annot[key] = arr
        mk = annot.get("/MK")
        if isinstance(mk, pikepdf.Dictionary):
            for key in ("/BG", "/BC"):
                if key in mk:
                    arr = self.convert_array(mk[key])
                    if arr is not None:
                        mk[key] = arr
        if "/DA" in annot:
            annot.DA = pikepdf.String(self.convert_da(str(annot.DA)))
        ap = annot.get("/AP")
        if isinstance(ap, pikepdf.Dictionary):
            for key in ("/N", "/R", "/D"):
                entry = ap.get(key)
                streams = [entry] if isinstance(entry, pikepdf.Stream) else list(entry.values()) if isinstance(entry, pikepdf.Dictionary) else []
                for st in streams:
                    if isinstance(st, pikepdf.Stream):
                        self.form(st, None)

    # --- flujos de contenido ---------------------------------------------------------------------------------
    def rewrite(self, target, resources) -> bytes:
        instructions = pikepdf.parse_content_stream(target)
        out: list = []
        stack: list[tuple[str, str]] = []
        fill = stroke = "gray"
        xobjects = resources.get("/XObject") if isinstance(resources, pikepdf.Dictionary) else None
        patterns = resources.get("/Pattern") if isinstance(resources, pikepdf.Dictionary) else None
        shadings = resources.get("/Shading") if isinstance(resources, pikepdf.Dictionary) else None
        for ins in instructions:
            if isinstance(ins, pikepdf.ContentStreamInlineImage):
                if not self.inline_images_safe:
                    self.reasons.append("imagen en línea")
                out.append(ins)
                continue
            op = str(ins.operator)
            operands = list(ins.operands)
            if op == "q":
                stack.append((fill, stroke))
            elif op == "Q":
                fill, stroke = stack.pop() if stack else (fill, stroke)
            elif op in OPS_FILL or op in OPS_STROKE:
                kind = OPS_FILL.get(op) or OPS_STROKE[op]
                if op in OPS_FILL:
                    fill = kind
                else:
                    stroke = kind
                try:
                    ins = pikepdf.ContentStreamInstruction(self.convert(kind, [float(v) for v in operands]), Operator(op))
                except (ValueError, TypeError):
                    self.reasons.append(f"operador {op} con valores no numéricos")
            elif op in ("cs", "CS"):
                kind = space_kind(operands[0] if operands else None, resources)
                if op == "cs":
                    fill = kind
                else:
                    stroke = kind
                if kind == "other":
                    self.reasons.append("espacio de color Separation, DeviceN, Indexed o Lab")
            elif op in ("sc", "scn", "SC", "SCN"):
                kind = fill if op in ("sc", "scn") else stroke
                nums = [v for v in operands if not isinstance(v, Name)]
                names = [v for v in operands if isinstance(v, Name)]
                if kind in ("gray", "rgb", "cmyk") and not names:
                    try:
                        ins = pikepdf.ContentStreamInstruction(self.convert(kind, [float(v) for v in nums]), Operator(op))
                    except (ValueError, TypeError):
                        self.reasons.append(f"operador {op} no convertible")
                elif kind == "pattern" and names and not nums:
                    pat = patterns.get(str(names[-1])) if isinstance(patterns, pikepdf.Dictionary) else None
                    if pat is None or not self.pattern(pat, resources):
                        self.reasons.append("patrón no convertible")
                else:
                    self.reasons.append("color en un espacio no convertible")
            elif op == "sh":
                sh = shadings.get(str(operands[0])) if isinstance(shadings, pikepdf.Dictionary) and operands else None
                self.shading(sh, resources)
            elif op == "Do" and operands and isinstance(xobjects, pikepdf.Dictionary):
                xobj = xobjects.get(str(operands[0]))
                if isinstance(xobj, pikepdf.Stream):
                    subtype = xobj.get("/Subtype")
                    if subtype == Name.Image:
                        self.image(xobj)
                    elif subtype == Name.Form:
                        self.form(xobj, resources)
            out.append(ins)
        return pikepdf.unparse_content_stream(out)

    def page(self, page: pikepdf.Page, prefix: bytes = b"") -> list[str]:
        """Reescribe la página y sus anotaciones; devuelve los motivos por los que no es segura (vacío si lo es)."""
        self.reasons = []
        resources = page.obj.get("/Resources")
        if resources is None:
            resources = page.resources
        data = self.rewrite(page, resources)
        page.obj.Contents = self.pdf.make_stream(prefix + data)
        for annot in page.obj.get("/Annots", []) or []:
            self.annotation(annot)
        return sorted(set(self.reasons))
