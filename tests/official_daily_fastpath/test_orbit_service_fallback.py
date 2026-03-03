from pathlib import Path

from experiments.official_daily_ntl_fastpath.orbit_registry import OrbitCandidate
from experiments.official_daily_ntl_fastpath.orbit_service import TleRecord, build_orbit_feed


_L1 = "1 37849U 11061A   26049.85327343  .00000081  00000+0  59383-4 0  9996"
_L2 = "2 37849  98.7848 351.6082 0001052 355.0526   5.0639 14.19537743741656"


def _ok_record(candidate: OrbitCandidate) -> TleRecord:
    return TleRecord(
        catnr=candidate.catnr,
        name=candidate.name,
        line1=_L1,
        line2=_L2,
        epoch_utc="2026-02-18T20:28:42Z",
    )


def test_build_orbit_feed_marks_luojia_unavailable_without_fallback(tmp_path: Path):
    def fake_fetch(candidate: OrbitCandidate):
        if candidate.catnr == 43035:
            return None, "no_gp_data CATNR 43035"
        return _ok_record(candidate), None

    payload = build_orbit_feed(
        workspace=tmp_path,
        force_refresh=True,
        ttl_minutes=180,
        fetch_tle_func=fake_fetch,
    )

    slots = payload["slots"]
    luojia = next(x for x in slots if x["slot_id"] == "luojia_slot")
    assert luojia["status"] == "unavailable"
    assert luojia["replaced"] is False
    assert luojia["effective_catnr"] is None
    ok_count = sum(1 for x in slots if x["status"] in {"ok", "fallback"})
    assert ok_count >= 4


def test_build_orbit_feed_returns_stale_cache_when_source_temporarily_down(tmp_path: Path):
    def ok_fetch(candidate: OrbitCandidate):
        if candidate.catnr == 43035:
            return None, "no_gp_data CATNR 43035"
        return _ok_record(candidate), None

    _ = build_orbit_feed(
        workspace=tmp_path,
        force_refresh=True,
        ttl_minutes=180,
        fetch_tle_func=ok_fetch,
    )

    def all_fail(_candidate: OrbitCandidate):
        return None, "network_down"

    stale = build_orbit_feed(
        workspace=tmp_path,
        force_refresh=True,
        ttl_minutes=180,
        fetch_tle_func=all_fail,
    )
    assert stale["cache"]["hit"] is True
    assert stale["cache"]["stale"] is True
    assert any(x["status"] == "stale" for x in stale["slots"])
