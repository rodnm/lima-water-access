"""Run the full pipeline end-to-end. Use: uv run python test_pipeline.py"""
import sys
import warnings

from src.lima_water.config import CENSO_XLSX, OUTPUTS
from src.lima_water.census import parse_censo_agua
from src.lima_water.districts import load_lima_distritos, join_distritos_censo, to_utm
from src.lima_water.osm import extract_infra_agua, extract_lugares_poblados
from src.lima_water.postgis import (
    load_distritos, load_infra, load_lugares, create_indexes, run_spatial_queries,
    table_exists,
)
from src.lima_water.ivh import compute_ivh, export_ivh_table
from src.lima_water.spatial import compute_moran, add_lisa_clusters, export_lisa_geojson

warnings.filterwarnings("ignore", category=UserWarning)

print("=== Block 1: Ingesta y validacion ===")
censo = parse_censo_agua(CENSO_XLSX)
assert len(censo) == 43
assert censo["total"].sum() > 2_000_000
distritos = load_lima_distritos()
lima = join_distritos_censo(distritos, censo)
lima_utm = to_utm(lima)
print(f"  {len(lima)} districts joined, CRS: {lima_utm.crs}")

print("\n=== Block 2: OSM (local PBF) ===")
infra = extract_infra_agua()
lugares = extract_lugares_poblados()
print(f"  Infra: {len(infra)} features")
if len(infra) > 0:
    print(f"  Categories: {infra['category'].value_counts().to_dict()}")
print(f"  Places: {len(lugares)} features")

print("\n=== PostGIS ===")
load_distritos(lima_utm)
load_infra(infra)
load_lugares(lugares)
print(f"  distritos_lima: {table_exists('distritos_lima')}")
print(f"  infra_agua_osm: {table_exists('infra_agua_osm')}")
print(f"  lugares_poblados: {table_exists('lugares_poblados')}")
create_indexes()
print("  GIST indexes created")

distancia_df = run_spatial_queries()
print(f"  Distance query: {len(distancia_df)} districts")
print(f"  Mean distance: {distancia_df['dist_promedio_metros'].mean():.0f}m")

print("\n=== Block 3: IVH ===")
ivh_df = compute_ivh(lima_utm, distancia_df)
print("  Top 5:")
for _, row in ivh_df.head(5).iterrows():
    print(f"    {row['distrito']}: IVH={row['IVH_equal']:.3f}, cov={row['cobertura_formal_pct']:.1f}%, dist={row['dist_promedio_metros']:.0f}m")
export_ivh_table(ivh_df, OUTPUTS / "ivh_table.csv")
print(f"  Exported to {OUTPUTS / 'ivh_table.csv'}")

print("\n=== Block 4: Moran's I + LISA ===")
lima_wgs = lima.to_crs(epsg=4326)
lima_wgs = lima_wgs.merge(ivh_df[["distrito", "IVH_equal"]],
                          left_on="NAME_3_norm", right_on="distrito", how="left")
moran = compute_moran(lima_wgs, "IVH_equal")
print(f"  Moran's I = {moran['moran_I']} (p = {moran['p_value']})")
lima_lisa = add_lisa_clusters(lima_wgs, "IVH_equal")
print(f"  LISA clusters: {lima_lisa['lisa_label'].value_counts().to_dict()}")
export_lisa_geojson(lima_lisa, OUTPUTS / "lima_ivh_lisa.geojson")

print("\n=== Block 5: Folium map ===")
import folium
m = folium.Map(location=[-12.05, -77.0], zoom_start=11, tiles="CartoDB positron")
folium.Choropleth(
    geo_data=lima_wgs.__geo_interface__,
    data=ivh_df,
    columns=["distrito", "IVH_equal"],
    key_on="feature.properties.NAME_3_norm",
    fill_color="YlOrRd",
    fill_opacity=0.7,
    line_opacity=0.3,
    legend_name="IVH",
    highlight=True,
).add_to(m)
m.save(str(OUTPUTS / "map_interactive.html"))
print(f"  Map saved to {OUTPUTS / 'map_interactive.html'}")

print("\n=== ALL TESTS PASSED ===")
