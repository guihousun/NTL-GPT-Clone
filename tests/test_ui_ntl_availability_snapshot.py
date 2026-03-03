import json
import os
import time
from pathlib import Path

import app_ui


def test_normalize_availability_rows_supports_monitor_and_scan_contracts():
    payload = {
        "gee_rows": [
            {
                "source": "GEE VNP46A2 (Daily)",
                "latest_global_date": "2026-02-22",
                "latest_global_lag_days": 2,
                "latest_bbox_date": "2026-02-21",
                "latest_bbox_lag_days": 3,
            }
        ],
        "rows": [
            {
                "source": "VJ146A1",
                "collection_time_start": "2018-01-05",
                "collection_time_end": None,
                "latest_global_date": "2026-02-22",
                "latest_global_lag_days": 2,
            }
        ],
    }
    rows = app_ui._normalize_availability_rows(payload)
    assert len(rows) == 2
    assert rows[0]["source"] == "GEE VNP46A2 (Daily)"
    assert rows[0]["latest_bbox_date"] == "2026-02-21"
    assert rows[1]["source"] == "VJ146A1"
    assert rows[1]["range_start"] == "2018-01-05"
    assert rows[1]["range_end"] == "-"


def test_load_snapshot_from_scan_file_uses_granule_window(tmp_path):
    p = tmp_path / "official_ntl_availability_20990101T000000Z.json"
    p.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-02-24T05:35:42Z",
                "granule_start_date": "2026-01-01",
                "granule_end_date": "2026-02-24",
                "rows": [
                    {
                        "source": "VJ102DNB",
                        "latest_global_date": "2026-02-24",
                        "latest_global_lag_days": 0,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    snap = app_ui._load_snapshot_from_scan_file(p)
    assert snap["ok"] is True
    assert snap["snapshot_source"] == "local_scan"
    assert snap["start_date"] == "2026-01-01"
    assert snap["end_date"] == "2026-02-24"
    assert snap["rows"][0]["source"] == "VJ102DNB"


def test_find_latest_scan_json_returns_newest_file(tmp_path, monkeypatch):
    d = tmp_path / "outputs"
    d.mkdir()
    old = d / "official_ntl_availability_20260224T010000Z.json"
    new = d / "official_ntl_availability_20260224T020000Z.json"
    old.write_text("{}", encoding="utf-8")
    new.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(app_ui, "_NTL_SCAN_OUTPUT_DIR", d)
    assert app_ui._find_latest_scan_json() == new


def test_order_availability_rows_puts_gee_first():
    rows = [
        {"source": "VJ146A1", "source_type": "official"},
        {"source": "GEE VNP46A2 (Daily)", "source_type": "gee"},
        {"source": "VJ102DNB", "source_type": "official"},
    ]
    ordered = app_ui._order_availability_rows(rows)
    assert ordered[0]["source"].startswith("GEE ")
    assert ordered[1]["source"] in {"VJ102DNB", "VJ146A1"}


def test_order_availability_rows_supports_name_only_gee_detection():
    rows = [
        {"source": "VJ146A2"},
        {"source": "GEE VNP46A1 (Daily)"},
    ]
    ordered = app_ui._order_availability_rows(rows)
    assert ordered[0]["source"] == "GEE VNP46A1 (Daily)"


def test_is_scan_fresh_true_and_false(tmp_path):
    p = tmp_path / "official_ntl_availability_20990101T000000Z.json"
    p.write_text("{}", encoding="utf-8")
    assert app_ui._is_scan_fresh(p, refresh_seconds=3600) is True
    old_ts = time.time() - 7200
    os.utime(p, (old_ts, old_ts))
    assert app_ui._is_scan_fresh(p, refresh_seconds=3600) is False


def test_scan_refresh_lock_exclusive(tmp_path, monkeypatch):
    d = tmp_path / "outputs"
    d.mkdir()
    lock = d / ".ntl_availability_refresh.lock"
    monkeypatch.setattr(app_ui, "_NTL_SCAN_OUTPUT_DIR", d)
    monkeypatch.setattr(app_ui, "_NTL_SCAN_LOCK_FILE", lock)
    assert app_ui._try_acquire_scan_refresh_lock() is True
    assert app_ui._try_acquire_scan_refresh_lock() is False
    app_ui._release_scan_refresh_lock()
    assert app_ui._try_acquire_scan_refresh_lock() is True
    app_ui._release_scan_refresh_lock()
