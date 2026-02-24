"""
Calculate annual growth rates of TNTL for Shanghai 2015-2020.
Using TNTL values from NTL_raster_statistics tool output.
"""
import pandas as pd
from storage_manager import storage_manager

# TNTL values from NTL_raster_statistics tool (already calculated)
# These are the sum of all valid pixel values within Shanghai boundary
tntl_data = {
    'year': [2015, 2016, 2017, 2018, 2019, 2020],
    'raster': [
        'shanghai_ntl__2015.tif',
        'shanghai_ntl_2016.tif',
        'shanghai_ntl__2017.tif',
        'shanghai_ntl__2018.tif',
        'shanghai_ntl__2019.tif',
        'shanghai_ntl_2020.tif'
    ],
    'TNTL': [
        433567.7500,
        430738.9688,
        473814.6562,
        477377.5000,
        479897.3438,
        490075.2812
    ]
}

# Create DataFrame
df = pd.DataFrame(tntl_data)

print("TNTL values for Shanghai 2015-2020:")
print(df)

# Calculate year-over-year growth rates
df['TNTL_Absolute_Change'] = df['TNTL'].diff()
df['TNTL_Growth_Rate'] = df['TNTL'].pct_change() * 100

# Calculate CAGR for the entire period (2015-2020)
n_years = len(df) - 1
if n_years > 0:
    CAGR = ((df['TNTL'].iloc[-1] / df['TNTL'].iloc[0]) ** (1/n_years) - 1) * 100
    print(f"\nCAGR (2015-2020): {CAGR:.4f}%")

# Save results to CSV
output_csv = storage_manager.resolve_output_path('shanghai_tntl_growth_rates_final.csv')
df.to_csv(output_csv, index=False)
print(f"\nResults saved to: {output_csv}")

# Print formatted summary table
print("\n" + "="*80)
print("ANNUAL TNTL GROWTH RATES FOR SHANGHAI (2015-2020)")
print("="*80)
for idx, row in df.iterrows():
    year = int(row['year'])
    tntl = row['TNTL']
    change = row['TNTL_Absolute_Change']
    rate = row['TNTL_Growth_Rate']
    
    if pd.isna(change):
        print(f"{year}: TNTL = {tntl:,.2f}, Growth Rate = N/A (baseline year)")
    else:
        sign = "+" if change > 0 else ""
        rate_sign = "+" if rate > 0 else ""
        print(f"{year}: TNTL = {tntl:,.2f}, Change = {sign}{change:,.2f}, Growth Rate = {rate_sign}{rate:.4f}%")
print("="*80)
