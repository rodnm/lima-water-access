"""Export all analysis layers to a single GeoPackage for QGIS.

Usage:
    uv run python scripts/export_qgis_layers.py

Produces:
    outputs/lima_water.gpkg  — four layers ready for QGIS:
        distritos_ivh      polygons  EPSG:32718
        infra_agua_osm     points    EPSG:32718
        lugares_poblados   points    EPSG:32718
        lisa_clusters      polygons  EPSG:32718 (LISA labels joined to districts)
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
GPKG = OUTPUTS / "lima_water.gpkg"

# Ensure src/ is importable when run from project root or from scripts/
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _get_engine():
    from sqlalchemy import create_engine

    from lima_water.config import db_url

    return create_engine(db_url())


def load_from_postgis(table: str, geom_col: str = "geometry") -> gpd.GeoDataFrame:
    engine = _get_engine()
    return gpd.read_postgis(f"SELECT * FROM {table}", engine, geom_col=geom_col)


def main() -> None:
    engine = _get_engine()

    print("Loading distritos_lima from PostGIS…")
    distritos = load_from_postgis("distritos_lima")

    print("Loading IVH table…")
    ivh_df = pd.read_csv(OUTPUTS / "ivh_table.csv")

    # Normalise join key: distritos_lima stores original GADM NAME_3
    from unidecode import unidecode
    from lima_water.districts import _NAME_ALIASES

    distritos["NAME_3_norm"] = (
        distritos["NAME_3"]
        .apply(lambda x: unidecode(str(x)).upper().strip())
        .replace(_NAME_ALIASES)
    )

    distritos_ivh = distritos.merge(
        ivh_df, left_on="NAME_3_norm", right_on="distrito", how="left"
    )

    # ── Layer 1: distritos_ivh ─────────────────────────────────────────────
    keep_cols = [
        "NAME_3", "NAME_3_norm", "cobertura_formal_pct", "hogares_sin_acceso",
        "dist_promedio_metros", "area_km2",
        "IVH_equal", "IVH_demand_heavy", "IVH_access_heavy",
        "rank_equal", "rank_demand_heavy", "rank_access_heavy",
        "geometry",
    ]
    layer1 = distritos_ivh[[c for c in keep_cols if c in distritos_ivh.columns]].copy()
    print(f"  distritos_ivh: {len(layer1)} rows, CRS={layer1.crs}")

    # ── Layer 2: LISA clusters joined to polygons ──────────────────────────
    print("Loading LISA GeoJSON…")
    lisa_gdf = gpd.read_file(OUTPUTS / "lima_ivh_lisa.geojson")
    lisa_cols = [c for c in ["NAME_3_norm", "lisa_label", "lisa_q", "lisa_sig", "IVH_equal", "geometry"] if c in lisa_gdf.columns]
    layer2 = lisa_gdf[lisa_cols].copy()
    # Reproject to UTM 18S to match other layers
    if layer2.crs and layer2.crs.to_epsg() != 32718:
        layer2 = layer2.to_crs(epsg=32718)
    print(f"  lisa_clusters: {len(layer2)} rows, CRS={layer2.crs}")

    # ── Layer 3: infra_agua_osm ────────────────────────────────────────────
    print("Loading infra_agua_osm from PostGIS…")
    infra = load_from_postgis("infra_agua_osm")
    print(f"  infra_agua_osm: {len(infra)} features, CRS={infra.crs}")

    # ── Layer 4: lugares_poblados (with hogares_sin_acceso weight) ────────
    print("Loading lugares_poblados from PostGIS…")
    lugares = load_from_postgis("lugares_poblados")
    # Spatial join: assign district-level hogares_sin_acceso to each place
    # so QGIS Processing can use it as weight field for KDE Heatmap.
    lugares_w = gpd.sjoin(
        lugares,
        layer1[["hogares_sin_acceso", "geometry"]],
        how="left",
        predicate="within",
    )
    lugares_w = lugares_w[~lugares_w.index.duplicated(keep="first")]
    lugares_w["hogares_sin_acceso"] = lugares_w["hogares_sin_acceso"].fillna(
        lugares_w["hogares_sin_acceso"].median()
    )
    keep_l = [c for c in ["place", "name", "hogares_sin_acceso", "geometry"]
              if c in lugares_w.columns]
    lugares = lugares_w[keep_l].copy()
    print(f"  lugares_poblados: {len(lugares)} features, CRS={lugares.crs}")

    # Write GeoPackage (overwrite each layer)
    print(f"\nWriting {GPKG} …")
    GPKG.parent.mkdir(parents=True, exist_ok=True)

    layer1.to_file(GPKG, layer="distritos_ivh", driver="GPKG")
    layer2.to_file(GPKG, layer="lisa_clusters", driver="GPKG")
    infra.to_file(GPKG, layer="infra_agua_osm", driver="GPKG")
    lugares.to_file(GPKG, layer="lugares_poblados", driver="GPKG")

    print(f"\nDone — {GPKG}")
    print("Layers:")
    import pyogrio
    for lyr in pyogrio.list_layers(str(GPKG)):
        print(f"  • {lyr[0]} ({lyr[1]})")


if __name__ == "__main__":
    main()
