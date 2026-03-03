from experiments.official_daily_ntl_fastpath.orbit_registry import get_orbit_slots


def test_orbit_registry_has_five_fixed_slots():
    slots = get_orbit_slots()
    ids = [x.slot_id for x in slots]
    assert ids == ["snpp_viirs", "noaa20_viirs", "noaa21_viirs", "sdgsat1", "luojia_slot"]


def test_luojia_slot_keeps_nightlight_only_policy_non_target_variation():
    slots = get_orbit_slots()
    luojia = next(x for x in slots if x.slot_id == "luojia_slot")
    assert luojia.requested.catnr == 43035
    assert [x.catnr for x in luojia.fallbacks] == []
