import ee
import pandas as pd
import geopandas as gpd
from storage_manager import storage_manager

PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Load Shanghai boundary from confirmed administrative data
boundary_path = storage_manager.resolve_input_path('shanghai_boundary.shp')
gdf = gpd.read_file(boundary_path)
region = ee.Geometry(gdf.to_crs('EPSG:4326').dissolve().geometry.iloc[0].__geo_interface__)

# Filter VNP46A2 collection for January 2022
collection = (
    ee.ImageCollection("NASA/VIIRS/002/VNP46A2")
    .filterDate("2022-01-01", "2022-01-31")
    .filterBounds(region)
    .select("Gap_Filled_DNB_BRDF_Corrected_NTL")
)

# Calculate mean ANTL per day using server-side reduceRegion
def per_image_stat(img):
    value = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=region,
        scale=500,
        maxPixels=1e13,
        bestEffort=True,
    ).get("Gap_Filled_DNB_BRDF_Corrected_NTL")
    return ee.Feature(None, {
        "date": img.date().format("YYYY-MM-dd"),
        "ANTL": value,
    })

# Map over collection and export results
stats_fc = ee.FeatureCollection(collection.map(per_image_stat))
rows = [f["properties"] for f in stats_fc.getInfo()["features"]]
df = pd.DataFrame(rows).sort_values("date")

# Save to CSV
out_csv = storage_manager.resolve_output_path("shanghai_vnp46a2_daily_antl_2022_01.csv")
df.to_csv(out_csv, index=False)
print(f"CSV saved to: {out_csv}")
print(f"Total daily records: {len(df)}")
print(df)