"""
Myanmar Earthquake 2025 Impact Assessment using VNP46A2 Daily NTL Imagery
=========================================================================

This script computes Average Nighttime Light (ANTL) for:
- Pre-event baseline period (March 14-21, 2025)
- First night after earthquake (March 29, 2025)
- Post-event recovery period (April 4-11, 2025)

Earthquake Details (USGS):
- Date: March 28, 2025 at 12:50:52 MMT (06:20:52 UTC)
- Magnitude: 7.7 Mw
- Epicenter: 22.01°N, 95.92°E (16 km NNW of Sagaing, Myanmar)
- Depth: 10 km

First Night Selection Rule:
- VNP46A2 nightly overpass is ~01:30 local time (MMT = UTC+6:30)
- Earthquake occurred at 12:50 MMT on March 28, which is AFTER the 01:30 MMT overpass
- Therefore, first post-event night image = VNP46A2 product dated 2025-03-29
  (capturing overpass at 01:30 MMT on March 29, which is 19:00 UTC on March 28)

Author: NTL Code Assistant
Date: 2026-02-18
"""

import ee
import pandas as pd
from storage_manager import storage_manager

# Initialize GEE
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# =============================================================================
# Configuration
# =============================================================================

# Epicenter coordinates from USGS
EPICENTER_LON = 95.92
EPICENTER_LAT = 22.01

# Create epicenter point and buffer zones
epicenter_point = ee.Geometry.Point([EPICENTER_LON, EPICENTER_LAT])
BUFFERS = {
    "25km": epicenter_point.buffer(25000),
    "50km": epicenter_point.buffer(50000),
    "100km": epicenter_point.buffer(100000),
}

# Temporal windows (GEE filterDate is exclusive on end date)
# Pre-event: event-14d to event-7d (March 14-21, 2025)
PRE_EVENT_START = "2025-03-14"
PRE_EVENT_END = "2025-03-22"

# First post-event night: March 29, 2025 (single day)
FIRST_NIGHT_DATE = "2025-03-29"

# Recovery: event+7d to event+14d (April 4-11, 2025)
RECOVERY_START = "2025-04-04"
RECOVERY_END = "2025-04-12"

# VNP46A2 dataset configuration
DATASET_ID = "NASA/VIIRS/002/VNP46A2"
BAND_NAME = "Gap_Filled_DNB_BRDF_Corrected_NTL"
SCALE = 500  # meters
MAX_PIXELS = 1e13

# =============================================================================
# Helper Functions
# =============================================================================

def compute_antl_for_period(collection, geometry, period_name):
    """
    Compute mean ANTL for a given period and geometry.
    Returns a dictionary with period statistics.
    """
    # Compute mean composite for the period
    mean_img = collection.mean()
    
    # Reduce region to get mean ANTL
    stats = mean_img.reduceRegion(
        reducer=ee.Reducer.mean().combine(
            ee.Reducer.stdDev(), sharedInputs=True
        ).combine(
            ee.Reducer.count(), sharedInputs=True
        ),
        geometry=geometry,
        scale=SCALE,
        maxPixels=MAX_PIXELS,
        bestEffort=True,
    )
    
    result = stats.getInfo()
    return {
        "mean": result.get(f"{BAND_NAME}_mean"),
        "std": result.get(f"{BAND_NAME}_stdDev"),
        "count": result.get(f"{BAND_NAME}_count"),
    }


def compute_daily_antl(collection, geometry):
    """
    Compute ANTL for each image in the collection.
    Returns a list of dictionaries with date and ANTL value.
    """
    def per_image_stat(img):
        stats = img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=SCALE,
            maxPixels=MAX_PIXELS,
            bestEffort=True,
        )
        return ee.Feature(None, {
            "date": img.date().format("YYYY-MM-dd"),
            "antl": stats.get(BAND_NAME),
        })
    
    fc = ee.FeatureCollection(collection.map(per_image_stat))
    records = [f["properties"] for f in fc.getInfo()["features"]]
    return sorted(records, key=lambda x: x["date"])


# =============================================================================
# Main Analysis
# =============================================================================

print("=" * 70)
print("Myanmar Earthquake 2025 - NTL Impact Assessment")
print("=" * 70)
print(f"Epicenter: {EPICENTER_LAT}°N, {EPICENTER_LON}°E")
print(f"Event Date: March 28, 2025 at 12:50:52 MMT (06:20:52 UTC)")
print(f"Magnitude: 7.7 Mw (USGS)")
print(f"First Post-Event Night: {FIRST_NIGHT_DATE}")
print("=" * 70)

# Load VNP46A2 collection for full analysis period
full_collection = (
    ee.ImageCollection(DATASET_ID)
    .filterDate(PRE_EVENT_START, RECOVERY_END)
    .filterBounds(BUFFERS["100km"])
    .select(BAND_NAME)
)

print(f"\nLoaded {full_collection.size().getInfo()} VNP46A2 images")
print(f"Analysis period: {PRE_EVENT_START} to {RECOVERY_END}")

# Initialize results storage
results = []

# Process each buffer zone
for buffer_name, buffer_geom in BUFFERS.items():
    print(f"\n{'='*50}")
    print(f"Processing {buffer_name} buffer zone...")
    print(f"{'='*50}")
    
    # Filter collection to buffer bounds
    buffer_collection = full_collection.filterBounds(buffer_geom)
    
    # 1. Pre-event baseline period
    pre_event_collection = buffer_collection.filterDate(PRE_EVENT_START, PRE_EVENT_END)
    pre_event_stats = compute_antl_for_period(pre_event_collection, buffer_geom, "pre_event")
    
    # Also get daily values for pre-event period
    pre_event_daily = compute_daily_antl(pre_event_collection, buffer_geom)
    
    # 2. First post-event night (single day)
    first_night_collection = buffer_collection.filterDate(FIRST_NIGHT_DATE, "2025-03-30")
    first_night_stats = compute_antl_for_period(first_night_collection, buffer_geom, "first_night")
    first_night_daily = compute_daily_antl(first_night_collection, buffer_geom)
    
    # 3. Recovery period
    recovery_collection = buffer_collection.filterDate(RECOVERY_START, RECOVERY_END)
    recovery_stats = compute_antl_for_period(recovery_collection, buffer_geom, "recovery")
    recovery_daily = compute_daily_antl(recovery_collection, buffer_geom)
    
    # Compute impact metrics
    baseline_mean = pre_event_stats["mean"]
    event_night_mean = first_night_stats["mean"]
    recovery_mean = recovery_stats["mean"]
    
    if baseline_mean and event_night_mean:
        blackout_pct = ((baseline_mean - event_night_mean) / baseline_mean) * 100 if baseline_mean > 0 else 0
    else:
        blackout_pct = None
    
    if baseline_mean and event_night_mean and recovery_mean:
        denominator = baseline_mean - event_night_mean
        if denominator > 0:
            recovery_rate = ((recovery_mean - event_night_mean) / denominator) * 100
        else:
            recovery_rate = 100.0 if recovery_mean >= baseline_mean else 0.0
    else:
        recovery_rate = None
    
    # Classify damage severity
    if blackout_pct is not None:
        if blackout_pct > 50:
            severity = "Severe"
        elif blackout_pct > 20:
            severity = "Moderate"
        else:
            severity = "Minor"
    else:
        severity = "Unknown"
    
    # Store results
    results.append({
        "buffer_km": buffer_name,
        "period_type": "pre_event",
        "start_date": PRE_EVENT_START,
        "end_date": "2025-03-21",
        "mean_antl": baseline_mean,
        "std_antl": pre_event_stats["std"],
        "pixel_count": pre_event_stats["count"],
        "blackout_pct": None,
        "recovery_rate": None,
        "severity": None,
    })
    
    results.append({
        "buffer_km": buffer_name,
        "period_type": "first_night",
        "start_date": FIRST_NIGHT_DATE,
        "end_date": FIRST_NIGHT_DATE,
        "mean_antl": event_night_mean,
        "std_antl": first_night_stats["std"],
        "pixel_count": first_night_stats["count"],
        "blackout_pct": blackout_pct,
        "recovery_rate": None,
        "severity": severity,
    })
    
    results.append({
        "buffer_km": buffer_name,
        "period_type": "recovery",
        "start_date": RECOVERY_START,
        "end_date": "2025-04-11",
        "mean_antl": recovery_mean,
        "std_antl": recovery_stats["std"],
        "pixel_count": recovery_stats["count"],
        "blackout_pct": None,
        "recovery_rate": recovery_rate,
        "severity": None,
    })
    
    print(f"  Pre-event ANTL: {baseline_mean:.4f} ± {pre_event_stats['std']:.4f} (n={pre_event_stats['count']:.0f})")
    print(f"  First night ANTL: {event_night_mean:.4f} ± {first_night_stats['std']:.4f}")
    print(f"  Recovery ANTL: {recovery_mean:.4f} ± {recovery_stats['std']:.4f}")
    print(f"  Blackout %: {blackout_pct:.2f}% ({severity})")
    if recovery_rate is not None:
        print(f"  Recovery rate: {recovery_rate:.2f}%")

# =============================================================================
# Export Results
# =============================================================================

# Create DataFrame and save to CSV
df_results = pd.DataFrame(results)
output_csv = storage_manager.resolve_output_path("myanmar_earthquake_antl_timeseries.csv")
df_results.to_csv(output_csv, index=False)
print(f"\n{'='*70}")
print(f"Results saved to: {output_csv}")
print(f"{'='*70}")

# Create summary DataFrame for damage assessment
summary_data = []
for buffer_name in BUFFERS.keys():
    buffer_results = [r for r in results if r["buffer_km"] == buffer_name]
    pre_event = next((r for r in buffer_results if r["period_type"] == "pre_event"), None)
    first_night = next((r for r in buffer_results if r["period_type"] == "first_night"), None)
    recovery = next((r for r in buffer_results if r["period_type"] == "recovery"), None)
    
    if pre_event and first_night:
        summary_data.append({
            "buffer_km": buffer_name,
            "baseline_antl": pre_event["mean_antl"],
            "first_night_antl": first_night["mean_antl"],
            "recovery_antl": recovery["mean_antl"] if recovery else None,
            "blackout_pct": first_night["blackout_pct"],
            "recovery_rate": first_night["recovery_rate"],
            "damage_severity": first_night["severity"],
        })

df_summary = pd.DataFrame(summary_data)
summary_csv = storage_manager.resolve_output_path("myanmar_earthquake_damage_summary.csv")
df_summary.to_csv(summary_csv, index=False)
print(f"Damage summary saved to: {summary_csv}")

# Print summary table
print(f"\n{'='*70}")
print("DAMAGE ASSESSMENT SUMMARY")
print(f"{'='*70}")
print(df_summary.to_string(index=False))
print(f"{'='*70}")

# Daily time series for visualization
daily_results = []
for buffer_name, buffer_geom in BUFFERS.items():
    buffer_collection = full_collection.filterBounds(buffer_geom)
    daily_data = compute_daily_antl(buffer_collection, buffer_geom)
    for record in daily_data:
        daily_results.append({
            "buffer_km": buffer_name,
            "date": record["date"],
            "antl": record["antl"],
        })

df_daily = pd.DataFrame(daily_results)
daily_csv = storage_manager.resolve_output_path("myanmar_earthquake_daily_antl.csv")
df_daily.to_csv(daily_csv, index=False)
print(f"Daily time series saved to: {daily_csv}")

print(f"\n{'='*70}")
print("Analysis complete!")
print(f"{'='*70}")