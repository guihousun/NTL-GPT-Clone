"""
Myanmar 2025 Earthquake Impact Assessment using VNP46A2 Daily NTL Data
Event: M7.7 Mandalay, Burma (Myanmar) Earthquake
Date: 2025-03-28 06:20:52 UTC (12:50:52 MMT local time)
Epicenter: 22.013°N, 95.922°E

First post-event night determination:
- VNP46A2 overpass: ~01:30 local time
- Event occurred at 12:51 PM local time on March 28 (AFTER 01:30 AM overpass)
- First post-event night: 2025-03-29 (day D+1)

Periods:
- Pre-event baseline: 2025-03-14 to 2025-03-27 (14 days)
- First post-event night: 2025-03-29
- Post-event recovery: 2025-03-30 to 2025-04-11 (13 days)
"""

import ee
import pandas as pd
import numpy as np
from storage_manager import storage_manager

# Initialize GEE
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Epicenter coordinates from USGS
EPICENTER_LAT = 22.013
EPICENTER_LON = 95.922

# Create epicenter point and multi-scale buffer zones
epicenter = ee.Geometry.Point([EPICENTER_LON, EPICENTER_LAT])
buffer_25km = epicenter.buffer(25000)
buffer_50km = epicenter.buffer(50000)
buffer_100km = epicenter.buffer(100000)

buffers = {
    "25km": buffer_25km,
    "50km": buffer_50km,
    "100km": buffer_100km,
}

# VNP46A2 collection parameters
DATASET = "NASA/VIIRS/002/VNP46A2"
BAND = "Gap_Filled_DNB_BRDF_Corrected_NTL"
SCALE = 500  # meters
MAX_PIXELS = 1e13

# Date ranges
BASELINE_START = "2025-03-14"
BASELINE_END = "2025-03-28"  # Up to but not including event day
FIRST_NIGHT_DATE = "2025-03-29"
RECOVERY_START = "2025-03-30"
RECOVERY_END = "2025-04-12"  # Up to but not including

# Full collection for time series
collection = (
    ee.ImageCollection(DATASET)
    .filterDate(BASELINE_START, RECOVERY_END)
    .filterBounds(buffer_100km)
    .select(BAND)
)

print(f"Total images in collection: {collection.size().getInfo()}")

# Function to compute mean ANTL for a given geometry
def compute_mean_antl(img, geometry, band_name):
    """Compute mean ANTL value for an image within a geometry."""
    stat = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometry,
        scale=SCALE,
        maxPixels=MAX_PIXELS,
        bestEffort=True,
    ).get(band_name)
    return stat

# Function to create feature with date and ANTL value for a buffer
def per_image_stats_for_buffer(buffer_name, geometry):
    """Map function to compute stats per image for a specific buffer."""
    def compute_stats(img):
        date_str = img.date().format("YYYY-MM-dd")
        antl_value = compute_mean_antl(img, geometry, BAND)
        return ee.Feature(None, {
            "date": date_str,
            "buffer": buffer_name,
            "ANTL": antl_value,
        })
    return compute_stats

# Compute time series for all buffers
all_features = []
for buffer_name, geometry in buffers.items():
    buffer_collection = collection.map(per_image_stats_for_buffer(buffer_name, geometry))
    all_features.append(buffer_collection)

# Combine all features
combined_fc = ee.FeatureCollection(all_features).flatten()

# Get results
print("Fetching time series data from GEE...")
features_info = combined_fc.getInfo()["features"]

# Convert to DataFrame
rows = []
for feat in features_info:
    props = feat["properties"]
    rows.append({
        "date": props["date"],
        "buffer": props["buffer"],
        "ANTL": props["ANTL"],
    })

df = pd.DataFrame(rows)
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values(["date", "buffer"]).reset_index(drop=True)

# Save full time series
out_timeseries_csv = storage_manager.resolve_output_path("myanmar_earthquake_antl_timeseries.csv")
df.to_csv(out_timeseries_csv, index=False)
print(f"Time series saved to: {out_timeseries_csv}")

# Define period labels
def get_period(date_str):
    """Classify date into baseline, first_night, or recovery period."""
    date = pd.to_datetime(date_str)
    baseline_end = pd.to_datetime(BASELINE_END)
    first_night = pd.to_datetime(FIRST_NIGHT_DATE)
    recovery_end = pd.to_datetime(RECOVERY_END)
    
    if date < baseline_end:
        return "baseline"
    elif date == first_night:
        return "first_night"
    elif date < recovery_end:
        return "recovery"
    else:
        return "other"

df["period"] = df["date"].apply(get_period)

# Compute summary statistics per buffer and period
summary_stats = df.groupby(["buffer", "period"])["ANTL"].agg(["mean", "std", "count", "min", "max"]).reset_index()
summary_stats.columns = ["buffer", "period", "mean_ANTL", "std_ANTL", "count", "min_ANTL", "max_ANTL"]

# Pivot to get values for damage computation
pivot_df = df.groupby(["buffer", "period"])["ANTL"].mean().unstack(level="period").reset_index()

# Compute damage metrics
damage_metrics = []
for _, row in pivot_df.iterrows():
    buffer = row["buffer"]
    baseline_antl = row.get("baseline", np.nan)
    first_night_antl = row.get("first_night", np.nan)
    recovery_antl = row.get("recovery", np.nan)
    
    # Drop percentage: (first_night - baseline) / baseline * 100
    if pd.notna(baseline_antl) and pd.notna(first_night_antl) and baseline_antl > 0:
        drop_pct = ((first_night_antl - baseline_antl) / baseline_antl) * 100
    else:
        drop_pct = np.nan
    
    # Recovery rate: (recovery - first_night) / (baseline - first_night) * 100
    if pd.notna(baseline_antl) and pd.notna(first_night_antl) and pd.notna(recovery_antl):
        if (baseline_antl - first_night_antl) != 0:
            recovery_rate = ((recovery_antl - first_night_antl) / (baseline_antl - first_night_antl)) * 100
        else:
            recovery_rate = np.nan
    else:
        recovery_rate = np.nan
    
    # Damage severity classification based on drop percentage
    if pd.notna(drop_pct):
        if drop_pct < -50:
            severity = "Severe"
        elif drop_pct < -25:
            severity = "Moderate"
        elif drop_pct < 0:
            severity = "Light"
        else:
            severity = "No damage / Increase"
    else:
        severity = "Unknown"
    
    damage_metrics.append({
        "buffer": buffer,
        "baseline_ANTL": baseline_antl,
        "first_night_ANTL": first_night_antl,
        "recovery_ANTL": recovery_antl,
        "drop_percentage": drop_pct,
        "recovery_rate": recovery_rate,
        "damage_severity": severity,
    })

damage_df = pd.DataFrame(damage_metrics)

# Save summary statistics
out_summary_csv = storage_manager.resolve_output_path("myanmar_earthquake_summary_stats.csv")
summary_stats.to_csv(out_summary_csv, index=False)
print(f"Summary statistics saved to: {out_summary_csv}")

# Save damage metrics
out_damage_csv = storage_manager.resolve_output_path("myanmar_earthquake_damage_metrics.csv")
damage_df.to_csv(out_damage_csv, index=False)
print(f"Damage metrics saved to: {out_damage_csv}")

# Print damage assessment summary
print("\n" + "="*80)
print("MYANMAR 2025 EARTHQUAKE IMPACT ASSESSMENT SUMMARY")
print("="*80)
print(f"Event: M7.7 Mandalay, Burma (Myanmar) Earthquake")
print(f"Date: 2025-03-28 06:20:52 UTC (12:50:52 MMT)")
print(f"Epicenter: {EPICENTER_LAT}°N, {EPICENTER_LON}°E")
print(f"First post-event night: {FIRST_NIGHT_DATE}")
print("="*80)
print("\nDamage Assessment by Buffer Zone:")
print("-"*80)
for _, row in damage_df.iterrows():
    print(f"\n{row['buffer']} Buffer:")
    print(f"  Baseline ANTL (2025-03-14 to 2025-03-27): {row['baseline_ANTL']:.4f}")
    print(f"  First Night ANTL ({FIRST_NIGHT_DATE}):     {row['first_night_ANTL']:.4f}")
    print(f"  Recovery ANTL (2025-03-30 to 2025-04-11):  {row['recovery_ANTL']:.4f}")
    print(f"  Drop Percentage: {row['drop_percentage']:.2f}%")
    print(f"  Recovery Rate:   {row['recovery_rate']:.2f}%")
    print(f"  Damage Severity: {row['damage_severity']}")

print("\n" + "="*80)
print("OUTPUT FILES:")
print(f"  - Time series: {out_timeseries_csv}")
print(f"  - Summary stats: {out_summary_csv}")
print(f"  - Damage metrics: {out_damage_csv}")
print("="*80)
