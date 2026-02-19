import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from storage_manager import storage_manager
import json

# Load damage metrics
damage_csv = storage_manager.resolve_output_path('myanmar_earthquake_2025_damage_metrics.csv')
damage_df = pd.read_csv(damage_csv)

# Load impact report for metadata
report_path = storage_manager.resolve_output_path('myanmar_earthquake_2025_impact_report.json')
with open(report_path, 'r') as f:
    impact_report = json.load(f)

earthquake_meta = impact_report['earthquake_metadata']
analysis_meta = impact_report['analysis_metadata']

# Create figure with multiple panels
fig = plt.figure(figsize=(16, 12))

# Panel 1: ANTL by Period and Buffer (bar chart)
ax1 = fig.add_subplot(2, 2, 1)
x = np.arange(len(damage_df))
width = 0.25

baseline_bars = ax1.bar(x - width, damage_df['baseline_ANTL'], width, label='Baseline', color='#2ca02c')
first_night_bars = ax1.bar(x, damage_df['first_night_ANTL'], width, label='First Night', color='#d62728')
recovery_bars = ax1.bar(x + width, damage_df['recovery_ANTL'], width, label='Recovery', color='#1f77b4')

ax1.set_xlabel('Buffer Zone')
ax1.set_ylabel('ANTL (radiance)')
ax1.set_title('ANTL by Period and Buffer Zone', fontweight='bold')
ax1.set_xticks(x)
ax1.set_xticklabels([f'{int(row)}km' for row in damage_df['buffer_km']])
ax1.legend()
ax1.grid(axis='y', alpha=0.3)

# Add value labels
for bars in [baseline_bars, first_night_bars, recovery_bars]:
    for bar in bars:
        height = bar.get_height()
        ax1.annotate(f'{height:.2f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=9)

# Panel 2: Blackout Percentage by Buffer
ax2 = fig.add_subplot(2, 2, 2)
colors = ['#d62728' if pct > 30 else '#ff7f0e' if pct > 10 else '#2ca02c' for pct in damage_df['blackout_pct']]
bars2 = ax2.bar(damage_df['buffer_km'], damage_df['blackout_pct'], color=colors, edgecolor='black')
ax2.set_xlabel('Buffer Distance from Epicenter (km)')
ax2.set_ylabel('Blackout Percentage (%)')
ax2.set_title('Power Outage Impact by Distance', fontweight='bold')
ax2.set_xticks(damage_df['buffer_km'])
ax2.grid(axis='y', alpha=0.3)

# Add threshold lines
ax2.axhline(y=30, color='red', linestyle='--', alpha=0.7, label='Severe (>30%)')
ax2.axhline(y=10, color='orange', linestyle='--', alpha=0.7, label='Moderate (>10%)')

# Add value labels
for bar, pct in zip(bars2, damage_df['blackout_pct']):
    height = bar.get_height()
    ax2.annotate(f'{pct:.1f}%',
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha='center', va='bottom', fontsize=10, fontweight='bold')

ax2.legend(loc='upper right')

# Panel 3: Recovery Ratio by Buffer
ax3 = fig.add_subplot(2, 2, 3)
colors3 = ['#2ca02c' if rr > 0.8 else '#ff7f0e' if rr > 0.5 else '#d62728' for rr in damage_df['recovery_ratio']]
bars3 = ax3.bar(damage_df['buffer_km'], damage_df['recovery_ratio'], color=colors3, edgecolor='black')
ax3.set_xlabel('Buffer Distance from Epicenter (km)')
ax3.set_ylabel('Recovery Ratio')
ax3.set_title('Power Recovery Status (Recovery Period / Baseline)', fontweight='bold')
ax3.set_xticks(damage_df['buffer_km'])
ax3.set_ylim(0, 1.2)
ax3.grid(axis='y', alpha=0.3)

# Add threshold lines
ax3.axhline(y=0.8, color='green', linestyle='--', alpha=0.7, label='Good (>80%)')
ax3.axhline(y=0.5, color='orange', linestyle='--', alpha=0.7, label='Partial (>50%)')

# Add value labels
for bar, rr in zip(bars3, damage_df['recovery_ratio']):
    height = bar.get_height()
    ax3.annotate(f'{rr:.2f}',
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha='center', va='bottom', fontsize=10, fontweight='bold')

ax3.legend(loc='upper right')

# Panel 4: Summary Statistics Table
ax4 = fig.add_subplot(2, 2, 4)
ax4.axis('off')

# Create summary text
summary_text = f"""
EARTHQUAKE IMPACT ASSESSMENT SUMMARY
{'='*60}

EVENT DETAILS:
  Event: {earthquake_meta['event_name']}
  Date: {earthquake_meta['event_date_utc']}
  Magnitude: {earthquake_meta['magnitude']} Mw | Depth: {earthquake_meta['depth_km']} km
  Epicenter: {earthquake_meta['epicenter_lat']}°N, {earthquake_meta['epicenter_lon']}°E
  Location: {earthquake_meta['epicenter_location']}

ANALYSIS PARAMETERS:
  Dataset: {analysis_meta['dataset']}
  Band: {analysis_meta['band']}
  Resolution: {analysis_meta['spatial_resolution_m']}m
  Baseline: {analysis_meta['baseline_period']}
  First Night: {analysis_meta['first_night_date']}
  Recovery: {analysis_meta['recovery_period']}

KEY FINDINGS:
  Maximum Blackout: {impact_report['summary']['max_blackout_pct']:.1f}% ({impact_report['summary']['max_blackout_buffer_km']}km buffer)
  Average Blackout: {impact_report['summary']['avg_blackout_pct']:.1f}%
  Average Recovery Ratio: {impact_report['summary']['avg_recovery_ratio']:.2f}

INTERPRETATION BY ZONE:
"""

for interp in impact_report['summary']['interpretation']:
    summary_text += f"  • {interp}\n"

summary_text += f"""
{'='*60}
Note: Negative blackout values indicate increased radiance (possibly due to
emergency lighting, rescue operations, or data variability).
"""

ax4.text(0.05, 0.95, summary_text, transform=ax4.transAxes, fontsize=10,
        verticalalignment='top', fontfamily='monospace',
        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

plt.suptitle(f'2025 Myanmar Earthquake (M{earthquake_meta["magnitude"]}) - Nighttime Light Impact Assessment', 
             fontsize=14, fontweight='bold', y=0.98)

plt.tight_layout()

# Save figure
output_png = storage_manager.resolve_output_path('myanmar_earthquake_2025_impact_maps.png')
plt.savefig(output_png, dpi=150, bbox_inches='tight')
print(f"Impact visualization saved to: {output_png}")
print("Visualization complete!")

# Also create a simple schematic map
fig2, ax = plt.subplots(1, 1, figsize=(10, 10))

# Draw buffer circles
epicenter_lon = earthquake_meta['epicenter_lon']
epicenter_lat = earthquake_meta['epicenter_lat']

for idx, row in damage_df.iterrows():
    buffer_km = row['buffer_km']
    blackout = row['blackout_pct']
    
    # Color based on severity
    if blackout > 30:
        color = '#d62728'  # Red - severe
        alpha = 0.6
    elif blackout > 10:
        color = '#ff7f0e'  # Orange - moderate
        alpha = 0.5
    else:
        color = '#2ca02c'  # Green - minimal
        alpha = 0.4
    
    circle = plt.Circle((epicenter_lon, epicenter_lat), buffer_km/111, 
                        color=color, fill=True, alpha=alpha, 
                        label=f'{buffer_km}km: {blackout:.1f}% blackout')
    ax.add_patch(circle)

# Plot epicenter
ax.plot(epicenter_lon, epicenter_lat, 'k*', markersize=20, label='Epicenter (M7.7)')

ax.set_xlabel('Longitude')
ax.set_ylabel('Latitude')
ax.set_title(f'2025 Myanmar Earthquake Impact Zones\nEpicenter: {epicenter_lat}°N, {epicenter_lon}°E', fontweight='bold')
ax.legend(loc='upper right')
ax.grid(alpha=0.3)
ax.set_aspect('equal')

# Set appropriate bounds
buffer_max = 100
ax.set_xlim(epicenter_lon - buffer_max/111 * 1.2, epicenter_lon + buffer_max/111 * 1.2)
ax.set_ylim(epicenter_lat - buffer_max/111 * 1.2, epicenter_lat + buffer_max/111 * 1.2)

plt.tight_layout()
output_schematic = storage_manager.resolve_output_path('myanmar_earthquake_2025_impact_schematic.png')
plt.savefig(output_schematic, dpi=150, bbox_inches='tight')
print(f"Impact schematic saved to: {output_schematic}")