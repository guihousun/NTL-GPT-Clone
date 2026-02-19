from experiments.official_daily_ntl_fastpath.run_fast_daily_ntl import compute_lead_days


def test_compute_lead_days_with_valid_dates():
    assert compute_lead_days("2026-02-11", "2026-02-10") == 1
    assert compute_lead_days("2026-02-10", "2026-02-11") == -1


def test_compute_lead_days_handles_missing_values():
    assert compute_lead_days(None, "2026-02-10") is None
    assert compute_lead_days("2026-02-11", None) is None

