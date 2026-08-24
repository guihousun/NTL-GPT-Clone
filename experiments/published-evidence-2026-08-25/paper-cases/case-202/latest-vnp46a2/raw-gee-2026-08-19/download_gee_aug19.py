"""Run the bounded raw-GEE verifier for the newly visible 19 August product.

The reusable verifier remains the 12--18 August implementation.  This adapter
changes only its output root and one UTC product day, preserving the same AOI,
raw VNP46A2 band, QA bands, scale, direct-download validation, and no-secret
logging policy.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CASE_ROOT = ROOT.parent
SOURCE = CASE_ROOT / "raw-gee-2026-08-12-to-18" / "download_gee_aug12_18.py"


def main() -> int:
    spec = importlib.util.spec_from_file_location("case202_aug19_raw", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("The bounded raw-GEE verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.ROOT = ROOT
    module.CASE_ROOT = CASE_ROOT
    module.AOI_PATH = CASE_ROOT / "tehran-boundary.geojson"
    module.EXISTING_AUGUST_CHUNK = CASE_ROOT / "gee-chunk-2026-08.json"
    module.START_DATE = date(2026, 8, 19)
    module.END_DATE = date(2026, 8, 19)
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(main())
