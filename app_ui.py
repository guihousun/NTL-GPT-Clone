import os
import re
import json
import zipfile
import base64
from pathlib import Path

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
from storage_manager import storage_manager


def _is_en() -> bool:
    return st.session_state.get("ui_lang", "EN") == "EN"


def _tr(zh: str, en: str) -> str:
    return en if _is_en() else zh


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
            var input = doc.querySelector('div[data-testid="stChatInput"]');
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

def get_user_input():
    return st.chat_input(_tr("请输入任务，例如：统计上海 2020 年 TNTL 并导出 CSV", "Describe your task, e.g., compute Shanghai 2020 TNTL and export CSV"))

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
        if srcs:
            st.markdown("### Reliable Sources")
            for i, s in enumerate(srcs, 1):
                with st.container(border=True):
                    st.markdown(f"**{i}. {s.get('Publisher','-')}** 路  {s.get('Domain','')}")
                    st.markdown(f"- **Title**: {s.get('Title','-')}")
                    if s.get("URL"): st.markdown(f"- **URL**: [{s['URL']}]({s['URL']})")
                    if s.get("Snippet"): st.caption(s["Snippet"])

        with _render_popover("View Raw JSON"): st.json(data)
        if isinstance(rest, str) and rest.strip(): st.write(rest)
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
                    st.caption(str(item.get("Notes")))

    with _render_popover("View Raw JSON"): st.json(data)
    if isinstance(rest, str) and rest.strip(): st.write(rest)


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
        st.warning(f"Knowledge base ({status}): {reason}")
        if normalized.get("sources"):
            with _render_popover("Sources"): st.json(normalized["sources"])
        with _render_popover("Raw JSON"): st.json(data)
        if isinstance(rest, str) and rest.strip(): st.write(rest)
        return

    if (
        not normalized.get("steps")
        and not normalized.get("description")
        and not normalized.get("output")
        and (normalized.get("reason") or normalized.get("message"))
    ):
        st.warning(f"Knowledge base: {normalized.get('reason') or normalized.get('message')}")
        if normalized.get("sources"):
            with _render_popover("Sources"): st.json(normalized["sources"])
        with _render_popover("Raw JSON"): st.json(data)
        if isinstance(rest, str) and rest.strip(): st.write(rest)
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
                with _render_popover(main_info or "Step Details"): st.json(step["input"])
            elif main_info:
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;<span style='color:gray; font-size:0.95em;'>{main_info}</span>", unsafe_allow_html=True)

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
                st.markdown(f"*Sources for this step: {sources_str}*")

    if normalized.get("output"):
        st.markdown("**Output**")
        st.write(normalized["output"])
    elif not steps and not normalized.get("description"):
        st.info("Knowledge base returned structured data without workflow steps.")
        summary = {}
        for key in ("task_name", "task_id", "category", "store", "message", "reason", "query"):
            if normalized.get(key):
                summary[key] = normalized.get(key)
        if summary:
            st.json(summary)

    with _render_popover("Raw JSON"): st.json(data)
    
    if normalized.get("supplementary_text"):
        st.markdown("---")
        with st.expander("Supplementary Knowledge & Code (Mixed Mode)", expanded=False):
            st.markdown(str(normalized.get("supplementary_text")))

    if isinstance(rest, str) and rest.strip(): 
        # 浼樺寲 rest 鐨勬樉绀猴細鏀惧叆 Expander 骞堕檷浣?Markdown 鏍囬绾у埆
        import re
        # 灏嗚棣栫殑涓€绾ф爣棰?(# ) 鍜屼簩绾ф爣棰?(## ) 缁熶竴闄嶇骇涓哄洓绾ф爣棰?(#### )
        # 閬垮厤鍦?UI 涓覆鏌撳嚭宸ㄥぇ鐨勬爣棰橈紝淇濇寔灞傜骇鍜岃皭
        formatted_rest = re.sub(r'^(#+)\s', r'#### ', rest, flags=re.MULTILINE)
        
        st.markdown("---")
        with st.expander("Supplementary Knowledge & Code (Mixed Mode)", expanded=False):
            st.markdown(formatted_rest)

# ==============================================================================
# SECTION E: 渚ц竟鏍忕粍浠?(Sidebar, Download, Upload)
# ==============================================================================

def render_sidebar():
    """Render all sidebar controls."""
    with st.sidebar:
        st.subheader(_tr("NTL-GPT 控制台", "NTL-GPT Console"))

        workspace = storage_manager.get_workspace()
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
            if st.button(_tr("激活", "Activate"), key="activate_btn", use_container_width=True, type="secondary"):
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
            if st.button(_tr("重置", "Reset"), key="reset_btn", use_container_width=True, type="secondary"):
                st.cache_resource.clear()
                st.session_state["initialized"] = False
                st.session_state.chat_history = []
                st.session_state.analysis_logs = []
                st.session_state.analysis_history = []
                st.session_state.last_question = ""
                st.session_state["cancel_requested"] = False

                if "user_api_key" in st.session_state:
                    del st.session_state["user_api_key"]
                
                import uuid
                st.session_state.thread_id = str(uuid.uuid4())[:8]
                st.warning(_tr("系统已重置。", "System reset."))
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
                else:
                    st.info(_tr("当前没有正在运行的任务。", "No task is currently running."))

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

        with st.expander(_tr("GEE 数据可用性", "Data Availability In GEE"), expanded=False):
            st.caption(_tr("**年度夜光：**", "**Annual NTL:**"))
            st.caption("- NPP-VIIRS-Like (2000-2024)")
            st.caption("- NPP-VIIRS (2012-2023)")
            st.caption("- DMSP-OLS (1992-2013)")
            st.caption(_tr("**月度**: 2014-01 至 2025-03", "**Monthly**: 2014-01 to 2025-03"))
            st.caption(_tr("**日度** (VNP46A2): 2012-01-19 至今（约 4 天延迟）", "**Daily** (VNP46A2): 2012-01-19 to present (4-day latency)"))
            st.caption(_tr("**日度** (VNP46A1): 2012-01-19 至 2025-01-02", "**Daily** (VNP46A1): 2012-01-19 to 2025-01-02"))

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
                st.caption(_tr(f"已加载用例文件: {', '.join(loaded_names)}", f"Loaded case files: {', '.join(loaded_names)}"))

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
        workspace = storage_manager.get_workspace()
        def get_valid_files(directory, include_py=False):
            if not directory.exists(): return []
            return [f for f in directory.glob("*.*") 
                    if f.suffix.lower() not in ([ ".zip", ".tmp"] + ([] if include_py else [".py"])) and not f.name.startswith('.')]

        in_files = get_valid_files(workspace / "inputs", include_py=False)
        out_files = get_valid_files(workspace / "outputs", include_py=True)

        if not in_files and not out_files: return

        st.sidebar.markdown("---")
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
    st.sidebar.subheader(_tr("上传数据", "Upload Data"))
    
    uploaded_files = st.sidebar.file_uploader(
        _tr("上传 TIF/SHP/GeoJSON/CSV/Excel/ZIP", "Upload TIF/SHP/GeoJSON/CSV/Excel/ZIP"),
        accept_multiple_files=True,
        type=['tif', 'tiff', 'shp', 'dbf', 'prj', 'shx', 'geojson', 'csv', 'xlsx', 'xls', 'zip'],
        key="data_uploader"
    )

    if uploaded_files:
        workspace = storage_manager.get_workspace()
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
    workspace = storage_manager.get_workspace()
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
        msgs = event.get("messages", [])
        if not isinstance(msgs, list):
            continue

        for msg in msgs:
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


def render_reasoning_content(events):
    """Render one-round reasoning in a single panel (no Step 1/2/3)."""
    grouped = _build_reasoning_sections(events)
    if not grouped:
        st.caption(_tr("等待推理事件...", "Waiting for reasoning events..."))
        return

    for step in grouped:
        if step["kind"] == "human":
            for msg in step["messages"]:
                render_event_human(msg.content)
                st.markdown("<hr style='margin: 10px 0; border: 1px dashed #64748b;'>", unsafe_allow_html=True)
        elif step["kind"] == "ai":
            agent_name = step["agent"]
            render_label_ai(agent_name)
            for msg in step["messages"]:
                msg_content = _strip_legacy_stream_marker(msg.content)
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
            for msg in step["messages"]:
                stage = _classify_code_assistant_stage(msg.name, msg.content)
                if stage:
                    st.caption(f"Code_Assistant Stage: {stage}")
                exp_title = _tr(f"工具输出: {msg.name}", f"Tool Output: {msg.name}")
                with st.expander(exp_title, expanded=False):
                    if msg.name and "NTL_Knowledge_Base" in msg.name:
                        render_kb_output(msg.content)
                    else:
                        try:
                            st.json(json.loads(msg.content))
                        except Exception:
                            st.write(msg.content)
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


def _render_output_preview():
    workspace = storage_manager.get_workspace()
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
    else:
        st.caption(_tr("该文件类型暂不支持预览，请在 Data Center 下载。", "Preview is not available for this file type. Use Data Center to download."))


def render_content_layout():
    """Render dual-column layout: chat and analysis/map/results."""
    workspace = storage_manager.get_workspace()
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
        user_question = get_user_input()
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
            tab_reasoning, tab_map, tab_outputs = st.tabs([
                _tr("推理过程", "Reasoning"),
                _tr("地图视图", "Map View"),
                _tr("结果预览", "Outputs"),
            ])

            reasoning_placeholder = None
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
            app_logic.handle_userinput(user_question, reasoning_placeholder, chat_container)
