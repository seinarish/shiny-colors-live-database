"""画像・歌詞を含めない公開用フォルダを作る。"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "public_release"
PRIVATE_FILES = {"lyrics.csv", "event_images.csv"}
PRIVATE_DIRS = {".git", "__pycache__", "event_images", "album_jackets", "song_jackets", "public_site", "public_release"}
TEXT_COLUMNS = ("歌詞", "画像", "ジャケット", "サムネイル", "ファイル", "パス", "素材")


def _read_table(path: Path) -> tuple[list[dict[str, str]], list[str], str, str]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    for encoding in ("utf-8-sig", "cp932"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle, delimiter=delimiter)
                return list(reader), list(reader.fieldnames or []), encoding, delimiter
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"{path.name} を読み込めません")


def _copy_sanitized_table(source: Path, destination: Path) -> None:
    rows, fieldnames, _, delimiter = _read_table(source)
    public_fields = [
        field for field in fieldnames
        if not any(term in field for term in TEXT_COLUMNS)
    ]
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=public_fields, delimiter=delimiter)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in public_fields} for row in rows)


def main() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir()

    for source in ROOT.iterdir():
        if source.name in PRIVATE_FILES or source.name in PRIVATE_DIRS or source.name.endswith(".backup_20260801_002849"):
            continue
        destination = OUTPUT / source.name
        if source.suffix.lower() in {".csv", ".tsv"}:
            _copy_sanitized_table(source, destination)
        elif source.suffix.lower() == ".py":
            shutil.copy2(source, destination)
        elif source.is_dir() and source.name == ".streamlit":
            shutil.copytree(source, destination)

    (OUTPUT / "requirements.txt").write_text("streamlit\npandas\nplotly\n", encoding="utf-8")
    (OUTPUT / "README.md").write_text(
        "# 公開版\n\n"
        "画像・歌詞・ローカル素材を含めない公開用の出力です。"
        "Streamlitでは `public_main.py` を起動ファイルに指定してください。\n",
        encoding="utf-8",
    )
    print(f"公開用フォルダを作成しました: {OUTPUT}")


if __name__ == "__main__":
    main()
