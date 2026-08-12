import os
from osgeo import gdal
import numpy as np
from pydantic.v1 import BaseModel, Field
from langchain_core.tools import StructuredTool

from storage_manager import storage_manager


# ======================
# 指数计算函数（带数值稳定性）
# ======================
def _safe_divide(numerator, denominator):
    """Return the declared ratio and mark undefined/non-finite samples as NaN."""
    numerator = np.asarray(numerator, dtype=np.float32)
    denominator = np.asarray(denominator, dtype=np.float32)
    result = np.full(np.broadcast_shapes(numerator.shape, denominator.shape), np.nan, dtype=np.float32)
    valid = np.isfinite(numerator) & np.isfinite(denominator) & (denominator != 0)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        np.divide(numerator, denominator, out=result, where=valid)
    result[~np.isfinite(result)] = np.nan
    return result


def compute_rbli(b, g):
    """Ratio Blue Light Index: B / G."""
    return _safe_divide(b, g)


def compute_rrli(r, g):
    """Ratio Red Light Index: R / G."""
    return _safe_divide(r, g)


def compute_ndibg(b, g):
    """Normalized Difference Index between blue and green: (B - G) / (B + G)."""
    return _safe_divide(b - g, b + g)


def compute_ndigr(g, r):
    """Normalized Difference Index between green and red: (G - R) / (G + R)."""
    return _safe_divide(g - r, g + r)


# ======================
# 保存指数影像函数
# ======================
def save_index_tif(array, reference_tif, output_tif_path, description="Index"):
    ds = gdal.Open(reference_tif)
    if ds is None:
        raise ValueError(f"无法打开参考影像: {reference_tif}")
    
    geo_transform = ds.GetGeoTransform()
    projection = ds.GetProjection()
    rows, cols = array.shape

    driver = gdal.GetDriverByName('GTiff')
    out_ds = driver.Create(output_tif_path, cols, rows, 1, gdal.GDT_Float32)
    out_ds.SetGeoTransform(geo_transform)
    out_ds.SetProjection(projection)
    
    band = out_ds.GetRasterBand(1)
    band.WriteArray(array)
    band.SetDescription(description)
    band.SetNoDataValue(-9999.0)
    
    out_ds.FlushCache()
    del out_ds
    # Keep console output ASCII-safe on Windows shells whose active code page is
    # not UTF-8; logging must never turn a successful raster write into failure.
    print(f"{description} image saved to: {output_tif_path}")


# ======================
# 输入参数模型
# ======================
class IndexInput(BaseModel):
    radiance_filename: str = Field(
        ..., 
        description="Filename of the calibrated RGB radiance GeoTIFF in your 'inputs/' folder (e.g., 'city_rgb.tif'). Must be 3-band Float32."
    )
    output_filename: str = Field(
        ..., 
        description="Output filename to save in your 'outputs/' folder (e.g., 'city_RRLI.tif')."
    )
    index_type: str = Field(
        ..., 
        description="Index type to compute. Must be one of: 'RBLI', 'RRLI', 'NDIBG', 'NDIGR'"
    )



# ======================
# 主计算函数
# ======================
def compute_index_from_rgb_tif(
    radiance_filename: str,
    output_filename: str,
    index_type: str,

) -> str:
    """
    Compute one spectral index from calibrated R/G/B radiance bands.
    Input NoData/non-finite pixels and formula-specific zero denominators are
    written as NoData (-9999).
    """
    try:
        # Resolve paths securely
        abs_radiance_tif = storage_manager.resolve_input_path(radiance_filename)
        abs_output_tif = storage_manager.resolve_output_path(output_filename)

        if not os.path.exists(abs_radiance_tif):
            return f"❌ Input file not found in 'inputs/': {radiance_filename}"

        ds = gdal.Open(abs_radiance_tif)
        if ds is None or ds.RasterCount < 3:
            return f"❌ Failed to open or invalid band count (<3) in: {radiance_filename}"

        # Read calibrated radiance bands (R=1, G=2, B=3) and their NoData values.
        bands = [ds.GetRasterBand(i) for i in (1, 2, 3)]
        r, g, b = [band.ReadAsArray().astype(np.float32) for band in bands]
        nodata_values = [band.GetNoDataValue() for band in bands]
        ds = None  # close

        # Build a shared source-valid mask. NoData in any RGB band propagates.
        valid_mask = np.isfinite(r) & np.isfinite(g) & np.isfinite(b)
        for array, nodata in zip((r, g, b), nodata_values):
            if nodata is not None:
                if np.isnan(nodata):
                    valid_mask &= ~np.isnan(array)
                else:
                    valid_mask &= array != np.float32(nodata)

        idx_type = index_type.upper()

        # Compute the declared formula. Formula-specific zero denominators become
        # NaN here and are written as output NoData below.
        if idx_type == "RBLI":
            computed = compute_rbli(b, g)
            desc = "RBLI (Blue / Green)"
        elif idx_type == "RRLI":
            computed = compute_rrli(r, g)
            desc = "RRLI (Red / Green)"
        elif idx_type == "NDIBG":
            computed = compute_ndibg(b, g)
            desc = "NDIBG (Blue - Green) / (Blue + Green)"
        elif idx_type == "NDIGR":
            computed = compute_ndigr(g, r)
            desc = "NDIGR (Green - Red) / (Green + Red)"
        else:
            return f"❌ Unsupported index_type: '{index_type}'. Choose from: RBLI, RRLI, NDIBG, NDIGR."

        output_valid_mask = valid_mask & np.isfinite(computed)
        index_array = np.full_like(r, -9999.0, dtype=np.float32)
        index_array[output_valid_mask] = computed[output_valid_mask]

        # Ensure output dir exists
        os.makedirs(os.path.dirname(abs_output_tif), exist_ok=True)

        # Save
        save_index_tif(index_array, abs_radiance_tif, abs_output_tif, desc)

        valid_ratio = np.sum(output_valid_mask) / output_valid_mask.size
        return f"✅ {idx_type} computed and saved to 'outputs/{output_filename}'. Valid pixel ratio: {valid_ratio:.2%}"

    except Exception as e:
        return f"❌ Error during index computation: {str(e)}"


# ======================
# LangChain 工具封装
# ======================
SDGSAT1_index_tool = StructuredTool.from_function(
    func=compute_index_from_rgb_tif,
    name="SDGSAT1_compute_index",
    description=(
        "Compute a spectral index (RBLI, RRLI, NDIBG, or NDIGR) from a calibrated SDGSAT-1 RGB radiance image in your 'inputs/' folder. "
        "Input NoData, non-finite values, and pixels with an undefined zero denominator are written as NoData (-9999). "
        "Result is saved to your 'outputs/' folder. "
        "\n\nExample:\n"
        "radiance_filename='shanghai_rgb.tif',\n"
        "output_filename='shanghai_RRLI.tif',\n"
        "index_type='RRLI',\n"
    ),
    args_schema=IndexInput,
    return_direct=True
)


# if __name__ == "__main__":
#     compute_index_from_rgb_tif(
#         radiance_tif="SDGSAT_1/SDGSAT1_GLI_shanghai_radiance_rgb.tif",
#         output_tif="SDGSAT_1/SDGSAT1_GLI_shanghai_RRLI1.tif",
#         index_type="RRLI"
#     )
#     compute_index_from_rgb_tif(
#         radiance_tif="SDGSAT_1/SDGSAT1_GLI_shanghai_radiance_rgb.tif",
#         output_tif="SDGSAT_1/SDGSAT1_GLI_shanghai_RBLI.tif",
#         index_type="RBLI"
#     )
