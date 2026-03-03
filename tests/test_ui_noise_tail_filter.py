from app_ui import _is_noise_tail_text


def test_noise_tail_filter_variants():
    assert _is_noise_tail_text("undefined")
    assert _is_noise_tail_text(" NULL ")
    assert _is_noise_tail_text("none")
    assert _is_noise_tail_text("")


def test_noise_tail_filter_keeps_real_text():
    assert not _is_noise_tail_text("supported")
    assert not _is_noise_tail_text("{\"status\":\"ok\"}")
