import ee
import geopandas as gpd
import geemap
from storage_manager import storage_manager

# AOI_CONFIRMED_BY_USER: Wuhan boundary loaded from Data_Searcher-confirmed wuhan_boundary.shp

# Initialize GEE
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# Load confirmed boundary file
boundary_path = storage_manager.resolve_input_path("wuhan_boundary.shp")
gdf = gpd.read_file(boundary_path)
print(f"Boundary loaded: {len(gdf)} features")
print(f"CRS: {gdf.crs}")

# Get bounds from boundary
bounds = gdf.total_bounds
region = ee.Geometry.Rectangle([bounds[0], bounds[1], bounds[2], bounds[3]])
print(f"Region bounds: {bounds}")

# Define date ranges
lockdown_2019_start = "2019-01-23"
lockdown_2019_end = "2019-04-08"
lockdown_2020_start = "2020-01-23"
lockdown_2020_end = "2020-04-08"

# Create ANTL composite for 2019 lockdown period
print("Creating ANTL composite for 2019 lockdown period...")
image_2019 = (
    ee.ImageCollection("NASA/VIIRS/002/VNP46A2")
    .filterDate(lockdown_2019_start, lockdown_2019_end)
    .select("Gap_Filled_DNB_BRDF_Corrected_NTL")
    .mean()
    .clip(region)
)

# Create ANTL composite for 2020 lockdown period
print("Creating ANTL composite for 2020 lockdown period...")
image_2020 = (
    ee.ImageCollection("NASA/VIIRS/002/VNP46A2")
    .filterDate(lockdown_2020_start, lockdown_2020_end)
    .select("Gap_Filled_DNB_BRDF_Corrected_NTL")
    .mean()
    .clip(region)
)

# Export 2019 ANTL
out_tif_2019 = storage_manager.resolve_output_path("wuhan_antlr_2019_lockdown_period.tif")
geemap.ee_export_image(
    ee_object=image_2019,
    filename=out_tif_2019,
    scale=500,
    region=region,
    crs="EPSG:4326",
    file_per_band=False,
)
print(f"2019 ANTL exported to: {out_tif_2019}")

# Export 2020 ANTL
out_tif_2020 = storage_manager.resolve_output_path("wuhan_antlr_2020_lockdown_period.tif")
geemap.ee_export_image(
    ee_object=image_2020,
    filename=out_tif_2020,
    scale=500,
    region=region,
    crs="EPSG:4326",
    file_per_band=False,
)
print(f"2020 ANTL exported to: {out_tif_2020}")

print("ANTL composites created successfully!")
