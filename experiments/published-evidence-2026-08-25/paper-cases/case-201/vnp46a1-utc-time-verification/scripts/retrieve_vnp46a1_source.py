"""Retrieve and identity-bind the one official VNP46A1 granule for Q18 timing.

This intentionally uses CMR discovery plus NASA Earthdata bearer authentication,
but stores no token, cookie, or credential material in the experiment package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


TARGET_ID = "VNP46A1.A2025087.h27v06.002.2025088113623.h5"
PRODUCT_DAY = "2025-03-28"
EVENT_BBOX = (95.8, 21.9, 96.1, 22.1)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_identity(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "hdf5_signature_valid": path.read_bytes()[:8] == b"\x89HDF\r\n\x1a\n",
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def download_with_requests(url: str, destination: Path, token: str) -> tuple[bool, dict[str, Any]]:
    """Stream the official HDF5 through requests without persisting credentials."""

    temporary = destination.with_name(f".{destination.name}.part")
    temporary.unlink(missing_ok=True)
    summary: dict[str, Any] = {"transport": "python_requests_bearer"}
    try:
        with requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            stream=True,
            timeout=(30, 600),
        ) as response:
            summary.update(
                {
                    "http_status": response.status_code,
                    "content_type": response.headers.get("Content-Type"),
                    "content_length": response.headers.get("Content-Length"),
                }
            )
            if response.status_code != 200:
                return False, summary
            with temporary.open("wb") as stream:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        stream.write(chunk)
        if temporary.read_bytes()[:8] != b"\x89HDF\r\n\x1a\n":
            summary["hdf5_signature_valid"] = False
            return False, summary
        summary["hdf5_signature_valid"] = True
        temporary.replace(destination)
        return True, summary
    except requests.RequestException as exc:
        summary["error_type"] = type(exc).__name__
        return False, summary
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--token-env", default="EARTHDATA_TOKEN")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve(strict=True)
    source_dir = args.source_dir.resolve()
    source_dir.mkdir(parents=True, exist_ok=True)
    # The shared resolver intentionally searches the active repository dotenv.
    # Run from that root even when this case script is launched elsewhere.
    os.chdir(repo_root)
    sys.path.insert(0, str(repo_root))
    from experiments.official_daily_ntl_fastpath.cmr_client import (  # noqa: PLC0415
        download_file_with_curl,
        extract_download_link,
        resolve_token,
        search_granules,
    )

    manifest_path = source_dir / "source-manifest.json"
    result: dict[str, Any] = {
        "schema_version": "ntl.q18.vnp46a1-source-manifest.v1",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "product": "VNP46A1 Collection 2",
        "short_name": "VNP46A1",
        "utc_product_date": PRODUCT_DAY,
        "target_granule_id": TARGET_ID,
        "cmr_query_bbox_wgs84": list(EVENT_BBOX),
        "authentication": {"token_env": args.token_env, "configured": False},
        "status": "not_started",
    }
    try:
        token = resolve_token(args.token_env)
        result["authentication"]["configured"] = bool(token)
        records = search_granules("VNP46A1", PRODUCT_DAY, PRODUCT_DAY, EVENT_BBOX)
        selected = next((row for row in records if row.producer_granule_id == TARGET_ID), None)
        result["cmr"] = {
            "returned_granule_count": len(records),
            "matching_granule_ids": [row.producer_granule_id for row in records],
            "selected": None,
        }
        if selected is None:
            result["status"] = "target_granule_not_returned_by_cmr"
            write_json(manifest_path, result)
            return 2
        link = extract_download_link(selected.links)
        result["cmr"]["selected"] = {
            "producer_granule_id": selected.producer_granule_id,
            "time_start": selected.time_start,
            "updated": selected.updated,
            "day_night_flag": selected.day_night_flag,
            "official_download_url": link,
        }
        if not token:
            result["status"] = "earthdata_token_not_configured"
            write_json(manifest_path, result)
            return 3
        if not link:
            result["status"] = "cmr_entry_has_no_download_link"
            write_json(manifest_path, result)
            return 4
        target = source_dir / TARGET_ID
        if target.exists() and target.stat().st_size > 0:
            result["download"] = {"status": "reused_existing_verified_candidate", **artifact_identity(target)}
        else:
            previous_cwd = Path.cwd()
            try:
                os.chdir(source_dir)
                ok, detail = download_file_with_curl(link, target, earthdata_token=token, timeout=600)
            finally:
                os.chdir(previous_cwd)
                (source_dir / "session").unlink(missing_ok=True)
            if not ok:
                request_ok, request_detail = download_with_requests(link, target, str(token))
                if not request_ok:
                    result["status"] = "official_download_failed"
                    result["download"] = {
                        "status": "failed",
                        "curl_transport_detail": detail,
                        "requests_fallback": request_detail,
                    }
                    write_json(manifest_path, result)
                    return 5
                result["download"] = {
                    "status": "downloaded_after_curl_transport_failure",
                    **request_detail,
                    **artifact_identity(target),
                }
            else:
                result["download"] = {"status": "downloaded", **artifact_identity(target)}
        if not result["download"]["hdf5_signature_valid"]:
            result["status"] = "download_payload_not_hdf5"
            write_json(manifest_path, result)
            return 6
        result["status"] = "official_hdf5_ready"
        write_json(manifest_path, result)
        return 0
    except Exception as exc:  # noqa: BLE001 - persist a redacted reproducibility state
        result["status"] = "source_retrieval_exception"
        result["error_type"] = type(exc).__name__
        result["error_message"] = str(exc)[:500]
        write_json(manifest_path, result)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
