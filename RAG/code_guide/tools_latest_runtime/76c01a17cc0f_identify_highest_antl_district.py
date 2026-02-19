import pandas as pd
from storage_manager import storage_manager

# Read the statistics CSV (generated in outputs/)
csv_path = storage_manager.resolve_output_path('shanghai_2022_district_stats.csv')
df = pd.read_csv(csv_path)

# Display all districts with their ANTL values
print("All Shanghai districts with ANTL values (2022):")
print(df)
print()

# Filter out the Global_Summary row to get only districts
districts_df = df[df['Region'] != 'Global_Summary'].copy()

# Find the district with highest ANTL
max_idx = districts_df['ANTL'].idxmax()
highest_district = districts_df.loc[max_idx]

print("=" * 60)
print("DISTRICT WITH HIGHEST ANTL IN SHANGHAI (2022)")
print("=" * 60)
print(f"District Name: {highest_district['Region']}")
print(f"ANTL Value: {highest_district['ANTL']:.4f}")
print("=" * 60)

# Rank all districts by ANTL (descending)
ranked_df = districts_df.sort_values('ANTL', ascending=False).reset_index(drop=True)
ranked_df['Rank'] = ranked_df.index + 1

print("\nRanked districts by ANTL (highest to lowest):")
print(ranked_df[['Rank', 'Region', 'ANTL']].to_string(index=False))

# Save the ranked results
output_csv = storage_manager.resolve_output_path('shanghai_2022_districts_ranked.csv')
ranked_df.to_csv(output_csv, index=False)
print(f"\nRanked results saved to: {output_csv}")
