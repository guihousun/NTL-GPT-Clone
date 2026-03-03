"""
VJ102DNB/VJ103DNB .nc 文件预处理工具

Suomi NPP VIIRS Day/Night Band L1B 数据预处理
支持从 LAADS DAAC 下载的 .nc 格式文件
"""

import netCDF4
import numpy as np
from pathlib import Path
from typing import Dict, Any, Tuple
import xarray as xr


def read_dnb_radiance(nc_file: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    读取 DNB 辐射数据
    
    VJ102DNB/VJ103DNB .nc 文件实际是 HDF5 格式，数据结构：
    - observation_data/DNB_observations: 辐射数据
    - observation_data/DNB_quality_flags: 质量标志
    
    Args:
        nc_file: NetCDF 文件路径
        
    Returns:
        radiance: 辐射数据数组
        metadata: 元数据字典
    """
    import h5py
    
    # 使用 h5py 读取 HDF5 结构
    with h5py.File(nc_file, 'r') as f:
        # 检查是否有预期的数据集
        if 'observation_data/DNB_observations' not in f:
            # 尝试查找替代路径
            possible_paths = [
                'observation_data/DNB_observations',
                'DNB_observations',
                'radiance',
                'DNB_radiance'
            ]
            
            radiance_path = None
            for path in possible_paths:
                if path in f:
                    radiance_path = path
                    break
            
            if radiance_path is None:
                # 列出所有数据集
                datasets = []
                f.visititems(lambda name, obj: datasets.append(name) if isinstance(obj, h5py.Dataset) else None)
                raise ValueError(f"未找到辐射数据。可用数据集：{datasets[:20]}")
        else:
            radiance_path = 'observation_data/DNB_observations'
        
        # 读取辐射数据
        radiance = f[radiance_path][:]
        
        # 尝试读取质量标志
        qf_path = 'observation_data/DNB_quality_flags'
        if qf_path in f:
            qf = f[qf_path][:]
        else:
            qf = None
        
        # 提取元数据
        metadata = {
            'radiance_path': radiance_path,
            'shape': radiance.shape,
            'dtype': str(radiance.dtype),
        }
        
        # 读取全局属性
        for attr in f.attrs:
            metadata[attr] = str(f.attrs[attr])
    
    return radiance, metadata


def read_dnb_quality(nc_file: Path) -> np.ndarray:
    """
    读取 DNB 质量控制数据
    """
    import h5py
    
    with h5py.File(nc_file, 'r') as f:
        qf_path = 'observation_data/DNB_quality_flags'
        if qf_path in f:
            return f[qf_path][:]
        else:
            return None


def preprocess_vj102dnb(
    input_nc: Path,
    output_dir: Path,
    apply_qc: bool = True
) -> Dict[str, Any]:
    """
    预处理 VJ102DNB 数据
    
    Args:
        input_nc: 输入 .nc 文件
        output_dir: 输出目录
        apply_qc: 是否应用质量控制
        
    Returns:
        处理结果字典
    """
    input_nc = Path(input_nc)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"处理文件：{input_nc.name}")
    
    # 读取辐射数据
    radiance, metadata = read_dnb_radiance(input_nc)
    
    # 读取质量控制数据
    if apply_qc:
        qf = read_dnb_quality(input_nc)
        if qf is not None:
            # 应用质量控制掩膜
            mask = qf == 0  # 假设 0 表示好数据
            radiance = np.where(mask, radiance, np.nan)
    
    # 计算统计信息
    stats = {
        'min': float(np.nanmin(radiance)),
        'max': float(np.nanmax(radiance)),
        'mean': float(np.nanmean(radiance)),
        'std': float(np.nanstd(radiance)),
        'valid_pixels': int(np.sum(~np.isnan(radiance)))
    }
    
    # 保存为 numpy 数组
    output_npy = output_dir / f"{input_nc.stem}_radiance.npy"
    np.save(output_npy, radiance)
    
    # 保存元数据
    import json
    metadata['stats'] = stats
    metadata['input_file'] = str(input_nc)
    metadata['output_file'] = str(output_npy)
    
    output_meta = output_dir / f"{input_nc.stem}_metadata.json"
    with open(output_meta, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"  ✅ 辐射数据形状：{radiance.shape}")
    print(f"  ✅ 统计信息：min={stats['min']:.4f}, max={stats['max']:.4f}, mean={stats['mean']:.4f}")
    print(f"  ✅ 有效像素：{stats['valid_pixels']}")
    print(f"  ✅ 输出文件：{output_npy.name}")
    
    return {
        'status': 'success',
        'input_file': str(input_nc),
        'output_file': str(output_npy),
        'metadata_file': str(output_meta),
        'stats': stats,
        'shape': radiance.shape
    }


def batch_preprocess(
    input_dir: Path,
    output_dir: Path,
    pattern: str = "VJ102DNB*.nc"  # 只处理 VJ102DNB 辐射数据
) -> Dict[str, Any]:
    """
    批量预处理 DNB 数据
    
    Args:
        input_dir: 输入目录
        output_dir: 输出目录
        pattern: 文件匹配模式 (默认只处理 VJ102DNB 辐射数据)
        
    Returns:
        批量处理结果
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    
    # 只处理 VJ102DNB 文件 (VJ103DNB 是几何数据，不需要预处理)
    nc_files = list(input_dir.glob(pattern))
    
    # 过滤掉 VJ103DNB 文件
    nc_files = [f for f in nc_files if 'VJ102DNB' in f.name]
    
    if not nc_files:
        print(f"⚠️ 警告：在 {input_dir} 中未找到 VJ102DNB 辐射数据文件")
        print(f"  提示：VJ103DNB 是几何校正数据，不需要辐射预处理")
        return {
            'status': 'no_files',
            'message': 'No VJ102DNB files found'
        }
    
    print(f"找到 {len(nc_files)} 个 VJ102DNB 辐射数据文件")
    print("=" * 80)
    
    results = []
    failed = []
    
    for i, nc_file in enumerate(nc_files, 1):
        print(f"\n[{i}/{len(nc_files)}] ", end="")
        try:
            result = preprocess_vj102dnb(nc_file, output_dir)
            results.append(result)
        except Exception as e:
            print(f"❌ 失败：{e}")
            failed.append({
                'file': str(nc_file),
                'error': str(e)
            })
    
    # 汇总统计
    summary = {
        'total_files': len(nc_files),
        'success': len(results),
        'failed': len(failed),
        'total_valid_pixels': sum(r['stats']['valid_pixels'] for r in results),
        'failed_files': failed
    }
    
    # 保存汇总
    import json
    summary_file = output_dir / "batch_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 80)
    print(f"批量处理完成!")
    print(f"  成功：{len(results)} 个文件")
    print(f"  失败：{len(failed)} 个文件")
    print(f"  总有效像素：{summary['total_valid_pixels']:,}")
    print(f"  汇总文件：{summary_file.name}")
    
    return summary


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="VJ102DNB/VJ103DNB 数据预处理工具")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="输入 .nc 文件或目录"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="输出目录"
    )
    parser.add_argument(
        "--no-qc",
        action="store_true",
        help="不应用质量控制"
    )
    
    args = parser.parse_args()
    
    if args.input.is_file():
        preprocess_vj102dnb(args.input, args.output, apply_qc=not args.no_qc)
    elif args.input.is_dir():
        batch_preprocess(args.input, args.output)
    else:
        print(f"错误：输入路径不存在：{args.input}")
