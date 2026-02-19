from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from storage_manager import current_thread_id, storage_manager

REQUIRED_GEE_PROJECT = "empyrean-caster-430308-m2"

GLOBAL_EXEC_CONTEXTS: Dict[str, Dict[str, Any]] = {}

# Known NTL datasets and expected bands for guardrail checks.
KNOWN_GEE_DATASETS: Dict[str, List[str]] = {
    "projects/sat-io/open-datasets/npp-viirs-ntl": ["b1"],
    "NOAA/VIIRS/DNB/ANNUAL_V21": ["average", "average_masked", "cf_cvg", "cvg", "maximum", "median", "minimum"],
    "NOAA/VIIRS/DNB/ANNUAL_V22": ["average", "average_masked", "cf_cvg", "cvg", "maximum", "median", "minimum"],
    "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG": ["avg_rad", "cf_cvg"],
    "NOAA/DMSP-OLS/NIGHTTIME_LIGHTS": ["avg_vis", "stable_lights"],
    "NASA/VIIRS/002/VNP46A2": ["Gap_Filled_DNB_BRDF_Corrected_NTL", "DNB_BRDF_Corrected_NTL"],
    "NOAA/VIIRS/001/VNP46A1": ["DNB_At_Sensor_Radiance_500m"],
}

KNOWN_GEE_PREFIXES = (
    "projects/sat-io/open-datasets/",
    "projects/empyrean-caster-430308-m2/assets/",
)

KNOWN_GEE_PUBLIC_COLLECTION_PREFIXES = (
    "NOAA/",
    "NASA/",
    "FAO/",
    "COPERNICUS/",
    "USGS/",
    "MODIS/",
)

ABSOLUTE_PATH_PATTERNS = [
    re.compile(r"[A-Za-z]:\\\\"),
    re.compile(r"/(?:home|Users|mnt|tmp)/"),
]

READ_PATTERNS = [
    r"rasterio\.open\(",
    r"gpd\.read_file\(",
    r"pd\.read_csv\(",
    r"pd\.read_excel\(",
]

WRITE_PATTERNS = [
    r"\.to_csv\(",
    r"\.to_file\(",
    r"plt\.savefig\(",
    r"rasterio\.open\([^\n]*['\"]w['\"]",
    r"open\([^\n]*,\s*['\"](?:w|a|x|wb|ab|xb)['\"]",
    r"\.write_text\(",
    r"\.write_bytes\(",
]

FORBIDDEN_SOURCE_TARGET_PATTERNS = [
    re.compile(r"['\"][^'\"]*[/\\]agents[/\\][^'\"]*['\"]"),
    re.compile(r"['\"][^'\"]*[/\\]tools[/\\][^'\"]*['\"]"),
    re.compile(r"['\"][^'\"]*[/\\]docs[/\\][^'\"]*['\"]"),
    re.compile(r"['\"][^'\"]*[/\\]tests[/\\][^'\"]*['\"]"),
    re.compile(r"['\"](?:app_agents\.py|app_logic\.py|app_ui\.py|Streamlit\.py|storage_manager\.py|requirements\.txt|installed_skill_meta\.json|\.env)['\"]"),
]

FORBIDDEN_COMMAND_PATTERNS = [
    re.compile(r"os\.system\([^\)]*git\s+", flags=re.IGNORECASE),
    re.compile(r"subprocess\.(?:run|Popen)\([^\)]*git\s+", flags=re.IGNORECASE),
    re.compile(r"apply_patch", flags=re.IGNORECASE),
]


class GeoCodeCOTBlockInput(BaseModel):
    code_block: str = Field(
        ...,
        description=(
            "A minimal, self-contained Python code snippet that tests one specific logic unit "
            "from the original geospatial code, such as data loading, CRS matching, field access, "
            "masking, or regression modeling."
        ),
    )
    strict_mode: bool = Field(
        default=True,
        description=(
            "If True, block execution when protocol violations are detected (e.g., absolute paths, "
            "missing storage_manager path resolution)."
        ),
    )


class FinalCodeInput(BaseModel):
    final_geospatial_code: str = Field(
        ...,
        description="The final geospatial Python code that has passed all Geo-CodeCoT mini tests.",
    )
    script_name: Optional[str] = Field(
        default=None,
        description="Optional output script filename. If omitted, a unique .py name is generated.",
    )
    strict_mode: bool = Field(
        default=True,
        description="If True, block final execution when preflight finds hard protocol violations.",
    )


class SaveScriptInput(BaseModel):
    script_content: str = Field(
        ...,
        description="Python script content to persist under the current thread workspace outputs.",
    )
    script_name: Optional[str] = Field(
        default=None,
        description="Optional script filename. .py will be appended automatically when missing.",
    )
    overwrite: bool = Field(
        default=False,
        description="Whether to overwrite an existing script when script_name already exists.",
    )


class ExecuteScriptInput(BaseModel):
    script_name: str = Field(
        ...,
        description="Script filename previously saved by save_geospatial_script_tool (for example analysis_plan.py).",
    )
    strict_mode: bool = Field(
        default=True,
        description="If True, block execution when preflight finds hard protocol violations.",
    )


def _sanitize_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text or "")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_script_name(script_name: Optional[str], prefix: str) -> str:
    if script_name and script_name.strip():
        basename = os.path.basename(script_name.strip())
        if not basename.lower().endswith(".py"):
            basename = f"{basename}.py"
        basename = re.sub(r"[^A-Za-z0-9._-]", "_", basename)
        basename = basename.strip("._")
        if basename and basename != "py":
            return basename
    return f"{prefix}_{_timestamp()}_{uuid4().hex[:8]}.py"


def _persist_script(
    script_content: str,
    script_name: Optional[str] = None,
    *,
    prefix: str,
    overwrite: bool = False,
) -> Tuple[str, str]:
    safe_name = _safe_script_name(script_name, prefix=prefix)
    script_path = Path(storage_manager.resolve_output_path(safe_name))

    if script_path.exists() and not overwrite and script_name:
        safe_name = _safe_script_name(None, prefix=prefix)
        script_path = Path(storage_manager.resolve_output_path(safe_name))

    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script_content, encoding="utf-8")
    return safe_name, str(script_path)


def _append_run_history(event: Dict[str, Any]) -> None:
    try:
        history_path = Path(storage_manager.resolve_output_path("code_execution_history.jsonl"))
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False))
            f.write("\n")
    except Exception:
        # History logging is best effort and must not interrupt tool execution.
        pass


def _runtime_code_guide_dir() -> Path:
    env_path = os.getenv("NTL_CODE_GUIDE_RUNTIME_DIR", "").strip()
    if env_path:
        return Path(env_path).resolve()
    repo_root = Path(__file__).resolve().parents[1]
    return (repo_root / "RAG" / "code_guide" / "tools_latest_runtime").resolve()


def _archive_success_script(
    script_content: str,
    *,
    source_tool: str,
    script_name: str,
    script_path: str,
    stdout: str = "",
) -> Dict[str, Any]:
    info: Dict[str, Any] = {"archived": False}
    if not script_content.strip():
        info["archive_error"] = "empty_script_content"
        return info

    try:
        runtime_dir = _runtime_code_guide_dir()
        runtime_dir.mkdir(parents=True, exist_ok=True)
        thread_id = str(current_thread_id.get() or "default")
        normalized = _normalize_whitespace(script_content)
        content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

        stem = re.sub(r"[^A-Za-z0-9._-]", "_", Path(script_name).stem).strip("._")
        if not stem:
            stem = "runtime_script"
        archive_script_name = f"{content_hash[:12]}_{stem}.py"
        archive_script_path = runtime_dir / archive_script_name
        if not archive_script_path.exists():
            archive_script_path.write_text(script_content, encoding="utf-8")

        metadata = {
            "timestamp_utc": _timestamp(),
            "source_tool": source_tool,
            "thread_id": thread_id,
            "original_script_name": script_name,
            "original_script_path": script_path,
            "content_hash": content_hash,
            "stdout_excerpt": (stdout or "")[:2000],
        }
        archive_meta_path = runtime_dir / f"{archive_script_path.stem}.meta.json"
        archive_meta_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        manifest_path = runtime_dir / "runtime_manifest.jsonl"
        manifest_entry = dict(metadata)
        manifest_entry["archive_script_name"] = archive_script_name
        manifest_entry["archive_script_path"] = str(archive_script_path)
        manifest_entry["archive_metadata_path"] = str(archive_meta_path)
        with manifest_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(manifest_entry, ensure_ascii=False))
            f.write("\n")

        info.update(
            {
                "archived": True,
                "archive_script_name": archive_script_name,
                "archive_script_path": str(archive_script_path),
                "archive_metadata_path": str(archive_meta_path),
                "archive_manifest_path": str(manifest_path),
                "content_hash": content_hash,
                "source_tool": source_tool,
            }
        )
        return info
    except Exception as exc:  # noqa: BLE001
        info["archive_error"] = str(exc)
        return info


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _detect_mode(code: str) -> str:
    has_gee = "import ee" in code or "ee." in code
    has_local = any(token in code for token in ("rasterio", "geopandas", "gpd.", "shapely"))
    if has_gee and has_local:
        return "hybrid"
    if has_gee:
        return "gee"
    if has_local:
        return "local"
    return "general"


def _find_regex_matches(pattern: str, text: str) -> List[str]:
    return [m.group(0) for m in re.finditer(pattern, text)]


def _extract_gee_assets(code: str) -> List[str]:
    assets: List[str] = []
    pattern = re.compile(r"ee\.(?:ImageCollection|FeatureCollection|Image)\(\s*['\"]([^'\"]+)['\"]\s*\)")
    for m in pattern.finditer(code):
        assets.append(m.group(1))
    return assets


def _extract_selected_bands(code: str) -> List[str]:
    bands: List[str] = []
    # select('band') or select(["band1", "band2"])  -> captures quoted names.
    for m in re.finditer(r"\.select\((.*?)\)", code, flags=re.DOTALL):
        inner = m.group(1)
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", inner)
        bands.extend(quoted)
    return bands


def _check_reduce_region_arguments(code: str, warnings: List[str]) -> None:
    calls = re.findall(r"\.reduceRegions?\((.*?)\)", code, flags=re.DOTALL)
    for call in calls:
        normalized = re.sub(r"\s+", " ", call)
        if not any(token in normalized for token in ("scale=", "crs=", "crsTransform=")):
            warnings.append(
                "GEE reduceRegion/reduceRegions is missing explicit scale/crs. Set scale or crs to avoid implicit projection errors."
            )
        if "maxPixels" not in normalized and "maxPixelsPerRegion" not in normalized:
            warnings.append(
                "GEE reduction call is missing maxPixels/maxPixelsPerRegion. Large regions may fail unexpectedly."
            )
        if "bestEffort" not in normalized and "tileScale" not in normalized:
            warnings.append(
                "Consider bestEffort=True or tileScale>1 for large reductions to improve robustness."
            )


def _preflight_checks(code: str, strict_mode: bool) -> Dict[str, Any]:
    blocking_errors: List[str] = []
    warnings: List[str] = []
    recommendations: List[str] = []

    mode = _detect_mode(code)

    # Syntax check
    try:
        compile(code, "<geocode>", "exec")
    except SyntaxError as exc:
        blocking_errors.append(f"SyntaxError at line {exc.lineno}: {exc.msg}")

    # Path protocol checks
    for pat in ABSOLUTE_PATH_PATTERNS:
        if pat.search(code):
            blocking_errors.append("Detected absolute path usage. Use storage_manager.resolve_input_path/resolve_output_path only.")
            break

    if re.search(r"['\"](?:inputs|outputs)/", code):
        msg = "Detected hardcoded 'inputs/' or 'outputs/' path literal. Use storage_manager path resolvers instead."
        if strict_mode:
            blocking_errors.append(msg)
        else:
            warnings.append(msg)

    has_storage_manager_import = "from storage_manager import storage_manager" in code
    has_resolve_input = "resolve_input_path(" in code
    has_resolve_output = "resolve_output_path(" in code

    uses_read_ops = any(re.search(p, code) for p in READ_PATTERNS)
    uses_write_ops = any(re.search(p, code) for p in WRITE_PATTERNS)

    if (uses_read_ops or uses_write_ops) and not has_storage_manager_import:
        msg = "File I/O detected but missing `from storage_manager import storage_manager` import."
        if strict_mode:
            blocking_errors.append(msg)
        else:
            warnings.append(msg)

    if uses_read_ops and not (has_resolve_input or has_resolve_output):
        msg = "Read operations detected but no resolve_input_path()/resolve_output_path() usage found."
        if strict_mode:
            blocking_errors.append(msg)
        else:
            warnings.append(msg)

    if uses_write_ops and not has_resolve_output:
        msg = "Write operations detected but no resolve_output_path() usage found."
        if strict_mode:
            blocking_errors.append(msg)
        else:
            warnings.append(msg)

    has_source_write_target = any(p.search(code) for p in FORBIDDEN_SOURCE_TARGET_PATTERNS)
    if uses_write_ops and has_source_write_target:
        blocking_errors.append(
            "Detected attempt to write repository source/config files. Code_Assistant may only write analysis outputs."
        )

    if any(p.search(code) for p in FORBIDDEN_COMMAND_PATTERNS):
        blocking_errors.append(
            "Detected prohibited repo-modification command (git/system patch). Only geospatial analysis execution is allowed."
        )

    # GEE checks
    assets = _extract_gee_assets(code)
    selected_bands = _extract_selected_bands(code)
    if mode in {"gee", "hybrid"}:
        has_bbox = "ee.Geometry.Rectangle(" in code
        has_admin_boundary = any(
            token in code
            for token in (
                "get_administrative_division",
                "get_administrative_division_osm",
                "FAO/GAUL/2015/level1",
                "projects/empyrean-caster-430308-m2/assets/province",
                "projects/empyrean-caster-430308-m2/assets/city",
                "projects/empyrean-caster-430308-m2/assets/county",
            )
        )
        has_user_bbox_override = "AOI_CONFIRMED_BY_USER" in code

        if has_bbox and not has_admin_boundary and not has_user_bbox_override:
            msg = (
                "Detected bbox AOI without administrative-boundary confirmation. "
                "Use Data_Searcher-confirmed boundary file/asset, or add `# AOI_CONFIRMED_BY_USER` if user explicitly provided coordinates."
            )
            if strict_mode:
                blocking_errors.append(msg)
            else:
                warnings.append(msg)

        if "ee.Initialize(" not in code:
            warnings.append("GEE code found but no explicit ee.Initialize(...) call. Add initialization with project id.")

        if "ee.Initialize(" in code and "project=" not in code:
            warnings.append(
                f"ee.Initialize() missing explicit project parameter. Recommended: ee.Initialize(project='{REQUIRED_GEE_PROJECT}')."
            )

        for asset in assets:
            is_known_public = asset in KNOWN_GEE_DATASETS or asset.startswith(KNOWN_GEE_PREFIXES) or asset.startswith(KNOWN_GEE_PUBLIC_COLLECTION_PREFIXES)
            if not is_known_public:
                warnings.append(f"Unrecognized GEE asset id: {asset}. Verify availability and access permissions.")

        for asset, allowed_bands in KNOWN_GEE_DATASETS.items():
            if asset in assets and selected_bands:
                unknown = [b for b in selected_bands if b not in allowed_bands]
                if unknown:
                    warnings.append(
                        f"Selected band(s) {unknown} may not belong to {asset}. Expected one of {allowed_bands}."
                    )

        _check_reduce_region_arguments(code, warnings)

    # Local geospatial checks
    if "gdf.area" in code or ".area" in code and "gpd." in code:
        if "to_crs(" not in code:
            warnings.append("Area/length calculation detected without to_crs(). Reproject to a projected CRS before metric calculations.")

    if "sjoin(" in code and "predicate=" not in code and "op=" in code:
        warnings.append("GeoPandas sjoin uses deprecated `op=` in newer versions. Prefer `predicate=`.")

    if "is_valid" in code and "make_valid" not in code and "buffer(0)" not in code:
        recommendations.append("If invalid geometries are found, repair with shapely.make_valid (preferred) or geometry.buffer(0).")

    if mode in {"gee", "hybrid"} and "getInfo()" in code and "for " in code:
        warnings.append("Potential client-side loop with getInfo(). Prefer server-side map/reduce patterns in Earth Engine.")

    if mode in {"gee", "hybrid"}:
        recommendations.append("Prefer server-side aggregation (reduceRegion/reduceRegions) and export only final CSV values.")

    score = max(0, 100 - 30 * len(blocking_errors) - 8 * len(warnings))
    return {
        "mode": mode,
        "strict_mode": strict_mode,
        "score": score,
        "blocking_errors": blocking_errors,
        "warnings": warnings,
        "recommendations": recommendations,
        "detected": {
            "assets": assets,
            "selected_bands": selected_bands,
            "uses_storage_manager_import": has_storage_manager_import,
            "uses_resolve_input_path": has_resolve_input,
            "uses_resolve_output_path": has_resolve_output,
        },
    }


def _derive_fix_suggestions(error_type: Optional[str], error_message: Optional[str]) -> List[str]:
    msg = (error_message or "").lower()
    et = (error_type or "").lower()
    fixes: List[str] = []

    if "filenotfounderror" in et or "no such file" in msg:
        fixes.append("Use storage_manager.resolve_input_path() for existing input files.")
        fixes.append("For files generated in this session, read via storage_manager.resolve_output_path().")

    if "eeexception" in et or "earth engine" in msg:
        fixes.append(f"Ensure ee.Initialize(project='{REQUIRED_GEE_PROJECT}') is called before GEE operations.")
        fixes.append("Verify asset IDs and band names against Earth Engine catalog before execution.")

    if "permission" in msg or "access" in msg:
        fixes.append("Check account permissions for the target GEE asset/project.")

    if "crs" in msg or "projection" in msg:
        fixes.append("Align CRS between raster/vector layers (e.g., vector.to_crs(raster_crs)).")

    if "memory" in msg or "too many pixels" in msg:
        fixes.append("For GEE reductions, set scale/maxPixels and consider bestEffort/tileScale.")
        fixes.append("For local rasters, process in chunks/windows instead of reading full arrays.")

    if "bbox aoi" in msg or "boundary" in msg:
        fixes.append("Request Data_Searcher to provide verified administrative boundary (source, CRS, bounds).")
        fixes.append("Avoid self-defined bbox for named regions unless user explicitly provided coordinates.")

    if not fixes:
        fixes.append("Run GeoCode_COT_Validation_tool with a smaller minimal block to isolate the failing step.")

    return fixes


def _build_error_handling_policy(
    error_type: Optional[str],
    error_message: Optional[str],
    *,
    preflight: Optional[Dict[str, Any]] = None,
    fix_suggestions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    et = (error_type or "").lower()
    msg = (error_message or "").lower()
    suggestions = [s.lower() for s in (fix_suggestions or [])]
    preflight_errors = [str(x).lower() for x in (preflight or {}).get("blocking_errors", [])]

    hard_markers = [
        "boundary",
        "administrative",
        "permission",
        "access denied",
        "authentication",
        "authorization",
        "credential",
        "asset",
        "dataset",
        "request data_searcher",
        "not found in current workspace",
        "missing input",
    ]

    simple_error_types = {
        "syntaxerror",
        "nameerror",
        "typeerror",
        "valueerror",
        "keyerror",
        "indexerror",
        "attributeerror",
        "filenotfounderror",
    }
    hard_error_types = {
        "preflighterror",
        "eeexception",
        "httperror",
        "permissionerror",
        "scriptpersisterror",
        "scriptnotfounderror",
    }

    marker_hit = any(marker in msg for marker in hard_markers)
    marker_hit = marker_hit or any(any(marker in s for marker in hard_markers) for s in suggestions)
    marker_hit = marker_hit or any(any(marker in e for marker in hard_markers) for e in preflight_errors)

    is_hard = et in hard_error_types or marker_hit
    if et in simple_error_types and not marker_hit:
        is_hard = False

    if is_hard:
        return {
            "severity": "hard",
            "should_handoff_to_engineer": True,
            "max_self_retries": 0,
            "recommendation": "handoff_to_engineer_with_context",
            "reason": (
                "The failure likely requires strategy/data/boundary or permission decision outside local code debugging."
            ),
            "decision_options": [
                "ask_engineer_for_additional_data_or_boundary_confirmation",
                "ask_engineer_to_switch_method_or_toolchain",
                "ask_engineer_to_request_user_clarification_if_constraints_are_missing",
            ],
        }

    return {
        "severity": "simple",
        "should_handoff_to_engineer": False,
        "max_self_retries": 1,
        "recommendation": "self_debug_then_retry",
        "reason": "The failure appears code-local and can usually be fixed with limited self-debug iterations.",
        "decision_options": [
            "fix_code_and_retry_within_budget",
            "if_still_failing_after_budget_then_handoff_to_engineer",
        ],
    }


def _get_thread_context() -> Dict[str, Any]:
    thread_id = current_thread_id.get() or "default"
    if thread_id not in GLOBAL_EXEC_CONTEXTS:
        GLOBAL_EXEC_CONTEXTS[thread_id] = {"__name__": "__main__"}
    return GLOBAL_EXEC_CONTEXTS[thread_id]


def _bind_thread_from_config(config: Optional[RunnableConfig]) -> Optional[Any]:
    """Bind current thread context from LangGraph/LangChain runnable config."""
    runtime_config: Optional[RunnableConfig] = None
    if isinstance(config, dict):
        runtime_config = config
    else:
        inherited = var_child_runnable_config.get()
        if isinstance(inherited, dict):
            runtime_config = inherited
    if not isinstance(runtime_config, dict):
        return None
    try:
        thread_id = storage_manager.get_thread_id_from_config(runtime_config)
    except Exception:
        return None
    if not thread_id:
        return None
    return current_thread_id.set(str(thread_id))


def _execute_code(code_block: str) -> Tuple[bool, str, Optional[str], Optional[str], Optional[str]]:
    user_globals = _get_thread_context()
    bootstrap = (
        "import ee\n"
        f"project_id = '{REQUIRED_GEE_PROJECT}'\n"
        "try:\n"
        "    ee.Initialize(project=project_id)\n"
        "except Exception:\n"
        "    pass\n"
    )

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            exec(bootstrap, user_globals)
            exec(code_block, user_globals)
        logs = _sanitize_ansi(buf.getvalue())
        return True, logs, None, None, None
    except Exception as exc:  # noqa: BLE001
        logs = _sanitize_ansi(buf.getvalue())
        return False, logs, type(exc).__name__, str(exc), traceback.format_exc()
    finally:
        buf.close()


def GEE_GeoCode_COT_Validation(
    code_block: str,
    strict_mode: bool = True,
    config: Optional[RunnableConfig] = None,
) -> str:
    token = _bind_thread_from_config(config)
    try:
        try:
            block_script_name, block_script_path = _persist_script(
                code_block,
                prefix="cot_block",
                overwrite=False,
            )
        except Exception as exc:  # noqa: BLE001
            policy = _build_error_handling_policy(
                "ScriptPersistError",
                str(exc),
                preflight=None,
                fix_suggestions=None,
            )
            return json.dumps(
                {
                    "status": "fail",
                    "stdout": "",
                    "error_type": "ScriptPersistError",
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                    "code_block": code_block,
                    "error_handling_policy": policy,
                    "execution_skipped": True,
                },
                indent=2,
                ensure_ascii=False,
            )

        preflight = _preflight_checks(code_block, strict_mode=strict_mode)

        if preflight["blocking_errors"]:
            policy = _build_error_handling_policy(
                "PreflightError",
                preflight["blocking_errors"][0],
                preflight=preflight,
                fix_suggestions=preflight["recommendations"],
            )
            report = {
                "status": "fail",
                "stdout": "",
                "error_type": "PreflightError",
                "error_message": preflight["blocking_errors"][0],
                "traceback": None,
                "code_block": code_block,
                "script_name": block_script_name,
                "script_path": block_script_path,
                "preflight": preflight,
                "fix_suggestions": preflight["recommendations"],
                "error_handling_policy": policy,
                "execution_skipped": True,
            }
            _append_run_history(
                {
                    "timestamp": _timestamp(),
                    "tool": "GeoCode_COT_Validation_tool",
                    "status": "fail",
                    "reason": "preflight",
                    "script_name": block_script_name,
                    "script_path": block_script_path,
                    "thread_id": current_thread_id.get(),
                }
            )
            return json.dumps(report, indent=2, ensure_ascii=False)

        ok, logs, etype, emsg, tb = _execute_code(code_block)
        fix_suggestions = _derive_fix_suggestions(etype, emsg) + preflight["recommendations"]
        report = {
            "status": "pass" if ok else "fail",
            "stdout": logs,
            "error_type": etype,
            "error_message": emsg,
            "traceback": tb,
            "code_block": code_block,
            "script_name": block_script_name,
            "script_path": block_script_path,
            "preflight": preflight,
            "fix_suggestions": fix_suggestions,
            "error_handling_policy": (
                _build_error_handling_policy(etype, emsg, preflight=preflight, fix_suggestions=fix_suggestions)
                if not ok
                else None
            ),
            "execution_skipped": False,
        }
        _append_run_history(
            {
                "timestamp": _timestamp(),
                "tool": "GeoCode_COT_Validation_tool",
                "status": report["status"],
                "script_name": block_script_name,
                "script_path": block_script_path,
                "thread_id": current_thread_id.get(),
            }
        )
        return json.dumps(report, indent=2, ensure_ascii=False)
    finally:
        if token is not None:
            current_thread_id.reset(token)


def final_geospatial_code_execution(
    final_geospatial_code: str,
    script_name: Optional[str] = None,
    strict_mode: bool = True,
    config: Optional[RunnableConfig] = None,
) -> str:
    token = _bind_thread_from_config(config)
    try:
        try:
            saved_script_name, saved_script_path = _persist_script(
                final_geospatial_code,
                script_name=script_name,
                prefix="final_geocode",
                overwrite=False,
            )
        except Exception as exc:  # noqa: BLE001
            policy = _build_error_handling_policy(
                "ScriptPersistError",
                str(exc),
                preflight=None,
                fix_suggestions=None,
            )
            return json.dumps(
                {
                    "status": "fail",
                    "stdout": "",
                    "error_type": "ScriptPersistError",
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                    "code": final_geospatial_code,
                    "error_handling_policy": policy,
                    "execution_skipped": True,
                },
                indent=2,
                ensure_ascii=False,
            )

        preflight = _preflight_checks(final_geospatial_code, strict_mode=strict_mode)

        if preflight["blocking_errors"]:
            policy = _build_error_handling_policy(
                "PreflightError",
                preflight["blocking_errors"][0],
                preflight=preflight,
                fix_suggestions=preflight["recommendations"],
            )
            result = {
                "status": "fail",
                "stdout": "",
                "error_type": "PreflightError",
                "error_message": preflight["blocking_errors"][0],
                "traceback": None,
                "code": final_geospatial_code,
                "script_name": saved_script_name,
                "script_path": saved_script_path,
                "preflight": preflight,
                "fix_suggestions": preflight["recommendations"],
                "error_handling_policy": policy,
                "execution_skipped": True,
            }
            _append_run_history(
                {
                    "timestamp": _timestamp(),
                    "tool": "final_geospatial_code_execution_tool",
                    "status": "fail",
                    "reason": "preflight",
                    "script_name": saved_script_name,
                    "script_path": saved_script_path,
                    "thread_id": current_thread_id.get(),
                }
            )
            return json.dumps(result, indent=2, ensure_ascii=False)

        ok, logs, etype, emsg, tb = _execute_code(final_geospatial_code)
        if ok:
            archive_info = _archive_success_script(
                final_geospatial_code,
                source_tool="final_geospatial_code_execution_tool",
                script_name=saved_script_name,
                script_path=saved_script_path,
                stdout=logs,
            )
            result = {
                "status": "success",
                "stdout": logs,
                "code": final_geospatial_code,
                "script_name": saved_script_name,
                "script_path": saved_script_path,
                "code_guide_archive": archive_info,
                "preflight": preflight,
                "execution_skipped": False,
            }
            _append_run_history(
                {
                    "timestamp": _timestamp(),
                    "tool": "final_geospatial_code_execution_tool",
                    "status": "success",
                    "script_name": saved_script_name,
                    "script_path": saved_script_path,
                    "code_guide_archive": archive_info,
                    "thread_id": current_thread_id.get(),
                }
            )
            return json.dumps(result, indent=2, ensure_ascii=False)

        fix_suggestions = _derive_fix_suggestions(etype, emsg) + preflight["recommendations"]
        result = {
            "status": "fail",
            "stdout": logs,
            "error_type": etype,
            "error_message": emsg,
            "traceback": tb,
            "code": final_geospatial_code,
            "script_name": saved_script_name,
            "script_path": saved_script_path,
            "preflight": preflight,
            "fix_suggestions": fix_suggestions,
            "error_handling_policy": _build_error_handling_policy(
                etype,
                emsg,
                preflight=preflight,
                fix_suggestions=fix_suggestions,
            ),
            "execution_skipped": False,
        }
        _append_run_history(
            {
                "timestamp": _timestamp(),
                "tool": "final_geospatial_code_execution_tool",
                "status": "fail",
                "script_name": saved_script_name,
                "script_path": saved_script_path,
                "thread_id": current_thread_id.get(),
                "error_type": etype,
            }
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    finally:
        if token is not None:
            current_thread_id.reset(token)


def save_geospatial_script(
    script_content: str,
    script_name: Optional[str] = None,
    overwrite: bool = False,
    config: Optional[RunnableConfig] = None,
) -> str:
    token = _bind_thread_from_config(config)
    try:
        if not script_content or not script_content.strip():
            policy = _build_error_handling_policy(
                "EmptyScriptError",
                "script_content is empty.",
                preflight=None,
                fix_suggestions=None,
            )
            return json.dumps(
                {
                    "status": "fail",
                    "error_type": "EmptyScriptError",
                    "error_message": "script_content is empty.",
                    "error_handling_policy": policy,
                },
                indent=2,
                ensure_ascii=False,
            )

        thread_ctx = _get_thread_context()
        normalized_content_hash = hashlib.sha256(_normalize_whitespace(script_content).encode("utf-8")).hexdigest()
        saved_by_hash = thread_ctx.setdefault("__ntl_saved_script_by_hash", {})
        cached_entry = saved_by_hash.get(normalized_content_hash)
        if isinstance(cached_entry, dict) and not overwrite:
            cached_name = str(cached_entry.get("script_name") or "")
            cached_path = str(cached_entry.get("script_path") or "")
            requested_name = (
                os.path.basename((script_name or "").strip()) if (script_name and script_name.strip()) else ""
            )
            if cached_name and cached_path and Path(cached_path).exists():
                # Reuse existing script when content is unchanged to avoid redundant save loops.
                if (not requested_name) or (requested_name.lower() == cached_name.lower()):
                    preflight = _preflight_checks(script_content, strict_mode=False)
                    return json.dumps(
                        {
                            "status": "success",
                            "script_name": cached_name,
                            "script_path": cached_path,
                            "bytes": len(script_content.encode("utf-8")),
                            "preflight_score": preflight["score"],
                            "preflight_warnings": preflight["warnings"],
                            "dedupe": {
                                "reused_existing_script": True,
                                "content_hash": normalized_content_hash,
                            },
                        },
                        indent=2,
                        ensure_ascii=False,
                    )

        try:
            saved_script_name, saved_script_path = _persist_script(
                script_content,
                script_name=script_name,
                prefix="analysis_script",
                overwrite=overwrite,
            )
        except Exception as exc:  # noqa: BLE001
            policy = _build_error_handling_policy(
                "ScriptPersistError",
                str(exc),
                preflight=None,
                fix_suggestions=None,
            )
            return json.dumps(
                {
                    "status": "fail",
                    "error_type": "ScriptPersistError",
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                    "error_handling_policy": policy,
                },
                indent=2,
                ensure_ascii=False,
            )

        preflight = _preflight_checks(script_content, strict_mode=False)
        saved_by_hash[normalized_content_hash] = {
            "script_name": saved_script_name,
            "script_path": saved_script_path,
        }
        thread_ctx["__ntl_last_saved_script_hash"] = normalized_content_hash
        thread_ctx["__ntl_last_saved_script_name"] = saved_script_name
        thread_ctx["__ntl_last_saved_script_path"] = saved_script_path
        _append_run_history(
            {
                "timestamp": _timestamp(),
                "tool": "save_geospatial_script_tool",
                "status": "success",
                "script_name": saved_script_name,
                "script_path": saved_script_path,
                "thread_id": current_thread_id.get(),
            }
        )
        return json.dumps(
            {
                "status": "success",
                "script_name": saved_script_name,
                "script_path": saved_script_path,
                "bytes": len(script_content.encode("utf-8")),
                "preflight_score": preflight["score"],
                "preflight_warnings": preflight["warnings"],
            },
            indent=2,
            ensure_ascii=False,
        )
    finally:
        if token is not None:
            current_thread_id.reset(token)


def execute_geospatial_script(
    script_name: str,
    strict_mode: bool = True,
    config: Optional[RunnableConfig] = None,
) -> str:
    token = _bind_thread_from_config(config)
    try:
        if not script_name or not script_name.strip():
            policy = _build_error_handling_policy(
                "InvalidScriptName",
                "script_name is required.",
                preflight=None,
                fix_suggestions=None,
            )
            return json.dumps(
                {
                    "status": "fail",
                    "error_type": "InvalidScriptName",
                    "error_message": "script_name is required.",
                    "error_handling_policy": policy,
                },
                indent=2,
                ensure_ascii=False,
            )
        safe_name = os.path.basename(script_name.strip())
        if not safe_name.lower().endswith(".py"):
            safe_name = f"{safe_name}.py"
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", safe_name)

        output_script_path = Path(storage_manager.resolve_output_path(safe_name))
        input_script_path = Path(storage_manager.resolve_input_path(safe_name))

        if output_script_path.exists():
            script_path = output_script_path
        elif input_script_path.exists():
            script_path = input_script_path
        else:
            policy = _build_error_handling_policy(
                "ScriptNotFoundError",
                f"Script '{safe_name}' was not found in current workspace inputs/outputs.",
                preflight=None,
                fix_suggestions=None,
            )
            return json.dumps(
                {
                    "status": "fail",
                    "error_type": "ScriptNotFoundError",
                    "error_message": f"Script '{safe_name}' was not found in current workspace inputs/outputs.",
                    "script_name": safe_name,
                    "error_handling_policy": policy,
                },
                indent=2,
                ensure_ascii=False,
            )

        script_content = script_path.read_text(encoding="utf-8")
        preflight = _preflight_checks(script_content, strict_mode=strict_mode)
        thread_ctx = _get_thread_context()
        normalized_script_hash = hashlib.sha256(_normalize_whitespace(script_content).encode("utf-8")).hexdigest()

        if (
            thread_ctx.get("__ntl_last_executed_success_hash") == normalized_script_hash
            and thread_ctx.get("__ntl_last_executed_success_script_path") == str(script_path)
        ):
            # Avoid repeated execution of unchanged successful scripts.
            result = {
                "status": "success",
                "stdout": "[dedupe] Identical script already executed successfully in this thread. Skipped re-execution.",
                "script_name": safe_name,
                "script_path": str(script_path),
                "already_executed": True,
                "execution_skipped": True,
                "code": script_content,
                "preflight": preflight,
                "next_action_hint": "transfer_back_to_ntl_engineer",
            }
            _append_run_history(
                {
                    "timestamp": _timestamp(),
                    "tool": "execute_geospatial_script_tool",
                    "status": "success_cached",
                    "script_name": safe_name,
                    "script_path": str(script_path),
                    "thread_id": current_thread_id.get(),
                }
            )
            return json.dumps(result, indent=2, ensure_ascii=False)

        if preflight["blocking_errors"]:
            policy = _build_error_handling_policy(
                "PreflightError",
                preflight["blocking_errors"][0],
                preflight=preflight,
                fix_suggestions=preflight["recommendations"],
            )
            result = {
                "status": "fail",
                "stdout": "",
                "error_type": "PreflightError",
                "error_message": preflight["blocking_errors"][0],
                "traceback": None,
                "script_name": safe_name,
                "script_path": str(script_path),
                "code": script_content,
                "preflight": preflight,
                "fix_suggestions": preflight["recommendations"],
                "error_handling_policy": policy,
                "execution_skipped": True,
            }
            _append_run_history(
                {
                    "timestamp": _timestamp(),
                    "tool": "execute_geospatial_script_tool",
                    "status": "fail",
                    "reason": "preflight",
                    "script_name": safe_name,
                    "script_path": str(script_path),
                    "thread_id": current_thread_id.get(),
                }
            )
            return json.dumps(result, indent=2, ensure_ascii=False)

        ok, logs, etype, emsg, tb = _execute_code(script_content)
        if ok:
            thread_ctx["__ntl_last_executed_success_hash"] = normalized_script_hash
            thread_ctx["__ntl_last_executed_success_script_name"] = safe_name
            thread_ctx["__ntl_last_executed_success_script_path"] = str(script_path)
            fail_counts = thread_ctx.setdefault("__ntl_execute_failure_signature_counts", {})
            for sig in list(fail_counts.keys()):
                if sig.startswith(f"{normalized_script_hash}:"):
                    fail_counts.pop(sig, None)
            archive_info = _archive_success_script(
                script_content,
                source_tool="execute_geospatial_script_tool",
                script_name=safe_name,
                script_path=str(script_path),
                stdout=logs,
            )
            result = {
                "status": "success",
                "stdout": logs,
                "script_name": safe_name,
                "script_path": str(script_path),
                "code_guide_archive": archive_info,
                "code": script_content,
                "preflight": preflight,
                "execution_skipped": False,
            }
            _append_run_history(
                {
                    "timestamp": _timestamp(),
                    "tool": "execute_geospatial_script_tool",
                    "status": "success",
                    "script_name": safe_name,
                    "script_path": str(script_path),
                    "code_guide_archive": archive_info,
                    "thread_id": current_thread_id.get(),
                }
            )
            return json.dumps(result, indent=2, ensure_ascii=False)

        fix_suggestions = _derive_fix_suggestions(etype, emsg) + preflight["recommendations"]
        failure_signature = (
            f"{normalized_script_hash}:{etype or 'UnknownError'}:{_normalize_whitespace(emsg or '')[:180]}"
        )
        fail_counts = thread_ctx.setdefault("__ntl_execute_failure_signature_counts", {})
        repeated_failure_count = int(fail_counts.get(failure_signature, 0)) + 1
        fail_counts[failure_signature] = repeated_failure_count
        policy = _build_error_handling_policy(
            etype,
            emsg,
            preflight=preflight,
            fix_suggestions=fix_suggestions,
        )
        if repeated_failure_count >= 2 and policy.get("severity") == "simple":
            policy = dict(policy)
            policy.update(
                {
                    "severity": "hard",
                    "should_handoff_to_engineer": True,
                    "max_self_retries": 0,
                    "recommendation": "handoff_to_engineer_with_context",
                    "reason": (
                        f"Repeated identical execution failure detected ({repeated_failure_count} times). "
                        "Escalate to NTL_Engineer instead of continued self-debug."
                    ),
                }
            )
        result = {
            "status": "fail",
            "stdout": logs,
            "error_type": etype,
            "error_message": emsg,
            "traceback": tb,
            "script_name": safe_name,
            "script_path": str(script_path),
            "code": script_content,
            "preflight": preflight,
            "fix_suggestions": fix_suggestions,
            "error_handling_policy": policy,
            "repeated_failure_signature_count": repeated_failure_count,
            "execution_skipped": False,
        }
        _append_run_history(
            {
                "timestamp": _timestamp(),
                "tool": "execute_geospatial_script_tool",
                "status": "fail",
                "script_name": safe_name,
                "script_path": str(script_path),
                "thread_id": current_thread_id.get(),
                "error_type": etype,
            }
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    finally:
        if token is not None:
            current_thread_id.reset(token)


GeoCode_COT_Validation_tool = StructuredTool.from_function(
    GEE_GeoCode_COT_Validation,
    name="GeoCode_COT_Validation_tool",
    description=(
        "Enhanced Geo-CodeCoT validator for geospatial Python. Performs preflight static checks "
        "(syntax, path protocol, GEE initialization, dataset/band and CRS risk checks), then executes "
        "one minimal code block and returns structured JSON with pass/fail, logs, traceback, and fix suggestions."
    ),
    args_schema=GeoCodeCOTBlockInput,
)


final_geospatial_code_execution_tool = StructuredTool.from_function(
    final_geospatial_code_execution,
    name="final_geospatial_code_execution_tool",
    description=(
        "Execute final geospatial Python workflow after Geo-CodeCoT validation. Includes the same preflight "
        "checks and returns structured JSON with success/failure, logs, and remediation suggestions."
    ),
    args_schema=FinalCodeInput,
)


save_geospatial_script_tool = StructuredTool.from_function(
    save_geospatial_script,
    name="save_geospatial_script_tool",
    description=(
        "Persist Python geospatial code to a thread-scoped .py file under workspace outputs, "
        "and return script metadata for later execution/auditing."
    ),
    args_schema=SaveScriptInput,
)


execute_geospatial_script_tool = StructuredTool.from_function(
    execute_geospatial_script,
    name="execute_geospatial_script_tool",
    description=(
        "Execute a previously saved .py geospatial script by filename. "
        "Returns structured JSON with status, logs, script metadata, and traceback when failed."
    ),
    args_schema=ExecuteScriptInput,
)
