"""Inspect VNP46A1 HDF5 metadata for observation time fields.

Usage:
    conda run -n NTL-Claw-Stable python scripts/inspect_vnp46a1_time_metadata.py <path.h5>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np


TIME_KEYWORDS = (
    "time",
    "date",
    "orbit",
    "range",
    "begin",
    "ending",
    "calendar",
    "production",
    "localgranule",
)


def decode_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        if value.shape == ():
            return decode_value(value.item())
        return [decode_value(item) for item in value.tolist()]
    return value


def collect_attrs(obj: h5py.Group | h5py.Dataset) -> dict[str, Any]:
    return {key: decode_value(value) for key, value in obj.attrs.items()}


def walk_hdf(path: Path) -> dict[str, Any]:
    datasets: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    time_attrs: dict[str, dict[str, Any]] = {}

    with h5py.File(path, "r") as h5:
        root_attrs = collect_attrs(h5)

        def visitor(name: str, obj: h5py.Group | h5py.Dataset) -> None:
            attrs = collect_attrs(obj)
            lower_name = name.lower()
            matched_attrs = {
                key: value
                for key, value in attrs.items()
                if any(token in key.lower() for token in TIME_KEYWORDS)
            }
            if any(token in lower_name for token in TIME_KEYWORDS) or matched_attrs:
                time_attrs[name or "/"] = matched_attrs or attrs

            if isinstance(obj, h5py.Dataset):
                info = {
                    "path": name,
                    "shape": obj.shape,
                    "dtype": str(obj.dtype),
                    "attrs": attrs,
                }
                datasets.append(info)
            elif isinstance(obj, h5py.Group):
                groups.append({"path": name, "attrs": attrs})

        h5.visititems(visitor)

    return {
        "file": str(path),
        "root_attrs": root_attrs,
        "groups": groups,
        "datasets": datasets,
        "time_related_attrs": time_attrs,
    }


def summarize(report: dict[str, Any]) -> None:
    print("file:", report["file"])
    print("root_attr_count:", len(report["root_attrs"]))
    print("group_count:", len(report["groups"]))
    print("dataset_count:", len(report["datasets"]))

    print("\nROOT TIME-LIKE ATTRS")
    for key, value in report["root_attrs"].items():
        if any(token in key.lower() for token in TIME_KEYWORDS):
            print(f"{key}: {value}")

    print("\nTIME-RELATED OBJECT ATTRS")
    for path, attrs in report["time_related_attrs"].items():
        print(f"[{path}]")
        for key, value in attrs.items():
            print(f"  {key}: {value}")

    print("\nDATASETS")
    for item in report["datasets"]:
        print(f"{item['path']} shape={item['shape']} dtype={item['dtype']}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/inspect_vnp46a1_time_metadata.py <path.h5>")
    path = Path(sys.argv[1])
    report = walk_hdf(path)
    out = path.with_suffix(path.suffix + ".time_metadata.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    summarize(report)
    print("\njson_report:", out)


if __name__ == "__main__":
    main()
