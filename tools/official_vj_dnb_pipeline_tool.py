from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from storage_manager import current_thread_id, storage_manager


REPO_ROOT = Path(__file__).resolve().parents[1]
QUERY_SCRIPT = REPO_ROOT / "tools" / "query_vj_dnb_laads_json.py"
DOWNLOAD_SCRIPT = REPO_ROOT / "tools" / "download_vj_dnb.py"
PREPROCESS_SCRIPT = REPO_ROOT / "experiments" / "official_daily_ntl_fastpath" / "convert_vj102_vj103_precise_to_tif.py"


class OfficialVJDNBPipelineInput(BaseModel):
    start_date: str = Field(..., description="Start date in YYYY-MM-DD")
    end_date: str = Field(..., description="End date in YYYY-MM-DD")
    bbox: str = Field(..., description="minx,miny,maxx,maxy in lon/lat. Example: 44.03,25.08,63.33,39.77")
    output_root: str = Field(
        default="official_vj_dnb_pipeline_runs",
        description=(
            "Output subfolder under current thread workspace outputs/. "
            "Example: official_vj_dnb_pipeline_runs"
        ),
    )
    run_label: str = Field(
        default="",
        description="Optional run label. If empty, auto-generated from date range.",
    )
    sources: str = Field(
        default="VJ102DNB,VJ103DNB",
        description="Comma-separated sources for query step. Default includes both.",
    )
    composite: str = Field(default="mean", description="Daily composite method: mean or max")
    resolution_m: float = Field(default=500.0, description="Output target resolution in meters")
    radius_m: float = Field(default=2000.0, description="Nearest-neighbor radius in meters")
    radiance_scale: float = Field(default=1e9, description="Radiance scale factor, default 1e9")
    token_env: str = Field(default="EARTHDATA_TOKEN", description="Earthdata token env var name")
    page_size: int = Field(default=200, description="CMR query page size")
    skip_preprocess: bool = Field(default=False, description="If true, only query+download without preprocessing")


def _resolve_thread_id_from_config(config: Optional[RunnableConfig] = None) -> str:
    runtime_config: Optional[RunnableConfig] = None
    if isinstance(config, dict):
        runtime_config = config
    else:
        inherited = var_child_runnable_config.get()
        if isinstance(inherited, dict):
            runtime_config = inherited

    if isinstance(runtime_config, dict):
        try:
            tid = str(storage_manager.get_thread_id_from_config(runtime_config) or "").strip()
            if tid:
                return tid
        except Exception:
            pass
    return str(current_thread_id.get() or "debug").strip() or "debug"


def _resolve_output_root(output_root: str, thread_id: str) -> tuple[Path, str]:
    workspace = storage_manager.get_workspace(thread_id=thread_id)
    outputs_root = workspace / "outputs"
    raw = (output_root or "").strip()
    if not raw:
        raw = "official_vj_dnb_pipeline_runs"

    if raw.startswith("/data/processed/"):
        return Path(storage_manager.resolve_deepagents_path(raw, thread_id=thread_id)), "deepagents_virtual"
    if raw.startswith("/shared/"):
        raise PermissionError("output_root under /shared/ is not allowed for writing.")

    p = Path(raw)
    if p.is_absolute():
        raise ValueError("output_root must be workspace-relative (do not use absolute path).")
    if ".." in p.parts:
        raise ValueError("output_root must not contain '..'.")

    return (outputs_root / p).resolve(), "workspace_outputs_relative"


def _run_cmd(cmd: list[str], cwd: Path) -> dict[str, Any]:
    started = datetime.utcnow()
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    ended = datetime.utcnow()
    return {
        "cmd": cmd,
        "returncode": int(proc.returncode),
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "started_utc": started.isoformat() + "Z",
        "ended_utc": ended.isoformat() + "Z",
        "duration_sec": max(0.0, (ended - started).total_seconds()),
    }


def _ensure_date(v: str, name: str) -> str:
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD, got: {v}") from exc
    return v


def _build_run_label(start_date: str, end_date: str, run_label: str) -> str:
    if run_label.strip():
        return run_label.strip()
    return f"vj_dnb_{start_date.replace('-', '')}_{end_date.replace('-', '')}"


def run_official_vj_dnb_fullchain(
    start_date: str,
    end_date: str,
    bbox: str,
    output_root: str = "official_vj_dnb_pipeline_runs",
    run_label: str = "",
    sources: str = "VJ102DNB,VJ103DNB",
    composite: str = "mean",
    resolution_m: float = 500.0,
    radius_m: float = 2000.0,
    radiance_scale: float = 1e9,
    token_env: str = "EARTHDATA_TOKEN",
    page_size: int = 200,
    skip_preprocess: bool = False,
    config: Optional[RunnableConfig] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Full chain pipeline for official VJ102/VJ103:
    1) Query download JSON by bbox+date
    2) Download VJ102DNB/VJ103DNB
    3) Precise preprocessing to daily GeoTIFF
    """
    start_date = _ensure_date(start_date, "start_date")
    end_date = _ensure_date(end_date, "end_date")
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")
    if composite not in {"mean", "max"}:
        raise ValueError("composite must be mean or max")

    thread_id = _resolve_thread_id_from_config(config)
    label = _build_run_label(start_date, end_date, run_label)
    root, path_mode = _resolve_output_root(output_root, thread_id=thread_id)
    run_dir = root / label
    query_dir = run_dir / "query"
    raw_dir = run_dir / "raw_nc"
    processed_dir = run_dir / "processed_tif"
    query_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    query_json = query_dir / f"LAADS_query_{start_date}_{end_date}.json"

    _ = kwargs  # reserved for forward-compatible optional fields
    env = os.environ.copy()
    token_present = bool(env.get(token_env, "").strip())

    query_cmd = [
        sys.executable,
        str(QUERY_SCRIPT),
        "--start-date",
        start_date,
        "--end-date",
        end_date,
        "--bbox",
        bbox,
        "--sources",
        sources,
        "--output",
        str(query_json),
        "--page-size",
        str(int(page_size)),
    ]
    query_result = _run_cmd(query_cmd, REPO_ROOT)
    if query_result["returncode"] != 0:
        raise RuntimeError(
            "Query step failed.\n"
            f"cmd={' '.join(query_cmd)}\n"
            f"stderr={query_result['stderr'][-1200:]}\n"
            f"stdout={query_result['stdout'][-1200:]}"
        )

    download_cmd = [
        sys.executable,
        str(DOWNLOAD_SCRIPT),
        "--input",
        str(query_json),
        "--output",
        str(raw_dir),
        "--token-env",
        token_env,
    ]
    download_result = _run_cmd(download_cmd, REPO_ROOT)
    if download_result["returncode"] != 0:
        raise RuntimeError(
            "Download step failed.\n"
            f"cmd={' '.join(download_cmd)}\n"
            f"stderr={download_result['stderr'][-1600:]}\n"
            f"stdout={download_result['stdout'][-1600:]}"
        )

    preprocess_result: Optional[dict[str, Any]] = None
    if not skip_preprocess:
        preprocess_cmd = [
            sys.executable,
            str(PREPROCESS_SCRIPT),
            "--input-dir",
            str(raw_dir),
            "--output-dir",
            str(processed_dir),
            "--start-date",
            start_date,
            "--end-date",
            end_date,
            "--bbox",
            bbox,
            "--composite",
            composite,
            "--resolution-m",
            str(float(resolution_m)),
            "--radius-m",
            str(float(radius_m)),
            "--radiance-scale",
            str(float(radiance_scale)),
        ]
        preprocess_result = _run_cmd(preprocess_cmd, REPO_ROOT)
        if preprocess_result["returncode"] != 0:
            raise RuntimeError(
                "Preprocess step failed.\n"
                f"cmd={' '.join(preprocess_cmd)}\n"
                f"stderr={preprocess_result['stderr'][-1600:]}\n"
                f"stdout={preprocess_result['stdout'][-1600:]}"
            )

    daily_outputs: list[str] = []
    if processed_dir.exists():
        daily_outputs = sorted(str(p) for p in (processed_dir / "daily_4326").glob("*.tif"))

    manifest = {
        "status": "success",
        "tool": "official_vj_dnb_fullchain_tool",
        "params": {
            "thread_id": thread_id,
            "start_date": start_date,
            "end_date": end_date,
            "bbox": bbox,
            "sources": sources,
            "composite": composite,
            "resolution_m": float(resolution_m),
            "radius_m": float(radius_m),
            "radiance_scale": float(radiance_scale),
            "token_env": token_env,
            "token_present": token_present,
            "skip_preprocess": bool(skip_preprocess),
            "path_mode": path_mode,
        },
        "paths": {
            "workspace": str(storage_manager.get_workspace(thread_id=thread_id)),
            "run_dir": str(run_dir),
            "query_json": str(query_json),
            "raw_dir": str(raw_dir),
            "processed_dir": str(processed_dir),
            "download_manifest": str(raw_dir / "download_manifest.json"),
            "preprocess_summary": str(processed_dir / "precise_preprocess_summary.json"),
        },
        "output_files": daily_outputs,
        "steps": {
            "query": query_result,
            "download": download_result,
            "preprocess": preprocess_result,
        },
    }
    out_manifest = run_dir / "pipeline_manifest.json"
    out_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["paths"]["pipeline_manifest"] = str(out_manifest)
    return manifest


official_vj_dnb_fullchain_tool = StructuredTool.from_function(
    func=run_official_vj_dnb_fullchain,
    name="official_vj_dnb_fullchain_tool",
    description=(
        "Official VJ102DNB/VJ103DNB full chain pipeline: query LAADS JSON by bbox/date, "
        "download raw NC files, and preprocess into daily GeoTIFF outputs."
    ),
    args_schema=OfficialVJDNBPipelineInput,
)
