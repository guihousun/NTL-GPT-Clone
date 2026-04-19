"""Plot ConflictNTL admin-level NTL curves from CSV outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def plot_level(output_dir: Path, level: str, top_n: int) -> None:
    daily_path = output_dir / f"{level}_top{top_n}_daily_ntl.csv"
    units_path = output_dir / f"top{top_n}_{level}_units.csv"
    if not daily_path.exists() or not units_path.exists():
        return
    daily = pd.read_csv(daily_path)
    units = pd.read_csv(units_path)
    if daily.empty:
        return
    daily["observation_date"] = pd.to_datetime(daily["observation_date"])
    fig, axes = plt.subplots(5, 2, figsize=(14, 16), sharex=True)
    axes = axes.ravel()
    for idx, unit in units.head(top_n).iterrows():
        ax = axes[idx]
        name = unit["admin_name"]
        sub = daily[daily["admin_id"] == unit["admin_id"]].sort_values("observation_date")
        if sub.empty:
            ax.text(0.5, 0.5, "No valid days\nunder QA threshold", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(f"{name} ({unit['country']}), n={unit['candidate_event_count']}")
            ax.grid(True, alpha=0.25)
            continue
        ax.plot(sub["observation_date"], sub["mean_ntl"], marker="o", linewidth=1.2, markersize=2.5)
        ax.axvline(pd.Timestamp("2026-02-28"), color="crimson", linestyle="--", linewidth=1)
        ax.axvspan(pd.Timestamp("2026-02-20"), pd.Timestamp("2026-02-27"), color="steelblue", alpha=0.08)
        ax.axvspan(pd.Timestamp("2026-02-28"), pd.Timestamp("2026-04-07"), color="orange", alpha=0.06)
        ax.set_title(f"{name} ({unit['country']}), n={unit['candidate_event_count']}, valid days={sub['observation_date'].nunique()}")
        ax.set_ylabel("Mean NTL")
        ax.grid(True, alpha=0.25)
    for ax in axes:
        ax.tick_params(axis="x", rotation=45)
    fig.suptitle(f"ConflictNTL {level.upper()} Top {top_n} Daily VNP46A1 NTL Curves", y=0.995)
    fig.tight_layout()
    fig.savefig(output_dir / f"fig_{level}_top{top_n}_ntl_curves.png", dpi=220)
    plt.close(fig)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="docs/ConflictNTL_admin_ntl_stats_iran_israel")
    parser.add_argument("--top-n", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out = Path(args.output_dir)
    plot_level(out, "adm1", args.top_n)
    plot_level(out, "adm2", args.top_n)
    print(f"plots written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
