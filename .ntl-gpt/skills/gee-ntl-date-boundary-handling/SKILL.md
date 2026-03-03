---
name: gee-ntl-date-boundary-handling
description: Handle GEE NTL date windows, first-night selection, AOI boundary constraints, and robust reduction settings for event impact analysis.
---

# GEE NTL Date & Boundary Handling

## Purpose
Prevent common failure modes in GEE nighttime light analysis:
- Wrong date window due to `filterDate` end-date exclusivity.
- Missing first-night image after daytime events.
- AOI mismatch from unverified bbox.
- Unstable reduction from missing `scale/maxPixels/tileScale`.

## When To Use
Use this skill when task includes any of:
- `VNP46A2` / `VIIRS` daily analysis.
- Event impact assessment (`pre-event`, `first-night`, `post-event`).
- Buffer-based ANTL statistics around epicenter.
- GEE server-side reduction (`reduceRegion`/`reduceRegions`).

## Non-Negotiable Rules
1. `filterDate(start, end)` is end-exclusive.
2. For single-day query, always use `end = start + 1 day`.
3. If event occurs after local VIIRS overpass (~01:30 local), `first_night = D+1`.
4. Prefer confirmed administrative boundary; avoid ad-hoc bbox for named regions.
5. Always set `scale` and `maxPixels` in reductions.
6. For large AOI, add `bestEffort=True` or `tileScale>1`.

## Execution Checklist
1. Confirm event local time and timezone.
2. Determine first-night date using overpass rule.
3. Build period windows:
   - baseline: event-14d to event-7d
   - first-night: D+1 (or short fallback window D+1..D+3)
   - recovery: event+7d to event+14d
4. Use inclusive-end helper for all date windows.
5. Use validated AOI (admin boundary / confirmed geometry).
6. Run reductions with explicit safety parameters.
7. Return structured logs for image counts and no-data periods.

## Reusable Snippets

### 1) Inclusive date helper
```python
from datetime import datetime, timedelta

def to_exclusive_end(date_str: str) -> str:
    return (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

# Example: single day 2025-03-29
# filterDate("2025-03-29", to_exclusive_end("2025-03-29"))
```

### 2) Timezone-aware first-night calculation
```python
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    from backports.zoneinfo import ZoneInfo  # Python < 3.9

def get_first_night_date(event_date_str: str, event_time_local: str, 
                         timezone_str: str, overpass_hour: int = 1, overpass_minute: int = 30):
    """
    Determine first-night image date based on VIIRS overpass timing.
    
    VIIRS overpass time: ~01:30 local time (varies by latitude)
    
    Rule: If event occurs AFTER local overpass on day D, first-night = D+1
          If event occurs BEFORE local overpass on day D, first-night = D
    
    Parameters:
    - event_date_str: 'YYYY-MM-DD'
    - event_time_local: 'HH:MM' (24-hour format, local time)
    - timezone_str: e.g., 'Asia/Shanghai', 'America/New_York'
    - overpass_hour, overpass_minute: VIIRS overpass time (default 01:30)
    
    Returns:
    - first_night_date: 'YYYY-MM-DD'
    """
    tz = ZoneInfo(timezone_str)
    event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
    event_time = datetime.strptime(event_time_local, "%H:%M").time()
    
    # Event datetime in local timezone
    event_dt = datetime.combine(event_date, event_time, tzinfo=tz)
    
    # Overpass time on the same calendar day
    overpass_dt = datetime.combine(event_date, 
                                    datetime.strptime(f"{overpass_hour:02d}:{overpass_minute:02d}", "%H:%M").time(),
                                    tzinfo=tz)
    
    # If event is after overpass, first night is next day
    if event_dt > overpass_dt:
        first_night = event_date + timedelta(days=1)
    else:
        first_night = event_date
    
    return first_night.strftime("%Y-%m-%d")

# Example: Myanmar earthquake 2025-03-29 15:30 (Asia/Yangon)
# overpass at 01:30, event at 15:30 -> after overpass -> first_night = 2025-03-30
# first_night = get_first_night_date("2025-03-29", "15:30", "Asia/Yangon")
# print(first_night)  # Output: 2025-03-30
```

### 3) Timezone conversion helper
```python
from datetime import datetime
from zoneinfo import ZoneInfo

def convert_timezone(datetime_str: str, from_tz: str, to_tz: str, 
                     fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Convert datetime from one timezone to another.
    
    Parameters:
    - datetime_str: datetime string in from_tz
    - from_tz: source timezone (e.g., 'Asia/Shanghai')
    - to_tz: target timezone (e.g., 'UTC')
    - fmt: datetime format string
    
    Returns:
    - Converted datetime string in to_tz
    """
    dt_naive = datetime.strptime(datetime_str, fmt)
    dt_from = dt_naive.replace(tzinfo=ZoneInfo(from_tz))
    dt_to = dt_from.astimezone(ZoneInfo(to_tz))
    return dt_to.strftime(fmt)

# Example: Convert local event time to UTC for GEE filter
# utc_time = convert_timezone("2025-03-29 15:30:00", "Asia/Yangon", "UTC")
```

### 4) Safe collection builder
```python
def load_vnp46a2(start_date: str, end_date_inclusive: str, geom):
    end_exclusive = to_exclusive_end(end_date_inclusive)
    return (
        ee.ImageCollection("NASA/VIIRS/002/VNP46A2")
        .filterDate(start_date, end_exclusive)
        .filterBounds(geom)
        .select("Gap_Filled_DNB_BRDF_Corrected_NTL")
    )
```

### 5) Robust reduction
```python
def mean_antl(image, geom):
    stats = image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geom,
        scale=500,
        maxPixels=1e13,
        bestEffort=True,
        tileScale=2,
    )
    return stats.get("Gap_Filled_DNB_BRDF_Corrected_NTL")
```

### 6) No-data guard
```python
collection = load_vnp46a2(start_date, end_date, geom)
count = collection.size().getInfo()
if count == 0:
    return {"status": "no_data", "image_count": 0}
```

## Boundary Strategy
- Preferred: confirmed administrative geometry from retrieval stage.
- Allowed fallback: epicenter buffers for impact analysis.
- Avoid: unnamed hardcoded bbox for named-city/province tasks.
- If AOI uncertainty exists, request boundary confirmation instead of guessing.

## Output Contract (Recommended)
Return at least:
- `period_name`, `start_date`, `end_date`, `image_count`, `status`
- `buffer_name` or `region_id`
- `antl_mean` (and optional `antl_std`)
- `notes` (first-night rule, timezone decision, boundary source)

## Case-Derived Guidance
From successful Myanmar impact runs in this workspace:
- First-night selection must be explicit and justified by local overpass timing.
- Buffer-based ANTL (25/50/100 km) is robust when admin boundaries are unavailable.
- `scale=500 + maxPixels + tileScale` significantly reduces reduction failures.

## Anti-Patterns
- `filterDate("2025-03-29", "2025-03-29")` (always empty).
- Running long loops with excessive `getInfo()` calls where server-side map/reduce is possible.
- Unbounded retries on no-data periods without window adjustment.
- Writing outputs via hardcoded absolute paths.

