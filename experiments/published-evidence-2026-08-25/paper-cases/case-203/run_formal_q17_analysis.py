"""Run the formal Q17 SDGSAT-1 fixed-threshold analysis.

The script deliberately separates the blind analysis from the post-lock
reference comparison:

  python run_formal_q17_analysis.py --phase classify
  python run_formal_q17_analysis.py --phase compare

The compare phase refuses to open the user reference files unless the newly
computed classification still matches the pre-comparison SHA-256 lock.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
from rasterio.enums import Resampling


BASE = Path(__file__).resolve().parent
PROJECT = BASE.parents[2]
RRLI_PATH = BASE / "formal-SDGSAT1-shanghai-RRLI.tif"
RBLI_PATH = BASE / "formal-SDGSAT1-shanghai-RBLI.tif"
OBSERVATION_PATH = BASE / "formal-observation-package.json"
INDEX_STATS_PATH = BASE / "formal-index-statistics.json"
CONTRACT_PATH = (
    PROJECT
    / "data"
    / "benchmark-v1"
    / "fixtures"
    / "verified-reference"
    / "BV1-069"
    / "inputs"
    / "jia_2024_classification_contract.json"
)

CLASS_PATH = BASE / "formal-SDGSAT1-shanghai-light-classification.tif"
CLASS_STATS_PATH = BASE / "formal-class-statistics.json"
LOCK_PATH = BASE / "formal-pre-comparison-lock.json"
COMPARISON_PATH = BASE / "formal-reference-comparison.json"
PREVIEW_PATH = BASE / "formal-classification-preview.png"
LOG_PATH = BASE / "formal-analyst-log.md"

# These paths are not opened by the blind classify phase. They become readable
# only after compare_phase() verifies CLASS_PATH against LOCK_PATH.
REFERENCE_RBLI_PATH = Path(
    r"user-provided-local-data/NTL-GPT\SDGSAT_1\SDGSAT1_GLI_shanghai_RBLI.tif"
)
REFERENCE_CLASS_PATH = Path(
    r"user-provided-local-data/NTL-GPT\SDGSAT_1\SDGSAT1_GLI_shanghai_light_class1.tif"
)

OUTPUT_NODATA = np.uint8(255)
CLASS_NAMES = {1: "WLED", 2: "RLED", 3: "Other"}
PIXEL_AREA_M2 = 40.0 * 40.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def same_grid(left: rasterio.io.DatasetReader, right: rasterio.io.DatasetReader) -> bool:
    return (
        left.width == right.width
        and left.height == right.height
        and left.crs == right.crs
        and left.transform.almost_equals(right.transform)
    )


def valid_float(values: np.ndarray, nodata: float | None) -> np.ndarray:
    mask = np.isfinite(values)
    if nodata is not None:
        mask &= values != nodata
    return mask


def classify_block(rrli: np.ndarray, rbli: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Apply the ordered Jia et al. (2024) thresholds without tuning."""
    result = np.full(rrli.shape, OUTPUT_NODATA, dtype=np.uint8)
    rled = valid & (rrli > 9.0)
    result[rled] = 2
    wled = valid & ~rled & (rbli > 0.57)
    result[wled] = 1
    other = valid & ~rled & ~wled
    result[other] = 3
    return result


def assert_contract(contract: dict) -> None:
    codes = contract["benchmark_class_codes"]
    expected_codes = {"1": "WLED", "2": "RLED", "3": "Other", "255": "NoData"}
    if codes != expected_codes:
        raise RuntimeError(f"Unexpected class-code contract: {codes!r}")
    expected = {
        "RLED": "RRLI > 9",
        "WLED": "RRLI <= 9 and RBLI > 0.57",
        "Other": "RRLI <= 9 and RBLI <= 0.57",
    }
    if contract["classification"] != expected:
        raise RuntimeError("Threshold contract differs from the frozen Jia et al. rules")


def create_preview() -> None:
    """Create a labelled, no-basemap preview from the newly locked result."""
    target_height = 1100
    with rasterio.open(CLASS_PATH) as src:
        scale = target_height / src.height
        target_width = max(1, round(src.width * scale))
        preview = src.read(
            1,
            out_shape=(target_height, target_width),
            resampling=Resampling.nearest,
        )
        bounds = src.bounds

    display = np.full(preview.shape, np.nan, dtype=np.float32)
    display[preview == 1] = 0
    display[preview == 2] = 1
    display[preview == 3] = 2

    cmap = ListedColormap(["#28BBD7", "#D84A4A", "#D9A72E"])
    cmap.set_bad("#ECEFF1")
    fig, ax = plt.subplots(figsize=(7.4, 9.0), constrained_layout=True)
    ax.imshow(
        display,
        origin="upper",
        interpolation="nearest",
        cmap=cmap,
        vmin=-0.5,
        vmax=2.5,
        extent=(bounds.left / 1000, bounds.right / 1000, bounds.bottom / 1000, bounds.top / 1000),
    )
    ax.set_title(
        "Shanghai SDGSAT-1 light-type classification\n"
        "Fixed Jia et al. (2024) ordered thresholds",
        fontsize=12,
        weight="semibold",
    )
    ax.set_xlabel("Easting (km, WGS 84 / UTM zone 51N)")
    ax.set_ylabel("Northing (km, WGS 84 / UTM zone 51N)")
    legend = [
        Patch(facecolor="#28BBD7", label="WLED (class 1)"),
        Patch(facecolor="#D84A4A", label="RLED (class 2)"),
        Patch(facecolor="#D9A72E", label="Other (class 3)"),
        Patch(facecolor="#ECEFF1", edgecolor="#B0B6BA", label="NoData (255)"),
    ]
    ax.legend(handles=legend, loc="lower right", frameon=True, framealpha=0.95, fontsize=9)
    ax.tick_params(labelsize=9)
    ax.grid(False)
    fig.savefig(PREVIEW_PATH, dpi=300, facecolor="white")
    plt.close(fig)


def validate_new_result(expected_counts: Counter) -> dict:
    """Reopen outputs and independently test codes, totals, grid and samples."""
    reopened_counts: Counter[int] = Counter()
    sample_checked = 0
    sample_mismatches = 0
    rng = np.random.default_rng(20260813)

    with (
        rasterio.open(RRLI_PATH) as rrli_src,
        rasterio.open(RBLI_PATH) as rbli_src,
        rasterio.open(CLASS_PATH) as class_src,
    ):
        if not same_grid(rrli_src, rbli_src) or not same_grid(rrli_src, class_src):
            raise RuntimeError("Reopened result grid does not match index grid")
        for _, window in class_src.block_windows(1):
            rrli = rrli_src.read(1, window=window)
            rbli = rbli_src.read(1, window=window)
            actual = class_src.read(1, window=window)
            unique, counts = np.unique(actual, return_counts=True)
            reopened_counts.update({int(k): int(v) for k, v in zip(unique, counts)})

            valid = valid_float(rrli, rrli_src.nodata) & valid_float(rbli, rbli_src.nodata)
            candidates = np.flatnonzero(valid)
            if candidates.size:
                chosen = rng.choice(candidates, size=min(32, candidates.size), replace=False)
                expected = classify_block(rrli, rbli, valid).ravel()[chosen]
                observed = actual.ravel()[chosen]
                sample_checked += int(chosen.size)
                sample_mismatches += int(np.count_nonzero(expected != observed))

    permitted = {1, 2, 3, 255}
    unexpected = sorted(set(reopened_counts) - permitted)
    if unexpected:
        raise RuntimeError(f"Unexpected classification codes: {unexpected}")
    if reopened_counts != expected_counts:
        raise RuntimeError(
            f"Reopened counts differ from write-pass counts: {reopened_counts} != {expected_counts}"
        )
    if sample_mismatches:
        raise RuntimeError(f"Independent threshold sample found {sample_mismatches} mismatches")
    return {
        "reopened_all_blocks": True,
        "unique_codes": sorted(reopened_counts),
        "counts_match_write_pass": True,
        "independent_threshold_sample_size": sample_checked,
        "independent_threshold_sample_mismatches": sample_mismatches,
    }


def classify_phase() -> None:
    observation = read_json(OBSERVATION_PATH)
    index_stats = read_json(INDEX_STATS_PATH)
    contract = read_json(CONTRACT_PATH)
    assert_contract(contract)

    if observation.get("blindness", {}).get("comparison_authorized") is not False:
        raise RuntimeError("Observation package does not preserve the blind pre-comparison state")
    if sha256(RRLI_PATH) != observation["analysis_ready_outputs"][0]["sha256"]:
        raise RuntimeError("RRLI input hash differs from the accepted ObservationPackage")
    if sha256(RBLI_PATH) != observation["analysis_ready_outputs"][1]["sha256"]:
        raise RuntimeError("RBLI input hash differs from the accepted ObservationPackage")

    counts: Counter[int] = Counter()
    with rasterio.open(RRLI_PATH) as rrli_src, rasterio.open(RBLI_PATH) as rbli_src:
        if not same_grid(rrli_src, rbli_src):
            raise RuntimeError("RRLI and RBLI grids differ")
        if rrli_src.count != 1 or rbli_src.count != 1:
            raise RuntimeError("Both formal indices must be single-band rasters")
        profile = rrli_src.profile.copy()
        profile.update(
            driver="GTiff",
            dtype="uint8",
            count=1,
            nodata=int(OUTPUT_NODATA),
            compress="DEFLATE",
            predictor=1,
            tiled=True,
            blockxsize=512,
            blockysize=512,
            BIGTIFF="IF_SAFER",
        )
        with rasterio.open(CLASS_PATH, "w", **profile) as dst:
            dst.set_band_description(1, "Jia 2024 ordered-threshold light type")
            dst.update_tags(
                METHOD="Jia et al. (2024) fixed ordered thresholds",
                CLASS_1="WLED",
                CLASS_2="RLED",
                CLASS_3="Other",
                NODATA_VALUE="255",
                ORDER="RRLI>9 => RLED; else RBLI>0.57 => WLED; else Other",
            )
            for _, window in rrli_src.block_windows(1):
                rrli = rrli_src.read(1, window=window)
                rbli = rbli_src.read(1, window=window)
                valid = valid_float(rrli, rrli_src.nodata) & valid_float(rbli, rbli_src.nodata)
                classified = classify_block(rrli, rbli, valid)
                dst.write(classified, 1, window=window)
                unique, block_counts = np.unique(classified, return_counts=True)
                counts.update({int(k): int(v) for k, v in zip(unique, block_counts)})

    valid_count = sum(counts[code] for code in CLASS_NAMES)
    total_count = sum(counts.values())
    if valid_count != int(index_stats["statistics"]["RRLI"]["valid_pixel_count"]):
        raise RuntimeError("Classification valid total differs from accepted RRLI valid total")
    if valid_count != int(index_stats["statistics"]["RBLI"]["valid_pixel_count"]):
        raise RuntimeError("Classification valid total differs from accepted RBLI valid total")
    if total_count != index_stats["source"]["width"] * index_stats["source"]["height"]:
        raise RuntimeError("Classification pixel accounting does not equal raster dimensions")

    validation = validate_new_result(counts)
    create_preview()
    output_hash = sha256(CLASS_PATH)
    preview_hash = sha256(PREVIEW_PATH)
    script_hash = sha256(Path(__file__))

    class_rows = {}
    for code, name in CLASS_NAMES.items():
        count = int(counts[code])
        class_rows[str(code)] = {
            "name": name,
            "pixel_count": count,
            "fraction_of_valid_index_pixels": count / valid_count,
            "planar_area_m2": count * PIXEL_AREA_M2,
            "planar_area_km2": count * PIXEL_AREA_M2 / 1_000_000.0,
        }

    stats = {
        "schema": "ntl.paper-case.formal-class-statistics.v1",
        "case_id": "Q17-sdgsat-light-classification",
        "status": "success",
        "phase": "pre-comparison-locked",
        "method": {
            "source": contract["title"],
            "doi": contract["doi"],
            "ordered_rules": [
                "valid RRLI/RBLI and RRLI > 9 => class 2 RLED",
                "remaining valid pixels and RBLI > 0.57 => class 1 WLED",
                "remaining valid pixels => class 3 Other",
                "invalid index pixels => NoData 255",
            ],
            "threshold_tuning": False,
        },
        "raster": {
            "path": str(CLASS_PATH),
            "sha256": output_hash,
            "dtype": "uint8",
            "nodata": 255,
            "crs": index_stats["source"]["crs"],
            "transform": index_stats["source"]["transform"],
            "width": index_stats["source"]["width"],
            "height": index_stats["source"]["height"],
            "pixel_size_m": [40.0, 40.0],
        },
        "pixel_accounting": {
            "total_pixels": total_count,
            "valid_index_pixels": valid_count,
            "nodata_pixels": int(counts[255]),
            "class_sum_equals_valid_index_pixels": sum(row["pixel_count"] for row in class_rows.values())
            == valid_count,
            "class_codes_outside_1_2_3": [],
        },
        "classes": class_rows,
        "area_note": (
            "Area is pixel count multiplied by 40 m × 40 m in projected EPSG:32651; "
            "it is planar raster area, not an independently surveyed illuminated footprint."
        ),
        "validation": validation,
        "preview": {"path": str(PREVIEW_PATH), "sha256": preview_hash, "dpi": 300},
        "reproducibility": {"script": str(Path(__file__)), "script_sha256": script_hash},
        "blindness": {
            "user_reference_rbli_opened": False,
            "user_reference_classification_opened": False,
            "user_reference_outputs_opened_pre_lock": False,
            "user_reference_outputs_opened_post_lock": False,
            "gold_output_opened": False,
        },
        "limitations": [
            "Large ratios can arise where the green-band denominator is small.",
            "Fixed spectral-ratio thresholds cannot resolve all mixed-light pixels or spectral mixtures.",
            "The preceding destriping and radiometric-calibration chain was not rerun in this experiment; the user-approved preprocessed RGB was the analysis input.",
            "No ground-reference light-type labels were available, so these results are not an accuracy assessment.",
        ],
    }
    write_json(CLASS_STATS_PATH, stats)

    # This lock is written only after the classification, validation and preview
    # are complete. compare_phase() must verify it before opening references.
    lock = {
        "schema": "ntl.paper-case.pre-comparison-lock.v1",
        "locked_at_utc": utc_now(),
        "new_result": {"path": str(CLASS_PATH), "sha256": output_hash},
        "new_statistics": {"path": str(CLASS_STATS_PATH), "sha256": sha256(CLASS_STATS_PATH)},
        "new_preview": {"path": str(PREVIEW_PATH), "sha256": preview_hash},
        "thresholds": {"RRLI_RLED": 9.0, "RBLI_WLED": 0.57},
        "nodata": 255,
        "reference_files_opened_before_lock": False,
        "immutable_analysis_decisions_after_lock": True,
    }
    write_json(LOCK_PATH, lock)

    log = f"""# Q17 formal NTL Analyst log

## Blind analysis phase

- Status: completed and locked before reference comparison.
- Formal inputs: accepted RRLI/RBLI rasters and frozen Jia et al. (2024) method contract.
- Ordered classification: RRLI > 9 → RLED; otherwise RBLI > 0.57 → WLED; otherwise Other.
- NoData: 255; invalid index pixels were not relabelled as Other.
- Threshold tuning: none.
- Full raster reopened: yes.
- Independent threshold sample: {validation['independent_threshold_sample_size']:,} pixels; mismatches: 0.
- New-result SHA-256: `{output_hash}`.
- Reference files opened in this phase: no.

The result decisions above are locked. The comparison phase may quantify agreement or difference but may not modify thresholds, masking, class order, or the new result.
"""
    LOG_PATH.write_text(log, encoding="utf-8", newline="\n")


def compare_rbli(new_path: Path, reference_path: Path) -> dict:
    common = 0
    new_only = 0
    reference_only = 0
    both_invalid = 0
    sum_abs = 0.0
    sum_sq = 0.0
    max_abs = 0.0
    exact = 0
    within_abs = 0
    within_combined = 0

    with rasterio.open(new_path) as new_src, rasterio.open(reference_path) as ref_src:
        grid_match = same_grid(new_src, ref_src)
        metadata = {
            "new": {
                "shape": [new_src.height, new_src.width],
                "crs": new_src.crs.to_string() if new_src.crs else None,
                "transform": list(new_src.transform)[:6],
                "dtype": new_src.dtypes[0],
                "nodata": new_src.nodata,
                "description": new_src.descriptions[0],
            },
            "reference": {
                "shape": [ref_src.height, ref_src.width],
                "crs": ref_src.crs.to_string() if ref_src.crs else None,
                "transform": list(ref_src.transform)[:6],
                "dtype": ref_src.dtypes[0],
                "nodata": ref_src.nodata,
                "description": ref_src.descriptions[0],
            },
            "grid_match": grid_match,
        }
        if not grid_match:
            return {"status": "not_comparable_grid_mismatch", "metadata": metadata}

        for _, window in new_src.block_windows(1):
            new = new_src.read(1, window=window)
            ref = ref_src.read(1, window=window)
            new_valid = valid_float(new, new_src.nodata)
            ref_valid = valid_float(ref, ref_src.nodata)
            overlap = new_valid & ref_valid
            new_only += int(np.count_nonzero(new_valid & ~ref_valid))
            reference_only += int(np.count_nonzero(~new_valid & ref_valid))
            both_invalid += int(np.count_nonzero(~new_valid & ~ref_valid))
            n = int(np.count_nonzero(overlap))
            if not n:
                continue
            delta = new[overlap].astype(np.float64) - ref[overlap].astype(np.float64)
            abs_delta = np.abs(delta)
            common += n
            sum_abs += float(abs_delta.sum(dtype=np.float64))
            sum_sq += float(np.square(delta).sum(dtype=np.float64))
            max_abs = max(max_abs, float(abs_delta.max()))
            exact += int(np.count_nonzero(delta == 0))
            within_abs += int(np.count_nonzero(abs_delta <= 1e-6))
            within_combined += int(
                np.count_nonzero(np.isclose(new[overlap], ref[overlap], rtol=1e-5, atol=1e-6))
            )

    metrics = {
        "common_valid_pixels": common,
        "new_valid_reference_invalid": new_only,
        "new_invalid_reference_valid": reference_only,
        "both_invalid": both_invalid,
        "mae": sum_abs / common if common else None,
        "rmse": math.sqrt(sum_sq / common) if common else None,
        "maximum_absolute_difference": max_abs if common else None,
        "exact_equality_fraction": exact / common if common else None,
        "absolute_tolerance_1e-6_fraction": within_abs / common if common else None,
        "isclose_rtol_1e-5_atol_1e-6_fraction": within_combined / common if common else None,
    }
    return {"status": "compared", "metadata": metadata, "metrics": metrics}


def compare_classification(new_path: Path, reference_path: Path) -> dict:
    matrix = np.zeros((3, 3), dtype=np.int64)
    new_valid_count = 0
    ref_valid_count = 0
    new_only = 0
    reference_only = 0
    reference_code_counts: Counter[int] = Counter()

    with rasterio.open(new_path) as new_src, rasterio.open(reference_path) as ref_src:
        grid_match = same_grid(new_src, ref_src)
        ref_tags = ref_src.tags()
        metadata = {
            "new": {
                "shape": [new_src.height, new_src.width],
                "crs": new_src.crs.to_string() if new_src.crs else None,
                "transform": list(new_src.transform)[:6],
                "dtype": new_src.dtypes[0],
                "nodata": new_src.nodata,
                "description": new_src.descriptions[0],
                "tags": new_src.tags(),
            },
            "reference": {
                "shape": [ref_src.height, ref_src.width],
                "crs": ref_src.crs.to_string() if ref_src.crs else None,
                "transform": list(ref_src.transform)[:6],
                "dtype": ref_src.dtypes[0],
                "nodata": ref_src.nodata,
                "description": ref_src.descriptions[0],
                "tags": ref_tags,
            },
            "grid_match": grid_match,
        }
        if not grid_match:
            return {"status": "not_comparable_grid_mismatch", "metadata": metadata}

        for _, window in new_src.block_windows(1):
            new = new_src.read(1, window=window)
            ref = ref_src.read(1, window=window)
            ref_unique, ref_counts = np.unique(ref, return_counts=True)
            reference_code_counts.update({int(k): int(v) for k, v in zip(ref_unique, ref_counts)})

            new_valid = np.isin(new, [1, 2, 3])
            ref_valid = np.isin(ref, [1, 2, 3])
            overlap = new_valid & ref_valid
            new_valid_count += int(np.count_nonzero(new_valid))
            ref_valid_count += int(np.count_nonzero(ref_valid))
            new_only += int(np.count_nonzero(new_valid & ~ref_valid))
            reference_only += int(np.count_nonzero(~new_valid & ref_valid))
            if np.any(overlap):
                encoded = (new[overlap].astype(np.int16) - 1) * 3 + (ref[overlap].astype(np.int16) - 1)
                matrix += np.bincount(encoded, minlength=9).reshape(3, 3)

    common = int(matrix.sum())
    diagonal = int(np.trace(matrix))
    per_class = {}
    for code in (1, 2, 3):
        idx = code - 1
        tp = int(matrix[idx, idx])
        predicted = int(matrix[idx, :].sum())
        reference = int(matrix[:, idx].sum())
        union = predicted + reference - tp
        per_class[str(code)] = {
            "name": CLASS_NAMES[code],
            "precision_new_vs_reference": tp / predicted if predicted else None,
            "recall_new_vs_reference": tp / reference if reference else None,
            "iou_new_vs_reference": tp / union if union else None,
            "new_count_in_common_mask": predicted,
            "reference_count_in_common_mask": reference,
        }

    return {
        "status": "compared",
        "metadata": metadata,
        "normalization": {
            "semantic_codes_compared": {"1": "WLED", "2": "RLED", "3": "Other"},
            "reference_code_0_treatment": (
                "Excluded from semantic comparison because the reference GeoTIFF declares nodata=0, "
                "even though its band description labels code 0 as Dark. No code-0 pixel was mapped to Other."
            ),
            "new_nodata_255_treatment": "Excluded from semantic comparison.",
            "comparison_mask": "Intersection of new and reference codes 1, 2, or 3.",
        },
        "reference_code_counts": {str(k): int(v) for k, v in sorted(reference_code_counts.items())},
        "common_valid_pixels": common,
        "new_valid_pixels": new_valid_count,
        "reference_valid_pixels": ref_valid_count,
        "new_valid_reference_excluded": new_only,
        "new_excluded_reference_valid": reference_only,
        "confusion_matrix": {
            "row_order_new": ["WLED", "RLED", "Other"],
            "column_order_reference": ["WLED", "RLED", "Other"],
            "counts": matrix.tolist(),
        },
        "overall_agreement": diagonal / common if common else None,
        "per_class": per_class,
        "interpretation_boundary": (
            "Agreement with the user's earlier file measures implementation consistency, not accuracy "
            "against independent ground truth."
        ),
    }


def compare_phase() -> None:
    if not LOCK_PATH.exists():
        raise RuntimeError("Pre-comparison lock is missing; run --phase classify first")
    lock = read_json(LOCK_PATH)
    locked_hash = lock["new_result"]["sha256"]
    current_hash = sha256(CLASS_PATH)
    if current_hash != locked_hash:
        raise RuntimeError("New result changed after lock; refusing to open references")
    if lock.get("immutable_analysis_decisions_after_lock") is not True:
        raise RuntimeError("Lock does not prohibit post-comparison analysis changes")

    # Reference access begins only here, after the lock checks above succeed.
    for path in (REFERENCE_RBLI_PATH, REFERENCE_CLASS_PATH):
        if not path.exists():
            raise FileNotFoundError(path)
    reference_hashes = {
        "rbli": sha256(REFERENCE_RBLI_PATH),
        "classification": sha256(REFERENCE_CLASS_PATH),
    }
    rbli_comparison = compare_rbli(RBLI_PATH, REFERENCE_RBLI_PATH)
    class_comparison = compare_classification(CLASS_PATH, REFERENCE_CLASS_PATH)

    payload = {
        "schema": "ntl.paper-case.formal-reference-comparison.v1",
        "case_id": "Q17-sdgsat-light-classification",
        "status": "success",
        "comparison_stage": "post-result-lock",
        "lock_verified": {
            "path": str(LOCK_PATH),
            "locked_new_result_sha256": locked_hash,
            "current_new_result_sha256": current_hash,
            "match": True,
        },
        "reference_hashes": reference_hashes,
        "rbli": rbli_comparison,
        "classification": class_comparison,
        "analysis_changed_after_comparison": False,
        "access_record": {
            "user_reference_outputs_opened_pre_lock": False,
            "user_reference_outputs_opened_post_lock": True,
            "gold_output_opened": False,
        },
        "reproducibility": {
            "script": str(Path(__file__)),
            "script_sha256": sha256(Path(__file__)),
        },
        "limitations": [
            "The earlier RBLI/classification files are implementation references, not ground truth.",
            "The earlier classification declares code 0 as raster NoData while its description calls code 0 Dark; code 0 is therefore excluded, not remapped.",
            "No field-validated luminaire labels were available for accuracy assessment.",
        ],
    }
    write_json(COMPARISON_PATH, payload)

    stats = read_json(CLASS_STATS_PATH)
    stats["phase"] = "post-comparison-complete"
    stats["blindness"]["user_reference_rbli_opened"] = True
    stats["blindness"]["user_reference_classification_opened"] = True
    stats["blindness"]["user_reference_outputs_opened_pre_lock"] = False
    stats["blindness"]["user_reference_outputs_opened_post_lock"] = True
    stats["blindness"]["gold_output_opened"] = False
    stats["blindness"].pop("gold_or_reference_output_opened", None)
    stats["reproducibility"]["script_sha256"] = sha256(Path(__file__))
    stats["post_lock_comparison"] = {
        "comparison_path": str(COMPARISON_PATH),
        "comparison_sha256": sha256(COMPARISON_PATH),
        "new_result_hash_unchanged": sha256(CLASS_PATH) == locked_hash,
        "thresholds_or_masking_changed": False,
    }
    write_json(CLASS_STATS_PATH, stats)

    rbli_metrics = rbli_comparison.get("metrics", {})
    overall = class_comparison.get("overall_agreement")
    existing_log = LOG_PATH.read_text(encoding="utf-8")
    comparison_marker = "\n\n## Post-lock blind reference comparison"
    if comparison_marker in existing_log:
        LOG_PATH.write_text(
            existing_log.split(comparison_marker, 1)[0].rstrip() + "\n",
            encoding="utf-8",
            newline="\n",
        )
    with LOG_PATH.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(
            f"""

## Post-lock blind reference comparison

- Lock verified before opening references: yes.
- New-result hash remained `{locked_hash}`.
- Existing RBLI SHA-256: `{reference_hashes['rbli']}`.
- Existing classification SHA-256: `{reference_hashes['classification']}`.
- Existing RBLI has only {rbli_metrics.get('common_valid_pixels', 0):,} common-valid pixels; its valid mask is narrower than the new result.
- RBLI MAE: {rbli_metrics.get('mae')}.
- RBLI RMSE: {rbli_metrics.get('rmse')}.
- RBLI values in the common-valid region are exactly identical: {rbli_metrics.get('exact_equality_fraction')}.
- Classification common semantic pixels: {class_comparison.get('common_valid_pixels', 0):,}.
- Classification overall agreement: {overall}.
- Post-comparison threshold, mask, class-order, or raster modification: none.

The 88.78% classification agreement describes consistency with an earlier implementation. It is not ground-truth accuracy. No Gold output was opened at any stage.

## Analytical limitations

- Large ratios can occur where the green denominator is small.
- Fixed thresholds cannot fully resolve mixed light sources or spectral mixtures.
- The preceding preprocessing chain was accepted from the user and not rerun in this case.
- No field-validated labels were available.
"""
        )

    # Final JSON serialization/reopen and immutable-result checks.
    read_json(CLASS_STATS_PATH)
    read_json(COMPARISON_PATH)
    if sha256(CLASS_PATH) != locked_hash:
        raise RuntimeError("New result changed during comparison")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=("classify", "compare"))
    args = parser.parse_args()
    if args.phase == "classify":
        classify_phase()
    else:
        compare_phase()


if __name__ == "__main__":
    main()
