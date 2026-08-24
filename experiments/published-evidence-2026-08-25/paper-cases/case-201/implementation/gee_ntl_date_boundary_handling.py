"""Generic, testable companion for the GEE NTL Date & Boundary Handling skill.

This module is scoped to the Case 201 evidence package.  It does not call GEE,
download data, or choose a fallback observation date.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


UTC = timezone.utc


@dataclass(frozen=True)
class LocalNightDecision:
    event_time_utc: str
    event_time_local: str
    timezone: str
    candidate_window_start_local: str
    candidate_window_end_local: str
    local_first_night_date: str | None
    status: str

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def parse_utc(iso_utc: str) -> datetime:
    value = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("event time must contain an explicit UTC offset")
    return value.astimezone(UTC)


def inclusive_end_to_exclusive(date_iso: str) -> str:
    return (datetime.fromisoformat(date_iso).date() + timedelta(days=1)).isoformat()


def local_time_context(event_time_utc: str, timezone_name: str) -> datetime:
    return parse_utc(event_time_utc).astimezone(ZoneInfo(timezone_name))


def determine_first_post_event_local_night(
    event_time_utc: str,
    timezone_name: str,
    candidate_start_local: time,
    candidate_end_local: time,
) -> LocalNightDecision:
    """Choose local-night date only when the event is clearly outside its window.

    If the event occurs within the candidate acquisition window, precise product
    metadata is required; this function intentionally returns no date rather
    than inventing an answer.
    """
    if candidate_end_local <= candidate_start_local:
        raise ValueError("candidate window must not cross local midnight")
    event_local = local_time_context(event_time_utc, timezone_name)
    start = datetime.combine(event_local.date(), candidate_start_local, tzinfo=event_local.tzinfo)
    end = datetime.combine(event_local.date(), candidate_end_local, tzinfo=event_local.tzinfo)
    if event_local < start:
        first_night = event_local.date()
        status = "resolved_before_candidate_window"
    elif event_local >= end:
        first_night = event_local.date() + timedelta(days=1)
        status = "resolved_after_candidate_window"
    else:
        first_night = None
        status = "needs_exact_acquisition_time"
    return LocalNightDecision(
        event_time_utc=parse_utc(event_time_utc).isoformat().replace("+00:00", "Z"),
        event_time_local=event_local.isoformat(),
        timezone=timezone_name,
        candidate_window_start_local=start.isoformat(),
        candidate_window_end_local=end.isoformat(),
        local_first_night_date=first_night.isoformat() if first_night else None,
        status=status,
    )


def utc_product_date_for_local_night(
    local_night_date: str,
    timezone_name: str,
    candidate_start_local: time,
    candidate_end_local: time,
) -> dict[str, str | None]:
    """Map a local candidate acquisition window to a UTC-indexed product day."""
    if candidate_end_local <= candidate_start_local:
        raise ValueError("candidate window must not cross local midnight")
    local_tz = ZoneInfo(timezone_name)
    local_day = datetime.fromisoformat(local_night_date).date()
    start_local = datetime.combine(local_day, candidate_start_local, tzinfo=local_tz)
    end_local = datetime.combine(local_day, candidate_end_local, tzinfo=local_tz)
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)
    if start_utc.date() != end_utc.date():
        status = "needs_product_metadata"
        product_date = None
    else:
        status = "resolved_utc_indexed_product_date"
        product_date = start_utc.date().isoformat()
    return {
        "local_first_night_date": local_day.isoformat(),
        "candidate_start_local": start_local.isoformat(),
        "candidate_end_local": end_local.isoformat(),
        "candidate_start_utc": start_utc.isoformat().replace("+00:00", "Z"),
        "candidate_end_utc": end_utc.isoformat().replace("+00:00", "Z"),
        "utc_product_date": product_date,
        "status": status,
    }


def exact_date_eligibility(
    utc_product_date: str,
    available_and_eligible_dates: dict[str, bool],
) -> dict[str, str | bool]:
    """Gate the exact first-night product date without later-date fallback."""
    if utc_product_date not in available_and_eligible_dates:
        return {
            "utc_product_date": utc_product_date,
            "status": "no_available_first_night_product",
            "eligible": False,
        }
    if not available_and_eligible_dates[utc_product_date]:
        return {
            "utc_product_date": utc_product_date,
            "status": "no_eligible_first_night_observation",
            "eligible": False,
        }
    return {
        "utc_product_date": utc_product_date,
        "status": "eligible_first_night_observation",
        "eligible": True,
    }
