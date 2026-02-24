"""
Load Shanghai 2020 NPP-VIIRS-like NTL data, set noise values < 1 to NaN, and visualize with 'viridis' colormap.
"""
import rasterio
import numpy as np
import matplotlib.pyplot as plt
from rasterio.mask import mask
import geopandas as gpd

# Input/Output paths
input_tif = r'E:\NTL-GPT-Clone\user_data\debug\inputs\shanghai_ntl__2020.tif'
boundary_shp = r'E:\NTL-GPT-Clone\user_data\debug\inputs\shanghai_boundary.shp'
output_clean_tif = r'E:\NTL-GPT-Clone\user_data\debug\outputs\shanghai_ntl_2020_cleaned.tif'
output_viz = r'E:\NTL-GPT-Clone\user_data\debug\outputs\shanghai_ntl_2020_viridis.png'

print(f"Loading data from: {input_tif}")

# Load boundary
boundary = gpd.read_file(boundary_shp)

# Read and mask raster
with rasterio.open(input_tif) as src:
    out_image, out_transform = mask(src, boundary.geometry, crop=True)
    ntl_data = out_image[0].astype(float)
    profile = src.profile.copy()
    profile.update({
        'driver': 'GTiff',
        'height': ntl_data.shape[0],
        'width': ntl_data.shape[1],
        'transform': out_transform,
        'count': 1,
        'dtype': 'float32',
        'nodata': -9999
    })

print(f"Original data shape: {ntl_data.shape}")
print(f"Original min: {np.nanmin(ntl_data):.4f}, max: {np.nanmax(ntl_data):.4f}")

# Apply noise threshold: set values < 1 to NaN
print("Applying noise filter: setting values < 1 to NaN...")
noise_count = np.sum(ntl_data < 1)
ntl_data[ntl_data < 1] = np.nan
print(f"Pixels set to NaN: {noise_count}")

# Save cleaned GeoTIFF
print(f"Saving cleaned raster to: {output_clean_tif}")
# Replace NaN with -9999 for GeoTIFF nodata compatibility
ntl_data_write = np.nan_to_num(ntl_data, nan=-9999)
with rasterio.open(output_clean_tif, 'w', **profile) as dst:
    dst.write(ntl_data_write.astype('float32'), 1)

# Visualization (using original NaN data for proper masking in plot)
print(f"Creating visualization with 'viridis' colormap...")
plt.figure(figsize=(12, 10))

# Display
im = plt.imshow(ntl_data, cmap='viridis')
plt.title('Shanghai NPP-VIIRS-like Nighttime Light (2020)\n(Noise < 1 nW/cm²/sr removed)', fontsize=14, fontweight='bold')
plt.axis('off')

# Colorbar
cbar = plt.colorbar(im, shrink=0.8, label='Radiance (nW/cm²/sr)')
cbar.set_label('Radiance (nW/cm²/sr)', rotation=270, labelpad=20)

plt.tight_layout()
plt.savefig(output_viz, dpi=300, bbox_inches='tight', facecolor='white')
print(f"Visualization saved to: {output_viz}")
plt.show()

print("\n✅ Task Complete!")
print(f"   Cleaned Raster: {output_clean_tif}")
print(f"   Visualization: {output_viz}")
