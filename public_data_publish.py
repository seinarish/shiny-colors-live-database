"""ローカルのデータだけを公開用リポジトリへ安全に同期する補助機能。"""

from __future__ import annotations

import base64
import csv
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PUBLIC_REPOSITORY = ROOT / "_public_publish_temp"
PRIVATE_FILES = {"lyrics.csv", "event_images.csv"}
PRIVATE_COLUMN_WORDS = ("歌詞", "画像", "ジャケット", "サムネイル", "ファイル", "パス", "関連画像")


class PublicPublishError(RuntimeError):
    """公開用データの同期を安全に中止するときに使う例外。"""


def _run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
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


def _ensure_publish_repository(allow_prepared_data: bool = False) -> None:
    if not (PUBLIC_REPOSITORY / ".git").exists():
        raise PublicPublishError("公開用フォルダが見つかりません。先に公開版を一度セットアップしてください。")

    status_lines = [
        line for line in _run(["git", "status", "--porcelain"], PUBLIC_REPOSITORY).splitlines()
        if line.strip()
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
    """公開リポジトリへCSV/TSVをコピーし、反映前の差分一覧を返す。"""
    _ensure_publish_repository(allow_prepared_data=True)
    for source in _data_sources():
        _write_sanitized_table(source, PUBLIC_REPOSITORY / source.name)

    changed = _run(
        ["git", "status", "--porcelain", "--", "*.csv", "*.tsv"],
        PUBLIC_REPOSITORY,
    )
    return [line[3:].strip() for line in changed.splitlines() if line.strip()]


def discard_prepared_public_data() -> None:
    """確認用に作った公開データ差分を取り消す。"""
    _ensure_publish_repository(allow_prepared_data=True)
    _run(["git", "restore", "--source=HEAD", "--staged", "--worktree", "--", "*.csv", "*.tsv"], PUBLIC_REPOSITORY)


def publish_prepared_public_data() -> tuple[str, list[str]]:
    """確認済みのCSV/TSV差分だけをコミットして公開版へ送る。"""
    _ensure_publish_repository(allow_prepared_data=True)
    _run(["git", "add", "--", "*.csv", "*.tsv"], PUBLIC_REPOSITORY)
    changed = _run(["git", "diff", "--cached", "--name-only"], PUBLIC_REPOSITORY)
    changed_files = [line for line in changed.splitlines() if line.strip()]
    if not changed_files:
        return "公開用データに差分はありません。", []

    _run(["git", "commit", "-m", "Sync local data to public site"], PUBLIC_REPOSITORY)
    gh_path = _github_cli_path()
    token = _run([gh_path, "auth", "token"], ROOT)
    if not token:
        raise PublicPublishError("GitHubへのログイン情報を取得できませんでした。")
    basic = base64.b64encode(f"x-access-token:{token}".encode("ascii")).decode("ascii")
    _run(
        [
            "git", "-c", "credential.helper=",
            "-c", f"http.extraHeader=AUTHORIZATION: basic {basic}",
            "push", "origin", "HEAD:main",
        ],
        PUBLIC_REPOSITORY,
    )
    return "公開版へ反映しました。Streamlit側の更新には数分かかることがあります。", changed_files
