"""Actividades deportivas (7.13, F6-H2, D-223): tcx-a-gpx, fit-a-gpx y fit-a-csv.

- TCX (Garmin Training Center) se lee aquí con defusedxml: actividades con sus vueltas y pistas, y recorridos (Courses).
- FIT (Garmin, Wahoo, Coros, Suunto…) se lee con fitparse (MIT): los mensajes `record` traen la posición en semicírculos,
  la altura, la frecuencia cardiaca, la cadencia, la potencia y la temperatura.
- El GPX lleva la frecuencia cardiaca, la cadencia, la potencia y la temperatura en la extensión TrackPointExtension v2 de
  Garmin, la que leen Strava, Garmin Connect y la mayoría de aplicaciones.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext
from tools.pdf.common import with_batch_zip
from tools.utils.geo import _safe_xml, _time, _valid

MAX_BYTES = 50 * 1024 * 1024
MAX_POINTS = 2_000_000
TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
TPX_NS = "http://www.garmin.com/xmlschemas/TrackPointExtension/v2"
SEMICIRCLE = 180 / 2**31

NOTES = {
    "es": {"summary": "{tracks} pista(s) con {points} punto(s).", "no_gps": "{n} punto(s) sin posición GPS (en cinta o en interior) se han dejado fuera.",
           "rows": "{n} registro(s) con {cols} columnas.", "empty": "La actividad no tiene puntos con posición."},
    "en": {"summary": "{tracks} track(s) with {points} point(s).", "no_gps": "{n} point(s) without a GPS position (treadmill or indoor) were left out.",
           "rows": "{n} record(s) with {cols} columns.", "empty": "The activity has no points with a position."},
}
SENSORS = (("hr", "hr"), ("cad", "cad"), ("power", "power"), ("atemp", "atemp"))


@dataclass
class Point:
    lat: float
    lon: float
    ele: float | None = None
    time: datetime | None = None
    sensors: dict = field(default_factory=dict)


@dataclass
class Track:
    name: str
    kind: str
    segments: list[list[Point]]


def _read(path: Path) -> bytes:
    if path.stat().st_size > MAX_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Archivo de más de 50 MB")
    return path.read_bytes()


def _float(text: str | None) -> float | None:
    try:
        value = float(text) if text is not None else None
    except ValueError:
        return None
    return value if value is None or value == value and abs(value) != float("inf") else None


# --- TCX --------------------------------------------------------------------------------------------------------------


def read_tcx(raw: bytes) -> tuple[list[Track], int]:
    root = _safe_xml(raw)
    if not root.tag.endswith("TrainingCenterDatabase"):
        raise ToolError(ErrorCode.CORRUPT_FILE, "TCX no válido")

    def q(tag: str) -> str:
        return f"{{{TCX_NS}}}{tag}"

    tracks, no_gps, total = [], 0, 0

    def points(track_el) -> list[Point]:
        nonlocal no_gps, total
        out = []
        for tp in track_el.findall(q("Trackpoint")):
            lat = _float(tp.findtext(f"{q('Position')}/{q('LatitudeDegrees')}"))
            lon = _float(tp.findtext(f"{q('Position')}/{q('LongitudeDegrees')}"))
            if lat is None or lon is None or not _valid(lon, lat):
                no_gps += 1
                continue
            total += 1
            if total > MAX_POINTS:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "geo_too_many_points")
            sensors = {}
            hr = _float(tp.findtext(f"{q('HeartRateBpm')}/{q('Value')}"))
            cad = _float(tp.findtext(q("Cadence")))
            if hr is not None:
                sensors["hr"] = int(hr)
            if cad is not None:
                sensors["cad"] = int(cad)
            for ext in tp.iter():
                if ext.tag.endswith("}Watts") and _float(ext.text) is not None:
                    sensors["power"] = int(_float(ext.text))
            out.append(Point(lat, lon, _float(tp.findtext(q("AltitudeMeters"))), _time(tp.findtext(q("Time"))), sensors))
        return out

    for activity in root.iter(q("Activity")):
        segments = [p for p in (points(t) for lap in activity.findall(q("Lap")) for t in lap.findall(q("Track"))) if len(p) >= 2]
        if segments:
            started = activity.findtext(q("Id")) or ""
            tracks.append(Track(f"{activity.get('Sport', 'Actividad')} {started}".strip(), activity.get("Sport", ""), segments))
    for course in root.iter(q("Course")):
        segments = [p for p in (points(t) for t in course.findall(q("Track"))) if len(p) >= 2]
        if segments:
            tracks.append(Track(course.findtext(q("Name")) or "Recorrido", "", segments))
    return tracks, no_gps


# --- FIT --------------------------------------------------------------------------------------------------------------


def fit_records(raw: bytes) -> list[dict]:
    """Los mensajes `record` de un FIT como diccionarios (sin los campos desconocidos)."""
    from fitparse import FitFile
    from fitparse.utils import FitParseError

    try:
        fit = FitFile(io.BytesIO(raw), check_crc=True)
        rows = []
        for message in fit.get_messages("record"):
            row = {}
            for f in message.fields:
                if f.name.startswith("unknown") or f.value is None:
                    continue
                row[f.name] = f.value
            if row:
                rows.append(row)
                if len(rows) > MAX_POINTS:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, "geo_too_many_points")
        return rows
    except ToolError:
        raise
    except (FitParseError, ValueError, KeyError, IndexError, TypeError, EOFError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "FIT no válido") from exc


def fit_track(raw: bytes) -> tuple[list[Track], int]:
    points, no_gps = [], 0
    for row in fit_records(raw):
        lat, lon = row.get("position_lat"), row.get("position_long")
        if not isinstance(lat, int) or not isinstance(lon, int):
            no_gps += 1
            continue
        lat, lon = lat * SEMICIRCLE, lon * SEMICIRCLE
        if not _valid(lon, lat):
            no_gps += 1
            continue
        ele = row.get("enhanced_altitude", row.get("altitude"))
        when = row.get("timestamp")
        if isinstance(when, datetime) and when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        sensors = {k: int(row[f]) for k, f in (("hr", "heart_rate"), ("cad", "cadence"), ("power", "power")) if isinstance(row.get(f), (int, float))}
        if isinstance(row.get("temperature"), (int, float)):
            sensors["atemp"] = int(row["temperature"])
        points.append(Point(lat, lon, float(ele) if isinstance(ele, (int, float)) else None, when if isinstance(when, datetime) else None, sensors))
    return ([Track("Actividad", "", [points])] if len(points) >= 2 else []), no_gps


def fit_csv(raw: bytes) -> tuple[bytes, int, int]:
    """Cada registro en una fila, con la posición en grados; columnas en el orden en que aparecen."""
    rows = fit_records(raw)
    columns: dict[str, None] = {}
    for row in rows:
        for k in row:
            columns.setdefault(k, None)
    header = list(columns)
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        out = []
        for k in header:
            v = row.get(k)
            if k in ("position_lat", "position_long") and isinstance(v, int):
                v = round(v * SEMICIRCLE, 7)
            if isinstance(v, datetime):
                v = (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat().replace("+00:00", "Z")
            out.append("" if v is None else v)
        writer.writerow(out)
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"), len(rows), len(header)


# --- GPX con extensiones ----------------------------------------------------------------------------------------------


def write_gpx(tracks: list[Track], name: str) -> bytes:
    import xml.etree.ElementTree as ET

    import gpxpy.gpx

    gpx = gpxpy.gpx.GPX()
    gpx.name = name
    gpx.creator = "conversor"
    gpx.nsmap["gpxtpx"] = TPX_NS
    for t in tracks:
        track = gpxpy.gpx.GPXTrack(name=t.name or None)
        track.type = t.kind or None
        for seg in t.segments:
            segment = gpxpy.gpx.GPXTrackSegment()
            for p in seg:
                point = gpxpy.gpx.GPXTrackPoint(p.lat, p.lon, elevation=p.ele, time=p.time)
                if p.sensors:
                    ext = ET.Element(f"{{{TPX_NS}}}TrackPointExtension")
                    for key, tag in SENSORS:
                        if key in p.sensors:
                            ET.SubElement(ext, f"{{{TPX_NS}}}{tag}").text = str(p.sensors[key])
                    point.extensions.append(ext)
                segment.points.append(point)
            track.segments.append(segment)
        gpx.tracks.append(track)
    return gpx.to_xml(version="1.1").encode("utf-8")


def run(ctx: ToolContext) -> list[dict]:
    t = NOTES.get(ctx.locale, NOTES["es"])
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        stem = Path(inp.name).stem or "actividad"
        raw = _read(inp.path)
        if ctx.tool == "fit-a-csv":
            data, rows, cols = fit_csv(raw)
            name, notes = f"{stem}.csv", [t["rows"].format(n=rows, cols=cols)]
        else:
            tracks, no_gps = read_tcx(raw) if ctx.tool == "tcx-a-gpx" else fit_track(raw)
            if not tracks:
                raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "geo_empty")
            points = sum(len(s) for tr in tracks for s in tr.segments)
            notes = [t["summary"].format(tracks=len(tracks), points=points)]
            if no_gps:
                notes.append(t["no_gps"].format(n=no_gps))
            data, name = write_gpx(tracks, stem), f"{stem}.gpx"
        dst = ctx.output(name)
        dst.write_bytes(data)
        outputs.append({"path": str(dst), "name": name, "note": " ".join(notes)})
    return with_batch_zip(ctx, outputs, f"{ctx.tool}.zip")
