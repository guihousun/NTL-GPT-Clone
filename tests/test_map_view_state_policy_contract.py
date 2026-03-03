from pathlib import Path

from map_view_policy import advance_map_view_state, build_layer_signature


def test_map_policy_first_open_skips_switch_and_starts_nonce_zero():
    opened_once = {}
    last_sig = {}
    reset_nonce = {}
    sig = build_layer_signature([Path("inputs/a.tif")])

    result = advance_map_view_state(
        thread_id="thread-a",
        layer_signature=sig,
        opened_once_by_thread=opened_once,
        last_layer_sig_by_thread=last_sig,
        reset_nonce_by_thread=reset_nonce,
    )

    assert result["is_first_open"] is True
    assert result["is_layer_switched"] is False
    assert result["map_nonce"] == 0


def test_map_policy_switch_increments_nonce_only_when_signature_changes():
    opened_once = {}
    last_sig = {}
    reset_nonce = {}
    sig_a = build_layer_signature([Path("inputs/a.tif")])
    sig_b = build_layer_signature([Path("inputs/b.tif")])

    advance_map_view_state(
        thread_id="thread-a",
        layer_signature=sig_a,
        opened_once_by_thread=opened_once,
        last_layer_sig_by_thread=last_sig,
        reset_nonce_by_thread=reset_nonce,
    )
    same = advance_map_view_state(
        thread_id="thread-a",
        layer_signature=sig_a,
        opened_once_by_thread=opened_once,
        last_layer_sig_by_thread=last_sig,
        reset_nonce_by_thread=reset_nonce,
    )
    switched = advance_map_view_state(
        thread_id="thread-a",
        layer_signature=sig_b,
        opened_once_by_thread=opened_once,
        last_layer_sig_by_thread=last_sig,
        reset_nonce_by_thread=reset_nonce,
    )

    assert same["is_first_open"] is False
    assert same["is_layer_switched"] is False
    assert same["map_nonce"] == 0
    assert switched["is_first_open"] is False
    assert switched["is_layer_switched"] is True
    assert switched["map_nonce"] == 1


def test_layer_signature_is_order_invariant_and_supports_vector_raster_variants():
    sig_vector_raster = build_layer_signature([Path("outputs/zone.shp"), Path("inputs/light.tif")])
    sig_reordered = build_layer_signature([Path("inputs/light.tif"), Path("outputs/zone.shp")])
    sig_empty = build_layer_signature([])

    assert sig_vector_raster == sig_reordered
    assert isinstance(sig_empty, str) and len(sig_empty) == 40
