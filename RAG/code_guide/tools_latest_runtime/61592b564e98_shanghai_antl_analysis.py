import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.mask import mask
import numpy as np
from storage_manager import storage_manager

# Resolve paths using storage_manager
ntl_path = storage_manager.resolve_input_path('ntl_shanghai_2022.tif')
boundary_path = storage_manager.resolve_input_path('shanghai_districts_boundary.shp')
output_csv_path = storage_manager.resolve_output_path('shanghai_district_antl_2022.csv')

# Load boundaries
gdf = gpd.read_file(boundary_path)

# Ensure CRS match
with rasterio.open(ntl_path) as src:
    ntl_crs = src.crs
    
# Reproject boundaries if needed
if gdf.crs != ntl_crs:
    gdf = gdf.to_crs(ntl_crs)

# Calculate ANTL for each district
results = []
for idx, row in gdf.iterrows():
    district_name = row['Name']
    geom = [row['geometry']]
    
    with rasterio.open(ntl_path) as src:
        # Mask the raster with the district geometry
        out_image, out_transform = mask(src, geom, crop=True)
        out_data = out_image[0]
        
        # Calculate mean (ANTL), excluding nodata values
        # NPP-VIIRS-Like typically has no nodata or uses 0 as background
        valid_data = out_data[out_data > 0]  # Exclude zero/background values
        
        if len(valid_data) > 0:
            antl = float(np.mean(valid_data))
        else:
            antl = 0.0
    
    results.append({
        'District': district_name,
        'ANTL': antl
    })

# Create DataFrame and save
df = pd.DataFrame(results)
df.to_csv(output_csv_path, index=False)

# Find district with highest ANTL
max_row = df.loc[df['ANTL'].idxmax()]
print(f"District with highest ANTL: {max_row['District']} (ANTL: {max_row['ANTL']:.4f})")
print(f"\nAll districts ANTL:\n{df.sort_values('ANTL', ascending=False)}")
print(f"\nResults saved to: {output_csv_path}")