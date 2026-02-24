"""
Myanmar Earthquake Impact Assessment using VNP46A2 Daily NTL Data
Event: M 7.7 Earthquake on 2025-03-28 at 06:20:52 UTC (12:50:52 local)
Epicenter: 22.011°N, 95.936°E

Analysis Periods:
- Pre-event baseline: 2025-03-14 to 2025-03-27 (14 days before event)
- First night after earthquake: 2025-03-29 (local day D+1)
- Post-event recovery: 2025-03-30 to 2025-04-11 (14 days after event)

Methodology:
- Use Gap_Filled_DNB_BRDF_Corrected_NTL band from VNP46A2
- Compute ANTL (Average Nighttime Light) for each period
- Create multi-scale epicenter buffers (25km, 50km, 100km)
- Calculate damage metrics: drop_pct = (ANTL_post - ANTL_baseline) / ANTL_baseline * 100

# AOI_CONFIRMED_BY_USER: Myanmar boundary confirmed by Data_Searcher via get_administrative_division_osm_tool
"""

import ee
import pandas as pd
from storage_manager import storage_manager

# Initialize GEE with project
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Load Myanmar boundary
boundary_path = storage_manager.resolve_input_path('myanmar_boundary.shp')
import geopandas as gpd
boundary_gdf = gpd.read_file(boundary_path)

# Convert boundary to GEE geometry using the bounds (confirmed by Data_Searcher)
boundary_bounds = boundary_gdf.total_bounds
myanmar_region = ee.Geometry.Rectangle([
    boundary_bounds[0], boundary_bounds[1],
    boundary_bounds[2], boundary_bounds[3]
])

# Epicenter coordinates (from USGS/ReliefWeb official sources)
EPICENTER_LAT = 22.011
EPICENTER_LON = 95.936
epicenter = ee.Geometry.Point([EPICENTER_LON, EPICENTER_LAT])

# Create multi-scale buffers around epicenter
epicenter_proj = epicenter.transform('EPSG:32646', maxError=10)
buffer_25km = epicenter_proj.buffer(25000).transform('EPSG:4326', maxError=10)
buffer_50km = epicenter_proj.buffer(50000).transform('EPSG:4326', maxError=10)
buffer_100km = epicenter_proj.buffer(100000).transform('EPSG:4326', maxError=10)

# Define analysis regions - start with national and 100km buffer (more likely to have data)
analysis_regions = {
    'myanmar_national': myanmar_region,
    'epicenter_100km': buffer_100km,
    'epicenter_50km': buffer_50km,
    'epicenter_25km': buffer_25km
}

# VNP46A2 collection parameters
DATASET = "NASA/VIIRS/002/VNP46A2"
BAND = "Gap_Filled_DNB_BRDF_Corrected_NTL"
SCALE = 500
MAX_PIXELS = 1e13

# Define analysis periods
PRE_EVENT_START = "2025-03-14"
PRE_EVENT_END = "2025-03-28"  # Include event day morning (before earthquake)
FIRST_NIGHT = "2025-03-29"
POST_EVENT_START = "2025-03-30"
POST_EVENT_END = "2025-04-12"

print("=" * 60)
print("Myanmar Earthquake Impact Assessment - VNP46A2 NTL Analysis")
print("=" * 60)
print(f"Event: M 7.7 Earthquake on 2025-03-28 at 06:20:52 UTC")
print(f"Epicenter: {EPICENTER_LAT}°N, {EPICENTER_LON}°E")
print(f"Pre-event baseline: {PRE_EVENT_START} to {PRE_EVENT_END}")
print(f"First night after event: {FIRST_NIGHT}")
print(f"Post-event recovery: {POST_EVENT_START} to {POST_EVENT_END}")
print("=" * 60)

# Load full VNP46A2 collection for the analysis period
full_collection = (
    ee.ImageCollection(DATASET)
    .filterDate("2025-03-14", "2025-04-12")
    .select(BAND)
)

# Function to compute mean NTL for a region and date range with empty collection handling
def compute_antlr_safe(region, start_date, end_date, region_name):
    """Compute ANTL with robust empty collection handling."""
    try:
        period_collection = full_collection.filterDate(start_date, end_date).filterBounds(region)
        
        # Check collection size first
        image_count = period_collection.size().getInfo()
        
        if image_count == 0:
            print(f"    WARNING: No images found for {region_name} in {start_date} to {end_date}")
            return None
        
        # Compute mean image
        mean_img = period_collection.mean()
        
        # Compute regional mean with error handling
        stats = mean_img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=SCALE,
            maxPixels=MAX_PIXELS,
            bestEffort=True,
            tileScale=4,  # Use larger tile scale for better coverage
        )
        
        antlr_value = stats.getInfo().get(BAND)
        
        if antlr_value is None:
            print(f"    WARNING: NULL value returned for {region_name}")
            return None
        
        return {
            'region': region_name,
            'start_date': start_date,
            'end_date': end_date,
            'image_count': image_count,
            'ANTL': antlr_value
        }
    except Exception as e:
        print(f"    ERROR processing {region_name}: {str(e)}")
        return None

# Compute ANTL for all periods and regions
results = []

print("\nComputing ANTL for all regions and periods...")
print("-" * 60)

for region_name, region_geom in analysis_regions.items():
    print(f"\nProcessing region: {region_name}")
    
    # Pre-event baseline
    pre_event_result = compute_antlr_safe(
        region_geom, PRE_EVENT_START, PRE_EVENT_END, region_name
    )
    if pre_event_result:
        pre_event_result['period'] = 'pre_event_baseline'
        results.append(pre_event_result)
        print(f"  Pre-event: ANTL = {pre_event_result['ANTL']:.4f} nW/cm²/sr (n={pre_event_result['image_count']})")
    
    # First night after earthquake
    first_night_result = compute_antlr_safe(
        region_geom, FIRST_NIGHT, FIRST_NIGHT, region_name
    )
    if first_night_result:
        first_night_result['period'] = 'first_night_post_event'
        results.append(first_night_result)
        print(f"  First night: ANTL = {first_night_result['ANTL']:.4f} nW/cm²/sr")
    
    # Post-event recovery
    post_event_result = compute_antlr_safe(
        region_geom, POST_EVENT_START, POST_EVENT_END, region_name
    )
    if post_event_result:
        post_event_result['period'] = 'post_event_recovery'
        results.append(post_event_result)
        print(f"  Post-event: ANTL = {post_event_result['ANTL']:.4f} nW/cm²/sr (n={post_event_result['image_count']})")

# Check if we have sufficient data
if len(results) == 0:
    print("\nERROR: No valid ANTL computations completed. Check data availability.")
    # Create minimal output
    df = pd.DataFrame(columns=['region', 'start_date', 'end_date', 'image_count', 'ANTL', 'period'])
else:
    # Create DataFrame
    df = pd.DataFrame(results)
    
    # Pivot to compute damage metrics
    pivot_df = df.pivot(index='region', columns='period', values='ANTL')
    
    # Calculate damage metrics
    damage_metrics = []
    
    print("\n" + "=" * 60)
    print("Damage Assessment Results")
    print("=" * 60)
    
    for region_name in analysis_regions.keys():
        if region_name in pivot_df.index:
            row = pivot_df.loc[region_name]
            
            pre_event_antlr = row.get('pre_event_baseline')
            first_night_antlr = row.get('first_night_post_event')
            post_event_antlr = row.get('post_event_recovery')
            
            print(f"\n{region_name}:")
            
            if pd.notna(pre_event_antlr) and pd.notna(first_night_antlr) and pre_event_antlr > 0:
                immediate_drop_pct = ((first_night_antlr - pre_event_antlr) / pre_event_antlr) * 100
                damage_metrics.append({
                    'region': region_name,
                    'metric': 'immediate_impact_drop_pct',
                    'value': immediate_drop_pct,
                    'description': 'NTL change from pre-event to first night'
                })
                print(f"  Immediate impact (first night): {immediate_drop_pct:.2f}%")
            
            if pd.notna(pre_event_antlr) and pd.notna(post_event_antlr) and pre_event_antlr > 0:
                recovery_drop_pct = ((post_event_antlr - pre_event_antlr) / pre_event_antlr) * 100
                damage_metrics.append({
                    'region': region_name,
                    'metric': 'recovery_phase_drop_pct',
                    'value': recovery_drop_pct,
                    'description': 'NTL change from pre-event to recovery period'
                })
                print(f"  Recovery phase impact: {recovery_drop_pct:.2f}%")
            
            if pd.notna(first_night_antlr) and pd.notna(post_event_antlr) and first_night_antlr > 0:
                recovery_progress_pct = ((post_event_antlr - first_night_antlr) / first_night_antlr) * 100
                damage_metrics.append({
                    'region': region_name,
                    'metric': 'recovery_progress_pct',
                    'value': recovery_progress_pct,
                    'description': 'NTL change from first night to recovery'
                })
                print(f"  Recovery progress: {recovery_progress_pct:.2f}%")

# Create damage metrics DataFrame
damage_df = pd.DataFrame(damage_metrics) if damage_metrics else pd.DataFrame()

# Save results to CSV
output_csv = storage_manager.resolve_output_path('myanmar_earthquake_antlr_analysis.csv')
df.to_csv(output_csv, index=False)
print(f"\n{'=' * 60}")
print(f"ANTL results saved to: {output_csv}")

if not damage_df.empty:
    damage_csv = storage_manager.resolve_output_path('myanmar_earthquake_damage_metrics.csv')
    damage_df.to_csv(damage_csv, index=False)
    print(f"Damage metrics saved to: {damage_csv}")

# Print summary
print(f"\n{'=' * 60}")
print("SUMMARY: Myanmar Earthquake Impact Assessment")
print(f"{'=' * 60}")
print(f"Event: M 7.7 Earthquake on 2025-03-28 at 12:50:52 local time")
print(f"Epicenter: {EPICENTER_LAT}°N, {EPICENTER_LON}°E (near Sagaing/Mandalay)")
print(f"\nOutput Files:")
print(f"  - {output_csv}")
if not damage_df.empty:
    print(f"  - {damage_csv}")
print(f"{'=' * 60}")
