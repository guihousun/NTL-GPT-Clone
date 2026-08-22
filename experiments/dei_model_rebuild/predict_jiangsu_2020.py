"""Generate fitted 2020 DEI values for the 13 Jiangsu prefecture-level cities."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from build_retrained_artifact import (
    DEFAULT_MATCHED,
    DEFAULT_OUTPUT as DEFAULT_ARTIFACT,
    ArtifactBuildError,
    predict_artifact,
    sha256_file,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_PREDICTIONS = ROOT / "results" / "jiangsu_2020_predictions_longntl.csv"
JIANGSU_13 = (
    "南京市",
    "无锡市",
    "徐州市",
    "常州市",
    "苏州市",
    "南通市",
    "连云港市",
    "淮安市",
    "盐城市",
    "扬州市",
    "镇江市",
    "泰州市",
    "宿迁市",
)


NTL_SCRIPT_CONTRACT = {
    "schema": "ntl.script.contract.v2",
    "objective": (
        "Generate the 13 Jiangsu 2020 fitted values from the non-deployed "
        "LongNTL retrained candidate and label them as in-sample, not external validation."
    ),
    "input_manifest": [
        {"kind": "candidate_model_json", "path": str(DEFAULT_ARTIFACT), "required": True},
        {"kind": "matched_city_year_csv", "path": str(DEFAULT_MATCHED), "required": True},
    ],
    "method_steps": [
        "load the 2020 selected model and matched training cohort",
        "require exactly all 13 Jiangsu prefecture-level cities",
        "calculate fitted DEI and observed-minus-predicted residual",
        "write a deterministic UTF-8-SIG CSV with explicit evaluation scope",
    ],
    "parameters": {"year": 2020, "cities": list(JIANGSU_13)},
    "output_manifest": [
        {"kind": "jiangsu_fitted_values_csv", "path": str(DEFAULT_PREDICTIONS), "required": True}
    ],
    "validation_checks": [
        "exactly 13 unique Jiangsu cities",
        "all rows originate in the matched 2020 training cohort",
        "artifact remains candidate-not-deployed",
        "residual equals observed DEI minus fitted DEI",
    ],
    "failure_gates": [
        "missing, duplicate, or extra Jiangsu city",
        "training input SHA-256 mismatch",
        "unsupported model year or feature outside training range",
        "artifact marked as deployed or non-candidate",
    ],
    "execution": {
        "mode": "local",
        "timeout_seconds": 60,
        "overwrite_policy": "explicit deterministic output path only",
        "network_scope": [],
        "test_strategy": "unit test city coverage, arithmetic, provenance, and deterministic bytes",
    },
}


FIELDS = (
    "city",
    "year",
    "tntl",
    "observed_dei",
    "predicted_dei",
    "residual_observed_minus_predicted",
    "model_type",
    "evaluation_scope",
    "artifact_status",
    "training_input_sha256",
)


def _load_artifact(path: Path) -> dict[str, Any]:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactBuildError(f"cannot read candidate artifact {path}: {exc}") from exc
    if artifact.get("artifact_type") != "retrained":
        raise ArtifactBuildError("artifact_type must be retrained")
    if artifact.get("status") != "candidate-not-deployed":
        raise ArtifactBuildError("artifact must remain candidate-not-deployed")
    if artifact.get("deployment", {}).get("deployed") is not False:
        raise ArtifactBuildError("deployed artifacts are not accepted by this candidate script")
    return artifact


def generate_rows(artifact_path: Path, matched_path: Path) -> list[dict[str, Any]]:
    artifact = _load_artifact(artifact_path)
    expected_sha = artifact["inputs"]["matched_training_csv"]["sha256"]
    actual_sha = sha256_file(matched_path)
    if actual_sha != expected_sha:
        raise ArtifactBuildError(
            f"training input SHA-256 mismatch: expected {expected_sha}, got {actual_sha}"
        )

    source: dict[str, tuple[float, float]] = {}
    with matched_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            if row.get("year") != "2020" or row.get("city") not in JIANGSU_13:
                continue
            city = str(row["city"])
            if city in source:
                raise ArtifactBuildError(f"duplicate 2020 Jiangsu city: {city}")
            source[city] = (float(row["dei"]), float(row["tntl"]))
    missing = [city for city in JIANGSU_13 if city not in source]
    extra = sorted(set(source) - set(JIANGSU_13))
    if missing or extra or len(source) != 13:
        raise ArtifactBuildError(
            f"2020 Jiangsu cohort mismatch; missing={missing}, extra={extra}"
        )

    model = artifact["models"]["2020"]
    rows: list[dict[str, Any]] = []
    for city in JIANGSU_13:
        observed, tntl = source[city]
        predicted = predict_artifact(artifact, 2020, tntl)
        rows.append(
            {
                "city": city,
                "year": "2020",
                "tntl": f"{tntl:.12f}",
                "observed_dei": f"{observed:.12f}",
                "predicted_dei": f"{predicted:.12f}",
                "residual_observed_minus_predicted": f"{observed - predicted:.12f}",
                "model_type": model["model_type"],
                "evaluation_scope": "in-sample fitted value; not external validation",
                "artifact_status": artifact["status"],
                "training_input_sha256": actual_sha,
            }
        )
    return rows


def _csv_text(rows: list[dict[str, Any]]) -> str:
    import io

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return "\ufeff" + stream.getvalue()


def write_predictions(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_csv_text(rows), encoding="utf-8", newline="")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--matched", type=Path, default=DEFAULT_MATCHED)
    parser.add_argument("--output", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    rows = generate_rows(args.artifact, args.matched)
    expected = _csv_text(rows)
    if args.check:
        if (
            not args.output.is_file()
            or args.output.read_bytes() != expected.encode("utf-8")
        ):
            raise ArtifactBuildError(f"prediction CSV is missing or stale: {args.output}")
    else:
        write_predictions(rows, args.output)
    print(
        json.dumps(
            {
                "status": "in-sample-fitted-values-only",
                "year": 2020,
                "rows": len(rows),
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
