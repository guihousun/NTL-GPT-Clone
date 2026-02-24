"""
Identify the district in Shanghai with the highest ANTL in 2022 NPP-VIIRS-like image.
Calculates zonal statistics (mean/ANTL) for each district and ranks them.
"""
import ee
import rasterio
import geopandas as gpd
import pandas as pd
import numpy as np
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
from storage_manager import storage_manager

# Initialize GEE (not needed for local processing but good practice)
ee.Initialize(project='empyrean-caster-430308-m2')

# Resolve paths using storage_manager
ntl_raster_path = storage_manager.resolve_input_path('shanghai_ntl_2022.tif')
boundary_shp_path = storage_manager.resolve_input_path('shanghai_boundary.shp')
output_csv_path = storage_manager.resolve_output_path('shanghai_district_antl_2022.csv')

# Load administrative boundaries
gdf = gpd.read_file(boundary_shp_path)
print(f"Loaded {len(gdf)} districts from boundary file")
print(f"District names: {gdf['Name'].tolist()}")

# Load NTL raster
with rasterio.open(ntl_raster_path) as src:
    ntl_data = src.read(1)
    ntl_nodata = src.nodata
    ntl_crs = src.crs
    ntl_transform = src.transform
    print(f"NTL raster shape: {ntl_data.shape}, CRS: {ntl_crs}")

# Ensure boundary is in same CRS as raster
if gdf.crs != ntl_crs:
    gdf = gdf.to_crs(ntl_crs)
    print(f"Reprojected boundary to {ntl_crs}")

# Calculate zonal statistics for each district
results = []

for idx, row in gdf.iterrows():
    district_name = row['Name']
    geom = [row['geometry']]
    
    try:
        # Mask the raster with the district polygon
        out_image, out_transform = mask(ntl_raster_path, geom, crop=True, nodata=ntl_nodata)
        out_data = out_image[0]
        
        # Calculate statistics, excluding nodata values
        if ntl_nodata is not None:
            valid_data = out_data[out_data != ntl_nodata]
        else:
            valid_data = out_data[~np.isnan(out_data)]
        
        if len(valid_data) > 0:
            antl = np.mean(valid_data)  # ANTL = Annual Nighttime Light (mean)
            sntl = np.sum(valid_data)   # SNTL = Sum of Nighttime Light
            max_light = np.max(valid_data)
            min_light = np.min(valid_data)
            count = len(valid_data)
        else:
            antl = np.nan
            sntl = np.nan
            max_light = np.nan
            min_light = np.nan
            count = 0
        
        results.append({
            'District': district_name,
            'ANTL': antl,
            'SNTL': sntl,
            'Max_Light': max_light,
            'Min_Light': min_light,
            'Pixel_Count': count
        })
        print(f"District: {district_name}, ANTL: {antl:.4f}")
        
    except Exception as e:
        print(f"Error processing district {district_name}: {e}")
        results.append({
            'District': district_name,
            'ANTL': np.nan,
            'SNTL': np.nan,
            'Max_Light': np.nan,
            'Min_Light': np.nan,
            'Pixel_Count': 0
        })

# Create DataFrame and save results
df_results = pd.DataFrame(results)

# Sort by ANTL descending
df_sorted = df_results.sort_values('ANTL', ascending=False)

# Identify district with highest ANTL
max_antl_row = df_sorted.iloc[0]
print(f"\n{'='*60}")
print(f"District with highest ANTL in Shanghai (2022): {max_antl_row['District']}")
print(f"ANTL Value: {max_antl_row['ANTL']:.4f} nW·cm⁻²·sr⁻¹")
print(f"{'='*60}")

# Save to CSV
df_sorted.to_csv(output_csv_path, index=False)
print(f"\nResults saved to: {output_csv_path}")

# Print top 5 districts
print(f"\nTop 5 Districts by ANTL:")
print(df_sorted[['District', 'ANTL']].head().to_string(index=False))