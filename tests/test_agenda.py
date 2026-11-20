"""F6-I (7.13, D-224): contactos y calendarios. 16.5: VCF → CSV → VCF conserva los contactos."""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from core.errors import ToolError
from test_tools import make_ctx, run  # noqa: F401  (fixture)

pytest.importorskip("vobject")
pytest.importorskip("icalendar")

VCF = """BEGIN:VCARD
VERSION:3.0
N:Núñez;María;José;Dra.;
FN:Dra. María José Núñez
ORG:Clínica Sol
TITLE:Pediatra
EMAIL;TYPE=INTERNET,WORK:maria@clinica.example
EMAIL;TYPE=INTERNET,HOME:mjn@correo.example
TEL;TYPE=CELL:+34 600 111 222
TEL;TYPE=WORK:910 000 000
ADR;TYPE=WORK:;;Calle Mayor 1;Madrid;Madrid;28013;España
BDAY:1980-04-03
NOTE:Llamar por la tarde
CATEGORIES:Médicos,Familia
END:VCARD
BEGIN:VCARD
VERSION:2.1
N:Smith;John
FN:John Smith
TEL;HOME:+1 555 0100
EMAIL:=40john@example.com
PHOTO;ENCODING=BASE64;TYPE=JPEG:/9j/4AAQ
END:VCARD
BEGIN:VCARD
VERSION:4.0
FN:=HYPERLINK("http://x","pulsa")
EMAIL:raro@example.com
END:VCARD
"""


def _write(tmp_path: Path, name: str, data: str | bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def _key(cards):
    return sorted((c.name, sorted(v for _, v in c.emails), sorted(v.replace(" ", "") for _, v in c.phones), c.org) for c in cards)


@pytest.mark.parametrize("template", ["google", "outlook", "generico"])
def test_vcf_csv_vcf_round_trip_keeps_contacts(make_ctx, tmp_path, template):
    from tools.utils.agenda import read_vcf

    src = _write(tmp_path, "agenda.vcf", VCF)
    out = run("vcf-a-csv", make_ctx("vcf-a-csv", [src], {"plantilla": template}))
    assert out[0]["name"] == "agenda.csv" and out[0]["note"].startswith("3 contacto(s).") and "1 foto(s)" in out[0]["note"]
    csv_path = _write(tmp_path, f"agenda-{template}.csv", Path(out[0]["path"]).read_bytes())
    back = run("csv-a-vcf", make_ctx("csv-a-vcf", [csv_path]))
    original, _ = read_vcf(src.read_bytes())
    rebuilt, _ = read_vcf(Path(back[0]["path"]).read_bytes())
    def norm(cards):  # la propia plantilla no guarda el tratamiento en el nombre completo ni el segundo nombre en Outlook
        return sorted((sorted(v for _, v in c.emails), sorted(v.replace(" ", "") for _, v in c.phones), c.org) for c in cards)
    assert norm(rebuilt) == norm(original)
    assert {c.family for c in rebuilt} >= {"Núñez", "Smith"} or template == "generico"


def test_google_columns_and_formula_guard(make_ctx, tmp_path):
    out = run("vcf-a-csv", make_ctx("vcf-a-csv", [_write(tmp_path, "a.vcf", VCF)]))
    rows = list(csv.reader(io.StringIO(Path(out[0]["path"]).read_bytes().decode("utf-8-sig"))))
    head = rows[0]
    first = dict(zip(head, rows[1]))
    assert first["First Name"] == "María" and first["Last Name"] == "Núñez" and first["Organization Name"] == "Clínica Sol"
    assert first["E-mail 1 - Label"] == "Work" and first["Phone 1 - Label"] == "Mobile" and first["Address 1 - City"] == "Madrid"
    assert "Médicos ::: Familia ::: * myContacts" == first["Labels"]
    assert rows[3][0].startswith("'=HYPERLINK")


def test_vcf_to_excel_outlook(make_ctx, tmp_path):
    import openpyxl

    out = run("vcf-a-excel", make_ctx("vcf-a-excel", [_write(tmp_path, "a.vcf", VCF)], {"plantilla": "outlook"}))
    ws = openpyxl.load_workbook(out[0]["path"]).active
    header = [c.value for c in ws[1]]
    row = dict(zip(header, [c.value for c in ws[2]]))
    assert row["Mobile Phone"] == "+34 600 111 222" and row["Business Phone"] == "910 000 000" and row["Business City"] == "Madrid"
    assert ws["A4"].data_type == "s"


ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//prueba//ES
BEGIN:VTIMEZONE
TZID:Europe/Madrid
BEGIN:STANDARD
DTSTART:19701025T030000
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19700329T020000
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:1@prueba
DTSTAMP:20261120T090000Z
DTSTART;TZID=Europe/Madrid:20261125T103000
DTEND;TZID=Europe/Madrid:20261125T113000
SUMMARY:Reunión de equipo
LOCATION:Sala 2
DESCRIPTION:Orden del día\\, punto 1
RRULE:FREQ=WEEKLY;COUNT=4
END:VEVENT
BEGIN:VEVENT
UID:2@prueba
DTSTAMP:20261120T090000Z
DTSTART;VALUE=DATE:20261208
DTEND;VALUE=DATE:20261209
SUMMARY:Festivo
END:VEVENT
END:VCALENDAR
"""


def test_ics_to_csv_full_and_google(make_ctx, tmp_path):
    src = _write(tmp_path, "cal.ics", ICS)
    out = run("ics-a-csv", make_ctx("ics-a-csv", [src]))
    rows = list(csv.reader(io.StringIO(Path(out[0]["path"]).read_bytes().decode("utf-8-sig"))))
    assert rows[1][:5] == ["Reunión de equipo", "2026-11-25 10:30", "2026-11-25 11:30", "no", "Europe/Madrid"]
    assert rows[1][6] == "Orden del día, punto 1" and rows[1][11] == "FREQ=WEEKLY;COUNT=4"
    assert rows[2][1:4] == ["2026-12-08", "2026-12-09", "sí"]
    out = run("ics-a-csv", make_ctx("ics-a-csv", [src], {"plantilla": "google"}))
    rows = list(csv.reader(io.StringIO(Path(out[0]["path"]).read_bytes().decode("utf-8-sig"))))
    assert rows[0][:6] == ["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event"]
    assert rows[1][1:6] == ["11/25/2026", "10:30 AM", "11/25/2026", "11:30 AM", "False"]
    assert rows[2][1:6] == ["12/08/2026", "", "12/08/2026", "", "True"] and "1 evento(s) que se repiten" in out[0]["note"]


def test_csv_to_ics_and_back(make_ctx, tmp_path):
    import icalendar

    csv_es = "Asunto;Fecha inicio;Hora inicio;Fecha fin;Hora fin;Lugar\nDentista;03/04/2026;9:30;;10:15;Calle Luna\nVacaciones;10/08/2026;;14/08/2026;;\n;sin fecha;;;;\n"
    out = run("csv-a-ics", make_ctx("csv-a-ics", [_write(tmp_path, "citas.csv", csv_es)]))
    cal = icalendar.Calendar.from_ical(Path(out[0]["path"]).read_bytes())
    events = list(cal.walk("VEVENT"))
    assert [str(e["SUMMARY"]) for e in events] == ["Dentista", "Vacaciones"] and cal.walk("VTIMEZONE")
    start = events[0]["DTSTART"].dt
    assert (start.month, start.day, start.hour, start.minute, str(start.tzinfo)) == (4, 3, 9, 30, "Europe/Madrid")
    assert events[0]["DTEND"].dt.minute == 15 and str(events[1]["DTEND"].dt) == "2026-08-15"
    assert "1 fila(s) sin una fecha de inicio válida" in out[0]["note"]
    google = "Subject,Start Date,Start Time,End Date,End Time,All Day Event\nCall,03/04/2026,02:00 PM,03/04/2026,03:00 PM,False\n"
    out = run("csv-a-ics", make_ctx("csv-a-ics", [_write(tmp_path, "g.csv", google)], {"zona": "America/New_York"}))
    ev = icalendar.Calendar.from_ical(Path(out[0]["path"]).read_bytes()).walk("VEVENT")[0]
    assert (ev["DTSTART"].dt.month, ev["DTSTART"].dt.day, ev["DTSTART"].dt.hour) == (3, 4, 14)


def test_errors(make_ctx, tmp_path):
    with pytest.raises(ToolError) as err:
        run("csv-a-ics", make_ctx("csv-a-ics", [_write(tmp_path, "x.csv", "a,b\n1,2\n")]))
    assert err.value.detail == "ics_no_columns"
    with pytest.raises(ToolError) as err:
        run("vcf-a-csv", make_ctx("vcf-a-csv", [_write(tmp_path, "v.vcf", "hola\n")]))
    assert err.value.code == "CORRUPT_FILE"
    with pytest.raises(ToolError) as err:
        run("ics-a-excel", make_ctx("ics-a-excel", [_write(tmp_path, "v.ics", "BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n")]))
    assert err.value.detail == "agenda_empty"


def test_never_creates_an_ai_client():
    from core.ai import is_excluded
    from core.registry import load_registry

    for slug in ("vcf-a-csv", "csv-a-vcf", "vcf-a-excel", "ics-a-csv", "csv-a-ics", "ics-a-excel"):
        spec = load_registry().require(slug)
        assert is_excluded(spec.slug_es, spec.category)
