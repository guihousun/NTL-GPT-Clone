import rasterio
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from storage_manager import storage_manager

# Configuration
year1_file = 'shanghai_ntl_2020_2021_2020.tif'
year2_file = 'shanghai_ntl_2020_2021_2021.tif'
output_diff = 'NTL_Difference_2021_2020.tif'
output_viz = 'NTL_Difference_Visualization.png'
output_stats = 'NTL_Difference_Statistics.csv'

# Resolve paths using storage_manager
year1_path = storage_manager.resolve_input_path(year1_file)
year2_path = storage_manager.resolve_input_path(year2_file)
diff_out = storage_manager.resolve_output_path(output_diff)
viz_out = storage_manager.resolve_output_path(output_viz)
stats_out = storage_manager.resolve_output_path(output_stats)

print(f"Loading {year1_file}...")
print(f"Loading {year2_file}...")

# Load both rasters
with rasterio.open(year1_path) as src1, rasterio.open(year2_path) as src2:
    # Ensure same CRS and transform
    assert src1.crs == src2.crs, f"CRS mismatch: {src1.crs} vs {src2.crs}"
    assert src1.transform == src2.transform, "Transform mismatch between years"
    
    ntl_year1 = src1.read(1).astype(np.float32)
    ntl_year2 = src2.read(1).astype(np.float32)
    
    # Handle NoData values
    nodata = src1.nodata
    if nodata is not None:
        ntl_year1[ntl_year1 == nodata] = np.nan
        ntl_year2[ntl_year2 == nodata] = np.nan
    
    meta = src1.meta.copy()
    meta.update({'dtype': 'float32', 'nodata': np.nan})
    
    # Calculate difference (Year2 - Year1)
    ntl_diff = ntl_year2 - ntl_year1
    
    # Save difference raster
    with rasterio.open(diff_out, 'w', **meta) as dst:
        dst.write(ntl_diff, 1)

print(f"Difference raster saved to: {output_diff}")

# Get valid pixels for statistics
valid_diff = ntl_diff[~np.isnan(ntl_diff)]

# Summary statistics
mean_change = float(np.nanmean(valid_diff))
std_change = float(np.nanstd(valid_diff))
pixels_increase = int(np.sum(valid_diff > 0))
pixels_decrease = int(np.sum(valid_diff < 0))
pixels_unchanged = int(np.sum(np.abs(valid_diff) < 0.1))
min_change = float(np.nanmin(valid_diff))
max_change = float(np.nanmax(valid_diff))

print(f"\n=== NTL Difference Analysis Summary ===")
print(f"Mean change: {mean_change:.4f}")
print(f"Std change: {std_change:.4f}")
print(f"Min change: {min_change:.4f}")
print(f"Max change: {max_change:.4f}")
print(f"Pixels with increase (>0): {pixels_increase}")
print(f"Pixels with decrease (<0): {pixels_decrease}")
print(f"Pixels unchanged (~0): {pixels_unchanged}")
print(f"Total valid pixels: {len(valid_diff)}")

# Visualization
plt.figure(figsize=(14, 6))

# Panel 1: Difference Map
plt.subplot(1, 2, 1)
v_max = np.nanpercentile(np.abs(ntl_diff), 95)
im1 = plt.imshow(ntl_diff, cmap='RdYlBu_r', vmin=-v_max, vmax=v_max)
plt.colorbar(im1, label='NTL Radiance Difference (2021 - 2020)')
plt.title('Shanghai NTL Intensity Change\n(Red=Decrease, Blue=Increase)')
plt.xlabel('Pixel X')
plt.ylabel('Pixel Y')

# Panel 2: Histogram of Changes
plt.subplot(1, 2, 2)
plt.hist(valid_diff, bins=100, color='steelblue', edgecolor='black', alpha=0.7)
plt.axvline(x=0, color='red', linestyle='--', linewidth=2, label='No Change')
plt.xlabel('NTL Radiance Difference')
plt.ylabel('Pixel Count')
plt.title('Distribution of NTL Changes (2020-2021)')
plt.legend()
plt.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(viz_out, dpi=300, bbox_inches='tight')
plt.close()

print(f"\nVisualization saved to: {output_viz}")

# Save statistics to CSV
import csv
stats_data = {
    'metric': ['mean_change', 'std_change', 'min_change', 'max_change', 
               'pixels_increase', 'pixels_decrease', 'pixels_unchanged', 'total_valid_pixels'],
    'value': [mean_change, std_change, min_change, max_change,
              pixels_increase, pixels_decrease, pixels_unchanged, len(valid_diff)]
}

with open(stats_out, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['metric', 'value'])
    writer.writeheader()
    for i in range(len(stats_data['metric'])):
        writer.writerow({'metric': stats_data['metric'][i], 'value': stats_data['value'][i]})

print(f"Statistics saved to: {output_stats}")
print("\n=== Analysis Complete ===")