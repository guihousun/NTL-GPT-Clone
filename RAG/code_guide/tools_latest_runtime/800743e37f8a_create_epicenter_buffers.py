import geopandas as gpd
from shapely.geometry import Point
from storage_manager import storage_manager

# Epicenter coordinates from USGS/British Geological Survey
epicenter_lon = 95.922
epicenter_lat = 22.013

# Buffer distances in km
buffer_distances_km = [25, 50, 100]

# Create point geometry in WGS84
point = Point(epicenter_lon, epicenter_lat)

# Create initial GeoDataFrame with WGS84 CRS (just the point)
gdf = gpd.GeoDataFrame([{'geometry': point}], crs='EPSG:4326')

# Project to a suitable projected CRS for accurate buffering (UTM Zone 47N for Myanmar)
projected_crs = 'EPSG:32647'  # UTM Zone 47N
gdf_projected = gdf.to_crs(projected_crs)

# Create buffers for each distance
buffer_features = []
for dist_km in buffer_distances_km:
    buffer_geom = gdf_projected.geometry[0].buffer(dist_km * 1000)  # Convert km to meters
    buffer_features.append({
        'buffer_id': f'buffer_{dist_km}km',
        'buffer_km': dist_km,
        'geometry': buffer_geom
    })

# Create final GeoDataFrame
buffers_gdf = gpd.GeoDataFrame(buffer_features, crs=projected_crs)

# Reproject back to WGS84 for GEE compatibility
buffers_gdf_wgs84 = buffers_gdf.to_crs('EPSG:4326')

# Save to outputs folder using storage_manager
output_path = storage_manager.resolve_output_path('epicenter_buffers.geojson')
buffers_gdf_wgs84.to_file(output_path, driver='GeoJSON')
print(f"Buffers saved to: {output_path}")
print(f"Created {len(buffers_gdf)} buffer zones around epicenter ({epicenter_lat}, {epicenter_lon})")