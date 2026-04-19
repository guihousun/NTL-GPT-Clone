"""Count unique VNP46A1 granules for selected country ADM0 bounding boxes."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.official_daily_ntl_fastpath.cmr_client import extract_download_link, search_granules


DEFAULT_BOUNDARY_DIR = ROOT / "docs" / "geoboundaries_irn_isr_all_levels"
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "ConflictNTL_vnp46a1_stats_iran_israel_bbox"
COUNTRIES = {
    "IRN": "Iran",
    "ISR": "Israel",
}


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def drange(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def iter_coords(obj: Any):
    if isinstance(obj, (list, tuple)):
        if len(obj) >= 2 and all(isinstance(v, (int, float)) for v in obj[:2]):
            yield float(obj[0]), float(obj[1])
        else:
            for item in obj:
                yield from iter_coords(item)


def geojson_bbox(path: Path) -> tuple[float, float, float, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    xs: list[float] = []
    ys: list[float] = []
    for feature in payload.get("features", []):
        geom = feature.get("geometry") or {}
        for x, y in iter_coords(geom.get("coordinates")):
            xs.append(x)
            ys.append(y)
    if not xs or not ys:
        raise RuntimeError(f"No coordinates found in {path}")
    return min(xs), min(ys), max(xs), max(ys)


def tile_id(granule_id: str) -> str:
    match = re.search(r"\.(h\d{2}v\d{2})\.", granule_id or "")
    return match.group(1) if match else ""


def count_country(iso3: str, name: str, bbox: tuple[float, float, float, float], start: date, end: date, page_size: int):
    rows: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []
    for day in drange(start, end):
        day_s = day.isoformat()
        try:
            granules = search_granules("VNP46A1", day_s, day_s, bbox, page_size=page_size)
        except Exception as exc:
            failures.append({"iso3": iso3, "country": name, "date": day_s, "error_message": str(exc)})
            continue
        for granule in granules:
            key = granule.producer_granule_id
            link = extract_download_link(granule.links) or ""
            rows.setdefault(
                key,
                {
                    "iso3": iso3,
                    "country": name,
                    "date": granule.time_start[:10],
                    "producer_granule_id": key,
                    "tile_id": tile_id(key),
                    "time_start": granule.time_start,
                    "updated": granule.updated or "",
                    "download_url": link,
                },
            )
    return list(rows.values()), failures


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({k for row in rows for k in row})
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2026-02-20")
    parser.add_argument("--end-date", default="2026-04-10")
    parser.add_argument("--boundary-dir", default=str(DEFAULT_BOUNDARY_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--page-size", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start = parse_date(args.start_date)
    end = parse_date(args.end_date)
    boundary_dir = Path(args.boundary_dir)
    output_dir = Path(args.output_dir)

    all_rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    summary: list[dict[str, Any]] = []
    country_bboxes: dict[str, tuple[float, float, float, float]] = {}

    for iso3, name in COUNTRIES.items():
        boundary = boundary_dir / f"{iso3.lower()}_geoboundaries_adm0.geojson"
        bbox = geojson_bbox(boundary)
        country_bboxes[iso3] = bbox
        rows, country_failures = count_country(iso3, name, bbox, start, end, args.page_size)
        all_rows.extend(rows)
        failures.extend(country_failures)
        summary.append(
            {
                "iso3": iso3,
                "country": name,
                "bbox": ",".join(f"{v:.6f}" for v in bbox),
                "unique_granules": len({r["producer_granule_id"] for r in rows}),
                "unique_tiles": len({r["tile_id"] for r in rows}),
                "tiles": ";".join(sorted({r["tile_id"] for r in rows})),
            }
        )

    union_ids = {row["producer_granule_id"] for row in all_rows}
    union_tiles = {row["tile_id"] for row in all_rows}
    summary.append(
        {
            "iso3": "IRN+ISR",
            "country": "Iran + Israel",
            "bbox": "",
            "unique_granules": len(union_ids),
            "unique_tiles": len(union_tiles),
            "tiles": ";".join(sorted(union_tiles)),
        }
    )

    write_csv(output_dir / "country_granule_manifest.csv", all_rows)
    write_csv(output_dir / "country_granule_summary.csv", summary)
    write_csv(output_dir / "country_granule_query_failures.csv", failures)
    (output_dir / "run_summary.json").write_text(
        json.dumps(
            {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "country_bboxes": {k: list(v) for k, v in country_bboxes.items()},
                "summary": summary,
                "query_failures": len(failures),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"output_dir": str(output_dir), "summary": summary, "query_failures": len(failures)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
