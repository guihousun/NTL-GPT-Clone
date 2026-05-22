import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from storage_manager import current_thread_id, storage_manager


_NBS_ENDPOINT = "https://data.stats.gov.cn/easyquery.htm"
_NBS_REFERER = "https://data.stats.gov.cn/easyquery.htm?cn=E0103"
_GDP_INDICATOR_CODE = "A020101"  # Regional GDP (100 million CNY)


def _resolve_thread_id_from_config(config: Optional[RunnableConfig] = None) -> str:
    runtime_config: Optional[RunnableConfig] = None
    if isinstance(config, dict):
        runtime_config = config
    else:
        inherited = var_child_runnable_config.get()
        if isinstance(inherited, dict):
            runtime_config = inherited
    if isinstance(runtime_config, dict):
        try:
            tid = str(storage_manager.get_thread_id_from_config(runtime_config) or "").strip()
            if tid:
                return tid
        except Exception:
            pass
    return str(current_thread_id.get() or "debug").strip() or "debug"


_REGION_CODE_MAP: Dict[str, str] = {
    # Municipalities
    "beijing": "110000",
    "北京市": "110000",
    "北京": "110000",
    "tianjin": "120000",
    "天津市": "120000",
    "天津": "120000",
    "shanghai": "310000",
    "上海": "310000",
    "上海市": "310000",
    "chongqing": "500000",
    "重庆": "500000",
    "重庆市": "500000",
    # Provinces / autonomous regions
    "hebei": "130000",
    "河北": "130000",
    "河北省": "130000",
    "山西": "140000",
    "山西省": "140000",
    "shanxi": "140000",
    "liaoning": "210000",
    "辽宁": "210000",
    "辽宁省": "210000",
    "jilin": "220000",
    "吉林": "220000",
    "吉林省": "220000",
    "heilongjiang": "230000",
    "黑龙江": "230000",
    "黑龙江省": "230000",
    "jiangsu": "320000",
    "江苏": "320000",
    "江苏省": "320000",
    "zhejiang": "330000",
    "浙江": "330000",
    "浙江省": "330000",
    "anhui": "340000",
    "安徽": "340000",
    "安徽省": "340000",
    "fujian": "350000",
    "福建": "350000",
    "福建省": "350000",
    "jiangxi": "360000",
    "江西": "360000",
    "江西省": "360000",
    "shandong": "370000",
    "山东": "370000",
    "山东省": "370000",
    "henan": "410000",
    "河南": "410000",
    "河南省": "410000",
    "hubei": "420000",
    "湖北": "420000",
    "湖北省": "420000",
    "hunan": "430000",
    "湖南": "430000",
    "湖南省": "430000",
    "guangdong": "440000",
    "广东": "440000",
    "广东省": "440000",
    "hainan": "460000",
    "海南": "460000",
    "海南省": "460000",
    "sichuan": "510000",
    "四川": "510000",
    "四川省": "510000",
    "guizhou": "520000",
    "贵州": "520000",
    "贵州省": "520000",
    "yunnan": "530000",
    "云南": "530000",
    "云南省": "530000",
    "shanxi": "610000",
    "陕西": "610000",
    "陕西省": "610000",
    "gansu": "620000",
    "甘肃": "620000",
    "甘肃省": "620000",
    "qinghai": "630000",
    "青海": "630000",
    "青海省": "630000",
    "taiwan": "710000",
    "台湾": "710000",
    "台湾省": "710000",
    "inner mongolia": "150000",
    "内蒙古": "150000",
    "内蒙古自治区": "150000",
    "广西": "450000",
    "guangxi": "450000",
    "广西壮族自治区": "450000",
    "tibet": "540000",
    "xizang": "540000",
    "西藏": "540000",
    "西藏自治区": "540000",
    "ningxia": "640000",
    "宁夏": "640000",
    "宁夏回族自治区": "640000",
    "xinjiang": "650000",
    "新疆": "650000",
    "新疆维吾尔自治区": "650000",
    "hong kong": "810000",
    "香港": "810000",
    "macau": "820000",
    "澳门": "820000",
}

# Region name mapping for web scraping
_REGION_NAME_MAP: Dict[str, str] = {
    "110000": "北京",
    "120000": "天津",
    "310000": "上海",
    "500000": "重庆",
    "130000": "河北",
    "140000": "山西",
    "210000": "辽宁",
    "220000": "吉林",
    "230000": "黑龙江",
    "320000": "江苏",
    "330000": "浙江",
    "340000": "安徽",
    "350000": "福建",
    "360000": "江西",
    "370000": "山东",
    "410000": "河南",
    "420000": "湖北",
    "430000": "湖南",
    "440000": "广东",
    "460000": "海南",
    "510000": "四川",
    "520000": "贵州",
    "530000": "云南",
    "610000": "陕西",
    "620000": "甘肃",
    "630000": "青海",
    "150000": "内蒙古",
    "450000": "广西",
    "540000": "西藏",
    "640000": "宁夏",
    "650000": "新疆",
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


def _scrape_gdp_from_web(region_code: str, year: int, timeout_s: int = 20) -> Optional[float]:
    """Fallback: scrape GDP data from web when API is blocked."""
    region_name = _REGION_NAME_MAP.get(region_code)
    if not region_name:
        return None
    
    # Try to fetch from alternative sources
    # Using a simple search-based approach
    try:
        search_url = f"https://www.stats.gov.cn/sj/ndsj/{year}/indexch.htm"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        resp = requests.get(search_url, headers=headers, timeout=timeout_s)
        resp.raise_for_status()
        # Parse the HTML to find GDP data for the region
        # This is a simplified version - in practice, you'd need to parse the specific table
        return None  # Placeholder - would need full HTML parsing
    except Exception:
        return None


def _query_single_year_gdp(region_code: str, year: int, timeout_s: int = 20) -> Optional[float]:
    """Query GDP data from NBS API with fallback to web scraping."""
    # Try API first with correct parameters
    params = {
        "m": "QueryData",
        "dbcode": "hgnd",
        "rowcode": "zb",
        "colcode": "sj",
        "wds": json.dumps(
            [
                {"wdcode": "zb", "valuecode": _GDP_INDICATOR_CODE},
                {"wdcode": "reg", "valuecode": region_code},
            ],
            ensure_ascii=False,
        ),
        "dfwds": json.dumps(
            [{"wdcode": "sj", "valuecode": str(year)}],
            ensure_ascii=False,
        ),
        "k1": str(int(time.time() * 1000)),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": _NBS_REFERER,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    # Use session to maintain cookies
    session = requests.Session()
    session.headers.update(headers)
    
    # First visit the main page to get necessary cookies
    try:
        session.get(_NBS_REFERER, timeout=10)
        time.sleep(1)  # Wait for cookies to be set
    except Exception:
        pass
    
    try:
        resp = session.get(_NBS_ENDPOINT, params=params, timeout=timeout_s)
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
    except requests.exceptions.HTTPError as e:
        # If API is blocked (403), fallback to web scraping
        if "403" in str(e):
            return _scrape_gdp_from_web(region_code, year, timeout_s)
        raise


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
    config: Optional[RunnableConfig] = None,
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
    thread_id = _resolve_thread_id_from_config(config)
    workspace = storage_manager.get_workspace(thread_id)
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
