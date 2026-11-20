"""F6-F (7.13, D-215): TTF, OTF, WOFF y WOFF2 con fontTools y brotli."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from core.errors import ToolError
from test_tools import make_ctx, run  # noqa: F401  (fixture)

pytest.importorskip("brotli")
from fontTools.pens.boundsPen import BoundsPen  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NOTO = ROOT / "apps/web/public/fonts/NotoSans-Regular.ttf"


def _bounds(font: TTFont, names) -> dict[str, tuple]:
    gs = font.getGlyphSet()
    out = {}
    for name in names:
        pen = BoundsPen(gs)
        gs[name].draw(pen)
        out[name] = pen.bounds
    return out


def _sample(font: TTFont) -> list[str]:
    cmap = font.getBestCmap()
    return [cmap[ord(c)] for c in "AaÑñ€gQ@&"]


def _copy(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.fixture
def otf(make_ctx, tmp_path) -> Path:
    out = run("ttf-a-otf", make_ctx("ttf-a-otf", [NOTO]))
    return _copy(tmp_path, out[0]["name"], Path(out[0]["path"]).read_bytes())


def test_ttf_to_otf_is_exact_and_drops_hinting(otf):
    src, dst = TTFont(NOTO), TTFont(otf)
    assert dst.sfntVersion == "OTTO" and "CFF " in dst and "glyf" not in dst and "fpgm" not in dst
    assert dst.getGlyphOrder() == src.getGlyphOrder() and dst.getBestCmap() == src.getBestCmap()
    names = _sample(src)
    for name, (a, b) in zip(names, zip(_bounds(src, names).values(), _bounds(dst, names).values())):
        assert all(abs(x - y) <= 1 for x, y in zip(a, b)), name
    assert dst["name"].getDebugName(1) == src["name"].getDebugName(1)


def test_otf_to_ttf_approximates_within_one_unit(make_ctx, otf):
    out = run("otf-a-ttf", make_ctx("otf-a-ttf", [otf]))
    assert out[0]["name"] == "NotoSans-Regular.ttf" and "error máximo de 1 unidad de 1000 por em" in out[0]["note"]
    ttf = TTFont(out[0]["path"])
    assert ttf.sfntVersion == "\x00\x01\x00\x00" and "glyf" in ttf and "CFF " not in ttf
    names = _sample(ttf)
    for a, b in zip(_bounds(TTFont(otf), names).values(), _bounds(ttf, names).values()):
        assert all(abs(x - y) <= 2 for x, y in zip(a, b))


def test_woff2_round_trip_keeps_the_font(make_ctx, tmp_path):
    out = run("ttf-a-woff2", make_ctx("ttf-a-woff2", [NOTO]))
    woff2 = _copy(tmp_path, out[0]["name"], Path(out[0]["path"]).read_bytes())
    assert woff2.read_bytes()[:4] == b"wOF2" and woff2.stat().st_size < NOTO.stat().st_size * 0.5
    back = run("woff2-a-ttf", make_ctx("woff2-a-ttf", [woff2]))
    font = TTFont(back[0]["path"])
    assert font.flavor is None and font.getGlyphOrder() == TTFont(NOTO).getGlyphOrder() and back[0]["note"] is None


def test_woff_with_cff_becomes_truetype(make_ctx, tmp_path, otf):
    font = TTFont(otf)
    font.flavor = "woff"
    woff = tmp_path / "cff.woff"
    font.save(woff)
    out = run("woff-a-ttf", make_ctx("woff-a-ttf", [woff]))
    ttf = TTFont(out[0]["path"])
    assert "glyf" in ttf and "contornos CFF" in out[0]["note"]
    woff2 = run("otf-a-woff2", make_ctx("otf-a-woff2", [otf]))
    assert TTFont(woff2[0]["path"]).flavor == "woff2" and "CFF " in TTFont(woff2[0]["path"])


def test_variable_font_only_to_woff2(make_ctx, tmp_path):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({65: "A"})
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0)), pen.lineTo((500, 700)), pen.lineTo((1000, 0)), pen.closePath()
    fb.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "A": pen.glyph()})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (1000, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Prueba", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.setupFvar([("wght", 100, 400, 900, "Weight")], [])
    path = tmp_path / "variable.ttf"
    fb.save(path)
    with pytest.raises(ToolError) as err:
        run("ttf-a-otf", make_ctx("ttf-a-otf", [path]))
    assert err.value.detail == "font_variable"
    out = run("ttf-a-woff2", make_ctx("ttf-a-woff2", [path]))
    assert "fvar" in TTFont(out[0]["path"])


@pytest.mark.parametrize("data", [b"\x00\x01\x00\x00\x00\x05basura" + bytes(64), b"wOF2" + bytes(60)])
def test_corrupt_fonts(make_ctx, tmp_path, data):
    tool = "woff2-a-ttf" if data.startswith(b"wOF2") else "ttf-a-otf"
    path = _copy(tmp_path, "rota." + ("woff2" if tool == "woff2-a-ttf" else "ttf"), data)
    with pytest.raises(ToolError) as err:
        run(tool, make_ctx(tool, [path]))
    assert err.value.code == "CORRUPT_FILE"


def test_batch(make_ctx, tmp_path):
    second = tmp_path / "Copia.ttf"
    shutil.copyfile(NOTO, second)
    out = run("ttf-a-woff2", make_ctx("ttf-a-woff2", [NOTO, second]))
    assert [o["name"] for o in out] == ["NotoSans-Regular.woff2", "Copia.woff2", "ttf-a-woff2.zip"]


# --- Revisión de F6-F (D-221) -----------------------------------------------------------------------------------------


def test_cff_bbox_and_latin1_names(make_ctx, tmp_path):
    font = TTFont(NOTO)
    for record in font["name"].names:
        if record.nameID in (0, 1, 4):
            record.string = record.toUnicode() + " ™ — 中文"
    src = tmp_path / "Rara.ttf"
    font.save(src)
    out = run("ttf-a-otf", make_ctx("ttf-a-otf", [src]))
    cff = TTFont(out[0]["path"])["CFF "].cff
    top = cff.topDictIndex[0]
    head = TTFont(NOTO)["head"]
    assert list(top.FontBBox) == [head.xMin, head.yMin, head.xMax, head.yMax]
    assert "(TM)" in top.Notice and cff.fontNames[0].isascii()


def test_missing_tables_are_corrupt(make_ctx, tmp_path):
    font = TTFont(NOTO)
    del font["post"]
    src = tmp_path / "SinPost.ttf"
    font.save(src)
    with pytest.raises(ToolError) as err:
        run("ttf-a-otf", make_ctx("ttf-a-otf", [src]))
    assert err.value.code == "CORRUPT_FILE"
