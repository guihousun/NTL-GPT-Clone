from experiments.official_daily_ntl_fastpath.cmr_client import (
    HDF5_SIGNATURE,
    download_file_with_curl,
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


def test_download_accepts_valid_payload_even_if_curl_nonzero(tmp_path, monkeypatch):
    out = tmp_path / "granule.h5"
    out.write_bytes(HDF5_SIGNATURE + b"\x00" * 64)

    class _Proc:
        returncode = 35
        stderr = "curl: (35) Recv failure: Connection was reset"
        stdout = ""

    monkeypatch.setattr("experiments.official_daily_ntl_fastpath.cmr_client._require_curl", lambda: "curl")
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: _Proc())

    ok, msg = download_file_with_curl("https://example.com/f.h5", out, earthdata_token="tok", timeout=30)
    assert ok is True
    assert "curl_nonzero_but_payload_valid" in msg
    assert out.exists()


def test_download_error_hint_is_sanitized_for_binary_payload(tmp_path, monkeypatch):
    out = tmp_path / "bad.bin"
    out.write_bytes(b"\x00\xff\x01\x02\x03\x04\x05\x06" * 16)

    class _Proc:
        returncode = 35
        stderr = "curl: (35) Recv failure: Connection was reset"
        stdout = ""

    monkeypatch.setattr("experiments.official_daily_ntl_fastpath.cmr_client._require_curl", lambda: "curl")
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: _Proc())

    ok, msg = download_file_with_curl("https://example.com/f.bin", out, earthdata_token="tok", timeout=30)
    assert ok is False
    assert "binary_payload_head_hex=" in msg
    assert "\x00" not in msg
    assert not out.exists()
