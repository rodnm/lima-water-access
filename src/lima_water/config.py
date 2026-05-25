"""Project-wide paths, CRS, and database configuration."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
OUTPUTS = PROJECT_ROOT / "outputs"
SQL_DIR = PROJECT_ROOT / "sql"

CENSO_XLSX = DATA_RAW / "censo_agua_lima.xlsx"
GADM_SHP = DATA_RAW / "gadm41_PER_shp" / "gadm41_PER_3.shp"
OSM_PBF = DATA_RAW / "peru-latest.osm.pbf"

CRS_WGS84 = 4326
CRS_UTM18S = 32718

LIMA_PROVINCIA_NAME = "Lima Province"
LIMA_DEPARTAMENTO_NAME = "Lima"
N_DISTRITOS_LIMA = 43

load_dotenv(PROJECT_ROOT / ".env")


def db_url() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "lima_water")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd = os.getenv("POSTGRES_PASSWORD", "postgres")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def ensure_dirs() -> None:
    for d in (DATA_PROCESSED, OUTPUTS):
        d.mkdir(parents=True, exist_ok=True)
