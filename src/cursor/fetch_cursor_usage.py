"""Cursor 利用状況取得モジュール

Cursor API を利用して、チームメンバーの利用状況データを取得する。
"""

import json
import sys
from typing import Any

import requests

from src.common.config import CURSOR_API_BASE_URL, CURSOR_API_KEY
from src.common.logger import get_logger
from src.common.utils import UsageRecord, generate_batch_id, now_iso, save_records_to_json

logger = get_logger(__name__)


class CursorAPIError(Exception):
    """Cursor API 呼び出し時のエラー。"""


def _build_headers() -> dict[str, str]:
    """API リクエスト用ヘッダーを構築する。"""
    if not CURSOR_API_KEY:
        raise CursorAPIError("CURSOR_API_KEY が設定されていません")
    return {
        "Authorization": f"Bearer {CURSOR_API_KEY}",
        "Content-Type": "application/json",
    }


def _request_api(endpoint: str, params: dict | None = None) -> Any:
    """Cursor API へ GET リクエストを送信する。"""
    url = f"{CURSOR_API_BASE_URL}/{endpoint.lstrip('/')}"
    headers = _build_headers()

    logger.info("Cursor API リクエスト: %s", url)
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        raise CursorAPIError(f"API リクエスト失敗: {e}") from e


def fetch_team_usage() -> list[dict[str, Any]]:
    """チームの利用状況を取得する。

    Cursor API のエンドポイント仕様に合わせて調整が必要。
    ここでは想定される構造でデータを取得する。
    """
    # NOTE: Cursor API の正式な仕様に合わせて endpoint / params を調整してください
    data = _request_api("usage/team")
    members = data.get("members", data.get("users", []))
    logger.info("Cursor: %d 件のユーザーデータを取得", len(members))
    return members


def build_records(
    raw_members: list[dict[str, Any]], batch_id: str
) -> list[UsageRecord]:
    """API レスポンスを UsageRecord のリストに正規化する。"""
    fetched_at = now_iso()
    records: list[UsageRecord] = []

    for member in raw_members:
        # NOTE: 実際の API レスポンスのキー名に合わせて修正してください
        user_name = member.get("name", member.get("displayName", ""))
        user_email = member.get("email", "")
        plan_name = member.get("plan", member.get("planName", ""))
        usage_date = member.get("date", member.get("period", ""))

        # 利用量メトリクスを個別レコードとして展開
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

    logger.info("Cursor: %d 件のレコードを生成", len(records))
    return records


def run() -> list[UsageRecord]:
    """Cursor 利用状況取得のメインエントリポイント。"""
    batch_id = generate_batch_id()
    logger.info("=== Cursor 取得開始 (batch_id: %s) ===", batch_id)

    try:
        raw_members = fetch_team_usage()
        records = build_records(raw_members, batch_id)
        if records:
            filepath = save_records_to_json(records, f"cursor_{batch_id}.json")
            logger.info("Cursor: 中間ファイル保存 -> %s", filepath)
        logger.info("=== Cursor 取得完了: %d 件 ===", len(records))
        return records
    except CursorAPIError:
        logger.exception("Cursor 取得でエラーが発生しました")
        raise


if __name__ == "__main__":
    try:
        run()
    except Exception:
        sys.exit(1)
