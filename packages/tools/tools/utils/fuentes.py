"""Fuentes (7.13, F6-F, D-215): TTF, OTF, WOFF y WOFF2 con fontTools (MIT) y brotli (MIT).

- A WOFF2: la misma fuente comprimida para la web (`flavor = "woff2"`), sin tocar los contornos.
- De WOFF o WOFF2: se descomprime; si dentro hay contornos CFF y se pide TTF, se pasan a TrueType.
- TTF a OTF: las curvas cuadráticas de TrueType se convierten en cúbicas, que es exacto, y se escribe una tabla CFF;
  las instrucciones de hinting de TrueType no tienen equivalente y se quitan.
- OTF a TTF: las cúbicas se aproximan con cuadráticas (cu2qu, error máximo de 1 unidad de la cuadrícula, como el
  ejemplo `otf2ttf` de fontTools).
Las fuentes variables se convierten a WOFF2 y desde él, pero no entre TTF y OTF (necesitarían CFF2 o rehacer las
variaciones): se rechazan con un mensaje propio.
"""
from __future__ import annotations

import re
import struct
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.pdf.common import with_batch_zip

MAX_FONT_BYTES = 15 * 1024 * 1024  # una fuente de 40 MB llegaba a 1,5 GB de memoria al convertirla
MAX_ERR = 1.0  # unidades de la cuadrícula (unitsPerEm suele ser 1000 o 2048)
TT_ONLY = ("glyf", "loca", "fpgm", "prep", "cvt ", "gasp", "hdmx", "LTSH", "VDMX", "cvar", "TSI0", "TSI1", "TSI2", "TSI3", "TSI5")
TARGET = {"ttf-a-woff2": "woff2", "otf-a-woff2": "woff2", "woff2-a-ttf": "ttf", "woff-a-ttf": "ttf", "ttf-a-otf": "otf",
          "otf-a-ttf": "ttf"}

NOTES = {
    "es": {"hinting": "Las instrucciones de hinting de TrueType no existen en OpenType CFF y se han quitado; la fuente se ve "
                      "igual en pantallas de alta resolución.",
           "approx": "Las curvas cúbicas se han aproximado con cuadráticas (error máximo de {err} unidad de {upm} por em).",
           "cff": "La fuente tenía contornos CFF: se han convertido a TrueType."},
    "en": {"hinting": "TrueType hinting instructions do not exist in OpenType CFF and were removed; the font looks the same on "
                      "high-resolution screens.",
           "approx": "Cubic curves were approximated with quadratic ones (maximum error of {err} unit of {upm} per em).",
           "cff": "The font had CFF outlines: they were converted to TrueType."},
}


def _open(path: Path):
    from fontTools.ttLib import TTFont, TTLibError

    if path.stat().st_size > MAX_FONT_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Fuente de más de 15 MB")
    try:
        font = TTFont(path, lazy=False, recalcBBoxes=False, recalcTimestamp=False)
        font.getGlyphOrder()
        return font
    except ImportError as exc:  # WOFF2 sin brotli
        raise ToolError(ErrorCode.ENGINE_FAILED, "brotli") from exc
    except (TTLibError, AssertionError, KeyError, ValueError, IndexError, TypeError, OSError, struct.error) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "fuente") from exc
    except Exception as exc:  # brotli.error y lo que lance fontTools con una fuente mal hecha: no tienen base común
        if type(exc).__module__.split(".")[0] in ("brotli", "fontTools", "_brotli"):
            raise ToolError(ErrorCode.CORRUPT_FILE, "fuente") from exc
        raise


def _is_variable(font) -> bool:
    return "fvar" in font


def _drop(font, tags) -> None:
    for tag in tags:
        if tag in font:
            del font[tag]


def latin1(text: str) -> str:
    """Los textos de una tabla CFF van en Latin-1: «™», «’» o un nombre en chino se aproximan o se cambian por «?»."""
    import unicodedata

    text = text.replace("™", "(TM)").replace("’", "'").replace("‘", "'").replace("—", "-").replace("–", "-")
    try:
        return text.encode("latin-1").decode("latin-1")
    except UnicodeEncodeError:
        return unicodedata.normalize("NFKD", text).encode("latin-1", errors="replace").decode("latin-1")


def _require(font, tags) -> None:
    missing = [t for t in tags if t not in font]
    if missing:
        raise ToolError(ErrorCode.CORRUPT_FILE, f"fuente sin {', '.join(missing)}")


def tt_to_cff(font) -> None:
    """Contornos TrueType a CFF (exacto: cada cuadrática es una cúbica) con los nombres de glifo y las métricas de la
    propia fuente."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen

    glyph_set = font.getGlyphSet()
    order = font.getGlyphOrder()
    hmtx = font["hmtx"]
    charstrings = {}
    for name in order:
        # roundTolerance=0: los puntos de control de las cúbicas (dos tercios de los de la cuadrática) no se redondean.
        pen = T2CharStringPen(hmtx[name][0], glyph_set, roundTolerance=0)
        glyph_set[name].draw(pen)
        charstrings[name] = pen.getCharString()
    names = font["name"]
    ps_name = re.sub(r"[^!-~]|[\[\](){}<>/%]", "", latin1(names.getDebugName(6) or ""))[:63] or "Fuente"
    info = {"FullName": latin1(names.getDebugName(4) or ps_name), "FamilyName": latin1(names.getDebugName(1) or ps_name),
            "Weight": latin1(names.getDebugName(2) or "Regular"), "version": f"{font['head'].fontRevision:.3f}"}
    copyright_ = names.getDebugName(0)
    if copyright_:
        info["Notice"] = latin1(copyright_)[:2000]
    fb = FontBuilder(font=font)
    _drop(font, (*TT_ONLY, "DSIG"))  # la firma digital de la fuente ya no vale con otros contornos
    font.recalcBBoxes = True  # FontBBox de la tabla CFF (sin esto, [0 0 0 0])
    fb.isTTF = False
    font.sfntVersion = "OTTO"
    fb.setupCFF(ps_name, info, charstrings, {})
    maxp = font["maxp"]
    maxp.tableVersion = 0x00005000
    for attr in list(vars(maxp)):
        if attr not in ("tableVersion", "numGlyphs", "tableTag"):
            delattr(maxp, attr)
    font["post"].formatType = 3.0
    font["head"].glyphDataFormat = 0


def cff_to_tt(font) -> None:
    """Contornos CFF a TrueType con cu2qu (el ejemplo otf2ttf de fontTools)."""
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import newTable

    glyph_set = font.getGlyphSet()
    order = font.getGlyphOrder()
    glyphs = {}
    for name in order:
        tt_pen = TTGlyphPen(glyph_set)
        glyph_set[name].draw(Cu2QuPen(tt_pen, MAX_ERR, reverse_direction=True))
        glyphs[name] = tt_pen.glyph()
    font["loca"] = newTable("loca")
    font["glyf"] = glyf = newTable("glyf")
    glyf.glyphOrder = order
    glyf.glyphs = glyphs
    _drop(font, ("CFF ", "VORG", "DSIG"))
    font.sfntVersion = "\x00\x01\x00\x00"
    font["head"].glyphDataFormat = 0
    font["maxp"] = maxp = newTable("maxp")
    maxp.tableVersion = 0x00010000
    for attr, value in (("maxZones", 1), ("maxTwilightPoints", 0), ("maxStorage", 0), ("maxFunctionDefs", 0),
                        ("maxInstructionDefs", 0), ("maxStackElements", 0), ("maxSizeOfInstructions", 0),
                        ("maxComponentElements", max((len(g.components) for g in glyphs.values() if hasattr(g, "components")), default=0))):
        setattr(maxp, attr, value)
    maxp.numGlyphs = len(order)
    font.recalcBBoxes = True  # cajas de los glifos, head y maxp se calculan al guardar
    post = font["post"]
    post.formatType = 2.0
    post.extraNames = []
    post.mapping = {}
    post.glyphOrder = order


def _guarded(step, font) -> None:
    """Un paso de conversión con los mismos errores que la lectura (componentes en bucle, tablas incoherentes)."""
    try:
        step(font)
    except ToolError:
        raise
    except RecursionError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "fuente con componentes en bucle") from exc
    except Exception as exc:  # noqa: BLE001 - fontTools no tiene una excepción común
        raise ToolError(ErrorCode.CORRUPT_FILE, "fuente") from exc


def convert(ctx: ToolContext, path: Path, target: str) -> tuple[bytes, list[str]]:
    import io

    t = NOTES.get(ctx.locale, NOTES["es"])
    font = _open(path)
    notes: list[str] = []
    has_cff = "CFF " in font or "CFF2" in font
    if target == "woff2":
        font.flavor = "woff2"
    else:
        font.flavor = None
        if target == "ttf" and has_cff:
            if _is_variable(font) or "CFF2" in font:
                raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "font_variable")
            _require(font, ("post", "hmtx", "head", "maxp"))
            _guarded(cff_to_tt, font)
            notes.append(t["approx"].format(err=f"{MAX_ERR:g}", upm=font["head"].unitsPerEm))
            if ctx.tool != "otf-a-ttf":
                notes.insert(0, t["cff"])
        elif target == "otf":
            if has_cff and "glyf" in font:
                _drop(font, ("glyf", "loca"))  # con los dos tipos de contornos, el OTF se queda con el CFF
                font.sfntVersion = "OTTO"
            if not has_cff:
                if _is_variable(font):
                    raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "font_variable")
                hinted = any(tag in font for tag in ("fpgm", "prep", "cvt "))
                _require(font, ("name", "post", "hmtx", "head", "maxp", "glyf"))
                _guarded(tt_to_cff, font)
                if hinted:
                    notes.append(t["hinting"])
    buf = io.BytesIO()
    try:
        font.save(buf, reorderTables=True)
    except Exception as exc:  # fontTools no tiene una excepción común al escribir
        raise ToolError(ErrorCode.CORRUPT_FILE, "fuente") from exc
    data = buf.getvalue()
    # Se vuelve a abrir: lo que se entrega se puede leer.
    check = ctx.work / f"comprobar.{target}"
    check.parent.mkdir(parents=True, exist_ok=True)
    check.write_bytes(data)
    _open(check).close()
    check.unlink()
    return data, notes


def run(ctx: ToolContext) -> list[dict]:
    target = TARGET[ctx.tool]
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        data, notes = convert(ctx, inp.path, target)
        name = derived_name(inp.name, "", target)
        dst = ctx.output(name)
        dst.write_bytes(data)
        outputs.append({"path": str(dst), "name": name, "note": " ".join(notes) or None})
    return with_batch_zip(ctx, outputs, f"{ctx.tool}.zip")
