import ee
import geopandas as gpd
import pandas as pd
from storage_manager import storage_manager

PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Load boundary from shapefile and convert to EE geometry
boundary_path = storage_manager.resolve_input_path('shanghai_boundary.shp')
gdf = gpd.read_file(boundary_path)

# Use union_all() to dissolve all features into one geometry for Shanghai
shanghai_geom = gdf.union_all()
region = ee.Geometry(shanghai_geom.__geo_interface__)

# Get 2020 NPP-VIIRS NTL image
ntl_image = (
    ee.ImageCollection("projects/sat-io/open-datasets/npp-viirs-ntl")
    .filterDate("2020-01-01", "2020-12-31")
    .select("b1")
    .first()
)

# Create binary mask: pixels > 50
threshold_mask = ntl_image.gt(50)

# Calculate total pixel count and count above threshold
total_stats = ntl_image.reduceRegion(
    reducer=ee.Reducer.count(),
    geometry=region,
    scale=500,
    maxPixels=1e13,
    bestEffort=True,
    tileScale=4
)

above_threshold_stats = threshold_mask.reduceRegion(
    reducer=ee.Reducer.sum(),
    geometry=region,
    scale=500,
    maxPixels=1e13,
    bestEffort=True,
    tileScale=4
)

# Get results
total_pixels = total_stats.get('b1').getInfo()
pixels_above_50 = above_threshold_stats.get('b1').getInfo()
proportion = pixels_above_50 / total_pixels if total_pixels else 0

# Create output DataFrame
results = {
    'year': 2020,
    'region': 'Shanghai',
    'total_pixels': total_pixels,
    'pixels_above_50': pixels_above_50,
    'proportion_above_50': proportion
}

df = pd.DataFrame([results])

# Save to CSV
out_csv = storage_manager.resolve_output_path('shanghai_ntl_proportion_2020.csv')
df.to_csv(out_csv, index=False)
print(f"Results saved to: {out_csv}")
print(f"Total pixels: {total_pixels}")
print(f"Pixels above 50: {pixels_above_50}")
print(f"Proportion above 50: {proportion:.4f}")
