"""Build a transparent, non-deployed LongNTL DEI model candidate.

The builder consumes the already validated LongNTL matching and retraining
reports.  It deliberately recomputes each annual winner from the candidate
five-fold RMSE values instead of trusting a pre-filled ``selected_model``
field.  The resulting JSON is an auditable candidate, not a deployed runtime
model and not a reconstruction of Chen et al. (2022).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
DEFAULT_REPORT = ROOT / "results" / "longntl_retraining_cv_rmse.json"
DEFAULT_MATCHED = ROOT / "data" / "dei_longntl_matched_2017_2024.csv"
DEFAULT_MATCHING_MANIFEST = ROOT / "data" / "dei_longntl_matching_manifest.json"
DEFAULT_EXTRACTION_MANIFEST = (
    ROOT / "data" / "city_tntl_longntl_2017_2024_manifest.json"
)
DEFAULT_OUTPUT = ROOT / "results" / "yearly_dei_models_longntl_candidate.json"
DEFAULT_METRICS = ROOT / "results" / "longntl_model_metrics.csv"

MODEL_ORDER = ("linear", "logarithmic", "exponential", "quadratic")
MODEL_CONTRACT = {
    "linear": {
        "form": "a * TNTL + b",
        "required_parameters": ["a", "b"],
    },
    "logarithmic": {
        "form": "a * ln(TNTL) + b",
        "required_parameters": ["a", "b"],
    },
    "exponential": {
        "form": "b * exp(a * TNTL)",
        "required_parameters": ["a", "b"],
    },
    "quadratic": {
        "form": "a * TNTL^2 + b * TNTL + c",
        "required_parameters": ["a", "b", "c"],
    },
}


NTL_SCRIPT_CONTRACT = {
    "schema": "ntl.script.contract.v2",
    "objective": (
        "Build a transparent candidate artifact from the LongNTL matched table "
        "and select each annual model by minimum deterministic five-fold RMSE."
    ),
    "input_manifest": [
        {"kind": "cv_retraining_report", "path": str(DEFAULT_REPORT), "required": True},
        {"kind": "matched_city_year_csv", "path": str(DEFAULT_MATCHED), "required": True},
        {
            "kind": "matching_manifest",
            "path": str(DEFAULT_MATCHING_MANIFEST),
            "required": True,
        },
        {
            "kind": "extraction_manifest",
            "path": str(DEFAULT_EXTRACTION_MANIFEST),
            "required": True,
        },
    ],
    "method_steps": [
        "verify source hashes and row/year reconciliation",
        "recompute annual winners from candidate five-fold RMSE values",
        "record fitted parameters, training ranges, metrics, and limitations",
        "write deterministic candidate JSON and candidate-metric CSV",
    ],
    "parameters": {
        "selection_rule": "minimum five-fold out-of-fold RMSE",
        "model_order_for_exact_ties": list(MODEL_ORDER),
    },
    "output_manifest": [
        {"kind": "candidate_model_json", "path": str(DEFAULT_OUTPUT), "required": True},
        {"kind": "candidate_metrics_csv", "path": str(DEFAULT_METRICS), "required": True},
    ],
    "validation_checks": [
        "all four candidate families and required parameters are present",
        "selected family equals the minimum reported five-fold RMSE",
        "training counts and TNTL ranges reconcile to the matched CSV",
        "input SHA-256 values reconcile across source manifests",
        "artifact is explicitly candidate-not-deployed",
    ],
    "failure_gates": [
        "missing or hash-mismatched input",
        "non-cv_rmse source report",
        "missing annual cohort or candidate metrics",
        "non-finite parameters, TNTL, or metrics",
        "source selected_model disagrees with recomputed winner",
    ],
    "execution": {
        "mode": "local",
        "timeout_seconds": 120,
        "overwrite_policy": "explicit deterministic output paths only",
        "network_scope": [],
        "test_strategy": "unit and committed-artifact determinism tests",
    },
}


class ArtifactBuildError(ValueError):
    """Raised when the candidate cannot be built without ambiguity."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactBuildError(f"cannot read JSON input {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ArtifactBuildError(f"JSON input must contain an object: {path}")
    return value


def _finite_float(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ArtifactBuildError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ArtifactBuildError(f"{label} must be finite")
    return number


def _load_training_rows(path: Path) -> dict[str, list[dict[str, Any]]]:
    cohorts: dict[str, list[dict[str, Any]]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"city", "year", "dei", "tntl"}
        missing = sorted(required - set(reader.fieldnames or ()))
        if missing:
            raise ArtifactBuildError(
                "matched CSV is missing fields: " + ", ".join(missing)
            )
        for row_number, row in enumerate(reader, start=2):
            city = (row.get("city") or "").strip()
            year = (row.get("year") or "").strip()
            if not city or not year.isdigit():
                raise ArtifactBuildError(
                    f"matched CSV row {row_number} has invalid city/year"
                )
            dei = _finite_float(row.get("dei"), f"row {row_number} DEI")
            tntl = _finite_float(row.get("tntl"), f"row {row_number} TNTL")
            if tntl <= 0:
                raise ArtifactBuildError(
                    f"matched CSV row {row_number} TNTL must be positive"
                )
            cohorts.setdefault(year, []).append(
                {"city": city, "dei": dei, "tntl": tntl}
            )
    if not cohorts:
        raise ArtifactBuildError("matched CSV contains no rows")
    for year, rows in cohorts.items():
        names = [row["city"] for row in rows]
        if len(names) != len(set(names)):
            raise ArtifactBuildError(f"year {year} contains duplicate city rows")
    return cohorts


def evaluate_model(model_type: str, parameters: dict[str, Any], tntl: float) -> float:
    """Evaluate any of the four transparent candidate model families."""

    x = _finite_float(tntl, "TNTL")
    if x <= 0:
        raise ArtifactBuildError("TNTL must be finite and strictly positive")
    if model_type not in MODEL_CONTRACT:
        raise ArtifactBuildError(f"unsupported model type: {model_type}")
    required = MODEL_CONTRACT[model_type]["required_parameters"]
    if set(parameters) != set(required):
        raise ArtifactBuildError(
            f"{model_type} parameters must be exactly {', '.join(required)}"
        )
    values = {
        name: _finite_float(parameters[name], f"{model_type}.{name}")
        for name in required
    }
    if model_type == "linear":
        result = values["a"] * x + values["b"]
    elif model_type == "logarithmic":
        result = values["a"] * math.log(x) + values["b"]
    elif model_type == "exponential":
        exponent = values["a"] * x
        if not -700 <= exponent <= 700:
            raise ArtifactBuildError("exponential prediction would overflow")
        result = values["b"] * math.exp(exponent)
    else:
        result = values["a"] * x**2 + values["b"] * x + values["c"]
    if not math.isfinite(result):
        raise ArtifactBuildError("model prediction is non-finite")
    return result


def predict_artifact(
    artifact: dict[str, Any],
    year: int,
    tntl: float,
    *,
    allow_extrapolation: bool = False,
) -> float:
    models = artifact.get("models", {})
    model = models.get(str(year))
    if not isinstance(model, dict):
        raise ArtifactBuildError(f"unsupported model year: {year}")
    lower = _finite_float(model["training"]["tntl_range"]["min"], "TNTL min")
    upper = _finite_float(model["training"]["tntl_range"]["max"], "TNTL max")
    value = _finite_float(tntl, "TNTL")
    if not allow_extrapolation and not lower <= value <= upper:
        raise ArtifactBuildError(
            f"TNTL {value} is outside the {year} training range [{lower}, {upper}]"
        )
    return evaluate_model(model["model_type"], model["parameters"], value)


def _deduplicate(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _verified_input(
    label: str, path: Path, *, expected_sha256: str | None = None
) -> dict[str, Any]:
    if not path.is_file():
        raise ArtifactBuildError(f"missing {label}: {path}")
    actual = sha256_file(path)
    if expected_sha256 and actual != expected_sha256.upper():
        raise ArtifactBuildError(
            f"{label} SHA-256 mismatch: expected {expected_sha256}, got {actual}"
        )
    return {"path": str(path.resolve()), "sha256": actual}


def build_artifact(
    report_path: Path = DEFAULT_REPORT,
    matched_path: Path = DEFAULT_MATCHED,
    matching_manifest_path: Path = DEFAULT_MATCHING_MANIFEST,
    extraction_manifest_path: Path = DEFAULT_EXTRACTION_MANIFEST,
) -> dict[str, Any]:
    report = _load_json(report_path)
    matching = _load_json(matching_manifest_path)
    extraction = _load_json(extraction_manifest_path)
    cohorts = _load_training_rows(matched_path)

    if report.get("selection_rule") != "cv_rmse":
        raise ArtifactBuildError("source report must use selection_rule=cv_rmse")
    if report.get("data_integrity_gate") != "passed":
        raise ArtifactBuildError("source report did not pass its data-integrity gate")
    if report.get("artifact_type") != "retrained":
        raise ArtifactBuildError("source report is not classified as retrained")

    report_input = report.get("input", {})
    matching_training = matching.get("outputs", {}).get("training", {})
    matched_input = _verified_input(
        "matched training CSV",
        matched_path,
        expected_sha256=str(report_input.get("sha256", "")),
    )
    if matching_training.get("sha256") != matched_input["sha256"]:
        raise ArtifactBuildError(
            "matching manifest training SHA-256 does not match the training CSV"
        )
    if int(report_input.get("row_count", -1)) != sum(map(len, cohorts.values())):
        raise ArtifactBuildError("source report row count does not match the training CSV")
    if int(matching_training.get("row_count", -1)) != sum(map(len, cohorts.values())):
        raise ArtifactBuildError("matching manifest row count does not match the training CSV")

    matching_manifest_input = _verified_input(
        "matching manifest", matching_manifest_path
    )
    extraction_manifest_input = _verified_input(
        "extraction manifest", extraction_manifest_path
    )
    matching_tntl_manifest = matching.get("inputs", {}).get("tntl_manifest", {})
    if matching_tntl_manifest.get("sha256") != extraction_manifest_input["sha256"]:
        raise ArtifactBuildError(
            "matching manifest does not reference the supplied extraction manifest"
        )
    report_input_info = _verified_input("CV retraining report", report_path)

    yearly_results = report.get("yearly_results")
    if not isinstance(yearly_results, dict) or set(yearly_results) != set(cohorts):
        raise ArtifactBuildError("report years do not reconcile to matched CSV years")

    models: dict[str, Any] = {}
    for year in sorted(cohorts, key=int):
        rows = cohorts[year]
        source_year = yearly_results.get(year, {})
        candidates = source_year.get("candidates")
        if not isinstance(candidates, dict) or set(candidates) != set(MODEL_ORDER):
            raise ArtifactBuildError(f"year {year} must contain all four candidates")

        candidate_rmse: dict[str, float] = {}
        for model_type in MODEL_ORDER:
            candidate = candidates[model_type]
            if candidate.get("form") != MODEL_CONTRACT[model_type]["form"]:
                raise ArtifactBuildError(f"year {year} {model_type} form mismatch")
            parameters = candidate.get("parameters", {})
            evaluate_model(model_type, parameters, rows[0]["tntl"])
            for scope in ("in_sample_metrics", "five_fold_out_of_fold_metrics"):
                metrics = candidate.get(scope, {})
                if set(metrics) != {"r2", "mae", "rmse"}:
                    raise ArtifactBuildError(
                        f"year {year} {model_type} has incomplete {scope}"
                    )
                for metric, value in metrics.items():
                    _finite_float(value, f"year {year} {model_type} {scope}.{metric}")
            candidate_rmse[model_type] = _finite_float(
                candidate["five_fold_out_of_fold_metrics"]["rmse"],
                f"year {year} {model_type} CV RMSE",
            )

        winner = min(MODEL_ORDER, key=lambda name: candidate_rmse[name])
        if source_year.get("selected_model") != winner:
            raise ArtifactBuildError(
                f"year {year} source selected_model disagrees with recomputed CV winner"
            )
        if int(source_year.get("sample_size", -1)) != len(rows):
            raise ArtifactBuildError(f"year {year} sample size does not reconcile")

        selected = candidates[winner]
        tntl_values = [row["tntl"] for row in rows]
        models[year] = {
            "model_type": winner,
            "form": winner,
            "equation": selected["form"],
            "parameters": selected["parameters"],
            "training_tntl_range": {
                "min": min(tntl_values),
                "max": max(tntl_values),
            },
            "training": {
                "model_year_semantics": (
                    "H3C IndexYear is the DEI model year and is paired to the "
                    "same LongNTL calendar year by explicit user instruction"
                ),
                "sample_size": len(rows),
                "cities": sorted(row["city"] for row in rows),
                "tntl_range": {
                    "min": min(tntl_values),
                    "max": max(tntl_values),
                    "unit": "sum of positive LongNTL b1 pixel values within boundary",
                },
            },
            "metrics": {
                "in_sample": selected["in_sample_metrics"],
                "five_fold_out_of_fold": selected[
                    "five_fold_out_of_fold_metrics"
                ],
            },
            "selection": {
                "criterion": "minimum five-fold out-of-fold RMSE",
                "selected_cv_rmse": candidate_rmse[winner],
                "candidate_cv_rmse": {
                    name: candidate_rmse[name] for name in MODEL_ORDER
                },
                "tie_break_order": list(MODEL_ORDER),
            },
        }

    limitations = _deduplicate(
        [
            *(str(value) for value in extraction.get("limitations", [])),
            *(str(value) for value in matching.get("limitations", [])),
            "Runtime parser compatibility tested, but artifact not copied to base_data/Model.",
            "The selected model is evaluated in-sample and by deterministic five-fold row-level cross-validation; no independent external city holdout is available.",
            "The 2020 Jiangsu table contains fitted values for cities used in the 2020 training cohort, not external validation predictions.",
        ]
    )

    return {
        "schema_version": "ntl-gpt.dei.yearly-formula.v2",
        "artifact_id": "h3c-indexyear-longntl-cv-rmse-2017-2024-candidate-v1",
        "artifact_type": "retrained",
        "status": "candidate-not-deployed",
        "deployment": {
            "deployed": False,
            "runtime_model_path": None,
            "runtime_schema_compatibility_tested": True,
        },
        "target": {
            "name": "city digital economy index",
            "field": "DEI",
            "range": [0, 100],
            "year_semantics": (
                "User-confirmed H3C IndexYear is treated as the actual DEI model "
                "year and paired to the same LongNTL calendar year."
            ),
            "semantics_authority": "explicit user instruction on 2026-08-09",
        },
        "feature": {
            "name": "TNTL",
            "semantic_definition": (
                "sum of positive annual LongNTL b1 pixel values within the matched "
                "city boundary on the product's native nominal 500 m grid"
            ),
            "required_domain": "finite TNTL > 0",
            "antl_is_accepted": False,
            "dataset": extraction.get("dataset"),
            "preprocessing": extraction.get("preprocessing"),
            "boundary": extraction.get("boundary"),
            "paper_compatibility": (
                "not numerically interchangeable with the monthly-composite TNTL "
                "used by Chen et al. (2022)"
            ),
        },
        "inputs": {
            "matched_training_csv": {
                **matched_input,
                "row_count": sum(map(len, cohorts.values())),
            },
            "cv_retraining_report": report_input_info,
            "matching_manifest": matching_manifest_input,
            "extraction_manifest": extraction_manifest_input,
            "longntl_city_tntl_csv": matching.get("inputs", {}).get("tntl"),
            "dei_labels_csv": matching.get("inputs", {}).get("labels"),
        },
        "cross_validation": report.get("cross_validation"),
        "selection_rule": "minimum five-fold out-of-fold RMSE per model year",
        "model_contract": {
            "supported_model_types": MODEL_CONTRACT,
            "unsupported_year_behavior": "fail",
            "out_of_training_tntl_range_behavior": (
                "fail by default; explicit allow_extrapolation is required"
            ),
        },
        "models": models,
        "limitations": limitations,
    }


def metrics_rows(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    input_sha = artifact["inputs"]["matched_training_csv"]["sha256"]
    rows: list[dict[str, Any]] = []
    report = _load_json(Path(artifact["inputs"]["cv_retraining_report"]["path"]))
    for year in sorted(artifact["models"], key=int):
        model = artifact["models"][year]
        source_candidates = report["yearly_results"][year]["candidates"]
        for model_type in MODEL_ORDER:
            candidate = source_candidates[model_type]
            rows.append(
                {
                    "year": year,
                    "model_type": model_type,
                    "selected": str(model_type == model["model_type"]).lower(),
                    "sample_size": model["training"]["sample_size"],
                    "tntl_min": model["training"]["tntl_range"]["min"],
                    "tntl_max": model["training"]["tntl_range"]["max"],
                    "in_sample_r2": candidate["in_sample_metrics"]["r2"],
                    "in_sample_mae": candidate["in_sample_metrics"]["mae"],
                    "in_sample_rmse": candidate["in_sample_metrics"]["rmse"],
                    "cv_r2": candidate["five_fold_out_of_fold_metrics"]["r2"],
                    "cv_mae": candidate["five_fold_out_of_fold_metrics"]["mae"],
                    "cv_rmse": candidate["five_fold_out_of_fold_metrics"]["rmse"],
                    "training_input_sha256": input_sha,
                }
            )
    return rows


METRICS_FIELDS = (
    "year",
    "model_type",
    "selected",
    "sample_size",
    "tntl_min",
    "tntl_max",
    "in_sample_r2",
    "in_sample_mae",
    "in_sample_rmse",
    "cv_r2",
    "cv_mae",
    "cv_rmse",
    "training_input_sha256",
)


def _json_text(artifact: dict[str, Any]) -> str:
    return json.dumps(artifact, ensure_ascii=False, indent=2) + "\n"


def _metrics_text(rows: list[dict[str, Any]]) -> str:
    import io

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=METRICS_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return "\ufeff" + stream.getvalue()


def write_outputs(
    artifact: dict[str, Any], output_path: Path, metrics_path: Path
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_json_text(artifact), encoding="utf-8", newline="")
    metrics_path.write_text(
        _metrics_text(metrics_rows(artifact)), encoding="utf-8", newline=""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--matched", type=Path, default=DEFAULT_MATCHED)
    parser.add_argument(
        "--matching-manifest", type=Path, default=DEFAULT_MATCHING_MANIFEST
    )
    parser.add_argument(
        "--extraction-manifest", type=Path, default=DEFAULT_EXTRACTION_MANIFEST
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    artifact = build_artifact(
        args.report, args.matched, args.matching_manifest, args.extraction_manifest
    )
    expected_json = _json_text(artifact)
    expected_metrics = _metrics_text(metrics_rows(artifact))
    if args.check:
        problems: list[str] = []
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != expected_json:
            problems.append(f"candidate JSON is missing or stale: {args.output}")
        if (
            not args.metrics.is_file()
            or args.metrics.read_bytes() != expected_metrics.encode("utf-8")
        ):
            problems.append(f"metrics CSV is missing or stale: {args.metrics}")
        if problems:
            raise ArtifactBuildError("; ".join(problems))
    else:
        write_outputs(artifact, args.output, args.metrics)
    print(
        json.dumps(
            {
                "status": "candidate-not-deployed",
                "years": sorted(artifact["models"], key=int),
                "output": str(args.output.resolve()),
                "metrics": str(args.metrics.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
