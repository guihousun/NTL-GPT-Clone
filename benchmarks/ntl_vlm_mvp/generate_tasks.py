"""Generate task files for the NTL-VLM benchmark MVP."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, List

import pandas as pd

from .constants import OBJECTIVE_TASK_IDS, TASK_SPECS
from .io_utils import ensure_dir, read_scene_manifest, write_jsonl
from .schemas import TaskSample


def _option_label(index: int) -> str:
    return chr(ord("A") + index)


def _stable_int(text: str, modulo: int) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % modulo


def _impact_presence_answer(drop_ratio: float) -> str:
    return "A" if drop_ratio >= 0.12 else "B"


def _hazard_answer(hazard_type: str) -> str:
    hazard = hazard_type.lower()
    if "earthquake" in hazard:
        return "A"
    if "flood" in hazard:
        return "B"
    if "wildfire" in hazard or "fire" in hazard:
        return "C"
    if "hurricane" in hazard or "typhoon" in hazard or "storm" in hazard:
        return "D"
    if "conflict" in hazard or "war" in hazard:
        return "E"
    return "F"


def _severity_answer(drop_ratio: float) -> str:
    if drop_ratio < 0.10:
        return "A"
    if drop_ratio < 0.25:
        return "B"
    if drop_ratio < 0.45:
        return "C"
    return "D"


def _count_bin_answer(cluster_count: int) -> str:
    if cluster_count <= 2:
        return "A"
    if cluster_count <= 5:
        return "B"
    if cluster_count <= 10:
        return "C"
    return "D"


def _recovery_answer(recovery_index: float, drop_ratio: float) -> str:
    if drop_ratio < 0.1:
        return "D"
    if recovery_index < 0.20:
        return "A"
    if recovery_index < 0.45:
        return "B"
    if recovery_index < 0.75:
        return "C"
    return "D"


def _caption_text(hazard_type: str, severity_label: str, drop_ratio: float) -> str:
    severity_map = {
        "A": "minimal",
        "B": "moderate",
        "C": "major",
        "D": "extreme",
    }
    sev = severity_map.get(severity_label, "moderate")
    return (
        f"The post-event NTL signal indicates {sev} disruption likely linked to {hazard_type}. "
        f"Estimated brightness decline is about {drop_ratio * 100:.1f}% with localized dark clusters."
    )


def _recommendation_text(hazard_type: str, severity_label: str) -> str:
    immediate = (
        "Immediate actions: prioritize power restoration for hospitals, shelters, and transport hubs; "
        "deploy mobile generators to the darkest districts."
    )
    long_term = (
        f"Long-term actions: reinforce grid resilience against {hazard_type} impacts, "
        "upgrade redundancy, and establish continuous NTL-based outage monitoring."
    )
    if severity_label in {"A", "B"}:
        immediate = (
            "Immediate actions: verify reported outages, focus on localized feeder repair, "
            "and maintain emergency response readiness."
        )
    return f"IMMEDIATE_RECOVERY: {immediate} LONG_TERM_RECOVERY: {long_term}"


def scene_to_task_samples(scene: Dict, source_tag: str) -> List[Dict]:
    scene_id = str(scene["scene_id"])
    hazard_type = str(scene["hazard_type"])
    split = str(scene["split"])
    drop_ratio = float(scene.get("drop_ratio", 0.0))
    quality = float(scene.get("quality_score", 0.8))
    recovery = float(scene.get("recovery_index", 0.5))
    sector = str(scene.get("affected_sector", "")).strip()
    if sector not in {"A", "B", "C", "D"}:
        sector = _option_label(_stable_int(scene_id + "sector", 4))
    cluster_count = int(scene.get("blackout_cluster_count", _stable_int(scene_id + "cluster", 14)))

    t1 = {
        "sample_id": f"{scene_id}_T1",
        "scene_id": scene_id,
        "task_id": "T1",
        "question": "Compare pre-disaster and post-disaster NTL. Is there a significant impact signal?",
        "options": TASK_SPECS["T1"]["options"],
        "answer": _impact_presence_answer(drop_ratio),
        "source": source_tag,
        "confidence": min(0.99, max(0.50, quality)),
        "metadata": {"split": split, "drop_ratio": drop_ratio},
    }
    t2 = {
        "sample_id": f"{scene_id}_T2",
        "scene_id": scene_id,
        "task_id": "T2",
        "question": "Which hazard type best explains this NTL change pattern?",
        "options": TASK_SPECS["T2"]["options"],
        "answer": _hazard_answer(hazard_type),
        "source": source_tag,
        "confidence": min(0.99, max(0.50, quality - 0.05)),
        "metadata": {"split": split, "hazard_type": hazard_type},
    }
    severity = _severity_answer(drop_ratio)
    t3 = {
        "sample_id": f"{scene_id}_T3",
        "scene_id": scene_id,
        "task_id": "T3",
        "question": "Estimate outage severity from the NTL signal drop.",
        "options": TASK_SPECS["T3"]["options"],
        "answer": severity,
        "source": source_tag,
        "confidence": min(0.99, max(0.50, quality - 0.03)),
        "metadata": {"split": split, "drop_ratio": drop_ratio},
    }
    t4 = {
        "sample_id": f"{scene_id}_T4",
        "scene_id": scene_id,
        "task_id": "T4",
        "question": "Which area appears most affected by nighttime darkening?",
        "options": TASK_SPECS["T4"]["options"],
        "answer": sector,
        "source": source_tag,
        "confidence": min(0.99, max(0.45, quality - 0.08)),
        "metadata": {"split": split, "affected_sector": sector},
    }
    t5_answer = _count_bin_answer(cluster_count)
    t5 = {
        "sample_id": f"{scene_id}_T5",
        "scene_id": scene_id,
        "task_id": "T5",
        "question": "How many blackout clusters are likely present?",
        "options": TASK_SPECS["T5"]["options"],
        "answer": t5_answer,
        "source": source_tag,
        "confidence": min(0.99, max(0.45, quality - 0.10)),
        "metadata": {
            "split": split,
            "cluster_count": cluster_count,
            "count_bin_idx": ord(t5_answer) - ord("A"),
        },
    }
    t6 = {
        "sample_id": f"{scene_id}_T6",
        "scene_id": scene_id,
        "task_id": "T6",
        "question": "Based on temporal NTL behavior, what is the recovery state?",
        "options": TASK_SPECS["T6"]["options"],
        "answer": _recovery_answer(recovery_index=recovery, drop_ratio=drop_ratio),
        "source": source_tag,
        "confidence": min(0.99, max(0.45, quality - 0.07)),
        "metadata": {"split": split, "recovery_index": recovery},
    }
    t7 = {
        "sample_id": f"{scene_id}_T7",
        "scene_id": scene_id,
        "task_id": "T7",
        "question": "Write a concise disaster situation caption from the NTL pair.",
        "options": [],
        "answer": _caption_text(hazard_type=hazard_type, severity_label=severity, drop_ratio=drop_ratio),
        "source": source_tag,
        "confidence": min(0.99, max(0.40, quality - 0.12)),
        "metadata": {"split": split},
    }
    t8 = {
        "sample_id": f"{scene_id}_T8",
        "scene_id": scene_id,
        "task_id": "T8",
        "question": "Provide immediate and long-term recovery recommendations.",
        "options": [],
        "answer": _recommendation_text(hazard_type=hazard_type, severity_label=severity),
        "source": source_tag,
        "confidence": min(0.99, max(0.40, quality - 0.14)),
        "metadata": {"split": split},
    }
    samples = [t1, t2, t3, t4, t5, t6, t7, t8]
    # Validate with schema.
    for sample in samples:
        TaskSample(**sample)
    return samples


def _build_annotation_template(task_rows: List[Dict]) -> pd.DataFrame:
    rows = []
    for row in task_rows:
        if row["task_id"] not in OBJECTIVE_TASK_IDS:
            continue
        split = row.get("metadata", {}).get("split", "")
        if split not in {"val", "public_test", "private_test"}:
            continue
        rows.append(
            {
                "sample_id": row["sample_id"],
                "task_id": row["task_id"],
                "split": split,
                "labeler_a": "",
                "labeler_b": "",
                "adjudicated_label": "",
            }
        )
    return pd.DataFrame(rows)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate task jsonl files from scene manifest.")
    parser.add_argument("--root", default="benchmarks/ntl_vlm_mvp")
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--source-tag", default="weak_rule+ntl_gpt_draft")
    parser.add_argument("--limit-scenes", type=int, default=None)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    root = Path(args.root)
    manifest_path = Path(args.manifest) if args.manifest else root / "manifests" / "scene_manifest.parquet"

    scene_df = read_scene_manifest(manifest_path)
    if args.limit_scenes is not None:
        scene_df = scene_df.head(int(args.limit_scenes)).copy()

    all_rows: List[Dict] = []
    for _, row in scene_df.iterrows():
        all_rows.extend(scene_to_task_samples(row.to_dict(), source_tag=str(args.source_tag)))

    tasks_dir = ensure_dir(root / "tasks")
    for task_id in TASK_SPECS:
        task_rows = [row for row in all_rows if row["task_id"] == task_id]
        write_jsonl(tasks_dir / f"{task_id}.jsonl", task_rows)

    write_jsonl(tasks_dir / "all_tasks.jsonl", all_rows)

    index_df = pd.DataFrame(
        [
            {
                "task_id": task_id,
                "task_name": TASK_SPECS[task_id]["name"],
                "task_type": TASK_SPECS[task_id]["task_type"],
                "sample_count": sum(1 for row in all_rows if row["task_id"] == task_id),
            }
            for task_id in TASK_SPECS
        ]
    )
    index_df.to_csv(tasks_dir / "task_index.csv", index=False, encoding="utf-8-sig")

    annotation_df = _build_annotation_template(all_rows)
    ensure_dir(root / "annotations")
    annotation_df.to_csv(root / "annotations" / "double_label_template.csv", index=False, encoding="utf-8-sig")

    summary = {
        "scene_count": int(len(scene_df)),
        "task_sample_count": int(len(all_rows)),
        "task_counts": {task_id: int(index_df[index_df["task_id"] == task_id]["sample_count"].iloc[0]) for task_id in TASK_SPECS},
    }
    (root / "tasks" / "task_build_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

