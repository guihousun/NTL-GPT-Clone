from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .gee_baseline import DEFAULT_GEE_PROJECT

_CACHE_TTL = timedelta(hours=6)
_CACHE: dict[tuple[str, str], tuple[datetime, dict[str, Any]]] = {}


def _normalize_name_list(values: list[Any], limit: int = 500) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item is None:
            continue
        text = str(item).strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        names.append(text)
    names.sort(key=lambda x: x.casefold())
    return names[: max(1, min(limit, 2000))]


def _init_ee() -> None:
    import ee

    try:
        ee.Initialize(project=DEFAULT_GEE_PROJECT)
    except Exception:
        ee.Initialize()


def _fetch_names(collection_id: str, field_name: str, filters: dict[str, str], limit: int) -> list[str]:
    import ee

    fc = ee.FeatureCollection(collection_id)
    for k, v in filters.items():
        if v:
            fc = fc.filter(ee.Filter.eq(k, v))
    names = fc.aggregate_array(field_name).getInfo() or []
    return _normalize_name_list(names, limit=limit)


def get_study_area_catalog(
    *,
    country: str | None = None,
    province: str | None = None,
    limit: int = 2000,
) -> dict[str, Any]:
    c = (country or "").strip()
    p = (province or "").strip()
    key = (c, p)
    now = datetime.now(UTC)

    if key in _CACHE:
        ts, payload = _CACHE[key]
        if now - ts <= _CACHE_TTL:
            return payload

    _init_ee()

    countries = _fetch_names("FAO/GAUL/2015/level0", "ADM0_NAME", {}, limit=limit)
    provinces = _fetch_names("FAO/GAUL/2015/level1", "ADM1_NAME", {"ADM0_NAME": c}, limit=limit) if c else []
    cities = (
        _fetch_names(
            "FAO/GAUL/2015/level2",
            "ADM2_NAME",
            {"ADM0_NAME": c, "ADM1_NAME": p},
            limit=limit,
        )
        if c and p
        else []
    )

    payload: dict[str, Any] = {
        "source": "FAO/GAUL/2015",
        "country": c or None,
        "province": p or None,
        "countries": countries,
        "provinces": provinces,
        "cities": cities,
        "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _CACHE[key] = (now, payload)
    return payload
