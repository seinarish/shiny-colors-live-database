"""公開版の起動入口。Streamlit はこのファイルを指定して起動する。"""

import os
from pathlib import Path


os.environ["SHINY_APP_MODE"] = "public"
_APP_DIR = Path(__file__).resolve().parent
_MAIN_FILE = _APP_DIR / "main.py"

exec(
    compile(_MAIN_FILE.read_text(encoding="utf-8-sig"), str(_MAIN_FILE), "exec"),
    globals(),
    globals(),
)
