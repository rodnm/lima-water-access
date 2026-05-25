# Lima Water Access — Spatial Vulnerability Analysis

**Which districts of Lima Metropolitana face the highest water access vulnerability?**

This project combines **INEI Census 2017** data, **GADM 4.1** boundaries, and **OpenStreetMap** water infrastructure to compute a **Water Vulnerability Index (IVH)** across Lima's 43 districts. It demonstrates spatial analysis skills with **QGIS 4**, **PostGIS**, **Python**, and **Folium**.

---

## Key Findings

| Rank | District | IVH | Coverage % | Avg Distance |
|------|----------|-----|------------|-------------|
| 1 | San Juan de Lurigancho | 1.033 | 79.9% | 1,080 m |
| 2 | Villa Maria del Triunfo | 0.967 | 78.6% | 2,618 m |
| 3 | Puente Piedra | 0.956 | 78.2% | 607 m |
| 4 | Santa Rosa | 0.907 | 36.1% | 898 m |
| 5 | Ate | 0.860 | 85.7% | 4,669 m |

**Moran's I = 0.266 (p = 0.002, seed = 42, 999 permutations)** — statistically significant spatial clustering. Vulnerable districts are not randomly distributed; they form a contiguous high-vulnerability belt across northern and eastern Lima.

**LISA clusters**: 3 districts show HH (High-High) autocorrelation — priority intervention zones. Miraflores, San Isidro, San Borja, Magdalena del Mar, and Pueblo Libre form a contiguous LL (Low-Low) zone with near-universal coverage.

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

### Reproducibility of statistical tests

`numpy.random.seed(42)` is set immediately before each `esda.Moran` / `esda.Moran_Local` call so p-values and LISA cluster assignments are identical across runs (esda 2.9 uses NumPy's global RNG for permutation tests).

---

## Reproducibility

### Prerequisites

| Tool | Purpose |
|------|---------|
| **Python 3.12** via `uv` | Pipeline and analysis |
| **Docker Desktop** | PostGIS 16-3.4 |
| **GDAL / ogr2ogr** | OSM PBF extraction (included with QGIS) |
| **QGIS 4** | Open `qgis/lima_water.qgz`; generate Print Layout and KDE |

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
uv run python -c "import geopandas, esda; print('OK')"

# 5. Run the full pipeline
uv run python test_pipeline.py

# 6. Open the notebook
uv run jupyter lab notebooks/analysis.ipynb
```

### What the pipeline produces

| Output | File | Description |
|--------|------|-------------|
| IVH table | `outputs/ivh_table.csv` | 43 districts ranked by vulnerability (3 weight scenarios) |
| LISA GeoJSON | `outputs/lima_ivh_lisa.geojson` | Spatial clusters (HH, LL, LH, HL) for QGIS / web |
| Interactive map | `outputs/map_interactive.html` | Folium choropleth + LISA cluster markers |
| QGIS layers | `outputs/lima_water.gpkg` | 4-layer GeoPackage (distritos_ivh, lisa_clusters, infra_agua_osm, lugares_poblados) |
| QGIS project | `qgis/lima_water.qgz` | Styled project: IVH choropleth, LISA, infra markers |
| Static map | `outputs/map_static.png` | QGIS Print Layout, A3, 300 dpi *(generate via QGIS)* |
| KDE heatmap | `outputs/kde_heatmap.png` | Kernel density of populated places *(generate via QGIS)* |

### QGIS Workflow

The QGIS project is generated programmatically — no manual styling needed:

```powershell
# Regenerate GeoPackage (if outputs/lima_water.gpkg is missing)
uv run python scripts/export_qgis_layers.py

# Regenerate QGIS project (requires QGIS 4 installed)
& "C:/Program Files/QGIS 4.0.2/bin/python-qgis.bat" scripts/create_qgis_project.py
```

Then open `qgis/lima_water.qgz` in QGIS. To produce the remaining visual deliverables (Print Layout → `map_static.png`, KDE heatmap → `kde_heatmap.png`) follow **[`docs/qgis_workflow.md`](docs/qgis_workflow.md)** (Steps 8–9).

---

## Data Sources

| Source | Description | Year | License |
|--------|-------------|------|---------|
| [INEI](https://www.inei.gob.pe/) | Census 2017 — Water access by district (REDATAM) | 2017 | Public |
| [GADM 4.1](https://gadm.org/) | Administrative boundaries (Level 3 — district) | 2022 | Free for academic use |
| [OpenStreetMap](https://www.openstreetmap.org/) | Water infrastructure and populated places | 2026 | ODbL |
| [Geofabrik](https://download.geofabrik.de/) | Peru OSM extract (PBF, processed via GDAL ogr2ogr) | Daily | ODbL |

---

## Limitations

- **Census data is from 2017** — the most recent available. Coverage may have improved since, especially in peri-urban expansion zones.
- **OSM coverage is variable** — rural districts may have fewer mapped water features. The pipeline uses a Geofabrik Peru extract (229 MB) processed locally via GDAL ogr2ogr — fully offline and reproducible. Overpass API is available as a fallback.
- **Equal weights in the base scenario** are a conscious simplification. Sensitivity analysis confirms rankings are stable across weighting schemes (Spearman > 0.95).
- **Informal water sources** (tanker trucks, shared standpipes) are not fully captured by formal network metrics alone.
- **Granularity is district-level** — does not capture intra-district inequality. The KDE heatmap partially addresses this.

---

## Project Structure

```
lima-water-access/
├── pyproject.toml                   # Dependencies (uv)
├── .python-version                  # Python 3.12
├── docker-compose.yml               # PostGIS 16-3.4
├── test_pipeline.py                 # One-command full pipeline runner
├── src/lima_water/
│   ├── config.py                    # Paths, CRS, DB URL
│   ├── census.py                    # INEI 2017 parser
│   ├── districts.py                 # GADM loading + census join + name aliases
│   ├── osm.py                       # OSM extraction via Geofabrik PBF + ogr2ogr
│   ├── postgis.py                   # DB loading, GIST indexes, spatial queries
│   ├── ivh.py                       # IVH computation + 3 weight scenarios
│   └── spatial.py                   # Moran's I + LISA (seed=42 for reproducibility)
├── sql/
│   ├── 01_indexes.sql               # GIST spatial indexes
│   └── 02_spatial_queries.sql       # CTE distance query + centroid fallback
├── scripts/
│   ├── export_qgis_layers.py        # Write 4 layers to outputs/lima_water.gpkg
│   ├── create_qgis_project.py       # Generate qgis/lima_water.qgz via PyQGIS 4
│   └── diagnose_overpass.py         # Test Overpass API endpoint connectivity
├── notebooks/
│   └── analysis.ipynb               # Narrative end-to-end analysis
├── qgis/
│   ├── lima_water.qgz               # Styled QGIS 4 project (generated by script)
│   └── layouts/
│       └── lima_water_print.qpt     # Print layout template (save from QGIS GUI)
├── docs/
│   └── qgis_workflow.md             # Step-by-step QGIS guide (Print Layout + KDE)
├── sql/
├── data/
│   ├── raw/                         # Census Excel, GADM shapefiles, osmconf.ini
│   │   └── peru-latest.osm.pbf      # Geofabrik extract (download first, 229 MB)
│   └── processed/
└── outputs/
    ├── ivh_table.csv                # 43 districts ranked by IVH
    ├── lima_ivh_lisa.geojson        # LISA clusters for QGIS / web
    ├── lima_water.gpkg              # 4-layer QGIS GeoPackage
    └── map_interactive.html         # Folium choropleth
```

---

## Author

Portfolio project demonstrating QGIS 4, PostGIS, and spatial analysis with Python.
