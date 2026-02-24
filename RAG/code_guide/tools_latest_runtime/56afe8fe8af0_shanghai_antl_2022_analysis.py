"""
Identify the Shanghai district with the highest ANTL in 2022 NPP-VIIRS-Like image.
Workflow:
1. Load Shanghai district boundaries from local shapefile
2. Upload boundaries to GEE as FeatureCollection
3. Use reduceRegions to calculate ANTL (mean) for each district server-side
4. Download results and identify the brightest district

# AOI_CONFIRMED_BY_USER: Shanghai administrative boundary (16 districts) confirmed by Data_Searcher
# Boundary file: shanghai_districts_boundary.shp (EPSG:4326, 16 features)
"""

import ee
import pandas as pd
import geopandas as gpd
import json
from storage_manager import storage_manager

# Initialize GEE
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Resolve paths
boundary_input = storage_manager.resolve_input_path("shanghai_districts_boundary.shp")
stats_output_csv = storage_manager.resolve_output_path("shanghai_district_antl_2022.csv")

print("Step 1: Loading Shanghai district boundaries...")

# Load district boundaries
gdf = gpd.read_file(boundary_input)
print(f"Loaded {len(gdf)} districts")
print(f"Districts: {gdf['Name'].tolist()}")

# Ensure CRS is WGS84
if gdf.crs.to_epsg() != 4326:
    gdf = gdf.to_crs("EPSG:4326")

print("\nStep 2: Converting boundaries to GeoJSON and uploading to GEE...")

# Convert to GeoJSON
geojson_str = gdf.to_json()
geojson_dict = json.loads(geojson_str)

# Create FeatureCollection from GeoJSON
fc = ee.FeatureCollection(geojson_dict)

print(f"FeatureCollection created with {fc.size().getInfo()} features")

print("\nStep 3: Loading 2022 NPP-VIIRS-Like annual composite from GEE...")

# Load NPP-VIIRS-Like annual data for 2022
# The dataset 'projects/sat-io/open-datasets/npp-viirs-ntl' contains annual composites
# Each image represents one year, with band 'b1' containing the ANTL values
ntl_collection = (
    ee.ImageCollection("projects/sat-io/open-datasets/npp-viirs-ntl")
    .filterDate("2022-01-01", "2022-12-31")
    .select("b1")
)

# Check how many images are in the collection
image_count = ntl_collection.size().getInfo()
print(f"Found {image_count} image(s) for 2022")

if image_count == 0:
    # Try filtering by year property if available
    print("Trying alternative filter...")
    ntl_collection = (
        ee.ImageCollection("projects/sat-io/open-datasets/npp-viirs-ntl")
        .filter(ee.Filter.calendarRange(2022, 2022, 'year'))
        .select("b1")
    )
    image_count = ntl_collection.size().getInfo()
    print(f"Found {image_count} image(s) with alternative filter")

if image_count == 0:
    raise ValueError("No NPP-VIIRS-Like images found for 2022. Please check the dataset availability.")

# Get the annual composite (mean if multiple, or the single image)
if image_count > 1:
    ntl_image = ntl_collection.mean()
    print("Using mean of multiple images for 2022")
else:
    ntl_image = ntl_collection.first()
    print("Using single annual composite for 2022")

print("\nStep 4: Calculating zonal statistics (ANTL) for each district using reduceRegions...")

# Perform zonal statistics
stats_fc = ntl_image.reduceRegions(
    collection=fc,
    reducer=ee.Reducer.mean().setOutputs(['ANTL']),
    scale=500,
    maxPixelsPerRegion=1e13,
    tileScale=4  # Increase tile scale for large regions
)

# Get results
print("Fetching results from GEE (this may take a moment)...")
stats_result = stats_fc.getInfo()

print(f"Received {len(stats_result['features'])} results")

# Parse results
results = []
for feature in stats_result['features']:
    props = feature['properties']
    # The district name should be in the properties
    district_name = props.get('Name', props.get('name', 'Unknown'))
    antl_value = props.get('ANTL', props.get('mean', None))
    
    results.append({
        'Region': district_name,
        'ANTL': antl_value
    })

# Create DataFrame
stats_df = pd.DataFrame(results)

# Save to CSV
stats_df.to_csv(stats_output_csv, index=False)
print(f"Statistics saved to: {stats_output_csv}")

print("\nStep 5: Identifying the district with the highest ANTL...")

# Find the district with maximum ANTL
# Exclude any rows with NaN
valid_stats = stats_df.dropna(subset=['ANTL'])

if len(valid_stats) > 0:
    brightest_idx = valid_stats['ANTL'].idxmax()
    brightest_district = valid_stats.loc[brightest_idx]
    
    print("\n" + "="*60)
    print("RESULT: District with Highest ANTL in Shanghai (2022)")
    print("="*60)
    print(f"District Name: {brightest_district['Region']}")
    print(f"ANTL (Mean Brightness): {brightest_district['ANTL']:.4f}")
    print("="*60)
    
    # Print all districts sorted by ANTL
    print("\nAll Districts Ranked by ANTL (2022):")
    ranked = valid_stats.sort_values('ANTL', ascending=False).reset_index(drop=True)
    ranked.index = ranked.index + 1  # Start ranking from 1
    print(ranked.to_string())
    
    # Print top 5 districts
    print("\nTop 5 Districts by ANTL:")
    top5 = valid_stats.nlargest(5, 'ANTL')[['Region', 'ANTL']]
    print(top5.to_string(index=False))
else:
    print("ERROR: No valid ANTL values found. Check the NTL data and boundary overlap.")
    print("Debug info - stats_df:")
    print(stats_df)

print("\nScript completed successfully.")