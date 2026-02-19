from osgeo import gdal, osr
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic.v1 import BaseModel, Field

def save_classification_tif(class_array, reference_tif, output_tif_path):
    """
    使用参考影像的地理信息，将分类结果数组保存为 GeoTIFF 文件。
    class_array: numpy 数组，分类值（0=未照明, 1=WLED, 2=RLED, 3=Other）
    reference_tif: 用于获取地理参考信息的 GeoTIFF 文件路径（如 RRLI）
    output_tif_path: 输出路径
    """
    ref_ds = gdal.Open(reference_tif)
    if ref_ds is None:
        raise ValueError(f"无法打开参考影像：{reference_tif}")

    geo_transform = ref_ds.GetGeoTransform()
    projection = ref_ds.GetProjection()
    rows, cols = class_array.shape

    driver = gdal.GetDriverByName('GTiff')
    out_ds = driver.Create(output_tif_path, cols, rows, 1, gdal.GDT_Byte)
    out_ds.SetGeoTransform(geo_transform)
    out_ds.SetProjection(projection)

    band = out_ds.GetRasterBand(1)
    band.WriteArray(class_array)
    band.SetDescription('Light Classification (0=Dark, 1=WLED, 2=RLED, 3=Other)')
    band.SetNoDataValue(0)  # 0 表示未照明区域

    out_ds.FlushCache()
    del out_ds

    print(f"✅ 灯光分类结果已保存为：{output_tif_path}")

class LightIndexClassificationInput(BaseModel):
    rrli_tif: str = Field(..., description="Path to the RRLI GeoTIFF file (Red/Green Ratio)")
    rbli_tif: str = Field(..., description="Path to the RBLI GeoTIFF file (Blue/Green Ratio)")
    output_tif: str = Field(..., description="Path to save the classified light types (GeoTIFF format)")

def classify_light_types_from_rrli_rbli(rrli_tif: str, rbli_tif: str, output_tif: str) -> str:
    ds_rrli = gdal.Open(rrli_tif)
    ds_rbli = gdal.Open(rbli_tif)

    band_rrli = ds_rrli.GetRasterBand(1)
    band_rbli = ds_rbli.GetRasterBand(1)

    rrli = band_rrli.ReadAsArray().astype(np.float32)
    rbli = band_rbli.ReadAsArray().astype(np.float32)

    # 获取 NoData 值（如果有的话）
    nodata_rrli = band_rrli.GetNoDataValue()
    nodata_rbli = band_rbli.GetNoDataValue()

    # 构建有效数据掩膜
    valid_mask = np.ones_like(rrli, dtype=bool)
    if nodata_rrli is not None:
        valid_mask &= (rrli != nodata_rrli)
    if nodata_rbli is not None:
        valid_mask &= (rbli != nodata_rbli)
    # 同时排除 NaN
    valid_mask &= np.isfinite(rrli) & np.isfinite(rbli)

    light_class = np.zeros(rrli.shape, dtype=np.uint8)  # 默认 0 = 未照明 / 无效

    # 只在有效区域分类
    raw_class = np.full(rrli.shape, 3, dtype=np.uint8)  # 默认 Other
    raw_class[valid_mask & (rrli > 9)] = 2              # RLED
    raw_class[valid_mask & (rrli <= 9) & (rbli > 0.57)] = 1  # WLED

    # 照亮区域：只要 RRLI 或 RBLI > 0 且有效
    lit_mask = valid_mask & ((rrli > 0.01) | (rbli > 0.01))
    light_class[lit_mask] = raw_class[lit_mask]

    save_classification_tif(light_class, reference_tif=rrli_tif, output_tif_path=output_tif)
    return f"✅ Light type classification completed. Output: {output_tif}"

light_index_classification_tool = StructuredTool.from_function(
    classify_light_types_from_rrli_rbli,
    name="classify_light_types_from_rrli_rbli",
    description="Classify light source types (WLED, RLED, Other) based on precomputed RRLI and RBLI index images (GeoTIFF). "
                "Output is a GeoTIFF with pixel-level classification.",
    args_schema=LightIndexClassificationInput,
)


# # plot_validation.py
# import numpy as np
# import matplotlib.pyplot as plt
# from matplotlib.colors import ListedColormap
# from osgeo import gdal

# def read_tif(path, band=1):
#     ds = gdal.Open(path)
#     return ds.GetRasterBand(band).ReadAsArray()

# def plot_validation(
#     radiance_rgb_tif,
#     rrli_tif,
#     rbli_tif,
#     class_tif,
#     output_png="classification_validation.png"
# ):
#     # 读取数据
#     r = read_tif(radiance_rgb_tif, 1)
#     g = read_tif(radiance_rgb_tif, 2)
#     b = read_tif(radiance_rgb_tif, 3)
#     rrli = read_tif(rrli_tif)
#     rbli = read_tif(rbli_tif)
#     light_class = read_tif(class_tif)

#     # 归一化 RGB 用于显示（取 log 或百分位）
#     rgb = np.stack([r, g, b], axis=-1)
#     rgb_display = np.clip(rgb / np.percentile(rgb, 99), 0, 1)

#     # 设置分类 colormap
#     cmap = ListedColormap(['black', 'white', 'red', 'yellow'])
#     bounds = [0, 1, 2, 3, 4]
#     norm = plt.Normalize(vmin=0, vmax=3)

#     # 绘图
#     fig, axes = plt.subplots(2, 2, figsize=(12, 10))
#     axes = axes.ravel()

#     # 1. 原始 RGB
#     axes[0].imshow(rgb_display)
#     axes[0].set_title("Original Radiance (RGB)")
#     axes[0].axis('off')

#     # 2. RRLI
#     im1 = axes[1].imshow(rrli, cmap='hot', vmin=0, vmax=20)
#     axes[1].set_title("RRLI (Red/Green)")
#     axes[1].axis('off')
#     plt.colorbar(im1, ax=axes[1], fraction=0.046, pad=0.04)

#     # 3. RBLI
#     im2 = axes[2].imshow(rbli, cmap='coolwarm', vmin=0, vmax=2)
#     axes[2].set_title("RBLI (Blue/Green)")
#     axes[2].axis('off')
#     plt.colorbar(im2, ax=axes[2], fraction=0.046, pad=0.04)

#     # 4. 分类结果
#     im3 = axes[3].imshow(light_class, cmap=cmap, norm=norm)
#     axes[3].set_title("Light Type Classification")
#     axes[3].axis('off')
#     cbar = plt.colorbar(im3, ax=axes[3], ticks=[0.5, 1.5, 2.5, 3.5], fraction=0.046, pad=0.04)
#     cbar.ax.set_yticklabels(['Dark', 'WLED', 'RLED', 'Other'])

#     plt.tight_layout()
#     plt.savefig(output_png, dpi=150, bbox_inches='tight')
#     plt.show()
#     print(f"✅ Validation plot saved to: {output_png}")

# # 示例调用
# if __name__ == "__main__":
#     plot_validation(
#         radiance_rgb_tif="SDGSAT_1/SDGSAT1_GLI_shanghai_radiance_rgb.tif",
#         rrli_tif="SDGSAT_1/SDGSAT1_GLI_shanghai_RRLI.tif",
#         rbli_tif="SDGSAT_1/SDGSAT1_GLI_shanghai_RBLI.tif",
#         class_tif="SDGSAT_1/SDGSAT1_GLI_shanghai_light_class.tif"
#     )

# classify_light_types_from_rrli_rbli(
#     rrli_tif="SDGSAT_1/SDGSAT1_GLI_shanghai_RRLI.tif",
#     rbli_tif="SDGSAT_1/SDGSAT1_GLI_shanghai_RBLI.tif",
#     output_tif="SDGSAT_1/SDGSAT1_GLI_shanghai_light_class3.tif"
# )

