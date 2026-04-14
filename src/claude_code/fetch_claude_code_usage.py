"""Claude Code 利用状況取得モジュール

Enterprise API が利用できないため、Playwright によるブラウザ自動操作で
Anthropic コンソールの Usage ページからデータを取得する。
"""

import asyncio
import json
import sys

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from src.common.config import CLAUDE_DASHBOARD_URL, CLAUDE_LOGIN_EMAIL, CLAUDE_LOGIN_PASSWORD
from src.common.logger import get_logger
from src.common.playwright_helper import browser_context, save_screenshot
from src.common.utils import UsageRecord, generate_batch_id, now_iso, save_records_to_json

logger = get_logger(__name__)

SERVICE_NAME = "claude_code"


async def _login(page: Page) -> None:
    """Anthropic コンソールへログインする。

    NOTE: Anthropic のログインフローは変更される可能性があるため、
    DOM 変更時にはセレクタの修正が必要。
    """
    logger.info("Claude Code: ログイン開始")
    await page.goto("https://console.anthropic.com/login", wait_until="networkidle")

    # ログイン済みかチェック
    if "login" not in page.url.lower():
        logger.info("Claude Code: ログイン済みのセッションを検出")
        return

    # メールアドレス入力
    email_input = page.locator('input[name="email"], input[type="email"]').first
    await email_input.fill(CLAUDE_LOGIN_EMAIL)

    # Continue / Sign in ボタン押下
    continue_btn = page.locator(
        'button:has-text("Continue"), button:has-text("Sign in"), button:has-text("ログイン")'
    ).first
    await continue_btn.click()
    await page.wait_for_timeout(2000)

    # パスワード入力 (フローにパスワードステップがある場合)
    password_input = page.locator('input[name="password"], input[type="password"]')
    if await password_input.count() > 0:
        await password_input.first.fill(CLAUDE_LOGIN_PASSWORD)
        login_btn = page.locator(
            'button:has-text("Sign in"), button:has-text("Log in"), button:has-text("ログイン")'
        ).first
        await login_btn.click()
        await page.wait_for_load_state("networkidle")

    logger.info("Claude Code: ログイン完了 (URL: %s)", page.url)


async def _navigate_to_usage(page: Page) -> None:
    """Usage ページへ遷移する。"""
    logger.info("Claude Code: Usage ページへ遷移")
    await page.goto(CLAUDE_DASHBOARD_URL, wait_until="networkidle")
    await page.wait_for_timeout(3000)


async def _extract_usage_data(page: Page) -> list[dict]:
    """Usage ページからデータを抽出する。

    NOTE: Anthropic コンソールの DOM 構造に依存するため、
    レイアウト変更時にはセレクタの修正が必要。
    """
    logger.info("Claude Code: データ抽出開始")
    results: list[dict] = []

    try:
        # テーブル形式でのデータ抽出を試行
        rows = page.locator("table tbody tr, [role='row']")
        row_count = await rows.count()

        if row_count > 0:
            for i in range(row_count):
                row = rows.nth(i)
                cells = row.locator("td, [role='cell']")
                cell_count = await cells.count()
                cell_texts = []
                for j in range(cell_count):
                    text = await cells.nth(j).inner_text()
                    cell_texts.append(text.strip())

                if cell_texts:
                    results.append({
                        "row_index": i,
                        "cells": cell_texts,
                        "raw_text": " | ".join(cell_texts),
                    })

        # テーブルが見つからない場合はカード / サマリ要素を取得
        if not results:
            logger.info("Claude Code: テーブルが見つかりません。カード要素を検索します")
            cards = page.locator("[class*='usage'], [class*='metric'], [class*='stat']")
            card_count = await cards.count()

            for i in range(card_count):
                text = await cards.nth(i).inner_text()
                results.append({
                    "row_index": i,
                    "cells": [text.strip()],
                    "raw_text": text.strip(),
                })

        # それでもデータがない場合はメインコンテンツ領域全体を取得
        if not results:
            logger.warning("Claude Code: 個別要素が見つかりません。ページテキストを取得します")
            content_area = page.locator("main, [role='main'], .content")
            if await content_area.count() > 0:
                text = await content_area.first.inner_text()
                results.append({
                    "row_index": 0,
                    "cells": [text[:2000]],
                    "raw_text": text[:2000],
                })

        # スクリーンショットを記録として保存
        await save_screenshot(page, "claude_code_usage")

    except PlaywrightTimeout:
        logger.error("Claude Code: データ抽出でタイムアウトが発生しました")
        await save_screenshot(page, "claude_code_error")
        raise

    logger.info("Claude Code: %d 件のデータ行を抽出", len(results))
    return results


def _build_records(
    raw_data: list[dict], batch_id: str
) -> list[UsageRecord]:
    """抽出データを UsageRecord に変換する。"""
    fetched_at = now_iso()
    records: list[UsageRecord] = []

    for item in raw_data:
        records.append(
            UsageRecord(
                fetched_at=fetched_at,
                service_name=SERVICE_NAME,
                user_name="",
                user_email="",
                plan_name="",
                usage_date="",
                metric_name="raw_usage",
                metric_value=item.get("raw_text", ""),
                source_type="playwright",
                raw_payload=json.dumps(item, ensure_ascii=False),
                batch_id=batch_id,
            )
        )

    return records


async def _run_async() -> list[UsageRecord]:
    """非同期メインロジック。"""
    batch_id = generate_batch_id()
    logger.info("=== Claude Code 取得開始 (batch_id: %s) ===", batch_id)

    async with browser_context(SERVICE_NAME) as (browser, ctx, page):
        try:
            await _login(page)
            await _navigate_to_usage(page)
            raw_data = await _extract_usage_data(page)
            records = _build_records(raw_data, batch_id)

            if records:
                filepath = save_records_to_json(records, f"claude_code_{batch_id}.json")
                logger.info("Claude Code: 中間ファイル保存 -> %s", filepath)

            logger.info("=== Claude Code 取得完了: %d 件 ===", len(records))
            return records

        except Exception:
            logger.exception("Claude Code 取得でエラーが発生しました")
            try:
                await save_screenshot(page, "claude_code_fatal_error")
            except Exception:
                pass
            raise


def run() -> list[UsageRecord]:
    """Claude Code 利用状況取得のメインエントリポイント。"""
    return asyncio.run(_run_async())


if __name__ == "__main__":
    try:
        run()
    except Exception:
        sys.exit(1)
