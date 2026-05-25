"""Water Vulnerability Index (IVH) computation with weight sensitivity.

Degrades gracefully when OSM data is unavailable: distance component is set to
zero and the index uses only coverage + density (with re-normalised weights).
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, RobustScaler

WEIGHT_SCENARIOS = {
    "equal": (1 / 3, 1 / 3, 1 / 3),
    "demand_heavy": (0.25, 0.50, 0.25),
    "access_heavy": (0.50, 0.25, 0.25),
}

_NO_OSM_SCENARIOS = {
    "equal": (0.50, 0.50, 0.00),
    "demand_heavy": (0.25, 0.75, 0.00),
    "access_heavy": (0.75, 0.25, 0.00),
}


def compute_ivh(
    districts_utm,
    distancia_df: pd.DataFrame | None = None,
    *,
    areas: pd.Series | None = None,
) -> pd.DataFrame:
    key = "NAME_3_norm" if "NAME_3_norm" in districts_utm.columns else "distrito_norm"

    df = districts_utm[[key, "cobertura_formal_pct", "hogares_sin_acceso", "geometry"]].copy()

    if areas is None:
        df["area_km2"] = districts_utm.to_crs(districts_utm.crs).geometry.area / 1e6
    else:
        df["area_km2"] = areas

    df["cobertura_inv"] = 100 - df["cobertura_formal_pct"].clip(0, 100)
    df["densidad_deficit"] = df["hogares_sin_acceso"] / df["area_km2"].replace(0, np.nan)

    osm_available = distancia_df is not None and len(distancia_df) > 0
    if osm_available:
        from unidecode import unidecode

        from .districts import _NAME_ALIASES

        dist_df = distancia_df.copy()
        # Normalise + apply same historical-name aliases as districts.py so the
        # merge below succeeds for districts whose GADM name differs from INEI
        # (e.g. "Magdalena Vieja" -> "Pueblo Libre").
        dist_df["distrito_norm"] = (
            dist_df["distrito"]
            .apply(lambda x: unidecode(str(x)).upper().strip())
            .replace(_NAME_ALIASES)
        )
        merged = df.merge(dist_df, left_on=key, right_on="distrito_norm", how="left")
        if merged["dist_promedio_metros"].isna().any():
            missing = merged.loc[merged["dist_promedio_metros"].isna(), key].tolist()
            warnings.warn(f"Districts missing distance after merge: {missing}")
        merged["dist_log"] = np.log1p(merged["dist_promedio_metros"].fillna(0))
        scenarios = WEIGHT_SCENARIOS
    else:
        warnings.warn("No OSM distance data available — using coverage + density only.")
        merged = df.copy()
        merged["dist_log"] = 0.0
        merged["dist_promedio_metros"] = 0.0
        scenarios = _NO_OSM_SCENARIOS

    base = pd.DataFrame()
    base["distrito"] = merged[key]
    base["cobertura_formal_pct"] = merged["cobertura_formal_pct"]
    base["hogares_sin_acceso"] = merged["hogares_sin_acceso"]
    base["dist_promedio_metros"] = merged.get("dist_promedio_metros", 0.0)
    base["area_km2"] = merged["area_km2"]

    cobertura_scaled = MinMaxScaler().fit_transform(merged[["cobertura_inv"]])
    densidad_scaled = RobustScaler().fit_transform(merged[["densidad_deficit"]].fillna(0))
    distancia_scaled = MinMaxScaler().fit_transform(merged[["dist_log"]])

    for scenario, (w_cob, w_den, w_dis) in scenarios.items():
        base[f"IVH_{scenario}"] = (
            w_cob * cobertura_scaled[:, 0]
            + w_den * densidad_scaled[:, 0]
            + w_dis * distancia_scaled[:, 0]
        )

    for scenario in scenarios:
        col = f"IVH_{scenario}"
        base[f"rank_{scenario}"] = base[col].rank(ascending=False).astype(int)

    return base.sort_values("IVH_equal", ascending=False).reset_index(drop=True)


def export_ivh_table(ivh_df: pd.DataFrame, output_path) -> None:
    ivh_df.to_csv(output_path, index=False)
