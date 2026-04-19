"""Export ISW StoryMap ArcGIS layer renderer/legend metadata.

The event extractor stores feature attributes and geometries. This companion
script records the ArcGIS layer renderer so the visual/event classification
used by ISW can be cited and reproduced in the ConflictNTL workflow.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

STORYMAP_URL = "https://storymaps.arcgis.com/stories/089bc1a2fe684405a67d67f13bd31324"
OUTPUT_JSON = DOCS / "ISW_storymap_layer_renderer_legend.json"
OUTPUT_CSV = DOCS / "ISW_storymap_layer_renderer_legend.csv"
OUTPUT_MD = DOCS / "ISW_storymap_layer_renderer_legend.md"

LAYERS = [
    {
        "name": "combined_force_strikes_on_iran_2026",
        "label": "View Combined Force Strikes on Iran 2026",
        "event_family": "us_israel_combined_force_strike",
        "url": "https://services5.arcgis.com/SaBe5HMtmnbqSWlu/arcgis/rest/services/MDS_CF_Strikes_on_Iran_2026_view/FeatureServer/0",
    },
    {
        "name": "iran_axis_retaliatory_strikes_2026",
        "label": "View Iran Axis Retaliatory Strikes 2026",
        "event_family": "iran_axis_retaliatory_strike",
        "url": "https://services5.arcgis.com/SaBe5HMtmnbqSWlu/arcgis/rest/services/View_Iran_Axis_Retaliatory_Strikes_2026/FeatureServer/0",
    },
]

CSV_FIELDS = [
    "source_storymap_url",
    "layer_name",
    "layer_label",
    "layer_url",
    "event_family",
    "arcgis_layer_name",
    "renderer_type",
    "renderer_field1",
    "renderer_field2",
    "renderer_field3",
    "value",
    "label",
    "description",
    "symbol_type",
    "symbol_style",
    "symbol_color_rgba",
    "symbol_outline_color_rgba",
    "symbol_size",
    "symbol_width",
]


def request_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    query = urlencode(params or {})
    full_url = f"{url}?{query}" if query else url
    with urlopen(full_url, timeout=90) as response:
        return json.load(response)


def rgba(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return ",".join(str(part) for part in value)


def flatten_unique_value_info(layer: dict[str, str], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    renderer = (metadata.get("drawingInfo") or {}).get("renderer") or {}
    rows: list[dict[str, Any]] = []
    for item in renderer.get("uniqueValueInfos") or []:
        symbol = item.get("symbol") or {}
        outline = symbol.get("outline") or {}
        rows.append(
            {
                "source_storymap_url": STORYMAP_URL,
                "layer_name": layer["name"],
                "layer_label": layer["label"],
                "layer_url": layer["url"],
                "event_family": layer["event_family"],
                "arcgis_layer_name": metadata.get("name", ""),
                "renderer_type": renderer.get("type", ""),
                "renderer_field1": renderer.get("field1", ""),
                "renderer_field2": renderer.get("field2", ""),
                "renderer_field3": renderer.get("field3", ""),
                "value": item.get("value", ""),
                "label": item.get("label", ""),
                "description": item.get("description", ""),
                "symbol_type": symbol.get("type", ""),
                "symbol_style": symbol.get("style", ""),
                "symbol_color_rgba": rgba(symbol.get("color")),
                "symbol_outline_color_rgba": rgba(outline.get("color")),
                "symbol_size": symbol.get("size", ""),
                "symbol_width": outline.get("width", ""),
            }
        )
    return rows


def write_csv(rows: list[dict[str, Any]]) -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_md(payload: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = [
        "# ISW StoryMap 图例与 Renderer 分类",
        "",
        f"更新时间：`{payload['retrieved_at_utc']}`",
        "",
        "本文档记录 ISW / CTP ArcGIS StoryMap 图层自身的 `drawingInfo.renderer` 分类。它不是 NTL-Claw 自行推断的分类，而是 ArcGIS 图层元数据中用于地图符号化的字段和值。",
        "",
        f"StoryMap：{STORYMAP_URL}",
        "",
        "## 图层分类摘要",
        "",
        "| 图层 | renderer 类型 | 分类字段 | 分类值数量 | 含义 |",
        "|---|---|---|---:|---|",
    ]
    for layer in payload["layers"]:
        renderer = layer.get("renderer") or {}
        fields = [renderer.get("field1"), renderer.get("field2"), renderer.get("field3")]
        field_text = " / ".join(field for field in fields if field) or ""
        meaning = (
            "按事件类型区分空袭、爆炸报告、防空活动和撤离通知。"
            if field_text == "event_type"
            else "按袭击方/阵营区分伊朗及轴心相关袭击来源。"
        )
        lines.append(
            f"| {layer['label']} | `{renderer.get('type', '')}` | `{field_text}` | {len(layer.get('legend_values') or [])} | {meaning} |"
        )

    lines.extend(
        [
            "",
            "## 具体分类值",
            "",
            "| 图层 | 分类字段 | value | label |",
            "|---|---|---|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['layer_label']} | `{row['renderer_field1']}` | `{row['value']}` | {row['label']} |"
        )

    lines.extend(
        [
            "",
            "## 在当前实验中的用法",
            "",
            "- 第一层 `Combined Force Strikes on Iran 2026` 的图例字段是 `event_type`。这可以直接服务第一轮筛选和第二轮夜光适用性判断，例如区分 `Confirmed Airstrike`、`Reported Airstrike`、`Report of Explosion with Footage`、`Air Defense Activity`。",
            "- 第二层 `Iran Axis Retaliatory Strikes 2026` 的图例字段是 `side`。它主要用于冲突方语义和来源分组，不直接决定夜光适用性。",
            "- 当前 NTL 候选筛选仍以事件属性字段为准，尤其是 `event_type`、`site_type`、`site_subtype`、`coord_type` 和来源字段。renderer 作为 ISW 原始分类证据保存，用于增强 workflow 可复现性。",
            "- 若 ISW 后续修改图层符号化，需要重新运行 `scripts/extract_isw_storymap_legend.py` 并更新本文件。",
            "",
            "## 输出文件",
            "",
            f"- JSON：`{OUTPUT_JSON.as_posix()}`",
            f"- CSV：`{OUTPUT_CSV.as_posix()}`",
            f"- Markdown：`{OUTPUT_MD.as_posix()}`",
            "",
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload_layers: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    for layer in LAYERS:
        metadata = request_json(layer["url"], {"f": "pjson"})
        renderer = (metadata.get("drawingInfo") or {}).get("renderer") or {}
        layer_rows = flatten_unique_value_info(layer, metadata)
        rows.extend(layer_rows)
        payload_layers.append(
            {
                **layer,
                "arcgis_layer_name": metadata.get("name", ""),
                "drawing_info": metadata.get("drawingInfo") or {},
                "renderer": renderer,
                "legend_values": [
                    {
                        "value": row["value"],
                        "label": row["label"],
                        "symbol_type": row["symbol_type"],
                        "symbol_style": row["symbol_style"],
                        "symbol_color_rgba": row["symbol_color_rgba"],
                    }
                    for row in layer_rows
                ],
            }
        )

    payload = {
        "retrieved_at_utc": retrieved_at,
        "source_storymap_url": STORYMAP_URL,
        "note": "ArcGIS drawingInfo.renderer metadata for ISW StoryMap event layers.",
        "layers": payload_layers,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(rows)
    write_md(payload, rows)
    print(f"wrote {OUTPUT_JSON}")
    print(f"wrote {OUTPUT_CSV}")
    print(f"wrote {OUTPUT_MD}")


if __name__ == "__main__":
    main()
