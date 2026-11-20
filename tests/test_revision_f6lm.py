"""Revisión de F6-L y F6-M (D-233): UDF sin crecimiento sin límite ni marcas inyectadas, MIDI que FluidSynth no toca
como dice, .mxl con señuelo y límites de MuseScore."""
from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest

from core.errors import ToolError
from core.settings import get_settings
from test_musica import MUSICXML, SCALE, midi
from test_tools import make_ctx, run  # noqa: F401  (fixture)


def _udf(tmp_path: Path, content: str, name: str = "d.udf") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.xml", content)
    return path


def _template(text: str, elements: str) -> str:
    return f'<?xml version="1.0"?><template><content><![CDATA[{text}]]></content><elements>{elements}</elements></template>'


def test_udf_nested_tables_do_not_explode(tmp_path):
    from tools.office.udf import to_html

    inner = '<paragraph><content startOffset="0" length="4"/></paragraph>'
    for _ in range(12):
        inner = f"<table><row><cell>{inner}</cell></row></table>"
    page = to_html(_udf(tmp_path, _template("Hola", inner))).decode()
    assert page.count("<table>") == 12 and page.count("Hola") == 1
    for _ in range(15):
        inner = f"<table><row><cell>{inner}</cell></row></table>"
    with pytest.raises(ToolError) as err:
        to_html(_udf(tmp_path, _template("Hola", inner), "hondo.udf"))
    assert err.value.code == "LIMIT_EXCEEDED"


def test_udf_repeated_slices_are_capped(tmp_path):
    from tools.office.udf import to_html

    text = "x" * 1_000_000
    elements = "<paragraph>" + '<content startOffset="0" length="1000000"/>' * 60 + "</paragraph>"
    with pytest.raises(ToolError) as err:
        to_html(_udf(tmp_path, _template(text, elements)))
    assert err.value.code == "LIMIT_EXCEEDED"


def test_udf_image_data_cannot_break_out_and_bad_numbers(tmp_path):
    from tools.office.udf import to_html

    evil = "A" * 200 + '&quot;&gt;&lt;iframe src=&quot;file:///etc/passwd&quot;&gt;&lt;/iframe&gt;'
    good = "iVBORw0KGgo="
    elements = (f'<paragraph><content startOffset="0" length="inf" size="1e999"/><image imageData="{evil}"/>'
                f'<image imageData="{good}"/></paragraph>')
    page = to_html(_udf(tmp_path, _template("Hola", elements))).decode()
    assert "<iframe" not in page and "file:///" not in page and f"base64,{good}" in page


def test_udf_encrypted_or_bad_zip(make_ctx, tmp_path):
    bad = tmp_path / "x.udf"
    bad.write_bytes(b"PK\x03\x04" + bytes(40))
    with pytest.raises(ToolError) as err:
        run("udf-a-pdf", make_ctx("udf-a-pdf", [bad]))
    assert err.value.code in ("CORRUPT_FILE", "UNSUPPORTED_FORMAT")


def _header(fmt: int, ntracks: int, division: int) -> bytes:
    return b"MThd" + struct.pack(">IHHH", 6, fmt, ntracks, division)


def test_midi_unplayable_or_cut_files_are_rejected():
    from tools.av.midi import duration

    body = midi(SCALE)[14:]
    with pytest.raises(ToolError) as err:
        duration(_header(0, 1, 0) + body)
    assert err.value.code == "CORRUPT_FILE"
    for header in (_header(2, 1, 480), _header(0, 1, 0xE728)):  # formato 2 y SMPTE de 25 fps
        with pytest.raises(ToolError) as err:
            duration(header + body)
        assert err.value.detail == "midi_unsupported"
    assert duration(_header(2, 1, 480) + body, playable=False) == pytest.approx(3.0)
    with pytest.raises(ToolError) as err:
        duration(_header(0, 1, 480) + b"MTrk\x00")
    assert err.value.code == "CORRUPT_FILE"


@pytest.mark.skipif(not Path(get_settings().FLUIDSYNTH_BIN).is_file(), reason="sin FluidSynth")
def test_fluidsynth_output_is_bounded_by_parsed_duration(make_ctx, tmp_path, monkeypatch):
    """Aunque el lector se equivoque, el WAV no pasa de lo que dice (más la cola y un margen)."""
    from tools.av import midi as mod

    monkeypatch.setattr(mod, "duration", lambda data, playable=True: 1.0)  # el lector «cree» que dura 1 s
    src = tmp_path / "largo.mid"
    src.write_bytes(midi([(60, 3000)]))  # 25 min de verdad: unos 260 MB de WAV, por encima del tope de 128 MB
    with pytest.raises(ToolError) as err:
        run("midi-a-wav", make_ctx("midi-a-wav", [src]))
    assert err.value.code == "LIMIT_EXCEEDED"


def _mxl(tmp_path: Path, files: dict[str, str], name: str = "p.mxl") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        for k, v in files.items():
            zf.writestr(k, v)
    return path


def test_mxl_checks_the_rootfile_not_a_decoy(tmp_path):
    from tools.office.partitura import _checked

    class Inp:
        def __init__(self, path):
            self.path, self.name, self.ext = path, path.name, "mxl"

    container = '<?xml version="1.0"?><container><rootfiles><rootfile full-path="real.xml"/></rootfiles></container>'
    evil = '<?xml version="1.0"?><!DOCTYPE s [<!ENTITY x "EXPANDIDO">]><score-partwise><work><work-title>&x;</work-title></work></score-partwise>'
    path = _mxl(tmp_path, {"META-INF/container.xml": container, "a_decoy.xml": MUSICXML, "real.xml": evil})
    with pytest.raises(ToolError) as err:
        _checked(Inp(path))
    assert err.value.detail == "xml_entities"
    missing = _mxl(tmp_path, {"META-INF/container.xml": container, "otra.xml": MUSICXML}, "m.mxl")
    with pytest.raises(ToolError) as err:
        _checked(Inp(missing))
    assert err.value.code == "CORRUPT_FILE"
    ok = _mxl(tmp_path, {"META-INF/container.xml": container, "real.xml": MUSICXML}, "ok.mxl")
    assert _checked(Inp(ok)) == "mxl"


def test_mxl_uncompressed_cap(tmp_path):
    from tools.office.partitura import _checked

    class Inp:
        def __init__(self, path):
            self.path, self.name, self.ext = path, path.name, "mxl"

    import os

    big = "<score-partwise>" + "".join(f"<a>{os.urandom(8).hex()}</a>" for _ in range(1_600_000)) + "</score-partwise>"
    path = tmp_path / "grande.mxl"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("score.xml", big)
    with pytest.raises(ToolError) as err:
        _checked(Inp(path))
    assert err.value.code == "LIMIT_EXCEEDED"


def test_wait_delay_is_milliseconds():
    from tools.office.web_a_pdf import chromium_fields
    from tools.office.specs import WebAPdfOptions

    fields = chromium_fields(WebAPdfOptions(url="https://example.com/", espera_s=0.00001))
    assert fields["waitDelay"] == "0ms"
