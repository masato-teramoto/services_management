"""設定管理モジュール

.env から環境変数を読み込み、各モジュールで利用する設定値を提供する。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# プロジェクトルートを基準に .env を読み込む
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _get_bool(key: str, default: bool = False) -> bool:
    return _get(key, str(default)).lower() in ("true", "1", "yes")


# --- Cursor API ---
CURSOR_API_KEY = _get("CURSOR_API_KEY")
CURSOR_API_BASE_URL = _get("CURSOR_API_BASE_URL", "https://www.cursor.com/api")

# --- Codex ---
CODEX_LOGIN_EMAIL = _get("CODEX_LOGIN_EMAIL")
CODEX_LOGIN_PASSWORD = _get("CODEX_LOGIN_PASSWORD")
CODEX_DASHBOARD_URL = _get("CODEX_DASHBOARD_URL", "https://platform.openai.com/usage")

# --- Claude Code ---
CLAUDE_LOGIN_EMAIL = _get("CLAUDE_LOGIN_EMAIL")
CLAUDE_LOGIN_PASSWORD = _get("CLAUDE_LOGIN_PASSWORD")
CLAUDE_DASHBOARD_URL = _get(
    "CLAUDE_DASHBOARD_URL", "https://console.anthropic.com/settings/usage"
)

# --- Google Sheets ---
GOOGLE_SHEETS_SPREADSHEET_ID = _get("GOOGLE_SHEETS_SPREADSHEET_ID")
GOOGLE_SERVICE_ACCOUNT_FILE = _get(
    "GOOGLE_SERVICE_ACCOUNT_FILE", "credentials/service_account.json"
)

# --- Playwright ---
PLAYWRIGHT_HEADLESS = _get_bool("PLAYWRIGHT_HEADLESS", True)
PLAYWRIGHT_SLOW_MO = int(_get("PLAYWRIGHT_SLOW_MO", "0"))
PLAYWRIGHT_STATE_DIR = PROJECT_ROOT / _get("PLAYWRIGHT_STATE_DIR", "playwright_state")

# --- ログ ---
LOG_LEVEL = _get("LOG_LEVEL", "INFO")
LOG_DIR = PROJECT_ROOT / _get("LOG_DIR", "logs")

# --- 出力 ---
SCREENSHOT_DIR = PROJECT_ROOT / _get("SCREENSHOT_DIR", "screenshots")
OUTPUT_DIR = PROJECT_ROOT / "output"
