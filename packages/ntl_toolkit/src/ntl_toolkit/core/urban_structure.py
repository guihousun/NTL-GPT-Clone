"""Deterministic localized-contour-tree urban-centre extraction.

This module implements the method described by Chen et al. (2017), rather
than asking the runtime agent to generate an algorithm at evaluation time.
The implementation keeps the three stages named in the paper explicit:

1. generate closed NTL contours from a smoothed raster;
2. build a localized contour tree from spatial containment;
3. simplify same-level branches and classify leaf/basic and composite nodes.

The public ``detect_urban_centres`` function is deliberately independent of
the LangChain tool layer.  It accepts already-resolved local paths and
returns a structured ``ToolResult`` only after all declared output files have
been written and re-opened for validation.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import CRS
from rasterio.features import geometry_mask
from scipy.ndimage import convolve, maximum_filter
from shapely import make_valid
from shapely.geometry import (
    LineString,
    MultiPolygon,
    Polygon,
    box,
    mapping,
)
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from skimage.measure import find_contours

from ..schemas.errors import ToolError
from ..schemas.results import OutputArtifact, ToolResult


TOOL_NAME = "detect_urban_centres"
PAPER_DOI = "10.1109/TGRS.2017.2725917"
ALGORITHM_VERSION = "chen2017-localized-contour-tree-v1"

# The fixed experimental configuration requested for the legacy Q70 case.
# This is a configuration record, not a result expectation: the algorithm
# never uses a presumed centre count.
CHEN2017_SHANGHAI_2014_CONFIG: dict[str, Any] = {
    "profile": "chen2017_shanghai_2014",
    "aoi": "Shanghai administrative boundary",
    "date": "2014-12",
    "product": "NPP-VIIRS Version 1 monthly composite",
    "unit": "nW/cm^2/sr",
    "aoi_buffer_km": 10.0,
    "gaussian_kernel": [3, 3],
    "gaussian_sigma": 1.0,
    "base_threshold": 34.0,
    "contour_interval": 1.0,
    "min_area_km2": 5.0,
    "target_pixel_size_m": 500.0,
}

_FLOAT_TOLERANCE = 1e-9
_GEOMETRY_TOLERANCE = 1e-7
_FIELD_ORDER = [
    "center_id",
    "tree_id",
    "parent_id",
    "child_ids",
    "level",
    "type",
    "main",
    "contour_v",
    "peak_ntl",
    "area_km2",
    "min_ntl",
    "max_ntl",
    "tntl",
    "avg_ntl",
    "std_ntl",
    "perim_km",
    "orient_deg",
    "compact",
    "elongated",
    "ulig",
    "n_children",
]
_SHAPEFILE_FIELD_TYPES = {
    "center_id": "str:16",
    "tree_id": "str:8",
    "parent_id": "str:16",
    "child_ids": "str:254",
    "level": "int:4",
    "type": "str:12",
    "main": "int:2",
    "contour_v": "float:24.8",
    "peak_ntl": "float:24.8",
    "area_km2": "float:24.8",
    "min_ntl": "float:24.8",
    "max_ntl": "float:24.8",
    "tntl": "float:24.8",
    "avg_ntl": "float:24.8",
    "std_ntl": "float:24.8",
    "perim_km": "float:24.8",
    "orient_deg": "float:24.8",
    "compact": "float:24.8",
    "elongated": "float:24.8",
    "ulig": "float:24.8",
    "n_children": "int:4",
}


@dataclass
class ContourNode:
    """A contour node used by the regular and simplified trees.

    ``has_local_peak`` is optional for hand-built test trees.  Production
    extraction always supplies the value computed from the smoothed raster.
    A node with ``None`` is treated as a seed only when it is a leaf; this
    keeps the topology helpers useful without allowing production code to
    silently invent peaks.
    """

    node_id: str
    geometry: BaseGeometry
    contour_value: float
    has_local_peak: bool | None = None
    peak_value: float | None = None
    parent_id: str | None = None
    children_ids: list[str] = field(default_factory=list)
    seed_ids: tuple[str, ...] = ()
    level: int = 0
    members: tuple[str, ...] = ()


def _tool_failure(code: str, message: str, *, details: dict[str, Any] | None = None, suggestion: str | None = None) -> ToolResult:
    return ToolResult.failed(
        tool=TOOL_NAME,
        error=ToolError(
            code=code,
            message=message,
            details=details or {},
            suggestion=suggestion,
        ),
    )


def _as_float(value: Any, *, parameter: str, minimum: float | None = None, strict_positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{parameter} must be numeric")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{parameter} must be finite")
    if strict_positive and converted <= 0:
        raise ValueError(f"{parameter} must be greater than zero")
    if minimum is not None and converted < minimum:
        raise ValueError(f"{parameter} must be at least {minimum}")
    return converted


def _normalize_unit(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = (
        str(value)
        .strip()
        .lower()
        .replace("²", "2")
        .replace("⁻", "-")
        .replace("·", " ")
        .replace("^", "")
        .replace(" ", "")
        .replace("cm-2", "cm2")
        .replace("sr-1", "sr1")
        .replace("nwcmsr", "nw/cm2/sr")
    )
    aliases = {
        "nw/cm2/sr": "nW/cm^2/sr",
        "nwcm2sr1": "nW/cm^2/sr",
        "nwcm-2sr-1": "nW/cm^2/sr",
        "nanowatt/cm2/sr": "nW/cm^2/sr",
        "nanowatts/cm2/sr": "nW/cm^2/sr",
        "nwcm²sr¹": "nW/cm^2/sr",
    }
    return aliases.get(normalized, str(value).strip())


def _unit_from_dataset(dataset: rasterio.io.DatasetReader) -> str | None:
    tags: dict[str, str] = {}
    tags.update({str(k).lower(): str(v) for k, v in dataset.tags().items()})
    tags.update({str(k).lower(): str(v) for k, v in dataset.tags(1).items()})
    for key in ("units", "unit", "radiance_unit", "radiance_units", "ntl_unit"):
        if tags.get(key):
            return _normalize_unit(tags[key])
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_node(node: ContourNode) -> ContourNode:
    return ContourNode(
        node_id=node.node_id,
        geometry=node.geometry,
        contour_value=float(node.contour_value),
        has_local_peak=node.has_local_peak,
        peak_value=node.peak_value,
        parent_id=node.parent_id,
        children_ids=list(node.children_ids),
        seed_ids=tuple(node.seed_ids),
        level=int(node.level),
        members=tuple(node.members),
    )


def _geometry_sort_key(geometry: BaseGeometry) -> tuple[float, float, float, str]:
    centroid = geometry.centroid
    return (
        -float(geometry.area),
        round(float(centroid.x), 9),
        round(float(centroid.y), 9),
        geometry.wkb_hex,
    )


def _validate_contour_nodes(contours: Sequence[ContourNode]) -> None:
    if not contours:
        raise ValueError("At least one contour node is required")
    ids = [node.node_id for node in contours]
    if len(set(ids)) != len(ids):
        raise ValueError("Contour node IDs must be unique")
    for node in contours:
        if not isinstance(node.geometry, (Polygon, MultiPolygon)):
            raise ValueError(f"Contour {node.node_id} is not a polygon geometry")
        if node.geometry.is_empty or not node.geometry.is_valid or node.geometry.area <= 0:
            raise ValueError(f"Contour {node.node_id} has invalid geometry")
        if not math.isfinite(float(node.contour_value)):
            raise ValueError(f"Contour {node.node_id} has an invalid contour value")


def _node_parent_by_containment(nodes: dict[str, ContourNode]) -> None:
    ordered = sorted(nodes.values(), key=lambda node: (float(node.geometry.area), node.node_id))
    for node in ordered:
        candidates: list[ContourNode] = []
        representative = node.geometry.representative_point()
        for candidate in ordered:
            if candidate.node_id == node.node_id:
                continue
            if candidate.geometry.area <= node.geometry.area * (1.0 + _GEOMETRY_TOLERANCE):
                continue
            if candidate.geometry.covers(representative):
                candidates.append(candidate)
        if candidates:
            parent = min(
                candidates,
                key=lambda candidate: (
                    float(candidate.geometry.area),
                    -float(candidate.contour_value),
                    candidate.node_id,
                ),
            )
            node.parent_id = parent.node_id
        else:
            node.parent_id = None

    for node in nodes.values():
        node.children_ids = []
    for node in nodes.values():
        if node.parent_id is not None:
            nodes[node.parent_id].children_ids.append(node.node_id)
    for node in nodes.values():
        node.children_ids.sort(
            key=lambda child_id: (
                float(nodes[child_id].geometry.area),
                float(nodes[child_id].contour_value),
                child_id,
            )
        )


def build_localized_contour_tree(contours: Sequence[ContourNode]) -> dict[str, ContourNode]:
    """Build and level a localized contour tree by spatial containment.

    The seed contours are leaf contours that contain a local peak.  For each
    outward contour, a level is unchanged while the contour contains only one
    seed branch.  A level increases by one only when two or more distinct seed
    branches merge at that contour.  This is the rule described in Section
    III-C of Chen et al. (2017), and is intentionally different from using
    the numeric radiance level as the hierarchy level.
    """

    _validate_contour_nodes(contours)
    nodes = {node.node_id: _copy_node(node) for node in contours}
    _node_parent_by_containment(nodes)

    ordered = sorted(nodes.values(), key=lambda node: (float(node.geometry.area), node.node_id))
    for node in ordered:
        if node.children_ids:
            seed_ids = set()
            for child_id in node.children_ids:
                seed_ids.update(nodes[child_id].seed_ids)
            node.seed_ids = tuple(sorted(seed_ids))
        else:
            is_seed = node.has_local_peak is not False
            node.seed_ids = (node.node_id,) if is_seed else ()

    keep_ids = {node.node_id for node in nodes.values() if node.seed_ids}
    if not keep_ids:
        raise ValueError("No contour leaf contains a local peak")

    # Remove unseeded branches while reconnecting each remaining node to its
    # nearest remaining outward contour.
    for node in nodes.values():
        if node.node_id not in keep_ids:
            continue
        parent_id = node.parent_id
        while parent_id is not None and parent_id not in keep_ids:
            parent_id = nodes[parent_id].parent_id
        node.parent_id = parent_id
        node.children_ids = []
    for node in nodes.values():
        if node.node_id in keep_ids and node.parent_id is not None:
            nodes[node.parent_id].children_ids.append(node.node_id)
    nodes = {node_id: node for node_id, node in nodes.items() if node_id in keep_ids}
    for node in nodes.values():
        node.children_ids.sort(
            key=lambda child_id: (
                float(nodes[child_id].geometry.area),
                float(nodes[child_id].contour_value),
                child_id,
            )
        )

    ordered = sorted(nodes.values(), key=lambda node: (float(node.geometry.area), node.node_id))
    for node in ordered:
        if not node.children_ids:
            node.level = 1
            continue
        child_levels = [nodes[child_id].level for child_id in node.children_ids]
        child_seed_sets = {
            frozenset(nodes[child_id].seed_ids) for child_id in node.children_ids
        }
        node.level = max(child_levels) + (1 if len(child_seed_sets) >= 2 else 0)
        node.seed_ids = tuple(
            sorted(
                seed_id
                for child_id in node.children_ids
                for seed_id in nodes[child_id].seed_ids
            )
        )

    return nodes


class _UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        root = value
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[value] != value:
            next_value = self.parent[value]
            self.parent[value] = root
            value = next_value
        return root

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def _simplify_contour_tree_with_mapping(
    nodes: dict[str, ContourNode],
) -> tuple[dict[str, ContourNode], dict[str, str]]:
    if not nodes:
        raise ValueError("Cannot simplify an empty contour tree")
    union_find = _UnionFind(nodes)
    for node in nodes.values():
        if node.parent_id is not None and nodes[node.parent_id].level == node.level:
            union_find.union(node.node_id, node.parent_id)

    components: dict[str, list[ContourNode]] = {}
    for node in nodes.values():
        components.setdefault(union_find.find(node.node_id), []).append(node)

    representative_by_component: dict[str, str] = {}
    for component_id, members in components.items():
        member_ids = {member.node_id for member in members}
        outer_members = [
            member
            for member in members
            if member.parent_id not in member_ids
        ]
        representative = min(
            outer_members or members,
            key=lambda member: (
                -float(member.geometry.area),
                -float(member.contour_value),
                member.node_id,
            ),
        )
        representative_by_component[component_id] = representative.node_id

    representative_for: dict[str, str] = {}
    for component_id, members in components.items():
        representative = representative_by_component[component_id]
        for member in members:
            representative_for[member.node_id] = representative

    simplified: dict[str, ContourNode] = {}
    for component_id, members in components.items():
        representative_id = representative_by_component[component_id]
        representative = nodes[representative_id]
        parent_id: str | None = None
        if representative.parent_id is not None:
            parent_id = representative_for[representative.parent_id]
            if parent_id == representative_id:
                parent_id = None
        simplified[representative_id] = ContourNode(
            node_id=representative_id,
            geometry=representative.geometry,
            contour_value=representative.contour_value,
            has_local_peak=representative.has_local_peak,
            peak_value=representative.peak_value,
            parent_id=parent_id,
            children_ids=[],
            seed_ids=representative.seed_ids,
            level=representative.level,
            members=tuple(sorted(member.node_id for member in members)),
        )

    for node in simplified.values():
        if node.parent_id is not None:
            simplified[node.parent_id].children_ids.append(node.node_id)
    for node in simplified.values():
        node.children_ids.sort(
            key=lambda child_id: (
                int(simplified[child_id].level),
                float(simplified[child_id].geometry.area),
                child_id,
            )
        )
    return simplified, representative_for


def simplify_contour_tree(nodes: dict[str, ContourNode]) -> dict[str, ContourNode]:
    """Collapse same-level branches and retain the outward contour.

    A branch with no topological change is represented by its last/outward
    node, exactly as the paper keeps ``T`` for the ``S2--T`` branch and ``V``
    for the ``U--V`` branch in Fig. 3.  The returned graph is a simplified
    contour tree whose level-1 leaves are basic/elemental centres and whose
    higher-level internal nodes are composite centres.
    """

    simplified, _ = _simplify_contour_tree_with_mapping(nodes)
    return simplified


def _kernel_3x3(sigma: float) -> np.ndarray:
    coordinates = np.arange(-1.0, 2.0, dtype=np.float64)
    yy, xx = np.meshgrid(coordinates, coordinates, indexing="ij")
    kernel = np.exp(-((xx * xx) + (yy * yy)) / (2.0 * sigma * sigma))
    return kernel / float(kernel.sum())


def smooth_ntl_3x3(data: np.ndarray, valid_mask: np.ndarray, *, sigma: float = 1.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Apply the paper's 3x3 Gaussian filter with deterministic nodata handling."""

    kernel = _kernel_3x3(sigma)
    valid_float = valid_mask.astype(np.float64)
    filled = np.where(valid_mask, data, 0.0).astype(np.float64)
    numerator = convolve(filled, kernel, mode="nearest")
    denominator = convolve(valid_float, kernel, mode="nearest")
    smoothed = np.full(data.shape, np.nan, dtype=np.float64)
    np.divide(numerator, denominator, out=smoothed, where=denominator > 0)
    smoothed_valid = valid_mask & np.isfinite(smoothed)
    return smoothed, smoothed_valid, kernel


def _contour_xy(points: np.ndarray, transform: rasterio.Affine) -> np.ndarray:
    xy = np.empty((len(points), 2), dtype=np.float64)
    for index, (row, column) in enumerate(points):
        x, y = transform * (float(column) + 0.5, float(row) + 0.5)
        xy[index] = (x, y)
    return xy


def _polygon_parts(geometry: BaseGeometry) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    if geometry.geom_type == "GeometryCollection":
        parts: list[Polygon] = []
        for part in geometry.geoms:
            parts.extend(_polygon_parts(part))
        return parts
    return []


def _valid_contour_polygon(line: LineString) -> list[Polygon]:
    if len(line.coords) < 4 or not line.is_ring or line.length <= 0:
        return []
    polygon = Polygon(line.coords)
    if polygon.is_valid and not polygon.is_empty:
        return [polygon]
    repaired = make_valid(polygon)
    return [part for part in _polygon_parts(repaired) if part.is_valid and not part.is_empty]


def _contains_local_peak(
    smoothed: np.ndarray,
    valid_mask: np.ndarray,
    geometry: Polygon,
    transform: rasterio.Affine,
    contour_value: float,
) -> tuple[bool, float | None]:
    inside = geometry_mask(
        [mapping(geometry)],
        out_shape=smoothed.shape,
        transform=transform,
        invert=True,
        all_touched=False,
    )
    candidates = inside & valid_mask & np.isfinite(smoothed) & (smoothed > contour_value + _FLOAT_TOLERANCE)
    if not np.any(candidates):
        return False, None
    values = np.where(np.isfinite(smoothed), smoothed, -np.inf)
    neighborhood_max = maximum_filter(values, size=3, mode="nearest")
    local_maxima = candidates & (values >= neighborhood_max - _FLOAT_TOLERANCE)
    if not np.any(local_maxima):
        return False, None
    peak_value = float(np.max(values[local_maxima]))
    return True, peak_value


def _extract_contour_nodes(
    smoothed: np.ndarray,
    valid_mask: np.ndarray,
    transform: rasterio.Affine,
    *,
    base_threshold: float,
    contour_interval: float,
    min_area_km2: float,
) -> tuple[list[ContourNode], dict[str, int | float]]:
    finite_values = smoothed[valid_mask & np.isfinite(smoothed)]
    if finite_values.size == 0 or float(np.nanmax(finite_values)) <= base_threshold:
        return [], {
            "levels_considered": 0,
            "closed_contours": 0,
            "open_contours": 0,
            "area_filtered_contours": 0,
        }

    max_value = float(np.nanmax(finite_values))
    level_count = int(math.floor((max_value - base_threshold) / contour_interval + _FLOAT_TOLERANCE))
    levels = [base_threshold + index * contour_interval for index in range(level_count + 1)]
    # A contour at the exact maximum has no crossing in a raster cell and is
    # not a contour line; keep it in the metadata but do not request it.
    levels = [level for level in levels if level < max_value - _FLOAT_TOLERANCE]
    plotting_array = np.where(valid_mask & np.isfinite(smoothed), smoothed, base_threshold - contour_interval)
    candidate_records: list[tuple[float, Polygon, bool, float | None]] = []
    open_count = 0
    closed_count = 0
    area_filtered_count = 0

    for level in levels:
        raw_contours = find_contours(
            plotting_array,
            level=float(level),
            fully_connected="high",
            positive_orientation="low",
        )
        for points in raw_contours:
            if len(points) < 4 or np.linalg.norm(points[0] - points[-1]) > 1e-6:
                open_count += 1
                continue
            if (
                np.any(points[:, 0] <= 0.0)
                or np.any(points[:, 0] >= smoothed.shape[0] - 1.0)
                or np.any(points[:, 1] <= 0.0)
                or np.any(points[:, 1] >= smoothed.shape[1] - 1.0)
            ):
                open_count += 1
                continue
            line = LineString(_contour_xy(points, transform))
            polygons = _valid_contour_polygon(line)
            if not polygons:
                open_count += 1
                continue
            for polygon in polygons:
                closed_count += 1
                if polygon.area / 1_000_000.0 + _FLOAT_TOLERANCE < min_area_km2:
                    area_filtered_count += 1
                    continue
                inside = geometry_mask(
                    [mapping(polygon)],
                    out_shape=smoothed.shape,
                    transform=transform,
                    invert=True,
                    all_touched=False,
                )
                if not np.any(inside & valid_mask):
                    continue
                if np.any(inside & ~valid_mask):
                    # A contour crossing missing source observations is not a
                    # closed data-supported contour and must not become a
                    # false urban centre.
                    open_count += 1
                    continue
                has_peak, peak_value = _contains_local_peak(
                    smoothed,
                    valid_mask,
                    polygon,
                    transform,
                    float(level),
                )
                candidate_records.append((float(level), polygon, has_peak, peak_value))

    candidate_records.sort(
        key=lambda record: (
            record[0],
            _geometry_sort_key(record[1]),
            record[1].wkb_hex,
        )
    )
    nodes: list[ContourNode] = []
    for index, (level, polygon, has_peak, peak_value) in enumerate(candidate_records, start=1):
        nodes.append(
            ContourNode(
                node_id=f"C{index:06d}",
                geometry=polygon,
                contour_value=level,
                has_local_peak=has_peak,
                peak_value=peak_value,
            )
        )
    return nodes, {
        "levels_considered": len(levels),
        "closed_contours": int(closed_count),
        "open_contours": int(open_count),
        "area_filtered_contours": int(area_filtered_count),
    }


def _resolve_polygonal_aoi(path: Path, target_crs: CRS) -> tuple[BaseGeometry, str]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    aoi = gpd.read_file(path)
    if aoi.empty:
        raise ValueError("AOI vector is empty")
    if aoi.crs is None:
        raise ValueError("AOI vector CRS is missing")
    if any(geometry is None or geometry.is_empty or not geometry.is_valid for geometry in aoi.geometry):
        raise ValueError("AOI vector contains empty or invalid geometry")
    if not all(geometry.geom_type in {"Polygon", "MultiPolygon"} for geometry in aoi.geometry):
        raise ValueError("AOI vector must contain polygon or multipolygon geometry")
    projected = aoi.to_crs(target_crs)
    geometry = unary_union(list(projected.geometry))
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("AOI union is empty or invalid")
    return geometry, str(aoi.crs)


def _clip_polygonal_geometry(geometry: BaseGeometry, aoi: BaseGeometry) -> BaseGeometry:
    clipped = geometry.intersection(aoi)
    parts = _polygon_parts(clipped)
    if not parts:
        return Polygon()
    merged = unary_union(parts)
    if not merged.is_valid:
        merged = make_valid(merged)
    return merged


def _raster_stats(
    geometry: BaseGeometry,
    data: np.ndarray,
    valid_mask: np.ndarray,
    smoothed: np.ndarray,
    slope: np.ndarray,
    transform: rasterio.Affine,
    *,
    pixel_area_km2: float,
) -> dict[str, float]:
    inside = geometry_mask(
        [mapping(geometry)],
        out_shape=data.shape,
        transform=transform,
        invert=True,
        all_touched=False,
    )
    source_values = data[inside & valid_mask & np.isfinite(data)]
    smoothed_values = smoothed[inside & np.isfinite(smoothed)]
    slope_values = slope[inside & np.isfinite(slope)]
    if source_values.size == 0:
        raise ValueError("Output center contains no valid raster pixels")

    minimum_rotated_rectangle = geometry.minimum_rotated_rectangle
    rectangle_coords = list(minimum_rotated_rectangle.exterior.coords) if not minimum_rotated_rectangle.is_empty else []
    edge_lengths: list[tuple[float, float, float]] = []
    for start, end in zip(rectangle_coords[:-1], rectangle_coords[1:]):
        dx = float(end[0] - start[0])
        dy = float(end[1] - start[1])
        length = math.hypot(dx, dy)
        if length > _GEOMETRY_TOLERANCE:
            angle = math.degrees(math.atan2(dy, dx)) % 180.0
            edge_lengths.append((length, angle, dx))
    if edge_lengths:
        major_length, orientation, _ = max(edge_lengths, key=lambda item: (item[0], -item[1]))
        minor_length = min(item[0] for item in edge_lengths)
    else:
        major_length = minor_length = 0.0
        orientation = 0.0
    perimeter = float(geometry.length)
    area_km2 = float(geometry.area / 1_000_000.0)
    compactness = float(4.0 * math.pi * geometry.area / (perimeter * perimeter)) if perimeter > 0 else 0.0
    elongatedness = float(major_length / minor_length) if minor_length > 0 else 0.0
    return {
        "contour_v": float("nan"),
        "peak_ntl": float(np.nanmax(smoothed_values)) if smoothed_values.size else float("nan"),
        "area_km2": area_km2,
        "min_ntl": float(np.nanmin(source_values)),
        "max_ntl": float(np.nanmax(source_values)),
        "tntl": float(np.nansum(source_values)),
        "avg_ntl": float(np.nanmean(source_values)),
        "std_ntl": float(np.nanstd(source_values)),
        "perim_km": perimeter / 1_000.0,
        "orient_deg": float(orientation),
        "compact": compactness,
        "elongated": elongatedness,
        "ulig": float(np.nanmean(slope_values)) if slope_values.size else 0.0,
        "n_children": 0.0,
        "_pixel_count": float(source_values.size),
        "_area_from_pixels_km2": float(source_values.size * pixel_area_km2),
    }


def _reserve_single_path(requested: Path) -> Path:
    requested = requested.expanduser().resolve(strict=False)
    requested.parent.mkdir(parents=True, exist_ok=True)
    if not requested.exists():
        return requested
    for index in range(1, 10000):
        candidate = requested.with_name(f"{requested.stem}_{index:03d}{requested.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to reserve an output path for {requested}")


def _reserve_vector_path(requested: Path) -> Path:
    requested = requested.expanduser().resolve(strict=False)
    requested.parent.mkdir(parents=True, exist_ok=True)
    sidecars = [".shp", ".shx", ".dbf", ".prj", ".cpg"]
    for index in range(0, 10000):
        if index == 0:
            candidate = requested
        else:
            candidate = requested.with_name(f"{requested.stem}_{index:03d}{requested.suffix}")
        if candidate.suffix.lower() == ".shp":
            if not any(candidate.with_suffix(suffix).exists() for suffix in sidecars):
                return candidate
        elif not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to reserve a vector output path for {requested}")


def _vector_files(path: Path) -> list[Path]:
    if path.suffix.lower() == ".shp":
        return [path.with_suffix(suffix) for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg")]
    return [path]


def _cleanup_paths(paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            if path.exists() and path.is_file():
                path.unlink()
        except OSError:
            pass


def _write_vector(path: Path, rows: list[dict[str, Any]], geometries: list[BaseGeometry], crs: CRS) -> None:
    frame = pd.DataFrame(rows, columns=_FIELD_ORDER)
    frame["geometry"] = geometries
    gdf = gpd.GeoDataFrame(frame, geometry="geometry", crs=crs)
    if path.suffix.lower() == ".shp":
        gdf.to_file(
            path,
            driver="ESRI Shapefile",
            index=False,
            encoding="UTF-8",
            engine="fiona",
        )
    elif path.suffix.lower() in {".geojson", ".json"}:
        gdf.to_file(path, driver="GeoJSON", index=False, engine="fiona")
    elif path.suffix.lower() == ".gpkg":
        gdf.to_file(path, driver="GPKG", layer="urban_centres", index=False, engine="fiona")
    else:
        raise ValueError("Vector output must use .shp, .geojson, .json, or .gpkg")


def _validate_written_outputs(vector_path: Path, csv_path: Path, metadata_path: Path, expected_ids: set[str]) -> dict[str, Any]:
    vector_files = _vector_files(vector_path)
    missing_or_empty = [str(path) for path in vector_files if not path.exists() or path.stat().st_size <= 0]
    for path in (csv_path, metadata_path):
        if not path.exists() or path.stat().st_size <= 0:
            missing_or_empty.append(str(path))
    if missing_or_empty:
        raise ValueError(f"Missing or empty output files: {missing_or_empty}")

    written = gpd.read_file(vector_path)
    if written.empty or len(written) != len(expected_ids):
        raise ValueError("Vector output is empty or has an unexpected feature count")
    if "center_id" not in written.columns or set(written["center_id"].astype(str)) != expected_ids:
        raise ValueError("Vector output center IDs do not match the computed records")
    if any(geometry is None or geometry.is_empty or not geometry.is_valid for geometry in written.geometry):
        raise ValueError("Vector output contains empty or invalid geometry")

    csv_frame = pd.read_csv(csv_path, dtype={"center_id": str}, keep_default_na=False)
    if csv_frame.empty or len(csv_frame) != len(expected_ids):
        raise ValueError("CSV output is empty or has an unexpected row count")
    if "center_id" not in csv_frame.columns or set(csv_frame["center_id"].astype(str)) != expected_ids:
        raise ValueError("CSV center IDs do not match the vector output")
    with metadata_path.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    if not isinstance(metadata, dict) or metadata.get("schema") != "ntl.urban_structure.metadata.v1":
        raise ValueError("Metadata JSON has an invalid schema")
    return {
        "vector_feature_count": int(len(written)),
        "csv_row_count": int(len(csv_frame)),
        "geometry_valid": True,
        "metadata_valid": True,
    }


def _profile_validation(
    profile: str | None,
    *,
    aoi_buffer_km: float,
    gaussian_kernel: int,
    gaussian_sigma: float,
    base_threshold: float,
    contour_interval: float,
    min_area_km2: float,
) -> None:
    if profile is None:
        return
    if profile != CHEN2017_SHANGHAI_2014_CONFIG["profile"]:
        raise ValueError(f"Unknown parameter profile: {profile}")
    expected = CHEN2017_SHANGHAI_2014_CONFIG
    actual = {
        "aoi_buffer_km": aoi_buffer_km,
        "gaussian_kernel": gaussian_kernel,
        "gaussian_sigma": gaussian_sigma,
        "base_threshold": base_threshold,
        "contour_interval": contour_interval,
        "min_area_km2": min_area_km2,
    }
    expected_values = {
        "aoi_buffer_km": expected["aoi_buffer_km"],
        "gaussian_kernel": expected["gaussian_kernel"][0],
        "gaussian_sigma": expected["gaussian_sigma"],
        "base_threshold": expected["base_threshold"],
        "contour_interval": expected["contour_interval"],
        "min_area_km2": expected["min_area_km2"],
    }
    conflicts = {
        key: {"expected": expected_values[key], "actual": value}
        for key, value in actual.items()
        if value != expected_values[key]
    }
    if conflicts:
        raise ValueError(f"Parameter profile conflicts with supplied values: {conflicts}")


def detect_urban_centres(
    raster_path: str | Path,
    aoi_path: str | Path,
    vector_output_path: str | Path,
    csv_output_path: str | Path,
    metadata_output_path: str | Path | None = None,
    *,
    base_threshold: float = 34.0,
    contour_interval: float = 1.0,
    min_area_km2: float = 5.0,
    gaussian_kernel: int = 3,
    gaussian_sigma: float = 1.0,
    aoi_buffer_km: float = 10.0,
    expected_unit: str | None = None,
    parameter_profile: str | None = None,
) -> ToolResult:
    """Run the deterministic Chen et al. localized contour-tree method."""

    raster_path = Path(raster_path).expanduser().resolve(strict=False)
    aoi_path = Path(aoi_path).expanduser().resolve(strict=False)
    vector_requested = Path(vector_output_path).expanduser().resolve(strict=False)
    csv_requested = Path(csv_output_path).expanduser().resolve(strict=False)
    metadata_requested = (
        Path(metadata_output_path).expanduser().resolve(strict=False)
        if metadata_output_path is not None
        else csv_requested.with_name(f"{csv_requested.stem}.metadata.json")
    )
    reserved_vector: Path | None = None
    reserved_csv: Path | None = None
    reserved_metadata: Path | None = None

    try:
        base_threshold = _as_float(base_threshold, parameter="base_threshold", minimum=0.0)
        contour_interval = _as_float(contour_interval, parameter="contour_interval", strict_positive=True)
        min_area_km2 = _as_float(min_area_km2, parameter="min_area_km2", minimum=0.0)
        gaussian_sigma = _as_float(gaussian_sigma, parameter="gaussian_sigma", strict_positive=True)
        aoi_buffer_km = _as_float(aoi_buffer_km, parameter="aoi_buffer_km", minimum=0.0)
        if isinstance(gaussian_kernel, bool) or int(gaussian_kernel) != gaussian_kernel or int(gaussian_kernel) != 3:
            raise ValueError("gaussian_kernel must be the fixed 3x3 kernel")
        gaussian_kernel = int(gaussian_kernel)
        _profile_validation(
            parameter_profile,
            aoi_buffer_km=aoi_buffer_km,
            gaussian_kernel=gaussian_kernel,
            gaussian_sigma=gaussian_sigma,
            base_threshold=base_threshold,
            contour_interval=contour_interval,
            min_area_km2=min_area_km2,
        )
    except (TypeError, ValueError) as exc:
        return _tool_failure(
            "INVALID_PARAMETER",
            str(exc),
            details={"parameter_profile": parameter_profile},
        )

    try:
        if not raster_path.exists():
            return _tool_failure(
                "INPUT_NOT_FOUND",
                f"Input raster was not found: {raster_path}",
                details={"path": str(raster_path)},
            )
        if not aoi_path.exists():
            return _tool_failure(
                "INPUT_NOT_FOUND",
                f"AOI vector was not found: {aoi_path}",
                details={"path": str(aoi_path)},
            )

        with rasterio.open(raster_path) as dataset:
            if dataset.count != 1:
                return _tool_failure(
                    "INVALID_RASTER",
                    "Urban-centre extraction requires a single-band NTL raster.",
                    details={"band_count": int(dataset.count)},
                )
            if dataset.crs is None:
                return _tool_failure("CRS_MISSING", "Input raster CRS is missing.")
            raster_crs = CRS.from_user_input(dataset.crs)
            linear_units = (
                raster_crs.axis_info[0].unit_name
                if raster_crs.axis_info
                else None
            )
            if not raster_crs.is_projected or str(linear_units).lower() not in {"metre", "meter", "metres", "meters"}:
                return _tool_failure(
                    "CRS_NOT_PROJECTED_METRIC",
                    "Input raster must use a projected CRS with metre units for contour areas.",
                    details={"crs": raster_crs.to_string(), "linear_units": linear_units},
                )
            x_resolution = abs(float(dataset.transform.a))
            y_resolution = abs(float(dataset.transform.e))
            if x_resolution <= 0 or y_resolution <= 0:
                return _tool_failure("INVALID_RASTER", "Input raster has an invalid pixel size.")
            if parameter_profile == CHEN2017_SHANGHAI_2014_CONFIG["profile"]:
                target_size = float(CHEN2017_SHANGHAI_2014_CONFIG["target_pixel_size_m"])
                if abs(x_resolution - target_size) > target_size * 0.05 or abs(y_resolution - target_size) > target_size * 0.05:
                    return _tool_failure(
                        "PIXEL_SIZE_MISMATCH",
                        "The Chen 2017 Shanghai profile requires approximately 500 m pixels.",
                        details={"x_resolution_m": x_resolution, "y_resolution_m": y_resolution},
                    )
            masked = dataset.read(1, masked=True)
            data = np.asarray(masked.filled(np.nan), dtype=np.float64)
            valid_mask = (~np.ma.getmaskarray(masked)) & np.isfinite(data)
            if not np.any(valid_mask):
                return _tool_failure("NO_VALID_RASTER_DATA", "Input raster contains no valid NTL pixels.")
            unit = _unit_from_dataset(dataset)
            override_unit = _normalize_unit(expected_unit)
            if unit is None and override_unit is not None:
                unit = override_unit
                unit_source = "explicit_parameter"
            else:
                unit_source = "raster_metadata"
            if override_unit is not None and unit is not None and unit != override_unit:
                return _tool_failure(
                    "UNIT_MISMATCH",
                    "The explicit expected unit conflicts with the raster unit metadata.",
                    details={"raster_unit": unit, "expected_unit": override_unit},
                )
            if unit is None:
                return _tool_failure(
                    "UNIT_MISSING",
                    "Input raster does not declare an NTL radiance unit.",
                    suggestion="Add a raster unit tag or supply the explicit expected_unit parameter.",
                )
            if unit != "nW/cm^2/sr":
                return _tool_failure(
                    "UNIT_MISMATCH",
                    "Input raster unit is not nW/cm^2/sr.",
                    details={"unit": unit},
                )
            raster_transform = dataset.transform
            raster_bounds = box(*dataset.bounds)
            input_nodata = dataset.nodata
            input_tags = {str(key): str(value) for key, value in dataset.tags().items()}

        aoi_geometry, aoi_crs = _resolve_polygonal_aoi(aoi_path, raster_crs)
        aoi_buffer = aoi_geometry.buffer(aoi_buffer_km * 1000.0)
        coverage_gap = aoi_buffer.difference(raster_bounds)
        if not coverage_gap.is_empty and coverage_gap.area > max(x_resolution, y_resolution) ** 2:
            return _tool_failure(
                "INPUT_COVERAGE_INSUFFICIENT",
                "Input raster does not cover the AOI plus the required outer buffer.",
                details={
                    "aoi_buffer_km": aoi_buffer_km,
                    "raster_bounds": list(map(float, raster_bounds.bounds)),
                    "missing_area_m2": float(coverage_gap.area),
                },
                suggestion="Provide a raster covering the Shanghai boundary plus a 10 km buffer.",
            )

        smoothed, smoothed_valid, _ = smooth_ntl_3x3(
            data,
            valid_mask,
            sigma=gaussian_sigma,
        )
        gradient_y, gradient_x = np.gradient(
            np.where(smoothed_valid, smoothed, np.nan_to_num(smoothed, nan=0.0)),
            y_resolution,
            x_resolution,
        )
        slope = np.sqrt(gradient_x * gradient_x + gradient_y * gradient_y)
        slope[~smoothed_valid] = np.nan
        contours, contour_metrics = _extract_contour_nodes(
            smoothed,
            smoothed_valid,
            raster_transform,
            base_threshold=base_threshold,
            contour_interval=contour_interval,
            min_area_km2=min_area_km2,
        )
        if not contours:
            return _tool_failure(
                "NO_CLOSED_CONTOURS",
                "No closed, area-qualified NTL contour was generated above the base threshold.",
                details=contour_metrics,
            )
        try:
            regular_tree = build_localized_contour_tree(contours)
            simplified_tree, _ = _simplify_contour_tree_with_mapping(regular_tree)
        except ValueError as exc:
            return _tool_failure(
                "NO_VALID_CENTERS",
                f"Contour tree construction produced no valid urban centre: {exc}",
                details=contour_metrics,
            )
        if not simplified_tree:
            return _tool_failure("NO_VALID_CENTERS", "Simplified contour tree is empty.")

        clipped_geometry: dict[str, BaseGeometry] = {}
        for node_id, node in simplified_tree.items():
            clipped = _clip_polygonal_geometry(node.geometry, aoi_geometry)
            if clipped.is_empty:
                # The input deliberately includes a buffer.  A contour tree
                # can therefore contain a valid centre wholly outside the
                # requested AOI; it is excluded from the final result rather
                # than emitted as an empty geometry.
                continue
            if not clipped.is_valid:
                return _tool_failure(
                    "INVALID_GEOMETRY",
                    f"Clipping contour node {node_id} produced an invalid geometry.",
                    details={"node_id": node_id},
                )
            clipped_geometry[node_id] = clipped
        if not clipped_geometry:
            return _tool_failure(
                "NO_VALID_CENTERS",
                "All area-qualified contour nodes fall outside the requested AOI.",
            )
        retained_ids = set(clipped_geometry)
        if retained_ids != set(simplified_tree):
            # Reconnect retained nodes through discarded buffer-only nodes so
            # parent/child IDs remain a valid tree after AOI clipping.
            for node in simplified_tree.values():
                if node.node_id not in retained_ids:
                    continue
                parent_id = node.parent_id
                while parent_id is not None and parent_id not in retained_ids:
                    parent_id = simplified_tree[parent_id].parent_id
                node.parent_id = parent_id
                node.children_ids = []
            for node in simplified_tree.values():
                if node.node_id in retained_ids and node.parent_id is not None:
                    simplified_tree[node.parent_id].children_ids.append(node.node_id)
            simplified_tree = {
                node_id: node
                for node_id, node in simplified_tree.items()
                if node_id in retained_ids
            }
            for node in simplified_tree.values():
                node.children_ids.sort()

        roots = [node for node in simplified_tree.values() if node.parent_id is None]
        roots.sort(key=lambda node: (-float(node.geometry.area), node.node_id))
        root_for: dict[str, str] = {}
        for root in roots:
            stack = [root.node_id]
            while stack:
                current = stack.pop()
                root_for[current] = root.node_id
                stack.extend(reversed(simplified_tree[current].children_ids))

        tree_id_for_root = {root.node_id: f"T{index:02d}" for index, root in enumerate(roots, start=1)}
        ordered_nodes: list[tuple[str, ContourNode]] = []
        for root in roots:
            tree_nodes = [node for node in simplified_tree.values() if root_for[node.node_id] == root.node_id]
            tree_nodes.sort(
                key=lambda node: (
                    int(node.level),
                    -float(node.geometry.area),
                    -float(node.peak_value if node.peak_value is not None else -math.inf),
                    round(float(node.geometry.centroid.x), 9),
                    round(float(node.geometry.centroid.y), 9),
                    node.node_id,
                )
            )
            ordered_nodes.extend((tree_id_for_root[root.node_id], node) for node in tree_nodes)

        assigned_ids: dict[str, str] = {}
        for tree_id, group in itertools.groupby(ordered_nodes, key=lambda item: item[0]):
            for index, (_, node) in enumerate(group, start=1):
                assigned_ids[node.node_id] = f"{tree_id}N{index:03d}"
        pixel_area_km2 = abs(x_resolution * y_resolution) / 1_000_000.0
        rows: list[dict[str, Any]] = []
        geometries: list[BaseGeometry] = []
        for tree_id, node in ordered_nodes:
            geometry = clipped_geometry[node.node_id]
            stats = _raster_stats(
                geometry,
                data,
                valid_mask,
                smoothed,
                slope,
                raster_transform,
                pixel_area_km2=pixel_area_km2,
            )
            is_basic = len(node.children_ids) == 0
            rows.append(
                {
                    "center_id": assigned_ids[node.node_id],
                    "tree_id": tree_id,
                    "parent_id": assigned_ids.get(node.parent_id, "") if node.parent_id else "",
                    "child_ids": ";".join(assigned_ids[child_id] for child_id in node.children_ids),
                    "level": int(node.level),
                    "type": "basic" if is_basic else "composite",
                    "main": 0,
                    "contour_v": float(node.contour_value),
                    "peak_ntl": float(stats["peak_ntl"]),
                    "area_km2": float(stats["area_km2"]),
                    "min_ntl": float(stats["min_ntl"]),
                    "max_ntl": float(stats["max_ntl"]),
                    "tntl": float(stats["tntl"]),
                    "avg_ntl": float(stats["avg_ntl"]),
                    "std_ntl": float(stats["std_ntl"]),
                    "perim_km": float(stats["perim_km"]),
                    "orient_deg": float(stats["orient_deg"]),
                    "compact": float(stats["compact"]),
                    "elongated": float(stats["elongated"]),
                    "ulig": float(stats["ulig"]),
                    "n_children": int(len(node.children_ids)),
                    "_node_id": node.node_id,
                    "_root_id": root_for[node.node_id],
                    "_members": list(node.members),
                    "_pixel_count": int(stats["_pixel_count"]),
                }
            )
            geometries.append(geometry)

        main_tree_id = tree_id_for_root[roots[0].node_id] if roots else None
        basic_rows = [row for row in rows if row["type"] == "basic" and row["tree_id"] == main_tree_id]
        if basic_rows:
            main_row = max(basic_rows, key=lambda row: (float(row["area_km2"]), float(row["avg_ntl"]), row["center_id"]))
            main_row["main"] = 1

        rows = [
            {key: row[key] for key in _FIELD_ORDER}
            for row in rows
        ]
        expected_ids = {str(row["center_id"]) for row in rows}
        if not rows or not expected_ids:
            return _tool_failure("NO_VALID_CENTERS", "No urban centre record was produced.")

        reserved_vector = _reserve_vector_path(vector_requested)
        reserved_csv = _reserve_single_path(csv_requested)
        reserved_metadata = _reserve_single_path(metadata_requested)
        _write_vector(reserved_vector, rows, geometries, raster_crs)
        csv_frame = pd.DataFrame(rows, columns=_FIELD_ORDER)
        csv_frame.to_csv(
            reserved_csv,
            index=False,
            encoding="utf-8",
            lineterminator="\n",
            float_format="%.12g",
        )

        vector_hashes = {
            path.name: _sha256(path)
            for path in _vector_files(reserved_vector)
            if path.exists()
        }
        metadata = {
            "schema": "ntl.urban_structure.metadata.v1",
            "algorithm": {
                "name": "localized contour tree",
                "version": ALGORITHM_VERSION,
                "paper_doi": PAPER_DOI,
                "deterministic": True,
                "random_steps": False,
            },
            "parameters": {
                "parameter_profile": parameter_profile,
                "base_threshold": base_threshold,
                "contour_interval": contour_interval,
                "min_area_km2": min_area_km2,
                "gaussian_kernel": [gaussian_kernel, gaussian_kernel],
                "gaussian_sigma": gaussian_sigma,
                "aoi_buffer_km": aoi_buffer_km,
                "unit": unit,
                "unit_source": unit_source,
                "pixel_size_m": [x_resolution, y_resolution],
            },
            "input": {
                "raster_name": raster_path.name,
                "raster_sha256": _sha256(raster_path),
                "band_count": 1,
                "nodata": None if input_nodata is None else float(input_nodata),
                "valid_pixel_count": int(np.count_nonzero(valid_mask)),
                "crs": raster_crs.to_string(),
                "tags": input_tags,
            },
            "aoi": {
                "vector_name": aoi_path.name,
                "source_crs": aoi_crs,
                "target_crs": raster_crs.to_string(),
                "buffer_km": aoi_buffer_km,
                "buffer_covered_by_input": True,
                "final_result_clipped": True,
            },
            "method_steps": [
                "validate single-band projected NTL radiance raster, nodata, CRS, and unit",
                "apply a 3x3 Gaussian filter with sigma=1",
                "generate closed contours from the base threshold at the configured interval",
                "discard open contours and contours below the minimum area",
                "identify seed contours as leaf contours containing local peaks",
                "build local contour trees by spatial containment and assign merge levels",
                "simplify same-level branches by retaining the outward contour",
                "classify level-1 leaves as basic centres and higher-level nodes as composite centres",
                "clip centre geometries to the AOI and validate vector/CSV/metadata outputs",
            ],
            "contours": contour_metrics,
            "tree": {
                "regular_node_count": int(len(regular_tree)),
                "simplified_node_count": int(len(simplified_tree)),
                "tree_count": int(len(roots)),
                "root_tree_ids": [tree_id_for_root[root.node_id] for root in roots],
            },
            "centres": {
                "total": int(len(rows)),
                "basic": int(sum(row["type"] == "basic" for row in rows)),
                "composite": int(sum(row["type"] == "composite" for row in rows)),
                "main_center_id": next((row["center_id"] for row in rows if row["main"] == 1), None),
            },
            "outputs": {
                "vector_name": reserved_vector.name,
                "vector_sha256": vector_hashes,
                "csv_name": reserved_csv.name,
                "csv_sha256": _sha256(reserved_csv),
                "metadata_name": reserved_metadata.name,
            },
        }
        with reserved_metadata.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(metadata, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        output_validation = _validate_written_outputs(
            reserved_vector,
            reserved_csv,
            reserved_metadata,
            expected_ids,
        )
        outputs = [
            OutputArtifact(path=str(reserved_vector), media_type="application/geopackage" if reserved_vector.suffix.lower() == ".gpkg" else "application/octet-stream", role="urban_centres"),
            OutputArtifact(path=str(reserved_csv), media_type="text/csv", role="attributes"),
            OutputArtifact(path=str(reserved_metadata), media_type="application/json", role="metadata"),
        ]
        if reserved_vector.suffix.lower() == ".shp":
            outputs.extend(
                OutputArtifact(path=str(path), media_type="application/octet-stream", role="vector_sidecar")
                for path in _vector_files(reserved_vector)[1:]
                if path.exists()
            )
        return ToolResult.succeeded(
            tool=TOOL_NAME,
            summary=f"Detected {len(rows)} urban centre node(s) in {len(roots)} localized contour tree(s).",
            outputs=outputs,
            metrics={
                "centre_count": int(len(rows)),
                "basic_count": int(sum(row["type"] == "basic" for row in rows)),
                "composite_count": int(sum(row["type"] == "composite" for row in rows)),
                "tree_count": int(len(roots)),
                "regular_node_count": int(len(regular_tree)),
                "simplified_node_count": int(len(simplified_tree)),
                "input_sha256": _sha256(raster_path),
                "output_validation": output_validation,
            },
        )
    except FileNotFoundError as exc:
        _cleanup_paths(
            [path for path in ([reserved_vector, reserved_csv, reserved_metadata] if reserved_vector else []) if path is not None for path in (_vector_files(path) if path == reserved_vector else [path])]
        )
        return _tool_failure("INPUT_NOT_FOUND", f"Input dataset was not found: {exc}")
    except Exception as exc:
        _cleanup_paths(
            [
                sidecar
                for path in (reserved_vector, reserved_csv, reserved_metadata)
                if path is not None
                for sidecar in (_vector_files(path) if path == reserved_vector else [path])
            ]
        )
        return _tool_failure(
            "PROCESSING_FAILED",
            f"Urban-centre extraction failed: {exc}",
            details={"raster_path": str(raster_path), "aoi_path": str(aoi_path)},
        )


__all__ = [
    "ALGORITHM_VERSION",
    "CHEN2017_SHANGHAI_2014_CONFIG",
    "ContourNode",
    "PAPER_DOI",
    "build_localized_contour_tree",
    "detect_urban_centres",
    "simplify_contour_tree",
    "smooth_ntl_3x3",
]
