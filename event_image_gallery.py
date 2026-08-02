from __future__ import annotations

import csv
import hashlib
import math
import re
import os
from pathlib import Path

import pandas as pd
import streamlit as st


_MANIFEST_FIELDS = ["event", "category", "title", "filename"]
_IMAGE_TYPES = ["jpg", "jpeg", "png", "webp"]
_PUBLIC_MODE = os.environ.get("SHINY_APP_MODE", "local").casefold() == "public"
_EVENT_HINTS = [
    ("8TH", "THE IDOLM@STER SHINY COLORS ∞th LIVE iと夢"),
    ("STILL BULE", "Shiny, the first REFRAC7IONS “Still blue”"),
    ("STILL BLUE", "Shiny, the first REFRAC7IONS “Still blue”"),
    ("5.5TH", "THE IDOLM@STER SHINY COLORS 5.5th Anniversary LIVE 星が見上げた空"),
    ("6.5TH", "THE IDOLM@STER SHINY COLORS 6.5th Anniversary LIVE Chapter 283"),
    ("4TH", "THE IDOLM@STER SHINY COLORS 4thLIVE 空は澄み、今を越えて。"),
    ("5TH", "THE IDOLM@STER SHINY COLORS 5thLIVE If I_wings."),
    ("6TH", "THE IDOLM@STER SHINY COLORS 6thLIVE TOUR Come and Unite!"),
    ("LIVEFUN", "THE IDOLM@STER SHINY COLORS LIVE FUN!! -Beyond the Blue sky-"),
    ("MUGEN", "283PRODUCTION UNIT LIVE MUGEN BEAT"),
    ("SETSUNA", "283PRODUCTION UNIT LIVE SETSUNA BEAT"),
    ("ユニットライブツアー", "THE IDOLM@STER SHINY COLORS 7th UNITLIVE TOUR 円環 -Halo around-"),
    ("円環", "THE IDOLM@STER SHINY COLORS 7th UNITLIVE TOUR 円環 -Halo around-"),
    ("螺旋", "THE IDOLM@STER SHINY COLORS 7th LIVE TOUR 螺旋 -Halo around-"),
    ("我儘", "283PRODUCTION SOLO PERFORMANCE LIVE「我儘なまま」"),
    ("大感謝祭", "THE IDOLM@STER SHINY COLORS シャニマス大感謝祭！"),
    ("シャニアニ2ND", "THE IDOLM@STER SHINY COLORS 2nd season LIVE Over the prism"),
    ("MSP", "THE IDOLM@STER M@STERS OF IDOL WORLD!!!!! 2023"),
]


def _load_images(manifest_path: Path) -> list[dict[str, str]]:
    if not manifest_path.exists():
        return []

    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            row
            for row in csv.DictReader(handle)
            if row.get("filename") and row.get("event") and row.get("title")
        ]


def _save_image_record(manifest_path: Path, record: dict[str, str]) -> None:
    needs_header = not manifest_path.exists() or manifest_path.stat().st_size == 0
    with manifest_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_MANIFEST_FIELDS)
        if needs_header:
            writer.writeheader()
        writer.writerow(record)


def _image_link_hint(path: Path) -> tuple[str, str]:
    """ファイル名から安全に判断できる分類・公演候補だけを表示する。"""
    name = path.stem.upper().replace("　", " ")
    if "ガシャ" in path.stem:
        return "ガチャ", "ガチャ情報として紐づけ候補"
    if "シナリオイベント" in path.stem:
        return "ゲーム内イベント", "イベント名へ紐づけ候補"
    if "衣装設定" in path.stem or "衣装" in path.stem:
        return "衣装", "衣装名へ紐づけ候補"
    if "イベントあらすじ" in path.stem or "イベント画像" in path.stem:
        return "ゲーム内イベント", "イベント名へ紐づけ候補"
    if "スケジュール" in path.stem:
        return "カレンダー", "月・年のスケジュール画像"
    for keyword, event_name in _EVENT_HINTS:
        if keyword in name:
            return "公演", event_name
    if "7TH" in name:
        return "公演", "7th系（円環・螺旋などの判別が必要）"
    return "共通資料", "自動判定できません"


def _material_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "シャニマス素材"


@st.cache_data(show_spinner=False)
def _material_image_paths() -> list[str]:
    source_dir = _material_dir()
    if not source_dir.exists():
        return []
    return [
        str(path)
        for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower().lstrip(".") in _IMAGE_TYPES
    ]


def _name_key(value: object) -> str:
    text = str(value).casefold()
    text = re.sub(r"day\s*\d+", "", text)
    return re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff∞]+", "", text)


def _render_context_images(title: str, paths: list[Path]) -> None:
    if not paths:
        return
    st.subheader(title)
    columns = st.columns(min(3, len(paths)))
    source_dir = _material_dir()
    for index, path in enumerate(paths[:3]):
        with columns[index % len(columns)]:
            st.image(str(path), caption=str(path.relative_to(source_dir)), width=180)
            with st.expander("🔍 タップして拡大"):
                st.image(str(path), use_container_width=True)


def render_event_context_images(event_name: str) -> None:
    if _PUBLIC_MODE:
        return
    event_key = _name_key(event_name)
    matched: list[Path] = []
    for raw_path in _material_image_paths():
        path = Path(raw_path)
        category, hint = _image_link_hint(path)
        hint_key = _name_key(hint)
        if category == "公演" and hint_key and (hint_key in event_key or event_key in hint_key):
            matched.append(path)
    day_match = re.search(r"DAY\s*(\d+)", event_name, flags=re.IGNORECASE)
    if day_match:
        day = day_match.group(1)
        matched = [
            path for path in matched
            if f"DAY{day}" in path.stem.upper() and "セットリスト" in path.stem
        ]
        _render_context_images(f"🖼️ DAY{day} セットリスト画像", matched)
    else:
        _render_context_images("🖼️ この公演の関連画像", matched)


def render_costume_context_images(costume_name: str) -> None:
    if _PUBLIC_MODE:
        return
    costume_key = _name_key(costume_name)
    matched = [
        Path(raw_path)
        for raw_path in _material_image_paths()
        if costume_key and costume_key in _name_key(Path(raw_path).stem)
    ]
    _render_context_images("🖼️ この衣装の設定画像", matched)


def render_gacha_context_images() -> None:
    if _PUBLIC_MODE:
        return
    matched = [
        Path(raw_path)
        for raw_path in _material_image_paths()
        if "ガシャ" in Path(raw_path).stem
    ]
    _render_context_images("🖼️ ガチャ関連画像", matched)


def render_calendar_context_images(year: int, month: int) -> None:
    if _PUBLIC_MODE:
        return
    month_text = f"{month}月"
    year_text = str(year)
    matched = [
        Path(raw_path)
        for raw_path in _material_image_paths()
        if "スケジュール" in Path(raw_path).stem
        and month_text in Path(raw_path).stem
        and (year_text in Path(raw_path).stem or "20" not in Path(raw_path).stem)
    ]
    _render_context_images(f"🖼️ {year}年{month}月の関連スケジュール画像", matched)


def _render_source_image_browser(source_dir: Path) -> None:
    """素材フォルダをそのまま閲覧する。登録やコピーは不要。"""
    image_files = sorted(
        path for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower().lstrip(".") in _IMAGE_TYPES
    )
    if not image_files:
        return

    st.subheader("シャニマス素材をそのまま見る")
    st.caption(f"{len(image_files)}枚をPC内のフォルダから直接表示しています。登録は不要です。")
    name_filter = st.text_input(
        "素材ファイル名で絞り込む",
        placeholder="例：8th、ゲーム先行、キービジュアル",
        key="material_image_browser_filter",
    ).strip()
    visible_files = [
        path for path in image_files
        if not name_filter or name_filter.casefold() in str(path.relative_to(source_dir)).casefold()
    ]
    if not visible_files:
        st.info("条件に合う画像はありません。")
        return

    page_size = 12
    page_count = max(1, math.ceil(len(visible_files) / page_size))
    page = 1
    if page_count > 1:
        page = st.selectbox(
            "素材のページ",
            list(range(1, page_count + 1)),
            format_func=lambda value: f"{value} / {page_count}",
            key="material_image_browser_page",
        )
    files_on_page = visible_files[(page - 1) * page_size : page * page_size]
    columns = st.columns(3)
    for index, path in enumerate(files_on_page):
        with columns[index % 3]:
            category, link_hint = _image_link_hint(path)
            st.image(
                str(path),
                caption=f"{path.relative_to(source_dir)}\n【{category}】{link_hint}",
                use_container_width=True,
            )


def _render_local_image_import(
    source_dir: Path,
    manifest_path: Path,
    *,
    label: str,
    store_relative_filename: bool,
    key_prefix: str,
) -> None:
    """PC内の画像を、会話へ送らずにまとめて登録する。"""
    records = _load_images(manifest_path)
    registered = {row["filename"] for row in records}
    image_files = sorted(
        path for path in source_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower().lstrip(".") in _IMAGE_TYPES
        and (path.name if store_relative_filename else str(path)) not in registered
    )
    if not image_files:
        return

    with st.expander(f"{label}の未登録画像をまとめて登録（{len(image_files)}枚）", expanded=True):
        st.caption("画像はPC内でそのまま読み込みます。会話へアップロード・コピーする必要はありません。")
        name_filter = st.text_input(
            "ファイル名で絞り込む",
            placeholder="例：8th、ゲーム先行、キービジュアル",
            key=f"{key_prefix}_filter",
        ).strip()
        visible_files = [
            path for path in image_files
            if not name_filter or name_filter.casefold() in path.name.casefold()
        ][:100]
        event = st.text_input(
            "この一括登録の公演名",
            placeholder="例：7th LIVE TOUR 螺旋 -THE ASCENT-",
            key=f"{key_prefix}_event",
        )
        category = st.selectbox(
            "カテゴリ",
            ["告知", "キービジュアル", "チケット", "ゲーム先行", "グッズ", "セットリスト", "会場", "その他"],
            key=f"{key_prefix}_category",
        )
        if not visible_files:
            st.info("条件に合う未登録画像はありません。")
            return

        selection = pd.DataFrame(
            {
                "追加": [False] * len(visible_files),
                "ファイル名": [str(path.relative_to(source_dir)) for path in visible_files],
                "画像タイトル": [path.stem for path in visible_files],
                "_path": [str(path) for path in visible_files],
            }
        )
        edited = st.data_editor(
            selection,
            column_config={
                "追加": st.column_config.CheckboxColumn("追加"),
                "ファイル名": st.column_config.TextColumn("ファイル名"),
                "画像タイトル": st.column_config.TextColumn("画像タイトル"),
                "_path": None,
            },
            disabled=["ファイル名", "_path"],
            hide_index=True,
            use_container_width=True,
            key=f"{key_prefix}_editor",
        )
        chosen = edited[edited["追加"]]
        if st.button(f"チェックした画像を登録（{len(chosen)}枚）", key=f"{key_prefix}_submit"):
            if not event.strip() or chosen.empty:
                st.error("公演名を入力し、追加する画像にチェックを入れてください。")
                return
            for _, row in chosen.iterrows():
                _save_image_record(
                    manifest_path,
                    {
                        "event": event.strip(),
                        "category": category,
                        "title": str(row["画像タイトル"]).strip() or Path(row["ファイル名"]).stem,
                        "filename": Path(str(row["_path"])).name if store_relative_filename else str(row["_path"]),
                    },
                )
            st.success(f"{len(chosen)}枚を登録しました。")
            st.rerun()


def _render_image_registration(app_dir: Path, image_dir: Path, manifest_path: Path) -> None:
    with st.expander("画像を追加する", expanded=False):
        st.caption("画像を選び、イベント名・カテゴリ・タイトルを入力して登録します。")
        with st.form("event_image_registration", clear_on_submit=True):
            uploaded_image = st.file_uploader(
                "画像ファイル",
                type=_IMAGE_TYPES,
                help="JPG、PNG、WebP形式に対応しています。",
            )
            event = st.text_input("イベント名", placeholder="例：7th LIVE TOUR 螺旋 -THE ASCENT-")
            category = st.text_input("カテゴリ", value="告知", placeholder="例：告知、セットリスト、会場、グッズ")
            title = st.text_input("画像タイトル", placeholder="例：DAY1 セットリスト")
            submitted = st.form_submit_button("この画像を登録")

        if not submitted:
            return
        if uploaded_image is None or not event.strip() or not category.strip() or not title.strip():
            st.error("画像ファイル、イベント名、カテゴリ、画像タイトルをすべて入力してください。")
            return

        image_bytes = uploaded_image.getvalue()
        extension = Path(uploaded_image.name).suffix.lower().lstrip(".")
        if extension not in _IMAGE_TYPES:
            st.error("対応していない画像形式です。")
            return

        filename = f"{hashlib.sha256(image_bytes).hexdigest()[:16]}.{extension}"
        image_path = image_dir / filename
        image_dir.mkdir(parents=True, exist_ok=True)
        if not image_path.exists():
            image_path.write_bytes(image_bytes)

        records = _load_images(manifest_path)
        if any(row["filename"] == filename for row in records):
            st.info("この画像はすでに登録されています。")
            return

        _save_image_record(
            manifest_path,
            {
                "event": event.strip(),
                "category": category.strip(),
                "title": title.strip(),
                "filename": filename,
            },
        )
        st.success("画像を登録しました。")
        st.rerun()


def render_event_image_gallery() -> None:
    if _PUBLIC_MODE:
        st.info("公開版では、画像・歌詞などの権利確認が必要な素材は掲載していません。")
        return
    app_dir = Path(__file__).resolve().parent
    image_dir = app_dir / "event_images"
    manifest_path = app_dir / "event_images.csv"

    st.markdown("---")
    st.header("イベント画像ギャラリー")
    st.caption("公演や告知の画像を、イベント・カテゴリ・キーワードで絞り込めます。")
    image_dir.mkdir(parents=True, exist_ok=True)
    material_dir = app_dir.parent / "シャニマス素材"
    if material_dir.exists():
        _render_source_image_browser(material_dir)
        _render_local_image_import(
            material_dir,
            manifest_path,
            label="デスクトップの「シャニマス素材」フォルダ",
            store_relative_filename=False,
            key_prefix="material_image_import",
        )
    _render_image_registration(app_dir, image_dir, manifest_path)

    records = _load_images(manifest_path)
    if not records:
        st.info("まだ登録された画像はありません。上の「画像を追加する」から最初の画像を登録してください。")
        return

    events = ["すべて"] + sorted({row["event"] for row in records})
    categories = ["すべて"] + sorted({row["category"] for row in records})

    filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 1.4])
    with filter_col1:
        selected_event = st.selectbox("イベント", events, key="event_gallery_event")
    with filter_col2:
        selected_category = st.selectbox("カテゴリ", categories, key="event_gallery_category")
    with filter_col3:
        keyword = st.text_input(
            "画像タイトルで検索",
            placeholder="例：セットリスト、DAY1",
            key="event_gallery_keyword",
        ).strip()

    filtered = [
        row
        for row in records
        if (selected_event == "すべて" or row["event"] == selected_event)
        and (selected_category == "すべて" or row["category"] == selected_category)
        and (not keyword or keyword.casefold() in row["title"].casefold())
    ]

    st.caption(f"{len(filtered)}件")
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
        image_path = Path(row["filename"])
        if not image_path.is_absolute():
            image_path = image_dir / image_path
        with columns[index % 3]:
            if image_path.exists():
                st.image(
                    str(image_path),
                    caption=f'{row["event"]}｜{row["category"]}｜{row["title"]}',
                    use_container_width=True,
                )
            else:
                st.warning(f'画像ファイルが見つかりません：{row["filename"]}')
