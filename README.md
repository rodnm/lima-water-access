# Lima Water Access — Spatial Vulnerability Analysis

**Which districts of Lima Metropolitana face the highest water access vulnerability?**

This project combines **INEI Census 2017** data, **GADM 4.1** boundaries, and **OpenStreetMap** water infrastructure to compute a **Water Vulnerability Index (IVH)** across Lima's 43 districts. It demonstrates spatial analysis skills with **QGIS**, **PostGIS**, **Python**, and **Folium**.

---

## Key Findings

| Rank | District | IVH | Coverage % | Avg Distance |
|------|----------|-----|------------|-------------|
| 1 | San Juan de Lurigancho | 1.033 | 79.9% | 1,080 m |
| 2 | Villa Maria del Triunfo | 0.967 | 78.6% | 2,618 m |
| 3 | Puente Piedra | 0.956 | 78.2% | 607 m |
| 4 | Santa Rosa | 0.907 | 36.1% | 898 m |
| 5 | Ate | 0.860 | 85.7% | 4,669 m |

**Moran's I = 0.266 (p = 0.005)** — statistically significant spatial clustering. Vulnerable districts are not randomly distributed; they form a contiguous high-vulnerability belt in northern and eastern Lima.

**LISA clusters**: 3 districts show HH (High-High) autocorrelation — these are priority intervention zones. Miraflores, San Isidro, San Borja, Magdalena del Mar, and Pueblo Libre form a contiguous LL (Low-Low) zone with near-universal coverage.

---

## Methodology

### Water Vulnerability Index (IVH)

The IVH combines three normalised components with equal weights:

| Component | Source | Transformation |
|-----------|--------|---------------|
| **Coverage deficit** | INEI 2017 (% without formal network) | MinMaxScaler |
| **Density of deficit** | Households without access / km² | RobustScaler (outlier-resistant) |
| **Distance to infra** | OSM populated places → nearest water node | Log-transform + MinMaxScaler |

**Why populated places instead of district centroids?** Large districts (Pachacamac, Cieneguilla) have centroids in desert areas far from population centers. Using OSM `place=*` nodes (suburbs, neighbourhoods) as measurement origins is methodologically more rigorous. Districts without OSM nodes fall back to centroids.

### Weight Sensitivity

Three scenarios tested — Spearman rank correlations > 0.95 confirm robustness:

| Scenario | Coverage | Density | Distance |
|----------|----------|---------|-----------|
| Equal (base) | 33% | 33% | 33% |
| Demand-heavy | 25% | 50% | 25% |
| Access-heavy | 50% | 25% | 25% |

---

## Reproducibility

### Prerequisites

- **Python 3.12** (managed via `uv`)
- **Docker Desktop** (for PostGIS)
- **GDAL** (for ogr2ogr — included with QGIS and Anaconda)
- **QGIS** (for static map and KDE — optional)

### Quick Start

```powershell
# 1. Install dependencies
uv sync

# 2. Start PostGIS
docker compose up -d

# 3. Download OSM data (one-time, 229 MB)
Invoke-WebRequest -Uri "https://download.geofabrik.de/south-america/peru-latest.osm.pbf" `
  -OutFile "data/raw/peru-latest.osm.pbf"

# 4. Verify environment
uv run python -c "import geopandas, osmnx, esda; print('OK')"

# 5. Run the full pipeline
uv run python test_pipeline.py

# 6. Open the notebook
uv run jupyter lab notebooks/analysis.ipynb
```

### What the pipeline produces

| Output | File | Description |
|--------|------|-------------|
| IVH table | `outputs/ivh_table.csv` | 43 districts ranked by vulnerability |
| LISA GeoJSON | `outputs/lima_ivh_lisa.geojson` | Spatial clusters (HH, LL, LH, HL) |
| Interactive map | `outputs/map_interactive.html` | Folium choropleth + cluster markers |
| Static map | `outputs/map_static.png` | QGIS Print Layout (A3, 300 dpi) |
| KDE heatmap | `outputs/kde_heatmap.png` | Kernel Density of unserved households |

### Generating QGIS Deliverables

All QGIS layers are pre-packaged in `outputs/lima_water.gpkg`. Run the
export script first (if the file doesn't exist):

```powershell
uv run python scripts/export_qgis_layers.py
```

Then follow the step-by-step instructions in **[`docs/qgis_workflow.md`](docs/qgis_workflow.md)**
to produce:

| Deliverable | Instructions |
|-------------|-------------|
| `qgis/lima_water.qgz` | Steps 1–7 (load, style, save project) |
| `outputs/map_static.png` | Step 8 (A3 Print Layout, 300 dpi) |
| `qgis/layouts/lima_water_print.qpt` | Step 8 (save layout template) |
| `outputs/kde_heatmap.png` | Step 9 (KDE heatmap, Inferno ramp) |

---

## Data Sources

| Source | Description | Year | License |
|--------|-------------|------|---------|
| [INEI](https://www.inei.gob.pe/) | Census 2017 — Water access by district (REDATAM) | 2017 | Public |
| [GADM 4.1](https://gadm.org/) | Administrative boundaries (Level 3 — district) | 2022 | Free for academic use |
| [OpenStreetMap](https://www.openstreetmap.org/) | Water infrastructure and populated places | 2026 | ODbL |
| [Geofabrik](https://download.geofabrik.de/) | Peru OSM extract (PBF, used via GDAL ogr2ogr) | Daily | ODbL |

---

## Limitations

- **Census data is from 2017** — the most recent available. Water coverage may have improved since then, especially in peri-urban expansion zones.
- **OSM coverage is variable** — rural districts may have fewer mapped water features than they actually contain. The pipeline uses a Geofabrik Peru extract (229 MB) processed locally via GDAL ogr2ogr, making it fully offline and reproducible. Overpass API is available as a fallback.
- **Equal weights in the base scenario** are a conscious simplification. The sensitivity analysis shows rankings are stable across weighting schemes (Spearman > 0.95).
- **Informal water sources** (tanker trucks, shared standpipes) are not fully captured by formal network metrics alone.
- **Granularity is district-level** — does not capture intra-district inequality. The KDE heatmap partially addresses this.

---

## Project Structure

```
lima-water-access/
├── pyproject.toml              # Dependencies (uv)
├── .python-version             # Python 3.12
├── docker-compose.yml          # PostGIS 16-3.4
├── src/lima_water/
│   ├── config.py               # Paths, CRS, DB URL
│   ├── census.py               # INEI 2017 parser
│   ├── districts.py            # GADM loading + census join
│   ├── osm.py                  # OSM extraction (infra + places)
│   ├── postgis.py              # DB loading, indexes, queries
│   ├── ivh.py                  # IVH computation + sensitivity
│   └── spatial.py              # Moran's I + LISA
├── sql/
│   ├── 01_indexes.sql          # GIST spatial indexes
│   └── 02_spatial_queries.sql  # Distance + buffer queries
├── notebooks/
│   └── analysis.ipynb          # Narrative end-to-end
├── qgis/
│   ├── lima_water.qgz          # Styled project
│   └── layouts/
│       └── lima_water_print.qpt
├── data/
│   ├── raw/                    # Census Excel + GADM shapefiles + Peru PBF
│   │   ├── osmconf.ini         # GDAL OSM tag configuration
│   │   └── peru-latest.osm.pbf # Geofabrik extract (download first)
│   └── processed/              # Consolidated GeoJSON
└── outputs/                    # Maps, tables, exports
```

---

## Author

Portfolio project demonstrating QGIS, PostGIS, and spatial analysis with Python.
