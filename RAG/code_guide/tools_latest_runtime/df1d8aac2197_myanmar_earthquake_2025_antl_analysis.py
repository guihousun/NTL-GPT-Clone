"""
Myanmar Earthquake 2025 Impact Assessment using Daily NPP-VIIRS VNP46A2 NTL Data
Computes ANTL statistics for pre-event, event day, and post-event periods.
Fixed: Load boundary locally and convert to GEE-compatible format.
"""
import ee
import pandas as pd
import geopandas as gpd
import json
from storage_manager import storage_manager

# Initialize GEE
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Load boundary locally with geopandas
boundary_path = storage_manager.resolve_input_path("myanmar_boundary.shp")
gdf = gpd.read_file(boundary_path)

# Convert to GeoJSON and then to GEE FeatureCollection
geojson_str = gdf.to_json()
geojson_dict = json.loads(geojson_str)
region = ee.FeatureCollection(geojson_dict)
geom = region.geometry()

print(f"Boundary loaded: {len(gdf)} feature(s), CRS: {gdf.crs}")
print(f"Geometry bounds: {geom.bounds().getInfo()}")

# Define analysis periods
PRE_EVENT_START = "2025-03-01"
PRE_EVENT_END = "2025-03-28"  # exclusive
EVENT_DATE = "2025-03-28"
POST_EVENT_START = "2025-03-29"
POST_EVENT_END = "2025-05-01"  # exclusive

# Load VNP46A2 collection
collection = (
    ee.ImageCollection("NASA/VIIRS/002/VNP46A2")
    .filterDate(PRE_EVENT_START, POST_EVENT_END)
    .filterBounds(geom)
    .select("Gap_Filled_DNB_BRDF_Corrected_NTL")
)

# Count images
image_count = collection.size().getInfo()
print(f"VNP46A2 images found: {image_count}")

def per_image_stat(img):
    """Compute mean ANTL for each image over the region."""
    antl = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geom,
        scale=500,
        maxPixels=1e13,
        bestEffort=True,
    ).get("Gap_Filled_DNB_BRDF_Corrected_NTL")
    return ee.Feature(None, {
        "date": img.date().format("YYYY-MM-dd"),
        "ANTL": antl,
    })

# Map over collection to get daily stats
stats_fc = ee.FeatureCollection(collection.map(per_image_stat))
records = [f["properties"] for f in stats_fc.getInfo()["features"]]

# Create DataFrame
df = pd.DataFrame(records).sort_values("date")
df["ANTL"] = pd.to_numeric(df["ANTL"], errors="coerce")

# Save daily metrics
daily_csv_path = storage_manager.resolve_output_path("myanmar_earthquake_2025_antl_metrics.csv")
df.to_csv(daily_csv_path, index=False)
print(f"Daily ANTL metrics saved to: {daily_csv_path}")

# Compute period statistics
pre_event = df[df["date"] < EVENT_DATE]["ANTL"]
event_day = df[df["date"] == EVENT_DATE]["ANTL"]
post_event = df[df["date"] > EVENT_DATE]["ANTL"]

pre_event_mean = pre_event.mean() if len(pre_event) > 0 else None
pre_event_std = pre_event.std() if len(pre_event) > 0 else None
event_day_value = event_day.iloc[0] if len(event_day) > 0 else None
post_event_mean = post_event.mean() if len(post_event) > 0 else None
post_event_std = post_event.std() if len(post_event) > 0 else None

# Compute impact metrics
if pre_event_mean is not None and event_day_value is not None:
    # ANTL drop on event night (negative = loss of light)
    antl_drop = event_day_value - pre_event_mean
    antl_drop_pct = (antl_drop / pre_event_mean * 100) if pre_event_mean != 0 else None
    
    # Recovery indicator (post-event vs pre-event)
    recovery_diff = post_event_mean - pre_event_mean if post_event_mean is not None else None
    recovery_pct = (recovery_diff / pre_event_mean * 100) if (post_event_mean is not None and pre_event_mean != 0) else None
else:
    antl_drop = None
    antl_drop_pct = None
    recovery_diff = None
    recovery_pct = None

# Create summary report
summary = {
    "earthquake_info": {
        "event_date": "2025-03-28",
        "event_time_utc": "06:20:54",
        "magnitude": 7.7,
        "epicenter_lat": 22.01,
        "epicenter_lon": 95.92,
        "depth_km": 10,
        "source": "USGS",
        "glide_id": "EQ-2025-000043-MMR"
    },
    "analysis_parameters": {
        "dataset": "NASA/VIIRS/002/VNP46A2",
        "band": "Gap_Filled_DNB_BRDF_Corrected_NTL",
        "spatial_resolution_m": 500,
        "region": "Myanmar",
        "pre_event_period": f"{PRE_EVENT_START} to {PRE_EVENT_END}",
        "event_date": EVENT_DATE,
        "post_event_period": f"{POST_EVENT_START} to {POST_EVENT_END}"
    },
    "ntl_statistics": {
        "pre_event": {
            "n_days": int(len(pre_event)),
            "mean_ANTL": float(pre_event_mean) if pre_event_mean is not None else None,
            "std_ANTL": float(pre_event_std) if pre_event_std is not None else None
        },
        "event_day": {
            "date": EVENT_DATE,
            "ANTL": float(event_day_value) if event_day_value is not None else None
        },
        "post_event": {
            "n_days": int(len(post_event)),
            "mean_ANTL": float(post_event_mean) if post_event_mean is not None else None,
            "std_ANTL": float(post_event_std) if post_event_std is not None else None
        }
    },
    "impact_assessment": {
        "antl_drop_event_night": float(antl_drop) if antl_drop is not None else None,
        "antl_drop_percent": float(antl_drop_pct) if antl_drop_pct is not None else None,
        "recovery_difference": float(recovery_diff) if recovery_diff is not None else None,
        "recovery_percent": float(recovery_pct) if recovery_pct is not None else None,
        "interpretation": ""
    },
    "damage_context": {
        "estimated_deaths": "3700+",
        "estimated_injured": "4800+",
        "estimated_displaced": "200000",
        "buildings_damaged": "157000+ (UNU-INWEH SAR analysis)",
        "critical_infrastructure": "3 hospitals destroyed, 22 partially damaged, Ava Bridge collapsed",
        "cultural_heritage": "150 ancient temples damaged in Mandalay Province",
        "rupture_length_km": ">400"
    }
}

# Add interpretation
if antl_drop_pct is not None:
    if antl_drop_pct < -30:
        summary["impact_assessment"]["interpretation"] = "Severe light loss detected on event night, indicating widespread power outages and/or infrastructure damage."
    elif antl_drop_pct < -10:
        summary["impact_assessment"]["interpretation"] = "Moderate light loss detected, suggesting localized power disruptions."
    elif antl_drop_pct < 0:
        summary["impact_assessment"]["interpretation"] = "Minor light loss detected."
    else:
        summary["impact_assessment"]["interpretation"] = "No significant light loss detected on event night."
    
    if recovery_pct is not None:
        if recovery_pct < -20:
            summary["impact_assessment"]["interpretation"] += " Post-event recovery is incomplete with sustained light loss."
        elif recovery_pct < 0:
            summary["impact_assessment"]["interpretation"] += " Partial recovery observed but not yet at pre-event levels."
        else:
            summary["impact_assessment"]["interpretation"] += " Recovery to or above pre-event levels observed."

# Save summary report
import json as json_lib
summary_path = storage_manager.resolve_output_path("myanmar_earthquake_2025_impact_summary.json")
with open(summary_path, "w") as f:
    json_lib.dump(summary, f, indent=2)
print(f"Impact summary saved to: {summary_path}")

print("\n=== Myanmar Earthquake 2025 NTL Impact Assessment ===")
print(f"Pre-event mean ANTL ({len(pre_event)} days): {pre_event_mean:.4f}" if pre_event_mean else "Pre-event: N/A")
print(f"Event day ANTL ({EVENT_DATE}): {event_day_value:.4f}" if event_day_value else "Event day: N/A")
print(f"Post-event mean ANTL ({len(post_event)} days): {post_event_mean:.4f}" if post_event_mean else "Post-event: N/A")
if antl_drop_pct is not None:
    print(f"ANTL drop on event night: {antl_drop:.4f} ({antl_drop_pct:.2f}%)")
if recovery_pct is not None:
    print(f"Recovery (post vs pre): {recovery_diff:.4f} ({recovery_pct:.2f}%)")
print("====================================================")
