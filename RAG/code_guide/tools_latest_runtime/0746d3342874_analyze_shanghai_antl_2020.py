"""
Analyze ANTL (Annual Nighttime Light) statistics for Shanghai districts, 2020.
Reads the zonal statistics CSV from outputs folder and produces a summary report.
"""
from storage_manager import storage_manager
import pandas as pd
import os

# The NTL_raster_statistics tool saves to outputs folder
# Try outputs first, then inputs as fallback
csv_path_outputs = storage_manager.resolve_output_path('shanghai_2020_district_stats.csv')
csv_path_inputs = storage_manager.resolve_input_path('shanghai_2020_district_stats.csv')

if os.path.exists(csv_path_outputs):
    csv_path = csv_path_outputs
    print(f"Reading from outputs: {csv_path}")
elif os.path.exists(csv_path_inputs):
    csv_path = csv_path_inputs
    print(f"Reading from inputs: {csv_path}")
else:
    raise FileNotFoundError(f"CSV file not found in either outputs or inputs folder")

# Read the statistics CSV
df = pd.read_csv(csv_path)

# Display all districts with their ANTL values
print("=" * 60)
print("SHANGHAI DISTRICT ANTL STATISTICS - 2020")
print("=" * 60)
print("\nPer-District ANTL (Annual Nighttime Light) Values:")
print("-" * 60)

# Sort by ANTL descending to show brightest districts first
df_sorted = df.sort_values('ANTL', ascending=False)

for idx, row in df_sorted.iterrows():
    district_name = row.get('Name', row.get('Region', 'Unknown'))
    antl_value = row['ANTL']
    tnl_value = row.get('TNL', 'N/A')
    print(f"{district_name:20s}: ANTL = {antl_value:10.4f}, TNL = {tnl_value}")

print("-" * 60)
print(f"\nTotal districts analyzed: {len(df)}")

# Summary statistics
print("\nSummary Statistics:")
print(f"  Brightest district: {df_sorted.iloc[0].get('Name', df_sorted.iloc[0].get('Region', 'Unknown'))} (ANTL = {df_sorted['ANTL'].max():.4f})")
print(f"  Dimmest district:   {df_sorted.iloc[-1].get('Name', df_sorted.iloc[-1].get('Region', 'Unknown'))} (ANTL = {df_sorted['ANTL'].min():.4f})")
print(f"  Mean ANTL:          {df['ANTL'].mean():.4f}")
print(f"  Std Dev ANTL:       {df['ANTL'].std():.4f}")

# Top 5 brightest districts
print("\nTop 5 Brightest Districts:")
top5 = df_sorted.head(5)
for i, (_, row) in enumerate(top5.iterrows(), 1):
    name = row.get('Name', row.get('Region', 'Unknown'))
    print(f"  {i}. {name}: ANTL = {row['ANTL']:.4f}")

print("\n" + "=" * 60)
print("Analysis complete. Results saved to outputs/")
print("=" * 60)
