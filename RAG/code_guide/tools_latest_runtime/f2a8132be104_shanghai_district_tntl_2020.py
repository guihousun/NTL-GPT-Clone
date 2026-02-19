import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.features import geometry_mask
from storage_manager import storage_manager

# Resolve paths using storage_manager
raster_path = storage_manager.resolve_input_path('shanghai_npp_viirs_like_2020.tif')
vector_path = storage_manager.resolve_input_path('shanghai_boundary.shp')
out_csv = storage_manager.resolve_output_path('shanghai_district_TNTL_2020.csv')

# Load raster
with rasterio.open(raster_path) as src:
    arr = src.read(1)
    nodata = src.nodata
    transform = src.transform
    crs = src.crs
    # Calculate pixel area in square degrees (for EPSG:4326)
    pixel_area = abs(transform.a * transform.e)

# Load vector and reproject to match raster CRS
gdf = gpd.read_file(vector_path).to_crs(crs)

# Calculate zonal statistics for each district
rows = []
for _, row in gdf.iterrows():
    geom = [row.geometry]
    # Create mask: True for pixels inside the geometry
    mask = geometry_mask(geom, transform=transform, invert=True, out_shape=arr.shape)
    vals = arr[mask]
    
    # Filter out nodata and non-finite values
    if nodata is not None:
        vals = vals[vals != nodata]
    vals = vals[np.isfinite(vals)]
    
    # Calculate TNTL (sum of NTL values)
    tntl = float(vals.sum()) if vals.size else np.nan
    # Calculate ANTL (mean NTL value)
    antl = float(vals.mean()) if vals.size else np.nan
    # Calculate lit area (number of lit pixels * pixel area)
    lit_pixels = int(vals.size) if vals.size else 0
    larea = float(lit_pixels * pixel_area) if vals.size else 0.0
    # Calculate max NTL
    max_ntl = float(vals.max()) if vals.size else np.nan
    
    rows.append({
        'Region': row.get('Name', 'unknown'),
        'AdCode': row.get('AdCode', None),
        'TNTL': tntl,
        'ANTL': antl,
        'LArea': larea,
        'Max_NTL': max_ntl,
        'Lit_Pixels': lit_pixels
    })

# Create DataFrame and save to CSV
df = pd.DataFrame(rows)
df.to_csv(out_csv, index=False, float_format='%.2f')
print(f"TNTL results saved to: {out_csv}")
print(f"\nSummary statistics:")
print(f"Total districts: {len(df)}")
print(f"Total TNTL (region): {df['TNTL'].sum():.2f}")
print(f"Mean TNTL per district: {df['TNTL'].mean():.2f}")
print(f"District with max TNTL: {df.loc[df['TNTL'].idxmax(), 'Region']} ({df['TNTL'].max():.2f})")
print(f"District with min TNTL: {df.loc[df['TNTL'].idxmin(), 'Region']} ({df['TNTL'].min():.2f})")