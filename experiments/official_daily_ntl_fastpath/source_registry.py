from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    short_name: str
    processing_mode: str
    variable_candidates: tuple[str, ...]
    night_only: bool = False


_SOURCE_REGISTRY: dict[str, SourceSpec] = {
    "VJ146A1_NRT": SourceSpec(
        short_name="VJ146A1_NRT",
        processing_mode="gridded_tile_clip",
        variable_candidates=(
            "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/DNB_At_Sensor_Radiance_500m",
            "DNB_At_Sensor_Radiance_500m",
            "DNB_At_Sensor_Radiance",
        ),
        night_only=False,
    ),
    "VJ146A1G_NRT": SourceSpec(
        short_name="VJ146A1G_NRT",
        processing_mode="feasibility_only",
        variable_candidates=(),
        night_only=False,
    ),
    "VJ146A2": SourceSpec(
        short_name="VJ146A2",
        processing_mode="gridded_tile_clip",
        variable_candidates=(
            "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/Gap_Filled_DNB_BRDF-Corrected_NTL",
            "Gap_Filled_DNB_BRDF-Corrected_NTL",
            "Gap_Filled_DNB_BRDF_Corrected_NTL",
            "DNB_BRDF-Corrected_NTL",
        ),
        night_only=False,
    ),
    "VJ146A1": SourceSpec(
        short_name="VJ146A1",
        processing_mode="gridded_tile_clip",
        variable_candidates=(
            "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/DNB_At_Sensor_Radiance_500m",
            "DNB_At_Sensor_Radiance_500m",
            "DNB_At_Sensor_Radiance",
        ),
        night_only=False,
    ),
    "VJ102DNB": SourceSpec(
        short_name="VJ102DNB",
        processing_mode="feasibility_only",
        variable_candidates=(),
        night_only=True,
    ),
    "VJ102DNB_NRT": SourceSpec(
        short_name="VJ102DNB_NRT",
        processing_mode="feasibility_only",
        variable_candidates=(),
        night_only=True,
    ),
}


def get_default_sources() -> list[str]:
    return ["VJ146A2", "VJ146A1", "VJ102DNB"]


def get_nrt_priority_sources() -> list[str]:
    return ["VJ146A1_NRT", "VJ146A1", "VJ146A2", "VJ102DNB_NRT", "VJ102DNB"]


def get_source_spec(source: str) -> SourceSpec:
    key = (source or "").strip().upper()
    if key not in _SOURCE_REGISTRY:
        raise ValueError(f"Unsupported source: {source}")
    return _SOURCE_REGISTRY[key]


def parse_sources_arg(raw: str | None) -> list[str]:
    if not raw:
        return get_default_sources()
    key_raw = raw.strip().lower()
    if key_raw in {"nrt_priority", "nrt-priority"}:
        return get_nrt_priority_sources()
    out: list[str] = []
    for part in raw.split(","):
        key = part.strip().upper()
        if not key:
            continue
        _ = get_source_spec(key)
        if key not in out:
            out.append(key)
    return out or get_default_sources()
