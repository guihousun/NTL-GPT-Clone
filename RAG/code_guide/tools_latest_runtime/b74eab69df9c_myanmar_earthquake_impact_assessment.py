"""
2025 Myanmar Earthquake Impact Assessment using Daily VNP46A2 NTL Data
========================================================================
Event Details (USGS Official):
- Date/Time: March 28, 2025, 06:20 UTC (12:50:52 MMT local)
- Epicenter: 22.013°N, 95.922°E (Sagaing Region, ~16 km NW of Sagaing city)
- Magnitude: 7.7 Mw
- Depth: 10 km

First-Night Rule (VNP46A2):
- VNP46A2 local overpass time: ~01:30 local time
- Earthquake occurred at 12:50:52 MMT (AFTER 01:30 local time on March 28)
- Therefore, first post-event night is March 29, 2025 (day D+1), NOT March 28

Analysis Periods:
- Pre-event baseline: March 14-21, 2025 (event_date-14d to event_date-7d)
- First post-event night: March 29, 2025 (single date)
- Post-event recovery: April 4-11, 2025 (event_date+7d to event_date+14d)

Methodology: Hu et al. (2024) - Remote Sensing of Environment
"""

import ee
import pandas as pd
from storage_manager import storage_manager

# Initialize GEE with explicit project
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Epicenter coordinates from USGS
EPICENTER_LON = 95.922
EPICENTER_LAT = 22.013
epicenter = ee.Geometry.Point([EPICENTER_LON, EPICENTER_LAT])

# Multi-scale buffer distances (km)
BUFFER_DISTANCES_KM = [25, 50, 100]

# Create buffer geometries
buffers = {
    dist_km: epicenter.buffer(dist_km * 1000)  # Convert km to meters
    for dist_km in BUFFER_DISTANCES_KM
}

# VNP46A2 dataset configuration
DATASET_ID = "NASA/VIIRS/002/VNP46A2"
BAND_NAME = "Gap_Filled_DNB_BRDF_Corrected_NTL"
SCALE = 500  # meters
MAX_PIXELS = 1e13

# Analysis periods
# Event date: March 28, 2025
# Pre-event baseline: March 14-21 (event_date-14d to event_date-7d)
PRE_EVENT_START = "2025-03-14"
PRE_EVENT_END = "2025-03-22"  # filterDate is exclusive on end

# First post-event night: March 29, 2025 (single date)
FIRST_NIGHT_DATE = "2025-03-29"

# Post-event recovery: April 4-11 (event_date+7d to event_date+14d)
POST_EVENT_START = "2025-04-04"
POST_EVENT_END = "2025-04-12"  # filterDate is exclusive on end

def get_collection_for_date_range(start_date, end_date):
    """Get VNP46A2 collection for a date range and return mean composite."""
    collection = (
        ee.ImageCollection(DATASET_ID)
        .filterDate(start_date, end_date)
        .filterBounds(epicenter.buffer(150000))  # Filter to larger area for efficiency
        .select(BAND_NAME)
    )
    return collection.mean()  # Return mean composite image

def get_single_date_image(date_str):
    """Get VNP46A2 image for a single date."""
    # Filter to single day (date_str to date_str + 1 day)
    next_day = pd.Timestamp(date_str) + pd.Timedelta(days=1)
    next_day_str = next_day.strftime("%Y-%m-%d")
    
    collection = (
        ee.ImageCollection(DATASET_ID)
        .filterDate(date_str, next_day_str)
        .filterBounds(epicenter.buffer(150000))
        .select(BAND_NAME)
    )
    return collection.first()

def compute_antl(image, geometry):
    """Compute ANTL for a given image and geometry."""
    result_dict = image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometry,
        scale=SCALE,
        maxPixels=MAX_PIXELS,
        bestEffort=True,
    ).getInfo()
    
    if result_dict and BAND_NAME in result_dict:
        return result_dict[BAND_NAME]
    return None

# Build results list
results = []

print("Computing ANTL for multi-buffer earthquake impact assessment...")
print(f"Epicenter: {EPICENTER_LAT}°N, {EPICENTER_LON}°E")
print(f"Pre-event baseline: {PRE_EVENT_START} to {PRE_EVENT_END}")
print(f"First post-event night: {FIRST_NIGHT_DATE}")
print(f"Post-event recovery: {POST_EVENT_START} to {POST_EVENT_END}")
print("-" * 60)

for dist_km in BUFFER_DISTANCES_KM:
    buffer_geom = buffers[dist_km]
    print(f"\nProcessing {dist_km} km buffer...")
    
    # Pre-event baseline ANTL (mean composite)
    pre_event_composite = get_collection_for_date_range(PRE_EVENT_START, PRE_EVENT_END)
    antl_baseline = compute_antl(pre_event_composite, buffer_geom)
    
    # First night ANTL (single image)
    first_night_image = get_single_date_image(FIRST_NIGHT_DATE)
    antl_first_night = compute_antl(first_night_image, buffer_geom)
    
    # Post-event recovery ANTL (mean composite)
    post_event_composite = get_collection_for_date_range(POST_EVENT_START, POST_EVENT_END)
    antl_recovery = compute_antl(post_event_composite, buffer_geom)
    
    # Store results
    results.append({
        "buffer_km": dist_km,
        "period": "pre_event_baseline",
        "ANTL": antl_baseline,
    })
    results.append({
        "buffer_km": dist_km,
        "period": "first_post_event_night",
        "ANTL": antl_first_night,
    })
    results.append({
        "buffer_km": dist_km,
        "period": "post_event_recovery",
        "ANTL": antl_recovery,
    })
    
    print(f"  Baseline: {antl_baseline:.4f}" if antl_baseline else "  Baseline: N/A")
    print(f"  First Night: {antl_first_night:.4f}" if antl_first_night else "  First Night: N/A")
    print(f"  Recovery: {antl_recovery:.4f}" if antl_recovery else "  Recovery: N/A")

# Create DataFrame
df = pd.DataFrame(results)

# Pivot to compute damage metrics
pivot_df = df.pivot(index="buffer_km", columns="period", values="ANTL").reset_index()

# Calculate damage assessment metrics
damage_metrics = []
for _, row in pivot_df.iterrows():
    buffer_km = row["buffer_km"]
    antl_baseline = row["pre_event_baseline"]
    antl_first_night = row["first_post_event_night"]
    antl_recovery = row["post_event_recovery"]
    
    # Blackout percentage: drop from baseline to first night
    if antl_baseline is not None and antl_baseline > 0:
        blackout_pct = ((antl_first_night - antl_baseline) / antl_baseline) * 100
    else:
        blackout_pct = None
    
    # Recovery rate: how much recovered from first night toward baseline
    if (antl_baseline is not None and antl_first_night is not None and 
        antl_recovery is not None and (antl_baseline - antl_first_night) != 0):
        recovery_pct = ((antl_recovery - antl_first_night) / (antl_baseline - antl_first_night)) * 100
    else:
        recovery_pct = None
    
    damage_metrics.append({
        "buffer_km": buffer_km,
        "ANTL_baseline": antl_baseline,
        "ANTL_first_night": antl_first_night,
        "ANTL_recovery": antl_recovery,
        "blackout_pct": blackout_pct,
        "recovery_pct": recovery_pct,
    })

damage_df = pd.DataFrame(damage_metrics)

# Save results
output_csv = storage_manager.resolve_output_path("myanmar_earthquake_antl_analysis.csv")
df.to_csv(output_csv, index=False)
print(f"\nSaved ANTL analysis to: {output_csv}")

# Save damage metrics
damage_csv = storage_manager.resolve_output_path("myanmar_earthquake_damage_metrics.csv")
damage_df.to_csv(damage_csv, index=False)
print(f"Saved damage metrics to: {damage_csv}")

# Print summary
print("\n" + "=" * 60)
print("EARTHQUAKE IMPACT ASSESSMENT SUMMARY")
print("=" * 60)
print(f"\nEvent: 2025 Myanmar Earthquake (Mw 7.7)")
print(f"Date: March 28, 2025, 06:20 UTC (12:50:52 MMT)")
print(f"Epicenter: {EPICENTER_LAT}°N, {EPICENTER_LON}°E")
print(f"\nDamage Assessment by Buffer Zone:")
print("-" * 60)
for _, row in damage_df.iterrows():
    print(f"\n{row['buffer_km']} km buffer:")
    print(f"  Baseline ANTL: {row['ANTL_baseline']:.4f}" if row['ANTL_baseline'] else "  Baseline ANTL: N/A")
    print(f"  First Night ANTL: {row['ANTL_first_night']:.4f}" if row['ANTL_first_night'] else "  First Night ANTL: N/A")
    print(f"  Recovery ANTL: {row['ANTL_recovery']:.4f}" if row['ANTL_recovery'] else "  Recovery ANTL: N/A")
    if row['blackout_pct'] is not None:
        print(f"  Blackout %: {row['blackout_pct']:.2f}%")
    else:
        print("  Blackout %: N/A")
    if row['recovery_pct'] is not None:
        print(f"  Recovery %: {row['recovery_pct']:.2f}%")
    else:
        print("  Recovery %: N/A")

print("\n" + "=" * 60)
print("Analysis complete. See output CSV files for detailed results.")
print("=" * 60)
