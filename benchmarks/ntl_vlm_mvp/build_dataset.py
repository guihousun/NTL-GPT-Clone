"""Build scene manifest for NTL-VLM benchmark MVP."""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import timedelta
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from .constants import (
    ALLOWED_LICENSE_TAGS,
    DEFAULT_POST_WINDOW_DAYS,
    DEFAULT_PRE_WINDOW_DAYS,
    DEFAULT_SPLIT_COUNTS,
)
from .io_utils import ensure_dir, write_dataframe_csv, write_scene_manifest
from .qc import find_overlap_duplicates


REQUIRED_EVENT_COLUMNS = {
    "event_id",
    "event_day",
    "hazard_type",
    "aoi_wkt",
    "license_tag",
}


_WKT_FLOAT_RE = re.compile(r"-?\d+(?:\.\d+)?")


def normalize_event_registry(event_df: pd.DataFrame, strict_license: bool = True) -> pd.DataFrame:
    missing = REQUIRED_EVENT_COLUMNS - set(event_df.columns)
    if missing:
        raise ValueError(f"event registry missing required columns: {sorted(missing)}")

    df = event_df.copy()
    df["event_id"] = df["event_id"].astype(str).str.strip()
    df["hazard_type"] = df["hazard_type"].astype(str).str.strip().str.lower()
    df["aoi_wkt"] = df["aoi_wkt"].astype(str).str.strip()
    df["license_tag"] = df["license_tag"].astype(str).str.strip().str.lower()
    df["event_day"] = pd.to_datetime(df["event_day"]).dt.date

    df = df[df["event_id"] != ""].drop_duplicates(subset=["event_id"]).reset_index(drop=True)
    if strict_license:
        before = len(df)
        df = df[df["license_tag"].isin(ALLOWED_LICENSE_TAGS)].copy()
        after = len(df)
        if after == 0:
            raise ValueError(
                "all events were filtered out by strict open-license policy. "
                f"allowed tags: {sorted(ALLOWED_LICENSE_TAGS)}"
            )
        if after < before:
            print(f"[BUILD] filtered out {before - after} events due to license_tag policy")
    return df.reset_index(drop=True)


def _distribute_total(total: int, bins: int) -> List[int]:
    if bins <= 0:
        raise ValueError("bins must be positive")
    base = total // bins
    remainder = total % bins
    return [base + (1 if i < remainder else 0) for i in range(bins)]


def _assign_events_to_splits(event_count: int, split_counts: Dict[str, int], seed: int) -> Dict[str, int]:
    """Allocate number of events for each split with at least one per split."""

    split_names = list(split_counts.keys())
    if event_count < len(split_names):
        raise ValueError(
            f"need at least {len(split_names)} events to satisfy split isolation; got {event_count}"
        )

    remaining = event_count - len(split_names)
    total_scenes = sum(split_counts.values())
    weights = {k: split_counts[k] / total_scenes for k in split_names}

    event_alloc = {k: 1 for k in split_names}
    raw_extra = {k: weights[k] * remaining for k in split_names}
    floored = {k: int(np.floor(raw_extra[k])) for k in split_names}
    for split in split_names:
        event_alloc[split] += floored[split]

    assigned = sum(event_alloc.values())
    remainder = event_count - assigned
    if remainder > 0:
        frac = sorted(
            ((raw_extra[k] - floored[k], k) for k in split_names),
            key=lambda item: item[0],
            reverse=True,
        )
        for idx in range(remainder):
            event_alloc[frac[idx % len(frac)][1]] += 1

    # deterministic tie-break shuffling for split order by seed
    rng = np.random.default_rng(seed)
    shuffled_names = split_names.copy()
    rng.shuffle(shuffled_names)
    event_alloc = {name: event_alloc[name] for name in shuffled_names}
    return event_alloc


def _event_group_key(event: Dict) -> str:
    """Build coarse spatiotemporal key to keep near-duplicate events in same split."""

    try:
        lon_min, lon_max, lat_min, lat_max = _extract_bbox_from_wkt(str(event.get("aoi_wkt", "")))
        lon_c = round((lon_min + lon_max) / 2.0, 1)
        lat_c = round((lat_min + lat_max) / 2.0, 1)
    except Exception:
        lon_c = 0.0
        lat_c = 0.0
    try:
        month = pd.to_datetime(event.get("event_day")).strftime("%Y-%m")
    except Exception:
        month = "unknown"
    hazard = str(event.get("hazard_type", "other")).strip().lower() or "other"
    return f"{hazard}|{lat_c}|{lon_c}|{month}"


def _bbox_iou_from_wkts(wkt_a: str, wkt_b: str) -> float:
    try:
        a_lon_min, a_lon_max, a_lat_min, a_lat_max = _extract_bbox_from_wkt(wkt_a)
        b_lon_min, b_lon_max, b_lat_min, b_lat_max = _extract_bbox_from_wkt(wkt_b)
    except Exception:
        return 0.0

    inter_lon_min = max(a_lon_min, b_lon_min)
    inter_lon_max = min(a_lon_max, b_lon_max)
    inter_lat_min = max(a_lat_min, b_lat_min)
    inter_lat_max = min(a_lat_max, b_lat_max)
    if inter_lon_max <= inter_lon_min or inter_lat_max <= inter_lat_min:
        return 0.0
    inter_area = (inter_lon_max - inter_lon_min) * (inter_lat_max - inter_lat_min)
    area_a = (a_lon_max - a_lon_min) * (a_lat_max - a_lat_min)
    area_b = (b_lon_max - b_lon_min) * (b_lat_max - b_lat_min)
    union = area_a + area_b - inter_area
    if union <= 0:
        return 0.0
    return float(inter_area / union)


def _event_temporal_overlap(event_a: Dict, event_b: Dict) -> float:
    try:
        da = pd.to_datetime(event_a.get("event_day")).date()
        db = pd.to_datetime(event_b.get("event_day")).date()
    except Exception:
        return 0.0
    a_start, a_end = da - timedelta(days=30), da + timedelta(days=21)
    b_start, b_end = db - timedelta(days=30), db + timedelta(days=21)
    inter_start = max(a_start, b_start)
    inter_end = min(a_end, b_end)
    if inter_end < inter_start:
        return 0.0
    inter = (inter_end - inter_start).days + 1
    union = (max(a_end, b_end) - min(a_start, b_start)).days + 1
    return float(inter / max(union, 1))


def _cluster_events_by_overlap(events: List[Dict], overlap_threshold: float = 0.8) -> List[List[Dict]]:
    if not events:
        return []
    n = len(events)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            spatial = _bbox_iou_from_wkts(str(events[i].get("aoi_wkt", "")), str(events[j].get("aoi_wkt", "")))
            if spatial > overlap_threshold:
                union(i, j)

    clusters: Dict[int, List[Dict]] = {}
    for idx, event in enumerate(events):
        clusters.setdefault(find(idx), []).append(event)
    return sorted(clusters.values(), key=len, reverse=True)


def _assign_event_groups_to_splits(
    events: List[Dict],
    target_event_counts: Dict[str, int],
) -> Dict[str, str]:
    """Assign grouped events to splits so near-duplicate events stay together."""

    split_names = list(target_event_counts.keys())
    assigned_counts = {name: 0 for name in split_names}
    event_splits: Dict[str, str] = {}

    grouped_events = _cluster_events_by_overlap(events, overlap_threshold=0.6)
    if not grouped_events:
        grouped_events = [[event] for event in events]
    # fallback coarse grouping when no overlap-driven grouping was possible
    if len(grouped_events) == len(events):
        coarse: Dict[str, List[Dict]] = {}
        for event in events:
            coarse.setdefault(_event_group_key(event), []).append(event)
        grouped_events = sorted(coarse.values(), key=len, reverse=True)

    sorted_groups = grouped_events
    for group_events in sorted_groups:
        # prioritize split with largest remaining event capacity
        split_name = max(
            split_names,
            key=lambda name: (target_event_counts[name] - assigned_counts[name], -assigned_counts[name]),
        )
        for event in group_events:
            event_splits[str(event["event_id"])] = split_name
        assigned_counts[split_name] += len(group_events)

    return event_splits


def _hazard_drop_factor(hazard_type: str) -> float:
    hazard = hazard_type.lower()
    if "conflict" in hazard or "war" in hazard:
        return 0.58
    if "flood" in hazard:
        return 0.42
    if "earthquake" in hazard:
        return 0.36
    if "wildfire" in hazard:
        return 0.31
    if "hurricane" in hazard or "typhoon" in hazard:
        return 0.44
    return 0.30


def _extract_bbox_from_wkt(aoi_wkt: str) -> tuple[float, float, float, float]:
    values = [float(x) for x in _WKT_FLOAT_RE.findall(aoi_wkt)]
    if len(values) < 8:
        raise ValueError("aoi_wkt has insufficient coordinates")
    lons = values[0::2]
    lats = values[1::2]
    lon_min = min(lons)
    lon_max = max(lons)
    lat_min = min(lats)
    lat_max = max(lats)
    if lon_max <= lon_min or lat_max <= lat_min:
        raise ValueError("invalid aoi_wkt bbox bounds")
    return lon_min, lon_max, lat_min, lat_max


def _bbox_to_wkt(lon_min: float, lon_max: float, lat_min: float, lat_max: float) -> str:
    return (
        f"POLYGON(({lon_min:.6f} {lat_min:.6f}, {lon_max:.6f} {lat_min:.6f}, "
        f"{lon_max:.6f} {lat_max:.6f}, {lon_min:.6f} {lat_max:.6f}, {lon_min:.6f} {lat_min:.6f}))"
    )


def _scene_aoi_from_event(aoi_wkt: str, local_idx: int, total_for_event: int) -> str:
    """Create sub-grid AOI to avoid near-duplicate overlap within one event."""

    lon_min, lon_max, lat_min, lat_max = _extract_bbox_from_wkt(aoi_wkt)
    grid_n = max(1, int(math.ceil(math.sqrt(max(total_for_event, 1)))))
    col = local_idx % grid_n
    row = (local_idx // grid_n) % grid_n

    cell_w = (lon_max - lon_min) / grid_n
    cell_h = (lat_max - lat_min) / grid_n

    sub_lon_min = lon_min + col * cell_w
    sub_lon_max = sub_lon_min + cell_w
    sub_lat_min = lat_min + row * cell_h
    sub_lat_max = sub_lat_min + cell_h

    # small deterministic margin to keep polygons valid and slightly varied
    margin_w = cell_w * 0.03
    margin_h = cell_h * 0.03
    sub_lon_min += margin_w
    sub_lon_max -= margin_w
    sub_lat_min += margin_h
    sub_lat_max -= margin_h

    if sub_lon_max <= sub_lon_min or sub_lat_max <= sub_lat_min:
        return aoi_wkt
    return _bbox_to_wkt(sub_lon_min, sub_lon_max, sub_lat_min, sub_lat_max)


def build_scene_manifest_from_events(
    event_df: pd.DataFrame,
    target_scenes: int,
    split_counts: Dict[str, int],
    seed: int = 42,
) -> pd.DataFrame:
    if sum(split_counts.values()) != target_scenes:
        raise ValueError("sum(split_counts.values()) must equal target_scenes")

    rng = np.random.default_rng(seed)
    events = event_df.to_dict(orient="records")
    rng.shuffle(events)
    event_alloc = _assign_events_to_splits(event_count=len(events), split_counts=split_counts, seed=seed)
    event_splits = _assign_event_groups_to_splits(events=events, target_event_counts=event_alloc)

    # Assign per-event scene counts within each split to satisfy fixed totals.
    event_scene_counts: Dict[str, int] = {}
    by_split: Dict[str, List[Dict]] = {split: [] for split in split_counts}
    for event in events:
        by_split[event_splits[str(event["event_id"])]].append(event)
    for split_name, split_events in by_split.items():
        allocations = _distribute_total(total=int(split_counts[split_name]), bins=len(split_events))
        for event, count in zip(split_events, allocations):
            event_scene_counts[str(event["event_id"])] = int(count)

    rows: List[Dict] = []
    pre_left, pre_right = DEFAULT_PRE_WINDOW_DAYS
    post_left, post_right = DEFAULT_POST_WINDOW_DAYS

    for event in events:
        event_day = pd.to_datetime(event["event_day"]).date()
        severity_hint = float(event.get("severity_hint", rng.uniform(0.35, 0.95)))
        hazard_factor = _hazard_drop_factor(str(event["hazard_type"]))
        region_name = str(event.get("region_name", "")).strip()
        source = str(event.get("source", "event_registry")).strip() or "event_registry"
        split_name = event_splits[str(event["event_id"])]
        total_for_event = event_scene_counts[str(event["event_id"])]
        for local_idx in range(total_for_event):
            jitter = int(rng.integers(-2, 3))
            pre_start = event_day - timedelta(days=pre_left + jitter)
            pre_end = event_day - timedelta(days=pre_right + jitter)
            post_start = event_day + timedelta(days=post_left + jitter)
            post_end = event_day + timedelta(days=post_right + jitter)
            scene_aoi_wkt = _scene_aoi_from_event(
                aoi_wkt=str(event["aoi_wkt"]),
                local_idx=local_idx,
                total_for_event=total_for_event,
            )

            quality = float(event.get("quality_score", rng.uniform(0.70, 0.99)))
            quality = max(0.0, min(1.0, quality))
            cloud_free_ratio = float(event.get("cloud_free_ratio", rng.uniform(0.60, 0.99)))
            cloud_free_ratio = max(0.0, min(1.0, cloud_free_ratio))

            mean_pre = float(rng.uniform(4.0, 35.0))
            impact_drop = float(np.clip(severity_hint * hazard_factor * rng.uniform(0.55, 1.15), 0.02, 0.95))
            mean_post = float(max(0.05, mean_pre * (1.0 - impact_drop)))
            recovery_index = float(np.clip(rng.normal(loc=0.45, scale=0.22), 0.0, 1.0))
            blackout_clusters = int(max(0, round(impact_drop * 18 + rng.normal(0.0, 1.8))))
            sector = ["A", "B", "C", "D"][int(rng.integers(0, 4))]

            rows.append(
                {
                    "scene_id": f"{event['event_id']}_{local_idx:04d}",
                    "event_id": event["event_id"],
                    "hazard_type": event["hazard_type"],
                    "aoi_wkt": scene_aoi_wkt,
                    "pre_start": pre_start,
                    "pre_end": pre_end,
                    "post_start": post_start,
                    "post_end": post_end,
                    "quality_score": quality,
                    "license_tag": event["license_tag"],
                    "source": source,
                    "region_name": region_name,
                    "mean_pre": round(mean_pre, 4),
                    "mean_post": round(mean_post, 4),
                    "mean_delta": round(mean_post - mean_pre, 4),
                    "drop_ratio": round(impact_drop, 4),
                    "recovery_index": round(recovery_index, 4),
                    "cloud_free_ratio": round(cloud_free_ratio, 4),
                    "blackout_cluster_count": blackout_clusters,
                    "affected_sector": sector,
                    "pre_dataset": "NASA/VIIRS/002/VNP46A2",
                    "post_dataset": "NASA/VIIRS/002/VNP46A2",
                    "fallback_dataset": "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG",
                    "split": split_name,
                }
            )
    scene_df = pd.DataFrame(rows)
    return scene_df


def assign_splits(scene_df: pd.DataFrame, split_counts: Dict[str, int], seed: int = 42) -> pd.DataFrame:
    total_expected = int(sum(split_counts.values()))
    if len(scene_df) < total_expected:
        raise ValueError(f"scene_df has {len(scene_df)} rows, expected at least {total_expected}")
    if len(scene_df) > total_expected:
        scene_df = scene_df.head(total_expected).copy()

    rng = np.random.default_rng(seed)
    shuffled_idx = rng.permutation(len(scene_df))
    scene_df = scene_df.iloc[shuffled_idx].reset_index(drop=True)

    cursor = 0
    for split_name, count in split_counts.items():
        count = int(count)
        if count < 0:
            raise ValueError(f"split count for {split_name} must be non-negative")
        end = cursor + count
        scene_df.loc[cursor:end - 1, "split"] = split_name
        cursor = end
    return scene_df


def remove_overlap_duplicates(scene_df: pd.DataFrame) -> pd.DataFrame:
    dedup_df = scene_df.copy()
    duplicates = find_overlap_duplicates(dedup_df, overlap_threshold=0.8)
    if not duplicates:
        return dedup_df

    remove_ids = {item["remove_scene_id"] for item in duplicates}
    dedup_df = dedup_df[~dedup_df["scene_id"].isin(remove_ids)].copy()
    return dedup_df.reset_index(drop=True)


def _parse_split_counts(args: argparse.Namespace) -> Dict[str, int]:
    return {
        "train": int(args.train_count),
        "val": int(args.val_count),
        "public_test": int(args.public_test_count),
        "private_test": int(args.private_test_count),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build NTL-VLM MVP scene manifest.")
    parser.add_argument("--root", default="benchmarks/ntl_vlm_mvp")
    parser.add_argument("--event-registry", default=None)
    parser.add_argument("--target-scenes", type=int, default=3600)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--strict-license", dest="strict_license", action="store_true")
    parser.add_argument("--no-strict-license", dest="strict_license", action="store_false")
    parser.set_defaults(strict_license=True)
    parser.add_argument("--train-count", type=int, default=DEFAULT_SPLIT_COUNTS["train"])
    parser.add_argument("--val-count", type=int, default=DEFAULT_SPLIT_COUNTS["val"])
    parser.add_argument("--public-test-count", type=int, default=DEFAULT_SPLIT_COUNTS["public_test"])
    parser.add_argument("--private-test-count", type=int, default=DEFAULT_SPLIT_COUNTS["private_test"])
    parser.add_argument("--no-dedup", action="store_true")
    return parser


def _resolve_event_registry_path(manifests_dir: Path, cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value)
    preferred = manifests_dir / "event_registry_clean.csv"
    if preferred.exists():
        return preferred
    return manifests_dir / "event_registry_template.csv"


def main() -> None:
    args = _build_arg_parser().parse_args()
    root = Path(args.root)
    manifests_dir = ensure_dir(root / "manifests")
    event_registry_path = _resolve_event_registry_path(manifests_dir=manifests_dir, cli_value=args.event_registry)
    split_counts = _parse_split_counts(args)

    target = int(args.target_scenes)
    if target != sum(split_counts.values()):
        raise ValueError("--target-scenes must match the sum of split counts")

    event_df = pd.read_csv(event_registry_path)
    event_df = normalize_event_registry(event_df=event_df, strict_license=bool(args.strict_license))
    scene_df = build_scene_manifest_from_events(
        event_df=event_df,
        target_scenes=target,
        split_counts=split_counts,
        seed=int(args.seed),
    )

    if not args.no_dedup:
        dedup_df = remove_overlap_duplicates(scene_df)
        if len(dedup_df) != len(scene_df):
            print(f"[BUILD] removed {len(scene_df) - len(dedup_df)} overlap duplicates")
            if len(dedup_df) < target:
                raise RuntimeError(
                    "deduplication reduced scene count below target; increase events or disable --strict-license"
                )
            scene_df = dedup_df.head(target).copy()
            scene_df = assign_splits(scene_df=scene_df, split_counts=split_counts, seed=int(args.seed))

    scene_manifest_path = manifests_dir / "scene_manifest.parquet"
    write_scene_manifest(scene_df, scene_manifest_path)
    write_dataframe_csv(scene_df, manifests_dir / "scene_manifest.csv")
    write_dataframe_csv(event_df, manifests_dir / "event_registry_clean.csv")

    summary = {
        "target_scenes": target,
        "event_count": int(len(event_df)),
        "split_counts": {k: int(v) for k, v in scene_df["split"].value_counts().to_dict().items()},
        "quality_mean": float(scene_df["quality_score"].mean()),
        "drop_ratio_mean": float(scene_df["drop_ratio"].mean()),
        "scene_manifest_path": str(scene_manifest_path),
        "seed": int(args.seed),
    }
    summary_path = manifests_dir / "build_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[BUILD] scene manifest written:", scene_manifest_path)
    print("[BUILD] summary written:", summary_path)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
