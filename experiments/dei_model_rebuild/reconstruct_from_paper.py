"""Deterministically reconstruct Chen et al. (2022) DEI formula artifacts.

This script does not fit data.  It transcribes the rounded logarithmic
coefficients and paper-reported in-sample metrics from Figure 2 and Table 1.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any


NTL_SCRIPT_CONTRACT = {
    "schema": "ntl.script.contract.v2",
    "objective": "Reconstruct the published 2017-2020 DEI/TNTL formulas without fitting data.",
    "input_manifest": [
        {
            "kind": "embedded_paper_evidence",
            "path": "reconstruct_from_paper.py:PAPER_MODELS",
            "required": True,
        }
    ],
    "method_steps": [
        "build a transparent formula artifact from fixed paper evidence",
        "serialize deterministically or compare a candidate artifact",
    ],
    "parameters": {"supported_years": [2017, 2018, 2019, 2020]},
    "output_manifest": [
        {
            "kind": "json_or_validation_stdout",
            "path": "CLI --output path or --check result on stdout",
            "required": True,
        }
    ],
    "validation_checks": [
        "exact coefficient, sample-size, and paper-metric equality",
        "TNTL is finite and positive before prediction",
    ],
    "failure_gates": [
        "artifact differs from paper reconstruction",
        "unsupported year",
        "non-positive or non-finite TNTL",
    ],
    "execution": {
        "mode": "local",
        "timeout_seconds": 60,
        "overwrite_policy": "explicit --output path only",
        "network_scope": [],
        "test_strategy": "exact committed-JSON comparison and unit formula arithmetic",
    },
}


PAPER_MODELS: dict[str, dict[str, float | int | str | None | dict[str, Any]]] = {
    "2017": {
        "form": "a * ln(TNTL) + b",
        "formula": "DEI = 13.387 * ln(TNTL) - 91.838",
        "coefficient": 13.387,
        "intercept": -91.838,
        "sample_size": 100,
        "paper_metrics": {
            "r2": 0.64,
            "rmse": 7.47,
            "scope": "in_sample",
            "mae": None,
            "cross_validation": None,
        },
    },
    "2018": {
        "form": "a * ln(TNTL) + b",
        "formula": "DEI = 13.596 * ln(TNTL) - 94.755",
        "coefficient": 13.596,
        "intercept": -94.755,
        "sample_size": 113,
        "paper_metrics": {
            "r2": 0.65,
            "rmse": 6.9,
            "scope": "in_sample",
            "mae": None,
            "cross_validation": None,
        },
    },
    "2019": {
        "form": "a * ln(TNTL) + b",
        "formula": "DEI = 13.0006 * ln(TNTL) - 85.622",
        "coefficient": 13.0006,
        "intercept": -85.622,
        "sample_size": 148,
        "paper_metrics": {
            "r2": 0.72,
            "rmse": 6.65,
            "scope": "in_sample",
            "mae": None,
            "cross_validation": None,
        },
    },
    "2020": {
        "form": "a * ln(TNTL) + b",
        "formula": "DEI = 12.619 * ln(TNTL) - 81.687",
        "coefficient": 12.619,
        "intercept": -81.687,
        "sample_size": 242,
        "paper_metrics": {
            "r2": 0.7,
            "rmse": 6.73,
            "scope": "in_sample",
            "mae": None,
            "cross_validation": None,
        },
    },
}


def build_artifact() -> dict[str, Any]:
    """Return the complete transparent JSON artifact as plain Python data."""

    return {
        "schema_version": "ntl-gpt.dei.yearly-formula.v1",
        "artifact_id": "chen-2022-dei-tntl-log-reconstruction-v1",
        "artifact_type": "reconstructed-from-paper",
        "status": "formula-reconstruction-only",
        "source": {
            "citation": (
                "Chen et al. (2022), Computers, Environment and Urban "
                "Systems 92, 101749"
            ),
            "doi": "10.1016/j.compenvurbsys.2021.101749",
            "official_url": (
                "https://www.sciencedirect.com/science/article/pii/"
                "S0198971521001563"
            ),
            "zotero_parent_key": "CZLEZQI2",
            "zotero_attachment_key": "YJSPRSTG",
            "pdf_sha256": (
                "3D3C4381E69BFB3D7233445EF4EEE622A96789A3817AA20ED6FE37A81F2FC3DE"
            ),
            "coefficient_precision": "rounded as printed in Figure 2 of the paper",
        },
        "feature": {
            "name": "TNTL",
            "semantic_definition": (
                "sum of valid annual nighttime-light pixel intensities "
                "within one city boundary"
            ),
            "transform": "natural_log",
            "formula_variable": "TNTL",
            "required_domain": "finite TNTL > 0",
            "antl_is_accepted": False,
            "ntl_product": (
                "EOG/Colorado School of Mines SNPP-VIIRS Version 1 "
                "monthly vcm composites"
            ),
            "paper_temporal_composite": "pixelwise annual median of monthly images",
            "paper_spatial_resolution": "15 arc-seconds (approximately 500 m)",
            "paper_preprocessing_summary": [
                "remove values below 1",
                (
                    "use Beijing and Shanghai city-centre maxima as reference "
                    "caps for abnormal high values"
                ),
                (
                    "replace values above the cap elsewhere with the maximum "
                    "of the eight neighbouring pixels"
                ),
                (
                    "use the product's zeroed stray-light-contaminated "
                    "high-latitude summer pixels"
                ),
            ],
        },
        "models": copy.deepcopy(PAPER_MODELS),
        "selection_evidence": {
            "selected_form": "logarithmic",
            "paper_basis": (
                "lowest reported RMSE and a saturating relationship consistent "
                "with the high-DEI plateau; the quadratic form had a slightly "
                "higher R2"
            ),
            "metric_scope": "paper-reported in-sample fit only",
        },
        "unsupported_year_policy": "fail",
        "limitations": [
            "No legacy serialized model was recovered.",
            (
                "No matched city-year DEI, TNTL, and boundary training table "
                "was available for retraining."
            ),
            (
                "The paper does not report MAE, cross-validation, holdout "
                "validation, residuals, or full-precision coefficients."
            ),
            (
                "The paper does not identify the exact city-boundary source or "
                "version, projection, pixel-area weighting, or missing-month policy."
            ),
            (
                "The printed coefficients are rounded and therefore cannot "
                "reproduce an unavailable full-precision fitted model exactly."
            ),
            "ANTL is not interchangeable with TNTL.",
            "Predictions for years outside 2017-2020 are unsupported.",
        ],
    }


def predict(artifact: dict[str, Any], year: int, tntl: float) -> float:
    """Apply one supported paper formula with strict TNTL/year validation."""

    if not math.isfinite(tntl) or tntl <= 0:
        raise ValueError("TNTL must be finite and strictly positive")
    year_key = str(year)
    try:
        model = artifact["models"][year_key]
    except KeyError as exc:
        raise ValueError(f"unsupported model year: {year}") from exc
    return float(model["coefficient"]) * math.log(tntl) + float(
        model["intercept"]
    )


def canonical_text(artifact: dict[str, Any]) -> str:
    """Serialize the artifact in its committed, deterministic representation."""

    return json.dumps(artifact, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output", type=Path, help="write reconstructed JSON")
    action.add_argument("--check", type=Path, help="compare a JSON file to reconstruction")
    args = parser.parse_args()

    expected = build_artifact()
    if args.output:
        args.output.write_text(canonical_text(expected), encoding="utf-8")
        print(f"wrote reconstructed-from-paper artifact: {args.output}")
        return 0

    actual = json.loads(args.check.read_text(encoding="utf-8"))
    if actual != expected:
        print(f"FAIL: {args.check} differs from the deterministic reconstruction")
        return 1
    print(f"PASS: {args.check} matches the deterministic paper reconstruction")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
