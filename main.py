from pathlib import Path
import os


_APP_DIR = Path(__file__).resolve().parent
_CORE_FILE = _APP_DIR / "main_app_core.py"
# Windows で起動する手元の管理版はローカル、Streamlit Cloud 側は公開版を既定にする。
# public_main.py 経由の場合は SHINY_APP_MODE=public が明示される。
_default_mode = "local" if os.name == "nt" else "public"
APP_MODE = globals().get("APP_MODE", os.environ.get("SHINY_APP_MODE", _default_mode)).casefold()

if APP_MODE != "public":
    from schedule_prediction import render_schedule_prediction

exec(
    compile(_CORE_FILE.read_text(encoding="utf-8-sig"), str(_CORE_FILE), "exec"),
    globals(),
    globals(),
)
