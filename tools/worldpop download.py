import ee
import os
import geemap

# Initialize the Earth Engine module.
project_id = 'empyrean-caster-430308-m2'
ee.Initialize(project=project_id)

# Define the Shanghai boundary using a FeatureCollection.
shanghai_boundary = ee.FeatureCollection("projects/empyrean-caster-430308-m2/assets/province") \
    .filter(ee.Filter.eq('name', '上海市'))

# Define the Landscan dataset.
landscan_dataset = ee.ImageCollection("projects/sat-io/open-datasets/ORNL/LANDSCAN_GLOBAL")

# Filter the dataset for the years 2015 to 2020.
landscan_filtered = landscan_dataset.filterDate('2015-01-01', '2020-12-31')

# Clip the dataset to the Shanghai boundary.
landscan_shanghai = landscan_filtered.map(lambda image: image.clip(shanghai_boundary))

# Export each year's data to the local path.
local_dir = r'C:\NTL_Agent\Pop_data'
os.makedirs(local_dir, exist_ok=True)

for year in range(2015, 2021):
    image = landscan_shanghai.filter(ee.Filter.calendarRange(year, year, 'year')).first()
    export_path = os.path.join(local_dir, f'Landscan_Shanghai_{year}.tif')
    geemap.ee_export_image(
        ee_object=image,
        filename=export_path,
        scale=1000,
        region=shanghai_boundary.geometry(),
        crs='EPSG:4326',
        file_per_band=False
    )
    print(f"Image exported to: {export_path}")

print('Landscan data export tasks have been completed for each year from 2015 to 2020.')