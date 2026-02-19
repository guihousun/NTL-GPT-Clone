from storage_manager import storage_manager
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Read TNTL time series
csv_path = storage_manager.resolve_output_path('shanghai_tntl_timeseries.csv')
df = pd.read_csv(csv_path)

# Sort by year to ensure correct order
df = df.sort_values('Year').reset_index(drop=True)

# Get beginning and ending values for CAGR calculation (2015 to 2020)
beginning_value = df.loc[df['Year'] == 2015, 'TNTL'].values[0]
ending_value = df.loc[df['Year'] == 2020, 'TNTL'].values[0]
n_years = 2020 - 2015

# Calculate CAGR
cagr = (ending_value / beginning_value) ** (1 / n_years) - 1
cagr_percent = cagr * 100

# Create results dataframe
results = {
    'Study_Area': ['Shanghai'],
    'Period': ['2015-2020'],
    'Beginning_TNTL_2015': [beginning_value],
    'Ending_TNTL_2020': [ending_value],
    'Number_of_Years': [n_years],
    'CAGR': [cagr],
    'CAGR_Percent': [cagr_percent]
}
results_df = pd.DataFrame(results)

# Save CAGR results to CSV
output_csv_path = storage_manager.resolve_output_path('shanghai_cagr_2015_2020.csv')
results_df.to_csv(output_csv_path, index=False)
print(f"CAGR results saved to: {output_csv_path}")

# Create visualization
fig, ax = plt.subplots(figsize=(10, 6))

# Plot TNTL time series
ax.plot(df['Year'], df['TNTL'], marker='o', linewidth=2, markersize=8, color='#2E86AB', label='TNTL')

# Add trend line based on CAGR
trend_values = [beginning_value * (1 + cagr) ** (year - 2015) for year in df['Year']]
ax.plot(df['Year'], trend_values, linestyle='--', linewidth=2, color='#A23B72', label=f'CAGR Trend ({cagr_percent:.2f}%)')

# Fill area under the curve
ax.fill_between(df['Year'], df['TNTL'], alpha=0.3, color='#2E86AB')

# Add annotations for each year
for i, row in df.iterrows():
    ax.annotate(f"{row['TNTL']:.0f}", 
                (row['Year'], row['TNTL']), 
                textcoords="offset points", 
                xytext=(0, 10), 
                ha='center',
                fontsize=9)

# Add CAGR annotation
ax.text(0.02, 0.98, f'CAGR (2015-2020): {cagr_percent:.4f}%', 
        transform=ax.transAxes, 
        fontsize=14, 
        fontweight='bold',
        verticalalignment='top',
        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

# Labels and title
ax.set_xlabel('Year', fontsize=12)
ax.set_ylabel('Total NTL Intensity (TNTL)', fontsize=12)
ax.set_title('Shanghai Total NTL Intensity and CAGR (2015-2020)', fontsize=14, fontweight='bold')
ax.legend(loc='upper left')
ax.grid(True, alpha=0.3)

# Save figure
output_png_path = storage_manager.resolve_output_path('shanghai_tntl_cagr_2015_2020.png')
plt.tight_layout()
plt.savefig(output_png_path, dpi=150, bbox_inches='tight')
print(f"Visualization saved to: {output_png_path}")

print("\n=== CAGR Analysis Summary ===")
print(f"Study Area: Shanghai")
print(f"Period: 2015-2020")
print(f"Beginning TNTL (2015): {beginning_value:.2f}")
print(f"Ending TNTL (2020): {ending_value:.2f}")
print(f"Number of Years: {n_years}")
print(f"CAGR: {cagr:.6f}")
print(f"CAGR (%): {cagr_percent:.4f}%")