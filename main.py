from pathlib import Path
import os


_APP_DIR = Path(__file__).resolve().parent
_CORE_FILE = _APP_DIR / "main_app_core.py"
APP_MODE = globals().get("APP_MODE", os.environ.get("SHINY_APP_MODE", "local")).casefold()

from schedule_prediction import render_schedule_prediction

exec(
    compile(_CORE_FILE.read_text(encoding="utf-8-sig"), str(_CORE_FILE), "exec"),
    globals(),
    globals(),
)
