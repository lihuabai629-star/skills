"""
Configuration for the IMA web automation skill.
"""

import os
from pathlib import Path


SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
BROWSER_STATE_DIR = DATA_DIR / "browser_state"
BROWSER_PROFILE_DIR = BROWSER_STATE_DIR / "browser_profile"
STATE_FILE = BROWSER_STATE_DIR / "state.json"
AUTH_INFO_FILE = DATA_DIR / "auth_info.json"
LIBRARY_FILE = DATA_DIR / "knowledge_library.json"

HOME_URL = "https://ima.qq.com/"
WIKIS_URL = "https://ima.qq.com/wikis"

LOGIN_REQUIRED_MARKERS = (
    "微信扫码登录",
    "登录以同步历史会话",
)

SIDEBAR_ITEMS = (
    "我的知识库",
    "知识库广场",
    "问答历史",
)

QUERY_EDITOR_SELECTOR = ".tiptap.ProseMirror"

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--no-first-run",
    "--no-default-browser-check",
]

BROWSER_UPGRADE_PATH = "/browser-upgrade"


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


PAGE_LOAD_TIMEOUT_MS = _env_int("IMA_PAGE_LOAD_TIMEOUT_MS", 30000)
LOGIN_TIMEOUT_MINUTES = _env_float("IMA_LOGIN_TIMEOUT_MINUTES", 10)
QUERY_TIMEOUT_SECONDS = _env_int("IMA_QUERY_TIMEOUT_SECONDS", 120)
QUERY_RETRIES = _env_int("IMA_QUERY_RETRIES", 1)
QUERY_RETRY_DELAY_SECONDS = _env_float("IMA_QUERY_RETRY_DELAY_SECONDS", 1.5)
LAUNCH_RETRIES = _env_int("IMA_LAUNCH_RETRIES", 2)
LAUNCH_RETRY_DELAY_SECONDS = _env_float("IMA_LAUNCH_RETRY_DELAY_SECONDS", 1.5)
LOCKFILE_MAX_AGE_SECONDS = _env_int("IMA_LOCKFILE_MAX_AGE_SECONDS", 90)
ALLOW_CHROMIUM_FALLBACK = _env_bool("IMA_ALLOW_CHROMIUM_FALLBACK", True)
