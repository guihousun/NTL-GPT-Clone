import ee
import pandas as pd
from storage_manager import storage_manager

# Initialize GEE
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Load Myanmar boundary from inputs
boundary_path = storage_manager.resolve_input_path('myanmar_boundary.shp')
import geopandas as gpd
boundary_gdf = gpd.read_file(boundary_path)
# Get bounds for GEE geometry
bounds = boundary_gdf.total_bounds
region = ee.Geometry.Rectangle([bounds[0], bounds[1], bounds[2], bounds[3]])

# Earthquake event details
# Event: 2025-03-28 12:50:52 MMT (06:20 UTC)
# First night after earthquake: 2025-03-29 (local day D+1, since event occurred after 01:30 overpass)
EARTHQUAKE_DATE = "2025-03-28"
FIRST_NIGHT_DATE = "2025-03-29"
PRE_EVENT_START = "2025-03-20"
PRE_EVENT_END = "2025-03-28"  # Up to but not including earthquake day
POST_EVENT_START = "2025-03-29"
POST_EVENT_END = "2025-04-10"

# VNP46A2 collection
collection = (
    ee.ImageCollection("NASA/VIIRS/002/VNP46A2")
    .filterDate(PRE_EVENT_START, POST_EVENT_END)
    .filterBounds(region)
    .select("Gap_Filled_DNB_BRDF_Corrected_NTL")
)

# Compute daily ANTL using server-side map
def per_image_stat(img):
    date_str = img.date().format("YYYY-MM-dd")
    value = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=region,
        scale=500,
        maxPixels=1e13,
        bestEffort=True,
    ).get("Gap_Filled_DNB_BRDF_Corrected_NTL")
    return ee.Feature(None, {
        "date": date_str,
        "antl": value,
    })

stats_fc = ee.FeatureCollection(collection.map(per_image_stat))
rows = [f["properties"] for f in stats_fc.getInfo()["features"]]
df = pd.DataFrame(rows).sort_values("date")

# Add period classification
def classify_period(date_str):
    if date_str < EARTHQUAKE_DATE:
        return "pre_event"
    elif date_str == FIRST_NIGHT_DATE:
        return "first_night_post_event"
    else:
        return "post_event"

df["period"] = df["date"].apply(classify_period)
df["antl"] = pd.to_numeric(df["antl"], errors="coerce")

# Save daily ANTL metrics
out_csv = storage_manager.resolve_output_path("myanmar_earthquake_daily_antl.csv")
df.to_csv(out_csv, index=False)
print(f"Daily ANTL saved to: {out_csv}")

# Compute summary statistics for damage assessment
pre_event_df = df[df["period"] == "pre_event"]
first_night_df = df[df["period"] == "first_night_post_event"]
post_event_df = df[df["period"] == "post_event"]

# Pre-event baseline statistics
pre_event_mean = pre_event_df["antl"].mean()
pre_event_std = pre_event_df["antl"].std()
pre_event_median = pre_event_df["antl"].median()

# First night ANTL
first_night_antl = first_night_df["antl"].values[0] if len(first_night_df) > 0 else None

# Post-event statistics
post_event_mean = post_event_df["antl"].mean()
post_event_std = post_event_df["antl"].std()

# Damage assessment metrics
if first_night_antl is not None and pre_event_mean is not None:
    first_night_change_pct = ((first_night_antl - pre_event_mean) / pre_event_mean) * 100 if pre_event_mean != 0 else None
    post_event_change_pct = ((post_event_mean - pre_event_mean) / pre_event_mean) * 100 if pre_event_mean != 0 else None
else:
    first_night_change_pct = None
    post_event_change_pct = None

# Create impact assessment report
import json
report = {
    "earthquake_event": {
        "date_utc": "2025-03-28T06:20:00Z",
        "date_mmt": "2025-03-28T12:50:52+06:30",
        "magnitude_mw": 7.7,
        "depth_km": 10,
        "epicenter_lat": 22.013,
        "epicenter_lon": 95.922,
        "location": "Sagaing Township, Myanmar",
        "source": "USGS"
    },
    "ntl_analysis": {
        "dataset": "NASA/VIIRS/002/VNP46A2",
        "band": "Gap_Filled_DNB_BRDF_Corrected_NTL",
        "spatial_resolution_m": 500,
        "region": "Myanmar",
        "analysis_period": {
            "start": PRE_EVENT_START,
            "end": POST_EVENT_END
        },
        "first_night_rule": "Earthquake occurred at 12:50:52 MMT on 2025-03-28. VNP46A2 overpass ~01:30 local. Event after overpass, so first_night = 2025-03-29 (D+1)."
    },
    "antl_statistics": {
        "pre_event": {
            "period": f"{PRE_EVENT_START} to {PRE_EVENT_END}",
            "days": len(pre_event_df),
            "mean_antl": float(pre_event_mean) if pd.notna(pre_event_mean) else None,
            "std_antl": float(pre_event_std) if pd.notna(pre_event_std) else None,
            "median_antl": float(pre_event_median) if pd.notna(pre_event_median) else None
        },
        "first_night_post_event": {
            "date": FIRST_NIGHT_DATE,
            "antl": float(first_night_antl) if first_night_antl is not None and pd.notna(first_night_antl) else None,
            "change_from_baseline_pct": float(first_night_change_pct) if first_night_change_pct is not None and pd.notna(first_night_change_pct) else None
        },
        "post_event": {
            "period": f"{POST_EVENT_START} to {POST_EVENT_END}",
            "days": len(post_event_df),
            "mean_antl": float(post_event_mean) if pd.notna(post_event_mean) else None,
            "std_antl": float(post_event_std) if pd.notna(post_event_std) else None,
            "change_from_baseline_pct": float(post_event_change_pct) if post_event_change_pct is not None and pd.notna(post_event_change_pct) else None
        }
    },
    "damage_assessment": {
        "impact_severity": "severe" if first_night_change_pct is not None and first_night_change_pct < -30 else "moderate" if first_night_change_pct is not None and first_night_change_pct < -10 else "minor" if first_night_change_pct is not None else "unknown",
        "recovery_trend": "recovering" if post_event_change_pct is not None and post_event_change_pct > first_night_change_pct else "declining" if post_event_change_pct is not None and post_event_change_pct < first_night_change_pct else "stable" if post_event_change_pct is not None else "unknown",
        "notes": [
            "Negative ANTL change indicates power outages, infrastructure damage, or population displacement.",
            "Recovery trend assessed by comparing post-event mean to first-night value.",
            "Official casualty data (as of 2025-04-12): 3,700 deaths, 4,800 injured, ~200,000 displaced in Myanmar."
        ]
    }
}

# Save impact assessment report
report_path = storage_manager.resolve_output_path("myanmar_earthquake_impact_assessment.json")
with open(report_path, "w") as f:
    json.dump(report, f, indent=2)
print(f"Impact assessment report saved to: {report_path}")

print("\n=== ANTL Damage Assessment Summary ===")
print(f"Pre-event baseline mean ANTL: {pre_event_mean:.4f}" if pd.notna(pre_event_mean) else "Pre-event baseline mean ANTL: N/A")
print(f"First night (2025-03-29) ANTL: {first_night_antl:.4f}" if first_night_antl and pd.notna(first_night_antl) else "First night ANTL: N/A")
print(f"First night change from baseline: {first_night_change_pct:.2f}%" if first_night_change_pct and pd.notna(first_night_change_pct) else "First night change: N/A")
print(f"Post-event mean ANTL: {post_event_mean:.4f}" if pd.notna(post_event_mean) else "Post-event mean ANTL: N/A")
print(f"Post-event change from baseline: {post_event_change_pct:.2f}%" if post_event_change_pct and pd.notna(post_event_change_pct) else "Post-event change: N/A")