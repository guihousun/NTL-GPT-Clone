import json
from pathlib import Path

from experiments.official_daily_ntl_fastpath import scan_official_ntl_availability as mod


def _latest_json(tmp_path: Path) -> Path:
    files = sorted(tmp_path.glob("official_ntl_availability_*.json"))
    assert files, "no output json generated"
    return files[-1]


def test_scan_with_include_gee_adds_project_gee_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "parse_sources_arg", lambda _: ["VJ146A1"])
    monkeypatch.setattr(mod, "_query_collection_time_range", lambda _: ("2018-01-05", None))
    monkeypatch.setattr(mod, "search_granules", lambda **_: [{"id": "g1"}])
    monkeypatch.setattr(mod, "latest_granule_day", lambda *_args, **_kwargs: "2026-02-22")
    monkeypatch.setattr(
        mod,
        "query_gee_products_latest",
        lambda **_: (
            [
                {
                    "source": "GEE VNP46A2 (Daily)",
                    "dataset_id": "NASA/VIIRS/002/VNP46A2",
                    "temporal_resolution": "daily",
                    "latest_global_date": "2026-02-22",
                    "error": None,
                },
                {
                    "source": "GEE VCMSLCFG (Monthly)",
                    "dataset_id": "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG",
                    "temporal_resolution": "monthly",
                    "latest_global_date": "2025-12-01",
                    "error": None,
                },
            ],
            None,
        ),
    )
    monkeypatch.setattr(
        mod,
        "_query_gee_time_ranges",
        lambda **_: {
            "NASA/VIIRS/002/VNP46A2": {
                "range_start": "2012-01-19",
                "range_end": "2026-02-22",
                "range_error": None,
            },
            "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG": {
                "range_start": "2014-01-01",
                "range_end": "2025-12-01",
                "range_error": None,
            },
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "scan_ntl_availability.py",
            "--sources",
            "VJ146A1",
            "--granule-start-date",
            "2026-01-01",
            "--granule-end-date",
            "2026-02-24",
            "--output-dir",
            str(tmp_path),
            "--include-gee",
            "--gee-project",
            "unit-test-project",
        ],
    )

    mod.main()

    payload = json.loads(_latest_json(tmp_path).read_text(encoding="utf-8"))
    assert payload["official_rows"] == 1
    assert payload["gee_rows"] == 2
    assert len(payload["rows"]) == 3
    assert payload["include_gee"] is True
    assert any(r.get("source_type") == "gee" for r in payload["rows"])


def test_scan_without_include_gee_keeps_official_only(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "parse_sources_arg", lambda _: ["VJ146A1"])
    monkeypatch.setattr(mod, "_query_collection_time_range", lambda _: ("2018-01-05", None))
    monkeypatch.setattr(mod, "search_granules", lambda **_: [{"id": "g1"}])
    monkeypatch.setattr(mod, "latest_granule_day", lambda *_args, **_kwargs: "2026-02-22")
    monkeypatch.setattr(
        mod,
        "query_gee_products_latest",
        lambda **_: (_ for _ in ()).throw(RuntimeError("should_not_be_called")),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "scan_ntl_availability.py",
            "--sources",
            "VJ146A1",
            "--granule-start-date",
            "2026-01-01",
            "--granule-end-date",
            "2026-02-24",
            "--output-dir",
            str(tmp_path),
        ],
    )

    mod.main()

    payload = json.loads(_latest_json(tmp_path).read_text(encoding="utf-8"))
    assert payload["official_rows"] == 1
    assert payload["gee_rows"] == 0
    assert len(payload["rows"]) == 1
    assert payload["include_gee"] is False
    assert payload["rows"][0]["source_type"] == "official"

