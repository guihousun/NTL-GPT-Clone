from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from tools import conflict_city_events as city_events


def _rows() -> list[dict[str, object]]:
    source_iran = "https://example.test/iran/FeatureServer/0"
    source_israel = "https://example.test/israel/FeatureServer/0"
    return [
        {"source_layer_url": source_iran, "OBJECTID": 1, "event_id": 1, "event_date_utc": "2026-06-01", "event_type": "Confirmed Airstrike", "country": "Iran", "city": "Tehran", "latitude": 35.7, "longitude": 51.4},
        {"source_layer_url": source_iran, "OBJECTID": 2, "event_id": 2, "event_date_utc": "2026-06-02", "event_type": "Reported Airstrike", "country": "IRN", "city": "City of Tehran", "latitude": 35.71, "longitude": 51.41},
        {"source_layer_url": source_iran, "OBJECTID": 3, "event_id": 99, "event_date_utc": "2026-06-03", "event_type": "Confirmed Airstrike", "country": "Islamic Republic of Iran", "city": "Shiraz", "latitude": 29.6, "longitude": 52.5},
        {"source_layer_url": source_iran, "OBJECTID": 4, "event_id": 99, "event_date_utc": "2026-06-04", "event_type": "Confirmed Airstrike", "country": "Iran", "city": "Shiraz", "latitude": 29.61, "longitude": 52.51},
        {"source_layer_url": source_israel, "OBJECTID": 1, "event_id": 1, "event_date_utc": "2026-06-01", "event_type": "Missile Attack", "country": "Israel", "city": "Haifa", "latitude": 32.8, "longitude": 35.0},
        {"source_layer_url": source_israel, "OBJECTID": 2, "event_id": 2, "event_date_utc": "2026-06-02", "event_type": "Rocket Attack", "country": "State of Israel", "city": "Haifa", "latitude": 32.81, "longitude": 35.01},
        {"source_layer_url": source_israel, "OBJECTID": 3, "event_id": 3, "event_date_utc": "2026-06-03", "event_type": "Drone Attack", "country": "ISR", "city": "Tel Aviv", "latitude": 32.1, "longitude": 34.8},
        {"source_layer_url": source_israel, "OBJECTID": 4, "event_id": 4, "event_date_utc": "2026-06-04", "event_type": "Air Defense Activity", "country": "Israel", "city": "Haifa"},
        {"source_layer_url": source_israel, "OBJECTID": 5, "event_id": 5, "event_date_utc": "2026-06-04", "event_type": "Missile Attack", "country": "Israel", "city": ""},
        {"source_layer_url": source_israel, "OBJECTID": 6, "event_id": 6, "event_date_utc": "2026-07-01", "event_type": "Missile Attack", "country": "Israel", "city": "Haifa"},
        {"source_layer_url": source_israel, "OBJECTID": 7, "event_id": 7, "event_date_utc": "2026-06-04", "event_type": "Missile Attack", "country": "Iraq", "city": "Baghdad"},
        {"source_layer_url": source_israel, "OBJECTID": 2, "event_id": 2, "event_date_utc": "2026-06-02", "event_type": "Rocket Attack", "country": "Israel", "city": "Haifa"},
    ]


def test_rank_records_preserves_country_ties_and_namespaces_ids() -> None:
    result = city_events.rank_conflict_city_records(
        _rows(),
        event_window_end="2026-06-30",
        city_aliases={"City of Tehran": "Tehran"},
    )

    selected = [(row["country"], row["city"], row["attack_record_count"]) for row in result["selected_cities"]]
    assert selected == [
        ("Iran", "Shiraz", 2),
        ("Iran", "Tehran", 2),
        ("Israel", "Haifa", 2),
    ]
    assert all(row["is_tied_maximum"] for row in result["selected_cities"][:2])
    assert result["selected_cities"][2]["is_tied_maximum"] is False
    assert result["audit"]["eligible_record_count"] == 7
    assert result["audit"]["excluded_counts"] == {
        "after_cutoff_date": 1,
        "duplicate_record_key": 1,
        "excluded_event_type": 1,
        "missing_city": 1,
        "non_target_or_missing_country": 1,
    }
    assert result["audit"]["source_event_id_collision_group_count"] == 1

    event_one_keys = {
        row["record_key"]
        for row in result["audited_records"]
        if str(row.get("event_id")) == "1"
    }
    assert len(event_one_keys) == 2, "identical numeric IDs from separate layers must not collide"


def test_local_tool_run_writes_auditable_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    input_path = tmp_path / "events.csv"
    output_dir = tmp_path / "outputs" / "run"
    with input_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in _rows() for key in row}))
        writer.writeheader()
        writer.writerows(_rows())

    monkeypatch.setattr(city_events, "_resolve_input_path", lambda _path, _thread: input_path)
    monkeypatch.setattr(city_events, "_resolve_output_dir", lambda *_args: output_dir)
    result = city_events.conflict_city_event_ranking_tool.invoke(
        {
            "events_path": "inputs/events.csv",
            "run_label": "run",
            "event_window_end": "2026-06-30",
            "city_aliases_json": json.dumps({"City of Tehran": "Tehran"}),
        },
        config={"configurable": {"thread_id": "conflict-city-test"}},
    )

    assert result["status"] == "complete"
    assert result["summary"]["country_maxima"] == {"Iran": 2, "Israel": 2}
    assert set(result["output_files"]) == {
        "event_records_snapshot",
        "city_attack_record_counts",
        "selected_cities",
        "selected_city_event_centroids",
        "ranking_metadata",
    }
    for path in result["output_files"].values():
        assert Path(path).is_file()
    metadata = json.loads(Path(result["output_files"]["ranking_metadata"]).read_text(encoding="utf-8"))
    assert metadata["count_semantics"].startswith("distinct source records")
    assert metadata["source"]["mode"] == "authorized_local_snapshot"
    assert "ranking_metadata" not in metadata["output_sha256"]


def test_missing_source_identity_is_excluded_and_prevents_complete_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        {"source_layer_url": "https://example.test/a/FeatureServer/0", "OBJECTID": 1, "event_id": 1, "event_date_utc": "2026-06-01", "event_type": "Confirmed Airstrike", "country": "Iran", "city": "Tehran"},
        {"source_layer_url": "https://example.test/b/FeatureServer/0", "OBJECTID": 1, "event_id": 1, "event_date_utc": "2026-06-01", "event_type": "Missile Attack", "country": "Israel", "city": "Haifa"},
        {"OBJECTID": 9, "event_id": 9, "event_date_utc": "2026-06-01", "event_type": "Confirmed Airstrike", "country": "Iran", "city": "Tehran"},
    ]
    input_path = tmp_path / "events.json"
    input_path.write_text(json.dumps(records), encoding="utf-8")
    output_dir = tmp_path / "out"
    monkeypatch.setattr(city_events, "_resolve_input_path", lambda _path, _thread: input_path)
    monkeypatch.setattr(city_events, "_resolve_output_dir", lambda *_args: output_dir)

    result = city_events.run_conflict_city_event_retrieval(
        events_path="inputs/events.json",
        event_window_end="2026-06-30",
        config={"configurable": {"thread_id": "conflict-city-test"}},
    )
    assert result["status"] == "partial"
    assert result["audit"]["missing_source_identity_record_count"] == 1
    assert result["audit"]["excluded_counts"]["missing_source_identity"] == 1


def test_live_retrieval_fails_closed_without_source_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_fetch(**_kwargs: object) -> dict[str, object]:
        raise AssertionError("live fetch must not run without explicit acknowledgement")

    monkeypatch.setattr(city_events, "run_conflict_ntl_fetch_isw_events", unexpected_fetch)
    result = city_events.run_conflict_city_event_retrieval(
        event_window_end="2026-06-30",
        source_terms_acknowledged=False,
        config={"configurable": {"thread_id": "conflict-city-test"}},
    )
    assert result["status"] == "needs_source_authorization"
    assert result["output_files"] == {}


def test_live_layer_provenance_records_freshness_and_license_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata_path = tmp_path / "fetch_metadata.json"
    layer_url = "https://example.test/service/FeatureServer/0"
    metadata_path.write_text(json.dumps({"layers": [{"name": "sample", "url": layer_url}]}), encoding="utf-8")

    def fake_request(url: str, **_kwargs: object) -> dict[str, object]:
        if url.endswith("/0"):
            return {"editingInfo": {"lastEditDate": 1_700_000_000_000}, "timeInfo": {"startTimeField": "pub_date"}}
        if url.endswith("/FeatureServer"):
            return {"serviceItemId": "abc123"}
        if url.endswith("/abc123"):
            return {"modified": 1_700_000_100_000, "licenseInfo": "permission required"}
        raise AssertionError(url)

    monkeypatch.setattr(city_events, "_request_json", fake_request)
    records, errors = city_events._collect_live_layer_provenance(
        {"output_files": {"metadata_json": str(metadata_path)}}
    )
    assert errors == []
    assert records[0]["service_item_id"] == "abc123"
    assert records[0]["time_start_field"] == "pub_date"
    assert records[0]["license_info_present"] is True
    assert len(records[0]["license_info_sha256"]) == 64


def test_registry_exposes_ranking_tool_to_event_tracker_and_specialized_catalog() -> None:
    import tools

    assert "conflict_city_event_ranking_tool" in tools._EXPORTS
    assert "conflict_city_event_ranking_tool" in tools._GROUPS["event_tracker_tools"]
    assert "conflict_city_event_ranking_tool" not in tools._GROUPS["data_searcher_tools"]
    assert "conflict_city_event_ranking_tool" in tools._GROUPS["specialized_tool_catalog"]
    assert tools.conflict_city_event_ranking_tool.name == "conflict_city_event_ranking_tool"
