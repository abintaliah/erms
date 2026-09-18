import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_DIR / ".env", override=False)


def api_url() -> str:
    return os.getenv("WEBUI_API_URL", "http://127.0.0.1:8000").rstrip("/")


def host() -> str:
    return os.getenv("WEBUI_HOST", "0.0.0.0")


def port() -> int:
    return int(os.getenv("WEBUI_PORT", "8080"))


def reload_enabled() -> bool:
    return os.getenv("WEBUI_RELOAD", "false").strip().lower() in {"1", "true", "yes", "on"}


def storage_secret() -> str:
    return os.getenv("WEBUI_STORAGE_SECRET", "local-development-change-me")


def _positive_integer(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error
    if value < 1:
        raise RuntimeError(f"{name} must be at least 1")
    return value


def dashboard_recent_item_limit() -> int:
    return _positive_integer("DASHBOARD_RECENT_ITEM_LIMIT", 4)


def dashboard_recent_days() -> int:
    return _positive_integer("DASHBOARD_RECENT_DAYS", 30)


def dashboard_favourite_item_limit() -> int:
    return _positive_integer("DASHBOARD_FAVOURITE_ITEM_LIMIT", 5)


def classification_recent_selection_limit() -> int:
    return _positive_integer("CLASSIFICATION_RECENT_SELECTION_LIMIT", 4)


def user_details_session_limit() -> int:
    return _positive_integer("USER_DETAILS_SESSION_LIMIT", 5)
