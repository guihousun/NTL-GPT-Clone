import app_logic


def test_should_recover_stale_run_when_heartbeat_expired():
    now = 1_000.0
    assert app_logic.should_recover_stale_run(
        is_running=True,
        run_started_ts=100.0,
        heartbeat_ts=200.0,
        now_ts=now,
        grace_s=300,
    ) is True


def test_should_not_recover_when_heartbeat_recent():
    now = 1_000.0
    assert app_logic.should_recover_stale_run(
        is_running=True,
        run_started_ts=900.0,
        heartbeat_ts=950.0,
        now_ts=now,
        grace_s=300,
    ) is False


def test_should_recover_stale_run_with_missing_heartbeat_but_old_start():
    now = 1_000.0
    assert app_logic.should_recover_stale_run(
        is_running=True,
        run_started_ts=100.0,
        heartbeat_ts=None,
        now_ts=now,
        grace_s=300,
    ) is True


def test_should_not_recover_when_not_running():
    assert app_logic.should_recover_stale_run(
        is_running=False,
        run_started_ts=0.0,
        heartbeat_ts=0.0,
        now_ts=1_000.0,
        grace_s=300,
    ) is False
