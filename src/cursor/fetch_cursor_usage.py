"""Cursor 利用状況取得モジュール

Cursor API を利用して、チームメンバーの利用状況データおよび料金データを取得する。

料金の取得方針:
- 基本料金 (base): CURSOR_MONTHLY_RATE × 稼働日数 ÷ 請求サイクル日数 で内部計算
- オンデマンド料金 (ondemand): Cursor API /teams/spend から取得 (spendCents → USD)
"""

import calendar
import json
import sys
from datetime import datetime, date
from typing import Any

import requests

from src.common.config import (
    CURSOR_API_BASE_URL,
    CURSOR_API_KEY,
    CURSOR_MONTHLY_RATE,
    CURSOR_BILLING_CYCLE_START_DAY,
)
from src.common.logger import get_logger
from src.common.utils import (
    PricingRecord,
    UsageRecord,
    generate_batch_id,
    now_iso,
    save_records_to_json,
)

logger = get_logger(__name__)


class CursorAPIError(Exception):
    """Cursor API 呼び出し時のエラー。"""


def _build_headers() -> dict[str, str]:
    """API リクエスト用ヘッダーを構築する (Basic 認証)。"""
    if not CURSOR_API_KEY:
        raise CursorAPIError("CURSOR_API_KEY が設定されていません")
    import base64
    encoded = base64.b64encode(f"{CURSOR_API_KEY}:".encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
    }


def _request_get(endpoint: str, params: dict | None = None) -> Any:
    """Cursor API へ GET リクエストを送信する。"""
    url = f"{CURSOR_API_BASE_URL}/{endpoint.lstrip('/')}"
    headers = _build_headers()

    logger.info("Cursor API GET: %s", url)
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        raise CursorAPIError(f"API GET リクエスト失敗: {e}") from e


def _request_post(endpoint: str, payload: dict | None = None) -> Any:
    """Cursor API へ POST リクエストを送信する。"""
    url = f"{CURSOR_API_BASE_URL}/{endpoint.lstrip('/')}"
    headers = _build_headers()

    logger.info("Cursor API POST: %s", url)
    try:
        resp = requests.post(url, headers=headers, json=payload or {}, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        raise CursorAPIError(f"API POST リクエスト失敗: {e}") from e


# ============================================
# メンバー取得
# ============================================

def fetch_team_members() -> list[dict[str, Any]]:
    """チームメンバー一覧を /teams/members から取得する。"""
    data = _request_get("teams/members")
    members = data.get("members", data.get("users", []))
    logger.info("Cursor: %d 件のメンバーを取得", len(members))
    return members


# ============================================
# オンデマンド利用額取得
# ============================================

def fetch_team_spend() -> list[dict[str, Any]]:
    """チームのオンデマンド利用額を /teams/spend からページングで全件取得する。"""
    all_spend: list[dict[str, Any]] = []
    page = 1
    page_size = 100

    while True:
        payload = {
            "sortBy": "amount",
            "sortDirection": "desc",
            "page": page,
            "pageSize": page_size,
        }
        data = _request_post("teams/spend", payload)
        items = data.get("teamMemberSpend", [])
        all_spend.extend(items)

        if len(items) < page_size:
            break
        page += 1

    logger.info("Cursor: %d 件のオンデマンド利用データを取得", len(all_spend))
    return all_spend


def build_ondemand_usd_map(spend_data: list[dict[str, Any]]) -> dict[str, float]:
    """オンデマンド利用データからユーザー別 USD マップを構築する。

    spendCents を 100 で割って USD に変換する。
    """
    usd_map: dict[str, float] = {}
    for item in spend_data:
        email = item.get("email", item.get("userEmail", ""))
        spend_cents = float(item.get("spendCents", 0))
        ondemand_usd = spend_cents / 100
        if email:
            usd_map[email] = usd_map.get(email, 0) + ondemand_usd
    return usd_map


# ============================================
# 基本料金の計算
# ============================================

def _get_billing_cycle_days(target_date: date) -> int:
    """対象月の請求サイクル日数を返す。

    請求サイクルは CURSOR_BILLING_CYCLE_START_DAY 日から翌月の同日前日まで。
    """
    start_day = CURSOR_BILLING_CYCLE_START_DAY
    year = target_date.year
    month = target_date.month

    # 当月サイクル開始日
    cycle_start = date(year, month, min(start_day, calendar.monthrange(year, month)[1]))

    # 翌月サイクル開始日
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    cycle_end = date(next_year, next_month, min(start_day, calendar.monthrange(next_year, next_month)[1]))

    return (cycle_end - cycle_start).days


def calculate_base_fee_usd(active_days: int, cycle_days: int) -> float:
    """基本料金を日割り計算する。

    基本料金USD = 月額単価USD × 稼働日数 ÷ 請求サイクル日数
    """
    if cycle_days <= 0 or CURSOR_MONTHLY_RATE <= 0:
        return 0.0
    return round(CURSOR_MONTHLY_RATE * active_days / cycle_days, 2)


# ============================================
# レコード生成
# ============================================

def build_usage_records(
    raw_members: list[dict[str, Any]], batch_id: str
) -> list[UsageRecord]:
    """API レスポンスを UsageRecord のリストに正規化する。"""
    fetched_at = now_iso()
    records: list[UsageRecord] = []

    for member in raw_members:
        user_name = member.get("name", member.get("displayName", ""))
        user_email = member.get("email", "")
        plan_name = member.get("plan", member.get("planName", ""))
        usage_date = member.get("date", member.get("period", ""))

        metrics = {
            "requests_count": member.get("requestsCount", member.get("requests", "")),
            "tokens_used": member.get("tokensUsed", member.get("tokens", "")),
            "active_days": member.get("activeDays", ""),
        }

        for metric_name, metric_value in metrics.items():
            if metric_value == "" or metric_value is None:
                continue
            records.append(
                UsageRecord(
                    fetched_at=fetched_at,
                    service_name="cursor",
                    user_name=user_name,
                    user_email=user_email,
                    plan_name=plan_name,
                    usage_date=usage_date,
                    metric_name=metric_name,
                    metric_value=str(metric_value),
                    source_type="api",
                    raw_payload=json.dumps(member, ensure_ascii=False),
                    batch_id=batch_id,
                )
            )

    logger.info("Cursor: %d 件の利用レコードを生成", len(records))
    return records


def build_pricing_records(
    members: list[dict[str, Any]],
    ondemand_usd_map: dict[str, float],
    batch_id: str,
) -> list[PricingRecord]:
    """メンバー情報とオンデマンド利用額から料金レコードを生成する。

    基本料金: メンバー 1 人あたり月額単価の全額 (稼働日数は GAS 側で精密計算)
    オンデマンド料金: API から取得した利用額
    """
    fetched_at = now_iso()
    today = date.today()
    accounting_month = today.strftime("%Y-%m")
    cycle_days = _get_billing_cycle_days(today)
    records: list[PricingRecord] = []

    # 基本料金: メンバーごとに 1 行
    for member in members:
        email = member.get("email", "")
        name = member.get("name", member.get("displayName", ""))
        # フルサイクル分の基本料金 (稼働日数の日割りは GAS 側で精密計算する)
        base_usd = calculate_base_fee_usd(cycle_days, cycle_days)

        records.append(
            PricingRecord(
                fetched_at=fetched_at,
                service_name="cursor",
                accounting_month=accounting_month,
                user_email=email,
                user_name=name,
                charge_type="base",
                amount_usd=base_usd,
                description=f"月額単価={CURSOR_MONTHLY_RATE} USD, サイクル日数={cycle_days}",
                batch_id=batch_id,
            )
        )

    # オンデマンド料金: ユーザーごとに 1 行
    for email, usd in ondemand_usd_map.items():
        # メンバー情報からユーザー名を取得
        name = ""
        for m in members:
            if m.get("email", "") == email:
                name = m.get("name", m.get("displayName", ""))
                break

        records.append(
            PricingRecord(
                fetched_at=fetched_at,
                service_name="cursor",
                accounting_month=accounting_month,
                user_email=email,
                user_name=name,
                charge_type="ondemand",
                amount_usd=usd,
                description="Cursor API /teams/spend から取得 (spendCents → USD)",
                batch_id=batch_id,
            )
        )

    logger.info("Cursor: %d 件の料金レコードを生成", len(records))
    return records


# ============================================
# メインエントリポイント
# ============================================

def run() -> tuple[list[UsageRecord], list[PricingRecord]]:
    """Cursor 利用状況取得のメインエントリポイント。

    Returns:
        (利用レコード, 料金レコード) のタプル
    """
    batch_id = generate_batch_id()
    logger.info("=== Cursor 取得開始 (batch_id: %s) ===", batch_id)

    try:
        # メンバー取得
        members = fetch_team_members()

        # 利用レコード生成
        usage_records = build_usage_records(members, batch_id)
        if usage_records:
            filepath = save_records_to_json(usage_records, f"cursor_{batch_id}.json")
            logger.info("Cursor: 利用データ中間ファイル保存 -> %s", filepath)

        # オンデマンド利用額取得
        spend_data = fetch_team_spend()
        ondemand_usd_map = build_ondemand_usd_map(spend_data)

        # 料金レコード生成
        pricing_records = build_pricing_records(members, ondemand_usd_map, batch_id)
        if pricing_records:
            filepath = save_records_to_json(
                pricing_records, f"cursor_pricing_{batch_id}.json"
            )
            logger.info("Cursor: 料金データ中間ファイル保存 -> %s", filepath)

        logger.info(
            "=== Cursor 取得完了: 利用=%d 件, 料金=%d 件 ===",
            len(usage_records),
            len(pricing_records),
        )
        return usage_records, pricing_records

    except CursorAPIError:
        logger.exception("Cursor 取得でエラーが発生しました")
        raise


if __name__ == "__main__":
    try:
        run()
    except Exception:
        sys.exit(1)
