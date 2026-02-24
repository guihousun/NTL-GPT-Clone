from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from .orbit_registry import OrbitCandidate, OrbitSlot, get_orbit_slots


CELESTRAK_GP_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR={catnr}&FORMAT=TLE"
ROGUE_TLE_JSON_URL = "https://sky.rogue.space/TLE.json"
SLOT_POLICY_VERSION = "nightlight_only_no_fallback_v1"


@dataclass(frozen=True)
class TleRecord:
    catnr: int
    name: str
    line1: str
    line2: str
    epoch_utc: str | None


FetchTleFunc = Callable[[OrbitCandidate], tuple[TleRecord | None, str | None]]


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _extract_tle_epoch_utc(line1: str) -> str | None:
    if not line1 or len(line1) < 32:
        return None
    raw = line1[18:32].strip()
    if not raw:
        return None
    try:
        year2 = int(raw[:2])
        day_of_year = float(raw[2:])
    except ValueError:
        return None
    year = 2000 + year2 if year2 < 57 else 1900 + year2
    base = datetime(year, 1, 1, tzinfo=UTC)
    dt = base + timedelta(days=day_of_year - 1)
    return _iso_utc(dt)


def _parse_tle_payload(text: str) -> tuple[str | None, str | None, str | None]:
    raw = (text or "").strip()
    if not raw:
        return None, None, None
    if "No GP data found" in raw:
        return None, None, None
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None, None, None
    if lines[0].startswith("1 ") and lines[1].startswith("2 "):
        return "UNKNOWN", lines[0], lines[1]
    if len(lines) >= 3 and lines[1].startswith("1 ") and lines[2].startswith("2 "):
        return lines[0], lines[1], lines[2]
    return None, None, None


def fetch_tle_from_celestrak(candidate: OrbitCandidate, timeout: int = 30) -> tuple[TleRecord | None, str | None]:
    url = CELESTRAK_GP_URL.format(catnr=candidate.catnr)
    req = Request(url, headers={"User-Agent": "NTL-Fast-Monitor/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310
            text = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        return None, f"fetch_error CATNR {candidate.catnr}: {exc}"
    name, line1, line2 = _parse_tle_payload(text)
    if not line1 or not line2:
        return None, f"no_gp_data CATNR {candidate.catnr}"
    epoch = _extract_tle_epoch_utc(line1)
    return (
        TleRecord(
            catnr=candidate.catnr,
            name=candidate.name if name in {None, "UNKNOWN"} else name,
            line1=line1,
            line2=line2,
            epoch_utc=epoch,
        ),
        None,
    )


def _parse_catnr_from_line1(line1: str) -> int | None:
    if not line1:
        return None
    match = re.match(r"^1\s+(\d{5})", line1.strip())
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def fetch_tle_catalog_from_rogue(timeout: int = 40) -> dict[int, TleRecord]:
    req = Request(ROGUE_TLE_JSON_URL, headers={"User-Agent": "NTL-Fast-Monitor/1.0"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    if not isinstance(payload, list):
        raise ValueError("rogue_tle_json_invalid_payload")
    records: dict[int, TleRecord] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        line1 = str(item.get("TLE_LINE1") or "").strip()
        line2 = str(item.get("TLE_LINE2") or "").strip()
        if not line1.startswith("1 ") or not line2.startswith("2 "):
            continue
        catnr = _parse_catnr_from_line1(line1)
        if catnr is None:
            continue
        name = str(item.get("OBJECT_NAME") or "").strip() or f"NORAD {catnr}"
        epoch = _extract_tle_epoch_utc(line1)
        records[catnr] = TleRecord(
            catnr=catnr,
            name=name,
            line1=line1,
            line2=line2,
            epoch_utc=epoch,
        )
    if not records:
        raise ValueError("rogue_tle_json_empty")
    return records


def build_fetcher_from_rogue_catalog(timeout: int = 40) -> FetchTleFunc:
    catalog = fetch_tle_catalog_from_rogue(timeout=timeout)

    def _fetch(candidate: OrbitCandidate) -> tuple[TleRecord | None, str | None]:
        record = catalog.get(candidate.catnr)
        if record is None:
            return None, f"no_rogue_tle CATNR {candidate.catnr}"
        return record, None

    return _fetch


def _resolve_slot(slot: OrbitSlot, fetch_tle_func: FetchTleFunc) -> tuple[dict[str, object], list[str]]:
    errors: list[str] = []
    candidates = (slot.requested, *slot.fallbacks)
    requested = slot.requested
    for idx, candidate in enumerate(candidates):
        record, err = fetch_tle_func(candidate)
        if err:
            errors.append(err)
            continue
        if not record:
            errors.append(f"empty_tle CATNR {candidate.catnr}")
            continue
        replaced = idx > 0
        return (
            {
                "slot_id": slot.slot_id,
                "slot_label_zh": slot.slot_label_zh,
                "slot_label_en": slot.slot_label_en,
                "requested_catnr": requested.catnr,
                "requested_name": requested.name,
                "effective_catnr": record.catnr,
                "effective_name": record.name,
                "replaced": replaced,
                "replace_reason": (
                    f"missing requested TLE; fallback to {record.name} ({record.catnr})"
                    if replaced
                    else None
                ),
                "tle_line1": record.line1,
                "tle_line2": record.line2,
                "tle_epoch_utc": record.epoch_utc,
                "status": "fallback" if replaced else "ok",
            },
            errors,
        )

    return (
        {
            "slot_id": slot.slot_id,
            "slot_label_zh": slot.slot_label_zh,
            "slot_label_en": slot.slot_label_en,
            "requested_catnr": requested.catnr,
            "requested_name": requested.name,
            "effective_catnr": None,
            "effective_name": None,
            "replaced": False,
            "replace_reason": "no usable TLE in requested/fallback chain",
            "tle_line1": None,
            "tle_line2": None,
            "tle_epoch_utc": None,
            "status": "unavailable",
        },
        errors,
    )


def _cache_path(workspace: Path) -> Path:
    return workspace / "cache" / "orbit_feed.json"


def _is_cache_compatible(payload: dict[str, object]) -> bool:
    if str(payload.get("slot_policy") or "") != SLOT_POLICY_VERSION:
        return False
    slots = payload.get("slots")
    if not isinstance(slots, list):
        return False
    expected = [x.slot_id for x in get_orbit_slots()]
    got = [str(x.get("slot_id")) for x in slots if isinstance(x, dict)]
    return got == expected


def _wrap_cache(payload: dict[str, object], *, hit: bool, stale: bool, ttl_minutes: int) -> dict[str, object]:
    out = copy.deepcopy(payload)
    generated_at = str(out.get("generated_at_utc") or "")
    expires_at_utc = None
    try:
        if generated_at:
            dt = datetime.strptime(generated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            expires_at_utc = _iso_utc(dt + timedelta(minutes=ttl_minutes))
    except ValueError:
        expires_at_utc = None
    out["cache"] = {
        "hit": hit,
        "stale": stale,
        "expires_at_utc": expires_at_utc,
    }
    return out


def _is_cache_fresh(payload: dict[str, object], ttl_minutes: int, now_utc: datetime) -> bool:
    generated_at = str(payload.get("generated_at_utc") or "")
    try:
        dt = datetime.strptime(generated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return False
    return (now_utc - dt) <= timedelta(minutes=ttl_minutes)


def _mark_slots_stale(payload: dict[str, object]) -> dict[str, object]:
    out = copy.deepcopy(payload)
    slots = out.get("slots")
    if not isinstance(slots, list):
        return out
    for row in slots:
        if not isinstance(row, dict):
            continue
        if row.get("status") in {"ok", "fallback"}:
            row["status"] = "stale"
    return out


def build_orbit_feed(
    workspace: Path,
    *,
    force_refresh: bool = False,
    ttl_minutes: int = 180,
    fetch_tle_func: FetchTleFunc | None = None,
) -> dict[str, object]:
    ttl = max(10, min(1440, int(ttl_minutes)))
    cache_path = _cache_path(workspace)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    now_utc = _now_utc()
    cached_payload = _safe_read_json(cache_path) if cache_path.exists() else None

    if isinstance(cached_payload, dict) and not _is_cache_compatible(cached_payload):
        cached_payload = None

    if not force_refresh and isinstance(cached_payload, dict):
        if _is_cache_fresh(cached_payload, ttl_minutes=ttl, now_utc=now_utc):
            return _wrap_cache(cached_payload, hit=True, stale=False, ttl_minutes=ttl)

    source_name = "custom_fetcher"
    startup_errors: list[str] = []
    if fetch_tle_func is not None:
        fetcher = fetch_tle_func
    else:
        try:
            fetcher = build_fetcher_from_rogue_catalog(timeout=40)
            source_name = "rogue_sky_tle_json"
        except Exception as exc:  # noqa: BLE001
            fetcher = fetch_tle_from_celestrak
            source_name = "celestrak_fallback"
            startup_errors.append(f"rogue_fetch_failed: {exc}")

    slots_payload: list[dict[str, object]] = []
    errors: list[str] = list(startup_errors)
    for slot in get_orbit_slots():
        row, slot_errors = _resolve_slot(slot, fetch_tle_func=fetcher)
        slots_payload.append(row)
        errors.extend(slot_errors)

    all_unavailable = all(str(x.get("status")) == "unavailable" for x in slots_payload)
    if all_unavailable:
        if isinstance(cached_payload, dict):
            stale_payload = _mark_slots_stale(cached_payload)
            stale_errors = list(stale_payload.get("errors") or [])
            stale_errors.extend(errors)
            stale_payload["errors"] = stale_errors
            return _wrap_cache(stale_payload, hit=True, stale=True, ttl_minutes=ttl)
        raise RuntimeError("orbit_feed_unavailable: no usable TLE data and no cache")

    fresh_payload: dict[str, object] = {
        "generated_at_utc": _iso_utc(now_utc),
        "source": source_name,
        "slot_policy": SLOT_POLICY_VERSION,
        "slots": slots_payload,
        "errors": errors,
    }
    cache_path.write_text(json.dumps(fresh_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return _wrap_cache(fresh_payload, hit=False, stale=False, ttl_minutes=ttl)
