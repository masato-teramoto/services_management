"""Playwright 共通ヘルパー

ブラウザ起動、スクリーンショット保存、セッション管理など
Codex / Claude Code の Playwright 取得処理で共通利用する機能を提供する。
"""

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from src.common.config import (
    PLAYWRIGHT_HEADLESS,
    PLAYWRIGHT_SLOW_MO,
    PLAYWRIGHT_STATE_DIR,
    SCREENSHOT_DIR,
)
from src.common.logger import get_logger

logger = get_logger(__name__)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_screenshot(page: Page, name: str) -> Path:
    """スクリーンショットを保存し、ファイルパスを返す。"""
    _ensure_dir(SCREENSHOT_DIR)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = SCREENSHOT_DIR / f"{name}_{ts}.png"
    await page.screenshot(path=str(filepath), full_page=True)
    logger.info("スクリーンショット保存: %s", filepath)
    return filepath


def _state_file(service_name: str) -> Path:
    """セッション保存先のパスを返す。"""
    _ensure_dir(PLAYWRIGHT_STATE_DIR)
    return PLAYWRIGHT_STATE_DIR / f"{service_name}_state.json"


@asynccontextmanager
async def browser_context(
    service_name: str,
) -> AsyncGenerator[tuple[Browser, BrowserContext, Page], None]:
    """Playwright のブラウザコンテキストを提供するコンテキストマネージャ。

    保存済みセッションがあれば復元し、終了時にセッションを保存する。
    """
    state_path = _state_file(service_name)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=PLAYWRIGHT_HEADLESS,
            slow_mo=PLAYWRIGHT_SLOW_MO,
        )

        # セッション復元
        storage_state = str(state_path) if state_path.exists() else None
        context = await browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
        )
        page = await context.new_page()

        try:
            yield browser, context, page
        finally:
            # セッション保存
            try:
                await context.storage_state(path=str(state_path))
                logger.info("セッション保存: %s", state_path)
            except Exception:
                logger.warning("セッション保存に失敗しました", exc_info=True)
            await context.close()
            await browser.close()
