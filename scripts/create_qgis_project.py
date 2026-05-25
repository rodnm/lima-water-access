"""Generate qgis/lima_water.qgz using the PyQGIS API (headless, no GUI).

Run from the project root with the QGIS-bundled Python:

    & "C:/Program Files/QGIS 4.0.2/bin/python-qgis.bat" scripts/create_qgis_project.py

Produces qgis/lima_water.qgz with four styled layers:
    distritos_ivh    — graduated IVH choropleth (YlOrRd, Jenks 5 classes)
    lisa_clusters    — categorized LISA labels (HH/LL/LH/Not significant)
    infra_agua_osm   — categorized water infrastructure markers
    lugares_poblados — simple grey markers (hidden by default)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
GPKG = str(ROOT / "outputs" / "lima_water.gpkg")
OUT  = str(ROOT / "qgis" / "lima_water.qgz")

# ── QGIS prefix (already set by python-qgis.bat; explicit fallback) ───────────
QGIS_PREFIX = r"C:\Program Files\QGIS 4.0.2\apps\qgis"
os.environ.setdefault("QGIS_PREFIX_PATH", QGIS_PREFIX)

# ── Import PyQGIS ──────────────────────────────────────────────────────────────
from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsGraduatedSymbolRenderer,
    QgsLayerTreeLayer,
    QgsMarkerSymbol,
    QgsProject,
    QgsReferencedRectangle,
    QgsRectangle,
    QgsRendererCategory,
    QgsRendererRange,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)

# ── Initialise QGIS (headless) ─────────────────────────────────────────────────
app = QgsApplication([], False)
app.setPrefixPath(QGIS_PREFIX, True)
app.initQgis()

try:
    from qgis.core import Qgis as _Qgis
    print(f"QGIS {_Qgis.QGIS_VERSION}")
except Exception:
    print("QGIS initialized")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LAYER 1 — distritos_ivh: graduated choropleth on IVH_equal
# Jenks 5-class breaks precomputed with mapclassify.NaturalBreaks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
layer_d = QgsVectorLayer(f"{GPKG}|layername=distritos_ivh", "IVH por Distrito", "ogr")
if not layer_d.isValid():
    sys.exit(f"ERROR: distritos_ivh failed to load from {GPKG}")

_BREAKS = [-0.019, 0.095, 0.271, 0.423, 0.738, 1.034]
_COLORS = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"]
_LABELS = [
    "Muy baja  (< 0.10)",
    "Baja      (0.10 – 0.27)",
    "Media     (0.27 – 0.42)",
    "Alta      (0.42 – 0.74)",
    "Muy alta  (> 0.74)",
]

ivh_ranges = []
for i in range(5):
    sym = QgsFillSymbol.createSimple(
        {"color": _COLORS[i], "outline_color": "#666666", "outline_width": "0.15"}
    )
    ivh_ranges.append(QgsRendererRange(_BREAKS[i], _BREAKS[i + 1], sym, _LABELS[i]))

renderer_d = QgsGraduatedSymbolRenderer("IVH_equal", ivh_ranges)
layer_d.setRenderer(renderer_d)
print(f"  distritos_ivh  → graduated ({layer_d.featureCount()} features)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LAYER 2 — lisa_clusters: categorized LISA spatial autocorrelation labels
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
layer_l = QgsVectorLayer(f"{GPKG}|layername=lisa_clusters", "Clusters LISA", "ogr")
if not layer_l.isValid():
    sys.exit(f"ERROR: lisa_clusters failed to load from {GPKG}")

_LISA = [
    ("HH (High-High)",  "#d73027", "HH — Alta vulnerabilidad"),
    ("LL (Low-Low)",    "#4575b4", "LL — Baja vulnerabilidad"),
    ("LH (Low-High)",   "#91bfdb", "LH — Baja rodeada de alta"),
    ("HL (High-Low)",   "#fc8d59", "HL — Alta rodeada de baja"),
    ("Not significant", "#eeeeee", "No significativo"),
]

lisa_cats = []
for val, color, label in _LISA:
    sym = QgsFillSymbol.createSimple(
        {"color": color, "outline_color": "#999999", "outline_width": "0.2"}
    )
    sym.setOpacity(0.7)
    lisa_cats.append(QgsRendererCategory(val, sym, label))

renderer_l = QgsCategorizedSymbolRenderer("lisa_label", lisa_cats)
layer_l.setRenderer(renderer_l)
print(f"  lisa_clusters  → categorized ({layer_l.featureCount()} features)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LAYER 3 — infra_agua_osm: categorized markers by infrastructure type
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
layer_i = QgsVectorLayer(
    f"{GPKG}|layername=infra_agua_osm", "Infraestructura de Agua", "ogr"
)
if not layer_i.isValid():
    sys.exit(f"ERROR: infra_agua_osm failed to load from {GPKG}")

_INFRA = [
    ("drinking_water",  "circle",  "#2166ac", "2",   "Punto de agua potable"),
    ("water_tower",     "square",  "#08306b", "3",   "Torre de agua"),
    ("storage_tank",    "diamond", "#006d2c", "2.5", "Tanque de almacenamiento"),
    ("pumping_station", "star",    "#6a51a3", "2.5", "Estación de bombeo"),
]

infra_cats = []
for val, shape, color, size, label in _INFRA:
    sym = QgsMarkerSymbol.createSimple(
        {"name": shape, "color": color, "size": size,
         "outline_color": "#ffffff", "outline_width": "0.2"}
    )
    infra_cats.append(QgsRendererCategory(val, sym, label))

renderer_i = QgsCategorizedSymbolRenderer("category", infra_cats)
layer_i.setRenderer(renderer_i)
print(f"  infra_agua_osm → categorized ({layer_i.featureCount()} features)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LAYER 4 — lugares_poblados: simple grey markers (hidden by default)
#           Mainly used for KDE heatmap in Processing Toolbox
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
layer_p = QgsVectorLayer(
    f"{GPKG}|layername=lugares_poblados", "Lugares Poblados", "ogr"
)
if not layer_p.isValid():
    sys.exit(f"ERROR: lugares_poblados failed to load from {GPKG}")

sym_p = QgsMarkerSymbol.createSimple(
    {"name": "circle", "color": "#888888", "size": "1", "outline_style": "no"}
)
sym_p.setOpacity(0.4)
layer_p.setRenderer(QgsSingleSymbolRenderer(sym_p))
print(f"  lugares_poblados → single symbol ({layer_p.featureCount()} features)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Assemble project
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
project = QgsProject.instance()
project.setTitle("Lima Water Access — IVH 2017")
project.setCrs(QgsCoordinateReferenceSystem("EPSG:32718"))

# Use relative paths so the .qgz is portable within the repo
try:
    from qgis.core import Qgis
    project.setFilePathStorage(Qgis.FilePathType.Relative)
except (AttributeError, TypeError):
    pass  # QGIS version may differ; default is fine

# Add layers to map store WITHOUT adding to legend tree (addToLegend=False)
for lyr in (layer_d, layer_l, layer_p, layer_i):
    project.addMapLayer(lyr, False)

# Rebuild layer tree: top of panel → rendered on top
root = project.layerTreeRoot()
root.insertChildNode(0, QgsLayerTreeLayer(layer_i))   # top: infra points
root.insertChildNode(1, QgsLayerTreeLayer(layer_p))   # places (hidden)
root.insertChildNode(2, QgsLayerTreeLayer(layer_l))   # LISA overlay
root.insertChildNode(3, QgsLayerTreeLayer(layer_d))   # bottom: IVH choropleth

# Hide lugares_poblados in panel
node_p = root.findLayer(layer_p.id())
if node_p:
    node_p.setItemVisibilityChecked(False)

# Initial map extent — Lima, UTM 18S, with 5 % padding
try:
    extent_rect = QgsReferencedRectangle(
        QgsRectangle(249197, 8609962, 327156, 8725142),
        QgsCoordinateReferenceSystem("EPSG:32718"),
    )
    project.viewSettings().setDefaultViewExtent(extent_rect)
except AttributeError:
    pass  # older QGIS API; extent will default to layer bounds

# ── Write ──────────────────────────────────────────────────────────────────────
Path(OUT).parent.mkdir(parents=True, exist_ok=True)
ok = project.write(OUT)
app.exitQgis()

if ok:
    size_kb = Path(OUT).stat().st_size // 1024
    print(f"\n✓  {OUT}  ({size_kb} KB)")
else:
    sys.exit("✗  project.write() returned False")
