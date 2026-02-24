"""
Calculate and visualize NTL intensity difference between 2020 and 2021 in Shanghai.
"""
import rasterio
import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from rasterio.mask import mask

# File paths
ntl_2020_path = r'E:\NTL-GPT-Clone\user_data\debug\inputs\shanghai_ntl__2020.tif'
ntl_2021_path = r'E:\NTL-GPT-Clone\user_data\debug\inputs\shanghai_ntl__2021.tif'
boundary_path = r'E:\NTL-GPT-Clone\user_data\debug\inputs\shanghai_boundary.shp'
output_diff_raster = r'E:\NTL-GPT-Clone\user_data\debug\outputs\shanghai_ntl_diff_2020_2021.tif'
output_viz = r'E:\NTL-GPT-Clone\user_data\debug\outputs\shanghai_ntl_comparison_2020_2021.png'
output_stats_csv = r'E:\NTL-GPT-Clone\user_data\debug\outputs\shanghai_ntl_diff_statistics.csv'

# Load boundary
print("Loading Shanghai boundary...")
boundary = gpd.read_file(boundary_path)

# Load and mask NTL data
def load_ntl(path):
    with rasterio.open(path) as src:
        out_image, out_transform = mask(src, boundary.geometry, crop=True)
        return out_image[0], src.transform, src.crs, src.nodata

print("Loading NTL data for 2020 and 2021...")
ntl_2020, transform, crs, nodata = load_ntl(ntl_2020_path)
ntl_2021, _, _, _ = load_ntl(ntl_2021_path)

# Calculate difference (2021 - 2020)
difference = ntl_2021 - ntl_2020

# Create valid pixel mask
valid_mask = (~np.isnan(ntl_2020)) & (~np.isnan(ntl_2021))
if nodata is not None:
    valid_mask = valid_mask & (ntl_2020 != nodata) & (ntl_2021 != nodata)

ntl_2020_valid = ntl_2020[valid_mask]
ntl_2021_valid = ntl_2021[valid_mask]
diff_valid = difference[valid_mask]

# Calculate statistics
tntl_2020 = ntl_2020_valid.sum()
tntl_2021 = ntl_2021_valid.sum()
antl_2020 = ntl_2020_valid.mean()
antl_2021 = ntl_2021_valid.mean()
mean_diff = diff_valid.mean()
std_diff = diff_valid.std()
pct_change = ((antl_2021 - antl_2020) / antl_2020) * 100
tntl_pct_change = ((tntl_2021 - tntl_2020) / tntl_2020) * 100

# Pixels by change category
pixels_increased = np.sum(diff_valid > 0)
pixels_decreased = np.sum(diff_valid < 0)
pixels_stable = np.sum(np.abs(diff_valid) <= 1)
total_valid = len(diff_valid)

print("\n" + "="*70)
print("SHANGHAI NTL INTENSITY COMPARISON: 2020 vs 2021")
print("="*70)
print(f"\nSUMMARY STATISTICS")
print(f"{'Metric':<30} {'2020':>14} {'2021':>14} {'Change':>14}")
print("-"*70)
print(f"{'Total NTL (TNTL)':<30} {tntl_2020:>14,.2f} {tntl_2021:>14,.2f} {tntl_2021-tntl_2020:>+14,.2f}")
print(f"{'Average NTL (ANTL)':<30} {antl_2020:>14,.4f} {antl_2021:>14,.4f} {antl_2021-antl_2020:>+14,.4f}")
print(f"{'Max NTL':<30} {ntl_2020_valid.max():>14,.2f} {ntl_2021_valid.max():>14,.2f} {ntl_2021_valid.max()-ntl_2020_valid.max():>+14,.2f}")
print(f"{'Std Deviation':<30} {ntl_2020_valid.std():>14,.4f} {ntl_2021_valid.std():>14,.4f} {ntl_2021_valid.std()-ntl_2020_valid.std():>+14,.4f}")
print(f"\nPercentage Change (ANTL): {pct_change:+.2f}%")
print(f"Percentage Change (TNTL): {tntl_pct_change:+.2f}%")

print(f"\nPIXEL CHANGE DISTRIBUTION")
print(f"Pixels with increased brightness: {pixels_increased:,} ({pixels_increased/total_valid*100:.2f}%)")
print(f"Pixels with decreased brightness: {pixels_decreased:,} ({pixels_decreased/total_valid*100:.2f}%)")
print(f"Pixels stable (within +/-1):      {pixels_stable:,} ({pixels_stable/total_valid*100:.2f}%)")
print(f"Total valid pixels:               {total_valid:,}")

print(f"\nMean Difference (2021-2020): {mean_diff:+.4f}")
print(f"Std of Difference: {std_diff:.4f}")
print("="*70)

# Save difference raster
print(f"\nSaving difference raster...")
diff_profile = {
    'driver': 'GTiff',
    'height': difference.shape[0],
    'width': difference.shape[1],
    'count': 1,
    'dtype': 'float32',
    'crs': crs,
    'transform': transform,
    'nodata': -9999
}
with rasterio.open(output_diff_raster, 'w', **diff_profile) as dst:
    diff_filled = np.nan_to_num(difference, nan=-9999)
    dst.write(diff_filled.astype('float32'), 1)
print(f"Difference raster saved: {output_diff_raster}")

# Save statistics to CSV
stats_df = pd.DataFrame({
    'metric': [
        'TNTL_2020', 'TNTL_2021', 'TNTL_Change', 'TNTL_Pct_Change',
        'ANTL_2020', 'ANTL_2021', 'ANTL_Change', 'ANTL_Pct_Change',
        'MaxNTL_2020', 'MaxNTL_2021', 'MaxNTL_Change',
        'Mean_Difference', 'Std_Difference',
        'Pixels_Increased', 'Pixels_Decreased', 'Pixels_Stable', 'Total_Valid_Pixels'
    ],
    'value': [
        tntl_2020, tntl_2021, tntl_2021-tntl_2020, tntl_pct_change,
        antl_2020, antl_2021, antl_2021-antl_2020, pct_change,
        ntl_2020_valid.max(), ntl_2021_valid.max(), ntl_2021_valid.max()-ntl_2020_valid.max(),
        mean_diff, std_diff,
        pixels_increased, pixels_decreased, pixels_stable, total_valid
    ]
})
stats_df.to_csv(output_stats_csv, index=False)
print(f"Statistics saved: {output_stats_csv}")

# Create visualization
print(f"\nCreating visualization...")
fig, axes = plt.subplots(2, 2, figsize=(16, 12))

# 1. Difference Map
vmax = max(abs(diff_valid.min()), diff_valid.max())
im1 = axes[0, 0].imshow(difference, cmap='RdYlGn', vmin=-vmax, vmax=vmax)
axes[0, 0].set_title('NTL Intensity Difference (2021 - 2020)\nShanghai', fontsize=14, fontweight='bold')
axes[0, 0].axis('off')
plt.colorbar(im1, ax=axes[0, 0], shrink=0.8, label='Radiance Difference')

# 2. Scatter Plot
sample_rate = max(1, len(ntl_2020_valid) // 1000)
axes[0, 1].scatter(ntl_2020_valid[::sample_rate], ntl_2021_valid[::sample_rate], 
                   alpha=0.3, s=2, c='steelblue', edgecolors='none')
max_val = max(ntl_2020_valid.max(), ntl_2021_valid.max())
axes[0, 1].plot([0, max_val], [0, max_val], 'r--', linewidth=2, label='1:1 Line (No Change)')
axes[0, 1].set_xlabel('2020 NTL Intensity')
axes[0, 1].set_ylabel('2021 NTL Intensity')
axes[0, 1].set_title('2020 vs 2021 Pixel Values\nShanghai', fontsize=14, fontweight='bold')
axes[0, 1].legend(loc='upper left')
axes[0, 1].grid(True, alpha=0.3)
axes[0, 1].set_xlim(0, max_val)
axes[0, 1].set_ylim(0, max_val)

# 3. Histogram of Differences
axes[1, 0].hist(diff_valid, bins=100, color='steelblue', edgecolor='black', alpha=0.7)
axes[1, 0].axvline(x=0, color='red', linestyle='--', linewidth=2.5, label='No Change (0)')
axes[1, 0].axvline(x=mean_diff, color='green', linestyle='-', linewidth=2, 
                   label=f'Mean Change ({mean_diff:+.3f})')
axes[1, 0].set_xlabel('NTL Difference (2021 - 2020)')
axes[1, 0].set_ylabel('Pixel Count')
axes[1, 0].set_title('Distribution of NTL Changes\nShanghai 2020-2021', fontsize=14, fontweight='bold')
axes[1, 0].legend()
axes[1, 0].grid(True, alpha=0.3, axis='y')

# 4. Box Plot Comparison
box_data = [ntl_2020_valid, ntl_2021_valid]
axes[1, 1].boxplot(box_data, labels=['2020', '2021'], patch_artist=True,
                   boxprops=dict(facecolor='lightblue', alpha=0.7),
                   medianprops=dict(color='red', linewidth=2))
axes[1, 1].set_ylabel('NTL Intensity')
axes[1, 1].set_title('NTL Intensity Distribution\nShanghai 2020 vs 2021', fontsize=14, fontweight='bold')
axes[1, 1].grid(True, alpha=0.3, axis='y')

# Add text annotation
textstr = f'ANTL Change: {pct_change:+.2f}%\nTNTL Change: {tntl_pct_change:+.2f}%\nMean Diff: {mean_diff:+.3f}'
axes[1, 1].text(0.05, 0.95, textstr, transform=axes[1, 1].transAxes, fontsize=10,
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

plt.tight_layout()
plt.savefig(output_viz, dpi=300, bbox_inches='tight', facecolor='white')
print(f"Visualization saved: {output_viz}")
plt.show()

print("\n" + "="*70)
print("ANALYSIS COMPLETE")
print("="*70)
print(f"\nOutput Files:")
print(f"  1. {output_diff_raster}")
print(f"  2. {output_viz}")
print(f"  3. {output_stats_csv}")
print(f"\nKey Finding: Shanghai's average NTL intensity {'increased' if pct_change > 0 else 'decreased'} by {abs(pct_change):.2f}% from 2020 to 2021.")
print("="*70)
