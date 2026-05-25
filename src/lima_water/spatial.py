"""Spatial autocorrelation: Global Moran's I and Local Moran's I (LISA)."""
from __future__ import annotations

import geopandas as gpd
from esda.moran import Moran, Moran_Local
from libpysal.weights import Queen


def compute_moran(
    gdf: gpd.GeoDataFrame, column: str = "IVH_equal", permutations: int = 999
) -> dict:
    W = Queen.from_dataframe(gdf, use_index=False)
    W.transform = "r"

    mi = Moran(gdf[column].values, W, permutations=permutations)
    return {
        "moran_I": round(mi.I, 4),
        "p_value": round(mi.p_sim, 4),
        "EI": round(mi.EI, 4),
        "z_score": round(mi.z_sim, 4),
    }


def add_lisa_clusters(
    gdf: gpd.GeoDataFrame, column: str = "IVH_equal", permutations: int = 999
) -> gpd.GeoDataFrame:
    W = Queen.from_dataframe(gdf, use_index=False)
    W.transform = "r"

    lisa = Moran_Local(gdf[column].values, W, permutations=permutations)
    gdf = gdf.copy()
    gdf["lisa_q"] = lisa.q
    gdf["lisa_sig"] = lisa.p_sim < 0.05
    gdf["lisa_label"] = gdf.apply(_label_lisa, axis=1)
    return gdf


def _label_lisa(row) -> str:
    if not row["lisa_sig"]:
        return "Not significant"
    q = row["lisa_q"]
    labels = {1: "HH (High-High)", 2: "LH (Low-High)", 3: "LL (Low-Low)", 4: "HL (High-Low)"}
    return labels.get(q, f"Q{q}")


def export_lisa_geojson(gdf: gpd.GeoDataFrame, output_path) -> None:
    wgs = gdf.to_crs(epsg=4326)
    wgs.to_file(output_path, driver="GeoJSON")
