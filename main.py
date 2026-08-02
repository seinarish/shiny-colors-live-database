from pathlib import Path


_APP_DIR = Path(__file__).resolve().parent
_CORE_FILE = _APP_DIR / "main_app_core.py"

exec(
    compile(_CORE_FILE.read_text(encoding="utf-8-sig"), str(_CORE_FILE), "exec"),
    globals(),
    globals(),
)

from event_image_gallery import render_event_image_gallery


render_event_image_gallery()
