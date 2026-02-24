from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from experiments.official_daily_ntl_fastpath.cmr_client import (  # noqa: E402
    extract_download_link,
    resolve_token,
    search_granules,
)
from experiments.official_daily_ntl_fastpath.source_registry import get_source_spec  # noqa: E402


def _parse_bbox(raw_values: list[str]) -> tuple[float, float, float, float]:
    if not raw_values:
        raise ValueError("bbox is required")

    if len(raw_values) == 1:
        parts = [x.strip() for x in raw_values[0].split(",") if x.strip()]
    elif len(raw_values) == 4:
        parts = [x.strip() for x in raw_values]
    else:
        raise ValueError("bbox must be 'minx,miny,maxx,maxy' or four values: minx miny maxx maxy")

    if len(parts) != 4:
        raise ValueError("bbox must be minx,miny,maxx,maxy")

    minx, miny, maxx, maxy = (float(x) for x in parts)
    if maxx < minx or maxy < miny:
        raise ValueError("bbox max must be >= min")
    return minx, miny, maxx, maxy


def _append_query(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    query = parts.query
    addon = urlencode([(key, value)])
    query = f"{query}&{addon}" if query else addon
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def main() -> None:
    parser = argparse.ArgumentParser(description="Open official granule links in browser for manual Earthdata login.")
    parser.add_argument("--source", required=True, help="e.g., VJ146A1, VJ146A1_NRT, VJ102DNB")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--bbox",
        required=True,
        nargs="+",
        help="bbox: either 'minx,miny,maxx,maxy' or four values 'minx miny maxx maxy'",
    )
    parser.add_argument("--max-open", type=int, default=3, help="max links opened in browser")
    parser.add_argument(
        "--with-token-query",
        action="store_true",
        help="append ?token=EARTHDATA_TOKEN for nrt3 links (optional)",
    )
    parser.add_argument(
        "--output",
        default="experiments/official_daily_ntl_fastpath/workspace_monitor/manual_download_links.txt",
        help="output txt path for all generated links",
    )
    args = parser.parse_args()

    spec = get_source_spec(args.source)
    bbox = _parse_bbox(args.bbox)
    granules = search_granules(
        short_name=spec.short_name,
        start_date=args.start_date,
        end_date=args.end_date,
        bbox=bbox,
        page_size=200,
    )
    links: list[str] = []
    token = resolve_token("EARTHDATA_TOKEN") if args.with_token_query else None
    for g in granules:
        link = extract_download_link(g.links)
        if not link:
            continue
        if token and "nrt3.modaps.eosdis.nasa.gov" in link:
            link = _append_query(link, "token", token)
        links.append(link)

    if not links:
        raise RuntimeError("No downloadable links found for given parameters.")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(links), encoding="utf-8")

    to_open = links[: max(1, args.max_open)]
    for u in to_open:
        webbrowser.open(u, new=2)

    print(f"source={args.source}")
    print(f"granules_with_links={len(links)}")
    print(f"opened_tabs={len(to_open)}")
    print(f"links_saved={out_path}")
    print("Next: finish Earthdata login in browser tabs, then download files manually.")


if __name__ == "__main__":
    main()
