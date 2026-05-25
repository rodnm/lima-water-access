"""Load Lima districts from GADM shapefile and join with census data."""
from __future__ import annotations

import geopandas as gpd
from unidecode import unidecode

from .config import CRS_UTM18S, CRS_WGS84, GADM_SHP, N_DISTRITOS_LIMA

_NAME_ALIASES = {
    "MAGDALENA VIEJA": "PUEBLO LIBRE",
}


def load_lima_distritos(crs: int = CRS_WGS84) -> gpd.GeoDataFrame:
    """Return Lima province districts (43) from GADM L3 reprojected to ``crs``."""
    gdf = gpd.read_file(GADM_SHP)
    lima = gdf[(gdf["NAME_1"] == "Lima Province") & (gdf["NAME_2"] == "Lima")].copy()
    assert len(lima) == N_DISTRITOS_LIMA, (
        f"Esperaba {N_DISTRITOS_LIMA} distritos en Lima provincia, obtuve {len(lima)}"
    )
    lima["NAME_3_norm"] = (
        lima["NAME_3"]
        .apply(lambda x: unidecode(str(x)).upper().strip())
        .replace(_NAME_ALIASES)
    )
    return lima.to_crs(epsg=crs)


def join_distritos_censo(
    distritos: gpd.GeoDataFrame, censo, *, raise_on_missing: bool = True
) -> gpd.GeoDataFrame:
    """Left-join districts (GADM) with census (INEI) on normalized district name."""
    merged = distritos.merge(
        censo, left_on="NAME_3_norm", right_on="distrito_norm", how="left"
    )
    missing = merged.loc[merged["cobertura_formal_pct"].isna(), "NAME_3"].tolist()
    if missing:
        msg = f"Distritos sin datos censales tras join: {missing}"
        if raise_on_missing:
            raise AssertionError(msg)
        print(f"WARN: {msg}")
    return merged


def to_utm(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return gdf.to_crs(epsg=CRS_UTM18S)
