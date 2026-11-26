"""Shapefile a GeoJSON (RFC 7946, WGS 84) con la GDAL de pyogrio, en un proceso aparte (D-220 y D-267).

Lo lanza ``tools.utils.geo.read_shapefile`` con ``run_engine`` y ``python -I``: GDAL nunca se carga en el proceso del
worker, y aquí solo se importa pyogrio. La GDAL de la rueda de pyogrio va enlazada de forma estática y sin libheif ni
x265 (la de Debian, por libheif1, traía libx265, prohibida en 11). Sin red: sin HTTP ni /vsicurl/, y solo se
convierte lo que GDAL haya abierto con el driver de Shapefile.

    python -I ogr_shp.py ENTRADA.shp SALIDA.geojson [--sin-prj]

Con ``--sin-prj`` (el Shapefile no trae .prj) las coordenadas se toman como WGS 84. RFC7946=YES hace que el driver de
GeoJSON reproyecte a WGS 84 desde el sistema del .prj.
"""
from __future__ import annotations

import sys

GDAL_CONFIG = {
    "GDAL_HTTP_TIMEOUT": "1",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": "none",
    "GDAL_DISABLE_READDIR_ON_OPEN": "YES",
    "GDAL_SKIP": "VRT GML WFS OAPIF",
    "OGR_SKIP": "VRT GML WFS OAPIF",
    "GDAL_HTTP_MAX_RETRY": "0",
}


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3) or not argv[0].lower().endswith(".shp") or not argv[1].endswith(".geojson"):
        print("uso: ogr_shp.py ENTRADA.shp SALIDA.geojson [--sin-prj]", file=sys.stderr)
        return 2
    src, dst, no_prj = argv[0], argv[1], argv[2:] == ["--sin-prj"]
    from pyogrio import raw, read_info, set_gdal_config_options

    set_gdal_config_options(GDAL_CONFIG)
    info = read_info(src)
    if info.get("driver") != "ESRI Shapefile":  # la cabecera ya la mira el llamador (D-226); esto, lo que abrió GDAL
        print(f"no es un Shapefile: {info.get('driver')}", file=sys.stderr)
        return 3
    meta, _fids, geometry, field_data = raw.read(src)
    crs = "EPSG:4326" if no_prj or not meta.get("crs") else meta["crs"]
    raw.write(dst, geometry, field_data, fields=meta["fields"], driver="GeoJSON", crs=crs,
              geometry_type=meta.get("geometry_type") or "Unknown", encoding="UTF-8",
              layer_options={"RFC7946": "YES", "COORDINATE_PRECISION": "7"})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
