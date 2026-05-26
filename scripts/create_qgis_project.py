"""Generate qgis/lima_water.qgz using the PyQGIS API (headless, no GUI).

Run from the project root with the QGIS-bundled Python:

    & "C:/Program Files/QGIS 4.0.2/bin/python-qgis.bat" scripts/create_qgis_project.py

Produces:
    qgis/lima_water.qgz                — QGIS 4 project with styled layers + layouts
    qgis/layouts/lima_water_print.qpt  — reusable print layout template
    outputs/map_static.png             — IVH choropleth A3, 300 dpi
    outputs/kde_heatmap.png            — KDE heatmap A3, 300 dpi (requires
                                         export_qgis_layers.py run first for weights)
    outputs/kde_raster.tif             — intermediate KDE raster (can be deleted)

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
    QgsLayoutMeasurement,
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


def _safe_remove(path: str) -> None:
    """Remove existing file so GDAL's PNG driver can write a fresh one.

    GDAL's PNG driver does not support update access; if the output file
    already exists, the layout exporter emits ERROR 6 and may leave the file
    with only the frame/legend rendered but no map content.
    """
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass


def _compute_point_weights(points_layer, weight_field, districts_layer,
                           ivh_csv_path):
    """Return a per-point weights array (float).

    Order of preference:
      1. If ``weight_field`` exists in the points layer, use it directly.
      2. Otherwise spatial-join points with districts and look up
         ``hogares_sin_acceso`` from ``ivh_table.csv`` keyed on NAME_3_norm.
      3. If neither works, return None (caller should fall back to unweighted).
    """
    import csv

    point_fields = [f.name() for f in points_layer.fields()]
    if weight_field in point_fields:
        ws = []
        for feat in points_layer.getFeatures():
            v = feat.attribute(weight_field)
            ws.append(float(v) if v is not None else 0.0)
        return ws

    # Fallback: read CSV and do point-in-polygon via spatial index
    from qgis.core import QgsSpatialIndex, QgsGeometry

    if not Path(ivh_csv_path).exists():
        return None
    lookup = {}
    with open(ivh_csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                lookup[row["distrito"]] = float(row["hogares_sin_acceso"])
            except (KeyError, ValueError):
                pass
    if not lookup:
        return None

    # Map each district feature ID to its weight
    name_field = "NAME_3_norm"
    if name_field not in [f.name() for f in districts_layer.fields()]:
        return None

    feat_weight = {}
    feat_geom = {}
    for feat in districts_layer.getFeatures():
        nm = feat.attribute(name_field)
        if nm in lookup:
            feat_weight[feat.id()] = lookup[nm]
            feat_geom[feat.id()] = QgsGeometry(feat.geometry())

    sindex = QgsSpatialIndex(districts_layer.getFeatures())

    ws = []
    for feat in points_layer.getFeatures():
        pt_geom = feat.geometry()
        candidates = sindex.intersects(pt_geom.boundingBox())
        w = 0.0
        for fid in candidates:
            geom = feat_geom.get(fid)
            if geom is not None and geom.contains(pt_geom):
                w = feat_weight[fid]
                break
        ws.append(w)
    return ws


def _compute_gaussian_kde(layer, bbox, pixel_m, bw_m, weight_field=None,
                          districts_layer=None, ivh_csv_path=None):
    """Compute a weighted Gaussian KDE on a regular grid.

    Identical algorithm to ``scripts/generate_kde_heatmap.py``:
    weighted 2-D histogram + ``scipy.ndimage.gaussian_filter`` with
    sigma = bw_m / pixel_m.  Returns (array, geotransform) ready to save
    as a single-band GeoTIFF.

    If ``weight_field`` is not present in ``layer`` but ``districts_layer`` and
    ``ivh_csv_path`` are supplied, weights are derived via spatial join.
    """
    import numpy as np
    from scipy.ndimage import gaussian_filter

    xmin, ymin, xmax, ymax = bbox
    nx = int(round((xmax - xmin) / pixel_m))
    ny = int(round((ymax - ymin) / pixel_m))

    xs, ys = [], []
    for feat in layer.getFeatures():
        pt = feat.geometry().asPoint()
        xs.append(pt.x()); ys.append(pt.y())

    weights = None
    if weight_field is not None and districts_layer is not None and ivh_csv_path is not None:
        weights = _compute_point_weights(
            layer, weight_field, districts_layer, ivh_csv_path,
        )
    if weights is None:
        weights = [1.0] * len(xs)

    xs = np.asarray(xs); ys = np.asarray(ys); ws = np.asarray(weights, dtype=float)
    positive = ws[ws > 0]
    if positive.size:
        fill = float(np.median(positive))
        ws = np.where(ws > 0, ws, fill)
    else:
        ws = np.ones_like(ws)

    xe = np.linspace(xmin, xmax, nx + 1)
    ye = np.linspace(ymin, ymax, ny + 1)
    grid, _, _ = np.histogram2d(xs, ys, bins=[xe, ye], weights=ws)
    grid = grid.T  # rows = y, cols = x

    sigma_px = bw_m / pixel_m
    zz = gaussian_filter(grid, sigma=sigma_px)

    # GDAL GeoTIFF: y descends from ymax → ymin, so flip the array vertically
    geotransform = (xmin, pixel_m, 0.0, ymax, 0.0, -pixel_m)
    return zz[::-1].astype("float32"), geotransform


def _save_geotiff(array, geotransform, epsg, path):
    """Write a 2-D numpy array as a single-band GeoTIFF (Float32)."""
    from osgeo import gdal, osr

    nrows, ncols = array.shape
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(path, ncols, nrows, 1, gdal.GDT_Float32,
                    options=["COMPRESS=LZW", "TILED=YES"])
    ds.SetGeoTransform(geotransform)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).WriteArray(array)
    ds.FlushCache()
    ds = None


def _render_colorbar_png(path, v_min, v_max, label, cmap_name="inferno",
                         orientation="vertical"):
    """Render a standalone matplotlib colorbar to PNG.

    Used to give the KDE layout a Python-style continuous colorbar
    instead of the categorized raster legend that QGIS produces by default.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib as mpl

    if orientation == "vertical":
        fig, ax = plt.subplots(figsize=(1.3, 5.5))
    else:
        fig, ax = plt.subplots(figsize=(5.5, 1.0))

    norm = mpl.colors.Normalize(vmin=float(v_min), vmax=float(v_max))
    cb = mpl.colorbar.ColorbarBase(
        ax, cmap=plt.get_cmap(cmap_name), norm=norm, orientation=orientation,
    )
    cb.set_label(label, fontsize=10, labelpad=10)
    cb.ax.tick_params(labelsize=9)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

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
# PRINT LAYOUT IVH — A3 portrait (297 × 420 mm)
# Lima's UTM extent has aspect ≈ 0.68 (much taller than wide), so portrait
# fits the shape naturally and avoids the east-west overflow that landscape
# produces.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MM = QgsUnitTypes.LayoutMillimeters

layout = QgsPrintLayout(project)
layout.initializeDefaults()
layout.setName("Lima Water Access")

# Página A3 vertical
page = layout.pageCollection().pages()[0]
page.setPageSize(QgsLayoutSize(297, 420, MM))


def _pos(item, x, y, w, h):
    """Posiciona y redimensiona un elemento del layout."""
    item.attemptMove(QgsLayoutPoint(x, y, MM))
    item.attemptResize(QgsLayoutSize(w, h, MM))


# ── Título principal ───────────────────────────────────────────────────────────
lbl_title = QgsLayoutItemLabel(layout)
lbl_title.setText("Vulnerabilidad Hidrica en Lima Metropolitana")
lbl_title.setFont(_bold_font("Arial", 16))
lbl_title.setFontColor(QColor("#1a1a2e"))
lbl_title.setHAlign(_AlignLeft)
lbl_title.setVAlign(_AlignVCenter)
layout.addLayoutItem(lbl_title)
_pos(lbl_title, 10, 8, 277, 14)

# ── Subtítulo ─────────────────────────────────────────────────────────────────
lbl_sub = QgsLayoutItemLabel(layout)
lbl_sub.setText("Indice IVH 2017  |  Deficit, densidad y distancia a infraestructura OSM")
lbl_sub.setFont(_font("Arial", 9))
lbl_sub.setFontColor(QColor("#555555"))
lbl_sub.setHAlign(_AlignLeft)
layout.addLayoutItem(lbl_sub)
_pos(lbl_sub, 10, 24, 277, 8)

# ── Marco del mapa ────────────────────────────────────────────────────────────
# Aspect ratio del mapa (220×325) ≈ 0.677, idéntico al de la extensión de
# Lima en UTM 18S → encaja sin desbordamiento.
map_item = QgsLayoutItemMap(layout)
map_item.setCrs(QgsCoordinateReferenceSystem("EPSG:32718"))
map_item.setFrameEnabled(True)
map_item.setFrameStrokeWidth(QgsLayoutMeasurement(0.3, MM))
map_item.setFrameStrokeColor(QColor("#333333"))
# In headless mode there is no active canvas, so the map item has no layers
# to render unless we set them explicitly.  Order: first = background.
map_item.setLayers([layer_d, layer_l, layer_i])
map_item.setKeepLayerSet(True)
layout.addLayoutItem(map_item)
_pos(map_item, 10, 36, 220, 325)
# setExtent MUST come AFTER _pos: when the item's physical size changes,
# QGIS reflows the extent to fit the new aspect ratio.  Calling setExtent
# before _pos leaves the extent with NaN values and the map renders blank.
map_item.setExtent(QgsRectangle(249197, 8609962, 327156, 8725142))
map_item.refresh()

# ── Leyenda (panel vertical a la derecha) ─────────────────────────────────────
legend = QgsLayoutItemLegend(layout)
legend.setLinkedMap(map_item)
legend.setAutoUpdateModel(True)
legend.setTitle("Leyenda")
legend.setFrameEnabled(True)
legend.setResizeToContents(True)
layout.addLayoutItem(legend)
_pos(legend, 235, 36, 55, 325)

# ── Barra de escala (superpuesta en el mapa, esquina inf-izq) ────────────────
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
_pos(scale, 15, 345, 80, 8)

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
    _pos(north_item, 200, 338, 22, 22)
    print(f"  Norte SVG: {north_svg}")
else:
    north_lbl = QgsLayoutItemLabel(layout)
    north_lbl.setText("N")
    north_lbl.setFont(_bold_font("Arial", 14))
    north_lbl.setFontColor(QColor("#1a1a1a"))
    north_lbl.setHAlign(_AlignCenter)
    north_lbl.setVAlign(_AlignVCenter)
    north_lbl.setBackgroundEnabled(True)
    north_lbl.setBackgroundColor(QColor(255, 255, 255, 200))
    layout.addLayoutItem(north_lbl)
    _pos(north_lbl, 200, 344, 22, 14)
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
_pos(lbl_attr, 10, 405, 277, 8)

# Registrar layout en el proyecto
project.layoutManager().addLayout(layout)
print("  Print Layout A3 creado")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXPORTAR PNG y guardar plantilla QPT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
exporter = QgsLayoutExporter(layout)

img_settings = QgsLayoutExporter.ImageExportSettings()
img_settings.dpi = 300

_safe_remove(OUT_PNG)
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
# KDE HEATMAP — Gaussian (scipy) + Layout A3 portrait + colorbar matplotlib
# Replicates the visual style of scripts/generate_kde_heatmap.py: weighted
# Gaussian KDE (sigma=2000 m), Inferno colormap, continuous colorbar on the
# side, portrait orientation that fits Lima's tall shape.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try:
    from qgis.core import (
        QgsColorRampShader, QgsRasterLayer, QgsRasterShader,
        QgsSingleBandPseudoColorRenderer,
    )

    OUT_KDE_TIF = str(ROOT / "outputs" / "kde_raster.tif")
    OUT_KDE_PNG = str(ROOT / "outputs" / "kde_heatmap.png")
    OUT_KDE_CBAR = str(ROOT / "outputs" / "kde_colorbar.png")

    BBOX_LIMA = (249197, 8609962, 327156, 8725142)
    PIXEL_M, BW_M = 100, 2000

    print(f"  KDE: Gaussian sigma={BW_M} m, peso = hogares_sin_acceso por distrito")

    # Compute weighted Gaussian KDE — same algorithm as generate_kde_heatmap.py.
    # Weights come either from the points layer field (if export_qgis_layers.py
    # was re-run) or from a spatial join against the districts layer + IVH CSV.
    zz, geotransform = _compute_gaussian_kde(
        layer_p, BBOX_LIMA, PIXEL_M, BW_M,
        weight_field="hogares_sin_acceso",
        districts_layer=layer_d,
        ivh_csv_path=str(ROOT / "outputs" / "ivh_table.csv"),
    )
    v_min, v_max = float(zz.min()), float(zz.max())
    print(f"  KDE: grid {zz.shape[1]}x{zz.shape[0]}, valores [{v_min:.2f}, {v_max:.2f}]")

    _safe_remove(OUT_KDE_TIF)
    _save_geotiff(zz, geotransform, 32718, OUT_KDE_TIF)

    kde_layer = QgsRasterLayer(OUT_KDE_TIF, "KDE — Densidad hidrica")
    if not kde_layer.isValid():
        raise RuntimeError("KDE raster no valido")

    # ── Estilo Inferno (mismas paradas que el script Python/matplotlib) ──────
    inferno = [
        (0.000, "#000004"),
        (0.250, "#420a68"),
        (0.500, "#932667"),
        (0.750, "#dd513a"),
        (0.875, "#fca50a"),
        (1.000, "#fcffa4"),
    ]
    ramp_items = [
        QgsColorRampShader.ColorRampItem(
            v_min + frac * (v_max - v_min), QColor(hex_c)
        )
        for frac, hex_c in inferno
    ]
    color_ramp = QgsColorRampShader()
    color_ramp.setColorRampType(QgsColorRampShader.Interpolated)
    color_ramp.setColorRampItemList(ramp_items)

    shader = QgsRasterShader()
    shader.setRasterShaderFunction(color_ramp)

    renderer = QgsSingleBandPseudoColorRenderer(
        kde_layer.dataProvider(), 1, shader
    )
    kde_layer.setRenderer(renderer)
    kde_layer.triggerRepaint()

    project.addMapLayer(kde_layer, False)
    root.insertChildNode(0, QgsLayerTreeLayer(kde_layer))

    # ── Colorbar continuo (renderizado con matplotlib, como en Python) ──────
    _render_colorbar_png(
        OUT_KDE_CBAR, v_min, v_max,
        label="Densidad ponderada\n(hogares sin acceso formal)",
        cmap_name="inferno", orientation="vertical",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Layout KDE — A3 portrait (297 × 420 mm)
    # ─────────────────────────────────────────────────────────────────────────
    kde_layout = QgsPrintLayout(project)
    kde_layout.initializeDefaults()
    kde_layout.setName("KDE Vulnerabilidad Hidrica")
    kde_layout.pageCollection().pages()[0].setPageSize(QgsLayoutSize(297, 420, MM))

    # Título
    lbl_k_title = QgsLayoutItemLabel(kde_layout)
    lbl_k_title.setText(
        "Densidad de Hogares sin Acceso Formal al Agua\nLima Metropolitana"
    )
    lbl_k_title.setFont(_bold_font("Arial", 14))
    lbl_k_title.setFontColor(QColor("#1a1a2e"))
    lbl_k_title.setHAlign(_AlignLeft)
    kde_layout.addLayoutItem(lbl_k_title)
    _pos(lbl_k_title, 10, 8, 277, 18)

    # Marco del mapa (aspect ratio 235/345 ≈ 0.68, encaja Lima sin desbordar)
    kde_map = QgsLayoutItemMap(kde_layout)
    kde_map.setCrs(QgsCoordinateReferenceSystem("EPSG:32718"))
    kde_map.setFrameEnabled(True)
    kde_map.setFrameStrokeWidth(QgsLayoutMeasurement(0.3, MM))
    kde_map.setFrameStrokeColor(QColor("#333333"))
    kde_map.setLayers([kde_layer, layer_d])   # KDE encima, distritos para contornos
    kde_map.setKeepLayerSet(True)
    kde_layout.addLayoutItem(kde_map)
    _pos(kde_map, 10, 32, 235, 345)
    kde_map.setExtent(QgsRectangle(*BBOX_LIMA))
    kde_map.refresh()

    # Colorbar continuo a la derecha (Picture de matplotlib)
    kde_cbar = QgsLayoutItemPicture(kde_layout)
    kde_cbar.setPicturePath(OUT_KDE_CBAR)
    kde_layout.addLayoutItem(kde_cbar)
    _pos(kde_cbar, 250, 60, 40, 250)

    # Barra de escala (superpuesta en esquina inf-izq del mapa)
    kde_scale = QgsLayoutItemScaleBar(kde_layout)
    kde_scale.setLinkedMap(kde_map)
    try:
        kde_scale.setStyle("Single Box")
    except Exception:
        pass
    kde_scale.setUnitsPerSegment(10000)
    kde_scale.setNumberOfSegments(3)
    kde_scale.setNumberOfSegmentsLeft(0)
    kde_scale.setUnitLabel("km")
    kde_scale.setFont(_font("Arial", 7))
    kde_scale.setBackgroundEnabled(True)
    kde_scale.setBackgroundColor(QColor(255, 255, 255, 180))
    kde_layout.addLayoutItem(kde_scale)
    _pos(kde_scale, 15, 360, 80, 8)

    # Flecha de norte (esquina inf-derecha del mapa)
    north_svg_kde = _find_north_svg()
    if north_svg_kde:
        kde_north = QgsLayoutItemPicture(kde_layout)
        kde_north.setPicturePath(north_svg_kde)
        try:
            kde_north.setNorthMode(QgsLayoutItemPicture.GridNorth)
        except Exception:
            pass
        kde_north.setBackgroundEnabled(True)
        kde_north.setBackgroundColor(QColor(255, 255, 255, 180))
        kde_layout.addLayoutItem(kde_north)
        _pos(kde_north, 215, 350, 22, 22)

    # Atribución
    lbl_k_attr = QgsLayoutItemLabel(kde_layout)
    lbl_k_attr.setText(
        "Fuentes: INEI 2017  |  OpenStreetMap (ODbL)  |  GADM 4.1  |  "
        "Proyeccion: UTM Zona 18S (EPSG:32718)  |  2026"
    )
    lbl_k_attr.setFont(_font("Arial", 7))
    lbl_k_attr.setFontColor(QColor("#777777"))
    lbl_k_attr.setHAlign(_AlignLeft)
    kde_layout.addLayoutItem(lbl_k_attr)
    _pos(lbl_k_attr, 10, 405, 277, 8)

    project.layoutManager().addLayout(kde_layout)

    # ── Exportar PNG ──────────────────────────────────────────────────────────
    kde_exp = QgsLayoutExporter(kde_layout)
    kde_img = QgsLayoutExporter.ImageExportSettings()
    kde_img.dpi = 300
    _safe_remove(OUT_KDE_PNG)
    r = kde_exp.exportToImage(OUT_KDE_PNG, kde_img)
    if r == QgsLayoutExporter.Success:
        size_kb = Path(OUT_KDE_PNG).stat().st_size // 1024
        print(f"  outputs/kde_heatmap.png exportado ({size_kb} KB, 300 dpi)")
    else:
        print(f"  AVISO KDE PNG: codigo {r}")

except Exception as _kde_err:
    import traceback
    print(f"  AVISO: KDE omitido — {_kde_err}")
    traceback.print_exc()

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
