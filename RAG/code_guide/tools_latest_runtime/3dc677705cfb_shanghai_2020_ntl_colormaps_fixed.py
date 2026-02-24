"""
Generate multiple colormap visualizations for Shanghai 2020 NTL data (noise-filtered).
Compares different matplotlib colormaps for NTL visualization.
"""
import rasterio
import numpy as np
import matplotlib.pyplot as plt
from rasterio.mask import mask
import geopandas as gpd

# Input/Output paths
input_tif = r'E:\NTL-GPT-Clone\user_data\debug\inputs\shanghai_ntl__2020.tif'
boundary_shp = r'E:\NTL-GPT-Clone\user_data\debug\inputs\shanghai_boundary.shp'
output_dir = r'E:\NTL-GPT-Clone\user_data\debug\outputs\\'

# Colormaps to compare (standard matplotlib sequential colormaps)
colormaps = [
    'viridis',    # Perceptually uniform, green-yellow (default)
    'plasma',     # Perceptually uniform, purple-yellow
    'inferno',    # Perceptually uniform, black-red-yellow
    'magma',      # Perceptually uniform, black-pink-white
    'cividis',    # Colorblind-friendly, blue-yellow
    'hot',        # Black-red-yellow-white (classic thermal)
    'gist_earth', # Blue-green-brown (terrain-like)
    'YlOrRd',     # Yellow-orange-red (sequential)
]

print("Loading data from:", input_tif)

# Load boundary
boundary = gpd.read_file(boundary_shp)

# Read and mask raster
with rasterio.open(input_tif) as src:
    out_image, out_transform = mask(src, boundary.geometry, crop=True)
    ntl_data = out_image[0].astype(float)
    profile = src.profile.copy()

# Apply noise threshold: set values < 1 to NaN
print("Applying noise filter: setting values < 1 to NaN...")
ntl_data[ntl_data < 1] = np.nan

print("Data shape:", ntl_data.shape)
print("Valid pixels:", np.sum(~np.isnan(ntl_data)))
print("Generating", len(colormaps), "colormap visualizations...\n")

# Create figure with subplots for comparison
fig, axes = plt.subplots(2, 4, figsize=(20, 12))
axes = axes.flatten()

for idx, cmap_name in enumerate(colormaps):
    ax = axes[idx]
    
    # Display with specific colormap
    im = ax.imshow(ntl_data, cmap=cmap_name, vmin=1, vmax=np.nanpercentile(ntl_data, 99))
    ax.set_title(cmap_name.capitalize(), fontsize=12, fontweight='bold')
    ax.axis('off')
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Radiance', rotation=270, labelpad=10, fontsize=9)

plt.suptitle('Shanghai NPP-VIIRS Nighttime Light (2020)\nColormap Comparison (Noise < 1 removed)', 
             fontsize=16, fontweight='bold', y=1.02)
plt.tight_layout()

# Save comparison figure
output_comparison = output_dir + 'shanghai_ntl_2020_colormap_comparison.png'
plt.savefig(output_comparison, dpi=300, bbox_inches='tight', facecolor='white')
print("Comparison figure saved:", output_comparison)
plt.show()

# Also save individual high-resolution visualizations for each colormap
print("\nSaving individual visualizations...")
for cmap_name in colormaps:
    plt.figure(figsize=(12, 10))
    im = plt.imshow(ntl_data, cmap=cmap_name, vmin=1, vmax=np.nanpercentile(ntl_data, 99))
    plt.title('Shanghai NPP-VIIRS Nighttime Light (2020)\nColormap: ' + cmap_name, 
              fontsize=14, fontweight='bold')
    plt.axis('off')
    cbar = plt.colorbar(im, shrink=0.8, label='Radiance')
    cbar.set_label('Radiance', rotation=270, labelpad=20)
    plt.tight_layout()
    
    output_individual = output_dir + 'shanghai_ntl_2020_' + cmap_name + '.png'
    plt.savefig(output_individual, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print("  " + cmap_name + ": " + output_individual)

print("\n" + "="*70)
print("COLORMAP COMPARISON COMPLETE")
print("="*70)
print("\nOutput Files:")
print("   Comparison Grid: " + output_comparison)
print("   Individual Files:")
for cmap_name in colormaps:
    print("      - shanghai_ntl_2020_" + cmap_name + ".png")
print("="*70)
print("\nRecommendation:")
print("   - viridis/cividis: Best for scientific publications (colorblind-friendly)")
print("   - inferno/magma/hot: High contrast, good for presentations")
print("   - plasma/YlOrRd: Vibrant, excellent for visual appeal")
print("   - gist_earth: Terrain-like appearance for geographic context")
print("="*70)
