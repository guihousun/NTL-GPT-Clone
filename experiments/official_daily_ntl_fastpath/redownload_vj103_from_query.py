from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Redownload VJ103DNB files from a LAADS query JSON using EARTHDATA token."
    )
    parser.add_argument("--query-json", required=True, help="Path to LAADS query JSON.")
    parser.add_argument("--output-dir", required=True, help="Output folder.")
    parser.add_argument(
        "--token-env",
        default="EARTHDATA_TOKEN",
        help="Environment variable name containing Earthdata bearer token.",
    )
    parser.add_argument(
        "--skip-existing-binary",
        action="store_true",
        help="Skip file if existing and not HTML.",
    )
    return parser.parse_args()


def looks_like_html(path: Path) -> bool:
    try:
        head = path.read_bytes()[:256].lower()
    except Exception:
        return True
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def main() -> None:
    args = parse_args()
    load_dotenv()

    token = (os.getenv(args.token_env) or "").strip()
    if not token:
        raise RuntimeError(f"Missing token in env: {args.token_env}")

    query_path = Path(args.query_json).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads(query_path.read_text(encoding="utf-8"))
    urls: list[str] = []
    for v in payload.values():
        if isinstance(v, dict) and "url" in v:
            url = str(v["url"])
            name = url.split("/")[-1]
            if name.startswith("VJ103DNB."):
                urls.append(url)

    if not urls:
        print("No VJ103DNB URLs found.")
        return

    ok = 0
    bad = 0
    skipped = 0
    for i, url in enumerate(urls, start=1):
        name = url.split("/")[-1]
        dst = out_dir / name

        if args.skip_existing_binary and dst.exists() and not looks_like_html(dst):
            skipped += 1
            print(f"[{i}/{len(urls)}] skip(existing): {name}")
            continue

        tmp = dst.with_suffix(dst.suffix + ".part")
        try:
            with requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                stream=True,
                timeout=120,
                allow_redirects=True,
            ) as r:
                r.raise_for_status()
                with tmp.open("wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
        except Exception as exc:  # noqa: BLE001
            bad += 1
            tmp.unlink(missing_ok=True)
            print(f"[{i}/{len(urls)}] fail: {name} :: {str(exc)[:180]}")
            continue
        tmp.replace(dst)
        if looks_like_html(dst):
            bad += 1
            print(f"[{i}/{len(urls)}] fail(html): {name}")
            continue
        ok += 1
        print(f"[{i}/{len(urls)}] ok: {name}")

    print(f"done total={len(urls)} ok={ok} bad={bad} skipped={skipped}")


if __name__ == "__main__":
    main()
