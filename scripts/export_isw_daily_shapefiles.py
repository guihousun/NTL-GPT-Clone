"""Export ISW StoryMap event points into one Shapefile set per event date.

Run with:
    conda run -n NTL-Claw-Stable python scripts/export_isw_daily_shapefiles.py

Input:
    docs/ISW_storymap_events_2026-02-27_2026-04-15.csv

Output:
    docs/ISW_daily_shp_2026-02-27_2026-04-07/

The current export groups records by normalized UTC date fields
(`event_date_utc`, falling back to post/publication date). ISW's public
StoryMap coverage label uses U.S. Eastern Time; April dates are EDT / UTC-4.
Use a separate export mode if ET-date or Beijing-date grouping is required.

Each date produces a standard Shapefile component set:
    ISW_YYYYMMDD.shp/.shx/.dbf/.prj/.cpg
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import shapefile


ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = ROOT / "docs" / "ISW_storymap_events_2026-02-27_2026-04-15.csv"
OUTPUT_DIR = ROOT / "docs" / "ISW_daily_shp_2026-02-27_2026-04-07"
INDEX_CSV = OUTPUT_DIR / "daily_shapefile_index.csv"
SKIPPED_CSV = OUTPUT_DIR / "skipped_records.csv"
START_DAY = datetime(2026, 2, 27, tzinfo=timezone.utc).date()
END_DAY = datetime(2026, 4, 7, tzinfo=timezone.utc).date()

WGS84_PRJ = (
    'GEOGCS["WGS 84",DATUM["WGS_1984",'
    'SPHEROID["WGS 84",6378137,298.257223563]],'
    'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'
)

FIELDS = [
    ("SRC_LAYER", "C", 96),
    ("FAMILY", "C", 64),
    ("OBJECTID", "C", 24),
    ("EVENT_ID", "C", 24),
    ("EVT_DATE", "C", 24),
    ("POST_DATE", "C", 24),
    ("PUB_DATE", "C", 24),
    ("EVT_TYPE", "C", 80),
    ("CONFIRMED", "C", 32),
    ("STRUCK", "C", 32),
    ("ACTOR", "C", 80),
    ("SIDE", "C", 32),
    ("SUBJECT", "C", 160),
    ("SITE_TYPE", "C", 80),
    ("SITE_SUB", "C", 96),
    ("CITY", "C", 80),
    ("PROVINCE", "C", 80),
    ("COUNTRY", "C", 80),
    ("COORDTYPE", "C", 32),
    ("SRC1", "C", 254),
    ("SRC2", "C", 254),
    ("SOURCES", "C", 254),
]

FIELD_MAP = {
    "SRC_LAYER": "source_layer",
    "FAMILY": "event_family",
    "OBJECTID": "objectid",
    "EVENT_ID": "event_id",
    "EVT_DATE": "event_date_utc",
    "POST_DATE": "post_date_utc",
    "PUB_DATE": "publication_date_utc",
    "EVT_TYPE": "event_type",
    "CONFIRMED": "confirmed",
    "STRUCK": "struck",
    "ACTOR": "actor",
    "SIDE": "side",
    "SUBJECT": "subject",
    "SITE_TYPE": "site_type",
    "SITE_SUB": "site_subtype",
    "CITY": "city",
    "PROVINCE": "province",
    "COUNTRY": "country",
    "COORDTYPE": "coord_type",
    "SRC1": "source_1",
    "SRC2": "source_2",
    "SOURCES": "sources",
}


def safe_text(value: str | None, length: int) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ").strip()
    return text[:length]


def date_key(row: dict[str, str]) -> tuple[str | None, str]:
    for field in ("event_date_utc", "post_date_utc", "publication_date_utc"):
        value = (row.get(field) or "").strip()
        if not value:
            continue
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d"), field
    return None, "missing_or_invalid_date"


def valid_point(row: dict[str, str]) -> tuple[float, float] | None:
    try:
        lon = float(row.get("longitude") or "")
        lat = float(row.get("latitude") or "")
    except ValueError:
        return None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return lon, lat


def iter_days() -> list[str]:
    days: list[str] = []
    current = START_DAY
    while current <= END_DAY:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def load_groups() -> tuple[dict[str, list[dict[str, str]]], list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    skipped: list[dict[str, str]] = []
    with INPUT_CSV.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key, date_source = date_key(row)
            point = valid_point(row)
            if key is None:
                row["skip_reason"] = date_source
                skipped.append(row)
                continue
            if not (START_DAY.isoformat() <= key <= END_DAY.isoformat()):
                continue
            if point is None:
                row["skip_reason"] = "missing_or_invalid_coordinates"
                skipped.append(row)
                continue
            row["_lon"] = str(point[0])
            row["_lat"] = str(point[1])
            row["_date_source"] = date_source
            grouped[key].append(row)
    for day in iter_days():
        grouped.setdefault(day, [])
    return dict(sorted(grouped.items())), skipped


def write_daily_shapefile(day: str, rows: list[dict[str, str]]) -> Path:
    stem = OUTPUT_DIR / f"ISW_{day.replace('-', '')}"
    writer = shapefile.Writer(str(stem), shapeType=shapefile.POINT)
    writer.autoBalance = 1
    for name, field_type, size in FIELDS:
        writer.field(name, field_type, size=size)

    for row in rows:
        writer.point(float(row["_lon"]), float(row["_lat"]))
        values = []
        for name, _, size in FIELDS:
            source_name = FIELD_MAP[name]
            values.append(safe_text(row.get(source_name), size))
        writer.record(*values)

    writer.close()
    (stem.with_suffix(".prj")).write_text(WGS84_PRJ, encoding="utf-8")
    (stem.with_suffix(".cpg")).write_text("UTF-8", encoding="ascii")
    return stem.with_suffix(".shp")


def write_index(index_rows: list[dict[str, str]]) -> None:
    with INDEX_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "date",
                "record_count",
                "shp",
                "shx",
                "dbf",
                "prj",
                "cpg",
            ],
        )
        writer.writeheader()
        writer.writerows(index_rows)


def write_skipped(skipped_rows: list[dict[str, str]]) -> None:
    if not skipped_rows:
        SKIPPED_CSV.write_text("skip_reason\n", encoding="utf-8")
        return
    fieldnames = ["skip_reason"]
    for row in skipped_rows:
        for key in row:
            if key not in fieldnames and not key.startswith("_"):
                fieldnames.append(key)
    with SKIPPED_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(skipped_rows)


def main() -> None:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(INPUT_CSV)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    grouped, skipped = load_groups()
    index_rows: list[dict[str, str]] = []
    for day, rows in grouped.items():
        shp_path = write_daily_shapefile(day, rows)
        stem = shp_path.with_suffix("")
        index_rows.append(
            {
                "date": day,
                "record_count": str(len(rows)),
                "shp": str(shp_path),
                "shx": str(stem.with_suffix(".shx")),
                "dbf": str(stem.with_suffix(".dbf")),
                "prj": str(stem.with_suffix(".prj")),
                "cpg": str(stem.with_suffix(".cpg")),
            }
        )

    write_index(index_rows)
    write_skipped(skipped)
    print(f"input={INPUT_CSV}")
    print(f"output_dir={OUTPUT_DIR}")
    print(f"daily_files={len(index_rows)}")
    print(f"total_records={sum(int(row['record_count']) for row in index_rows)}")
    print(f"skipped_records={len(skipped)}")
    print(f"index={INDEX_CSV}")
    print(f"skipped={SKIPPED_CSV}")


if __name__ == "__main__":
    main()
