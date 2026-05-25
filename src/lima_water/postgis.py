"""PostGIS connection, data loading, and spatial query execution."""
from __future__ import annotations

import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text

from .config import PROJECT_ROOT, SQL_DIR, db_url


def get_engine():
    return create_engine(db_url())


def load_distritos(lima_utm: gpd.GeoDataFrame, schema: str = "public") -> None:
    engine = get_engine()
    cols = ["NAME_3", "cobertura_formal_pct", "hogares_sin_acceso", "pct_camion_pilon", "total", "geometry"]
    available = [c for c in cols if c in lima_utm.columns]
    lima_utm[available].to_postgis(
        "distritos_lima", engine, schema=schema, if_exists="replace", index=False
    )


def load_infra(gdf: gpd.GeoDataFrame, schema: str = "public") -> None:
    engine = get_engine()
    cols = [c for c in ["category", "man_made", "amenity", "landuse", "waterway", "geometry"] if c in gdf.columns]
    gdf[cols].to_postgis("infra_agua_osm", engine, schema=schema, if_exists="replace", index=False)


def load_lugares(gdf: gpd.GeoDataFrame, schema: str = "public") -> None:
    engine = get_engine()
    cols = [c for c in ["place", "name", "geometry"] if c in gdf.columns]
    gdf[cols].to_postgis("lugares_poblados", engine, schema=schema, if_exists="replace", index=False)


def run_sql_file(filepath: str) -> None:
    engine = get_engine()
    sql = filepath.read_text(encoding="utf-8") if hasattr(filepath, "read_text") else filepath
    with engine.begin() as conn:
        conn.execute(text(sql))


def create_indexes() -> None:
    run_sql_file(SQL_DIR / "01_indexes.sql")


def run_spatial_queries() -> pd.DataFrame:
    engine = get_engine()
    sql_path = SQL_DIR / "02_spatial_queries.sql"
    sql = sql_path.read_text(encoding="utf-8")
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


def table_exists(table_name: str) -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :t)"),
            {"t": table_name},
        )
        return result.scalar()
