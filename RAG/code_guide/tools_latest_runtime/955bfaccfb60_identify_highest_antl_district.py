import pandas as pd
import matplotlib.pyplot as plt
from storage_manager import storage_manager

# Read the district ANTL statistics CSV
# The NTL_raster_statistics tool saved this to outputs folder
csv_path = storage_manager.resolve_output_path('shanghai_district_antl_2022.csv')
df = pd.read_csv(csv_path)

# Display the dataframe to understand its structure
print("CSV Columns:", df.columns.tolist())
print("\nFirst few rows:")
print(df.head())

# Filter out any global summary rows if present
# The district-level data should have actual district names
district_df = df.copy()

# Find the district with highest ANTL
if 'ANTL' in district_df.columns:
    max_idx = district_df['ANTL'].idxmax()
    highest_district = district_df.loc[max_idx]
    
    print("\n" + "="*60)
    print("DISTRICT WITH HIGHEST ANTL IN SHANGHAI (2022)")
    print("="*60)
    print(f"District Name: {highest_district.iloc[0]}")
    print(f"ANTL Value: {highest_district['ANTL']:.4f}")
    print("="*60)
    
    # Sort districts by ANTL for ranking
    district_sorted = district_df.sort_values('ANTL', ascending=True)
    
    # Create visualization
    plt.figure(figsize=(10, 8))
    colors = plt.cm.YlOrRd(range(len(district_sorted)))
    # Highlight the highest district
    colors[-1] = [0.8, 0.2, 0.2, 1]  # Red for highest
    
    bars = plt.barh(district_sorted.iloc[:, 0], district_sorted['ANTL'], color=colors)
    plt.xlabel('Average Nighttime Light (ANTL)', fontsize=12)
    plt.title('Shanghai District ANTL Ranking (2022 NPP-VIIRS-like)', fontsize=14, fontweight='bold')
    plt.gca().invert_yaxis()  # Highest at top
    plt.tight_layout()
    
    # Save the visualization
    output_png = storage_manager.resolve_output_path('shanghai_district_antl_ranking_2022.png')
    plt.savefig(output_png, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"\nVisualization saved to: {output_png}")
    
    # Save ranking CSV
    output_csv = storage_manager.resolve_output_path('shanghai_district_antl_ranking_2022.csv')
    district_sorted.to_csv(output_csv, index=False)
    print(f"Ranking CSV saved to: {output_csv}")
    
    # Print full ranking
    print("\nFull District ANTL Ranking (2022):")
    print("-" * 40)
    for i, (idx, row) in enumerate(district_sorted.iterrows(), 1):
        district_name = row.iloc[0]
        antl_value = row['ANTL']
        marker = " <-- HIGHEST" if i == len(district_sorted) else ""
        print(f"{i:2d}. {district_name}: {antl_value:.4f}{marker}")
    
else:
    print("Error: ANTL column not found in CSV")
    print("Available columns:", df.columns.tolist())
