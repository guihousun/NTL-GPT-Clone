import os
import re
import json
import html
import zipfile
import base64
import textwrap
import uuid
import socket
from pathlib import Path
from typing import Optional
from datetime import UTC, datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError
import subprocess
import sys

# --- 1. 鐜閰嶇疆 ---
if 'CONDA_PREFIX' in os.environ:
    proj_path = os.path.join(os.environ['CONDA_PREFIX'], 'Library', 'share', 'proj')
    if os.path.exists(proj_path):
        os.environ['PROJ_LIB'] = proj_path
        os.environ['PROJ_DATA'] = proj_path
        try:
            import pyproj
            pyproj.datadir.set_data_dir(proj_path)
        except:
            pass

# --- 2. 绗笁鏂瑰簱瀵煎叆 ---
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import geopandas as gpd
import folium
import rasterio
from streamlit_folium import st_folium
from PIL import Image
from matplotlib import cm
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

# --- 3. 鏈湴妯″潡瀵煎叆 ---
import app_state 
import app_logic
import history_store
from storage_manager import storage_manager

try:
    from st_chat_input_multimodal import multimodal_chat_input
except Exception:  # noqa: BLE001
    multimodal_chat_input = None


def _is_en() -> bool:
    return st.session_state.get("ui_lang", "EN") == "EN"


def _tr(zh: str, en: str) -> str:
    return en if _is_en() else zh


MONITOR_UI_URL = "http://127.0.0.1:8765/"
MONITOR_API_URL = "http://127.0.0.1:8765/api/latest"
_NTL_AVAIL_SNAPSHOT_KEY = "ntl_data_availability_snapshot_v1"
_NTL_SCAN_SCRIPT_PATH = Path("experiments/official_daily_ntl_fastpath/scan_ntl_availability.py")
_NTL_SCAN_OUTPUT_DIR = Path("experiments/official_daily_ntl_fastpath/workspace_monitor/outputs")
_NTL_SCAN_TIMEOUT_SECONDS = 160
_NTL_SCAN_REFRESH_SECONDS = 3600
_NTL_SCAN_LOCK_FILE = _NTL_SCAN_OUTPUT_DIR / ".ntl_availability_refresh.lock"
_NTL_SCAN_LOCK_STALE_SECONDS = max(_NTL_SCAN_TIMEOUT_SECONDS * 2, 600)


def _normalize_availability_rows(payload: dict) -> list[dict]:
    rows = []
    all_rows = []
    if isinstance(payload.get("gee_rows"), list):
        all_rows.extend(payload.get("gee_rows") or [])
    if isinstance(payload.get("rows"), list):
        all_rows.extend(payload.get("rows") or [])

    for row in all_rows:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "source": row.get("source") or row.get("dataset_id") or "-",
                "source_type": row.get("source_type"),
                "latest_global_date": row.get("latest_global_date") or row.get("latest_global_granule_date") or "-",
                "latest_global_lag_days": row.get("latest_global_lag_days", "-"),
                "latest_bbox_date": row.get("latest_bbox_date") or "-",
                "latest_bbox_lag_days": row.get("latest_bbox_lag_days", "-"),
                "range_start": row.get("collection_time_start") or row.get("range_start") or "-",
                "range_end": row.get("collection_time_end") or row.get("range_end") or "-",
            }
        )
    return rows


def _is_gee_row(row: dict) -> bool:
    source_type = str(row.get("source_type") or "").strip().lower()
    if source_type == "gee":
        return True
    source = str(row.get("source") or "").strip().lower()
    return source.startswith("gee ")


def _order_availability_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (0 if _is_gee_row(r) else 1, str(r.get("source") or "")))


def _build_snapshot_from_payload(payload: dict, source: str) -> dict:
    return {
        "ok": True,
        "generated_at_utc": payload.get("generated_at_utc"),
        "start_date": payload.get("start_date") or payload.get("granule_start_date"),
        "end_date": payload.get("end_date") or payload.get("granule_end_date"),
        "rows": _order_availability_rows(_normalize_availability_rows(payload)),
        "state": "ok",
        "error": None,
        "snapshot_source": source,
    }


def _find_latest_scan_json() -> Optional[Path]:
    if not _NTL_SCAN_OUTPUT_DIR.exists():
        return None
    files = sorted(_NTL_SCAN_OUTPUT_DIR.glob("official_ntl_availability_*.json"))
    return files[-1] if files else None


def _scan_age_seconds(path: Path) -> int:
    if not path.exists():
        return 10**9
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return int((datetime.now(UTC) - mtime).total_seconds())


def _is_scan_fresh(path: Path, refresh_seconds: int = _NTL_SCAN_REFRESH_SECONDS) -> bool:
    return _scan_age_seconds(path) <= int(refresh_seconds)


def _try_acquire_scan_refresh_lock() -> bool:
    _NTL_SCAN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if _NTL_SCAN_LOCK_FILE.exists():
        age = _scan_age_seconds(_NTL_SCAN_LOCK_FILE)
        if age > _NTL_SCAN_LOCK_STALE_SECONDS:
            _NTL_SCAN_LOCK_FILE.unlink(missing_ok=True)
    try:
        fd = os.open(str(_NTL_SCAN_LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"pid": os.getpid(), "created_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")},
                    ensure_ascii=False,
                )
            )
        return True
    except FileExistsError:
        return False


def _release_scan_refresh_lock() -> None:
    _NTL_SCAN_LOCK_FILE.unlink(missing_ok=True)


def _run_ntl_scan_script() -> tuple[bool, Optional[str]]:
    if not _NTL_SCAN_SCRIPT_PATH.exists():
        return False, f"scan script not found: {_NTL_SCAN_SCRIPT_PATH}"

    today = datetime.now(UTC).date()
    start_day = today - timedelta(days=45)
    cmd = [
        sys.executable,
        str(_NTL_SCAN_SCRIPT_PATH),
        "--sources",
        "nrt_priority",
        "--granule-start-date",
        start_day.strftime("%Y-%m-%d"),
        "--granule-end-date",
        today.strftime("%Y-%m-%d"),
        "--include-gee",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(Path(__file__).resolve().parent),
            capture_output=True,
            text=True,
            timeout=_NTL_SCAN_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"local scan timed out ({_NTL_SCAN_TIMEOUT_SECONDS}s)"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)

    if proc.returncode != 0:
        err = (proc.stderr or "").strip() or (proc.stdout or "").strip()
        return False, err or f"scan failed (exit={proc.returncode})"
    return True, None


def _load_snapshot_from_scan_file(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    snapshot = _build_snapshot_from_payload(payload, source="local_scan")
    if not snapshot.get("generated_at_utc"):
        snapshot["generated_at_utc"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return snapshot


def _load_ntl_availability_snapshot_once() -> dict:
    """Load availability once per page session with shared 1h cache and single refresher lock."""
    if _NTL_AVAIL_SNAPSHOT_KEY in st.session_state:
        return st.session_state[_NTL_AVAIL_SNAPSHOT_KEY]

    snapshot = {
        "ok": False,
        "generated_at_utc": None,
        "start_date": None,
        "end_date": None,
        "rows": [],
        "state": "error",
        "error": None,
        "snapshot_source": None,
    }

    local_json = _find_latest_scan_json()
    if local_json is not None and _is_scan_fresh(local_json):
        try:
            snapshot = _load_snapshot_from_scan_file(local_json)
            snapshot["snapshot_source"] = "local_cache_fresh_1h"
            st.session_state[_NTL_AVAIL_SNAPSHOT_KEY] = snapshot
            return snapshot
        except Exception as exc:  # noqa: BLE001
            snapshot["error"] = str(exc).strip()

    ok_local = False
    local_err: Optional[str] = None
    acquired = _try_acquire_scan_refresh_lock()
    if acquired:
        try:
            ok_local, local_err = _run_ntl_scan_script()
        finally:
            _release_scan_refresh_lock()
    else:
        local_err = "shared refresh in progress, using local cache"

    local_json = _find_latest_scan_json()

    if local_json is not None:
        try:
            snapshot = _load_snapshot_from_scan_file(local_json)
            snapshot["snapshot_source"] = (
                "local_cache_fresh_1h_after_refresh"
                if _is_scan_fresh(local_json)
                else "local_cache_stale"
            )
            if local_err and (not ok_local or not acquired):
                snapshot["error"] = local_err
            st.session_state[_NTL_AVAIL_SNAPSHOT_KEY] = snapshot
            return snapshot
        except Exception as exc:  # noqa: BLE001
            local_err = local_err or str(exc).strip()

    if local_err:
        snapshot["state"] = "waiting" if "timed out" in str(local_err).lower() else "error"
        snapshot["error"] = local_err

    if not snapshot.get("ok"):
        try:
            req = Request(MONITOR_API_URL, headers={"User-Agent": "NTL-GPT-UI/1.0"})
            with urlopen(req, timeout=6) as resp:  # noqa: S310
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
            snapshot = _build_snapshot_from_payload(payload, source="monitor_api")
        except Exception as exc:  # noqa: BLE001
            err = str(exc).strip()
            err_low = err.lower()
            waiting = False
            if isinstance(exc, (TimeoutError, socket.timeout)):
                waiting = True
            elif isinstance(exc, URLError):
                reason = str(getattr(exc, "reason", "")).lower()
                waiting = any(
                    token in reason
                    for token in ("timed out", "connection refused", "failed to establish a new connection", "winerror 10061")
                )
            if any(token in err_low for token in ("timed out", "connection refused", "winerror 10061", "errno 111", "max retries exceeded")):
                waiting = True
            snapshot["state"] = "waiting" if waiting else "error"
            snapshot["error"] = snapshot.get("error") or err

    st.session_state[_NTL_AVAIL_SNAPSHOT_KEY] = snapshot
    return snapshot

def _render_monitor_jump_button(label: str) -> None:
    if hasattr(st, "link_button"):
        st.link_button(label, MONITOR_UI_URL, use_container_width=True)
        return

    safe_label = html.escape(label)
    safe_url = html.escape(MONITOR_UI_URL, quote=True)
    st.markdown(
        (
            f'<a class="ntl-sidebar-link-btn" href="{safe_url}" '
            f'target="_blank" rel="noopener noreferrer">{safe_label}</a>'
        ),
        unsafe_allow_html=True,
    )

def _render_data_availability_block() -> None:
    """Render NTL availability snapshot with the same row contract as monitor table."""
    if _NTL_AVAIL_SNAPSHOT_KEY not in st.session_state:
        first_hit = _find_latest_scan_json()
        if first_hit is not None and _is_scan_fresh(first_hit):
            snapshot = _load_ntl_availability_snapshot_once()
        else:
            with st.spinner(_tr("正在加载 NTL 可用性（本地扫描）...", "Loading NTL availability (local scan)...")):
                snapshot = _load_ntl_availability_snapshot_once()
    else:
        snapshot = _load_ntl_availability_snapshot_once()

    if snapshot.get("ok"):
        rows = snapshot.get("rows") or []
        if _is_en():
            df = pd.DataFrame(rows).rename(
                columns={
                    "source": "Source",
                    "latest_global_date": "Global Latest",
                    "range_start": "Available Start",
                }
            )
            if not df.empty and "Source" in df.columns:
                df = df.set_index("Source")[["Available Start", "Global Latest"]]
            st.caption(f"Snapshot: {snapshot.get('generated_at_utc') or '-'}")
            jump_label = "Open NTL Data Monitor"
        else:
            df = pd.DataFrame(rows).rename(
                columns={
                    "source": "Source",
                    "latest_global_date": "全局最新",
                    "range_start": "可用起始",
                }
            )
            if not df.empty and "Source" in df.columns:
                df = df.set_index("Source")[["可用起始", "全局最新"]]
            st.caption(f"快照时间: {snapshot.get('generated_at_utc') or '-'} | 来源={snapshot.get('snapshot_source') or '-'}")
            if snapshot.get("start_date") or snapshot.get("end_date"):
                st.caption(f"查询窗口: {snapshot.get('start_date') or '-'} -> {snapshot.get('end_date') or '-'}")
            jump_label = "打开夜光遥感数据监控界面"

        st.dataframe(df, use_container_width=True, hide_index=False, height=260)
        if snapshot.get("error"):
            st.caption(_tr(f"本地扫描告警：{snapshot.get('error')}", f"Local scan warning: {snapshot.get('error')}"))
        _render_monitor_jump_button(jump_label)
        return

    msg = snapshot.get("error") or "unknown"
    if snapshot.get("state") == "waiting":
        st.info(
            _tr(
                "正在等待数据服务响应，请稍后重试。",
                "Waiting for data service to respond. Please retry shortly.",
            )
        )
        st.caption(_tr(f"等待原因：{msg}", f"Wait reason: {msg}"))
    else:
        st.warning(_tr(f"未能读取 Monitor 快照：{msg}", f"Failed to load monitor snapshot: {msg}"))
    _render_monitor_jump_button(_tr("打开夜光遥感数据监控界面", "Open NTL Data Monitor"))
    if st.button(_tr("重试加载", "Retry Loading"), key="retry_ntl_availability_snapshot", use_container_width=True):
        if _NTL_AVAIL_SNAPSHOT_KEY in st.session_state:
            del st.session_state[_NTL_AVAIL_SNAPSHOT_KEY]
        st.rerun()


def _get_nasa_bg_data_uri() -> str:
    if "nasa_bg_data_uri" in st.session_state:
        return st.session_state["nasa_bg_data_uri"]
    img_path = os.path.join("assets", "nasa_black_marble.jpg")
    if not os.path.exists(img_path):
        st.session_state["nasa_bg_data_uri"] = ""
        return ""
    with open(img_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    uri = f"data:image/jpeg;base64,{encoded}"
    st.session_state["nasa_bg_data_uri"] = uri
    return uri

# ==============================================================================
# SECTION A: 甯搁噺涓?HTML 妯℃澘
# ==============================================================================

BOT_TEMPLATE = """
<div class="chat-message bot">
    <div class="avatar"><span class="bot-badge">AI</span></div>
    <div class="message" >{{MSG}}</div>
</div>
"""

USER_TEMPLATE = """
<div class="chat-message user">
    <div class="avatar"><span class="user-badge">U</span></div>
    <div class="message" >{{MSG}}</div>
</div>
"""

# ==============================================================================
# SECTION B: 鏍峰紡 (CSS) 涓?鑴氭湰 (JS) 娉ㄥ叆
# ==============================================================================

def inject_css():
    """Inject global CSS styles."""
    bg_uri = _get_nasa_bg_data_uri()
    bg_css = f"url('{bg_uri}')" if bg_uri else "none"
    css = """
    <style>
    :root {
        --ntl-bg: #f3f7f7;
        --ntl-border: #d7e3e0;
        --ntl-panel-border: rgba(255, 255, 255, 0.52);
        --ntl-chat-user: #123b62;
        --ntl-chat-bot: #0f766e;
        --ntl-subtle: #61717a;
    }
    .stApp {
        background:
            linear-gradient(rgba(14, 18, 33, 0.58), rgba(14, 18, 33, 0.58)),
            __BG__,
            radial-gradient(900px 300px at -20% -20%, #d6f2ed 0%, transparent 55%),
            radial-gradient(700px 240px at 120% 0%, #dbeafe 0%, transparent 50%),
            var(--ntl-bg);
        background-size: cover, cover, auto, auto, auto;
        background-attachment: fixed;
        background-position: center;
        color: #e8edf8;
    }
    header, header[data-testid="stHeader"] {
        background: transparent !important;
        height: 0 !important;
        min-height: 0 !important;
        display: none !important;
    }
    div[data-testid="stDecoration"] { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stAppViewContainer"] {
        background: transparent !important;
    }
    .stDeployButton { visibility: hidden; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .block-container { padding: 3.1rem 1.5rem 8.0rem 1.5rem; max-width: 1700px; }
    [data-testid="stAppViewContainer"] [data-testid="stVerticalBlockBorderWrapper"],
    [data-testid="stAppViewContainer"] [data-testid="stVerticalBlock"][overflow="auto"][height="600px"] {
        border: 1.2px solid var(--ntl-panel-border) !important;
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
    }
    [data-testid="stChatInput"] {
        position: fixed !important;
        bottom: calc(clamp(12px, 1.8vh, 20px) + env(safe-area-inset-bottom));
        left: 18px;
        transform: none !important;
        width: min(58vw, 760px);
        max-width: calc(100vw - 2rem);
        box-sizing: border-box;
        z-index: 900 !important;
        opacity: 1;
        height: auto !important;
    }
    [data-testid="stChatInput"] > div {
        width: 100% !important;
        max-width: 100% !important;
    }
    iframe[title*="st_chat_input_multimodal"] {
        border: none !important;
        border-radius: 0 !important;
        background: transparent !important;
        box-shadow: none !important;
        outline: none !important;
        width: 100% !important;
    }
    .st-key-main_chat_input_mm,
    .st-key-main_chat_input_mm > div,
    .st-key-main_chat_input_mm [data-testid="stElementContainer"],
    .st-key-main_chat_input_mm [data-testid="stCustomComponentV1"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
        padding: 0 !important;
    }
    [data-testid="stBottom"],
    [data-testid="stBottomBlockContainer"] {
        background: transparent !important;
    }
    div:has(> [data-testid="stBottomBlockContainer"]) {
        background: transparent !important;
    }
    div[data-testid="stElementContainer"]:has(iframe[title*="st_chat_input_multimodal"]) {
        background: transparent !important;
    }
    .chat-message {
        display: grid;
        grid-template-columns: 2.1rem 1fr;
        gap: 0.8rem;
        align-items: start;
        padding: 0.95rem 1rem;
        border-radius: 12px;
        margin-bottom: 0.7rem;
        color: #fff;
        box-shadow: 0 8px 20px rgba(16,24,40,0.08);
    }
    .chat-message.user { background: linear-gradient(120deg, var(--ntl-chat-user), #1a5f95); }
    .chat-message.bot { background: linear-gradient(120deg, var(--ntl-chat-bot), #0d5f59); }
    .chat-message .avatar { font-size: 1.25rem; line-height: 1.4; }
    .chat-message .message { font-size: 0.97rem; line-height: 1.55; word-break: break-word; }
    .bot-badge, .user-badge {
        display: inline-flex;
        width: 1.45rem;
        height: 1.45rem;
        border-radius: 999px;
        align-items: center;
        justify-content: center;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.02em;
        color: #ffffff;
    }
    .bot-badge { background: #0f172a; border: 1px solid rgba(255,255,255,0.35); }
    .user-badge { background: #1d4ed8; border: 1px solid rgba(255,255,255,0.35); }
    .stExpander { border: 1px solid var(--ntl-border); border-radius: 10px; }
    .stCode { border-radius: 10px; }
    [data-testid="stSidebar"] {
        min-width: 290px !important;
        max-width: 360px !important;
        border-right: 1px solid var(--ntl-border);
        background:
            linear-gradient(rgba(14, 18, 33, 0.52), rgba(14, 18, 33, 0.52)),
            __BG__,
            linear-gradient(180deg, #f8fbfb 0%, #edf6f6 100%);
        background-size: cover;
        background-position: center;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] h4,
    [data-testid="stSidebar"] label {
        color: #f0f5ff !important;
    }
    [data-testid="stSidebar"] h3 {
        margin-top: 0.38rem !important;
        margin-bottom: 0.42rem !important;
    }
    .ntl-sidebar-divider-tight {
        height: 1px;
        margin: 0.32rem 0 0.38rem 0;
        background: linear-gradient(
            90deg,
            rgba(159, 182, 248, 0.00),
            rgba(159, 182, 248, 0.45),
            rgba(159, 182, 248, 0.00)
        );
    }
    [data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea {
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
        background: #ffffff !important;
    }
    [data-testid="stSidebar"] input::placeholder,
    [data-testid="stSidebar"] textarea::placeholder {
        color: #9ca3af !important;
        -webkit-text-fill-color: #9ca3af !important;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] [data-baseweb="select"] span,
    [data-testid="stSidebar"] [data-baseweb="select"] input {
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
    }
    [data-testid="stSidebar"] [data-testid="stTextInput"] input,
    [data-testid="stSidebar"] [data-testid="stNumberInput"] input {
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
    }
    [data-testid="stSidebar"] .stSelectbox svg {
        fill: #334155 !important;
    }
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
        color: #f0f5ff !important;
    }
    [data-testid="stSidebar"] [data-testid="stMetricLabel"] p,
    [data-testid="stSidebar"] [data-testid="stMetricValue"] {
        color: #f8fbff !important;
    }
    [data-testid="stSidebar"] .stButton button {
        color: #0f172a !important;
        background: #ffffff !important;
        border: 1px solid #d7e3e0 !important;
        font-weight: 600 !important;
        opacity: 1 !important;
    }
    [data-testid="stSidebar"] .stButton button span {
        color: #0f172a !important;
        opacity: 1 !important;
    }
    [data-testid="stSidebar"] .stButton button:disabled,
    [data-testid="stSidebar"] .stButton button:disabled span {
        color: #64748b !important;
        opacity: 0.75 !important;
    }
    [data-testid="stSidebar"] code {
        color: #0f172a !important;
        background: #f8fafc !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
        background: #ffffff !important;
        border: 1px solid #d7e3e0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] * {
        color: #334155 !important;
        -webkit-text-fill-color: #334155 !important;
    }
    .stMarkdown p, .stText, .stAlert, .stInfo { color: #eaf1ff; }
    [data-testid="stWidgetLabel"] p { color: #eaf1ff !important; font-weight: 550; }
    [data-testid="stAppViewContainer"] [data-baseweb="select"] > div {
        background: rgba(15, 23, 42, 0.72) !important;
        border: 1px solid #334155 !important;
    }
    [data-testid="stAppViewContainer"] [data-baseweb="select"] span,
    [data-testid="stAppViewContainer"] [data-baseweb="select"] input {
        color: #eaf1ff !important;
        -webkit-text-fill-color: #eaf1ff !important;
    }
    [data-testid="stAppViewContainer"] [data-baseweb="select"] svg {
        fill: #dbe7ff !important;
    }
    /* Improve main-panel select contrast (e.g., Preview Output selector) */
    [data-testid="stAppViewContainer"] [data-baseweb="select"] > div {
        background: #ffffff !important;
        border: 1px solid #334155 !important;
    }
    [data-testid="stAppViewContainer"] [data-baseweb="select"] span,
    [data-testid="stAppViewContainer"] [data-baseweb="select"] input,
    [data-testid="stAppViewContainer"] [data-baseweb="select"] div[role="combobox"] {
        color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important;
        opacity: 1 !important;
    }
    [data-testid="stAppViewContainer"] [data-baseweb="select"] svg {
        fill: #334155 !important;
        opacity: 1 !important;
    }
    [data-testid="stVerticalBlock"] > div { gap: 0.5rem !important; padding-bottom: 0px !important; }
    .stMarkdown div p { margin-bottom: 5px !important; }
    .stCaption { color: #cdd8ee; }
    button[data-baseweb="tab"] p { font-size: 0.95rem !important; font-weight: 650 !important; color: #ffffff !important; }
    button[aria-selected="true"][data-baseweb="tab"] p { color: #ff5f5f !important; }
    button[data-baseweb="tab"] { padding-right: 14px !important; padding-left: 14px !important; }
    [data-testid="stSidebar"] button[data-baseweb="tab"] p {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        opacity: 1 !important;
    }
    [data-testid="stSidebar"] button[aria-selected="true"][data-baseweb="tab"] p { color: #ef4444 !important; }
    .stDownloadButton button, .stButton > button { border-radius: 8px; }
    [data-testid="stSidebar"] .stDownloadButton button { min-height: 30px !important; }
    div[data-testid="stRadio"] label p { font-size: 0.78rem !important; }
    /* Language switch (CN / EN) contrast */
    [data-testid="stRadio"] label,
    [data-testid="stRadio"] label p,
    [data-testid="stRadio"] label span,
    [data-testid="stRadio"] [role="radiogroup"] * {
        color: #eaf1ff !important;
        -webkit-text-fill-color: #eaf1ff !important;
        opacity: 1 !important;
        font-weight: 700 !important;
    }
    .ntl-card { border:1px solid #d7e3e0;border-radius:10px;background:rgba(255,255,255,0.94);padding:10px 12px; color:#111827; }
    .ntl-card *, .ntl-card p, .ntl-card span, .ntl-card div { color:#111827 !important; }
    [data-testid="stExpander"] details {
        background: rgba(255,255,255,0.96);
        border-radius: 10px;
    }
    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] label,
    [data-testid="stExpander"] span,
    [data-testid="stExpander"] p,
    [data-testid="stExpander"] li,
    [data-testid="stExpander"] div {
        color: #111827 !important;
    }
    [data-testid="stExpander"] .stCaption { color: #334155 !important; }
    [data-testid="stSidebar"] [data-testid="stExpander"] details {
        background: #ffffff !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary p,
    [data-testid="stSidebar"] [data-testid="stExpander"] summary span {
        color: #0f172a !important;
    }
    /* Final contrast overrides for sidebar controls and white-surface blocks */
    [data-testid="stSidebar"] [data-baseweb="select"] > div {
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] span,
    [data-testid="stSidebar"] [data-baseweb="select"] input,
    [data-testid="stSidebar"] [data-baseweb="select"] div[role="combobox"] {
        color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important;
        opacity: 1 !important;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] svg {
        fill: #334155 !important;
        opacity: 1 !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] .stMarkdown p,
    [data-testid="stSidebar"] [data-testid="stExpander"] .stMarkdown span,
    [data-testid="stSidebar"] [data-testid="stExpander"] .stMarkdown li,
    [data-testid="stSidebar"] [data-testid="stExpander"] .stCaption {
        color: #334155 !important;
        -webkit-text-fill-color: #334155 !important;
        opacity: 1 !important;
    }
    /* Premium sidebar style overrides (NTL-GPT night console) */
    [data-testid="stSidebar"] [data-baseweb="select"] > div {
        background: rgba(10, 18, 40, 0.86) !important;
        border: 1px solid rgba(110, 151, 255, 0.42) !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), 0 8px 20px rgba(5, 12, 30, 0.28) !important;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] span,
    [data-testid="stSidebar"] [data-baseweb="select"] input,
    [data-testid="stSidebar"] [data-baseweb="select"] div[role="combobox"] {
        color: #eaf2ff !important;
        -webkit-text-fill-color: #eaf2ff !important;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] svg {
        fill: #c9dcff !important;
    }
    [data-testid="stSidebar"] .stButton > button {
        min-height: 2.5rem !important;
        height: 2.5rem !important;
        border-radius: 10px !important;
        border: 1px solid rgba(121, 161, 255, 0.35) !important;
        background: linear-gradient(180deg, rgba(14, 28, 58, 0.90), rgba(7, 16, 36, 0.92)) !important;
        color: #dce8ff !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.07), 0 6px 16px rgba(0,0,0,0.24) !important;
        font-weight: 600 !important;
        font-size: 0.86rem !important;
        white-space: nowrap !important;
        line-height: 1 !important;
        padding: 0.1rem 0.4rem !important;
        letter-spacing: 0.01em !important;
        transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease !important;
    }
    [data-testid="stSidebar"] .stButton > button span {
        color: #dce8ff !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        transform: translateY(-1px) !important;
        border-color: rgba(142, 184, 255, 0.72) !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.1), 0 10px 18px rgba(0,0,0,0.3) !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        border: 1px solid rgba(123, 243, 255, 0.92) !important;
        background: linear-gradient(135deg, #00a8ff 0%, #2d6dff 100%) !important;
        color: #ffffff !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.26), 0 8px 18px rgba(16, 127, 255, 0.42) !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="primary"] span {
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="secondary"] {
        border: 1px solid rgba(121, 161, 255, 0.35) !important;
        background: linear-gradient(180deg, rgba(14, 28, 58, 0.90), rgba(7, 16, 36, 0.92)) !important;
        color: #dce8ff !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="secondary"] span {
        color: #dce8ff !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="tertiary"] {
        border: 1px solid rgba(255, 125, 125, 0.55) !important;
        background: linear-gradient(180deg, rgba(67, 20, 26, 0.88), rgba(45, 16, 24, 0.90)) !important;
        color: #ffd6d6 !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), 0 6px 16px rgba(32, 6, 8, 0.30) !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="tertiary"] span {
        color: #ffd6d6 !important;
    }
    [data-testid="stSidebar"] .st-key-activate_btn button {
        border: 1px solid rgba(121, 161, 255, 0.35) !important;
        background: linear-gradient(180deg, rgba(14, 28, 58, 0.90), rgba(7, 16, 36, 0.92)) !important;
        color: #dce8ff !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.07), 0 6px 16px rgba(0,0,0,0.24) !important;
        font-weight: 700 !important;
    }
    [data-testid="stSidebar"] .st-key-activate_btn button span {
        color: #dce8ff !important;
    }
    [data-testid="stSidebar"] .st-key-reset_btn button {
        border: 1px solid rgba(121, 161, 255, 0.35) !important;
        background: linear-gradient(180deg, rgba(14, 28, 58, 0.90), rgba(7, 16, 36, 0.92)) !important;
        color: #dce8ff !important;
    }
    [data-testid="stSidebar"] .st-key-reset_btn button span {
        color: #dce8ff !important;
    }
    [data-testid="stSidebar"] .st-key-interrupt_current_run_btn button {
        border: 1px solid rgba(255, 125, 125, 0.60) !important;
        background: linear-gradient(180deg, rgba(67, 20, 26, 0.88), rgba(45, 16, 24, 0.90)) !important;
        color: #ffd6d6 !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), 0 6px 16px rgba(32, 6, 8, 0.30) !important;
    }
    [data-testid="stSidebar"] .st-key-interrupt_current_run_btn button span {
        color: #ffd6d6 !important;
    }
    [data-testid="stSidebar"] .stElementContainer.st-key-interrupt_current_run_btn [data-testid="stBaseButton-secondary"] {
        border: 1px solid rgba(255, 125, 125, 0.60) !important;
        background: linear-gradient(180deg, rgba(67, 20, 26, 0.88), rgba(45, 16, 24, 0.90)) !important;
        color: #ffd6d6 !important;
    }
    [data-testid="stSidebar"] .stElementContainer.st-key-interrupt_current_run_btn [data-testid="stBaseButton-secondary"] p,
    [data-testid="stSidebar"] .stElementContainer.st-key-interrupt_current_run_btn [data-testid="stBaseButton-secondary"] span {
        color: #ffd6d6 !important;
        -webkit-text-fill-color: #ffd6d6 !important;
    }
    [data-testid="stSidebar"] .stButton > button:disabled,
    [data-testid="stSidebar"] .stButton > button:disabled span {
        color: #6f88b0 !important;
        border-color: rgba(111, 136, 176, 0.28) !important;
        opacity: 0.7 !important;
    }
    [data-testid="stSidebar"] .stLinkButton > a,
    [data-testid="stSidebar"] a.ntl-sidebar-link-btn {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 100% !important;
        min-height: 2.5rem !important;
        border-radius: 10px !important;
        border: 1px solid rgba(121, 161, 255, 0.35) !important;
        background: linear-gradient(180deg, rgba(14, 28, 58, 0.90), rgba(7, 16, 36, 0.92)) !important;
        color: #dce8ff !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.07), 0 6px 16px rgba(0,0,0,0.24) !important;
        font-weight: 600 !important;
        font-size: 0.86rem !important;
        text-decoration: none !important;
        letter-spacing: 0.01em !important;
        transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease !important;
        padding: 0.1rem 0.4rem !important;
        box-sizing: border-box !important;
    }
    [data-testid="stSidebar"] .stLinkButton > a *,
    [data-testid="stSidebar"] a.ntl-sidebar-link-btn * {
        color: #dce8ff !important;
        -webkit-text-fill-color: #dce8ff !important;
    }
    [data-testid="stSidebar"] .stLinkButton > a:visited,
    [data-testid="stSidebar"] a.ntl-sidebar-link-btn:visited {
        color: #dce8ff !important;
    }
    [data-testid="stSidebar"] .stLinkButton > a:hover,
    [data-testid="stSidebar"] a.ntl-sidebar-link-btn:hover {
        transform: translateY(-1px) !important;
        border-color: rgba(142, 184, 255, 0.72) !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.1), 0 10px 18px rgba(0,0,0,0.3) !important;
        color: #e8f2ff !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] details {
        background: linear-gradient(180deg, rgba(13,22,46,0.90), rgba(8,16,35,0.88)) !important;
        border: 1px solid rgba(121, 161, 255, 0.20) !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.06), 0 6px 14px rgba(0,0,0,0.20) !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary p,
    [data-testid="stSidebar"] [data-testid="stExpander"] .stMarkdown p,
    [data-testid="stSidebar"] [data-testid="stExpander"] .stMarkdown span,
    [data-testid="stSidebar"] [data-testid="stExpander"] .stMarkdown li,
    [data-testid="stSidebar"] [data-testid="stExpander"] .stCaption {
        color: #dbe8ff !important;
        -webkit-text-fill-color: #dbe8ff !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] .stMarkdown strong,
    [data-testid="stSidebar"] [data-testid="stExpander"] .stMarkdown b {
        color: #f4f8ff !important;
        -webkit-text-fill-color: #f4f8ff !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button {
        border: 1px solid rgba(96, 146, 255, 0.44) !important;
        background: linear-gradient(180deg, rgba(11, 24, 52, 0.90), rgba(7, 16, 36, 0.92)) !important;
        color: #dce8ff !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button span,
    [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button p {
        color: #dce8ff !important;
        -webkit-text-fill-color: #dce8ff !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
        background: linear-gradient(180deg, rgba(13,22,46,0.86), rgba(8,16,35,0.86)) !important;
        border: 1px dashed rgba(129, 168, 255, 0.50) !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.05) !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] * {
        color: #dbe8ff !important;
        -webkit-text-fill-color: #dbe8ff !important;
    }
    [data-testid="stSidebar"] code {
        color: #d9e7ff !important;
        background: rgba(20, 35, 66, 0.88) !important;
        border: 1px solid rgba(121, 161, 255, 0.35) !important;
    }
    .ntl-thread-status-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.8rem;
        color: #dce8ff;
        font-size: 0.93rem;
        margin-top: 0.2rem;
    }
    .ntl-thread-status-item {
        display: inline-flex;
        align-items: center;
        gap: 0.22rem;
        white-space: nowrap;
    }
    .ntl-thread-status-value {
        color: #f1f6ff;
        font-weight: 600;
    }
    .ntl-status-text.active {
        color: #b4ffe0;
    }
    .ntl-status-text.inactive {
        color: #ffd2d2;
    }
    /* Sidebar harmonization: enforce readable contrast in all nested states */
    [data-testid="stSidebar"] [data-baseweb="select"] * {
        color: #e7f1ff !important;
        -webkit-text-fill-color: #e7f1ff !important;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] p,
    [data-testid="stSidebar"] [data-baseweb="select"] div,
    [data-testid="stSidebar"] [data-baseweb="select"] span,
    [data-testid="stSidebar"] [data-baseweb="select"] input {
        color: #e7f1ff !important;
        -webkit-text-fill-color: #e7f1ff !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] details,
    [data-testid="stSidebar"] [data-testid="stExpander"] details * {
        color: #dbe8ff !important;
        -webkit-text-fill-color: #dbe8ff !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary,
    [data-testid="stSidebar"] [data-testid="stExpander"] details > summary,
    [data-testid="stSidebar"] [data-testid="stExpander"] details[open] > summary {
        background: linear-gradient(180deg, rgba(16, 30, 62, 0.92), rgba(9, 18, 40, 0.92)) !important;
        color: #dbe8ff !important;
        -webkit-text-fill-color: #dbe8ff !important;
        border-bottom: 1px solid rgba(121, 161, 255, 0.30) !important;
        border-radius: 8px !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] details[open] > summary {
        border-bottom-left-radius: 0 !important;
        border-bottom-right-radius: 0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary p,
    [data-testid="stSidebar"] [data-testid="stExpander"] summary span,
    [data-testid="stSidebar"] [data-testid="stExpander"] summary svg {
        color: #dbe8ff !important;
        fill: #dbe8ff !important;
        -webkit-text-fill-color: #dbe8ff !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] .stCaption,
    [data-testid="stSidebar"] [data-testid="stExpander"] .stCaption * {
        color: #b8cbec !important;
        -webkit-text-fill-color: #b8cbec !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button:hover {
        border-color: rgba(142, 184, 255, 0.72) !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.1), 0 10px 18px rgba(0,0,0,0.3) !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {
        border: 1px solid rgba(132, 168, 255, 0.45) !important;
        background: linear-gradient(180deg, rgba(14, 28, 58, 0.88), rgba(7, 16, 36, 0.90)) !important;
        color: #dce8ff !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button span {
        color: #dce8ff !important;
        -webkit-text-fill-color: #dce8ff !important;
    }
    .ntl-step .streamlit-expanderHeader {
        font-weight: 600;
    }
    </style>
    """
    st.markdown(css.replace("__BG__", bg_css), unsafe_allow_html=True)
def scroll_to_bottom():
    """Inject JS to scroll containers to the bottom."""
    js = f"""
    <script>
        function findMainPanels(doc) {{
            var blocks = Array.from(doc.querySelectorAll('div[data-testid="stVerticalBlock"][overflow="auto"]'));
            blocks = blocks.filter(function(el) {{
                var r = el.getBoundingClientRect();
                return r && r.width > 280 && r.height > 200;
            }});
            blocks.sort(function(a, b) {{
                return a.getBoundingClientRect().left - b.getBoundingClientRect().left;
            }});
            return blocks;
        }}
        function styleMainPanels(doc) {{
            var panels = findMainPanels(doc);
            for (var i = 0; i < panels.length; i++) {{
                var panel = panels[i];
                panel.style.border = '1.2px solid rgba(255,255,255,0.52)';
                panel.style.borderRadius = '12px';
                panel.style.boxShadow = 'inset 0 0 0 1px rgba(255,255,255,0.08)';
            }}
            return panels;
        }}
        function scroll() {{
            var doc = window.parent.document;
            var panels = findMainPanels(doc);
            if (panels.length > 0) {{
                panels[0].scrollTop = panels[0].scrollHeight;
            }}
        }}
        function alignChatInput() {{
            var doc = window.parent.document;
            function styleMultimodalFrame(frame) {{
                try {{
                    if (!frame) return;
                    var host = frame.closest('div[data-testid="stElementContainer"]') || frame.parentElement;
                    if (host) {{
                        host.style.setProperty('background', 'transparent', 'important');
                        host.style.setProperty('border', 'none', 'important');
                        host.style.setProperty('box-shadow', 'none', 'important');
                        host.style.setProperty('outline', 'none', 'important');
                        host.style.setProperty('padding', '0px', 'important');
                        host.style.setProperty('border-radius', '0px', 'important');
                    }}
                    var parent = frame.parentElement;
                    if (parent) {{
                        parent.style.setProperty('background', 'transparent', 'important');
                        parent.style.setProperty('border', 'none', 'important');
                        parent.style.setProperty('box-shadow', 'none', 'important');
                        parent.style.setProperty('outline', 'none', 'important');
                        parent.style.setProperty('padding', '0px', 'important');
                    }}
                    frame.style.setProperty('background', 'transparent', 'important');
                    frame.style.setProperty('border', 'none', 'important');
                    frame.style.setProperty('border-radius', '0px', 'important');
                    frame.style.setProperty('box-shadow', 'none', 'important');
                    frame.style.setProperty('outline', 'none', 'important');
                    frame.style.setProperty('min-height', '62px', 'important');
                    var idoc = frame.contentDocument || (frame.contentWindow && frame.contentWindow.document);
                    if (!idoc) return;
                    var root = idoc.documentElement;
                    var body = idoc.body;
                    var h = 62;
                    if (root && root.scrollHeight) h = Math.max(h, root.scrollHeight);
                    if (body && body.scrollHeight) h = Math.max(h, body.scrollHeight);
                    frame.style.setProperty('height', Math.min(h, 220) + 'px', 'important');
                }} catch (e) {{}}
            }}

            var nativeInput = doc.querySelector('div[data-testid="stChatInput"]');
            var mmFrame = null;
            var mmHost = null;
            if (!nativeInput) {{
                var frames = Array.from(doc.querySelectorAll('iframe'));
                mmFrame = frames.find(function(fr) {{
                    var t = String(fr.getAttribute('title') || '').toLowerCase();
                    return t.indexOf('st_chat_input_multimodal') >= 0;
                }});
                if (mmFrame) {{
                    mmHost = mmFrame.closest('div[data-testid="stElementContainer"]') || mmFrame.parentElement || mmFrame;
                }}
            }}

            var input = nativeInput || mmHost;
            if (!input) return;
            var panels = styleMainPanels(doc);
            if (!panels.length) return;
            var chatPanel = panels[0];
            var chatRect = chatPanel.getBoundingClientRect();
            if (!chatRect || chatRect.width < 220 || chatRect.height < 120) return;

            var viewportW = window.parent.innerWidth || doc.documentElement.clientWidth || 1200;
            var sidebar = doc.querySelector('section[data-testid="stSidebar"]');
            var sidebarRight = 0;
            if (sidebar) {{
                var sb = sidebar.getBoundingClientRect();
                if (sb && sb.width > 40) sidebarRight = sb.right;
            }}
            var minLeft = Math.max(12, Math.round(sidebarRight + 12));

            var left = Math.max(minLeft, Math.round(chatRect.left + 10));
            var width = Math.round(chatRect.width - 20);
            width = Math.max(280, Math.min(width, viewportW - left - 12));
            input.style.setProperty('position', 'fixed', 'important');
            input.style.setProperty('left', left + 'px', 'important');
            input.style.setProperty('width', width + 'px', 'important');
            input.style.setProperty('max-width', width + 'px', 'important');
            var inputRect = input.getBoundingClientRect();
            var inputH = Math.max(44, Math.round(inputRect.height || 52));
            var viewportH = window.parent.innerHeight || doc.documentElement.clientHeight || 900;
            var targetTop = Math.round(chatRect.bottom - inputH - 8);
            var minTop = Math.round(chatRect.top + 8);
            var maxTop = Math.min(Math.round(chatRect.bottom - inputH - 8), viewportH - inputH - 8);
            targetTop = Math.max(minTop, Math.min(targetTop, maxTop));
            input.style.setProperty('top', targetTop + 'px', 'important');
            input.style.setProperty('bottom', 'auto', 'important');
            input.style.setProperty('right', 'auto', 'important');
            input.style.setProperty('height', 'auto', 'important');
            input.style.setProperty('min-height', '0px', 'important');
            input.style.setProperty('transform', 'none', 'important');
            input.style.setProperty('z-index', '900', 'important');
            input.style.setProperty('opacity', '1', 'important');
            if (mmFrame) {{
                input.style.setProperty('background', 'transparent', 'important');
                input.style.setProperty('border', 'none', 'important');
                input.style.setProperty('border-radius', '0px', 'important');
                input.style.setProperty('backdrop-filter', 'none', 'important');
                input.style.setProperty('padding', '0px', 'important');
                input.style.setProperty('box-shadow', 'none', 'important');
                styleMultimodalFrame(mmFrame);
            }}
        }}
        function initAlignChatInput() {{
            alignChatInput();
            if (!window.parent.__ntlChatInputBound) {{
                window.parent.addEventListener('resize', alignChatInput);
                window.parent.addEventListener('scroll', alignChatInput, true);
                window.parent.__ntlChatInputBound = true;
            }}
        }}
        setTimeout(scroll, 300);
        setTimeout(initAlignChatInput, 40);
        setTimeout(alignChatInput, 400);
        setTimeout(alignChatInput, 900);
    </script>
    """
    components.html(js, height=0)

# ==============================================================================
# SECTION C: 閫氱敤 UI 杈呭姪宸ュ叿 (搴曞眰)
# ==============================================================================

def _extract_json(s: str):
    """Extract JSON from mixed text and strip JS-style comments."""
    if not isinstance(s, str): return None, s
    for open_ch, close_ch in [('{','}'), ('[',']')]:
        stack, start = 0, None
        for i, ch in enumerate(s):
            if ch == open_ch:
                if stack == 0: start = i
                stack += 1
            elif ch == close_ch and stack > 0:
                stack -= 1
                if stack == 0 and start is not None:
                    frag = s[start:i+1]
                    try:
                        clean_frag = re.sub(r'(?<!:)\/\/.*', '', frag)
                        return json.loads(clean_frag), (s[:start] + s[i+1:]).strip()
                    except Exception: 
                        pass
    return None, s


def _normalize_kb_payload(data: dict) -> dict:
    """Normalize heterogeneous KB payloads into a render-friendly schema."""
    if not isinstance(data, dict):
        return {}

    normalized = dict(data)
    schema = str(normalized.get("schema") or "").strip().lower()
    workflow = normalized.get("workflow")
    if isinstance(workflow, dict):
        for key in ("task_id", "task_name", "category", "description", "steps", "output", "result", "sources"):
            if key not in normalized and key in workflow:
                normalized[key] = workflow.get(key)

    if schema == "ntl.kb.response.v2":
        normalized["mode"] = normalized.get("mode") or ""
        if not isinstance(normalized.get("intent"), dict):
            normalized["intent"] = {}
        if "message" not in normalized and normalized.get("reason"):
            normalized["message"] = normalized.get("reason")
        if "reason" not in normalized and normalized.get("message"):
            normalized["reason"] = normalized.get("message")

    task_name = normalized.get("task_name") or normalized.get("task") or normalized.get("title") or normalized.get("task_id")
    if task_name:
        normalized["task_name"] = task_name

    normalized["category"] = normalized.get("category") or normalized.get("type") or ""
    if "output" not in normalized and "result" in normalized:
        normalized["output"] = normalized.get("result")

    steps_raw = normalized.get("steps")
    if steps_raw is None and isinstance(workflow, dict):
        steps_raw = workflow.get("steps")

    if isinstance(steps_raw, dict):
        try:
            keys = sorted(steps_raw.keys(), key=lambda x: int(str(x)) if str(x).isdigit() else str(x))
        except Exception:
            keys = list(steps_raw.keys())
        steps = [steps_raw[k] for k in keys]
    elif isinstance(steps_raw, list):
        steps = steps_raw
    else:
        steps = []

    normalized_steps = []
    for step in steps:
        if isinstance(step, dict):
            normalized_steps.append(step)
        elif step is not None:
            normalized_steps.append({"type": "note", "name": str(step)})
    normalized["steps"] = normalized_steps
    return normalized


def _strip_legacy_stream_marker(content):
    """Remove legacy inline streaming headings from historical text payloads."""
    if not isinstance(content, str):
        return content
    patterns = [
        r"^\s*\*{0,2}\s*Data_Searcher\s*\(streaming\)\s*\*{0,2}\s*:?\s*\n?",
        r"^\s*\*{0,2}\s*Code_Assistant\s*\(streaming\)\s*\*{0,2}\s*:?\s*\n?",
    ]
    text = content
    for p in patterns:
        text = re.sub(p, "", text, flags=re.IGNORECASE | re.MULTILINE)
    return text.strip()

def _render_popover(title: str):
    """Render popover if available, fallback to expander."""
    try:
        return st.popover(title)
    except Exception:
        return st.expander(title, expanded=False)

def render_label_human(msg):
    st.write(USER_TEMPLATE.replace("{{MSG}}", msg), unsafe_allow_html=True)

def render_bot_message(msg):
    st.write(BOT_TEMPLATE.replace("{{MSG}}", msg), unsafe_allow_html=True)

def render_label_ai(agent_name):
    color = "#0b5cab" if agent_name.lower() == "code_assistant" else "#0f766e"
    st.markdown(f"<div style='color:{color};font-weight:700;font-size:16px;'>🧠 {agent_name}:</div>", unsafe_allow_html=True)

def render_label_tool(tool_name):
    st.markdown(f"<div style='color:#0b5cab;font-weight:700;font-size:15px;'>🛠️ Tool ({tool_name}) Output:</div>", unsafe_allow_html=True)

def render_label_function(tool_name):
    st.markdown(f"<div style='color:#8a6f00;font-weight:700;font-size:15px;'>📌 Function Call to `{tool_name}`:</div>", unsafe_allow_html=True)

def render_divider():
    st.markdown("<hr style='margin: 15px 0; border: 1px dashed #ccc;'>", unsafe_allow_html=True)

def render_event_header(index):
    st.markdown(f"""
    <div style="border: 1px solid #ccc; border-radius: 4px; padding: 10px; margin: 12px 0; background-color: #f8f9fa;">
        <div style="display: flex; align-items: center; gap: 6px;">
            <span style="font-size: 18px; line-height: 1;">🧾</span>
            <span style="color: #4a6fa5; font-size: 18px; font-weight: 600;">{_tr('推理事件', 'Reasoning Event')} {index}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_event_human(content):
    st.markdown("<div style='color:#8a1750;font-weight:700;font-size:16px;'>👤 Human:</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='margin-left:15px;font-size:16px;'>{content}</div>", unsafe_allow_html=True)


_CHAT_INPUT_FILE_TYPES = [
    "png",
    "jpg",
    "jpeg",
    "webp",
    "bmp",
    "tif",
    "tiff",
    "pdf",
]


def _extract_chat_input_text_and_files(chat_value):
    """Normalize st.chat_input return value to (text, files)."""
    if chat_value is None:
        return "", []
    if isinstance(chat_value, str):
        return chat_value.strip(), []

    text = ""
    files = []
    if isinstance(chat_value, dict):
        text = str(chat_value.get("text", "") or "").strip()
        files = list(chat_value.get("files", []) or [])
    else:
        text = str(getattr(chat_value, "text", "") or "").strip()
        files = list(getattr(chat_value, "files", []) or [])
    return text, files


def _next_available_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    idx = 1
    while True:
        candidate = parent / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


def _decode_chat_file_bytes(file_obj) -> bytes:
    if hasattr(file_obj, "getbuffer"):
        return bytes(file_obj.getbuffer())
    if isinstance(file_obj, dict):
        raw = str(file_obj.get("data", "") or "").strip()
        if raw:
            if "," in raw and raw.lower().startswith("data:"):
                raw = raw.split(",", 1)[1]
            return base64.b64decode(raw)
    raise ValueError("Unsupported chat file payload")


def _save_chat_input_files_to_workspace(files, thread_id: str) -> dict:
    workspace = storage_manager.get_workspace(thread_id)
    input_dir = workspace / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    errors = []
    for uploaded_file in files or []:
        if isinstance(uploaded_file, dict):
            name = os.path.basename(str(uploaded_file.get("name", "") or "")).strip()
        else:
            name = os.path.basename(str(getattr(uploaded_file, "name", "") or "")).strip()
        if not name:
            continue
        target = _next_available_path(input_dir / name)
        try:
            with open(target, "wb") as f:
                f.write(_decode_chat_file_bytes(uploaded_file))
            saved.append(target.name)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")

    return {"saved": saved, "errors": errors}


def get_user_input():
    placeholder = _tr(
        "Query",
        "Query",
    )
    if multimodal_chat_input is not None:
        return multimodal_chat_input(
            placeholder=placeholder,
            accepted_file_types=_CHAT_INPUT_FILE_TYPES,
            max_file_size_mb=200,
            enable_voice_input=False,
            key="main_chat_input_mm",
        )
    return st.chat_input(
        placeholder,
        accept_file="multiple",
        file_type=_CHAT_INPUT_FILE_TYPES,
        key="main_chat_input",
    )

# ==============================================================================
# SECTION D: 鐗瑰畾涓氬姟娓叉煋鍣?(Searcher, KB)
# ==============================================================================

def render_data_searcher_output(raw_content):
    """Render structured Data Searcher output."""
    data, rest = (None, raw_content)
    if isinstance(raw_content, dict): 
        data, rest = raw_content, ""
    elif isinstance(raw_content, str): 
        data, rest = _extract_json(raw_content)

    if not isinstance(data, dict):
        if isinstance(rest, str) and rest.strip(): st.write(rest)
        return

    # SCHEMA B: News / Events
    if "event_overview" in data and isinstance(data["event_overview"], dict):
        ov = data["event_overview"]
        ov = _sanitize_paths_in_obj(ov)
        st.markdown("### Event Overview")
        st.markdown(f"- **Title**: {ov.get('Title','-')}")
        st.markdown(f"- **Event Time (UTC)**: {ov.get('Event_time_utc','-')}")
        st.markdown(f"- **Location**: {ov.get('Location','-')}")
        st.markdown(f"- **Magnitude / Scale**: {ov.get('Magnitude_or_scale', '-')}")
        
        if ov.get("Event_details"): 
            st.markdown("**Detailed Information**")
            st.write(ov["Event_details"])
        if ov.get("Summary"): 
            st.markdown("**Summary**")
            st.info(ov["Summary"])

        srcs = data.get("sources", [])
        if isinstance(srcs, dict): srcs = [srcs]
        srcs = _sanitize_paths_in_obj(srcs)
        if srcs:
            st.markdown("### Reliable Sources")
            for i, s in enumerate(srcs, 1):
                with st.container(border=True):
                    st.markdown(f"**{i}. {s.get('Publisher','-')}** 路  {s.get('Domain','')}")
                    st.markdown(f"- **Title**: {s.get('Title','-')}")
                    if s.get("URL"): st.markdown(f"- **URL**: [{s['URL']}]({s['URL']})")
                    if s.get("Snippet"): st.caption(s["Snippet"])

        with _render_popover("View Raw JSON"): st.json(_sanitize_paths_in_obj(data))
        if isinstance(rest, str) and rest.strip(): st.write(_sanitize_paths_in_text(rest))
        return

    # SCHEMA A: Geospatial Data Retrieval
    Data_source        = data.get("Data_source", "")
    Product            = data.get("Product", "")
    Temporal_coverage  = data.get("Temporal_coverage", "")
    Spatial_coverage   = data.get("Spatial_coverage", "")
    Spatial_resolution = data.get("Spatial_resolution", "")
    Files_name         = data.get("Files_name", [])
    Storage_location   = data.get("Storage_location", "")
    Auxiliary_data     = data.get("Auxiliary_data", [])

    if isinstance(Data_source, list):
        Data_source = ", ".join(str(x) for x in Data_source if x)

    if isinstance(Files_name, str): Files_name = [Files_name]
    if isinstance(Auxiliary_data, dict): Auxiliary_data = [Auxiliary_data]
    if not isinstance(Auxiliary_data, list): Auxiliary_data = []
    Storage_location = _sanitize_paths_in_text(Storage_location)

    st.markdown("### Geospatial Data Acquisition")
    cols = st.columns(2)
    with cols[0]:
        st.markdown("**Data Source**"); st.write(Data_source or "-")
        st.markdown("**Temporal Coverage**"); st.write(Temporal_coverage or "-")
        st.markdown("**Product Identifier**"); st.code(Product or "-", language="text")
    with cols[1]:
        st.markdown("**Spatial Coverage**"); st.write(Spatial_coverage or "-")
        st.markdown("**Spatial Resolution**"); st.write(Spatial_resolution or "-")
        st.markdown("**Storage Location**"); st.code(Storage_location or "Local Workspace (inputs/)")

    if Files_name:
        st.markdown("**Generated Output Files**")
        for p in Files_name: 
            # Ensure we only show the filename, avoiding double paths if agent returns full path
            fname = os.path.basename(str(p))
            st.markdown(f"- `inputs/{fname}`")

    if Auxiliary_data:
        st.markdown("### Auxiliary / Socio-economic Data")
        for i, item in enumerate(Auxiliary_data, 1):
            if not isinstance(item, dict):
                st.markdown(f"- {item}")
                continue
            with st.container(border=True):
                st.markdown(f"**{i}. {item.get('Data_type', 'Auxiliary Data')}**")
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Source**"); st.write(item.get("Source", "-"))
                    st.markdown("**Product**"); st.write(item.get("Product", "-"))
                    st.markdown("**Temporal Coverage**"); st.write(item.get("Temporal_coverage", "-"))
                with c2:
                    st.markdown("**Spatial Coverage**"); st.write(item.get("Spatial_coverage", "-"))
                    aux_files = item.get("Files_name", [])
                    if isinstance(aux_files, str):
                        aux_files = [aux_files]
                    st.markdown("**Files**")
                    if aux_files:
                        for fp in aux_files:
                            st.markdown(f"- `inputs/{os.path.basename(str(fp))}`")
                    else:
                        st.write("-")
                if item.get("Notes"):
                    st.caption(_sanitize_paths_in_text(str(item.get("Notes"))))

    with _render_popover("View Raw JSON"): st.json(_sanitize_paths_in_obj(data))
    if isinstance(rest, str) and rest.strip(): st.write(_sanitize_paths_in_text(rest))


def render_kb_output(kb_content):
    """Render NTL knowledge-base output."""
    data, rest = None, kb_content
    if isinstance(kb_content, dict): data, rest = kb_content, ""
    elif isinstance(kb_content, str): data, rest = _extract_json(kb_content)

    if not isinstance(data, dict):
        if isinstance(rest, str) and rest.strip(): st.write(rest)
        return

    normalized = _normalize_kb_payload(data)
    status = str(normalized.get("status") or "").strip().lower()
    if status in {"no_valid_tool", "empty_store", "code_corpus_unavailable", "error"}:
        reason = normalized.get("reason") or normalized.get("message") or "No details provided."
        st.warning(f"Knowledge base ({status}): {_sanitize_paths_in_text(reason)}")
        if normalized.get("sources"):
            with _render_popover("Sources"): st.json(_sanitize_paths_in_obj(normalized["sources"]))
        with _render_popover("Raw JSON"): st.json(_sanitize_paths_in_obj(data))
        if isinstance(rest, str) and rest.strip(): st.write(_sanitize_paths_in_text(rest))
        return

    if (
        not normalized.get("steps")
        and not normalized.get("description")
        and not normalized.get("output")
        and (normalized.get("reason") or normalized.get("message"))
    ):
        st.warning(_sanitize_paths_in_text(f"Knowledge base: {normalized.get('reason') or normalized.get('message')}"))
        if normalized.get("sources"):
            with _render_popover("Sources"): st.json(_sanitize_paths_in_obj(normalized["sources"]))
        with _render_popover("Raw JSON"): st.json(_sanitize_paths_in_obj(data))
        if isinstance(rest, str) and rest.strip(): st.write(_sanitize_paths_in_text(rest))
        return

    task = normalized.get("task_name") or normalized.get("task_id") or "Knowledge Base Task"
    category = normalized.get("category", "")
    mode = normalized.get("mode", "")
    schema = normalized.get("schema", "")
    st.markdown(f"""
        <div style="border:1px solid #e3e7ef;border-radius:8px;padding:14px;background:#f9fbff">
          <div style="font-size:18px;font-weight:700;color:#2b4a8b;">task: {task}</div>
          <div style="margin-top:4px;color:#5f6b7a;">category: {category}</div>
          <div style="margin-top:2px;color:#6b7280;font-size:0.88rem;">mode: {mode or '-'} | schema: {schema or '-'}</div>
        </div>
        """, unsafe_allow_html=True)

    if normalized.get("description"):
        st.markdown("**Description**")
        st.write(normalized["description"])

    steps = normalized.get("steps") or []

    if steps:
        st.markdown("**Steps**")
        for i, step in enumerate(steps, 1):
            typ, name = step.get("type", ""), step.get("name", "")
            note, desc = step.get("note", ""), step.get("description", "")
            st.markdown(f"- **{i}. {name or typ}**")
            
            has_input = "input" in step and step["input"]
            main_info = note or desc
            
            if has_input:
                with _render_popover(main_info or "Step Details"): st.json(_sanitize_paths_in_obj(step["input"]))
            elif main_info:
                st.markdown(
                    f"&nbsp;&nbsp;&nbsp;&nbsp;<span style='color:gray; font-size:0.95em;'>{_sanitize_paths_in_text(main_info)}</span>",
                    unsafe_allow_html=True,
                )

            if typ in ("geospatial_code", "code"):
                code_text = step.get("code") or step.get("Code_description")
                if code_text:
                    lang = (step.get("language") or "python").lower()
                    with _render_popover(f"View {lang} Code"): st.code(code_text, language=lang)

            if step.get("sources"):
                srcs = step["sources"]
                if isinstance(srcs, list):
                    # Clean up list formatting
                    sources_str = ", ".join(str(s) for s in srcs)
                else:
                    sources_str = str(srcs)
                st.markdown(f"*Sources for this step: {_sanitize_paths_in_text(sources_str)}*")

    if normalized.get("output"):
        st.markdown("**Output**")
        st.write(_sanitize_paths_in_text(str(normalized["output"])))
    elif not steps and not normalized.get("description"):
        st.info("Knowledge base returned structured data without workflow steps.")
        summary = {}
        for key in ("task_name", "task_id", "category", "store", "message", "reason", "query"):
            if normalized.get(key):
                summary[key] = normalized.get(key)
        if summary:
            st.json(_sanitize_paths_in_obj(summary))

    with _render_popover("Raw JSON"): st.json(_sanitize_paths_in_obj(data))
    
    if normalized.get("supplementary_text"):
        st.markdown("---")
        with st.expander("Supplementary Knowledge & Code (Mixed Mode)", expanded=False):
            st.markdown(_sanitize_paths_in_text(str(normalized.get("supplementary_text"))))

    if isinstance(rest, str) and rest.strip(): 
        # 浼樺寲 rest 鐨勬樉绀猴細鏀惧叆 Expander 骞堕檷浣?Markdown 鏍囬绾у埆
        import re
        # 灏嗚棣栫殑涓€绾ф爣棰?(# ) 鍜屼簩绾ф爣棰?(## ) 缁熶竴闄嶇骇涓哄洓绾ф爣棰?(#### )
        # 閬垮厤鍦?UI 涓覆鏌撳嚭宸ㄥぇ鐨勬爣棰橈紝淇濇寔灞傜骇鍜岃皭
        formatted_rest = re.sub(r'^(#+)\s', r'#### ', rest, flags=re.MULTILINE)
        
        st.markdown("---")
        with st.expander("Supplementary Knowledge & Code (Mixed Mode)", expanded=False):
            st.markdown(formatted_rest)


def render_uploaded_understanding_output(raw_content, tool_name: str = ""):
    """Render structured output for uploaded PDF/image understanding tools."""
    data, rest = (None, raw_content)
    if isinstance(raw_content, dict):
        data, rest = raw_content, ""
    elif isinstance(raw_content, str):
        data, rest = _extract_json(raw_content)

    if not isinstance(data, dict):
        if isinstance(rest, str) and rest.strip():
            st.write(_sanitize_paths_in_text(rest))
        return

    status = str(data.get("status", "")).strip() or "unknown"
    targets = data.get("targets", [])
    if isinstance(targets, str):
        targets = [targets]
    if not isinstance(targets, list):
        targets = []
    warnings = data.get("warnings", [])
    if isinstance(warnings, str):
        warnings = [warnings]
    if not isinstance(warnings, list):
        warnings = []
    snippets = data.get("snippets", [])
    if not isinstance(snippets, list):
        snippets = []

    if "pdf" in str(tool_name).lower():
        st.markdown("### Uploaded PDF Understanding")
    elif "image" in str(tool_name).lower():
        st.markdown("### Uploaded Image Understanding")
    else:
        st.markdown("### Uploaded File Understanding")

    st.markdown(f"**Status**: `{status}`")

    if targets:
        st.markdown("**Target Files**")
        for f in targets:
            st.markdown(f"- `inputs/{os.path.basename(str(f))}`")

    merge_stats = data.get("merge_stats", {})
    if isinstance(merge_stats, dict) and merge_stats:
        st.caption(
            _tr(
                f"注入统计：新增 {merge_stats.get('inserted', 0)}，更新 {merge_stats.get('updated', 0)}，总计 {merge_stats.get('total', 0)}",
                f"Injection stats: inserted {merge_stats.get('inserted', 0)}, updated {merge_stats.get('updated', 0)}, total {merge_stats.get('total', 0)}",
            )
        )

    if warnings:
        for w in warnings:
            st.warning(_sanitize_paths_in_text(str(w)))

    if snippets:
        st.markdown("**Relevant Snippets**")
        for i, s in enumerate(snippets, 1):
            if not isinstance(s, dict):
                continue
            with st.container(border=True):
                source = os.path.basename(str(s.get("source_file", "")))
                file_type = str(s.get("file_type", "") or "-")
                page = s.get("page")
                score = s.get("score")
                meta = [f"`{source}`", f"type={file_type}"]
                if page not in (None, "", 0):
                    meta.append(f"page={page}")
                if score not in (None, ""):
                    meta.append(f"score={score}")
                st.markdown(f"**{i}.** " + " | ".join(meta))
                text = _sanitize_paths_in_text(str(s.get("text", "") or "").strip())
                if text:
                    st.write(text)
    elif status == "context_injected_no_match":
        st.info(
            _tr(
                "文件已成功解析并注入上下文，但当前问题未命中相关片段。可换一种更具体问法（如指定文件名、页码、关键词）。",
                "File context was parsed and injected successfully, but this query found no direct snippet match. "
                "Try a more specific question (file name, page, or keywords).",
            )
        )
    elif status != "success":
        message = data.get("message")
        if message:
            st.info(_sanitize_paths_in_text(str(message)))

    with _render_popover("View Raw JSON"):
        st.json(_sanitize_paths_in_obj(data))
    if isinstance(rest, str) and rest.strip():
        st.write(_sanitize_paths_in_text(rest))

# ==============================================================================
# SECTION E: 渚ц竟鏍忕粍浠?(Sidebar, Download, Upload)
# ==============================================================================

def render_sidebar():
    """Render all sidebar controls."""
    with st.sidebar:
        st.subheader(_tr("NTL-GPT 控制台", "NTL-GPT Console"))

        workspace = storage_manager.get_workspace(st.session_state.get("thread_id", "debug"))
        # User/session scope: each user owns independent thread history in workspace.
        current_user_id = str(st.session_state.get("user_id", "") or "").strip()
        if not current_user_id or history_store.is_reserved_user_id(current_user_id):
            current_user_id = history_store.generate_anonymous_user_id()
            st.session_state["user_id"] = current_user_id
            st.session_state["user_name"] = ""

        current_user_name = str(st.session_state.get("user_name", "") or "")
        bootstrap_anonymous = str(current_user_id).startswith("anon-")
        typed_user_name = st.text_input(
            _tr("用户名（限英文）", "Username (only English)"),
            value=current_user_name,
            key="sidebar_user_name_input",
            help=_tr("用于隔离用户历史记录。", "Used to isolate per-user history."),
        )

        normalized_typed_user = history_store.normalize_user_id(typed_user_name)
        stripped_user_name = str(typed_user_name or "").strip()
        username_ready = (
            bool(stripped_user_name)
            and (not history_store.is_reserved_user_id(normalized_typed_user))
            and (not bootstrap_anonymous)
        )
        if (not stripped_user_name) or history_store.is_reserved_user_id(normalized_typed_user):
            if stripped_user_name and stripped_user_name != current_user_name:
                st.warning(
                    _tr(
                        "guest/debug/default/anonymous 为保留用户名，请使用其他用户名。",
                        "guest/debug/default/anonymous are reserved names. Please choose another username.",
                    )
                )
                st.session_state["sidebar_user_name_input"] = current_user_name
        elif normalized_typed_user != current_user_id or bootstrap_anonymous:
            st.session_state["user_name"] = typed_user_name or normalized_typed_user
            st.session_state["user_id"] = normalized_typed_user
            history_store.ensure_user_profile(normalized_typed_user, typed_user_name or normalized_typed_user)
            known_threads = history_store.list_user_threads(normalized_typed_user, limit=100)
            if known_threads:
                app_state.set_active_thread(str(known_threads[0].get("thread_id")))
            else:
                new_thread_id = history_store.generate_thread_id(normalized_typed_user)
                app_state.set_active_thread(new_thread_id)
                history_store.bind_thread_to_user(normalized_typed_user, new_thread_id)
            st.rerun()

        if not username_ready:
            st.warning(
                _tr(
                    "请先创建一个用户名。",
                    "Please create an username first.",
                )
            )

        if username_ready:
            user_threads = history_store.list_user_threads(current_user_id, limit=100)
            thread_ids = [str(row.get("thread_id")) for row in user_threads if row.get("thread_id")]
            thread_ids = [tid for tid in thread_ids if tid]
            current_tid = str(st.session_state.get("thread_id", "debug") or "debug")

            if not thread_ids:
                new_thread_id = history_store.generate_thread_id(current_user_id)
                app_state.set_active_thread(new_thread_id)
                history_store.bind_thread_to_user(current_user_id, new_thread_id)
                st.rerun()

            if current_tid not in thread_ids:
                app_state.set_active_thread(thread_ids[0])
                st.rerun()

            thread_label_map = {}
            for row in user_threads:
                tid = str(row.get("thread_id", "")).strip()
                if not tid:
                    continue
                q = str(row.get("last_question", "") or "").strip()
                q_short = (q[:28] + "...") if len(q) > 28 else q
                label = f"{tid} | {q_short}" if q_short else tid
                thread_label_map[tid] = label
            default_idx = thread_ids.index(current_tid) if current_tid in thread_ids else 0
            selected_tid = st.selectbox(
                _tr("历史线程", "History Threads"),
                options=thread_ids,
                index=default_idx,
                format_func=lambda tid: thread_label_map.get(tid, tid),
                key="sidebar_thread_selector",
            )
            if selected_tid != current_tid:
                app_state.set_active_thread(selected_tid)
                history_store.bind_thread_to_user(current_user_id, selected_tid)
                st.rerun()


        # in_count = len(list((workspace / "inputs").glob("*.*"))) if (workspace / "inputs").exists() else 0
        # out_count = len(list((workspace / "outputs").glob("*.*"))) if (workspace / "outputs").exists() else 0
        current_model = st.session_state.get("cfg_model", app_state.MODEL_OPTIONS[0])
        if current_model not in app_state.MODEL_OPTIONS:
            current_model = app_state.MODEL_OPTIONS[0]
        selected_model = st.selectbox(
            _tr("模型", "Model"),
            app_state.MODEL_OPTIONS,
            index=app_state.MODEL_OPTIONS.index(current_model),
            key="model_selector"
        )
        st.session_state["cfg_model"] = selected_model

        key_label = "OpenAI API Key"
        if "qwen" in selected_model.lower():
            key_label = "DashScope API Key"
        elif "claude" in selected_model.lower():
            key_label = "Anthropic API Key"

        use_env_key_for_qwen = "qwen" in selected_model.lower()
        env_qwen_key = (os.getenv("DASHSCOPE_API_KEY") or "").strip()
        user_api_key = ""
        if use_env_key_for_qwen:
            if env_qwen_key:
                st.caption(
                    _tr(
                        "",
                        "",
                    )
                )
            else:
                st.warning(
                    _tr(
                        "未检测到 .env 中的 DASHSCOPE_API_KEY，激活会失败。",
                        "DASHSCOPE_API_KEY not found in .env; activation will fail.",
                    )
                )
        else:
            user_api_key = st.text_input(
                label=_tr(f"输入 {key_label}", f"Enter {key_label}"),
                type="password",
                help=_tr("激活系统所必需。", "Required to activate the agent system."),
                key="user_api_key_input"
            )

        action_cols = st.columns(3, gap="small")
        with action_cols[0]:
            if st.button(
                _tr("激活", "Activate"),
                key="activate_btn",
                use_container_width=True,
                type="secondary",
                disabled=not username_ready,
            ):
                effective_api_key = ""
                can_activate = True
                if use_env_key_for_qwen:
                    effective_api_key = env_qwen_key
                    if not effective_api_key:
                        st.error(
                            _tr(
                                "请先在 .env 中配置 DASHSCOPE_API_KEY。",
                                "Please set DASHSCOPE_API_KEY in .env first.",
                            )
                        )
                        can_activate = False
                else:
                    effective_api_key = (user_api_key or "").strip()
                    if not effective_api_key:
                        st.error(_tr(f"请输入 {key_label}！", f"Please enter your {key_label}!"))
                        can_activate = False

                if can_activate and effective_api_key:
                    st.session_state["user_api_key"] = effective_api_key
                    st.session_state["initialized"] = True
                    
                    app_logic.ensure_conversation_initialized()
                    st.success(_tr("已激活！", "Activated!"))
                    st.rerun()
                # ---------------------

        with action_cols[1]:
            if st.button(
                _tr("新建", "New"),
                key="reset_btn",
                use_container_width=True,
                type="secondary",
                disabled=not username_ready,
            ):
                st.cache_resource.clear()
                st.session_state["initialized"] = False
                st.session_state.chat_history = []
                st.session_state.analysis_logs = []
                st.session_state.analysis_history = []
                st.session_state.last_question = ""
                st.session_state["cancel_requested"] = False

                if "user_api_key" in st.session_state:
                    del st.session_state["user_api_key"]

                uid = str(st.session_state.get("user_id", "") or "").strip()
                if not uid or history_store.is_reserved_user_id(uid):
                    uid = history_store.generate_anonymous_user_id()
                    st.session_state["user_id"] = uid
                    st.session_state["user_name"] = ""
                new_thread_id = history_store.generate_thread_id(uid)
                app_state.set_active_thread(new_thread_id)
                history_store.bind_thread_to_user(uid, new_thread_id)
                st.warning(_tr("已创建新会话。", "New session created."))
                st.rerun()

        with action_cols[2]:
            if st.button(
                _tr("中断", "Stop"),
                key="interrupt_current_run_btn",
                use_container_width=True,
                type="secondary",
                help=_tr("请求立即中断当前回答。", "Request immediate interruption of the current run."),
            ):
                if st.session_state.get("is_running", False):
                    st.session_state["cancel_requested"] = True
                    st.warning(_tr("已发送中断请求。", "Interrupt request sent."))
                    st.rerun()

        status = _tr("已激活", "Active") if st.session_state.get("initialized") else _tr("未激活", "Inactive")
        status_class = "active" if st.session_state.get("initialized") else "inactive"
        st.markdown(
            (
                "<div class='ntl-thread-status-row'>"
                f"<span class='ntl-thread-status-item'><span>{_tr('线程 ID', 'Thread ID')}:</span>"
                f"<span class='ntl-thread-status-value'>{st.session_state.thread_id}</span></span>"
                f"<span class='ntl-thread-status-item'><span>{_tr('状态', 'Status')}:</span>"
                f"<span class='ntl-status-text {status_class}'>{status}</span></span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        st.markdown("<hr style='margin: 8px 0;'>", unsafe_allow_html=True)

        with st.expander("NTL Data Availability", expanded=False):
            _render_data_availability_block()

        with st.expander(_tr("测试用例", "Test Cases"), expanded=False):
            try:
                case_files = [Path("./example/test_cases_mini.xlsx")]
                loaded_names = []
                frames = []
                for fp in case_files:
                    if fp.exists():
                        frames.append(pd.read_excel(fp))
                        loaded_names.append(fp.name)

                if not frames:
                    raise FileNotFoundError("No test case file found. Expected test_cases.xlsx or test_cases_extended_50.xlsx")

                df_cases = pd.concat(frames, ignore_index=True)
                df_cases = df_cases.dropna(subset=['Case'])
                df_cases = df_cases.drop_duplicates(subset=['Case'], keep='first')
                df_cases['Category'] = df_cases['Category'].fillna("General").astype(str)
                df_cases['Label'] = df_cases['Label'].fillna("Unnamed Task").astype(str)
                categories = {}
                for _, row in df_cases.iterrows():
                    cat = row['Category'].strip().title() 
                    if cat not in categories: categories[cat] = []
                    categories[cat].append({"label": row['Label'].strip(), "query": str(row['Case']).strip()})

                for cat, cases in categories.items():
                    with st.expander(f"{cat}", expanded=False):
                        for i, case in enumerate(cases, 1):
                            st.markdown(f"**{i}. {case['label']}**")
                            st.markdown(
                                f"<div style='color:#cfe1ff;font-size:0.95rem;line-height:1.55;'>{case['query']}</div>",
                                unsafe_allow_html=True,
                            )
                            if st.button(_tr(f"运行用例", f"Run Case"), key=f"run_case_{cat}_{i}", use_container_width=True):
                                st.session_state["pending_question"] = case["query"]
                                st.rerun()
            except Exception as e:
                st.error(f"Failed to load test case files: {e}")

def render_download_center():
    """Render input/output download center in sidebar."""
    try:
        workspace = storage_manager.get_workspace(st.session_state.get("thread_id", "debug"))
        def get_valid_files(directory, include_py=False):
            if not directory.exists(): return []
            return [f for f in directory.glob("*.*") 
                    if f.suffix.lower() not in ([ ".zip", ".tmp"] + ([] if include_py else [".py"])) and not f.name.startswith('.')]

        in_files = get_valid_files(workspace / "inputs", include_py=False)
        out_files = get_valid_files(workspace / "outputs", include_py=True)

        if not in_files and not out_files: return

        st.sidebar.markdown("<div class='ntl-sidebar-divider-tight'></div>", unsafe_allow_html=True)
        st.sidebar.subheader(_tr("数据中心", "Data Center"))
        tab_in, tab_out = st.sidebar.tabs([_tr("输入", "Inputs"), _tr("输出", "Outputs")])

        with tab_in:
            if in_files:
                for f in in_files:
                    with open(f, "rb") as file_data:
                        st.download_button(
                            label=f"{f.name}",
                            data=file_data,
                            file_name=f.name,
                            key=f"dl_in_{f.name}",
                            use_container_width=True,
                        )
            else:
                st.caption(_tr("暂无", "Empty"))

        with tab_out:
            if out_files:
                for f in out_files:
                    with open(f, "rb") as file_data:
                        st.download_button(
                            label=f"{f.name}",
                            data=file_data,
                            file_name=f.name,
                            key=f"dl_out_{f.name}",
                            use_container_width=True,
                        )
            else:
                st.caption(_tr("暂无", "Empty"))
    except Exception as e:
        st.sidebar.error(f"Download Center Error: {e}")

def render_file_uploader():
    """Render file uploader in sidebar."""
    st.markdown("<hr style='margin: 8px 0;'>", unsafe_allow_html=True)
    
    uploaded_files = st.sidebar.file_uploader(
        _tr("上传数据文件", "Upload Data Files"),
        accept_multiple_files=True,
        type=['tif', 'tiff', 'shp', 'dbf', 'prj', 'shx', 'geojson', 'csv', 'xlsx', 'xls', 'zip', 'pdf', 'png', 'jpg', 'jpeg', 'webp', 'bmp'],
        key="data_uploader"
    )

    if uploaded_files:
        workspace = storage_manager.get_workspace(st.session_state.get("thread_id", "debug"))
        input_dir = workspace / "inputs"
        for uploaded_file in uploaded_files:
            target_path = input_dir / uploaded_file.name
            if not target_path.exists():
                if uploaded_file.name.endswith(".zip"):
                    with zipfile.ZipFile(uploaded_file, "r") as zip_ref:
                        zip_ref.extractall(input_dir)
                    st.sidebar.success(_tr(f"已解压：{uploaded_file.name}", f"Extracted: {uploaded_file.name}"))
                else:
                    with open(target_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                st.sidebar.success(_tr(f"已上传：{uploaded_file.name}", f"Uploaded: {uploaded_file.name}"))


def render_file_understanding_panel():
    """Manual file-understanding panel (no auto-token usage on upload)."""
    st.sidebar.markdown("<hr style='margin: 8px 0;'>", unsafe_allow_html=True)
    st.sidebar.subheader(_tr("文件理解（手动触发）", "File Understanding (Manual)"))
    st.sidebar.caption(
        _tr(
            "上传后不会自动理解。仅在你点击按钮时，才会解析并注入相关片段到上下文。",
            "Upload stays passive. Parsing/context injection only runs when you click the action button.",
        )
    )

    workspace = storage_manager.get_workspace(st.session_state.get("thread_id", "debug"))
    input_dir = workspace / "inputs"
    supported_ext = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
    files = []
    if input_dir.exists():
        files = sorted(
            [p for p in input_dir.glob("*.*") if p.suffix.lower() in supported_ext],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    if not files:
        st.sidebar.info(_tr("当前线程 inputs 下没有可理解文件。", "No supported files in current thread inputs."))
        return

    file_options = [p.name for p in files]
    default_pick = file_options[: min(3, len(file_options))]
    selected_files = st.sidebar.multiselect(
        _tr("选择文件", "Select Files"),
        options=file_options,
        default=default_pick,
        key="manual_understanding_file_selector",
    )
    default_max_pages = 120
    default_top_n = 4
    default_max_chars = 6000
    st.session_state["manual_understanding_max_pages"] = default_max_pages
    st.session_state["injected_context_top_n"] = default_top_n
    st.session_state["injected_context_max_chars"] = default_max_chars
    st.sidebar.caption(
        _tr(
            "默认参数：PDF页数=120，Top-N=4，最大注入字符=6000（固定）。",
            "Defaults: Max PDF Pages=120, Top-N=4, Max Injected Chars=6000 (fixed).",
        )
    )

    if st.sidebar.button(_tr("理解并注入上下文", "Analyze and Inject Context"), use_container_width=True):
        if not selected_files:
            st.sidebar.warning(_tr("请至少选择一个文件。", "Please select at least one file."))
        else:
            with st.sidebar:
                with st.spinner(_tr("正在解析文件...", "Parsing files...")):
                    result = app_logic.inject_selected_files_to_context(
                        file_names=selected_files,
                        max_pages=default_max_pages,
                    )
            merge_stats = result.get("merge_stats", {}) or {}
            st.sidebar.success(
                _tr(
                    f"完成：新增 {merge_stats.get('inserted', 0)}，更新 {merge_stats.get('updated', 0)}，总计 {merge_stats.get('total', 0)}。",
                    f"Done: inserted {merge_stats.get('inserted', 0)}, updated {merge_stats.get('updated', 0)}, total {merge_stats.get('total', 0)}.",
                )
            )
            for w in result.get("warnings", []) or []:
                st.sidebar.warning(str(w))
            if result.get("unsupported_files"):
                st.sidebar.caption(
                    _tr(
                        f"不支持：{', '.join(result.get('unsupported_files'))}",
                        f"Unsupported: {', '.join(result.get('unsupported_files'))}",
                    )
                )
            if result.get("missing_files"):
                st.sidebar.caption(
                    _tr(
                        f"缺失：{', '.join(result.get('missing_files'))}",
                        f"Missing: {', '.join(result.get('missing_files'))}",
                    )
                )

    current_injected = history_store.injected_file_overview(str(st.session_state.get("thread_id", "debug")))
    if current_injected:
        st.sidebar.caption(_tr("当前已注入文件", "Currently Injected Files"))
        for row in current_injected[:12]:
            st.sidebar.markdown(
                f"- `{row.get('source_file')}` · {row.get('chunks', 0)} chunks"
            )
        if st.sidebar.button(_tr("清空注入上下文", "Clear Injected Context"), use_container_width=True):
            app_logic.clear_injected_context()
            st.sidebar.success(_tr("已清空。", "Cleared."))
            st.rerun()

def show_history(chat_history):
    """Render chat history, images, and tables."""
    for role, content in chat_history:
        if role == "user":
            st.write(USER_TEMPLATE.replace("{{MSG}}", content), unsafe_allow_html=True)
        elif role == "assistant":
            st.write(BOT_TEMPLATE.replace("{{MSG}}", content), unsafe_allow_html=True)
        elif role == "assistant_img":
            file_name = os.path.basename(content)
            st.image(content, width=600, caption=_tr(f"图像结果: {file_name}", f"Plot: {file_name}"))
        elif role == "assistant_table":
            file_name = os.path.basename(content)
            try:
                df = pd.read_csv(content)
                with st.expander(_tr(f"查看统计表: {file_name}", f"View statistics table: {file_name}"), expanded=False):
                    st.dataframe(df, use_container_width=True)
            except Exception as e:
                st.error(_tr(f"读取表格失败 {file_name}: {e}", f"Failed to load table {file_name}: {e}"))
    scroll_to_bottom()

import matplotlib.colors as mcolors

def render_map_view():
    """Render map view for vector/raster layers."""
    workspace = storage_manager.get_workspace(st.session_state.get("thread_id", "debug"))
    geo_files = []
    for folder in ["inputs", "outputs"]:
        path = workspace / folder
        if path.exists():
            geo_files.extend([f for f in path.glob("*.*") if f.suffix.lower() in [".tif", ".tiff", ".shp", ".geojson"]])

    if not geo_files:
        st.info(_tr("暂无地理数据可视化。", "No geospatial data available yet."))
        return

    geo_files = sorted(geo_files, key=lambda p: p.stat().st_mtime)
    option_keys = {str(p): p for p in geo_files}
    current_tif = st.session_state.get("current_map_tif")
    preferred = next((f for f in geo_files if current_tif and str(f) == str(current_tif)), None)
    default_layer = preferred or geo_files[-1]

    raw_selected = st.session_state.get("selected_layers")
    if raw_selected is None:
        sanitized_selected = [default_layer]
    else:
        if not isinstance(raw_selected, list):
            raw_selected = [raw_selected]
        sanitized_selected = []
        for item in raw_selected:
            key = str(item)
            if key in option_keys:
                sanitized_selected.append(option_keys[key])
        if not sanitized_selected:
            sanitized_selected = [default_layer]
    st.session_state["selected_layers"] = sanitized_selected

    selected_layers = st.multiselect(
        _tr("选择显示图层", "Select Layers to Display"),
        options=geo_files,
        default=sanitized_selected,
        format_func=lambda x: f"[{x.parent.name}] {x.name}",
    )
    st.session_state["selected_layers"] = selected_layers

    if not selected_layers:
        st.warning(_tr("请至少选择一个图层进行可视化。", "Please select at least one layer to visualize."))
        m = folium.Map(location=[31.23, 121.47], zoom_start=8, control_scale=True)
        folium.TileLayer("CartoDB dark_matter", name="Dark Canvas").add_to(m)
        st_folium(m, width=None, height=520, use_container_width=True)
        return

    if "layer_styles" not in st.session_state:
        st.session_state["layer_styles"] = {}

    with st.expander(_tr("图层样式（配色与透明度）", "Layer Styling (Symbology & Opacity)"), expanded=False):
        active_layer_file = st.selectbox(
            _tr("配置图层", "Configure Layer"),
            options=selected_layers,
            format_func=lambda x: x.name,
            key="style_target_selector",
        )

        layer_key = str(active_layer_file.name)
        current_style = st.session_state["layer_styles"].get(layer_key, {
            "opacity": 0.8,
            "vis_mode": "Auto",
            "colormap": "viridis",
            "mask_color": "#FF0000",
        })

        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            new_opacity = st.slider(_tr("透明度", "Opacity"), 0.0, 1.0, current_style["opacity"], key=f"op_{layer_key}")
        with col_s2:
            vis_modes = ["Auto", "Stretched (Continuous)", "Discrete (Categorical/Mask)"]
            try:
                idx = vis_modes.index(current_style["vis_mode"])
            except Exception:
                idx = 0
            new_vis_mode = st.selectbox(_tr("可视化模式", "Visualization Mode"), vis_modes, index=idx, key=f"vm_{layer_key}")
        with col_s3:
            if new_vis_mode == "Discrete (Categorical/Mask)":
                new_mask_color = st.color_picker(_tr("掩膜颜色（值=1）", "Mask Color (for value=1)"), current_style["mask_color"], key=f"mc_{layer_key}")
                new_colormap = current_style["colormap"]
            else:
                colormap_options = ["gray", "magma", "viridis", "inferno", "cividis", "plasma", "coolwarm"]
                try:
                    idx_cm = colormap_options.index(current_style["colormap"])
                except Exception:
                    idx_cm = 2
                new_colormap = st.selectbox("Colormap", colormap_options, index=idx_cm, key=f"cm_{layer_key}")
                new_mask_color = current_style["mask_color"]

        st.session_state["layer_styles"][layer_key] = {
            "opacity": new_opacity,
            "vis_mode": new_vis_mode,
            "colormap": new_colormap,
            "mask_color": new_mask_color,
        }

    def _add_bound(bounds_acc, min_lat, min_lon, max_lat, max_lon):
        vals = [min_lat, min_lon, max_lat, max_lon]
        if all(np.isfinite(v) for v in vals):
            bounds_acc.append(vals)

    overall_bounds = []
    m = folium.Map(control_scale=True)
    folium.TileLayer("CartoDB dark_matter", name="Dark Canvas").add_to(m)
    folium.TileLayer("https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", attr="Google", name="Satellite").add_to(m)
    for file_path in selected_layers:
        try:
            layer_name = file_path.name
            style = st.session_state["layer_styles"].get(layer_name, {
                "opacity": 0.8, "vis_mode": "Auto", "colormap": "viridis", "mask_color": "#FF0000"
            })

            if file_path.suffix.lower() in [".tif", ".tiff"]:
                with rasterio.open(file_path) as src:
                    from rasterio.warp import transform_bounds as rio_transform_bounds

                    src_crs = src.crs if src.crs else "EPSG:4326"
                    bounds = rio_transform_bounds(src_crs, "EPSG:4326", *src.bounds, densify_pts=21)
                    _add_bound(overall_bounds, bounds[1], bounds[0], bounds[3], bounds[2])

                    if src.count >= 3:
                        rgb_data = []
                        for b in [1, 2, 3]:
                            band = src.read(b).astype(float)
                            p2, p98 = np.percentile(band[band > 0], [2, 98]) if np.any(band > 0) else (0, 1)
                            if p98 - p2 == 0:
                                p98 += 1e-6
                            band = np.clip((band - p2) / (p98 - p2), 0, 1)
                            rgb_data.append(band)
                        img_array = np.stack(rgb_data, axis=-1)
                        alpha = np.where(np.sum(img_array, axis=-1) > 0, 1.0, 0.0)
                        img_array = np.dstack([img_array, alpha])
                        img_pil = Image.fromarray((img_array * 255).astype(np.uint8))
                    else:
                        data = src.read(1)
                        is_categorical = False
                        if style["vis_mode"] == "Discrete (Categorical/Mask)":
                            is_categorical = True
                        elif style["vis_mode"] == "Auto":
                            unique_vals = np.unique(data)
                            if len(unique_vals) < 15:
                                is_categorical = True

                        if is_categorical:
                            img_rgba = np.zeros((data.shape[0], data.shape[1], 4), dtype=np.uint8)
                            mask_c = mcolors.to_rgb(style["mask_color"])
                            mask_rgb = [int(c * 255) for c in mask_c]
                            foreground_mask = (data > 0) & (data != src.nodata)
                            img_rgba[foreground_mask, 0] = mask_rgb[0]
                            img_rgba[foreground_mask, 1] = mask_rgb[1]
                            img_rgba[foreground_mask, 2] = mask_rgb[2]
                            img_rgba[foreground_mask, 3] = 255
                            img_pil = Image.fromarray(img_rgba)
                        else:
                            data = data.astype(float)
                            valid_mask = (data != src.nodata) & (~np.isnan(data))
                            if np.any(valid_mask):
                                valid_data = data[valid_mask]
                                p2, p98 = np.percentile(valid_data, [2, 98])
                                if p98 - p2 == 0:
                                    p98 += 1e-6
                                data_norm = np.clip((data - p2) / (p98 - p2), 0, 1)
                            else:
                                data_norm = np.zeros_like(data)
                            colormap = cm.get_cmap(style["colormap"])
                            img_array = colormap(data_norm)
                            img_array[..., 3] = np.where(valid_mask & (data > 0), 1.0, 0.0)
                            img_pil = Image.fromarray((img_array * 255).astype(np.uint8))

                    folium.raster_layers.ImageOverlay(
                        image=np.array(img_pil),
                        bounds=[[bounds[1], bounds[0]], [bounds[3], bounds[2]]],
                        opacity=style["opacity"],
                        name=f"{file_path.name}",
                        interactive=True,
                        cross_origin=False,
                    ).add_to(m)

            elif file_path.suffix.lower() in [".shp", ".geojson"]:
                gdf = gpd.read_file(file_path)
                if gdf.empty:
                    continue
                if gdf.crs is None:
                    gdf = gdf.set_crs(epsg=4326, allow_override=True)
                elif str(gdf.crs).upper() != "EPSG:4326":
                    gdf = gdf.to_crs(epsg=4326)
                b = gdf.total_bounds
                _add_bound(overall_bounds, b[1], b[0], b[3], b[2])

                folium.GeoJson(
                    gdf,
                    name=f"{file_path.name}",
                    style_function=lambda x: {"color": "#ff0000", "weight": 2, "opacity": 0.7, "fillOpacity": 0.1},
                ).add_to(m)

        except Exception as e:
            st.error(_tr(f"图层加载失败 {file_path.name}: {e}", f"Error loading {file_path.name}: {e}"))

    if overall_bounds:
        try:
            min_lat = min(b[0] for b in overall_bounds)
            min_lon = min(b[1] for b in overall_bounds)
            max_lat = max(b[2] for b in overall_bounds)
            max_lon = max(b[3] for b in overall_bounds)
            if max_lat - min_lat < 1e-6:
                max_lat += 0.001
                min_lat -= 0.001
            if max_lon - min_lon < 1e-6:
                max_lon += 0.001
                min_lon -= 0.001
            m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])
        except Exception:
            m.location = [31.23, 121.47]
            m.zoom_start = 9
    else:
        center = st.session_state.get("map_center", [31.23, 121.47])
        m.location = center
        m.zoom_start = 9

    folium.LayerControl().add_to(m)
    map_output = st_folium(m, width=None, height=540, use_container_width=True, key="main_map")

    if map_output and map_output.get("last_clicked"):
        click_lat = map_output["last_clicked"]["lat"]
        click_lon = map_output["last_clicked"]["lng"]
        st.session_state["map_center"] = [click_lat, click_lon]

        last_tif = next((f for f in reversed(selected_layers) if f.suffix.lower() in [".tif", ".tiff"]), None)
        if last_tif:
            try:
                with rasterio.open(last_tif) as src:
                    if src.crs is None:
                        return
                    from pyproj import Transformer

                    transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                    x, y = transformer.transform(click_lon, click_lat)
                    if (src.bounds.left <= x <= src.bounds.right) and (src.bounds.bottom <= y <= src.bounds.top):
                        row, col = src.index(x, y)
                        val = src.read(1, window=rasterio.windows.Window(col, row, 1, 1))
                        if val.size > 0:
                            v = val[0, 0]
                            st.info(_tr(f"识别结果\n- 图层: `{last_tif.name}`\n- 值: `{v}`", f"Identify Result\n- Layer: `{last_tif.name}`\n- Value: `{v}`"))
            except Exception as e:
                st.warning(_tr(f"像元识别失败: {e}", f"Pixel identify failed: {e}"))

def _build_reasoning_sections(events):
    """Group adjacent messages for compact single-panel reasoning view."""
    grouped = []
    for event in events:
        if not isinstance(event, dict):
            continue
        kb_records = []
        notice_records = []
        raw_kb = event.get("kb_progress")
        if isinstance(raw_kb, list):
            kb_records.extend([x for x in raw_kb if isinstance(x, dict)])
        raw_custom = event.get("custom")
        if isinstance(raw_custom, list):
            kb_records.extend(
                [x for x in raw_custom if isinstance(x, dict) and x.get("event_type") == "kb_progress"]
            )
            notice_records.extend(
                [
                    x
                    for x in raw_custom
                    if isinstance(x, dict)
                    and x.get("event_type")
                    in {"auto_image_understanding_triggered", "auto_pdf_understanding_triggered"}
                ]
            )
        if kb_records:
            if grouped and grouped[-1]["kind"] == "kb_progress":
                grouped[-1]["records"].extend(kb_records)
            else:
                grouped.append({"kind": "kb_progress", "records": list(kb_records)})
        if notice_records:
            if grouped and grouped[-1]["kind"] == "custom_notice":
                grouped[-1]["records"].extend(notice_records)
            else:
                grouped.append({"kind": "custom_notice", "records": list(notice_records)})

        msgs = event.get("messages", [])
        if not isinstance(msgs, list):
            continue

        for msg in msgs:
            md = getattr(msg, "response_metadata", None)
            if not isinstance(md, dict) and isinstance(msg, dict):
                md = msg.get("response_metadata")
            if isinstance(md, dict) and md.get("__is_handoff_back"):
                continue

            if isinstance(msg, AIMessage):
                agent = (msg.name or "AI")
                if "(streaming)" in agent.lower():
                    # Skip transient streaming markers; final messages are rendered below.
                    continue
                if grouped and grouped[-1]["kind"] == "ai" and grouped[-1]["agent"] == agent:
                    grouped[-1]["messages"].append(msg)
                else:
                    grouped.append({"kind": "ai", "agent": agent, "messages": [msg]})
            elif isinstance(msg, ToolMessage):
                tool_name = msg.name or "tool"
                if grouped and grouped[-1]["kind"] == "tool" and grouped[-1]["tool"] == tool_name:
                    grouped[-1]["messages"].append(msg)
                else:
                    grouped.append({"kind": "tool", "tool": tool_name, "messages": [msg]})
            elif isinstance(msg, HumanMessage):
                if grouped and grouped[-1]["kind"] == "human":
                    grouped[-1]["messages"].append(msg)
                else:
                    grouped.append({"kind": "human", "messages": [msg]})
    return grouped


def _dedupe_tool_messages(messages: list[ToolMessage]) -> list[ToolMessage]:
    """Deduplicate repeated tool messages emitted from mixed stream modes."""
    seen = set()
    unique: list[ToolMessage] = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        key = (
            str(getattr(msg, "name", "") or "").strip(),
            str(getattr(msg, "tool_call_id", "") or "").strip(),
            _normalize_content_to_text(getattr(msg, "content", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(msg)
    return unique


def _normalize_content_to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def _get_ui_thread_id() -> str:
    return str(st.session_state.get("thread_id", "debug") or "debug")


def _to_ui_relative_path(path_str: str, thread_id: Optional[str] = None) -> str:
    """Convert absolute/local paths into UI-safe relative paths."""
    raw = str(path_str or "").strip()
    if not raw:
        return raw

    tid = str(thread_id or _get_ui_thread_id())
    repo_root = Path.cwd().resolve()
    workspace = storage_manager.get_workspace(tid).resolve()

    candidate = raw.strip("\"'`")
    candidate_norm = candidate.replace("/", "\\")

    # Explicitly normalize any user_data absolute-like path.
    m = re.search(r"(user_data[\\/][^\\/]+[\\/](?:inputs|outputs)[\\/][^\s\"'`]+)", candidate, flags=re.IGNORECASE)
    if m:
        rel_user_data = m.group(1).replace("\\", "/")
        parts = rel_user_data.split("/")
        if len(parts) >= 3:
            parts[1] = tid
        return "/".join(parts)

    try:
        p = Path(candidate)
        if p.is_absolute():
            resolved = p.resolve()
            try:
                rel_to_ws = resolved.relative_to(workspace)
                return rel_to_ws.as_posix()
            except Exception:
                pass
            try:
                rel_to_repo = resolved.relative_to(repo_root)
                rel_repo = rel_to_repo.as_posix()
                if rel_repo.startswith("user_data/"):
                    parts = rel_repo.split("/")
                    if len(parts) >= 3:
                        parts[1] = tid
                        return "/".join(parts)
                return rel_repo
            except Exception:
                pass
    except Exception:
        pass

    if re.search(r"^[A-Za-z]:[\\/]", candidate_norm) or candidate_norm.startswith("/"):
        return os.path.basename(candidate_norm) or raw
    return raw


def _sanitize_paths_in_text(text: str, thread_id: Optional[str] = None) -> str:
    value = str(text or "")
    tid = str(thread_id or _get_ui_thread_id())

    def _replace_abs(m):
        return _to_ui_relative_path(m.group(0), tid)

    value = re.sub(r"[A-Za-z]:[\\/][^\s\"'`]+", _replace_abs, value)
    value = re.sub(r"/(?:home|Users|mnt|tmp)/[^\s\"'`]+", _replace_abs, value)

    def _replace_user_data(m):
        return _to_ui_relative_path(m.group(1), tid)

    value = re.sub(
        r"(?i)(user_data[\\/][^\\/]+[\\/](?:inputs|outputs)[\\/][^\s\"'`]+)",
        _replace_user_data,
        value,
    )
    return value


def _sanitize_paths_in_obj(obj, thread_id: Optional[str] = None, parent_key: str = ""):
    tid = str(thread_id or _get_ui_thread_id())
    key = str(parent_key or "").lower()
    path_key_hit = any(token in key for token in ("path", "dir", "location", "workspace", "output", "file"))

    if isinstance(obj, dict):
        return {k: _sanitize_paths_in_obj(v, tid, str(k)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_paths_in_obj(v, tid, parent_key) for v in obj]
    if isinstance(obj, str):
        if path_key_hit:
            return _to_ui_relative_path(obj, tid)
        return _sanitize_paths_in_text(obj, tid)
    return obj


def _truncate_text(value: str, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "..."


def _agent_node_id(agent_name: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", str(agent_name or "ai").strip().lower()).strip("_")
    return f"ai_{key or 'default'}"


def _infer_transfer_target_agent(tool_name: str):
    name = str(tool_name or "").strip().lower()
    if not name:
        return None
    if "transfer_to_code_assistant" in name or "transfer_to_code" in name:
        return "Code_Assistant"
    if (
        "transfer_back_to_ntl_engineer" in name
        or "transfer_to_ntl_engineer" in name
        or "transfer_back_to_engineer" in name
    ):
        return "NTL_Engineer"
    m = re.search(r"transfer_to_([a-z0-9_]+)", name)
    if m:
        suffix = m.group(1)
        return "_".join(part.capitalize() for part in suffix.split("_"))
    return None


def _kb_phase_specs() -> list[tuple[str, str, str]]:
    return [
        ("query_received", _tr("接收查询", "Query Received"), _tr("已进入检索流程", "Entered retrieval flow")),
        (
            "knowledge_retrieval",
            _tr("知识检索", "Knowledge Retrieval"),
            _tr("正在检索知识库候选内容", "Retrieving candidate context from KB"),
        ),
        (
            "workflow_assembly",
            _tr("工作流组装", "Workflow Assembly"),
            _tr("正在组装工作流步骤", "Assembling workflow steps"),
        ),
        (
            "structured_output",
            _tr("结构化输出", "Structured Output"),
            _tr("正在准备可渲染 JSON", "Preparing renderable JSON contract"),
        ),
    ]


def _build_kb_progress_nodes_from_records(records: list[dict]) -> list[dict]:
    if not records:
        return []
    latest_by_phase = {}
    for item in records:
        phase = str(item.get("phase", "")).strip()
        if phase:
            latest_by_phase[phase] = item

    nodes = []
    for phase_key, label, default_detail in _kb_phase_specs():
        record = latest_by_phase.get(phase_key)
        status = str((record or {}).get("status", "")).strip().lower()
        done = status == "done"
        running = status == "running"
        error = status == "error"
        meta = (record or {}).get("meta")
        error_summary = ""
        if isinstance(meta, dict):
            error_summary = str(meta.get("error_summary", "")).strip()
        detail = str((record or {}).get("label", "")).strip() or default_detail
        if error and error_summary:
            detail = f"{detail} | {error_summary}"
        nodes.append(
            {
                "key": phase_key,
                "label": label,
                "done": done,
                "running": running,
                "error": error,
                "detail": detail,
            }
        )
    return nodes


def _render_kb_progress_nodes(nodes: list[dict], caption_text: str):
    if not nodes:
        return
    done = sum(1 for n in nodes if n.get("done"))
    total = len(nodes)
    st.caption(caption_text)
    st.progress(done / total if total else 0.0)
    cols = st.columns(total)
    for idx, node in enumerate(nodes):
        icon = "⌛"
        if node.get("error"):
            icon = "❌"
        elif node.get("done"):
            icon = "✅"
        elif node.get("running"):
            icon = "⏳"
        with cols[idx]:
            st.markdown(f"**{icon} {node.get('label', '')}**")
            if node.get("error"):
                st.caption(node.get("detail", ""))


def _build_reasoning_graph_payload(events, show_sub_steps: bool = False):
    grouped = _build_reasoning_sections(events)
    if not grouped:
        return None
    has_final_kb_tool = any(
        step.get("kind") == "tool"
        and any(
            isinstance(msg, ToolMessage)
            and "ntl_knowledge_base" in str(getattr(msg, "name", "")).strip().lower()
            for msg in (step.get("messages") or [])
        )
        for step in grouped
    )

    nodes = [
        {"data": {"id": "start", "label": "START", "kind": "system"}, "classes": "system"},
    ]
    edges = []
    seen_nodes = {"start"}
    last_anchor = "start"
    last_ai = None
    human_idx = 0
    tool_idx = 0

    def add_node(node_id: str, label: str, kind: str = "default"):
        if node_id in seen_nodes:
            return
        nodes.append(
            {
                "data": {"id": node_id, "label": _truncate_text(label, 140), "kind": kind},
                "classes": kind,
            }
        )
        seen_nodes.add(node_id)

    def add_edge(src: str, dst: str, cls: str = "flow"):
        edges.append(
            {
                "data": {"id": f"e_{len(edges) + 1}", "source": src, "target": dst},
                "classes": cls,
            }
        )

    for step in grouped:
        kind = step.get("kind")
        if kind == "human":
            human_idx += 1
            node_id = f"h{human_idx}"
            add_node(node_id, "Human Query", "human")
            add_edge(last_anchor, node_id, "flow")
            last_anchor = node_id
            last_ai = None
            continue

        if kind == "ai":
            agent = str(step.get("agent") or "AI")
            node_id = _agent_node_id(agent)
            add_node(node_id, f"AI: {agent}", "ai")
            if last_anchor.startswith("ai_") and node_id.startswith("ai_") and last_anchor != node_id:
                add_edge(last_anchor, node_id, "handoff_edge")
            elif last_anchor != node_id:
                add_edge(last_anchor, node_id, "flow")
            last_anchor = node_id
            last_ai = node_id
            continue

        if kind == "kb_progress":
            if has_final_kb_tool:
                continue
            node_id = f"kbp_{len([n for n in nodes if str((n.get('data') or {}).get('id', '')).startswith('kbp_')]) + 1}"
            add_node(node_id, "KB Progress", "tool_kb")
            add_edge(last_ai or last_anchor, node_id, "tool_call_edge")
            add_edge(node_id, last_ai or last_anchor, "return_edge")
            last_anchor = last_ai or last_anchor
            continue

        if kind == "tool":
            tool_messages = [m for m in step.get("messages", []) if isinstance(m, ToolMessage)]
            if not tool_messages:
                continue

            tool_name = str(getattr(tool_messages[0], "name", "") or "tool")
            call_count = len(tool_messages)
            start_seq = tool_idx + 1
            end_seq = start_seq + call_count - 1
            tool_idx = end_seq

            transfer_target = _infer_transfer_target_agent(tool_name)
            if transfer_target and tool_name.lower().startswith("transfer"):
                target_node = _agent_node_id(transfer_target)
                add_node(target_node, f"AI: {transfer_target}", "ai")
                add_edge(last_ai or last_anchor, target_node, "handoff_edge")
                last_anchor = target_node
                last_ai = target_node
                continue

            node_id = f"tc_{start_seq}"
            if call_count > 1:
                tool_label = f"#{start_seq}-{end_seq} {tool_name}*{call_count}"
            else:
                tool_label = f"#{start_seq} {tool_name}"
            add_node(
                node_id,
                _truncate_text(tool_label, 120),
                "tool_kb" if tool_name.strip().lower() == "ntl_knowledge_base" else "tool",
            )
            add_edge(last_ai or last_anchor, node_id, "tool_call_edge")
            add_edge(node_id, last_ai or last_anchor, "return_edge")
            last_anchor = last_ai or last_anchor

    add_node("end", "END", "system")
    add_edge(last_anchor, "end", "flow")
    return {"nodes": nodes, "edges": edges, "main_edge_ids": []}


def _escape_dot_label(text: str) -> str:
    value = str(text or "")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_reasoning_dot(payload: dict) -> str:
    nodes = payload.get("nodes") or []
    edges = payload.get("edges") or []
    lines = [
        "digraph ReasoningMap {",
        "rankdir=LR;",
        'graph [bgcolor="#ffffff", splines=true, overlap=false];',
        'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10];',
        'edge [color="#475569"];',
    ]
    for node in nodes:
        data = node.get("data", {})
        node_id = str(data.get("id", "n")).replace("-", "_")
        label = _escape_dot_label(data.get("label") or node_id)
        kind = str(data.get("kind", "default"))
        fill = "#f1f5f9"
        if kind == "human":
            fill = "#dbeafe"
        elif kind == "ai":
            fill = "#dcfce7"
        elif kind == "tool":
            fill = "#fef3c7"
        elif kind == "tool_kb":
            fill = "#ccfbf1"
        elif kind == "system":
            fill = "#e2e8f0"
        lines.append(f'{node_id} [label="{label}", fillcolor="{fill}"];')
    for edge in edges:
        data = edge.get("data", {})
        src = str(data.get("source", "")).replace("-", "_")
        dst = str(data.get("target", "")).replace("-", "_")
        cls = str(edge.get("classes", "flow"))
        attrs = []
        if cls == "handoff_edge":
            attrs.extend(['color="#2563eb"', 'penwidth=2.0'])
        elif cls == "return_edge":
            attrs.extend(['style="dashed"', 'color="#0ea5e9"'])
        style = f" [{', '.join(attrs)}]" if attrs else ""
        if src and dst:
            lines.append(f"{src} -> {dst}{style};")
    lines.append("}")
    return "\n".join(lines)


def _json_for_html_script(data) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def render_reasoning_map(events, interactive: bool = True, show_sub_steps: bool = False):
    payload = _build_reasoning_graph_payload(events, show_sub_steps=show_sub_steps)
    if not payload:
        st.caption(_tr("暂无可视化推理路径。", "No reasoning graph yet."))
        return

    if not interactive:
        dot = _build_reasoning_dot(payload)
        if dot:
            st.graphviz_chart(dot, use_container_width=True)
        return

    elements = payload["nodes"] + payload["edges"]
    container_id = f"reasoning-map-{uuid.uuid4().hex[:8]}"
    graph_height = min(700, max(360, 260 + len(payload["nodes"]) * 20))
    js_elements = _json_for_html_script(elements)
    html = f"""
    <div id="{container_id}" style="width:100%;height:{graph_height}px;border:1px solid #d1d5db;border-radius:12px;background:#ffffff;"></div>
    <script src="https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js"></script>
    <script>
    (function() {{
      const root = document.getElementById("{container_id}");
      const elements = {js_elements};
      if (!root) return;
      function render() {{
        if (typeof cytoscape !== "function") {{
          root.innerHTML = "<div style='padding:12px;color:#cbd5e1'>Graph library unavailable.</div>";
          return;
        }}
        if (root.__cy) root.__cy.destroy();
        const cy = cytoscape({{
          container: root,
          elements: elements,
          style: [
            {{ selector: "node", style: {{ "label": "data(label)", "font-size": 10, "color": "#111827", "text-wrap": "wrap", "text-max-width": 160, "shape": "round-rectangle", "background-color": "#f3f4f6", "border-width": 1, "border-color": "#6b7280" }} }},
            {{ selector: "node.human", style: {{ "background-color": "#dbeafe" }} }},
            {{ selector: "node.ai", style: {{ "background-color": "#dcfce7" }} }},
            {{ selector: "node.tool", style: {{ "background-color": "#fef3c7" }} }},
            {{ selector: "node.tool_kb", style: {{ "background-color": "#ccfbf1" }} }},
            {{ selector: "edge", style: {{ "curve-style": "bezier", "target-arrow-shape": "triangle", "line-color": "#6b7280", "target-arrow-color": "#6b7280", "width": 1.4 }} }},
            {{ selector: "edge.handoff_edge", style: {{ "line-color": "#1d4ed8", "target-arrow-color": "#1d4ed8", "width": 2.0 }} }},
            {{ selector: "edge.return_edge", style: {{ "line-style": "dashed", "line-color": "#0f766e", "target-arrow-color": "#0f766e" }} }}
          ],
          layout: {{ name: "breadthfirst", directed: true, padding: 20, spacingFactor: 1.15 }}
        }});
        root.__cy = cy;
        setTimeout(() => {{
          try {{ cy.fit(undefined, 24); }} catch (e) {{}}
        }}, 0);
      }}
      render();
      const ro = new ResizeObserver(() => {{ if (root.__cy) {{ root.__cy.resize(); root.__cy.fit(undefined, 24); }} }});
      ro.observe(root);
      const mo = new MutationObserver(() => {{ if (root.__cy) {{ root.__cy.resize(); }} }});
      mo.observe(document.body, {{ childList: true, subtree: true }});
      document.addEventListener("visibilitychange", () => {{ if (document.visibilityState === "visible" && root.__cy) {{ root.__cy.resize(); root.__cy.fit(undefined, 24); }} }});
    }})();
    </script>
    """
    components.html(html, height=graph_height + 8, scrolling=False)


def render_reasoning_content(events):
    """Render one-round reasoning in a single panel (no Step 1/2/3)."""
    grouped = _build_reasoning_sections(events)
    if not grouped:
        st.caption(_tr("等待推理事件...", "Waiting for reasoning events..."))
        return
    has_final_kb_tool = any(
        step.get("kind") == "tool"
        and any(
            isinstance(msg, ToolMessage) and "NTL_Knowledge_Base" in str(getattr(msg, "name", ""))
            for msg in (step.get("messages") or [])
        )
        for step in grouped
    )

    for step in grouped:
        if step["kind"] == "human":
            for msg in step["messages"]:
                render_event_human(msg.content)
                st.markdown("<hr style='margin: 10px 0; border: 1px dashed #64748b;'>", unsafe_allow_html=True)
        elif step["kind"] == "ai":
            agent_name = step["agent"]
            render_label_ai(agent_name)
            effective_messages = []
            for msg in step["messages"]:
                msg_content = _normalize_content_to_text(_strip_legacy_stream_marker(msg.content))
                if not isinstance(msg_content, str):
                    msg_content = str(msg_content)
                if not msg_content.strip():
                    continue
                effective_messages.append(msg_content)

            if not effective_messages:
                st.markdown("<hr style='margin: 10px 0; border: 1px dashed #64748b;'>", unsafe_allow_html=True)
                continue

            for msg_content in effective_messages:
                if agent_name.lower() == "data_searcher":
                    render_data_searcher_output(msg_content)
                elif agent_name.lower() == "code_assistant":
                    st.code(msg_content, language="python")
                else:
                    st.markdown(
                        f"<div style='margin-left:15px;font-size:16px;'>{msg_content}</div>",
                        unsafe_allow_html=True,
                    )
            st.markdown("<hr style='margin: 10px 0; border: 1px dashed #64748b;'>", unsafe_allow_html=True)
        elif step["kind"] == "tool":
            tool_messages = _dedupe_tool_messages([m for m in step["messages"] if isinstance(m, ToolMessage)])
            for msg in tool_messages:
                exp_title = _tr(f"工具输出: {msg.name}", f"Tool Output: {msg.name}")
                with st.expander(exp_title, expanded=False):
                    if msg.name and "NTL_Knowledge_Base" in msg.name:
                        render_kb_output(msg.content)
                    elif str(msg.name or "").strip().lower() in {
                        "uploaded_pdf_understanding_tool",
                        "uploaded_image_understanding_tool",
                        "uploaded_file_understanding_tool",
                    }:
                        render_uploaded_understanding_output(msg.content, tool_name=str(msg.name or ""))
                    else:
                        try:
                            st.json(_sanitize_paths_in_obj(json.loads(msg.content)))
                        except Exception:
                            st.write(_sanitize_paths_in_text(str(msg.content)))
            st.markdown("<hr style='margin: 10px 0; border: 1px dashed #64748b;'>", unsafe_allow_html=True)
        elif step["kind"] == "kb_progress":
            if has_final_kb_tool:
                continue
            records = [x for x in step.get("records", []) if isinstance(x, dict)]
            if not records:
                continue
            nodes = _build_kb_progress_nodes_from_records(records)
            if not nodes:
                continue
            exp_title = _tr("工具输出: NTL_Knowledge_Base", "Tool Output: NTL_Knowledge_Base")
            with st.expander(exp_title, expanded=False):
                _render_kb_progress_nodes(
                    nodes,
                    _tr("NTL_Knowledge_Base_Searcher 节点进度（流式）", "NTL_Knowledge_Base_Searcher Node Progress (Streaming)"),
                )
            st.markdown("<hr style='margin: 10px 0; border: 1px dashed #64748b;'>", unsafe_allow_html=True)
        elif step["kind"] == "custom_notice":
            for record in (step.get("records") or []):
                if not isinstance(record, dict):
                    continue
                et = str(record.get("event_type", "")).strip()
                if et not in {"auto_image_understanding_triggered", "auto_pdf_understanding_triggered"}:
                    continue
                files = record.get("files") or []
                if isinstance(files, str):
                    files = [files]
                files = [str(x).strip() for x in files if str(x).strip()]
                reason = str(record.get("trigger_reason", "")).strip()
                suffix = f" ({reason})" if reason else ""
                if et == "auto_pdf_understanding_triggered":
                    msg = _tr(
                        f"已自动触发 PDF 理解: {', '.join(files) if files else 'pdf'}{suffix}",
                        f"Auto PDF understanding triggered: {', '.join(files) if files else 'pdf'}{suffix}",
                    )
                else:
                    msg = _tr(
                        f"已自动触发图片理解: {', '.join(files) if files else 'image'}{suffix}",
                        f"Auto image understanding triggered: {', '.join(files) if files else 'image'}{suffix}",
                    )
                st.info(msg)
            st.markdown("<hr style='margin: 10px 0; border: 1px dashed #64748b;'>", unsafe_allow_html=True)


def _classify_code_assistant_stage(tool_name, tool_payload):
    name = str(tool_name or "").strip().lower()
    if not name:
        return None

    def _status_from_payload(payload):
        if isinstance(payload, dict):
            return str(payload.get("status", "")).strip().lower()
        if isinstance(payload, str):
            try:
                obj = json.loads(payload)
                if isinstance(obj, dict):
                    return str(obj.get("status", "")).strip().lower()
            except Exception:
                return ""
        return ""

    status = _status_from_payload(tool_payload)
    if name == "save_geospatial_script_tool":
        return "Draft Received"
    if name in {"geocode_cot_validation_tool", "execute_geospatial_script_tool", "final_geospatial_code_execution_tool"}:
        if status == "success":
            return "Success"
        if status in {"needs_engineer_decision", "fail"}:
            return "Escalate"
        return "Validate/Execute"
    if name in {"transfer_back_to_ntl_engineer", "transfer_to_ntl_engineer"}:
        return "Escalate"
    return None


def _collect_workspace_output_mismatch_records() -> list[dict]:
    records: list[dict] = []
    current_thread = str(st.session_state.get("thread_id", "debug"))

    def _scan_events(events):
        if not isinstance(events, list):
            return
        for event in events:
            if not isinstance(event, dict):
                continue
            for msg in (event.get("messages") or []):
                if not isinstance(msg, ToolMessage):
                    continue
                name = str(getattr(msg, "name", "") or "")
                if "execute_geospatial_script_tool" not in name:
                    continue
                payload, _ = _extract_json(getattr(msg, "content", ""))
                if not isinstance(payload, dict):
                    continue
                audit = payload.get("artifact_audit")
                if not isinstance(audit, dict):
                    continue
                recovered = bool(payload.get("cross_workspace_recovered", False))
                if bool(audit.get("pass", True)) and not recovered:
                    continue
                records.append(
                    {
                        "thread_id": str(audit.get("thread_id") or current_thread),
                        "workspace_outputs_dir": str(audit.get("workspace_outputs_dir") or ""),
                        "out_of_workspace_paths": list(audit.get("out_of_workspace_paths") or []),
                        "cross_workspace_recovered": recovered,
                        "auto_migrated_files": list(payload.get("auto_migrated_files") or []),
                        "recovery_note": str(payload.get("recovery_note") or ""),
                    }
                )

    _scan_events(st.session_state.get("analysis_logs", []))
    history = st.session_state.get("analysis_history", [])
    if isinstance(history, list):
        for item in history[-3:]:
            if isinstance(item, dict):
                _scan_events(item.get("logs", []))
    return records


def _render_output_workspace_mismatch_notice():
    mismatches = _collect_workspace_output_mismatch_records()
    if not mismatches:
        return
    latest = mismatches[-1]
    workspace = _to_ui_relative_path(str(latest.get("workspace_outputs_dir") or ""))
    out_paths = [_to_ui_relative_path(str(x)) for x in (latest.get("out_of_workspace_paths") or []) if str(x).strip()]
    recovered = bool(latest.get("cross_workspace_recovered", False))
    migrated_paths = [
        _to_ui_relative_path(str(x))
        for x in (latest.get("auto_migrated_files") or [])
        if str(x).strip()
    ]

    if recovered:
        st.info(
            _tr(
                "检测到跨线程输出并已自动恢复到当前会话 outputs。",
                "Cross-thread outputs detected and auto-recovered to current session outputs.",
            )
        )
    else:
        st.warning(
            _tr(
                "检测到跨线程输出：部分结果未写入当前会话 outputs，可能导致本页看不到文件。",
                "Cross-thread outputs detected: some files were written outside current session outputs.",
            )
        )

    if workspace:
        st.caption(_tr(f"当前线程 outputs: {workspace}", f"Current thread outputs: {workspace}"))
    if recovered and migrated_paths:
        st.caption(_tr("已恢复文件：", "Recovered files:"))
        for p in migrated_paths:
            st.code(p, language="text")
        note = str(latest.get("recovery_note") or "").strip()
        if note:
            st.caption(_sanitize_paths_in_text(note))
        return

    if out_paths:
        st.caption(_tr("实际落盘路径：", "Actual output paths:"))
        for p in out_paths:
            st.code(p, language="text")
        dst = workspace or f"user_data/{st.session_state.get('thread_id', 'debug')}/outputs"
        copy_cmd = "\n".join(
            [f"Copy-Item \"{p}\" \"{dst}\" -Force" for p in out_paths]
        )
        st.caption(_tr("建议修复命令（可复制）：", "Suggested recovery commands (copy):"))
        st.code(copy_cmd, language="powershell")


def _render_output_preview():
    workspace = storage_manager.get_workspace(st.session_state.get("thread_id", "debug"))
    _render_output_workspace_mismatch_notice()
    output_dir = workspace / "outputs"
    files = [f for f in output_dir.glob("*.*") if f.is_file()] if output_dir.exists() else []
    if not files:
        st.info(_tr("暂无输出文件。", "No output files available."))
        return

    selected = st.selectbox(_tr("预览输出文件", "Preview Output"), options=files, format_func=lambda p: p.name)
    suffix = selected.suffix.lower()
    if suffix == ".csv":
        try:
            df = pd.read_csv(selected)
            st.dataframe(df, use_container_width=True, height=360)
        except Exception as e:
            st.error(_tr(f"预览失败 {selected.name}: {e}", f"Failed to preview {selected.name}: {e}"))
    elif suffix in [".png", ".jpg", ".jpeg"]:
        st.image(str(selected), use_container_width=True)
    elif suffix in [".tif", ".tiff"]:
        with rasterio.open(selected) as src:
            st.caption(f"CRS: {src.crs} | Size: {src.width} x {src.height} | Bands: {src.count}")
    elif suffix == ".py":
        try:
            code_text = selected.read_text(encoding="utf-8")
            st.code(code_text, language="python")
        except Exception:
            try:
                code_text = selected.read_text(encoding="gbk")
                st.code(code_text, language="python")
            except Exception as e:
                st.error(_tr(f"预览失败 {selected.name}: {e}", f"Failed to preview {selected.name}: {e}"))
    elif suffix in [".jsonl", ".ndjson"]:
        rows = []
        bad_lines = 0
        preview_limit = 500
        try:
            with selected.open("r", encoding="utf-8") as f:
                for i, line in enumerate(f, start=1):
                    if i > preview_limit:
                        break
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        obj = json.loads(text)
                        if isinstance(obj, dict):
                            rows.append(obj)
                        else:
                            rows.append({"_value": obj})
                    except Exception:
                        bad_lines += 1
                        rows.append({"_line": i, "_raw": text})
            st.caption(
                _tr(
                    f"JSONL 预览：最多显示前 {preview_limit} 行；解析失败 {bad_lines} 行。",
                    f"JSONL preview: first {preview_limit} lines max; parse failures: {bad_lines}.",
                )
            )
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, height=360)
            else:
                st.info(_tr("JSONL 文件为空。", "JSONL file is empty."))
        except Exception as e:
            st.error(_tr(f"预览失败 {selected.name}: {e}", f"Failed to preview {selected.name}: {e}"))
    else:
        st.caption(_tr("该文件类型暂不支持预览，请在 Data Center 下载。", "Preview is not available for this file type. Use Data Center to download."))


def render_content_layout():
    """Render dual-column layout: chat and analysis/map/results."""
    workspace = storage_manager.get_workspace(st.session_state.get("thread_id", "debug"))
    # st.markdown(
    #     f"<div class='ntl-card'>"
    #     f"<b>{_tr('工作空间', 'Workspace')}</b><br><span style='color:#61717a;font-size:0.88rem;'>{workspace}</span></div>",
    #     unsafe_allow_html=True,
    # )

    col_chat, col_analysis = st.columns([0.58, 0.42], gap="medium")

    with col_chat:
        chat_container = st.container(height=getattr(app_state, "CHAT_CONTAINER_HEIGHT", 640))
        with chat_container:
            show_history(st.session_state.chat_history)
        chat_input_value = get_user_input()
        user_question, chat_files = _extract_chat_input_text_and_files(chat_input_value)
        if chat_files:
            thread_id = str(st.session_state.get("thread_id", "debug"))
            save_result = _save_chat_input_files_to_workspace(chat_files, thread_id)
            saved = save_result.get("saved", []) or []
            errors = save_result.get("errors", []) or []
            if saved:
                st.success(
                    _tr(
                        f"已从输入框上传到 inputs/: {', '.join(saved)}",
                        f"Uploaded from chat input to inputs/: {', '.join(saved)}",
                    )
                )
            for err in errors:
                st.warning(_sanitize_paths_in_text(str(err)))
            if saved and not user_question:
                st.session_state.chat_history.append(
                    (
                        "assistant",
                        _tr(
                            f"已接收并保存文件到 `inputs/`：{', '.join(saved)}。请继续提问需要我如何理解或分析这些文件。",
                            f"Files saved to `inputs/`: {', '.join(saved)}. Ask what you want me to analyze from them.",
                        ),
                    )
                )
                st.rerun()
        pending_question = st.session_state.pop("pending_question", None) if "pending_question" in st.session_state else None
        if pending_question and not user_question:
            user_question = pending_question
            st.info(_tr(f"已载入测试用例: {pending_question[:120]}", f"Loaded test case: {pending_question[:120]}"))
        runtime_notice = st.session_state.pop("runtime_recovered_notice", None)
        if runtime_notice:
            st.info(_tr("检测到上轮任务状态残留，已自动恢复，可继续提问。", runtime_notice))

    with col_analysis:
        analysis_panel = st.container(height=getattr(app_state, "ANALYSIS_CONTAINER_HEIGHT", 640))
        with analysis_panel:
            tab_reasoning, tab_reasoning_graph, tab_map, tab_outputs = st.tabs([
                _tr("推理过程", "Reasoning"),
                _tr("推理图谱", "Reasoning Graph"),
                _tr("地图视图", "Map View"),
                _tr("结果预览", "Outputs"),
            ])

            reasoning_placeholder = None
            reasoning_graph_placeholder = None
            reasoning_graph_show_sub_steps = False
            with tab_reasoning:
                try:
                    reasoning_placeholder = st.empty()
                    history = st.session_state.get("analysis_history", [])
                    if history and not user_question:
                        for item in reversed(history):
                            q = str(item.get("question", "")).strip()
                            title_q = (q[:56] + "...") if len(q) > 56 else q
                            title = _tr(
                                f"历史推理: {title_q or '上一轮'}",
                                f"Previous Reasoning: {title_q or 'Previous round'}",
                            )
                            with st.expander(title, expanded=False):
                                render_reasoning_content(item.get("logs", []))
                    if st.session_state.analysis_logs and not user_question:
                        with reasoning_placeholder.container():
                            with st.expander(_tr("本轮推理过程", "Reasoning Flow"), expanded=True):
                                render_reasoning_content(st.session_state.analysis_logs)
                except Exception as e:
                    st.error(_tr(f"推理面板渲染异常: {e}", f"Reasoning panel render error: {e}"))

            with tab_reasoning_graph:
                try:
                    reasoning_graph_placeholder = st.empty()
                    history = st.session_state.get("analysis_history", [])
                    if history and not user_question:
                        for item in reversed(history):
                            q = str(item.get("question", "")).strip()
                            title_q = (q[:56] + "...") if len(q) > 56 else q
                            title = _tr(
                                f"历史图谱: {title_q or '上一轮'}",
                                f"Previous Graph: {title_q or 'Previous round'}",
                            )
                            with st.expander(title, expanded=False):
                                render_reasoning_map(
                                    item.get("logs", []),
                                    interactive=False,
                                    show_sub_steps=reasoning_graph_show_sub_steps,
                                )
                    if st.session_state.analysis_logs and not user_question:
                        with reasoning_graph_placeholder.container():
                            with st.expander(_tr("本轮推理图谱", "Reasoning Graph"), expanded=True):
                                render_reasoning_map(
                                    st.session_state.analysis_logs,
                                    interactive=False,
                                    show_sub_steps=reasoning_graph_show_sub_steps,
                                )
                except Exception as e:
                    st.error(_tr(f"图谱面板渲染异常: {e}", f"Graph panel render error: {e}"))

            with tab_map:
                try:
                    render_map_view()
                except Exception as e:
                    st.error(_tr(f"地图面板渲染异常: {e}", f"Map panel render error: {e}"))

            with tab_outputs:
                try:
                    _render_output_preview()
                except Exception as e:
                    st.error(_tr(f"输出面板渲染异常: {e}", f"Outputs panel render error: {e}"))

        if user_question:
            if not st.session_state.chat_history or st.session_state.chat_history[-1] != ("user", user_question):
                st.session_state.chat_history.append(("user", user_question))
            if not st.session_state.get("conversation"):
                app_logic.ensure_conversation_initialized()
            if not st.session_state.get("conversation"):
                st.session_state.chat_history.append(
                    (
                        "assistant",
                        _tr(
                            "会话初始化失败，请先在侧边栏重新激活后再提问。",
                            "Conversation initialization failed. Please reactivate in sidebar and retry.",
                        ),
                    )
                )
                st.rerun()
                return
            if reasoning_placeholder is None:
                reasoning_placeholder = st.empty()
            app_logic.handle_userinput(
                user_question,
                reasoning_placeholder,
                chat_container,
                reasoning_graph_placeholder=reasoning_graph_placeholder,
                reasoning_graph_show_sub_steps=reasoning_graph_show_sub_steps,
            )
