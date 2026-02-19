import os
import rasterio
import numpy as np
import cv2

def read_tif(path):
    with rasterio.open(path) as src:
        image = src.read(1).astype(np.float32)
        nodata = src.nodata
    return image, nodata

def calculate_perimeter(binary_image):
    contours, _ = cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    perimeter = sum(cv2.arcLength(cnt, True) for cnt in contours)
    return perimeter

def analyze_thresholds(image, nodata, num_thresholds=64):
    valid_pixels = image[image != nodata]
    min_val = valid_pixels.min()
    max_val = valid_pixels.max()
    thresholds = np.linspace(min_val, max_val, num_thresholds)
    perimeters = []
    for t in thresholds:
        binary = np.uint8((image > t) * 255)
        perimeter = calculate_perimeter(binary)
        perimeters.append(perimeter)
    return thresholds, perimeters

def find_optimal_threshold(thresholds, perimeters):
    # 这里保持原有逻辑不变
    for i in range(1, len(perimeters)):
        if perimeters[i] > perimeters[i - 1] and all(
            perimeters[j] > perimeters[j - 1] for j in range(i, min(i + 3, len(perimeters)))
        ):
            return thresholds[i]
    return thresholds[np.argmax(perimeters)]

def extract_urban_area_with_optimal_threshold(tif_path: str, output_path: str) -> str:
    # Step 1: 读取影像及NoData值，并计算最佳阈值
    image, nodata = read_tif(tif_path)
    thresholds, perimeters = analyze_thresholds(image, nodata)
    optimal_threshold = find_optimal_threshold(thresholds, perimeters)
    print(f"最佳阈值为：{optimal_threshold}")

    # Step 2: 生成建成区掩膜并忽略NoData值
    urban_mask = (image >= optimal_threshold) & (image != nodata)
    
    # 计算建成区比例
    valid_area = np.sum(image != nodata)
    built_up_area = np.sum(urban_mask)
    built_up_ratio = built_up_area / valid_area
    
    print(f"建成区比例为：{built_up_ratio:.2%}")
    
    # 写入结果
    with rasterio.open(tif_path) as src:
        profile = src.profile
        profile.update(dtype=rasterio.uint8, count=1)

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(urban_mask.astype(rasterio.uint8), 1)

    print(f"建成区掩膜图像已保存至：{os.path.abspath(output_path)}")
    return f"Optimal threshold = {optimal_threshold:.2f}\nBuilt-up area ratio = {built_up_ratio:.2%}\nMask saved to: {os.path.abspath(output_path)}"

# extract_urban_area_with_optimal_threshold(tif_path="./NTL_Agent/Night_data/上海市/Annual/NTL_上海市_VIIRS_2020.tif",
#     output_path="./NTL_Agent/Night_data/上海市/Annual/urban_mask_2020.tif")

extract_urban_area_with_optimal_threshold(tif_path="C:\\NTL_Agent\\NPP_VIIRS_2020_MASK.tif",
    output_path="C:\\NTL_Agent\\NPP_VIIRS_2020_urban_MASK.tif")