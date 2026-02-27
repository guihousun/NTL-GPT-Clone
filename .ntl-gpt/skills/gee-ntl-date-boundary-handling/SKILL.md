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

### 2) Safe collection builder
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

### 3) Robust reduction
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

### 4) No-data guard
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

