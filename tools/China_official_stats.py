import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from storage_manager import storage_manager


_NBS_ENDPOINT = "https://data.stats.gov.cn/easyquery.htm"
_NBS_REFERER = "https://data.stats.gov.cn/easyquery.htm?cn=E0103"
_GDP_INDICATOR_CODE = "A020101"  # Regional GDP (100 million CNY)


_REGION_CODE_MAP: Dict[str, str] = {
    # Municipalities
    "beijing": "110000",
    "北京市": "110000",
    "tianjin": "120000",
    "天津市": "120000",
    "shanghai": "310000",
    "上海": "310000",
    "上海市": "310000",
    "chongqing": "500000",
    "重庆": "500000",
    "重庆市": "500000",
    # Provinces / autonomous regions
    "hebei": "130000",
    "山西": "140000",
    "liaoning": "210000",
    "jilin": "220000",
    "heilongjiang": "230000",
    "jiangsu": "320000",
    "zhejiang": "330000",
    "anhui": "340000",
    "fujian": "350000",
    "jiangxi": "360000",
    "shandong": "370000",
    "henan": "410000",
    "hubei": "420000",
    "hunan": "430000",
    "guangdong": "440000",
    "hainan": "460000",
    "sichuan": "510000",
    "guizhou": "520000",
    "yunnan": "530000",
    "shanxi": "610000",
    "gansu": "620000",
    "qinghai": "630000",
    "taiwan": "710000",
    "inner mongolia": "150000",
    "广西": "450000",
    "guangxi": "450000",
    "tibet": "540000",
    "xizang": "540000",
    "ningxia": "640000",
    "xinjiang": "650000",
    "hong kong": "810000",
    "macau": "820000",
    # Common CN aliases
    "河北": "130000",
    "山西省": "140000",
    "辽宁": "210000",
    "吉林": "220000",
    "黑龙江": "230000",
    "江苏": "320000",
    "浙江": "330000",
    "安徽": "340000",
    "福建": "350000",
    "江西": "360000",
    "山东": "370000",
    "河南": "410000",
    "湖北": "420000",
    "湖南": "430000",
    "广东": "440000",
    "海南": "460000",
    "四川": "510000",
    "贵州": "520000",
    "云南": "530000",
    "陕西": "610000",
    "甘肃": "620000",
    "青海": "630000",
    "台湾省": "710000",
    "内蒙古": "150000",
    "内蒙古自治区": "150000",
    "广西壮族自治区": "450000",
    "西藏": "540000",
    "西藏自治区": "540000",
    "宁夏": "640000",
    "宁夏回族自治区": "640000",
    "新疆": "650000",
    "新疆维吾尔自治区": "650000",
    "香港": "810000",
    "澳门": "820000",
}


class ChinaOfficialGDPInput(BaseModel):
    region: str = Field(..., description="Region name, e.g., Shanghai/上海/Beijing/北京市")
    start_year: int = Field(..., description="Start year, e.g., 2013")
    end_year: int = Field(..., description="End year, e.g., 2022")
    indicator: str = Field(
        default="GDP",
        description="Currently supports GDP only. Other indicators can be added later.",
    )
    output_csv_filename: Optional[str] = Field(
        default=None,
        description="Optional CSV filename to save under inputs/, e.g. shanghai_gdp_2013_2022.csv",
    )


def _normalize_region_key(region: str) -> str:
    return (region or "").strip().lower()


def _resolve_region_code(region: str) -> Optional[str]:
    key = _normalize_region_key(region)
    if key in _REGION_CODE_MAP:
        return _REGION_CODE_MAP[key]
    if key.endswith("市") and key[:-1] in _REGION_CODE_MAP:
        return _REGION_CODE_MAP[key[:-1]]
    if key.endswith("省") and key[:-1] in _REGION_CODE_MAP:
        return _REGION_CODE_MAP[key[:-1]]
    return None


def _query_single_year_gdp(region_code: str, year: int, timeout_s: int = 20) -> Optional[float]:
    params = {
        "m": "QueryData",
        "dbcode": "fsnd",
        "rowcode": "sj",
        "colcode": "reg",
        "wds": json.dumps([{"wdcode": "zb", "valuecode": _GDP_INDICATOR_CODE}], ensure_ascii=False),
        "dfwds": json.dumps(
            [
                {"wdcode": "reg", "valuecode": region_code},
                {"wdcode": "sj", "valuecode": str(year)},
            ],
            ensure_ascii=False,
        ),
        "k1": str(int(time.time() * 1000)),
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": _NBS_REFERER,
    }
    resp = requests.get(_NBS_ENDPOINT, params=params, headers=headers, timeout=timeout_s)
    resp.raise_for_status()
    payload = resp.json()
    nodes = payload.get("returndata", {}).get("datanodes", [])
    if not nodes:
        return None
    data = nodes[0].get("data", {}) or {}
    if not data.get("hasdata"):
        return None
    val = data.get("data")
    try:
        return float(val)
    except Exception:
        return None


def _default_output_name(region: str, start_year: int, end_year: int) -> str:
    slug = "".join(c if c.isalnum() else "_" for c in region.strip()) or "region"
    return f"{slug}_official_gdp_{start_year}_{end_year}.csv"


def _build_report(
    region: str,
    region_code: str,
    indicator: str,
    start_year: int,
    end_year: int,
    rows: List[Dict[str, object]],
    output_csv_filename: Optional[str],
) -> Dict[str, object]:
    found_years = sorted([int(r["year"]) for r in rows if r.get("value_100m_cny") is not None])
    expected_years = list(range(start_year, end_year + 1))
    missing_years = [y for y in expected_years if y not in found_years]
    return {
        "status": "success" if rows else "no_data",
        "provider": "NBS_China_Official_API",
        "source_url": "https://data.stats.gov.cn/easyquery.htm?cn=E0103",
        "indicator": indicator,
        "indicator_code": _GDP_INDICATOR_CODE,
        "unit": "100 million CNY",
        "region": region,
        "region_code": region_code,
        "time_range": {"start_year": start_year, "end_year": end_year},
        "records": rows,
        "coverage": {
            "expected_count": len(expected_years),
            "actual_count": len(found_years),
            "years_found": found_years,
            "missing_years": missing_years,
        },
        "output_file": output_csv_filename,
        "reliability": {
            "level": "high",
            "reason": "Fetched from official NBS endpoint with region/year structured query.",
        },
    }


def china_official_gdp_tool(
    region: str,
    start_year: int,
    end_year: int,
    indicator: str = "GDP",
    output_csv_filename: Optional[str] = None,
) -> str:
    if start_year > end_year:
        return json.dumps(
            {"status": "error", "message": "start_year must be <= end_year"},
            ensure_ascii=False,
        )
    if start_year < 1978 or end_year > 2100:
        return json.dumps(
            {"status": "error", "message": "year range is out of supported bounds"},
            ensure_ascii=False,
        )
    if (indicator or "").strip().lower() not in {"gdp", "gross domestic product"}:
        return json.dumps(
            {
                "status": "error",
                "message": "Only GDP is supported currently for the official CN stats tool.",
            },
            ensure_ascii=False,
        )

    region_code = _resolve_region_code(region)
    if not region_code:
        return json.dumps(
            {
                "status": "region_not_supported",
                "message": "Region not recognized in official CN region map; fallback to other tools.",
                "region": region,
            },
            ensure_ascii=False,
        )

    rows: List[Dict[str, object]] = []
    for year in range(start_year, end_year + 1):
        try:
            value = _query_single_year_gdp(region_code=region_code, year=year)
            rows.append({"year": year, "value_100m_cny": value})
        except Exception as exc:  # noqa: BLE001
            rows.append({"year": year, "value_100m_cny": None, "error": str(exc)})

    output_name = output_csv_filename or _default_output_name(region, start_year, end_year)
    workspace = storage_manager.get_workspace()
    input_dir = workspace / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    out_path = input_dir / Path(output_name).name
    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False, encoding="utf-8")

    report = _build_report(
        region=region,
        region_code=region_code,
        indicator=indicator,
        start_year=start_year,
        end_year=end_year,
        rows=rows,
        output_csv_filename=out_path.name,
    )
    return json.dumps(report, ensure_ascii=False)


China_Official_GDP_tool = StructuredTool.from_function(
    func=china_official_gdp_tool,
    name="China_Official_GDP_tool",
    description=(
        "Fetch province/municipality-level annual GDP from the official National Bureau of Statistics "
        "(China) structured API, save CSV into inputs/, and return coverage diagnostics. "
        "Use this tool first for China GDP requests before generic web search."
    ),
    args_schema=ChinaOfficialGDPInput,
)

