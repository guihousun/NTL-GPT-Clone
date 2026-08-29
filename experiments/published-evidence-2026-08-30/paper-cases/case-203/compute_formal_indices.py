"""Create blinded RRLI/RBLI inputs for the paper-case Analyst.

This script intentionally reads only the user-supplied calibrated RGB raster.
It does not read the user's existing RBLI or classified raster.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio


CASE_DIR = Path(__file__).resolve().parent
SOURCE = Path(
    r"user-provided-local-data/NTL-GPT/SDGSAT_1/SDGSAT1_GLI_shanghai_radiance_rgb.tif"
)
ORIGINAL = Path(
    r"user-provided-local-data/SGDSAT-1/KX10_GIU_20220304_E121.82_N31.56_202200100146_L4A_A_RGB.tif"
)
RRLI_PATH = CASE_DIR / "formal-SDGSAT1-shanghai-RRLI.tif"
RBLI_PATH = CASE_DIR / "formal-SDGSAT1-shanghai-RBLI.tif"
SUMMARY_PATH = CASE_DIR / "formal-index-statistics.json"
NODATA = np.float32(-9999.0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def blank_stats() -> dict[str, object]:
    return {
        "valid_pixel_count": 0,
        "nodata_pixel_count": 0,
        "minimum": None,
        "maximum": None,
        "sum": 0.0,
        "sum_of_squares": 0.0,
    }


def update_stats(stats: dict[str, object], values: np.ndarray, total: int) -> None:
    count = int(values.size)
    stats["valid_pixel_count"] = int(stats["valid_pixel_count"]) + count
    stats["nodata_pixel_count"] = int(stats["nodata_pixel_count"]) + total - count
    if not count:
        return
    current_min = float(np.min(values))
    current_max = float(np.max(values))
    stats["minimum"] = (
        current_min if stats["minimum"] is None else min(float(stats["minimum"]), current_min)
    )
    stats["maximum"] = (
        current_max if stats["maximum"] is None else max(float(stats["maximum"]), current_max)
    )
    values64 = values.astype(np.float64, copy=False)
    stats["sum"] = float(stats["sum"]) + float(np.sum(values64))
    stats["sum_of_squares"] = float(stats["sum_of_squares"]) + float(
        np.sum(values64 * values64)
    )


def finalize_stats(stats: dict[str, object]) -> dict[str, object]:
    count = int(stats["valid_pixel_count"])
    if count:
        mean = float(stats["sum"]) / count
        variance = max(float(stats["sum_of_squares"]) / count - mean * mean, 0.0)
        stats["mean"] = mean
        stats["population_standard_deviation"] = variance**0.5
    else:
        stats["mean"] = None
        stats["population_standard_deviation"] = None
    stats.pop("sum_of_squares")
    stats["valid_fraction"] = count / (
        count + int(stats["nodata_pixel_count"])
    )
    return stats


def main() -> None:
    if not SOURCE.is_file() or not ORIGINAL.is_file():
        raise FileNotFoundError("The declared SDGSAT-1 inputs are unavailable.")

    stats = {"RRLI": blank_stats(), "RBLI": blank_stats()}
    source_band_stats = {"R": blank_stats(), "G": blank_stats(), "B": blank_stats()}

    with rasterio.open(SOURCE) as src:
        if src.count != 3:
            raise ValueError(f"Expected 3 bands, found {src.count}.")
        if tuple(src.dtypes) != ("float32", "float32", "float32"):
            raise ValueError(f"Expected calibrated float32 RGB, found {src.dtypes}.")

        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            count=1,
            dtype="float32",
            nodata=float(NODATA),
            tiled=True,
            blockxsize=256,
            blockysize=256,
            compress="deflate",
            predictor=3,
            interleave="band",
            BIGTIFF="IF_SAFER",
        )

        with rasterio.open(RRLI_PATH, "w", **profile) as rrli_dst, rasterio.open(
            RBLI_PATH, "w", **profile
        ) as rbli_dst:
            rrli_dst.set_band_description(1, "RRLI (Red / Green)")
            rbli_dst.set_band_description(1, "RBLI (Blue / Green)")
            rrli_dst.update_tags(
                formula="Band1 / Band2",
                band_order="R,G,B",
                source=str(SOURCE),
                role="analysis-ready index; no classification applied",
            )
            rbli_dst.update_tags(
                formula="Band3 / Band2",
                band_order="R,G,B",
                source=str(SOURCE),
                role="analysis-ready index; no classification applied",
            )

            for _, window in src.block_windows(1):
                rgb = src.read((1, 2, 3), window=window, out_dtype="float32")
                masks = src.read_masks((1, 2, 3), window=window) > 0
                r, g, b = rgb
                shared_valid = np.all(masks, axis=0) & np.all(np.isfinite(rgb), axis=0)
                if src.nodata is not None:
                    shared_valid &= np.all(rgb != np.float32(src.nodata), axis=0)

                for name, band in zip(("R", "G", "B"), (r, g, b), strict=True):
                    update_stats(
                        source_band_stats[name], band[shared_valid], int(band.size)
                    )

                ratio_valid = shared_valid & (g != 0)
                rrli = np.full(g.shape, NODATA, dtype=np.float32)
                rbli = np.full(g.shape, NODATA, dtype=np.float32)
                np.divide(r, g, out=rrli, where=ratio_valid)
                np.divide(b, g, out=rbli, where=ratio_valid)
                rrli_valid = ratio_valid & np.isfinite(rrli)
                rbli_valid = ratio_valid & np.isfinite(rbli)
                rrli[~rrli_valid] = NODATA
                rbli[~rbli_valid] = NODATA
                rrli_dst.write(rrli, 1, window=window)
                rbli_dst.write(rbli, 1, window=window)
                update_stats(stats["RRLI"], rrli[rrli_valid], int(rrli.size))
                update_stats(stats["RBLI"], rbli[rbli_valid], int(rbli.size))

        metadata = {
            "schema": "ntl.paper-case.formal-index-statistics.v1",
            "status": "success",
            "blindness": {
                "read_existing_user_RBLI": False,
                "read_existing_user_classification": False,
            },
            "source": {
                "path": str(SOURCE),
                "sha256": sha256(SOURCE),
                "original_path": str(ORIGINAL),
                "original_sha256": sha256(ORIGINAL),
                "band_order": ["R", "G", "B"],
                "band_order_evidence": "NTL-GPT SDGSAT1_compute_index runtime contract",
                "crs": str(src.crs),
                "transform": list(src.transform)[:6],
                "bounds": list(src.bounds),
                "width": src.width,
                "height": src.height,
                "resolution": list(src.res),
                "dtype": list(src.dtypes),
                "nodata": src.nodata,
                "source_band_statistics": {
                    key: finalize_stats(value) for key, value in source_band_stats.items()
                },
            },
            "formulae": {"RRLI": "BandR / BandG", "RBLI": "BandB / BandG"},
            "output_nodata": float(NODATA),
            "statistics": {
                key: finalize_stats(value) for key, value in stats.items()
            },
            "outputs": [
                {"path": str(RRLI_PATH), "sha256": sha256(RRLI_PATH)},
                {"path": str(RBLI_PATH), "sha256": sha256(RBLI_PATH)},
            ],
        }

    SUMMARY_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
