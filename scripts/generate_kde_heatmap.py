"""Generate a weighted KDE heatmap of water-vulnerable populated places in Lima.

Methodology
-----------
* Points : ``lugares_poblados`` layer (1 424 OSM place nodes in Lima).
* Weights: ``hogares_sin_acceso`` (households without formal water access) from
  ``distritos_ivh``, assigned to each place via spatial join.  Places that fall
  outside every district polygon (edge artefacts) receive the median weight.
* Kernel : Gaussian, σ ≈ 2 000 m — equivalent to QGIS Heatmap radius=2000 m.
  Implemented as a weighted 2-D histogram + scipy.ndimage Gaussian filter, which
  is orders of magnitude faster than evaluating gaussian_kde on a fine grid while
  producing virtually identical results for n > 500.

Run
---
    uv run python scripts/generate_kde_heatmap.py

Output
------
    outputs/kde_heatmap.png  — A3 landscape, 300 dpi
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parents[1]
GPKG = ROOT / "outputs" / "lima_water.gpkg"
OUT  = ROOT / "outputs" / "kde_heatmap.png"

# Lima bounding box — UTM Zone 18S (EPSG:32718), 5 % padding
XMIN, YMIN, XMAX, YMAX = 249_197, 8_609_962, 327_156, 8_725_142
PIXEL_M = 100    # raster cell size (metres)
BW_M    = 2_000  # Gaussian sigma (metres) -- matches QGIS Heatmap radius


def generate() -> None:
    if not GPKG.exists():
        print(f"  ERROR: {GPKG} not found.")
        print("     Run first:  uv run python scripts/export_qgis_layers.py")
        sys.exit(1)

    # ── 1. Load layers ─────────────────────────────────────────────────────
    print("  Loading layers from GeoPackage ...")
    places    = gpd.read_file(GPKG, layer="lugares_poblados")
    districts = gpd.read_file(GPKG, layer="distritos_ivh")

    # Enrich districts with hogares_sin_acceso from ivh_table.csv
    # (the committed GeoPackage may not include that column)
    ivh_csv = ROOT / "outputs" / "ivh_table.csv"
    if "hogares_sin_acceso" not in districts.columns and ivh_csv.exists():
        ivh_df = pd.read_csv(ivh_csv)[["distrito", "hogares_sin_acceso"]]
        # ivh_table uses uppercase NAME_3_norm as key
        districts = districts.merge(
            ivh_df, left_on="NAME_3_norm", right_on="distrito", how="left"
        )

    # ── 2. Spatial join → assign hogares_sin_acceso weight to each place ───
    joined = gpd.sjoin(
        places,
        districts[["hogares_sin_acceso", "geometry"]],
        how="left",
        predicate="within",
    )
    # Deduplicate if a place matched >1 polygon (border artefact)
    joined = joined[~joined.index.duplicated(keep="first")]

    fallback = joined["hogares_sin_acceso"].median()
    weights  = joined["hogares_sin_acceso"].fillna(fallback).values.astype(float)
    # Floor at 1 so every place contributes at least a unit of density
    weights  = np.where(weights > 0, weights, 1.0)

    x = places.geometry.x.values
    y = places.geometry.y.values

    # ── 3. Weighted histogram ───────────────────────────────────────────────
    nx = int(round((XMAX - XMIN) / PIXEL_M))
    ny = int(round((YMAX - YMIN) / PIXEL_M))
    print(f"  Building {nx}x{ny} grid (pixel={PIXEL_M} m) ...")

    xi_edges = np.linspace(XMIN, XMAX, nx + 1)
    yi_edges = np.linspace(YMIN, YMAX, ny + 1)

    grid, _, _ = np.histogram2d(x, y, bins=[xi_edges, yi_edges], weights=weights)
    grid = grid.T  # shape (ny, nx) — row=y, col=x for imshow

    # ── 4. Gaussian smoothing (equivalent to KDE with Gaussian kernel) ──────
    sigma_px = BW_M / PIXEL_M  # sigma in pixel units
    print(f"  Applying Gaussian filter (sigma={BW_M} m = {sigma_px:.0f} px) ...")
    zz = gaussian_filter(grid, sigma=sigma_px)

    # ── 5. Plot ─────────────────────────────────────────────────────────────
    print("  Rendering map ...")
    fig, ax = plt.subplots(figsize=(16.54, 11.69))  # A3 landscape (inches)
    ax.set_aspect("equal")
    ax.set_xlim(XMIN, XMAX)
    ax.set_ylim(YMIN, YMAX)

    # KDE raster
    im = ax.imshow(
        zz,
        extent=(XMIN, XMAX, YMIN, YMAX),
        origin="lower",
        cmap="inferno",
        alpha=0.88,
        interpolation="bilinear",
        zorder=1,
    )

    # District boundary overlay
    districts.boundary.plot(ax=ax, color="#cccccc", linewidth=0.45, zorder=2)

    # Label the 10 most vulnerable districts
    top10 = districts.nlargest(10, "IVH_equal")
    for _, row in top10.iterrows():
        cx, cy = row.geometry.centroid.x, row.geometry.centroid.y
        ax.annotate(
            row["NAME_3"],
            xy=(cx, cy),
            fontsize=5.5,
            ha="center",
            va="center",
            color="white",
            fontweight="bold",
            zorder=4,
            bbox=dict(
                boxstyle="round,pad=0.15",
                fc="none",
                ec="none",
            ),
        )

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01, shrink=0.85)
    cbar.set_label(
        "Densidad ponderada\n(hogares sin acceso formal)",
        fontsize=8,
        labelpad=8,
    )
    cbar.ax.tick_params(labelsize=6.5)

    # Title
    ax.set_title(
        "Densidad de Hogares sin Acceso Formal al Agua — Lima Metropolitana",
        fontsize=12,
        fontweight="bold",
        pad=10,
    )

    # ── Cartographic elements ──────────────────────────────────────────────

    # Scale bar (10 km) — bottom-left, in data coordinates
    sb_x0 = XMIN + 4_000
    sb_y0 = YMIN + 5_000
    sb_len = 10_000  # 10 km in metres
    bar_kw = dict(color="white", lw=2.5, zorder=5, solid_capstyle="butt")
    ax.plot([sb_x0, sb_x0 + sb_len], [sb_y0, sb_y0], **bar_kw)
    ax.plot([sb_x0, sb_x0],                [sb_y0 - 400, sb_y0 + 400], **bar_kw)
    ax.plot([sb_x0 + sb_len, sb_x0 + sb_len], [sb_y0 - 400, sb_y0 + 400], **bar_kw)
    ax.text(
        sb_x0 + sb_len / 2, sb_y0 + 1_500,
        "10 km",
        ha="center", va="bottom",
        color="white", fontsize=7, fontweight="bold", zorder=5,
    )

    # North arrow — bottom-right corner
    ax.text(
        XMAX - 5_000, YMIN + 5_500,
        "↑ N",
        ha="center", va="center",
        fontsize=13, fontweight="bold",
        color="white", zorder=5,
    )

    # Attribution
    ax.text(
        0.5, -0.015,
        "Fuentes: INEI 2017 · OpenStreetMap (ODbL) · GADM 4.1  |  "
        "Proyección: UTM Zona 18S (EPSG:32718)  |  2026",
        transform=ax.transAxes,
        ha="center", va="top",
        fontsize=6.5, color="#777777",
    )

    ax.axis("off")
    fig.tight_layout(pad=0.4)

    # ── 6. Export ───────────────────────────────────────────────────────────
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=300, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    size_kb = OUT.stat().st_size // 1024
    print(f"  OK  {OUT.relative_to(ROOT)}  ({size_kb} KB, 300 dpi)")


if __name__ == "__main__":
    generate()
