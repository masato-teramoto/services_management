"""Codex (OpenAI) 利用状況取得モジュール

Enterprise API が利用できないため、Playwright によるブラウザ自動操作で
OpenAI プラットフォームの Usage ページからデータを取得する。
"""

import asyncio
import json
import sys

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from src.common.config import CODEX_DASHBOARD_URL, CODEX_LOGIN_EMAIL, CODEX_LOGIN_PASSWORD
from src.common.logger import get_logger
from src.common.playwright_helper import browser_context, save_screenshot
from src.common.utils import UsageRecord, generate_batch_id, now_iso, save_records_to_json

logger = get_logger(__name__)

SERVICE_NAME = "codex"


async def _login(page: Page) -> None:
    """OpenAI プラットフォームへログインする。

    NOTE: OpenAI のログインフローは変更される可能性があるため、
    DOM 変更時にはセレクタの修正が必要。
    """
    logger.info("Codex: ログイン開始")
    await page.goto("https://platform.openai.com/login", wait_until="networkidle")

    # ログイン済みかチェック (ダッシュボードにリダイレクトされていれば済)
    if "login" not in page.url.lower():
        logger.info("Codex: ログイン済みのセッションを検出")
        return

    # メールアドレス入力
    email_input = page.locator('input[name="email"], input[type="email"]').first
    await email_input.fill(CODEX_LOGIN_EMAIL)

    # Continue ボタン押下
    continue_btn = page.locator('button:has-text("Continue"), button:has-text("続行")').first
    await continue_btn.click()
    await page.wait_for_timeout(2000)

    # パスワード入力
    password_input = page.locator('input[name="password"], input[type="password"]').first
    await password_input.fill(CODEX_LOGIN_PASSWORD)

    # ログインボタン押下
    login_btn = page.locator('button:has-text("Log in"), button:has-text("ログイン")').first
    await login_btn.click()
    await page.wait_for_load_state("networkidle")

    logger.info("Codex: ログイン完了 (URL: %s)", page.url)


async def _navigate_to_usage(page: Page) -> None:
    """Usage ページへ遷移する。"""
    logger.info("Codex: Usage ページへ遷移")
    await page.goto(CODEX_DASHBOARD_URL, wait_until="networkidle")
    await page.wait_for_timeout(3000)


async def _extract_usage_data(page: Page) -> list[dict]:
    """Usage ページからデータを抽出する。

    NOTE: OpenAI の Usage ページの DOM 構造に依存するため、
    レイアウト変更時にはセレクタの修正が必要。
    抽出が困難な場合はスクリーンショットを保存して手動確認に備える。
    """
    logger.info("Codex: データ抽出開始")
    results: list[dict] = []

    try:
        # Usage ページのテーブルやカード要素からデータを抽出
        # NOTE: 実際の DOM 構造に合わせてセレクタを調整してください
        #
        # 方法1: テーブル行からの抽出を試行
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

        # 方法2: テーブルが見つからない場合はページ全体のテキストを取得
        if not results:
            logger.warning("Codex: テーブルが見つかりません。ページテキストを取得します")
            content_area = page.locator("main, [role='main'], .content")
            if await content_area.count() > 0:
                text = await content_area.first.inner_text()
                results.append({
                    "row_index": 0,
                    "cells": [text[:2000]],
                    "raw_text": text[:2000],
                })

        # スクリーンショットを記録として保存
        await save_screenshot(page, "codex_usage")

    except PlaywrightTimeout:
        logger.error("Codex: データ抽出でタイムアウトが発生しました")
        await save_screenshot(page, "codex_error")
        raise

    logger.info("Codex: %d 件のデータ行を抽出", len(results))
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
    logger.info("=== Codex 取得開始 (batch_id: %s) ===", batch_id)

    async with browser_context(SERVICE_NAME) as (browser, ctx, page):
        try:
            await _login(page)
            await _navigate_to_usage(page)
            raw_data = await _extract_usage_data(page)
            records = _build_records(raw_data, batch_id)

            if records:
                filepath = save_records_to_json(records, f"codex_{batch_id}.json")
                logger.info("Codex: 中間ファイル保存 -> %s", filepath)

            logger.info("=== Codex 取得完了: %d 件 ===", len(records))
            return records

        except Exception:
            logger.exception("Codex 取得でエラーが発生しました")
            try:
                await save_screenshot(page, "codex_fatal_error")
            except Exception:
                pass
            raise


def run() -> list[UsageRecord]:
    """Codex 利用状況取得のメインエントリポイント。"""
    return asyncio.run(_run_async())


if __name__ == "__main__":
    try:
        run()
    except Exception:
        sys.exit(1)
