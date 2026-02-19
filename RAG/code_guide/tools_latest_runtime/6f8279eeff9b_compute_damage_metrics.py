import pandas as pd
import json
from storage_manager import storage_manager

# Load zonal statistics
stats_csv = storage_manager.resolve_output_path('myanmar_earthquake_2025_antl_zonal_stats.csv')
df = pd.read_csv(stats_csv)

print("Loaded zonal statistics:")
print(df.to_string())

# Pivot data to have periods as columns
pivot_df = df.pivot(index=['buffer_id', 'buffer_km'], columns='period', values='mean_ANTL')
print("\nPivoted data:")
print(pivot_df.to_string())

# Compute damage metrics for each buffer
damage_metrics = []

for idx, row in pivot_df.iterrows():
    buffer_id = idx[0]
    buffer_km = idx[1]
    
    baseline_antl = row.get('baseline', 0)
    first_night_antl = row.get('first_night', 0)
    recovery_antl = row.get('recovery', 0)
    
    # Avoid division by zero
    if baseline_antl > 0:
        blackout_pct = (baseline_antl - first_night_antl) / baseline_antl * 100
        recovery_ratio = recovery_antl / baseline_antl
    else:
        blackout_pct = 0
        recovery_ratio = 0
    
    radiance_drop = baseline_antl - first_night_antl
    
    # Recovery rate: how much of the lost light was recovered
    if radiance_drop != 0:
        recovery_rate = (recovery_antl - first_night_antl) / radiance_drop * 100
    else:
        recovery_rate = 0
    
    damage_metrics.append({
        'buffer_id': buffer_id,
        'buffer_km': buffer_km,
        'baseline_ANTL': baseline_antl,
        'first_night_ANTL': first_night_antl,
        'recovery_ANTL': recovery_antl,
        'blackout_pct': blackout_pct,
        'radiance_drop': radiance_drop,
        'recovery_rate': recovery_rate,
        'recovery_ratio': recovery_ratio
    })

damage_df = pd.DataFrame(damage_metrics)
damage_df = damage_df.sort_values('buffer_km')

print("\nDamage Assessment Metrics:")
print(damage_df.to_string())

# Save damage metrics to CSV
damage_csv = storage_manager.resolve_output_path('myanmar_earthquake_2025_damage_metrics.csv')
damage_df.to_csv(damage_csv, index=False)
print(f"\nDamage metrics saved to: {damage_csv}")

# Generate structured impact report
earthquake_metadata = {
    'event_name': '2025 Myanmar Earthquake',
    'event_date_utc': '2025-03-28T06:20:00Z',
    'event_date_local': '2025-03-28T12:50:00+06:30',
    'magnitude': 7.7,
    'depth_km': 10,
    'epicenter_lat': 22.013,
    'epicenter_lon': 95.922,
    'epicenter_location': 'Sagaing Region, Myanmar (15-19 km NW of Mandalay)',
    'source': 'USGS/British Geological Survey'
}

analysis_metadata = {
    'dataset': 'NASA/VIIRS/002/VNP46A2',
    'band': 'Gap_Filled_DNB_BRDF_Corrected_NTL',
    'spatial_resolution_m': 500,
    'baseline_period': '2025-03-14 to 2025-03-21 (8 days)',
    'first_night_date': '2025-03-29',
    'recovery_period': '2025-04-04 to 2025-04-11 (8 days)',
    'first_night_rule': 'Event occurred at 12:50 local time (after ~01:30 nightly overpass), so first post-event night = day D+1 (March 29)'
}

# Create impact summary
impact_summary = {
    'earthquake_metadata': earthquake_metadata,
    'analysis_metadata': analysis_metadata,
    'damage_assessment': damage_df.to_dict(orient='records'),
    'summary': {
        'max_blackout_pct': float(damage_df['blackout_pct'].max()),
        'max_blackout_buffer_km': int(damage_df.loc[damage_df['blackout_pct'].idxmax(), 'buffer_km']),
        'avg_blackout_pct': float(damage_df['blackout_pct'].mean()),
        'avg_recovery_ratio': float(damage_df['recovery_ratio'].mean()),
        'interpretation': []
    }
}

# Add interpretation
for _, row in damage_df.iterrows():
    if row['blackout_pct'] > 30:
        severity = "SEVERE"
    elif row['blackout_pct'] > 10:
        severity = "MODERATE"
    else:
        severity = "MINIMAL"
    
    if row['recovery_ratio'] > 0.8:
        recovery_status = "GOOD RECOVERY"
    elif row['recovery_ratio'] > 0.5:
        recovery_status = "PARTIAL RECOVERY"
    else:
        recovery_status = "POOR RECOVERY"
    
    impact_summary['summary']['interpretation'].append(
        f"{row['buffer_km']}km buffer: {severity} impact (blackout: {row['blackout_pct']:.1f}%), {recovery_status} (recovery ratio: {row['recovery_ratio']:.2f})"
    )

# Save impact report
report_path = storage_manager.resolve_output_path('myanmar_earthquake_2025_impact_report.json')
with open(report_path, 'w') as f:
    json.dump(impact_summary, f, indent=2)
print(f"Impact report saved to: {report_path}")

print("\n" + "="*80)
print("EARTHQUAKE IMPACT ASSESSMENT SUMMARY")
print("="*80)
print(f"\nEvent: {earthquake_metadata['event_name']}")
print(f"Magnitude: {earthquake_metadata['magnitude']} Mw | Depth: {earthquake_metadata['depth_km']} km")
print(f"Epicenter: {earthquake_metadata['epicenter_lat']}°N, {earthquake_metadata['epicenter_lon']}°E")
print(f"\nAnalysis Periods:")
print(f"  - Baseline: {analysis_metadata['baseline_period']}")
print(f"  - First Night: {analysis_metadata['first_night_date']}")
print(f"  - Recovery: {analysis_metadata['recovery_period']}")
print(f"\nDamage Assessment by Buffer Zone:")
for _, row in damage_df.iterrows():
    print(f"\n  {row['buffer_km']}km buffer:")
    print(f"    Baseline ANTL: {row['baseline_ANTL']:.4f}")
    print(f"    First Night ANTL: {row['first_night_ANTL']:.4f}")
    print(f"    Recovery ANTL: {row['recovery_ANTL']:.4f}")
    print(f"    Blackout: {row['blackout_pct']:.1f}%")
    print(f"    Radiance Drop: {row['radiance_drop']:.4f}")
    print(f"    Recovery Rate: {row['recovery_rate']:.1f}%")
    print(f"    Recovery Ratio: {row['recovery_ratio']:.2f}")

print("\n" + "="*80)