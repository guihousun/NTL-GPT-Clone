import pandas as pd
import os
from storage_manager import storage_manager

# Try to find the CSV file in both inputs and outputs
possible_paths = [
    storage_manager.resolve_input_path('shanghai_district_ntl_stats.csv'),
    storage_manager.resolve_output_path('shanghai_district_ntl_stats.csv'),
]

found_path = None
for p in possible_paths:
    if os.path.exists(p):
        found_path = p
        break

if found_path is None:
    # List files in inputs and outputs directories to debug
    base_dir = os.path.dirname(storage_manager.resolve_input_path('test.txt'))
    inputs_dir = os.path.dirname(storage_manager.resolve_input_path('shanghai_boundary.shp'))
    outputs_dir = os.path.dirname(storage_manager.resolve_output_path('test.txt'))
    
    print("Inputs directory:", inputs_dir)
    print("Files in inputs:", os.listdir(inputs_dir) if os.path.exists(inputs_dir) else "N/A")
    print("\nOutputs directory:", outputs_dir)
    print("Files in outputs:", os.listdir(outputs_dir) if os.path.exists(outputs_dir) else "N/A")
else:
    print("Found CSV at:", found_path)
    df = pd.read_csv(found_path)
    print("Columns:", df.columns.tolist())
    print("\nFirst 20 rows:")
    print(df.head(20))
    print("\nTotal rows:", len(df))
