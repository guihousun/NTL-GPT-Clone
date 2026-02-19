from __future__ import annotations

import pandas as pd

from benchmarks.ntl_vlm_mvp.qc import (
    compute_cohens_kappa,
    detect_split_leakage,
    run_quality_gate,
    validate_scene_dataframe,
)


def _base_scene(scene_id: str, aoi_wkt: str, split: str, cloud_free_ratio: float | None) -> dict:
    return {
        "scene_id": scene_id,
        "event_id": "evt_001",
        "hazard_type": "flood",
        "aoi_wkt": aoi_wkt,
        "pre_start": "2024-01-01",
        "pre_end": "2024-01-10",
        "post_start": "2024-01-10",
        "post_end": "2024-01-25",
        "quality_score": 0.9,
        "split": split,
        "license_tag": "gee-public-catalog",
        "cloud_free_ratio": cloud_free_ratio,
    }


def test_qc_handles_empty_aoi_invalid_geometry_and_dateline_polygon():
    dateline_wkt = "POLYGON((179 10, -179 10, -179 12, 179 12, 179 10))"
    invalid_wkt = "POLYGON((0 0, 1 1, 1 0))"

    df = pd.DataFrame(
        [
            _base_scene("scene_dateline", dateline_wkt, "train", 0.95),
            _base_scene("scene_empty", "", "val", 0.80),
            _base_scene("scene_invalid", invalid_wkt, "public_test", None),
        ]
    )

    validation = validate_scene_dataframe(df)
    assert validation["valid"] == 1
    assert validation["invalid"] == 2
    invalid_ids = {row["scene_id"] for row in validation["errors"]}
    assert "scene_dateline" not in invalid_ids
    assert "scene_empty" in invalid_ids
    assert "scene_invalid" in invalid_ids

    report = run_quality_gate(scene_df=df, task_rows=[], annotation_df=None)
    assert report["missing_quality_band_rows"] == 1


def test_qc_detects_train_test_leakage():
    aoi = "POLYGON((10 10, 11 10, 11 11, 10 11, 10 10))"
    train_row = _base_scene("scene_train", aoi, "train", 0.9)
    test_row = _base_scene("scene_test", aoi, "public_test", 0.9)
    test_row["event_id"] = train_row["event_id"]

    leakages = detect_split_leakage(pd.DataFrame([train_row, test_row]))
    assert len(leakages) >= 1
    leak_types = {item["type"] for item in leakages}
    assert "event_id_split_leak" in leak_types or "aoi_time_overlap_leak" in leak_types


def test_cohens_kappa_basic():
    labels_a = ["A", "A", "B", "C", "C"]
    labels_b = ["A", "B", "B", "C", "C"]
    score = compute_cohens_kappa(labels_a, labels_b)
    assert -1.0 <= score <= 1.0
    perfect = compute_cohens_kappa(labels_a, labels_a)
    assert perfect == 1.0

