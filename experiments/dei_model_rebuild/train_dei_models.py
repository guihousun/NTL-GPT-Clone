"""Fail-closed city DEI/TNTL retraining pipeline.

The pipeline intentionally refuses to train from a DEI-only workbook.  Every
observation must carry an explicit city, year, DEI label, same-year TNTL, DEI
source, boundary source, NTL product, and preprocessing identifier.

Only Python's standard library is required.  The four fitted candidate forms
are those compared by Chen et al. (2022):

* linear:      y = a*x + b
* logarithmic: y = a*ln(x) + b
* exponential: y = b*exp(a*x)
* quadratic:   y = a*x^2 + b*x + c

The exponential curve is fitted by deterministic one-dimensional least
squares in the original DEI scale.  For each trial slope, the optimal
multiplicative coefficient has a closed-form solution.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


REQUIRED_FIELDS = (
    "city",
    "year",
    "dei",
    "tntl",
    "dei_source",
    "boundary_source",
    "ntl_product",
    "preprocessing_id",
)
PROVENANCE_FIELDS = (
    "dei_source",
    "boundary_source",
    "ntl_product",
    "preprocessing_id",
)
PLACEHOLDER_VALUES = {"", "-", "na", "n/a", "none", "null", "tbd", "unknown"}
MODEL_NAMES = ("linear", "logarithmic", "exponential", "quadratic")


NTL_SCRIPT_CONTRACT = {
    "schema": "ntl.script.contract.v2",
    "objective": "Retrain annual city DEI models only from complete, source-traceable city-year DEI/TNTL rows.",
    "input_manifest": [
        {
            "kind": "matched_city_year_csv",
            "path": "CLI input_csv argument",
            "required": True,
        }
    ],
    "method_steps": [
        "apply a fail-closed integrity and provenance gate",
        "fit linear, logarithmic, exponential, and quadratic candidates per year",
        "calculate in-sample and deterministic five-fold out-of-fold metrics",
        "report the selected candidate without deploying it",
    ],
    "parameters": {
        "folds": 5,
        "default_seed": 202208,
        "default_selection_rule": "paper_logarithmic",
    },
    "output_manifest": [
        {
            "kind": "retraining_report_json",
            "path": "CLI --output path or stdout",
            "required": True,
        }
    ],
    "validation_checks": [
        "R2, MAE, and RMSE for every candidate",
        "five-fold out-of-fold R2, MAE, and RMSE",
        "unique city-year keys and complete provenance",
    ],
    "failure_gates": [
        "any missing required field",
        "ANTL supplied without TNTL",
        "non-positive or non-finite TNTL",
        "duplicate city-year row",
        "placeholder provenance",
        "fewer than ten observations in a year",
    ],
    "execution": {
        "mode": "local",
        "timeout_seconds": 300,
        "overwrite_policy": "explicit --output path only",
        "network_scope": [],
        "test_strategy": "failure-gate unit tests and complete synthetic four-model fit",
    },
}


class DataIntegrityError(ValueError):
    """Raised when candidate training data do not cross the integrity gate."""


class ModelFitError(ValueError):
    """Raised when one candidate model cannot be fitted to a valid cohort."""


@dataclass(frozen=True)
class Record:
    city: str
    year: int
    dei: float
    tntl: float
    dei_source: str
    boundary_source: str
    ntl_product: str
    preprocessing_id: str


def _is_placeholder(value: str) -> bool:
    return value.strip().casefold() in PLACEHOLDER_VALUES


def _parse_finite_float(value: str, field: str, row_number: int) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise DataIntegrityError(f"row {row_number}: {field} must be numeric") from exc
    if not math.isfinite(parsed):
        raise DataIntegrityError(f"row {row_number}: {field} must be finite")
    return parsed


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_and_validate(path: Path) -> list[Record]:
    """Load a CSV and apply the complete-data, provenance, and cohort gate."""

    errors: list[str] = []
    records: list[Record] = []
    seen: dict[tuple[str, int], int] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = tuple(reader.fieldnames or ())
        missing_fields = [field for field in REQUIRED_FIELDS if field not in fields]
        if missing_fields:
            if "tntl" in missing_fields and "antl" in fields:
                errors.append(
                    "missing required field 'tntl'; ANTL is present but is not "
                    "interchangeable with TNTL"
                )
                missing_fields.remove("tntl")
            if missing_fields:
                errors.append("missing required fields: " + ", ".join(missing_fields))
            raise DataIntegrityError("data integrity gate failed:\n- " + "\n- ".join(errors))

        for row_number, row in enumerate(reader, start=2):
            row_errors: list[str] = []
            city = (row.get("city") or "").strip()
            if _is_placeholder(city):
                row_errors.append(f"row {row_number}: city is missing")

            year: int | None = None
            raw_year = (row.get("year") or "").strip()
            try:
                year = int(raw_year)
            except ValueError:
                row_errors.append(f"row {row_number}: year must be an integer")
            if year is not None and not 1900 <= year <= 2100:
                row_errors.append(f"row {row_number}: year is outside 1900-2100")

            dei: float | None = None
            tntl: float | None = None
            try:
                dei = _parse_finite_float(row.get("dei") or "", "dei", row_number)
                if not 0 <= dei <= 100:
                    row_errors.append(f"row {row_number}: dei must be within 0-100")
            except DataIntegrityError as exc:
                row_errors.append(str(exc))
            try:
                tntl = _parse_finite_float(row.get("tntl") or "", "tntl", row_number)
                if tntl <= 0:
                    row_errors.append(
                        f"row {row_number}: tntl must be strictly positive for ln(TNTL)"
                    )
            except DataIntegrityError as exc:
                row_errors.append(str(exc))

            provenance: dict[str, str] = {}
            for field in PROVENANCE_FIELDS:
                value = (row.get(field) or "").strip()
                provenance[field] = value
                if _is_placeholder(value):
                    row_errors.append(
                        f"row {row_number}: {field} must contain explicit provenance"
                    )

            if not row_errors and year is not None and dei is not None and tntl is not None:
                key = (city.casefold(), year)
                if key in seen:
                    row_errors.append(
                        f"row {row_number}: duplicate (city, year); first seen at row {seen[key]}"
                    )
                else:
                    seen[key] = row_number

            if row_errors:
                errors.extend(row_errors)
                continue
            records.append(
                Record(
                    city=city,
                    year=year,
                    dei=dei,
                    tntl=tntl,
                    **provenance,
                )
            )

    if not records and not errors:
        errors.append("CSV contains no data rows")

    by_year: dict[int, list[Record]] = {}
    for record in records:
        by_year.setdefault(record.year, []).append(record)
    for year, cohort in sorted(by_year.items()):
        if len(cohort) < 10:
            errors.append(
                f"year {year}: {len(cohort)} observations; at least 10 are required "
                "for stable five-fold validation of all four candidates"
            )
        if len({row.tntl for row in cohort}) < 5:
            errors.append(f"year {year}: fewer than 5 distinct TNTL values")
        if len({row.dei for row in cohort}) < 2:
            errors.append(f"year {year}: DEI has no variation")

    if errors:
        raise DataIntegrityError("data integrity gate failed:\n- " + "\n- ".join(errors))
    return sorted(records, key=lambda item: (item.year, item.city.casefold()))


def _ols(x: Sequence[float], y: Sequence[float]) -> tuple[float, float]:
    if len(x) != len(y) or len(x) < 2:
        raise ModelFitError("OLS requires at least two paired observations")
    mean_x = math.fsum(x) / len(x)
    mean_y = math.fsum(y) / len(y)
    denominator = math.fsum((value - mean_x) ** 2 for value in x)
    if denominator <= 0:
        raise ModelFitError("predictor has no variation")
    slope = math.fsum(
        (x_value - mean_x) * (y_value - mean_y)
        for x_value, y_value in zip(x, y)
    ) / denominator
    intercept = mean_y - slope * mean_x
    return slope, intercept


def _solve_three(matrix: list[list[float]], vector: list[float]) -> list[float]:
    augmented = [row[:] + [value] for row, value in zip(matrix, vector)]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-14:
            raise ModelFitError("quadratic normal equations are singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(3):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                left - factor * right
                for left, right in zip(augmented[row], augmented[column])
            ]
    return [augmented[row][3] for row in range(3)]


def _fit_quadratic(x: Sequence[float], y: Sequence[float]) -> dict[str, float]:
    # Centre and scale before solving to avoid ill-conditioning from large TNTL.
    centre = math.fsum(x) / len(x)
    scale = max(abs(value - centre) for value in x)
    if scale <= 0:
        raise ModelFitError("TNTL has no variation")
    z = [(value - centre) / scale for value in x]
    n = float(len(z))
    s1 = math.fsum(z)
    s2 = math.fsum(value**2 for value in z)
    s3 = math.fsum(value**3 for value in z)
    s4 = math.fsum(value**4 for value in z)
    sy = math.fsum(y)
    szy = math.fsum(value * target for value, target in zip(z, y))
    sz2y = math.fsum(value**2 * target for value, target in zip(z, y))
    alpha, beta, gamma = _solve_three(
        [[s4, s3, s2], [s3, s2, s1], [s2, s1, n]],
        [sz2y, szy, sy],
    )
    # y = alpha*((x-centre)/scale)^2 + beta*((x-centre)/scale) + gamma
    a = alpha / (scale**2)
    b = beta / scale - 2 * alpha * centre / (scale**2)
    c = alpha * (centre**2) / (scale**2) - beta * centre / scale + gamma
    return {"a": a, "b": b, "c": c}


def _fit_exponential(x: Sequence[float], y: Sequence[float]) -> dict[str, float]:
    centre = math.fsum(x) / len(x)
    scale = max(abs(value - centre) for value in x)
    if scale <= 0:
        raise ModelFitError("TNTL has no variation")
    z = [(value - centre) / scale for value in x]

    def objective(alpha: float) -> tuple[float, float]:
        basis = [math.exp(max(-80.0, min(80.0, alpha * value))) for value in z]
        denominator = math.fsum(value * value for value in basis)
        coefficient = math.fsum(
            target * value for target, value in zip(y, basis)
        ) / denominator
        sse = math.fsum(
            (target - coefficient * value) ** 2
            for target, value in zip(y, basis)
        )
        return sse, coefficient

    # Golden-section search in a broad, stable standardized-slope interval.
    left, right = -40.0, 40.0
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    c = right - ratio * (right - left)
    d = left + ratio * (right - left)
    fc = objective(c)[0]
    fd = objective(d)[0]
    for _ in range(160):
        if fc <= fd:
            right, d, fd = d, c, fc
            c = right - ratio * (right - left)
            fc = objective(c)[0]
        else:
            left, c, fc = c, d, fd
            d = left + ratio * (right - left)
            fd = objective(d)[0]
    alpha = (left + right) / 2.0
    _, centred_b = objective(alpha)
    a = alpha / scale
    exponent = -a * centre
    if exponent < -700 or exponent > 700:
        raise ModelFitError("exponential coefficient conversion overflow")
    b = centred_b * math.exp(exponent)
    return {"a": a, "b": b}


def fit_model(name: str, rows: Sequence[Record]) -> dict[str, Any]:
    x = [row.tntl for row in rows]
    y = [row.dei for row in rows]
    if name == "linear":
        a, b = _ols(x, y)
        return {"form": "a * TNTL + b", "parameters": {"a": a, "b": b}}
    if name == "logarithmic":
        a, b = _ols([math.log(value) for value in x], y)
        return {"form": "a * ln(TNTL) + b", "parameters": {"a": a, "b": b}}
    if name == "exponential":
        return {
            "form": "b * exp(a * TNTL)",
            "parameters": _fit_exponential(x, y),
        }
    if name == "quadratic":
        return {
            "form": "a * TNTL^2 + b * TNTL + c",
            "parameters": _fit_quadratic(x, y),
        }
    raise ModelFitError(f"unknown candidate model: {name}")


def predict_model(model: dict[str, Any], tntl: float) -> float:
    parameters = model["parameters"]
    form = model["form"]
    if form == "a * TNTL + b":
        return parameters["a"] * tntl + parameters["b"]
    if form == "a * ln(TNTL) + b":
        return parameters["a"] * math.log(tntl) + parameters["b"]
    if form == "b * exp(a * TNTL)":
        exponent = parameters["a"] * tntl
        if exponent < -700 or exponent > 700:
            raise ModelFitError("exponential prediction overflow")
        return parameters["b"] * math.exp(exponent)
    if form == "a * TNTL^2 + b * TNTL + c":
        return (
            parameters["a"] * tntl**2
            + parameters["b"] * tntl
            + parameters["c"]
        )
    raise ModelFitError(f"unknown model form: {form}")


def regression_metrics(actual: Sequence[float], predicted: Sequence[float]) -> dict[str, float | None]:
    if len(actual) != len(predicted) or not actual:
        raise ValueError("metrics require non-empty paired values")
    errors = [want - got for want, got in zip(actual, predicted)]
    sse = math.fsum(error**2 for error in errors)
    mean = math.fsum(actual) / len(actual)
    total = math.fsum((value - mean) ** 2 for value in actual)
    return {
        "r2": None if total == 0 else 1.0 - sse / total,
        "mae": math.fsum(abs(error) for error in errors) / len(errors),
        "rmse": math.sqrt(sse / len(errors)),
    }


def five_fold_predictions(
    name: str, rows: Sequence[Record], *, seed: int
) -> tuple[list[float], list[float]]:
    if len(rows) < 5:
        raise ModelFitError("five-fold validation requires at least five rows")
    indices = list(range(len(rows)))
    random.Random(seed).shuffle(indices)
    actual: list[float] = []
    predicted: list[float] = []
    for fold in range(5):
        test_indices = set(indices[fold::5])
        train_rows = [row for index, row in enumerate(rows) if index not in test_indices]
        test_rows = [row for index, row in enumerate(rows) if index in test_indices]
        model = fit_model(name, train_rows)
        for row in test_rows:
            actual.append(row.dei)
            predicted.append(predict_model(model, row.tntl))
    return actual, predicted


def _provenance_summary(rows: Sequence[Record]) -> dict[str, list[str]]:
    return {
        field: sorted({getattr(row, field) for row in rows})
        for field in PROVENANCE_FIELDS
    }


def train(
    records: Sequence[Record],
    *,
    input_path: Path,
    selection_rule: str = "paper_logarithmic",
    seed: int = 202208,
) -> dict[str, Any]:
    by_year: dict[int, list[Record]] = {}
    for record in records:
        by_year.setdefault(record.year, []).append(record)

    yearly_results: dict[str, Any] = {}
    for year, cohort in sorted(by_year.items()):
        candidates: dict[str, Any] = {}
        for model_name in MODEL_NAMES:
            fitted = fit_model(model_name, cohort)
            in_sample = regression_metrics(
                [row.dei for row in cohort],
                [predict_model(fitted, row.tntl) for row in cohort],
            )
            cv_actual, cv_predicted = five_fold_predictions(
                model_name, cohort, seed=seed + year
            )
            candidates[model_name] = {
                **fitted,
                "in_sample_metrics": in_sample,
                "five_fold_out_of_fold_metrics": regression_metrics(
                    cv_actual, cv_predicted
                ),
            }
        if selection_rule == "paper_logarithmic":
            selected = "logarithmic"
            selection_basis = (
                "paper-compatible rule: logarithmic form retained; all four forms "
                "and five-fold metrics are reported"
            )
        else:
            selected = min(
                MODEL_NAMES,
                key=lambda name: candidates[name]["five_fold_out_of_fold_metrics"][
                    "rmse"
                ],
            )
            selection_basis = "lowest deterministic five-fold out-of-fold RMSE"
        yearly_results[str(year)] = {
            "sample_size": len(cohort),
            "cities": sorted(row.city for row in cohort),
            "provenance": _provenance_summary(cohort),
            "candidates": candidates,
            "selected_model": selected,
            "selection_basis": selection_basis,
        }

    return {
        "schema_version": "ntl-gpt.dei.retraining-report.v1",
        "artifact_type": "retrained",
        "data_integrity_gate": "passed",
        "input": {
            "path": str(input_path.resolve()),
            "sha256": sha256_file(input_path),
            "required_fields": list(REQUIRED_FIELDS),
            "row_count": len(records),
        },
        "selection_rule": selection_rule,
        "cross_validation": {
            "method": "deterministic shuffled five-fold out-of-fold prediction",
            "folds": 5,
            "seed": seed,
            "unit": "unique city-year row within each year",
        },
        "yearly_results": yearly_results,
        "warnings": [
            "Passing the structural gate does not independently prove that source labels, boundaries, or NTL preprocessing are scientifically correct.",
            "Do not deploy a retrained report until its source licenses and spatial/temporal matching have been manually audited.",
        ],
    }


def gate_summary(path: Path, records: Sequence[Record]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for record in records:
        counts[str(record.year)] = counts.get(str(record.year), 0) + 1
    return {
        "status": "passed",
        "classification": "eligible-for-retraining",
        "input_sha256": sha256_file(path),
        "row_count": len(records),
        "year_counts": counts,
        "required_fields": list(REQUIRED_FIELDS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--selection-rule",
        choices=("paper_logarithmic", "cv_rmse"),
        default="paper_logarithmic",
    )
    parser.add_argument("--seed", type=int, default=202208)
    args = parser.parse_args()
    try:
        records = load_and_validate(args.input_csv)
    except (OSError, DataIntegrityError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, indent=2))
        return 2

    if args.validate_only:
        print(json.dumps(gate_summary(args.input_csv, records), indent=2))
        return 0

    try:
        report = train(
            records,
            input_path=args.input_csv,
            selection_rule=args.selection_rule,
            seed=args.seed,
        )
    except (ModelFitError, ValueError, OverflowError) as exc:
        print(json.dumps({"status": "fit-failed", "error": str(exc)}, indent=2))
        return 3
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        print(f"wrote retraining report: {args.output}")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
