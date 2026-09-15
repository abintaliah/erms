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
