from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import streamlit as st


_EVENT_NAME = "列 1"
_ANNOUNCEMENT = "発表"
_DAY1 = "公演日DAY1"
_DAY2 = "公演日DAY2"
_ANCHOR_COLUMNS = {_EVENT_NAME, _ANNOUNCEMENT, _DAY1, _DAY2}
_HISTORY_FILE = Path(__file__).resolve().parent / "ticket_schedule_history.csv"
_EVENTS_FILE = Path(__file__).resolve().parent / "events.csv"
_DENSITY_WINDOW_DAYS = 28
_RECENCY_HALF_LIFE_DAYS = 365 * 3
_TICKET_OPTIONS = [
    ("プレミアム会員先行", lambda name: "プレミアム会員先行" in name and "SPラウンジ" not in name),
    ("一般会員先行", lambda name: "一般会員先行" in name and "ティーン割" not in name),
    ("ティーン割チケット", lambda name: "ティーン割" in name),
    ("ブルーレイ先行", lambda name: "ブルーレイ先行" in name),
    ("CD先行", lambda name: "CD先行" in name),
    ("ゲーム先行", lambda name: "ゲーム先行" in name),
    ("SPラウンジ・バルコニー席", lambda name: "SPラウンジ" in name or "バルコニー席" in name),
    ("一般発売（先着）", lambda name: ("一般発売" in name or "一般販売" in name) and "先着" in name and all(word not in name for word in ("SPラウンジ", "バルコニー席", "2次", "二次", "見切れ", "立見"))),
    ("一般発売（抽選）", lambda name: ("一般発売" in name or "一般販売" in name) and "抽選" in name and all(word not in name for word in ("2次", "二次", "見切れ", "立見"))),
    ("一般販売（二次抽選）", lambda name: "二次抽選" in name or ("一般販売" in name and "二次" in name and "抽選" in name)),
    ("一般発売（二次・先着）", lambda name: "先着" in name and ("一般発売2次" in name or "一般発売（二次" in name)),
    ("見切れ席・立見（先着）", lambda name: ("見切れ" in name or "立見" in name) and "先着" in name),
    ("見切れ席（抽選）", lambda name: "見切れ" in name and "抽選" in name),
    ("リセール", lambda name: "リセール" in name),
]
_TICKET_KEYWORDS = ("先行", "一般発売", "一般販売", "チケット", "リセール", "SPラウンジ", "バルコニー席")


def _parse_date(value: object) -> pd.Timestamp | pd.NaT:
    if pd.isna(value) or not str(value).strip():
        return pd.NaT
    return pd.to_datetime(str(value).strip(), errors="coerce")


def _schedule_columns(frame: pd.DataFrame) -> list[str]:
    candidates = []
    for column in frame.columns:
        if column in _ANCHOR_COLUMNS:
            continue
        parsed = frame[column].map(_parse_date)
        if parsed.notna().sum() >= 1:
            candidates.append(column)
    return candidates


def _short_label(column: str) -> str:
    return re.sub(r"\s+", " ", column.replace("\n", " ")).strip()


def _clean_text(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _event_series(value: object) -> str:
    """公演名から、十分に確信できるシリーズ名だけを取り出す。"""
    text = str(value).upper()
    match = re.search(r"\b(\d+(?:\.\d+)?(?:ST|ND|RD|TH)\s*(?:LIVE|ANNIVERSARY))\b", text)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).replace("ANNIVERSARY", "Anniversary")
    for name in ("MUGEN BEAT", "SUNNY PARTY", "TWINKLE WAY", "PANOR@MA WING", "L@YERED WING"):
        if name in text:
            return name
    return ""


def _venue_scale(value: object) -> str:
    """会場名から、厳密な収容人数ではなく大まかな規模だけを分類する。"""
    venue = str(value).upper()
    if any(word in venue for word in ("ドーム", "DOME")):
        return "ドーム級"
    if any(word in venue for word in ("アリーナ", "ARENA", "さいたまスーパー", "幕張メッセ", "Kアリーナ")):
        return "アリーナ級"
    if any(word in venue for word in ("ホール", "HALL", "武道館", "国際フォーラム", "パシフィコ", "ガーデンシアター")):
        return "ホール級"
    if any(word in venue for word in ("ZEPP", "CLUB", "LIVE HOUSE", "ライブハウス", "MUSE", "MARZ", "LOTUS")):
        return "ライブハウス級"
    return ""


def _season_from_date(value: pd.Timestamp | pd.NaT) -> str:
    if pd.isna(value):
        return ""
    return {12: "冬", 1: "冬", 2: "冬", 3: "春", 4: "春", 5: "春", 6: "夏", 7: "夏", 8: "夏", 9: "秋", 10: "秋", 11: "秋"}[value.month]


def _densest_offsets(offsets: pd.Series) -> pd.Series:
    """日数が最も密集したグループを返し、少数の極端値を予測から外す。"""
    values = sorted(int(value) for value in offsets.dropna())
    if len(values) <= 3:
        return pd.Series(values, dtype="int64")

    best_group = values
    best_rank = (0, float("inf"))
    for start_index, start in enumerate(values):
        group = [value for value in values[start_index:] if value - start <= _DENSITY_WINDOW_DAYS]
        if not group:
            continue
        rank = (len(group), -(group[-1] - group[0]))
        if rank > best_rank:
            best_group = group
            best_rank = rank
    return pd.Series(best_group, dtype="int64")


def _columns_for_option(schedule_columns: list[str], matcher: object) -> list[str]:
    return [column for column in schedule_columns if matcher(_short_label(column))]


def _similar_configuration_history(
    history: pd.DataFrame,
    target_column: str,
    ticket_selection: dict[str, bool],
    option_columns: dict[str, list[str]],
    event_type: str,
    event_series: str = "",
    venue_scale: str = "",
    season: str = "",
) -> tuple[pd.DataFrame, int]:
    """今回のチケット構成に近い履歴を優先して、販売順の変化を学習する。"""
    target_exists = history[target_column].map(_parse_date).notna()
    candidates = history.loc[target_exists].copy()
    if candidates.empty:
        return candidates, 0

    if event_type != "すべて" and "_event_type" in candidates.columns:
        same_type = candidates[candidates["_event_type"] == event_type]
        if len(same_type) >= 5:
            candidates = same_type

    distance = pd.Series(0, index=candidates.index, dtype="int64")
    for label, selected in ticket_selection.items():
        columns = option_columns.get(label, [])
        if not columns:
            continue
        historical_has_ticket = candidates[columns].apply(
            lambda row: any(not pd.isna(_parse_date(value)) for value in row),
            axis=1,
        )
        distance += (historical_has_ticket != selected).astype("int64")

    # 公演名・会場・時期から得た条件は、件数が少ないため除外条件にはせず、
    # 同じチケット構成の中で近いものを優先するために使う。
    context_distance = pd.Series(0.0, index=candidates.index)
    for feature, current_value, weight in (
        ("_event_series", event_series, 2.0),
        ("_venue_scale", venue_scale, 1.0),
        ("_event_season", season, 0.5),
    ):
        if current_value and feature in candidates.columns:
            context_distance += (candidates[feature].fillna("") != current_value).astype(float) * weight

    # 構成が近いものを優先しつつ、新しい公演ほど強く使う。
    day1_dates = candidates[_DAY1].map(_parse_date)
    newest = day1_dates.max()
    if pd.isna(newest):
        recency_penalty = pd.Series(0.0, index=candidates.index)
    else:
        age_days = (newest - day1_dates).dt.days.fillna(_RECENCY_HALF_LIFE_DAYS * 2)
        recency_penalty = age_days / _RECENCY_HALF_LIFE_DAYS
    ranking = pd.DataFrame(
        {"configuration": distance, "context": context_distance, "recency": recency_penalty}
    )
    nearest_count = min(len(candidates), max(5, min(10, len(candidates))))
    nearest_index = ranking.sort_values(["configuration", "context", "recency"], kind="stable").head(nearest_count).index
    return candidates.loc[nearest_index], len(candidates)


@st.cache_data(show_spinner=False)
def _context_improves_accuracy(
    history: pd.DataFrame,
    column: str,
    option_columns: dict[str, list[str]],
) -> tuple[bool, str]:
    """条件一致が実際の過去予測を改善する列だけ、文脈条件を有効にする。"""
    usable = history.loc[
        history[column].map(_parse_date).notna() & history[_DAY1].map(_parse_date).notna()
    ]
    # 全履歴で同じ検証を何十回も行うと画面が重くなるため、直近10件で検証する。
    # この関数自体はデータ更新までキャッシュされる。
    usable = usable.assign(_validation_day1=usable[_DAY1].map(_parse_date)).sort_values("_validation_day1").tail(10)
    if len(usable) < 8:
        return False, "条件一致の検証件数不足"

    baseline_errors: list[float] = []
    context_errors: list[float] = []
    for index, row in usable.iterrows():
        training = history.drop(index=index)
        ticket_selection = {
            label: any(not pd.isna(_parse_date(row[value])) for value in columns)
            for label, columns in option_columns.items()
            if columns
        }
        event_type = _clean_text(row.get("_event_type", "すべて")) or "すべて"
        event_series = _clean_text(row.get("_event_series", ""))
        venue_scale = _clean_text(row.get("_venue_scale", ""))
        season = _clean_text(row.get("_event_season", ""))
        if not any((event_series, venue_scale, season)):
            continue

        baseline, _ = _similar_configuration_history(
            training, column, ticket_selection, option_columns, event_type
        )
        contextual, _ = _similar_configuration_history(
            training, column, ticket_selection, option_columns, event_type,
            event_series, venue_scale, season,
        )
        actual_offset = (_parse_date(row[column]) - _parse_date(row[_DAY1])).days
        for sample, errors in ((baseline, baseline_errors), (contextual, context_errors)):
            offsets = (sample[column].map(_parse_date) - sample[_DAY1].map(_parse_date)).dropna().dt.days
            dense_offsets = _densest_offsets(offsets)
            if not dense_offsets.empty:
                errors.append(abs(actual_offset - float(dense_offsets.median())))

    count = min(len(baseline_errors), len(context_errors))
    if count < 5:
        return False, "条件一致の検証件数不足"
    baseline_mae = sum(baseline_errors[:count]) / count
    context_mae = sum(context_errors[:count]) / count
    # たまたまの微差ではなく、5%以上の改善が確認できた場合だけ採用する。
    if context_mae <= baseline_mae * 0.95:
        return True, f"条件一致で検証誤差 {baseline_mae:.1f}→{context_mae:.1f}日"
    return False, f"条件一致は検証誤差 {baseline_mae:.1f}→{context_mae:.1f}日で不採用"


def _lead_time_prediction(
    history: pd.DataFrame,
    column: str,
    announcement: pd.Timestamp | None,
    event_day1: pd.Timestamp | None,
) -> tuple[pd.Timestamp, pd.Series, float, float, int, float, float] | None:
    """発表からDAY1までの長さが日程をどれだけ動かすかを線形モデルで学習する。"""
    if announcement is None or event_day1 is None:
        return None

    training = pd.DataFrame(
        {
            "announcement": history[_ANNOUNCEMENT].map(_parse_date),
            "day1": history[_DAY1].map(_parse_date),
            "target": history[column].map(_parse_date),
        }
    ).dropna()
    if len(training) < 5:
        return None

    lead_days = (training["day1"] - training["announcement"]).dt.days.astype(float)
    target_offsets = (training["target"] - training["announcement"]).dt.days.astype(float)
    lead_variance = float(((lead_days - lead_days.mean()) ** 2).sum())
    if lead_variance == 0:
        return None

    slope = float(((lead_days - lead_days.mean()) * (target_offsets - target_offsets.mean())).sum() / lead_variance)
    intercept = float(target_offsets.mean() - slope * lead_days.mean())
    fitted = intercept + slope * lead_days
    residuals = target_offsets - fitted
    total_variance = float(((target_offsets - target_offsets.mean()) ** 2).sum())
    r_squared = 1 - float((residuals**2).sum()) / total_variance if total_variance else 0.0
    if r_squared < 0.10:
        return None

    current_lead = float((event_day1 - announcement).days)
    predicted = announcement + pd.Timedelta(days=intercept + slope * current_lead)
    return pd.Timestamp(predicted), residuals, slope, r_squared, len(training), float(lead_days.min()), float(lead_days.max())


def _weekday_adjustment(predicted: pd.Timestamp, dates: pd.Series) -> tuple[pd.Timestamp, str]:
    weekdays = dates.dropna().dt.dayofweek
    if len(weekdays) < 3:
        return predicted, ""
    preferred = int(weekdays.value_counts().idxmax())
    candidates = [predicted + pd.Timedelta(days=delta) for delta in range(-3, 4)]
    adjusted = min(
        (date for date in candidates if date.dayofweek == preferred),
        key=lambda date: abs((date - predicted).days),
        default=predicted,
    )
    if adjusted == predicted:
        return predicted, ""
    return adjusted, f"{adjusted.strftime('%a')}へ調整"


def _parse_known_schedule_text(text: str, columns: list[str]) -> dict[str, pd.Timestamp]:
    """公式告知を行ごとに貼り付けたとき、項目名と日付をできるだけ自動対応させる。"""
    detected: dict[str, pd.Timestamp] = {}
    date_pattern = re.compile(r"(20\d{2})\s*(?:/|年|\.)\s*(\d{1,2})\s*(?:/|月|\.)\s*(\d{1,2})")
    keywords = (
        "プレミアム", "一般会員", "ティーン", "ブルーレイ", "CD", "ゲーム",
        "SPラウンジ", "バルコニー", "一般発売", "一般販売", "リセール",
        "イベントグッズ", "協賛", "キービジュ", "事前販売",
    )
    for raw_line in text.splitlines():
        match = date_pattern.search(raw_line)
        if not match:
            continue
        date = pd.Timestamp(year=int(match.group(1)), month=int(match.group(2)), day=int(match.group(3)))
        line = _short_label(raw_line)
        best_column = None
        best_score = 0
        for column in columns:
            label = _short_label(column)
            score = 0
            for action in ("開始", "終了", "当落"):
                if action in line and action in label:
                    score += 3
            for keyword in keywords:
                if keyword in line and keyword in label:
                    score += 2
            if score > best_score:
                best_column = column
                best_score = score
        if best_column is not None and best_score >= 3:
            detected[best_column] = date
    return detected


def _learn_order_constraints(history: pd.DataFrame, columns: list[str]) -> list[tuple[str, str, int]]:
    """過去データから、必ず守られている販売日程の前後関係を抽出する。"""
    constraints: set[tuple[str, str, int]] = set()
    action_columns: dict[str, dict[str, str]] = {}
    for column in columns:
        label = _short_label(column)
        action = next((value for value in ("開始", "終了", "当落") if value in label), None)
        if action:
            base = re.sub(r"(開始|終了|当落)", "", label).strip()
            action_columns.setdefault(base, {})[action] = column

    for values in action_columns.values():
        if "開始" in values and "終了" in values:
            constraints.add((values["開始"], values["終了"], 0))
        if "終了" in values and "当落" in values:
            constraints.add((values["終了"], values["当落"], 0))
        if "開始" in values and "当落" in values:
            constraints.add((values["開始"], values["当落"], 0))

    ticket_columns = [
        column
        for column in columns
        if any(keyword in _short_label(column) for keyword in _TICKET_KEYWORDS)
    ]
    for before_index, before in enumerate(ticket_columns):
        before_dates = history[before].map(_parse_date)
        for after in ticket_columns[before_index + 1 :]:
            after_dates = history[after].map(_parse_date)
            gaps = (after_dates - before_dates).dropna().dt.days
            if len(gaps) >= 3 and (gaps >= 0).all() and gaps.min() <= 60:
                constraints.add((before, after, int(gaps.min())))
            reverse_gaps = -gaps
            if len(reverse_gaps) >= 3 and (reverse_gaps >= 0).all() and reverse_gaps.min() <= 60:
                constraints.add((after, before, int(reverse_gaps.min())))
    return sorted(constraints)


def _enforce_order_constraints(
    result: pd.DataFrame,
    constraints: list[tuple[str, str, int]],
) -> pd.DataFrame:
    """確定日を動かさず、順序を破る未確定予測だけを後ろへ補正する。"""
    if result.empty:
        return result
    result = result.copy()
    result["予想日"] = pd.to_datetime(result["予想日"])
    result["順序補正"] = ""
    rows_by_column = {row["_column"]: index for index, row in result.iterrows()}
    for _ in range(len(constraints)):
        changed = False
        for before, after, minimum_gap in constraints:
            if before not in rows_by_column or after not in rows_by_column:
                continue
            before_index = rows_by_column[before]
            after_index = rows_by_column[after]
            earliest_after = result.at[before_index, "予想日"] + pd.Timedelta(days=minimum_gap)
            if result.at[after_index, "予想日"] >= earliest_after:
                continue
            if result.at[after_index, "目安の範囲"] == "確定":
                continue
            result.at[after_index, "予想日"] = earliest_after
            note = f"{_short_label(before)}の後へ補正"
            result.at[after_index, "順序補正"] = "／".join(
                part for part in [result.at[after_index, "順序補正"], note] if part
            )
            changed = True
        if not changed:
            break
    result["予想日"] = result["予想日"].dt.date
    return result


def _prediction_row(
    history: pd.DataFrame,
    column: str,
    announcement: pd.Timestamp | None,
    event_day1: pd.Timestamp | None,
    ticket_selection: dict[str, bool],
    option_columns: dict[str, list[str]],
    event_type: str,
    event_series: str,
    venue_scale: str,
    season: str,
    known_dates: dict[str, pd.Timestamp],
    as_of_date: pd.Timestamp | None,
) -> dict[str, object] | None:
    if column in known_dates:
        return {
            "_column": column,
            "項目": _short_label(column),
            "予想日": known_dates[column].date(),
            "目安の範囲": "確定",
            "採用基準": "入力済みの日程",
            "期間による補正": "",
            "発表日から": "",
            "DAY1から": "",
            "信頼度": "確定",
            "外れ値リスク": "なし（確定日）",
            "類似構成": "",
            "採用件数": "",
        }
    use_context, context_validation = _context_improves_accuracy(history, column, option_columns)
    learning_history, total_target_count = _similar_configuration_history(
        history,
        column,
        ticket_selection,
        option_columns,
        event_type,
        event_series if use_context else "",
        venue_scale if use_context else "",
        season if use_context else "",
    )
    dates = learning_history[column].map(_parse_date)
    all_announcement_offsets = (dates - learning_history[_ANNOUNCEMENT].map(_parse_date)).dropna().dt.days
    all_event_offsets = (dates - learning_history[_DAY1].map(_parse_date)).dropna().dt.days
    announcement_offsets = _densest_offsets(all_announcement_offsets)
    event_offsets = _densest_offsets(all_event_offsets)
    lead_model = _lead_time_prediction(learning_history, column, announcement, event_day1)

    candidates: list[tuple[float, str, pd.Timestamp, pd.Series]] = []
    if announcement is not None and not announcement_offsets.empty:
        spread = float((announcement_offsets - announcement_offsets.median()).abs().median())
        score = len(announcement_offsets) / (1 + spread)
        candidates.append(
            (
                score,
                "発表日基準",
                announcement + pd.Timedelta(days=float(announcement_offsets.median())),
                announcement_offsets,
            )
        )
    if event_day1 is not None and not event_offsets.empty:
        spread = float((event_offsets - event_offsets.median()).abs().median())
        score = len(event_offsets) / (1 + spread)
        candidates.append(
            (
                score,
                "DAY1基準",
                event_day1 + pd.Timedelta(days=float(event_offsets.median())),
                event_offsets,
            )
        )
    sequence_candidates: list[tuple[float, str, pd.Timestamp, pd.Series]] = []
    for known_column, known_date in known_dates.items():
        if known_column not in learning_history.columns:
            continue
        known_offsets = (dates - learning_history[known_column].map(_parse_date)).dropna().dt.days
        dense_known_offsets = _densest_offsets(known_offsets)
        if dense_known_offsets.empty:
            continue
        known_spread = float((dense_known_offsets - dense_known_offsets.median()).abs().median())
        known_score = len(dense_known_offsets) / (1 + known_spread)
        sequence_candidates.append(
            (
                known_score,
                f"{_short_label(known_column)}からの連鎖",
                known_date + pd.Timedelta(days=float(dense_known_offsets.median())),
                dense_known_offsets,
            )
        )
    if not candidates:
        return None

    lead_model_summary = ""
    if sequence_candidates:
        total_score = sum(candidate[0] for candidate in sequence_candidates)
        weighted_timestamp = sum(candidate[0] * candidate[2].value for candidate in sequence_candidates) / total_score
        predicted = pd.Timestamp(int(weighted_timestamp))
        selected_basis = "確定日程との相関"
        selected_offsets = pd.concat([candidate[3] for candidate in sequence_candidates], ignore_index=True)
        spread = max(7, int((selected_offsets - selected_offsets.median()).abs().quantile(0.80)))
        correlation_sources = "・".join(_short_label(candidate[1].removesuffix("からの連鎖")) for candidate in sequence_candidates)
        lead_model_summary = f"{correlation_sources}との日程差を学習"
    elif lead_model is not None:
        predicted, residuals, slope, r_squared, sample_count, lead_min, lead_max = lead_model
        selected_basis = "発表〜DAY1の期間を学習"
        selected_offsets = residuals
        spread = max(7, int(residuals.abs().quantile(0.80)))
        lead_model_summary = f"1日長いと {slope:+.2f}日／説明力 {r_squared:.0%}／{sample_count}件"
        current_lead = float((event_day1 - announcement).days) if announcement is not None and event_day1 is not None else 0
        learned_error = float(residuals.abs().quantile(0.90))
        outside_range = current_lead < lead_min or current_lead > lead_max
        outlier_risk = "高" if outside_range or learned_error > 45 else "中" if learned_error > 25 else "低"
        risk_detail = f"{outlier_risk}（過去90%誤差 ±{learned_error:.0f}日" + ("／期間が学習範囲外" if outside_range else "") + "）"
    else:
        _, selected_basis, predicted, selected_offsets = max(candidates, key=lambda item: item[0])
        predicted = pd.Timestamp(predicted)
        spread = max(7, int((selected_offsets - selected_offsets.median()).abs().quantile(0.80)))

    if lead_model is None or sequence_candidates:
        learned_error = float((selected_offsets - selected_offsets.median()).abs().quantile(0.90))
        outlier_risk = "高" if learned_error > 45 else "中" if learned_error > 25 else "低"
        risk_detail = f"{outlier_risk}（過去90%誤差 ±{learned_error:.0f}日）"

    predicted, weekday_note = _weekday_adjustment(predicted, dates)
    today_note = ""
    # 未確定の予定は、基準日（通常は今日）より前には置かない。
    # 入力済みの確定日程は関数の冒頭で返しているため、この補正の対象外。
    if as_of_date is not None and predicted.normalize() < as_of_date.normalize():
        predicted = as_of_date.normalize()
        today_note = f"基準日（{as_of_date.strftime('%Y/%m/%d')}）以降に補正"

    confidence = "高" if len(selected_offsets) >= 5 and spread <= 14 else "参考"
    announcement_median = int(announcement_offsets.median()) if not announcement_offsets.empty else None
    announcement_mean = int(round(announcement_offsets.mean())) if not announcement_offsets.empty else None
    event_median = int(event_offsets.median()) if not event_offsets.empty else None
    event_mean = int(round(event_offsets.mean())) if not event_offsets.empty else None
    return {
        "_column": column,
        "項目": _short_label(column),
        "予想日": predicted.date(),
        "目安の範囲": f"±{spread}日",
        "採用基準": selected_basis,
        "期間による補正": "／".join(
            part for part in [lead_model_summary, context_validation, weekday_note, today_note] if part
        ) or "関係が弱いため未適用",
        "発表日から": f"中央値 {announcement_median:+d}日／平均 {announcement_mean:+d}日" if announcement_median is not None else "データ不足",
        "DAY1から": f"中央値 {event_median:+d}日／平均 {event_mean:+d}日" if event_median is not None else "データ不足",
        "信頼度": confidence,
        "外れ値リスク": risk_detail,
        "類似構成": f"{len(learning_history)}/{total_target_count}件",
        "採用件数": f"発表日 {len(announcement_offsets)}/{len(all_announcement_offsets)}件・DAY1 {len(event_offsets)}/{len(all_event_offsets)}件",
    }


def _event_name_key(value: object) -> str:
    text = str(value).casefold()
    text = re.sub(r"day\s*\d+", "", text)
    return re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]+", "", text)


def _fill_event_dates_from_events(history: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if not _EVENTS_FILE.exists():
        return history, 0
    try:
        events = pd.read_csv(_EVENTS_FILE, encoding="utf-8-sig")
    except UnicodeDecodeError:
        events = pd.read_csv(_EVENTS_FILE, encoding="cp932")
    if not {"日付", "公演名"}.issubset(events.columns):
        return history, 0

    history = history.copy()
    # 履歴CSVではDAY1が空欄のみのため、pandasがfloat列として読み込む。
    # 公演データから日付文字列を補完できるよう、明示的に汎用列へ変換する。
    history[_DAY1] = history[_DAY1].astype("object")
    events["_date"] = events["日付"].map(_parse_date)
    events = events.dropna(subset=["_date", "公演名"])
    candidates = [
        {
            "key": _event_name_key(row["公演名"]),
            "date": pd.Timestamp(row["_date"]),
            "type": str(row.get("公演区分", "")),
            "series": _event_series(row["公演名"]),
            "venue_scale": _venue_scale(row.get("会場", "")),
            "season": _season_from_date(pd.Timestamp(row["_date"])),
        }
        for _, row in events.iterrows()
    ]

    filled = 0
    for index, row in history.iterrows():
        target = _event_name_key(row[_EVENT_NAME])
        if not target:
            continue
        direct_matches = [
            candidate
            for candidate in candidates
            if target in candidate["key"] or candidate["key"] in target
        ]
        if direct_matches:
            best_match = min(direct_matches, key=lambda item: item["date"])
        else:
            best_score = 0.0
            best_match: dict[str, object] | None = None
            for candidate in candidates:
                score = SequenceMatcher(None, target, str(candidate["key"])).ratio()
                if score > best_score:
                    best_score = score
                    best_match = candidate
            if best_match is None or best_score < 0.62:
                continue

        if pd.isna(_parse_date(row[_DAY1])):
            history.at[index, _DAY1] = pd.Timestamp(best_match["date"]).strftime("%Y/%m/%d")
            filled += 1
        history.at[index, "_event_type"] = str(best_match["type"])
        history.at[index, "_event_series"] = str(best_match["series"])
        history.at[index, "_venue_scale"] = str(best_match["venue_scale"])
        history.at[index, "_event_season"] = str(best_match["season"])
    return history, filled


def render_schedule_prediction() -> None:
    st.markdown("---")
    st.header("ライブスケジュール予想")
    st.caption("過去公演の発表日・DAY1・DAY2と販売日程の差分から算出する参考予測です。公式発表ではありません。")

    if not _HISTORY_FILE.exists():
        st.error("予想に必要な履歴データが見つかりません。")
        return

    try:
        history = pd.read_csv(_HISTORY_FILE, encoding="utf-8-sig")
    except UnicodeDecodeError:
        history = pd.read_csv(_HISTORY_FILE, encoding="cp932")
    except Exception as error:
        st.error(f"CSVを読み込めませんでした：{error}")
        return

    missing = _ANCHOR_COLUMNS - set(history.columns)
    if missing:
        st.error(f"必要な列がありません：{', '.join(sorted(missing))}")
        return

    history, filled_event_dates = _fill_event_dates_from_events(history)
    if filled_event_dates:
        st.caption(f"既存の公演データから、過去公演のDAY1を{filled_event_dates}件補完して予測に利用しています。")

    schedule_columns = _schedule_columns(history)
    if not schedule_columns:
        st.error("予想に使える日程列が見つかりませんでした。")
        return

    test_options: list[int | None] = [None, *history.index.tolist()]
    selected_test_index = st.selectbox(
        "過去公演を選んで予測を試す",
        test_options,
        format_func=lambda index: "手入力で予測する" if index is None else str(history.at[index, _EVENT_NAME]),
        key="prediction_test_event",
        help="選んだ公演の実際の日程は学習から隠し、発表日・DAY1・チケット構成だけで予測します。",
    )

    selected_test_row = history.loc[selected_test_index] if selected_test_index is not None else None
    if selected_test_row is None:
        input_col1, input_col2 = st.columns(2)
        with input_col1:
            announcement_input = st.date_input("発表日（任意）", value=None, key="prediction_announcement")
        with input_col2:
            day1_input = st.date_input("DAY1（任意）", value=None, key="prediction_day1")
        if not announcement_input and not day1_input:
            st.info("発表日またはDAY1を入力してください。")
            return
        announcement = pd.Timestamp(announcement_input) if announcement_input else None
        event_day1 = pd.Timestamp(day1_input) if day1_input else None
        prediction_history = history
    else:
        announcement = _parse_date(selected_test_row[_ANNOUNCEMENT])
        event_day1 = _parse_date(selected_test_row[_DAY1])
        if pd.isna(announcement) or pd.isna(event_day1):
            st.warning("この公演は発表日またはDAY1が不足しているため、選択検証には使えません。")
            return
        prediction_history = history.drop(index=selected_test_index)
        st.info(
            f"発表日：{announcement.strftime('%Y/%m/%d')}　／　DAY1：{event_day1.strftime('%Y/%m/%d')}　／　DAY2：{(event_day1 + pd.Timedelta(days=1)).strftime('%Y/%m/%d')}"
        )

    as_of_input = st.date_input(
        "予測の基準日（今日）",
        value=pd.Timestamp.today().date(),
        key="prediction_as_of_date",
        help="まだ発表されていない日程は、この日より前には予想しません。過去公演の検証では、当時の日付に変更できます。",
    )
    as_of_date = pd.Timestamp(as_of_input) if as_of_input else None

    if event_day1 is not None:
        event_day2 = pd.Timestamp(event_day1) + pd.Timedelta(days=1)
        st.caption(f"DAY2はDAY1の翌日として扱います：{event_day2.strftime('%Y/%m/%d')}")

    if selected_test_row is not None:
        # ???????????????????????????????????
        selected_event_type = _clean_text(selected_test_row.get("_event_type", ""))
        selected_series = _clean_text(selected_test_row.get("_event_series", ""))
        selected_venue_scale = _clean_text(selected_test_row.get("_venue_scale", ""))
    else:
        selected_event_type = ""
        selected_series = ""
        selected_venue_scale = ""

    selected_season = _season_from_date(event_day1)

    st.subheader("今回あるチケット種別")
    st.caption("当てはまるチケット種別だけをオンにしてください。グッズ・キービジュアルなどの予定は常に表示します。")
    option_columns = {
        label: _columns_for_option(schedule_columns, matcher)
        for label, matcher in _TICKET_OPTIONS
    }
    ticket_columns = {
        column
        for columns in option_columns.values()
        for column in columns
    }
    selected_columns = [
        column
        for column in schedule_columns
        if column not in ticket_columns and not any(keyword in _short_label(column) for keyword in _TICKET_KEYWORDS)
    ]
    toggle_columns = st.columns(2)
    ticket_selection: dict[str, bool] = {}
    for index, (label, columns) in enumerate(option_columns.items()):
        if not columns:
            continue
        with toggle_columns[index % 2]:
            if selected_test_row is not None:
                enabled = any(not pd.isna(_parse_date(selected_test_row[column])) for column in columns)
                st.caption(f"{'●' if enabled else '○'} {label}")
            else:
                enabled = st.toggle(label, value=False, key=f"prediction_ticket_{index}")
            ticket_selection[label] = enabled
            if enabled:
                selected_columns.extend(columns)

    known_dates = st.session_state.setdefault("prediction_known_dates", {})
    if selected_columns:
        with st.expander("確定済み日程を追加して再予測する"):
            st.caption("追加したい種別だけにチェックを入れ、日付をカレンダーで選んでください。")
            available_columns = list(dict.fromkeys(selected_columns))
            today = pd.Timestamp.today().date()
            bulk_input = pd.DataFrame(
                {
                    "追加": [column in known_dates for column in available_columns],
                    "種別": [_short_label(column) for column in available_columns],
                    "日付": [known_dates.get(column, pd.Timestamp(today)).date() for column in available_columns],
                    "_column": available_columns,
                }
            )
            edited_bulk_input = st.data_editor(
                bulk_input,
                column_config={
                    "追加": st.column_config.CheckboxColumn("追加", help="予測に使う確定日として追加します"),
                    "種別": st.column_config.TextColumn("種別"),
                    "日付": st.column_config.DateColumn("確定した日付", format="YYYY/MM/DD"),
                    "_column": None,
                },
                disabled=["種別", "_column"],
                hide_index=True,
                use_container_width=True,
                key="prediction_known_bulk_editor",
            )
            if st.button("チェックした日程をまとめて追加", key="prediction_known_bulk_add"):
                for _, row in edited_bulk_input[edited_bulk_input["追加"]].iterrows():
                    known_dates[row["_column"]] = pd.Timestamp(row["日付"])
                st.rerun()
            if known_dates:
                st.caption("入力済み：" + "、 ".join(f"{_short_label(name)}（{date.strftime('%Y/%m/%d')}）" for name, date in known_dates.items()))
                if st.button("入力済み日程をすべて消す", key="prediction_known_clear"):
                    known_dates.clear()
                    st.rerun()

    predictions = [
        _prediction_row(
            prediction_history,
            column,
            announcement,
            event_day1,
            ticket_selection,
            option_columns,
            selected_event_type,
            selected_series,
            selected_venue_scale,
            selected_season,
            known_dates,
            as_of_date,
        )
        for column in dict.fromkeys(selected_columns)
    ]
    result = pd.DataFrame(row for row in predictions if row is not None)
    if result.empty:
        st.info("入力日から予想できる項目がありません。")
        return

    order_constraints = _learn_order_constraints(prediction_history, list(dict.fromkeys(selected_columns)))
    result = _enforce_order_constraints(result, order_constraints)
    result = result.sort_values("予想日", kind="stable")
    st.subheader("予想結果")
    public_result = result[["項目", "予想日", "目安の範囲", "信頼度"]].rename(
        columns={
            "項目": "チケット種別",
            "目安の範囲": "誤差",
            "信頼度": "信頼性",
        }
    )
    st.dataframe(public_result, use_container_width=True, hide_index=True)
