import sys
import os

# Add root to sys.path
sys.path.append(os.getcwd())

from tools.NTL_Code_generation import execute_geospatial_script, save_geospatial_script
from storage_manager import current_thread_id

# Set a thread ID for this execution
current_thread_id.set("user_request_execution")

geospatial_code = r"""
import ee
import pandas as pd
from storage_manager import storage_manager

# Initialize GEE
project_id = 'empyrean-caster-430308-m2'
try:
    ee.Initialize(project=project_id)
except Exception:
    try:
        ee.Authenticate()
        ee.Initialize(project=project_id)
    except Exception as e:
        print(f"GEE Init failed: {e}")

print("GEE Initialized.")

# Load China boundary
countries = ee.FeatureCollection("FAO/GAUL/2015/level0")
china = countries.filter(ee.Filter.eq('ADM0_NAME', 'China'))

# Attempt to load dataset
# User requested: projects/sat-io/open-datasets/NTL_VIIRS_LIKE
# Known correct alias often used: projects/sat-io/open-datasets/npp-viirs-ntl
target_asset = "projects/sat-io/open-datasets/NTL_VIIRS_LIKE"
fallback_asset = "projects/sat-io/open-datasets/npp-viirs-ntl"

collection = None
asset_used = ""

try:
    c = ee.ImageCollection(target_asset)
    # Trigger check
    c.limit(1).size().getInfo()
    collection = c
    asset_used = target_asset
except Exception as e:
    print(f"Asset {target_asset} access failed: {e}")
    try:
        print(f"Trying fallback: {fallback_asset}")
        c = ee.ImageCollection(fallback_asset)
        c.limit(1).size().getInfo()
        collection = c
        asset_used = fallback_asset
    except Exception as e2:
        print(f"Fallback failed: {e2}")
        # Try NOAA standard
        print("Trying NOAA standard monthly data...")
        asset_used = "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG"
        collection = ee.ImageCollection(asset_used).select('avg_rad')

print(f"Using Asset: {asset_used}")

# Filter for 2024
ntl_2024 = collection.filterDate('2024-01-01', '2024-12-31')
count = ntl_2024.size().getInfo()
print(f"Found {count} images for 2024.")

target_year = 2024
if count == 0:
    print("No data for 2024. Checking 2023...")
    ntl_2024 = collection.filterDate('2023-01-01', '2023-12-31')
    count = ntl_2024.size().getInfo()
    if count > 0:
        target_year = 2023
        print(f"Found {count} images for 2023.")

if count > 0:
    # Compute mean (annual composite)
    ntl_img = ntl_2024.mean().clip(china)
    
    # Get band
    bands = ntl_img.bandNames().getInfo()
    band = bands[0]
    print(f"Using band: {band}")
    
    # ANTL
    print("Calculating ANTL...")
    antl_val = ntl_img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=china.geometry(),
        scale=5000, 
        maxPixels=1e13,
        bestEffort=True
    ).get(band).getInfo()
    
    # TNTL
    print("Calculating TNTL...")
    tntl_img = ntl_img.multiply(ee.Image.pixelArea())
    tntl_val = tntl_img.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=china.geometry(),
        scale=5000,
        maxPixels=1e13,
        bestEffort=True
    ).get(band).getInfo()
    
    print(f"Year: {target_year}")
    print(f"ANTL: {antl_val}")
    print(f"TNTL: {tntl_val}")
    
    df = pd.DataFrame({
        'Region': ['China'],
        'Year': [target_year],
        'ANTL': [antl_val],
        'TNTL': [tntl_val],
        'Dataset': [asset_used]
    })
    
    output_path = storage_manager.resolve_output_path('China_ANTL_TNTL_2024.csv')
    df.to_csv(output_path, index=False)
    print(f"Saved results to: {output_path}")

else:
    print("No data available for 2023 or 2024.")
    output_path = storage_manager.resolve_output_path('China_ANTL_TNTL_2024.csv')
    pd.DataFrame({'Error': ['No data']}).to_csv(output_path, index=False)
"""

print("Saving and executing code via tools...")
save_res = save_geospatial_script(
    script_content=geospatial_code,
    script_name="execute_via_tool_case.py",
    overwrite=True,
)
print("Save Result:")
print(save_res)
result = execute_geospatial_script(script_name="execute_via_tool_case.py")
print("Execution Result:")
print(result)
