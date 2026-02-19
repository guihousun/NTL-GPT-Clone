"""Quality checks for NTL-VLM benchmark artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

from .constants import DEFAULT_SPLIT_COUNTS
from .io_utils import read_jsonl, read_scene_manifest
from .schemas import SceneRecord, TaskSample

try:
    from shapely import wkt
except Exception:  # pragma: no cover
    wkt = None


def _to_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def _time_overlap_ratio(a_start: date, a_end: date, b_start: date, b_end: date) -> float:
    inter_start = max(a_start, b_start)
    inter_end = min(a_end, b_end)
    if inter_end < inter_start:
        return 0.0
    inter_days = (inter_end - inter_start).days + 1
    union_days = (max(a_end, b_end) - min(a_start, b_start)).days + 1
    return float(inter_days / max(union_days, 1))


def _geom_overlap_ratio(wkt_a: str, wkt_b: str) -> float:
    if wkt is None:
        return 0.0
    ga = wkt.loads(wkt_a)
    gb = wkt.loads(wkt_b)
    if ga.is_empty or gb.is_empty:
        return 0.0
    union_area = ga.union(gb).area
    if union_area == 0:
        return 0.0
    return float(ga.intersection(gb).area / union_area)


def validate_scene_dataframe(scene_df: pd.DataFrame) -> Dict[str, Any]:
    errors: List[Dict[str, Any]] = []
    valid_count = 0
    for _, row in scene_df.iterrows():
        payload = row.to_dict()
        try:
            SceneRecord(**payload)
            valid_count += 1
        except Exception as exc:
            errors.append({"scene_id": payload.get("scene_id", ""), "error": str(exc)})
    return {
        "total": int(len(scene_df)),
        "valid": int(valid_count),
        "invalid": int(len(errors)),
        "errors": errors,
    }


def validate_task_rows(task_rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(task_rows)
    errors: List[Dict[str, Any]] = []
    valid_count = 0
    for row in rows:
        try:
            TaskSample(**row)
            valid_count += 1
        except Exception as exc:
            errors.append({"sample_id": row.get("sample_id", ""), "error": str(exc)})
    return {
        "total": int(len(rows)),
        "valid": int(valid_count),
        "invalid": int(len(errors)),
        "errors": errors,
    }


def find_overlap_duplicates(scene_df: pd.DataFrame, overlap_threshold: float = 0.8) -> List[Dict[str, Any]]:
    if scene_df.empty:
        return []
    duplicates: List[Dict[str, Any]] = []

    for event_id, group in scene_df.groupby("event_id"):
        if len(group) < 2:
            continue
        records = group.to_dict(orient="records")
        for left, right in combinations(records, 2):
            temporal_overlap = _time_overlap_ratio(
                _to_date(left["pre_start"]),
                _to_date(left["post_end"]),
                _to_date(right["pre_start"]),
                _to_date(right["post_end"]),
            )
            spatial_overlap = _geom_overlap_ratio(left["aoi_wkt"], right["aoi_wkt"])
            if temporal_overlap > overlap_threshold and spatial_overlap > overlap_threshold:
                keep = left if float(left["quality_score"]) >= float(right["quality_score"]) else right
                remove = right if keep is left else left
                duplicates.append(
                    {
                        "event_id": event_id,
                        "keep_scene_id": keep["scene_id"],
                        "remove_scene_id": remove["scene_id"],
                        "temporal_overlap": temporal_overlap,
                        "spatial_overlap": spatial_overlap,
                    }
                )
    return duplicates


def detect_split_leakage(scene_df: pd.DataFrame, overlap_threshold: float = 0.8) -> List[Dict[str, Any]]:
    if scene_df.empty:
        return []
    leakages: List[Dict[str, Any]] = []

    test_splits = {"val", "public_test", "private_test"}

    for event_id, group in scene_df.groupby("event_id"):
        splits = set(group["split"].astype(str))
        if "train" in splits and len(splits.intersection(test_splits)) > 0:
            leakages.append(
                {
                    "type": "event_id_split_leak",
                    "event_id": event_id,
                    "splits": sorted(splits),
                }
            )

    records = scene_df.to_dict(orient="records")
    for left, right in combinations(records, 2):
        left_split = str(left["split"])
        right_split = str(right["split"])
        if left_split == right_split:
            continue
        if not {"train", "val", "public_test", "private_test"}.issuperset({left_split, right_split}):
            continue
        temporal_overlap = _time_overlap_ratio(
            _to_date(left["pre_start"]),
            _to_date(left["post_end"]),
            _to_date(right["pre_start"]),
            _to_date(right["post_end"]),
        )
        spatial_overlap = _geom_overlap_ratio(left["aoi_wkt"], right["aoi_wkt"])
        if temporal_overlap > overlap_threshold and spatial_overlap > overlap_threshold:
            leakages.append(
                {
                    "type": "aoi_time_overlap_leak",
                    "scene_id_left": left["scene_id"],
                    "scene_id_right": right["scene_id"],
                    "split_left": left_split,
                    "split_right": right_split,
                    "temporal_overlap": temporal_overlap,
                    "spatial_overlap": spatial_overlap,
                }
            )
    return leakages


def compute_cohens_kappa(labels_a: List[str], labels_b: List[str]) -> float:
    if len(labels_a) != len(labels_b):
        raise ValueError("labels_a and labels_b must have same length")
    if not labels_a:
        return 0.0
    label_set = sorted(set(labels_a).union(labels_b))
    if not label_set:
        return 0.0
    n = len(labels_a)
    observed = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    p_a = {label: labels_a.count(label) / n for label in label_set}
    p_b = {label: labels_b.count(label) / n for label in label_set}
    expected = sum(p_a[label] * p_b[label] for label in label_set)
    if expected == 1:
        return 1.0
    return float((observed - expected) / (1 - expected))


def load_task_rows(tasks_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for task_file in sorted(tasks_dir.glob("T*.jsonl")):
        rows.extend(read_jsonl(task_file))
    return rows


@dataclass
class QualityGateThresholds:
    min_auto_pass_rate: float = 0.98
    min_kappa: float = 0.80
    expected_split_counts: Dict[str, int] | None = None


def run_quality_gate(
    scene_df: pd.DataFrame,
    task_rows: List[Dict[str, Any]],
    annotation_df: pd.DataFrame | None = None,
    thresholds: QualityGateThresholds | None = None,
) -> Dict[str, Any]:
    thresholds = thresholds or QualityGateThresholds(expected_split_counts=DEFAULT_SPLIT_COUNTS.copy())
    scene_validation = validate_scene_dataframe(scene_df)
    task_validation = validate_task_rows(task_rows)
    duplicates = find_overlap_duplicates(scene_df)
    leakages = detect_split_leakage(scene_df)

    missing_quality = int(scene_df["cloud_free_ratio"].isna().sum()) if "cloud_free_ratio" in scene_df.columns else len(scene_df)
    split_counts = (
        scene_df["split"].value_counts().to_dict() if "split" in scene_df.columns else {}
    )
    split_ok = True
    if thresholds.expected_split_counts:
        for split_name, expected in thresholds.expected_split_counts.items():
            if int(split_counts.get(split_name, 0)) != int(expected):
                split_ok = False
                break

    total_rows = scene_validation["total"] + task_validation["total"]
    valid_rows = scene_validation["valid"] + task_validation["valid"]
    auto_pass_rate = float(valid_rows / total_rows) if total_rows > 0 else 0.0

    kappa = None
    if annotation_df is not None and not annotation_df.empty:
        if {"labeler_a", "labeler_b"}.issubset(annotation_df.columns):
            labels_a = annotation_df["labeler_a"].fillna("").astype(str).tolist()
            labels_b = annotation_df["labeler_b"].fillna("").astype(str).tolist()
            kappa = compute_cohens_kappa(labels_a, labels_b)

    quality_gate_pass = True
    quality_gate_pass &= auto_pass_rate >= thresholds.min_auto_pass_rate
    quality_gate_pass &= len(duplicates) == 0
    quality_gate_pass &= len(leakages) == 0
    quality_gate_pass &= split_ok
    if kappa is not None:
        quality_gate_pass &= kappa >= thresholds.min_kappa

    return {
        "scene_validation": scene_validation,
        "task_validation": task_validation,
        "duplicates": duplicates,
        "leakages": leakages,
        "missing_quality_band_rows": missing_quality,
        "split_counts": split_counts,
        "split_counts_ok": split_ok,
        "auto_pass_rate": auto_pass_rate,
        "kappa": kappa,
        "thresholds": {
            "min_auto_pass_rate": thresholds.min_auto_pass_rate,
            "min_kappa": thresholds.min_kappa,
            "expected_split_counts": thresholds.expected_split_counts,
        },
        "quality_gate_pass": bool(quality_gate_pass),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NTL-VLM benchmark quality gate checks.")
    parser.add_argument("--root", default="benchmarks/ntl_vlm_mvp")
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--tasks-dir", default=None)
    parser.add_argument("--annotation-file", default=None)
    parser.add_argument("--out-json", default=None)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    root = Path(args.root)
    manifest_path = Path(args.manifest) if args.manifest else root / "manifests" / "scene_manifest.parquet"
    tasks_dir = Path(args.tasks_dir) if args.tasks_dir else root / "tasks"
    annotation_file = Path(args.annotation_file) if args.annotation_file else root / "annotations" / "double_label_template.csv"
    out_json = Path(args.out_json) if args.out_json else root / "reports" / "qc_report.json"

    scene_df = read_scene_manifest(manifest_path)
    task_rows = load_task_rows(tasks_dir)
    annotation_df = pd.read_csv(annotation_file) if annotation_file.exists() else None

    report = run_quality_gate(scene_df=scene_df, task_rows=task_rows, annotation_df=annotation_df)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[QC] scene rows: {report['scene_validation']['total']}")
    print(f"[QC] task rows: {report['task_validation']['total']}")
    print(f"[QC] auto pass rate: {report['auto_pass_rate']:.4f}")
    print(f"[QC] quality gate pass: {report['quality_gate_pass']}")
    print(f"[QC] report written to: {out_json}")


if __name__ == "__main__":
    main()
