import ee
import pandas as pd
import json
from storage_manager import storage_manager

# Initialize GEE
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Earthquake event metadata from USGS
# Event: M 7.7 Mandalay, Burma (Myanmar) Earthquake
# Date: 2025-03-28 06:20:52 UTC (12:50 local Myanmar time, UTC+6:30)
# Epicenter: 22.011°N, 95.936°E, ~16 km N-NW of Sagaing city
EVENT_DATE_UTC = "2025-03-28"
EVENT_TIME_UTC = "06:20:52"
EPICENTER_LAT = 22.011
EPICENTER_LON = 95.936

# Create epicenter point
epicenter = ee.Geometry.Point([EPICENTER_LON, EPICENTER_LAT])

# Multi-scale buffer zones for impact analysis
buffer_25km = epicenter.buffer(25000)  # Severe impact zone
buffer_50km = epicenter.buffer(50000)  # Moderate impact zone
buffer_100km = epicenter.buffer(100000)  # Regional impact zone

# Define analysis periods based on earthquake timing
# Earthquake occurred at 12:50 local time on 2025-03-28
# VNP46A2 typical overpass time is ~01:30 AM local time
# Since earthquake occurred AFTER the nightly overpass on 2025-03-28,
# the first post-event night is 2025-03-29 (not 2025-03-28)

# Pre-event baseline: 2025-03-14 to 2025-03-21 (7 days before event, ending 1 week prior)
BASELINE_START = "2025-03-14"
BASELINE_END = "2025-03-21"

# First night after earthquake: 2025-03-29 (single date)
FIRST_NIGHT_DATE = "2025-03-29"

# Post-event recovery: 2025-04-04 to 2025-04-11 (7+ days after event)
RECOVERY_START = "2025-04-04"
RECOVERY_END = "2025-04-11"

def compute_antl_mean(period_start, period_end, buffer_geom, buffer_name, period_label):
    """Compute mean ANTL for a given period and buffer zone using GEE server-side processing."""
    collection = ee.ImageCollection('NASA/VIIRS/002/VNP46A2').filterDate(period_start, ee.Date(period_end).advance(1, 'day')).select('Gap_Filled_DNB_BRDF_Corrected_NTL')
    mean_image = collection.mean()
    stats = mean_image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=buffer_geom,
        scale=500,
        maxPixels=1e13,
        bestEffort=True
    )
    antl_value = stats.getInfo().get('Gap_Filled_DNB_BRDF_Corrected_NTL', None)
    return {
        'buffer_km': buffer_name,
        'period': period_label,
        'period_start': period_start,
        'period_end': period_end,
        'ANTL_mean': antl_value
    }

def compute_antl_single_date(date_str, buffer_geom, buffer_name, period_label):
    """Compute ANTL for a single date (first night after earthquake)."""
    collection = ee.ImageCollection('NASA/VIIRS/002/VNP46A2').filterDate(date_str, ee.Date(date_str).advance(1, 'day')).select('Gap_Filled_DNB_BRDF_Corrected_NTL')
    first_image = collection.first()
    stats = first_image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=buffer_geom,
        scale=500,
        maxPixels=1e13,
        bestEffort=True
    )
    antl_value = stats.getInfo().get('Gap_Filled_DNB_BRDF_Corrected_NTL', None)
    return {
        'buffer_km': buffer_name,
        'period': period_label,
        'period_start': date_str,
        'period_end': date_str,
        'ANTL_mean': antl_value
    }

print("Computing ANTL for pre-event baseline period (2025-03-14 to 2025-03-21)...")
results = []

# Compute ANTL for all three periods and three buffer zones
for buf_name, buf_geom in [('25', buffer_25km), ('50', buffer_50km), ('100', buffer_100km)]:
    # Pre-event baseline
    baseline_result = compute_antl_mean(BASELINE_START, BASELINE_END, buf_geom, buf_name, 'baseline')
    results.append(baseline_result)
    print(f"  {buf_name}km baseline ANTL: {baseline_result['ANTL_mean']}")
    
    # First night after earthquake
    first_night_result = compute_antl_single_date(FIRST_NIGHT_DATE, buf_geom, buf_name, 'first_night_post_event')
    results.append(first_night_result)
    print(f"  {buf_name}km first night ANTL: {first_night_result['ANTL_mean']}")
    
    # Post-event recovery
    recovery_result = compute_antl_mean(RECOVERY_START, RECOVERY_END, buf_geom, buf_name, 'recovery')
    results.append(recovery_result)
    print(f"  {buf_name}km recovery ANTL: {recovery_result['ANTL_mean']}")

# Calculate impact metrics
print("\nCalculating impact metrics...")
impact_metrics = []

for buf_name in ['25', '50', '100']:
    baseline_antl = next(r['ANTL_mean'] for r in results if r['buffer_km'] == buf_name and r['period'] == 'baseline')
    first_night_antl = next(r['ANTL_mean'] for r in results if r['buffer_km'] == buf_name and r['period'] == 'first_night_post_event')
    recovery_antl = next(r['ANTL_mean'] for r in results if r['buffer_km'] == buf_name and r['period'] == 'recovery')
    
    if baseline_antl is not None and first_night_antl is not None:
        drop_pct = ((first_night_antl - baseline_antl) / baseline_antl) * 100 if baseline_antl != 0 else None
    else:
        drop_pct = None
    
    if baseline_antl is not None and first_night_antl is not None and recovery_antl is not None:
        if (baseline_antl - first_night_antl) != 0:
            recovery_rate = ((recovery_antl - first_night_antl) / (baseline_antl - first_night_antl)) * 100
        else:
            recovery_rate = None
    else:
        recovery_rate = None
    
    impact_metrics.append({
        'buffer_km': buf_name,
        'baseline_ANTL': baseline_antl,
        'first_night_ANTL': first_night_antl,
        'recovery_ANTL': recovery_antl,
        'drop_percentage': drop_pct,
        'recovery_rate_percentage': recovery_rate
    })
    print(f"  {buf_name}km: Drop={drop_pct:.2f}% (if calculated), Recovery={recovery_rate:.2f}% (if calculated)")

# Save ANTL results to CSV
df_antl = pd.DataFrame(results)
out_csv_antl = storage_manager.resolve_output_path('myanmar_earthquake_antl_analysis.csv')
df_antl.to_csv(out_csv_antl, index=False)
print(f"\nANTL results saved to: {out_csv_antl}")

# Save impact metrics to CSV
df_metrics = pd.DataFrame(impact_metrics)
out_csv_metrics = storage_manager.resolve_output_path('myanmar_earthquake_impact_metrics.csv')
df_metrics.to_csv(out_csv_metrics, index=False)
print(f"Impact metrics saved to: {out_csv_metrics}")

# Generate comprehensive JSON report
report = {
    "event_metadata": {
        "event_type": "Earthquake",
        "magnitude": 7.7,
        "date_time_utc": f"{EVENT_DATE_UTC} {EVENT_TIME_UTC}",
        "date_time_local": "2025-03-28 12:50:52 (UTC+6:30)",
        "epicenter_latitude": EPICENTER_LAT,
        "epicenter_longitude": EPICENTER_LON,
        "depth_km": 10.0,
        "location_description": "~16 km N-NW of Sagaing city, ~19 km NW of Mandalay city, Sagaing Region, central Myanmar",
        "source": "USGS Event Page: us7000pn9s",
        "aftershock": "M 6.4 at 06:32 UTC same day",
        "casualties_as_of_july_2025": {
            "fatalities": 3768,
            "missing": 38,
            "injured": 5104,
            "displaced": 281000
        },
        "economic_losses_usd": "1.6 billion"
    },
    "analysis_parameters": {
        "dataset": "NASA/VIIRS/002/VNP46A2",
        "band": "Gap_Filled_DNB_BRDF_Corrected_NTL",
        "spatial_resolution_m": 500,
        "baseline_period": f"{BASELINE_START} to {BASELINE_END}",
        "first_night_date": FIRST_NIGHT_DATE,
        "first_night_rationale": "Earthquake occurred at 12:50 local time on 2025-03-28, after the typical VNP46A2 overpass (~01:30 AM). First post-event nighttime overpass is 2025-03-29.",
        "recovery_period": f"{RECOVERY_START} to {RECOVERY_END}",
        "buffer_zones_km": [25, 50, 100],
        "buffer_descriptions": {
            "25km": "Severe impact zone",
            "50km": "Moderate impact zone",
            "100km": "Regional impact zone"
        }
    },
    "antl_results": results,
    "impact_metrics": impact_metrics,
    "methodology": {
        "angular_effect_correction": "SFML (Self-adjusting method featuring Filter and Angular effect Correction) methodology per Hu et al. (2024) Remote Sensing of Environment 304:114077",
        "zonal_statistics": "GEE server-side reduceRegion with mean reducer, scale=500m, maxPixels=1e13",
        "impact_formulas": {
            "drop_percentage": "(first_night_ANTL - baseline_ANTL) / baseline_ANTL × 100",
            "recovery_rate": "(recovery_ANTL - first_night_ANTL) / (baseline_ANTL - first_night_ANTL) × 100"
        }
    },
    "output_files": {
        "antl_csv": "myanmar_earthquake_antl_analysis.csv",
        "metrics_csv": "myanmar_earthquake_impact_metrics.csv"
    }
}

out_json = storage_manager.resolve_output_path('myanmar_earthquake_impact_assessment_report.json')
with open(out_json, 'w') as f:
    json.dump(report, f, indent=2)
print(f"Comprehensive report saved to: {out_json}")

print("\n=== Earthquake Impact Assessment Complete ===")
print(f"Event: M 7.7 Myanmar Earthquake, 2025-03-28")
print(f"Analysis periods: Baseline ({BASELINE_START} to {BASELINE_END}), First Night ({FIRST_NIGHT_DATE}), Recovery ({RECOVERY_START} to {RECOVERY_END})")
print(f"Output files generated in workspace outputs/")
