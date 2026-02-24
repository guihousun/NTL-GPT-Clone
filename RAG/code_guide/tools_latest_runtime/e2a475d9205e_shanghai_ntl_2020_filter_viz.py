import rasterio
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from storage_manager import storage_manager

# Resolve paths using storage_manager
input_tif = storage_manager.resolve_input_path('shanghai_ntl_2020.tif')
output_tif = storage_manager.resolve_output_path('shanghai_ntl_2020_filtered.tif')
output_png = storage_manager.resolve_output_path('shanghai_ntl_2020_visualization.png')

# Read the NTL raster
with rasterio.open(input_tif) as src:
    ntl_data = src.read(1).astype(np.float32)
    profile = src.profile
    transform = src.transform
    crs = src.crs

# Set noise values less than 1 to NaN
print(f"Original data range: {np.nanmin(ntl_data):.2f} to {np.nanmax(ntl_data):.2f}")
noise_mask = ntl_data < 1
noise_count = np.sum(noise_mask)
print(f"Number of pixels set to NaN (values < 1): {noise_count}")
ntl_data[noise_mask] = np.nan

# Save filtered raster
profile.update(dtype=rasterio.float32, nodata=np.nan)
with rasterio.open(output_tif, 'w', **profile) as dst:
    dst.write(ntl_data, 1)
print(f"Filtered raster saved to: {output_tif}")

# Create visualization with viridis colormap
plt.figure(figsize=(12, 10))
# Create a norm that ignores NaN values
vmin = np.nanmin(ntl_data)
vmax = np.nanmax(ntl_data)
norm = Normalize(vmin=vmin, vmax=vmax)

im = plt.imshow(ntl_data, cmap='viridis', norm=norm)
plt.colorbar(im, label='NTL Intensity (DN)', shrink=0.8)
plt.title('Shanghai NPP-VIIRS-like NTL (2020)\nNoise values (<1) masked as NaN', fontsize=14, fontweight='bold')
plt.xlabel('Pixel Column')
plt.ylabel('Pixel Row')
plt.axis('off')
plt.tight_layout()
plt.savefig(output_png, dpi=300, bbox_inches='tight')
plt.close()
print(f"Visualization saved to: {output_png}")

print("\nProcessing complete!")
print(f"  - Filtered raster: {output_tif}")
print(f"  - Visualization: {output_png}")
