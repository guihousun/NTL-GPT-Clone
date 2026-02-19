import pandas as pd
from storage_manager import storage_manager

# Read the district-level ANTL statistics (generated file, so use output path)
csv_path = storage_manager.resolve_output_path('shanghai_district_antl_2022.csv')
df = pd.read_csv(csv_path)

# Filter out the Global_Summary row to get only district data
districts_df = df[df['Region'] != 'Global_Summary'].copy()

# Display the dataframe
print("District ANTL Statistics for Shanghai 2022:")
print(districts_df)
print(f"\nTotal districts: {len(districts_df)}")

# Find the district with the highest ANTL
if 'ANTL' in districts_df.columns:
    max_idx = districts_df['ANTL'].idxmax()
    max_district = districts_df.loc[max_idx]
    print(f"\n=== District with Highest ANTL ===")
    print(f"District Name (Region): {max_district['Region']}")
    print(f"ANTL Value: {max_district['ANTL']:.4f}")
    
    # Sort all districts by ANTL descending
    sorted_df = districts_df.sort_values('ANTL', ascending=False)
    print(f"\n=== All Districts Ranked by ANTL (Descending) ===")
    for idx, row in sorted_df.iterrows():
        print(f"{row['Region']}: {row['ANTL']:.4f}")
    
    # Save the ranking to a CSV file
    output_path = storage_manager.resolve_output_path('shanghai_district_antl_ranking_2022.csv')
    sorted_df.to_csv(output_path, index=False)
    print(f"\nRanking saved to: {output_path}")
else:
    print("ANTL column not found. Available columns:", districts_df.columns.tolist())
