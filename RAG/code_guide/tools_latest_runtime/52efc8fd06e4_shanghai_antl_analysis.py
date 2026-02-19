import ee
import pandas as pd
import geopandas as gpd
from storage_manager import storage_manager

# Initialize GEE
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Load Shanghai boundary from Data_Searcher-confirmed file
boundary_path = storage_manager.resolve_input_path('shanghai_boundary.shp')
gdf = gpd.read_file(boundary_path)

# Dissolve all districts into single Shanghai geometry
shanghai_geom = gdf.dissolve().geometry.iloc[0]
region = ee.Geometry(shanghai_geom.__geo_interface__)

# Load NPP-VIIRS annual collection for 2015-2022
collection = (
    ee.ImageCollection("projects/sat-io/open-datasets/npp-viirs-ntl")
    .filterDate("2015-01-01", "2022-12-31")
    .filterBounds(region)
    .select("b1")
)

# Function to compute mean NTL (ANTL) per image
def per_image_stat(img):
    year = img.date().format('YYYY')
    mean_val = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=region,
        scale=500,
        maxPixels=1e13,
        bestEffort=True,
    ).get("b1")
    return ee.Feature(None, {
        "year": year,
        "ANTL": mean_val,
    })

# Map over collection and get results
stats_fc = ee.FeatureCollection(collection.map(per_image_stat))
results = stats_fc.getInfo()["features"]

# Build DataFrame
rows = []
for f in results:
    props = f["properties"]
    rows.append({
        "year": int(props["year"]),
        "ANTL": props["ANTL"],
    })

df = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)

# Save to CSV
out_csv = storage_manager.resolve_output_path("shanghai_antl_2015_2022.csv")
df.to_csv(out_csv, index=False)

print(f"Output saved to: {out_csv}")
print(df.to_string(index=False))
