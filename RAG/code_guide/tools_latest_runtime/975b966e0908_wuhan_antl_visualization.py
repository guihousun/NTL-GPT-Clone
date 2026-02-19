import ee
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from storage_manager import storage_manager

# AOI_CONFIRMED_BY_USER: Boundary from Data_Searcher (wuhan_boundary.shp for 武汉市)
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Load Wuhan boundary
boundary_path = storage_manager.resolve_input_path('wuhan_boundary.shp')
gdf = gpd.read_file(boundary_path)
region = ee.Geometry.Rectangle(gdf.total_bounds.tolist())

# Load VNP46A2 collection for the full date range (2019-01-23 to 2020-04-08)
collection = (
    ee.ImageCollection("NASA/VIIRS/002/VNP46A2")
    .filterDate("2019-01-23", "2020-04-09")
    .filterBounds(region)
    .select("Gap_Filled_DNB_BRDF_Corrected_NTL")
)

def per_image_stat(img):
    """Compute mean NTL for each image over the region."""
    value = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=region,
        scale=500,
        maxPixels=1e13,
        bestEffort=True,
    ).get("Gap_Filled_DNB_BRDF_Corrected_NTL")
    return ee.Feature(None, {
        "date": img.date().format("YYYY-MM-dd"),
        "value": value,
    })

# Map over the entire collection (server-side)
stats_fc = ee.FeatureCollection(collection.map(per_image_stat))

# Download results to client
rows = [f["properties"] for f in stats_fc.getInfo()["features"]]

# Create DataFrame and sort by date
df = pd.DataFrame(rows).sort_values("date")
df["date"] = pd.to_datetime(df["date"])

# Define lockdown and comparison periods
lockdown_2020_start = pd.Timestamp("2020-01-23")
lockdown_2020_end = pd.Timestamp("2020-04-08")
comparison_2019_start = pd.Timestamp("2019-01-23")
comparison_2019_end = pd.Timestamp("2019-04-08")

# Filter for lockdown period (2020)
df_lockdown = df[(df["date"] >= lockdown_2020_start) & (df["date"] <= lockdown_2020_end)].copy()
antl_lockdown = df_lockdown["value"].mean()

# Filter for comparison period (2019)
df_comparison = df[(df["date"] >= comparison_2019_start) & (df["date"] <= comparison_2019_end)].copy()
antl_comparison = df_comparison["value"].mean()

# Calculate percentage change
pct_change = ((antl_lockdown - antl_comparison) / antl_comparison) * 100

# Create visualization
fig, axes = plt.subplots(2, 1, figsize=(14, 10))

# Plot 1: Time series comparison (shifted to align dates)
df_comparison_plot = df_comparison.copy()
df_lockdown_plot = df_lockdown.copy()

# Shift 2020 dates to 2019 for direct comparison
df_lockdown_plot["date_shifted"] = df_lockdown_plot["date"] - pd.Timedelta(days=365)

ax1 = axes[0]
ax1.plot(df_comparison_plot["date"], df_comparison_plot["value"], 
         label="2019 (Comparison Period)", color="blue", linewidth=1.5, alpha=0.8)
ax1.plot(df_lockdown_plot["date_shifted"], df_lockdown_plot["value"], 
         label="2020 (Lockdown Period)", color="red", linewidth=1.5, alpha=0.8)
ax1.axvline(x=pd.Timestamp("2020-01-23") - pd.Timedelta(days=365), color="red", 
            linestyle="--", linewidth=1.5, label="Lockdown Start (Jan 23)")
ax1.axvline(x=pd.Timestamp("2020-04-08") - pd.Timedelta(days=365), color="darkred", 
            linestyle="--", linewidth=1.5, label="Lockdown End (Apr 8)")
ax1.set_xlabel("Date", fontsize=12)
ax1.set_ylabel("ANTL (Gap-Filled DNB BRDF-Corrected NTL)", fontsize=12)
ax1.set_title("Wuhan Daily ANTL: 2019 vs 2020 Lockdown Period (Aligned)", fontsize=14, fontweight="bold")
ax1.legend(loc="upper left", fontsize=10)
ax1.grid(True, alpha=0.3)
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
ax1.xaxis.set_major_locator(mdates.MonthLocator())
plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha="right")

# Plot 2: Separate time series for each year
ax2 = axes[1]
ax2.plot(df_comparison["date"], df_comparison["value"], 
         label="2019 (Comparison Period)", color="blue", linewidth=1.5, alpha=0.8)
ax2.plot(df_lockdown["date"], df_lockdown["value"], 
         label="2020 (Lockdown Period)", color="red", linewidth=1.5, alpha=0.8)
ax2.axvline(x=lockdown_2020_start, color="red", linestyle="--", linewidth=1.5)
ax2.axvline(x=lockdown_2020_end, color="darkred", linestyle="--", linewidth=1.5)
ax2.axvspan(lockdown_2020_start, lockdown_2020_end, alpha=0.1, color="red", label="Lockdown Period")
ax2.set_xlabel("Date", fontsize=12)
ax2.set_ylabel("ANTL (Gap-Filled DNB BRDF-Corrected NTL)", fontsize=12)
ax2.set_title("Wuhan Daily ANTL: Separate Year View", fontsize=14, fontweight="bold")
ax2.legend(loc="upper left", fontsize=10)
ax2.grid(True, alpha=0.3)
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
ax2.xaxis.set_major_locator(mdates.MonthLocator())
plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")

plt.tight_layout()

# Save visualization
out_png = storage_manager.resolve_output_path("wuhan_antl_lockdown_comparison.png")
plt.savefig(out_png, dpi=150, bbox_inches="tight")
print(f"Visualization saved to: {out_png}")

# Print summary statistics
print(f"\n=== Wuhan ANTL Lockdown Analysis ===")
print(f"Lockdown period (2020-01-23 to 2020-04-08): {len(df_lockdown)} days")
print(f"  ANTL (mean): {antl_lockdown:.4f}")
print(f"  ANTL (std): {df_lockdown['value'].std():.4f}")
print(f"  ANTL (min): {df_lockdown['value'].min():.4f}")
print(f"  ANTL (max): {df_lockdown['value'].max():.4f}")
print(f"\nComparison period (2019-01-23 to 2019-04-08): {len(df_comparison)} days")
print(f"  ANTL (mean): {antl_comparison:.4f}")
print(f"  ANTL (std): {df_comparison['value'].std():.4f}")
print(f"  ANTL (min): {df_comparison['value'].min():.4f}")
print(f"  ANTL (max): {df_comparison['value'].max():.4f}")
print(f"\nPercentage change (lockdown vs comparison): {pct_change:.2f}%")
if pct_change < 0:
    print(f"  Interpretation: Nighttime light DECREASED during lockdown (expected pattern)")
else:
    print(f"  Interpretation: Nighttime light INCREASED during lockdown (requires further investigation)")
    print(f"  Note: This may be due to seasonal effects, data quality, or other factors.")
