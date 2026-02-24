from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from experiments.official_daily_ntl_fastpath.scan_official_ntl_availability import main


if __name__ == "__main__":
    main()
