import ee
import pandas as pd
from storage_manager import storage_manager

# Initialize GEE with project
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Define Myanmar study area using bounds from boundary file
# AOI_CONFIRMED_BY_USER: myanmar_boundary.shp via get_administrative_division_osm_tool
# Bounds: [92.1729181, 9.526084, 101.1700796, 28.547835] (EPSG:4326)
myanmar_bounds = ee.Geometry.Rectangle([92.1729181, 9.526084, 101.1700796, 28.547835])

# Define date ranges
PRE_EVENT_START = "2025-03-20"
PRE_EVENT_END = "2025-03-28"  # Exclusive, so up to 2025-03-27
EARTHQUAKE_DATE = "2025-03-28"
POST_EVENT_START = "2025-03-29"
POST_EVENT_END = "2025-04-06"  # Exclusive, so up to 2025-04-05

# Define VNP46A2 collection
def get_vnp46a2_collection(start_date, end_date):
    return (
        ee.ImageCollection("NASA/VIIRS/002/VNP46A2")
        .filterDate(start_date, end_date)
        .filterBounds(myanmar_bounds)
        .select("Gap_Filled_DNB_BRDF_Corrected_NTL")
    )

# Function to compute ANTL per image
def per_image_stat(img):
    antl = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=myanmar_bounds,
        scale=500,
        maxPixels=1e13,
        bestEffort=True,
    ).get("Gap_Filled_DNB_BRDF_Corrected_NTL")
    return ee.Feature(None, {
        "date": img.date().format("YYYY-MM-dd"),
        "ANTL": antl,
    })

# Compute pre-event ANTL (2025-03-20 to 2025-03-27)
pre_event_collection = get_vnp46a2_collection(PRE_EVENT_START, PRE_EVENT_END)
pre_event_fc = ee.FeatureCollection(pre_event_collection.map(per_image_stat))
pre_event_rows = [f["properties"] for f in pre_event_fc.getInfo()["features"]]

# Compute earthquake day ANTL (2025-03-28)
earthquake_collection = get_vnp46a2_collection(EARTHQUAKE_DATE, "2025-03-29")
earthquake_fc = ee.FeatureCollection(earthquake_collection.map(per_image_stat))
earthquake_rows = [f["properties"] for f in earthquake_fc.getInfo()["features"]]

# Compute post-event ANTL (2025-03-29 to 2025-04-05)
post_event_collection = get_vnp46a2_collection(POST_EVENT_START, POST_EVENT_END)
post_event_fc = ee.FeatureCollection(post_event_collection.map(per_image_stat))
post_event_rows = [f["properties"] for f in post_event_fc.getInfo()["features"]]

# Combine all results
all_rows = pre_event_rows + earthquake_rows + post_event_rows
df = pd.DataFrame(all_rows).sort_values("date")

# Add period classification
def classify_period(date_str):
    if date_str < "2025-03-28":
        return "pre_event"
    elif date_str == "2025-03-28":
        return "earthquake_day"
    else:
        return "post_event"

df["period"] = df["date"].apply(classify_period)

# Compute summary statistics by period
summary_stats = df.groupby("period")["ANTL"].agg(["mean", "std", "min", "max", "count"]).reset_index()
summary_stats.columns = ["period", "ANTL_mean", "ANTL_std", "ANTL_min", "ANTL_max", "ANTL_count"]

# Compute damage assessment metrics
pre_event_mean = df[df["period"] == "pre_event"]["ANTL"].mean()
earthquake_day_antl = df[df["period"] == "earthquake_day"]["ANTL"].values[0] if len(df[df["period"] == "earthquake_day"]) > 0 else None
post_event_mean = df[df["period"] == "post_event"]["ANTL"].mean()

# Calculate percentage change
if pre_event_mean and earthquake_day_antl:
    earthquake_day_change_pct = ((earthquake_day_antl - pre_event_mean) / pre_event_mean) * 100
else:
    earthquake_day_change_pct = None

if pre_event_mean and post_event_mean:
    post_event_change_pct = ((post_event_mean - pre_event_mean) / pre_event_mean) * 100
else:
    post_event_change_pct = None

# Add damage assessment summary
damage_summary = {
    "metric": [
        "pre_event_mean_ANTL",
        "earthquake_day_ANTL",
        "earthquake_day_change_percent",
        "post_event_mean_ANTL",
        "post_event_change_percent"
    ],
    "value": [
        pre_event_mean,
        earthquake_day_antl,
        earthquake_day_change_pct,
        post_event_mean,
        post_event_change_pct
    ]
}
damage_df = pd.DataFrame(damage_summary)

# Save outputs
daily_antl_csv = storage_manager.resolve_output_path("myanmar_earthquake_daily_antl.csv")
summary_csv = storage_manager.resolve_output_path("myanmar_earthquake_antl_summary.csv")
damage_csv = storage_manager.resolve_output_path("myanmar_earthquake_damage_assessment.csv")

df.to_csv(daily_antl_csv, index=False)
summary_stats.to_csv(summary_csv, index=False)
damage_df.to_csv(damage_csv, index=False)

print(f"Daily ANTL saved to: {daily_antl_csv}")
print(f"Summary statistics saved to: {summary_csv}")
print(f"Damage assessment saved to: {damage_csv}")

# Print summary for quick review
print("\n=== Myanmar Earthquake ANTL Damage Assessment ===")
print(f"Earthquake Date: 2025-03-28 (M7.7, Epicenter: 22.013°N, 95.922°E)")
print(f"\nPre-event Period: 2025-03-20 to 2025-03-27")
print(f"  Mean ANTL: {pre_event_mean:.4f}" if pre_event_mean else "  Mean ANTL: N/A")
print(f"\nEarthquake Day: 2025-03-28")
print(f"  ANTL: {earthquake_day_antl:.4f}" if earthquake_day_antl else "  ANTL: N/A")
if earthquake_day_change_pct is not None:
    print(f"  Change from Pre-event: {earthquake_day_change_pct:.2f}%")
print(f"\nPost-event Period: 2025-03-29 to 2025-04-05")
print(f"  Mean ANTL: {post_event_mean:.4f}" if post_event_mean else "  Mean ANTL: N/A")
if post_event_change_pct is not None:
    print(f"  Change from Pre-event: {post_event_change_pct:.2f}%")
print("\n===============================================")
