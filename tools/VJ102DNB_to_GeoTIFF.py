"""
VJ102DNB + VJ103DNB 转 GeoTIFF 工具

将 VIIRS DNB 辐射数据与几何数据结合，生成带有地理坐标的 GeoTIFF 文件
"""

import h5py
import numpy as np
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import json
from datetime import datetime


def read_vj102dnb_data(nc_file: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    读取 VJ102DNB 辐射数据
    
    Returns:
        radiance: 辐射数据数组
        metadata: 元数据
    """
    with h5py.File(nc_file, 'r') as f:
        if 'observation_data/DNB_observations' not in f:
            raise ValueError(f"未找到辐射数据：{nc_file.name}")
        
        radiance = f['observation_data/DNB_observations'][:]
        
        # 读取质量控制
        qf = None
        if 'observation_data/DNB_quality_flags' in f:
            qf = f['observation_data/DNB_quality_flags'][:]
        
        # 元数据
        metadata = {
            'radiance_shape': radiance.shape,
            'qf_shape': qf.shape if qf is not None else None,
        }
        
        # 读取全局属性
        for attr in f.attrs:
            metadata[attr] = str(f.attrs[attr])
    
    return radiance, metadata


def read_vj103dnb_geo(nc_file: Path) -> Dict[str, np.ndarray]:
    """
    读取 VJ103DNB 几何数据
    
    Returns:
        包含经纬度等几何数据的字典
    """
    geo_data = {}
    
    with h5py.File(nc_file, 'r') as f:
        # 读取经纬度
        if 'geolocation_data/latitude' in f:
            geo_data['latitude'] = f['geolocation_data/latitude'][:]
        if 'geolocation_data/longitude' in f:
            geo_data['longitude'] = f['geolocation_data/longitude'][:]
        
        # 读取其他几何参数
        for key in ['sensor_zenith', 'sensor_azimuth', 'solar_zenith', 'solar_azimuth']:
            ds_path = f'geolocation_data/{key}'
            if ds_path in f:
                geo_data[key] = f[ds_path][:]
        
        # 读取质量标志
        if 'geolocation_data/quality_flag' in f:
            geo_data['quality_flag'] = f['geolocation_data/quality_flag'][:]
        
        # 读取全局属性
        for attr in f.attrs:
            geo_data[f'attr_{attr}'] = str(f.attrs[attr])
    
    return geo_data


def match_vj102_vj103(vj102_file: Path, vj103_files: list) -> Optional[Path]:
    """
    为 VJ102DNB 文件匹配对应的 VJ103DNB 文件
    
    匹配规则：相同日期时间（精确到分钟）
    """
    vj102_time = vj102_file.name.split('.')[1:4]  # A2026058.0000.021
    
    for vj103_file in vj103_files:
        vj103_time = vj103_file.name.split('.')[1:4]
        if vj102_time == vj103_time:
            return vj103_file
    
    return None


def create_geotiff(
    radiance: np.ndarray,
    latitude: np.ndarray,
    longitude: np.ndarray,
    output_path: Path,
    metadata: Optional[Dict] = None
):
    """
    创建带有地理坐标的 TIFF 文件
    
    注意：由于 VIIRS 是扫描 swath 数据，不是规则网格，
    我们保存为包含经纬度数组的多波段 TIFF
    """
    try:
        from osgeo import gdal, osr
        import struct
        
        use_gdal = True
    except ImportError:
        use_gdal = False
        print("⚠️ 警告：未找到 GDAL，将保存为包含经纬度的 numpy 格式")
    
    if use_gdal:
        # 使用 GDAL 创建 GeoTIFF
        rows, cols = radiance.shape
        
        # 创建临时文件用于存储经纬度和辐射
        driver = gdal.GetDriverByName('GTiff')
        
        # 创建 3 波段 TIFF：波段 1=辐射，波段 2=纬度，波段 3=经度
        geotiff_path = str(output_path.with_suffix('.tif'))
        dataset = driver.Create(geotiff_path, cols, rows, 3, gdal.GDT_Float32)
        
        # 波段 1: 辐射数据
        dataset.GetRasterBand(1).WriteArray(radiance)
        dataset.GetRasterBand(1).SetDescription('radiance')
        dataset.GetRasterBand(1).SetMetadataItem('units', 'W cm-2 sr-1')
        
        # 波段 2: 纬度
        dataset.GetRasterBand(2).WriteArray(latitude)
        dataset.GetRasterBand(2).SetDescription('latitude')
        dataset.GetRasterBand(2).SetMetadataItem('units', 'degrees_north')
        
        # 波段 3: 经度
        dataset.GetRasterBand(3).WriteArray(longitude)
        dataset.GetRasterBand(3).SetDescription('longitude')
        dataset.GetRasterBand(3).SetMetadataItem('units', 'degrees_east')
        
        # 设置地理变换（近似，使用中心点和平均分辨率）
        center_lat = np.nanmean(latitude)
        center_lon = np.nanmean(longitude)
        
        # 估算分辨率（度/像素）
        lat_range = np.nanmax(latitude) - np.nanmin(latitude)
        lon_range = np.nanmax(longitude) - np.nanmin(longitude)
        lat_res = lat_range / rows if rows > 0 else 0.0075
        lon_res = lon_range / cols if cols > 0 else 0.0075
        
        # 设置地理变换
        geotransform = (
            center_lon - cols * lon_res / 2,  # 左上角经度
            lon_res,  # 东西方向分辨率
            0,
            center_lat + rows * lat_res / 2,  # 左上角纬度
            0,
            -lat_res  # 南北方向分辨率（负值表示从北向南）
        )
        dataset.SetGeoTransform(geotransform)
        
        # 设置坐标参考系统（WGS84）
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        dataset.SetProjection(srs.ExportToWkt())
        
        # 设置元数据
        if metadata:
            meta_dict = dataset.GetMetadata()
            for key, value in metadata.items():
                if isinstance(value, str) and len(value) < 1000:
                    meta_dict[f'{key}'] = value
            dataset.SetMetadata(meta_dict)
        
        # 关闭数据集
        dataset = None
        
        print(f"  ✅ GeoTIFF: {output_path.name}")
        
    else:
        # 不使用 GDAL，保存为 numpy 格式
        npz_path = output_path.with_suffix('.npz')
        np.savez_compressed(
            npz_path,
            radiance=radiance,
            latitude=latitude,
            longitude=longitude,
            metadata=metadata
        )
        print(f"  ✅ NPZ: {npz_path.name}")
        
        geotiff_path = npz_path
    
    return geotiff_path


def process_pair(
    vj102_file: Path,
    vj103_file: Path,
    output_dir: Path
) -> Dict[str, Any]:
    """
    处理一对 VJ102DNB + VJ103DNB 文件
    
    Args:
        vj102_file: VJ102DNB 辐射数据文件
        vj103_file: VJ103DNB 几何数据文件
        output_dir: 输出目录
        
    Returns:
        处理结果字典
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n处理配对:")
    print(f"  辐射：{vj102_file.name}")
    print(f"  几何：{vj103_file.name}")
    
    # 读取辐射数据
    radiance, rad_meta = read_vj102dnb_data(vj102_file)
    print(f"  ✅ 辐射数据形状：{radiance.shape}")
    
    # 读取几何数据
    geo_data = read_vj103dnb_geo(vj103_file)
    print(f"  ✅ 几何数据：纬度 {geo_data['latitude'].shape}, 经度 {geo_data['longitude'].shape}")
    
    # 处理填充值（-999.9 等异常值设为 NaN）
    fill_value_mask = radiance < -100  # 填充值通常是 -999.9
    if np.any(fill_value_mask):
        print(f"  ⚠️ 检测到 {np.sum(fill_value_mask)} 个填充值，转换为 NaN")
        radiance = radiance.astype(np.float64)  # 转换为 float64 以支持 NaN
        radiance[fill_value_mask] = np.nan
    
    # 检查形状是否匹配
    if radiance.shape != geo_data['latitude'].shape:
        print(f"  ⚠️ 警告：辐射和几何数据形状不匹配，尝试插值...")
        # 这里可以添加插值逻辑，暂时跳过
        return {
            'status': 'shape_mismatch',
            'radiance_shape': radiance.shape,
            'geo_shape': geo_data['latitude'].shape
        }
    
    # 创建输出文件名
    base_name = vj102_file.stem  # 去掉 .nc
    output_path = output_dir / f"{base_name}_geo"
    
    # 准备元数据
    metadata = {
        'processing_date': datetime.now().isoformat(),
        'radiance_file': vj102_file.name,
        'geolocation_file': vj103_file.name,
        'platform': 'Suomi NPP',
        'instrument': 'VIIRS',
        'product': 'DNB L1B',
    }
    
    # 创建 GeoTIFF
    geotiff_path = create_geotiff(
        radiance=radiance,
        latitude=geo_data['latitude'],
        longitude=geo_data['longitude'],
        output_path=output_path,
        metadata=metadata
    )
    
    # 计算统计信息（排除 NaN）
    valid_mask = ~np.isnan(radiance)
    if np.sum(valid_mask) > 0:
        stats = {
            'min': float(np.nanmin(radiance)),
            'max': float(np.nanmax(radiance)),
            'mean': float(np.nanmean(radiance)),
            'std': float(np.nanstd(radiance)),
            'valid_pixels': int(np.sum(valid_mask))
        }
    else:
        stats = {
            'min': 0.0,
            'max': 0.0,
            'mean': 0.0,
            'std': 0.0,
            'valid_pixels': 0
        }
    
    # 保存统计信息
    stats_file = output_dir / f"{base_name}_stats.json"
    result = {
        'status': 'success',
        'radiance_file': str(vj102_file),
        'geolocation_file': str(vj103_file),
        'output_file': str(geotiff_path),
        'shape': radiance.shape,
        'stats': stats,
        'metadata': metadata
    }
    
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"  ✅ 统计：min={stats['min']:.6f}, max={stats['max']:.6f}, mean={stats['mean']:.6f}")
    print(f"  ✅ 有效像素：{stats['valid_pixels']:,}")
    
    return result


def batch_process(
    input_dir: Path,
    output_dir: Path
) -> Dict[str, Any]:
    """
    批量处理 VJ102DNB + VJ103DNB 配对
    
    Args:
        input_dir: 输入目录（包含 .nc 文件）
        output_dir: 输出目录
        
    Returns:
        批量处理结果
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    
    # 查找所有文件
    vj102_files = sorted(input_dir.glob('VJ102DNB*.nc'))
    vj103_files = sorted(input_dir.glob('VJ103DNB*.nc'))
    
    print(f"找到文件:")
    print(f"  VJ102DNB (辐射): {len(vj102_files)} 个")
    print(f"  VJ103DNB (几何): {len(vj103_files)} 个")
    print("=" * 80)
    
    if not vj102_files or not vj103_files:
        print("⚠️ 警告：缺少辐射或几何数据文件")
        return {
            'status': 'missing_files',
            'vj102_count': len(vj102_files),
            'vj103_count': len(vj103_files)
        }
    
    results = []
    failed = []
    no_match = []
    
    for i, vj102_file in enumerate(vj102_files, 1):
        print(f"\n[{i}/{len(vj102_files)}] ", end="")
        
        # 查找匹配的 VJ103DNB 文件
        vj103_file = match_vj102_vj103(vj102_file, vj103_files)
        
        if vj103_file is None:
            print(f"⚠️ 未找到匹配的几何数据：{vj102_file.name}")
            no_match.append(str(vj102_file))
            continue
        
        try:
            result = process_pair(vj102_file, vj103_file, output_dir)
            results.append(result)
        except Exception as e:
            print(f"❌ 失败：{e}")
            failed.append({
                'file': str(vj102_file),
                'error': str(e)
            })
    
    # 汇总统计
    summary = {
        'total_vj102': len(vj102_files),
        'total_vj103': len(vj103_files),
        'matched_pairs': len(results),
        'no_match': len(no_match),
        'failed': len(failed),
        'total_valid_pixels': sum(r.get('stats', {}).get('valid_pixels', 0) for r in results),
        'failed_files': failed,
        'no_match_files': no_match
    }
    
    # 保存汇总
    summary_file = output_dir / "geotiff_batch_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 80)
    print(f"批量处理完成!")
    print(f"  成功配对：{len(results)} 对")
    print(f"  无匹配：{len(no_match)} 个")
    print(f"  失败：{len(failed)} 个")
    print(f"  总有效像素：{summary['total_valid_pixels']:,}")
    print(f"  汇总文件：{summary_file.name}")
    
    return summary


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="VJ102DNB + VJ103DNB 转 GeoTIFF 工具")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="输入目录（包含 VJ102DNB 和 VJ103DNB .nc 文件）"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="输出目录"
    )
    
    args = parser.parse_args()
    
    batch_process(args.input, args.output)
