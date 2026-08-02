from __future__ import annotations

import csv
import math
from pathlib import Path

import streamlit as st


def _load_images(manifest_path: Path) -> list[dict[str, str]]:
    if not manifest_path.exists():
        return []
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def render_event_image_gallery() -> None:
    app_dir = Path(__file__).resolve().parent
    image_dir = app_dir / "event_images"
    records = _load_images(app_dir / "event_images.csv")

    st.markdown("---")
    st.header("イベント画像ギャラリー")
    st.caption("公演や画像の種類を選んで、関連画像をまとめて閲覧できます。")

    if not records:
        st.info("表示できる画像はまだありません。")
        return

    events = ["すべて"] + sorted({row["event"] for row in records})
    categories = ["すべて"] + sorted({row["category"] for row in records})

    filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 1.4])
    with filter_col1:
        selected_event = st.selectbox(
            "公演", events, key="event_gallery_event"
        )
    with filter_col2:
        selected_category = st.selectbox(
            "種類", categories, key="event_gallery_category"
        )
    with filter_col3:
        keyword = st.text_input(
            "画像名で検索",
            placeholder="例：セットリスト、配信、DAY1",
            key="event_gallery_keyword",
        ).strip()

    filtered = []
    for row in records:
        if selected_event != "すべて" and row["event"] != selected_event:
            continue
        if selected_category != "すべて" and row["category"] != selected_category:
            continue
        if keyword and keyword.casefold() not in row["title"].casefold():
            continue
        filtered.append(row)

    st.caption(f"{len(filtered)}枚")
    if not filtered:
        st.info("条件に合う画像はありません。")
        return

    page_size = 12
    page_count = max(1, math.ceil(len(filtered) / page_size))
    page = 1
    if page_count > 1:
        page = st.selectbox(
            "ページ",
            list(range(1, page_count + 1)),
            format_func=lambda value: f"{value} / {page_count}",
            key="event_gallery_page",
        )

    visible = filtered[(page - 1) * page_size : page * page_size]
    columns = st.columns(3)
    for index, row in enumerate(visible):
        image_path = image_dir / row["filename"]
        with columns[index % 3]:
            if image_path.exists():
                st.image(
                    str(image_path),
                    caption=f'{row["event"]}｜{row["title"]}',
                    use_container_width=True,
                )

