"""メイン実行スクリプト

全サービスの利用状況を取得し、Google Sheets へ追記する統合バッチ処理。
個別サービスの取得失敗時も、他サービスは可能な範囲で継続実行する。

各サービスから利用レコード (UsageRecord) と料金レコード (PricingRecord) を取得し、
それぞれ raw_* シートと raw_pricing シートへ追記する。
"""

import argparse
import sys

from src.common.logger import get_logger
from src.common.utils import PricingRecord, UsageRecord, generate_batch_id

logger = get_logger("main")


def fetch_cursor() -> tuple[list[UsageRecord], list[PricingRecord]]:
    from src.cursor.fetch_cursor_usage import run
    return run()


def fetch_codex() -> tuple[list[UsageRecord], list[PricingRecord]]:
    from src.codex.fetch_codex_usage import run
    return run()


def fetch_claude_code() -> tuple[list[UsageRecord], list[PricingRecord]]:
    from src.claude_code.fetch_claude_code_usage import run
    return run()


def append_to_sheets(records: list[UsageRecord]) -> int:
    from src.sheets.append_to_sheets import append_records
    return append_records(records)


def append_pricing_to_sheets(records: list[PricingRecord]) -> int:
    from src.sheets.append_to_sheets import append_pricing_records
    return append_pricing_records(records)


SERVICE_FETCHERS = {
    "cursor": fetch_cursor,
    "codex": fetch_codex,
    "claude_code": fetch_claude_code,
}

# Codex は利用料をサイトから確認することが不可能なため、現時点ではデフォルト対象外とする。
# 将来的に対応可能になった場合は DEFAULT_TARGETS へ追加する。
# 明示的に --targets codex を指定すれば個別実行は可能。
DEFAULT_TARGETS = ["cursor", "claude_code"]


def main(targets: list[str] | None = None, skip_sheets: bool = False) -> None:
    """メイン処理。

    Args:
        targets: 取得対象サービス名のリスト。None の場合は全サービス。
        skip_sheets: True の場合、Sheets への追記をスキップ (中間ファイルのみ保存)。
    """
    batch_id = generate_batch_id()
    logger.info("========================================")
    logger.info("バッチ処理開始 (batch_id: %s)", batch_id)
    logger.info("========================================")

    if targets is None:
        targets = list(DEFAULT_TARGETS)

    all_usage_records: list[UsageRecord] = []
    all_pricing_records: list[PricingRecord] = []
    errors: list[str] = []

    for service_name in targets:
        fetcher = SERVICE_FETCHERS.get(service_name)
        if fetcher is None:
            logger.error("不明なサービス: %s", service_name)
            errors.append(f"不明なサービス: {service_name}")
            continue

        try:
            usage_records, pricing_records = fetcher()
            all_usage_records.extend(usage_records)
            all_pricing_records.extend(pricing_records)
            logger.info(
                "%s: 利用=%d 件, 料金=%d 件 取得成功",
                service_name,
                len(usage_records),
                len(pricing_records),
            )
        except Exception as e:
            logger.error("%s: 取得失敗 - %s", service_name, e)
            errors.append(f"{service_name}: {e}")
            # 他サービスは継続実行

    # Google Sheets 追記
    if not skip_sheets:
        # 利用データ追記
        if all_usage_records:
            try:
                count = append_to_sheets(all_usage_records)
                logger.info("Google Sheets (raw) へ合計 %d 件追記しました", count)
            except Exception as e:
                logger.error("Sheets 利用データ追記失敗: %s", e)
                errors.append(f"sheets_usage: {e}")

        # 料金データ追記
        if all_pricing_records:
            try:
                count = append_pricing_to_sheets(all_pricing_records)
                logger.info("Google Sheets (pricing) へ合計 %d 件追記しました", count)
            except Exception as e:
                logger.error("Sheets 料金データ追記失敗: %s", e)
                errors.append(f"sheets_pricing: {e}")

    # 結果サマリ
    logger.info("========================================")
    logger.info("バッチ処理完了")
    logger.info("  利用レコード数: %d", len(all_usage_records))
    logger.info("  料金レコード数: %d", len(all_pricing_records))
    logger.info("  エラー数: %d", len(errors))
    if errors:
        for err in errors:
            logger.error("  - %s", err)
    logger.info("========================================")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIサービス利用状況取得バッチ")
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=list(SERVICE_FETCHERS.keys()),
        help="取得対象サービス (省略時は全サービス)",
    )
    parser.add_argument(
        "--skip-sheets",
        action="store_true",
        help="Google Sheets への追記をスキップ",
    )
    args = parser.parse_args()
    main(targets=args.targets, skip_sheets=args.skip_sheets)
