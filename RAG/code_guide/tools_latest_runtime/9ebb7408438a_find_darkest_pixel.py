import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import xy
from storage_manager import storage_manager

# Resolve input paths
raster_path = storage_manager.resolve_input_path('shanghai_ntl_2022_06.tif')
output_csv = storage_manager.resolve_output_path('shanghai_darkest_pixel_2022_06.csv')

# Load NTL data
with rasterio.open(raster_path) as src:
    ntl = src.read(1).astype(np.float32)
    transform = src.transform
    crs = src.crs
    
    # Get nodata value if exists
    nodata = src.nodata

# Apply noise floor mask
# For NOAA_VCMSLCFG monthly data, values are in nanoWatts/cm²/sr
# Noise floor is typically very low; we use a conservative threshold
# Values <= 0 are typically invalid/background
NOISE_FLOOR = 0  # Keep all positive values as valid
valid_mask = ntl > NOISE_FLOOR

# Also mask out any nodata values
if nodata is not None:
    valid_mask = valid_mask & (ntl != nodata)

# Find minimum valid pixel
if np.any(valid_mask):
    min_value = np.min(ntl[valid_mask])
    min_indices = np.where((ntl == min_value) & valid_mask)
    row, col = min_indices[0][0], min_indices[1][0]
    
    # Convert to coordinates (upper-left corner of pixel)
    lon, lat = xy(transform, row, col, offset='ul')
    
    # Also get pixel center
    lon_center, lat_center = xy(transform, row, col, offset='center')
    
    result = {
        'metric': 'darkest_pixel',
        'min_value': min_value,
        'latitude_ul': lat,
        'longitude_ul': lon,
        'latitude_center': lat_center,
        'longitude_center': lon_center,
        'row': row,
        'col': col,
        'crs': str(crs)
    }
    
    # Save to CSV
    pd.DataFrame([result]).to_csv(output_csv, index=False)
    
    print(f"Darkest valid pixel value: {min_value:.6e}")
    print(f"Coordinates (WGS84, upper-left): Lat={lat:.6f}, Lon={lon:.6f}")
    print(f"Coordinates (WGS84, center): Lat={lat_center:.6f}, Lon={lon_center:.6f}")
    print(f"Output saved to: {output_csv}")
else:
    print("All pixels below noise floor or invalid")
    pd.DataFrame([{'error': 'No valid pixels found'}]).to_csv(output_csv, index=False)
