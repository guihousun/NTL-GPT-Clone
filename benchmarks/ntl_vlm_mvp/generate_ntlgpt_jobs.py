"""Generate NTL-GPT agent job manifests for benchmark production steps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import pandas as pd

from .io_utils import ensure_dir, read_scene_manifest, write_jsonl


def build_event_discovery_jobs(event_df: pd.DataFrame) -> List[Dict]:
    jobs: List[Dict] = []
    for _, row in event_df.iterrows():
        event_id = str(row["event_id"])
        jobs.append(
            {
                "job_id": f"event_discovery_{event_id}",
                "agent": "Data_Searcher",
                "stage": 1,
                "tool_chain": ["Tavily_search", "geocode_tool", "geodata_quick_check_tool"],
                "input": {
                    "event_id": event_id,
                    "hazard_type": str(row["hazard_type"]),
                    "event_day": str(row["event_day"]),
                    "aoi_wkt": str(row["aoi_wkt"]),
                },
                "prompt": (
                    "Retrieve and verify event metadata for benchmark candidate generation. "
                    "Return structured AOI validation status, coordinate source, and references."
                ),
                "expected_outputs": ["event_metadata.json", "aoi_validation.json"],
            }
        )
    return jobs


def build_router_blueprint_jobs(scene_df: pd.DataFrame) -> List[Dict]:
    jobs: List[Dict] = []
    for _, row in scene_df.iterrows():
        scene_id = str(row["scene_id"])
        jobs.append(
            {
                "job_id": f"gee_blueprint_{scene_id}",
                "agent": "Data_Searcher",
                "stage": 2,
                "tool_chain": ["GEE_dataset_router_tool", "GEE_script_blueprint_tool"],
                "input": {
                    "scene_id": scene_id,
                    "pre_start": str(row["pre_start"]),
                    "pre_end": str(row["pre_end"]),
                    "post_start": str(row["post_start"]),
                    "post_end": str(row["post_end"]),
                    "aoi_wkt": str(row["aoi_wkt"]),
                },
                "prompt": (
                    "Route dataset and emit GEE script blueprint for NTL pre/post patch extraction. "
                    "Prefer VNP46A2 and fallback to monthly VIIRS only when needed."
                ),
                "expected_outputs": ["gee_router_decision.json", "gee_blueprint.py"],
            }
        )
    return jobs


def build_extraction_jobs(scene_df: pd.DataFrame) -> List[Dict]:
    jobs: List[Dict] = []
    for _, row in scene_df.iterrows():
        scene_id = str(row["scene_id"])
        jobs.append(
            {
                "job_id": f"patch_extract_{scene_id}",
                "agent": "Code_Assistant",
                "stage": 3,
                "tool_chain": [
                    "GeoCode_Knowledge_Recipes_tool",
                    "GeoCode_COT_Validation_tool",
                    "execute_geospatial_script_tool",
                ],
                "input": {
                    "scene_id": scene_id,
                    "thread_workspace": f"user_data/<thread_id>/outputs/{scene_id}",
                    "dataset": "NASA/VIIRS/002/VNP46A2",
                    "fallback_dataset": "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG",
                },
                "prompt": (
                    "Execute Geo-CodeCoT workflow to generate pre/post 256x256 NTL patches and scene statistics "
                    "under outputs/, without modifying repository source files."
                ),
                "expected_outputs": [
                    "pre_patch.tif",
                    "post_patch.tif",
                    "scene_stats.json",
                    "qc_thumbnail.png",
                ],
            }
        )
    return jobs


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate staged NTL-GPT jobs for benchmark production.")
    parser.add_argument("--root", default="benchmarks/ntl_vlm_mvp")
    parser.add_argument("--event-registry", default=None)
    parser.add_argument("--scene-manifest", default=None)
    parser.add_argument("--limit-scenes", type=int, default=200)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    root = Path(args.root)
    jobs_dir = ensure_dir(root / "jobs")

    event_registry = Path(args.event_registry) if args.event_registry else root / "manifests" / "event_registry_clean.csv"
    scene_manifest = Path(args.scene_manifest) if args.scene_manifest else root / "manifests" / "scene_manifest.parquet"

    if not event_registry.exists():
        raise FileNotFoundError(f"event registry not found: {event_registry}")
    if not scene_manifest.exists() and not scene_manifest.with_suffix(".csv").exists():
        raise FileNotFoundError(f"scene manifest not found: {scene_manifest}")

    event_df = pd.read_csv(event_registry)
    scene_df = read_scene_manifest(scene_manifest)
    scene_df = scene_df.head(int(args.limit_scenes)).copy()

    stage1 = build_event_discovery_jobs(event_df)
    stage2 = build_router_blueprint_jobs(scene_df)
    stage3 = build_extraction_jobs(scene_df)

    write_jsonl(jobs_dir / "stage1_event_discovery.jsonl", stage1)
    write_jsonl(jobs_dir / "stage2_gee_router_blueprint.jsonl", stage2)
    write_jsonl(jobs_dir / "stage3_patch_extraction.jsonl", stage3)

    summary = {
        "stage1_jobs": len(stage1),
        "stage2_jobs": len(stage2),
        "stage3_jobs": len(stage3),
        "jobs_dir": str(jobs_dir),
    }
    (jobs_dir / "job_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
