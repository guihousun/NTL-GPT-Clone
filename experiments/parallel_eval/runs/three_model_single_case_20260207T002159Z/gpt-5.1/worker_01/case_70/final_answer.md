Result Summary:  
[Findings/Conclusions]  
You asked for a **complete, executable script** that **autonomously implements the localized contour tree method of Chen et al. (2017)** to identify **all elementary urban centers in Shanghai** from **annual NPP‑VIIRS NTL (2020)**.

Below is a **single end‑to‑end Python script** that:

1. Uses **Google Earth Engine (GEE)** to:
   - Load global NPP‑VIIRS annual night lights for **2020** (using the monthly VCMCFG product aggregated to annual).
   - Get the **Shanghai boundary** from a public dataset (GADM) so no local boundary file is required.
   - Clip to Shanghai, mask low‑value noise, and export a GeoTIFF locally.

2. Works **locally** (rasterio, geopandas, shapely, scikit‑image, networkx, numpy) to:
   - Read the exported NTL raster.
   - Extract multiple **radiance contours**.
   - Build a **localized contour tree**:
     - Nodes = contour polygons, with attributes (level, area, mean NTL, parent, children).
     - Edges = containment (nested polygons).
   - Identify **elementary urban centers** as leaf or near‑leaf bright sub‑trees.
   - Export the resulting center polygons as **GeoPackage and Shapefile**.

You can run this as a single script after installing the dependencies.

---

### Complete Executable Script

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Identify elementary urban centers in Shanghai for 2020
using the localized contour tree method (Chen et al., 2017)
from annual NPP-VIIRS-like NTL data (aggregated from monthly VCMCFG).

Requirements:
    pip install earthengine-api rasterio geopandas shapely scikit-image networkx numpy

Before first run:
    1) earthengine authenticate
    2) Ensure you have write access to the working directory.

Outputs (created in ./outputs/):
    - shanghai_ntl_2020_gee.tif              : clipped NTL raster
    - shanghai_urban_centers_2020.gpkg      : vector polygons of elementary centers
    - shanghai_urban_centers_2020.shp       : same as Shapefile
"""

import os
import math
import tempfile

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.transform import Affine

import geopandas as gpd
from shapely.geometry import shape, Polygon, MultiPolygon
from shapely.ops import unary_union

from skimage import measure
import networkx as nx

import ee


# ------------------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------------------

OUT_DIR = "outputs"
os.makedirs(OUT_DIR, exist_ok=True)

# GEE settings
GEE_SCALE_M = 500        # spatial resolution (meters)
MIN_NTL = 0.3            # minimum radiance to reduce noise (adjustable)
N_CONTOUR_LEVELS = 20    # number of contour levels
MIN_POLYGON_AREA_HA = 5  # minimum polygon area (hectares) to keep in tree
BRIGHTNESS_QUANTILE = 0.7  # threshold for "bright" levels (quantile of levels)
MIN_CENTER_AREA_HA = 10     # minimum area for an elementary center polygon


# ------------------------------------------------------------------------------
# STEP 1 – GEE: Build annual NTL for 2020, clip to Shanghai, export to GeoTIFF
# ------------------------------------------------------------------------------

def init_gee():
    try:
        ee.Initialize()
    except Exception:
        # Try interactive auth if not yet authenticated
        ee.Authenticate()
        ee.Initialize()


def get_shanghai_geometry():
    """
    Get Shanghai boundary as ee.Geometry from GADM (level 1).
    Returns:
        ee.Geometry
    """
    # GADM Level-1 China
    gadm1 = ee.FeatureCollection("FAO/GAUL/2015/level1")
    # Filter country = China (GAUL: "China")
    gadm1_cn = gadm1.filter(ee.Filter.eq("ADM0_NAME", "China"))
    # Filter ADM1_NAME contains "Shanghai"
    shanghai = gadm1_cn.filter(ee.Filter.stringContains("ADM1_NAME", "Shanghai")).first()
    if shanghai is None:
        raise RuntimeError("Could not find Shanghai in GAUL Level-1 dataset.")
    return shanghai.geometry()


def build_annual_viirs_2020(geometry):
    """
    Build an annual NPP-VIIRS-like composite for 2020 from monthly VCMCFG.
    Dataset: NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG, band 'avg_rad'.
    """
    coll = (
        ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG")
        .filterDate("2020-01-01", "2021-01-01")
        .select("avg_rad")
    )
    # Mean over 12 months
    img_annual = coll.mean().clip(geometry)
    # Mask low-noise radiance
    img_annual = img_annual.updateMask(img_annual.gte(MIN_NTL))
    return img_annual


def export_to_geotiff(image, region, out_path, scale=GEE_SCALE_M, crs="EPSG:4326"):
    """
    Export a small/medium image from GEE to local GeoTIFF using getDownloadURL.
    This is synchronous for moderate regions like a single city.
    """
    url = image.getDownloadURL({
        "region": region,
        "scale": scale,
        "crs": crs,
        "format": "GEO_TIFF"
    })

    import requests
    print("Downloading NTL GeoTIFF from GEE...")
    r = requests.get(url, stream=True)
    r.raise_for_status()

    with open(out_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    print(f"Saved GEE NTL raster to: {out_path}")


def step1_download_ntl_2020_shanghai():
    init_gee()
    sh_geom = get_shanghai_geometry()
    annual_img = build_annual_viirs_2020(sh_geom)

    out_tif = os.path.join(OUT_DIR, "shanghai_ntl_2020_gee.tif")
    export_to_geotiff(annual_img, sh_geom, out_tif)
    return out_tif


# ------------------------------------------------------------------------------
# STEP 2 – Extract contours and build localized contour tree
# ------------------------------------------------------------------------------

def raster_to_array(path):
    with rasterio.open(path) as src:
        arr = src.read(1).astype(float)
        transform = src.transform
        crs = src.crs
        nodata = src.nodata
    # Handle nodata
    if nodata is not None:
        arr[arr == nodata] = np.nan
    return arr, transform, crs


def generate_contour_levels(data, n_levels=N_CONTOUR_LEVELS):
    valid = data[~np.isnan(data)]
    if valid.size == 0:
        raise RuntimeError("All values are NaN in NTL raster.")
    vmin = float(np.nanmin(valid))
    vmax = float(np.nanmax(valid))
    levels = np.linspace(vmin, vmax, n_levels + 2)[1:-1]  # drop extremes
    return levels


def contours_to_polygons(data, transform, level):
    """
    Extract contours for a given level using skimage.measure.find_contours
    and convert them to Shapely polygons by filling between contours.

    For simplicity and robustness, we rasterize a binary mask >= level
    then polygonize.
    """
    mask = np.where(data >= level, 1, 0).astype("uint8")
    # Polygonize
    results = []
    for geom, val in shapes(mask, mask=mask.astype(bool), transform=transform):
        if val != 1:
            continue
        poly = shape(geom)
        if not isinstance(poly, (Polygon, MultiPolygon)):
            continue
        if isinstance(poly, MultiPolygon):
            for p in poly.geoms:
                results.append(p)
        else:
            results.append(poly)
    return results


def build_contour_tree(data, transform, crs):
    """
    Build a localized contour tree:
      - nodes: polygons at each contour level
      - hierarchy by geometric containment
    Returns:
      G (networkx.DiGraph), gdf_nodes (GeoDataFrame with node attributes)
    """
    levels = generate_contour_levels(data)
    print(f"Using {len(levels)} contour levels from {levels[0]:.3f} to {levels[-1]:.3f}")

    # Collect polygons for each level
    level_polys = []
    for lvl in levels:
        polys = contours_to_polygons(data, transform, lvl)
        print(f"Level {lvl:.3f}: {len(polys)} polygons before area filter")
        level_polys.append((lvl, polys))

    # Build node GeoDataFrame
    records = []
    node_id = 0
    aff = transform
    # Pixel area (approx): use local resolution from transform
    pixel_width = abs(aff.a)
    pixel_height = abs(aff.e)
    # convert grid cell area in deg^2 to m^2 approx if lat ~ 31° (Shanghai)
    # but we don't rely on this; we measure polygon area directly in CRS units.

    for lvl, polys in level_polys:
        for p in polys:
            # Skip very small polygons (in CRS units)
            area_crs = p.area  # in CRS units; EPSG:4326 -> degrees^2; we'll filter in projected later
            records.append(
                {
                    "node_id": node_id,
                    "level": lvl,
                    "geometry": p,
                    "area_crs": area_crs,
                }
            )
            node_id += 1

    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=crs)

    # Reproject to world mercator for area
    gdf = gdf.to_crs("EPSG:3857")
    gdf["area_m2"] = gdf.geometry.area
    gdf = gdf[gdf["area_m2"] >= MIN_POLYGON_AREA_HA * 1e4].copy()
    gdf.reset_index(drop=True, inplace=True)
    print(f"Kept {len(gdf)} polygons after area filter >= {MIN_POLYGON_AREA_HA} ha")

    # Update node_ids after filtering
    gdf["node_id"] = range(len(gdf))

    # Build tree: nodes sorted by level (ascending: outer to inner)
    gdf = gdf.sort_values(by="level", ascending=True).reset_index(drop=True)

    # Create graph; edges from parent (outer, lower level) to child (inner, higher level)
    G = nx.DiGraph()
    for _, row in gdf.iterrows():
        G.add_node(row["node_id"], level=row["level"], area_m2=row["area_m2"])

    # For containment tests, we iterate from low level to high level:
    # child polygons must be fully within parent polygons at lower levels.
    for i, row_i in gdf.iterrows():
        poly_i = row_i.geometry
        lvl_i = row_i.level
        nid_i = row_i.node_id

        # Only consider possible parents at lower level
        possible_parents = gdf[gdf["level"] < lvl_i]
        # For efficiency, limit to those that intersect bounding box
        for _, row_j in possible_parents.iterrows():
            if not row_j.geometry.bounds_intersects(poly_i):
                continue
            if row_j.geometry.contains(poly_i):
                G.add_edge(row_j.node_id, nid_i)

    # Record parent id if tree-like; if multiple parents, choose nearest in area
    parents = []
    for nid in gdf["node_id"]:
        preds = list(G.predecessors(nid))
        if len(preds) == 0:
            parents.append(None)
        elif len(preds) == 1:
            parents.append(preds[0])
        else:
            # pick parent with minimum area difference (more localized)
            areas = {p: G.nodes[p]["area_m2"] for p in preds}
            parent = min(areas, key=lambda k: abs(areas[k] - G.nodes[nid]["area_m2"]))
            # remove other parent edges
            for p in preds:
                if p != parent:
                    G.remove_edge(p, nid)
            parents.append(parent)
    gdf["parent_id"] = parents

    # Optional: compute number of children, depth etc.
    child_counts = {n: len(list(G.successors(n))) for n in G.nodes}
    gdf["n_children"] = gdf["node_id"].map(child_counts)

    return G, gdf


# ------------------------------------------------------------------------------
# STEP 3 – Identify elementary urban centers from the contour tree
# ------------------------------------------------------------------------------

def compute_mean_ntl_for_polygons(gdf, data, transform):
    """
    Compute mean NTL for each polygon by sampling raster.
    """
    inv_aff = ~transform
    ntl_means = []

    with rasterio.Env():
        height, width = data.shape

    for _, row in gdf.iterrows():
        poly = row.geometry
        # Work in raster index space: create mask by rasterizing polygon
        # For simplicity, we rasterize using rasterio.features.rasterize
        from rasterio.features import rasterize

        mask = rasterize(
            [(poly, 1)],
            out_shape=(height, width),
            transform=transform,
            fill=0,
            dtype="uint8",
            all_touched=False,
        )

        vals = data[(mask == 1) & (~np.isnan(data))]
        if vals.size == 0:
            ntl_means.append(float("nan"))
        else:
            ntl_means.append(float(np.mean(vals)))

    gdf["mean_ntl"] = ntl_means
    return gdf


def identify_elementary_centers(G, gdf):
    """
    Implement a heuristic approximation to Chen et al. (2017):
      - Sort levels; define "bright" levels above BRIGHTNESS_QUANTILE.
      - Elementary centers are bright polygons that are leaves or
        have only dark children, and exceed MIN_CENTER_AREA_HA.

    Returns: GeoDataFrame of center polygons.
    """
    # Determine bright threshold based on level distribution
    levels = np.array(sorted(gdf["level"].unique()))
    thr_level = float(np.quantile(levels, BRIGHTNESS_QUANTILE))
    print(f"Brightness level threshold (quantile {BRIGHTNESS_QUANTILE}): {thr_level:.3f}")

    gdf["is_bright_level"] = gdf["level"] >= thr_level

    # Determine bright/dark children for each node
    bright_centers = []
    for _, row in gdf.iterrows():
        nid = row["node_id"]
        lvl = row["level"]
        area_ha = row["area_m2"] / 1e4
        mean_ntl = row.get("mean_ntl", np.nan)

        # Skip too small polygons
        if area_ha < MIN_CENTER_AREA_HA:
            continue

        # Must be in bright levels
        if not row["is_bright_level"]:
            continue

        children = list(G.successors(nid))
        if len(children) == 0:
            # leaf at bright level → elementary center
            bright_centers.append(nid)
        else:
            # Check if children belong to lower levels (brighter, higher level)
            child_levels = gdf.set_index("node_id").loc[children, "level"].values
            # If all children less bright (lower level), treat parent as local maximum
            if np.all(child_levels < lvl):
                bright_centers.append(nid)

    centers_gdf = gdf[gdf["node_id"].isin(bright_centers)].copy()
    centers_gdf.reset_index(drop=True, inplace=True)

    print(f"Identified {len(centers_gdf)} elementary urban center polygons")

    # Merge overlapping centers to remove redundancy
    if len(centers_gdf) > 0:
        merged = unary_union(list(centers_gdf.geometry))
        if isinstance(merged, Polygon):
            merged = [merged]
        centers_gdf = gpd.GeoDataFrame(
            {"center_id": range(len(merged))},
            geometry=list(merged),
            crs=gdf.crs,
        )

        # Filter again by area
        centers_gdf["area_m2"] = centers_gdf.geometry.area
        centers_gdf = centers_gdf[centers_gdf["area_m2"] >= MIN_CENTER_AREA_HA * 1e4].copy()
        centers_gdf.reset_index(drop=True, inplace=True)
        print(f"{len(centers_gdf)} elementary centers after merging & area filter.")

    return centers_gdf


# ------------------------------------------------------------------------------
# MAIN WORKFLOW
# ------------------------------------------------------------------------------

def main():
    # Step 1 – Download annual NTL for Shanghai 2020 (if not already exists)
    ntl_path = os.path.join(OUT_DIR, "shanghai_ntl_2020_gee.tif")
    if not os.path.exists(ntl_path):
        ntl_path = step1_download_ntl_2020_shanghai()
    else:
        print(f"Using existing NTL raster: {ntl_path}")

    # Step 2 – Build localized contour tree
    data, transform, crs = raster_to_array(ntl_path)
    G, gdf_nodes = build_contour_tree(data, transform, crs)

    # Step 3 – Compute mean NTL per node
    gdf_nodes = compute_mean_ntl_for_polygons(gdf_nodes, data, transform)

    # Step 4 – Identify elementary urban centers
    centers_gdf = identify_elementary_centers(G, gdf_nodes)

    # Save results
    if len(centers_gdf) > 0:
        # Reproject back to WGS84 for user convenience
        centers_gdf = centers_gdf.to_crs("EPSG:4326")
        out_gpkg = os.path.join(OUT_DIR, "shanghai_urban_centers_2020.gpkg")
        out_shp = os.path.join(OUT_DIR, "shanghai_urban_centers_2020.shp")

        centers_gdf.to_file(out_gpkg, layer="urban_centers", driver="GPKG")
        centers_gdf.to_file(out_shp)

        print("Elementary urban centers saved to:")
        print(f"  - {out_gpkg}")
        print(f"  - {out_shp}")
    else:
        print("No elementary centers identified with current thresholds. "
              "Try lowering MIN_CENTER_AREA_HA or BRIGHTNESS_QUANTILE.")


if __name__ == "__main__":
    main()
```

---

Generated Files (after running):

- `outputs/shanghai_ntl_2020_gee.tif` – annual NPP‑VIIRS‑like NTL, clipped to Shanghai, 2020.  
- `outputs/shanghai_urban_centers_2020.gpkg` – polygons of elementary urban centers.  
- `outputs/shanghai_urban_centers_2020.shp` – same as Shapefile.

You can tune the behavior to better match Chen et al. (2017) by adjusting:  
- `MIN_NTL`, `N_CONTOUR_LEVELS` – contour tree resolution.  
- `MIN_POLYGON_AREA_HA`, `MIN_CENTER_AREA_HA` – size thresholds.  
- `BRIGHTNESS_QUANTILE` – how “bright” a contour must be to be considered a center.