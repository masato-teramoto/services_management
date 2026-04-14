"""Claude Code 利用状況取得モジュール

Enterprise API が利用できないため、Playwright によるブラウザ自動操作で
Anthropic コンソールの Usage ページからデータを取得する。

料金の取得方針:
- 基本料金 (base): CLAUDE_MONTHLY_RATE × ユーザー数 で内部計算
- オンデマンド料金 (ondemand): Usage ページから利用額を抽出
"""

import asyncio
import json
import re
import sys
from datetime import date

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from src.common.config import (
    CLAUDE_DASHBOARD_URL,
    CLAUDE_LOGIN_EMAIL,
    CLAUDE_LOGIN_PASSWORD,
    CLAUDE_MONTHLY_RATE,
)
from src.common.logger import get_logger
from src.common.playwright_helper import browser_context, save_screenshot
from src.common.utils import (
    PricingRecord,
    UsageRecord,
    generate_batch_id,
    now_iso,
    save_records_to_json,
)

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


async def _extract_spend_amount(page: Page) -> float:
    """Usage ページからオンデマンド利用額 (USD) を抽出する。

    NOTE: Anthropic コンソールに表示される利用額を取得する。
    DOM 構造変更時にはセレクタの修正が必要。
    """
    logger.info("Claude Code: オンデマンド利用額の抽出開始")

    try:
        # 利用額が表示される要素を取得 ($XX.XX 形式の金額を探す)
        # NOTE: 実際の DOM 構造に合わせてセレクタを調整してください
        amount_elements = page.locator(
            "[class*='cost'], [class*='amount'], [class*='spend'], "
            "[class*='total'], [class*='price'], [class*='usage']"
        )
        count = await amount_elements.count()

        for i in range(count):
            text = await amount_elements.nth(i).inner_text()
            match = re.search(r"\$\s*([\d,]+\.?\d*)", text)
            if match:
                amount = float(match.group(1).replace(",", ""))
                logger.info("Claude Code: オンデマンド利用額 = $%.2f", amount)
                return amount

        # フォールバック: ページ全体のテキストから金額を探す
        content = page.locator("main, [role='main']")
        if await content.count() > 0:
            page_text = await content.first.inner_text()
            matches = re.findall(r"\$\s*([\d,]+\.?\d*)", page_text)
            if matches:
                amount = float(matches[0].replace(",", ""))
                logger.info("Claude Code: オンデマンド利用額 (フォールバック) = $%.2f", amount)
                return amount

    except Exception:
        logger.warning("Claude Code: オンデマンド利用額の抽出に失敗しました")

    return 0.0


async def _extract_member_count(page: Page) -> int:
    """管理画面からメンバー数を取得する。

    NOTE: 取得できない場合は 0 を返す。
    """
    try:
        # メンバー管理ページへ遷移して人数を取得
        # NOTE: 実際の URL / セレクタに合わせて調整してください
        await page.goto(
            "https://console.anthropic.com/settings/members",
            wait_until="networkidle",
        )
        await page.wait_for_timeout(2000)

        # メンバー一覧のテーブル行数を取得
        rows = page.locator("table tbody tr, [role='row']")
        count = await rows.count()
        if count > 0:
            logger.info("Claude Code: メンバー数 = %d", count)
            return count

        # フォールバック: テキストからメンバー数を探す
        content = page.locator("main, [role='main']")
        if await content.count() > 0:
            page_text = await content.first.inner_text()
            match = re.search(r"(\d+)\s*(?:members?|メンバー|ユーザー|seats?)", page_text, re.IGNORECASE)
            if match:
                member_count = int(match.group(1))
                logger.info("Claude Code: メンバー数 (テキスト抽出) = %d", member_count)
                return member_count

    except Exception:
        logger.warning("Claude Code: メンバー数の取得に失敗しました")

    return 0


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


def _build_pricing_records(
    member_count: int, ondemand_usd: float, batch_id: str
) -> list[PricingRecord]:
    """料金レコードを生成する。

    基本料金: 月額単価 × メンバー数
    オンデマンド料金: Usage ページから抽出した利用額
    """
    fetched_at = now_iso()
    accounting_month = date.today().strftime("%Y-%m")
    records: list[PricingRecord] = []

    # 基本料金 (チーム全体で 1 行)
    base_usd = round(CLAUDE_MONTHLY_RATE * member_count, 2) if member_count > 0 else 0.0
    records.append(
        PricingRecord(
            fetched_at=fetched_at,
            service_name=SERVICE_NAME,
            accounting_month=accounting_month,
            user_email="",
            user_name="",
            charge_type="base",
            amount_usd=base_usd,
            description=f"月額単価={CLAUDE_MONTHLY_RATE} USD × {member_count} 名",
            batch_id=batch_id,
        )
    )

    # オンデマンド料金 (チーム全体で 1 行)
    records.append(
        PricingRecord(
            fetched_at=fetched_at,
            service_name=SERVICE_NAME,
            accounting_month=accounting_month,
            user_email="",
            user_name="",
            charge_type="ondemand",
            amount_usd=ondemand_usd,
            description="Usage ページから取得",
            batch_id=batch_id,
        )
    )

    logger.info("Claude Code: %d 件の料金レコードを生成", len(records))
    return records


async def _run_async() -> tuple[list[UsageRecord], list[PricingRecord]]:
    """非同期メインロジック。"""
    batch_id = generate_batch_id()
    logger.info("=== Claude Code 取得開始 (batch_id: %s) ===", batch_id)

    async with browser_context(SERVICE_NAME) as (browser, ctx, page):
        try:
            await _login(page)
            await _navigate_to_usage(page)

            # 利用データ抽出
            raw_data = await _extract_usage_data(page)
            usage_records = _build_records(raw_data, batch_id)

            # オンデマンド利用額抽出
            ondemand_usd = await _extract_spend_amount(page)

            # メンバー数取得
            member_count = await _extract_member_count(page)

            # 料金レコード生成
            pricing_records = _build_pricing_records(member_count, ondemand_usd, batch_id)

            if usage_records:
                filepath = save_records_to_json(usage_records, f"claude_code_{batch_id}.json")
                logger.info("Claude Code: 利用データ中間ファイル保存 -> %s", filepath)

            if pricing_records:
                filepath = save_records_to_json(
                    pricing_records, f"claude_code_pricing_{batch_id}.json"
                )
                logger.info("Claude Code: 料金データ中間ファイル保存 -> %s", filepath)

            logger.info(
                "=== Claude Code 取得完了: 利用=%d 件, 料金=%d 件 ===",
                len(usage_records),
                len(pricing_records),
            )
            return usage_records, pricing_records

        except Exception:
            logger.exception("Claude Code 取得でエラーが発生しました")
            try:
                await save_screenshot(page, "claude_code_fatal_error")
            except Exception:
                pass
            raise


def run() -> tuple[list[UsageRecord], list[PricingRecord]]:
    """Claude Code 利用状況取得のメインエントリポイント。"""
    return asyncio.run(_run_async())


if __name__ == "__main__":
    try:
        run()
    except Exception:
        sys.exit(1)
