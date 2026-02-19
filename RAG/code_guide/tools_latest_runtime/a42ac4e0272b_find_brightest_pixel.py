"""
Find the brightest pixel in Shanghai NPP-VIIRS NTL 2022 imagery and extract its WGS84 coordinates.
"""
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import xy
from storage_manager import storage_manager

# Resolve paths using storage_manager
ntl_path = storage_manager.resolve_input_path('shanghai_NTL_2022.tif')
output_csv = storage_manager.resolve_output_path('brightest_pixel_coordinates.csv')

# Load the NTL GeoTIFF
with rasterio.open(ntl_path) as src:
    # Read the data
    data = src.read(1)
    transform = src.transform
    crs = src.crs
    
    # Find the maximum value and its pixel location
    # Handle potential NaN or invalid values
    valid_mask = np.isfinite(data)
    valid_data = np.where(valid_mask, data, -9999)
    
    max_value = np.max(valid_data)
    max_indices = np.where(valid_data == max_value)
    
    # Get the first occurrence of the maximum value
    row_idx = int(max_indices[0][0])
    col_idx = int(max_indices[1][0])
    
    # Convert pixel indices to coordinates (using center of pixel)
    # rasterio uses 0-based indexing
    lon, lat = xy(transform, row_idx, col_idx, offset='center')
    
    # Print results
    print(f"Maximum NTL value: {max_value}")
    print(f"Pixel location (row, col): ({row_idx}, {col_idx})")
    print(f"WGS84 Coordinates: Latitude={lat:.6f}, Longitude={lon:.6f}")
    
    # Save to CSV
    df = pd.DataFrame({
        'latitude': [lat],
        'longitude': [lon],
        'ntl_value': [max_value],
        'row_index': [row_idx],
        'col_index': [col_idx]
    })
    df.to_csv(output_csv, index=False)
    
    print(f"Results saved to {output_csv}")
