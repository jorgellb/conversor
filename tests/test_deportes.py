"""F6-H2 (7.13, D-223): tcx-a-gpx, fit-a-gpx y fit-a-csv con un FIT de prueba escrito aquí (fitparse no escribe)."""
from __future__ import annotations

import csv
import io
import struct
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.errors import ToolError
from test_tools import make_ctx, run  # noqa: F401  (fixture)

pytest.importorskip("fitparse")
CRC = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401, 0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]
FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)


def _crc(data: bytes, crc: int = 0) -> int:
    for byte in data:
        tmp = CRC[crc & 0xF]
        crc = ((crc >> 4) & 0x0FFF) ^ tmp ^ CRC[byte & 0xF]
        tmp = CRC[crc & 0xF]
        crc = ((crc >> 4) & 0x0FFF) ^ tmp ^ CRC[(byte >> 4) & 0xF]
    return crc


def fit(points: list[tuple]) -> bytes:
    """Un FIT con mensajes `record`: (fecha, lat, lon, altura, pulso); lat None para un punto sin GPS."""
    fields = [(253, 4, 0x86), (0, 4, 0x85), (1, 4, 0x85), (2, 2, 0x84), (3, 1, 0x02)]
    body = bytes([0x40, 0, 0]) + struct.pack("<HB", 20, len(fields)) + b"".join(bytes(f) for f in fields)
    for when, lat, lon, alt, hr in points:
        semi = (lambda d: 0x7FFFFFFF if d is None else round(d / 180 * 2**31))
        body += b"\x00" + struct.pack("<Iii", int((when - FIT_EPOCH).total_seconds()), semi(lat), semi(lon))
        body += struct.pack("<HB", round((alt + 500) * 5), hr)
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(body), b".FIT")
    header += struct.pack("<H", _crc(header))
    return header + body + struct.pack("<H", _crc(header + body))


POINTS = [(datetime(2026, 11, 20, 8, 0, s, tzinfo=timezone.utc), 40.4 + s / 10000, -3.7 + s / 10000, 650 + s, 120 + s) for s in range(0, 50, 10)]


def _write(tmp_path: Path, name: str, data: bytes | str) -> Path:
    path = tmp_path / name
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def test_fit_to_gpx_with_heart_rate(make_ctx, tmp_path):
    import gpxpy

    data = fit(POINTS + [(datetime(2026, 11, 20, 8, 1, tzinfo=timezone.utc), None, None, 700, 150)])
    out = run("fit-a-gpx", make_ctx("fit-a-gpx", [_write(tmp_path, "salida.fit", data)]))
    text = Path(out[0]["path"]).read_text()
    gpx = gpxpy.parse(text)
    pts = gpx.tracks[0].segments[0].points
    assert len(pts) == 5 and abs(pts[0].latitude - 40.4) < 1e-6 and pts[1].elevation == 660 and pts[0].time == POINTS[0][0]
    assert "<gpxtpx:hr>130</gpxtpx:hr>" in text and "1 punto(s) sin posición GPS" in out[0]["note"]


def test_fit_to_csv(make_ctx, tmp_path):
    out = run("fit-a-csv", make_ctx("fit-a-csv", [_write(tmp_path, "salida.fit", fit(POINTS))]))
    rows = list(csv.reader(io.StringIO(Path(out[0]["path"]).read_bytes().decode("utf-8-sig"))))
    header = rows[0]
    assert header[:3] == ["timestamp", "position_lat", "position_long"] and {"altitude", "heart_rate"} <= set(header)
    first = dict(zip(header, rows[1]))
    assert first["timestamp"] == "2026-11-20T08:00:00Z" and float(first["position_lat"]) == pytest.approx(40.4, abs=1e-6)
    assert first["heart_rate"] == "120" and out[0]["note"].startswith("5 registro(s) con ")


def test_corrupt_fit(make_ctx, tmp_path):
    data = bytearray(fit(POINTS))
    data[30] ^= 0xFF
    with pytest.raises(ToolError) as err:
        run("fit-a-gpx", make_ctx("fit-a-gpx", [_write(tmp_path, "roto.fit", bytes(data))]))
    assert err.value.code == "CORRUPT_FILE"


TCX = """<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
  xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2">
 <Activities><Activity Sport="Biking"><Id>2026-11-20T08:00:00Z</Id>
  <Lap StartTime="2026-11-20T08:00:00Z"><Track>
   <Trackpoint><Time>2026-11-20T08:00:00Z</Time><Position><LatitudeDegrees>40.4</LatitudeDegrees><LongitudeDegrees>-3.7</LongitudeDegrees></Position>
    <AltitudeMeters>650</AltitudeMeters><HeartRateBpm><Value>120</Value></HeartRateBpm><Cadence>85</Cadence>
    <Extensions><ns3:TPX><ns3:Watts>210</ns3:Watts></ns3:TPX></Extensions></Trackpoint>
   <Trackpoint><Time>2026-11-20T08:00:10Z</Time><Position><LatitudeDegrees>40.401</LatitudeDegrees><LongitudeDegrees>-3.701</LongitudeDegrees></Position></Trackpoint>
   <Trackpoint><Time>2026-11-20T08:00:20Z</Time></Trackpoint>
  </Track></Lap>
  <Lap StartTime="2026-11-20T08:10:00Z"><Track>
   <Trackpoint><Time>2026-11-20T08:10:00Z</Time><Position><LatitudeDegrees>40.41</LatitudeDegrees><LongitudeDegrees>-3.71</LongitudeDegrees></Position></Trackpoint>
   <Trackpoint><Time>2026-11-20T08:10:10Z</Time><Position><LatitudeDegrees>40.411</LatitudeDegrees><LongitudeDegrees>-3.711</LongitudeDegrees></Position></Trackpoint>
  </Track></Lap>
 </Activity></Activities>
</TrainingCenterDatabase>
"""


def test_tcx_to_gpx_laps_and_sensors(make_ctx, tmp_path):
    import gpxpy

    out = run("tcx-a-gpx", make_ctx("tcx-a-gpx", [_write(tmp_path, "bici.tcx", TCX)]))
    text = Path(out[0]["path"]).read_text()
    gpx = gpxpy.parse(text)
    track = gpx.tracks[0]
    assert track.type == "Biking" and len(track.segments) == 2 and track.segments[0].points[0].elevation == 650
    assert "<gpxtpx:hr>120</gpxtpx:hr>" in text and "<gpxtpx:cad>85</gpxtpx:cad>" in text and "<gpxtpx:power>210</gpxtpx:power>" in text
    assert "1 punto(s) sin posición" in out[0]["note"]
    with pytest.raises(ToolError) as err:
        run("tcx-a-gpx", make_ctx("tcx-a-gpx", [_write(tmp_path, "x.tcx", '<?xml version="1.0"?><!DOCTYPE t [<!ENTITY x SYSTEM "file:///etc/passwd">]><t>&x;</t>')]))
    assert err.value.detail == "xml_entities"
