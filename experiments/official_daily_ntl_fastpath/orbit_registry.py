from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrbitCandidate:
    catnr: int
    name: str


@dataclass(frozen=True)
class OrbitSlot:
    slot_id: str
    slot_label_zh: str
    slot_label_en: str
    requested: OrbitCandidate
    fallbacks: tuple[OrbitCandidate, ...] = ()


_ORBIT_SLOTS: tuple[OrbitSlot, ...] = (
    OrbitSlot(
        slot_id="snpp_viirs",
        slot_label_zh="Suomi-NPP (VIIRS)",
        slot_label_en="Suomi-NPP (VIIRS)",
        requested=OrbitCandidate(catnr=37849, name="SUOMI NPP"),
    ),
    OrbitSlot(
        slot_id="noaa20_viirs",
        slot_label_zh="NOAA-20 (VIIRS)",
        slot_label_en="NOAA-20 (VIIRS)",
        requested=OrbitCandidate(catnr=43013, name="NOAA 20"),
    ),
    OrbitSlot(
        slot_id="noaa21_viirs",
        slot_label_zh="NOAA-21 (VIIRS)",
        slot_label_en="NOAA-21 (VIIRS)",
        requested=OrbitCandidate(catnr=54234, name="NOAA 21"),
    ),
    OrbitSlot(
        slot_id="sdgsat1",
        slot_label_zh="可持续发展科学卫星1号 (SDGSAT-1)",
        slot_label_en="SDGSAT-1",
        requested=OrbitCandidate(catnr=49387, name="SDGSAT 1"),
    ),
    OrbitSlot(
        slot_id="luojia_slot",
        slot_label_zh="珞珈一号 01 星",
        slot_label_en="LUOJIA-1 01",
        requested=OrbitCandidate(catnr=43035, name="LUOJIA 1-01"),
    ),
)


def get_orbit_slots() -> tuple[OrbitSlot, ...]:
    return _ORBIT_SLOTS


def get_orbit_slot(slot_id: str) -> OrbitSlot:
    key = (slot_id or "").strip().lower()
    for slot in _ORBIT_SLOTS:
        if slot.slot_id == key:
            return slot
    raise ValueError(f"Unknown orbit slot id: {slot_id}")
