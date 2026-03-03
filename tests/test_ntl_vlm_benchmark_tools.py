from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

from benchmarks.ntl_vlm_mvp.io_utils import read_jsonl, read_scene_manifest
from benchmarks.ntl_vlm_mvp.schemas import TaskSample


def _load_tools_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "NTL_VLM_benchmark_tools.py"
    spec = importlib.util.spec_from_file_location("ntl_vlm_benchmark_tools_test", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_VLM_benchmark_tools module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _event_registry_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_id": "evt_eq",
                "event_day": "2024-01-10",
                "hazard_type": "earthquake",
                "aoi_wkt": "POLYGON((10 10, 11 10, 11 11, 10 11, 10 10))",
                "license_tag": "cc-by-4.0",
                "source": "stub",
                "region_name": "r1",
                "severity_hint": 0.8,
                "quality_score": 0.9,
                "cloud_free_ratio": 0.8,
            },
            {
                "event_id": "evt_wf",
                "event_day": "2024-02-11",
                "hazard_type": "wildfire",
                "aoi_wkt": "POLYGON((20 20, 21 20, 21 21, 20 21, 20 20))",
                "license_tag": "cc-by-4.0",
                "source": "stub",
                "region_name": "r2",
                "severity_hint": 0.7,
                "quality_score": 0.88,
                "cloud_free_ratio": 0.79,
            },
            {
                "event_id": "evt_fl",
                "event_day": "2024-03-12",
                "hazard_type": "flood",
                "aoi_wkt": "POLYGON((30 30, 31 30, 31 31, 30 31, 30 30))",
                "license_tag": "cc-by-4.0",
                "source": "stub",
                "region_name": "r3",
                "severity_hint": 0.75,
                "quality_score": 0.91,
                "cloud_free_ratio": 0.82,
            },
            {
                "event_id": "evt_cf",
                "event_day": "2024-04-13",
                "hazard_type": "conflict",
                "aoi_wkt": "POLYGON((40 40, 41 40, 41 41, 40 41, 40 40))",
                "license_tag": "cc-by-4.0",
                "source": "stub",
                "region_name": "r4",
                "severity_hint": 0.85,
                "quality_score": 0.92,
                "cloud_free_ratio": 0.81,
            },
        ]
    )


def _write_event_registry(root: Path) -> Path:
    manifests = root / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    path = manifests / "event_registry_clean.csv"
    _event_registry_df().to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _build_manifest_with_tool(mod, root: Path, event_registry_path: Path) -> dict:
    raw = mod.ntl_vlm_build_scene_manifest_tool.invoke(
        {
            "root": str(root),
            "event_registry": str(event_registry_path),
            "target_scenes": 14,
            "train_count": 8,
            "val_count": 2,
            "public_test_count": 2,
            "private_test_count": 2,
            "dedup": False,
            "strict_license": True,
            "seed": 7,
        }
    )
    return json.loads(raw)


def _generate_tasks_with_tool(mod, root: Path) -> dict:
    raw = mod.ntl_vlm_generate_tasks_tool.invoke({"root": str(root)})
    return json.loads(raw)


def _write_perfect_submissions(root: Path, track: str = "zero_shot", model: str = "test_model") -> None:
    tasks = read_jsonl(root / "tasks" / "all_tasks.jsonl")
    model_dir = root / "submissions" / track / model
    model_dir.mkdir(parents=True, exist_ok=True)
    grouped = {}
    for row in tasks:
        grouped.setdefault(str(row["task_id"]), []).append(row)
    for task_id, rows in grouped.items():
        preds = [
            {
                "sample_id": row["sample_id"],
                "prediction": row["answer"],
                "model_id": model,
                "track": track,
            }
            for row in rows
        ]
        with (model_dir / f"{task_id}.jsonl").open("w", encoding="utf-8") as f:
            for rec in preds:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def test_fetch_tool_builds_clean_registry_with_stubbed_sources(tmp_path, monkeypatch):
    mod = _load_tools_module()

    def _stub_build_event_registry(**_kwargs):
        return _event_registry_df()

    monkeypatch.setattr(mod.fetch_mod, "build_event_registry", _stub_build_event_registry)
    result = json.loads(
        mod.ntl_vlm_fetch_event_registry_tool.invoke(
            {
                "root": str(tmp_path),
                "natural_target": 3,
                "conflict_target": 1,
            }
        )
    )
    assert result["status"] == "success"
    summary = result["summary"]
    assert summary["clean_count"] == 4
    assert Path(summary["paths"]["raw"]).exists()
    assert Path(summary["paths"]["clean"]).exists()
    assert Path(result["summary_path"]).exists()


def test_build_manifest_tool_handles_multi_hazard_inputs(tmp_path):
    mod = _load_tools_module()
    event_registry_path = _write_event_registry(tmp_path)
    result = _build_manifest_with_tool(mod, tmp_path, event_registry_path)
    assert result["status"] == "success"

    scene_df = read_scene_manifest(tmp_path / "manifests" / "scene_manifest.parquet")
    assert len(scene_df) == 14
    assert set(scene_df["split"].unique()) == {"train", "val", "public_test", "private_test"}
    assert set(scene_df["hazard_type"].unique()) == {"earthquake", "wildfire", "flood", "conflict"}


def test_generate_tasks_tool_outputs_t1_to_t8_contract(tmp_path):
    mod = _load_tools_module()
    event_registry_path = _write_event_registry(tmp_path)
    build_result = _build_manifest_with_tool(mod, tmp_path, event_registry_path)
    assert build_result["status"] == "success"

    result = _generate_tasks_with_tool(mod, tmp_path)
    assert result["status"] == "success"
    for task_id in [f"T{i}" for i in range(1, 9)]:
        path = tmp_path / "tasks" / f"{task_id}.jsonl"
        assert path.exists()
        rows = read_jsonl(path)
        assert rows
        TaskSample(**rows[0])

    all_rows = read_jsonl(tmp_path / "tasks" / "all_tasks.jsonl")
    assert len(all_rows) == 14 * 8
    assert Path(result["annotation_template_path"]).exists()


def test_generate_jobs_tool_outputs_three_stage_job_files(tmp_path):
    mod = _load_tools_module()
    event_registry_path = _write_event_registry(tmp_path)
    build_result = _build_manifest_with_tool(mod, tmp_path, event_registry_path)
    assert build_result["status"] == "success"

    result = json.loads(
        mod.ntl_vlm_generate_jobs_tool.invoke(
            {
                "root": str(tmp_path),
                "event_registry": str(event_registry_path),
                "limit_scenes": 10,
            }
        )
    )
    assert result["status"] == "success"
    assert Path(result["stage_paths"]["stage1"]).exists()
    assert Path(result["stage_paths"]["stage2"]).exists()
    assert Path(result["stage_paths"]["stage3"]).exists()
    summary = result["summary"]
    assert summary["stage1_jobs"] == 4
    assert summary["stage2_jobs"] == 10
    assert summary["stage3_jobs"] == 10


def test_qc_tool_returns_gate_report(tmp_path):
    mod = _load_tools_module()
    event_registry_path = _write_event_registry(tmp_path)
    build_result = _build_manifest_with_tool(mod, tmp_path, event_registry_path)
    assert build_result["status"] == "success"
    tasks_result = _generate_tasks_with_tool(mod, tmp_path)
    assert tasks_result["status"] == "success"

    result = json.loads(mod.ntl_vlm_qc_tool.invoke({"root": str(tmp_path)}))
    assert result["status"] == "success"
    assert isinstance(result["quality_gate_pass"], bool)
    assert Path(result["report_path"]).exists()


def test_evaluate_tool_writes_leaderboard_from_minimal_submissions(tmp_path):
    mod = _load_tools_module()
    event_registry_path = _write_event_registry(tmp_path)
    build_result = _build_manifest_with_tool(mod, tmp_path, event_registry_path)
    assert build_result["status"] == "success"
    tasks_result = _generate_tasks_with_tool(mod, tmp_path)
    assert tasks_result["status"] == "success"
    _write_perfect_submissions(tmp_path, track="zero_shot", model="test_model")

    result = json.loads(
        mod.ntl_vlm_evaluate_tool.invoke(
            {
                "root": str(tmp_path),
                "tracks": "zero_shot",
                "splits": "val",
                "enable_llm_judge": False,
            }
        )
    )
    assert result["status"] == "success"
    reports = result["reports"]
    assert Path(reports["overall"]).exists()
    assert Path(reports["by_task"]).exists()
    assert Path(reports["by_split"]).exists()
    assert Path(reports["leaderboard"]).exists()
    assert result["top_leaderboard"][0]["model"] == "test_model"

