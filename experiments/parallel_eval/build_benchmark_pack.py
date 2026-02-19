#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List

import pandas as pd


def _normalize_text(v) -> str:
    if pd.isna(v):
        return ""
    return str(v).strip()


def load_appendix_cases(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, header=None)
    rows: List[Dict] = []
    for i in range(len(raw)):
        idx = raw.iat[i, 0]
        if isinstance(idx, (int, float)) and not pd.isna(idx):
            row = {
                "id": int(idx),
                "category": _normalize_text(raw.iat[i, 1]),
                "label": _normalize_text(raw.iat[i, 2]),
                "case": _normalize_text(raw.iat[i, 3]),
                "gpt41_a1": _normalize_text(raw.iat[i, 4]),
                "gpt41_a2": _normalize_text(raw.iat[i, 5]),
                "gpt41_a3": _normalize_text(raw.iat[i, 6]),
                "gpt41_s": _normalize_text(raw.iat[i, 7]),
                "gpt41m_a1": _normalize_text(raw.iat[i, 11]),
                "gpt41m_a2": _normalize_text(raw.iat[i, 12]),
                "gpt41m_a3": _normalize_text(raw.iat[i, 13]),
                "gpt41m_s": _normalize_text(raw.iat[i, 14]),
                "qwen_a1": _normalize_text(raw.iat[i, 18]),
                "qwen_a2": _normalize_text(raw.iat[i, 19]),
                "qwen_a3": _normalize_text(raw.iat[i, 20]),
                "qwen_s": _normalize_text(raw.iat[i, 21]),
            }
            rows.append(row)

    df = pd.DataFrame(rows).sort_values("id").reset_index(drop=True)

    attempt_cols = [
        "gpt41_a1",
        "gpt41_a2",
        "gpt41_a3",
        "gpt41m_a1",
        "gpt41m_a2",
        "gpt41m_a3",
        "qwen_a1",
        "qwen_a2",
        "qwen_a3",
    ]
    status_cols = ["gpt41_s", "gpt41m_s", "qwen_s"]

    df["fail_models"] = (df[status_cols] == "N").sum(axis=1)
    df["hallucination_models"] = (df[attempt_cols] == "H").sum(axis=1)
    df["execution_error_models"] = (df[attempt_cols] == "E").sum(axis=1)
    df["difficulty_score"] = (
        df["fail_models"] * 5
        + (df["hallucination_models"] > 0).astype(int) * 2
        + (df["execution_error_models"] > 0).astype(int) * 2
    )
    df["priority_level"] = "normal"
    df.loc[df["difficulty_score"] >= 5, "priority_level"] = "high"
    df.loc[df["difficulty_score"] >= 8, "priority_level"] = "critical"
    return df


def load_test_cases(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path)
    id_col = "Unnamed: 0" if "Unnamed: 0" in df.columns else "id"
    out = pd.DataFrame(
        {
            "id": pd.to_numeric(df[id_col], errors="coerce"),
            "category": df.get("Category", "").fillna("").astype(str).str.strip(),
            "label": df.get("Label", "").fillna("").astype(str).str.strip(),
            "case": df.get("Case", "").fillna("").astype(str).str.strip(),
        }
    )
    out = out[out["id"].notna() & out["case"].ne("")].copy()
    out["id"] = out["id"].astype(int)
    return out.sort_values("id").reset_index(drop=True)


def build_shards(df: pd.DataFrame, workers: int) -> Dict[int, pd.DataFrame]:
    work_df = df.sort_values(["difficulty_score", "id"], ascending=[False, True]).reset_index(drop=True)
    loads = [{"score": 0, "count": 0, "rows": []} for _ in range(workers)]

    for _, row in work_df.iterrows():
        # Balance case count first, then difficulty score.
        target = min(range(workers), key=lambda i: (loads[i]["count"], loads[i]["score"]))
        loads[target]["rows"].append(row.to_dict())
        loads[target]["score"] += int(row["difficulty_score"])
        loads[target]["count"] += 1

    shards = {}
    for i, load in enumerate(loads, start=1):
        shard_df = pd.DataFrame(load["rows"]).sort_values("id").reset_index(drop=True)
        shard_df["shard_id"] = i
        shards[i] = shard_df
    return shards


def main() -> None:
    parser = argparse.ArgumentParser(description="Build benchmark pack for parallel NTL-GPT/Codex evaluation.")
    parser.add_argument("--appendix", default="Appendix B. Supplementary materials.xlsx")
    parser.add_argument("--test-cases", default="test_cases.xlsx")
    parser.add_argument("--out-dir", default="experiments/parallel_eval/benchmark")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    appendix_df = load_appendix_cases(Path(args.appendix))
    current_df = load_test_cases(Path(args.test_cases))

    current_ids = set(current_df["id"].tolist())
    missing_df = appendix_df[~appendix_df["id"].isin(current_ids)].copy()
    hard_df = appendix_df[(appendix_df["priority_level"].isin(["high", "critical"])) | (appendix_df["category"].str.contains("modeling", case=False))].copy()

    appendix_df.to_csv(out_dir / "canonical_70_cases.csv", index=False, encoding="utf-8-sig")
    current_df.to_csv(out_dir / "current_test_cases_44.csv", index=False, encoding="utf-8-sig")
    missing_df.to_csv(out_dir / "missing_26_cases.csv", index=False, encoding="utf-8-sig")
    hard_df.to_csv(out_dir / "priority_hard_cases.csv", index=False, encoding="utf-8-sig")

    shards = build_shards(appendix_df[["id", "category", "label", "case", "difficulty_score", "priority_level"]], args.workers)
    for sid, shard_df in shards.items():
        shard_df.to_csv(out_dir / f"shard_{sid:02d}.csv", index=False, encoding="utf-8-sig")

    summary = {
        "canonical_cases": int(len(appendix_df)),
        "current_cases": int(len(current_df)),
        "missing_cases": int(len(missing_df)),
        "hard_cases": int(len(hard_df)),
        "workers": int(args.workers),
    }
    pd.DataFrame([summary]).to_csv(out_dir / "benchmark_pack_summary.csv", index=False, encoding="utf-8-sig")

    print("Benchmark pack generated at:", out_dir)
    print(summary)


if __name__ == "__main__":
    main()
