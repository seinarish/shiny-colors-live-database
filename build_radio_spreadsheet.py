from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DOWNLOADS = Path(r"C:\Users\takey\Downloads")
EPISODE_FILE = ROOT / "shiny_radio_episodes.tsv"
REGULAR_FILE = ROOT / "shiny_radio_appearances.csv"
GUEST_FILE = DOWNLOADS / "\u60c5\u5831\u307e\u3068\u3081 - \u30b2\u30b9\u30c8.csv"
MC_FILE = DOWNLOADS / "\u60c5\u5831\u307e\u3068\u3081 - \u30de\u30f3\u30b9\u30ea\u30fcMC.csv"
ABSENCE_FILE = DOWNLOADS / "\u60c5\u5831\u307e\u3068\u3081 - \u30b7\u30e3\u30cb\u30e9\u30b8\u6b20\u5e2d.csv"
OUTPUT_FILE = ROOT / "\u30b7\u30e3\u30cb\u30e9\u30b8_\u7d71\u5408\u7de8\u96c6\u7528.tsv"


def normalize_cast_name(value: str) -> str:
    value = str(value or "").strip()
    value = value.replace("\u5c0f\u6fa4\u9e97\u5948", "\u5c0f\u6fa4\u9e97\u90a3")
    return re.sub(r"[\u2460-\u2473]", "", value).strip()


def add_value(target: dict[int, list[str]], episode: int, name: str) -> None:
    if name and name not in target[episode]:
        target[episode].append(name)


def read_wide_episode_csv(path: Path) -> dict[int, list[str]]:
    result: dict[int, list[str]] = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 3 or not row[0].strip().isdigit():
                continue
            name = normalize_cast_name(row[1])
            for value in row[2:]:
                if value.strip().isdigit():
                    add_value(result, int(value.strip()), name)
    return result


def main() -> None:
    regular_by_episode = read_wide_episode_csv(REGULAR_FILE)
    guest_by_episode = read_wide_episode_csv(GUEST_FILE)
    absence_by_episode = read_wide_episode_csv(ABSENCE_FILE)

    mc_by_month: dict[str, list[str]] = defaultdict(list)
    with MC_FILE.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 3 or not re.fullmatch(r"\d{4}/\d{1,2}", row[2].strip()):
                continue
            name = normalize_cast_name(row[1])
            if name and name not in mc_by_month[row[2].strip()]:
                mc_by_month[row[2].strip()].append(name)

    episode_records: list[tuple[int, str, str, str]] = []
    pending_episode: tuple[int, str] | None = None
    # 元TSVにはフルサイズ版の補助行があり、一部の行はCSVとしては不完全。
    # 先頭が「回\t」の正式行だけを、改行単位で安全に採用する。
    for line in EPISODE_FILE.read_text(encoding="utf-8-sig").splitlines():
        row = line.split("\t", maxsplit=2)
        if row[0].strip().isdigit():
            if len(row) >= 3:
                episode_records.append((int(row[0].strip()), row[1].strip(), row[2].strip(), ""))
                pending_episode = None
            elif len(row) == 2:
                pending_episode = (int(row[0].strip()), row[1].strip())
            continue
        if pending_episode and "\t" in line:
            detail, broadcast_at = line.rsplit("\t", maxsplit=1)
            episode_records.append((pending_episode[0], pending_episode[1], broadcast_at.strip(), detail.strip()))
            pending_episode = None

    output_rows: list[dict[str, str | int]] = []
    for number, raw, broadcast_at, detail in episode_records:
        title = ""
        unit = ""
        monthly_mc: list[str] = []
        guests: list[str] = []

        detail_text = detail or raw
        unit_match = re.match(r"^\u51fa\u6f14[\uff1a:]\s*(.+)$", detail_text)
        if unit_match:
            unit = re.split(r"\s*[\uff08(]", unit_match.group(1), maxsplit=1)[0].strip()
            if detail:
                title = raw
        elif re.match(r"^(\u30de\u30f3\u30b9\u30ea\u30fcMC|MC[\uff1a:]|\u30b2\u30b9\u30c8[\uff1a:])", detail_text):
            mc_match = re.search(r"\u30de\u30f3\u30b9\u30ea\u30fcMC[\uff1a:]\s*([^\u3001#]+)", detail_text)
            if mc_match:
                monthly_mc.append(normalize_cast_name(mc_match.group(1)))
            guest_match = re.search(r"\u30b2\u30b9\u30c8[\uff1a:]\s*([^#]+)", detail_text)
            if guest_match:
                for guest in re.split(r"[\u30fb\u3001]", guest_match.group(1)):
                    guest = normalize_cast_name(guest)
                    if guest and guest not in guests:
                        guests.append(guest)
        else:
            title = raw

        month_match = re.match(r"(\d{4}/\d{1,2})", broadcast_at)
        if month_match:
            for name in mc_by_month.get(month_match.group(1), []):
                if name not in monthly_mc:
                    monthly_mc.append(name)
        for name in guest_by_episode.get(number, []):
            if name not in guests:
                guests.append(name)

        output_rows.append(
            {
                    "\u56de": number,
                    "\u653e\u9001\u65e5\u6642": broadcast_at,
                    "\u56fa\u6709\u30bf\u30a4\u30c8\u30eb": title,
                    "\u30e6\u30cb\u30c3\u30c8\uff08\u30ea\u30cb\u30e5\u30fc\u30a2\u30eb\u524d\uff09": unit,
                    "\u30de\u30f3\u30b9\u30ea\u30fcMC\uff08\u30ea\u30cb\u30e5\u30fc\u30a2\u30eb\u5f8c\uff09": "\u30fb".join(monthly_mc),
                    "\u30b2\u30b9\u30c8": "\u30fb".join(guests),
                    "\u6b20\u5e2d": "\u30fb".join(absence_by_episode.get(number, [])),
                    "\u65e2\u5b58\u767b\u9332\u5185\u5bb9\uff08\u78ba\u8a8d\u7528\uff09": " / ".join(value for value in [raw, detail] if value),
                    "\u516c\u5f0f\u914d\u4fe1URL": "https://asobichannel.asobistore.jp/watch/qtd5x9i353yk" if number == 394 else "",
            }
        )

    fieldnames = list(output_rows[0])
    with OUTPUT_FILE.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"Created: {OUTPUT_FILE} ({len(output_rows)} episodes)")


if __name__ == "__main__":
    main()
