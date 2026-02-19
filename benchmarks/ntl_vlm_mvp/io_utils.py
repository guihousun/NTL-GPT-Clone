"""I/O helpers for benchmark artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_scene_manifest(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet" and path.exists():
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv" and path.exists():
        return pd.read_csv(path)
    if path.suffix.lower() == ".parquet" and path.with_suffix(".csv").exists():
        # Fallback for environments missing parquet engines.
        return pd.read_csv(path.with_suffix(".csv"))
    raise FileNotFoundError(f"scene manifest not found at {path}")


def write_scene_manifest(df: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    try:
        df.to_parquet(path, index=False)
    except Exception as exc:
        fallback = path.with_suffix(".csv")
        df.to_csv(fallback, index=False, encoding="utf-8-sig")
        raise RuntimeError(
            f"failed to write parquet at {path}; wrote fallback CSV at {fallback}. "
            "Install pyarrow or fastparquet to enable parquet output."
        ) from exc


def read_task_file(path: Path) -> pd.DataFrame:
    rows = read_jsonl(path)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def write_dataframe_csv(df: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    df.to_csv(path, index=False, encoding="utf-8-sig")

