# import os
# from typing import Optional
# import rasterio
# import numpy as np
# import cv2
# import streamlit as st
# from langchain_core.tools import StructuredTool
# from pydantic.v1 import BaseModel, Field
# from langchain_core.runnables import RunnableConfig
from typing import Optional
# from langchain_core.runnables import RunnableConfig # 必须导入这个


# # --- 底层算法函数保持不变 ---
# def read_tif(path):
#     with rasterio.open(path) as src:
#         image = src.read(1).astype(np.float32)
#     return image

# def calculate_perimeter(binary_image):
#     contours, _ = cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
#     perimeter = sum(cv2.arcLength(cnt, True) for cnt in contours)
#     return perimeter

# def analyze_thresholds(image, num_thresholds=64):
#     min_val = image.min()
#     max_val = image.max()
#     thresholds = np.linspace(min_val, max_val, num_thresholds)
#     perimeters = []
#     for t in thresholds:
#         binary = np.uint8((image > t) * 255)
#         perimeter = calculate_perimeter(binary)
#         perimeters.append(perimeter)
#     return thresholds, perimeters

# def find_optimal_threshold(thresholds, perimeters):
#     for i in range(1, len(perimeters)):
#         if perimeters[i] > perimeters[i - 1] and all(
#             perimeters[j] > perimeters[j - 1] for j in range(i, min(i + 3, len(perimeters)))
#         ):
#             return thresholds[i]
#     return thresholds[np.argmax(perimeters)]

# # --- 修改后的参数模型：只接收文件名 ---
# class UrbanExtractionInput(BaseModel):
#     tif_filename: str = Field(..., description="输入的夜间灯光影像文件名（例如: NTL_2020.tif）")
#     output_filename: str = Field(..., description="输出的掩膜文件名（例如: result_mask.tif）")

# # --- 修改后的包装函数 ---
# def extract_urban_area_with_optimal_threshold(
#     tif_filename: str, 
#     output_filename: str, 
# ) -> str:

#     abs_input_path = storage_manager.resolve_input_path(tif_filename)
#     abs_output_path = storage_manager.resolve_output_path(output_filename)

#     if not os.path.exists(abs_input_path):
#         return f"错误：找不到文件 {tif_filename}。请确认文件已下载到工作空间或存在于基础库中。"

#     # 3. 执行核心算法
#     try:
#         image = read_tif(abs_input_path)
#         thresholds, perimeters = analyze_thresholds(image)
#         optimal_threshold = find_optimal_threshold(thresholds, perimeters)

#         with rasterio.open(abs_input_path) as src:
#             raw = src.read(1)
#             profile = src.profile

#         urban_mask = raw >= optimal_threshold
#         profile.update(dtype=rasterio.uint8, count=1)

#         with rasterio.open(abs_output_path, "w", **profile) as dst:
#             dst.write(urban_mask.astype(rasterio.uint8), 1)

#         # 4. 返回相对路径信息，方便 Agent 回复和前端展示
#         return (f"成功！最佳阈值: {optimal_threshold:.2f}\n"
#                 f"输入文件: {tif_filename}\n"
#                 f"结果已保存至个人空间: outputs/{os.path.basename(output_filename)}")
                
#     except Exception as e:
#         return f"处理过程中发生错误: {str(e)}"

# # --- 定义 StructuredTool ---
# urban_extraction_tool = StructuredTool.from_function(
#     func=extract_urban_area_with_optimal_threshold,
#     name="extract_urban_area_use_change_point",
#     description="使用突变点检测法从 NTL 影像中自动提取建成区。输入和输出均只需提供文件名。",
#     args_schema=UrbanExtractionInput
# )

import json
import os
from pathlib import Path
from typing import Optional

import geopandas as gpd
import rasterio
import numpy as np
import cv2
from langchain_core.tools import StructuredTool
from pydantic.v1 import BaseModel, Field
from storage_manager import storage_manager, current_thread_id
from langchain_core.runnables import RunnableConfig
from rasterio.features import geometry_mask
from shapely.geometry import mapping
from shapely.ops import unary_union

# Keep thresholded-area reporting consistent with the public zonal-statistics
# tool.  In particular, this is WGS84 geodesic area rather than a degree-grid
# affine determinant for geographic NTL rasters.
from tools.NTL_raster_stats import _pixel_area_grid_km2

# --- Core Algorithm Functions ---
def read_tif(path):
    with rasterio.open(path) as src:
        image = src.read(1).astype(np.float32)
    return image

def calculate_perimeter(binary_image):
    contours, _ = cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    perimeter = sum(cv2.arcLength(cnt, True) for cnt in contours)
    return perimeter

def analyze_thresholds(image, num_thresholds=64, valid_mask=None):
    """Derive perimeter-change thresholds without treating NoData as signal."""

    image = np.asarray(image, dtype=np.float64)
    if valid_mask is None:
        valid_mask = np.isfinite(image)
    else:
        valid_mask = np.asarray(valid_mask, dtype=bool) & np.isfinite(image)
    if image.ndim != 2 or valid_mask.shape != image.shape:
        raise ValueError("Threshold analysis requires matching two-dimensional image and validity mask.")
    if not np.any(valid_mask):
        raise ValueError("Input raster has no valid finite pixels for threshold analysis.")

    min_val = float(np.min(image[valid_mask]))
    max_val = float(np.max(image[valid_mask]))
    thresholds = np.linspace(min_val, max_val, num_thresholds)
    perimeters = []
    for t in thresholds:
        binary = np.zeros(image.shape, dtype=np.uint8)
        binary[valid_mask & (image > t)] = 255
        perimeter = calculate_perimeter(binary)
        perimeters.append(perimeter)
    return thresholds, perimeters

def find_optimal_threshold(thresholds, perimeters):
    # Change-point detection logic based on perimeter-threshold curve
    for i in range(1, len(perimeters)):
        if perimeters[i] > perimeters[i - 1] and all(
            perimeters[j] > perimeters[j - 1] for j in range(i, min(i + 3, len(perimeters)))
        ):
            return thresholds[i]
    return thresholds[np.argmax(perimeters)]

# --- Input Schema ---
class UrbanExtractionInput(BaseModel):
    tif_filename: str = Field(..., description="The filename of the input NTL GeoTIFF located in 'inputs/' (e.g., 'ntl_2020.tif').")
    output_filename: str = Field(..., description="The filename for the resulting urban mask to be saved in 'outputs/' (e.g., 'shanghai_urban_mask.tif').")
    threshold: Optional[float] = Field(
        default=None,
        description=(
            "Optional fixed NTL threshold. When supplied, valid pixels with NTL >= threshold "
            "are classed as built-up. When omitted, the legacy perimeter change-point threshold "
            "is estimated from valid source pixels."
        ),
    )
    aoi_boundary: Optional[str] = Field(
        default=None,
        description=(
            "Optional polygon boundary in inputs/. The mask uses pixel-centre inclusion "
            "(all_touched=False); pixels outside it are output as NoData=255."
        ),
    )
    statistics_filename: Optional[str] = Field(
        default=None,
        description=(
            "Optional JSON filename in outputs/ for threshold, pixel-count, fraction, and "
            "WGS84-geodesic built-up-area statistics. Defaults beside output_filename."
        ),
    )


def _read_valid_ntl(source: rasterio.io.DatasetReader) -> np.ndarray:
    """Read one NTL band, excluding declared NoData and every non-finite value.

    Rasterio's masked read handles a declared finite or NaN NoData value.  The
    explicit finite check also prevents ``+/-inf`` from being silently treated
    as a thresholdable radiance.  Valid zeroes intentionally remain finite.
    """

    if source.count < 1:
        raise ValueError("Raster contains no bands.")
    masked = source.read(1, masked=True).astype(np.float64)
    values = np.asarray(masked.filled(np.nan), dtype=np.float64)
    values[~np.isfinite(values)] = np.nan
    return values


def _aoi_pixel_centre_mask(
    source: rasterio.io.DatasetReader,
    aoi_path: Optional[Path],
) -> np.ndarray:
    """Return the requested AOI mask using source-grid pixel centres."""

    if aoi_path is None:
        return np.ones((source.height, source.width), dtype=bool)
    if source.crs is None:
        raise ValueError("Raster has no CRS; cannot align an AOI boundary or calculate geodesic area.")

    boundary = gpd.read_file(aoi_path)
    if boundary.empty:
        raise ValueError("AOI boundary contains no features.")
    if boundary.crs is None:
        raise ValueError("AOI boundary has no CRS.")
    if boundary.geometry.isna().any() or boundary.geometry.is_empty.any():
        raise ValueError("AOI boundary contains missing or empty geometry.")
    if not bool(boundary.geometry.is_valid.all()):
        raise ValueError("AOI boundary contains invalid geometry.")
    if boundary.crs != source.crs:
        boundary = boundary.to_crs(source.crs)

    union_geometry = unary_union(boundary.geometry)
    return geometry_mask(
        [mapping(union_geometry)],
        out_shape=(source.height, source.width),
        transform=source.transform,
        invert=True,
        all_touched=False,
    )


def _default_statistics_filename(output_filename: str) -> str:
    """Derive a sibling JSON without assuming an absolute host path."""

    output = Path(str(output_filename).replace("\\", "/"))
    return str(output.with_name(f"{output.stem}_statistics.json"))


def _format_threshold(threshold: float) -> str:
    return format(float(threshold), ".12g")


def _write_threshold_statistics(
    path: Path,
    *,
    tif_filename: str,
    output_filename: str,
    aoi_boundary: Optional[str],
    threshold: float,
    threshold_source: str,
    valid: np.ndarray,
    built: np.ndarray,
    area_grid_km2: np.ndarray,
    source_crs: Optional[str],
) -> dict:
    valid_count = int(np.count_nonzero(valid))
    built_count = int(np.count_nonzero(built))
    non_built_count = int(np.count_nonzero(valid & ~built))
    if valid_count == 0:
        raise ValueError("The requested AOI contains no valid finite NTL pixels.")
    statistics = {
        "schema": "ntl.thresholded_built_up.v1",
        "input": {
            "path": str(tif_filename),
            "crs": source_crs,
            "band": 1,
        },
        "aoi": {
            "path": str(aoi_boundary) if aoi_boundary else None,
            "inclusion": "raster pixel centre lies within the AOI geometry",
            "all_touched": False,
        },
        "method": {
            "threshold": float(threshold),
            "threshold_source": threshold_source,
            "comparison": f"NTL >= {_format_threshold(threshold)}",
            "validity_rule": "exclude declared NoData and non-finite values; retain valid zero-valued pixels",
            "built_up_rule": "valid NTL >= threshold",
            "pixel_area": "WGS84 geodesic source-pixel area in km2",
        },
        "output": {
            "mask_path": str(output_filename),
            "classes": {"built_up": 1, "non_built": 0, "nodata": 255},
            "outside_aoi": 255,
        },
        "result": {
            "aoi_valid_pixel_count": valid_count,
            "built_up_pixel_count": built_count,
            "non_built_pixel_count": non_built_count,
            "built_up_fraction": float(built_count / valid_count),
            "built_up_area_km2": float(np.sum(area_grid_km2[built], dtype=np.float64)),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(statistics, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return statistics

# --- Main Tool Function ---
def extract_urban_area_by_thresholding(
    tif_filename: str,
    output_filename: str,
    threshold: Optional[float] = None,
    aoi_boundary: Optional[str] = None,
    statistics_filename: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Extract built-up areas from NTL imagery with either a caller-supplied
    threshold or the legacy perimeter change-point threshold.
    """
    thread_id = storage_manager.get_thread_id_from_config(config) if config else None
    abs_input_path = storage_manager.resolve_input_path(tif_filename, thread_id)
    abs_output_path = storage_manager.resolve_output_path(output_filename, thread_id)
    abs_aoi_path = (
        Path(storage_manager.resolve_input_path(aoi_boundary, thread_id))
        if aoi_boundary
        else None
    )
    statistics_filename = statistics_filename or _default_statistics_filename(output_filename)
    abs_statistics_path = Path(
        storage_manager.resolve_output_path(statistics_filename, thread_id)
    )

    if not os.path.exists(abs_input_path):
        return f"Error: The file '{tif_filename}' was not found in the 'inputs/' folder."
    if abs_aoi_path is not None and not abs_aoi_path.exists():
        return f"Error: The AOI boundary '{aoi_boundary}' was not found in the 'inputs/' folder."
    if threshold is not None and not np.isfinite(float(threshold)):
        return "Error: threshold must be a finite number."

    try:
        with rasterio.open(abs_input_path) as src:
            values = _read_valid_ntl(src)
            profile = src.profile.copy()
            source_crs = src.crs.to_string() if src.crs else None
            aoi_mask = _aoi_pixel_centre_mask(src, abs_aoi_path)
            valid = aoi_mask & np.isfinite(values)
            if not np.any(valid):
                raise ValueError("The requested AOI contains no valid finite NTL pixels.")

            if threshold is None:
                thresholds, perimeters = analyze_thresholds(values, valid_mask=valid)
                applied_threshold = float(find_optimal_threshold(thresholds, perimeters))
                threshold_source = "perimeter_change_point"
            else:
                applied_threshold = float(threshold)
                threshold_source = "caller_supplied"

            built = valid & (values >= applied_threshold)
            urban_mask = np.full(values.shape, 255, dtype=np.uint8)
            urban_mask[valid] = 0
            urban_mask[built] = 1
            area_grid_km2 = _pixel_area_grid_km2(src)

            profile.update(
                dtype=rasterio.uint8,
                count=1,
                nodata=255,
                compress="DEFLATE",
                predictor=2,
            )

        with rasterio.open(abs_output_path, "w", **profile) as dst:
            dst.write(urban_mask, 1)
            dst.update_tags(
                method="thresholded built-up mask: valid NTL >= threshold",
                threshold=_format_threshold(applied_threshold),
                threshold_source=threshold_source,
                aoi_inclusion="pixel-centre",
                nodata_semantics="declared source NoData and non-finite values excluded; output NoData=255",
            )

        statistics = _write_threshold_statistics(
            abs_statistics_path,
            tif_filename=tif_filename,
            output_filename=output_filename,
            aoi_boundary=aoi_boundary,
            threshold=applied_threshold,
            threshold_source=threshold_source,
            valid=valid,
            built=built,
            area_grid_km2=area_grid_km2,
            source_crs=source_crs,
        )

        return (f"✅ Success! Applied Threshold: {_format_threshold(applied_threshold)}\n"
                f"- Input: {tif_filename}\n"
                f"- Built-up pixels: {statistics['result']['built_up_pixel_count']} of "
                f"{statistics['result']['aoi_valid_pixel_count']} valid AOI pixels\n"
                f"- Built-up area (WGS84 geodesic): {statistics['result']['built_up_area_km2']:.12g} km²\n"
                f"- Output mask: {output_filename}\n"
                f"- Statistics JSON: {statistics_filename}")
                
    except Exception as e:
        return f"Error during urban extraction: {str(e)}"

# --- Tool Registration ---
urban_extraction_by_thresholding_tool = StructuredTool.from_function(
    func=extract_urban_area_by_thresholding,
    name="Extract_Urban_Area_by_Thresholding",
    description=(
        "Extracts a thresholded built-up-area mask from a nighttime-light GeoTIFF. Supply `threshold` for a "
        "reproducible rule (valid NTL >= threshold); omit it only when the legacy perimeter change-point threshold "
        "is intended. An optional polygon AOI uses pixel-centre containment. Declared NoData and non-finite values "
        "are excluded while valid zeroes remain, and the tool writes a uint8 mask (1 built-up, 0 non-built, "
        "255 NoData) plus JSON pixel-count/fraction/WGS84-geodesic area statistics in outputs/."
    ),
    args_schema=UrbanExtractionInput
)


import os
import joblib
import rasterio
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic.v1 import BaseModel, Field
from storage_manager import storage_manager

# --- Input Schema ---
class SVMExtractionInput(BaseModel):
    tif_filename: str = Field(..., description="The filename of the input NTL raster in 'inputs/' (e.g., 'shanghai_ntl.tif').")
    output_filename: str = Field(..., description="The target filename for the SVM classification result in 'outputs/' (e.g., 'urban_svm_mask.tif').")

# --- Main Tool Function ---
def detect_urban_area_by_svm(tif_filename: str, output_filename: str, config: RunnableConfig = None) -> str:
    """
    Extracts urban built-up areas from NTL imagery using a pre-trained Support Vector Machine (SVM) model.
    """
    # Resolve absolute paths using storage_manager
    thread_id = storage_manager.get_thread_id_from_config(config) if config else None
    
    if not thread_id:
        thread_id = current_thread_id.get()
        print(f"[DEBUG] Thread ID missing in config. Fallback to contextvar: {thread_id}")
    
    # Debug info
    print(f"[DEBUG] SVM Tool Called. Config present: {config is not None}")
    print(f"[DEBUG] Extracted thread_id: {thread_id}")
    
    abs_input_path = storage_manager.resolve_input_path(tif_filename, thread_id)
    abs_output_path = storage_manager.resolve_output_path(output_filename, thread_id)
    
    print(f"[DEBUG] Resolved input path: {abs_input_path}")
    print(f"[DEBUG] Input path exists: {os.path.exists(str(abs_input_path))}")

    # Path for pre-trained assets
    model_path = os.path.join("./assets/models", "svm_built_up_model.joblib")
    scaler_path = os.path.join("./assets/models", "svm_scaler.joblib")

    # --- 修改后的 Validations 部分 ---
    # 使用 os.path.exists() 来检查字符串路径是否存在
    if not os.path.exists(str(abs_input_path)):
        return f"Error: Input file '{tif_filename}' not found in 'inputs/' folder."
    
    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        return "Error: Internal SVM model or Scaler assets are missing from the system."

    try:
        # 1. Load assets
        model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)

        # 2. Read NTL data
        with rasterio.open(abs_input_path) as src:
            raw_data = src.read(1).astype('float32')
            profile = src.profile
            nodata_val = src.nodata

        # 3. Masking and Vectorization
        valid_mask = (raw_data != nodata_val) & (~np.isnan(raw_data))
        X_to_predict = raw_data[valid_mask].reshape(-1, 1)

        # 4. Feature Scaling & Prediction
        X_scaled = scaler.transform(X_to_predict)
        predictions = model.predict(X_scaled)

        # 5. Spatial Reconstruction
        # 0: Non-Urban, 1: Urban, -1: Background/NoData
        result_mask = np.full(raw_data.shape, -1, dtype='int16')
        result_mask[valid_mask] = predictions

        # 6. Save Output
        profile.update(dtype=rasterio.int16, count=1, nodata=-1)

        with rasterio.open(abs_output_path, "w", **profile) as dst:
            dst.write(result_mask.astype(rasterio.int16), 1)

        return (f"✅ Success! SVM classification completed.\n"
                f"- Input: {tif_filename}\n"
                f"- Result saved: outputs/{output_filename}")
                
    except Exception as e:
        return f"Error during SVM urban extraction: {str(e)}"

# --- Tool Registration ---
svm_urban_extraction_tool = StructuredTool.from_function(
    func=detect_urban_area_by_svm,
    name="Detect_Urban_Area_by_SVM",
    description=(
        "Extracts urban built-up areas from nighttime light (NTL) imagery using a pre-trained Support Vector Machine (SVM) classifier. "
        "The tool applies machine learning to differentiate urban from non-urban pixels based on intensity scaling. "
        "Ideal for high-accuracy urban boundary mapping in complex urban environments."
    ),
    args_schema=SVMExtractionInput,
    # IMPORTANT: Enable config injection
    # This tells LangChain to pass the RunnableConfig to the tool
)

import os
import rasterio
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic.v1 import BaseModel, Field
from storage_manager import storage_manager

# --- Input Schema ---
class ElectrifiedDetectionInput(BaseModel):
    input_tif: str = Field(
        ..., 
        description="Filename of the preprocessed grayscale SDGSAT-1 image in 'inputs/' (e.g., 'calibrated_ntl.tif')."
    )
    output_tif: str = Field(
        ..., 
        description="Filename for the resulting electrification mask in 'outputs/' (e.g., 'electrified_mask.tif')."
    )

# --- Main Tool Function ---
def detect_electrified_areas_by_thresholding(input_tif: str, output_tif: str, config: RunnableConfig = None) -> str:
    """
    Detects electrified regions by applying a threshold to nighttime light (NTL) imagery.
    Supports SDG 7.1.1 monitoring for universal electricity access.
    """
    # Resolve absolute paths
    thread_id = storage_manager.get_thread_id_from_config(config) if config else None
    abs_input_path = storage_manager.resolve_input_path(input_tif, thread_id)
    abs_output_path = storage_manager.resolve_output_path(output_tif, thread_id)
    threshold = 0.001
    if not os.path.exists(abs_input_path):
        return f"Error: Input file '{input_tif}' not found in 'inputs/' directory."

    try:
        # Read the grayscale NTL data
        with rasterio.open(abs_input_path) as src:
            data = src.read(1).astype(np.float32)
            profile = src.profile
            nodata = src.nodata

        # Apply thresholding
        # Values >= threshold are classified as electrified (1), others as non-electrified (0)
        # Note: We must exclude existing NoData or NaN values
        valid_mask = (data != nodata) & (~np.isnan(data))
        electrified_mask = np.zeros_like(data, dtype=np.uint8)
        electrified_mask[valid_mask & (data >= threshold)] = 1

        # Update metadata for binary mask
        profile.update(
            dtype=rasterio.uint8,
            count=1,
            nodata=0,  # 0 is used for non-electrified or background
            compress='lzw'
        )

        # Save result
        with rasterio.open(abs_output_path, "w", **profile) as dst:
            dst.write(electrified_mask, 1)

        return (f"✅ Electrification detection completed.\n"
                f"- Input Image: {input_tif}\n"
                f"- Result saved to: outputs/{output_tif}")

    except Exception as e:
        return f"Error during electrification detection: {str(e)}"

# --- Tool Registration ---
electrified_detection_tool = StructuredTool.from_function(
    func=detect_electrified_areas_by_thresholding,
    name="Detect_Electrified_Areas_by_Thresholding",
    description=(
        "Detects regions with access to electricity from preprocessed SDGSAT-1 grayscale imagery. "
        "It segments electrified from non-electrified areas using a threshold determined as the average "
        "of the maximum NTL value in non-electrified zones and the minimum NTL value in electrified zones. "
        "This tool supports the monitoring of SDG Indicator 7.1.1 (Universal access to electricity)."
        "\n\nExample:\n"
        "input_tif='calibrated_sdgsat.tif',\n"
        "output_tif='electrified_mask.tif',\n"
    ),
    args_schema=ElectrifiedDetectionInput
)

from pathlib import Path

from ntl_toolkit.core.urban_structure import (
    CHEN2017_SHANGHAI_2014_CONFIG,
    detect_urban_centres,
)


class UrbanStructureInput(BaseModel):
    ntl_tif: str = Field(
        ...,
        description="The single-band projected NTL radiance GeoTIFF in the workspace inputs/ folder.",
    )
    aoi_boundary: Optional[str] = Field(
        None,
        description="The polygon AOI boundary in inputs/. Required unless a default Shanghai boundary exists in inputs/.",
    )
    output_shp: str = Field(
        ...,
        description="Vector output filename (.shp, .gpkg, or .geojson) saved in outputs/.",
    )
    output_csv: str = Field(
        ...,
        description="Center attributes and hierarchy CSV filename saved in outputs/.",
    )
    metadata_json: Optional[str] = Field(
        None,
        description="Optional run metadata JSON filename saved in outputs/. Defaults beside output_csv.",
    )
    base_threshold: float = Field(
        34.0,
        description="Base NTL contour value in nW/cm^2/sr; Chen 2017 Shanghai setting is 34.",
    )
    contour_interval: float = Field(
        1.0,
        description="NTL contour interval in nW/cm^2/sr; Chen 2017 Shanghai setting is 1.",
    )
    min_area_km2: float = Field(
        5.0,
        description="Minimum closed-contour area in km^2; Chen 2017 setting is 5.",
    )
    gaussian_sigma: float = Field(
        1.0,
        description="Sigma for the fixed 3x3 Gaussian filter.",
    )
    aoi_buffer_km: float = Field(
        10.0,
        description="Required raster coverage beyond the AOI boundary in kilometres.",
    )
    radiance_unit: Optional[str] = Field(
        None,
        description="Explicit unit override only when the raster metadata lacks a unit tag; expected nW/cm^2/sr.",
    )
    parameter_profile: Optional[str] = Field(
        CHEN2017_SHANGHAI_2014_CONFIG["profile"],
        description="Fixed reproducibility profile, chen2017_shanghai_2014, or null for generic tests.",
    )


def _default_shanghai_boundary(thread_id: Optional[str]) -> Optional[Path]:
    """Find an explicit default boundary without inventing an AOI."""

    workspace = Path(storage_manager.get_workspace(thread_id))
    candidates = (
        workspace / "inputs" / "shanghai_boundary.geojson",
        workspace / "inputs" / "shanghai_boundary.gpkg",
        workspace / "inputs" / "shanghai_boundary.shp",
    )
    return next((candidate for candidate in candidates if candidate.exists()), None)


def detect_urban_centres_logic(
    ntl_tif: str,
    output_shp: str,
    output_csv: str,
    aoi_boundary: Optional[str] = None,
    metadata_json: Optional[str] = None,
    base_threshold: float = 34.0,
    contour_interval: float = 1.0,
    min_area_km2: float = 5.0,
    gaussian_sigma: float = 1.0,
    aoi_buffer_km: float = 10.0,
    radiance_unit: Optional[str] = None,
    parameter_profile: Optional[str] = CHEN2017_SHANGHAI_2014_CONFIG["profile"],
    config: RunnableConfig = None,
) -> str:
    """Resolve workspace paths and run the deterministic core algorithm."""

    thread_id = storage_manager.get_thread_id_from_config(config) if config else None
    try:
        input_path = Path(storage_manager.resolve_input_path(ntl_tif, thread_id))
        if aoi_boundary:
            aoi_path = Path(storage_manager.resolve_input_path(aoi_boundary, thread_id))
        else:
            aoi_path = _default_shanghai_boundary(thread_id)
            if aoi_path is None:
                return "Error [AOI_REQUIRED]: Provide a Shanghai polygon boundary in the inputs/ workspace."
        vector_path = Path(storage_manager.resolve_output_path(output_shp, thread_id))
        csv_path = Path(storage_manager.resolve_output_path(output_csv, thread_id))
        metadata_path = (
            Path(storage_manager.resolve_output_path(metadata_json, thread_id))
            if metadata_json
            else csv_path.with_name(f"{csv_path.stem}.metadata.json")
        )
    except (OSError, PermissionError, ValueError) as exc:
        return f"Error [PATH_RESOLUTION_FAILED]: {exc}"

    result = detect_urban_centres(
        input_path,
        aoi_path,
        vector_path,
        csv_path,
        metadata_path,
        base_threshold=base_threshold,
        contour_interval=contour_interval,
        min_area_km2=min_area_km2,
        gaussian_kernel=3,
        gaussian_sigma=gaussian_sigma,
        aoi_buffer_km=aoi_buffer_km,
        expected_unit=radiance_unit,
        parameter_profile=parameter_profile,
    )
    if result.status != "succeeded":
        error = result.error
        code = error.code if error is not None else "PROCESSING_FAILED"
        message = error.message if error is not None else result.summary
        return f"Error [{code}]: {message}"

    output_lines = [
        f"Success: {result.summary}",
        *[f"- {artifact.role}: {artifact.path}" for artifact in result.outputs],
    ]
    return "\n".join(output_lines)

# 3. 封装为 StructuredTool
detect_urban_centres_tool = StructuredTool.from_function(
    func=detect_urban_centres_logic,
    name="Detect_Urban_Centres_and_Spatial_Structure",
    description=(
        "An advanced geospatial analysis tool that identifies urban centers and their hierarchical relationships. "
        "It uses the localized NTL contour tree algorithm to distinguish between primary and sub-centers based on "
        "topological depth and radiance intensity. Ideal for studying polycentric urban development and "
        "spatial structure evolution using high-precision nighttime light data."
    ),
    args_schema=UrbanStructureInput,
)

# 示例：Agent 内部查看工具定义
# print(detect_urban_centres_tool.name)
# print(detect_urban_centres_tool.description)
# print(detect_urban_centres_tool.args)
# import os
# import rasterio
# import numpy as np
# import cv2
# import matplotlib.pyplot as plt
# from langchain_core.tools import StructuredTool
# from pydantic.v1 import BaseModel, Field


# def read_tif(path):
#     with rasterio.open(path) as src:
#         image = src.read(1).astype(np.float32)
#     return image

# def calculate_perimeter(binary_image):
#     contours, _ = cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
#     perimeter = sum(cv2.arcLength(cnt, True) for cnt in contours)
#     return perimeter

# def analyze_thresholds(image, num_thresholds=64):
#     min_val = image.min()
#     max_val = image.max()
#     thresholds = np.linspace(min_val, max_val, num_thresholds)
#     perimeters = []
#     for t in thresholds:
#         binary = np.uint8((image > t) * 255)
#         perimeter = calculate_perimeter(binary)
#         perimeters.append(perimeter)
#     return thresholds, perimeters

# def find_optimal_threshold(thresholds, perimeters):
#     for i in range(1, len(perimeters)):
#         if perimeters[i] > perimeters[i - 1] and all(
#             perimeters[j] > perimeters[j - 1] for j in range(i, min(i + 3, len(perimeters)))
#         ):
#             return thresholds[i]
#     return thresholds[np.argmax(perimeters)]

# # ====================== 参数模型 ======================

# class UrbanExtractionInput(BaseModel):
#     tif_path: str = Field(..., description="输入的夜间灯光影像路径")
#     output_path: str = Field(..., description="输出的建成区掩膜图像路径")

# # ====================== 合并工具函数 ======================

# def extract_urban_area_with_optimal_threshold(tif_path: str, output_path: str) -> str:
#     # Step 1: 读取影像并计算最佳阈值
#     image = read_tif(tif_path)
#     thresholds, perimeters = analyze_thresholds(image)
#     optimal_threshold = find_optimal_threshold(thresholds, perimeters)
#     print(f"最佳阈值为：{optimal_threshold}")

#     # Step 2: 生成建成区掩膜
#     with rasterio.open(tif_path) as src:
#         raw = src.read(1)
#         profile = src.profile

#     urban_mask = raw >= optimal_threshold
#     profile.update(dtype=rasterio.uint8, count=1)

#     with rasterio.open(output_path, "w", **profile) as dst:
#         dst.write(urban_mask.astype(rasterio.uint8), 1)

#     print(f"建成区掩膜图像已保存至：{os.path.abspath(output_path)}")
#     return f"Optimal threshold = {optimal_threshold:.2f}\nMask saved to: {os.path.abspath(output_path)}"


# urban_extraction_tool = StructuredTool.from_function(
#     func=extract_urban_area_with_optimal_threshold,
#     name="extract_urban_area_use_change_point",
#     description="""
#     Automatically extract built-up areas from nighttime light (NTL) imagery using a change-point detection method, and export a binary mask.
    
#     **Input:**
#     - `tif_path`: Path to the input NTL image (.tif, single-band, float32)
#     - `output_path`: Path to save the output binary built-up area mask (.tif)
    
#     **Output:**
#     - A binary mask GeoTIFF (1 = built-up, 0 = non-built-up)
#     - Text output indicating the optimal threshold and saved file path
    
#     **Example:**
#     Input:
#       tif_path = "./NTL_Agent/Night_data/Shanghai/NTL_2020.tif"
#       output_path = "./NTL_Agent/Night_data/Shanghai/urban_mask_2020.tif"
    
#     Output:
#       Optimal threshold = 38.75
#       Mask saved to: ./NTL_Agent/Night_data/Shanghai/urban_mask_2020.tif
#     """,
#     input_type=UrbanExtractionInput,
# )

# extract_urban_area_with_optimal_threshold(
#     tif_path="./NTL_Agent/Night_data/上海市/Annual/NTL_上海市_VIIRS_2020.tif",
#     output_path="./NTL_Agent/Night_data/上海市/Annual/urban_mask_2020.tif"
# )

# 示例调用方式（实际使用中由 LangChain Agent 调用）
# result1 = detect_optimal_urban_threshold.run({"tif_path": "./NTL_Agent/Night_data/上海市/Annual/NTL_上海市_VIIRS_2020.tif"})
# result2 = generate_urban_mask_by_threshold.run({
#     "tif_path": "./NTL_Agent/Night_data/上海市/Annual/NTL_上海市_VIIRS_2020.tif",
#     "output_path": "./NTL_Agent/Night_data/上海市/Annual/urban_mask.tif",
#     "optimal_threshold": result1
# })

# with rasterio.open("urban_mask.tif") as src:
#     image = src.read(1)  # 读取第一个波段，假设是单波段灰度图
#     profile = src.profile
#
# # 可视化城市区域掩膜
# plt.figure(figsize=(8, 6))
# plt.imshow(image, cmap='gray')
# plt.title("Extracted Urban Area (Binary Mask)")
# plt.axis('off')  # 关闭坐标轴
# plt.show()
