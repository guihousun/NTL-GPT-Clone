from __future__ import annotations

import pandas as pd

from benchmarks.ntl_vlm_mvp.build_dataset import build_scene_manifest_from_events, normalize_event_registry


def _event_registry_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_id": "evt_a",
                "event_day": "2024-01-10",
                "hazard_type": "flood",
                "aoi_wkt": "POLYGON((10 10, 11 10, 11 11, 10 11, 10 10))",
                "license_tag": "gee-public-catalog",
            },
            {
                "event_id": "evt_b",
                "event_day": "2024-02-20",
                "hazard_type": "conflict",
                "aoi_wkt": "POLYGON((20 20, 21 20, 21 21, 20 21, 20 20))",
                "license_tag": "cc-by-4.0",
            },
            {
                "event_id": "evt_c",
                "event_day": "2024-03-10",
                "hazard_type": "earthquake",
                "aoi_wkt": "POLYGON((30 30, 31 30, 31 31, 30 31, 30 30))",
                "license_tag": "cc-by-4.0",
            },
            {
                "event_id": "evt_d",
                "event_day": "2024-04-10",
                "hazard_type": "wildfire",
                "aoi_wkt": "POLYGON((40 40, 41 40, 41 41, 40 41, 40 40))",
                "license_tag": "cc-by-4.0",
            },
        ]
    )


def test_build_manifest_is_reproducible_with_same_seed():
    events = normalize_event_registry(_event_registry_df(), strict_license=True)
    split_counts = {"train": 8, "val": 2, "public_test": 2, "private_test": 2}

    first = build_scene_manifest_from_events(events, target_scenes=14, split_counts=split_counts, seed=7)
    second = build_scene_manifest_from_events(events, target_scenes=14, split_counts=split_counts, seed=7)

    cols = ["scene_id", "event_id", "split", "pre_start", "post_end", "drop_ratio"]
    assert first[cols].to_dict("records") == second[cols].to_dict("records")


def test_build_manifest_changes_when_seed_changes():
    events = normalize_event_registry(_event_registry_df(), strict_license=True)
    split_counts = {"train": 8, "val": 2, "public_test": 2, "private_test": 2}

    first = build_scene_manifest_from_events(events, target_scenes=14, split_counts=split_counts, seed=7)
    second = build_scene_manifest_from_events(events, target_scenes=14, split_counts=split_counts, seed=8)
    assert first["scene_id"].tolist() != second["scene_id"].tolist()
