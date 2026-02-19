import json
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import requests


MODELS_URL = "https://openrouter.ai/api/v1/models"
RANKINGS_URL = "https://openrouter.ai/rankings"
RANKING_TEST_IDS = [
    "model-rankings-categories-chart",
    "model-rankings-natural-languages-chart",
    "model-rankings-programming-languages-chart",
    "model-rankings-tools-chart",
    "model-rankings-images-chart",
]

# Providers generally recognized as Chinese model vendors on OpenRouter.
DOMESTIC_PROVIDERS = {
    "01-ai",
    "baai",
    "baidu",
    "deepseek",
    "hunyuan",
    "minimax",
    "moonshotai",
    "qwen",
    "stepfun",
    "tencent",
    "xiaomi",
    "z-ai",
}


def usd_per_million(token_price: str) -> float:
    return float(token_price) * 1_000_000


def fetch_models() -> list[dict]:
    resp = requests.get(MODELS_URL, timeout=30)
    resp.raise_for_status()
    return resp.json()["data"]


def parse_chart_points(html: str, test_id: str) -> list[dict]:
    test_id_token = rf'\"testId\":\"{test_id}\"'
    data_token = r'\"data\":['
    test_pos = html.find(test_id_token)
    if test_pos == -1:
        raise RuntimeError(f"Failed to parse rankings testId={test_id}.")
    data_pos = html.rfind(data_token, 0, test_pos)
    if data_pos == -1:
        raise RuntimeError(f"Failed to locate chart data for testId={test_id}.")

    raw = html[data_pos + len(data_token) - 1 : test_pos - 1]
    decoded = raw.encode("utf-8").decode("unicode_escape")
    return json.loads(decoded)


def fetch_latest_ranking() -> tuple[str, dict]:
    html = requests.get(RANKINGS_URL, timeout=30).text
    aggregated: dict[str, float] = {}
    latest_dates: list[str] = []

    for test_id in RANKING_TEST_IDS:
        points = parse_chart_points(html, test_id)
        latest = max(points, key=lambda item: item["x"])
        latest_dates.append(latest["x"])
        for model_id, tokens in latest["ys"].items():
            if model_id == "Others":
                continue
            aggregated[model_id] = aggregated.get(model_id, 0.0) + float(tokens)

    ranking_date = ", ".join(sorted(set(latest_dates)))
    return ranking_date, aggregated


def to_frame(models: list[dict], ranking: dict, ranking_date: str) -> pd.DataFrame:
    model_map = {m["id"]: m for m in models}
    rows = []
    sorted_items = sorted(ranking.items(), key=lambda kv: kv[1], reverse=True)
    rank = 0
    for model_id, tokens in sorted_items:
        if model_id == "Others":
            continue
        rank += 1
        model = model_map.get(model_id)
        if model is None and model_id.endswith(":free"):
            model = model_map.get(model_id.replace(":free", ""))
        pricing = (model or {}).get("pricing", {})
        prompt = float(pricing.get("prompt", "nan"))
        completion = float(pricing.get("completion", "nan"))
        provider = model_id.split("/", 1)[0]
        region = "国内" if provider in DOMESTIC_PROVIDERS else "国外"
        has_price = not pd.isna(prompt) and not pd.isna(completion)

        rows.append(
            {
                "ranking_date": ranking_date,
                "rank_overall": rank,
                "model_id": model_id,
                "model_name": (model or {}).get("name", model_id),
                "provider": provider,
                "region": region,
                "tokens_weekly": float(tokens),
                "prompt_usd_per_1m": usd_per_million(str(prompt)) if has_price else float("nan"),
                "completion_usd_per_1m": usd_per_million(str(completion)) if has_price else float("nan"),
                "avg_usd_per_1m": usd_per_million(str((prompt + completion) / 2)) if has_price else float("nan"),
                "is_free_price": bool(has_price and prompt == 0 and completion == 0),
                "price_available": has_price,
            }
        )

    df = pd.DataFrame(rows).sort_values("rank_overall")
    df["region_rank"] = df.groupby("region")["tokens_weekly"].rank(
        method="first", ascending=False
    )
    return df


def plot_top(df: pd.DataFrame, out_path: Path, top_n: int = 10) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(18, 8), constrained_layout=True)
    for idx, region in enumerate(["国内", "国外"]):
        subset = (
            df[df["region"] == region]
            .sort_values("tokens_weekly", ascending=False)
            .head(top_n)
            .copy()
        )
        if subset.empty:
            axes[idx].set_title(f"{region}模型（无数据）")
            axes[idx].axis("off")
            continue

        labels = subset["model_id"].str.replace(":free", "", regex=False)
        values_b = subset["tokens_weekly"] / 1_000_000_000
        axes[idx].barh(labels[::-1], values_b[::-1], color="#2E86AB" if region == "国内" else "#F18F01")
        title_region = "Domestic (CN)" if region == "国内" else "Global"
        axes[idx].set_title(f"{title_region} Top {len(subset)} by Weekly Tokens")
        axes[idx].set_xlabel("Weekly Tokens (B)")

    fig.suptitle("OpenRouter Hot Models: Domestic vs Global (Rankings)", fontsize=14)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> None:
    now = datetime.now().strftime("%Y-%m-%d")
    out_dir = Path("experiments/openrouter_pricing")
    out_dir.mkdir(parents=True, exist_ok=True)

    models = fetch_models()
    ranking_date, ranking = fetch_latest_ranking()
    df = to_frame(models, ranking, ranking_date)

    full_csv = out_dir / f"openrouter_hot_models_pricing_{now}.csv"
    domestic_csv = out_dir / f"openrouter_hot_models_domestic_top10_{now}.csv"
    global_csv = out_dir / f"openrouter_hot_models_global_top10_{now}.csv"
    chart_png = out_dir / f"openrouter_hot_models_comparison_{now}.png"

    df.to_csv(full_csv, index=False, encoding="utf-8-sig")
    (
        df[df["region"] == "国内"]
        .sort_values("tokens_weekly", ascending=False)
        .head(10)
        .to_csv(domestic_csv, index=False, encoding="utf-8-sig")
    )
    (
        df[df["region"] == "国外"]
        .sort_values("tokens_weekly", ascending=False)
        .head(10)
        .to_csv(global_csv, index=False, encoding="utf-8-sig")
    )
    plot_top(df, chart_png, top_n=10)

    print(f"ranking_date={ranking_date}")
    print(f"saved: {full_csv}")
    print(f"saved: {domestic_csv}")
    print(f"saved: {global_csv}")
    print(f"saved: {chart_png}")


if __name__ == "__main__":
    main()
