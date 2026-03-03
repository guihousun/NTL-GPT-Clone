#!/usr/bin/env python
"""
逐天运行 VJ102DNB/VJ103DNB 官方预处理管道
Daily pipeline runner for VJ102DNB/VJ103DNB official preprocessing
"""

import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 伊朗边界框 (Iran bounding box)
BBOX = "44.03,25.08,63.33,39.77"

# 输出目录 (Output directory)
OUTPUT_DIR = r"E:\Download\LAADS_geotiff_precise"

# 需要处理的日期范围 (Date ranges to process)
# 范围 1: 2026-02-22 到 2026-03-01
# 范围 2: 2026-02-01 (单独一天)
DATE_RANGES = [
    ("2026-02-22", "2026-03-01"),
    ("2026-02-01", "2026-02-01"),
]

# 管道脚本路径 (Pipeline script path)
PIPELINE_TOOL = Path(__file__).parent / "official_vj_dnb_pipeline_tool.py"


def daterange(start_date, end_date):
    """生成日期范围 (Generate date range)"""
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)


def process_single_date(date_str):
    """处理单个日期 (Process single date)"""
    print(f"\n{'='*60}")
    print(f"处理日期 (Processing date): {date_str}")
    print(f"{'='*60}\n")
    
    date_label = date_str.replace('-', '')
    
    # 使用 Python 直接调用工具函数 (Call tool function directly with Python)
    python_code = """
import sys
from pathlib import Path
sys.path.insert(0, r'""" + str(Path(__file__).parent.parent) + """')

from tools.official_vj_dnb_pipeline_tool import run_official_vj_dnb_fullchain
import json
import shutil

result = run_official_vj_dnb_fullchain(
    start_date='""" + date_str + """',
    end_date='""" + date_str + """',
    bbox='""" + BBOX + """',
    output_root='base_data/VJ102DNB_Iran/official_pipeline_runs',
    run_label='daily_""" + date_label + """',
    sources='VJ102DNB,VJ103DNB',
    composite='mean',
    resolution_m=500.0,
    radius_m=2000.0,
    radiance_scale=1e9,
    skip_preprocess=False,
)

# 复制 GeoTIFF 到目标目录 (Copy GeoTIFF to target directory)
processed_dir = Path(result['paths']['processed_dir'])
target_dir = Path(r'""" + OUTPUT_DIR + """')
target_dir.mkdir(parents=True, exist_ok=True)

# 复制每日合成文件 (Copy daily composite files)
tif_count = 0
# 每日合成文件在 daily_4326 子目录中 (Daily composite files are in daily_4326 subdirectory)
daily_subdir = processed_dir / 'daily_4326'
if daily_subdir.exists():
    for pattern in ['*_mean.tif', '*_max.tif']:
        for tif_file in daily_subdir.glob(pattern):
            dest = target_dir / tif_file.name
            shutil.copy2(tif_file, dest)
            print(f'已复制每日合成 (Copied daily composite): {tif_file.name}')
            tif_count += 1

# 如果没有找到每日合成文件，复制 granule 文件 (If no daily composite found, copy granule files)
if tif_count == 0:
    granules_dir = processed_dir / 'granules_4326'
    if granules_dir.exists():
        for tif_file in granules_dir.glob('*.tif'):
            dest = target_dir / tif_file.name
            shutil.copy2(tif_file, dest)
            print(f'已复制 granule (Copied granule): {tif_file.name}')
            tif_count += 1

# 复制总结文件 (Copy summary file)
for json_file in processed_dir.glob('precise_preprocess_summary.json'):
    dest = target_dir / f'daily_""" + date_label + """_summary.json'
    shutil.copy2(json_file, dest)
    print(f'已复制总结 (Copied summary): {json_file.name}')

print()
print('='*60)
print('处理完成 (Processing complete)')
print('='*60)
print(f'复制了 {tif_count} 个 GeoTIFF 文件到：{target_dir}')
    """
    
    cmd = [sys.executable, "-c", python_code]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    
    # 打印输出 (Print output)
    print(proc.stdout)
    if proc.stderr:
        print("错误 (Errors):", proc.stderr)
    
    return proc.returncode == 0


def main():
    """主函数 (Main function)"""
    print("="*60)
    print("VJ102DNB/VJ103DNB 逐天预处理管道")
    print("Daily VJ102DNB/VJ103DNB Preprocessing Pipeline")
    print("="*60)
    print(f"\n输出目录 (Output directory): {OUTPUT_DIR}")
    print(f"边界框 (Bounding box): {BBOX}")
    print(f"\n日期范围 (Date ranges):")
    for start, end in DATE_RANGES:
        print(f"  - {start} 到 {end}")
    
    total_dates = 0
    successful = 0
    failed = []
    
    # 处理每个日期范围 (Process each date range)
    for start_str, end_str in DATE_RANGES:
        start_date = datetime.strptime(start_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_str, "%Y-%m-%d")
        
        # 逐天处理 (Process day by day)
        for single_date in daterange(start_date, end_date):
            date_str = single_date.strftime("%Y-%m-%d")
            total_dates += 1
            
            print(f"\n[{total_dates}] 开始处理 (Starting): {date_str}")
            
            if process_single_date(date_str):
                successful += 1
                print(f"✓ 成功 (Success): {date_str}")
            else:
                failed.append(date_str)
                print(f"✗ 失败 (Failed): {date_str}")
    
    # 总结 (Summary)
    print("\n" + "="*60)
    print("处理总结 (Processing Summary)")
    print("="*60)
    print(f"总天数 (Total dates): {total_dates}")
    print(f"成功 (Successful): {successful}")
    print(f"失败 (Failed): {len(failed)}")
    if failed:
        print(f"失败的日期 (Failed dates): {', '.join(failed)}")
    
    print(f"\n所有文件已保存到 (All files saved to): {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
