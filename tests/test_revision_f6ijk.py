"""Revisión de F6-I, F6-J y F6-K (D-230): vCard con comas, 2.1 y quoted-printable; tablas acotadas; zonas horarias;
run_engine sin motores huérfanos; LaTeX con report y BibTeX; draw.io con Base64 estricto y presupuesto total."""
from __future__ import annotations

import base64
import csv
import io
import os
import signal
import time
import urllib.parse
import zipfile
import zlib
from pathlib import Path

import pytest

from core.errors import ToolError
from core.settings import get_settings
from test_tools import make_ctx, run  # noqa: F401  (fixture)


def _write(tmp_path: Path, name: str, data: str | bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def _rows(path: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(Path(path).read_text(encoding="utf-8-sig"))))


# --- vCard ------------------------------------------------------------------------------------------------------------

VCF_COMMAS = (
    "BEGIN:VCARD\r\nVERSION:2.1\r\nN:Smith;John\r\nFN:Smith, John\r\nTITLE:Director, Ventas\r\nORG:Acme, S.L.\r\n"
    "NOTE:Llamar lunes, martes o jueves\r\nADR;WORK:;;Calle Mayor, 5, 2º B;Madrid;;28013;España\r\n"
    "TEL;CELL:600 111 222\r\nTEL;WORK;FAX:910 000 001\r\nTEL;CELL:600 333 444\r\nTEL;HOME:912 345 678\r\nTEL;HOME:913 000 000\r\n"
    "NOTE;ENCODING=QUOTED-PRINTABLE;CHARSET=UTF-8:Nota larga que se =\r\nparte en dos l=C3=ADneas\r\nEND:VCARD\r\n"
    "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Ana\\, la de Ventas\r\nN:López;Ana;;;\r\nCATEGORIES:Clientes\\, VIP,Madrid\r\n"
    "TEL;TYPE=WORK,FAX:910 999 999\r\nitem1.EMAIL;TYPE=INTERNET:ana@example.com\r\nEND:VCARD\r\n")


def test_vcard_reader_keeps_commas_types_and_qp():
    from tools.utils.agenda import read_vcf

    (john, ana), _ = read_vcf(VCF_COMMAS.encode())
    assert john.full == "Smith, John" and john.title == "Director, Ventas" and john.org == "Acme, S.L."
    assert john.note == "Nota larga que se parte en dos líneas"
    assert john.addresses == [("work", {"street": "Calle Mayor, 5, 2º B", "city": "Madrid", "region": "", "code": "28013", "country": "España"})]
    assert ("fax", "910 000 001") in john.phones and ("cell", "600 333 444") in john.phones and ("home", "912 345 678") in john.phones
    assert ana.full == "Ana, la de Ventas" and ana.categories == ["Clientes, VIP", "Madrid"] and ana.phones == [("fax", "910 999 999")]
    assert ana.emails == [("other", "ana@example.com")]


def test_outlook_keeps_second_phones(make_ctx, tmp_path):
    out = run("vcf-a-csv", make_ctx("vcf-a-csv", [_write(tmp_path, "c.vcf", VCF_COMMAS)], {"plantilla": "outlook"}))
    rows = _rows(out[0]["path"])
    john = dict(zip(rows[0], rows[1]))
    assert john["Mobile Phone"] == "600 111 222" and john["Car Phone"] == "600 333 444"
    assert john["Home Phone"] == "912 345 678" and john["Home Phone 2"] == "913 000 000" and john["Business Fax"] == "910 000 001"
    assert john["Business Street"] == "Calle Mayor, 5, 2º B" and john["Job Title"] == "Director, Ventas"
    back = run("csv-a-vcf", make_ctx("csv-a-vcf", [Path(out[0]["path"])]))
    from tools.utils.agenda import read_vcf

    cards, _ = read_vcf(Path(back[0]["path"]).read_bytes())
    phones = {v for _, v in cards[0].phones}
    assert {"600 111 222", "600 333 444", "912 345 678", "913 000 000", "910 000 001"} <= phones


def test_vcard_entries_are_capped(make_ctx, tmp_path):
    many = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Muchos\r\n" + "".join(f"EMAIL:a{i}@example.com\r\n" for i in range(5000)) + "END:VCARD\r\n"
    small = "".join(f"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:P{i}\r\nEMAIL:p{i}@example.com\r\nEND:VCARD\r\n" for i in range(2000))
    out = run("vcf-a-csv", make_ctx("vcf-a-csv", [_write(tmp_path, "m.vcf", many + small)], {"plantilla": "google"}))
    rows = _rows(out[0]["path"])
    assert len(rows[0]) < 100 and len(rows) == 2002 and "como mucho 10" in out[0]["note"]


ICS_UTC = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nX-WR-TIMEZONE:Europe/Madrid\r\nBEGIN:VEVENT\r\nUID:a\r\nSUMMARY:Reunión\r\n"
           "DTSTART:20250115T090000Z\r\nDTEND:20250115T100000Z\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nUID:b\r\nSUMMARY:NY\r\n"
           "DTSTART;TZID=America/New_York:20250115T090000\r\nDTEND;TZID=America/New_York:20250115T093000\r\nEND:VEVENT\r\n"
           "END:VCALENDAR\r\n")


def test_ics_google_template_converts_to_calendar_zone(make_ctx, tmp_path):
    src = _write(tmp_path, "c.ics", ICS_UTC)
    rows = _rows(run("ics-a-csv", make_ctx("ics-a-csv", [src], {"plantilla": "google"}))[0]["path"])
    assert rows[1][2] == "10:00 AM" and rows[2][2] == "03:00 PM"
    rows = _rows(run("ics-a-csv", make_ctx("ics-a-csv", [src], {"plantilla": "outlook", "zona": "UTC"}))[0]["path"])
    assert rows[1][2] == "09:00 AM" and rows[2][2] == "02:00 PM"


def test_csv_to_ics_spanish_times(make_ctx, tmp_path):
    src = _write(tmp_path, "e.csv", "Título;Fecha;Hora\nA;03/04/2026;9.30\nB;03/04/2026;9:00 p. m.\nC;03/04/2026;mañana\n")
    out = run("csv-a-ics", make_ctx("csv-a-ics", [src]))
    data = Path(out[0]["path"]).read_text()
    assert "T093000" in data and "T210000" in data and "1 evento(s) con una hora que no se entiende" in out[0]["note"]


# --- run_engine -------------------------------------------------------------------------------------------------------


def test_run_engine_kills_engine_on_soft_time_limit(tmp_path):
    from tools.base import run_engine

    class Soft(Exception):
        pass

    def boom(*_):
        raise Soft

    old = signal.signal(signal.SIGALRM, boom)
    signal.alarm(1)
    try:
        with pytest.raises(Soft):
            run_engine(["/bin/sh", "-c", "echo $$ > pid; exec sleep 30"], cwd=tmp_path, timeout=60)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
    pid = int((tmp_path / "pid").read_text())
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_run_engine_bounds_output(tmp_path):
    from tools.base import STDERR_KEEP, run_engine

    with pytest.raises(ToolError) as err:
        run_engine(["/bin/sh", "-c", "head -c 5000 /dev/zero"], cwd=tmp_path, timeout=20, max_stdout=1000)
    assert err.value.code == "LIMIT_EXCEEDED"
    res = run_engine(["/bin/sh", "-c", "head -c 20000000 /dev/zero >&2; echo fin >&2"], cwd=tmp_path, timeout=30)
    assert len(res.stderr) <= 3 * STDERR_KEEP + 16 and res.stderr.endswith(b"fin\n")
    with pytest.raises(ToolError) as err:
        run_engine(["/bin/sh", "-c", "head -c 3000000 /dev/zero > big"], cwd=tmp_path, timeout=20, max_file_mb=1)
    assert err.value.code == "ENGINE_FAILED"


# --- LaTeX ------------------------------------------------------------------------------------------------------------

needs_tectonic = pytest.mark.skipif(not Path(get_settings().TECTONIC_BIN).is_file(), reason="sin Tectonic")
BIB = "@book{lamport94, author = {Leslie Lamport}, title = {LaTeX: A Document Preparation System}, publisher = {Addison-Wesley}, year = {1994}}\n"


@needs_tectonic
def test_latex_report_with_bibtex(make_ctx, tmp_path):
    packed = tmp_path / "tesis.zip"
    with zipfile.ZipFile(packed, "w") as zf:
        zf.writestr("old/main.tex", "\\documentclass{article}\\begin{document}Antiguo\\end{document}")
        zf.writestr("borrador.tex", "% \\documentclass{article}\nnada")
        zf.writestr("memoria.tex", "\\documentclass{report}\\usepackage[spanish]{babel}\\begin{document}\\chapter{Intro}"
                                   "Según \\cite{lamport94} y \\cite{nadie}.\\bibliographystyle{plain}\\bibliography{refs}\\end{document}")
        zf.writestr("refs.bib", BIB)
    out = run("latex-a-pdf", make_ctx("latex-a-pdf", [packed]))
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(out[0]["path"])
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert out[0]["name"] == "tesis.pdf" and "Lamport" in text and "memoria.tex" in out[0]["note"]
    assert "citas sin resolver (nadie)" in out[0]["note"]


def test_latex_zip_with_clashing_paths(make_ctx, tmp_path):
    if not Path(get_settings().TECTONIC_BIN).is_file():
        pytest.skip("sin Tectonic")
    packed = tmp_path / "x.zip"
    with zipfile.ZipFile(packed, "w") as zf:
        zf.writestr("a.tex", "\\documentclass{article}")
        zf.writestr("a.tex/b.tex", "x")
    with pytest.raises(ToolError) as err:
        run("latex-a-pdf", make_ctx("latex-a-pdf", [packed]))
    assert err.value.code == "CORRUPT_FILE"


# --- draw.io ----------------------------------------------------------------------------------------------------------

MODEL = ('<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
         '<mxCell id="g" vertex="1" parent="1"><mxGeometry x="100" y="100" width="50" height="50" as="geometry"/></mxCell>'
         '<mxCell id="c" vertex="1" parent="g"><mxGeometry x="200" y="0" width="40" height="40" as="geometry"/></mxCell>'
         '<mxCell id="e" edge="1" parent="1"><mxGeometry relative="1" as="geometry"><Array as="points">'
         '<mxPoint x="100" y="400"/></Array></mxGeometry></mxCell></root></mxGraphModel>')


def _packed(xml: str) -> str:
    raw = urllib.parse.quote(xml, safe="").encode()
    deflater = zlib.compressobj(9, zlib.DEFLATED, -15)
    return base64.b64encode(deflater.compress(raw) + deflater.flush()).decode()


def test_drawio_bounds_groups_and_waypoints():
    from tools.office.drawio import pages

    info = pages(f'<mxfile><diagram name="A">{MODEL}</diagram></mxfile>'.encode())
    assert info[0][1] == (240.0, 300.0)  # del grupo (100) al hijo (100+200+40) y hasta el punto de la flecha (y=400)


def test_drawio_strict_base64_and_budget(monkeypatch):
    from tools.office import drawio

    data = _packed(MODEL)
    with pytest.raises(ToolError) as err:
        drawio.pages(f'<mxfile><diagram name="A">{data[:10]}!*{data[10:]}</diagram></mxfile>'.encode())
    assert err.value.code == "CORRUPT_FILE"
    assert drawio.pages(f'<mxfile><diagram name="A">{data[:10]}\n  {data[10:]}</diagram></mxfile>'.encode())
    monkeypatch.setattr(drawio, "MAX_INFLATED", len(urllib.parse.quote(MODEL, safe="")) * 2 - 10)
    two = "".join(f'<diagram name="{i}">{data}</diagram>' for i in range(2))
    with pytest.raises(ToolError) as err:
        drawio.pages(f"<mxfile>{two}</mxfile>".encode())
    assert err.value.code == "LIMIT_EXCEEDED"


def test_drawio_png_sends_only_its_page():
    import defusedxml.ElementTree as DET

    from tools.office.drawio import single_page

    root = DET.fromstring(f'<mxfile><diagram name="A">{MODEL}</diagram><diagram name="B">ZZZ</diagram></mxfile>')
    one = single_page("mxfile", root.findall("diagram")[1])
    assert one == '<mxfile><diagram name="B">ZZZ</diagram></mxfile>'
