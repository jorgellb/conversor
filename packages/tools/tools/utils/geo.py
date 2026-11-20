"""Rutas y mapas (7.13, F6-H1, D-220): GPX, KML, KMZ, GeoJSON, Shapefile y CSV con coordenadas.

Todo pasa por un modelo propio (puntos, líneas con sus tramos y polígonos, con nombre, descripción, altura, hora y
atributos). GPX se lee con gpxpy (Apache-2.0) después de comprobarlo con defusedxml (sin entidades ni DTD, 16.4) y se
escribe con gpxpy; KML y GeoJSON se leen y escriben aquí. Las pistas con hora van a KML como `gx:Track`, que guarda la
hora de cada punto, para que GPX ↔ KML no pierda tiempos (16.5). Shapefile usa `ogr2ogr` de GDAL como programa externo
(nunca `osgeo` en el proceso, 11), que además lo pasa a WGS84 con su .prj.
"""
from __future__ import annotations

import json
import math
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.zipguard import check_zip
from tools.base import ToolContext, run_engine
from tools.pdf.common import with_batch_zip

MAX_BYTES = 50 * 1024 * 1024
MAX_POINTS = 2_000_000
KML_NS = "http://www.opengis.net/kml/2.2"
GX_NS = "http://www.google.com/kml/ext/2.2"
LAT_NAMES = ("lat", "latitude", "latitud", "y", "lat_dd")
LON_NAMES = ("lon", "lng", "long", "longitude", "longitud", "x", "lon_dd")
NAME_NAMES = ("name", "nombre", "title", "titulo", "título", "label", "etiqueta")
DESC_NAMES = ("description", "descripcion", "descripción", "desc", "notes", "notas")

NOTES = {
    "es": {"summary": "{points} punto(s), {lines} línea(s) o pista(s) y {polygons} polígono(s).",
           "polygons_dropped": "{n} polígono(s) no se han incluido: GPX solo tiene puntos, rutas y pistas.",
           "bad_rows": "{n} fila(s) sin coordenadas válidas se han saltado.", "bad_coords": "{n} coordenada(s) fuera de rango se han descartado.",
           "columns": "Coordenadas de las columnas «{lat}» y «{lon}».", "empty": "No hay ninguna geometría."},
    "en": {"summary": "{points} point(s), {lines} line(s) or track(s) and {polygons} polygon(s).",
           "polygons_dropped": "{n} polygon(s) were not included: GPX only has points, routes and tracks.",
           "bad_rows": "{n} row(s) without valid coordinates were skipped.", "bad_coords": "{n} out-of-range coordinate(s) were discarded.",
           "columns": "Coordinates from the “{lat}” and “{lon}” columns.", "empty": "There is no geometry."},
}


@dataclass
class Pt:
    lon: float
    lat: float
    ele: float | None = None
    time: datetime | None = None


@dataclass
class Feature:
    kind: str  # point, line, polygon
    parts: list[list[Pt]]  # point: [[pt]]; line: tramos; polygon: anillos (el primero, el exterior)
    name: str = ""
    desc: str = ""
    props: dict = field(default_factory=dict)


class Budget:
    def __init__(self):
        self.points = 0
        self.bad = 0

    def take(self, n: int = 1) -> None:
        self.points += n
        if self.points > MAX_POINTS:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "geo_too_many_points")


def _valid(lon: float, lat: float) -> bool:
    return math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90


def _read(path: Path) -> bytes:
    if path.stat().st_size > MAX_BYTES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Archivo de más de 50 MB")
    return path.read_bytes()


def _safe_xml(raw: bytes):
    import defusedxml.ElementTree as DET
    from defusedxml import DefusedXmlException

    try:
        return DET.fromstring(raw, forbid_dtd=False, forbid_entities=True, forbid_external=True)
    except (DefusedXmlException, ValueError) as exc:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "xml_entities") from exc
    except SyntaxError as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "XML no válido") from exc


def _time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# --- GPX --------------------------------------------------------------------------------------------------------------


def read_gpx(raw: bytes, budget: Budget) -> list[Feature]:
    import gpxpy
    import gpxpy.gpx

    _safe_xml(raw)  # entidades fuera antes de que gpxpy (ElementTree) las expanda
    try:
        gpx = gpxpy.parse(raw.decode("utf-8", errors="replace"))
    except (gpxpy.gpx.GPXException, ValueError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "GPX no válido") from exc

    def pt(p) -> Pt | None:
        if p.latitude is None or p.longitude is None or not _valid(p.longitude, p.latitude):
            budget.bad += 1
            return None
        budget.take()
        return Pt(p.longitude, p.latitude, p.elevation, p.time if p.time is None or p.time.tzinfo else p.time.replace(tzinfo=timezone.utc))

    features = []
    for w in gpx.waypoints:
        p = pt(w)
        if p:
            features.append(Feature("point", [[p]], w.name or "", w.description or w.comment or "",
                                    {k: v for k, v in (("simbolo", w.symbol), ("tipo", w.type)) if v}))
    for r in gpx.routes:
        points = [p for p in (pt(x) for x in r.points) if p]
        if len(points) >= 2:
            features.append(Feature("line", [points], r.name or "", r.description or "", {"gpx": "ruta"}))
    for t in gpx.tracks:
        parts = [[p for p in (pt(x) for x in seg.points) if p] for seg in t.segments]
        parts = [part for part in parts if len(part) >= 2]
        if parts:
            features.append(Feature("line", parts, t.name or "", t.description or "", {"tipo": t.type} if t.type else {}))
    return features


def write_gpx(features: list[Feature], name: str) -> tuple[str, int]:
    import gpxpy.gpx

    gpx = gpxpy.gpx.GPX()
    gpx.name = name
    gpx.creator = "conversor"
    dropped = 0
    for f in features:
        if f.kind == "point":
            p = f.parts[0][0]
            gpx.waypoints.append(gpxpy.gpx.GPXWaypoint(p.lat, p.lon, elevation=p.ele, time=p.time, name=f.name or None,
                                                       description=f.desc or None))
        elif f.kind == "line":
            if f.props.get("gpx") == "ruta" and len(f.parts) == 1:
                route = gpxpy.gpx.GPXRoute(name=f.name or None, description=f.desc or None)
                route.points = [gpxpy.gpx.GPXRoutePoint(p.lat, p.lon, elevation=p.ele, time=p.time) for p in f.parts[0]]
                gpx.routes.append(route)
                continue
            track = gpxpy.gpx.GPXTrack(name=f.name or None, description=f.desc or None)
            for part in f.parts:
                seg = gpxpy.gpx.GPXTrackSegment([gpxpy.gpx.GPXTrackPoint(p.lat, p.lon, elevation=p.ele, time=p.time) for p in part])
                track.segments.append(seg)
            gpx.tracks.append(track)
        else:
            dropped += 1
    return gpx.to_xml(version="1.1"), dropped


# --- KML --------------------------------------------------------------------------------------------------------------


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _coords(text: str, budget: Budget) -> list[Pt]:
    out = []
    for item in (text or "").split():
        parts = item.split(",")
        try:
            lon, lat = float(parts[0]), float(parts[1])
            ele = float(parts[2]) if len(parts) > 2 and parts[2] else None
        except (ValueError, IndexError):
            budget.bad += 1
            continue
        if not _valid(lon, lat):
            budget.bad += 1
            continue
        budget.take()
        out.append(Pt(lon, lat, ele if ele is not None and math.isfinite(ele) else None))
    return out


def _geometries(el, budget: Budget) -> list[tuple[str, list[list[Pt]]]]:
    """(tipo, partes) de cada geometría de un Placemark, también dentro de MultiGeometry y gx:MultiTrack."""
    local = el.tag.rsplit("}", 1)[-1]
    if local in ("MultiGeometry", "MultiTrack"):
        out = []
        for child in el:
            out += _geometries(child, budget)
        return out
    if local == "Point":
        pts = _coords(el.findtext(_q(KML_NS, "coordinates")) or "", budget)
        return [("point", [pts[:1]])] if pts else []
    if local in ("LineString", "LinearRing"):
        pts = _coords(el.findtext(_q(KML_NS, "coordinates")) or "", budget)
        return [("line", [pts])] if len(pts) >= 2 else []
    if local == "Polygon":
        rings = []
        for boundary in ("outerBoundaryIs", "innerBoundaryIs"):
            for b in el.findall(_q(KML_NS, boundary)):
                ring = _coords(b.findtext(f"{_q(KML_NS, 'LinearRing')}/{_q(KML_NS, 'coordinates')}") or "", budget)
                if len(ring) >= 4:
                    rings.append(ring)
        return [("polygon", rings)] if rings else []
    if local == "Track":
        whens = [_time(w.text) for w in el.findall(_q(KML_NS, "when"))]
        pts = []
        for i, c in enumerate(el.findall(_q(GX_NS, "coord"))):
            parts = (c.text or "").split()
            try:
                lon, lat = float(parts[0]), float(parts[1])
                ele = float(parts[2]) if len(parts) > 2 else None
            except (ValueError, IndexError):
                budget.bad += 1
                continue
            if not _valid(lon, lat):
                budget.bad += 1
                continue
            budget.take()
            pts.append(Pt(lon, lat, ele, whens[i] if i < len(whens) else None))
        return [("line", [pts])] if len(pts) >= 2 else []
    return []


def read_kml(raw: bytes, budget: Budget) -> list[Feature]:
    root = _safe_xml(raw)
    if not root.tag.endswith("kml") and root.tag.rsplit("}", 1)[-1] not in ("Document", "Folder", "Placemark"):
        raise ToolError(ErrorCode.CORRUPT_FILE, "KML no válido")
    # KML 2.0/2.1 usan otro espacio de nombres: se lee igual con el de 2.2.
    for el in root.iter():
        if el.tag.startswith("{http://earth.google.com/kml/"):
            el.tag = "{" + KML_NS + "}" + el.tag.rsplit("}", 1)[-1]
    features = []
    for pm in root.iter(_q(KML_NS, "Placemark")):
        name = (pm.findtext(_q(KML_NS, "name")) or "").strip()
        desc = (pm.findtext(_q(KML_NS, "description")) or "").strip()
        props = {}
        for data in pm.iter(_q(KML_NS, "Data")):
            props[data.get("name", "")] = data.findtext(_q(KML_NS, "value")) or ""
        for data in pm.iter(_q(KML_NS, "SimpleData")):
            props[data.get("name", "")] = data.text or ""
        when = _time(pm.findtext(f"{_q(KML_NS, 'TimeStamp')}/{_q(KML_NS, 'when')}"))
        geoms = []
        for child in pm:
            geoms += _geometries(child, budget)
        lines = [parts for kind, parts in geoms if kind == "line"]
        if lines and all(k == "line" for k, _ in geoms):
            features.append(Feature("line", [p for parts in lines for p in parts], name, desc, props))
            continue
        for kind, parts in geoms:
            if kind == "point" and when:
                parts[0][0].time = when
            features.append(Feature(kind, parts, name, desc, dict(props)))
    return features


def _kml_coords(points: list[Pt]) -> str:
    return " ".join(f"{p.lon:.7f},{p.lat:.7f}" + (f",{p.ele:.2f}" if p.ele is not None else "") for p in points)


def write_kml(features: list[Feature], name: str) -> bytes:
    import xml.etree.ElementTree as ET

    ET.register_namespace("", KML_NS)
    ET.register_namespace("gx", GX_NS)
    kml = ET.Element(_q(KML_NS, "kml"))
    doc = ET.SubElement(kml, _q(KML_NS, "Document"))
    ET.SubElement(doc, _q(KML_NS, "name")).text = name
    style = ET.SubElement(doc, _q(KML_NS, "Style"), id="linea")
    line = ET.SubElement(style, _q(KML_NS, "LineStyle"))
    ET.SubElement(line, _q(KML_NS, "color")).text = "ff2f6fd6"
    ET.SubElement(line, _q(KML_NS, "width")).text = "3"
    poly = ET.SubElement(style, _q(KML_NS, "PolyStyle"))
    ET.SubElement(poly, _q(KML_NS, "color")).text = "552f6fd6"
    for f in features:
        pm = ET.SubElement(doc, _q(KML_NS, "Placemark"))
        if f.name:
            ET.SubElement(pm, _q(KML_NS, "name")).text = _xml(f.name)
        if f.desc:
            ET.SubElement(pm, _q(KML_NS, "description")).text = _xml(f.desc)
        props = {k: v for k, v in f.props.items() if k and v not in (None, "") and k != "gpx"}
        if props:
            ext = ET.SubElement(pm, _q(KML_NS, "ExtendedData"))
            for k, v in props.items():
                data = ET.SubElement(ext, _q(KML_NS, "Data"), name=_xml(str(k))[:200])
                ET.SubElement(data, _q(KML_NS, "value")).text = _xml(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
        if f.kind == "point":
            p = f.parts[0][0]
            if p.time:
                ts = ET.SubElement(pm, _q(KML_NS, "TimeStamp"))
                ET.SubElement(ts, _q(KML_NS, "when")).text = _iso(p.time)
            pt = ET.SubElement(pm, _q(KML_NS, "Point"))
            ET.SubElement(pt, _q(KML_NS, "coordinates")).text = _kml_coords([p])
            continue
        ET.SubElement(pm, _q(KML_NS, "styleUrl")).text = "#linea"
        parent = pm if len(f.parts) == 1 or f.kind == "polygon" else ET.SubElement(pm, _q(KML_NS, "MultiGeometry"))
        if f.kind == "polygon":
            pg = ET.SubElement(parent, _q(KML_NS, "Polygon"))
            for i, ring in enumerate(f.parts):
                b = ET.SubElement(pg, _q(KML_NS, "outerBoundaryIs" if i == 0 else "innerBoundaryIs"))
                lr = ET.SubElement(b, _q(KML_NS, "LinearRing"))
                ET.SubElement(lr, _q(KML_NS, "coordinates")).text = _kml_coords(ring)
            continue
        for part in f.parts:
            if all(p.time for p in part):
                # gx:Track guarda la hora de cada punto (Google Earth la usa para reproducir la ruta).
                track = ET.SubElement(parent, _q(GX_NS, "Track"))
                ET.SubElement(track, _q(KML_NS, "altitudeMode")).text = "clampToGround"
                for p in part:
                    ET.SubElement(track, _q(KML_NS, "when")).text = _iso(p.time)
                for p in part:
                    ET.SubElement(track, _q(GX_NS, "coord")).text = f"{p.lon:.7f} {p.lat:.7f} {p.ele if p.ele is not None else 0:.2f}"
            else:
                ls = ET.SubElement(parent, _q(KML_NS, "LineString"))
                ET.SubElement(ls, _q(KML_NS, "tessellate")).text = "1"
                ET.SubElement(ls, _q(KML_NS, "coordinates")).text = _kml_coords(part)
    ET.indent(kml)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(kml, encoding="utf-8") + b"\n"


_XML_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


def _xml(text: str) -> str:
    return _XML_BAD.sub("", text)


# --- GeoJSON ------------------------------------------------------------------------------------------------------------


def _gj_pt(c, budget: Budget) -> Pt | None:
    try:
        lon, lat = float(c[0]), float(c[1])
        ele = float(c[2]) if len(c) > 2 and c[2] is not None else None
    except (TypeError, ValueError, IndexError):
        budget.bad += 1
        return None
    if not _valid(lon, lat):
        budget.bad += 1
        return None
    budget.take()
    return Pt(lon, lat, ele)


def read_geojson(raw: bytes, budget: Budget) -> list[Feature]:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, RecursionError) as exc:
        raise ToolError(ErrorCode.CORRUPT_FILE, "GeoJSON no válido") from exc
    items = data.get("features") if isinstance(data, dict) and data.get("type") == "FeatureCollection" else [data]
    if not isinstance(items, list):
        raise ToolError(ErrorCode.CORRUPT_FILE, "GeoJSON no válido")
    features = []

    def geometry(geom, props: dict) -> None:
        if not isinstance(geom, dict):
            return
        kind, c = geom.get("type"), geom.get("coordinates")
        name = str(props.get("name") or props.get("nombre") or props.get("title") or "")
        desc = str(props.get("description") or props.get("descripcion") or props.get("desc") or "")
        rest = {k: v for k, v in props.items() if k not in ("name", "nombre", "title", "description", "descripcion", "desc", "coordTimes", "time")}
        times = props.get("coordTimes")
        try:
            if kind == "Point":
                p = _gj_pt(c, budget)
                if p:
                    p.time = _time(props.get("time")) if isinstance(props.get("time"), str) else None
                    features.append(Feature("point", [[p]], name, desc, rest))
            elif kind == "MultiPoint":
                for item in c:
                    p = _gj_pt(item, budget)
                    if p:
                        features.append(Feature("point", [[p]], name, desc, dict(rest)))
            elif kind in ("LineString", "MultiLineString"):
                lines = [c] if kind == "LineString" else c
                time_lists = [times] if kind == "LineString" else (times or [])
                parts = []
                for i, line in enumerate(lines):
                    pts = []
                    for j, item in enumerate(line):
                        p = _gj_pt(item, budget)
                        if p:
                            tl = time_lists[i] if i < len(time_lists) and isinstance(time_lists[i], list) else []
                            p.time = _time(tl[j]) if j < len(tl) and isinstance(tl[j], str) else None
                            pts.append(p)
                    if len(pts) >= 2:
                        parts.append(pts)
                if parts:
                    features.append(Feature("line", parts, name, desc, rest))
            elif kind in ("Polygon", "MultiPolygon"):
                for polygon in ([c] if kind == "Polygon" else c):
                    rings = [[p for p in (_gj_pt(item, budget) for item in ring) if p] for ring in polygon]
                    rings = [r for r in rings if len(r) >= 4]
                    if rings:
                        features.append(Feature("polygon", rings, name, desc, dict(rest)))
            elif kind == "GeometryCollection":
                for g in geom.get("geometries") or []:
                    geometry(g, props)
        except TypeError as exc:
            raise ToolError(ErrorCode.CORRUPT_FILE, "GeoJSON no válido") from exc

    for item in items:
        if isinstance(item, dict) and item.get("type") == "Feature":
            geometry(item.get("geometry"), item.get("properties") if isinstance(item.get("properties"), dict) else {})
        else:
            geometry(item, {})
    return features


def write_geojson(features: list[Feature]) -> bytes:
    out = []
    for f in features:
        def c(p: Pt) -> list:
            return [round(p.lon, 7), round(p.lat, 7)] + ([round(p.ele, 2)] if p.ele is not None else [])

        props = {**({"name": f.name} if f.name else {}), **({"description": f.desc} if f.desc else {}),
                 **{k: v for k, v in f.props.items() if k != "gpx"}}
        if f.kind == "point":
            p = f.parts[0][0]
            geom = {"type": "Point", "coordinates": c(p)}
            if p.time:
                props["time"] = _iso(p.time)
        elif f.kind == "line":
            lines = [[c(p) for p in part] for part in f.parts]
            geom = {"type": "LineString", "coordinates": lines[0]} if len(lines) == 1 else {"type": "MultiLineString", "coordinates": lines}
            if any(p.time for part in f.parts for p in part):
                times = [[_iso(p.time) if p.time else None for p in part] for part in f.parts]
                props["coordTimes"] = times[0] if len(times) == 1 else times
        else:
            geom = {"type": "Polygon", "coordinates": [[c(p) for p in ring] for ring in f.parts]}
        out.append({"type": "Feature", "geometry": geom, "properties": props})
    return (json.dumps({"type": "FeatureCollection", "features": out}, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


# --- CSV y Shapefile ---------------------------------------------------------------------------------------------------


def _column(header: list[str], names: tuple[str, ...], chosen: str) -> int | None:
    lowered = [h.strip().lower() for h in header]
    if chosen:
        return lowered.index(chosen.strip().lower()) if chosen.strip().lower() in lowered else None
    return next((i for i, h in enumerate(lowered) if h in names), None)


def read_csv_points(ctx: ToolContext, path: Path, budget: Budget) -> tuple[list[Feature], list[str]]:
    from tools.utils.datos import read_csv

    t = NOTES.get(ctx.locale, NOTES["es"])
    o = ctx.options
    rows, _codec, _sep = read_csv(ctx, path, "auto")
    if not rows:
        raise ToolError(ErrorCode.CORRUPT_FILE, "CSV vacío")
    header = rows[0]
    lat_i, lon_i = _column(header, LAT_NAMES, o.columna_latitud), _column(header, LON_NAMES, o.columna_longitud)
    if lat_i is None or lon_i is None:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "geo_no_columns")
    name_i, desc_i = _column(header, NAME_NAMES, ""), _column(header, DESC_NAMES, "")
    features, bad = [], 0
    for row in rows[1:]:
        try:
            lat = float(row[lat_i].strip().replace(",", "."))
            lon = float(row[lon_i].strip().replace(",", "."))
        except (ValueError, IndexError):
            bad += 1
            continue
        if not _valid(lon, lat):
            bad += 1
            continue
        budget.take()
        props = {header[i]: v for i, v in enumerate(row) if i not in (lat_i, lon_i, name_i, desc_i) and i < len(header) and v}
        features.append(Feature("point", [[Pt(lon, lat)]], row[name_i] if name_i is not None and name_i < len(row) else "",
                                row[desc_i] if desc_i is not None and desc_i < len(row) else "", props))
    notes = [t["columns"].format(lat=header[lat_i], lon=header[lon_i])]
    if bad:
        notes.append(t["bad_rows"].format(n=bad))
    return features, notes


def read_kmz(path: Path, budget: Budget) -> list[Feature]:
    check_zip(path)
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".kml") and ".." not in n]
        if not names:
            raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "kmz_no_kml")
        main = "doc.kml" if "doc.kml" in names else min(names, key=lambda n: (n.count("/"), n))
        info = zf.getinfo(main)
        if info.file_size > MAX_BYTES:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "KML de más de 50 MB")
        return read_kml(zf.read(info), budget)


def shapefiles(ctx: ToolContext, path: Path, n: int) -> list[tuple[str, Path]]:
    """Las capas (.shp con su .shx y .dbf) de un ZIP, copiadas con nombres seguros en el directorio del trabajo."""
    check_zip(path)
    out = ctx.work / f"shp-{n}"
    out.mkdir(parents=True, exist_ok=True)
    layers: list[tuple[str, Path]] = []
    with zipfile.ZipFile(path) as zf:
        members = {m.filename.replace("\\", "/"): m for m in zf.infolist() if not m.is_dir() and ".." not in m.filename}
        stems = sorted({k.rsplit(".", 1)[0] for k in members if k.lower().endswith(".shp")})
        for i, stem in enumerate(stems[:20]):
            for ext in ("shp", "shx", "dbf", "prj", "cpg"):
                member = next((k for k in members if k.rsplit(".", 1)[0] == stem and k.lower().endswith("." + ext)), None)
                if member is not None:
                    (out / f"capa{i}.{ext}").write_bytes(zf.read(members[member]))
            if (out / f"capa{i}.shx").exists() and (out / f"capa{i}.dbf").exists():
                layers.append((Path(stem).name, out / f"capa{i}.shp"))
    if not layers:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "shp_incomplete")
    return layers


def read_shapefile(ctx: ToolContext, shp: Path, budget: Budget) -> list[Feature]:
    exe = ctx.settings.OGR2OGR_BIN
    if not Path(exe).is_file():
        raise ToolError(ErrorCode.ENGINE_FAILED, "ogr2ogr no está instalado")
    dst = shp.with_suffix(".geojson")
    # Sin red: GDAL no sigue rutas /vsicurl/ que no le damos, y se le corta el HTTP por si acaso.
    run_engine([exe, "-f", "GeoJSON", "-t_srs", "EPSG:4326", "-lco", "RFC7946=YES", "-lco", "COORDINATE_PRECISION=7",
                str(dst.name), str(shp.name)], cwd=shp.parent, timeout=300, mem_mb=1024,
               extra_env={"GDAL_HTTP_TIMEOUT": "1", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": "none", "GDAL_DISABLE_READDIR_ON_OPEN": "YES"})
    if not dst.exists():
        raise ToolError(ErrorCode.CORRUPT_FILE, "Shapefile ilegible")
    return read_geojson(dst.read_bytes(), budget)


# --- Herramienta ------------------------------------------------------------------------------------------------------

READERS = {"gpx-a-kml": "gpx", "gpx-a-geojson": "gpx", "kml-a-gpx": "kml", "kmz-a-gpx": "kmz", "geojson-a-kml": "geojson",
           "shp-a-geojson": "shp", "shp-a-kml": "shp", "csv-a-kml": "csv"}
TARGETS = {"gpx-a-kml": "kml", "gpx-a-geojson": "geojson", "kml-a-gpx": "gpx", "kmz-a-gpx": "gpx", "geojson-a-kml": "kml",
           "shp-a-geojson": "geojson", "shp-a-kml": "kml", "csv-a-kml": "kml"}


def _summary(t: dict, features: list[Feature]) -> str:
    count = {k: sum(1 for f in features if f.kind == k) for k in ("point", "line", "polygon")}
    return t["summary"].format(points=count["point"], lines=count["line"], polygons=count["polygon"])


def _write(ctx: ToolContext, features: list[Feature], target: str, stem: str, notes: list[str]) -> dict:
    t = NOTES.get(ctx.locale, NOTES["es"])
    if not features:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "geo_empty")
    if target == "gpx":
        text, dropped = write_gpx(features, stem)
        data = text.encode("utf-8")
        if dropped:
            notes.append(t["polygons_dropped"].format(n=dropped))
    elif target == "kml":
        data = write_kml(features, stem)
    else:
        data = write_geojson(features)
    name = f"{stem}.{target}"
    dst = ctx.output(name)
    dst.write_bytes(data)
    return {"path": str(dst), "name": name, "note": " ".join([_summary(t, features), *notes])}


def run(ctx: ToolContext) -> list[dict]:
    t = NOTES.get(ctx.locale, NOTES["es"])
    source, target = READERS[ctx.tool], TARGETS[ctx.tool]
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        budget = Budget()
        stem = Path(inp.name).stem or "mapa"
        notes: list[str] = []
        if source == "shp":
            for layer, shp in shapefiles(ctx, inp.path, n):
                features = read_shapefile(ctx, shp, budget)
                outputs.append(_write(ctx, features, target, layer if layer else stem, notes[:]))
            continue
        if source == "gpx":
            features = read_gpx(_read(inp.path), budget)
        elif source == "kml":
            features = read_kml(_read(inp.path), budget)
        elif source == "kmz":
            features = read_kmz(inp.path, budget)
        elif source == "geojson":
            features = read_geojson(_read(inp.path), budget)
        else:
            features, notes = read_csv_points(ctx, inp.path, budget)
        if budget.bad:
            notes.append(t["bad_coords"].format(n=budget.bad))
        outputs.append(_write(ctx, features, target, stem, notes))
    return with_batch_zip(ctx, outputs, f"{ctx.tool}.zip")
