from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from benchmarks.ntl_vlm_mvp import build_dataset as build_mod
from benchmarks.ntl_vlm_mvp import evaluate_benchmark as eval_mod
from benchmarks.ntl_vlm_mvp import fetch_event_registry as fetch_mod
from benchmarks.ntl_vlm_mvp import generate_ntlgpt_jobs as jobs_mod
from benchmarks.ntl_vlm_mvp import generate_tasks as tasks_mod
from benchmarks.ntl_vlm_mvp import qc as qc_mod
from benchmarks.ntl_vlm_mvp.constants import DEFAULT_SPLIT_COUNTS, TASK_SPECS, TRACKS
from benchmarks.ntl_vlm_mvp.io_utils import (
    ensure_dir,
    read_jsonl,
    read_scene_manifest,
    write_dataframe_csv,
    write_jsonl,
    write_scene_manifest,
)
from benchmarks.ntl_vlm_mvp.llm_judge import LLMJudge


DEFAULT_BENCHMARK_ROOT = "benchmarks/ntl_vlm_mvp"


def _abs(path: Path) -> str:
    return str(path.resolve())


def _ok(payload: Dict[str, Any]) -> str:
    output = {"status": "success"}
    output.update(payload)
    return json.dumps(output, indent=2, ensure_ascii=False)


def _err(error_type: str, error_message: str, fix_suggestions: Optional[List[str]] = None) -> str:
    payload = {
        "status": "fail",
        "error_type": error_type,
        "error_message": error_message,
        "fix_suggestions": fix_suggestions or [],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _parse_splits(raw: str) -> List[str]:
    value = str(raw or "").strip().lower()
    if value == "all":
        return ["val", "public_test", "private_test"]
    chunks = [part.strip() for part in str(raw).split(",") if part.strip()]
    return chunks or ["val", "public_test", "private_test"]


def _parse_tracks(raw: str) -> List[str]:
    chunks = [part.strip() for part in str(raw).split(",") if part.strip()]
    if not chunks:
        return ["zero_shot", "fine_tune"]
    return [track for track in chunks if track in TRACKS]


class NTLVLMFetchEventRegistryInput(BaseModel):
    root: str = Field(default=DEFAULT_BENCHMARK_ROOT, description="Benchmark root directory.")
    natural_target: int = Field(default=120, ge=1, description="Target count for natural hazards.")
    conflict_target: int = Field(default=80, ge=1, description="Target count for conflict events.")
    ucdp_pages: int = Field(default=10, ge=1, description="Max pages to fetch from UCDP endpoint.")
    start_date: str = Field(default="2023-01-01", description="Start date for conflict fetch.")
    end_date: str = Field(default="2024-12-31", description="End date for conflict fetch.")


class NTLVLMBuildSceneManifestInput(BaseModel):
    root: str = Field(default=DEFAULT_BENCHMARK_ROOT, description="Benchmark root directory.")
    event_registry: Optional[str] = Field(
        default=None,
        description="Optional explicit event registry CSV path. Defaults to manifests/event_registry_clean.csv then template.",
    )
    target_scenes: int = Field(default=3600, ge=1, description="Total number of target scene pairs.")
    strict_license: bool = Field(default=True, description="Apply strict open-license filtering.")
    dedup: bool = Field(default=True, description="Apply overlap duplicate removal.")
    seed: int = Field(default=42, description="Random seed for deterministic sampling.")
    train_count: int = Field(default=DEFAULT_SPLIT_COUNTS["train"], ge=0)
    val_count: int = Field(default=DEFAULT_SPLIT_COUNTS["val"], ge=0)
    public_test_count: int = Field(default=DEFAULT_SPLIT_COUNTS["public_test"], ge=0)
    private_test_count: int = Field(default=DEFAULT_SPLIT_COUNTS["private_test"], ge=0)


class NTLVLMGenerateTasksInput(BaseModel):
    root: str = Field(default=DEFAULT_BENCHMARK_ROOT, description="Benchmark root directory.")
    manifest: Optional[str] = Field(
        default=None,
        description="Optional manifest path. Defaults to manifests/scene_manifest.parquet.",
    )
    source_tag: str = Field(default="weak_rule+ntl_gpt_draft", description="Task source tag.")
    limit_scenes: Optional[int] = Field(default=None, ge=1, description="Optional scene count cap.")


class NTLVLMGenerateJobsInput(BaseModel):
    root: str = Field(default=DEFAULT_BENCHMARK_ROOT, description="Benchmark root directory.")
    event_registry: Optional[str] = Field(default=None, description="Optional event registry path.")
    scene_manifest: Optional[str] = Field(default=None, description="Optional scene manifest path.")
    limit_scenes: int = Field(default=200, ge=1, description="Max scenes for stage2/stage3 jobs.")


class NTLVLMQCInput(BaseModel):
    root: str = Field(default=DEFAULT_BENCHMARK_ROOT, description="Benchmark root directory.")
    manifest: Optional[str] = Field(default=None, description="Optional scene manifest path.")
    tasks_dir: Optional[str] = Field(default=None, description="Optional task directory path.")
    annotation_file: Optional[str] = Field(default=None, description="Optional annotation CSV path.")
    min_auto_pass_rate: float = Field(default=0.98, ge=0.0, le=1.0)
    min_kappa: float = Field(default=0.80, ge=-1.0, le=1.0)


class NTLVLMEvaluateInput(BaseModel):
    root: str = Field(default=DEFAULT_BENCHMARK_ROOT, description="Benchmark root directory.")
    splits: str = Field(
        default="val,public_test,private_test",
        description="Comma-separated splits or 'all'.",
    )
    tracks: str = Field(default="zero_shot,fine_tune", description="Comma-separated track list.")
    enable_llm_judge: bool = Field(default=False, description="Enable LLM text judge if API key is available.")
    llm_model: str = Field(default="gpt-4o-mini", description="LLM judge model name.")
    llm_cache: Optional[str] = Field(default=None, description="Optional path for LLM judge cache jsonl.")


def ntl_vlm_fetch_event_registry(
    root: str = DEFAULT_BENCHMARK_ROOT,
    natural_target: int = 120,
    conflict_target: int = 80,
    ucdp_pages: int = 10,
    start_date: str = "2023-01-01",
    end_date: str = "2024-12-31",
) -> str:
    try:
        root_path = Path(root)
        manifests = ensure_dir(root_path / "manifests")
        fetched_df = fetch_mod.build_event_registry(
            natural_target=int(natural_target),
            conflict_target=int(conflict_target),
            ucdp_pages=int(ucdp_pages),
            start_date=str(start_date),
            end_date=str(end_date),
        )

        fetched_path = manifests / "event_registry_fetched_raw.csv"
        fetched_df.to_csv(fetched_path, index=False, encoding="utf-8-sig")

        clean_df = build_mod.normalize_event_registry(fetched_df, strict_license=True)
        clean_path = manifests / "event_registry_clean.csv"
        clean_df.to_csv(clean_path, index=False, encoding="utf-8-sig")

        summary = {
            "raw_count": int(len(fetched_df)),
            "clean_count": int(len(clean_df)),
            "natural_count": int((clean_df["hazard_type"] != "conflict").sum()),
            "conflict_count": int((clean_df["hazard_type"] == "conflict").sum()),
            "source_counts": clean_df["source"].value_counts().to_dict(),
            "hazard_counts": clean_df["hazard_type"].value_counts().to_dict(),
            "event_day_range": {
                "min": str(pd.to_datetime(clean_df["event_day"]).min().date()),
                "max": str(pd.to_datetime(clean_df["event_day"]).max().date()),
            },
            "paths": {
                "raw": _abs(fetched_path),
                "clean": _abs(clean_path),
            },
        }
        summary_path = manifests / "event_registry_fetch_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

        return _ok(
            {
                "root": _abs(root_path),
                "summary_path": _abs(summary_path),
                "summary": summary,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(
            "NTLVLMFetchEventRegistryError",
            str(exc),
            fix_suggestions=[
                "Check internet connectivity and source availability (GDACS/UCDP).",
                "Retry with smaller targets or fewer UCDP pages.",
                "Verify root path is writable.",
            ],
        )


def ntl_vlm_build_scene_manifest(
    root: str = DEFAULT_BENCHMARK_ROOT,
    event_registry: Optional[str] = None,
    target_scenes: int = 3600,
    strict_license: bool = True,
    dedup: bool = True,
    seed: int = 42,
    train_count: int = DEFAULT_SPLIT_COUNTS["train"],
    val_count: int = DEFAULT_SPLIT_COUNTS["val"],
    public_test_count: int = DEFAULT_SPLIT_COUNTS["public_test"],
    private_test_count: int = DEFAULT_SPLIT_COUNTS["private_test"],
) -> str:
    try:
        root_path = Path(root)
        manifests_dir = ensure_dir(root_path / "manifests")
        split_counts = {
            "train": int(train_count),
            "val": int(val_count),
            "public_test": int(public_test_count),
            "private_test": int(private_test_count),
        }
        total_expected = sum(split_counts.values())
        if int(target_scenes) != total_expected:
            return _err(
                "InvalidSplitCountConfig",
                f"target_scenes={target_scenes} does not equal split sum={total_expected}",
                fix_suggestions=["Align target_scenes with train/val/public_test/private_test counts."],
            )

        event_registry_path = build_mod._resolve_event_registry_path(  # type: ignore[attr-defined]
            manifests_dir=manifests_dir,
            cli_value=event_registry,
        )
        if not event_registry_path.exists():
            return _err(
                "EventRegistryNotFound",
                f"event registry not found: {event_registry_path}",
                fix_suggestions=[
                    "Run ntl_vlm_fetch_event_registry_tool first.",
                    "Provide explicit event_registry path.",
                ],
            )

        event_df = pd.read_csv(event_registry_path)
        event_df = build_mod.normalize_event_registry(event_df=event_df, strict_license=bool(strict_license))
        scene_df = build_mod.build_scene_manifest_from_events(
            event_df=event_df,
            target_scenes=int(target_scenes),
            split_counts=split_counts,
            seed=int(seed),
        )

        warnings: List[str] = []
        if dedup:
            dedup_df = build_mod.remove_overlap_duplicates(scene_df)
            if len(dedup_df) != len(scene_df):
                if len(dedup_df) < int(target_scenes):
                    return _err(
                        "DedupInsufficientScenes",
                        (
                            f"dedup removed {len(scene_df) - len(dedup_df)} rows and reduced scene count below "
                            f"target={target_scenes}"
                        ),
                        fix_suggestions=[
                            "Disable dedup for this run.",
                            "Increase event diversity in event registry.",
                            "Use a larger event pool before strict license filtering.",
                        ],
                    )
                scene_df = dedup_df.head(int(target_scenes)).copy()
                scene_df = build_mod.assign_splits(scene_df=scene_df, split_counts=split_counts, seed=int(seed))
                warnings.append("dedup_removed_overlap_rows")

        scene_manifest_path = manifests_dir / "scene_manifest.parquet"
        try:
            write_scene_manifest(scene_df, scene_manifest_path)
        except Exception as exc:  # noqa: BLE001
            # write_scene_manifest already writes CSV fallback; keep tool successful with warning.
            warnings.append(str(exc))
        scene_manifest_csv_path = manifests_dir / "scene_manifest.csv"
        write_dataframe_csv(scene_df, scene_manifest_csv_path)
        write_dataframe_csv(event_df, manifests_dir / "event_registry_clean.csv")

        summary = {
            "target_scenes": int(target_scenes),
            "event_count": int(len(event_df)),
            "split_counts": {k: int(v) for k, v in scene_df["split"].value_counts().to_dict().items()},
            "quality_mean": float(scene_df["quality_score"].mean()),
            "drop_ratio_mean": float(scene_df["drop_ratio"].mean()),
            "scene_manifest_path": _abs(scene_manifest_path),
            "scene_manifest_csv_path": _abs(scene_manifest_csv_path),
            "seed": int(seed),
            "warnings": warnings,
        }
        summary_path = manifests_dir / "build_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

        return _ok(
            {
                "root": _abs(root_path),
                "event_registry_path": _abs(event_registry_path),
                "summary_path": _abs(summary_path),
                "summary": summary,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(
            "NTLVLMBuildSceneManifestError",
            str(exc),
            fix_suggestions=[
                "Verify event_registry columns satisfy required schema.",
                "Check split counts and target scene configuration.",
                "Ensure manifests directory is writable.",
            ],
        )


def ntl_vlm_generate_tasks(
    root: str = DEFAULT_BENCHMARK_ROOT,
    manifest: Optional[str] = None,
    source_tag: str = "weak_rule+ntl_gpt_draft",
    limit_scenes: Optional[int] = None,
) -> str:
    try:
        root_path = Path(root)
        manifest_path = Path(manifest) if manifest else root_path / "manifests" / "scene_manifest.parquet"
        scene_df = read_scene_manifest(manifest_path)
        if limit_scenes is not None:
            scene_df = scene_df.head(int(limit_scenes)).copy()

        all_rows: List[Dict[str, Any]] = []
        for _, row in scene_df.iterrows():
            all_rows.extend(tasks_mod.scene_to_task_samples(row.to_dict(), source_tag=str(source_tag)))

        tasks_dir = ensure_dir(root_path / "tasks")
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
        index_path = tasks_dir / "task_index.csv"
        index_df.to_csv(index_path, index=False, encoding="utf-8-sig")

        annotation_df = tasks_mod._build_annotation_template(all_rows)  # type: ignore[attr-defined]
        annotations_dir = ensure_dir(root_path / "annotations")
        annotation_path = annotations_dir / "double_label_template.csv"
        annotation_df.to_csv(annotation_path, index=False, encoding="utf-8-sig")

        summary = {
            "scene_count": int(len(scene_df)),
            "task_sample_count": int(len(all_rows)),
            "task_counts": {
                task_id: int(index_df[index_df["task_id"] == task_id]["sample_count"].iloc[0])
                for task_id in TASK_SPECS
            },
        }
        summary_path = tasks_dir / "task_build_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

        return _ok(
            {
                "root": _abs(root_path),
                "manifest_path": _abs(manifest_path),
                "tasks_dir": _abs(tasks_dir),
                "task_index_path": _abs(index_path),
                "annotation_template_path": _abs(annotation_path),
                "summary_path": _abs(summary_path),
                "summary": summary,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(
            "NTLVLMGenerateTasksError",
            str(exc),
            fix_suggestions=[
                "Ensure scene manifest exists and is readable.",
                "Check scene schema contains required task fields.",
                "Verify tasks/annotations directories are writable.",
            ],
        )


def ntl_vlm_generate_jobs(
    root: str = DEFAULT_BENCHMARK_ROOT,
    event_registry: Optional[str] = None,
    scene_manifest: Optional[str] = None,
    limit_scenes: int = 200,
) -> str:
    try:
        root_path = Path(root)
        jobs_dir = ensure_dir(root_path / "jobs")

        event_registry_path = Path(event_registry) if event_registry else root_path / "manifests" / "event_registry_clean.csv"
        scene_manifest_path = Path(scene_manifest) if scene_manifest else root_path / "manifests" / "scene_manifest.parquet"

        if not event_registry_path.exists():
            return _err(
                "EventRegistryNotFound",
                f"event registry not found: {event_registry_path}",
                fix_suggestions=["Run ntl_vlm_fetch_event_registry_tool first or pass explicit event_registry."],
            )
        if not scene_manifest_path.exists() and not scene_manifest_path.with_suffix(".csv").exists():
            return _err(
                "SceneManifestNotFound",
                f"scene manifest not found: {scene_manifest_path}",
                fix_suggestions=["Run ntl_vlm_build_scene_manifest_tool first or pass explicit scene_manifest."],
            )

        event_df = pd.read_csv(event_registry_path)
        scene_df = read_scene_manifest(scene_manifest_path)
        scene_df = scene_df.head(int(limit_scenes)).copy()

        stage1 = jobs_mod.build_event_discovery_jobs(event_df)
        stage2 = jobs_mod.build_router_blueprint_jobs(scene_df)
        stage3 = jobs_mod.build_extraction_jobs(scene_df)

        stage1_path = jobs_dir / "stage1_event_discovery.jsonl"
        stage2_path = jobs_dir / "stage2_gee_router_blueprint.jsonl"
        stage3_path = jobs_dir / "stage3_patch_extraction.jsonl"
        write_jsonl(stage1_path, stage1)
        write_jsonl(stage2_path, stage2)
        write_jsonl(stage3_path, stage3)

        summary = {
            "stage1_jobs": len(stage1),
            "stage2_jobs": len(stage2),
            "stage3_jobs": len(stage3),
            "jobs_dir": _abs(jobs_dir),
        }
        summary_path = jobs_dir / "job_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

        return _ok(
            {
                "root": _abs(root_path),
                "summary_path": _abs(summary_path),
                "stage_paths": {
                    "stage1": _abs(stage1_path),
                    "stage2": _abs(stage2_path),
                    "stage3": _abs(stage3_path),
                },
                "summary": summary,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(
            "NTLVLMGenerateJobsError",
            str(exc),
            fix_suggestions=[
                "Ensure scene/event manifests exist.",
                "Validate limit_scenes is positive.",
                "Verify jobs directory is writable.",
            ],
        )


def ntl_vlm_run_qc(
    root: str = DEFAULT_BENCHMARK_ROOT,
    manifest: Optional[str] = None,
    tasks_dir: Optional[str] = None,
    annotation_file: Optional[str] = None,
    min_auto_pass_rate: float = 0.98,
    min_kappa: float = 0.80,
) -> str:
    try:
        root_path = Path(root)
        reports_dir = ensure_dir(root_path / "reports")
        manifest_path = Path(manifest) if manifest else root_path / "manifests" / "scene_manifest.parquet"
        tasks_path = Path(tasks_dir) if tasks_dir else root_path / "tasks"
        annotation_path = Path(annotation_file) if annotation_file else root_path / "annotations" / "double_label_template.csv"

        scene_df = read_scene_manifest(manifest_path)
        task_rows = qc_mod.load_task_rows(tasks_path)
        annotation_df = pd.read_csv(annotation_path) if annotation_path.exists() else None

        thresholds = qc_mod.QualityGateThresholds(
            min_auto_pass_rate=float(min_auto_pass_rate),
            min_kappa=float(min_kappa),
            expected_split_counts=DEFAULT_SPLIT_COUNTS.copy(),
        )
        report = qc_mod.run_quality_gate(
            scene_df=scene_df,
            task_rows=task_rows,
            annotation_df=annotation_df,
            thresholds=thresholds,
        )

        report_path = reports_dir / "qc_report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return _ok(
            {
                "root": _abs(root_path),
                "report_path": _abs(report_path),
                "quality_gate_pass": bool(report.get("quality_gate_pass", False)),
                "auto_pass_rate": float(report.get("auto_pass_rate", 0.0)),
                "kappa": report.get("kappa"),
                "split_counts_ok": bool(report.get("split_counts_ok", False)),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(
            "NTLVLMQCToolError",
            str(exc),
            fix_suggestions=[
                "Ensure manifest and tasks are generated before QC.",
                "Check annotation CSV format (labeler_a/labeler_b).",
                "Verify shapely/parquet dependencies if geometry/manifest loading fails.",
            ],
        )


def ntl_vlm_evaluate(
    root: str = DEFAULT_BENCHMARK_ROOT,
    splits: str = "val,public_test,private_test",
    tracks: str = "zero_shot,fine_tune",
    enable_llm_judge: bool = False,
    llm_model: str = "gpt-4o-mini",
    llm_cache: Optional[str] = None,
) -> str:
    try:
        root_path = Path(root)
        reports_dir = ensure_dir(root_path / "reports")
        split_list = _parse_splits(splits)
        track_list = _parse_tracks(tracks)
        if not track_list:
            return _err(
                "NoValidTracks",
                f"No valid tracks in '{tracks}'",
                fix_suggestions=[f"Use one or more of: {TRACKS}"],
            )

        refs, split_map = eval_mod.load_references(root_path)
        cache_path = Path(llm_cache) if llm_cache else reports_dir / "llm_judge_cache.jsonl"
        judge_enabled = bool(enable_llm_judge)
        judge = LLMJudge(cache_path=cache_path, model=llm_model, enabled=judge_enabled)

        models = eval_mod._collect_models(root=root_path, requested_tracks=track_list)  # type: ignore[attr-defined]
        if not models:
            return _err(
                "NoSubmissionsFound",
                f"no submissions found under {root_path / 'submissions'}",
                fix_suggestions=[
                    "Generate submissions under submissions/<track>/<model>/<task_id>.jsonl.",
                    "Verify tracks parameter matches existing submission folders.",
                ],
            )

        overall_rows: List[Dict[str, Any]] = []
        by_split_rows: List[Dict[str, Any]] = []
        by_task_rows: List[Dict[str, Any]] = []

        for track, model in models:
            per_split_summaries: List[Dict[str, Any]] = []
            for split_name in split_list:
                split_summary, task_details = eval_mod.evaluate_track_model_split(
                    root=root_path,
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
                "objective_score": float(
                    sum(item["objective_score"] for item in per_split_summaries) / len(per_split_summaries)
                ),
                "text_score": float(sum(item["text_score"] for item in per_split_summaries) / len(per_split_summaries)),
            }
            overall["overall_score"] = (
                eval_mod.DEFAULT_OBJECTIVE_WEIGHT * overall["objective_score"]
                + eval_mod.DEFAULT_TEXT_WEIGHT * overall["text_score"]
            )
            overall_rows.append(overall)

        overall_df = pd.DataFrame(overall_rows).sort_values("overall_score", ascending=False).reset_index(drop=True)
        by_split_df = pd.DataFrame(by_split_rows).sort_values(["track", "model", "split"]).reset_index(drop=True)
        by_task_df = pd.DataFrame(by_task_rows).sort_values(["track", "model", "split", "task_id"]).reset_index(drop=True)
        leaderboard_df = overall_df[["track", "model", "overall_score", "objective_score", "text_score"]].copy()
        leaderboard_df = leaderboard_df.sort_values("overall_score", ascending=False).reset_index(drop=True)
        leaderboard_df["rank"] = leaderboard_df.index + 1
        leaderboard_df = leaderboard_df[["rank", "track", "model", "overall_score", "objective_score", "text_score"]]

        overall_path = reports_dir / "overall.csv"
        by_task_path = reports_dir / "by_task.csv"
        by_split_path = reports_dir / "by_split.csv"
        leaderboard_path = reports_dir / "leaderboard.csv"

        write_dataframe_csv(overall_df, overall_path)
        write_dataframe_csv(by_task_df, by_task_path)
        write_dataframe_csv(by_split_df, by_split_path)
        write_dataframe_csv(leaderboard_df, leaderboard_path)

        llm_key_present = bool(os.getenv("OPENAI_API_KEY", "").strip())
        summary_payload = {
            "models_evaluated": len(overall_df),
            "splits": split_list,
            "tracks": track_list,
            "enable_llm_judge_requested": bool(enable_llm_judge),
            "llm_model": llm_model,
            "openai_api_key_present": llm_key_present,
            "llm_judge_effective_mode": (
                "llm_or_heuristic_fallback" if bool(enable_llm_judge) else "heuristic_only"
            ),
            "cache_path": _abs(cache_path),
        }
        summary_path = reports_dir / "summary.json"
        summary_path.write_text(json.dumps(summary_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        return _ok(
            {
                "root": _abs(root_path),
                "reports": {
                    "overall": _abs(overall_path),
                    "by_task": _abs(by_task_path),
                    "by_split": _abs(by_split_path),
                    "leaderboard": _abs(leaderboard_path),
                    "summary": _abs(summary_path),
                },
                "top_leaderboard": leaderboard_df.head(5).to_dict(orient="records"),
                "summary": summary_payload,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(
            "NTLVLMEvaluateToolError",
            str(exc),
            fix_suggestions=[
                "Ensure task references and submissions are generated.",
                "Validate submission JSONL schema: sample_id,prediction,model_id,track.",
                "Try smaller split scope first (for example splits='val').",
            ],
        )


ntl_vlm_fetch_event_registry_tool = StructuredTool.from_function(
    func=ntl_vlm_fetch_event_registry,
    name="ntl_vlm_fetch_event_registry_tool",
    description=(
        "Fetch and normalize benchmark event registry from public sources (GDACS/UCDP), "
        "then write raw/clean manifests and summary JSON."
    ),
    args_schema=NTLVLMFetchEventRegistryInput,
)


ntl_vlm_build_scene_manifest_tool = StructuredTool.from_function(
    func=ntl_vlm_build_scene_manifest,
    name="ntl_vlm_build_scene_manifest_tool",
    description=(
        "Build NTL-VLM scene manifest from event registry with split control, "
        "license filtering, and optional overlap dedup."
    ),
    args_schema=NTLVLMBuildSceneManifestInput,
)


ntl_vlm_generate_tasks_tool = StructuredTool.from_function(
    func=ntl_vlm_generate_tasks,
    name="ntl_vlm_generate_tasks_tool",
    description=(
        "Generate benchmark tasks T1..T8 plus task index and annotation template from scene manifest."
    ),
    args_schema=NTLVLMGenerateTasksInput,
)


ntl_vlm_generate_jobs_tool = StructuredTool.from_function(
    func=ntl_vlm_generate_jobs,
    name="ntl_vlm_generate_jobs_tool",
    description=(
        "Generate staged NTL-GPT production job manifests for event discovery, GEE routing, and patch extraction."
    ),
    args_schema=NTLVLMGenerateJobsInput,
)


ntl_vlm_qc_tool = StructuredTool.from_function(
    func=ntl_vlm_run_qc,
    name="ntl_vlm_qc_tool",
    description=(
        "Run benchmark quality gates (schema checks, duplicate/leak checks, pass-rate and kappa thresholds)."
    ),
    args_schema=NTLVLMQCInput,
)


ntl_vlm_evaluate_tool = StructuredTool.from_function(
    func=ntl_vlm_evaluate,
    name="ntl_vlm_evaluate_tool",
    description=(
        "Evaluate submissions and write overall/by_task/by_split/leaderboard reports."
    ),
    args_schema=NTLVLMEvaluateInput,
)

