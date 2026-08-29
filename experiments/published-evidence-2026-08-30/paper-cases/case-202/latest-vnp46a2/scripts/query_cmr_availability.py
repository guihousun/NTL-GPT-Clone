"""Record public NASA CMR VNP46A2 availability for the accepted Tehran AOI."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
CMR_URL = "httplocal-path/granules.json"


def product_date(granule_id: str) -> str | None:
    match = re.search(r"\.A(\d{4})(\d{3})\.", granule_id)
    if not match:
        return None
    return datetime.strptime("".join(match.groups()), "%Y%j").date().isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    boundary = json.loads((root / "tehran-boundary-metadata.json").read_text(encoding="utf-8"))
    west, south, east, north = boundary["geometry"]["bbox"]
    params = {
        "short_name": "VNP46A2",
        "bounding_box": f"{west},{south},{east},{north}",
        "temporal": "2026-01-01T00:00:00Z,2026-08-21T23:59:59Z",
        "page_size": 2000,
        "sort_key[]": "-start_date",
    }
    response = requests.get(CMR_URL, params=params, timeout=60)
    response.raise_for_status()
    items = response.json().get("feed", {}).get("entry", [])
    rows = []
    for item in items:
        granule_id = str(item.get("producer_granule_id") or "")
        rows.append(
            {
                "granule_id": granule_id,
                "product_date_utc": product_date(granule_id),
                "time_start": item.get("time_start"),
                "related_urls": [
                    link.get("href")
                    for link in item.get("links", [])
                    if isinstance(link, dict) and link.get("href")
                ],
            }
        )
    dated_rows = [row for row in rows if row["product_date_utc"]]
    payload = {
        "schema_version": "ntl.case202.cmr-availability.v1",
        "queried_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "NASA CMR public granule metadata API",
        "http_status": response.status_code,
        "query": params,
        "matched_granule_count": len(rows),
        "latest_product_date_utc": max((row["product_date_utc"] for row in dated_rows), default=None),
        "latest_granules": dated_rows[:10],
        "interpretation": "CMR establishes public granule availability for the AOI/tile query. It does not prove AOI-level strict-QA eligibility; the GEE daily reduction remains authoritative for that decision.",
    }
    destination = root / "qa" / "cmr-availability.json"
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"matched_granules": len(rows), "latest_product_date_utc": payload["latest_product_date_utc"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
