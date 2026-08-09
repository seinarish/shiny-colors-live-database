import io
import json
import csv
import html
import os
import random
import re
import datetime
import calendar
import textwrap
import shutil
import html
from datetime import datetime
from functools import lru_cache
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
from event_image_gallery import (
    render_calendar_context_images,
    render_costume_context_images,
    render_event_context_images,
    render_event_image_gallery,
    render_gacha_context_images,
)

PUBLIC_MODE = globals().get("APP_MODE", os.environ.get("SHINY_APP_MODE", "local")).casefold() == "public"

# 公開版は小さなメモリ枠で動くため、使い終えた集計結果を早めに入れ替える。
# ローカル版は編集作業の快適さを優先して従来どおり多めに保持する。
FILE_CACHE_MAX_ENTRIES = 18 if PUBLIC_MODE else 96
DERIVED_CACHE_MAX_ENTRIES = 12 if PUBLIC_MODE else 32
LYRIC_CACHE_MAX_ENTRIES = 8 if PUBLIC_MODE else 16
MEDIA_CACHE_MAX_ENTRIES = 32 if PUBLIC_MODE else 128
SONG_MEDIA_CACHE_MAX_ENTRIES = 48 if PUBLIC_MODE else 256


def _clean_public_table_text(data):
    """公開版の表だけ、データ内の区切り記号を読みやすく整える。"""
    if not isinstance(data, pd.DataFrame):
        return data
    display_data = data.copy()
    for column in display_data.columns:
        if pd.api.types.is_object_dtype(display_data[column]) or pd.api.types.is_string_dtype(display_data[column]):
            display_data[column] = display_data[column].map(
                lambda value: value.replace(";", "・").replace("；", "・") if isinstance(value, str) else value
            )
    return display_data


def _adaptive_table_column_config(data, current_config=None):
    """短い値の列だけをコンパクトにし、長文列は必要以上に広げない。"""
    table_data = getattr(data, "data", data)
    if not isinstance(table_data, pd.DataFrame):
        return current_config

    config = dict(current_config or {})
    for column in table_data.columns:
        values = table_data[column].dropna().astype(str).head(300)
        max_chars = max([len(str(column))] + [len(value) for value in values], default=len(str(column)))
        desired_width = "small" if max_chars <= 8 else "medium"

        # すでに書式指定された短い列も、余白だけが大きくならないよう細くする。
        if max_chars <= 8 or column not in config:
            config[column] = st.column_config.Column(str(column), width=desired_width)
    return config


# 元データや集計用の区切り文字は保持し、公開画面の表だけを整形する。
_original_dataframe = st.dataframe
_original_table = st.table


def _responsive_dataframe(data, *args, **kwargs):
    display_data = _clean_public_table_text(data) if PUBLIC_MODE else data
    kwargs["column_config"] = _adaptive_table_column_config(
        display_data,
        kwargs.get("column_config"),
    )
    return _original_dataframe(display_data, *args, **kwargs)


def _responsive_table(data, *args, **kwargs):
    display_data = _clean_public_table_text(data) if PUBLIC_MODE else data
    return _original_table(display_data, *args, **kwargs)


st.dataframe = _responsive_dataframe
st.table = _responsive_table

# ------------------------------------------
# 1. ページ初期設定＆シャニマス公式風（クリスタル＆虹色グラデーション）CSS
# ------------------------------------------
st.set_page_config(
    page_title="SHINY COLORS LIVE DATABASE", 
    page_icon="✨", 
    layout="wide",
    # 公開版はまずコンテンツを見せ、絞り込み設定は必要なときだけ開けるようにする。
    initial_sidebar_state="expanded" if PUBLIC_MODE else "auto"
)

if PUBLIC_MODE:
    # 公開版ではStreamlit標準の右上メニューを出さず、閲覧画面に専念させる。
    st.markdown(
        """
        <style>
        [data-testid="stToolbar"],
        [data-testid="stToolbarActions"],
        [data-testid="stHeaderActionElements"],
        [data-testid="stAppDeployButton"] {
            display: none !important;
        }
        /* 公開版のサイドバーは、迷わない閲覧用の案内だけを表示する。 */
        [data-testid="stSidebar"] [data-testid="stCheckbox"],
        [data-testid="stSidebar"] [data-testid="stButton"],
        [data-testid="stSidebar"] [data-baseweb="select"],
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] hr,
        [data-testid="stSidebar"] .stCaption {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

# 公式Shiny Colors風のビジュアル ＆ 全域テキスト自動折り返し＆明るいテーマ固定CSS
st.markdown(
    """
    <style>
    /* Google Fonts 読み込み */
    @import url('https://fonts.googleapis.com/css2?family=M+PLUS+Rounded+1c:wght@400;500;700;800;900&family=Rajdhani:wght@600;700;800&display=swap');

    /* 全体フォント・背景設定（白基調＋虹色/ホログラフィック/クリスタル風） */
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'M PLUS Rounded 1c', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background: linear-gradient(135deg, #ffffff 0%, #f4f0ff 35%, #e8f7ff 70%, #fff0f5 100%) !important;
        background-attachment: fixed !important;
        color: #2c2c54 !important;
    }

    /* クリスタル/キラキラのアクセント背景 */
    [data-testid="stAppViewContainer"]::before {
        content: "";
        position: fixed;
        top: 0; left: 0; width: 100%; height: 100%;
        background-image: 
            radial-gradient(circle at 15% 15%, rgba(123, 92, 255, 0.08) 0%, transparent 35%),
            radial-gradient(circle at 85% 25%, rgba(81, 194, 240, 0.08) 0%, transparent 35%),
            radial-gradient(circle at 50% 85%, rgba(255, 133, 161, 0.08) 0%, transparent 45%);
        pointer-events: none;
        z-index: 0;
    }

    /* 基本要素の文字色保護 */
    p, span, div, label, .stMarkdown, .stSelectbox label, .stRadio label {
        color: #2c2c54 !important;
    }

    /* 余白調整 */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }

    /* ----------------------------------
       テキスト省略（…）の完全防止・自動改行
    ---------------------------------- */
    .dataframe td, .dataframe th, .stDataFrame td, .stDataFrame th,
    [data-testid="stDataFrame"] div, [data-testid="stMetricValue"],
    [data-testid="stMetricLabel"], [data-testid="stMetricCaption"],
    div[data-baseweb="tag"] span, div.stButton > button,
    div[data-testid="stMarkdownContainer"] p {
        white-space: normal !important;
        word-break: break-word !important;
        overflow-wrap: break-word !important;
        text-overflow: clip !important;
        line-height: 1.4 !important;
    }

    /* ----------------------------------
       データフレーム（テーブル）・ドロップダウンの明るい背景統一
    ---------------------------------- */
    [data-testid="stDataFrame"] {
        background-color: #ffffff !important;
        border: 1px solid rgba(123, 92, 255, 0.2) !important;
        border-radius: 16px !important;
        box-shadow: 0 6px 20px rgba(90, 69, 214, 0.05) !important;
    }

    /* ----------------------------------
       ドロップダウン（BaseWeb Popover/Menu）修正版
    ---------------------------------- */
    div[data-baseweb="popover"], 
    div[data-baseweb="menu"],
    ul[role="listbox"] {
        background-color: #ffffff !important;
        border-radius: 12px !important;
        box-shadow: 0 8px 24px rgba(90, 69, 214, 0.15) !important;
    }

    /* 選択肢（Option）のスタイル定義 */
    div[data-baseweb="popover"] li,
    div[data-baseweb="menu"] li,
    div[role="option"] {
        background-color: #ffffff !important;
        color: #2c2c54 !important;
    }

    /* 選択肢の中のテキスト・スパン要素 */
    div[role="option"] *, 
    div[data-baseweb="menu"] * {
        color: #2c2c54 !important;
    }

    /* マウスホバー・アクティブ・フォーカス（紫色の視認性修正） */
    div[role="option"]:hover,
    div[role="option"][aria-selected="true"],
    div[data-baseweb="menu"] [aria-selected="true"] {
        background-color: #f0ebff !important;
    }

    div[role="option"]:hover *,
    div[role="option"][aria-selected="true"] *,
    div[data-baseweb="menu"] [aria-selected="true"] * {
        color: #5a45d6 !important;
        font-weight: bold !important;
    }

    /* ----------------------------------
       サイドバー (Sidebar) デザイン（ガラスモック・グラデーション線）
    ---------------------------------- */
    [data-testid="stSidebar"] {
        background: rgba(255, 255, 255, 0.75) !important;
        backdrop-filter: blur(16px) !important;
        border-right: 1px solid rgba(123, 92, 255, 0.2) !important;
        box-shadow: 4px 0 20px rgba(90, 69, 214, 0.05);
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #5a45d6 !important;
        font-family: 'Rajdhani', 'M PLUS Rounded 1c', sans-serif;
        font-weight: 800;
        letter-spacing: 0.05em;
    }

    /* ----------------------------------
       公式風 華やかヒーローヘッダー
    ---------------------------------- */
    .shiny-header {
        position: relative;
        padding: 32px 20px;
        background: rgba(255, 255, 255, 0.85);
        backdrop-filter: blur(12px);
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.9);
        box-shadow: 0 10px 30px rgba(90, 69, 214, 0.12), 0 2px 10px rgba(81, 194, 240, 0.15);
        text-align: center;
        margin-bottom: 25px;
        overflow: hidden;
    }
    .shiny-title {
        font-family: 'Rajdhani', 'M PLUS Rounded 1c', sans-serif;
        font-size: 2.6rem;
        font-weight: 900;
        letter-spacing: 0.08em;
        background: linear-gradient(135deg, #5a45d6 0%, #7b5cff 40%, #51c2f0 70%, #ff85a1 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0 0 6px 0;
        text-shadow: 0px 4px 15px rgba(123, 92, 255, 0.15);
    }
    .shiny-subtitle {
        font-size: 0.95rem;
        color: #7b5cff !important;
        letter-spacing: 0.18em;
        font-weight: 700;
        text-transform: uppercase;
    }

    /* ----------------------------------
       マルチセレクト / 入力フィールド
    ---------------------------------- */
    div[data-baseweb="select"] {
        background-color: rgba(255, 255, 255, 0.9) !important;
        border-radius: 12px !important;
        border: 1px solid rgba(123, 92, 255, 0.25) !important;
        height: auto !important;
        min-height: 42px !important;
    }
    div[data-baseweb="select"] > div {
        flex-wrap: wrap !important;
        height: auto !important;
        max-width: 100% !important;
        padding: 4px !important;
        background-color: #ffffff !important;
        color: #2c2c54 !important;
    }
    div[data-baseweb="tag"] {
        background: linear-gradient(135deg, #f0ebff 0%, #e6f7ff 100%) !important;
        border: 1px solid #7b5cff !important;
        border-radius: 8px !important;
        padding: 4px 10px !important;
        margin: 3px !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
        height: auto !important;
    }
    div[data-baseweb="tag"] span {
        color: #5a45d6 !important;
        font-weight: 700 !important;
        font-size: 0.85rem !important;
    }

    /* ----------------------------------
       メトリックカード (集計カード) 
    ---------------------------------- */
    [data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.85) !important;
        backdrop-filter: blur(12px) !important;
        border: 1px solid rgba(123, 92, 255, 0.2) !important;
        border-radius: 16px !important;
        padding: 16px 18px !important;
        box-shadow: 0 8px 20px rgba(90, 69, 214, 0.06) !important;
        transition: all 0.3s ease !important;
        height: auto !important;
    }
    [data-testid="stMetric"]:hover {
        border-color: #7b5cff !important;
        box-shadow: 0 10px 25px rgba(123, 92, 255, 0.18) !important;
        transform: translateY(-2px);
    }
    [data-testid="stMetricLabel"] {
        color: #5a45d6 !important;
        font-weight: 800 !important;
        font-size: 0.88rem !important;
    }
    [data-testid="stMetricValue"] {
        color: #2c2c54 !important;
        font-family: 'Rajdhani', 'M PLUS Rounded 1c', sans-serif !important;
        font-weight: 800 !important;
        font-size: 1.6rem !important;
        line-height: 1.3 !important;
    }
    [data-testid="stMetricDelta"] > div {
        color: #ff85a1 !important;
        font-size: 0.82rem !important;
        font-weight: 700 !important;
    }

    /* ----------------------------------
       公式風グラデーションボタン
    ---------------------------------- */
    div.stButton > button {
        width: 100%;
        border-radius: 20px !important;
        font-weight: 700 !important;
        padding: 0.55rem 1rem !important;
        transition: all 0.25s ease !important;
        letter-spacing: 0.02em !important;
        height: auto !important;
    }
    div.stButton > button[kind="secondary"] {
        background: #ffffff !important;
        color: #5a45d6 !important;
        border: 1px solid rgba(123, 92, 255, 0.3) !important;
        box-shadow: 0 2px 8px rgba(90, 69, 214, 0.05) !important;
    }
    div.stButton > button[kind="secondary"]:hover {
        background: #f4f0ff !important;
        color: #5a45d6 !important;
        border-color: #7b5cff !important;
        box-shadow: 0 4px 14px rgba(123, 92, 255, 0.2) !important;
    }
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #7b5cff 0%, #51c2f0 50%, #ff85a1 100%) !important;
        color: #ffffff !important;
        border: none !important;
        box-shadow: 0 4px 15px rgba(123, 92, 255, 0.3) !important;
    }
    div.stButton > button[kind="primary"] p {
        color: #ffffff !important;
    }
    div.stButton > button[kind="primary"]:hover {
        box-shadow: 0 6px 20px rgba(255, 133, 161, 0.4) !important;
        transform: translateY(-1px);
        opacity: 0.95;
    }

    /* ----------------------------------
       タブ (Tabs) デザイン
    ---------------------------------- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: rgba(255, 255, 255, 0.7);
        padding: 6px;
        border-radius: 16px;
        border: 1px solid rgba(123, 92, 255, 0.15);
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 12px;
        padding: 8px 18px;
        color: #5a45d6 !important;
        font-weight: 700;
        transition: all 0.25s ease;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #7b5cff 0%, #51c2f0 100%) !important;
        color: #ffffff !important;
        box-shadow: 0 4px 12px rgba(123, 92, 255, 0.3) !important;
    }
    .stTabs [aria-selected="true"] p {
        color: #ffffff !important;
    }

    .stRadio > div {
        flex-wrap: wrap;
        gap: 8px;
    }

    /* ----------------------------------
       Song for Prism 風：ホワイト×虹彩プリズム
    ---------------------------------- */
    html, body, [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(ellipse at 3% 15%, rgba(191, 225, 255, 0.46), transparent 23%),
            radial-gradient(ellipse at 94% 74%, rgba(255, 218, 238, 0.42), transparent 26%),
            linear-gradient(118deg, #ffffff 0%, #fbfbff 46%, #f5f7ff 100%) !important;
        color: #35365f !important;
    }
    [data-testid="stAppViewContainer"]::before {
        opacity: 0.85;
        background-image:
            linear-gradient(145deg, transparent 0 46%, rgba(139, 125, 225, 0.055) 46.2% 53%, transparent 53.2%),
            linear-gradient(35deg, transparent 0 48%, rgba(109, 208, 241, 0.065) 48.2% 56%, transparent 56.2%),
            radial-gradient(circle at 15% 24%, rgba(255, 234, 159, 0.25), transparent 19%),
            radial-gradient(circle at 80% 12%, rgba(214, 188, 255, 0.22), transparent 21%);
    }
    .block-container {
        max-width: 1460px;
        padding-top: 2.4rem;
    }
    [data-testid="stSidebar"] {
        background: rgba(255, 255, 255, 0.88) !important;
        border-right: 1px solid rgba(131, 124, 196, 0.22) !important;
        box-shadow: 9px 0 34px rgba(66, 59, 130, 0.08) !important;
    }
    [data-testid="stSidebar"]::before {
        content: "";
        position: absolute;
        inset: 0;
        pointer-events: none;
        background: linear-gradient(145deg, transparent 0 43%, rgba(194, 224, 255, 0.28) 43.3% 50%, transparent 50.3%);
    }
    .shiny-header {
        padding: 26px 34px !important;
        margin: 0 auto 32px !important;
        max-width: 980px;
        background: rgba(255, 255, 255, 0.74) !important;
        border: 1px solid rgba(255, 255, 255, 0.96) !important;
        border-bottom: 4px solid rgba(121, 115, 183, 0.38) !important;
        border-radius: 0 !important;
        clip-path: polygon(3% 0, 97% 0, 100% 20%, 100% 80%, 97% 100%, 3% 100%, 0 80%, 0 20%);
        box-shadow: 0 15px 35px rgba(54, 49, 112, 0.13) !important;
    }
    .shiny-header::after {
        content: "";
        position: absolute;
        inset: 7px;
        border: 1px solid rgba(124, 119, 190, 0.28);
        clip-path: polygon(3% 0, 97% 0, 100% 20%, 100% 80%, 97% 100%, 3% 100%, 0 80%, 0 20%);
        pointer-events: none;
    }
    .shiny-title {
        font-size: clamp(1.8rem, 4vw, 2.8rem) !important;
        letter-spacing: 0.12em !important;
        background: linear-gradient(105deg, #575394 8%, #7c79bd 38%, #79c6df 64%, #d59ec4 92%) !important;
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
    }
    .shiny-subtitle {
        color: #6e6aa6 !important;
        letter-spacing: 0.12em !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0 !important;
        display: flex !important;
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        overflow-y: hidden !important;
        scrollbar-width: thin;
        padding: 5px 18px !important;
        background: rgba(255, 255, 255, 0.78) !important;
        border: 1px solid rgba(130, 123, 190, 0.24) !important;
        border-radius: 0 !important;
        clip-path: polygon(1.5% 0, 98.5% 0, 100% 50%, 98.5% 100%, 1.5% 100%, 0 50%);
        box-shadow: 0 8px 22px rgba(64, 58, 124, 0.1) !important;
    }
    .stTabs [data-baseweb="tab"] {
        flex: 0 0 auto !important;
        white-space: nowrap !important;
        text-wrap: nowrap !important;
        min-height: 44px !important;
        padding: 8px 15px !important;
        border-radius: 0 !important;
        color: #626095 !important;
        font-family: 'Rajdhani', 'M PLUS Rounded 1c', sans-serif !important;
        font-size: 0.92rem !important;
        letter-spacing: 0.04em !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #5a5795 0%, #7774b5 55%, #4e91b5 100%) !important;
        clip-path: polygon(8% 0, 92% 0, 100% 50%, 92% 100%, 8% 100%, 0 50%) !important;
        box-shadow: none !important;
    }
    [data-testid="stMetric"], [data-testid="stDataFrame"] {
        background: rgba(255, 255, 255, 0.91) !important;
        border: 1px solid rgba(126, 118, 185, 0.22) !important;
        border-radius: 0 !important;
        box-shadow: 0 10px 26px rgba(59, 53, 115, 0.09) !important;
    }
    [data-testid="stMetric"] {
        border-bottom: 3px solid rgba(122, 192, 218, 0.42) !important;
    }
    div[data-baseweb="select"], div[data-baseweb="select"] > div {
        border-radius: 0 !important;
        background: rgba(255, 255, 255, 0.94) !important;
    }
    div[data-baseweb="select"] {
        border-color: rgba(116, 108, 181, 0.35) !important;
        clip-path: polygon(2% 0, 98% 0, 100% 50%, 98% 100%, 2% 100%, 0 50%);
    }
    div.stButton > button {
        border-radius: 0 !important;
        clip-path: polygon(8% 0, 92% 0, 100% 50%, 92% 100%, 8% 100%, 0 50%);
        font-family: 'Rajdhani', 'M PLUS Rounded 1c', sans-serif !important;
        letter-spacing: 0.08em !important;
    }
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #575391 0%, #7f7aba 52%, #529bb8 100%) !important;
        box-shadow: 0 8px 17px rgba(75, 69, 146, 0.25) !important;
    }
    div.stButton > button[kind="secondary"] {
        background: rgba(255, 255, 255, 0.92) !important;
        color: #605d9d !important;
        border-color: rgba(100, 94, 165, 0.42) !important;
    }
    h1, h2, h3 {
        color: #4f4d82 !important;
        letter-spacing: 0.04em !important;
    }
    hr {
        border-color: rgba(115, 108, 179, 0.22) !important;
    }
    .lyric-result {
        background: rgba(255, 255, 255, 0.86);
        border: 1px solid rgba(115, 108, 179, 0.22);
        border-left: 4px solid #72b8db;
        box-shadow: 0 8px 22px rgba(59, 53, 115, 0.08);
        margin: 0.35rem 0 0.9rem;
        padding: 0.8rem 1rem;
        line-height: 1.9;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        word-break: break-word;
    }
    mark.lyric-hit {
        background: linear-gradient(120deg, rgba(255, 218, 101, 0.88), rgba(255, 165, 198, 0.68));
        color: #343052 !important;
        border-radius: 3px;
        padding: 0.04em 0.16em;
        font-weight: 800;
    }

    /* 狭い画面・ブラウザ拡大時：情報を潰さず、読むことを最優先にする */
    @media (max-width: 900px) {
        .block-container {
            padding: 1rem 1rem 2.5rem !important;
        }
        .shiny-header {
            margin-bottom: 1.2rem !important;
            padding: 1.1rem 1.25rem !important;
            clip-path: none !important;
        }
        .shiny-header::after {
            display: none !important;
        }
        .shiny-title {
            font-size: clamp(1.45rem, 7vw, 2.15rem) !important;
            line-height: 1.25 !important;
            letter-spacing: 0.04em !important;
            word-break: keep-all !important;
            overflow-wrap: anywhere !important;
        }
        .shiny-subtitle {
            font-size: 0.72rem !important;
            line-height: 1.5 !important;
            letter-spacing: 0.04em !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            display: flex !important;
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
            overflow-y: hidden !important;
            padding: 0.25rem !important;
            clip-path: none !important;
            scrollbar-width: thin;
        }
        .stTabs [data-baseweb="tab"] {
            flex: 0 0 auto !important;
            white-space: nowrap !important;
            min-height: 2.65rem !important;
            padding: 0.5rem 0.8rem !important;
            font-size: 0.8rem !important;
        }
        .stTabs [aria-selected="true"] {
            clip-path: none !important;
            border-radius: 0.35rem !important;
        }
        [data-testid="stMetric"] {
            min-width: 0 !important;
            padding: 0.8rem 0.75rem !important;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.78rem !important;
            line-height: 1.4 !important;
            word-break: keep-all !important;
        }
        [data-testid="stMetricValue"] {
            font-size: clamp(1.35rem, 7vw, 1.8rem) !important;
            word-break: keep-all !important;
            line-height: 1.2 !important;
        }
        div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
            flex-wrap: wrap !important;
            gap: 0.65rem !important;
        }
        div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="column"] {
            flex: 1 1 calc(50% - 0.65rem) !important;
            width: calc(50% - 0.65rem) !important;
            min-width: 8.3rem !important;
        }
        h1 { font-size: clamp(1.55rem, 7vw, 2.2rem) !important; }
        h2 { font-size: clamp(1.25rem, 6vw, 1.7rem) !important; }
        h3 { font-size: clamp(1.08rem, 5vw, 1.4rem) !important; }
        p, li, label { font-size: 0.96rem !important; }
    }
    @media (max-width: 480px) {
        .block-container { padding-left: 0.75rem !important; padding-right: 0.75rem !important; }
        div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="column"] {
            flex-basis: 100% !important;
            width: 100% !important;
        }
        [data-testid="stMetric"] { padding: 0.9rem 1rem !important; }
        .stTabs [data-baseweb="tab"] { font-size: 0.76rem !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------
# 画面全体の最終UIレイヤー
# 古い端末・ブラウザ拡大時でも、文字と操作部品が潰れないことを優先する。
# ------------------------------------------
st.markdown(
    """
    <style>
    :root {
        --sc-ink: #29294f;
        --sc-muted: #717394;
        --sc-violet: #6657d9;
        --sc-violet-soft: #eeeaff;
        --sc-blue: #3daed7;
        --sc-pink: #ed7fa8;
        --sc-border: rgba(92, 84, 163, 0.20);
        --sc-surface: rgba(255, 255, 255, 0.92);
        --sc-shadow: 0 10px 28px rgba(55, 49, 111, 0.09);
    }

    html {
        font-size: clamp(14px, 0.12vw + 13px, 16px);
    }
    [data-testid="stAppViewContainer"] {
        overflow-x: hidden;
    }
    [data-testid="stMainBlockContainer"],
    .block-container {
        width: min(100%, 1600px) !important;
        max-width: 1600px !important;
        /* Streamlit の固定ヘッダー（約 3.75rem）の下から始める */
        padding: 4.35rem clamp(0.65rem, 1.4vw, 1.35rem) 2.2rem !important;
    }
    [data-testid="stMainBlockContainer"] > div {
        gap: 0.45rem;
    }

    /* ブランド帯は内容を邪魔しない高さにする */
    .shiny-header {
        max-width: none !important;
        margin: 0 0 0.45rem !important;
        padding: 0.45rem clamp(0.75rem, 1.5vw, 1.1rem) !important;
        text-align: left !important;
        clip-path: none !important;
        border-radius: 14px !important;
        border: 1px solid rgba(255, 255, 255, 0.94) !important;
        border-left: 5px solid #7165db !important;
        border-bottom: 1px solid var(--sc-border) !important;
        box-shadow: 0 7px 22px rgba(55, 49, 111, 0.08) !important;
    }
    .shiny-header::after {
        display: none !important;
    }
    .shiny-title {
        font-size: clamp(1rem, 1.55vw, 1.35rem) !important;
        line-height: 1.15 !important;
        letter-spacing: 0.055em !important;
        margin: 0 !important;
    }
    .shiny-subtitle {
        margin-top: 0.1rem;
        font-size: clamp(0.62rem, 0.8vw, 0.72rem) !important;
        line-height: 1.35 !important;
        letter-spacing: 0.07em !important;
    }

    /* 各ページの見出しを共通カード化 */
    .app-page-header {
        position: relative;
        overflow: hidden;
        margin: 0.3rem 0 0.6rem;
        padding: 0.62rem clamp(0.75rem, 1.5vw, 1rem);
        border: 1px solid var(--sc-border);
        border-radius: 12px;
        background:
            linear-gradient(112deg, rgba(255,255,255,.96), rgba(245,243,255,.9) 58%, rgba(231,247,255,.88));
        box-shadow: var(--sc-shadow);
    }
    .app-page-header::after {
        content: "";
        position: absolute;
        right: -1.5rem;
        top: -2.2rem;
        width: 7rem;
        height: 7rem;
        transform: rotate(28deg);
        background: linear-gradient(135deg, rgba(108,91,218,.12), rgba(61,174,215,.10), rgba(237,127,168,.10));
    }
    .app-page-title {
        position: relative;
        z-index: 1;
        margin: 0;
        color: var(--sc-ink) !important;
        font-size: clamp(1.22rem, 2vw, 1.65rem);
        font-weight: 900;
        line-height: 1.22;
        letter-spacing: 0.025em;
        overflow-wrap: anywhere;
    }
    .app-page-description {
        position: relative;
        z-index: 1;
        margin: 0.18rem 0 0;
        max-width: 72rem;
        color: var(--sc-muted) !important;
        font-size: 0.78rem;
        line-height: 1.45;
    }
    .analysis-target-card {
        margin: 0.35rem 0 0.7rem;
        padding: 0.65rem 0.8rem;
        border: 1px solid var(--sc-border);
        border-left: 5px solid var(--sc-violet);
        border-radius: 12px;
        background: var(--sc-surface);
        box-shadow: 0 6px 18px rgba(55, 49, 111, 0.07);
    }
    .analysis-target-label {
        color: var(--sc-violet) !important;
        font-size: 0.78rem;
        font-weight: 900;
        letter-spacing: 0.04em;
    }
    .analysis-target-title {
        margin-top: 0.18rem;
        color: var(--sc-ink) !important;
        font-size: clamp(1.05rem, 2vw, 1.28rem);
        font-weight: 900;
        line-height: 1.45;
        overflow-wrap: anywhere;
    }
    .analysis-target-meta {
        margin-top: 0.28rem;
        color: var(--sc-muted) !important;
        font-size: 0.86rem;
        line-height: 1.5;
    }

    /* 主ナビゲーション。横スクロールでき、現在地は明確にする */
    .stTabs [data-baseweb="tab-list"] {
        position: relative !important;
        top: auto !important;
        z-index: 1 !important;
        gap: 0.15rem !important;
        padding: 0.16rem !important;
        border-radius: 13px !important;
        clip-path: none !important;
        background: rgba(255, 255, 255, 0.93) !important;
        backdrop-filter: blur(18px) !important;
        box-shadow: 0 7px 22px rgba(48, 43, 99, 0.11) !important;
        scrollbar-color: rgba(102,87,217,.45) transparent;
    }
    .stTabs [data-baseweb="tab"] {
        min-height: 38px !important;
        padding: 0.36rem 0.55rem !important;
        border-radius: 9px !important;
        clip-path: none !important;
        font-family: 'M PLUS Rounded 1c', sans-serif !important;
        font-size: 0.76rem !important;
        letter-spacing: 0 !important;
    }
    .stTabs [data-baseweb="tab"] * {
        white-space: nowrap !important;
        word-break: keep-all !important;
        overflow-wrap: normal !important;
    }
    /* Streamlitの実際のタブボタンにも直接指定し、スマホで1文字ずつ折れないようにする。 */
    .stTabs button[role="tab"],
    .stTabs button[role="tab"] * {
        width: max-content !important;
        min-width: max-content !important;
        white-space: nowrap !important;
        word-break: keep-all !important;
        overflow-wrap: normal !important;
    }
    @media (max-width: 900px) {
        .stTabs [data-baseweb="tab-list"] {
            overflow-x: scroll !important;
            overscroll-behavior-x: contain;
            -webkit-overflow-scrolling: touch;
        }
        div[data-baseweb="popover"],
        ul[role="listbox"] {
            max-height: 38vh !important;
            overflow-y: auto !important;
        }
    }
    .stTabs [aria-selected="true"] {
        border-radius: 9px !important;
        clip-path: none !important;
        background: linear-gradient(125deg, #6255cf, #5b93d0) !important;
        box-shadow: 0 4px 12px rgba(83, 71, 180, 0.28) !important;
    }

    /* 入力部品は同じ高さ・角丸・余白に統一 */
    div[data-baseweb="select"],
    div[data-baseweb="select"] > div,
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stDateInput"] input,
    [data-testid="stTextArea"] textarea {
        border-radius: 10px !important;
        clip-path: none !important;
    }
    div[data-baseweb="select"] {
        min-height: 40px !important;
        border: 1px solid rgba(102, 87, 217, 0.28) !important;
        box-shadow: 0 2px 8px rgba(61, 55, 120, 0.04);
    }
    [data-testid="stWidgetLabel"] p {
        color: var(--sc-ink) !important;
        font-size: 0.78rem !important;
        font-weight: 700 !important;
        line-height: 1.45 !important;
    }
    div.stButton > button,
    [data-testid="stDownloadButton"] button,
    [data-testid="stLinkButton"] a {
        min-height: 36px;
        border-radius: 10px !important;
        clip-path: none !important;
        letter-spacing: 0 !important;
    }

    /* 数値・表・通知を読みやすくする */
    [data-testid="stMetric"] {
        height: 100% !important;
        min-height: 82px;
        padding: 0.62rem 0.75rem !important;
        border-radius: 10px !important;
    }
    [data-testid="stMetricValue"] {
        font-size: clamp(1.25rem, 2vw, 1.65rem) !important;
        line-height: 1.1 !important;
    }
    [data-testid="stMetricDelta"] {
        overflow-wrap: anywhere;
    }
    [data-testid="stDataFrame"] {
        overflow: hidden;
        border-radius: 13px !important;
        box-shadow: 0 6px 20px rgba(55, 49, 111, 0.07) !important;
    }
    [data-testid="stAlert"] {
        border-radius: 12px;
    }
    [data-testid="stExpander"] {
        overflow: hidden;
        border: 1px solid var(--sc-border);
        border-radius: 12px;
        background: rgba(255,255,255,.66);
    }
    hr {
        margin: 1rem 0 !important;
    }

    /* サイドバーを長い設定一覧として読みやすくする */
    [data-testid="stSidebar"] {
        min-width: min(88vw, 330px) !important;
    }
    [data-testid="stSidebarContent"] {
        padding-top: 0.5rem;
    }
    [data-testid="stSidebar"] {
        font-size: 0.84rem;
    }
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
        font-size: 0.76rem !important;
    }
    [data-testid="stSidebar"] div.stButton > button {
        min-height: 34px;
        font-size: 0.76rem;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.55rem;
    }

    @media (max-width: 900px) {
        [data-testid="stMainBlockContainer"],
        .block-container {
            padding: 4.1rem 0.72rem 3rem !important;
        }
        .shiny-header {
            padding: 0.62rem 0.85rem !important;
            margin-bottom: 0.65rem !important;
        }
        .shiny-subtitle {
            display: none;
        }
        .app-page-header {
            margin: 0.45rem 0 0.75rem;
            padding: 0.82rem 0.9rem;
            border-radius: 13px;
        }
        .app-page-title {
            font-size: clamp(1.35rem, 6.3vw, 1.9rem);
        }
        .app-page-description {
            font-size: 0.84rem;
            line-height: 1.55;
        }
        .stTabs [data-baseweb="tab-list"] {
            top: auto !important;
            margin-left: -0.15rem;
            margin-right: -0.15rem;
        }
        .stTabs [data-baseweb="tab"] {
            min-height: 42px !important;
            padding: 0.5rem 0.68rem !important;
            font-size: 0.8rem !important;
        }
        [data-testid="stMetric"] {
            min-height: 98px;
        }
        div[data-testid="stHorizontalBlock"]:has([data-testid="stSelectbox"]),
        div[data-testid="stHorizontalBlock"]:has([data-testid="stTextInput"]),
        div[data-testid="stHorizontalBlock"]:has([data-testid="stRadio"]),
        div[data-testid="stHorizontalBlock"]:has([data-testid="stDataFrame"]) {
            flex-wrap: wrap !important;
        }
        div[data-testid="stHorizontalBlock"]:has([data-testid="stSelectbox"]) > [data-testid="column"],
        div[data-testid="stHorizontalBlock"]:has([data-testid="stTextInput"]) > [data-testid="column"],
        div[data-testid="stHorizontalBlock"]:has([data-testid="stRadio"]) > [data-testid="column"],
        div[data-testid="stHorizontalBlock"]:has([data-testid="stDataFrame"]) > [data-testid="column"] {
            flex: 1 1 min(100%, 19rem) !important;
            width: auto !important;
            min-width: min(100%, 16rem) !important;
        }
        div[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) {
            flex-wrap: wrap !important;
        }
        div[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) > [data-testid="column"] {
            flex: 1 1 6.5rem !important;
            min-width: 6.5rem !important;
        }
    }
    @media (max-width: 520px) {
        .shiny-title {
            font-size: 1.08rem !important;
            letter-spacing: 0.015em !important;
        }
        .app-page-header::after {
            opacity: 0.55;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.84rem !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.55rem !important;
        }
    }
    /* モバイルの主タブは縮小せず、横にスワイプして選ぶ。 */
    @media (max-width: 900px) {
        .stTabs [role="tablist"],
        .stTabs [data-baseweb="tab-list"] {
            display: flex !important;
            flex-wrap: nowrap !important;
            width: 100% !important;
            overflow-x: auto !important;
            overflow-y: hidden !important;
            -webkit-overflow-scrolling: touch !important;
        }
        .stTabs [role="tab"],
        .stTabs button[role="tab"],
        .stTabs [data-baseweb="tab"] {
            display: inline-flex !important;
            flex: 0 0 auto !important;
            width: auto !important;
            min-width: max-content !important;
            max-width: none !important;
            white-space: nowrap !important;
        }
        .stTabs [role="tab"] * {
            white-space: nowrap !important;
            word-break: keep-all !important;
            overflow-wrap: normal !important;
        }
    }
    .ranking-card-list {
        display: grid;
        gap: 0.55rem;
        margin-top: 0.55rem;
    }
    .ranking-card {
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid rgba(102, 87, 217, 0.2);
        border-radius: 12px;
        padding: 0.72rem 0.85rem;
        box-shadow: 0 4px 13px rgba(54, 47, 117, 0.06);
    }
    .ranking-card--1 { border-left: 5px solid #d7a61d; background: #fff9e6; }
    .ranking-card--2 { border-left: 5px solid #9aa3ac; background: #f5f6f7; }
    .ranking-card--3 { border-left: 5px solid #c97a77; background: #fff3f2; }
    .ranking-card-title {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        color: #29274f !important;
        font-size: 1.02rem;
        line-height: 1.4;
    }
    .ranking-card-rank {
        display: inline-grid;
        place-items: center;
        width: 1.8rem;
        height: 1.8rem;
        flex: 0 0 1.8rem;
        border-radius: 50%;
        background: #6158b8;
        color: #ffffff !important;
        font-weight: 800;
    }
    .ranking-card-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem 1rem;
        margin: 0.65rem 0 0;
    }
    .ranking-card-meta div { display: flex; gap: 0.25rem; }
    .ranking-card-meta dt { color: #6d6899 !important; font-size: 0.8rem; }
    .ranking-card-meta dd { margin: 0; color: #35335e !important; font-size: 0.8rem; font-weight: 700; }
    @media (min-width: 901px) {
        .ranking-card-list {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.85rem;
        }
        .ranking-card {
            min-height: 6.6rem;
            padding: 0.95rem 1rem;
        }
        .ranking-card-title { font-size: 1.12rem; }
        .ranking-card-meta {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.35rem 0.7rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ヒーロータイトル表示
st.markdown(
    """
    <div class="shiny-header">
        <div class="shiny-title">✨ SHINY COLORS LIVE DATABASE ✨</div>
        <div class="shiny-subtitle">アイドルマスター シャイニーカラーズ ライブデータベース</div>
    </div>
    """,
    unsafe_allow_html=True
)

# ファイルパスの設定
SETLIST_FILE = "songs.csv"
CATEGORY_FILE = "songs_categories.csv"
SONG_ALBUM_FILE = "songs_albums.csv"
ALBUM_MASTER_FILE = "albums.csv"
EVENT_MASTER_FILE = "events.csv"
IDOL_MASTER_FILE = "idols.csv"
COSTUME_MASTER_FILE = "costumes.csv"
LYRICS_FILE = "lyrics.csv"
ATTENDANCE_FILE = "cast_attendance.csv"
BROADCAST_FILE = "broadcasts.csv"
CARD_FILE = "cards.tsv"
COMMENTARY_BD_FILE = "commentary_blu_ray.csv"
COMMENTARY_STREAM_FILE = "commentary_streaming.csv"
RADIO_APPEARANCE_FILE = "shiny_radio_appearances.csv"
RADIO_EPISODE_FILE = "shiny_radio_episodes.tsv"
JACKET_MAP_FILE = "release_jackets.csv"
SONG_JACKET_FILE = "song_jackets.csv"
JACKET_DIR = "album_jackets"
YOUTUBE_AUDIO_DRAFT_FILE = "youtube_media_links_draft.csv"
YOUTUBE_AUDIO_VARIANTS_FILE = "youtube_media_variants_manual.csv"
MIGRATORY_ECHOES_MEDIA_FILE = "youtube_migratory_echoes_media.csv"
YOUTUBE_VIDEO_VARIANTS_FILE = "youtube_video_variants_manual.csv"
YOUTUBE_ALBUM_PREVIEW_FILE = "youtube_album_preview_links.csv"
YOUTUBE_UNIT_PV_FILE = "youtube_unit_pv_links.csv"
YOUTUBE_RADIO_CLIP_FILE = "youtube_radio_clip_links.csv"
YOUTUBE_LIVE_AP_STREAM_FILE = "youtube_live_ap_stream_links.csv"
YOUTUBE_ANNIVERSARY_PV_FILE = "youtube_anniversary_pv_links.csv"
EVENT_SOCIAL_LINKS_FILE = "event_social_links.csv"
YOUTUBE_LIVE_DIGEST_FILE = "youtube_live_digest_links_manual.csv"
YOUTUBE_XR_INTRO_FILE = "youtube_xr_free_intro_links_manual.csv"
EVENT_OFFICIAL_SITE_FILE = "event_official_sites.csv"
PRICE_HISTORY_FILE = "price_history.csv"

# 5.5th Anniversary LIVE 「星が見上げた空」は、全体曲でもユニットごとに
# 着用衣装が固定されているため、通常の全体衣装フォールバックより先に判定する。
FIVE_HALF_EVENT_COSTUME_OVERRIDES = {
    "イルミネーションスターズ": "ビヨンドザブルースカイ",
    "アンティーカ": "ビヨンドザブルースカイ",
    "放課後クライマックスガールズ": "ビヨンドザブルースカイ",
    "アルストロメリア": "ビヨンドザブルースカイ",
    "ストレイライト": "オーバーキャストモノクローム",
    "ノクチル": "サンセットスカイパッセージ",
    "シーズ": "ユナイトバースプラネタリ",
    "コメティック": "コメティックノート",
}

# 公式のユニット・アイドルカラー。カード入力時の確認表示などで使う。
MEMBER_COLOR_MAP = {
    "イルミネーションスターズ": "#fff68d", "櫻木真乃": "#ffbad6", "風野灯織": "#144384", "八宮めぐる": "#ffe012",
    "アンティーカ": "#853998", "月岡恋鐘": "#f84cad", "田中摩美々": "#a846fb", "白瀬咲耶": "#006047", "三峰結華": "#3b91c4", "幽谷霧子": "#d9f2ff",
    "放課後クライマックスガールズ": "#fa8333", "小宮果穂": "#e5461c", "園田智代子": "#f93b90", "西城樹里": "#ffc602", "杜野凛世": "#89c3eb", "有栖川夏葉": "#90e667",
    "アルストロメリア": "#ff699e", "大崎甘奈": "#f54275", "大崎甜花": "#e75bec", "桑山千雪": "#fafafa",
    "ストレイライト": "#af011c", "芹沢あさひ": "#f30100", "黛冬優子": "#5aff19", "和泉愛依": "#ff00ff",
    "ノクチル": "#384d98", "浅倉透": "#50d0d0", "樋口円香": "#be1e3e", "福丸小糸": "#7967c3", "市川雛菜": "#ffc639",
    "SHHis": "#008e74", "シーズ": "#008e74", "七草にちか": "#a6cdb6", "緋田美琴": "#760f10",
    "コメティック": "#333333", "斑鳩ルカ": "#35281f", "鈴木羽那": "#e0b5d3", "郁田はるき": "#ead7a4",
    "七草はづき": "#8adfff", "シャイニーカラーズ": "#8dbbff",
}

# PJ:REFRAC7IONS の配色。既存のイメージカラーと併記し、カード登録時などで確認に使う。
PROJECT_COLOR_MAP = {
    "櫻木真乃": "#FBC600", "風野灯織": "#FBFBF6", "八宮めぐる": "#EC6816",
    "月岡恋鐘": "#8E4593", "田中摩美々": "#F4D500", "白瀬咲耶": "#355273", "三峰結華": "#B0E0E6", "幽谷霧子": "#B86D77",
    "小宮果穂": "#E3FF00", "園田智代子": "#C1F9A2", "西城樹里": "#D94DFF", "杜野凛世": "#E8ECEF", "有栖川夏葉": "#EB6101",
    "大崎甘奈": "#FDDDCD", "大崎甜花": "#FFB366", "桑山千雪": "#93B881",
    "芹沢あさひ": "#ED6C00", "黛冬優子": "#7DF9FF", "和泉愛依": "#B7282E",
    "浅倉透": "#719BAD", "樋口円香": "#FE347E", "福丸小糸": "#CFD4F1", "市川雛菜": "#235BC8",
    "七草にちか": "#CEC5F0", "緋田美琴": "#006374", "斑鳩ルカ": "#6050DC", "鈴木羽那": "#FFBCD9", "郁田はるき": "#E83F1D",
    "I’m a Cutie Finder": "#7BFFC3", "Fumage": "#3582A2", "Sonic Heart (and Signal)": "#0068B7",
    "Σ Desire": "#A1A3A6", "ザ・ふたりトラベラー": "#E83F1D", "彼岸流": "#5AB5B2", "No 1 feel alone": "#F3F0EF",
}

SPECIAL_UNIT_COLOR_MAP = {
    "I’m a Cutie Finder": "#FFD4F5", "Fumage": "#2A5D79", "Sonic Heart (and Signal)": "#FFF700",
    "Σ Desire": "#282928", "ザ・ふたりトラベラー": "#FBC600", "彼岸流": "#E7001D", "No 1 feel alone": "#AFCBEB",
    "Team.Stella": "#E9868C", "Team.Luna": "#527CC5", "Team.Sol": "#D5A52C",
    "アール・エ・クルール": "#4F78D8", "マエストリア・エ・トラディチオーネ": "#078B96",
    "ストリート・アンド・アヴォンガード": "#F05D55", "アーバン・アンド・ライフスタイル": "#9A9A9A",
}


def member_color_swatch(name):
    """既存色とPJ:REFRAC7IONS色を並べた、小さな確認用スウォッチ。"""
    primary = MEMBER_COLOR_MAP.get(str(name), "") or SPECIAL_UNIT_COLOR_MAP.get(str(name), "")
    project = PROJECT_COLOR_MAP.get(str(name), "")
    colors = [color for color in (primary, project) if re.fullmatch(r"#[0-9a-fA-F]{6}", color)]
    if not colors:
        return "", ""
    background = colors[0] if len(colors) == 1 else f"linear-gradient(135deg, {colors[0]} 0 50%, {colors[1]} 50% 100%)"
    label = " / ".join(colors)
    return background, label


def display_group_color(name):
    """通常・公演固有を問わず、表示に使う代表色を返す。"""
    return MEMBER_COLOR_MAP.get(str(name), "") or SPECIAL_UNIT_COLOR_MAP.get(str(name), "")


def display_group_background(name):
    """PJ:REFRAC7IONS は色①・色②を使い、その他は単色で表示する。"""
    primary = display_group_color(name)
    accent = PROJECT_COLOR_MAP.get(str(name), "")
    if (
        str(name) in SPECIAL_UNIT_COLOR_MAP
        and re.fullmatch(r"#[0-9a-fA-F]{6}", primary)
        and re.fullmatch(r"#[0-9a-fA-F]{6}", accent)
    ):
        return f"linear-gradient(135deg, {primary} 0%, {primary} 48%, {accent} 52%, {accent} 100%)"
    return primary


def render_unit_color_badges(unit_names):
    """表のスタイル制限を避け、PJユニットの2色を確実に表示する。"""
    badges = []
    for unit_name in unique_in_registered_order([str(name) for name in unit_names if str(name).strip()]):
        color = display_group_color(unit_name)
        background = display_group_background(unit_name)
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            continue
        red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
        brightness = (red * 299 + green * 587 + blue * 114) / 1000
        text_color = "#20243d" if brightness > 165 else "#ffffff"
        badges.append(
            '<span style="display:inline-block;margin:0 8px 8px 0;padding:5px 10px;'
            f'border-radius:999px;background:{background};color:{text_color} !important;'
            'font-weight:800;text-shadow:0 1px 1px rgba(255,255,255,.22);">'
            f'{html.escape(unit_name)}</span>'
        )
    if badges:
        st.markdown("<div style=\"margin:0.2rem 0 0.7rem;\">" + "".join(badges) + "</div>", unsafe_allow_html=True)


def find_file(filename):
    if os.path.exists(filename):
        return filename
    sub_path = os.path.join("shiny", filename)
    if os.path.exists(sub_path):
        return sub_path
    return filename


SETLIST_FILE = find_file(SETLIST_FILE)
CATEGORY_FILE = find_file(CATEGORY_FILE)
SONG_ALBUM_FILE = find_file(SONG_ALBUM_FILE)
ALBUM_MASTER_FILE = find_file(ALBUM_MASTER_FILE)
EVENT_MASTER_FILE = find_file(EVENT_MASTER_FILE)
IDOL_MASTER_FILE = find_file(IDOL_MASTER_FILE)
COSTUME_MASTER_FILE = find_file(COSTUME_MASTER_FILE)
LYRICS_FILE = find_file(LYRICS_FILE)
ATTENDANCE_FILE = find_file(ATTENDANCE_FILE)
BROADCAST_FILE = find_file(BROADCAST_FILE)
CARD_FILE = find_file(CARD_FILE)
COMMENTARY_BD_FILE = find_file(COMMENTARY_BD_FILE)
COMMENTARY_STREAM_FILE = find_file(COMMENTARY_STREAM_FILE)
RADIO_APPEARANCE_FILE = find_file(RADIO_APPEARANCE_FILE)
RADIO_EPISODE_FILE = find_file(RADIO_EPISODE_FILE)
if not os.path.exists(LYRICS_FILE):
    LYRICS_FILE = find_file("ライブ歌唱履歴 - 歌詞 のコピー.csv")
JACKET_MAP_FILE = find_file(JACKET_MAP_FILE)
SONG_JACKET_FILE = find_file(SONG_JACKET_FILE)
JACKET_DIR = find_file(JACKET_DIR)
YOUTUBE_AUDIO_DRAFT_FILE = find_file(YOUTUBE_AUDIO_DRAFT_FILE)
YOUTUBE_AUDIO_VARIANTS_FILE = find_file(YOUTUBE_AUDIO_VARIANTS_FILE)
MIGRATORY_ECHOES_MEDIA_FILE = find_file(MIGRATORY_ECHOES_MEDIA_FILE)
YOUTUBE_VIDEO_VARIANTS_FILE = find_file(YOUTUBE_VIDEO_VARIANTS_FILE)
YOUTUBE_ALBUM_PREVIEW_FILE = find_file(YOUTUBE_ALBUM_PREVIEW_FILE)
YOUTUBE_UNIT_PV_FILE = find_file(YOUTUBE_UNIT_PV_FILE)
YOUTUBE_RADIO_CLIP_FILE = find_file(YOUTUBE_RADIO_CLIP_FILE)
YOUTUBE_LIVE_AP_STREAM_FILE = find_file(YOUTUBE_LIVE_AP_STREAM_FILE)
YOUTUBE_ANNIVERSARY_PV_FILE = find_file(YOUTUBE_ANNIVERSARY_PV_FILE)
EVENT_SOCIAL_LINKS_FILE = find_file(EVENT_SOCIAL_LINKS_FILE)
YOUTUBE_LIVE_DIGEST_FILE = find_file(YOUTUBE_LIVE_DIGEST_FILE)
YOUTUBE_XR_INTRO_FILE = find_file(YOUTUBE_XR_INTRO_FILE)
EVENT_OFFICIAL_SITE_FILE = find_file(EVENT_OFFICIAL_SITE_FILE)
PRICE_HISTORY_FILE = find_file(PRICE_HISTORY_FILE)


# ------------------------------------------
# ユーティリティ関数
# ------------------------------------------
@lru_cache(maxsize=65536)
def clean_text(text):
    if not isinstance(text, str):
        return text
    text = re.sub(r"(br|Td)\s*\{[^}]*\}", "", text, flags=re.IGNORECASE)
    # 全角・半角の記号差で、楽曲・衣装・出演者などが別データにならないよう統一する。
    text = text.translate(str.maketrans({"！": "!", "？": "?", "＆": "&", "／": "/", "：": ":"}))
    text = text.replace("　", " ").strip()
    return re.sub(r"\s+", " ", text)


@lru_cache(maxsize=32768)
def clean_live_name(text):
    if not isinstance(text, str):
        return text
    text = re.sub(
        r"THE\s+IDOLM@STER\s+SHINY\s+COLORS\s*", "", text, flags=re.IGNORECASE
    )
    return text.strip()


@lru_cache(maxsize=32768)
def clean_song_title_for_search(text):
    if not isinstance(text, str):
        return ""
    text = clean_text(text)
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"[―ー－—–‐]", "-", text)
    return text.strip()


@lru_cache(maxsize=65536)
def make_search_key(text):
    if not isinstance(text, str):
        return ""
    text = clean_song_title_for_search(text).lower()
    text = text.replace("？", "?").replace("！", "!")
    # 「フェアリー・ガール」/「フェアリーガール」のような中黒の有無は同一扱いにする。
    text = text.replace("・", "").replace("･", "")
    return re.sub(r"\s+", "", text)


@st.cache_data(show_spinner=False, max_entries=FILE_CACHE_MAX_ENTRIES)
def _load_csv_cached(absolute_path, file_signature):
    """更新時刻とサイズをキーにして、同じファイルの再読込を省く。"""
    load_error = None
    for encoding_name in ["utf-8-sig", "utf-8", "cp932", "shift_jis"]:
        try:
            # sep=None はカンマ・タブを自動判定する。engine="python" が必要。
            return pd.read_csv(
                absolute_path,
                encoding=encoding_name,
                sep=None,
                engine="python",
            )
        except (UnicodeDecodeError, pd.errors.ParserError, ValueError, OSError) as error:
            load_error = str(error)
    raise ValueError(f"CSVを読み込めませんでした: {absolute_path} ({load_error})")


def load_csv(file_path):
    """CSV・TSVを安全に読み込む。変更されていないファイルはメモリから返す。"""
    absolute_path = os.path.abspath(file_path)
    stat = os.stat(absolute_path)
    signature = (stat.st_mtime_ns, stat.st_size)
    # 呼び出し側で列を追加してもキャッシュ本体を汚さないよう、浅いコピーを返す。
    return _load_csv_cached(absolute_path, signature).copy()


def normalize_dataframe(dataframe, clean_column_names=True):
    """列名と文字列列を一括で整え、各読込箇所の重複処理を減らす。"""
    normalized = dataframe.copy()
    if clean_column_names:
        normalized.columns = [clean_text(column) for column in normalized.columns]
    object_columns = normalized.select_dtypes(include=["object", "string"]).columns
    for column in object_columns:
        normalized[column] = normalized[column].map(clean_text)
    return normalized


@st.cache_data(show_spinner=False, max_entries=FILE_CACHE_MAX_ENTRIES)
def _load_normalized_csv_cached(absolute_path, file_signature):
    """読込後の文字列整形まで含めてキャッシュする。"""
    return normalize_dataframe(
        _load_csv_cached(absolute_path, file_signature)
    )


def load_normalized_csv(file_path):
    """更新された時だけ、CSVの読込と全列の文字列整形をやり直す。"""
    absolute_path = os.path.abspath(file_path)
    stat = os.stat(absolute_path)
    signature = (stat.st_mtime_ns, stat.st_size)
    return _load_normalized_csv_cached(absolute_path, signature).copy()


def render_page_header(icon, title, description=""):
    """全タブ共通の、短く読みやすいページ見出し。"""
    safe_icon = html.escape(str(icon))
    safe_title = html.escape(str(title))
    safe_description = html.escape(str(description))
    description_html = (
        f'<p class="app-page-description">{safe_description}</p>'
        if safe_description
        else ""
    )
    st.markdown(
        (
            '<section class="app-page-header">'
            f'<h1 class="app-page-title">{safe_icon} {safe_title}</h1>'
            f"{description_html}"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def get_file_separator(file_path):
    """TSVはタブ、その他はカンマで保存する。"""
    return "\t" if os.path.splitext(str(file_path))[1].lower() == ".tsv" else ","


def save_dataframe(dataframe, file_path, create_backup=False):
    """区切り文字を維持して保存し、必要なら直前のファイルを退避する。"""
    if create_backup and os.path.exists(file_path):
        backup_path = f"{file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(file_path, backup_path)
    else:
        backup_path = ""
    dataframe.to_csv(
        file_path,
        index=False,
        encoding="utf-8",
        sep=get_file_separator(file_path),
    )
    _load_csv_cached.clear()
    _load_normalized_csv_cached.clear()
    return backup_path


def append_csv_rows(file_path, rows, expected_columns):
    """既存CSVの列名・列順を保ったまま行を追加する。"""
    file_existed = os.path.exists(file_path)
    if file_existed:
        existing_df = load_csv(file_path)
        columns = existing_df.columns.tolist()
    else:
        existing_df = pd.DataFrame(columns=expected_columns)
        columns = expected_columns

    new_df = pd.DataFrame(rows)
    for column in columns:
        if column not in new_df.columns:
            new_df[column] = ""
    new_df = new_df.reindex(columns=columns)

    save_dataframe(
        pd.concat([existing_df, new_df], ignore_index=True),
        file_path,
        create_backup=file_existed,
    )


def upsert_csv_row(file_path, row, expected_columns, key_columns):
    """キーが同じ行は更新し、それ以外は追加する。登録フォーム用。"""
    if os.path.exists(file_path):
        existing_df = load_csv(file_path).fillna("")
        columns = existing_df.columns.tolist()
        backup_path = f"{file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(file_path, backup_path)
    else:
        existing_df = pd.DataFrame(columns=expected_columns)
        columns = expected_columns

    for column in expected_columns:
        if column not in columns:
            columns.append(column)
    for column in columns:
        if column not in existing_df.columns:
            existing_df[column] = ""

    key_mask = pd.Series(True, index=existing_df.index)
    for key_column in key_columns:
        if key_column not in existing_df.columns:
            existing_df[key_column] = ""
        key_mask &= existing_df[key_column].astype(str) == str(row.get(key_column, ""))

    remaining_df = existing_df[~key_mask]
    new_row_df = pd.DataFrame([row])
    for column in columns:
        if column not in new_row_df.columns:
            new_row_df[column] = ""
    save_dataframe(
        pd.concat(
            [remaining_df, new_row_df.reindex(columns=columns)],
            ignore_index=True,
        ),
        file_path,
    )


def upsert_csv_rows(file_path, rows, expected_columns, key_columns):
    """複数行を一度に追加・更新する。大量入力でもバックアップと保存は一回だけ。"""
    if not rows:
        return 0
    if os.path.exists(file_path):
        existing_df = load_csv(file_path).fillna("")
        columns = existing_df.columns.tolist()
    else:
        existing_df = pd.DataFrame(columns=expected_columns)
        columns = list(expected_columns)

    for column in expected_columns:
        if column not in columns:
            columns.append(column)
    for column in columns:
        if column not in existing_df.columns:
            existing_df[column] = ""

    incoming_df = pd.DataFrame(rows).fillna("")
    for column in columns:
        if column not in incoming_df.columns:
            incoming_df[column] = ""
    incoming_df = incoming_df.reindex(columns=columns)

    if key_columns and not existing_df.empty:
        existing_keys = existing_df[key_columns].astype(str).agg("\x1f".join, axis=1)
        incoming_keys = set(
            incoming_df[key_columns].astype(str).agg("\x1f".join, axis=1)
        )
        existing_df = existing_df[~existing_keys.isin(incoming_keys)]

    combined_df = pd.concat([existing_df, incoming_df], ignore_index=True)
    save_dataframe(combined_df, file_path, create_backup=os.path.exists(file_path))
    return len(incoming_df)


def unique_in_registered_order(values):
    """CSVに登場した順を保って重複だけを除く。"""
    seen = set()
    ordered_values = []
    for value in values:
        if pd.isna(value) or value in seen:
            continue
        seen.add(value)
        ordered_values.append(value)
    return ordered_values


@st.cache_data(show_spinner=False, max_entries=DERIVED_CACHE_MAX_ENTRIES)
def build_song_series_map(song_album_df, album_master_df, song_album_col, album_name_col, series_col):
    """アルバム名の略称・正式名の違いを許容して、楽曲からシリーズを引ける辞書を作る。"""
    if any(frame.empty for frame in [song_album_df, album_master_df]):
        return {}
    if not all([song_album_col, album_name_col, series_col]):
        return {}

    master_rows = []
    for album_name, raw_series_name in zip(
        album_master_df[album_name_col],
        album_master_df[series_col],
    ):
        album_key = make_search_key(str(album_name))
        series_name = clean_text(str(raw_series_name))
        if album_key and series_name and series_name != "nan":
            master_rows.append((album_key, series_name))
    exact_series_map = dict(master_rows)

    song_to_series = {}
    song_keys = (
        song_album_df["_song_search_key"]
        if "_song_search_key" in song_album_df.columns
        else song_album_df["楽曲名"].map(make_search_key)
    )
    album_keys = (
        song_album_df["_album_search_key"]
        if "_album_search_key" in song_album_df.columns
        else song_album_df[song_album_col].map(make_search_key)
    )
    for song_key, album_key in zip(song_keys, album_keys):
        if not song_key or not album_key:
            continue
        matched_series = exact_series_map.get(album_key)
        if matched_series is None:
            matched_series = next(
                (
                    series_name for master_key, series_name in master_rows
                    if album_key in master_key or master_key in album_key
                ),
                None,
            )
        if matched_series:
            song_to_series[song_key] = matched_series
    return song_to_series


def normalize_radio_episode(value):
    """CSVで 104 / 104.0 のように揺れる回番号を同じ値として扱う。"""
    episode = clean_text(str(value))
    matched = re.fullmatch(r"(\d+)\.0", episode)
    return matched.group(1) if matched else episode


# 歌詞検索では、表記ゆれ・英語の関連語・表示用の強調を一か所に集約する。
# 日本語は単語境界を機械的に判定しにくいため、「単語として検索」は助詞や
# 記号に接している場合だけを対象にする、控えめで誤検出の少ない判定にしている。
LYRIC_ENGLISH_HINTS = {
    "夢": ["dream", "dreams", "dreaming"],
    "光": ["light", "lights", "shine", "shining"],
    "空": ["sky", "blue sky"],
    "未来": ["future"],
    "星": ["star", "stars", "starlight"],
    "愛": ["love", "loved", "loving"],
    "希望": ["hope", "hopeful"],
    "虹": ["rainbow"],
    "翼": ["wing", "wings"],
    "笑顔": ["smile", "smiles"],
}


def build_lyric_search_terms(keyword, include_english=False, extra_english=""):
    """検索語を重複なく返す。英語の追加語はカンマ区切りにも対応する。"""
    terms = [clean_text(keyword)] if clean_text(keyword) else []
    if include_english:
        terms.extend(LYRIC_ENGLISH_HINTS.get(clean_text(keyword), []))
    terms.extend(
        clean_text(term)
        for term in re.split(r"[,，、/]", extra_english or "")
        if clean_text(term)
    )
    return unique_in_registered_order(terms)


def lyric_contains(text, terms, match_mode="部分一致"):
    """歌詞が検索語のいずれかを含むかを判定する。"""
    lyric_text = str(text)
    if match_mode == "部分一致":
        folded = lyric_text.casefold()
        return any(term.casefold() in folded for term in terms)

    # 英語は単語境界、日本語は助詞・記号に接する形だけを「単語」とみなす。
    for term in terms:
        if re.fullmatch(r"[A-Za-z][A-Za-z' -]*", term):
            if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", lyric_text, flags=re.IGNORECASE):
                return True
        elif re.search(
            rf"(?<![一-龥々〆〤ぁ-んァ-ヶーA-Za-z0-9]){re.escape(term)}(?=$|[\s、。！？…,.!?'\"」』）\)をがにはへともでやの])",
            lyric_text,
        ):
            return True
    return False


def highlight_lyric_text(text, terms):
    """検索語だけを安全にマークアップして表示する。"""
    escaped = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for term in sorted(set(terms), key=len, reverse=True):
        if term:
            escaped = re.sub(
                re.escape(term),
                lambda match: f'<mark class="lyric-hit">{match.group(0)}</mark>',
                escaped,
                flags=re.IGNORECASE,
            )
    return escaped.replace("\n", "<br>")


def make_lyric_excerpt(lyrics, terms, radius=46):
    """最初のヒット付近を表示用に抜粋する。"""
    text = str(lyrics)
    folded = text.casefold()
    positions = [folded.find(term.casefold()) for term in terms if term.casefold() in folded]
    match_index = min(positions) if positions else 0
    start = max(0, match_index - radius)
    end = min(len(text), match_index + max([len(term) for term in terms] or [0]) + radius)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


@st.cache_data(show_spinner=False, max_entries=LYRIC_CACHE_MAX_ENTRIES)
def get_frequent_lyric_phrases(lyrics_series, limit=20):
    """助詞・語尾を除き、歌詞の内容に関わる語だけを簡易集計する。"""
    ignored_words = {
        "私", "僕", "君", "私達", "僕達", "自分", "今日", "明日", "今", "時", "事",
        "全部", "一緒", "本当", "気持", "誰", "何", "人", "日", "言葉", "手", "目", "場所", "色",
    }
    # 一文字でも歌詞検索で意味を持ちやすい語だけは残す。
    meaningful_single_kanji = {"夢", "空", "光", "愛", "星", "花", "風", "涙", "虹"}
    counts = {}

    for lyric in lyrics_series.dropna():
        text = re.sub(r"[\[\]（）()「」『』【】【：:・!！?？…]", " ", str(lyric))

        candidates = re.findall(r"[一-龥々〆〤]{1,8}", text)
        candidates += re.findall(r"[ァ-ヶー]{3,}", text)
        candidates += re.findall(r"[A-Za-z][A-Za-z'!?.-]{2,}", text)

        for word in candidates:
            word = word.strip("ー.-!?")
            if not word or word in ignored_words:
                continue
            if re.fullmatch(r"[一-龥々〆〤]", word) and word not in meaningful_single_kanji:
                continue
            counts[word] = counts.get(word, 0) + 1

    ranking = [
        {"注目語": word, "登場回数": count}
        for word, count in counts.items()
        if count >= 3
    ]
    if not ranking:
        return pd.DataFrame(columns=["注目語", "登場回数"])
    return pd.DataFrame(ranking).sort_values(["登場回数", "注目語"], ascending=[False, True]).head(limit)


def format_days_ago(days):
    if pd.isnull(days) or pd.isna(days) or days < 0:
        return "未披露 / データなし"
    days = int(days)
    years = days // 365
    remaining_days = days % 365
    months = remaining_days // 30
    days_rem = remaining_days % 30

    parts = []
    if years > 0:
        parts.append(f"{years}年")
    if months > 0 or years > 0:
        parts.append(f"{months}ヶ月")
    parts.append(f"{days_rem}日")

    time_str = "".join(parts)
    return f"{time_str}前 ({days:,} 日前)"


@lru_cache(maxsize=32768)
def get_base_song_name(song_name, include_versions=True, include_no_vocal=False):
    if not isinstance(song_name, str):
        return song_name

    unit_pattern = r"[\(（\[][^\)）\]]*(イルミネーションスターズ|アンティーカ|放課後クライマックスガールズ|アルストロメリア|ストレイライト|ノクチル|シーズ|コメティック|shhis|cometik|season)[^\)）\]]*ver[\)）\]]"
    if re.search(unit_pattern, song_name, flags=re.IGNORECASE):
        return song_name.strip()

    # Migratory Echoes はユニット名が付く版だけを別楽曲として扱う。
    # short版などは通常版に統合し、披露履歴のバージョン差分として表示する。
    migratory_unit_pattern = r"^\s*Migratory Echoes\s*[\(（\[][^\)）\]]*(イルミネーションスターズ|アンティーカ|放課後クライマックスガールズ|アルストロメリア|ストレイライト|ノクチル|シーズ|コメティック|shhis|cometik)[^\)）\]]*[\)）\]]"
    if re.search(migratory_unit_pattern, song_name, flags=re.IGNORECASE):
        return song_name.strip()

    target = song_name
    version_pattern = r"\s*[\(（\[][^\)）\]]*(short|ver|version|size|mix|edit|tv|anime|come and unite)[^\)）\]]*[\)）\]]"
    novocal_pattern = r"\s*[\(（\[][^\)）\]]*(歌唱無|歌唱なし|off vocal|instrumental|inst)[^\)）\]]*[\)）\]]"

    prev = None
    while prev != target:
        prev = target
        if include_versions:
            target = re.sub(version_pattern, "", target, flags=re.IGNORECASE)
        if include_no_vocal:
            target = re.sub(novocal_pattern, "", target, flags=re.IGNORECASE)

    if include_versions:
        target = re.sub(
            r"\s*[-–—]\s*(short|ver|version|size|mix|edit).*?$",
            "",
            target,
            flags=re.IGNORECASE,
        )

    target = re.sub(r"\s+", " ", target)
    return target.strip(" -_（(）)")


@lru_cache(maxsize=32768)
def get_catalog_song_key(song_name):
    """アルバム収録曲との照合用キー。楽曲分析の表示名は変更しない。"""
    song_name = str(song_name)
    # リミックスは通常版と別曲として扱う。
    if re.search(r"\bremix\b", song_name, flags=re.IGNORECASE):
        return make_search_key(song_name)
    song_name = re.sub(r"\s*[\(（\[][^\)）\]]*[\)）\]]", "", song_name)
    return make_search_key(song_name)


def migratory_echoes_songs_for_album(album_name, all_songs):
    """ECHOES各巻・09に対応する Migratory Echoes のユニット版を返す。"""
    album_key = make_search_key(album_name)
    album_match = re.search(r"echoes0?([1-9])", album_key, flags=re.IGNORECASE)
    if not album_match:
        return []

    echo_number = album_match.group(1)
    migratory_songs = [song for song in all_songs if str(song).lower().startswith("migratory echoes")]
    if echo_number == "9":
        return migratory_songs

    unit_keywords = {
        "1": ("イルミネーションスターズ", "illumination"),
        "2": ("アンティーカ", "antica"),
        "3": ("放課後クライマックスガールズ", "houkago", "climax"),
        "4": ("アルストロメリア", "alstroemeria"),
        "5": ("ストレイライト", "straylight"),
        "6": ("ノクチル", "noctchill"),
        "7": ("シーズ", "shhis"),
        "8": ("コメティック", "cometik"),
    }
    keywords = unit_keywords.get(echo_number, ())
    return [song for song in migratory_songs if any(keyword.lower() in str(song).lower() for keyword in keywords)]


@lru_cache(maxsize=32768)
def get_version_tag(song_name):
    if not isinstance(song_name, str):
        return "通常"
    s = song_name.lower()
    tags = []
    if "short" in s:
        tags.append("short")
    if "歌唱無" in song_name or "歌唱なし" in song_name or "off vocal" in s or "inst" in s:
        tags.append("歌唱なし")
    
    return " / ".join(tags) if tags else "通常"


@lru_cache(maxsize=32768)
def make_event_media_key(name):
    """DAY表記を外し、同一公演の共通映像を日別ページでも照合できるキーにする。"""
    normalized = clean_live_name(str(name))
    normalized = re.sub(r"\s*(?:DAY|day)\s*[0-9０-９]+.*$", "", normalized)
    return make_search_key(normalized)


def load_optional_media_csv(file_path, columns):
    """メディア用CSVが未配置でも、画面全体を止めずに読み込む。"""
    if not os.path.exists(file_path):
        return pd.DataFrame(columns=columns)
    try:
        media_df = load_normalized_csv(file_path)
        if "楽曲名" in media_df.columns:
            media_df["_song_search_key"] = media_df["楽曲名"].map(make_search_key)
        if "対象アルバム" in media_df.columns:
            media_df["_album_search_key"] = media_df["対象アルバム"].map(make_search_key)
        if "対象公演" in media_df.columns:
            media_df["_event_search_keys"] = media_df["対象公演"].map(
                lambda value: "\x1f".join(
                    make_event_media_key(name)
                    for name in str(value).split(";")
                    if clean_text(str(name))
                )
            )
        return media_df
    except Exception:
        return pd.DataFrame(columns=columns)


@st.cache_data(show_spinner=False, max_entries=SONG_MEDIA_CACHE_MAX_ENTRIES)
def build_song_media_options(
    song_name,
    audio_draft_df,
    audio_variants_df,
    video_variants_df,
    album_name="",
    contextual_media_df=None,
):
    """選択曲に紐づく公式YouTubeの音源・MVを、重複なく選択肢にする。"""
    song_key = make_search_key(song_name)
    options = []
    seen_urls = set()
    contextual_match_found = False

    def add_option(kind, label, url):
        url = str(url).strip()
        if not url or url == "nan" or url in seen_urls:
            return
        seen_urls.add(url)
        options.append({"種別": kind, "表示": label, "URL": url})

    if contextual_media_df is not None and not contextual_media_df.empty and {"楽曲名", "対象アルバム", "YouTube_URL"}.issubset(contextual_media_df.columns):
        selected_album_key = make_search_key(album_name)
        if str(song_name).lower().startswith("migratory echoes") and selected_album_key:
            contextual_song_keys = (
                contextual_media_df["_song_search_key"]
                if "_song_search_key" in contextual_media_df.columns
                else contextual_media_df["楽曲名"].map(make_search_key)
            )
            contextual_album_keys = (
                contextual_media_df["_album_search_key"]
                if "_album_search_key" in contextual_media_df.columns
                else contextual_media_df["対象アルバム"].map(make_search_key)
            )
            matched = contextual_media_df[
                (contextual_song_keys == song_key)
                & contextual_album_keys.map(
                    lambda album_key: album_key in selected_album_key
                    or selected_album_key in album_key
                )
            ]
            for row in matched.to_dict("records"):
                contextual_match_found = True
                add_option("公式音源", f"公式音源｜{row['対象アルバム']}", row["YouTube_URL"])

    # Migratory Echoes は収録盤ごとの音源が最優先。ECHOES 09 の
    # 汎用音源で上書きしないよう、文脈一致時は通常音源候補を追加しない。
    if not contextual_match_found and not audio_draft_df.empty and {"楽曲名", "公式音源_URL"}.issubset(audio_draft_df.columns):
        draft_song_keys = (
            audio_draft_df["_song_search_key"]
            if "_song_search_key" in audio_draft_df.columns
            else audio_draft_df["楽曲名"].map(make_search_key)
        )
        matched = audio_draft_df[draft_song_keys == song_key]
        for row in matched.to_dict("records"):
            for index, url in enumerate(str(row["公式音源_URL"]).split(";"), start=1):
                suffix = "" if index == 1 else f" {index}"
                add_option("公式音源", f"公式音源{suffix}", url)

    if not contextual_match_found and not audio_variants_df.empty and {"楽曲名", "種別", "バージョン表示", "YouTube_URL"}.issubset(audio_variants_df.columns):
        audio_song_keys = (
            audio_variants_df["_song_search_key"]
            if "_song_search_key" in audio_variants_df.columns
            else audio_variants_df["楽曲名"].map(make_search_key)
        )
        matched = audio_variants_df[audio_song_keys == song_key]
        for row in matched.to_dict("records"):
            add_option(str(row["種別"]), f"{row['種別']}｜{row['バージョン表示']}", row["YouTube_URL"])

    if not video_variants_df.empty and {"楽曲名", "種別", "バージョン表示", "YouTube_URL"}.issubset(video_variants_df.columns):
        video_song_keys = (
            video_variants_df["_song_search_key"]
            if "_song_search_key" in video_variants_df.columns
            else video_variants_df["楽曲名"].map(make_search_key)
        )
        matched = video_variants_df[video_song_keys == song_key]
        for row in matched.to_dict("records"):
            add_option(str(row["種別"]), f"{row['種別']}｜{row['バージョン表示']}", row["YouTube_URL"])

    return options


@st.cache_data(show_spinner=False, max_entries=MEDIA_CACHE_MAX_ENTRIES)
def build_album_preview_options(album_name, album_preview_df):
    """選択中の収録アルバムに紐づく試聴動画だけを返す。"""
    if not album_name or album_preview_df is None or album_preview_df.empty:
        return []
    if not {"アルバム", "種別", "YouTube_URL"}.issubset(album_preview_df.columns):
        return []

    selected_album_key = make_search_key(album_name)
    preview_album_keys = (
        album_preview_df["_album_search_key"]
        if "_album_search_key" in album_preview_df.columns
        else album_preview_df["アルバム"].map(make_search_key)
    )
    matched_previews = album_preview_df[
        preview_album_keys.map(
            lambda preview_key: preview_key in selected_album_key
            or selected_album_key in preview_key
        )
    ]
    options, seen_urls = [], set()
    for row in matched_previews.to_dict("records"):
        url = str(row["YouTube_URL"]).strip()
        if not url or url == "nan" or url in seen_urls:
            continue
        seen_urls.add(url)
        kind = str(row["種別"])
        options.append({"種別": kind, "表示": f"{kind}｜{row['アルバム']}", "URL": url})
    return options


@st.cache_data(show_spinner=False, max_entries=MEDIA_CACHE_MAX_ENTRIES)
def build_event_media_options(event_name, live_digest_df, xr_intro_df, ap_stream_df=None):
    """公演名が日別表記でも、共通の公式映像を見つけられるようにする。"""
    selected_key = make_event_media_key(event_name)
    options = []
    seen_urls = set()

    def add_rows(media_df):
        if media_df.empty or not {"対象公演", "種別", "YouTube_URL"}.issubset(media_df.columns):
            return
        for row in media_df.to_dict("records"):
            stored_target_keys = str(row.get("_event_search_keys", "")).strip()
            target_keys = (
                stored_target_keys.split("\x1f")
                if stored_target_keys and stored_target_keys != "nan"
                else [
                    make_event_media_key(name)
                    for name in str(row["対象公演"]).split(";")
                    if clean_text(str(name))
                ]
            )
            if not any(
                target_key in selected_key or selected_key in target_key
                for target_key in target_keys if target_key
            ):
                continue
            url = str(row["YouTube_URL"]).strip()
            if not url or url == "nan" or url in seen_urls:
                continue
            seen_urls.add(url)
            kind = str(row["種別"])
            options.append({
                "種別": kind,
                "表示": f"{kind} #{len(options) + 1}",
                "URL": url,
            })

    add_rows(live_digest_df)
    add_rows(xr_intro_df)
    if ap_stream_df is not None:
        add_rows(ap_stream_df)
    return options


@st.cache_data(show_spinner=False, max_entries=MEDIA_CACHE_MAX_ENTRIES)
def find_event_social_links(event_name, social_links_df):
    """公演の日別表記を吸収し、公式告知・ビジュアルへのリンクを返す。"""
    if social_links_df.empty or not {"対象公演", "種別", "URL"}.issubset(social_links_df.columns):
        return []
    selected_key = make_event_media_key(event_name)
    links = []
    seen_urls = set()
    for row in social_links_df.to_dict("records"):
        target_key = make_event_media_key(row["対象公演"])
        url = str(row["URL"]).strip()
        if (
            not target_key
            or not url.startswith(("https://x.com/", "https://twitter.com/"))
            or url in seen_urls
            or not (target_key in selected_key or selected_key in target_key)
        ):
            continue
        seen_urls.add(url)
        links.append({"種別": str(row["種別"]), "URL": url})
    return links


def render_analysis_chart(fig, key=None, height=None):
    """Render a chart with Plotly's built-in PNG export button enabled."""
    if height:
        fig.update_layout(height=height)
    st.plotly_chart(
        fig,
        use_container_width=True,
        key=key,
        config={
            "displaylogo": False,
            "toImageButtonOptions": {
                "format": "png",
                "filename": "shiny_colors_analysis",
                "scale": 2,
            },
        },
    )
    st.caption("グラフ右上のカメラボタンから、PNG画像として保存できます。")


@st.cache_data(show_spinner=False, max_entries=MEDIA_CACHE_MAX_ENTRIES)
def find_event_official_site_urls(event_name, official_site_df):
    """DAY別の公演名から、共通の公式イベントページを見つける。"""
    if official_site_df.empty or not {"対象公演", "公式サイトURL"}.issubset(official_site_df.columns):
        return []
    selected_key = make_event_media_key(event_name)
    urls = []
    for row in official_site_df.to_dict("records"):
        stored_target_keys = str(row.get("_event_search_keys", "")).strip()
        target_keys = stored_target_keys.split("\x1f") if stored_target_keys else []
        if not target_keys:
            target_keys = [make_event_media_key(str(row.get("対象公演", "")))]
        if any(target_key and (target_key in selected_key or selected_key in target_key) for target_key in target_keys):
            url = clean_text(str(row.get("公式サイトURL", "")))
            if url.startswith(("https://", "http://")) and url not in urls:
                urls.append(url)
    return urls


def render_compact_youtube(url, title="公式YouTube", compact=True):
    """楽曲ページはコンパクトに、公演ページは大きく公式動画を埋め込む。"""
    match = re.search(
        r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|live/|embed/))([A-Za-z0-9_-]{11})",
        str(url),
    )
    if not match:
        st.link_button("YouTubeで開く", url)
        return

    video_id = match.group(1)
    safe_title = str(title).replace("&", "&amp;").replace("\"", "&quot;")
    frame_style = (
        "width:min(100%, 320px); aspect-ratio:16/9; margin:0.25rem 0 0.5rem;"
        if compact else "width:100%; max-width:960px; aspect-ratio:16/9; margin:0.5rem 0 0.75rem;"
    )
    frame_height = 198 if compact else 570
    components.html(
        f"""
        <div style="{frame_style}">
          <iframe
            src="https://www.youtube-nocookie.com/embed/{video_id}"
            title="{safe_title}"
            style="width:100%; height:100%; border:0; border-radius:12px; box-shadow:0 8px 18px rgba(45,40,100,0.18);"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowfullscreen>
          </iframe>
        </div>
        """,
        height=frame_height,
    )


# ------------------------------------------
# データ読み込み処理
# ------------------------------------------
if os.path.exists(SETLIST_FILE):
    df = load_normalized_csv(SETLIST_FILE)
    if PUBLIC_MODE and "楽曲名" in df.columns:
        # 公開版では、セットリストではないトークのみの記録を全タブから除外する。
        df = df[~df["楽曲名"].astype(str).str.contains("トークのみ", na=False)].copy()

    live_col_name = next(
        (
            c
            for c in df.columns
            if any(k in c for k in ["公演", "ライブ", "イベント", "ツアー"])
        ),
        None,
    )
    if live_col_name:
        df[live_col_name] = df[live_col_name].apply(clean_live_name)
        df["live_search_key"] = df[live_col_name].map(make_search_key)

    if os.path.exists(EVENT_MASTER_FILE):
        event_df = load_normalized_csv(EVENT_MASTER_FILE)
        e_live_col = next(
            (
                c
                for c in event_df.columns
                if "公演" in c or "イベント" in c or "ライブ" in c
            ),
            None,
        )
        e_type_col = next(
            (
                c
                for c in event_df.columns
                if "区分" in c or "種別" in c or "タイプ" in c
            ),
            None,
        )

        if e_live_col and e_type_col:
            event_df[e_live_col] = event_df[e_live_col].apply(clean_live_name)
            event_df["live_search_key"] = event_df[e_live_col].apply(
                make_search_key
            )
            event_map = (
                event_df.drop_duplicates("live_search_key")
                .set_index("live_search_key")[e_type_col]
                .to_dict()
            )
            df["公演区分"] = df["live_search_key"].map(event_map).fillna("未設定")
    else:
        df["公演区分"] = "未設定"

    if "公演区分" not in df.columns:
        df["公演区分"] = "未設定"

    # 公演は複数の区分に属する場合があるため、表示用の区分と絞り込み用の区分を分ける。
    # events.csv では複数区分を「XR|合同」のように | で記載する。
    def split_event_categories(value):
        categories = [
            category.strip()
            for category in re.split(r"[|｜]", str(value))
            if category.strip()
        ]
        return categories or ["未設定"]

    df["公演区分フィルター"] = df["公演区分"].apply(split_event_categories)
    df["公演区分"] = df["公演区分フィルター"].apply("・".join)

    idol_df = pd.DataFrame()
    cast_list = []
    idol_list = []
    cast_to_idol_map = {}
    idol_to_cast_map = {}
    idol_to_unit_map = {}
    idol_to_groups_map = {}
    group_member_map_by_column = {}

    if os.path.exists(IDOL_MASTER_FILE):
        idol_df = load_normalized_csv(IDOL_MASTER_FILE)

        char_col = next(
            (c for c in idol_df.columns if "キャラ" in c or "アイドル" in c), None
        )
        cast_col = next(
            (c for c in idol_df.columns if "キャスト" in c or "声優" in c), None
        )
        unit_col_m = next(
            (c for c in idol_df.columns if "ユニット" in c), None
        )
        member_group_columns = [
            c for c in [
                "既存ユニット",
                "PJ: REFRAC7IONS",
                "Team.",
                "-Master ShowPiece-",
                "ハロウィン",
            ] if c in idol_df.columns
        ]
        if unit_col_m and unit_col_m not in member_group_columns:
            member_group_columns.append(unit_col_m)

        if char_col and cast_col:
            for row in idol_df.to_dict("records"):
                ch, ca = str(row[char_col]), str(row[cast_col])
                un = str(row[unit_col_m]) if unit_col_m and pd.notnull(row[unit_col_m]) else ""
                groups = set()
                for group_col in member_group_columns:
                    group = str(row[group_col]) if pd.notnull(row[group_col]) else ""
                    if group and group != "nan":
                        groups.add(group)
                        group_member_map_by_column.setdefault(group_col, {})[ch] = group
                if ch and ch != "nan":
                    idol_list.append(ch)
                    if un: idol_to_unit_map[ch] = un
                    if groups: idol_to_groups_map[ch] = groups
                if ca and ca != "nan":
                    for sub_ca in re.split(r"[;；]", ca):
                        if sub_ca.strip():
                            cast_list.append(sub_ca.strip())
                            cast_to_idol_map[sub_ca.strip()] = ch
                            if un: idol_to_unit_map[sub_ca.strip()] = un
                            if groups: idol_to_groups_map[sub_ca.strip()] = groups
                            for group_col in member_group_columns:
                                group = str(row[group_col]) if pd.notnull(row[group_col]) else ""
                                if group and group != "nan":
                                    group_member_map_by_column.setdefault(group_col, {})[sub_ca.strip()] = group
                if ch and ca:
                    idol_to_cast_map[ch] = ca

    cast_list = unique_in_registered_order(cast_list)
    idol_list = unique_in_registered_order(idol_list)
    group_to_casts_map = {}
    for cast_name in cast_list:
        for group_name in idol_to_groups_map.get(cast_name, set()):
            group_to_casts_map.setdefault(group_name, []).append(cast_name)
    group_to_casts_map = {
        group_name: unique_in_registered_order(casts)
        for group_name, casts in group_to_casts_map.items()
    }

    costume_master_df = pd.DataFrame()
    costume_to_unit_map = {}
    if os.path.exists(COSTUME_MASTER_FILE):
        costume_master_df = load_normalized_csv(COSTUME_MASTER_FILE)
        
        c_name_col_m = next((c for c in costume_master_df.columns if "衣装" in c), None)
        c_unit_col_m = next((c for c in costume_master_df.columns if "ユニット" in c or "対象" in c), None)
        if c_name_col_m and c_unit_col_m:
            for r in costume_master_df.to_dict("records"):
                cn, un = str(r[c_name_col_m]), str(r[c_unit_col_m])
                if cn and cn != "nan" and un and un != "nan":
                    costume_to_unit_map[cn] = un

    song_album_df = pd.DataFrame()
    album_registered_songs = set()
    if os.path.exists(SONG_ALBUM_FILE):
        song_album_df = load_normalized_csv(SONG_ALBUM_FILE)

        if "楽曲名" in song_album_df.columns:
            song_album_df["_song_search_key"] = song_album_df["楽曲名"].map(
                make_search_key
            )
            album_registered_songs = set(
                song_album_df["_song_search_key"].dropna().unique()
            )
        song_album_name_col = next(
            (column for column in song_album_df.columns if "アルバム" in column or "CD" in column),
            None,
        )
        if song_album_name_col:
            song_album_df["_album_search_key"] = song_album_df[
                song_album_name_col
            ].map(make_search_key)

    album_master_df = pd.DataFrame()
    if os.path.exists(ALBUM_MASTER_FILE):
        album_master_df = load_normalized_csv(ALBUM_MASTER_FILE)
        album_master_name_col = next(
            (column for column in album_master_df.columns if "アルバム" in column or "CD" in column),
            None,
        )
        if album_master_name_col:
            album_master_df["_album_search_key"] = album_master_df[
                album_master_name_col
            ].map(make_search_key)

    # 公式ディスコグラフィーから取得したジャケットの対応表
    album_jacket_map = {}
    jacket_path_by_file_name = {}
    if os.path.exists(JACKET_MAP_FILE) and os.path.isdir(JACKET_DIR):
        jacket_master_df = load_normalized_csv(JACKET_MAP_FILE)
        jacket_file_names = {}
        jacket_manifest_path = os.path.join(JACKET_DIR, "manifest.json")
        if os.path.exists(jacket_manifest_path):
            with open(jacket_manifest_path, encoding="utf-8") as manifest_file:
                jacket_manifest = json.load(manifest_file)
            for asset in jacket_manifest.get("assets", []):
                original_name = clean_text(str(asset.get("name", "")))
                saved_name = os.path.basename(str(asset.get("path", "")))
                if original_name and saved_name:
                    jacket_file_names[original_name] = saved_name

        if {"アルバム名", "ジャケット画像ファイル"}.issubset(jacket_master_df.columns):
            for jacket_row in jacket_master_df.to_dict("records"):
                official_name = clean_text(str(jacket_row["アルバム名"]))
                original_image_name = clean_text(str(jacket_row["ジャケット画像ファイル"]))
                image_name = jacket_file_names.get(original_image_name, original_image_name)
                image_path = os.path.join(JACKET_DIR, image_name)
                if official_name and official_name != "nan" and os.path.exists(image_path):
                    album_jacket_map[make_search_key(official_name)] = image_path
                    jacket_path_by_file_name[original_image_name] = image_path

        # songs_albums.csv の短いアルバム名と公式ディスコグラフィーの表記差を吸収する。
        # 画像は既存の release_jackets.csv / album_jackets をそのまま利用する。
        album_jacket_aliases = {
            "Synse-Side 01": "LACM-24244.jpg",
            "Synse-Side 02": "LACM-24245.jpg",
            "Synse-Side 03": "LACM-24246.jpg",
            "アニメ ツバサグラビティ": "LACM-24508.jpg",
            "アニメ プリズムフレア": "LACM-24580.jpg",
            "アニメ Happy Surprise Trick!": "LACA-25127-1.jpg",
            "アニメ Over the prism": "LACA-25138.jpg",
            '"円環 -Halo around-" 01': "LACM-24701.jpg",
            '"円環 -Halo around-" 02': "LACM-24702.jpg",
            '"円環 -Halo around-" 03': "LACM-24703.jpg",
            '"円環 -Halo around-" 04': "LACM-24704.jpg",
        }
        for alias_name, image_file_name in album_jacket_aliases.items():
            image_path = jacket_path_by_file_name.get(image_file_name)
            if image_path:
                album_jacket_map[make_search_key(alias_name)] = image_path

    # 同一アルバム内で曲ごとにジャケットを変えたい場合の任意マスタ。
    song_jacket_map = {}
    if os.path.exists(SONG_JACKET_FILE) and jacket_path_by_file_name:
        song_jacket_df = load_normalized_csv(SONG_JACKET_FILE).fillna("")
        required_song_jacket_columns = {"楽曲名", "アルバム", "ジャケット画像ファイル"}
        if required_song_jacket_columns.issubset(song_jacket_df.columns):
            for song_jacket_row in song_jacket_df.to_dict("records"):
                image_file_name = clean_text(str(song_jacket_row["ジャケット画像ファイル"]))
                # ジャケットはすべてローカル保存した画像だけを表示する。
                image_path = jacket_path_by_file_name.get(image_file_name)
                if not image_path and image_file_name:
                    local_image_path = os.path.join(JACKET_DIR, image_file_name)
                    if os.path.exists(local_image_path):
                        image_path = local_image_path
                if image_path:
                    song_jacket_map[
                        (make_search_key(song_jacket_row["楽曲名"]), make_search_key(song_jacket_row["アルバム"]))
                    ] = image_path

    def get_album_jacket_path(album_name):
        album_key = make_search_key(album_name)
        if album_key in album_jacket_map:
            return album_jacket_map[album_key]
        for official_key, image_path in album_jacket_map.items():
            if album_key and (album_key in official_key or official_key in album_key):
                return image_path
        return None

    def get_song_jacket_path(song_name, album_name):
        """曲別ジャケットがあれば最優先し、なければアルバム共通ジャケットを返す。"""
        exact_key = (make_search_key(song_name), make_search_key(album_name))
        if exact_key in song_jacket_map:
            return song_jacket_map[exact_key]
        return get_album_jacket_path(album_name)

    # 歌詞データは、先頭の連番列や空列を自動で無視して使用する
    lyrics_df = pd.DataFrame(columns=["楽曲名", "歌詞"])
    if not PUBLIC_MODE and os.path.exists(LYRICS_FILE):
        raw_lyrics_df = load_normalized_csv(LYRICS_FILE)
        lyrics_song_col = next((c for c in raw_lyrics_df.columns if "楽曲名" in c), None)
        lyrics_text_col = next((c for c in raw_lyrics_df.columns if "歌詞" in c), None)

        if lyrics_song_col and lyrics_text_col:
            lyric_metadata_cols = [
                c for c in ["アルバム", "リリース日", "歌唱者"]
                if c in raw_lyrics_df.columns
            ]
            lyrics_df = raw_lyrics_df[[lyrics_song_col, lyrics_text_col, *lyric_metadata_cols]].copy()
            lyrics_df = lyrics_df.rename(
                columns={lyrics_song_col: "楽曲名", lyrics_text_col: "歌詞"}
            )
            lyrics_df = lyrics_df.dropna(subset=["楽曲名", "歌詞"])
            lyrics_df["楽曲名"] = lyrics_df["楽曲名"].apply(clean_text)
            lyrics_df["歌詞"] = lyrics_df["歌詞"].astype(str).str.strip()
            lyrics_df = lyrics_df[lyrics_df["歌詞"] != ""]
            lyrics_df["search_key"] = lyrics_df["楽曲名"].map(make_search_key)
            lyrics_df = lyrics_df.drop_duplicates(subset=["search_key"], keep="first")

    # キャスト参加履歴（画像の色分けをCSV化した補助データ）
    attendance_df = pd.DataFrame()
    if os.path.exists(ATTENDANCE_FILE):
        attendance_df = load_normalized_csv(ATTENDANCE_FILE)
        required_attendance_columns = {"公演名", "日程", "キャスト", "参加状況"}
        if not required_attendance_columns.issubset(attendance_df.columns):
            attendance_df = pd.DataFrame()

    # 公式生配信・番組履歴（任意の補助データ）
    broadcast_df = pd.DataFrame()
    if not PUBLIC_MODE and os.path.exists(BROADCAST_FILE):
        broadcast_df = load_normalized_csv(BROADCAST_FILE)
        if "初回放送" in broadcast_df.columns:
            broadcast_df["初回放送_dt"] = pd.to_datetime(
                broadcast_df["初回放送"].astype(str).str.replace(r"\([^)]*\)", "", regex=True),
                errors="coerce",
            )

    # カード実装履歴（任意の補助データ）
    card_df = pd.DataFrame()
    if not PUBLIC_MODE and os.path.exists(CARD_FILE):
        card_df = load_normalized_csv(CARD_FILE)
        if "実装日" in card_df.columns:
            card_df["実装日_dt"] = pd.to_datetime(card_df["実装日"], errors="coerce")
        else:
            card_df = pd.DataFrame()

    # オーディオコメンタリー担当（横持ちCSVをキャスト×公演の行データへ変換）
    commentary_rows = []
    if not PUBLIC_MODE:
        for commentary_file, commentary_type in [
            (COMMENTARY_BD_FILE, "Blu-ray版"),
            (COMMENTARY_STREAM_FILE, "配信版"),
        ]:
            if os.path.exists(commentary_file):
                raw_commentary_df = load_csv(commentary_file).fillna("")
                for commentary_row in raw_commentary_df.to_dict("records"):
                    row_values = list(commentary_row.values())
                    if not row_values:
                        continue
                    commentary_cast = clean_text(str(row_values[0]))
                    for shorthand_event in row_values[1:]:
                        shorthand_event = clean_text(str(shorthand_event))
                        if commentary_cast and shorthand_event and shorthand_event != "nan":
                            commentary_rows.append({
                                "キャスト": commentary_cast,
                                "公演略称": shorthand_event,
                                "種別": commentary_type,
                            })
    commentary_df = pd.DataFrame(commentary_rows)

    # シャニラジ出演履歴（キャストごとの横持ち回番号一覧を行データへ変換）
    radio_rows = []
    if not PUBLIC_MODE and os.path.exists(RADIO_APPEARANCE_FILE):
        raw_radio_df = load_csv(RADIO_APPEARANCE_FILE).fillna("")
        radio_cast_aliases = {"菅沼千沙": "菅沼千紗"}
        for radio_row in raw_radio_df.to_dict("records"):
            radio_values = list(radio_row.values())
            if len(radio_values) < 2:
                continue
            radio_cast = radio_cast_aliases.get(clean_text(str(radio_values[1])), clean_text(str(radio_values[1])))
            for episode_value in radio_values[2:]:
                episode_text = normalize_radio_episode(episode_value)
                if radio_cast and episode_text and episode_text != "nan":
                    radio_rows.append({"キャスト": radio_cast, "出演回": episode_text})
    radio_appearance_df = pd.DataFrame(radio_rows).drop_duplicates()

    # シャニラジ各回の放送日・内容。フルサイズの重複行（#で始まる行）は読み飛ばす。
    radio_episode_rows = []
    if not PUBLIC_MODE and os.path.exists(RADIO_EPISODE_FILE):
        with open(RADIO_EPISODE_FILE, encoding="utf-8", newline="") as radio_episode_file:
            for row in csv.reader(radio_episode_file, delimiter="\t"):
                if len(row) < 3:
                    continue
                episode_number = normalize_radio_episode(row[0])
                if not re.fullmatch(r"\d+", episode_number):
                    continue
                radio_episode_rows.append({
                    "出演回": episode_number,
                    "放送内容": clean_text(row[1]),
                    "初回放送": clean_text(row[2]),
                })
    radio_episode_df = pd.DataFrame(radio_episode_rows)
    if not radio_episode_df.empty:
        radio_episode_df = radio_episode_df.drop_duplicates("出演回")
    if not radio_episode_df.empty:
        radio_episode_df["初回放送_dt"] = pd.to_datetime(
            radio_episode_df["初回放送"].astype(str).str.replace(r"\([^)]*\)", "", regex=True),
            errors="coerce",
        )

    radio_clip_df = load_optional_media_csv(
        YOUTUBE_RADIO_CLIP_FILE,
        ["出演回", "YouTube_URL"],
    ) if not PUBLIC_MODE else pd.DataFrame()
    if not radio_clip_df.empty:
        radio_clip_df["出演回"] = radio_clip_df["出演回"].map(normalize_radio_episode)

    youtube_unit_pv_df = load_optional_media_csv(
        YOUTUBE_UNIT_PV_FILE,
        ["対象", "区分", "YouTube_URL"],
    ) if not PUBLIC_MODE else pd.DataFrame()
    youtube_anniversary_pv_df = load_optional_media_csv(
        YOUTUBE_ANNIVERSARY_PV_FILE,
        ["周年", "種別", "YouTube_URL"],
    ) if not PUBLIC_MODE else pd.DataFrame()

    # 公式YouTubeリンクは任意の補助データ。未配置時も分析機能は通常どおり動作する。
    youtube_audio_draft_df = load_optional_media_csv(
        YOUTUBE_AUDIO_DRAFT_FILE,
        ["楽曲名", "公式音源_URL"],
    )
    youtube_audio_variants_df = load_optional_media_csv(
        YOUTUBE_AUDIO_VARIANTS_FILE,
        ["楽曲名", "種別", "バージョン表示", "YouTube_URL"],
    )
    migratory_echoes_media_df = load_optional_media_csv(
        MIGRATORY_ECHOES_MEDIA_FILE,
        ["楽曲名", "対象アルバム", "YouTube_URL"],
    )
    youtube_video_variants_df = load_optional_media_csv(
        YOUTUBE_VIDEO_VARIANTS_FILE,
        ["楽曲名", "種別", "バージョン表示", "YouTube_URL"],
    )
    youtube_album_preview_df = load_optional_media_csv(
        YOUTUBE_ALBUM_PREVIEW_FILE,
        ["アルバム", "種別", "YouTube_URL"],
    )
    youtube_live_digest_df = load_optional_media_csv(
        YOUTUBE_LIVE_DIGEST_FILE,
        ["対象公演", "種別", "YouTube_URL"],
    )
    youtube_live_ap_stream_df = load_optional_media_csv(
        YOUTUBE_LIVE_AP_STREAM_FILE,
        ["対象公演", "種別", "YouTube_URL"],
    )
    youtube_xr_intro_df = load_optional_media_csv(
        YOUTUBE_XR_INTRO_FILE,
        ["対象公演", "種別", "YouTube_URL"],
    )
    event_official_site_df = load_optional_media_csv(
        EVENT_OFFICIAL_SITE_FILE,
        ["対象公演", "公式サイトURL"],
    )
    event_social_links_df = load_optional_media_csv(
        EVENT_SOCIAL_LINKS_FILE,
        ["対象公演", "種別", "URL"],
    ) if not PUBLIC_MODE else pd.DataFrame()
    price_history_df = load_optional_media_csv(
        PRICE_HISTORY_FILE,
        ["対象名", "カテゴリ", "価格種別", "価格", "日付"],
    ) if not PUBLIC_MODE else pd.DataFrame()

    if "日付" in df.columns:
        df["日付_dt"] = pd.to_datetime(df["日付"], errors="coerce")
        df["開催年"] = df["日付_dt"].dt.year.fillna(0).astype(int)
    else:
        df["開催年"] = 0

    # ------------------------------------------
    # サイドバー設定
    # ------------------------------------------
    st.sidebar.header("⚙️ 集計・表示設定")
    if PUBLIC_MODE:
        st.sidebar.info(
            "公開版はすべての公演区分・楽曲区分を表示しています。"
            "曲名や公演名は、各ページの候補から選んで絞り込めます。"
        )
    source_files = [
        file_path
        for file_path in [
            SETLIST_FILE, EVENT_MASTER_FILE, SONG_ALBUM_FILE, CARD_FILE
        ]
        if os.path.exists(file_path)
    ]
    if source_files:
        latest_source_update = max(
            datetime.fromtimestamp(os.path.getmtime(file_path))
            for file_path in source_files
        )
        st.sidebar.caption(
            f"データ最終更新: {latest_source_update.strftime('%Y/%m/%d %H:%M')}"
        )

    # 表・選択欄の表示がOSのダークモードに引っ張られないよう、当面はライト表示に固定する。
    display_mode = "ライト"
    st.sidebar.caption("🎨 表示：ライト固定")

    if display_mode == "ダーク":
        st.markdown(
            """
            <style>
            html, body, [data-testid="stAppViewContainer"] {
                color-scheme: dark !important;
                background: linear-gradient(135deg, #161622 0%, #20203a 50%, #172b3a 100%) !important;
                color: #f5f3ff !important;
            }
            p, span, div, label, .stMarkdown, .stSelectbox label, .stRadio label {
                color: #f5f3ff !important;
            }
            [data-testid="stSidebar"] {
                background: rgba(27, 27, 43, 0.94) !important;
                border-right-color: rgba(167, 139, 250, 0.35) !important;
            }
            [data-testid="stDataFrame"],
            [data-testid="stDataFrame"] [role="grid"],
            [data-testid="stDataFrame"] [role="gridcell"],
            [data-testid="stDataFrame"] [role="columnheader"] {
                color-scheme: dark !important;
                background-color: #242438 !important;
                color: #f5f3ff !important;
                border-color: #464665 !important;
            }
            [data-testid="stDataFrame"] div,
            [data-testid="stDataFrame"] span {
                color: #f5f3ff !important;
            }
            [data-testid="stDataFrame"] [role="columnheader"] {
                background-color: #343452 !important;
                color: #ffffff !important;
            }
            div[data-baseweb="select"],
            div[data-baseweb="select"] > div,
            div[data-baseweb="popover"],
            div[data-baseweb="menu"],
            ul[role="listbox"],
            div[role="option"] {
                background-color: #2a2a40 !important;
                color: #f5f3ff !important;
            }
            div[data-baseweb="popover"] *,
            div[data-baseweb="menu"] *,
            div[role="option"] * {
                color: #f5f3ff !important;
            }
            [data-testid="stMetric"], .shiny-header {
                background: rgba(36, 36, 56, 0.92) !important;
                border-color: rgba(167, 139, 250, 0.4) !important;
            }
            .app-page-header,
            .analysis-target-card,
            [data-testid="stExpander"] {
                background: linear-gradient(120deg, rgba(36,36,58,.96), rgba(42,40,70,.94)) !important;
                border-color: rgba(167, 139, 250, 0.35) !important;
            }
            .app-page-title {
                color: #ffffff !important;
            }
            .analysis-target-title {
                color: #ffffff !important;
            }
            .app-page-description {
                color: #c7c4e8 !important;
            }
            .analysis-target-meta {
                color: #c7c4e8 !important;
            }
            [data-testid="stMetricLabel"] { color: #c4b5fd !important; }
            [data-testid="stMetricValue"] { color: #ffffff !important; }
            div.stButton > button[kind="secondary"] {
                background: #2a2a40 !important;
                color: #d8d4fe !important;
                border-color: #7567c7 !important;
            }
            .stTabs [data-baseweb="tab-list"] { background-color: #25253a !important; }
            .stTabs [data-baseweb="tab"] { color: #d8d4fe !important; }
            </style>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <style>
            :root, html, body, [data-testid="stAppViewContainer"], [data-testid="stDataFrame"] {
                color-scheme: light !important;
            }
            html, body, [data-testid="stAppViewContainer"] {
                background: linear-gradient(135deg, #ffffff 0%, #f4f0ff 35%, #e8f7ff 70%, #fff0f5 100%) !important;
                color: #2c2c54 !important;
            }
            p, span, div, label, .stMarkdown, .stSelectbox label, .stRadio label {
                color: #2c2c54 !important;
            }
            [data-testid="stSidebar"] {
                background: rgba(255, 255, 255, 0.94) !important;
                border-right-color: rgba(123, 92, 255, 0.22) !important;
            }
            [data-testid="stDataFrame"] [role="grid"],
            [data-testid="stDataFrame"] [role="gridcell"],
            [data-testid="stDataFrame"] [role="columnheader"] {
                background-color: #ffffff !important;
                color: #2c2c54 !important;
                border-color: #deddf0 !important;
            }
            [data-testid="stDataFrame"] [role="columnheader"] {
                background-color: #f4f0ff !important;
            }
            [data-testid="stDataFrame"] div,
            [data-testid="stDataFrame"] span {
                color: #2c2c54 !important;
            }
            [data-testid="stDataFrame"] {
                --gdg-bg-cell: #ffffff !important;
                --gdg-bg-cell-medium: #fbfaff !important;
                --gdg-bg-header: #f4f0ff !important;
                --gdg-bg-header-has-focus: #e8e1ff !important;
                --gdg-text-dark: #2c2c54 !important;
                --gdg-text-medium: #62627d !important;
                --gdg-border-color: #deddf0 !important;
                --gdg-accent-color: #7b5cff !important;
            }
            div[data-baseweb="select"],
            div[data-baseweb="select"] > div,
            div[data-baseweb="popover"],
            div[data-baseweb="menu"],
            ul[role="listbox"],
            div[role="option"] {
                background-color: #ffffff !important;
                color: #2c2c54 !important;
            }
            div[data-baseweb="popover"] *,
            div[data-baseweb="menu"] *,
            div[role="option"] * {
                color: #2c2c54 !important;
            }
            [data-testid="stMetric"], .shiny-header {
                background: rgba(255, 255, 255, 0.92) !important;
                border-color: rgba(123, 92, 255, 0.25) !important;
            }
            .app-page-header,
            .analysis-target-card,
            [data-testid="stExpander"] {
                background: rgba(255, 255, 255, 0.9) !important;
                border-color: rgba(123, 92, 255, 0.2) !important;
            }
            .app-page-title, .analysis-target-title, [data-testid="stMetricValue"] {
                color: #2c2c54 !important;
            }
            .app-page-description, .analysis-target-meta, [data-testid="stMetricLabel"] {
                color: #62627d !important;
            }
            div.stButton > button[kind="secondary"] {
                background: #ffffff !important;
                color: #5a45d6 !important;
                border-color: #b9afe8 !important;
            }
            .stTabs [data-baseweb="tab-list"] { background-color: #ffffff !important; }
            .stTabs [data-baseweb="tab"] { color: #4b467c !important; }
            </style>
            """,
            unsafe_allow_html=True,
        )

    unify_member_names = st.sidebar.checkbox(
        "👥 キャスト名とアイドル名を同一視して集計する",
        value=True,
        key="unify_member_names"
    )

    include_versions = st.sidebar.checkbox(
        "🔄 ショート版 (short / Ver.) を同一曲として合算する",
        value=True,
        key="include_versions"
    )

    include_no_vocal = st.sidebar.checkbox(
        "🔇 歌唱なしを同一曲として合算する",
        value=False,
        key="include_no_vocal"
    )

    if PUBLIC_MODE:
        # 公開版は閲覧専用として固定ルールを使う。
        unify_member_names = True
        include_versions = True
        include_no_vocal = False

    if PUBLIC_MODE:
        exclude_talk_events = True
    else:
        exclude_talk_events = st.sidebar.checkbox(
            "💬 『トークのみ』等のイベントを楽曲集計から除外する",
            value=True,
            key="exclude_talk_events"
        )

    df["原曲名"] = df["楽曲名"].apply(lambda x: get_base_song_name(x, include_versions=True, include_no_vocal=True))
    df["バージョン"] = df["楽曲名"].apply(get_version_tag)
    df["集計用楽曲名"] = df["楽曲名"].apply(
        lambda x: get_base_song_name(
            x, 
            include_versions=include_versions, 
            include_no_vocal=include_no_vocal
        )
    )

    df["search_key"] = df["集計用楽曲名"].map(make_search_key)

    if os.path.exists(CATEGORY_FILE):
        cat_df = load_normalized_csv(CATEGORY_FILE)
        if "楽曲名" in cat_df.columns and "楽曲区分" in cat_df.columns:
            cat_df["search_key"] = cat_df["楽曲名"].map(make_search_key)
            cat_map = (
                cat_df.drop_duplicates("search_key")
                .set_index("search_key")["楽曲区分"]
                .to_dict()
            )

            def resolve_category(raw_name, key, current_category="未分類"):
                if key in cat_map:
                    return cat_map[key]

                raw_name = str(raw_name)
                stripped_name = re.sub(r"[\(（\[].*?[\)）\]]", "", raw_name)
                stripped_name = re.sub(r"[-–—].*?$", "", stripped_name).strip()
                stripped_key = make_search_key(stripped_name)
                if stripped_key in cat_map:
                    return cat_map[stripped_key]

                for master_key, category in cat_map.items():
                    if master_key and (key.startswith(master_key) or master_key.startswith(key)):
                        return category

                return current_category if clean_text(str(current_category)) else "未分類"

            current_categories = (
                df["楽曲区分"]
                if "楽曲区分" in df.columns
                else pd.Series("未分類", index=df.index)
            )
            df["楽曲区分"] = [
                resolve_category(raw_name, key, current_category)
                for raw_name, key, current_category in zip(
                    df["楽曲名"],
                    df["search_key"],
                    current_categories,
                )
            ]
        elif "楽曲区分" not in df.columns:
            df["楽曲区分"] = "未分類"
    else:
        df["楽曲区分"] = "未分類"

    # 個人名義の出演は「外部」公演の中でも別扱いにし、通常のライブ記録には
    # 含めない。現状は衣装欄に個人アーティスト活動として登録された記録を対象にする。
    individual_artist_mask = (
        df["公演区分"].astype(str).eq("外部")
        & df.get("衣装", pd.Series("", index=df.index)).astype(str).str.contains("個人アーティスト", na=False)
    )
    include_individual_artist_activity = st.sidebar.checkbox(
        "🎙️ 個人アーティストとしての歌唱を含める",
        value=False,
        key="include_individual_artist_activity",
        help="キャストが個人名義のアーティストとして歌唱した、シャイニーカラーズ楽曲の記録を含めます。",
    )
    if PUBLIC_MODE:
        include_individual_artist_activity = False
    if not include_individual_artist_activity:
        df = df.loc[~individual_artist_mask].copy()

    # サイドバーフィルター適用前の全履歴（前回披露日の計算に使用）
    full_analysis_df = df.copy()

    st.sidebar.markdown("---")

    # 公演区分フィルター
    st.sidebar.subheader("🏟️ 公演区分フィルター")
    all_event_types = unique_in_registered_order(
        [
            category
            for categories in df["公演区分フィルター"]
            for category in categories
        ]
    )

    if "selected_event_types" not in st.session_state:
        st.session_state.selected_event_types = set(all_event_types)
    else:
        st.session_state.selected_event_types &= set(all_event_types)

    event_filter_actions = st.sidebar.columns(2)
    if event_filter_actions[0].button(
        "すべて選択",
        key="select_all_event_types",
        use_container_width=True,
    ):
        st.session_state.selected_event_types = set(all_event_types)
        st.rerun()
    if event_filter_actions[1].button(
        "外部を除く",
        key="exclude_external_event_types",
        use_container_width=True,
    ):
        non_external_event_types = {
            event_type
            for event_type in all_event_types
            if event_type not in {"外部"}
        }
        st.session_state.selected_event_types = (
            non_external_event_types or set(all_event_types)
        )
        st.rerun()
    st.sidebar.caption(
        f"{len(st.session_state.selected_event_types)} / {len(all_event_types)} 区分を選択中"
    )

    cols_e = st.sidebar.columns(2)
    for idx, etype in enumerate(all_event_types):
        is_selected = etype in st.session_state.selected_event_types
        btn_type = "primary" if is_selected else "secondary"
        if cols_e[idx % 2].button(etype, key=f"btn_e_{etype}", type=btn_type):
            if is_selected:
                if len(st.session_state.selected_event_types) > 1:
                    st.session_state.selected_event_types.remove(etype)
            else:
                st.session_state.selected_event_types.add(etype)
            st.rerun()

    if PUBLIC_MODE:
        # 公開版は絞り込みを設けず、すべての公演区分を表示する。
        st.session_state.selected_event_types = set(all_event_types)

    df = df[
        df["公演区分フィルター"].apply(
            lambda categories: set(categories).issubset(st.session_state.selected_event_types)
        )
    ]

    st.sidebar.markdown("---")

    # 楽曲区分フィルター
    st.sidebar.subheader("🎵 楽曲区分フィルター")
    all_cat_types = unique_in_registered_order(df["楽曲区分"].tolist())

    if "selected_cat_types" not in st.session_state:
        st.session_state.selected_cat_types = set(
            [c for c in all_cat_types if c not in ["外部", "合同"]]
        )
    else:
        st.session_state.selected_cat_types &= set(all_cat_types)

    default_cat_types = set(
        category for category in all_cat_types if category not in ["外部", "合同"]
    )
    category_filter_actions = st.sidebar.columns(2)
    if category_filter_actions[0].button(
        "標準に戻す",
        key="reset_category_types",
        use_container_width=True,
    ):
        st.session_state.selected_cat_types = default_cat_types
        st.rerun()
    if category_filter_actions[1].button(
        "すべて選択",
        key="select_all_category_types",
        use_container_width=True,
    ):
        st.session_state.selected_cat_types = set(all_cat_types)
        st.rerun()
    st.sidebar.caption(
        f"{len(st.session_state.selected_cat_types)} / {len(all_cat_types)} 区分を選択中"
    )

    cols_c = st.sidebar.columns(2)
    for idx, ctype in enumerate(all_cat_types):
        is_selected = ctype in st.session_state.selected_cat_types
        btn_type = "primary" if is_selected else "secondary"
        if cols_c[idx % 2].button(ctype, key=f"btn_c_{ctype}", type=btn_type):
            if is_selected:
                if len(st.session_state.selected_cat_types) > 1:
                    st.session_state.selected_cat_types.remove(ctype)
            else:
                st.session_state.selected_cat_types.add(ctype)
            st.rerun()

    if PUBLIC_MODE:
        # 公開版は絞り込みを設けず、すべての楽曲区分を表示する。
        st.session_state.selected_cat_types = set(all_cat_types)

    df = df[df["楽曲区分"].isin(st.session_state.selected_cat_types)]

    if album_registered_songs:
        df["アルバム登録済"] = df["search_key"].isin(album_registered_songs)
    else:
        df["アルバム登録済"] = True

    # バックアップ・出力
    if not PUBLIC_MODE:
        st.sidebar.markdown("---")
        st.sidebar.subheader("📥 バックアップ・出力")
    csv_buffer = io.StringIO()
    df.drop(
        columns=[
            "search_key",
            "live_search_key",
            "日付_dt",
            "アルバム登録済",
            "集計用楽曲名",
            "原曲名",
            "バージョン"
        ],
        errors="ignore",
    ).to_csv(csv_buffer, index=False, encoding="utf-8-sig")
    if not PUBLIC_MODE:
        st.sidebar.download_button(
            label="📄 最新セットリストCSVを出力",
            data=csv_buffer.getvalue(),
            file_name=f"shiny_live_songs_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

    # ------------------------------------------
    # 入口を「ホーム」にし、はじめて使う人にも分析の出発点が見える構成にする。
    # ------------------------------------------
    home_singer_col = next(
        (c for c in df.columns if "歌唱" in c or "出演" in c or "メンバー" in c),
        None,
    )
    home_costume_col = next((c for c in df.columns if "衣装" in c), None)
    if PUBLIC_MODE:
        # 公開版には、編集・歌詞本文・ローカル画像のタブをそもそも作らない。
        tab1, tab2, tab3, tab4, tab8, tab9, tab16, tab17, tab18 = st.tabs(
            [
                "📊 分析", "🎵 楽曲", "🎤 歌唱・衣装", "👗 衣装",
                "🏟️ 公演", "👥 参加履歴", "📚 分類ガイド", "🔰 使い方", "ℹ️ このサイトについて",
            ]
        )
    else:
        tab0, tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12, tab13, tab14, tab15 = st.tabs(
            [
                "✨ ホーム", "📊 分析", "🎵 楽曲", "🎤 歌唱・衣装", "👗 衣装", "🎲 ガチャ",
                "🔍 検索", "➕ データ管理", "🏟️ 公演", "👥 参加履歴", "📝 歌詞",
                "📺 番組・配信", "🗓️ カレンダー", "💴 価格推移", "📅 スケジュール予想", "🖼️ イベント画像",
            ]
        )

    if not PUBLIC_MODE:
        # TAB 0: ホーム
        with tab0:
            render_page_header(
                "✨",
                "ライブデータ・ホーム",
                "現在の絞り込み条件で全データを集計しています。設定はサイドバーからいつでも変更できます。",
            )

            home_event_count = df["公演名"].nunique() if "公演名" in df.columns else 0
            home_song_count = df["集計用楽曲名"].nunique() if "集計用楽曲名" in df.columns else 0
            home_performer_count = 0
            if home_singer_col and home_singer_col in df.columns:
                home_performer_count = len({
                    performer.strip()
                    for value in df[home_singer_col].dropna()
                    for performer in re.split(r"[;；]", str(value))
                    if performer.strip()
                })
            home_costume_count = df[home_costume_col].nunique() if home_costume_col and home_costume_col in df.columns else 0
            metric_cols = st.columns(4)
            metric_cols[0].metric("分析対象の公演", f"{home_event_count:,} 件")
            metric_cols[1].metric("披露楽曲", f"{home_song_count:,} 曲")
            metric_cols[2].metric("歌唱者", f"{home_performer_count:,} 人")
            metric_cols[3].metric("衣装", f"{home_costume_count:,} 種")

            latest_event_row = pd.DataFrame()
            if "日付_dt" in df.columns:
                latest_event_row = df.dropna(subset=["日付_dt"]).sort_values("日付_dt", ascending=False).head(1)

            overview_col, guide_col = st.columns([1.25, 1])
            with overview_col:
                st.subheader("📅 最新の記録")
                if not latest_event_row.empty:
                    latest = latest_event_row.iloc[0]
                    st.markdown(
                        f"**{latest.get('公演名', '公演名未登録')}**  \n\n"
                        f"{latest['日付_dt'].strftime('%Y/%m/%d')}"
                    )
                    latest_setlist = df[df["公演名"] == latest.get("公演名")]
                    st.caption(f"セットリスト掲載曲: {len(latest_setlist):,} 曲")
                    preview_columns = [c for c in ["曲順", "楽曲名", home_singer_col, home_costume_col] if c and c in latest_setlist.columns]
                    preview_df = latest_setlist[preview_columns].head(8).reset_index(drop=True).copy()
                    if home_singer_col and home_singer_col in preview_df.columns:
                        preview_df[home_singer_col] = (
                            preview_df[home_singer_col]
                            .fillna("")
                            .astype(str)
                            .str.replace(";", "・", regex=False)
                            .str.replace("；", "・", regex=False)
                        )
                    st.dataframe(
                        preview_df,
                        use_container_width=True,
                        height=285,
                        hide_index=True,
                    )
                else:
                    st.info("日付を含む公演データを登録すると、ここに最新公演を表示します。")
            with guide_col:
                st.subheader("🧭 まずはここから")
                st.markdown(
                    """
                    - **ランキング＆比率分析**：全体の傾向や、選んだ公演のアルバム比率を見る
                    - **楽曲詳細分析**：曲の披露履歴、収録アルバム、ジャケットを確認する
                    - **歌唱者×楽曲・衣装分析**：キャスト／アイドルごとの歌唱・衣装履歴を見る
                    - **公演セットリスト分析**：公演ごとの曲順と前回披露からの間隔を見る
                    - **楽曲・公演検索**：気になる曲や公演を探す
                    """
                )
                if not lyrics_df.empty:
                    st.info(f"歌詞データ {len(lyrics_df):,} 曲を読み込み済みです。")

            if not youtube_unit_pv_df.empty:
                st.markdown("---")
                st.subheader("🎬 ユニット・企画PV")
                home_pv_col1, home_pv_col2 = st.columns([1, 1.45])
                with home_pv_col1:
                    selected_pv_target = st.selectbox(
                        "PVを選ぶ対象:",
                        unique_in_registered_order(youtube_unit_pv_df["対象"].tolist()),
                        key="home_unit_pv_target",
                    )
                    selected_pv_rows = youtube_unit_pv_df[
                        youtube_unit_pv_df["対象"] == selected_pv_target
                    ]
                    pv_choices = {
                        f"{row['区分']} PV": row["YouTube_URL"]
                        for row in selected_pv_rows.to_dict("records")
                    }
                    selected_pv_label = st.radio(
                        "バージョン:",
                        list(pv_choices),
                        horizontal=True,
                        key="home_unit_pv_version",
                    )
                with home_pv_col2:
                    render_compact_youtube(pv_choices[selected_pv_label], selected_pv_label)

            if not youtube_anniversary_pv_df.empty:
                st.markdown("---")
                st.subheader("🎉 周年PV・記念動画")
                anniversary_col1, anniversary_col2 = st.columns([1, 1.45])
                with anniversary_col1:
                    selected_anniversary = st.selectbox(
                        "周年を選択:",
                        unique_in_registered_order(youtube_anniversary_pv_df["周年"].tolist()),
                        key="home_anniversary_pv",
                    )
                    anniversary_rows = youtube_anniversary_pv_df[
                        youtube_anniversary_pv_df["周年"] == selected_anniversary
                    ]
                    anniversary_choices = {
                        str(row["種別"]): row["YouTube_URL"]
                        for row in anniversary_rows.to_dict("records")
                    }
                    selected_anniversary_video = st.radio(
                        "動画:",
                        list(anniversary_choices),
                        horizontal=True,
                        key="home_anniversary_pv_video",
                    )
                with anniversary_col2:
                    render_compact_youtube(
                        anniversary_choices[selected_anniversary_video],
                        f"{selected_anniversary}｜{selected_anniversary_video}",
                    )

    # TAB 1: ランキング＆公演別アルバムシリーズ比率分析
    with tab1:
        render_page_header(
            "📊",
            "ランキング＆比率分析",
            "披露回数・衣装・ユニットの傾向を、同じ条件のまま比較できます。",
        )
        ranking_df = df[df["アルバム登録済"]].copy()

        if exclude_talk_events:
            ranking_df = ranking_df[~ranking_df["楽曲名"].astype(str).str.contains("トークのみ", na=False)]

        col_rank_target, col_rank_order, col_rank_unit = st.columns(3)
        with col_rank_target:
            rank_target = st.radio(
                "📍 ランキング対象:",
                ["楽曲", "衣装", "ユニット"],
                horizontal=True,
                key="rank_target"
            )
        with col_rank_order:
            rank_order = st.selectbox(
                "📐 並び替え順:",
                ["多い順", "少ない順", "前回披露から長い順"],
                key="rank_order"
            )
        with col_rank_unit:
            if rank_target == "衣装":
                costume_count_unit = st.selectbox(
                    "👗 衣装の集計方法:",
                    ["楽曲数（パフォーマンス数）", "公演数（イベント数）"],
                    key="costume_count_unit"
                )

        target_col_map = {
            "楽曲": "集計用楽曲名",
            "衣装": next((c for c in df.columns if "衣装" in c), "衣装"),
            "ユニット": next((c for c in df.columns if "ユニット" in c), "ユニット")
        }
        active_col = target_col_map[rank_target]

        if active_col in ranking_df.columns and len(ranking_df) > 0:
            today = pd.to_datetime(datetime.now().date())
            
            prep_df = ranking_df.copy()
            if rank_target in ["衣装", "ユニット"]:
                prep_df[active_col] = prep_df[active_col].astype(str).apply(lambda x: re.split(r"[;；]", x))
                prep_df = prep_df.explode(active_col)
                prep_df[active_col] = prep_df[active_col].str.strip()
                prep_df = prep_df[prep_df[active_col].astype(bool) & (prep_df[active_col] != "nan")]

            if rank_target == "衣装" and costume_count_unit == "公演数（イベント数）" and live_col_name:
                aggregated_rank = (
                    prep_df.groupby(active_col)
                    .agg(
                        披露回数=(live_col_name, "nunique"),
                        最終披露日_dt=("日付_dt", "max")
                    )
                    .reset_index()
                    .rename(columns={active_col: rank_target, "披露回数": "着用公演数"})
                )
                count_col_name = "着用公演数"
            else:
                aggregated_rank = (
                    prep_df.groupby(active_col)
                    .agg(
                        披露回数=(active_col, "count"),
                        最終披露日_dt=("日付_dt", "max")
                    )
                    .reset_index()
                    .rename(columns={active_col: rank_target})
                )
                count_col_name = "披露回数"
            
            aggregated_rank = aggregated_rank.dropna(subset=["最終披露日_dt"])
            aggregated_rank["経過日数_num"] = (today - aggregated_rank["最終披露日_dt"]).dt.days
            aggregated_rank["最終披露日"] = aggregated_rank["最終披露日_dt"].dt.strftime("%Y/%m/%d")
            aggregated_rank["前回からの経過"] = aggregated_rank["経過日数_num"].apply(format_days_ago)

            if rank_order == "多い順":
                aggregated_rank = aggregated_rank.sort_values(by=count_col_name, ascending=False)
            elif rank_order == "少ない順":
                aggregated_rank = aggregated_rank.sort_values(by=count_col_name, ascending=True)
            else:
                aggregated_rank = aggregated_rank.sort_values(by="経過日数_num", ascending=False)

            display_rank = aggregated_rank[[rank_target, count_col_name, "最終披露日", "前回からの経過"]].reset_index(drop=True)
            # 一覧では順位を最初に置くと、縦に追って比較しやすい。
            rank_value_col = count_col_name if rank_order in {"多い順", "少ない順"} else "経過日数_num"
            rank_ascending = rank_order == "少ない順"
            display_rank.insert(
                0,
                "順位",
                aggregated_rank[rank_value_col].rank(method="min", ascending=rank_ascending).astype(int).to_list(),
            )
            
            # 1〜3位の行を強調表示するハイライト関数
            def highlight_top3_rows(row):
                rank_number = int(row["順位"])
                if rank_number == 1:
                    return ['background-color: #FFF3CD; color: #856404; font-weight: bold;'] * len(row)
                elif rank_number == 2:
                    return ['background-color: #E2E3E5; color: #383D41; font-weight: bold;'] * len(row)
                elif rank_number == 3:
                    return ['background-color: #F8D7DA; color: #721C24; font-weight: bold;'] * len(row)
                return [''] * len(row)

            st.markdown("### 📋 ランキング詳細一覧")
            st.markdown(
                """
                <style>
                .ranking-table-wrap { max-height: 720px; overflow: auto; border: 1px solid rgba(102,87,217,.22); border-radius: 14px; background: rgba(255,255,255,.92); }
                .ranking-table { width: 100%; border-collapse: collapse; color: #29274f; table-layout: fixed; }
                .ranking-table th { position: sticky; top: 0; z-index: 1; background: #f7f5ff; border-bottom: 2px solid #4a4674; font-weight: 800; text-align: left; }
                .ranking-table th, .ranking-table td { padding: .62rem .72rem; border-bottom: 1px solid rgba(72,65,131,.13); vertical-align: middle; overflow-wrap: anywhere; }
                .ranking-table .rank-col { width: 4.2rem; text-align: center; font-weight: 800; }
                .ranking-table .count-col { width: 6.5rem; text-align: right; font-weight: 800; }
                .ranking-table .mobile-metric-col { display: none; }
                .ranking-table .date-col { width: 7.8rem; }
                .ranking-table .elapsed-col { width: 12rem; }
                .ranking-table tr.rank-1 td { background: #fff3cd; }
                .ranking-table tr.rank-2 td { background: #e2e3e5; }
                .ranking-table tr.rank-3 td { background: #f8d7da; }
                @media (max-width: 700px) {
                    .ranking-table-wrap { max-height: 66vh; overflow-x: hidden; }
                    .ranking-table th, .ranking-table td { padding: .56rem .48rem; font-size: .9rem; }
                    .ranking-table .rank-col { width: 2.8rem; }
                    .ranking-table .count-col { display: none; }
                    .ranking-table .mobile-metric-col { display: table-cell; width: 5.8rem; text-align: right; font-weight: 800; }
                    .ranking-table .date-col, .ranking-table .elapsed-col { display: none; }
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            ranking_rows = []
            mobile_metric_label = count_col_name if rank_order in {"多い順", "少ない順"} else "前回からの経過"
            for _, ranking_row in display_rank.iterrows():
                rank_number = int(ranking_row["順位"])
                row_class = f"rank-{rank_number}" if rank_number in {1, 2, 3} else ""
                mobile_metric = ranking_row[count_col_name] if rank_order in {"多い順", "少ない順"} else ranking_row["前回からの経過"]
                ranking_rows.append(
                    "<tr class='{row_class}'><td class='rank-col'>{rank}</td><td>{name}</td>"
                    "<td class='count-col'>{count}</td><td class='mobile-metric-col'>{mobile_metric}</td><td class='date-col'>{last_date}</td>"
                    "<td class='elapsed-col'>{elapsed}</td></tr>".format(
                        row_class=row_class,
                        rank=rank_number,
                        name=html.escape(str(ranking_row[rank_target])),
                        count=html.escape(str(ranking_row[count_col_name])),
                        mobile_metric=html.escape(str(mobile_metric)),
                        last_date=html.escape(str(ranking_row["最終披露日"])),
                        elapsed=html.escape(str(ranking_row["前回からの経過"])),
                    )
                )
            st.markdown(
                "<div class='ranking-table-wrap'><table class='ranking-table'><thead><tr>"
                f"<th class='rank-col'>順位</th><th>{html.escape(rank_target)}</th>"
                f"<th class='count-col'>{html.escape(count_col_name)}</th><th class='mobile-metric-col'>{html.escape(mobile_metric_label)}</th>"
                "<th class='date-col'>最終披露日</th><th class='elapsed-col'>前回からの経過</th>"
                "</tr></thead><tbody>" + "".join(ranking_rows) + "</tbody></table></div>",
                unsafe_allow_html=True,
            )
        else:
            st.info("該当するデータがありません。")

        st.markdown("---")
        st.subheader("💿 公演別 アルバムシリーズ比率")

        if "selected_tab1_years" not in st.session_state:
            st.session_state.selected_tab1_years = set([y for y in df["開催年"].unique() if y > 0])
        if "selected_tab1_cats" not in st.session_state:
            st.session_state.selected_tab1_cats = set([c for c in df["公演区分"].unique() if pd.notna(c)])

        available_years = sorted([y for y in df["開催年"].unique() if y > 0], reverse=True)
        st.session_state.selected_tab1_years &= set(available_years)
        available_cats = unique_in_registered_order(df["公演区分"].tolist())
        st.session_state.selected_tab1_cats &= set(available_cats)
        filter_year_col, filter_category_col = st.columns(2)
        with filter_year_col:
            st.caption("📅 開催年")
            year_actions = st.columns(2)
            if year_actions[0].button("すべて選択", key="tab1_select_all_years", use_container_width=True):
                st.session_state.selected_tab1_years = set(available_years)
                st.rerun()
            if year_actions[1].button("すべて解除", key="tab1_clear_years", use_container_width=True):
                st.session_state.selected_tab1_years = set()
                st.rerun()
            year_buttons = st.columns(5)
            for index, year in enumerate(available_years):
                is_selected = year in st.session_state.selected_tab1_years
                if year_buttons[index % len(year_buttons)].button(
                    f"{year}年",
                    key=f"tab1_year_button_{year}",
                    type="primary" if is_selected else "secondary",
                    use_container_width=True,
                ):
                    if is_selected:
                        st.session_state.selected_tab1_years.discard(year)
                    else:
                        st.session_state.selected_tab1_years.add(year)
                    st.rerun()
        with filter_category_col:
            st.caption("🏷️ 公演区分")
            category_actions = st.columns(2)
            if category_actions[0].button("すべて選択", key="tab1_select_all_categories", use_container_width=True):
                st.session_state.selected_tab1_cats = set(available_cats)
                st.rerun()
            if category_actions[1].button("すべて解除", key="tab1_clear_categories", use_container_width=True):
                st.session_state.selected_tab1_cats = set()
                st.rerun()
            category_buttons = st.columns(3)
            for index, category in enumerate(available_cats):
                is_selected = category in st.session_state.selected_tab1_cats
                if category_buttons[index % len(category_buttons)].button(
                    str(category),
                    key=f"tab1_category_button_{category}",
                    type="primary" if is_selected else "secondary",
                    use_container_width=True,
                ):
                    if is_selected:
                        st.session_state.selected_tab1_cats.discard(category)
                    else:
                        st.session_state.selected_tab1_cats.add(category)
                    st.rerun()

        filtered_live_df = df[
            (df["開催年"].isin(st.session_state.selected_tab1_years)) & 
            (df["公演区分"].isin(st.session_state.selected_tab1_cats))
        ]

        if live_col_name:
            all_lives = unique_in_registered_order(filtered_live_df[live_col_name].tolist())

            if not all_lives:
                st.warning("⚠️ 該当する条件の公演が見つかりませんでした。ボタンで選択を変更してください。")
            else:
                selected_lives = st.multiselect(
                    "分析対象の公演を選択してください (複数選択で合算表示):",
                    options=all_lives,
                    default=all_lives if PUBLIC_MODE else [all_lives[0]],
                    key="selected_lives"
                )

                if selected_lives:
                    st.markdown(
                        "<div class='analysis-target-card'>"
                        "<div class='analysis-target-label'>🎯 現在の分析対象</div>"
                        "<div class='analysis-target-title'>"
                        + "<br>".join(f"・{html.escape(str(live))}" for live in selected_lives)
                        + "</div>"
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                    live_songs_df = filtered_live_df[
                        filtered_live_df[live_col_name].isin(selected_lives)
                    ].copy()

                    if exclude_talk_events:
                        live_songs_df = live_songs_df[~live_songs_df["楽曲名"].astype(str).str.contains("トークのみ", na=False)]

                    series_col = (
                        next((c for c in album_master_df.columns if "シリーズ" in c), None)
                        if not album_master_df.empty else None
                    )
                    alb_col = (
                        next((c for c in album_master_df.columns if "アルバム" in c or "CD" in c), None)
                        if not album_master_df.empty else None
                    )
                    song_alb_col = (
                        next((c for c in song_album_df.columns if "アルバム" in c or "CD" in c), None)
                        if not song_album_df.empty else None
                    )

                    song_to_series = {}
                    if not song_album_df.empty and not album_master_df.empty and song_alb_col and alb_col and series_col:
                        song_to_series = build_song_series_map(
                            song_album_df,
                            album_master_df,
                            song_alb_col,
                            alb_col,
                            series_col,
                        )

                    live_songs_df["シリーズ"] = live_songs_df["search_key"].map(
                        lambda k: song_to_series.get(k, "その他/未登録")
                    )

                    gc1, gc2 = st.columns([1.2, 1])

                    with gc1:
                        st.subheader("📈 シリーズ別構成比 (円グラフ)")
                        series_counts = (
                            live_songs_df["シリーズ"]
                            .value_counts()
                            .reset_index()
                            .rename(
                                columns={
                                    "count": "曲数（実数）",
                                    "シリーズ": "アルバムシリーズ",
                                }
                            )
                        )

                        series_counts = series_counts.sort_values(
                            by=["曲数（実数）", "アルバムシリーズ"],
                            ascending=[False, True],
                            kind="stable",
                        ).reset_index(drop=True)
                        total_pie_sum = series_counts["曲数（実数）"].sum()

                        fig = px.pie(
                            series_counts,
                            values="曲数（実数）",
                            names="アルバムシリーズ",
                            hole=0.45,
                            color_discrete_sequence=["#7b5cff", "#51c2f0", "#ff85a1", "#a0e0ff", "#d8b4fe", "#f472b6", "#38bdf8"],
                        )

                        fig.update_traces(
                            sort=False,
                            direction="clockwise",
                            textposition="inside",
                            texttemplate="%{percent}",
                            hovertemplate="<b>%{label}</b><br>曲数: %{value}曲<br>割合: %{percent}<extra></extra>",
                        )

                        fig.update_layout(
                            margin=dict(l=16, r=16, t=20, b=105),
                            legend=dict(
                                orientation="h",
                                x=0.5,
                                y=-0.12,
                                xanchor="center",
                                yanchor="top",
                            ),
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            font_color="#2c2c54",
                            height=540
                        )

                        render_analysis_chart(fig, key="tab1_series_pie")

                    with gc2:
                        st.subheader("🔢 シリーズ別実数一覧 (絶対値)")
                        total_s_count = len(live_songs_df)
                        series_counts["割合 (%)"] = (
                            series_counts["曲数（実数）"] / total_s_count * 100
                        ).round(1).astype(str) + "%"
                        series_counts.index = series_counts.index + 1
                        st.dataframe(series_counts, use_container_width=True)

                    st.markdown("---")
                    st.subheader(f"📜 選択公演の実際のセットリスト合算 ({len(live_songs_df)} 曲)")

                    d_cols = ["search_key", "live_search_key", "日付_dt", "アルバム登録済", "集計用楽曲名", "原曲名"]
                    disp_live_df = live_songs_df.drop(
                        columns=[c for c in d_cols if c in live_songs_df.columns],
                        errors="ignore",
                    ).reset_index(drop=True)
                    disp_live_df.index = disp_live_df.index + 1
                    st.dataframe(
                        disp_live_df, 
                        use_container_width=True,
                        column_config={
                            "公演名": st.column_config.TextColumn("公演名", width="large"),
                            "楽曲名": st.column_config.TextColumn("楽曲名", width="large"),
                        }
                    )

    # TAB 2: 楽曲詳細分析
    with tab2:
        render_page_header(
            "🎵",
            "楽曲別データ分析",
            "シリーズ、アルバム、楽曲の順に絞り込み、披露履歴・収録情報・公式映像をまとめて確認できます。",
        )

        analysis_base_df = df.copy()
        if exclude_talk_events:
            analysis_base_df = analysis_base_df[~analysis_base_df["楽曲名"].astype(str).str.contains("トークのみ", na=False)]

        if "楽曲区分" in analysis_base_df.columns:
            analysis_base_df = analysis_base_df[
                analysis_base_df["楽曲区分"].isin(["オリジナル", "合同"])
            ]

        series_col = (
            next((c for c in album_master_df.columns if "シリーズ" in c), None)
            if not album_master_df.empty else None
        )
        alb_col = (
            next((c for c in album_master_df.columns if "アルバム" in c or "CD" in c), None)
            if not album_master_df.empty else None
        )
        song_alb_col = (
            next((c for c in song_album_df.columns if "アルバム" in c or "CD" in c), None)
            if not song_album_df.empty else None
        )

        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            series_list = ["すべて"]
            if series_col:
                series_list += unique_in_registered_order(album_master_df[series_col].tolist())
            sel_series = st.selectbox("1. シリーズを選択:", series_list, key="tab2_sel_series")

        with sc2:
            album_list = ["すべて"]
            if not album_master_df.empty and alb_col:
                filtered_alb_df = album_master_df.copy()
                if sel_series != "すべて" and series_col:
                    filtered_alb_df = filtered_alb_df[filtered_alb_df[series_col] == sel_series]
                album_list += unique_in_registered_order(filtered_alb_df[alb_col].tolist())
            if (
                not song_album_df.empty
                and song_alb_col
                and "アルバム未収録" in song_album_df[song_alb_col].astype(str).tolist()
                and "アルバム未収録" not in album_list
            ):
                album_list.append("アルバム未収録")
            sel_album = st.selectbox("2. アルバムを選択:", album_list, key="tab2_sel_album")

        with sc3:
            all_song_values = analysis_base_df["集計用楽曲名"].tolist()
            if not song_album_df.empty and "楽曲名" in song_album_df.columns:
                all_song_values += song_album_df["楽曲名"].dropna().astype(str).tolist()
            all_songs = unique_in_registered_order(all_song_values)
            filtered_songs = []

            if not song_album_df.empty and "楽曲名" in song_album_df.columns and song_alb_col:
                target_sa_df = song_album_df.copy()

                if sel_album != "すべて":
                    key_sel_album = make_search_key(sel_album)
                    album_key_series = (
                        target_sa_df["_album_search_key"]
                        if "_album_search_key" in target_sa_df.columns
                        else target_sa_df[song_alb_col].map(make_search_key)
                    )
                    matched_rows = target_sa_df[
                        album_key_series.map(
                            lambda album_key: key_sel_album in album_key
                            or album_key in key_sel_album
                        )
                    ]
                    filtered_songs = matched_rows["楽曲名"].unique().tolist()

                elif sel_series != "すべて" and not album_master_df.empty and series_col:
                    target_albs = album_master_df[album_master_df[series_col] == sel_series][alb_col].unique()
                    alb_keys = [make_search_key(str(a)) for a in target_albs]

                    album_key_series = (
                        target_sa_df["_album_search_key"]
                        if "_album_search_key" in target_sa_df.columns
                        else target_sa_df[song_alb_col].map(make_search_key)
                    )
                    matched_rows = target_sa_df[
                        album_key_series.map(
                            lambda album_key: any(
                                master_key in album_key or album_key in master_key
                                for master_key in alb_keys
                            )
                        )
                    ]
                    filtered_songs = matched_rows["楽曲名"].unique().tolist()

            if filtered_songs:
                # アルバムCSVは通常版だけを記録していても、ライブデータにある
                # ユニットVer.（例: Migratory Echoes）を選択肢から落とさない。
                filtered_keys = [get_catalog_song_key(s) for s in filtered_songs]
                final_song_list = [s for s in all_songs if get_catalog_song_key(s) in filtered_keys]

                # 記号や副題の表記差でキー照合が届かない場合も、同じ表示曲名を
                # 補完して楽曲ページから選べるようにする。
                for catalog_song in filtered_songs:
                    catalog_search_key = make_search_key(catalog_song)
                    for display_song in all_songs:
                        if (
                            make_search_key(display_song) == catalog_search_key
                            or get_catalog_song_key(display_song) == get_catalog_song_key(catalog_song)
                        ) and display_song not in final_song_list:
                            final_song_list.append(display_song)

                if not final_song_list:
                    final_song_list = unique_in_registered_order(filtered_songs)
            else:
                final_song_list = all_songs

            # ECHOESは各ユニット盤と09の両方に収録されるため、
            # アルバムCSVに個別登録がなくても選択肢へ補完する。
            # 個別盤では対応ユニット版のみ、ECHOES 09では全ユニット版を表示する。
            if sel_album != "すべて":
                echoes_versions = migratory_echoes_songs_for_album(sel_album, all_songs)
                if echoes_versions:
                    final_song_list = [
                        song for song in final_song_list
                        if not str(song).lower().startswith("migratory echoes")
                    ]
                    final_song_list += echoes_versions
                    final_song_list = unique_in_registered_order(final_song_list)

            selected_song = st.selectbox("3. 分析する楽曲を選択:", final_song_list, key="tab2_sel_song")

        if selected_song:
            song_df = analysis_base_df[analysis_base_df["集計用楽曲名"] == selected_song].copy()
            if "日付_dt" in song_df.columns:
                song_df = song_df.sort_values(by="日付_dt", ascending=False)

            song_media_options = build_song_media_options(
                selected_song,
                youtube_audio_draft_df,
                youtube_audio_variants_df,
                youtube_video_variants_df,
                sel_album,
                migratory_echoes_media_df,
            )

            selected_album_row = pd.DataFrame()
            if not song_album_df.empty and song_alb_col and "楽曲名" in song_album_df.columns:
                song_album_keys = (
                    song_album_df["_song_search_key"]
                    if "_song_search_key" in song_album_df.columns
                    else song_album_df["楽曲名"].map(make_search_key)
                )
                selected_album_row = song_album_df[
                    song_album_keys == make_search_key(selected_song)
                ]
            # アルバムを明示的に選んでいる場合は、その選択を最優先する。
            # 同一曲が複数盤に収録される場合でも、別盤のジャケットに切り替わらない。
            selected_album = (
                sel_album
                if sel_album != "すべて"
                else (str(selected_album_row.iloc[0][song_alb_col]) if not selected_album_row.empty else "")
            )
            selected_jacket_path = get_song_jacket_path(selected_song, selected_album) if selected_album else None
            album_preview_options = build_album_preview_options(
                selected_album,
                youtube_album_preview_df,
            )
            if PUBLIC_MODE:
                # 画像ファイルは公開せず、公式YouTubeの再生画面を主役にする。
                album_info_col, media_col = st.columns([1, 1.55])
            else:
                jacket_col, album_info_col, media_col = st.columns([1, 1.35, 1.35])
                with jacket_col:
                    if selected_jacket_path:
                        st.image(selected_jacket_path, use_container_width=True)
            with album_info_col:
                if selected_album:
                    st.subheader("💿 収録情報" if selected_album == "アルバム未収録" else "💿 収録アルバム")
                    st.markdown(f"**{selected_album}**")
                    if series_col and not album_master_df.empty and alb_col:
                        album_master_keys = (
                            album_master_df["_album_search_key"]
                            if "_album_search_key" in album_master_df.columns
                            else album_master_df[alb_col].map(make_search_key)
                        )
                        series_match = album_master_df[
                            album_master_keys == make_search_key(selected_album)
                        ]
                        if not series_match.empty:
                            st.caption(f"シリーズ: {series_match.iloc[0][series_col]}")
                    if album_preview_options:
                        st.markdown("##### ▶️ 視聴動画")
                        selected_preview_index = st.selectbox(
                            "視聴する動画を選択:",
                            range(len(album_preview_options)),
                            format_func=lambda index: album_preview_options[index]["表示"],
                            key=f"tab2_album_preview_{make_search_key(selected_song)}",
                        )
                        selected_preview = album_preview_options[selected_preview_index]
                        render_compact_youtube(selected_preview["URL"], selected_preview["表示"])
                        st.link_button("YouTubeで開く", selected_preview["URL"])
            with media_col:
                if song_media_options:
                    st.subheader("▶️ 公式音源・MV")
                    selected_media_index = st.selectbox(
                        "再生する公式コンテンツを選択:",
                        range(len(song_media_options)),
                        format_func=lambda index: song_media_options[index]["表示"],
                        key=f"tab2_media_{make_search_key(selected_song)}",
                    )
                    selected_media = song_media_options[selected_media_index]
                    render_compact_youtube(selected_media["URL"], selected_media["表示"])
                    st.caption(f"{selected_media['種別']}｜公式YouTubeの埋め込みです。")
                    st.link_button("YouTubeで開く", selected_media["URL"])
                else:
                    st.caption("公式YouTubeコンテンツは、まだ登録されていません。")

            st.markdown("---")

            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            total_count = len(song_df)
            m_col1.metric("🎤 総披露回数", f"{total_count} 回")

            valid_dates = song_df.dropna(subset=["日付_dt"])
            if not valid_dates.empty:
                latest_row = valid_dates.loc[valid_dates["日付_dt"].idxmax()]
                first_row = valid_dates.loc[valid_dates["日付_dt"].idxmin()]

                last_date_str = latest_row["日付_dt"].strftime("%Y/%m/%d")
                first_date_str = first_row["日付_dt"].strftime("%Y/%m/%d")

                last_live_name = str(latest_row[live_col_name]) if live_col_name and pd.notnull(latest_row[live_col_name]) else ""
                first_live_name = str(first_row[live_col_name]) if live_col_name and pd.notnull(first_row[live_col_name]) else ""

                days_since = (pd.to_datetime(datetime.now().date()) - latest_row["日付_dt"]).days

                m_col2.metric("📅 最終披露日", last_date_str, delta=last_live_name, delta_color="normal")
                m_col3.metric("⏳ 前回からの経過", format_days_ago(days_since))
                m_col4.metric("🌟 初披露日", first_date_str, delta=first_live_name, delta_color="normal")
            else:
                m_col2.metric("📅 最終披露日", "未披露 / データなし")
                m_col3.metric("⏳ 前回からの経過", "未披露")
                m_col4.metric("🌟 初披露日", "未披露")

            st.markdown("---")
            st.subheader(f"📜 「{selected_song}」の全披露履歴 ({total_count} 件)")

            drop_cols = ["search_key", "live_search_key", "日付_dt", "アルバム登録済", "集計用楽曲名", "原曲名", "楽曲区分", "曲順", "No", "NO", "no"]
            display_song_df = song_df.drop(columns=[c for c in drop_cols if c in song_df.columns], errors="ignore").reset_index(drop=True)
            display_song_df.index = display_song_df.index + 1

            def highlight_versions(row):
                ver = str(row.get("バージョン", ""))
                if "short" in ver and "歌唱なし" in ver:
                    return ['background-color: rgba(244, 114, 182, 0.2); color: #be185d'] * len(row)
                elif "short" in ver:
                    return ['background-color: rgba(81, 194, 240, 0.2); color: #0369a1'] * len(row)
                elif "歌唱なし" in ver:
                    return ['background-color: rgba(123, 92, 255, 0.2); color: #5a45d6'] * len(row)
                return [''] * len(row)

            st.dataframe(
                display_song_df.style.apply(highlight_versions, axis=1), 
                use_container_width=True,
                column_config={
                    "公演名": st.column_config.TextColumn("公演名", width="large"),
                    "楽曲名": st.column_config.TextColumn("楽曲名", width="large"),
                }
            )

    # TAB 3: 歌唱者（キャスト/アイドル）× 楽曲・衣装分析
    with tab3:
        render_page_header(
            "🎤",
            "歌唱者・楽曲・衣装分析",
            "キャストとアイドルを横断し、歌唱履歴と本人に対応する衣装だけを確認できます。",
        )

        singer_col = next((c for c in df.columns if "歌唱" in c or "出演" in c or "メンバー" in c), None)
        costume_col = next((c for c in df.columns if "衣装" in c), None)
        unit_col_song = next((c for c in df.columns if "ユニット" in c), None)

        if singer_col:
            col_mode, col_person, col_song = st.columns(3)

            with col_mode:
                search_mode = st.radio(
                    "1. 絞り込み種別を選択:",
                    ["キャスト名で検索", "アイドル名で検索", "全歌唱者から選択"],
                    horizontal=True,
                    key="tab3_search_mode"
                )

            if search_mode == "キャスト名で検索" and cast_list:
                person_options = cast_list
            elif search_mode == "アイドル名で検索" and idol_list:
                person_options = idol_list
            else:
                raw_singers = []
                for val in df[singer_col].dropna():
                    for s in re.split(r"[;；]", str(val)):
                        if s.strip(): raw_singers.append(s.strip())
                person_options = unique_in_registered_order(raw_singers)

            with col_person:
                selected_person = st.selectbox("2. 人物・歌唱者を選択:", person_options, key="tab3_sel_person")

            search_keywords = [selected_person]
            if unify_member_names:
                if selected_person in cast_to_idol_map:
                    search_keywords.append(cast_to_idol_map[selected_person])
                if selected_person in idol_to_cast_map:
                    for sub_c in re.split(r"[;；]", idol_to_cast_map[selected_person]):
                        if sub_c.strip(): search_keywords.append(sub_c.strip())

            pattern = "|".join([re.escape(k) for k in set(search_keywords)])
            singer_df = df[df[singer_col].astype(str).str.contains(pattern, na=False, regex=True)].copy()

            with col_song:
                if exclude_talk_events:
                    singer_song_df = singer_df[~singer_df["楽曲名"].astype(str).str.contains("トークのみ", na=False)]
                else:
                    singer_song_df = singer_df
                singer_songs = unique_in_registered_order(singer_song_df["集計用楽曲名"].tolist()) if len(singer_song_df) > 0 else []
                selected_singer_song = st.selectbox("3. 楽曲を選択:", singer_songs, key="tab3_sel_song")

            person_unit = idol_to_unit_map.get(selected_person, "")
            person_groups = set(idol_to_groups_map.get(selected_person, set()))
            if selected_person in cast_to_idol_map:
                person_groups.update(
                    idol_to_groups_map.get(cast_to_idol_map[selected_person], set())
                )
            if person_unit:
                person_groups.add(person_unit)

            # ソロ衣装はユニット名ではなくアイドル名で登録されているため、
            # キャスト／アイドルのどちらを選んでも本人の衣装だけを判定できるようにする。
            person_costume_targets = {selected_person}
            if selected_person in cast_to_idol_map:
                person_costume_targets.add(cast_to_idol_map[selected_person])
            if selected_person in idol_to_cast_map:
                person_costume_targets.update(
                    s.strip()
                    for s in re.split(r"[;；]", idol_to_cast_map[selected_person])
                    if s.strip()
                )

            def find_person_costume(row, c_list):
                # 5.5th Anniversary LIVE is a special case: the costume is
                # determined by the member's unit, even for all-member songs.
                # Apply this before the generic group / SHINY COLORS fallback.
                event_name = str(row.get(live_col_name, "")) if live_col_name else ""
                if "5.5th" in event_name and "星が見上げた空" in event_name:
                    for unit_name, override_costume in FIVE_HALF_EVENT_COSTUME_OVERRIDES.items():
                        if unit_name in person_groups and override_costume in c_list:
                            return override_costume

                if len(c_list) == 1:
                    only_costume_target = costume_to_unit_map.get(c_list[0])
                    if (
                        only_costume_target in person_groups
                        or only_costume_target in person_costume_targets
                        or only_costume_target == "シャイニーカラーズ"
                    ):
                        return c_list[0]
                    return None

                for c_item in c_list:
                    costume_target = costume_to_unit_map.get(c_item)
                    if (
                        costume_target in person_groups
                        or costume_target in person_costume_targets
                    ):
                        return c_item

                for c_item in c_list:
                    if costume_to_unit_map.get(c_item) == "シャイニーカラーズ":
                        return c_item

                if unit_col_song and pd.notnull(row[unit_col_song]):
                    u_list = [
                        u.strip()
                        for u in re.split(r"[;；]", str(row[unit_col_song]))
                        if u.strip()
                    ]
                    if person_unit in u_list:
                        u_idx = u_list.index(person_unit)
                        if u_idx < len(c_list):
                            return c_list[u_idx]

                return None

            st.markdown("---")

            if selected_singer_song and len(singer_df) > 0:
                match_df = singer_df[singer_df["集計用楽曲名"] == selected_singer_song].copy()
                if "日付_dt" in match_df.columns:
                    match_df = match_df.sort_values(by="日付_dt", ascending=False)

                st.subheader(f"🎤 「{selected_person}」×「{selected_singer_song}」歌唱実績")
                
                m_c1, m_c2, m_c3 = st.columns(3)
                m_c1.metric("🎤 個人歌唱回数", f"{len(match_df)} 回")

                valid_singer_dates = match_df.dropna(subset=["日付_dt"])
                if not valid_singer_dates.empty:
                    last_row = valid_singer_dates.iloc[0]
                    l_date = last_row["日付_dt"].strftime("%Y/%m/%d")
                    l_live = str(last_row[live_col_name]) if live_col_name else ""
                    days_ago = (pd.to_datetime(datetime.now().date()) - last_row["日付_dt"]).days

                    m_c2.metric("📅 最後に歌った日", l_date, delta=l_live, delta_color="normal")
                    m_c3.metric("⏳ 最後に歌ってからの経過", format_days_ago(days_ago))
                else:
                    m_c2.metric("📅 最後に歌った日", "データなし")
                    m_c3.metric("⏳ 最後に歌ってからの経過", "データなし")

                st.write(f"📜 **「{selected_person}」が「{selected_singer_song}」を歌唱した全公演履歴**")

                d_cols = ["search_key", "live_search_key", "日付_dt", "アルバム登録済", "集計用楽曲名", "原曲名"]
                disp_df = match_df.drop(columns=[c for c in d_cols if c in match_df.columns], errors="ignore").reset_index(drop=True)
                disp_df.index = disp_df.index + 1
                st.dataframe(
                    disp_df, 
                    use_container_width=True,
                    column_config={
                        "公演名": st.column_config.TextColumn("公演名", width="large"),
                        "楽曲名": st.column_config.TextColumn("楽曲名", width="large"),
                    }
                )
            else:
                st.info("該当する歌唱データがありません。")

            st.markdown("---")

            if len(singer_df) > 0 and costume_col:
                st.subheader(f"👗 「{selected_person}」の衣装着用記録")

                tab3_series_col = (
                    next((c for c in costume_master_df.columns if "シリーズ" in c), None)
                    if not costume_master_df.empty else None
                )
                tab3_unit_col = (
                    next((c for c in costume_master_df.columns if "ユニット" in c or "キャラ" in c), None)
                    if not costume_master_df.empty else None
                )

                f_col1, f_col2 = st.columns(2)
                with f_col1:
                    c_series_list = ["すべて"]
                    if tab3_series_col:
                        c_series_list += unique_in_registered_order(costume_master_df[tab3_series_col].tolist())
                    sel_tab3_c_series = st.selectbox("衣装シリーズで絞り込み:", c_series_list, key="tab3_c_series")

                with f_col2:
                    c_unit_list = ["すべて"]
                    if tab3_unit_col:
                        tab3_filter_master = costume_master_df.copy()
                        if sel_tab3_c_series != "すべて" and tab3_series_col:
                            tab3_filter_master = tab3_filter_master[
                                tab3_filter_master[tab3_series_col] == sel_tab3_c_series
                            ]
                        c_unit_list += unique_in_registered_order(tab3_filter_master[tab3_unit_col].tolist())
                    sel_tab3_c_unit = st.selectbox(
                        "対象ユニット/キャラで絞り込み:",
                        c_unit_list,
                        key="tab3_c_unit",
                    )

                assigned_costume_by_index = {}
                for row_index, r in zip(
                    singer_df.index,
                    singer_df.to_dict("records"),
                ):
                    c_val = str(r[costume_col]) if pd.notnull(r[costume_col]) else ""
                    if not c_val or c_val == "nan":
                        assigned_costume_by_index[row_index] = []
                        continue
                    
                    c_list = [c.strip() for c in re.split(r"[;；]", c_val) if c.strip()]
                    
                    matched_c = find_person_costume(r, c_list)
                    if matched_c:
                        assigned_costume_by_index[row_index] = [matched_c]
                    else:
                        # 本人との対応を確認できない衣装は、誤った着用記録として
                        # 表示しない。衣装名が並んだだけの公演データもここで除外する。
                        assigned_costume_by_index[row_index] = []

                person_costumes = [
                    costume
                    for costumes in assigned_costume_by_index.values()
                    for costume in costumes
                ]

                candidate_person_costumes = unique_in_registered_order(person_costumes)
                if not costume_master_df.empty and "衣装" in costume_master_df.columns:
                    target_c_m = costume_master_df.copy()
                    if sel_tab3_c_series != "すべて" and tab3_series_col:
                        target_c_m = target_c_m[target_c_m[tab3_series_col] == sel_tab3_c_series]
                    if sel_tab3_c_unit != "すべて" and tab3_unit_col:
                        target_c_m = target_c_m[target_c_m[tab3_unit_col] == sel_tab3_c_unit]

                    person_costume_set = set(person_costumes)
                    master_ordered_costumes = [
                        costume
                        for costume in target_c_m["衣装"].tolist()
                        if costume in person_costume_set
                    ]
                    unmatched_costumes = [
                        costume
                        for costume in candidate_person_costumes
                        if costume not in set(costume_master_df["衣装"].dropna())
                        and sel_tab3_c_series == "すべて"
                        and sel_tab3_c_unit == "すべて"
                    ]
                    candidate_person_costumes = unique_in_registered_order(
                        master_ordered_costumes + unmatched_costumes
                    )

                if candidate_person_costumes:
                    col_costume_select, col_costume_metric1, col_costume_metric2 = st.columns([1, 1, 1])
                    with col_costume_select:
                        selected_person_costume = st.selectbox(
                            "👗 着用衣装を選択して着用最終日を確認:",
                            candidate_person_costumes,
                            key="tab3_sel_costume"
                        )
                    
                    if selected_person_costume:
                        matching_indexes = [
                            row_index
                            for row_index, costumes in assigned_costume_by_index.items()
                            if selected_person_costume in costumes
                        ]
                        costume_match_df = singer_df.loc[matching_indexes].copy()
                        
                        valid_c_dates = costume_match_df.dropna(subset=["日付_dt"]).sort_values(by="日付_dt", ascending=False)
                        if not valid_c_dates.empty:
                            last_c_row = valid_c_dates.iloc[0]
                            c_last_date = last_c_row["日付_dt"].strftime("%Y/%m/%d")
                            c_last_live = str(last_c_row[live_col_name]) if live_col_name else ""
                            c_days_ago = (pd.to_datetime(datetime.now().date()) - last_c_row["日付_dt"]).days

                            with col_costume_metric1:
                                st.metric(
                                    f"📅 「{selected_person_costume}」着用最終日",
                                    c_last_date,
                                    delta=c_last_live,
                                    delta_color="normal"
                                )
                            with col_costume_metric2:
                                st.metric("⏳ 着用最終日からの経過", format_days_ago(c_days_ago))
                        else:
                            with col_costume_metric1: st.metric("📅 着用最終日", "データなし")
                            with col_costume_metric2: st.metric("⏳ 経過日数", "データなし")

                        if not costume_match_df.empty:
                            st.write(
                                f"📜 **「{selected_person}」が「{selected_person_costume}」を着用した公演履歴**"
                            )
                            costume_history_df = costume_match_df.copy()
                            if "日付_dt" in costume_history_df.columns:
                                costume_history_df = costume_history_df.sort_values(
                                    by="日付_dt", ascending=False, kind="stable"
                                )
                            costume_history_hidden_cols = [
                                "search_key", "live_search_key", "日付_dt", "アルバム登録済",
                                "集計用楽曲名", "原曲名",
                            ]
                            costume_history_display_df = costume_history_df.drop(
                                columns=[
                                    column for column in costume_history_hidden_cols
                                    if column in costume_history_df.columns
                                ],
                                errors="ignore",
                            ).reset_index(drop=True)
                            costume_history_display_df.index = costume_history_display_df.index + 1
                            st.dataframe(
                                costume_history_display_df,
                                use_container_width=True,
                                column_config={
                                    "公演名": st.column_config.TextColumn("公演名", width="large"),
                                    "楽曲名": st.column_config.TextColumn("楽曲名", width="large"),
                                },
                            )
                else:
                    st.info("※ 条件に一致する着用衣装データがありません。")

    # TAB 4: 衣装別データ分析
    with tab4:
        render_page_header(
            "👗",
            "衣装別データ分析",
            "シリーズとユニットから衣装を絞り込み、着用回数と披露履歴を確認できます。",
        )

        costume_col = next((c for c in df.columns if "衣装" in c), None)

        if costume_col:
            raw_costumes = []
            for val in df[costume_col].dropna():
                for c in re.split(r"[;；]", str(val)):
                    if c.strip(): raw_costumes.append(c.strip())

            if not costume_master_df.empty and "衣装" in costume_master_df.columns:
                master_costumes = costume_master_df["衣装"].tolist()
                all_costumes = unique_in_registered_order(master_costumes + raw_costumes)
            else:
                all_costumes = unique_in_registered_order(raw_costumes)

            all_costumes = [c for c in all_costumes if c and str(c) != "nan"]

            if all_costumes:
                c_series_col = (
                    next((c for c in costume_master_df.columns if "シリーズ" in c), None)
                    if not costume_master_df.empty else None
                )
                c_unit_col = (
                    next((c for c in costume_master_df.columns if "ユニット" in c or "キャラ" in c), None)
                    if not costume_master_df.empty else None
                )

                cc1, cc2, cc3 = st.columns(3)

                with cc1:
                    c_series_list = ["すべて"]
                    if c_series_col:
                        c_series_list += unique_in_registered_order(costume_master_df[c_series_col].tolist())
                    sel_c_series = st.selectbox("1. シリーズで絞り込み:", c_series_list, key="tab4_sel_c_series")

                with cc2:
                    c_unit_list = ["すべて"]
                    if c_unit_col:
                        filtered_c_m = costume_master_df.copy()
                        if sel_c_series != "すべて" and c_series_col:
                            filtered_c_m = filtered_c_m[filtered_c_m[c_series_col] == sel_c_series]
                        c_unit_list += unique_in_registered_order(filtered_c_m[c_unit_col].tolist())
                    sel_c_unit = st.selectbox("2. ユニットで絞り込み:", c_unit_list, key="tab4_sel_c_unit")

                with cc3:
                    candidate_costumes = all_costumes
                    if not costume_master_df.empty and "衣装" in costume_master_df.columns:
                        target_c_df = costume_master_df.copy()
                        if sel_c_series != "すべて" and c_series_col:
                            target_c_df = target_c_df[target_c_df[c_series_col] == sel_c_series]
                        if sel_c_unit != "すべて" and c_unit_col:
                            target_c_df = target_c_df[target_c_df[c_unit_col] == sel_c_unit]

                        if sel_c_series != "すべて" or sel_c_unit != "すべて":
                            candidate_costumes = unique_in_registered_order(target_c_df["衣装"].tolist())

                    if not candidate_costumes:
                        st.warning("⚠️ 条件に一致する衣装がありませんでした。")
                        selected_costume = None
                    else:
                        selected_costume = st.selectbox("3. 分析する衣装を選択:", candidate_costumes, key="tab4_sel_costume")

                if selected_costume:
                    escaped_c_name = re.escape(selected_costume)
                    c_df = df[df[costume_col].astype(str).str.contains(escaped_c_name, na=False, regex=True)].copy()

                    if "日付_dt" in c_df.columns:
                        c_df = c_df.sort_values(by="日付_dt", ascending=False)

                    if not costume_master_df.empty and "衣装" in costume_master_df.columns:
                        m_info = costume_master_df[costume_master_df["衣装"] == selected_costume]
                        if not m_info.empty:
                            st.markdown("---")
                            st.subheader("💡 衣装マスタ情報")
                            mc1, mc2, mc3 = st.columns(3)

                            c_type_col = next((c for c in costume_master_df.columns if "区分" in c), None)

                            if c_series_col: mc1.metric("シリーズ", str(m_info.iloc[0][c_series_col]))
                            if c_unit_col: mc2.metric("対象ユニット/キャラ", str(m_info.iloc[0][c_unit_col]))
                            if c_type_col: mc3.metric("衣装区分", str(m_info.iloc[0][c_type_col]))

                    render_costume_context_images(str(selected_costume))

                    st.markdown("---")
                    st.subheader("📊 着用（披露）実績")
                    m_c1, m_c2, m_c3, m_c4 = st.columns(4)
                    c_total = len(c_df)
                    c_live_total = c_df[live_col_name].nunique() if live_col_name else c_total

                    m_c1.metric("👗 着用パフォーマンス", f"{c_total} 曲 ({c_live_total} 公演)")

                    valid_c_dates = c_df.dropna(subset=["日付_dt"])
                    if c_total > 0 and not valid_c_dates.empty:
                        latest_c = valid_c_dates.iloc[0]
                        first_c = valid_c_dates.iloc[-1]

                        last_c_date = latest_c["日付_dt"].strftime("%Y/%m/%d")
                        first_c_date = first_c["日付_dt"].strftime("%Y/%m/%d")

                        last_c_live = str(latest_c[live_col_name]) if live_col_name else ""
                        first_c_live = str(first_c[live_col_name]) if live_col_name else ""

                        days_c_ago = (pd.to_datetime(datetime.now().date()) - latest_c["日付_dt"]).days

                        m_c2.metric("📅 最後に着用した日", last_c_date, delta=last_c_live, delta_color="normal")
                        m_c3.metric("⏳ 前回からの経過", format_days_ago(days_c_ago))
                        m_c4.metric("🌟 初お披露目日", first_c_date, delta=first_c_live, delta_color="normal")

                        st.markdown("---")
                        st.subheader(f"📜 衣装「{selected_costume}」で披露された全楽曲＆公演履歴 ({c_total} 件)")

                        d_cols = ["search_key", "live_search_key", "日付_dt", "アルバム登録済", "集計用楽曲名", "原曲名"]
                        disp_c_df = c_df.drop(columns=[c for c in d_cols if c in c_df.columns], errors="ignore").reset_index(drop=True)
                        disp_c_df.index = disp_c_df.index + 1
                        st.dataframe(
                            disp_c_df, 
                            use_container_width=True,
                            column_config={
                                "公演名": st.column_config.TextColumn("公演名", width="large"),
                                "楽曲名": st.column_config.TextColumn("楽曲名", width="large"),
                            }
                        )
                    else:
                        m_c2.metric("📅 最後に着用した日", "データなし")
                        m_c3.metric("⏳ 前回からの経過", "データなし")
                        m_c4.metric("🌟 初お披露目日", "データなし")
                        st.info(f"⚠️ 衣装「{selected_costume}」でのライブ着用記録（songs.csv）はまだ登録されていません。")
            else:
                st.info("衣装データが見つかりません。")
        else:
            st.warning("⚠️ `songs.csv` に「衣装」を表す列が見つかりません。")

    if not PUBLIC_MODE:
        # TAB 5: ランダムガチャ
        with tab5:
            render_page_header(
                "🎲",
                "今日のおすすめライブガチャ",
                "現在の分析対象から、見返したい一曲・一公演をランダムに提案します。",
            )

            gacha_df = df.copy()
            if exclude_talk_events:
                gacha_df = gacha_df[~gacha_df["楽曲名"].astype(str).str.contains("トークのみ", na=False)]

            if st.button("✨ ガチャを回す！", key="btn_gacha", type="primary") and len(gacha_df) > 0:
                st.session_state.gacha_result = gacha_df.sample(n=1).iloc[0]
                st.balloons()

            if "gacha_result" in st.session_state:
                g_row = st.session_state.gacha_result
                st.markdown("---")
                st.subheader("🎉 本日のおすすめパフォーマンス！")

                gc1, gc2, gc3 = st.columns(3)
                gc1.metric("🎵 楽曲名", str(g_row.get("楽曲名", "-")), delta=str(g_row.get("ユニット", "")), delta_color="normal")
                gc2.metric("🏟️ 公演名", str(g_row.get("公演名", "-")), delta=str(g_row.get("日付", "")), delta_color="normal")
                gc3.metric("👗 着用衣装", str(g_row.get("衣装", "-")))

                st.markdown(f"**🎤 歌唱キャスト/アイドル:** {g_row.get('歌唱者', '-')}")
                render_gacha_context_images()

    if not PUBLIC_MODE:
        # TAB 6: データ検索・全データ
        with tab6:
            render_page_header(
                "🔍",
                "楽曲・公演検索" if PUBLIC_MODE else "データ検索・全データ",
                "楽曲名・公演名・歌唱者・衣装から記録を探せます。" if PUBLIC_MODE else "登録内容を横断検索し、分類漏れや元データもまとめて確認できます。",
            )
            searchable_columns = [
                column
                for column in df.columns
                if not column.startswith("_")
                and column not in {
                    "search_key", "live_search_key", "日付_dt",
                    "アルバム登録済", "集計用楽曲名", "原曲名", "バージョン",
                }
            ]
            search_input_col, search_target_col = st.columns([2.2, 1])
            with search_input_col:
                data_search_keyword = st.text_input(
                    "キーワード",
                    placeholder="楽曲名、公演名、歌唱者、衣装など",
                    key="tab6_data_search",
                )
            with search_target_col:
                data_search_target = st.selectbox(
                    "検索対象",
                    ["すべての列"] + searchable_columns,
                    key="tab6_data_search_target",
                )

            searched_df = df
            if data_search_keyword.strip():
                if data_search_target == "すべての列":
                    search_mask = pd.Series(False, index=df.index)
                    for column in searchable_columns:
                        search_mask |= df[column].astype(str).str.contains(
                            data_search_keyword.strip(),
                            case=False,
                            na=False,
                            regex=False,
                        )
                else:
                    search_mask = df[data_search_target].astype(str).str.contains(
                        data_search_keyword.strip(),
                        case=False,
                        na=False,
                        regex=False,
                    )
                searched_df = df[search_mask]

            if not PUBLIC_MODE and "楽曲区分" in df.columns:
                unclassified_df = df[df["楽曲区分"] == "未分類"]
                if len(unclassified_df) > 0:
                    with st.expander(
                        f"⚠️ 未分類データ {len(unclassified_df):,}件を確認",
                        expanded=False,
                    ):
                        st.dataframe(
                            unclassified_df["楽曲名"].value_counts().reset_index(),
                            use_container_width=True,
                            hide_index=True,
                        )
                else:
                    st.success("✅ すべての曲が正常に分類（紐付け）されています！")

            st.subheader(f"📊 検索結果：{len(searched_df):,} 件")
            st.dataframe(
                searched_df.drop(
                    columns=["search_key", "live_search_key", "日付_dt", "アルバム登録済", "集計用楽曲名", "原曲名", "バージョン"],
                    errors="ignore",
                ),
                use_container_width=True,
                hide_index=True,
                height=620,
                column_config={
                    "公演名": st.column_config.TextColumn("公演名", width="large"),
                    "楽曲名": st.column_config.TextColumn("楽曲名", width="large"),
                }
            )

    if not PUBLIC_MODE:
        # TAB 7: 新規データ＆各種マスタ登録フォーム（全項目網羅版）
        with tab7:
            render_page_header(
                "➕",
                "データ管理",
                "よく使う登録は専用フォームから、細かな修正はCSV編集から行えます。保存前に内容を確認できます。",
            )
            register_modes = [
                "🎤 セットリスト（ライブ歌唱）＆公演マスタ登録",
                "👗 衣装マスタ追加",
                "🎵 アルバム・楽曲マスタ追加",
                "👤 アイドル・キャストを追加",
                "🃏 カード・シナリオ実装を登録",
                "📝 楽曲の分類・歌詞・公式リンクを登録",
                "🖼️ ジャケット情報を登録",
                "👥 出演・参加履歴をまとめて登録",
                "🗃️ 全CSVを追加・編集",
            ]
            if st.session_state.get("tab7_register_mode") not in register_modes:
                st.session_state["tab7_register_mode"] = register_modes[0]
            st.caption("登録するデータを選択")
            register_mode_buttons = st.columns(3)
            for index, mode_name in enumerate(register_modes):
                with register_mode_buttons[index % 3]:
                    if st.button(
                        mode_name,
                        key=f"tab7_register_mode_button_{index}",
                        type="primary" if st.session_state["tab7_register_mode"] == mode_name else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state["tab7_register_mode"] = mode_name
                        st.rerun()
            register_mode = st.session_state["tab7_register_mode"]

            st.markdown("---")

            if register_mode == "🎤 セットリスト（ライブ歌唱）＆公演マスタ登録":
                st.subheader("🎤 新公演セットリスト ＆ 公演マスタ同時登録")
            
                if "num_songs_to_add" not in st.session_state:
                    st.session_state.num_songs_to_add = 1

                requested_song_rows = st.number_input(
                    "個別入力する曲数",
                    min_value=1,
                    max_value=40,
                    value=st.session_state.num_songs_to_add,
                    step=1,
                    help="下の個別入力欄の数です。まとめて貼り付ける場合は1のままで大丈夫です。",
                )
                if requested_song_rows != st.session_state.num_songs_to_add:
                    st.session_state.num_songs_to_add = requested_song_rows
                    st.rerun()

                event_casts = st.multiselect(
                    "この公演の出演者（先に選ぶと各楽曲で候補を絞り込めます）",
                    options=cast_list,
                    key="setlist_event_casts",
                    help="合同・外部ライブでは、ここで選んだ出演者に加えて各楽曲で「その他」も選べます。",
                )

                with st.form("add_individual_songs_form"):
                    st.markdown("##### 🏟️ 公演情報（公演マスター `events.csv` にも自動登録されます）")
                    fc1, fc2, fc3, fc4 = st.columns(4)
                    with fc1: input_date = st.date_input("日付 *", datetime.now().date())
                    with fc2: input_live_name = st.text_input("公演名 *（例: 7thLIVE DAY1）")
                    with fc3: input_event_type = st.selectbox("公演区分 *", ["キャストライブ", "XR", "発売記念イベント", "合同", "外部", "その他"])
                    with fc4: input_venue_name = st.text_input("会場（例: Kアリーナ横浜）")

                    st.markdown("---")
                    st.markdown("##### 🎵 セットリスト楽曲情報")
                    bulk_setlist_text = st.text_area(
                        "まとめて貼り付け（任意）",
                        placeholder=(
                            "曲順 | 楽曲名 | ユニット | 歌唱者 | 衣装\n"
                            "1 | Spread the Wings!! | シャイニーカラーズ | 関根瞳;近藤玲奈 | ビヨンドザブルースカイ\n"
                            "※ タブ区切りでも入力できます。貼り付けた行は個別入力欄に追加して保存されます。"
                        ),
                        height=150,
                    )
                
                    # キャスト/アイドル選択補助
                    available_members = unique_in_registered_order(event_casts + cast_list + idol_list) if (cast_list or idol_list) else []
                    unit_options_for_setlist = ["（指定なし）"] + unique_in_registered_order(group_to_casts_map.keys())

                    songs_input_data = []
                    for i in range(st.session_state.num_songs_to_add):
                        st.write(f"**🎵 {i+1} 曲目**")
                        rc1, rc2, rc3, rc4, rc5 = st.columns([1, 3, 2, 3, 3])
                        with rc1: order_val = st.text_input("曲順", value=str(i + 1), key=f"ord_{i}")
                        with rc2: song_val = st.text_input("楽曲名 *", key=f"sng_{i}", placeholder="例: Spread the Wings!!")
                        with rc3:
                            selected_unit = st.selectbox(
                                "ユニット",
                                unit_options_for_setlist,
                                key=f"unt_{i}",
                            )
                            unit_val = "" if selected_unit == "（指定なし）" else selected_unit
                    
                        with rc4:
                            if available_members:
                                unit_members = group_to_casts_map.get(unit_val, [])
                                # 全体曲は、公演出演者を初期候補にする。
                                if unit_val == "シャイニーカラーズ":
                                    unit_members = event_casts
                                allowed_singers = unique_in_registered_order(event_casts + unit_members)
                                if not allowed_singers:
                                    allowed_singers = available_members
                                singer_options = unique_in_registered_order(allowed_singers + ["その他"])
                                multiselect_singers = st.multiselect(
                                    "歌唱者（複数選択）",
                                    options=singer_options,
                                    default=[name for name in unit_members if name in singer_options],
                                    key=f"sgr_multi_{i}_{make_search_key(unit_val) or 'none'}",
                                )
                                singer_text_extra = st.text_input("その他の歌唱者（任意）", key=f"sgr_txt_{i}", placeholder="外部出演者など")
                                all_singers_combined = ";".join(multiselect_singers)
                                if singer_text_extra.strip():
                                    manual_singers = [
                                        name.strip()
                                        for name in re.split(r"[;；・]", singer_text_extra)
                                        if name.strip()
                                    ]
                                    all_singers_combined = ";".join(
                                        [name for name in [all_singers_combined, *manual_singers] if name]
                                    )
                                singer_val = all_singers_combined
                            else:
                                singer_val = st.text_input("歌唱者", key=f"sgr_{i}", placeholder="例: 関根瞳・近藤玲奈・峯田茉優")

                        with rc5: costume_val = st.text_input("衣装", key=f"cst_{i}", placeholder="例: ビヨンドザブルースカイ")

                        songs_input_data.append(
                            {"曲順": order_val, "楽曲名": song_val, "ユニット": unit_val, "歌唱者": singer_val, "衣装": costume_val}
                        )

                    if bulk_setlist_text.strip():
                        for line_index, raw_line in enumerate(bulk_setlist_text.splitlines(), start=1):
                            raw_line = raw_line.strip()
                            if not raw_line or raw_line.startswith("#"):
                                continue
                            parts = [part.strip() for part in re.split(r"[|\t]", raw_line)]
                            if len(parts) < 2:
                                continue
                            parts += [""] * (5 - len(parts))
                            songs_input_data.append(
                                {
                                    "曲順": parts[0] or str(line_index),
                                    "楽曲名": parts[1],
                                    "ユニット": parts[2],
                                    "歌唱者": parts[3],
                                    "衣装": parts[4],
                                }
                            )

                    # ユニットを指定した曲で歌唱者が未選択なら、所属キャストを自動補完する。
                    # シャイニーカラーズの全体曲は、この公演で選んだ出演者を使う。
                    for row in songs_input_data:
                        if str(row.get("歌唱者", "")).strip():
                            continue
                        row_unit = str(row.get("ユニット", "")).strip()
                        if row_unit == "シャイニーカラーズ":
                            automatic_singers = event_casts
                        else:
                            automatic_singers = group_to_casts_map.get(row_unit, [])
                        if automatic_singers:
                            row["歌唱者"] = ";".join(automatic_singers)

                    if st.form_submit_button("🚀 セットリスト＆公演マスタを一括保存"):
                        if not input_live_name.strip():
                            st.error("⚠️ 公演名を入力してください。")
                        else:
                            formatted_date = input_date.strftime("%Y/%m/%d")
                            clean_event_title = clean_live_name(input_live_name)
                        
                            # 1. 公演マスター (events.csv) への一括追加処理
                            new_ev_row = [
                                {
                                    "日付": formatted_date,
                                    "公演名": clean_event_title,
                                    "会場": input_venue_name.strip(),
                                    "公演区分": input_event_type,
                                }
                            ]
                            append_csv_rows(
                                EVENT_MASTER_FILE,
                                new_ev_row,
                                ["日付", "公演名", "会場", "公演区分"],
                            )

                            # 2. セットリスト (songs.csv) への保存処理
                            valid_songs = [
                                {
                                    "日付": formatted_date,
                                    "公演名": clean_event_title,
                                    "曲順": r["曲順"],
                                    "楽曲名": r["楽曲名"],
                                    "ユニット": r["ユニット"],
                                    "歌唱者": r["歌唱者"],
                                    "衣装": r["衣装"],
                                }
                                for r in songs_input_data if r["楽曲名"].strip()
                            ]

                            if valid_songs:
                                append_csv_rows(
                                    SETLIST_FILE,
                                    valid_songs,
                                    ["曲順", "日付", "公演名", "楽曲名", "ユニット", "歌唱者", "衣装"],
                                )
                                st.success(f"🎉 公演「{clean_event_title}」のマスタ情報およびセットリスト ({len(valid_songs)} 曲) を一括保存しました！(F5キーで最新情報に更新)")
                            else:
                                st.warning("⚠️ 公演マスタは追加されましたが、有効な楽曲名が入力されていないためセットリストは保存されませんでした。")

            elif register_mode == "👗 衣装マスタ追加":
                st.subheader("👗 新規衣装マスタ追加 (`costumes.csv`)")
                with st.form("add_costume_form"):
                    c1, c2 = st.columns(2)
                    with c1:
                        new_costume_name = st.text_input("衣装名（必須） *")
                        new_costume_series = st.text_input("シリーズ（例: 7thLIVE / ソンフォプリズム）")
                    with c2:
                        new_costume_unit = st.text_input("対象ユニット/キャラ（例: ストレイライト / 共通）")
                        new_costume_type = st.selectbox("衣装区分", ["共通衣装", "ユニット衣装", "個装", "その他"])

                    if st.form_submit_button("💾 衣装マスタへ保存"):
                        if not new_costume_name.strip():
                            st.error("⚠️ 衣装名を入力してください。")
                        else:
                            new_c_row = pd.DataFrame(
                                [
                                    {
                                        "衣装": new_costume_name.strip(),
                                        "シリーズ": new_costume_series.strip(),
                                        "ユニット/キャラ": new_costume_unit.strip(),
                                        "衣装区分": new_costume_type,
                                    }
                                ]
                            )
                            append_csv_rows(
                                COSTUME_MASTER_FILE,
                                new_c_row.to_dict("records"),
                                ["衣装", "シリーズ", "ユニット/キャラ", "衣装区分"],
                            )
                            st.success(f"🎉 衣装「{new_costume_name}」を保存しました！(F5キーで最新情報に更新)")

            elif register_mode == "🎵 アルバム・楽曲マスタ追加":
                st.subheader("🎵 新規アルバム＆楽曲マスタ追加 (`albums.csv` / `songs_albums.csv`)")
                with st.form("add_album_form"):
                    ac1, ac2 = st.columns(2)
                    with ac1:
                        new_album_name = st.text_input("アルバム・CD名（例: CANVAS 01） *")
                        new_series_name = st.text_input("アルバムシリーズ（例: CANVAS）")
                    with ac2:
                        new_release_date = st.date_input("発売日", datetime.now().date())
                        new_album_singer = st.text_input("歌唱者（収録曲共通・任意）", placeholder="例: シャイニーカラーズ")
                        new_album_songs = st.text_area("収録楽曲リスト（1行に1曲ずつ入力）")

                    if st.form_submit_button("💾 アルバム＆楽曲マスタへ保存"):
                        if not new_album_name.strip():
                            st.error("⚠️ アルバム名を入力してください。")
                        else:
                            new_alb_row = [
                                {
                                    "アルバム名": new_album_name.strip(),
                                    "アルバムシリーズ": new_series_name.strip(),
                                }
                            ]
                            append_csv_rows(
                                ALBUM_MASTER_FILE,
                                new_alb_row,
                                ["アルバム名", "アルバムシリーズ"],
                            )

                            song_lines = [s.strip() for s in new_album_songs.split("\n") if s.strip()]
                            if song_lines:
                                sa_df_old = load_csv(SONG_ALBUM_FILE) if os.path.exists(SONG_ALBUM_FILE) else pd.DataFrame()
                                if "Column 7" in sa_df_old.columns:
                                    song_numbers = pd.to_numeric(sa_df_old["Column 7"], errors="coerce")
                                    next_song_number = int(song_numbers.max()) + 1 if song_numbers.notna().any() else 1
                                else:
                                    next_song_number = 1

                                new_sa_rows = [
                                    {
                                        "Column 7": next_song_number + index,
                                        "楽曲名": song_name,
                                        "アルバム": new_album_name.strip(),
                                        "リリース日": new_release_date.strftime("%Y/%m/%d"),
                                        "歌唱者": new_album_singer.strip(),
                                    }
                                    for index, song_name in enumerate(song_lines)
                                ]
                                append_csv_rows(
                                    SONG_ALBUM_FILE,
                                    new_sa_rows,
                                    ["Column 7", "楽曲名", "アルバム", "リリース日", "歌唱者"],
                                )

                            st.success(f"🎉 アルバム「{new_album_name}」と収録楽曲 ({len(song_lines)}曲) を保存しました！(F5キーで最新情報に更新)")

            elif register_mode == "👤 アイドル・キャストを追加":
                st.subheader("👤 アイドル・キャストを追加")
                st.caption("新しいアイドル・キャストや、企画ユニットの所属を追加します。すでに登録済みのキャラ名は内容を更新します。")
                with st.form("add_idol_form"):
                    member_col1, member_col2 = st.columns(2)
                    with member_col1:
                        new_idol_name = st.text_input("キャラ名 *")
                        existing_unit = st.text_input("既存ユニット")
                        refrac7ions_unit = st.text_input("PJ: REFRAC7IONS")
                    with member_col2:
                        new_cast_name = st.text_input("キャスト名 *")
                        team_unit = st.text_input("Team.")
                        master_showpiece_unit = st.text_input("-Master ShowPiece-")
                    halloween_unit = st.text_input("ハロウィン")
                    if st.form_submit_button("💾 アイドル・キャストを保存", type="primary"):
                        if not new_idol_name.strip() or not new_cast_name.strip():
                            st.error("⚠️ キャラ名とキャスト名を入力してください。")
                        else:
                            upsert_csv_row(
                                IDOL_MASTER_FILE,
                                {
                                    "キャラ": new_idol_name.strip(),
                                    "キャスト": new_cast_name.strip(),
                                    "既存ユニット": existing_unit.strip(),
                                    "PJ: REFRAC7IONS": refrac7ions_unit.strip(),
                                    "Team.": team_unit.strip(),
                                    "-Master ShowPiece-": master_showpiece_unit.strip(),
                                    "ハロウィン": halloween_unit.strip(),
                                },
                                ["キャラ", "キャスト", "既存ユニット", "PJ: REFRAC7IONS", "Team.", "-Master ShowPiece-", "ハロウィン"],
                                ["キャラ"],
                            )
                            st.success(f"🎉 「{new_idol_name.strip()}」を保存しました。")
                            st.rerun()

            elif register_mode == "🃏 カード・シナリオ実装を登録":
                st.subheader("🃏 カード・シナリオ実装を登録")
                st.caption(
                    "カードは P/S を指定します。P/S以外の名称はシナリオとして登録し、カレンダーでもカードとは分けて表示します。"
                )
                card_entry_buttons = st.columns(2)
                if "card_entry_mode" not in st.session_state:
                    st.session_state["card_entry_mode"] = "カード"
                with card_entry_buttons[0]:
                    if st.button("🃏 カード", key="card_entry_card_button", use_container_width=True,
                                 type="primary" if st.session_state["card_entry_mode"] == "カード" else "secondary"):
                        st.session_state["card_entry_mode"] = "カード"
                        st.rerun()
                with card_entry_buttons[1]:
                    if st.button("🎬 シナリオ・コミュ", key="card_entry_scenario_button", use_container_width=True,
                                 type="primary" if st.session_state["card_entry_mode"] == "シナリオ・コミュ" else "secondary"):
                        st.session_state["card_entry_mode"] = "シナリオ・コミュ"
                        st.rerun()
                card_entry_mode = st.session_state["card_entry_mode"]

                if card_entry_mode == "カード":
                    card_game_label, card_ps_label = st.columns([1, 1])
                    with card_game_label:
                        st.caption("作品")
                        if "card_game" not in st.session_state:
                            st.session_state["card_game"] = "シャニマス"
                        game_buttons = st.columns(2)
                        for index, game_name in enumerate(["シャニマス", "シャニソン"]):
                            if game_buttons[index].button(
                                game_name,
                                key=f"card_game_{game_name}",
                                use_container_width=True,
                                type="primary" if st.session_state["card_game"] == game_name else "secondary",
                            ):
                                st.session_state["card_game"] = game_name
                                st.rerun()
                        card_game = st.session_state["card_game"]
                    with card_ps_label:
                        st.caption("P/S")
                        ps_buttons = st.columns(2)
                        if "card_ps" not in st.session_state:
                            st.session_state["card_ps"] = "P"
                        with ps_buttons[0]:
                            if st.button("P", key="card_ps_p", use_container_width=True,
                                         type="primary" if st.session_state["card_ps"] == "P" else "secondary"):
                                st.session_state["card_ps"] = "P"
                                st.rerun()
                        with ps_buttons[1]:
                            if st.button("S", key="card_ps_s", use_container_width=True,
                                         type="primary" if st.session_state["card_ps"] == "S" else "secondary"):
                                st.session_state["card_ps"] = "S"
                                st.rerun()
                    card_ps = st.session_state["card_ps"]
                    with st.form("add_card_implementation_form"):
                        card_common_date = st.date_input(
                            "実装日 *",
                            datetime.now().date(),
                            key="card_common_date",
                        )
                        card_col1, card_col2 = st.columns(2)
                        with card_col1:
                            card_idol_name = st.selectbox(
                                "アイドル",
                                idol_list if idol_list else [""],
                                key="card_idol_name",
                            )
                            selected_member_background, selected_member_colors = member_color_swatch(card_idol_name)
                            if selected_member_background:
                                st.markdown(
                                    f"<span style='display:inline-flex;align-items:center;gap:.4rem;font-size:.82rem;'>"
                                    f"<span style='width:1rem;height:1rem;border-radius:50%;background:{selected_member_background};border:1px solid #777;'></span>"
                                    f"イメージカラー（既存 / PJ:REFRAC7IONS） {selected_member_colors}</span>",
                                    unsafe_allow_html=True,
                                )
                            card_rarity = st.selectbox(
                                "レア度",
                                ["SSR", "SR", "R", "UR", "N", "その他"],
                            )
                        with card_col2:
                            card_name = st.text_input("カード名")
                            card_source = st.selectbox(
                                "入手方法",
                                [
                                    "恒常", "限定", "イベント", "配布", "トワコレ",
                                    "マイコレ", "パラコレ", "ガシャ特典", "ライブ",
                                    "誕生日ガシャ", "その他",
                                ],
                            )

                        st.markdown("##### まとめて貼り付ける場合")
                        bulk_card_text = st.text_area(
                            "1行に「アイドル｜P/S｜レア度｜カード名｜入手方法」。日付は上の実装日を共通で使用します。",
                            placeholder=(
                                "櫻木真乃 | P | SSR | 【カード名】 | 限定\n"
                                "風野灯織 | S | SR | 【カード名】 | イベント"
                            ),
                            height=150,
                        )
                        save_card_rows = st.form_submit_button(
                            "💾 カード実装を保存",
                            type="primary",
                        )

                    if save_card_rows:
                        implementation_date = card_common_date.strftime("%Y/%m/%d")
                        card_rows_to_save = []
                        if card_name.strip():
                            card_rows_to_save.append(
                                {
                                    "アイドル": card_idol_name,
                                    "作品": card_game,
                                    "P/S": card_ps,
                                    "レア度": card_rarity,
                                    "カード名": card_name.strip(),
                                    "入手": card_source,
                                    "実装日": implementation_date,
                                }
                            )
                        for raw_line in bulk_card_text.splitlines():
                            parts = [
                                part.strip()
                                for part in re.split(r"[|｜\t]", raw_line)
                            ]
                            if len(parts) < 4:
                                continue
                            parts += [""] * (5 - len(parts))
                            if parts[1] not in {"P", "S"}:
                                continue
                            card_rows_to_save.append(
                                {
                                    "アイドル": parts[0],
                                    "作品": card_game,
                                    "P/S": parts[1],
                                    "レア度": parts[2],
                                    "カード名": parts[3],
                                    "入手": parts[4],
                                    "実装日": implementation_date,
                                }
                            )

                        if not card_rows_to_save:
                            st.error("カード名を入力するか、まとめ入力を貼り付けてください。")
                        else:
                            saved_count = upsert_csv_rows(
                                CARD_FILE,
                                card_rows_to_save,
                                ["アイドル", "作品", "P/S", "レア度", "カード名", "入手", "実装日"],
                                ["アイドル", "P/S", "カード名", "実装日"],
                            )
                            st.success(f"{saved_count}件のカード実装を保存しました。")
                            st.rerun()
                else:
                    with st.form("add_scenario_implementation_form"):
                        scenario_date = st.date_input(
                            "実装日 *",
                            datetime.now().date(),
                            key="scenario_date",
                        )
                        scenario_scope_options = unique_in_registered_order(
                            ["全体"] + idol_list
                            + (
                                idol_df["既存ユニット"].dropna().tolist()
                                if not idol_df.empty and "既存ユニット" in idol_df.columns
                                else []
                            )
                        )
                        scenario_scope = st.selectbox(
                            "対象アイドル・ユニット",
                            scenario_scope_options,
                        )
                        scenario_name = st.text_input(
                            "シナリオ・コミュ名 *",
                            help="この名称をP/S列へ保存し、カレンダーではシナリオとして表示します。",
                        )
                        scenario_bulk_text = st.text_area(
                            "同じ日に複数対象へ実装する場合（任意）",
                            placeholder="イルミネーションスターズ | シナリオ名\n櫻木真乃 | W.I.N.G編",
                            height=120,
                        )
                        save_scenario_rows = st.form_submit_button(
                            "💾 シナリオ実装を保存",
                            type="primary",
                        )

                    if save_scenario_rows:
                        implementation_date = scenario_date.strftime("%Y/%m/%d")
                        scenario_rows_to_save = []
                        if scenario_name.strip():
                            scenario_rows_to_save.append(
                                {
                                    "アイドル": scenario_scope,
                                    "P/S": scenario_name.strip(),
                                    "レア度": "",
                                    "カード名": "",
                                    "入手": "",
                                    "実装日": implementation_date,
                                }
                            )
                        for raw_line in scenario_bulk_text.splitlines():
                            parts = [
                                part.strip()
                                for part in re.split(r"[|｜\t]", raw_line)
                            ]
                            if len(parts) >= 2 and parts[0] and parts[1]:
                                scenario_rows_to_save.append(
                                    {
                                        "アイドル": parts[0],
                                        "P/S": parts[1],
                                        "レア度": "",
                                        "カード名": "",
                                        "入手": "",
                                        "実装日": implementation_date,
                                    }
                                )
                        if not scenario_rows_to_save:
                            st.error("シナリオ名を入力してください。")
                        else:
                            saved_count = upsert_csv_rows(
                                CARD_FILE,
                                scenario_rows_to_save,
                                ["アイドル", "P/S", "レア度", "カード名", "入手", "実装日"],
                                ["アイドル", "P/S", "実装日"],
                            )
                            st.success(f"{saved_count}件のシナリオ実装を保存しました。")
                            st.rerun()

            elif register_mode == "📝 楽曲の分類・歌詞・公式リンクを登録":
                st.subheader("📝 楽曲の分類・歌詞・公式リンクを登録")
                st.caption("曲名を選んで、分類・歌詞・YouTubeリンクを登録します。同じ曲・種別を登録し直すと内容を更新します。")
                song_entry_type = st.radio(
                    "登録する内容:",
                    ["楽曲区分", "歌詞", "公式音源", "音源バージョン", "MV", "ライブダイジェスト / XR冒頭無料"],
                    horizontal=True,
                )

                known_song_options = unique_in_registered_order(
                    df["集計用楽曲名"].dropna().tolist() if "集計用楽曲名" in df.columns else []
                )
                if song_entry_type == "ライブダイジェスト / XR冒頭無料":
                    with st.form("add_live_video_form"):
                        video_kind = st.radio("映像の種類:", ["ライブダイジェスト", "XR冒頭無料"], horizontal=True)
                        live_input_mode = st.radio("公演名:", ["公演マスターから選択", "手入力"], horizontal=True)
                        known_live_options = unique_in_registered_order(
                            event_df["公演名"].dropna().tolist() if 'event_df' in locals() and "公演名" in event_df.columns else []
                        )
                        if live_input_mode == "公演マスターから選択" and known_live_options:
                            media_live_name = st.selectbox("対象公演", known_live_options)
                        else:
                            media_live_name = st.text_input("対象公演 *")
                        media_url = st.text_input("YouTube URL *", placeholder="https://www.youtube.com/watch?v=...")
                        if st.form_submit_button("💾 公演映像リンクを保存", type="primary"):
                            if not media_live_name.strip() or not media_url.strip():
                                st.error("⚠️ 対象公演とYouTube URLを入力してください。")
                            else:
                                target_file = YOUTUBE_LIVE_DIGEST_FILE if video_kind == "ライブダイジェスト" else YOUTUBE_XR_INTRO_FILE
                                upsert_csv_row(
                                    target_file,
                                    {"対象公演": media_live_name.strip(), "種別": video_kind, "YouTube_URL": media_url.strip()},
                                    ["対象公演", "種別", "YouTube_URL"],
                                    ["対象公演", "種別"],
                                )
                                st.success("🎉 公演映像リンクを保存しました。")
                                st.rerun()
                else:
                    with st.form("add_song_detail_form"):
                        song_input_mode = st.radio("楽曲:", ["登録済みから選択", "手入力"], horizontal=True)
                        if song_input_mode == "登録済みから選択" and known_song_options:
                            detail_song_name = st.selectbox("楽曲名", known_song_options)
                        else:
                            detail_song_name = st.text_input("楽曲名 *")

                        if song_entry_type == "楽曲区分":
                            category_options = ["オリジナル", "合同", "カバー", "外部", "その他", "自由入力"]
                            selected_category = st.selectbox("楽曲区分", category_options)
                            detail_value = st.text_input("自由入力の区分") if selected_category == "自由入力" else selected_category
                        elif song_entry_type == "歌詞":
                            detail_value = st.text_area("歌詞 *", height=220, placeholder="歌詞を貼り付けてください")
                        else:
                            if song_entry_type in ["音源バージョン", "MV"]:
                                media_type = st.text_input("種別", value="公式音源" if song_entry_type == "音源バージョン" else "3DMV")
                                version_label = st.text_input("表示名（任意）", placeholder="例: 28人Ver. / 2DMV")
                            detail_value = st.text_input("YouTube URL *", placeholder="https://youtu.be/...")

                        if st.form_submit_button("💾 楽曲情報を保存", type="primary"):
                            if not detail_song_name.strip() or not detail_value.strip():
                                st.error("⚠️ 楽曲名と必須項目を入力してください。")
                            elif song_entry_type == "楽曲区分":
                                upsert_csv_row(CATEGORY_FILE, {"楽曲名": detail_song_name.strip(), "楽曲区分": detail_value.strip()}, ["楽曲名", "楽曲区分"], ["楽曲名"])
                                st.success("🎉 楽曲区分を保存しました。")
                                st.rerun()
                            elif song_entry_type == "歌詞":
                                upsert_csv_row(LYRICS_FILE, {"楽曲名": detail_song_name.strip(), "歌詞": detail_value.strip()}, ["楽曲名", "歌詞"], ["楽曲名"])
                                st.success("🎉 歌詞を保存しました。")
                                st.rerun()
                            elif song_entry_type == "公式音源":
                                upsert_csv_row(YOUTUBE_AUDIO_DRAFT_FILE, {"楽曲名": detail_song_name.strip(), "公式音源_URL": detail_value.strip()}, ["楽曲名", "公式音源_URL"], ["楽曲名"])
                                st.success("🎉 公式音源リンクを保存しました。")
                                st.rerun()
                            else:
                                target_file = YOUTUBE_AUDIO_VARIANTS_FILE if song_entry_type == "音源バージョン" else YOUTUBE_VIDEO_VARIANTS_FILE
                                upsert_csv_row(
                                    target_file,
                                    {"楽曲名": detail_song_name.strip(), "種別": media_type.strip(), "バージョン表示": version_label.strip(), "YouTube_URL": detail_value.strip()},
                                    ["楽曲名", "種別", "バージョン表示", "YouTube_URL"],
                                    ["楽曲名", "種別", "バージョン表示"],
                                )
                                st.success("🎉 動画・音源リンクを保存しました。")
                                st.rerun()

            elif register_mode == "🖼️ ジャケット情報を登録":
                st.subheader("🖼️ ジャケット情報を登録")
                st.caption("先に画像ファイルを album_jackets フォルダへ入れ、そのファイル名を指定します。同じアルバムでも、曲ごとに別ジャケットを指定できます。")
                with st.form("add_jacket_map_form"):
                    jacket_target_type = st.radio(
                        "ジャケットの使い方:",
                        ["アルバムの共通ジャケット", "この曲だけ別ジャケット"],
                        horizontal=True,
                    )
                    jacket_album_name = st.text_input("アルバム名 *")
                    jacket_song_name = ""
                    if jacket_target_type == "この曲だけ別ジャケット":
                        jacket_song_name = st.text_input("楽曲名 *")
                    jacket_file_name = st.text_input("画像ファイル名 *", placeholder="例: LACM-12345.jpg")
                    if st.form_submit_button("💾 ジャケット対応を保存", type="primary"):
                        required_song_name = jacket_target_type == "この曲だけ別ジャケット"
                        if not jacket_album_name.strip() or not jacket_file_name.strip() or (required_song_name and not jacket_song_name.strip()):
                            st.error("⚠️ 必須項目を入力してください。")
                        else:
                            if jacket_target_type == "この曲だけ別ジャケット":
                                upsert_csv_row(
                                    SONG_JACKET_FILE,
                                    {
                                        "楽曲名": jacket_song_name.strip(),
                                        "アルバム": jacket_album_name.strip(),
                                        "ジャケット画像ファイル": jacket_file_name.strip(),
                                    },
                                    ["楽曲名", "アルバム", "ジャケット画像ファイル"],
                                    ["楽曲名", "アルバム"],
                                )
                                st.success("🎉 この曲専用のジャケットを保存しました。")
                            else:
                                upsert_csv_row(
                                    JACKET_MAP_FILE,
                                    {"アルバム名": jacket_album_name.strip(), "ジャケット画像ファイル": jacket_file_name.strip()},
                                    ["アルバム名", "ジャケット画像ファイル"],
                                    ["アルバム名"],
                                )
                                st.success("🎉 アルバム共通ジャケットを保存しました。")
                            st.rerun()

            elif register_mode == "👥 出演・参加履歴をまとめて登録":
                st.subheader("👥 出演・参加履歴をまとめて登録")
                st.caption("まず全員の状態を決め、欠席・一部参加などの例外だけを選びます。全員分を1人ずつ入力する必要はありません。")

                current_attendance = (
                    load_csv(ATTENDANCE_FILE).fillna("")
                    if os.path.exists(ATTENDANCE_FILE) else pd.DataFrame()
                )
                attendance_cast_options = unique_in_registered_order(
                    (current_attendance["キャスト"].tolist() if "キャスト" in current_attendance.columns else [])
                    + cast_list
                )
                if not attendance_cast_options:
                    st.warning("参加履歴CSVまたはアイドルマスターからキャスト一覧を読み込めませんでした。")
                else:
                    attendance_event_choices = []
                    attendance_event_lookup = {}
                    if 'event_df' in locals() and not event_df.empty:
                        attendance_event_date_col = next((c for c in event_df.columns if "日付" in c), None)
                        attendance_event_title_col = next((c for c in event_df.columns if "公演" in c or "イベント" in c or "ライブ" in c), None)
                        attendance_event_venue_col = next((c for c in event_df.columns if "会場" in c), None)
                        if attendance_event_date_col and attendance_event_title_col:
                            for row in event_df.to_dict("records"):
                                event_title = clean_text(str(row[attendance_event_title_col]))
                                event_date = clean_text(str(row[attendance_event_date_col]))
                                event_venue = clean_text(str(row[attendance_event_venue_col])) if attendance_event_venue_col else ""
                                event_label = f"{event_date} ｜ {event_title}"
                                attendance_event_choices.append(event_label)
                                attendance_event_lookup[event_label] = (event_title, event_venue)

                    with st.form("bulk_attendance_form"):
                        input_method = st.radio(
                            "公演の指定方法:",
                            ["公演マスターから選択", "手入力"],
                            horizontal=True,
                        )
                        if input_method == "公演マスターから選択" and attendance_event_choices:
                            attendance_event_label = st.selectbox("公演:", attendance_event_choices)
                            attendance_event_name, attendance_venue = attendance_event_lookup[attendance_event_label]
                        else:
                            attendance_event_name = st.text_input("公演名 *")
                            attendance_venue = st.text_input("会場")

                        day_col, default_col = st.columns(2)
                        with day_col:
                            attendance_day = st.selectbox(
                                "日程・公演回:",
                                ["DAY1", "DAY2", "DAY3", "昼公演", "夜公演", "開催"],
                            )
                        with default_col:
                            default_attendance_status = st.selectbox(
                                "全員の初期状態:",
                                ["参加", "ユニット出演予定なし", "対象外"],
                                help="下の例外指定をした人だけ、ここで選んだ状態から変更されます。",
                            )

                        st.markdown("##### 例外だけ選択")
                        exception_statuses = [
                            "一部楽曲参加", "急遽不参加", "欠席", "サプライズ披露",
                            "ユニット出演予定なし", "対象外",
                        ]
                        exception_map = {}
                        status_columns = st.columns(2)
                        for index, status_name in enumerate(exception_statuses):
                            with status_columns[index % 2]:
                                exception_map[status_name] = st.multiselect(
                                    status_name,
                                    attendance_cast_options,
                                    key=f"attendance_exception_{status_name}",
                                )

                        st.markdown("##### 補足・追加参加決定日（任意）")
                        attendance_notes = st.text_area(
                            "1行ずつ「キャスト名 | 補足 | YYYY/MM/DD」で入力",
                            placeholder="例: 白石晴香 | 体調不良 |\n例: 河野ひより | 追加参加 | 2021/11/29",
                        )
                        replace_existing = st.checkbox(
                            "同じ公演・日程の既存参加履歴を置き換える",
                            value=True,
                        )

                        if st.form_submit_button("💾 この公演の参加履歴を保存", type="primary"):
                            if not attendance_event_name.strip():
                                st.error("⚠️ 公演名を入力してください。")
                            else:
                                status_by_cast = {
                                    cast_name: default_attendance_status
                                    for cast_name in attendance_cast_options
                                }
                                for status_name, selected_casts in exception_map.items():
                                    for cast_name in selected_casts:
                                        status_by_cast[cast_name] = status_name

                                note_map = {}
                                for note_line in attendance_notes.splitlines():
                                    note_parts = [part.strip() for part in re.split(r"[|｜]", note_line)]
                                    if note_parts and note_parts[0]:
                                        note_map[note_parts[0]] = {
                                            "補足": note_parts[1] if len(note_parts) > 1 else "",
                                            "追加参加決定日": note_parts[2] if len(note_parts) > 2 else "",
                                        }

                                new_attendance_rows = [
                                    {
                                        "公演名": clean_live_name(attendance_event_name.strip()),
                                        "日程": attendance_day,
                                        "会場": attendance_venue.strip(),
                                        "キャスト": cast_name,
                                        "参加状況": status_by_cast[cast_name],
                                        "追加参加決定日": note_map.get(cast_name, {}).get("追加参加決定日", ""),
                                        "補足": note_map.get(cast_name, {}).get("補足", ""),
                                        "判定元": "アプリ入力",
                                    }
                                    for cast_name in attendance_cast_options
                                ]
                                expected_columns = [
                                    "公演名", "日程", "会場", "キャスト", "参加状況",
                                    "追加参加決定日", "補足", "判定元",
                                ]
                                if current_attendance.empty:
                                    updated_attendance = pd.DataFrame(columns=expected_columns)
                                else:
                                    updated_attendance = current_attendance.copy()
                                if replace_existing and {"公演名", "日程"}.issubset(updated_attendance.columns):
                                    updated_attendance = updated_attendance[
                                        ~(
                                            (updated_attendance["公演名"] == clean_live_name(attendance_event_name.strip()))
                                            & (updated_attendance["日程"] == attendance_day)
                                        )
                                    ]
                                save_dataframe(
                                    pd.concat(
                                        [updated_attendance, pd.DataFrame(new_attendance_rows)],
                                        ignore_index=True,
                                    ).reindex(columns=expected_columns),
                                    ATTENDANCE_FILE,
                                    create_backup=True,
                                )
                                st.success(f"{attendance_day}分の {len(new_attendance_rows)} 人を保存しました。")
                                st.rerun()

            elif register_mode == "🗃️ 全CSVを追加・編集":
                st.subheader("🗃️ 全CSVを追加・編集")
                st.caption("対象のCSVを選んで、行の追加・既存データの修正・削除ができます。保存時には同じフォルダにバックアップを自動作成します。")

                csv_targets = {
                    "🎤 セットリスト（songs.csv）": SETLIST_FILE,
                    "🏟️ 公演マスター（events.csv）": EVENT_MASTER_FILE,
                    "👥 アイドル・キャスト（idols.csv）": IDOL_MASTER_FILE,
                    "👗 衣装マスター（costumes.csv）": COSTUME_MASTER_FILE,
                    "💿 アルバム（albums.csv）": ALBUM_MASTER_FILE,
                    "🎼 楽曲×アルバム（songs_albums.csv）": SONG_ALBUM_FILE,
                    "🏷️ 楽曲区分（songs_categories.csv）": CATEGORY_FILE,
                    "📝 歌詞（lyrics.csv）": LYRICS_FILE,
                    "📅 出演・参加履歴（cast_attendance.csv）": ATTENDANCE_FILE,
                    "📺 公式番組・配信履歴（broadcasts.csv）": BROADCAST_FILE,
                    "🃏 カード実装履歴（cards.tsv）": CARD_FILE,
                    "📻 シャニラジ出演履歴（shiny_radio_appearances.csv）": RADIO_APPEARANCE_FILE,
                    "📻 シャニラジ各回データ（shiny_radio_episodes.tsv）": RADIO_EPISODE_FILE,
                    "🎙️ オーコメ担当・Blu-ray版": COMMENTARY_BD_FILE,
                    "🎙️ オーコメ担当・配信版": COMMENTARY_STREAM_FILE,
                    "🖼️ ジャケット情報（release_jackets.csv）": JACKET_MAP_FILE,
                    "🖼️ 曲別ジャケット（song_jackets.csv）": SONG_JACKET_FILE,
                    "▶️ 公式音源リンク": YOUTUBE_AUDIO_DRAFT_FILE,
                    "🎵 音源バージョン別リンク": YOUTUBE_AUDIO_VARIANTS_FILE,
                    "🎵 Migratory Echoes・収録盤別音源": MIGRATORY_ECHOES_MEDIA_FILE,
                    "🎬 MVリンク": YOUTUBE_VIDEO_VARIANTS_FILE,
                    "🎬 ユニット・企画PVリンク": YOUTUBE_UNIT_PV_FILE,
                    "📻 シャニラジ切り抜きリンク": YOUTUBE_RADIO_CLIP_FILE,
                    "📡 公演AP生配信リンク": YOUTUBE_LIVE_AP_STREAM_FILE,
                    "🎉 周年PVリンク": YOUTUBE_ANNIVERSARY_PV_FILE,
                    "🎨 公演公式告知・ビジュアルリンク": EVENT_SOCIAL_LINKS_FILE,
                    "🎥 ライブダイジェスト": YOUTUBE_LIVE_DIGEST_FILE,
                    "🕶️ XR冒頭無料映像": YOUTUBE_XR_INTRO_FILE,
                    "🌐 公演公式サイト": EVENT_OFFICIAL_SITE_FILE,
                    "💴 価格推移（price_history.csv）": PRICE_HISTORY_FILE,
                }
                available_csv_targets = {
                    label: path for label, path in csv_targets.items() if path and os.path.exists(path)
                }
                selected_csv_label = st.selectbox(
                    "編集するCSVを選択:",
                    list(available_csv_targets.keys()),
                    key="tab7_csv_target",
                )
                selected_csv_path = available_csv_targets[selected_csv_label]
                selected_csv_df = load_csv(selected_csv_path).fillna("")

                st.caption(f"{os.path.basename(selected_csv_path)} ｜ {len(selected_csv_df):,} 行 ｜ {len(selected_csv_df.columns)} 列")
                edited_csv_df = st.data_editor(
                    selected_csv_df,
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    key=f"csv_editor_{make_search_key(os.path.basename(selected_csv_path))}",
                )
                st.warning("保存すると、選択中CSVの内容全体がこの表の内容に置き換わります。")
                if st.button("💾 このCSVへ保存", key="save_selected_csv", type="primary"):
                    backup_path = save_dataframe(
                        edited_csv_df,
                        selected_csv_path,
                        create_backup=True,
                    )
                    st.success(
                        f"保存しました。バックアップ: {os.path.basename(backup_path)}"
                    )
                    st.rerun()

    # TAB 8: 公演セットリスト分析
    with tab8:
        render_page_header(
            "🏟️",
            "公演セットリスト・前回披露分析",
            "公演ごとの構成、各曲の前回披露からの間隔、公式ダイジェストを一画面で確認できます。",
        )

        if not live_col_name:
            st.warning("⚠️ 公演名の列が見つかりません。")
        else:
            event_catalog = df[[live_col_name, "日付_dt", "公演区分"]].drop_duplicates(
                subset=[live_col_name], keep="first"
            )
            event_catalog = event_catalog.sort_values(
                ["日付_dt", live_col_name],
                ascending=[False, True],
                kind="stable",
                na_position="last",
            )
            filter_col1, filter_col2 = st.columns(2)
            available_event_years = sorted(
                event_catalog["日付_dt"].dropna().dt.year.unique().tolist(), reverse=True
            )
            available_event_categories = unique_in_registered_order(
                event_catalog["公演区分"].fillna("未分類").astype(str).tolist()
            )
            if "tab8_event_year_filter" not in st.session_state:
                st.session_state["tab8_event_year_filter"] = set(available_event_years)
            if "tab8_event_category_filter" not in st.session_state:
                st.session_state["tab8_event_category_filter"] = set(available_event_categories)

            # 年・区分は多数選択のプルダウンではなく、押して切り替えるボタンにする。
            with filter_col1:
                st.caption("開催年で絞り込み")
                active_years = set(st.session_state["tab8_event_year_filter"])
                year_buttons = st.columns(min(4, max(len(available_event_years), 1)))
                for index, year in enumerate(available_event_years):
                    is_active = year in active_years
                    if year_buttons[index % len(year_buttons)].button(
                        str(year),
                        key=f"tab8_year_{year}",
                        type="primary" if is_active else "secondary",
                        use_container_width=True,
                    ):
                        if is_active:
                            active_years.discard(year)
                        else:
                            active_years.add(year)
                        st.session_state["tab8_event_year_filter"] = active_years
                        st.rerun()
                selected_event_years = [year for year in available_event_years if year in active_years]
            with filter_col2:
                st.caption("公演区分で絞り込み")
                active_categories = set(st.session_state["tab8_event_category_filter"])
                category_buttons = st.columns(min(3, max(len(available_event_categories), 1)))
                for index, category in enumerate(available_event_categories):
                    is_active = category in active_categories
                    if category_buttons[index % len(category_buttons)].button(
                        category,
                        key=f"tab8_category_{category}",
                        type="primary" if is_active else "secondary",
                        use_container_width=True,
                    ):
                        if is_active:
                            active_categories.discard(category)
                        else:
                            active_categories.add(category)
                        st.session_state["tab8_event_category_filter"] = active_categories
                        st.rerun()
                selected_event_categories = [
                    category for category in available_event_categories if category in active_categories
                ]
            event_catalog = event_catalog[
                event_catalog["日付_dt"].dt.year.isin(selected_event_years)
            ]
            event_catalog = event_catalog[
                event_catalog["公演区分"].fillna("未分類").astype(str).isin(selected_event_categories)
            ]
            event_options = []
            event_lookup = {}
            for event_row in event_catalog.to_dict("records"):
                event_date = event_row["日付_dt"]
                date_label = event_date.strftime("%Y/%m/%d") if pd.notna(event_date) else "日付不明"
                category_label = str(event_row["公演区分"]) if pd.notna(event_row["公演区分"]) else "未分類"
                event_label = f"{date_label} ｜ {category_label} ｜ {event_row[live_col_name]}"
                event_options.append(event_label)
                event_lookup[event_label] = event_row[live_col_name]

            if not event_options:
                st.info("分析できる公演がありません。")
            else:
                selected_event_label = st.selectbox(
                    "分析する公演を選択:",
                    event_options,
                    key="tab8_selected_event",
                )
                selected_event = event_lookup[selected_event_label]
                event_setlist_df = df[df[live_col_name] == selected_event].copy()

                if "曲順" in event_setlist_df.columns:
                    event_setlist_df["_sort_order"] = pd.to_numeric(
                        event_setlist_df["曲順"], errors="coerce"
                    )
                    event_setlist_df = event_setlist_df.sort_values(
                        by="_sort_order", kind="stable", na_position="last"
                    )

                selected_event_date = event_setlist_df["日付_dt"].dropna().iloc[0] if event_setlist_df["日付_dt"].notna().any() else pd.NaT
                selected_event_date_label = (
                    selected_event_date.strftime("%Y/%m/%d")
                    if pd.notna(selected_event_date) else "日付不明"
                )
                selected_event_category = str(event_setlist_df["公演区分"].iloc[0])
                st.markdown(
                    "<div class='analysis-target-card'>"
                    "<div class='analysis-target-label'>🎯 分析対象の公演</div>"
                    f"<div class='analysis-target-title'>{html.escape(str(selected_event))}</div>"
                    f"<div class='analysis-target-meta'>{html.escape(selected_event_date_label)}"
                    f"　｜　{html.escape(selected_event_category)}　｜　{len(event_setlist_df)}曲</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )

                render_event_context_images(str(selected_event))

                # 略称（例: 5thDAY2 / 6th大阪DAY1）を現在の公演名と照合する。
                def is_commentary_for_event(shorthand, event_name):
                    # 空白・引用符・記号の表記ゆれを除いて照合する。
                    shorthand_key = re.sub(r"[\W_]+", "", str(shorthand), flags=re.UNICODE).lower()
                    event_key = re.sub(r"[\W_]+", "", str(event_name), flags=re.UNICODE).lower()
                    day_tokens = re.findall(r"day\d+", shorthand_key)
                    # DAY番号だけでは別公演にも一致してしまうため、必ず公演を識別する部分を照合する。
                    identity_key = re.sub(r"day\d+", "", shorthand_key).strip()
                    if not identity_key or identity_key not in event_key:
                        return False
                    return all(token in event_key for token in day_tokens)

                if not commentary_df.empty:
                    selected_commentary_df = commentary_df[
                        commentary_df["公演略称"].apply(
                            lambda shorthand: is_commentary_for_event(shorthand, selected_event)
                        )
                    ]
                    if not selected_commentary_df.empty:
                        st.subheader("🎙️ オーディオコメンタリー担当")
                        commentary_columns = st.columns(2)
                        for index, commentary_type in enumerate(["Blu-ray版", "配信版"]):
                            selected_type_df = selected_commentary_df[
                                selected_commentary_df["種別"] == commentary_type
                            ]
                            with commentary_columns[index]:
                                st.markdown(f"**{commentary_type}**")
                                if selected_type_df.empty:
                                    st.caption("担当情報なし")
                                else:
                                    st.write("・" + "\n・".join(selected_type_df["キャスト"].tolist()))

                official_site_urls = find_event_official_site_urls(
                    selected_event,
                    event_official_site_df,
                )
                if official_site_urls:
                    official_site_columns = st.columns(min(3, len(official_site_urls)))
                    for official_site_index, official_site_url in enumerate(official_site_urls):
                        official_site_columns[official_site_index].link_button(
                            "🌐 公演公式サイトを開く",
                            official_site_url,
                            use_container_width=True,
                        )

                event_social_links = find_event_social_links(
                    selected_event,
                    event_social_links_df,
                )
                if event_social_links and not PUBLIC_MODE:
                    st.caption("🎨 公式告知・ビジュアル")
                    social_columns = st.columns(min(4, len(event_social_links)))
                    for social_index, social_link in enumerate(event_social_links):
                        social_columns[social_index % len(social_columns)].link_button(
                            f"𝕏 {social_link['種別']}",
                            social_link["URL"],
                            use_container_width=True,
                        )

                event_media_options = build_event_media_options(
                    selected_event,
                    youtube_live_digest_df,
                    youtube_xr_intro_df,
                )
                ap_stream_options = build_event_media_options(
                    selected_event,
                    pd.DataFrame(),
                    pd.DataFrame(),
                    youtube_live_ap_stream_df,
                )
                if event_media_options:
                    st.subheader("🎬 公式ライブ映像")
                    if st.checkbox(
                        "映像を見る",
                        key=f"tab8_show_media_{make_search_key(selected_event)}",
                    ):
                        selected_event_media_index = st.selectbox(
                            "視聴する公演映像を選択:",
                            range(len(event_media_options)),
                            format_func=lambda index: event_media_options[index]["表示"],
                            key=f"tab8_media_{make_search_key(selected_event)}",
                        )
                        selected_event_media = event_media_options[selected_event_media_index]
                        render_compact_youtube(
                            selected_event_media["URL"],
                            selected_event_media["表示"],
                            compact=False,
                        )
                        st.caption(f"{selected_event_media['種別']}｜公式YouTubeの埋め込みです。")
                        st.link_button("YouTubeで開く", selected_event_media["URL"])

                if ap_stream_options:
                    st.subheader("📡 AP生配信")
                    if st.checkbox(
                        "AP生配信を表示する",
                        key=f"tab8_show_ap_stream_{make_search_key(selected_event)}",
                    ):
                        selected_ap_stream_index = st.selectbox(
                            "視聴するAP生配信を選択:",
                            range(len(ap_stream_options)),
                            format_func=lambda index: ap_stream_options[index]["表示"],
                            key=f"tab8_ap_stream_{make_search_key(selected_event)}",
                        )
                        selected_ap_stream = ap_stream_options[selected_ap_stream_index]
                        render_compact_youtube(
                            selected_ap_stream["URL"],
                            selected_ap_stream["表示"],
                            compact=False,
                        )
                        st.caption("AP生配信｜公式YouTubeの埋め込みです。")
                        st.link_button("YouTubeで開く", selected_ap_stream["URL"])

                series_col = (
                    next((c for c in album_master_df.columns if "シリーズ" in c), None)
                    if not album_master_df.empty else None
                )
                alb_col = (
                    next((c for c in album_master_df.columns if "アルバム" in c or "CD" in c), None)
                    if not album_master_df.empty else None
                )
                song_alb_col = (
                    next((c for c in song_album_df.columns if "アルバム" in c or "CD" in c), None)
                    if not song_album_df.empty else None
                )
                song_to_series = {}
                if song_alb_col and alb_col and series_col:
                    song_to_series = build_song_series_map(
                        song_album_df,
                        album_master_df,
                        song_alb_col,
                        alb_col,
                        series_col,
                    )

                event_setlist_df["アルバムシリーズ"] = event_setlist_df["search_key"].map(
                    lambda key: song_to_series.get(key, "その他/未登録")
                )
                series_counts = (
                    event_setlist_df["アルバムシリーズ"]
                    .value_counts(sort=False)
                    .rename_axis("アルバムシリーズ")
                    .reset_index(name="曲数（実数）")
                )
                series_counts = series_counts.sort_values(
                    ["曲数（実数）", "アルバムシリーズ"],
                    ascending=[False, True],
                    kind="stable",
                ).reset_index(drop=True)

                chart_col, count_col = st.columns([1.2, 1])
                with chart_col:
                    st.subheader("📈 アルバムシリーズ比率")
                    pie_fig = px.pie(
                        series_counts,
                        values="曲数（実数）",
                        names="アルバムシリーズ",
                        hole=0.45,
                        color_discrete_sequence=["#7b5cff", "#51c2f0", "#ff85a1", "#a0e0ff", "#d8b4fe", "#f472b6", "#38bdf8"],
                    )
                    pie_fig.update_traces(
                        sort=False,
                        textposition="inside",
                        texttemplate="%{percent}",
                        hovertemplate="<b>%{label}</b><br>曲数: %{value}曲<br>割合: %{percent}<extra></extra>",
                    )
                    pie_fig.update_layout(
                        height=540,
                        margin=dict(l=16, r=16, t=20, b=105),
                        legend=dict(
                            orientation="h",
                            x=0.5,
                            y=-0.12,
                            xanchor="center",
                            yanchor="top",
                        ),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font_color="#2c2c54",
                    )
                    render_analysis_chart(pie_fig, key="tab8_event_series_pie")

                with count_col:
                    st.subheader("🔢 シリーズ別実数")
                    series_counts["割合 (%)"] = (
                        series_counts["曲数（実数）"] / len(event_setlist_df) * 100
                    ).round(1).astype(str) + "%"
                    series_counts.index = series_counts.index + 1
                    st.dataframe(series_counts, use_container_width=True)

                prior_history_by_song = {}
                if pd.notna(selected_event_date):
                    prior_history = full_analysis_df[
                        full_analysis_df["日付_dt"].notna()
                        & (full_analysis_df["日付_dt"] < selected_event_date)
                    ].sort_values("日付_dt", kind="stable")
                    prior_history = prior_history.drop_duplicates(
                        "search_key",
                        keep="last",
                    )
                    prior_history_by_song = {
                        row["search_key"]: row
                        for row in prior_history.to_dict("records")
                    }

                previous_rows = []
                for song_row in event_setlist_df.to_dict("records"):
                    previous_row = prior_history_by_song.get(song_row["search_key"])
                    if previous_row is None:
                        previous_date = "初披露 / データなし"
                        previous_live = "-"
                        interval = "-"
                    else:
                        previous_date = previous_row["日付_dt"].strftime("%Y/%m/%d")
                        previous_live = str(previous_row[live_col_name])
                        interval_days = (selected_event_date - previous_row["日付_dt"]).days
                        interval = f"{format_days_ago(interval_days)}（{interval_days}日）"

                    previous_rows.append(
                        {
                            "曲順": song_row.get("曲順", ""),
                            "楽曲名": song_row.get("楽曲名", ""),
                            "ユニット": song_row.get("ユニット", ""),
                            "歌唱者": song_row.get("歌唱者", ""),
                            "衣装": song_row.get("衣装", ""),
                            "アルバムシリーズ": song_row["アルバムシリーズ"],
                            "前回披露日": previous_date,
                            "前回披露公演": previous_live,
                            "前回披露からの間隔": interval,
                        }
                    )

                st.markdown("---")
                st.subheader("📜 セットリストと前回披露との間隔")
                previous_display_df = pd.DataFrame(previous_rows)
                previous_display_df.index = previous_display_df.index + 1
                st.dataframe(
                    previous_display_df,
                    use_container_width=True,
                    column_config={
                        "前回披露公演": st.column_config.TextColumn("前回披露公演", width="large"),
                        "楽曲名": st.column_config.TextColumn("楽曲名", width="large"),
                    },
                )

    # TAB 9: 出演・参加履歴
    with tab9:
        render_page_header(
            "👥",
            "出演・参加履歴",
            "キャスト別の参加状況と、公演ごとの出演予定・欠席・追加参加を確認できます。",
        )
        st.caption("水色＝参加、緑＝一部楽曲参加、赤＝急遽不参加、薄黄色＝ユニット出演予定なし、紫＝欠席、黄色＝サプライズ披露")

        if attendance_df.empty:
            st.info("`cast_attendance.csv` をアプリと同じフォルダに置くと、参加履歴を表示できます。")
        else:
            attendance_status_colors = {
                "参加": "#bff6f6",
                "一部楽曲参加": "#bdf5b7",
                "急遽不参加": "#ffc2c2",
                "ユニット出演予定なし": "#fff0bd",
                "欠席": "#d8b8ff",
                "サプライズ披露": "#fff35c",
                "空欄": "#f4f4f4",
            }

            attendance_clean_df = attendance_df.copy().fillna("")
            # 「対象外」は履歴の読みやすさを損ねるため、通常表示から除外する。
            attendance_clean_df = attendance_clean_df[
                attendance_clean_df["参加状況"].astype(str) != "対象外"
            ].copy()
            attendance_clean_df["所属ユニット"] = attendance_clean_df["キャスト"].map(
                lambda cast_name: idol_to_unit_map.get(str(cast_name), "その他")
            )

            def unit_cell_style(unit_name):
                """公式ユニットカラーを表に使いつつ、文字の可読性を保つ。"""
                color = display_group_color(unit_name)
                background = display_group_background(unit_name)
                if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                    return ""
                red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
                brightness = (red * 299 + green * 587 + blue * 114) / 1000
                text_color = "#20243d" if brightness > 165 else "#ffffff"
                style = f"background-color: {color}; color: {text_color}; font-weight: 700;"
                if background != color:
                    style += f" background-image: {background};"
                return style

            for empty_col in ["追加参加決定日", "補足"]:
                if empty_col in attendance_clean_df.columns:
                    attendance_clean_df[empty_col] = attendance_clean_df[empty_col].replace({"None": "", "nan": ""})

            def attendance_event_key(value):
                """公演名の引用符・記号・全半角の違いを無視して照合する。"""
                value = clean_live_name(str(value)).lower()
                # 公演マスター側に付いている DAY1 / DAY2 は、公演そのものを
                # 判定する際には無視する（出演履歴では別列「日程」で管理している）。
                value = re.sub(r"\bday\s*[0-9０-９]+\b", "", value, flags=re.IGNORECASE)
                return re.sub(r"[^\w]", "", value, flags=re.UNICODE)

            def attendance_day_order(value):
                """同一公演内では DAY1 → DAY2 の順に必ず並べる。"""
                match = re.search(r"day\s*([0-9０-９]+)", str(value), flags=re.IGNORECASE)
                if match:
                    return int(match.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789")))
                return 999

            # CSVの追加順ではなく、公演マスターの開催日で一貫して並べる
            attendance_clean_df["_event_date"] = pd.NaT
            event_date_sources = []
            if 'event_df' in locals() and not event_df.empty:
                event_date_col = next((c for c in event_df.columns if "日付" in c), None)
                event_title_col = next((c for c in event_df.columns if "公演" in c or "イベント" in c or "ライブ" in c), None)
                if event_date_col and event_title_col:
                    event_date_sources.append(
                        event_df[[event_date_col, event_title_col]].rename(
                            columns={event_date_col: "_event_date", event_title_col: "_event_title"}
                        )
                    )
            # 公演マスターに表記違いがある場合でも、セットリストの実施日を予備の
            # 開催日として使う。これで DAY1 / DAY2 が別公演に挟まらない。
            if live_col_name and "日付_dt" in df.columns:
                event_date_sources.append(
                    df[["日付_dt", live_col_name]].rename(
                        columns={"日付_dt": "_event_date", live_col_name: "_event_title"}
                    )
                )
            if event_date_sources:
                event_sort_df = pd.concat(event_date_sources, ignore_index=True).dropna().copy()
                event_sort_df["_event_date"] = pd.to_datetime(event_sort_df["_event_date"], errors="coerce")
                event_sort_df = event_sort_df.dropna(subset=["_event_date"])
                event_sort_df["_event_key"] = event_sort_df["_event_title"].map(attendance_event_key)
                event_dates = {}
                for attendance_event in attendance_clean_df["公演名"].dropna().unique():
                    attendance_key = attendance_event_key(attendance_event)
                    exact_dates = event_sort_df.loc[
                        event_sort_df["_event_key"] == attendance_key, "_event_date"
                    ]
                    matched_dates = exact_dates if not exact_dates.empty else event_sort_df.loc[
                        event_sort_df["_event_key"].apply(
                            lambda key: attendance_key in key or key in attendance_key
                        ), "_event_date"
                    ]
                    if not matched_dates.empty:
                        event_dates[attendance_event] = matched_dates.min()
                attendance_clean_df["_event_date"] = attendance_clean_df["公演名"].map(event_dates)

            attendance_clean_df["_event_date"] = pd.to_datetime(
                attendance_clean_df["_event_date"], errors="coerce"
            )
            # 斑鳩ルカ（川口莉奈）は 5.5th Anniversary LIVE からコメティックへ加入。
            # それ以前の参加履歴は、現在の所属ではなく「ソロ」と表示する。
            def event_specific_unit_column(event_name):
                """通常ユニットではない、公演固有のチーム編成を選ぶ。"""
                name = clean_live_name(str(event_name)).lower()
                if "master showpiece" in name:
                    return "-Master ShowPiece-"
                if "refrac7ions" in name or "still blue" in name:
                    return "PJ: REFRAC7IONS"
                if "シャニマス大感謝祭" in name or "283スポーツフェスティバル" in name:
                    return "Team."
                return ""

            def attendance_unit_at_event(row):
                cast_name = str(row.get("キャスト", ""))
                event_date = row.get("_event_date")
                special_column = event_specific_unit_column(row.get("公演名", ""))
                if special_column:
                    special_unit = group_member_map_by_column.get(special_column, {}).get(cast_name)
                    if special_unit:
                        return special_unit
                if cast_name in {"川口莉奈", "斑鳩ルカ"} and pd.notna(event_date):
                    if event_date < pd.Timestamp("2023-10-21"):
                        return "ソロ"
                return idol_to_unit_map.get(cast_name, "その他")

            attendance_clean_df["所属ユニット"] = attendance_clean_df.apply(
                attendance_unit_at_event, axis=1
            )
            # ユニットとして出演しない予定の記録では、所属欄を表示しない。
            attendance_clean_df.loc[
                attendance_clean_df["参加状況"].astype(str).str.contains("ユニット出演予定なし", na=False),
                "所属ユニット",
            ] = ""
            attendance_clean_df["_event_group"] = attendance_clean_df["公演名"].map(attendance_event_key)
            attendance_clean_df["_day_order"] = attendance_clean_df["日程"].map(attendance_day_order)
            attendance_clean_df = attendance_clean_df.sort_values(
                ["_event_date", "_event_group", "_day_order"], na_position="last"
            )
            attendance_casts = unique_in_registered_order(attendance_clean_df["キャスト"].tolist())
            attendance_events = unique_in_registered_order(attendance_clean_df["公演名"].tolist())

            cast_view, event_view, calendar_view = st.tabs(
                ["👤 キャスト別", "🏟️ 公演別", "🗓️ 公演カレンダー"]
            )

            with cast_view:
                selected_attendance_cast = st.selectbox(
                    "キャストを選択:",
                    attendance_casts,
                    key="tab9_attendance_cast",
                )
                cast_attendance = attendance_clean_df[
                    attendance_clean_df["キャスト"] == selected_attendance_cast
                ].copy().sort_values(
                    ["_event_date", "_event_group", "_day_order"], na_position="last"
                )
                count_cols = st.columns(3)
                count_cols[0].metric("参加", int((cast_attendance["参加状況"] == "参加").sum()))
                count_cols[1].metric("一部参加", int((cast_attendance["参加状況"] == "一部楽曲参加").sum()))
                count_cols[2].metric(
                    "欠席（急遽不参加を含む）",
                    int(cast_attendance["参加状況"].isin(["欠席", "急遽不参加"]).sum()),
                )

                cast_history_columns = [
                    col for col in ["公演名", "日程", "所属ユニット", "参加状況", "追加参加決定日", "補足"]
                    if col in cast_attendance.columns
                ]
                cast_history = cast_attendance[cast_history_columns].copy()
                st.subheader(f"📅 {selected_attendance_cast}さんの参加履歴")
                render_unit_color_badges(cast_history["所属ユニット"].tolist())
                st.dataframe(
                    cast_history.style.map(
                        lambda value: f"background-color: {attendance_status_colors.get(value, '#ffffff')};"
                        if value in attendance_status_colors else "",
                        subset=["参加状況"],
                    ).map(unit_cell_style, subset=["所属ユニット"]),
                    use_container_width=True,
                    hide_index=True,
                    height=520,
                    column_config={
                        "公演名": st.column_config.TextColumn("公演名", width="large"),
                        "参加状況": st.column_config.TextColumn("参加状況", width="medium"),
                    },
                )

            with event_view:
                selected_attendance_event = st.selectbox(
                    "公演を選択:",
                    attendance_events,
                    key="tab9_attendance_event",
                )
                event_attendance = attendance_clean_df[
                    attendance_clean_df["公演名"] == selected_attendance_event
                ].copy()
                st.caption("表示する参加状況（ボタンで切り替え）")
                status_options = ["参加", "一部楽曲参加", "急遽不参加", "ユニット出演予定なし", "欠席", "サプライズ披露"]
                status_buttons = st.columns(len(status_options))
                visible_statuses = []
                for index, status_name in enumerate(status_options):
                    with status_buttons[index]:
                        if st.checkbox(
                            status_name,
                            value=status_name != "ユニット出演予定なし",
                            key=f"tab9_status_button_{status_name}",
                        ):
                            visible_statuses.append(status_name)
                if visible_statuses:
                    event_attendance = event_attendance[event_attendance["参加状況"].isin(visible_statuses)]
                # pivot_table は標準ではユニット名を五十音順に並べるため、
                # アイドルマスターに登録された順番を明示的に使う。
                registered_unit_order = unique_in_registered_order(
                    [idol_to_unit_map.get(cast_name, "その他") for cast_name in cast_list]
                )
                if "その他" not in registered_unit_order:
                    registered_unit_order.append("その他")
                unit_sort_order = {unit_name: index for index, unit_name in enumerate(registered_unit_order)}
                cast_sort_order = {cast_name: index for index, cast_name in enumerate(cast_list)}
                event_attendance["_unit_sort"] = event_attendance["所属ユニット"].map(unit_sort_order).fillna(len(unit_sort_order))
                event_attendance["_cast_sort"] = event_attendance["キャスト"].map(cast_sort_order).fillna(len(cast_sort_order))
                event_attendance = event_attendance.sort_values(
                    ["_unit_sort", "_cast_sort", "_day_order"], kind="stable"
                )
                st.subheader("🏟️ 公演ごとの出演状況")
                render_unit_color_badges(event_attendance["所属ユニット"].tolist())
                day_order = unique_in_registered_order(event_attendance["日程"].astype(str).tolist())
                if day_order:
                    parallel_attendance = event_attendance.pivot_table(
                        index=["所属ユニット", "キャスト"],
                        columns="日程",
                        values="参加状況",
                        aggfunc="first",
                        fill_value="",
                        sort=False,
                    ).reindex(columns=day_order, fill_value="").reset_index()
                    st.caption("DAYごとに横並びで確認できます。")
                    st.dataframe(
                        parallel_attendance.style.map(
                            lambda value: f"background-color: {attendance_status_colors.get(value, '#ffffff')};"
                            if value in attendance_status_colors else "",
                            subset=day_order,
                        ).map(unit_cell_style, subset=["所属ユニット"]),
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "所属ユニット": st.column_config.TextColumn("所属ユニット", width="medium"),
                            "キャスト": st.column_config.TextColumn("キャスト", width="medium"),
                        },
                    )
                event_columns = [
                    col for col in ["日程", "所属ユニット", "キャスト", "参加状況", "追加参加決定日", "補足"]
                    if col in event_attendance.columns
                ]
                st.dataframe(
                    event_attendance[event_columns].style.map(
                        lambda value: f"background-color: {attendance_status_colors.get(value, '#ffffff')};"
                        if value in attendance_status_colors else "",
                        subset=["参加状況"],
                    ).map(unit_cell_style, subset=["所属ユニット"]),
                    use_container_width=True,
                    hide_index=True,
                    height=560,
                    column_config={
                        "所属ユニット": st.column_config.TextColumn("所属ユニット", width="medium"),
                        "キャスト": st.column_config.TextColumn("キャスト", width="medium"),
                        "参加状況": st.column_config.TextColumn("参加状況", width="medium"),
                    },
                )

            with calendar_view:
                st.caption("公演マスターに日付が登録されている公演を、月ごとに表示します。")
                calendar_events = []
                if 'event_df' in locals() and not event_df.empty:
                    event_date_col = next((c for c in event_df.columns if "日付" in c), None)
                    event_title_col = next((c for c in event_df.columns if "公演" in c or "イベント" in c or "ライブ" in c), None)
                    if event_date_col and event_title_col:
                        event_dates = event_df[[event_date_col, event_title_col]].dropna().copy()
                        event_dates["_date"] = pd.to_datetime(event_dates[event_date_col], errors="coerce")
                        event_dates = event_dates.dropna(subset=["_date"])
                        for event_name in attendance_events:
                            event_key = attendance_event_key(event_name)
                            matched_events = event_dates[
                                event_dates[event_title_col].apply(
                                    lambda title: event_key in attendance_event_key(title)
                                    or attendance_event_key(title) in event_key
                                )
                            ]
                            if not matched_events.empty:
                                for event_date in matched_events["_date"].drop_duplicates().tolist():
                                    calendar_events.append({"日付": event_date, "公演名": event_name})

                calendar_events_df = pd.DataFrame(calendar_events).drop_duplicates()
                if calendar_events_df.empty:
                    st.info("`events.csv` の公演名と日付が一致する公演から、ここにカレンダーを表示します。")
                else:
                    calendar_events_df["月"] = calendar_events_df["日付"].dt.strftime("%Y年%m月")
                    month_options = unique_in_registered_order(calendar_events_df["月"].tolist())
                    selected_month = st.selectbox("表示する月:", month_options, index=len(month_options) - 1)
                    month_events = calendar_events_df[calendar_events_df["月"] == selected_month]
                    display_date = month_events["日付"].iloc[0]
                    cal = calendar.Calendar(firstweekday=6)
                    weekdays = ["日", "月", "火", "水", "木", "金", "土"]
                    header_cols = st.columns(7)
                    for index, weekday in enumerate(weekdays):
                        header_cols[index].markdown(f"**{weekday}**")
                    for week in cal.monthdatescalendar(display_date.year, display_date.month):
                        day_cols = st.columns(7)
                        for index, day in enumerate(week):
                            with day_cols[index]:
                                if day.month != display_date.month:
                                    st.caption("")
                                    continue
                                st.markdown(f"**{day.day}**")
                                day_events = month_events[
                                    month_events["日付"].dt.date == day
                                ]["公演名"].tolist()
                                for event_name in day_events:
                                    st.markdown(
                                        f"<div style='font-size:0.78rem; padding:5px; margin:3px 0; "
                                        f"border-radius:7px; background:#e8ddff; color:#342b68; word-break:break-word;'>"
                                        f"{event_name}</div>",
                                        unsafe_allow_html=True,
                                    )

    if not PUBLIC_MODE:
        # TAB 10: 歌詞キーワード検索
        with tab10:
            render_page_header(
                "📚" if PUBLIC_MODE else "📝",
                "楽曲情報" if PUBLIC_MODE else "歌詞キーワード検索",
                "公開版では歌詞本文を掲載せず、楽曲データと公式リンクを案内します。" if PUBLIC_MODE else "言葉・関連する英語表現から歌詞を探し、該当箇所を色付きで確認できます。",
            )

            if PUBLIC_MODE:
                st.info("公開版では歌詞本文・歌詞検索は掲載していません。公式の楽曲情報をご利用ください。")
            elif lyrics_df.empty:
                st.info(
                    "歌詞データが見つかりません。歌詞CSVをアプリと同じフォルダへ "
                    "`lyrics.csv` として配置してください。"
                )
            else:
                search_col, mode_col, language_col = st.columns([2.2, 1.25, 1.55])
                with search_col:
                    lyric_keyword = st.text_input(
                        "検索したい言葉",
                        placeholder="例: 夢、空、光、未来",
                        key="lyrics_keyword",
                    ).strip()
                with mode_col:
                    lyric_match_mode = st.radio(
                        "一致方法",
                        ["部分一致", "単語として検索"],
                        horizontal=False,
                        key="lyrics_match_mode",
                        help="「単語として検索」は、たとえば「夢」で「夢中」を拾いにくくする検索です。日本語は助詞・記号に接している場合を単語として扱います。",
                    )
                with language_col:
                    include_english_hint = st.checkbox(
                        "関連する英語表現も探す",
                        value=False,
                        key="include_english_lyrics",
                        help="夢→dream、光→light / shine など、登録済みの関連語を追加して検索します。",
                    )
                    extra_english = st.text_input(
                        "英語の追加語（任意）",
                        placeholder="例: wish, future",
                        key="extra_english_lyrics",
                    )

                st.caption(f"登録済み歌詞: {len(lyrics_df):,} 曲")
                st.subheader("🔎 検索結果")
                if lyric_keyword:
                    lyric_terms = build_lyric_search_terms(
                        lyric_keyword,
                        include_english=include_english_hint,
                        extra_english=extra_english,
                    )
                    lyric_matches = lyrics_df[
                        lyrics_df["歌詞"].map(
                            lambda lyric: lyric_contains(
                                lyric,
                                lyric_terms,
                                lyric_match_mode,
                            )
                        )
                    ].copy()

                    st.caption(
                        "検索対象: "
                        + " / ".join(f"「{term}」" for term in lyric_terms)
                    )
                    if lyric_matches.empty:
                        st.warning("条件に一致する歌詞は見つかりませんでした。")
                    else:
                        lyric_matches["歌詞の抜粋"] = lyric_matches["歌詞"].map(
                            lambda lyric: make_lyric_excerpt(lyric, lyric_terms)
                        )
                        result_columns = [
                            column
                            for column in ["楽曲名", "アルバム", "リリース日", "歌唱者"]
                            if column in lyric_matches.columns
                        ]
                        st.subheader(f"🎵 ヒットした楽曲一覧（{len(lyric_matches):,}曲）")
                        st.dataframe(
                            lyric_matches[result_columns].reset_index(drop=True),
                            use_container_width=True,
                            hide_index=True,
                            height=min(360, 54 + len(lyric_matches) * 36),
                        )
                        result_metric_col, result_select_col = st.columns([1, 3])
                        with result_metric_col:
                            st.metric("見つかった楽曲", f"{len(lyric_matches):,} 曲")
                        with result_select_col:
                            selected_lyric_song = st.selectbox(
                                "歌詞全体を確認する楽曲",
                                lyric_matches["楽曲名"].tolist(),
                                key="selected_lyric_song",
                            )

                        selected_lyric = lyric_matches[
                            lyric_matches["楽曲名"] == selected_lyric_song
                        ].iloc[0]
                        st.markdown(
                            f'<div class="lyric-result">{highlight_lyric_text(selected_lyric["歌詞"], lyric_terms)}</div>',
                            unsafe_allow_html=True,
                        )

                else:
                    st.info("キーワードを入力すると、該当する楽曲と歌詞の抜粋を表示します。")

                with st.expander("🔤 よく使われる単語ランキング", expanded=False):
                    st.caption(
                        "助詞・語尾を除外し、漢字語・カタカナ語・英単語を中心に集計しています。"
                    )
                    phrase_ranking_df = get_frequent_lyric_phrases(
                        lyrics_df["歌詞"]
                    )
                    if phrase_ranking_df.empty:
                        st.info("ランキングを作成できる歌詞がまだありません。")
                    else:
                        st.dataframe(
                            phrase_ranking_df.reset_index(drop=True),
                            use_container_width=True,
                            hide_index=True,
                            height=420,
                            column_config={
                                "注目語": st.column_config.TextColumn(
                                    "注目語",
                                    width="large",
                                )
                            },
                        )

    if not PUBLIC_MODE:
        # TAB 11: 公式番組・生配信履歴
        with tab11:
            render_page_header(
                "📺",
                "番組・配信履歴",
                "公式番組、配信、シャニラジの出演履歴をまとめて確認できます。",
            )
            if not radio_appearance_df.empty:
                st.subheader("📻 シャニラジ出演履歴")
                radio_count_df = (
                    radio_appearance_df["キャスト"].value_counts().rename_axis("キャスト")
                    .reset_index(name="出演回数")
                )
                radio_col1, radio_col2 = st.columns([1, 1.4])
                with radio_col1:
                    st.dataframe(radio_count_df, use_container_width=True, height=280, hide_index=True)
                with radio_col2:
                    selected_radio_cast = st.selectbox(
                        "出演回を確認するキャスト:",
                        radio_count_df["キャスト"].tolist(),
                        key="selected_radio_cast",
                    )
                    selected_radio_episodes = radio_appearance_df[
                        radio_appearance_df["キャスト"] == selected_radio_cast
                    ]["出演回"].tolist()
                    st.metric("出演回数", f"{len(selected_radio_episodes)} 回")
                    if not radio_episode_df.empty:
                        selected_radio_detail_df = pd.DataFrame({"出演回": selected_radio_episodes}).merge(
                            radio_episode_df, on="出演回", how="left"
                        ).sort_values("初回放送_dt", ascending=False)
                        if not radio_clip_df.empty:
                            selected_radio_detail_df = selected_radio_detail_df.merge(
                                radio_clip_df.rename(columns={"YouTube_URL": "切り抜き動画"}),
                                on="出演回",
                                how="left",
                            )
                        radio_detail_columns = [
                            column for column in ["出演回", "初回放送", "放送内容", "切り抜き動画"]
                            if column in selected_radio_detail_df.columns
                        ]
                        st.dataframe(
                            selected_radio_detail_df[radio_detail_columns],
                            use_container_width=True,
                            height=280,
                            hide_index=True,
                            column_config={
                                "切り抜き動画": st.column_config.LinkColumn(
                                    "切り抜き動画",
                                    display_text="YouTubeで見る",
                                )
                            },
                        )
                    else:
                        st.write("・" + "\n・".join([f"第 {episode} 回" for episode in selected_radio_episodes]))
                if radio_episode_df.empty:
                    st.caption("※ 放送日・各回タイトルのデータを追加すると詳細表示になります。")
                st.markdown("---")
            if broadcast_df.empty:
                st.info("`broadcasts.csv` を main.py と同じフォルダへ置くと表示されます。")
            else:
                display_broadcast_df = broadcast_df.copy()
                if "初回放送_dt" in display_broadcast_df.columns:
                    display_broadcast_df = display_broadcast_df.sort_values("初回放送_dt", ascending=False)

                known_broadcast_casts = [
                    cast_name for cast_name in cast_list
                    if "出演者" in display_broadcast_df.columns
                    and display_broadcast_df["出演者"].astype(str).str.contains(re.escape(cast_name), na=False).any()
                ]
                filter_col, metric_col = st.columns([2, 1])
                with filter_col:
                    selected_broadcast_cast = st.selectbox(
                        "キャストで絞り込み:",
                        ["すべて"] + known_broadcast_casts,
                        key="broadcast_cast_filter",
                    )
                if selected_broadcast_cast != "すべて":
                    display_broadcast_df = display_broadcast_df[
                        display_broadcast_df["出演者"].astype(str).str.contains(
                            re.escape(selected_broadcast_cast), na=False
                        )
                    ]
                with metric_col:
                    st.metric("該当番組数", f"{len(display_broadcast_df):,} 件")

                if not display_broadcast_df.empty:
                    shown_columns = [
                        column for column in ["放送内容", "出演者", "初回放送", "告知サイト", "まとめ"]
                        if column in display_broadcast_df.columns
                    ]
                    st.dataframe(
                        display_broadcast_df[shown_columns].reset_index(drop=True),
                        use_container_width=True,
                        height=520,
                        column_config={
                            "放送内容": st.column_config.TextColumn("放送内容", width="large"),
                            "出演者": st.column_config.TextColumn("出演者", width="large"),
                        },
                    )

                    selected_broadcast_title = st.selectbox(
                        "告知・まとめページを開く番組:",
                        display_broadcast_df["放送内容"].tolist(),
                        key="selected_broadcast_title",
                    )
                    selected_broadcast_row = display_broadcast_df[
                        display_broadcast_df["放送内容"] == selected_broadcast_title
                    ].iloc[0]
                    link_col1, link_col2 = st.columns(2)
                    if str(selected_broadcast_row.get("告知サイト", "")).startswith("http"):
                        link_col1.link_button("📢 告知サイトを開く", selected_broadcast_row["告知サイト"])
                    if str(selected_broadcast_row.get("まとめ", "")).startswith("http"):
                        link_col2.link_button("📝 まとめページを開く", selected_broadcast_row["まとめ"])

    if not PUBLIC_MODE:
        # TAB 12: 統合カレンダー
        with tab12:
            render_page_header(
                "🗓️",
                "シャイニーカレンダー",
                "公演・番組・ラジオ・リリース・カード・シナリオ実装日を月ごとに確認できます。",
            )
            st.caption("🎤 公演　📺 公式番組　📻 シャニラジ　💿 楽曲・アルバム発売日　🃏 カード実装　🎬 シナリオ")
            calendar_rows = []
            if 'event_df' in locals() and not event_df.empty:
                event_date_col = next((c for c in event_df.columns if "日付" in c), None)
                event_title_col = next((c for c in event_df.columns if "公演" in c), None)
                if event_date_col and event_title_col:
                    for row in event_df.drop_duplicates(
                        [event_date_col, event_title_col]
                    ).to_dict("records"):
                        calendar_rows.append({"日付": row[event_date_col], "種類": "🎤 公演", "内容": row[event_title_col]})
            if not broadcast_df.empty:
                for row in broadcast_df.to_dict("records"):
                    calendar_rows.append({"日付": row.get("初回放送_dt"), "種類": "📺 公式番組", "内容": row.get("放送内容", "")})
            if not radio_episode_df.empty:
                for row in radio_episode_df.to_dict("records"):
                    calendar_rows.append({"日付": row.get("初回放送_dt"), "種類": "📻 シャニラジ", "内容": f"第{row.get('出演回', '')}回　{row.get('放送内容', '')}"})
            if not song_album_df.empty and "リリース日" in song_album_df.columns:
                for row in song_album_df.drop_duplicates(
                    ["リリース日", "アルバム"]
                ).to_dict("records"):
                    calendar_rows.append({"日付": row.get("リリース日"), "種類": "💿 リリース", "内容": row.get("アルバム", "")})
            if not card_df.empty and {"実装日_dt", "カード名"}.issubset(card_df.columns):
                valid_card_df = card_df.dropna(subset=["実装日_dt"]).copy()
                def has_card_calendar_value(value):
                    return clean_text(str(value)).lower() not in {"", "nan", "none"}

                def is_card_ps_value(value):
                    normalized = clean_text(str(value)).upper()
                    return normalized in {"P", "S", "ライブ専用P"}

                card_only_df = valid_card_df[
                    valid_card_df["P/S"].apply(is_card_ps_value)
                    & valid_card_df["カード名"].apply(has_card_calendar_value)
                ]
                for implementation_date, card_group in card_only_df.groupby("実装日_dt"):
                    card_count = len(card_group)
                    card_names = []
                    for card_row in card_group.to_dict("records"):
                        idol_name = clean_text(str(card_row.get("アイドル", "")))
                        card_name = clean_text(str(card_row.get("カード名", "")))
                        game_name = clean_text(str(card_row.get("作品", "")))
                        card_names.append(f"{game_name + '｜' if game_name else ''}{idol_name} {card_name}".strip())
                    calendar_rows.append({
                        "日付": implementation_date,
                        "種類": "🃏 カード実装",
                        "内容": f"カード実装 {card_count}枚：{' ／ '.join(card_names)}",
                    })
                # P/S列がP・S以外の行は、カードではなくシナリオ・イベントの実装日。
                scenario_df = valid_card_df[
                    valid_card_df["P/S"].apply(has_card_calendar_value)
                    & ~valid_card_df["P/S"].apply(is_card_ps_value)
                ].copy()
                for implementation_date, scenario_group in scenario_df.groupby("実装日_dt"):
                    scenario_names = unique_in_registered_order([
                        clean_text(str(value))
                        for value in scenario_group["P/S"].tolist()
                        if has_card_calendar_value(value)
                    ])
                    calendar_rows.append({
                        "日付": implementation_date,
                        "種類": "🎬 シナリオ・イベント",
                        "内容": f"シナリオ・イベント実装：{' ／ '.join(scenario_names)}",
                    })
            calendar_df = pd.DataFrame(calendar_rows)
            if calendar_df.empty:
                st.info("カレンダーに表示できる日付データがありません。")
            else:
                calendar_df["日付"] = pd.to_datetime(calendar_df["日付"], errors="coerce")
                calendar_df = calendar_df.dropna(subset=["日付"])
                years = sorted(calendar_df["日付"].dt.year.unique(), reverse=True)
                if st.session_state.get("calendar_year") not in years:
                    st.session_state["calendar_year"] = years[0]
                if st.session_state.get("calendar_month") not in range(1, 13):
                    st.session_state["calendar_month"] = datetime.now().month

                search_col, jump_col = st.columns([3, 1])
                with search_col:
                    calendar_search_query = st.text_input(
                        "予定を検索して該当月へ移動",
                        placeholder="例：6thLIVE、キズナシェアリング、【カード名】",
                        key="calendar_jump_search",
                    ).strip()
                calendar_search_matches = pd.DataFrame()
                selected_calendar_match = None
                if calendar_search_query:
                    calendar_search_matches = calendar_df[
                        calendar_df["内容"].astype(str).str.contains(
                            calendar_search_query, case=False, na=False, regex=False
                        )
                    ].sort_values("日付", ascending=False, kind="stable")
                    if calendar_search_matches.empty:
                        with search_col:
                            st.caption("一致する予定はありません。")
                    else:
                        calendar_search_matches = calendar_search_matches.drop_duplicates(
                            subset=["日付", "種類", "内容"], keep="first"
                        )
                        calendar_match_labels = []
                        calendar_match_lookup = {}
                        for match_index, match_row in calendar_search_matches.iterrows():
                            content_label = str(match_row["内容"]).replace("\n", " ").strip()
                            if len(content_label) > 56:
                                content_label = f"{content_label[:56]}…"
                            match_label = (
                                f"{match_row['日付'].strftime('%Y/%m/%d')} ｜ "
                                f"{match_row['種類']} ｜ {content_label}"
                            )
                            calendar_match_labels.append(match_label)
                            calendar_match_lookup[match_label] = match_index
                        with search_col:
                            selected_calendar_match = st.selectbox(
                                f"見つかった予定（{len(calendar_match_labels)}件）",
                                calendar_match_labels,
                                key="calendar_jump_match",
                            )
                with jump_col:
                    st.caption(" ")
                    if st.button(
                        "該当月へ移動",
                        key="calendar_jump_button",
                        type="primary",
                        disabled=selected_calendar_match is None,
                        use_container_width=True,
                    ):
                        matched_date = calendar_search_matches.loc[
                            calendar_match_lookup[selected_calendar_match], "日付"
                        ]
                        st.session_state["calendar_year"] = int(matched_date.year)
                        st.session_state["calendar_month"] = int(matched_date.month)
                        st.rerun()

                nav_left, nav_title, nav_right = st.columns([1, 3, 1])
                current_year = st.session_state["calendar_year"]
                current_month = st.session_state["calendar_month"]
                previous_year, previous_month = (current_year - 1, 12) if current_month == 1 else (current_year, current_month - 1)
                next_year, next_month = (current_year + 1, 1) if current_month == 12 else (current_year, current_month + 1)
                with nav_left:
                    if st.button("← 前の月", key="calendar_previous", disabled=previous_year not in years):
                        st.session_state["calendar_year"] = previous_year
                        st.session_state["calendar_month"] = previous_month
                        st.rerun()
                with nav_title:
                    st.markdown(f"<div style='text-align:center; font-size:1.35rem; font-weight:800; padding:.25rem'>{current_year}年 {current_month}月</div>", unsafe_allow_html=True)
                with nav_right:
                    if st.button("次の月 →", key="calendar_next", disabled=next_year not in years):
                        st.session_state["calendar_year"] = next_year
                        st.session_state["calendar_month"] = next_month
                        st.rerun()

                cal_col1, cal_col2, cal_col3 = st.columns([1, 1, 2])
                with cal_col1:
                    selected_calendar_year = st.selectbox("年", years, key="calendar_year")
                with cal_col2:
                    selected_calendar_month = st.selectbox("月", list(range(1, 13)), key="calendar_month")
                with cal_col3:
                    st.caption("表示する種類（ボタンで切り替え）")
                    calendar_type_options = unique_in_registered_order(calendar_df["種類"].tolist())
                    type_button_columns = st.columns(min(3, max(1, len(calendar_type_options))))
                    visible_calendar_types = []
                    for index, calendar_type in enumerate(calendar_type_options):
                        with type_button_columns[index % len(type_button_columns)]:
                            if st.checkbox(
                                calendar_type,
                                value=True,
                                key=f"calendar_type_button_{make_search_key(calendar_type)}",
                            ):
                                visible_calendar_types.append(calendar_type)
                month_df = calendar_df[(calendar_df["日付"].dt.year == selected_calendar_year) & (calendar_df["日付"].dt.month == selected_calendar_month) & (calendar_df["種類"].isin(visible_calendar_types))].copy()
                st.subheader(f"{selected_calendar_year}年 {selected_calendar_month}月")
                render_calendar_context_images(selected_calendar_year, selected_calendar_month)
                weekdays = ["日", "月", "火", "水", "木", "金", "土"]
                badge_colors = {"🎤 公演": "#e879a8", "📺 公式番組": "#58aee8", "📻 シャニラジ": "#8b7be8", "💿 リリース": "#e8a54f", "🃏 カード実装": "#55b99d", "🎬 シナリオ・イベント": "#7287d8"}
                short_kind_names = {"🎤 公演": "公演", "📺 公式番組": "番組", "📻 シャニラジ": "ラジオ", "💿 リリース": "発売", "🃏 カード実装": "カード", "🎬 シナリオ・イベント": "シナリオ"}
                calendar_html = textwrap.dedent("""
                    <style>
                        .shiny-calendar-scroll {width:100%; overflow-x:auto; padding-bottom:4px; scrollbar-color:rgba(102,87,217,.5) transparent;}
                        .shiny-calendar {display:grid; grid-template-columns:repeat(7, minmax(0, 1fr)); gap:4px; margin:5px 0 12px;}
                        .shiny-calendar-head {font-weight:800; color:#30335f; padding:2px 5px; font-size:.78rem;}
                        .shiny-calendar-day {min-height:82px; padding:5px; border:1px solid #deddf0; border-radius:8px; background:rgba(255,255,255,.72);}
                        .shiny-calendar-empty {background:rgba(255,255,255,.18); border-color:transparent;}
                        .shiny-calendar-date {font-weight:800; color:#343761; margin-bottom:2px; font-size:.82rem;}
                        .shiny-calendar-item {font-size:.67rem; line-height:1.25; margin:2px 0; padding:2px 4px; background:#fff; border-left:3px solid #8892aa; white-space:normal; overflow-wrap:anywhere;}
                        .shiny-calendar-kind {font-size:.59rem; font-weight:800; color:#5c5d83; margin-right:2px;}
                        .shiny-calendar-more {font-size:.66rem; color:#77799e; margin-top:2px;}
                        @media (max-width: 760px) {
                            .shiny-calendar {min-width:980px; gap:5px;}
                            .shiny-calendar-day {min-height:104px; padding:6px; border-radius:7px;}
                            .shiny-calendar-head {font-size:.82rem; padding:3px; text-align:center;}
                            .shiny-calendar-item {font-size:.72rem; padding:3px 4px; border-left-width:3px;}
                        }
                    </style>
                    <div class='shiny-calendar-scroll'><div class='shiny-calendar'>
                """)
                for weekday in weekdays:
                    calendar_html += f"<div class='shiny-calendar-head'>{weekday}</div>"
                sunday_first_calendar = calendar.Calendar(firstweekday=calendar.SUNDAY)
                for week in sunday_first_calendar.monthdayscalendar(selected_calendar_year, selected_calendar_month):
                    for day in week:
                        if not day:
                            calendar_html += "<div class='shiny-calendar-day shiny-calendar-empty'></div>"
                            continue
                        day_items = month_df[month_df["日付"].dt.day == day]
                        calendar_html += f"<div class='shiny-calendar-day'><div class='shiny-calendar-date'>{day}</div>"
                        for item in day_items.to_dict("records"):
                            short_title = str(item["内容"]).replace("THE IDOLM@STER SHINY COLORS", "").strip()
                            item_kind = item["種類"]
                            calendar_html += (
                                f"<div class='shiny-calendar-item' style='border-left-color:{badge_colors.get(item_kind, '#8892aa')}'>"
                                f"<span class='shiny-calendar-kind'>{html.escape(short_kind_names.get(item_kind, item_kind))}</span>"
                                f"{html.escape(short_title)}</div>"
                            )
                        calendar_html += "</div>"
                calendar_html += "</div></div>"
                st.markdown(calendar_html, unsafe_allow_html=True)
                st.subheader("📋 今月の予定一覧")
                st.dataframe(month_df.sort_values("日付")[["日付", "種類", "内容"]], use_container_width=True, hide_index=True)

    if not PUBLIC_MODE:
        with tab14:
            render_schedule_prediction()

    if not PUBLIC_MODE:
        with tab15:
            render_event_image_gallery()

    if PUBLIC_MODE:
        with tab16:
            render_page_header(
                "📚",
                "分類ガイド",
                "このサイト内でデータを見やすくするために使っている独自の分類です。公式の呼称・区分とは一致しない場合があります。",
            )
            st.info("分類は検索や集計をしやすくするための管理上の目安です。公式発表の分類ではありません。")

            st.subheader("🔎 曲・公演の分類を調べる")
            guide_event_column = next(
                (column for column in event_df.columns if "公演" in column or "イベント" in column or "ライブ" in column),
                None,
            ) if not event_df.empty else None
            guide_options = unique_in_registered_order(
                df["楽曲名"].astype(str).tolist()
                + (event_df[guide_event_column].astype(str).tolist() if guide_event_column else [])
            )
            classification_query = st.selectbox(
                "曲名または公演名を選択",
                [""] + guide_options,
                format_func=lambda value: "候補を検索して選択" if not value else value,
                key="classification_guide_query",
                help="候補名を入力して絞り込み、表示された候補から選びます。",
            )
            if classification_query:
                song_matches = unique_in_registered_order(
                    df.loc[
                        df["楽曲名"].astype(str).str.contains(
                            classification_query, case=False, regex=False, na=False
                        ),
                        "楽曲名",
                    ].tolist()
                )
                event_name_col = next(
                    (column for column in event_df.columns if "公演" in column or "イベント" in column or "ライブ" in column),
                    None,
                ) if not event_df.empty else None
                event_type_col = next(
                    (column for column in event_df.columns if "区分" in column or "種別" in column or "タイプ" in column),
                    None,
                ) if not event_df.empty else None
                event_matches = []
                if event_name_col:
                    event_matches = unique_in_registered_order(
                        event_df.loc[
                            event_df[event_name_col].astype(str).str.contains(
                                classification_query, case=False, regex=False, na=False
                            ),
                            event_name_col,
                        ].tolist()
                    )

                if not song_matches and not event_matches:
                    st.info("一致する楽曲・公演は見つかりませんでした。表記の一部でも検索できます。")
                result_col1, result_col2 = st.columns(2)
                with result_col1:
                    if song_matches:
                        selected_guide_song = st.selectbox(
                            "楽曲の候補",
                            song_matches,
                            key="classification_guide_song",
                        )
                        song_classes = unique_in_registered_order(
                            df.loc[df["楽曲名"] == selected_guide_song, "楽曲区分"].fillna("未分類").tolist()
                        )
                        st.success(f"🎵 「{selected_guide_song}」は、このサイトでは「{'・'.join(song_classes)}」です。")
                with result_col2:
                    if event_matches and event_name_col and event_type_col:
                        selected_guide_event = st.selectbox(
                            "公演の候補",
                            event_matches,
                            key="classification_guide_event",
                        )
                        event_classes = unique_in_registered_order(
                            event_df.loc[event_df[event_name_col] == selected_guide_event, event_type_col].fillna("未設定").tolist()
                        )
                        st.success(f"🏟️ 「{selected_guide_event}」は、このサイトでは「{'・'.join(event_classes)}」です。")

            st.subheader("🏟️ 公演区分")
            st.dataframe(
                pd.DataFrame(
                    [
                        ["キャストライブ", "シャイニーカラーズの出演者を中心としたライブ公演"],
                        ["XR", "XR・バーチャル形式で行われるライブ"],
                        ["発売記念イベント", "CD・映像作品などの発売に関連するイベント"],
                        ["合同", "複数ブランドが出演する公式イベント"],
                        ["外部", "ブランド外を主とするイベントへの出演"],
                        ["その他", "上記に当てはまらないイベント・企画"],
                        ["未設定", "分類を確認・整理中のデータ"],
                    ],
                    columns=["分類", "このサイトでの扱い"],
                ),
                use_container_width=True,
                hide_index=True,
            )

            st.subheader("🎵 楽曲区分")
            st.dataframe(
                pd.DataFrame(
                    [
                        ["オリジナル", "シャイニーカラーズの楽曲として扱う曲"],
                        ["合同", "複数ブランド・合同企画に関わる楽曲"],
                        ["カバー", "他作品・他アーティストの楽曲をカバーしたもの"],
                        ["外部", "外部作品・企画に関わる楽曲"],
                        ["その他", "上記に当てはまらない特別な扱いの楽曲"],
                        ["未分類", "分類を確認・整理中の楽曲"],
                    ],
                    columns=["分類", "このサイトでの扱い"],
                ),
                use_container_width=True,
                hide_index=True,
            )

    if PUBLIC_MODE:
        with tab17:
            render_page_header(
                "🔰",
                "使い方",
                "シャイニーカラーズのライブ記録を、目的に合わせて気軽に見られるデータベースです。",
            )
            st.subheader("まずはここから")
            st.markdown(
                """
                1. **分析**で、楽曲・衣装・ユニットの披露回数を見ます。
                2. **楽曲**で、気になる曲の披露履歴や公式動画を確認します。
                3. **公演**で、公演ごとのセットリストと前回披露からの間隔を見ます。
                """
            )

            st.subheader("各タブでできること")
            st.dataframe(
                pd.DataFrame(
                    [
                        ["📊 分析", "楽曲・衣装・ユニットの披露回数を比較する"],
                        ["🎵 楽曲", "楽曲ごとの披露履歴、収録情報、公式動画を確認する"],
                        ["🎤 歌唱・衣装", "出演者や衣装ごとの記録をたどる"],
                        ["👗 衣装", "衣装の着用記録と最後に着用された日を確認する"],
                        ["🏟️ 公演", "公演ごとのセットリストや前回披露からの間隔を見る"],
                        ["👥 参加履歴", "出演者ごとの公演参加記録を見る"],
                        ["📚 分類ガイド", "このサイト独自の分類ルールを確認する"],
                    ],
                    columns=["タブ", "できること"],
                ),
                use_container_width=True,
                hide_index=True,
            )

            st.subheader("サイドバーの設定について")
            st.write("画面左上の矢印から開けるサイドバーでは、集計に含める範囲をまとめて切り替えられます。設定は分析だけでなく、楽曲・歌唱・衣装・公演の表示にも反映されます。")
            st.markdown(
                """
                - **公演区分フィルター**：単独・合同・外部など、集計に含める公演の種類を選びます。
                - **楽曲区分フィルター**：オリジナル・外部・ブランド合同など、集計に含める楽曲の種類を選びます。
- **キャスト名とアイドル名を同一視**：対応するキャスト名・アイドル名の歌唱記録をまとめて表示・集計します。キャスト名で選んだ場合はキャラクター名義の歌唱も、アイドル名で選んだ場合はキャスト名義の歌唱も含めます（例：XRライブなど）。
- **ショート版を同一曲として合算**：short版は元の楽曲とまとめて数えます。ただし「Migratory Echoes（イルミネーションスターズVer.）」のようなユニット別バージョンは、同じ曲名でも別の楽曲として扱います。
                - **個人アーティストとしての歌唱**：個人名義で歌ったシャイニーカラーズ楽曲を、通常の記録に含めるか選べます。初期状態では含めません。
                """
            )


        with tab18:
            render_page_header(
                "ℹ️",
                "このサイトについて",
                "このサイトで扱っている記録と、見てもらうときのお願いです。",
            )
            st.write(
                "ライブを振り返るときに『この曲はいつ以来？』『この衣装はどこで着ていた？』をすぐ見られたらいいなと思って、個人でまとめています。"
            )

            st.subheader("運営について")
            st.write(
                "このサイトは、シャイニーカラーズのライブを振り返るために個人が趣味で運営している非公式ファンサイトです。株式会社バンダイナムコエンターテインメントおよび関係各社とは関係ありません。"
            )

            st.subheader("ここに載せている記録")
            st.write("公演とセットリストをもとに、楽曲の披露記録や衣装、出演状況を整理しています。対象にしているのは、シャイニーカラーズのキャストまたはアイドルが歌唱した記録です。")
            st.write("合同ライブで他ブランドのキャスト・アイドルだけがシャイニーカラーズ楽曲をカバーした場合は、このサイトの集計には入れていません。")
            st.write("公演や楽曲の分類は、比較しやすくするためにこのサイト用に付けたものです。公式の分類とは少し違う場合があります。")

            st.subheader("権利について")
            st.write(
                "作品名・楽曲名・登場人物名などに関する権利は、それぞれの権利者に帰属します。掲載内容は公式発表を置き換えるものではありません。"
            )

            st.subheader("リンク・転載について")
            st.write(
                "このサイトへのリンクや、ページを紹介する形での引用は歓迎します。紹介するときは、できるだけ該当ページへのリンクを添えてください。サイト全体をそのまま複製するような転載はご遠慮ください。"
            )

            st.subheader("外部サービスとプライバシー")
            st.write(
                "このサイトでは、アカウント登録や問い合わせフォームを設けておらず、運営者が閲覧者の氏名やメールアドレスを集めることはありません。動画の表示などで利用するStreamlitやYouTube等の外部サービスでは、各サービスの方針に基づいて通信情報やCookieが扱われる場合があります。"
            )

            st.subheader("ご利用にあたって")
            st.write(
                "できるだけ確認して登録していますが、表記ゆれや記録漏れが残っているかもしれません。公式発表・公式サイトの情報を優先して、ひとつの参考として楽しんでもらえたらうれしいです。"
            )
            st.caption("記録の誤りや抜けに気づいたときは、[X（@seinarish）](https://x.com/seinarish) まで知らせてもらえると助かります。")

    if not PUBLIC_MODE:
        with tab13:
            render_page_header(
                "💴",
                "価格推移・購入ガイド",
                "CD・ソロコレクション・Blu-ray・チケット・配信の定価を、カテゴリ別に比較できます。",
            )
            if price_history_df.empty:
                st.info("価格データを読み込めませんでした。price_history.csv を配置してください。")
            else:
                display_price_df = price_history_df.copy().fillna("")
                display_price_df["価格"] = pd.to_numeric(
                    display_price_df["価格"].astype(str).str.replace(",", "", regex=False),
                    errors="coerce",
                )
                display_price_df = display_price_df.dropna(subset=["価格"])
                display_price_df["日付"] = pd.to_datetime(display_price_df["日付"], errors="coerce")
                display_price_df["日付種別"] = "登録日"

                # 日付未入力の価格は、CDなら収録アルバムの発売日、公演関連なら初日を補助日付にする。
                album_date_candidates = []
                if not song_album_df.empty:
                    price_album_col = next((c for c in song_album_df.columns if "アルバム" in c or "CD" in c), None)
                    price_release_col = next((c for c in song_album_df.columns if "リリース" in c or "発売日" in c), None)
                    if price_album_col and price_release_col:
                        for price_album_row in song_album_df[[price_album_col, price_release_col]].dropna().drop_duplicates().to_dict("records"):
                            parsed_date = pd.to_datetime(price_album_row[price_release_col], errors="coerce")
                            if pd.notna(parsed_date):
                                album_date_candidates.append((
                                    make_search_key(price_album_row[price_album_col]), parsed_date
                                ))
                event_date_candidates = []
                # events.csv に未収録の公演。中止公演も、当初予定されていた日を明示して価格履歴へ残す。
                price_event_date_overrides = {
                    "springparty2020": (pd.Timestamp("2020-03-21"), "開催予定日（中止）"),
                }

                def make_price_event_key(title):
                    """価格表とevents.csvの公演名の記号・引用符・DAY表記差を吸収する。"""
                    normalized = clean_live_name(str(title))
                    normalized = re.sub(r"\s*(?:DAY|day)\s*[0-9０-９]+.*$", "", normalized)
                    normalized = normalized.replace("∞", "infinity")
                    normalized = normalized.lower()
                    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)

                if "event_df" in locals() and not event_df.empty:
                    price_event_name_col = next((c for c in event_df.columns if "公演" in c or "イベント" in c), None)
                    price_event_date_col = next((c for c in event_df.columns if "日付" in c), None)
                    if price_event_name_col and price_event_date_col:
                        for price_event_row in event_df[[price_event_name_col, price_event_date_col]].dropna().drop_duplicates().to_dict("records"):
                            parsed_date = pd.to_datetime(price_event_row[price_event_date_col], errors="coerce")
                            if pd.notna(parsed_date):
                                event_date_candidates.append((
                                    make_price_event_key(price_event_row[price_event_name_col]), parsed_date
                                ))

                # 価格表は「01～08」「Song for Prism ①」のように、ディスコグラフィの
                # 個別商品名とは異なるまとめ表記を使う。その差分をここで吸収する。
                def make_price_catalog_key(title):
                    """CD名の括弧・引用符・@・ハイフンなどの表記揺れを除いた照合キー。"""
                    normalized = (
                        clean_song_title_for_search(str(title))
                        .replace("①", "1周目")
                        .replace("②", "2周目")
                        .replace("③", "3周目")
                        .replace("Synthe-Side", "Synse-Side")
                        .replace("Synthe Side", "Synse-Side")
                        .lower()
                    )
                    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)

                def make_price_match_keys(title):
                    raw_title = str(title)
                    normalized_title = (
                        raw_title
                        .replace("①", "1周目")
                        .replace("②", "2周目")
                        .replace("③", "3周目")
                        .replace("全体", "")
                        .replace("Synthe-Side", "Synse-Side")
                        .replace("Synthe Side", "Synse-Side")
                    )
                    aliases = [make_price_catalog_key(raw_title), make_price_catalog_key(normalized_title)]
                    manual_aliases = {
                        "songforprismリフラク": "pjrefractions",
                        "colorfulfethersシーズ": "colorfulfethersshhis",
                        "colorfulfethersコメ": "colorfulfetherscometik",
                        "円環haloaround": "円環haloaround",
                        "28colorscollection数量限定盤": "28colorscollection",
                        "28colorscollection通常盤": "28colorscollection",
                    }
                    title_key = make_price_catalog_key(raw_title)
                    if title_key in manual_aliases:
                        aliases.append(manual_aliases[title_key])
                    return [alias for alias in aliases if alias]

                # songs_albums.csv に収録曲がない会場CD・企画盤は、公式ディスコグラフィの発売日を使う。
                price_release_date_overrides = {
                    make_price_catalog_key("COLORFUL FE@THERS シーズ"): pd.Timestamp("2023-07-26"),
                    make_price_catalog_key("COLORFUL FE@THERS コメ"): pd.Timestamp("2024-12-04"),
                    make_price_catalog_key("6thLIVE TOUR Come and Unite! part1"): pd.Timestamp("2024-03-02"),
                    make_price_catalog_key("6thLIVE TOUR Come and Unite! part2"): pd.Timestamp("2024-03-02"),
                    make_price_catalog_key("6thLIVE TOUR Come and Unite! part3"): pd.Timestamp("2024-03-02"),
                    make_price_catalog_key("7th UNITLIVE TOUR 円環 -Halo around- part1"): pd.Timestamp("2025-06-21"),
                    make_price_catalog_key("7th UNITLIVE TOUR 円環 -Halo around- part2"): pd.Timestamp("2025-06-21"),
                    make_price_catalog_key("7th UNITLIVE TOUR 円環 -Halo around- part3"): pd.Timestamp("2025-06-21"),
                    make_price_catalog_key("Beyond the Blue sky part1"): pd.Timestamp("2024-07-27"),
                    make_price_catalog_key("Beyond the Blue sky part2"): pd.Timestamp("2024-07-27"),
                    make_price_catalog_key("L@YERED WING part 1"): pd.Timestamp("2022-02-14"),
                    make_price_catalog_key("L@YERED WING part 2"): pd.Timestamp("2022-02-14"),
                    make_price_catalog_key("M@STERS OF IDOL WORLD 2025 part1"): pd.Timestamp("2025-12-13"),
                    make_price_catalog_key("M@STERS OF IDOL WORLD 2025 part2"): pd.Timestamp("2025-12-13"),
                    make_price_catalog_key("SOLO PERFORMANCE LIVE 我儘なまま Stella"): pd.Timestamp("2023-07-22"),
                    make_price_catalog_key("SOLO PERFORMANCE LIVE 我儘なまま Luna"): pd.Timestamp("2023-07-22"),
                    make_price_catalog_key("SOLO PERFORMANCE LIVE 我儘なまま Sol"): pd.Timestamp("2023-07-22"),
                    make_price_catalog_key("28 colors- COLLECTION 【数量限定盤】"): pd.Timestamp("2025-10-01"),
                    make_price_catalog_key("28 colors- COLLECTION 【通常盤】"): pd.Timestamp("2025-10-01"),
                    make_price_catalog_key("HOPEFUL FE@THERS -Stella-"): pd.Timestamp("2026-09-16"),
                    make_price_catalog_key("HOPEFUL FE@THERS -Luna-"): pd.Timestamp("2026-09-16"),
                    make_price_catalog_key("HOPEFUL FE@THERS -Sol-"): pd.Timestamp("2026-09-16"),
                    make_price_catalog_key("OFF VOCAL COLLECTION 01"): pd.Timestamp("2022-01-19"),
                    make_price_catalog_key("OFF VOCAL COLLECTION 02"): pd.Timestamp("2022-12-07"),
                    make_price_catalog_key("WING COLLECTION"): pd.Timestamp("2023-01-18"),
                    make_price_catalog_key("Song for Prism ①"): pd.Timestamp("2023-10-18"),
                    make_price_catalog_key("Song for Prism ①全体"): pd.Timestamp("2023-10-18"),
                    make_price_catalog_key("Song for Prism ②"): pd.Timestamp("2024-11-20"),
                    make_price_catalog_key("Song for Prism ②全体"): pd.Timestamp("2024-11-20"),
                    make_price_catalog_key("Song for Prism ③"): pd.Timestamp("2025-12-24"),
                    make_price_catalog_key("Song for Prism ③全体"): pd.Timestamp("2025-12-24"),
                    make_price_catalog_key("Song for Prism リフラク"): pd.Timestamp("2026-01-07"),
                }

                for row_index, price_row in display_price_df[display_price_df["日付"].isna()].iterrows():
                    target_keys = make_price_match_keys(price_row["対象名"])
                    category = str(price_row["カテゴリ"])
                    manual_release_date = price_release_date_overrides.get(
                        make_price_catalog_key(price_row["対象名"])
                    )
                    album_matched_dates = [
                        candidate_date for candidate_key, candidate_date in album_date_candidates
                        if candidate_key and any(
                            target_key in make_price_catalog_key(candidate_key)
                            or make_price_catalog_key(candidate_key) in target_key
                            for target_key in target_keys
                        )
                    ]
                    event_target_key = make_price_event_key(price_row["対象名"])
                    event_matched_dates = [
                        candidate_date for candidate_key, candidate_date in event_date_candidates
                        if candidate_key and event_target_key and (
                            event_target_key in candidate_key or candidate_key in event_target_key
                        )
                    ]
                    override_date_info = price_event_date_overrides.get(event_target_key)
                    if not event_matched_dates and override_date_info:
                        event_matched_dates = [override_date_info[0]]
                    if manual_release_date is not None:
                        matched_dates = [manual_release_date]
                        matched_date_kind = "発売日（公式対応表）"
                    elif category == "CD":
                        matched_dates = album_matched_dates
                        matched_date_kind = "発売日（自動照合）"
                    elif category == "ソロコレクション":
                        matched_dates = album_matched_dates or event_matched_dates
                        matched_date_kind = (
                            "発売日（自動照合）" if album_matched_dates
                            else (override_date_info[1] if override_date_info else "公演日（基準）")
                        )
                    else:
                        matched_dates = event_matched_dates
                        matched_date_kind = override_date_info[1] if override_date_info else "公演日（基準）"
                    if matched_dates:
                        display_price_df.loc[row_index, "日付"] = min(matched_dates)
                        display_price_df.loc[row_index, "日付種別"] = matched_date_kind

                price_categories = unique_in_registered_order(display_price_df["カテゴリ"].tolist())
                price_filter_col, price_type_col = st.columns([1, 2])
                with price_filter_col:
                    selected_price_category = st.selectbox("表示カテゴリ", ["すべて"] + price_categories)
                price_filtered_df = display_price_df.copy()
                if selected_price_category != "すべて":
                    price_filtered_df = price_filtered_df[
                        price_filtered_df["カテゴリ"] == selected_price_category
                    ]
                price_type_options = unique_in_registered_order(price_filtered_df["価格種別"].tolist())
                with price_type_col:
                    selected_price_types = st.multiselect(
                        "価格種別（比較する項目を選択）",
                        price_type_options,
                        default=price_type_options,
                    )
                price_filtered_df = price_filtered_df[
                    price_filtered_df["価格種別"].isin(selected_price_types)
                ]

                metric_total, metric_low, metric_high = st.columns(3)
                metric_total.metric("登録価格", f"{len(price_filtered_df):,}件")
                metric_low.metric("最安価格", f"¥{int(price_filtered_df['価格'].min()):,}" if not price_filtered_df.empty else "—")
                metric_high.metric("最高価格", f"¥{int(price_filtered_df['価格'].max()):,}" if not price_filtered_df.empty else "—")

                dated_price_df = price_filtered_df.dropna(subset=["日付"]).sort_values("日付", kind="stable")
                if not dated_price_df.empty:
                    price_chart = px.line(
                        dated_price_df,
                        x="日付",
                        y="価格",
                        color="価格種別",
                        markers=True,
                        hover_data={"対象名": True, "カテゴリ": True, "日付種別": True, "価格": ":,.0f"},
                        labels={"日付": "基準日", "価格": "価格（円）", "価格種別": "価格種別"},
                    )
                    price_chart.update_layout(
                        height=440,
                        margin=dict(l=20, r=20, t=30, b=20),
                        legend_title_text="",
                    )
                    render_analysis_chart(price_chart, key="tab13_price_history")
                else:
                    st.info("この条件では日付を特定できる価格データがありません。日付を price_history.csv に追加すると推移グラフへ表示されます。")

                st.subheader("📋 価格一覧")
                price_display_columns = [
                    column for column in ["日付", "日付種別", "対象名", "カテゴリ", "価格種別", "価格"]
                    if column in price_filtered_df.columns
                ]
                st.dataframe(
                    price_filtered_df.sort_values(["日付", "対象名"], ascending=[False, True], na_position="last")[price_display_columns],
                    use_container_width=True,
                    hide_index=True,
                    column_config={"価格": st.column_config.NumberColumn("価格", format="¥%d")},
                )

                st.divider()
                st.subheader("📈 ライブ・リリースの推移")
                st.caption("価格以外にも、時系列で比較しやすい公演・楽曲データをまとめました。")

                trend_kind = st.radio(
                    "表示する推移",
                    [
                        "公演ごとの曲数",
                        "年ごとのリリース曲数",
                        "年ごとの公演数",
                        "年ごとの総披露回数",
                    ],
                    horizontal=True,
                    key="tab13_trend_kind",
                )

                music_history_df = df.copy()
                if "楽曲名" in music_history_df.columns:
                    music_history_df = music_history_df[
                        ~music_history_df["楽曲名"].astype(str).str.contains("トークのみ", na=False)
                    ]

                if trend_kind == "公演ごとの曲数":
                    if live_col_name and "日付_dt" in music_history_df.columns:
                        event_song_trend_df = (
                            music_history_df.dropna(subset=["日付_dt"])
                            .groupby(["日付_dt", live_col_name], as_index=False)
                            .size()
                            .rename(columns={"size": "曲数"})
                            .sort_values("日付_dt", kind="stable")
                        )
                        event_song_trend_df["開催年"] = event_song_trend_df["日付_dt"].dt.year
                        event_song_trend_df["公演名（全文）"] = event_song_trend_df[live_col_name].astype(str)
                        event_song_trend_df["表示名"] = event_song_trend_df["公演名（全文）"].map(
                            lambda value: value if len(value) <= 34 else value[:33] + "…"
                        )

                        def classify_trend_live(event_name):
                            """推移グラフ用の大まかな公演分類を返す。"""
                            name = str(event_name)
                            normalized_name = name.lower()

                            # 周年表記を含んでいても、シャニソン連動ライブは優先して分ける。
                            if (
                                "chapter 283" in normalized_name
                                or "星が見上げた空" in name
                                or ("7th live tour" in normalized_name and "螺旋" in name)
                            ):
                                return "シャニソンライブ"
                            if re.search(
                                r"(?:\d+(?:\.\d+)?th|∞th)\s*(?:anniversary\s*)?live",
                                name,
                                flags=re.IGNORECASE,
                            ):
                                return "周年ライブ"
                            return "その他"

                        event_song_trend_df["公演分類"] = event_song_trend_df["公演名（全文）"].map(
                            classify_trend_live
                        )
                        st.caption("表示する公演分類")
                        filter_col1, filter_col2, filter_col3 = st.columns(3)
                        with filter_col1:
                            show_anniversary_lives = st.checkbox(
                                "🎂 周年ライブ",
                                value=True,
                                key="tab13_show_anniversary_lives",
                            )
                        with filter_col2:
                            show_shiny_song_lives = st.checkbox(
                                "🎮 シャニソンライブ",
                                value=True,
                                key="tab13_show_shiny_song_lives",
                            )
                        with filter_col3:
                            show_other_lives = st.checkbox(
                                "📌 その他の公演",
                                value=True,
                                key="tab13_show_other_lives",
                            )

                        selected_live_groups = []
                        if show_anniversary_lives:
                            selected_live_groups.append("周年ライブ")
                        if show_shiny_song_lives:
                            selected_live_groups.append("シャニソンライブ")
                        if show_other_lives:
                            selected_live_groups.append("その他")

                        if not selected_live_groups:
                            st.info("表示する公演分類を1つ以上選択してください。")
                            event_song_trend_df = event_song_trend_df.iloc[0:0]
                        else:
                            event_song_trend_df = event_song_trend_df[
                                event_song_trend_df["公演分類"].isin(selected_live_groups)
                            ].copy()

                        selected_years = sorted(event_song_trend_df["日付_dt"].dt.year.unique(), reverse=True)
                        selected_event_year = st.selectbox(
                            "表示する期間",
                            ["すべて（時系列）"] + selected_years,
                            key="tab13_event_song_year",
                        )
                        trend_chart = None
                        if event_song_trend_df.empty:
                            st.info("条件に一致する公演がありません。")
                        elif selected_event_year == "すべて（時系列）":
                            trend_chart = px.line(
                                event_song_trend_df.sort_values("日付_dt", kind="stable"),
                                x="日付_dt",
                                y="曲数",
                                markers=True,
                                hover_data={"公演名（全文）": True, "開催年": True},
                                labels={"日付_dt": "開催日", "曲数": "曲数"},
                            )
                            trend_chart.update_traces(marker={"size": 8}, line={"width": 2})
                            trend_chart.update_layout(
                                height=440,
                                margin=dict(l=20, r=20, t=30, b=20),
                                hovermode="x unified",
                            )
                        else:
                            event_song_trend_df = event_song_trend_df[
                                event_song_trend_df["開催年"] == selected_event_year
                            ].sort_values("日付_dt", ascending=False, kind="stable")
                            trend_chart = px.bar(
                                event_song_trend_df,
                                x="曲数",
                                y="表示名",
                                orientation="h",
                                color="曲数",
                                color_continuous_scale="Blues",
                                hover_data={"日付_dt": "|%Y/%m/%d", "公演名（全文）": True},
                                labels={"表示名": "公演", "曲数": "曲数"},
                            )
                            trend_chart.update_layout(
                                height=max(420, len(event_song_trend_df) * 30 + 110),
                                margin=dict(l=20, r=20, t=30, b=20),
                                coloraxis_showscale=False,
                                yaxis={"categoryorder": "array", "categoryarray": event_song_trend_df["表示名"].tolist()},
                            )
                        if trend_chart is not None:
                            render_analysis_chart(trend_chart, key="tab13_event_song_trend")
                            st.dataframe(
                                event_song_trend_df[["日付_dt", live_col_name, "曲数"]].sort_values("日付_dt", ascending=False),
                                use_container_width=True,
                                hide_index=True,
                                column_config={"日付_dt": st.column_config.DateColumn("日付", format="YYYY/MM/DD")},
                            )
                    else:
                        st.info("公演名と日付のデータが揃うと、公演ごとの曲数を表示できます。")
                elif trend_kind == "年ごとのリリース曲数":
                    release_date_col = next((column for column in song_album_df.columns if "リリース" in column or "発売日" in column), None)
                    release_song_col = next((column for column in song_album_df.columns if "楽曲" in column), None)
                    if release_date_col and release_song_col:
                        release_trend_df = song_album_df[[release_date_col, release_song_col]].copy()
                        release_trend_df["リリース日_dt"] = pd.to_datetime(release_trend_df[release_date_col], errors="coerce")
                        release_trend_df = release_trend_df.dropna(subset=["リリース日_dt"])
                        release_trend_df["年"] = release_trend_df["リリース日_dt"].dt.year
                        release_trend_df = (
                            release_trend_df.groupby("年", as_index=False)[release_song_col]
                            .nunique()
                            .rename(columns={release_song_col: "リリース曲数"})
                        )
                        trend_chart = px.bar(
                            release_trend_df,
                            x="年",
                            y="リリース曲数",
                            text="リリース曲数",
                            color="リリース曲数",
                            color_continuous_scale="Purples",
                        )
                        trend_chart.update_layout(height=440, margin=dict(l=20, r=20, t=30, b=20), coloraxis_showscale=False)
                        render_analysis_chart(trend_chart, key="tab13_release_song_trend")
                    else:
                        st.info("楽曲×アルバムに発売日・楽曲名を登録すると、年ごとのリリース曲数を表示できます。")
                else:
                    if "日付_dt" in music_history_df.columns:
                        event_year_df = music_history_df.dropna(subset=["日付_dt"]).copy()
                        event_year_df["年"] = event_year_df["日付_dt"].dt.year
                        if trend_kind == "年ごとの公演数":
                            if live_col_name:
                                trend_df = (
                                    event_year_df.groupby("年", as_index=False)[live_col_name]
                                    .nunique()
                                    .rename(columns={live_col_name: "公演数"})
                                )
                                value_column = "公演数"
                            else:
                                trend_df = pd.DataFrame(columns=["年", "公演数"])
                                value_column = "公演数"
                        else:
                            trend_df = event_year_df.groupby("年", as_index=False).size().rename(columns={"size": "総披露回数"})
                            value_column = "総披露回数"
                        trend_chart = px.bar(
                            trend_df,
                            x="年",
                            y=value_column,
                            text=value_column,
                            color=value_column,
                            color_continuous_scale="Teal",
                        )
                        trend_chart.update_layout(height=440, margin=dict(l=20, r=20, t=30, b=20), coloraxis_showscale=False)
                        render_analysis_chart(trend_chart, key="tab13_total_performance_trend")
                    else:
                        st.info("日付データを登録すると、年ごとの公演・披露回数を表示できます。")

else:
    st.warning("⚠️ `songs.csv` が見つかりません。配置をご確認ください。")
