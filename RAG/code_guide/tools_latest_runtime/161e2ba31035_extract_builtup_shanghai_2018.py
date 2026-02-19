"""
Extract built-up area in Shanghai for 2018 using a fixed threshold of 10.
Threshold: NTL >= 10 -> built-up (1), NTL < 10 -> non-built-up (0)
"""
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.features import geometry_mask
from storage_manager import storage_manager

# Resolve input paths
raster_path = storage_manager.resolve_input_path('ntl_shanghai_2018.tif')
vector_path = storage_manager.resolve_input_path('shanghai_boundary.shp')
out_tif = storage_manager.resolve_output_path('shanghai_builtup_2018_threshold10.tif')

# Load boundary and reproject to match raster CRS
gdf = gpd.read_file(vector_path)

# Load raster
with rasterio.open(raster_path) as src:
    arr = src.read(1).astype(np.float32)
    nodata = src.nodata
    profile = src.profile.copy()
    
    # Reproject boundary to raster CRS if needed
    gdf = gdf.to_crs(src.crs)
    
    # Create mask from boundary geometry
    mask = geometry_mask(
        [geom for geom in gdf.geometry],
        transform=src.transform,
        invert=True,
        out_shape=arr.shape
    )
    
    # Apply threshold: NTL >= 10 -> built-up (1), else (0)
    # First, handle nodata if present
    if nodata is not None:
        valid_mask = (arr != nodata) & np.isfinite(arr)
    else:
        valid_mask = np.isfinite(arr)
    
    # Apply boundary mask
    valid_mask = valid_mask & mask
    
    # Create binary built-up mask
    built_up = np.zeros_like(arr, dtype=np.uint8)
    built_up[valid_mask & (arr >= 10)] = 1
    
    # Update profile for output
    profile.update({
        'dtype': 'uint8',
        'count': 1,
        'nodata': 255,  # Use 255 as nodata for the binary mask
    })
    
    # Set areas outside boundary to nodata
    output_arr = built_up.copy()
    output_arr[~mask] = 255
    
    # Write output
    with rasterio.open(out_tif, 'w', **profile) as dst:
        dst.write(output_arr, 1)

print(f"Built-up area mask saved to: {out_tif}")

# Calculate statistics
total_pixels = np.sum(mask)
built_up_pixels = np.sum(built_up[mask])
built_up_area_km2 = built_up_pixels * abs(src.transform.a * src.transform.e) * 111.32 * 111.32  # Approximate km2

print(f"Total pixels within boundary: {total_pixels}")
print(f"Built-up pixels (NTL >= 10): {built_up_pixels}")
print(f"Built-up area (approx km2): {built_up_area_km2:.2f}")
print(f"Built-up percentage: {100 * built_up_pixels / total_pixels:.2f}%")
