"""ローカルのデータだけを公開用リポジトリへ安全に同期する補助機能。"""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
# 公開用リポジトリは、現在このアプリを置いているGitHub連携済みのフォルダそのもの。
# 旧来の一時コピー先フォルダは使わない。
PUBLIC_REPOSITORY = ROOT
PRIVATE_FILES = {"lyrics.csv", "event_images.csv"}
PRIVATE_COLUMN_WORDS = ("歌詞", "画像", "ジャケット", "サムネイル", "ファイル", "パス", "関連画像")
GENERATED_PATH_PREFIXES = (
    "__pycache__/",
    "_public_publish_temp/",
    "public_release/",
    "public_site/",
)


class PublicPublishError(RuntimeError):
    """公開用データの同期を安全に中止するときに使う例外。"""


def _git_executable_path() -> str:
    """Streamlitから起動してPATHが短い場合でもGitを見つける。"""
    candidates = [
        shutil.which("git"),
        str(Path(r"C:\Program Files\Git\cmd\git.exe")),
        str(Path(r"C:\Program Files\Git\bin\git.exe")),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise PublicPublishError("Gitが見つかりません。Git for Windows をインストールしてから再試行してください。")


def _run(command: list[str], cwd: Path) -> str:
    resolved_command = [_git_executable_path(), *command[1:]] if command and command[0] == "git" else command
    try:
        result = subprocess.run(
            resolved_command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        raise PublicPublishError("公開処理に必要なプログラムが見つかりません。Gitの設定を確認してください。") from exc
    if result.returncode:
        message = (result.stderr or result.stdout or "処理に失敗しました。").strip()
        raise PublicPublishError(message)
    return result.stdout.strip()


def _github_cli_path() -> str:
    candidates = [
        shutil.which("gh"),
        str(Path(r"C:\Program Files\GitHub CLI\gh.exe")),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise PublicPublishError("GitHubへの接続が見つかりません。GitHub CLIでログインしてください。")


def _data_sources() -> list[Path]:
    return sorted(
        [
            path for path in ROOT.iterdir()
            if path.is_file()
            and path.suffix.lower() in {".csv", ".tsv"}
            and path.name not in PRIVATE_FILES
            and ".backup_" not in path.name
        ],
        key=lambda path: path.name.casefold(),
    )


def _read_rows(path: Path) -> tuple[list[dict[str, str]], list[str], str]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    for encoding in ("utf-8-sig", "cp932"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle, delimiter=delimiter)
                return list(reader), list(reader.fieldnames or []), delimiter
        except UnicodeDecodeError:
            continue
    raise PublicPublishError(f"{path.name} を読み取れませんでした。")


def _write_sanitized_table(source: Path, destination: Path) -> None:
    rows, fieldnames, delimiter = _read_rows(source)
    public_fields = [
        field for field in fieldnames
        if not any(word in field for word in PRIVATE_COLUMN_WORDS)
    ]
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=public_fields, delimiter=delimiter)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in public_fields} for row in rows)


def _is_generated_status_line(line: str) -> bool:
    path = line[3:].strip().replace("\\", "/")
    return path.startswith(GENERATED_PATH_PREFIXES) or ".backup_" in path


def _ensure_publish_repository(allow_prepared_data: bool = False) -> None:
    if not (PUBLIC_REPOSITORY / ".git").exists():
        raise PublicPublishError("公開用フォルダが見つかりません。先に公開版を一度セットアップしてください。")

    status_lines = [
        line for line in _run(["git", "status", "--porcelain"], PUBLIC_REPOSITORY).splitlines()
        if line.strip() and not _is_generated_status_line(line)
    ]
    non_data_changes = [
        line for line in status_lines
        if not line.rstrip().lower().endswith((".csv", ".tsv"))
    ]
    if non_data_changes or (status_lines and not allow_prepared_data):
        raise PublicPublishError(
            "公開用フォルダに未反映の変更があります。公開処理を止めました。Codexで確認してから再試行してください。"
        )

    _run(["git", "fetch", "origin", "main"], PUBLIC_REPOSITORY)
    head = _run(["git", "rev-parse", "HEAD"], PUBLIC_REPOSITORY)
    remote_head = _run(["git", "rev-parse", "origin/main"], PUBLIC_REPOSITORY)
    if head != remote_head and status_lines:
        raise PublicPublishError(
            "公開版に新しい変更があるため、確認中のデータ差分は反映しませんでした。一度『確認用ファイルを作る』をやり直してください。"
        )
    if head != remote_head:
        _run(["git", "merge", "--ff-only", "origin/main"], PUBLIC_REPOSITORY)


def prepare_public_data_sync() -> list[str]:
    """現在のCSV/TSVの差分を、公開前に確認できる形で返す。"""
    _ensure_publish_repository(allow_prepared_data=True)
    changed = _run(
        ["git", "status", "--porcelain", "--", "*.csv", "*.tsv"],
        PUBLIC_REPOSITORY,
    )
    return [
        line[3:].strip()
        for line in changed.splitlines()
        if line.strip() and Path(line[3:].strip()).name not in PRIVATE_FILES
    ]


def discard_prepared_public_data() -> None:
    """旧コピー方式との互換用。現在はローカルの編集内容を消さない。"""
    # 現在は同じフォルダの内容をそのまま確認してから公開する方式なので、
    # 「取り消す」で未保存のローカル編集を消してしまわないよう何もしない。
    return None


def publish_prepared_public_data() -> tuple[str, list[str]]:
    """確認済みのCSV/TSV差分だけをコミットして公開版へ送る。"""
    _ensure_publish_repository(allow_prepared_data=True)
    changed_before_stage = prepare_public_data_sync()
    if not changed_before_stage:
        return "公開用データに差分はありません。", []

    _run(["git", "add", "--", *changed_before_stage], PUBLIC_REPOSITORY)
    changed = _run(["git", "diff", "--cached", "--name-only"], PUBLIC_REPOSITORY)
    changed_files = [line for line in changed.splitlines() if line.strip()]
    if not changed_files:
        return "公開用データに差分はありません。", []

    _run(["git", "commit", "-m", "Sync local data to public site"], PUBLIC_REPOSITORY)
    _run(["git", "push", "origin", "HEAD:main"], PUBLIC_REPOSITORY)
    return "公開版へ反映しました。Streamlit側の更新には数分かかることがあります。", changed_files
