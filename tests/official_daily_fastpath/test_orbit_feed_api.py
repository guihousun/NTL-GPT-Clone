from experiments.official_daily_ntl_fastpath import monitor_server


def test_build_orbit_feed_payload_passes_force_refresh_and_ttl(monkeypatch):
    called = {}

    def fake_build_orbit_feed(*, workspace, force_refresh, ttl_minutes):
        called["workspace"] = workspace
        called["force_refresh"] = force_refresh
        called["ttl_minutes"] = ttl_minutes
        return {
            "generated_at_utc": "2026-02-19T00:00:00Z",
            "source": "celestrak",
            "slots": [],
            "errors": [],
            "cache": {"hit": False, "stale": False, "expires_at_utc": None},
        }

    monkeypatch.setattr(
        "experiments.official_daily_ntl_fastpath.orbit_service.build_orbit_feed",
        fake_build_orbit_feed,
    )
    payload = monitor_server.build_orbit_feed_payload({"force_refresh": ["1"], "ttl_minutes": ["200"]})
    assert payload["source"] == "celestrak"
    assert called["force_refresh"] is True
    assert called["ttl_minutes"] == 200


def test_build_orbit_feed_payload_clamps_ttl_non_target_variation(monkeypatch):
    called = {}

    def fake_build_orbit_feed(*, workspace, force_refresh, ttl_minutes):
        called["ttl_minutes"] = ttl_minutes
        return {
            "generated_at_utc": "2026-02-19T00:00:00Z",
            "source": "celestrak",
            "slots": [],
            "errors": [],
            "cache": {"hit": False, "stale": False, "expires_at_utc": None},
        }

    monkeypatch.setattr(
        "experiments.official_daily_ntl_fastpath.orbit_service.build_orbit_feed",
        fake_build_orbit_feed,
    )
    _ = monitor_server.build_orbit_feed_payload({"ttl_minutes": ["1"]})
    assert called["ttl_minutes"] == 10
