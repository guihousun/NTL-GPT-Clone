"""
Shanghai NTL Annual Growth Rate Analysis (2015-2020)
Calculates year-over-year growth rate of Total Nighttime Light (TNTL) intensity.
"""
import pandas as pd
import matplotlib.pyplot as plt
from storage_manager import storage_manager

# Resolve input path for the TNTL timeseries CSV
csv_path = storage_manager.resolve_output_path('shanghai_TNTL_timeseries.csv')

# Load the TNTL timeseries data
df = pd.read_csv(csv_path)

# Aggregate TNTL by year (sum across all regions/districts)
yearly_tntl = df.groupby('Year')['TNTL'].sum().reset_index()
yearly_tntl.columns = ['Year', 'Total_TNTL']
yearly_tntl = yearly_tntl.sort_values('Year').reset_index(drop=True)

# Calculate year-over-year growth rate (%)
# Growth Rate = (Current Year TNTL - Previous Year TNTL) / Previous Year TNTL * 100
yearly_tntl['Growth_Rate'] = yearly_tntl['Total_TNTL'].pct_change() * 100

# Export results to CSV
out_csv = storage_manager.resolve_output_path('shanghai_ntl_growth_rate.csv')
yearly_tntl.to_csv(out_csv, index=False)
print(f"Growth rate CSV saved: {out_csv}")

# Create visualization
fig, ax1 = plt.subplots(figsize=(10, 6))

# Plot Total TNTL as bar chart
ax1.bar(yearly_tntl['Year'].astype(str), yearly_tntl['Total_TNTL'], color='steelblue', alpha=0.7, label='Total TNTL')
ax1.set_xlabel('Year', fontsize=12)
ax1.set_ylabel('Total TNTL', fontsize=12, color='steelblue')
ax1.tick_params(axis='y', labelcolor='steelblue')
ax1.set_title('Shanghai NTL Intensity and Annual Growth Rate (2015-2020)', fontsize=14)

# Create secondary axis for growth rate line plot
ax2 = ax1.twinx()
ax2.plot(yearly_tntl['Year'].astype(str), yearly_tntl['Growth_Rate'], color='red', marker='o', linewidth=2, markersize=8, label='Growth Rate (%)')
ax2.set_ylabel('Growth Rate (%)', fontsize=12, color='red')
ax2.tick_params(axis='y', labelcolor='red')

# Add value labels on bars and points
for i, (tntl, gr) in enumerate(zip(yearly_tntl['Total_TNTL'], yearly_tntl['Growth_Rate'])):
    ax1.text(i, tntl, f'{tntl:,.0f}', ha='center', va='bottom', fontsize=9)
    if not pd.isna(gr):
        ax2.text(i, gr, f'{gr:.2f}%', ha='center', va='bottom', fontsize=9, color='red')

plt.tight_layout()
out_png = storage_manager.resolve_output_path('shanghai_ntl_growth_rate.png')
plt.savefig(out_png, dpi=150, bbox_inches='tight')
plt.close()
print(f"Growth rate visualization saved: {out_png}")

# Print summary
print("\n=== Shanghai NTL Annual Growth Rate Summary (2015-2020) ===")
print(yearly_tntl.to_string(index=False))