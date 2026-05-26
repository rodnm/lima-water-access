# Acceso al Agua en Lima — Análisis de Vulnerabilidad Espacial

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![QGIS](https://img.shields.io/badge/QGIS-4.0-589632?logo=qgis&logoColor=white)
![PostGIS](https://img.shields.io/badge/PostGIS-16-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-✓-2496ED?logo=docker&logoColor=white)
![GeoPandas](https://img.shields.io/badge/GeoPandas-✓-139C5A?logo=geopandas&logoColor=white)
![Folium](https://img.shields.io/badge/Folium-✓-77B829?logo=leaflet&logoColor=white)
![OSMnx](https://img.shields.io/badge/OSMnx-✓-000000?logo=openstreetmap&logoColor=white)

**¿Qué distritos de Lima Metropolitana presentan mayor vulnerabilidad en el acceso al agua?**

Este proyecto combina datos del **Censo INEI 2017**, límites administrativos **GADM 4.1** e infraestructura de agua de **OpenStreetMap** para calcular un **Índice de Vulnerabilidad Hídrica (IVH)** en los 43 distritos de Lima.

## Stack Tecnológico

| Categoría | Tecnología |
|-----------|-------------|
| Lenguaje | Python 3.12 (`uv`) |
| SIG | QGIS 4.0, GDAL / ogr2ogr |
| BD espacial | PostGIS 16-3.4 (Docker) |
| Análisis espacial | GeoPandas, OSMnx, Shapely |
| Estadística espacial | esda, libpysal |
| Machine learning | scikit-learn (MinMaxScaler, RobustScaler) |
| Visualización | Folium, Matplotlib, GeoPackage |
| Notebooks | Jupyter Notebook |
| Datos OSM | Geofabrik PBF |

## Hallazgos principales

| Rank | Distrito | IVH | Cobertura % | Dist. promedio |
|------|----------|-----|-------------|----------------|
| 1 | San Juan de Lurigancho | 1.033 | 79.9 % | 1 080 m |
| 2 | Villa María del Triunfo | 0.967 | 78.6 % | 2 618 m |
| 3 | Puente Piedra | 0.956 | 78.2 % | 607 m |
| 4 | Santa Rosa | 0.907 | 36.1 % | 898 m |
| 5 | Ate | 0.860 | 85.7 % | 4 669 m |

**I de Moran = 0.266 (p = 0.002, semilla = 42, 999 permutaciones)** — autocorrelación espacial estadísticamente significativa. Los distritos vulnerables no están distribuidos al azar: forman un corredor continuo de alta vulnerabilidad en el norte y el este de Lima.

**Clústeres LISA**: 3 distritos muestran autocorrelación HH (Alto-Alto) — zonas prioritarias de intervención. Miraflores, San Isidro, San Borja, Magdalena del Mar y Pueblo Libre conforman una zona contigua LL (Bajo-Bajo) con cobertura casi universal.

## Metodología

### Índice de Vulnerabilidad Hídrica (IVH)

El IVH combina tres componentes normalizados con pesos iguales:

| Componente | Fuente | Transformación |
|------------|--------|----------------|
| **Déficit de cobertura** | INEI 2017 (% sin red formal) | MinMaxScaler |
| **Densidad del déficit** | Hogares sin acceso / km² | RobustScaler (resistente a outliers) |
| **Distancia a infraestructura** | Lugares poblados OSM → nodo de agua más cercano | Log-transform + MinMaxScaler |

**¿Por qué lugares poblados en vez de centroides distritales?** Los distritos grandes (Pachacamac, Cieneguilla) tienen centroides en zonas desérticas, lejos de los núcleos poblados. Usar nodos OSM `place=*` (barrios, urbanizaciones) como origen de medición es metodológicamente más riguroso. Los distritos sin nodos OSM usan el centroide como respaldo.

### Sensibilidad de pesos

Se probaron tres escenarios — correlaciones de Spearman > 0.95 confirman robustez:

| Escenario | Cobertura | Densidad | Distancia |
|-----------|-----------|----------|-----------|
| Igual (base) | 33 % | 33 % | 33 % |
| Demanda prioritaria | 25 % | 50 % | 25 % |
| Acceso prioritario | 50 % | 25 % | 25 % |

### Reproducibilidad de las pruebas estadísticas

Se fija `numpy.random.seed(42)` inmediatamente antes de cada llamada a `esda.Moran` / `esda.Moran_Local`, de modo que los p-valores y las asignaciones de clústeres LISA son idénticos entre ejecuciones (esda 2.9 usa el RNG global de NumPy para las pruebas de permutación).

## Reproducibilidad

### Requisitos

| Herramienta | Uso |
|-------------|-----|
| **Python 3.12** vía `uv` | Pipeline y análisis |
| **Docker Desktop** | PostGIS 16-3.4 |
| **GDAL / ogr2ogr** | Extracción del PBF de OSM (incluido con QGIS) |
| **QGIS 4** | Abrir `qgis/lima_water.qgz` (proyecto pre-estilizado) |

### Inicio rápido

```powershell
# 1. Instalar dependencias
uv sync

# 2. Iniciar PostGIS
docker compose up -d

# 3. Descargar datos OSM (una sola vez, 229 MB)
Invoke-WebRequest -Uri "https://download.geofabrik.de/south-america/peru-latest.osm.pbf" `
  -OutFile "data/raw/peru-latest.osm.pbf"

# 4. Verificar entorno
uv run python -c "import geopandas, esda; print('OK')"

# 5. Ejecutar el pipeline completo
uv run python test_pipeline.py

# 6. Abrir el notebook
uv run jupyter lab notebooks/analysis.ipynb
```

### Qué produce el pipeline

| Salida | Archivo | Descripción |
|--------|---------|-------------|
| Tabla IVH | `outputs/ivh_table.csv` | 43 distritos ordenados por vulnerabilidad (3 escenarios de pesos) |
| GeoJSON LISA | `outputs/lima_ivh_lisa.geojson` | Clústeres espaciales (HH, LL, LH, HL) para QGIS / web |
| Mapa interactivo | `outputs/map_interactive.html` | Coropleta Folium + marcadores LISA |
| Capas QGIS | `outputs/lima_water.gpkg` | GeoPackage con 4 capas (distritos_ivh, lisa_clusters, infra_agua_osm, lugares_poblados) |
| Proyecto QGIS | `qgis/lima_water.qgz` | Proyecto estilizado: coropleta IVH, LISA, marcadores de infraestructura |
| Mapa estático | `outputs/map_static.png` | Coropleta IVH A3, 300 dpi — `create_qgis_project.py` |
| Plantilla layout | `qgis/layouts/lima_water_print.qpt` | Plantilla QPT del Print Layout para edición en QGIS |
| Mapa de calor KDE | `outputs/kde_heatmap.png` | KDE ponderado A3, 300 dpi — `create_qgis_project.py` (QGIS Processing) o `generate_kde_heatmap.py` (Python puro) |

### Flujo de trabajo QGIS

El proyecto QGIS se genera programáticamente — no es necesario estilizar manualmente:

```powershell
# Regenerar GeoPackage (si outputs/lima_water.gpkg no existe)
uv run python scripts/export_qgis_layers.py

# Regenerar proyecto QGIS + map_static.png + kde_heatmap.png (requiere QGIS 4)
& "C:/Program Files/QGIS 4.0.2/bin/python-qgis.bat" scripts/create_qgis_project.py

# Alternativa: KDE en Python puro, sin necesidad de QGIS
uv run python scripts/generate_kde_heatmap.py
```

Luego abrir `qgis/lima_water.qgz` en QGIS — el proyecto carga las 4 capas ya estilizadas y con el Print Layout configurado.

## Fuentes de datos

| Fuente | Descripción | Año | Licencia |
|--------|-------------|-----|---------|
| [INEI — REDATAM](https://censos2017.inei.gob.pe/redatam/index.htm) | Censo 2017 — Acceso al agua por distrito | 2017 | Pública |
| [GADM 4.1](https://gadm.org/) | Límites administrativos (Nivel 3 — distrito) | 2022 | Libre para uso académico |
| [OpenStreetMap](https://www.openstreetmap.org/) | Infraestructura de agua y lugares poblados | 2026 | ODbL |
| [Geofabrik](https://download.geofabrik.de/) | Extracto OSM de Perú (PBF, procesado con GDAL ogr2ogr) | Diario | ODbL |

## Limitaciones

- **Los datos del Censo son de 2017** — los más recientes disponibles. La cobertura puede haber mejorado desde entonces, especialmente en zonas de expansión periurbana.
- **La cobertura OSM es variable** — los distritos rurales pueden tener menos infraestructura mapeada de la que realmente existe. El pipeline usa un extracto Geofabrik de Perú (229 MB) procesado localmente con GDAL ogr2ogr — completamente offline y reproducible. La API Overpass está disponible como respaldo.
- **Los pesos iguales en el escenario base** son una simplificación consciente. El análisis de sensibilidad confirma que los rankings son estables entre esquemas de ponderación (Spearman > 0.95).
- **Las fuentes informales de agua** (camiones cisterna, pilones compartidos) no quedan completamente capturadas por las métricas de red formal.
- **La granularidad es distrital** — no captura la desigualdad intra-distrital. El mapa de calor KDE aborda parcialmente esto.

## Estructura del proyecto

```
lima-water-access/
├── pyproject.toml                   # Dependencias (uv)
├── .python-version                  # Python 3.12
├── docker-compose.yml               # PostGIS 16-3.4
├── test_pipeline.py                 # Ejecutor del pipeline completo (un comando)
├── src/lima_water/
│   ├── config.py                    # Rutas, CRS, URL de BD
│   ├── census.py                    # Parser del Censo INEI 2017
│   ├── districts.py                 # Carga GADM + join censo + alias de nombres
│   ├── osm.py                       # Extracción OSM vía PBF Geofabrik + ogr2ogr
│   ├── postgis.py                   # Carga en BD, índices GIST, consultas espaciales
│   ├── ivh.py                       # Cálculo IVH + 3 escenarios de pesos
│   └── spatial.py                   # I de Moran + LISA (semilla=42 para reproducibilidad)
├── sql/
│   ├── 01_indexes.sql               # Índices espaciales GIST
│   └── 02_spatial_queries.sql       # Consulta CTE de distancias + respaldo centroide
├── scripts/
│   ├── export_qgis_layers.py        # Exporta 4 capas a outputs/lima_water.gpkg
│   ├── create_qgis_project.py       # Genera qgis/lima_water.qgz + map_static.png vía PyQGIS 4
│   └── generate_kde_heatmap.py      # Genera outputs/kde_heatmap.png (scipy + matplotlib)
├── notebooks/
│   └── analysis.ipynb               # Análisis narrativo de extremo a extremo
├── qgis/
│   ├── lima_water.qgz               # Proyecto QGIS 4 estilizado (generado por script)
│   └── layouts/
│       └── lima_water_print.qpt     # Plantilla QPT del Print Layout
├── data/
│   ├── osmconf.ini                  # Configuración GDAL para extracción OSM
│   └── raw/
│       ├── censo_agua_lima.xlsx     # Datos REDATAM — Censo INEI 2017
│       ├── censo_agua_lima.pdf      # Reporte original REDATAM (referencia)
│       ├── gadm41_PER_shp/          # Shapefiles GADM 4.1 — solo nivel 3 (distritos)
│       └── peru-latest.osm.pbf      # Extracto Geofabrik (descargar primero, 229 MB)
└── outputs/
    ├── ivh_table.csv                # 43 distritos ordenados por IVH
    ├── lima_ivh_lisa.geojson        # Clústeres LISA para QGIS / web
    ├── lima_water.gpkg              # GeoPackage con 4 capas para QGIS
    ├── map_interactive.html         # Coropleta Folium interactiva
    ├── map_static.png               # Print Layout A3, 300 dpi
    └── kde_heatmap.png              # Mapa de calor KDE ponderado, 300 dpi
```

## Licencia

El código fuente de este proyecto se distribuye bajo la [Licencia MIT](LICENSE).

Los datos de terceros mantienen sus licencias originales: datos del Censo INEI (uso público), límites GADM (libre para uso académico), OpenStreetMap (ODbL).

## Autor

Rodrigo Norabuena
