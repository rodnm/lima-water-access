"""Extract water infrastructure and populated places from OpenStreetMap.

Primary source: local Geofabrik PBF file (processed with GDAL ogr2ogr).
Fallback: Overpass API if PBF is not available.
"""
from __future__ import annotations

import subprocess
import sys

import geopandas as gpd
import pandas as pd

from .config import CRS_UTM18S, DATA_RAW, OSM_PBF

# HSTORE parser: "key"=>"value","key2"=>"value2" -> dict
_HSTORE_RE = __import__("re").compile(r'"([^"]+)"=>"([^"]*)"')

TAGS_INFRA = {
    "man_made": ["water_tower", "water_works", "pumping_station", "storage_tank"],
    "amenity": ["drinking_water"],
    "landuse": ["reservoir"],
    "waterway": ["water_point"],
}

TAGS_LUGARES = {
    "place": [
        "suburb", "neighbourhood", "quarter", "town",
        "village", "hamlet", "locality",
    ],
}

LIMA_BBOX = (-77.20, -12.55, -76.65, -11.55)


def extract_infra_agua() -> gpd.GeoDataFrame:
    gdf = _get_or_export_points()
    points = gdf[_match_tags(gdf, TAGS_INFRA)].copy()

    gdf_mp = _get_or_export_multipolygons()
    polys = gdf_mp[_match_tags(gdf_mp, TAGS_INFRA)].copy()
    if len(polys) > 0:
        polys["geometry"] = polys.geometry.centroid
        points = pd.concat([points, polys], ignore_index=True)

    if len(points) == 0:
        return _fallback_overpass(TAGS_INFRA, "water infrastructure")

    points = points.to_crs(epsg=CRS_UTM18S)
    points["category"] = _derive_category(points, TAGS_INFRA)
    return points


def extract_lugares_poblados() -> gpd.GeoDataFrame:
    gdf = _get_or_export_points()
    lugares = gdf[_match_tags(gdf, TAGS_LUGARES)].copy()

    if len(lugares) == 0:
        return _fallback_overpass(TAGS_LUGARES, "populated places")

    return lugares.to_crs(epsg=CRS_UTM18S)


def _get_or_export_points() -> gpd.GeoDataFrame:
    cache_path = DATA_RAW / "lima_points.geojson"
    if not cache_path.exists():
        _run_ogr2ogr(OSM_PBF, cache_path, "points")
    return gpd.read_file(cache_path)


def _get_or_export_multipolygons() -> gpd.GeoDataFrame:
    cache_path = DATA_RAW / "lima_multipolygons.geojson"
    if not cache_path.exists():
        _run_ogr2ogr(OSM_PBF, cache_path, "multipolygons")
    return gpd.read_file(cache_path)


def _run_ogr2ogr(pbf_path, output_path, layer):
    ogr2ogr = _find_ogr2ogr()
    bbox_str = f"{LIMA_BBOX[0]} {LIMA_BBOX[1]} {LIMA_BBOX[2]} {LIMA_BBOX[3]}"
    cmd = [ogr2ogr, "-f", "GeoJSON", str(output_path), str(pbf_path),
           "-spat"] + bbox_str.split() + [layer]
    subprocess.run(cmd, check=True, capture_output=True)


def _find_ogr2ogr():
    import shutil
    exe = shutil.which("ogr2ogr")
    if exe:
        return exe
    candidates = [
        r"C:\tools\Anaconda3\Library\bin\ogr2ogr.exe",
        r"C:\OSGeo4W\bin\ogr2ogr.exe",
        r"C:\Program Files\QGIS*\bin\ogr2ogr.exe",
    ]
    for c in candidates:
        if __import__("pathlib").Path(c).exists():
            return c
    raise FileNotFoundError(
        "ogr2ogr not found. Install GDAL or ensure it is on PATH."
    )


def _match_tags(gdf: gpd.GeoDataFrame, tag_config: dict) -> pd.Series:
    other = gdf.get("other_tags", pd.Series(dtype=str))
    parsed = other.apply(_parse_hstore)
    mask = pd.Series(False, index=gdf.index)
    for key, values in tag_config.items():
        col = parsed.apply(lambda d: d.get(key) if isinstance(d, dict) else None)
        mask |= col.isin(values)
    return mask


def _parse_hstore(hstore_str):
    if not isinstance(hstore_str, str):
        return {}
    return dict(_HSTORE_RE.findall(hstore_str))


def _derive_category(gdf: gpd.GeoDataFrame, tags: dict) -> pd.Series:
    cat = pd.Series("unknown", index=gdf.index, dtype="object")
    for col, values in tags.items():
        if col in gdf.columns:
            for v in values:
                cat[gdf[col] == v] = v
    other = gdf.get("other_tags", pd.Series(dtype=str)).apply(_parse_hstore)
    for col, values in tags.items():
        for v in values:
            mask = other.apply(lambda d: d.get(col) == v if isinstance(d, dict) else False)
            cat[mask] = v
    return cat


def _to_points(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    poly_mask = gdf.geom_type.isin(["Polygon", "MultiPolygon"])
    if poly_mask.any():
        gdf.loc[poly_mask, "geometry"] = gdf.loc[poly_mask, "geometry"].centroid
    return gdf[gdf.geom_type.isin(["Point", "MultiPoint"])].copy()


def _fallback_overpass(tags, label):
    import osmnx as ox
    ox.settings.overpass_url = "https://overpass.kumi.systems/api/interpreter"
    ox.settings.requests_timeout = 120
    ox.settings.use_cache = True
    ox.settings.log_console = False

    try:
        gdf = ox.features_from_bbox(bbox=LIMA_BBOX, tags=tags)
    except TypeError:
        west, south, east, north = LIMA_BBOX
        gdf = ox.features_from_bbox(north, south, east, west, tags=tags)

    if len(gdf) == 0:
        raise RuntimeError(f"Overpass returned 0 features for {label}")
    gdf = _to_points(gdf)
    return gdf.to_crs(epsg=CRS_UTM18S)
