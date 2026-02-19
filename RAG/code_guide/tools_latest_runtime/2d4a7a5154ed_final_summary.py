import pandas as pd
import json
from storage_manager import storage_manager

# Load and display all outputs
print("="*80)
print("2025 MYANMAR EARTHQUAKE IMPACT ASSESSMENT - FINAL SUMMARY")
print("="*80)

# Load damage metrics
damage_csv = storage_manager.resolve_output_path('myanmar_earthquake_2025_damage_metrics.csv')
damage_df = pd.read_csv(damage_csv)

# Load impact report
report_path = storage_manager.resolve_output_path('myanmar_earthquake_2025_impact_report.json')
with open(report_path, 'r') as f:
    impact_report = json.load(f)

print("\n" + "="*80)
print("EARTHQUAKE EVENT DETAILS (from USGS/British Geological Survey)")
print("="*80)
meta = impact_report['earthquake_metadata']
print(f"Event: {meta['event_name']}")
print(f"Date/Time UTC: {meta['event_date_utc']}")
print(f"Date/Time Local: {meta['event_date_local']}")
print(f"Magnitude: {meta['magnitude']} Mw")
print(f"Depth: {meta['depth_km']} km")
print(f"Epicenter: {meta['epicenter_lat']}°N, {meta['epicenter_lon']}°E")
print(f"Location: {meta['epicenter_location']}")
print(f"Source: {meta['source']}")

print("\n" + "="*80)
print("ANALYSIS METHODOLOGY")
print("="*80)
analysis = impact_report['analysis_metadata']
print(f"Dataset: {analysis['dataset']}")
print(f"Band: {analysis['band']}")
print(f"Spatial Resolution: {analysis['spatial_resolution_m']}m")
print(f"Baseline Period: {analysis['baseline_period']}")
print(f"First Night: {analysis['first_night_date']}")
print(f"Recovery Period: {analysis['recovery_period']}")
print(f"\nFirst-Night Rule Applied: {analysis['first_night_rule']}")

print("\n" + "="*80)
print("DAMAGE ASSESSMENT RESULTS (ANTL Zonal Statistics)")
print("="*80)
print(f"\n{'Buffer':<15} {'Baseline':<12} {'First Night':<14} {'Recovery':<12} {'Blackout':<12} {'Recovery':<12}")
print(f"{'Zone':<15} {'ANTL':<12} {'ANTL':<14} {'ANTL':<12} {'(%)':<12} {'Ratio':<12}")
print("-"*80)

for _, row in damage_df.iterrows():
    print(f"{int(row['buffer_km'])}km buffer     {row['baseline_ANTL']:<12.4f} {row['first_night_ANTL']:<14.4f} {row['recovery_ANTL']:<12.4f} {row['blackout_pct']:<12.1f} {row['recovery_ratio']:<12.2f}")

print("\n" + "="*80)
print("KEY FINDINGS")
print("="*80)
summary = impact_report['summary']
print(f"\nMaximum Blackout: {summary['max_blackout_pct']:.1f}% (at {summary['max_blackout_buffer_km']}km from epicenter)")
print(f"Average Blackout: {summary['avg_blackout_pct']:.1f}%")
print(f"Average Recovery Ratio: {summary['avg_recovery_ratio']:.2f}")

print("\n" + "="*80)
print("IMPACT INTERPRETATION BY ZONE")
print("="*80)
for interp in summary['interpretation']:
    print(f"  • {interp}")

print("\n" + "="*80)
print("GENERATED OUTPUT FILES")
print("="*80)
print(f"  1. epicenter_buffers.geojson - 25/50/100 km buffer zones around epicenter")
print(f"  2. myanmar_earthquake_2025_antl_zonal_stats.csv - Raw ANTL zonal statistics")
print(f"  3. myanmar_earthquake_2025_damage_metrics.csv - Computed damage metrics")
print(f"  4. myanmar_earthquake_2025_impact_report.json - Structured impact report (JSON)")
print(f"  5. myanmar_earthquake_2025_impact_maps.png - Multi-panel visualization")
print(f"  6. myanmar_earthquake_2025_impact_schematic.png - Impact zone schematic map")

print("\n" + "="*80)
print("NOTES")
print("="*80)
print("""
• The 25km buffer zone shows SEVERE impact (40.9% blackout), indicating significant
  power infrastructure damage closest to the epicenter.

• The 50km and 100km zones show minimal to negative blackout values, which may indicate:
  - Less direct damage at these distances
  - Possible emergency lighting/rescue operations increasing nighttime radiance
  - Natural variability in daily VNP46A2 data

• Recovery ratios of 0.77-0.82 indicate PARTIAL TO GOOD RECOVERY (77-82% of baseline
  levels) within 1-2 weeks after the earthquake.

• The first-night rule was applied: Since the earthquake occurred at 12:50 local time
  (after the ~01:30 nightly overpass), the first post-event night is March 29, 2025
  (day D+1), not March 28.

• Analysis used NASA VNP46A2 daily NTL product (Gap_Filled_DNB_BRDF_Corrected_NTL band)
  at 500m resolution, processed via Google Earth Engine server-side API.
""")

print("="*80)
print("ASSESSMENT COMPLETE")
print("="*80)