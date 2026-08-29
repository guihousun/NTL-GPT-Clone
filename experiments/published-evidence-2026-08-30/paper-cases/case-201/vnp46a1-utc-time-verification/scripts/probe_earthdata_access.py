"""Record safe, credential-redacted access probes for the selected granule."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


TARGET_URL = "httplocal-path/VNP46A1.A2025087.h27v06.002.2025088113623.h5"
OPENDAP_PAGE = "httplocal-path/VNP46A1.A2025087.h27v06.002.2025088113623.h5.html"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve(strict=True)
    sys.path.insert(0, str(repo_root))
    os.chdir(repo_root)
    from experiments.official_daily_ntl_fastpath.cmr_client import resolve_token  # noqa: PLC0415

    token = resolve_token("EARTHDATA_TOKEN")
    record = {
        "schema_version": "ntl.q18.earthdata-access-probe.v1",
        "queried_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_url": TARGET_URL,
        "authentication": {"token_env": "EARTHDATA_TOKEN", "configured": bool(token)},
    }
    try:
        response = requests.get(
            TARGET_URL,
            headers={"Authorization": f"Bearer {token}"} if token else {},
            stream=True,
            timeout=(30, 180),
        )
        first_chunk = next(response.iter_content(16), b"")
        record["official_hdf5_download_probe"] = {
            "http_status": response.status_code,
            "content_type": response.headers.get("Content-Type"),
            "content_length": response.headers.get("Content-Length"),
            "hdf5_signature_observed": first_chunk.startswith(b"\x89HDF\r\n\x1a\n"),
        }
        response.close()
    except requests.RequestException as exc:
        record["official_hdf5_download_probe"] = {"error_type": type(exc).__name__}
    try:
        response = requests.get(OPENDAP_PAGE, timeout=(30, 90))
        title_match = re.search(r"<title>(.*?)</title>", response.text, flags=re.IGNORECASE | re.DOTALL)
        record["opendap_metadata_probe"] = {
            "http_status": response.status_code,
            "page_title": title_match.group(1).strip() if title_match else None,
            "utc_time_metadata_visible_without_login": "UTC_Time" in response.text,
        }
        response.close()
    except requests.RequestException as exc:
        record["opendap_metadata_probe"] = {"error_type": type(exc).__name__}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
