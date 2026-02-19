from experiments.official_daily_ntl_fastpath.cmr_client import (
    extract_download_link,
    parse_granules_payload,
    resolve_token,
    select_latest_day_entries,
    validate_download_payload,
)


def test_parse_granules_payload_and_pick_latest_day():
    payload = {
        "feed": {
            "entry": [
                {
                    "producer_granule_id": "VJ146A2.A2026034.h30v05.002.x.h5",
                    "time_start": "2026-02-03T00:00:00.000Z",
                    "updated": "2026-02-13T17:51:40.770Z",
                    "day_night_flag": "UNSPECIFIED",
                    "links": [
                        {"href": "https://example.com/file_older.h5", "rel": "http://esipfed.org/ns/fedsearch/1.1/data#"}
                    ],
                },
                {
                    "producer_granule_id": "VJ146A2.A2026042.h30v05.002.y.h5",
                    "time_start": "2026-02-11T00:00:00.000Z",
                    "updated": "2026-02-13T18:51:57.990Z",
                    "day_night_flag": "UNSPECIFIED",
                    "links": [
                        {"href": "https://example.com/file_newer.h5", "rel": "http://esipfed.org/ns/fedsearch/1.1/data#"}
                    ],
                },
            ]
        }
    }
    granules = parse_granules_payload(payload)
    latest_date, latest_entries = select_latest_day_entries(granules)
    assert latest_date == "2026-02-11"
    assert len(latest_entries) == 1
    assert latest_entries[0].producer_granule_id.endswith(".h5")


def test_extract_download_link_prefers_data_link():
    links = [
        {"href": "https://example.com/readme.html", "rel": "http://esipfed.org/ns/fedsearch/1.1/documentation#"},
        {"href": "https://example.com/data.h5", "rel": "http://esipfed.org/ns/fedsearch/1.1/data#"},
    ]
    assert extract_download_link(links) == "https://example.com/data.h5"


def test_validate_download_payload_rejects_access_denied_text(tmp_path):
    bad_file = tmp_path / "fake.h5"
    bad_file.write_text("HTTP Basic: Access denied.\n", encoding="utf-8")
    ok, reason = validate_download_payload(bad_file)
    assert ok is False
    assert "access denied" in reason.lower()


def test_resolve_token_does_not_fallback_to_generic_access_token(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("ACCESS_TOKEN=ntl_fake\n", encoding="utf-8")
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    monkeypatch.delenv("EARTHDATA_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("EDL_TOKEN", raising=False)
    assert resolve_token("EARTHDATA_TOKEN") is None
