"""One-command pipeline for NTL-VLM benchmark MVP."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from .build_dataset import (
    build_scene_manifest_from_events,
    normalize_event_registry,
    remove_overlap_duplicates,
)
from .constants import DEFAULT_SPLIT_COUNTS, TASK_SPECS
from .generate_tasks import scene_to_task_samples
from .io_utils import ensure_dir, read_jsonl, write_jsonl, write_scene_manifest
from .qc import QualityGateThresholds, run_quality_gate


def _resolve_event_registry_path(manifests_dir: Path, cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value)
    preferred = manifests_dir / "event_registry_clean.csv"
    if preferred.exists():
        return preferred
    return manifests_dir / "event_registry_template.csv"


def _build_tasks(root: Path, scene_df: pd.DataFrame) -> Dict[str, int]:
    task_rows: List[Dict] = []
    for _, row in scene_df.iterrows():
        task_rows.extend(scene_to_task_samples(row.to_dict(), source_tag="weak_rule+ntl_gpt_draft"))

    tasks_dir = ensure_dir(root / "tasks")
    counts: Dict[str, int] = {}
    for task_id in TASK_SPECS:
        rows = [r for r in task_rows if r["task_id"] == task_id]
        write_jsonl(tasks_dir / f"{task_id}.jsonl", rows)
        counts[task_id] = len(rows)
    write_jsonl(tasks_dir / "all_tasks.jsonl", task_rows)

    annotation_rows = []
    for row in task_rows:
        split = row.get("metadata", {}).get("split", "")
        if row["task_id"] in {"T1", "T2", "T3", "T4", "T5", "T6"} and split in {"val", "public_test", "private_test"}:
            annotation_rows.append(
                {
                    "sample_id": row["sample_id"],
                    "task_id": row["task_id"],
                    "split": split,
                    "labeler_a": "",
                    "labeler_b": "",
                    "adjudicated_label": "",
                }
            )
    annotations_dir = ensure_dir(root / "annotations")
    pd.DataFrame(annotation_rows).to_csv(
        annotations_dir / "double_label_template.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pd.DataFrame(
        [
            {
                "task_id": task_id,
                "task_name": TASK_SPECS[task_id]["name"],
                "task_type": TASK_SPECS[task_id]["task_type"],
                "sample_count": counts[task_id],
            }
            for task_id in TASK_SPECS
        ]
    ).to_csv(tasks_dir / "task_index.csv", index=False, encoding="utf-8-sig")
    return counts


def _create_demo_submissions(root: Path, seed: int = 42) -> None:
    rng = np.random.default_rng(seed)
    tasks_dir = root / "tasks"
    all_tasks = read_jsonl(tasks_dir / "all_tasks.jsonl")

    configs = [
        ("zero_shot", "api_mock_strong", 0.15),
        ("zero_shot", "api_mock_random", 0.85),
        ("fine_tune", "lora7b_mock", 0.10),
    ]
    grouped: Dict[str, List[Dict]] = {}
    for task_id in TASK_SPECS:
        grouped[task_id] = [row for row in all_tasks if row["task_id"] == task_id]

    for track, model, noise in configs:
        model_dir = ensure_dir(root / "submissions" / track / model)
        for task_id, task_rows in grouped.items():
            preds = []
            for row in task_rows:
                answer = row["answer"]
                task_type = TASK_SPECS[task_id]["task_type"]
                if task_type == "objective":
                    if rng.random() < noise:
                        options = row.get("options", [])
                        label_count = max(1, len(options))
                        random_label = chr(ord("A") + int(rng.integers(0, label_count)))
                        pred_val = random_label
                    else:
                        pred_val = str(answer)
                else:
                    if rng.random() < noise:
                        pred_val = "NTL indicates disruption, further assessment required."
                    else:
                        pred_val = str(answer)
                preds.append(
                    {
                        "sample_id": row["sample_id"],
                        "prediction": pred_val,
                        "model_id": model,
                        "track": track,
                    }
                )
            write_jsonl(model_dir / f"{task_id}.jsonl", preds)


def _run_evaluator(root: Path, enable_llm_judge: bool) -> None:
    cmd = [
        sys.executable,
        "-m",
        "benchmarks.ntl_vlm_mvp.evaluate_benchmark",
        "--root",
        str(root),
    ]
    if enable_llm_judge:
        cmd.append("--enable-llm-judge")
    subprocess.run(cmd, check=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full NTL-VLM MVP pipeline.")
    parser.add_argument("--root", default="benchmarks/ntl_vlm_mvp")
    parser.add_argument("--event-registry", default=None)
    parser.add_argument("--target-scenes", type=int, default=3600)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--strict-license", dest="strict_license", action="store_true")
    parser.add_argument("--no-strict-license", dest="strict_license", action="store_false")
    parser.set_defaults(strict_license=True)
    parser.add_argument("--dedup", dest="dedup", action="store_true")
    parser.add_argument("--no-dedup", dest="dedup", action="store_false")
    parser.set_defaults(dedup=True)
    parser.add_argument("--create-demo-submissions", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--enable-llm-judge", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    root = Path(args.root)
    manifests_dir = ensure_dir(root / "manifests")
    reports_dir = ensure_dir(root / "reports")
    split_counts = DEFAULT_SPLIT_COUNTS.copy()

    if int(args.target_scenes) != sum(split_counts.values()):
        raise ValueError("--target-scenes must be 3600 for MVP defaults")

    event_registry = _resolve_event_registry_path(manifests_dir=manifests_dir, cli_value=args.event_registry)
    event_df = pd.read_csv(event_registry)
    event_df = normalize_event_registry(event_df=event_df, strict_license=bool(args.strict_license))

    scene_df = build_scene_manifest_from_events(
        event_df=event_df,
        target_scenes=int(args.target_scenes),
        split_counts=split_counts,
        seed=int(args.seed),
    )
    if args.dedup:
        dedup_df = remove_overlap_duplicates(scene_df)
        if len(dedup_df) == len(scene_df):
            scene_df = dedup_df
        else:
            raise RuntimeError(
                f"dedup removed {len(scene_df) - len(dedup_df)} rows and broke fixed-size split target. "
                "Increase event diversity or run with --no-dedup."
            )

    write_scene_manifest(scene_df, manifests_dir / "scene_manifest.parquet")
    scene_df.to_csv(manifests_dir / "scene_manifest.csv", index=False, encoding="utf-8-sig")
    event_df.to_csv(manifests_dir / "event_registry_clean.csv", index=False, encoding="utf-8-sig")

    task_counts = _build_tasks(root, scene_df)
    task_rows = read_jsonl(root / "tasks" / "all_tasks.jsonl")
    annotation_df = pd.read_csv(root / "annotations" / "double_label_template.csv")
    qc_report = run_quality_gate(
        scene_df=scene_df,
        task_rows=task_rows,
        annotation_df=annotation_df,
        thresholds=QualityGateThresholds(expected_split_counts=split_counts),
    )
    (reports_dir / "qc_report.json").write_text(json.dumps(qc_report, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.create_demo_submissions:
        _create_demo_submissions(root=root, seed=int(args.seed))

    if args.evaluate:
        _run_evaluator(root=root, enable_llm_judge=bool(args.enable_llm_judge))

    summary = {
        "scene_count": int(len(scene_df)),
        "split_counts": scene_df["split"].value_counts().to_dict(),
        "task_counts": task_counts,
        "qc_pass": bool(qc_report["quality_gate_pass"]),
        "reports_dir": str(reports_dir),
    }
    (reports_dir / "pipeline_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
