import os
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional
from langchain_core.tools import StructuredTool
from pydantic.v1 import BaseModel, Field
from storage_manager import storage_manager

# 1. 定义输入 Schema (保持不变)
class NTL_Estimate_Indicator_Input(BaseModel):
    tntl: float = Field(..., description="Total Nighttime Light (TNTL) value for the province (e.g., 12345.67)")
    indicator: str = Field(..., description="Indicator to estimate: 'GDP', 'electric power consumption', 'population', 'CO2 emissions' (case-insensitive)")
    province: Optional[str] = Field(None, description="Province/municipality name in Chinese (e.g., '上海市', '浙江省'). Required for CO2 estimation.")

# 2. 定义核心函数 (已修复 Warning)
def NTL_estimate_indicator_provincial(tntl: float, indicator: str, province: Optional[str] = None):
    """
    Estimate a provincial indicator from TNTL using the corresponding pre-trained model.
    """
    
    # --- 1. 路径配置 ---
    current_dir = Path(os.getcwd())
    # 尝试多种路径策略以适应不同的运行环境
    possible_paths = [
        # Preferred: unified shared base from storage manager (stable across E:/D: copies)
        storage_manager.shared_dir / "Model",
        # Backward-compatible fallbacks
        current_dir / "base_data" / "Model",
        Path(__file__).parent.parent / "base_data" / "Model",
    ]
    
    model_dir = None
    for p in possible_paths:
        if p.exists():
            model_dir = p
            break
            
    if model_dir is None:
        return {"error": True, "message": "Critical Error: Model directory not found. Please check project structure."}

    # --- 2. 指标映射 ---
    norm = str(indicator).strip().lower()
    alias_map = {
        'gdp': 'gdp', 'gross domestic product': 'gdp',
        'electric power consumption': 'electric_power_consumption', 'epc': 'electric_power_consumption',
        'population': 'population', 'population_count': 'population',
        'co2': 'co2', 'co2 emissions': 'co2', 'co2 emission': 'co2'
    }

    canonical = alias_map.get(norm)
    if canonical is None:
        return {"error": True, "message": f"Unsupported indicator '{indicator}'."}

    # --- 3. 模型加载 ---
    model_files = {
        'gdp': 'GDP_TNTL_best_model.pkl',
        'electric_power_consumption': 'EPC_TNTL_best_model.pkl',
        'population': 'population_TNTL_best_model.pkl',
        'co2': 'CO2_TNTL_best_model.pkl'
    }
    unit_map = {
        'gdp': '100 million CNY', 'electric_power_consumption': '10^8 kWh', 
        'population': '10^4 people', 'co2': '10^6 tons'
    }

    target_file = model_files.get(canonical)
    model_path = model_dir / target_file

    if canonical == 'co2' and (province is None or str(province).strip() == ''):
        return {"error": True, "message": "CO₂ model requires a 'province' argument."}

    try:
        with open(model_path, 'rb') as f:
            saved_obj = pickle.load(f)
    except Exception as e:
        return {"error": True, "message": f"Error loading model: {str(e)}"}

    # 提取模型
    model = saved_obj
    scaler = None
    poly = None
    if isinstance(saved_obj, dict):
        model = saved_obj.get('model') or saved_obj.get('pipeline') or saved_obj.get('estimator') or saved_obj.get('best_estimator_')
        scaler = saved_obj.get('scaler')
        poly = saved_obj.get('poly') or saved_obj.get('poly_transformer')

    # --- 4. 执行预测 (核心修改部分) ---
    try:
        predicted = None
        
        # 场景 A: CO2 模型
        if canonical == 'co2':
            # 构建 DataFrame 保证列顺序正确
            input_df = pd.DataFrame({'Province': [province], 'TNTL': [float(tntl)]})
            
            # [关键修改] 使用 .values 转换为 numpy array
            # 这样 sklearn 就不会抱怨 "X has feature names but StandardScaler was fitted without feature names"
            input_array = input_df.values 
            
            try:
                predicted = model.predict(input_array)[0]
            except Exception:
                # 备用：如果 pipeline 里有步骤强制依赖列名（极少见），则回退到 DataFrame
                predicted = model.predict(input_df)[0]

        # 场景 B: 其他数值模型
        else:
            X_num = np.array([[float(tntl)]], dtype=float)
            if scaler is not None:
                X_in = scaler.transform(X_num)
                if poly is not None:
                    X_in = poly.transform(X_in)
                predicted = model.predict(X_in)[0]
            else:
                # 兼容可能的 Pipeline 输入要求
                try:
                    predicted = model.predict(X_num)[0]
                except:
                    # 如果必须要有列名（虽然这与你的warning相反，但作为防御性编程）
                    predicted = model.predict(pd.DataFrame({'TNTL': [float(tntl)]}))[0]

    except Exception as e:
        return {"error": True, "message": f"Prediction failed: {str(e)}"}

    # --- 5. 返回结果 ---
    unit = unit_map.get(canonical, '')
    loc_str = f" in {province}" if province else ""
    
    return {
        "error": False,
        "indicator": canonical,
        "tntl": float(tntl),
        "province": province,
        "predicted_value": float(predicted),
        "unit": unit,
        "message": f"Estimated {canonical.upper()}{loc_str} based on TNTL {tntl:.2f}: {predicted:,.2f} {unit}"
    }

# 3. 注册工具
NTL_estimate_indicator_provincial_tool = StructuredTool.from_function(
    func=NTL_estimate_indicator_provincial,
    name="NTL_Estimate_Indicator_Provincial",
    description="Estimate provincial indicators (GDP, EPC, Population, CO2) using TNTL. For CO2, 'province' is required.",
    args_schema=NTL_Estimate_Indicator_Input,
)

import os
import pickle
import json
import math
from numbers import Integral
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic.v1 import BaseModel, Field, StrictInt

class DEI_Estimate_City_Input(BaseModel):
    tntl: float = Field(
        ...,
        description=(
            "City total nighttime light (TNTL), not average nighttime light (ANTL). "
            "TNTL must be finite and greater than zero."
        ),
    )
    year: StrictInt = Field(..., description="Model year. Availability is defined by the deployed JSON artifact.")

    class Config:
        extra = "forbid"


_DEI_SCHEMA_VERSION_V1 = "ntl-gpt.dei.yearly-formula.v1"
_DEI_SCHEMA_VERSION_V2 = "ntl-gpt.dei.yearly-formula.v2"
# Backward-compatible module constant used by the original transparent format.
_DEI_SCHEMA_VERSION = _DEI_SCHEMA_VERSION_V1
_DEI_ARTIFACT_TYPES = {
    "reconstructed-from-paper",
    "retrained",
    "recovered-original-model",
}
_DEI_V2_PARAMETER_KEYS = {
    "linear": frozenset({"a", "b"}),
    "logarithmic": frozenset({"a", "b"}),
    "quadratic": frozenset({"a", "b", "c"}),
    "exponential": frozenset({"a", "b"}),
}


def _dei_model_candidates():
    """Return deterministic locations for the transparent DEI formula artifact."""
    candidates = [
        storage_manager.shared_dir / "Model" / "yearly_dei_models.json",
        Path(__file__).resolve().parent.parent / "base_data" / "Model" / "yearly_dei_models.json",
        Path.cwd() / "base_data" / "Model" / "yearly_dei_models.json",
    ]
    unique = []
    seen = set()
    for candidate in candidates:
        resolved = str(Path(candidate).resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(Path(candidate))
    return unique


def _dei_finite_number(value, context):
    """Return a finite float while rejecting booleans and JSON strings."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must be a JSON number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{context} must be finite")
    return numeric


def _validate_dei_training_range(entry, context, *, required):
    """Validate an inclusive positive TNTL applicability domain."""
    raw_range = entry.get("training_tntl_range")
    if raw_range is None:
        if required:
            raise ValueError(f"{context} is retrained but training_tntl_range is missing")
        return None
    if not isinstance(raw_range, dict):
        raise ValueError(f"{context}.training_tntl_range must be an object")
    if set(raw_range) != {"min", "max"}:
        raise ValueError(
            f"{context}.training_tntl_range must contain exactly 'min' and 'max'"
        )
    minimum = _dei_finite_number(raw_range["min"], f"{context}.training_tntl_range.min")
    maximum = _dei_finite_number(raw_range["max"], f"{context}.training_tntl_range.max")
    if minimum <= 0 or maximum <= 0:
        raise ValueError(f"{context}.training_tntl_range bounds must be greater than zero")
    if minimum > maximum:
        raise ValueError(f"{context}.training_tntl_range.min must not exceed max")
    return minimum, maximum


def _validate_dei_year_key(raw_year, seen_years):
    """Require canonical four-digit JSON year keys and prevent aliases."""
    if not isinstance(raw_year, str) or len(raw_year) != 4 or not raw_year.isascii() or not raw_year.isdigit():
        raise ValueError(f"model key {raw_year!r} must be a canonical four-digit year string")
    year = int(raw_year)
    if str(year) != raw_year:
        raise ValueError(f"model key {raw_year!r} is not canonical")
    if year in seen_years:
        raise ValueError(f"duplicate model year {year}")
    seen_years.add(year)
    return year


def _validate_dei_v1_model(entry, context, *, require_range):
    if entry.get("form") != "a * ln(TNTL) + b":
        raise ValueError(f"{context} has an unsupported v1 form")
    for key in ("coefficient", "intercept"):
        _dei_finite_number(entry.get(key), f"{context}.{key}")
    _validate_dei_training_range(entry, context, required=require_range)


def _validate_dei_v2_model(entry, context, *, require_range):
    form = entry.get("form")
    if form not in _DEI_V2_PARAMETER_KEYS:
        raise ValueError(
            f"{context}.form must be one of {sorted(_DEI_V2_PARAMETER_KEYS)}"
        )
    parameters = entry.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError(f"{context}.parameters must be an object")
    expected_keys = _DEI_V2_PARAMETER_KEYS[form]
    if set(parameters) != expected_keys:
        raise ValueError(
            f"{context}.parameters for {form!r} must contain exactly {sorted(expected_keys)}"
        )
    for key in sorted(expected_keys):
        _dei_finite_number(parameters[key], f"{context}.parameters.{key}")
    training_range = _validate_dei_training_range(entry, context, required=require_range)

    if "model_type" in entry and entry["model_type"] != form:
        raise ValueError(f"{context}.model_type must equal form")
    expected_equations = {
        "linear": "a * TNTL + b",
        "logarithmic": "a * ln(TNTL) + b",
        "quadratic": "a * TNTL^2 + b * TNTL + c",
        "exponential": "b * exp(a * TNTL)",
    }
    if "equation" in entry and entry["equation"] != expected_equations[form]:
        raise ValueError(f"{context}.equation is inconsistent with form {form!r}")

    training = entry.get("training")
    if training is not None:
        if not isinstance(training, dict) or not isinstance(training.get("tntl_range"), dict):
            raise ValueError(f"{context}.training.tntl_range must be an object")
        audit_range = training["tntl_range"]
        if not {"min", "max"}.issubset(audit_range):
            raise ValueError(f"{context}.training.tntl_range must contain min and max")
        audit_min = _dei_finite_number(audit_range["min"], f"{context}.training.tntl_range.min")
        audit_max = _dei_finite_number(audit_range["max"], f"{context}.training.tntl_range.max")
        if training_range is None or (audit_min, audit_max) != training_range:
            raise ValueError(
                f"{context}.training.tntl_range must match training_tntl_range"
            )


def _dei_unique_json_object(pairs):
    """Reject duplicate JSON keys instead of silently keeping the last value."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _load_dei_formula_artifact(path):
    """Load and strictly validate a non-executable JSON coefficient artifact."""
    with Path(path).open("r", encoding="utf-8") as stream:
        artifact = json.load(stream, object_pairs_hook=_dei_unique_json_object)

    if not isinstance(artifact, dict):
        raise ValueError("artifact root must be a JSON object")
    schema_version = artifact.get("schema_version")
    if schema_version not in {_DEI_SCHEMA_VERSION_V1, _DEI_SCHEMA_VERSION_V2}:
        raise ValueError(
            f"unsupported schema_version {schema_version!r}; expected one of "
            f"{[_DEI_SCHEMA_VERSION_V1, _DEI_SCHEMA_VERSION_V2]}"
        )
    artifact_type = artifact.get("artifact_type")
    if artifact_type not in _DEI_ARTIFACT_TYPES:
        raise ValueError("artifact_type must state recovered, retrained, or reconstructed provenance")
    if schema_version == _DEI_SCHEMA_VERSION_V1:
        if not isinstance(artifact.get("source"), dict) or not artifact["source"]:
            raise ValueError("source provenance metadata is missing")
    else:
        if "artifact_id" in artifact and (
            not isinstance(artifact["artifact_id"], str) or not artifact["artifact_id"].strip()
        ):
            raise ValueError("v2 artifact_id, when present, must be a non-empty string")
        has_source = isinstance(artifact.get("source"), dict) and bool(artifact["source"])
        has_inputs = isinstance(artifact.get("inputs"), dict) and bool(artifact["inputs"])
        if not has_source and not has_inputs:
            raise ValueError("v2 source or inputs provenance metadata is missing")

    feature = artifact.get("feature")
    if not isinstance(feature, dict):
        raise ValueError("feature metadata is missing")
    if feature.get("name") != "TNTL":
        raise ValueError("feature.name must be 'TNTL'; ANTL artifacts are incompatible")
    if feature.get("antl_is_accepted") is True:
        raise ValueError("feature.antl_is_accepted must not be true; ANTL is incompatible")
    if schema_version == _DEI_SCHEMA_VERSION_V1:
        if feature.get("transform") != "natural_log":
            raise ValueError("v1 feature.transform must be 'natural_log'")
    elif "transform" in feature and feature["transform"] not in {
        "identity",
        "model-specific",
    }:
        raise ValueError("v2 feature.transform, when present, must be 'identity' or 'model-specific'")

    models = artifact.get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError("models must be a non-empty year-to-formula object")
    seen_years = set()
    require_range = artifact_type == "retrained"
    for raw_year, entry in models.items():
        _validate_dei_year_key(raw_year, seen_years)
        if not isinstance(entry, dict):
            raise ValueError(f"model entry {raw_year!r} must be an object")
        context = f"model entry {raw_year!r}"
        if schema_version == _DEI_SCHEMA_VERSION_V1:
            _validate_dei_v1_model(entry, context, require_range=require_range)
        else:
            _validate_dei_v2_model(entry, context, require_range=require_range)
    for field in ("warnings", "limitations"):
        values = artifact.get(field, [])
        if not isinstance(values, list) or not all(
            isinstance(item, str) for item in values
        ):
            raise ValueError(f"{field} must be a list of strings")
    status = artifact.get("status")
    if status is not None and (
        not isinstance(status, str) or not status.strip()
    ):
        raise ValueError("status, when present, must be a non-empty string")
    return artifact


def _dei_normalized_model_spec(artifact, entry):
    """Normalize v1 and v2 entries without executing serialized code."""
    if artifact["schema_version"] == _DEI_SCHEMA_VERSION_V1:
        return "logarithmic", {
            "a": float(entry["coefficient"]),
            "b": float(entry["intercept"]),
        }
    return entry["form"], {
        key: float(value) for key, value in entry["parameters"].items()
    }


def _evaluate_dei_formula(form, parameters, tntl):
    """Evaluate one of the four transparent, validated formula families."""
    if form == "linear":
        predicted = parameters["a"] * tntl + parameters["b"]
        display = "DEI = {a:g} * TNTL {sign} {b_abs:g}"
    elif form == "logarithmic":
        predicted = parameters["a"] * math.log(tntl) + parameters["b"]
        display = "DEI = {a:g} * ln(TNTL) {sign} {b_abs:g}"
    elif form == "quadratic":
        predicted = parameters["a"] * tntl**2 + parameters["b"] * tntl + parameters["c"]
        display = "DEI = {a:g} * TNTL^2 {b_sign} {b_abs:g} * TNTL {c_sign} {c_abs:g}"
    elif form == "exponential":
        predicted = parameters["b"] * math.exp(parameters["a"] * tntl)
        display = "DEI = {b:g} * exp({a:g} * TNTL)"
    else:  # Defensive; the artifact validator rejects this before evaluation.
        raise ValueError(f"unsupported DEI formula form {form!r}")

    if not math.isfinite(predicted):
        raise ValueError("formula produced a non-finite result")
    values = {
        "a": parameters.get("a", 0.0),
        "b": parameters.get("b", 0.0),
        "b_abs": abs(parameters.get("b", 0.0)),
        "sign": "+" if parameters.get("b", 0.0) >= 0 else "-",
        "b_sign": "+" if parameters.get("b", 0.0) >= 0 else "-",
        "c_abs": abs(parameters.get("c", 0.0)),
        "c_sign": "+" if parameters.get("c", 0.0) >= 0 else "-",
    }
    return float(predicted), display.format(**values)


def DEI_estimate_city(tntl: float, year: int):
    """Estimate city DEI from positive TNTL using the explicitly selected yearly formula."""
    try:
        if isinstance(tntl, bool):
            raise ValueError("boolean values are not valid TNTL")
        tntl_value = float(tntl)
    except (TypeError, ValueError) as exc:
        return {"error": True, "message": f"Invalid TNTL feature: {exc}."}
    if not math.isfinite(tntl_value) or tntl_value <= 0:
        return {
            "error": True,
            "message": "Invalid TNTL feature: 'tntl' must be finite and greater than zero.",
        }

    if isinstance(year, bool) or not isinstance(year, Integral):
        return {"error": True, "message": "Invalid model year: 'year' must be an integer."}
    selected_year = int(year)

    candidates = _dei_model_candidates()
    model_path = next((path for path in candidates if path.is_file()), None)
    if model_path is None:
        return {
            "error": True,
            "message": (
                "DEI model artifact is missing. Expected transparent JSON at one of: "
                + ", ".join(str(path) for path in candidates)
            ),
        }

    try:
        artifact = _load_dei_formula_artifact(model_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {
            "error": True,
            "message": f"DEI model artifact '{model_path}' is invalid or unreadable: {exc}",
        }

    yearly_models = {int(key): value for key, value in artifact["models"].items()}
    if selected_year not in yearly_models:
        available = sorted(yearly_models)
        return {
            "error": True,
            "message": f"Requested DEI model year {selected_year} is unavailable. Available years: {available}.",
        }

    entry = yearly_models[selected_year]
    training_range = _validate_dei_training_range(
        entry,
        f"model entry {selected_year!r}",
        required=artifact["artifact_type"] == "retrained",
    )
    if artifact["artifact_type"] == "retrained" and training_range is not None:
        minimum, maximum = training_range
        if tntl_value < minimum or tntl_value > maximum:
            return {
                "error": True,
                "message": (
                    f"TNTL {tntl_value:g} is outside the inclusive training TNTL range "
                    f"[{minimum:g}, {maximum:g}] for retrained DEI model year {selected_year}; "
                    "prediction refused."
                ),
                "year": selected_year,
                "tntl": tntl_value,
                "training_tntl_range": {"min": minimum, "max": maximum},
            }

    form, parameters = _dei_normalized_model_spec(artifact, entry)
    try:
        predicted, formula = _evaluate_dei_formula(form, parameters, tntl_value)
    except (ArithmeticError, ValueError) as exc:
        return {
            "error": True,
            "message": (
                f"DEI formula evaluation failed for year {selected_year} ({form}): {exc}."
            ),
        }

    warnings = list(artifact.get("warnings", []))
    warnings.extend(artifact.get("limitations", []))
    if artifact["artifact_type"] == "reconstructed-from-paper":
        warnings.extend(
            [
                "This is a paper-formula reconstruction from rounded printed coefficients, not a retrained model.",
                "Use only TNTL produced with a compatible product, year, city boundary, and preprocessing chain.",
            ]
        )
    if predicted < 0 or predicted > 100:
        warnings.append(
            "The un-clipped formula produced a value outside the DEI scale [0, 100]; verify TNTL compatibility."
        )

    return {
        "error": False,
        "tntl": tntl_value,
        "year": selected_year,
        "predicted_dei": float(predicted),
        "formula": formula,
        "formula_form": form,
        "model_provenance": artifact["artifact_type"],
        "artifact_status": artifact.get("status"),
        "model_schema_version": artifact["schema_version"],
        "model_path": str(model_path),
        "input_semantics": "city total nighttime light (TNTL); ANTL is incompatible",
        "training_tntl_range": (
            {"min": training_range[0], "max": training_range[1]}
            if training_range is not None
            else None
        ),
        "warnings": warnings,
        "message": (
            f"Estimated {selected_year} city DEI from TNTL {tntl_value:.4f}: {predicted:.4f}. "
            f"Artifact provenance: {artifact['artifact_type']}; "
            f"status: {artifact.get('status', 'unspecified')}."
        ),
    }

# Tool Definition
DEI_estimate_city_tool = StructuredTool.from_function(
    func=DEI_estimate_city,
    name="DEI_Estimate_City",
    description=(
        "Estimate city-level Digital Economy Indicator (DEI) from positive city TNTL. "
        "TNTL means total nighttime light; ANTL/mean radiance is not compatible. "
        "Both 'tntl' and an explicitly available model 'year' are required."
    ),
    args_schema=DEI_Estimate_City_Input,
)

# CO2 usually requires province argument (depending on how the model was trained)
# res_co2 = NTL_estimate_indicator_provincial(tntl=23456.78, indicator='CO2', province='上海市')
# print(res_co2)

# via tool object
# res_co2b = NTL_estimate_indicator_provincial_tool.func(tntl=23456.78, indicator='CO2', province='上海市')
# print(res_co2b)
