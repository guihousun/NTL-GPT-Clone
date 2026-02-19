"""Evaluate submissions for NTL-VLM benchmark MVP."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

from .constants import (
    DEFAULT_OBJECTIVE_WEIGHT,
    DEFAULT_TEXT_WEIGHT,
    OBJECTIVE_TASK_IDS,
    TASK_SPECS,
    TEXT_TASK_IDS,
    TRACKS,
)
from .io_utils import ensure_dir, read_jsonl, read_scene_manifest, write_dataframe_csv
from .llm_judge import LLMJudge
from .schemas import PredictionRecord
from .text_metrics import aggregate_text_metrics, normalized_text_score


_LABEL_RE = re.compile(r"\b([A-Z])\b")


def _normalize_label(value: Any) -> str:
    text = str(value).strip().upper()
    if len(text) == 1 and text.isalpha():
        return text
    match = _LABEL_RE.search(text)
    if match:
        return match.group(1)
    return text[:1] if text else ""


def _accuracy(y_true: List[str], y_pred: List[str]) -> float:
    if not y_true:
        return 0.0
    hits = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    return float(hits / len(y_true))


def _binary_f1(y_true: List[str], y_pred: List[str], positive_label: str = "A") -> float:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == positive_label and p == positive_label)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t != positive_label and p == positive_label)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == positive_label and p != positive_label)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    if precision + recall == 0:
        return 0.0
    return float((2 * precision * recall) / (precision + recall))


def _macro_f1(y_true: List[str], y_pred: List[str]) -> float:
    if not y_true:
        return 0.0
    labels = sorted(set(y_true) | set(y_pred))
    if not labels:
        return 0.0

    scores: List[float] = []
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        if precision + recall == 0:
            scores.append(0.0)
        else:
            scores.append((2 * precision * recall) / (precision + recall))
    return float(sum(scores) / len(scores))


def _label_index(label: str) -> int:
    label = _normalize_label(label)
    if not label or not label[0].isalpha():
        return -1
    return ord(label[0]) - ord("A")


def load_references(root: Path) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, str]]:
    manifest = read_scene_manifest(root / "manifests" / "scene_manifest.parquet")
    split_map = {str(row["scene_id"]): str(row["split"]) for _, row in manifest.iterrows()}

    refs: Dict[str, List[Dict[str, Any]]] = {}
    for task_id in TASK_SPECS:
        task_file = root / "tasks" / f"{task_id}.jsonl"
        refs[task_id] = read_jsonl(task_file)
    return refs, split_map


def _filter_by_split(rows: List[Dict[str, Any]], split_map: Dict[str, str], splits: Iterable[str]) -> List[Dict[str, Any]]:
    split_set = set(splits)
    return [row for row in rows if split_map.get(str(row["scene_id"])) in split_set]


def _load_prediction_map(path: Path) -> Dict[str, Any]:
    pred_map: Dict[str, Any] = {}
    for row in read_jsonl(path):
        parsed = PredictionRecord(**row)
        pred_map[parsed.sample_id] = parsed.prediction
    return pred_map


def evaluate_objective_task(task_id: str, ref_rows: List[Dict[str, Any]], pred_map: Dict[str, Any]) -> Dict[str, float]:
    y_true: List[str] = []
    y_pred: List[str] = []
    for row in ref_rows:
        y_true.append(_normalize_label(row["answer"]))
        pred_val = pred_map.get(row["sample_id"], "")
        y_pred.append(_normalize_label(pred_val))

    result: Dict[str, float] = {
        "sample_count": float(len(ref_rows)),
        "accuracy": _accuracy(y_true, y_pred),
        "macro_f1": _macro_f1(y_true, y_pred),
    }
    if task_id == "T1":
        result["f1"] = _binary_f1(y_true=y_true, y_pred=y_pred, positive_label="A")
    if task_id == "T5":
        idx_true = [_label_index(v) for v in y_true]
        idx_pred = [_label_index(v) for v in y_pred]
        exact = sum(1 for t, p in zip(idx_true, idx_pred) if t == p) / max(len(idx_true), 1)
        pm1 = sum(1 for t, p in zip(idx_true, idx_pred) if t >= 0 and p >= 0 and abs(t - p) <= 1) / max(len(idx_true), 1)
        result["exact_accuracy"] = float(exact)
        result["pm1_accuracy"] = float(pm1)
    return result


def evaluate_text_task(
    task_id: str,
    ref_rows: List[Dict[str, Any]],
    pred_map: Dict[str, Any],
    judge: LLMJudge,
) -> Dict[str, float]:
    refs: List[str] = []
    preds: List[str] = []
    llm_scores: List[float] = []
    for row in ref_rows:
        ref_text = str(row["answer"])
        pred_text = str(pred_map.get(row["sample_id"], ""))
        refs.append(ref_text)
        preds.append(pred_text)
        context = row.get("question", "")
        llm_scores.append(judge.score(task_id=task_id, reference=ref_text, prediction=pred_text, context=context))

    metrics = aggregate_text_metrics(refs, preds)
    llm_avg = float(sum(llm_scores) / max(len(llm_scores), 1))
    text_score = normalized_text_score(
        bleu=metrics["bleu4"],
        rouge=metrics["rouge_l"],
        cider=metrics["cider_lite"],
        llm_score=llm_avg,
    )
    metrics.update(
        {
            "sample_count": float(len(ref_rows)),
            "llm_score": llm_avg,
            "text_score": text_score,
        }
    )
    return metrics


def _primary_metric(task_id: str, task_metrics: Dict[str, float]) -> float:
    metric_name = TASK_SPECS[task_id]["primary_metric"]
    if metric_name not in task_metrics:
        return 0.0
    return float(task_metrics[metric_name])


def evaluate_track_model_split(
    root: Path,
    refs: Dict[str, List[Dict[str, Any]]],
    split_map: Dict[str, str],
    track: str,
    model: str,
    split_name: str,
    judge: LLMJudge,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    split_rows: List[Dict[str, Any]] = []
    objective_scores: List[float] = []
    text_scores: List[float] = []
    tasks_details: List[Dict[str, Any]] = []

    for task_id in TASK_SPECS:
        subset = _filter_by_split(refs[task_id], split_map=split_map, splits=[split_name])
        pred_file = root / "submissions" / track / model / f"{task_id}.jsonl"
        pred_map = _load_prediction_map(pred_file) if pred_file.exists() else {}

        if TASK_SPECS[task_id]["task_type"] == "objective":
            metrics = evaluate_objective_task(task_id=task_id, ref_rows=subset, pred_map=pred_map)
            objective_scores.append(_primary_metric(task_id, metrics))
        else:
            metrics = evaluate_text_task(task_id=task_id, ref_rows=subset, pred_map=pred_map, judge=judge)
            text_scores.append(float(metrics["text_score"]))

        task_row = {
            "track": track,
            "model": model,
            "split": split_name,
            "task_id": task_id,
            "task_name": TASK_SPECS[task_id]["name"],
            "task_type": TASK_SPECS[task_id]["task_type"],
            **metrics,
        }
        tasks_details.append(task_row)

    objective_score = float(sum(objective_scores) / max(len(objective_scores), 1))
    text_score = float(sum(text_scores) / max(len(text_scores), 1))
    overall = DEFAULT_OBJECTIVE_WEIGHT * objective_score + DEFAULT_TEXT_WEIGHT * text_score

    summary = {
        "track": track,
        "model": model,
        "split": split_name,
        "objective_score": objective_score,
        "text_score": text_score,
        "overall_score": overall,
        "objective_weight": DEFAULT_OBJECTIVE_WEIGHT,
        "text_weight": DEFAULT_TEXT_WEIGHT,
    }
    return summary, tasks_details


def _collect_models(root: Path, requested_tracks: List[str]) -> List[Tuple[str, str]]:
    results: List[Tuple[str, str]] = []
    submissions_root = root / "submissions"
    for track in requested_tracks:
        track_dir = submissions_root / track
        if not track_dir.exists():
            continue
        for model_dir in sorted(track_dir.iterdir()):
            if model_dir.is_dir():
                results.append((track, model_dir.name))
    return results


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate NTL-VLM benchmark submissions.")
    parser.add_argument("--root", default="benchmarks/ntl_vlm_mvp")
    parser.add_argument(
        "--splits",
        default="val,public_test,private_test",
        help="Comma-separated splits to evaluate. Use 'all' to include val,public_test,private_test.",
    )
    parser.add_argument("--tracks", default="zero_shot,fine_tune")
    parser.add_argument("--enable-llm-judge", action="store_true")
    parser.add_argument("--llm-model", default="gpt-4o-mini")
    parser.add_argument("--llm-cache", default=None)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    root = Path(args.root)
    reports_dir = ensure_dir(root / "reports")

    if args.splits.strip().lower() == "all":
        split_list = ["val", "public_test", "private_test"]
    else:
        split_list = [chunk.strip() for chunk in args.splits.split(",") if chunk.strip()]
    track_list = [chunk.strip() for chunk in args.tracks.split(",") if chunk.strip()]
    track_list = [track for track in track_list if track in TRACKS]

    refs, split_map = load_references(root)
    cache_path = Path(args.llm_cache) if args.llm_cache else reports_dir / "llm_judge_cache.jsonl"
    judge = LLMJudge(cache_path=cache_path, model=args.llm_model, enabled=bool(args.enable_llm_judge))

    models = _collect_models(root=root, requested_tracks=track_list)
    if not models:
        raise RuntimeError("no submissions found under submissions/<track>/<model>")

    overall_rows: List[Dict[str, Any]] = []
    by_split_rows: List[Dict[str, Any]] = []
    by_task_rows: List[Dict[str, Any]] = []

    for track, model in models:
        per_split_summaries: List[Dict[str, Any]] = []
        for split_name in split_list:
            split_summary, task_details = evaluate_track_model_split(
                root=root,
                refs=refs,
                split_map=split_map,
                track=track,
                model=model,
                split_name=split_name,
                judge=judge,
            )
            by_split_rows.append(split_summary)
            by_task_rows.extend(task_details)
            per_split_summaries.append(split_summary)

        overall = {
            "track": track,
            "model": model,
            "split": "overall",
            "objective_score": float(sum(item["objective_score"] for item in per_split_summaries) / len(per_split_summaries)),
            "text_score": float(sum(item["text_score"] for item in per_split_summaries) / len(per_split_summaries)),
        }
        overall["overall_score"] = DEFAULT_OBJECTIVE_WEIGHT * overall["objective_score"] + DEFAULT_TEXT_WEIGHT * overall["text_score"]
        overall_rows.append(overall)

    overall_df = pd.DataFrame(overall_rows).sort_values("overall_score", ascending=False).reset_index(drop=True)
    by_split_df = pd.DataFrame(by_split_rows).sort_values(["track", "model", "split"]).reset_index(drop=True)
    by_task_df = pd.DataFrame(by_task_rows).sort_values(["track", "model", "split", "task_id"]).reset_index(drop=True)
    leaderboard_df = overall_df[["track", "model", "overall_score", "objective_score", "text_score"]].copy()
    leaderboard_df = leaderboard_df.sort_values("overall_score", ascending=False).reset_index(drop=True)
    leaderboard_df["rank"] = leaderboard_df.index + 1
    leaderboard_df = leaderboard_df[["rank", "track", "model", "overall_score", "objective_score", "text_score"]]

    write_dataframe_csv(overall_df, reports_dir / "overall.csv")
    write_dataframe_csv(by_task_df, reports_dir / "by_task.csv")
    write_dataframe_csv(by_split_df, reports_dir / "by_split.csv")
    write_dataframe_csv(leaderboard_df, reports_dir / "leaderboard.csv")
    (reports_dir / "summary.json").write_text(
        json.dumps(
            {
                "models_evaluated": len(overall_df),
                "splits": split_list,
                "tracks": track_list,
                "enable_llm_judge": bool(args.enable_llm_judge),
                "llm_model": args.llm_model,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("[EVAL] overall report:", reports_dir / "overall.csv")
    print("[EVAL] leaderboard:", reports_dir / "leaderboard.csv")
    print(leaderboard_df.to_string(index=False))


if __name__ == "__main__":
    main()

