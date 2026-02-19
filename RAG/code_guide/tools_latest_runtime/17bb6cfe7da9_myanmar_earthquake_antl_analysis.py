import ee
import pandas as pd
import json
from storage_manager import storage_manager
import geopandas as gpd

# Initialize GEE
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Epicenter coordinates from USGS/British Geological Survey
epicenter_lon = 95.922
epicenter_lat = 22.013

# Temporal windows based on first-night rule:
# Earthquake: 2025-03-28 06:20 UTC (12:50 local time, Myanmar UTC+6:30)
# Since event happened AFTER ~01:30 local nightly overpass on day D (March 28),
# first post-event night = local day D+1 = 2025-03-29
# Pre-event baseline: 2025-03-14 to 2025-03-21 (8 days before event)
# First night: 2025-03-29 (single image, day after event)
# Recovery phase: 2025-04-04 to 2025-04-11 (7-14 days after event)

baseline_start = "2025-03-14"
baseline_end = "2025-03-22"  # filterDate is exclusive on end
first_night_date = "2025-03-29"
recovery_start = "2025-04-04"
recovery_end = "2025-04-12"  # filterDate is exclusive on end

# Load epicenter buffers from GeoJSON
buffers_path = storage_manager.resolve_output_path('epicenter_buffers.geojson')
buffers_gdf = gpd.read_file(buffers_path)
print(f"Loaded {len(buffers_gdf)} buffers")

# Convert to GeoJSON and upload as GEE FeatureCollection
geojson_str = buffers_gdf.to_json()
fc = ee.FeatureCollection(json.loads(geojson_str))

# VNP46A2 dataset
dataset_id = "NASA/VIIRS/002/VNP46A2"
band = "Gap_Filled_DNB_BRDF_Corrected_NTL"

# Function to compute ANTL (mean) for a collection over regions
def compute_period_antl(collection, period_name):
    """Compute mean ANTL for each buffer zone for a given period."""
    # Compute mean composite for the period
    mean_img = collection.mean()
    
    # Reduce regions to get mean ANTL per buffer
    stats_fc = mean_img.reduceRegions(
        collection=fc,
        reducer=ee.Reducer.mean().combine(
            ee.Reducer.stdDev(), sharedInputs=True
        ).combine(
            ee.Reducer.count(), sharedInputs=True
        ),
        scale=500,
        maxPixelsPerRegion=1e13,
        tileScale=4
    )
    
    # Add period name to each feature
    def add_period(f):
        return f.set('period', period_name)
    
    return stats_fc.map(add_period)

# Create collections for each period
print("Creating image collections...")
baseline_collection = (
    ee.ImageCollection(dataset_id)
    .filterDate(baseline_start, baseline_end)
    .filterBounds(fc)
    .select(band)
)

first_night_collection = (
    ee.ImageCollection(dataset_id)
    .filterDate(first_night_date, "2025-03-30")
    .filterBounds(fc)
    .select(band)
)

recovery_collection = (
    ee.ImageCollection(dataset_id)
    .filterDate(recovery_start, recovery_end)
    .filterBounds(fc)
    .select(band)
)

# Verify collection sizes
print(f"Baseline collection: {baseline_collection.size().getInfo()} images")
print(f"First night collection: {first_night_collection.size().getInfo()} images")
print(f"Recovery collection: {recovery_collection.size().getInfo()} images")

# Compute ANTL for each period
print("\nComputing baseline ANTL...")
baseline_stats = compute_period_antl(baseline_collection, "baseline")

print("Computing first night ANTL...")
first_night_stats = compute_period_antl(first_night_collection, "first_night")

print("Computing recovery ANTL...")
recovery_stats = compute_period_antl(recovery_collection, "recovery")

# Combine all results
all_stats = baseline_stats.merge(first_night_stats).merge(recovery_stats)

# Download results
print("\nDownloading results...")
features = all_stats.getInfo()['features']

# Parse results into DataFrame
rows = []
for ft in features:
    props = ft['properties']
    rows.append({
        'buffer_id': props.get('buffer_id', 'unknown'),
        'buffer_km': props.get('buffer_km', 0),
        'period': props.get('period', 'unknown'),
        'mean_ANTL': props.get('mean', None),
        'std_ANTL': props.get('stdDev', None),
        'pixel_count': props.get('count', None)
    })

df = pd.DataFrame(rows)
df = df.sort_values(['buffer_km', 'period'])

# Save to CSV
output_csv = storage_manager.resolve_output_path('myanmar_earthquake_2025_antl_zonal_stats.csv')
df.to_csv(output_csv, index=False)
print(f"\nZonal statistics saved to: {output_csv}")
print(f"Total records: {len(df)}")
print("\nResults:")
print(df.to_string())