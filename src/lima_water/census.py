"""Parse REDATAM INEI Census 2017 water-access data for Lima province (UBIGEO 1501*)."""
from __future__ import annotations

from pathlib import Path

import openpyxl
import pandas as pd

CAT_MAP = {
    "Red pública dentro de la vivienda": "red_intra",
    "Red pública fuera de la vivienda, pero dentro de la edificación": "red_extra",
    "Pilón o pileta de uso público": "pilon",
    "Camión - cisterna u otro similar": "camion",
    "Pozo (agua subterránea)": "pozo",
    "Manantial o puquio": "manantial",
    "Río, acequia, lago, laguna": "rio",
    "Vecino": "vecino",
    "Otro": "otro",
    "Total": "total",
}

LIMA_PROVINCIA_UBIGEO_PREFIX = "1501"
NUMERIC_COLS = list(CAT_MAP.values())


def parse_censo_agua(filepath: str | Path) -> pd.DataFrame:
    """Parse REDATAM Excel export and return one row per district in Lima province."""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active

    records: list[dict] = []
    current: dict = {}

    for row in ws.iter_rows(values_only=True):
        if len(row) < 2:
            continue
        col2 = row[1]
        col3 = row[2] if len(row) > 2 else None

        if isinstance(col2, str) and col2.startswith("AREA #"):
            if current and current.get("ubigeo", "").startswith(LIMA_PROVINCIA_UBIGEO_PREFIX):
                records.append(current)
            ubigeo = col2.replace("AREA #", "").strip()
            nombre = col3.split(":")[-1].strip() if isinstance(col3, str) else ""
            current = {"ubigeo": ubigeo, "distrito": nombre}
        elif isinstance(col2, str) and col2 in CAT_MAP:
            val = col3
            if isinstance(val, (int, float)):
                current[CAT_MAP[col2]] = val

    if current and current.get("ubigeo", "").startswith(LIMA_PROVINCIA_UBIGEO_PREFIX):
        records.append(current)

    wb.close()

    df = pd.DataFrame(records)
    for col in NUMERIC_COLS:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df["cobertura_formal_pct"] = (
        (df["red_intra"] + df["red_extra"]) / df["total"] * 100
    ).round(2)
    df["hogares_sin_acceso"] = df["total"] - df["red_intra"] - df["red_extra"]
    df["pct_camion_pilon"] = (
        (df["camion"] + df["pilon"]) / df["total"] * 100
    ).round(2)
    df["distrito_norm"] = df["distrito"].apply(_normalize_name)

    return df


def _normalize_name(name: str) -> str:
    from unidecode import unidecode

    return unidecode(str(name)).upper().strip()
