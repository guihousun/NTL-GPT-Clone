from pathlib import Path

from experiments.official_daily_ntl_fastpath.orbit_registry import OrbitCandidate
from experiments.official_daily_ntl_fastpath.orbit_service import TleRecord, build_orbit_feed


_L2 = "2 37849  98.7848 351.6082 0001052 355.0526   5.0639 14.19537743741656"


def _record(catnr: int, name: str) -> TleRecord:
    l1 = f"1 {catnr:05d}U 11061A   26049.85327343  .00000081  00000+0  59383-4 0  9996"
    return TleRecord(
        catnr=catnr,
        name=name,
        line1=l1,
        line2=_L2,
        epoch_utc="2026-02-18T20:28:42Z",
    )


def test_build_orbit_feed_prefers_rogue_catalog(monkeypatch, tmp_path: Path):
    def fake_catalog(timeout: int = 40):
        _ = timeout
        return {
            37849: _record(37849, "NPP"),
            43013: _record(43013, "NOAA 20"),
            54234: _record(54234, "NOAA 21"),
            49387: _record(49387, "SDGSAT 1"),
        }

    def should_not_call_celestrak(candidate: OrbitCandidate, timeout: int = 30):  # noqa: ARG001
        raise AssertionError("celestrak fallback should not be called when rogue catalog succeeds")

    monkeypatch.setattr(
        "experiments.official_daily_ntl_fastpath.orbit_service.fetch_tle_catalog_from_rogue",
        fake_catalog,
    )
    monkeypatch.setattr(
        "experiments.official_daily_ntl_fastpath.orbit_service.fetch_tle_from_celestrak",
        should_not_call_celestrak,
    )

    payload = build_orbit_feed(workspace=tmp_path, force_refresh=True, ttl_minutes=180)
    assert payload["source"] == "rogue_sky_tle_json"
    slots = payload["slots"]
    ok_count = sum(1 for x in slots if x["status"] == "ok")
    assert ok_count == 4
    luojia = next(x for x in slots if x["slot_id"] == "luojia_slot")
    assert luojia["status"] == "unavailable"


def test_build_orbit_feed_falls_back_to_celestrak_when_rogue_fails_non_target_variation(monkeypatch, tmp_path: Path):
    def fail_catalog(timeout: int = 40):  # noqa: ARG001
        raise RuntimeError("network_down")

    def fake_celestrak(candidate: OrbitCandidate, timeout: int = 30):  # noqa: ARG001
        if candidate.catnr == 43035:
            return None, "no_gp_data CATNR 43035"
        return _record(candidate.catnr, candidate.name), None

    monkeypatch.setattr(
        "experiments.official_daily_ntl_fastpath.orbit_service.fetch_tle_catalog_from_rogue",
        fail_catalog,
    )
    monkeypatch.setattr(
        "experiments.official_daily_ntl_fastpath.orbit_service.fetch_tle_from_celestrak",
        fake_celestrak,
    )

    payload = build_orbit_feed(workspace=tmp_path, force_refresh=True, ttl_minutes=180)
    assert payload["source"] == "celestrak_fallback"
    assert any("rogue_fetch_failed" in str(x) for x in payload["errors"])
    ok_count = sum(1 for x in payload["slots"] if x["status"] == "ok")
    assert ok_count >= 4
