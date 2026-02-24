"""
Calculate the proportion of NPP-VIIRS NTL pixels with values > 50 
within Shanghai's 2020 administrative boundary.
"""
import rasterio
import geopandas as gpd
import numpy as np
from rasterio.mask import mask
from storage_manager import storage_manager

# Resolve paths using storage_manager
ntl_path = storage_manager.resolve_input_path('shanghai_ntl_2020.tif')
boundary_path = storage_manager.resolve_input_path('shanghai_boundary.shp')
output_csv_path = storage_manager.resolve_output_path('shanghai_ntl_threshold_proportion_2020.csv')

# Load administrative boundary
boundary = gpd.read_file(boundary_path)

# Load NTL raster and mask with boundary
with rasterio.open(ntl_path) as src:
    # Mask raster with boundary geometry
    out_image, out_transform = mask(src, boundary.geometry, crop=True)
    ntl_data = out_image[0]
    
    # Get nodata value (if any)
    nodata = src.nodata
    
    # Create mask for valid pixels (exclude nodata)
    if nodata is not None:
        valid_mask = ~np.isnan(ntl_data) & (ntl_data != nodata)
    else:
        valid_mask = ~np.isnan(ntl_data)
    
    # Extract valid pixel values
    valid_pixels = ntl_data[valid_mask]
    
    # Apply threshold: count pixels > 50
    threshold = 50
    pixels_above_threshold = np.sum(valid_pixels > threshold)
    total_valid_pixels = len(valid_pixels)
    
    # Calculate proportion
    proportion = (pixels_above_threshold / total_valid_pixels) * 100 if total_valid_pixels > 0 else 0

# Print results
print(f"Total valid pixels within Shanghai boundary: {total_valid_pixels}")
print(f"Pixels with NTL value > {threshold}: {pixels_above_threshold}")
print(f"Proportion of pixels > {threshold}: {proportion:.4f}%")

# Save results to CSV
import csv
with open(output_csv_path, 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(['metric', 'value'])
    writer.writerow(['threshold', threshold])
    writer.writerow(['total_valid_pixels', total_valid_pixels])
    writer.writerow(['pixels_above_threshold', pixels_above_threshold])
    writer.writerow(['proportion_percent', proportion])

print(f"\nResults saved to: {output_csv_path}")
