"""Download VNP46A1 HDF5 granules from a manifest with terminal progress.

The script is intended for large LAADS/Earthdata downloads. It keeps files
outside the repository by default and shows curl's progress bar for each
granule when run in a terminal.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.official_daily_ntl_fastpath.cmr_client import (  # noqa: E402
    download_file_with_curl,
    resolve_token,
    validate_download_payload,
)


DEFAULT_MANIFEST = ROOT / "docs" / "ConflictNTL_vnp46a1_stats_iran_israel_bbox" / "country_granule_manifest.csv"
DEFAULT_OUTPUT_DIR = Path(r"E:\VNP46A1")
LAADS_ARCHIVE_SET = "5200"


def read_manifest(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row.get("producer_granule_id") or row.get("download_url")
        if not key:
            continue
        deduped.setdefault(key, row)
    return list(deduped.values())


def output_path(row: dict[str, Any], output_dir: Path) -> Path:
    url = str(row.get("download_url") or "").strip()
    filename = Path(url.split("?")[0]).name if url else str(row.get("producer_granule_id") or "").strip()
    if not filename.endswith(".h5"):
        filename = f"{filename}.h5"
    date = str(row.get("date") or "unknown_date").strip() or "unknown_date"
    tile = str(row.get("tile_id") or "unknown_tile").strip() or "unknown_tile"
    return output_dir / date / tile / filename


def laads_archive_url(row: dict[str, Any]) -> str | None:
    """Build the stable LAADS archive URL for VNP46A1.

    CMR may return Earthdata Cloud URLs that reject otherwise valid EDL tokens.
    The LAADS archive path follows the official allData layout and works with
    the same bearer-token download flow.
    """
    granule_id = str(row.get("producer_granule_id") or "").strip()
    if not granule_id.startswith("VNP46A1.A"):
        return None
    parts = granule_id.split(".")
    if len(parts) < 2 or len(parts[1]) < 8 or not parts[1].startswith("A"):
        return None
    acq = parts[1][1:]
    year = acq[:4]
    doy = acq[4:7]
    if not (year.isdigit() and doy.isdigit()):
        return None
    return (
        "https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/"
        f"{LAADS_ARCHIVE_SET}/VNP46A1/{year}/{doy}/{granule_id}"
    )


def select_download_url(row: dict[str, Any], use_manifest_url: bool = False) -> str:
    if not use_manifest_url:
        archive = laads_archive_url(row)
        if archive:
            return archive
    return str(row.get("download_url") or "").strip()


def already_valid(path: Path) -> bool:
    if not path.exists() or path.stat().st_size <= 0:
        return False
    ok, _reason = validate_download_payload(path)
    return bool(ok)


def write_status(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "producer_granule_id",
        "date",
        "tile_id",
        "download_url",
        "local_path",
        "status",
        "error_message",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="CSV manifest with download_url rows.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for downloaded HDF5 files.")
    parser.add_argument("--token-env", default="EARTHDATA_TOKEN", help="Environment/.env token variable name.")
    parser.add_argument("--status-csv", default="", help="Optional output status CSV path.")
    parser.add_argument("--limit", type=int, default=0, help="Download only the first N unique granules.")
    parser.add_argument("--start-date", default="", help="Optional inclusive acquisition date filter, YYYY-MM-DD.")
    parser.add_argument("--end-date", default="", help="Optional inclusive acquisition date filter, YYYY-MM-DD.")
    parser.add_argument("--shard-count", type=int, default=1, help="Split the manifest into N disjoint shards.")
    parser.add_argument("--shard-index", type=int, default=0, help="Zero-based shard index to download.")
    parser.add_argument("--timeout", type=int, default=1800, help="Per-file timeout in seconds.")
    parser.add_argument("--force", action="store_true", help="Re-download even if an existing valid file is found.")
    parser.add_argument("--no-progress", action="store_true", help="Disable curl progress bar.")
    parser.add_argument(
        "--use-manifest-url",
        action="store_true",
        help="Use the manifest download_url instead of the derived LAADS archive URL.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = Path(args.manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    rows = read_manifest(manifest)
    if args.start_date:
        rows = [row for row in rows if str(row.get("date") or "") >= args.start_date]
    if args.end_date:
        rows = [row for row in rows if str(row.get("date") or "") <= args.end_date]
    if args.shard_count < 1:
        raise ValueError("--shard-count must be >= 1")
    if args.shard_index < 0 or args.shard_index >= args.shard_count:
        raise ValueError("--shard-index must satisfy 0 <= shard-index < shard-count")
    if args.shard_count > 1:
        rows = [row for idx, row in enumerate(rows) if idx % args.shard_count == args.shard_index]
    if args.limit:
        rows = rows[: args.limit]

    token = resolve_token(args.token_env)
    if not token:
        raise RuntimeError(f"Missing Earthdata token. Set {args.token_env} in the environment or .env file.")

    status_rows: list[dict[str, Any]] = []
    total = len(rows)
    ok_count = 0
    skip_count = 0
    fail_count = 0

    print(
        json.dumps(
            {
                "manifest": str(manifest),
                "output_dir": str(output_dir),
                "granules": total,
                "shard_index": args.shard_index,
                "shard_count": args.shard_count,
            },
            ensure_ascii=False,
        )
    )
    for idx, row in enumerate(rows, start=1):
        url = select_download_url(row, use_manifest_url=args.use_manifest_url)
        local = output_path(row, output_dir)
        status = {
            "producer_granule_id": row.get("producer_granule_id", ""),
            "date": row.get("date", ""),
            "tile_id": row.get("tile_id", ""),
            "download_url": url,
            "local_path": str(local),
            "status": "",
            "error_message": "",
        }
        print(f"\n[{idx}/{total}] {status['producer_granule_id']} -> {local}")
        if not url:
            status.update({"status": "failed", "error_message": "missing download_url"})
            fail_count += 1
            status_rows.append(status)
            continue
        if not args.force and already_valid(local):
            print("skip: existing valid HDF5")
            status.update({"status": "skipped_existing_valid"})
            skip_count += 1
            status_rows.append(status)
            continue
        ok, err = download_file_with_curl(
            url=url,
            output_path=local,
            earthdata_token=token,
            timeout=args.timeout,
            show_progress=not args.no_progress,
        )
        if ok:
            status.update({"status": "downloaded"})
            ok_count += 1
        else:
            status.update({"status": "failed", "error_message": err})
            fail_count += 1
            print(f"failed: {err}")
        status_rows.append(status)

    if args.status_csv:
        status_csv = Path(args.status_csv).resolve()
    elif args.shard_count > 1:
        status_csv = output_dir / f"download_status_shard{args.shard_index}_of_{args.shard_count}.csv"
    else:
        status_csv = output_dir / "download_status.csv"
    write_status(status_csv, status_rows)
    summary = {
        "downloaded": ok_count,
        "skipped_existing_valid": skip_count,
        "failed": fail_count,
        "status_csv": str(status_csv),
    }
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if fail_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
