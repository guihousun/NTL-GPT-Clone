"""Validate the DEI reconstructed-from-paper JSON artifact."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


NTL_SCRIPT_CONTRACT = {
    "schema": "ntl.script.contract.v2",
    "objective": "Validate schema, provenance, formulas, and arithmetic of the DEI paper reconstruction.",
    "input_manifest": [
        {
            "kind": "transparent_formula_json",
            "path": "CLI artifact argument",
            "required": True,
        }
    ],
    "method_steps": [
        "validate strict schema and source identity",
        "validate exact annual formulas and paper metric scope",
        "run a positive synthetic TNTL arithmetic smoke test",
    ],
    "parameters": {"default_synthetic_tntl": 100000.0},
    "output_manifest": [
        {
            "kind": "validation_json",
            "path": "stdout",
            "required": True,
        }
    ],
    "validation_checks": [
        "supported years are exactly 2017-2020",
        "feature is TNTL with natural-log transform",
        "MAE and cross-validation remain explicitly unavailable",
    ],
    "failure_gates": ["schema mismatch", "source mismatch", "formula or metric mismatch"],
    "execution": {
        "mode": "local",
        "timeout_seconds": 60,
        "overwrite_policy": "read-only validation",
        "network_scope": [],
        "test_strategy": "schema/source/formula assertions plus synthetic TNTL smoke test",
    },
}


EXPECTED_MODELS = {
    "2017": (13.387, -91.838, 100, 0.64, 7.47),
    "2018": (13.596, -94.755, 113, 0.65, 6.90),
    "2019": (13.0006, -85.622, 148, 0.72, 6.65),
    "2020": (12.619, -81.687, 242, 0.70, 6.73),
}


def validate(artifact: dict[str, Any]) -> list[str]:
    """Return all validation errors; an empty list means the artifact passes."""

    errors: list[str] = []
    if artifact.get("schema_version") != "ntl-gpt.dei.yearly-formula.v1":
        errors.append("schema_version must equal ntl-gpt.dei.yearly-formula.v1")
    if artifact.get("artifact_type") != "reconstructed-from-paper":
        errors.append("artifact_type must equal reconstructed-from-paper")
    source = artifact.get("source")
    if not isinstance(source, dict):
        errors.append("source must be an object")
        source = {}
    if source.get("doi") != "10.1016/j.compenvurbsys.2021.101749":
        errors.append("unexpected or missing DOI")
    if source.get("zotero_parent_key") != "CZLEZQI2":
        errors.append("unexpected or missing Zotero parent key")
    if source.get("zotero_attachment_key") != "YJSPRSTG":
        errors.append("unexpected or missing Zotero attachment key")
    if source.get("pdf_sha256") != (
        "3D3C4381E69BFB3D7233445EF4EEE622A96789A3817AA20ED6FE37A81F2FC3DE"
    ):
        errors.append("unexpected or missing source PDF SHA-256")

    feature = artifact.get("feature")
    if not isinstance(feature, dict):
        errors.append("feature must be an object")
        feature = {}
    if feature.get("name") != "TNTL":
        errors.append("feature.name must be TNTL")
    if feature.get("transform") != "natural_log":
        errors.append("transform must be natural_log")
    if feature.get("antl_is_accepted") is not False:
        errors.append("ANTL must be explicitly rejected")

    models = artifact.get("models")
    if not isinstance(models, dict):
        errors.append("models must be an object")
        models = {}
    if set(models) != set(EXPECTED_MODELS):
        errors.append("models must contain exactly 2017, 2018, 2019, and 2020")

    for year, expected in EXPECTED_MODELS.items():
        model = models.get(year)
        if not isinstance(model, dict):
            errors.append(f"{year}: model must be an object")
            continue
        coefficient, intercept, n, r2, rmse = expected
        if model.get("form") != "a * ln(TNTL) + b":
            errors.append(f"{year}: form must be a * ln(TNTL) + b")
        for key, want in (("coefficient", coefficient), ("intercept", intercept)):
            got = model.get(key)
            if not isinstance(got, (int, float)) or not math.isclose(
                float(got), want, rel_tol=0, abs_tol=1e-12
            ):
                errors.append(f"{year}: {key} differs from paper")
        if model.get("sample_size") != n:
            errors.append(f"{year}: sample_size differs from paper")
        metrics = model.get("paper_metrics")
        if not isinstance(metrics, dict):
            errors.append(f"{year}: paper_metrics must be an object")
            continue
        if metrics.get("r2") != r2 or metrics.get("rmse") != rmse:
            errors.append(f"{year}: paper R2/RMSE mismatch")
        if metrics.get("scope") != "in_sample":
            errors.append(f"{year}: paper metric scope must be in_sample")
        if metrics.get("mae") is not None:
            errors.append(f"{year}: MAE must be null because paper did not report it")
        if metrics.get("cross_validation") is not None:
            errors.append(
                f"{year}: cross_validation must be null because paper did not report it"
            )
    if artifact.get("unsupported_year_policy") != "fail":
        errors.append("unsupported_year_policy must equal fail")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument(
        "--tntl", type=float, default=100000.0, help="positive synthetic TNTL smoke test"
    )
    args = parser.parse_args()
    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    errors = validate(artifact)
    if errors:
        print(json.dumps({"status": "fail", "errors": errors}, indent=2))
        return 1

    predictions = {}
    for year, model in artifact["models"].items():
        predictions[year] = model["coefficient"] * math.log(args.tntl) + model[
            "intercept"
        ]
    print(
        json.dumps(
            {
                "status": "pass",
                "classification": artifact["artifact_type"],
                "supported_years": sorted(artifact["models"]),
                "synthetic_tntl": args.tntl,
                "synthetic_predictions": predictions,
                "claims_not_validated": [
                    "paper training rows",
                    "paper MAE",
                    "paper cross-validation",
                    "Jiangsu city predictions",
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
