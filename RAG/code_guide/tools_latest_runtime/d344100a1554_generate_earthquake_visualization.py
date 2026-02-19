"""
Generate visualization for 2025 Myanmar Earthquake Impact Assessment
Creates bar charts and line plots showing ANTL changes across periods and buffers.
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
from storage_manager import storage_manager

# Load the damage metrics
damage_csv = storage_manager.resolve_output_path("myanmar_earthquake_damage_metrics.csv")
df = pd.read_csv(damage_csv)

# Load the ANTL analysis
antl_csv = storage_manager.resolve_output_path("myanmar_earthquake_antl_analysis.csv")
antl_df = pd.read_csv(antl_csv)

# Create figure with subplots
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle('2025 Myanmar Earthquake Impact Assessment\nMw 7.7 - March 28, 2025 - Epicenter: 22.013°N, 95.922°E', 
             fontsize=14, fontweight='bold')

# Plot 1: ANTL by Period and Buffer (Grouped Bar Chart)
ax1 = axes[0, 0]
periods = ['pre_event_baseline', 'first_post_event_night', 'post_event_recovery']
period_labels = ['Pre-Event\nBaseline\n(Mar 14-21)', 'First Night\n(Mar 29)', 'Recovery\n(Apr 4-11)']
x = range(len(periods))
width = 0.25

for i, (_, row) in enumerate(df.iterrows()):
    buffer_km = row['buffer_km']
    antl_values = [
        row['ANTL_baseline'],
        row['ANTL_first_night'],
        row['ANTL_recovery']
    ]
    offset = (i - 1) * width  # Center the groups
    ax1.bar([p + offset for p in x], antl_values, width, label=f'{int(buffer_km)} km buffer')

ax1.set_xlabel('Period', fontsize=11)
ax1.set_ylabel('ANTL (Average Nighttime Light)', fontsize=11)
ax1.set_title('ANTL by Period and Buffer Zone', fontsize=12, fontweight='bold')
ax1.set_xticks(x)
ax1.set_xticklabels(period_labels, fontsize=9)
ax1.legend(loc='upper right')
ax1.grid(axis='y', alpha=0.3)

# Plot 2: Blackout Percentage by Buffer
ax2 = axes[0, 1]
buffers = df['buffer_km'].values
blackout_pct = df['blackout_pct'].values
colors = ['red' if pct < -20 else 'orange' if pct < 0 else 'green' for pct in blackout_pct]

bars = ax2.bar(buffers, blackout_pct, color=colors, edgecolor='black')
ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
ax2.axhline(y=-20, color='red', linestyle='--', linewidth=1, label='Severe damage threshold (-20%)')
ax2.set_xlabel('Buffer Distance from Epicenter (km)', fontsize=11)
ax2.set_ylabel('Blackout Percentage (%)', fontsize=11)
ax2.set_title('Nighttime Light Loss on First Night After Earthquake', fontsize=12, fontweight='bold')
ax2.legend(loc='lower right')
ax2.grid(axis='y', alpha=0.3)

# Add value labels on bars
for bar, pct in zip(bars, blackout_pct):
    height = bar.get_height()
    ax2.annotate(f'{pct:.1f}%',
                 xy=(bar.get_x() + bar.get_width() / 2, height),
                 xytext=(0, 3 if height >= 0 else -10),
                 textcoords="offset points",
                 ha='center', va='bottom' if height >= 0 else 'top',
                 fontsize=9)

# Plot 3: Recovery Percentage by Buffer
ax3 = axes[1, 0]
recovery_pct = df['recovery_pct'].values
colors_rec = ['green' if pct > 50 else 'orange' if pct > 0 else 'red' for pct in recovery_pct]

bars3 = ax3.bar(buffers, recovery_pct, color=colors_rec, edgecolor='black')
ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
ax3.axhline(y=50, color='green', linestyle='--', linewidth=1, label='Good recovery threshold (>50%)')
ax3.set_xlabel('Buffer Distance from Epicenter (km)', fontsize=11)
ax3.set_ylabel('Recovery Percentage (%)', fontsize=11)
ax3.set_title('Power Restoration Progress (Recovery Phase vs First Night)', fontsize=12, fontweight='bold')
ax3.legend(loc='lower right')
ax3.grid(axis='y', alpha=0.3)

# Add value labels on bars
for bar, pct in zip(bars3, recovery_pct):
    height = bar.get_height()
    ax3.annotate(f'{pct:.1f}%',
                 xy=(bar.get_x() + bar.get_width() / 2, height),
                 xytext=(0, 3 if height >= 0 else -10),
                 textcoords="offset points",
                 ha='center', va='bottom' if height >= 0 else 'top',
                 fontsize=9)

# Plot 4: ANTL Time Series Pattern
ax4 = axes[1, 1]
antl_pivot = antl_df.pivot(index='buffer_km', columns='period', values='ANTL')
period_order = ['pre_event_baseline', 'first_post_event_night', 'post_event_recovery']
x_positions = [0, 1, 2]

for buffer_km in antl_pivot.index:
    values = [antl_pivot.loc[buffer_km, p] for p in period_order]
    ax4.plot(x_positions, values, marker='o', linewidth=2, markersize=8, label=f'{int(buffer_km)} km')

ax4.set_xlabel('Period', fontsize=11)
ax4.set_ylabel('ANTL', fontsize=11)
ax4.set_title('ANTL Temporal Pattern by Buffer Zone', fontsize=12, fontweight='bold')
ax4.set_xticks(x_positions)
ax4.set_xticklabels(['Baseline', 'First Night', 'Recovery'], fontsize=10)
ax4.legend(loc='best')
ax4.grid(axis='y', alpha=0.3)

plt.tight_layout()

# Save the figure
output_png = storage_manager.resolve_output_path("myanmar_earthquake_impact_visualization.png")
plt.savefig(output_png, dpi=150, bbox_inches='tight')
print(f"Saved visualization to: {output_png}")

plt.close()
