import rasterio
import numpy as np
from rasterio.mask import mask
import geopandas as gpd
import csv
from storage_manager import storage_manager

# Resolve input paths using storage_manager
boundary_path = storage_manager.resolve_input_path('shanghai_boundary.shp')
ntl_path = storage_manager.resolve_input_path('shanghai_ntl_202206.tif')
output_csv_path = storage_manager.resolve_output_path('shanghai_darkest_pixel_202206.csv')

# Load boundary
boundary = gpd.read_file(boundary_path)
boundary = boundary.to_crs(epsg=4326)  # Ensure WGS84

# Load NTL raster
with rasterio.open(ntl_path) as src:
    # Mask to study area
    masked_data, masked_transform = mask(src, boundary.geometry, crop=True)
    ntl_array = masked_data[0]
    
    # Handle NoData values
    nodata_value = src.nodata if src.nodata is not None else -9999
    valid_mask = (ntl_array != nodata_value) & (ntl_array > -9999)
    
    # Find minimum valid pixel
    if np.any(valid_mask):
        min_value = np.min(ntl_array[valid_mask])
        min_indices = np.where(ntl_array == min_value)
        
        # Get first occurrence
        row, col = min_indices[0][0], min_indices[1][0]
        
        # Convert pixel indices to WGS84 coordinates
        lon, lat = rasterio.transform.xy(masked_transform, row, col)
        
        print(f'Darkest pixel value: {min_value}')
        print(f'WGS84 Coordinates: Latitude={lat}, Longitude={lon}')
        
        # Save results to CSV
        with open(output_csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['latitude', 'longitude', 'radiance_value'])
            writer.writerow([lat, lon, min_value])
        
        print(f'Results saved to: {output_csv_path}')
    else:
        print('No valid pixels found in study area')