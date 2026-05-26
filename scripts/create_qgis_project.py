"""Generate qgis/lima_water.qgz using the PyQGIS API (headless, no GUI).

Run from the project root with the QGIS-bundled Python:

    & "C:/Program Files/QGIS 4.0.2/bin/python-qgis.bat" scripts/create_qgis_project.py

Produces:
    qgis/lima_water.qgz           — QGIS 4 project with styled layers + print layout
    qgis/layouts/lima_water_print.qpt  — reusable print layout template
    outputs/map_static.png        — A3 map exported at 300 dpi

Layers (panel order top → bottom):
    Infraestructura OSM
        infra_agua_osm   — categorized markers by type
        lugares_poblados — simple grey markers (hidden)
    Analisis IVH
        lisa_clusters    — categorized LISA labels (70 % opacity)
        distritos_ivh    — graduated IVH choropleth + district name labels
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
GPKG     = str(ROOT / "outputs" / "lima_water.gpkg")
OUT_QGZ  = str(ROOT / "qgis" / "lima_water.qgz")
OUT_PNG  = str(ROOT / "outputs" / "map_static.png")
OUT_QPT  = str(ROOT / "qgis" / "layouts" / "lima_water_print.qpt")

QGIS_PREFIX = r"C:\Program Files\QGIS 4.0.2\apps\qgis"
os.environ.setdefault("QGIS_PREFIX_PATH", QGIS_PREFIX)

# ── PyQGIS imports ─────────────────────────────────────────────────────────────
from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsGraduatedSymbolRenderer,
    QgsLayerTreeLayer,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPrintLayout,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsProject,
    QgsProperty,
    QgsReadWriteContext,
    QgsReferencedRectangle,
    QgsRectangle,
    QgsRendererCategory,
    QgsRendererRange,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QFont
    _AlignLeft    = Qt.AlignmentFlag.AlignLeft
    _AlignCenter  = Qt.AlignmentFlag.AlignCenter
    _AlignVCenter = Qt.AlignmentFlag.AlignVCenter
except ModuleNotFoundError:
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QColor, QFont
    _AlignLeft    = Qt.AlignLeft
    _AlignCenter  = Qt.AlignCenter
    _AlignVCenter = Qt.AlignVCenter


def _bold_font(family: str, size: int) -> QFont:
    f = QFont(family, size)
    f.setBold(True)
    return f


def _font(family: str, size: int) -> QFont:
    return QFont(family, size)

# ── Initialise QGIS (headless) ─────────────────────────────────────────────────
app = QgsApplication([], False)
app.setPrefixPath(QGIS_PREFIX, True)
app.initQgis()

try:
    from qgis.core import Qgis as _Qgis
    print(f"QGIS {_Qgis.QGIS_VERSION}")
except Exception:
    print("QGIS inicializado")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CAPAS — renderers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── distritos_ivh — graduated choropleth (Jenks 5 clases) ─────────────────────
layer_d = QgsVectorLayer(f"{GPKG}|layername=distritos_ivh", "IVH por Distrito", "ogr")
if not layer_d.isValid():
    sys.exit(f"ERROR: distritos_ivh no cargó desde {GPKG}")

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
        {"color": _COLORS[i], "outline_color": "#808080", "outline_width": "0.15"}
    )
    ivh_ranges.append(QgsRendererRange(_BREAKS[i], _BREAKS[i + 1], sym, _LABELS[i]))

layer_d.setRenderer(QgsGraduatedSymbolRenderer("IVH_equal", ivh_ranges))
print(f"  distritos_ivh  → graduated ({layer_d.featureCount()} features)")

# ── Etiquetas de nombres de distrito (todos; QGIS resuelve colisiones) ─────────
try:
    pal = QgsPalLayerSettings()
    pal.fieldName = "NAME_3"
    pal.enabled = True

    txt = QgsTextFormat()
    txt.setFont(_bold_font("Arial", 6))
    txt.setColor(QColor("#1a1a1a"))
    txt.setSizeUnit(QgsUnitTypes.RenderPoints)

    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.8)
    buf.setSizeUnit(QgsUnitTypes.RenderMillimeters)
    buf.setColor(QColor("white"))
    txt.setBuffer(buf)

    pal.setFormat(txt)
    layer_d.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    layer_d.setLabelsEnabled(True)
    print("  distritos_ivh  → etiquetas activadas")
except Exception as e:
    print(f"  AVISO etiquetas: {e}")

# ── lisa_clusters — categorized LISA labels ────────────────────────────────────
layer_l = QgsVectorLayer(f"{GPKG}|layername=lisa_clusters", "Clusteres LISA", "ogr")
if not layer_l.isValid():
    sys.exit(f"ERROR: lisa_clusters no cargó desde {GPKG}")

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

layer_l.setRenderer(QgsCategorizedSymbolRenderer("lisa_label", lisa_cats))
print(f"  lisa_clusters  → categorized ({layer_l.featureCount()} features)")

# ── infra_agua_osm — categorized markers ──────────────────────────────────────
layer_i = QgsVectorLayer(
    f"{GPKG}|layername=infra_agua_osm", "Infraestructura de Agua", "ogr"
)
if not layer_i.isValid():
    sys.exit(f"ERROR: infra_agua_osm no cargó desde {GPKG}")

_INFRA = [
    ("drinking_water",  "circle",  "#2166ac", "2",   "Punto de agua potable"),
    ("water_tower",     "square",  "#08306b", "3",   "Torre de agua"),
    ("storage_tank",    "diamond", "#006d2c", "2.5", "Tanque de almacenamiento"),
    ("pumping_station", "star",    "#6a51a3", "2.5", "Estacion de bombeo"),
]

infra_cats = []
for val, shape, color, size, label in _INFRA:
    sym = QgsMarkerSymbol.createSimple(
        {"name": shape, "color": color, "size": size,
         "outline_color": "#ffffff", "outline_width": "0.2"}
    )
    infra_cats.append(QgsRendererCategory(val, sym, label))

layer_i.setRenderer(QgsCategorizedSymbolRenderer("category", infra_cats))
print(f"  infra_agua_osm → categorized ({layer_i.featureCount()} features)")

# ── lugares_poblados — simple grey marker (oculto por defecto) ─────────────────
layer_p = QgsVectorLayer(
    f"{GPKG}|layername=lugares_poblados", "Lugares Poblados", "ogr"
)
if not layer_p.isValid():
    sys.exit(f"ERROR: lugares_poblados no cargó desde {GPKG}")

sym_p = QgsMarkerSymbol.createSimple(
    {"name": "circle", "color": "#888888", "size": "1", "outline_style": "no"}
)
sym_p.setOpacity(0.4)
layer_p.setRenderer(QgsSingleSymbolRenderer(sym_p))
print(f"  lugares_poblados → single symbol ({layer_p.featureCount()} features)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROYECTO — configuración base
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
project = QgsProject.instance()
project.setTitle("Acceso al Agua en Lima — IVH 2017")
project.setCrs(QgsCoordinateReferenceSystem("EPSG:32718"))

try:
    from qgis.core import Qgis
    project.setFilePathStorage(Qgis.FilePathType.Relative)
except (AttributeError, TypeError):
    pass

# Añadir capas al almacén del proyecto (sin agregar al árbol aún)
for lyr in (layer_d, layer_l, layer_p, layer_i):
    project.addMapLayer(lyr, False)

# ── Árbol de capas con grupos ──────────────────────────────────────────────────
root = project.layerTreeRoot()

# Grupo "Infraestructura OSM" (arriba del panel → se renderiza encima)
g_osm = root.insertGroup(0, "Infraestructura OSM")
g_osm.insertChildNode(0, QgsLayerTreeLayer(layer_i))  # encima dentro del grupo
g_osm.insertChildNode(1, QgsLayerTreeLayer(layer_p))  # debajo (oculto)

# Grupo "Analisis IVH" (abajo del panel → se renderiza primero como fondo)
g_ivh = root.insertGroup(1, "Analisis IVH")
g_ivh.insertChildNode(0, QgsLayerTreeLayer(layer_l))  # LISA encima
g_ivh.insertChildNode(1, QgsLayerTreeLayer(layer_d))  # IVH de fondo

# Ocultar lugares_poblados
node_p = g_osm.findLayer(layer_p.id())
if node_p:
    node_p.setItemVisibilityChecked(False)

# Extent inicial de Lima (UTM 18S, con 5 % de margen)
try:
    extent_rect = QgsReferencedRectangle(
        QgsRectangle(249197, 8609962, 327156, 8725142),
        QgsCoordinateReferenceSystem("EPSG:32718"),
    )
    project.viewSettings().setDefaultViewExtent(extent_rect)
except AttributeError:
    pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PRINT LAYOUT — A3 horizontal (420 × 297 mm)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MM = QgsUnitTypes.LayoutMillimeters

layout = QgsPrintLayout(project)
layout.initializeDefaults()
layout.setName("Lima Water Access")

# Página A3 horizontal
page = layout.pageCollection().pages()[0]
page.setPageSize(QgsLayoutSize(420, 297, MM))


def _pos(item, x, y, w, h):
    """Posiciona y redimensiona un elemento del layout."""
    item.attemptMove(QgsLayoutPoint(x, y, MM))
    item.attemptResize(QgsLayoutSize(w, h, MM))


# ── Título principal ───────────────────────────────────────────────────────────
lbl_title = QgsLayoutItemLabel(layout)
lbl_title.setText("Vulnerabilidad Hidrica en Lima Metropolitana")
lbl_title.setFont(_bold_font("Arial", 18))
lbl_title.setFontColor(QColor("#1a1a2e"))
lbl_title.setHAlign(_AlignLeft)
lbl_title.setVAlign(_AlignVCenter)
layout.addLayoutItem(lbl_title)
_pos(lbl_title, 10, 6, 400, 18)

# ── Subtítulo ─────────────────────────────────────────────────────────────────
lbl_sub = QgsLayoutItemLabel(layout)
lbl_sub.setText(
    "Indice IVH 2017  |  Deficit de cobertura  |  Densidad de hogares sin acceso"
    "  |  Distancia a infraestructura OSM"
)
lbl_sub.setFont(_font("Arial", 9))
lbl_sub.setFontColor(QColor("#555555"))
lbl_sub.setHAlign(_AlignLeft)
layout.addLayoutItem(lbl_sub)
_pos(lbl_sub, 10, 26, 400, 8)

# ── Marco del mapa ────────────────────────────────────────────────────────────
map_item = QgsLayoutItemMap(layout)
map_item.setExtent(QgsRectangle(249197, 8609962, 327156, 8725142))
map_item.setCrs(QgsCoordinateReferenceSystem("EPSG:32718"))
map_item.setFrameEnabled(True)
# In headless mode there is no active canvas, so the map item has no layers
# to render unless we set them explicitly.  Order: first = background.
map_item.setLayers([layer_d, layer_l, layer_i])
map_item.setKeepLayerSet(True)
layout.addLayoutItem(map_item)
_pos(map_item, 10, 36, 292, 228)

# ── Leyenda ───────────────────────────────────────────────────────────────────
legend = QgsLayoutItemLegend(layout)
legend.setLinkedMap(map_item)
legend.setAutoUpdateModel(True)
legend.setTitle("Leyenda")
legend.setFrameEnabled(True)
legend.setResizeToContents(True)
layout.addLayoutItem(legend)
_pos(legend, 308, 36, 102, 228)

# ── Barra de escala ───────────────────────────────────────────────────────────
scale = QgsLayoutItemScaleBar(layout)
scale.setLinkedMap(map_item)
try:
    scale.setStyle("Single Box")
except Exception:
    pass
scale.setUnitsPerSegment(10000)   # 10 km por segmento
scale.setNumberOfSegments(3)
scale.setNumberOfSegmentsLeft(0)
scale.setUnitLabel("km")
scale.setFont(_font("Arial", 7))
scale.setBackgroundEnabled(True)
scale.setBackgroundColor(QColor(255, 255, 255, 180))
layout.addLayoutItem(scale)
_pos(scale, 14, 252, 110, 8)

# ── Flecha de norte ───────────────────────────────────────────────────────────
def _find_north_svg() -> str | None:
    candidates = [
        r"C:\Program Files\QGIS 4.0.2\apps\qgis\svg\north_arrows\NorthArrow_01.svg",
        r"C:\Program Files\QGIS 4.0.2\apps\qgis\svg\north_arrows\NorthArrow_02.svg",
        r"C:\Program Files\QGIS 4.0.2\share\qgis\svg\north_arrows\NorthArrow_01.svg",
    ]
    candidates += glob.glob(
        r"C:\Program Files\QGIS 4.0.2\**\*orth*rrow*.svg", recursive=True
    )[:5]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


north_svg = _find_north_svg()
if north_svg:
    north_item = QgsLayoutItemPicture(layout)
    north_item.setPicturePath(north_svg)
    try:
        north_item.setNorthMode(QgsLayoutItemPicture.GridNorth)
    except AttributeError:
        pass
    north_item.setBackgroundEnabled(True)
    north_item.setBackgroundColor(QColor(255, 255, 255, 180))
    layout.addLayoutItem(north_item)
    _pos(north_item, 272, 240, 24, 30)
    print(f"  Norte SVG: {north_svg}")
else:
    # Fallback: etiqueta de texto con símbolo unicode
    north_lbl = QgsLayoutItemLabel(layout)
    north_lbl.setText("N")
    north_lbl.setFont(_bold_font("Arial", 14))
    north_lbl.setFontColor(QColor("#1a1a1a"))
    north_lbl.setHAlign(_AlignCenter)
    north_lbl.setVAlign(_AlignVCenter)
    north_lbl.setBackgroundEnabled(True)
    north_lbl.setBackgroundColor(QColor(255, 255, 255, 200))
    layout.addLayoutItem(north_lbl)
    _pos(north_lbl, 272, 244, 24, 14)
    print("  Norte: texto (SVG no encontrado)")

# ── Atribución / fuentes ──────────────────────────────────────────────────────
lbl_attr = QgsLayoutItemLabel(layout)
lbl_attr.setText(
    "Fuentes: INEI 2017  |  OpenStreetMap (ODbL)  |  GADM 4.1  |  "
    "Proyeccion: UTM Zona 18S (EPSG:32718)  |  2026"
)
lbl_attr.setFont(_font("Arial", 7))
lbl_attr.setFontColor(QColor("#777777"))
lbl_attr.setHAlign(_AlignLeft)
layout.addLayoutItem(lbl_attr)
_pos(lbl_attr, 10, 272, 400, 10)

# Registrar layout en el proyecto
project.layoutManager().addLayout(layout)
print("  Print Layout A3 creado")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXPORTAR PNG y guardar plantilla QPT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
exporter = QgsLayoutExporter(layout)

img_settings = QgsLayoutExporter.ImageExportSettings()
img_settings.dpi = 300

result = exporter.exportToImage(OUT_PNG, img_settings)
if result == QgsLayoutExporter.Success:
    size_kb = Path(OUT_PNG).stat().st_size // 1024
    print(f"  outputs/map_static.png exportado ({size_kb} KB, 300 dpi)")
else:
    print(f"  AVISO: exportToImage devolvio codigo {result}")

# Plantilla QPT
Path(OUT_QPT).parent.mkdir(parents=True, exist_ok=True)
try:
    layout.saveAsTemplate(OUT_QPT, QgsReadWriteContext())
    print(f"  qgis/layouts/lima_water_print.qpt guardado")
except Exception as e:
    print(f"  AVISO QPT: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GUARDAR PROYECTO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Path(OUT_QGZ).parent.mkdir(parents=True, exist_ok=True)
ok = project.write(OUT_QGZ)
app.exitQgis()

if ok:
    size_kb = Path(OUT_QGZ).stat().st_size // 1024
    print(f"\n✓  {OUT_QGZ}  ({size_kb} KB)")
else:
    sys.exit("✗  project.write() devolvio False")
