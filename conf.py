import os
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


BASE_DIR = Path(__file__).parent.resolve()
XHS_SERVER = os.getenv("XHS_SERVER", "http://127.0.0.1:11901")
LOCAL_CHROME_PATH = os.getenv("LOCAL_CHROME_PATH", "")
LOCAL_CHROME_HEADLESS = _env_bool("LOCAL_CHROME_HEADLESS", False)
DEBUG_MODE = _env_bool("DEBUG_MODE", False)
YT_PROXY = os.getenv("YT_PROXY") or None

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5409"))
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "db" / "database.db")))
VIDEO_FOLDER = Path(os.getenv("VIDEO_FOLDER", str(BASE_DIR / "videoFile")))
COOKIES_FOLDER = Path(os.getenv("COOKIES_FOLDER", str(BASE_DIR / "cookiesFile")))
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(10 * 1024 * 1024 * 1024)))
