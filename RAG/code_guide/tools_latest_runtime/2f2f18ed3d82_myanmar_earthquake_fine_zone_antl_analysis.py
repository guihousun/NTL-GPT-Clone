import ee
import pandas as pd
from storage_manager import storage_manager

# Initialize GEE with project
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Earthquake epicenter from USGS: 22.013°N, 95.922°E
epicenter = ee.Geometry.Point([95.922, 22.013])

# Create finer buffer zones around epicenter
# Zone 1: 0-25km (core damage zone - epicenter area)
# Zone 2: 25-50km (severe damage zone)
# Zone 3: 50-100km (moderate damage zone)
# Zone 4: 100-200km (light damage zone)
# Zone 5: 200-300km (control zone)
zone_25km = epicenter.buffer(25000)   # 25km
zone_50km = epicenter.buffer(50000)   # 50km
zone_100km = epicenter.buffer(100000) # 100km
zone_200km = epicenter.buffer(200000) # 200km
zone_300km = epicenter.buffer(300000) # 300km

# Create ring zones (annulus)
zone_0_25 = zone_25km
zone_25_50 = zone_50km.difference(zone_25km)
zone_50_100 = zone_100km.difference(zone_50km)
zone_100_200 = zone_200km.difference(zone_100km)
zone_200_300 = zone_300km.difference(zone_200km)

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
        .select("Gap_Filled_DNB_BRDF_Corrected_NTL")
    )

# Define zones with descriptive names
zones = [
    (zone_0_25, "0-25km_core"),
    (zone_25_50, "25-50km_severe"),
    (zone_50_100, "50-100km_moderate"),
    (zone_100_200, "100-200km_light"),
    (zone_200_300, "200-300km_control"),
]

# Collect results for all zones and periods
all_results = []

for zone_geom, zone_name in zones:
    # Create closure for per_image_stat function
    def make_per_image_stat(zone_geom, zone_name):
        def per_image_stat(img):
            antl = img.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=zone_geom,
                scale=500,
                maxPixels=1e13,
                bestEffort=True,
            ).get("Gap_Filled_DNB_BRDF_Corrected_NTL")
            return ee.Feature(None, {
                "date": img.date().format("YYYY-MM-dd"),
                "zone": zone_name,
                "ANTL": antl,
            })
        return per_image_stat
    
    per_image_stat = make_per_image_stat(zone_geom, zone_name)
    
    # Pre-event
    pre_collection = get_vnp46a2_collection(PRE_EVENT_START, PRE_EVENT_END)
    pre_fc = ee.FeatureCollection(pre_collection.map(per_image_stat))
    pre_rows = [f["properties"] for f in pre_fc.getInfo()["features"]]
    all_results.extend(pre_rows)
    
    # Earthquake day
    eq_collection = get_vnp46a2_collection(EARTHQUAKE_DATE, "2025-03-29")
    eq_fc = ee.FeatureCollection(eq_collection.map(per_image_stat))
    eq_rows = [f["properties"] for f in eq_fc.getInfo()["features"]]
    all_results.extend(eq_rows)
    
    # Post-event
    post_collection = get_vnp46a2_collection(POST_EVENT_START, POST_EVENT_END)
    post_fc = ee.FeatureCollection(post_collection.map(per_image_stat))
    post_rows = [f["properties"] for f in post_fc.getInfo()["features"]]
    all_results.extend(post_rows)

# Create DataFrame
df = pd.DataFrame(all_results).sort_values(["zone", "date"])

# Add period classification
def classify_period(date_str):
    if date_str < "2025-03-28":
        return "pre_event"
    elif date_str == "2025-03-28":
        return "earthquake_day"
    else:
        return "post_event"

df["period"] = df["date"].apply(classify_period)

# Compute summary statistics by zone and period
summary_stats = df.groupby(["zone", "period"])["ANTL"].agg(["mean", "std", "min", "max", "count"]).reset_index()

# Compute damage assessment metrics per zone
damage_results = []
for zone in df["zone"].unique():
    zone_df = df[df["zone"] == zone]
    pre_mean = zone_df[zone_df["period"] == "pre_event"]["ANTL"].mean()
    eq_antl = zone_df[zone_df["period"] == "earthquake_day"]["ANTL"].values
    eq_antl = eq_antl[0] if len(eq_antl) > 0 else None
    post_mean = zone_df[zone_df["period"] == "post_event"]["ANTL"].mean()
    
    eq_change_pct = ((eq_antl - pre_mean) / pre_mean * 100) if (pre_mean and eq_antl) else None
    post_change_pct = ((post_mean - pre_mean) / pre_mean * 100) if (pre_mean and post_mean) else None
    
    damage_results.append({
        "zone": zone,
        "pre_event_mean": pre_mean,
        "earthquake_day_antl": eq_antl,
        "earthquake_day_change_pct": eq_change_pct,
        "post_event_mean": post_mean,
        "post_event_change_pct": post_change_pct,
    })

damage_df = pd.DataFrame(damage_results)

# Save outputs
daily_antl_csv = storage_manager.resolve_output_path("myanmar_eq_fine_zone_daily_antl.csv")
summary_csv = storage_manager.resolve_output_path("myanmar_eq_fine_zone_summary.csv")
damage_csv = storage_manager.resolve_output_path("myanmar_eq_fine_zone_damage_assessment.csv")

df.to_csv(daily_antl_csv, index=False)
summary_stats.to_csv(summary_csv, index=False)
damage_df.to_csv(damage_csv, index=False)

print(f"Daily ANTL saved to: {daily_antl_csv}")
print(f"Summary statistics saved to: {summary_csv}")
print(f"Damage assessment saved to: {damage_csv}")

# Print detailed summary
print("\n" + "="*80)
print("2025年缅甸地震 - 精细分区ANTL灾害评估")
print("震中: 22.013°N, 95.922°E (M7.7, 2025-03-28)")
print("分析区域: 以震中为中心的同心圆缓冲区")
print("="*80)
print(f"\n{'区域':<20} {'震前均值':>10} {'地震当日':>10} {'当日变化%':>12} {'震后均值':>10} {'震后变化%':>12}")
print("-"*80)
for _, row in damage_df.iterrows():
    zone_display = row["zone"].replace("_", " ")
    pre = f"{row['pre_event_mean']:.4f}" if row['pre_event_mean'] else "N/A"
    eq = f"{row['earthquake_day_antl']:.4f}" if row['earthquake_day_antl'] else "N/A"
    eq_pct = f"{row['earthquake_day_change_pct']:+.2f}%" if row['earthquake_day_change_pct'] else "N/A"
    post = f"{row['post_event_mean']:.4f}" if row['post_event_mean'] else "N/A"
    post_pct = f"{row['post_event_change_pct']:+.2f}%" if row['post_event_change_pct'] else "N/A"
    print(f"{zone_display:<20} {pre:>10} {eq:>10} {eq_pct:>12} {post:>10} {post_pct:>12}")
print("="*80)

# Print key findings
print("\n📊 关键发现:")
print("-"*80)

# Find zone with maximum change
max_eq_zone = damage_df.loc[damage_df['earthquake_day_change_pct'].abs().idxmax()]
print(f"• 地震当日变化最大区域: {max_eq_zone['zone'].replace('_', ' ')} ({max_eq_zone['earthquake_day_change_pct']:+.2f}%)")

# Find core zone (0-25km) results
core_zone = damage_df[damage_df['zone'] == '0-25km_core'].iloc[0]
print(f"• 震中核心区(0-25km): 震前={core_zone['pre_event_mean']:.4f}, 地震当日={core_zone['earthquake_day_antl']:.4f} ({core_zone['earthquake_day_change_pct']:+.2f}%)")

# Analyze recovery pattern
print("\n📈 震后恢复模式:")
for _, row in damage_df.iterrows():
    zone_display = row["zone"].replace("_", " ")
    post_pct = row['post_event_change_pct']
    if post_pct is not None:
        status = "已恢复" if abs(post_pct) < 10 else "持续影响" if post_pct > 10 else "低于震前"
        print(f"  • {zone_display}: {post_pct:+.2f}% ({status})")

print("="*80)
