"""F6-H1 (7.13, D-220): GPX, KML, KMZ, GeoJSON, Shapefile y CSV. 16.5: GPX ↔ KML conserva puntos, alturas y horas."""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from core.errors import ToolError
from core.settings import get_settings
from test_tools import make_ctx, run  # noqa: F401  (fixture)

pytest.importorskip("gpxpy")

GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="prueba" xmlns="http://www.topografix.com/GPX/1/1">
  <wpt lat="40.4168" lon="-3.7038"><ele>657</ele><name>Sol</name><desc>Kilómetro cero</desc></wpt>
  <rte><name>Ruta corta</name><rtept lat="40.41" lon="-3.70"/><rtept lat="40.42" lon="-3.71"/></rte>
  <trk><name>Paseo por el Retiro</name>
    <trkseg>
      <trkpt lat="40.4150" lon="-3.6840"><ele>650.5</ele><time>2026-11-20T09:00:00Z</time></trkpt>
      <trkpt lat="40.4160" lon="-3.6830"><ele>651.0</ele><time>2026-11-20T09:01:00Z</time></trkpt>
      <trkpt lat="40.4170" lon="-3.6820"><ele>652.25</ele><time>2026-11-20T09:02:30Z</time></trkpt>
    </trkseg>
    <trkseg>
      <trkpt lat="40.4180" lon="-3.6810"><time>2026-11-20T09:10:00Z</time></trkpt>
      <trkpt lat="40.4190" lon="-3.6800"><time>2026-11-20T09:11:00Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>
"""


def _write(tmp_path: Path, name: str, data: str | bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def _copy(tmp_path: Path, out: list[dict], i: int = 0) -> Path:
    dst = tmp_path / out[i]["name"]
    shutil.copyfile(out[i]["path"], dst)
    return dst


def test_gpx_kml_gpx_round_trip_keeps_points_elevation_and_times(make_ctx, tmp_path):
    import gpxpy

    kml_out = run("gpx-a-kml", make_ctx("gpx-a-kml", [_write(tmp_path, "paseo.gpx", GPX)]))
    kml = _copy(tmp_path, kml_out)
    text = kml.read_text()
    assert kml_out[0]["name"] == "paseo.kml" and "<gx:Track>" in text and "<name>Sol</name>" in text
    assert kml_out[0]["note"].startswith("1 punto(s), 2 línea(s) o pista(s) y 0 polígono(s)")
    back = run("kml-a-gpx", make_ctx("kml-a-gpx", [kml]))
    gpx = gpxpy.parse(Path(back[0]["path"]).read_text())
    original = gpxpy.parse(GPX)
    assert [(w.name, round(w.latitude, 6), round(w.longitude, 6), w.elevation) for w in gpx.waypoints] == [("Sol", 40.4168, -3.7038, 657.0)]
    track = next(t for t in gpx.tracks if t.name == "Paseo por el Retiro")
    for seg_a, seg_b in zip(original.tracks[0].segments, track.segments):
        assert [(round(p.latitude, 6), round(p.longitude, 6), p.time) for p in seg_a.points] == \
               [(round(p.latitude, 6), round(p.longitude, 6), p.time) for p in seg_b.points]
    assert [p.elevation for p in track.segments[0].points] == [650.5, 651.0, 652.25]
    assert len(gpx.routes) == 1 or any(t.name == "Ruta corta" for t in gpx.tracks)


def test_gpx_to_geojson_and_geojson_to_kml(make_ctx, tmp_path):
    out = run("gpx-a-geojson", make_ctx("gpx-a-geojson", [_write(tmp_path, "paseo.gpx", GPX)]))
    data = json.loads(Path(out[0]["path"]).read_text())
    kinds = [f["geometry"]["type"] for f in data["features"]]
    assert kinds == ["Point", "LineString", "MultiLineString"]
    track = data["features"][2]
    assert track["properties"]["name"] == "Paseo por el Retiro" and track["properties"]["coordTimes"][0][0] == "2026-11-20T09:00:00Z"
    assert track["geometry"]["coordinates"][0][0] == [-3.684, 40.415, 650.5]
    poly = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Parcela", "uso": "huerta", "superficie": 120},
         "geometry": {"type": "Polygon", "coordinates": [[[-3.7, 40.4], [-3.69, 40.4], [-3.69, 40.41], [-3.7, 40.4]]]}},
        {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [500, 40]}}]}
    out = run("geojson-a-kml", make_ctx("geojson-a-kml", [_write(tmp_path, "parcelas.geojson", json.dumps(poly))]))
    text = Path(out[0]["path"]).read_text()
    assert "<Polygon>" in text and '<Data name="uso">' in text and "1 coordenada(s) fuera de rango" in out[0]["note"]


def test_kml_polygons_are_dropped_from_gpx_and_kmz(make_ctx, tmp_path):
    kml = ('<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Folder>'
           '<Placemark><name>Zona</name><Polygon><outerBoundaryIs><LinearRing><coordinates>-3.7,40.4 -3.69,40.4 -3.69,40.41 -3.7,40.4'
           '</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>'
           '<Placemark><name>Casa</name><Point><coordinates>-3.7,40.4,10</coordinates></Point></Placemark>'
           '<Placemark><MultiGeometry><LineString><coordinates>-3.7,40.4 -3.6,40.5</coordinates></LineString>'
           '<LineString><coordinates>-3.6,40.5 -3.5,40.6</coordinates></LineString></MultiGeometry></Placemark>'
           '</Folder></Document></kml>')
    out = run("kml-a-gpx", make_ctx("kml-a-gpx", [_write(tmp_path, "zonas.kml", kml)]))
    assert "1 polígono(s) no se han incluido" in out[0]["note"]
    import gpxpy

    gpx = gpxpy.parse(Path(out[0]["path"]).read_text())
    assert gpx.waypoints[0].name == "Casa" and len(gpx.tracks[0].segments) == 2
    kmz = tmp_path / "zonas.kmz"
    with zipfile.ZipFile(kmz, "w") as zf:
        zf.writestr("doc.kml", kml)
        zf.writestr("files/icono.png", b"\x89PNG")
    out = run("kmz-a-gpx", make_ctx("kmz-a-gpx", [kmz]))
    assert out[0]["name"] == "zonas.gpx"


def test_csv_to_kml_detects_columns_and_decimal_comma(make_ctx, tmp_path):
    csv = "nombre;latitud;longitud;teléfono\nBar Pepe;40,4168;-3,7038;600111222\nSin sitio;;\nLejos;95;0\n"
    out = run("csv-a-kml", make_ctx("csv-a-kml", [_write(tmp_path, "bares.csv", csv.encode("cp1252"))]))
    text = Path(out[0]["path"]).read_text()
    assert "<name>Bar Pepe</name>" in text and "-3.7038000,40.4168000" in text and '<Data name="teléfono">' in text
    assert "2 fila(s) sin coordenadas válidas" in out[0]["note"] and "«latitud» y «longitud»" in out[0]["note"]
    with pytest.raises(ToolError) as err:
        run("csv-a-kml", make_ctx("csv-a-kml", [_write(tmp_path, "otros.csv", "a,b\n1,2\n")]))
    assert err.value.detail == "geo_no_columns"
    out = run("csv-a-kml", make_ctx("csv-a-kml", [_write(tmp_path, "otros.csv", "a,b\n40,-3\n")],
                                    {"columna_latitud": "A", "columna_longitud": "b"}))
    assert "-3.0000000,40.0000000" in Path(out[0]["path"]).read_text()


@pytest.mark.parametrize("tool,name,data", [
    ("gpx-a-kml", "xxe.gpx", '<?xml version="1.0"?><!DOCTYPE g [<!ENTITY x SYSTEM "file:///etc/hostname">]><gpx>&x;</gpx>'),
    ("kml-a-gpx", "bomba.kml", '<?xml version="1.0"?><!DOCTYPE k [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><kml>&b;</kml>'),
])
def test_xml_entities_rejected(make_ctx, tmp_path, tool, name, data):
    with pytest.raises(ToolError) as err:
        run(tool, make_ctx(tool, [_write(tmp_path, name, data)]))
    assert err.value.detail == "xml_entities"


def test_empty_and_point_limit(make_ctx, tmp_path, monkeypatch):
    from tools.utils import geo

    with pytest.raises(ToolError) as err:
        run("geojson-a-kml", make_ctx("geojson-a-kml", [_write(tmp_path, "v.geojson", '{"type": "FeatureCollection", "features": []}')]))
    assert err.value.detail == "geo_empty"
    monkeypatch.setattr(geo, "MAX_POINTS", 3)
    with pytest.raises(ToolError) as err:
        run("gpx-a-kml", make_ctx("gpx-a-kml", [_write(tmp_path, "p.gpx", GPX)]))
    assert err.value.detail == "geo_too_many_points"


def test_shapefile_zip_needs_its_parts(make_ctx, tmp_path):
    bad = tmp_path / "capa.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("capa.shp", b"x")
    with pytest.raises(ToolError) as err:
        run("shp-a-geojson", make_ctx("shp-a-geojson", [bad]))
    assert err.value.detail == "shp_incomplete"


@pytest.mark.skipif(not Path(get_settings().OGR2OGR_BIN).is_file(), reason="sin ogr2ogr (gdal-bin, en la CI)")
def test_shapefile_with_ogr2ogr(make_ctx, tmp_path):
    import subprocess

    src = _write(tmp_path, "pts.geojson", json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"nombre": "A"}, "geometry": {"type": "Point", "coordinates": [-3.7, 40.4]}}]}))
    subprocess.run([str(get_settings().OGR2OGR_BIN), "-f", "ESRI Shapefile", "-t_srs", "EPSG:25830", str(tmp_path / "pts.shp"), str(src)], check=True)
    packed = tmp_path / "puntos.zip"
    with zipfile.ZipFile(packed, "w") as zf:
        for ext in ("shp", "shx", "dbf", "prj"):
            zf.write(tmp_path / f"pts.{ext}", f"datos/pts.{ext}")
    out = run("shp-a-geojson", make_ctx("shp-a-geojson", [packed]))
    data = json.loads(Path(out[0]["path"]).read_text())
    lon, lat = data["features"][0]["geometry"]["coordinates"][:2]
    assert abs(lon + 3.7) < 1e-5 and abs(lat - 40.4) < 1e-5 and data["features"][0]["properties"]["nombre"] == "A"
    out = run("shp-a-kml", make_ctx("shp-a-kml", [packed]))
    assert out[0]["name"] == "pts.kml"


# --- Revisión de F6-H1 (D-226) -----------------------------------------------------------------------------------------


def test_disguised_vrt_in_a_shapefile_zip_is_refused(make_ctx, tmp_path):
    vrt = b'<OGRVRTDataSource><OGRVRTLayer name="x"><SrcDataSource>CSV:/etc/passwd</SrcDataSource></OGRVRTLayer></OGRVRTDataSource>'
    packed = tmp_path / "trampa.zip"
    with zipfile.ZipFile(packed, "w") as zf:
        zf.writestr("pts.shp", vrt)
        zf.writestr("pts.shx", b"\x00\x00\x27\x0a" + bytes(96))
        zf.writestr("pts.dbf", b"\x03" + bytes(40))
    with pytest.raises(ToolError) as err:
        run("shp-a-geojson", make_ctx("shp-a-geojson", [packed]))
    assert err.value.detail == "shp_not_shapefile"


def test_round_trip_keeps_missing_elevation_routes_and_waypoint_symbols(make_ctx, tmp_path):
    import gpxpy

    gpx = ('<?xml version="1.0" encoding="ISO-8859-1"?><gpx version="1.1" creator="x" xmlns="http://www.topografix.com/GPX/1/1">'
           '<wpt lat="40" lon="-3"><name>Peña</name><sym>Flag</sym><type>Cumbre</type></wpt>'
           '<rte><name>Ruta</name><rtept lat="40.1" lon="-3.1"/><rtept lat="40.2" lon="-3.2"/></rte>'
           '<trk><trkseg><trkpt lat="40.3" lon="-3.3"><time>2026-11-20T09:00:00Z</time></trkpt>'
           '<trkpt lat="40.4" lon="-3.4"><time>2026-11-20T09:01:00Z</time></trkpt></trkseg>'
           '<trkseg><trkpt lat="41" lon="-4"/></trkseg></trk></gpx>').encode("latin-1")
    kml_out = run("gpx-a-kml", make_ctx("gpx-a-kml", [_write(tmp_path, "r.gpx", gpx)]))
    assert "1 tramo(s) o ruta(s) de un solo punto" in kml_out[0]["note"]
    back = gpxpy.parse(Path(run("kml-a-gpx", make_ctx("kml-a-gpx", [_copy(tmp_path, kml_out)]))[0]["path"]).read_text())
    wpt = back.waypoints[0]
    assert (wpt.name, wpt.symbol, wpt.type) == ("Peña", "Flag", "Cumbre")
    assert [r.name for r in back.routes] == ["Ruta"]
    assert [p.elevation for p in back.tracks[0].segments[0].points] == [None, None]


def test_kml_without_namespace_nan_and_uppercase_names(make_ctx, tmp_path):
    kml = "<kml><Document><Placemark><name>A</name><Point><coordinates>-3,40</coordinates></Point></Placemark></Document></kml>"
    out = run("kml-a-gpx", make_ctx("kml-a-gpx", [_write(tmp_path, "s.kml", kml)]))
    assert out[0]["note"].startswith("1 punto(s)")
    with pytest.raises(ToolError) as err:
        run("geojson-a-kml", make_ctx("geojson-a-kml", [_write(tmp_path, "n.geojson", '{"type":"Point","coordinates":[NaN, 1]}')]))
    assert err.value.code == "CORRUPT_FILE"
    upper = json.dumps({"type": "Feature", "properties": {"NOMBRE": "Parcela 7"}, "geometry": {"type": "Point", "coordinates": [-3, 40]}})
    text = Path(run("geojson-a-kml", make_ctx("geojson-a-kml", [_write(tmp_path, "u.geojson", upper)]))[0]["path"]).read_text()
    assert "<name>Parcela 7</name>" in text


def test_csv_rows_with_extra_fields_are_skipped(make_ctx, tmp_path):
    out = run("csv-a-kml", make_ctx("csv-a-kml", [_write(tmp_path, "c.csv", "nombre,lat,lon\nA,40,1,-3,2\nB,41,-3\n")]))
    assert out[0]["note"].startswith("1 punto(s)") and "1 fila(s) sin coordenadas" in out[0]["note"]
