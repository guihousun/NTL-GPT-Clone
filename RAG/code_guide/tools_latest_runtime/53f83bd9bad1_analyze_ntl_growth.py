import pandas as pd
from storage_manager import storage_manager

# Read the statistics CSV from outputs
stats_csv_path = storage_manager.resolve_output_path('shanghai_district_ntl_stats.csv')
df = pd.read_csv(stats_csv_path)

print("Original data shape:", df.shape)
print("Columns:", df.columns.tolist())
print("\nAll data:")
print(df.to_string())

# Filter out global summary rows (rows where Region might be 'Global' or similar)
# Based on the output, row 16 and 33 appear to be global summaries
# Let's check unique Region values
print("\nUnique Region values:", df['Region'].unique())

# Filter to keep only district-level data (exclude global summaries)
# The global summary rows likely have a special Region value or are the last row per year
# Let's filter by checking if the row has a valid district name
district_df = df[df['Region'] != 'Global'].copy()

# Actually, looking at the data more carefully, the global summary might have a different pattern
# Let's check the row count per year
print("\nRows per Year:")
print(df.groupby('Year').size())

# Filter out rows that appear to be global summaries (ANTL around 12-13 which is much lower than districts)
# District ANTL values are typically > 1, while global might be different
# Let's keep rows where ANTL > 1 (districts typically have higher ANTL than global average in this context)
# Actually, looking at the data: row 15 has ANTL 1.6418, row 16 has ANTL 12.8280 (global)
# The global row seems to have a specific pattern

# Let's identify global rows by checking if Region is empty or has a special value
# From the output, it seems rows 16 and 33 (index) are global summaries
# Let's filter by excluding rows where the Region might indicate global

# A safer approach: keep only rows where we have exactly 17 rows per year (16 districts + 1 global)
# and exclude the one with the lowest or highest ANTL that doesn't match district pattern

# Let's pivot the data first and see what we get
pivot_df = df.pivot_table(index='Region', columns='Year', values='ANTL', aggfunc='first')
print("\nPivot table (ANTL by Region and Year):")
print(pivot_df)

# Check for NaN values which might indicate global summary rows
print("\nRows with NaN in either year:")
print(pivot_df[pivot_df.isna().any(axis=1)])

# Remove rows with NaN (these are likely global summaries that don't have both years)
pivot_df = pivot_df.dropna()
print("\nCleaned pivot table:")
print(pivot_df)

# Calculate growth rate
pivot_df['Growth_Rate'] = (pivot_df[2020] - pivot_df[2019]) / pivot_df[2019] * 100
print("\nWith Growth Rate:")
print(pivot_df.sort_values('Growth_Rate', ascending=False))

# Find the district with highest growth rate
max_growth_district = pivot_df['Growth_Rate'].idxmax()
max_growth_rate = pivot_df.loc[max_growth_district, 'Growth_Rate']

print("\n" + "="*60)
print(f"District with highest NTL growth rate (2019-2020): {max_growth_district}")
print(f"Growth rate: {max_growth_rate:.2f}%")
print(f"ANTL 2019: {pivot_df.loc[max_growth_district, 2019]:.4f}")
print(f"ANTL 2020: {pivot_df.loc[max_growth_district, 2020]:.4f}")
print("="*60)

# Save results to CSV
result_df = pivot_df.reset_index()
result_df['Growth_Rate'] = (result_df[2020] - result_df[2019]) / result_df[2019] * 100
result_df = result_df.rename(columns={2019: 'ANTL_2019', 2020: 'ANTL_2020'})
result_df = result_df.sort_values('Growth_Rate', ascending=False)

output_csv = storage_manager.resolve_output_path('shanghai_district_ntl_growth_rates.csv')
result_df.to_csv(output_csv, index=False)
print(f"\nResults saved to: {output_csv}")
