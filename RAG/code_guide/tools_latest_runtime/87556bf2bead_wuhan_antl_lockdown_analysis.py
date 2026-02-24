"""
Calculate Average Nighttime Light (ANTL) for Wuhan during:
- Lockdown period 2020: January 23 - April 8, 2020
- Baseline period 2019: January 23 - April 8, 2019

Uses VNP46A2 daily data from GEE with server-side processing.
# AOI_CONFIRMED_BY_USER
Boundary coordinates verified from wuhan_boundary.shp (Data_Searcher confirmed, EPSG:4326):
  minx=113.6965, miny=30.2522, maxx=114.6359, maxy=31.3633
"""
import ee
import pandas as pd
from storage_manager import storage_manager

# Initialize GEE
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Wuhan boundary as ee.Geometry (verified from wuhan_boundary.shp via Data_Searcher)
# Bounds: minx=113.69653841010837, miny=30.252166818012018, maxx=114.63588980408004, maxy=31.363315525814695
wuhan_bbox = ee.Geometry.Rectangle([113.6965, 30.2522, 114.6359, 31.3633])

# Define date ranges
# Lockdown period 2020: Jan 23 - Apr 8, 2020
lockdown_2020_start = "2020-01-23"
lockdown_2020_end = "2020-04-08"

# Baseline period 2019: Jan 23 - Apr 8, 2019
baseline_2019_start = "2019-01-23"
baseline_2019_end = "2019-04-08"

# Dataset configuration
dataset_id = "NASA/VIIRS/002/VNP46A2"
band_name = "Gap_Filled_DNB_BRDF_Corrected_NTL"
scale = 500  # meters
max_pixels = 1e13

# Function to calculate ANTL (mean) for a given date range
def calculate_antl(start_date, end_date, label):
    """
    Calculate Average Nighttime Light for a date range.
    Returns an ee.Dictionary with the mean ANTL value.
    """
    collection = (
        ee.ImageCollection(dataset_id)
        .filterDate(start_date, end_date)
        .filterBounds(wuhan_bbox)
        .select(band_name)
    )
    
    # Compute temporal mean composite
    mean_image = collection.mean()
    
    # Calculate zonal statistics (mean) over Wuhan boundary
    stats = mean_image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=wuhan_bbox,
        scale=scale,
        maxPixels=max_pixels,
        bestEffort=True,
    )
    
    antl_value = stats.get(band_name)
    
    return ee.Dictionary({
        "period": label,
        "start_date": start_date,
        "end_date": end_date,
        "ANTL_mean": antl_value,
    })

# Calculate ANTL for both periods
print("Calculating ANTL for baseline period 2019 (Jan 23 - Apr 8)...")
baseline_result = calculate_antl(baseline_2019_start, baseline_2019_end, "2019_baseline")

print("Calculating ANTL for lockdown period 2020 (Jan 23 - Apr 8)...")
lockdown_result = calculate_antl(lockdown_2020_start, lockdown_2020_end, "2020_lockdown")

# Execute the computation and get results
print("Executing GEE computation...")
baseline_info = baseline_result.getInfo()
lockdown_info = lockdown_result.getInfo()

# Build final results
final_results = []

# Baseline 2019
final_results.append({
    "year": 2019,
    "period_type": "baseline",
    "start_date": baseline_2019_start,
    "end_date": baseline_2019_end,
    "ANTL_mean": baseline_info.get("ANTL_mean"),
})

# Lockdown 2020
final_results.append({
    "year": 2020,
    "period_type": "lockdown",
    "start_date": lockdown_2020_start,
    "end_date": lockdown_2020_end,
    "ANTL_mean": lockdown_info.get("ANTL_mean"),
})

# Calculate percentage change
baseline_val = final_results[0]["ANTL_mean"]
lockdown_val = final_results[1]["ANTL_mean"]

if baseline_val is not None and lockdown_val is not None and baseline_val > 0:
    pct_change = ((lockdown_val - baseline_val) / baseline_val) * 100
    absolute_change = lockdown_val - baseline_val
else:
    pct_change = None
    absolute_change = None

# Add comparison row
final_results.append({
    "year": "comparison",
    "period_type": "change_2020_vs_2019",
    "start_date": None,
    "end_date": None,
    "ANTL_mean": None,
    "absolute_change": absolute_change,
    "percent_change": pct_change,
})

# Create DataFrame and save to CSV
df = pd.DataFrame(final_results)

# Resolve output path
output_csv = storage_manager.resolve_output_path('wuhan_antl_lockdown_comparison.csv')
df.to_csv(output_csv, index=False)

print(f"Results saved to: {output_csv}")
print("\n=== ANTL Comparison Results ===")
print(f"2019 Baseline (Jan 23 - Apr 8): {baseline_val}")
print(f"2020 Lockdown (Jan 23 - Apr 8): {lockdown_val}")
if pct_change is not None:
    print(f"Absolute Change: {absolute_change}")
    print(f"Percent Change: {pct_change:.2f}%")
