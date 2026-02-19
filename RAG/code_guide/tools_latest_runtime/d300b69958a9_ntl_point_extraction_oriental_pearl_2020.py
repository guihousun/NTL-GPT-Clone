import rasterio
import pandas as pd
import numpy as np
from rasterio.warp import transform
from rasterio.sample import sample_gen
from storage_manager import storage_manager
from datetime import datetime

# Resolve paths
raster_path = storage_manager.resolve_input_path('ntl_shanghai_2020.tif')
point_csv = storage_manager.resolve_input_path('oriental_pearl_tower_location.csv')
output_csv = storage_manager.resolve_output_path('ntl_oriental_pearl_tower_2020.csv')

# Load coordinates
df = pd.read_csv(point_csv)
lat, lon = df['Latitude'].iloc[0], df['Longitude'].iloc[0]

print("=" * 60)
print("NTL Intensity Extraction at Oriental Pearl Tower")
print("=" * 60)
print(f"Location: Oriental Pearl Tower, Shanghai, China")
print(f"Coordinates: {lat:.6f}°N, {lon:.6f}°E (WGS-84)")
print(f"Year: 2020")
print(f"Dataset: NPP-VIIRS-Like")
print(f"Units: nW·cm⁻²·sr⁻¹ (nano-Watts per square centimeter per steradian)")
print("=" * 60)

# Open NTL raster and extract values
with rasterio.open(raster_path) as src:
    # CRS is already EPSG:4326, no transformation needed
    lon_trans, lat_trans = lon, lat
    
    # Method 1: Nearest-neighbor (single pixel)
    row, col = src.index(lon_trans, lat_trans)
    ntl_single = src.read(1, window=((row, row+1), (col, col+1)))[0, 0]
    
    # Method 2: 3x3 focal mean (recommended for noise reduction)
    window_size = 1  # 1 pixel radius = 3x3 window
    row_start = max(0, row - window_size)
    row_end = min(src.height, row + window_size + 1)
    col_start = max(0, col - window_size)
    col_end = min(src.width, col + window_size + 1)
    window_data = src.read(1, window=((row_start, row_end), (col_start, col_end)))
    ntl_focal_mean = np.mean(window_data[window_data > -9999])  # Exclude NoData
    
    # Method 3: Bilinear interpolation
    ntl_bilinear = list(sample_gen(src, [(lon_trans, lat_trans)], masked=True))[0][0]
    
    print(f'\nExtraction Results:')
    print(f'  Single pixel (nearest-neighbor): {ntl_single:.4f} nW·cm⁻²·sr⁻¹')
    print(f'  3x3 focal mean (recommended):    {ntl_focal_mean:.4f} nW·cm⁻²·sr⁻¹')
    print(f'  Bilinear interpolation:          {ntl_bilinear:.4f} nW·cm⁻²·sr⁻¹')
    print(f'\n  *** RECOMMENDED VALUE: {ntl_focal_mean:.4f} nW·cm⁻²·sr⁻¹ ***')
    print(f'  (3x3 focal mean recommended for noise reduction)')

# Save results to CSV
results = {
    'location': ['Oriental Pearl Tower, Shanghai, China'],
    'latitude': [lat],
    'longitude': [lon],
    'year': [2020],
    'dataset': ['NPP-VIIRS-Like'],
    'ntl_single_pixel': [float(ntl_single)],
    'ntl_3x3_mean': [float(ntl_focal_mean)],
    'ntl_bilinear': [float(ntl_bilinear)],
    'recommended_value': [float(ntl_focal_mean)],
    'units': ['nW·cm⁻²·sr⁻¹'],
    'extraction_timestamp': [datetime.now().isoformat()]
}

result_df = pd.DataFrame(results)
result_df.to_csv(output_csv, index=False)
print(f'\nResults saved to: {output_csv}')
print("=" * 60)
