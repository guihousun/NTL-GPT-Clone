"""
Myanmar Earthquake 2025 - ANTL Time Series Visualization
Generate PNG plot showing daily ANTL with earthquake event marked.
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from storage_manager import storage_manager

# Load daily ANTL data
daily_csv = storage_manager.resolve_output_path('myanmar_earthquake_2025_antlr_daily.csv')
df = pd.read_csv(daily_csv)
df['date'] = pd.to_datetime(df['date'])

# Earthquake date
eq_date = pd.to_datetime('2025-03-28')

# Create figure
fig, ax = plt.subplots(figsize=(14, 7))

# Plot daily ANTL
ax.plot(df['date'], df['antlr'], 'b-o', linewidth=1.5, markersize=4, label='Daily ANTL', alpha=0.7)

# Highlight periods
pre_event = df[df['date'] < eq_date]
event_night = df[df['date'] == eq_date]
post_event = df[df['date'] > eq_date]

ax.fill_between(pre_event['date'], pre_event['antlr'], alpha=0.3, color='green', label='Pre-event (Mar 1-27)')
ax.fill_between(post_event['date'], post_event['antlr'], alpha=0.3, color='orange', label='Post-event (Mar 29-Apr 30)')

# Mark earthquake date
ax.axvline(x=eq_date, color='red', linestyle='--', linewidth=2, label='Earthquake (Mar 28, 2025, M7.7)')

# Mark event night point
if len(event_night) > 0:
    ax.scatter(event_night['date'], event_night['antlr'], color='red', s=150, zorder=5, 
               label=f'Event Night ANTL: {event_night["antlr"].values[0]:.4f}', edgecolors='black')

# Compute and show pre/post means
pre_mean = pre_event['antlr'].mean()
post_mean = post_event['antlr'].mean()

ax.axhline(y=pre_mean, color='green', linestyle=':', linewidth=2, alpha=0.7, 
           label=f'Pre-event mean: {pre_mean:.4f}')
ax.axhline(y=post_mean, color='orange', linestyle=':', linewidth=2, alpha=0.7,
           label=f'Post-event mean: {post_mean:.4f}')

# Formatting
ax.set_xlabel('Date', fontsize=12)
ax.set_ylabel('Average Nighttime Light (ANTL)', fontsize=12)
ax.set_title('Myanmar Earthquake 2025 - Daily ANTL Time Series\nNASA/VIIRS/002/VNP46A2 (Gap-Filled DNB BRDF-Corrected NTL)', fontsize=14)
ax.legend(loc='upper left', fontsize=10)
ax.grid(True, alpha=0.3)

# Format x-axis dates
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
plt.xticks(rotation=45)

# Add text box with key metrics
textstr = f'Earthquake: Mar 28, 2025, M7.7\nEpicenter: 22.013°N, 95.922°E\nPre-event mean: {pre_mean:.4f}\nEvent night: {event_night["antlr"].values[0]:.4f} (if available)\nPost-event mean: {post_mean:.4f}\nChange: {((post_mean - pre_mean) / pre_mean * 100):.1f}%'
props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
ax.text(0.98, 0.02, textstr, transform=ax.transAxes, fontsize=9,
        verticalalignment='bottom', horizontalalignment='right', bbox=props)

plt.tight_layout()

# Save figure
out_png = storage_manager.resolve_output_path('myanmar_earthquake_2025_antlr_timeseries.png')
plt.savefig(out_png, dpi=150, bbox_inches='tight')
print(f"Time series plot saved: {out_png}")

# Also create a zoomed view around the earthquake date
fig2, ax2 = plt.subplots(figsize=(12, 6))

# Focus on Mar 20 - Apr 10
zoom_df = df[(df['date'] >= '2025-03-20') & (df['date'] <= '2025-04-10')]
ax2.plot(zoom_df['date'], zoom_df['antlr'], 'b-o', linewidth=2, markersize=6, label='Daily ANTL')
ax2.axvline(x=eq_date, color='red', linestyle='--', linewidth=2, label='Earthquake (Mar 28)')

if len(event_night) > 0:
    ax2.scatter(event_night['date'], event_night['antlr'], color='red', s=200, zorder=5, 
                edgecolors='black', linewidth=2)

ax2.set_xlabel('Date', fontsize=12)
ax2.set_ylabel('ANTL', fontsize=12)
ax2.set_title('Myanmar Earthquake 2025 - ANTL Around Event Date (Zoomed)', fontsize=13)
ax2.legend(loc='upper left')
ax2.grid(True, alpha=0.3)
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
plt.xticks(rotation=45)

out_zoom_png = storage_manager.resolve_output_path('myanmar_earthquake_2025_antlr_zoomed.png')
plt.savefig(out_zoom_png, dpi=150, bbox_inches='tight')
print(f"Zoomed plot saved: {out_zoom_png}")

print("\n=== Visualization Complete ===")