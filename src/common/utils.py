"""共通ユーティリティモジュール

batch_id の生成、日時フォーマット、共通データ構造の定義など。
"""

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.common.config import OUTPUT_DIR


def generate_batch_id() -> str:
    """実行単位識別子を生成する (日時 + UUID短縮)。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"{ts}_{short_uuid}"


def now_iso() -> str:
    """現在日時を ISO 8601 形式で返す。"""
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class UsageRecord:
    """raw シートへ追記する 1 行分のデータ。"""

    fetched_at: str
    service_name: str
    user_name: str
    user_email: str
    plan_name: str
    usage_date: str
    metric_name: str
    metric_value: str
    source_type: str  # "api" or "playwright"
    raw_payload: str = ""
    batch_id: str = ""

    def to_row(self) -> list[str]:
        """Google Sheets 追記用のリスト形式に変換する。"""
        return [
            self.fetched_at,
            self.service_name,
            self.user_name,
            self.user_email,
            self.plan_name,
            self.usage_date,
            self.metric_name,
            self.metric_value,
            self.source_type,
            self.raw_payload,
            self.batch_id,
        ]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# raw シートのヘッダー定義
RAW_SHEET_HEADERS = [
    "fetched_at",
    "service_name",
    "user_name",
    "user_email",
    "plan_name",
    "usage_date",
    "metric_name",
    "metric_value",
    "source_type",
    "raw_payload",
    "batch_id",
]


@dataclass
class PricingRecord:
    """料金シートへ追記する 1 行分のデータ。

    各サービスの基本料金・オンデマンド料金・合計料金を保持する。
    """

    fetched_at: str
    service_name: str  # "cursor" / "codex" / "claude_code"
    accounting_month: str  # "YYYY-MM" 形式の計上月
    user_email: str
    user_name: str
    charge_type: str  # "base" / "ondemand"
    amount_usd: float
    description: str = ""
    batch_id: str = ""

    def to_row(self) -> list:
        """Google Sheets 追記用のリスト形式に変換する。"""
        return [
            self.fetched_at,
            self.service_name,
            self.accounting_month,
            self.user_email,
            self.user_name,
            self.charge_type,
            self.amount_usd,
            self.description,
            self.batch_id,
        ]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# 料金シートのヘッダー定義
PRICING_SHEET_HEADERS = [
    "fetched_at",
    "service_name",
    "accounting_month",
    "user_email",
    "user_name",
    "charge_type",
    "amount_usd",
    "description",
    "batch_id",
]


def save_records_to_json(
    records: list[UsageRecord] | list[PricingRecord], filename: str
) -> Path:
    """取得結果を JSON ファイルとして output/ に保存する (中間ファイル)。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = OUTPUT_DIR / filename
    data = [r.to_dict() for r in records]
    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return filepath


def load_records_from_json(filepath: Path) -> list[UsageRecord]:
    """JSON ファイルから UsageRecord のリストを復元する。"""
    data = json.loads(filepath.read_text(encoding="utf-8"))
    return [UsageRecord(**item) for item in data]


def load_pricing_records_from_json(filepath: Path) -> list[PricingRecord]:
    """JSON ファイルから PricingRecord のリストを復元する。"""
    data = json.loads(filepath.read_text(encoding="utf-8"))
    return [PricingRecord(**item) for item in data]
