"""
Configuration for NotebookLM Skill
Centralizes constants, selectors, and paths
"""

import os
from pathlib import Path

# Paths
SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
BROWSER_STATE_DIR = DATA_DIR / "browser_state"
BROWSER_PROFILE_DIR = BROWSER_STATE_DIR / "browser_profile"
STATE_FILE = BROWSER_STATE_DIR / "state.json"
AUTH_INFO_FILE = DATA_DIR / "auth_info.json"
LIBRARY_FILE = DATA_DIR / "library.json"

# NotebookLM Selectors
QUERY_INPUT_SELECTORS = [
    "textarea.query-box-input",  # Primary
    'textarea[aria-label="Feld für Anfragen"]',  # Fallback German
    'textarea[aria-label="Input for queries"]',  # Fallback English
]

RESPONSE_SELECTORS = [
    ".to-user-container .message-text-content",  # Primary
    "[data-message-author='bot']",
    "[data-message-author='assistant']",
]

# Browser Configuration
BROWSER_ARGS = [
    '--disable-blink-features=AutomationControlled',  # Patches navigator.webdriver
    '--disable-dev-shm-usage',
    '--no-sandbox',
    '--no-first-run',
    '--no-default-browser-check'
]

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

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


# Timeouts & retries (overridable via env)
LOGIN_TIMEOUT_MINUTES = _env_float("NOTEBOOKLM_LOGIN_TIMEOUT_MINUTES", 10)
QUERY_TIMEOUT_SECONDS = _env_int("NOTEBOOKLM_QUERY_TIMEOUT_SECONDS", 120)
PAGE_LOAD_TIMEOUT = _env_int("NOTEBOOKLM_PAGE_LOAD_TIMEOUT_MS", 30000)
LAUNCH_RETRIES = _env_int("NOTEBOOKLM_LAUNCH_RETRIES", 2)
LAUNCH_RETRY_DELAY_SECONDS = _env_float("NOTEBOOKLM_LAUNCH_RETRY_DELAY_SECONDS", 1.5)
LOCKFILE_MAX_AGE_SECONDS = _env_int("NOTEBOOKLM_LOCKFILE_MAX_AGE_SECONDS", 90)
ALLOW_CHROMIUM_FALLBACK = _env_bool("NOTEBOOKLM_ALLOW_CHROMIUM_FALLBACK", True)
QUERY_RETRIES = _env_int("NOTEBOOKLM_QUERY_RETRIES", 1)
QUERY_RETRY_DELAY_SECONDS = _env_float("NOTEBOOKLM_QUERY_RETRY_DELAY_SECONDS", 1.5)
