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


class JiaLightClassificationInput(BaseModel):
    """Inputs for the fixed Jia et al. (2024) RGB-light classification."""

    radiance_filename: str = Field(
        ...,
        description=(
            "Filename of the calibrated three-band SDGSAT-1 RGB radiance GeoTIFF "
            "in 'inputs/'. Bands must be ordered Red, Green, Blue."
        ),
    )
    rrli_output_filename: str = Field(
        ...,
        description="Filename for the RRLI (Red/Green) GeoTIFF written under 'outputs/'.",
    )
    rbli_output_filename: str = Field(
        ...,
        description="Filename for the RBLI (Blue/Green) GeoTIFF written under 'outputs/'.",
    )
    classification_output_filename: str = Field(
        ...,
        description="Filename for the uint8 Jia et al. light-class GeoTIFF written under 'outputs/'.",
    )


def _source_valid_mask(arrays, nodata_values):
    """Return a shared finite/non-NoData mask for R, G, B arrays."""

    valid = np.ones_like(arrays[0], dtype=bool)
    for array, nodata in zip(arrays, nodata_values):
        valid &= np.isfinite(array)
        if nodata is not None:
            if np.isnan(nodata):
                valid &= ~np.isnan(array)
            else:
                valid &= array != np.float32(nodata)
    return valid


def _write_light_class_tif(array, reference_tif, output_tif_path):
    """Write a categorical uint8 raster with the source grid and 255 NoData."""

    ds = gdal.Open(reference_tif)
    if ds is None:
        raise ValueError(f"Unable to open reference image: {reference_tif}")
    driver = gdal.GetDriverByName("GTiff")
    output = driver.Create(output_tif_path, ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Byte)
    if output is None:
        raise ValueError(f"Unable to create output image: {output_tif_path}")
    output.SetGeoTransform(ds.GetGeoTransform())
    output.SetProjection(ds.GetProjection())
    band = output.GetRasterBand(1)
    band.WriteArray(np.asarray(array, dtype=np.uint8))
    band.SetDescription("Jia et al. (2024) SDGSAT-1 light class")
    band.SetNoDataValue(255)
    output.FlushCache()
    output = None
    ds = None


def classify_jia_light_from_rgb_tif(
    radiance_filename: str,
    rrli_output_filename: str,
    rbli_output_filename: str,
    classification_output_filename: str,
) -> str:
    """Compute RRLI/RBLI and the fixed Jia et al. (2024) three-class rule.

    The threshold order is part of the method contract: first assign RLED when
    RRLI > 9; among all remaining valid pixels assign WLED when RBLI > 0.57;
    assign Other otherwise.  Codes are WLED=1, RLED=2, Other=3 and NoData=255.
    """

    try:
        input_path = storage_manager.resolve_input_path(radiance_filename)
        rrli_path = storage_manager.resolve_output_path(rrli_output_filename)
        rbli_path = storage_manager.resolve_output_path(rbli_output_filename)
        class_path = storage_manager.resolve_output_path(classification_output_filename)
        if not os.path.exists(input_path):
            return f"Error: input file not found in inputs/: {radiance_filename}"

        dataset = gdal.Open(input_path)
        if dataset is None or dataset.RasterCount < 3:
            return f"Error: expected a readable three-band RGB GeoTIFF: {radiance_filename}"
        bands = [dataset.GetRasterBand(index) for index in (1, 2, 3)]
        red, green, blue = [band.ReadAsArray().astype(np.float32) for band in bands]
        nodata_values = [band.GetNoDataValue() for band in bands]
        dataset = None

        valid = _source_valid_mask((red, green, blue), nodata_values)
        # The Jia ratios are defined only for a positive green-channel
        # radiance.  A non-positive denominator is not a valid dark-light
        # observation: keep it as NoData rather than allowing a finite ratio
        # from a negative denominator to enter the class thresholds.
        valid &= np.isfinite(green) & (green > 0.0)
        rrli_raw = compute_rrli(red, green)
        rbli_raw = compute_rbli(blue, green)
        valid &= np.isfinite(rrli_raw) & np.isfinite(rbli_raw)

        rrli = np.full_like(red, -9999.0, dtype=np.float32)
        rbli = np.full_like(red, -9999.0, dtype=np.float32)
        rrli[valid] = rrli_raw[valid]
        rbli[valid] = rbli_raw[valid]

        # The order below is intentional and tested.  A pixel meeting both
        # thresholds is RLED because the RLED rule is evaluated first.
        light_class = np.full(red.shape, 255, dtype=np.uint8)
        rled = valid & (rrli_raw > 9.0)
        wled = valid & ~rled & (rbli_raw > 0.57)
        other = valid & ~rled & ~wled
        light_class[wled] = 1
        light_class[rled] = 2
        light_class[other] = 3

        for path in (rrli_path, rbli_path, class_path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        save_index_tif(rrli, input_path, rrli_path, "RRLI (Red / Green)")
        save_index_tif(rbli, input_path, rbli_path, "RBLI (Blue / Green)")
        _write_light_class_tif(light_class, input_path, class_path)

        counts = {
            "WLED": int(np.count_nonzero(light_class == 1)),
            "RLED": int(np.count_nonzero(light_class == 2)),
            "Other": int(np.count_nonzero(light_class == 3)),
            "NoData": int(np.count_nonzero(light_class == 255)),
        }
        return (
            "Jia et al. (2024) light classification completed. "
            "RRLI=Red/Green; RBLI=Blue/Green; classification order is "
            "RLED if RRLI>9, otherwise WLED if RBLI>0.57, otherwise Other. "
            f"Outputs: outputs/{rrli_output_filename}, outputs/{rbli_output_filename}, "
            f"outputs/{classification_output_filename}. Counts: {counts}."
        )
    except Exception as exc:
        return f"Error during Jia light classification: {exc}"



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
        "For named SDGSAT-1 light indices, use this tool rather than recreating a ratio in generic code: RRLI is Red/Green and RBLI is Blue/Green. "
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


SDGSAT1_jia_light_classification_tool = StructuredTool.from_function(
    func=classify_jia_light_from_rgb_tif,
    name="SDGSAT1_jia_light_classification",
    description=(
        "Compute RRLI (Red/Green), RBLI (Blue/Green), and the fixed Jia et al. "
        "(2024) SDGSAT-1 light-source classification from one calibrated RGB "
        "radiance GeoTIFF. This is the dedicated method for a request that names "
        "Jia et al. light classification: RLED if RRLI > 9; otherwise WLED if "
        "RBLI > 0.57; otherwise Other. Class codes are WLED=1, RLED=2, Other=3, "
        "NoData=255. Do not replace these thresholds or their order with generic code."
    ),
    args_schema=JiaLightClassificationInput,
    return_direct=True,
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
