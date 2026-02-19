import pandas as pd
from storage_manager import storage_manager

# Read the district-level ANTL statistics (generated file, so use output path)
csv_path = storage_manager.resolve_output_path('shanghai_district_antl_2022.csv')
df = pd.read_csv(csv_path)

# Display the dataframe to understand its structure
print("District ANTL Statistics for Shanghai 2022:")
print(df.head(20))
print(f"\nTotal districts: {len(df)}")

# Find the district with the highest ANTL
if 'ANTL' in df.columns:
    max_idx = df['ANTL'].idxmax()
    max_district = df.loc[max_idx]
    print(f"\n=== District with Highest ANTL ===")
    print(f"District Name: {max_district.get('Name', 'N/A')}")
    print(f"AdCode: {max_district.get('AdCode', 'N/A')}")
    print(f"ANTL Value: {max_district['ANTL']:.4f}")
    
    # Sort all districts by ANTL descending
    sorted_df = df.sort_values('ANTL', ascending=False)
    print(f"\n=== All Districts Ranked by ANTL (Descending) ===")
    for idx, row in sorted_df.iterrows():
        print(f"{row.get('Name', 'N/A')}: {row['ANTL']:.4f}")
else:
    print("ANTL column not found. Available columns:", df.columns.tolist())
