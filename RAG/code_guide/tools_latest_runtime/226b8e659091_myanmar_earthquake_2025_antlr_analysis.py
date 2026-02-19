"""
Myanmar Earthquake 2025 - Nighttime Light Damage Assessment
Using daily NPP-VIIRS VNP46A2 imagery to compute ANTL time series
for pre-event, event night, and post-event periods.

Earthquake: March 28, 2025, M7.7, Epicenter: 22.013°N, 95.922°E
"""
import ee
import geopandas as gpd
import pandas as pd
import json
from storage_manager import storage_manager

# Initialize GEE
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)
print("GEE initialized successfully")

# Load Myanmar boundary from confirmed shapefile
boundary_path = storage_manager.resolve_input_path('myanmar_boundary.shp')
gdf = gpd.read_file(boundary_path)
print(f"Boundary loaded: CRS={gdf.crs}, bounds={gdf.total_bounds}")

# Convert to GeoJSON for GEE
boundary_geojson = json.loads(gdf.to_json())
region = ee.Geometry(boundary_geojson['features'][0]['geometry'])
print(f"GEE region created: {region.type().getInfo()}")

# Define analysis periods
PRE_EVENT_START = "2025-03-01"
PRE_EVENT_END = "2025-03-27"   # Before earthquake
EVENT_DATE = "2025-03-28"      # Earthquake day
POST_EVENT_START = "2025-03-29"
POST_EVENT_END = "2025-04-30"  # Recovery period

# Create VNP46A2 collection
collection = (
    ee.ImageCollection("NASA/VIIRS/002/VNP46A2")
    .filterDate(PRE_EVENT_START, POST_EVENT_END)
    .filterBounds(region)
    .select("Gap_Filled_DNB_BRDF_Corrected_NTL")
)

print(f"Collection filtered, computing daily ANTL...")

# Function to compute mean NTL per image
def per_image_stat(img):
    value = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=region,
        scale=500,
        maxPixels=1e13,
        bestEffort=True,
        tileScale=4,
    ).get("Gap_Filled_DNB_BRDF_Corrected_NTL")
    return ee.Feature(None, {
        "date": img.date().format("YYYY-MM-dd"),
        "antlr": value,
    })

# Map over collection and get results
stats_fc = ee.FeatureCollection(collection.map(per_image_stat))
rows = [f["properties"] for f in stats_fc.getInfo()["features"]]
df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

print(f"Computed ANTL for {len(df)} days")

# Classify periods
def classify_period(date_str):
    if date_str < EVENT_DATE:
        return "pre_event"
    elif date_str == EVENT_DATE:
        return "event_night"
    else:
        return "post_event"

df['period'] = df['date'].apply(classify_period)

# Compute period statistics
period_stats = df.groupby('period')['antlr'].agg(['mean', 'std', 'min', 'max', 'count']).round(6)
period_stats.columns = ['mean_antlr', 'std_antlr', 'min_antlr', 'max_antlr', 'days']
period_stats = period_stats.reset_index()

print("\n=== Period Statistics ===")
print(period_stats.to_string(index=False))

# Compute damage metrics
pre_event_mean = df[df['period'] == 'pre_event']['antlr'].mean()
event_night_value = df[df['period'] == 'event_night']['antlr'].values[0] if len(df[df['period'] == 'event_night']) > 0 else None
post_event_mean = df[df['period'] == 'post_event']['antlr'].mean()

print(f"\n=== Damage Assessment Metrics ===")
print(f"Pre-event mean ANTL (Mar 1-27): {pre_event_mean:.6f}")
print(f"Event night ANTL (Mar 28): {event_night_value:.6f}" if event_night_value else "Event night: No data")
print(f"Post-event mean ANTL (Mar 29-Apr 30): {post_event_mean:.6f}")

if event_night_value and pre_event_mean > 0:
    immediate_drop_pct = ((pre_event_mean - event_night_value) / pre_event_mean) * 100
    print(f"Immediate light drop on event night: {immediate_drop_pct:.2f}%")

if pre_event_mean > 0 and post_event_mean:
    sustained_change_pct = ((post_event_mean - pre_event_mean) / pre_event_mean) * 100
    print(f"Sustained ANTL change (post vs pre): {sustained_change_pct:.2f}%")

# Save full time series CSV
out_csv = storage_manager.resolve_output_path('myanmar_earthquake_2025_antlr_daily.csv')
df.to_csv(out_csv, index=False)
print(f"\nDaily ANTL time series saved: {out_csv}")

# Save period summary CSV
out_summary_csv = storage_manager.resolve_output_path('myanmar_earthquake_2025_antlr_summary.csv')
period_stats.to_csv(out_summary_csv, index=False)
print(f"Period summary saved: {out_summary_csv}")

# Create damage metrics DataFrame
damage_metrics = pd.DataFrame([{
    'metric': 'pre_event_mean_antlr',
    'value': pre_event_mean,
    'period': '2025-03-01 to 2025-03-27'
}, {
    'metric': 'event_night_antlr',
    'value': event_night_value,
    'period': '2025-03-28'
}, {
    'metric': 'post_event_mean_antlr',
    'value': post_event_mean,
    'period': '2025-03-29 to 2025-04-30'
}, {
    'metric': 'immediate_drop_percent',
    'value': ((pre_event_mean - event_night_value) / pre_event_mean) * 100 if event_night_value and pre_event_mean > 0 else None,
    'period': 'event_night vs pre_event'
}, {
    'metric': 'sustained_change_percent',
    'value': ((post_event_mean - pre_event_mean) / pre_event_mean) * 100 if pre_event_mean > 0 and post_event_mean else None,
    'period': 'post_event vs pre_event'
}])

out_metrics_csv = storage_manager.resolve_output_path('myanmar_earthquake_2025_damage_metrics.csv')
damage_metrics.to_csv(out_metrics_csv, index=False)
print(f"Damage metrics saved: {out_metrics_csv}")

print("\n=== Analysis Complete ===")