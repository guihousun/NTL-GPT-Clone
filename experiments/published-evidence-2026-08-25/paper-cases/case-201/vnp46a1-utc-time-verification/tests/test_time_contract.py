from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "analyze_utc_time.py"
SPEC = importlib.util.spec_from_file_location("q18_utc_time", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_mainshock_converts_to_yangon_without_product_time_inference() -> None:
    event = datetime(2025, 3, 28, 6, 20, 52, tzinfo=timezone.utc)
    assert event.astimezone(ZoneInfo("Asia/Yangon")).isoformat() == "2025-03-28T12:50:52+06:30"


def test_utc_product_day_decimal_hour_maps_to_the_following_local_date() -> None:
    # This tests the calendar conversion rule only, not an asserted observed UTC_Time value.
    assert MODULE.local_timestamp(17.5).isoformat() == "2025-03-29T00:00:00+06:30"


def test_source_backed_result_keeps_product_day_and_local_night_distinct() -> None:
    root = Path(__file__).resolve().parents[1]
    result = json.loads((root / "results" / "utc-time-analysis.json").read_text(encoding="utf-8"))
    assert result["product"]["utc_product_date"] == "2025-03-28"
    assert result["event_pixel"]["observation_time_utc"].startswith("2025-03-28T")
    assert result["event_pixel"]["observation_time_local"].startswith("2025-03-29T")
    assert result["interpretation"]["event_pixel_is_post_event"] is True
    assert all(row["local_date_counts"] == {"2025-03-29": row["n"]} for row in result["buffer_summaries"])
