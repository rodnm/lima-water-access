# Changelog

## [0.3.0] — 2026-05-25

### Added

- **Print Layout A3 automático** (`scripts/create_qgis_project.py`): título (18 pt bold), subtítulo, marco del mapa UTM 18S, leyenda enlazada, barra de escala (10 km × 3 segmentos), flecha de norte SVG (NorthArrow_01) y atribución de fuentes.
- **`outputs/map_static.png`**: exportación automática a 300 dpi desde el script PyQGIS — ya no requiere pasos manuales en QGIS.
- **`qgis/layouts/lima_water_print.qpt`**: plantilla QPT del Print Layout para edición posterior en QGIS.
- **Etiquetas de distritos**: los 10 distritos más vulnerables (`rank_equal <= 10`) muestran su nombre en Arial 7 pt con halo blanco; implementado mediante `QgsPalLayerSettings` + `QgsVectorLayerSimpleLabeling`.
- **Grupos de capas**: panel organizado en "Infraestructura OSM" (infra_agua_osm + lugares_poblados) y "Análisis IVH" (distritos_ivh + lisa_clusters) mediante `QgsLayerTreeGroup`.
- **Semilla reproducible en Moran's I / LISA** (`src/lima_water/spatial.py`): `np.random.seed(42)` fijado antes de cada llamada a `esda.Moran` / `esda.Moran_Local` — p-valores y asignaciones LISA idénticos entre ejecuciones. Resultado canónico: I=0.266, p=0.002 (999 permutaciones).
- **Compatibilidad PyQt6/PyQt5**: el script detecta automáticamente qué versión de Qt usa la instalación de QGIS y ajusta los enums (`Qt.AlignmentFlag.AlignLeft` en PyQt6, `Qt.AlignLeft` en PyQt5).

### Changed

- `README.md`: traducido íntegramente al español; sección de reproducibilidad de pruebas estadísticas; `map_static.png` marcado como generado automáticamente.
- `scripts/create_qgis_project.py`: reescrito completamente — añade layout A3, grupos de capas, etiquetas y exportación PNG en un solo comando headless.

---

## [0.2.0] — 2026-05-25

### Fixed

- **Pueblo Libre IVH merge bug**: PostGIS spatial query returns `NAME_3 = "Magdalena Vieja"` (original GADM name). After `unidecode + upper`, this produced `"MAGDALENA VIEJA"`, which failed to match `"PUEBLO LIBRE"` in the district GeoDataFrame (already aliased by `districts.py`). Fix: apply `_NAME_ALIASES` in `compute_ivh()` when normalising `distancia_df["distrito"]` — same alias table used by `districts.py`. Result: Pueblo Libre now has `dist_promedio_metros = 1120.8 m`, `IVH_equal = 0.022`, rank 40/43 (correctly among the least vulnerable).

### Added

- **`scripts/export_qgis_layers.py`**: Reads from PostGIS + `outputs/ivh_table.csv` + `outputs/lima_ivh_lisa.geojson` and writes four layers to `outputs/lima_water.gpkg` in EPSG:32718.
- **`outputs/lima_water.gpkg`**: Portable GeoPackage with four QGIS-ready layers: `distritos_ivh` (polygons + full IVH/LISA attributes), `lisa_clusters` (LISA labels in UTM), `infra_agua_osm` (424 water infrastructure points), `lugares_poblados` (1,424 OSM place nodes).
- **`docs/qgis_workflow.md`**: Step-by-step QGIS guide covering: loading the GeoPackage, styling each layer (IVH graduated choropleth, LISA categorized, infra symbols), creating the A3 Print Layout (→ `outputs/map_static.png`), and generating the KDE heatmap (→ `outputs/kde_heatmap.png`). Includes troubleshooting notes.

### Changed

- `.gitignore`: Added explicit exclusions for `data/raw/lima_points.geojson` (60 MB) and `data/raw/lima_multipolygons.geojson` (100 MB) ogr2ogr caches; added `*.qgz~` QGIS backup exclusion; added `!outputs/lima_water.gpkg` exception to track GeoPackage deliverable.
- Deleted `data/raw/peru-260524.osm.pbf` (229 MB duplicate of `peru-latest.osm.pbf`).

### Results (updated — full 3-component IVH, Pueblo Libre fixed)

| # | District | IVH | Coverage | Avg Distance |
|---|----------|-----|----------|-------------|
| 1 | San Juan de Lurigancho | 1.033 | 79.9% | 1,080 m |
| 2 | Villa Maria del Triunfo | 0.967 | 78.6% | 2,618 m |
| 3 | Puente Piedra | 0.956 | 78.2% | 607 m |
| 4 | Santa Rosa | 0.907 | 36.1% | 898 m |
| 5 | Ate | 0.860 | 85.7% | 4,669 m |
| 40 | Pueblo Libre | 0.022 | 99.96% | 1,121 m | ← was negative (bug) |

- **Moran's I**: 0.266 (p = 0.005) — statistically significant spatial clustering confirmed

---

## [0.1.0] — 2026-05-25

### Added

#### Core Pipeline
- **Census parser** (`src/lima_water/census.py`): Parse REDATAM Excel export (INEI 2017) with `CAT_MAP` for water source categories, derive `cobertura_formal_pct`, `hogares_sin_acceso`, `pct_camion_pilon`. Normalise district names via `unidecode`.
- **District loader** (`src/lima_water/districts.py`): Load GADM 4.1 Level 3 shapefile, filter Lima Province (`NAME_1="Lima Province"`, `NAME_2="Lima"`), assert 43 districts. Join with census data on normalised name. Includes `_NAME_ALIASES` for historical name mismatches (Magdalena Vieja → Pueblo Libre).
- **OSM extraction** (`src/lima_water/osm.py`): Primary source is local **Geofabrik Peru PBF** (229 MB) processed via **GDAL ogr2ogr** — fully offline and reproducible. Extracts 424 water infrastructure points (drinking water, towers, tanks, pumping stations) and 1,424 populated places (suburbs, neighbourhoods, villages). Overpass API available as fallback. Uses `osmconf.ini` to configure GDAL's OSM driver tag exposure, and a custom HSTORE parser (`"key"=>"value"`) to filter features by tag values after ogr2ogr export.
- **PostGIS loader** (`src/lima_water/postgis.py`): Load GeoDataFrames to PostGIS 16, run SQL files from disk, create GIST indexes, execute spatial distance queries via `pd.read_sql`.
- **IVH computation** (`src/lima_water/ivh.py`): Three-component Water Vulnerability Index (coverage deficit, density of deficit, log-transformed distance). RobustScaler for density, MinMaxScaler for coverage and distance. Three weight scenarios (equal, demand-heavy, access-heavy). Falls back to 2-component index if no distance data is available. Normalises district names from PostGIS queries before merging to ensure cross-source compatibility.
- **Spatial autocorrelation** (`src/lima_water/spatial.py`): Global Moran's I with Queen weights and 999 permutations (`esda.Moran`). Local Moran's I (LISA) via `esda.Moran_Local` with cluster labels (HH, LL, LH, HL). Export to GeoJSON for QGIS import.

#### SQL
- `sql/01_indexes.sql`: GIST spatial indexes on `distritos_lima`, `infra_agua_osm`, `lugares_poblados`.
- `sql/02_spatial_queries.sql`: CTE-based distance query — measures distance from OSM populated places to nearest water infrastructure, with centroid fallback for districts without OSM nodes. Returns `dist_promedio_metros`, `dist_minima_metros`, `n_lugares_medidos` per district.

#### Configuration & Infrastructure
- `pyproject.toml`: Dependencies via `uv` (geopandas, osmnx, shapely, folium, esda, libpysal, scikit-learn, psycopg2-binary, geoalchemy2, jupyterlab, unidecode, scipy).
- `docker-compose.yml`: PostGIS 16-3.4 with healthcheck, persistent volume, port 5432.
- `.env.example` / `.env`: Database credentials.
- `.python-version`: Python 3.12.
- `.gitignore`: Excludes `.venv`, outputs (except `.gitkeep`), `.env`, `.claude`, `.osm.pbf` files.
- `data/osmconf.ini`: GDAL OSM driver configuration — exposes `man_made`, `amenity`, `landuse`, `waterway`, `place` tags as columns for all geometry types (points, lines, multipolygons, multilinestrings, other_relations).

#### Deliverables
- `notebooks/analysis.ipynb`: End-to-end narrative (census → districts → OSM → IVH → Moran's I → LISA → Folium map).
- `README.md`: English documentation with findings, methodology, reproducibility, QGIS workflow, data sources, limitations.
- `test_pipeline.py`: One-command full pipeline runner (`uv run python test_pipeline.py`).
- `outputs/ivh_table.csv`: 43 districts ranked by IVH across 3 weight scenarios.
- `outputs/map_interactive.html`: Folium choropleth with LISA cluster markers.
- `outputs/lima_ivh_lisa.geojson`: LISA clusters for QGIS import.
- `docs/plan de implementacion v1.md`: Final implementation plan with methodological corrections.
- `docs/plan_tareas.md`: Detailed task breakdown with status tracking.
- `scripts/diagnose_overpass.py`: Diagnostic tool to test Overpass endpoint connectivity.

### Fixed

- **GADM province filter**: `NAME_1` changed from `"Lima"` to `"Lima Province"` — GADM 4.1 represents Lima province as a separate `NAME_1` entry distinct from the Lima department.
- **District name mismatch**: `"Magdalena Vieja"` (GADM) mapped to `"Pueblo Libre"` (INEI) via `_NAME_ALIASES` in `districts.py`. These are the same district under different historical names.
- **OSM Overpass timeout**: Replaced network-dependent Overpass API with local **Geofabrik PBF extract** processed via GDAL ogr2ogr. Pipeline now runs fully offline — no dependency on external API availability. Overpass kept as fallback for environments where ogr2ogr is unavailable.
- **IVH distance merge**: PostGIS query returns original GADM names (mixed case, accented) while Python code uses `unidecode`-normalised names (uppercase, ASCII). Fixed by applying `unidecode` + `.upper().strip()` to the `distrito` column from the distance query result before merging with district GeoDataFrames.

### Results (full 3-component IVH)

| # | District | IVH | Coverage | Avg Distance |
|---|----------|-----|----------|-------------|
| 1 | San Juan de Lurigancho | 1.182 | 79.9% | 1,080 m |
| 2 | Puente Piedra | 1.132 | 78.2% | 607 m |
| 3 | Villa Maria del Triunfo | 1.072 | 78.6% | 2,618 m |
| 4 | Santa Rosa | 1.064 | 36.1% | 898 m |
| 5 | Ate | 0.937 | 85.7% | 4,669 m |

- **OSM data**: 424 water infrastructure features + 1,424 populated places in Lima area
- **Moran's I**: 0.284 (p = 0.004) — statistically significant spatial clustering confirmed
- **LISA clusters**: 3 HH (High-High) hot spots, 10 LL (Low-Low) cold spots
- **Spatial autocorrelation**: Vulnerability is not randomly distributed — it forms a contiguous belt across northern and eastern Lima

### Known Limitations

- QGIS deliverables (`.qgz` project, print layout, KDE heatmap) are manual steps — documented in README.
- Census data is from 2017; coverage may have improved in peri-urban expansion zones since then.
- The Geofabrik Peru PBF is 229 MB — must be downloaded once before first run.
- OSM tag coverage is uneven: urban districts have more mapped features than rural ones, which may under-represent infrastructure in peri-urban areas.
- Equal weights in the base IVH scenario are a conscious simplification. Sensitivity analysis (3 weight scenarios) confirms rankings are robust (Spearman > 0.95).
