"""Google Sheets 追記モジュール

取得した UsageRecord データを Google Sheets の raw_* シートへ追記する。
"""

import sys
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from src.common.config import GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_SHEETS_SPREADSHEET_ID, PROJECT_ROOT
from src.common.logger import get_logger
from src.common.utils import RAW_SHEET_HEADERS, UsageRecord, load_records_from_json

logger = get_logger(__name__)

# Google Sheets API のスコープ
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

# サービス名 → シート名のマッピング
SHEET_NAME_MAP = {
    "cursor": "raw_cursor",
    "codex": "raw_codex",
    "claude_code": "raw_claude_code",
}


def _get_client() -> gspread.Client:
    """認証済み gspread クライアントを返す。"""
    cred_path = Path(GOOGLE_SERVICE_ACCOUNT_FILE)
    if not cred_path.is_absolute():
        cred_path = PROJECT_ROOT / cred_path

    if not cred_path.exists():
        raise FileNotFoundError(
            f"サービスアカウントファイルが見つかりません: {cred_path}\n"
            "作業者操作.md の手順に従って設定してください。"
        )

    credentials = Credentials.from_service_account_file(str(cred_path), scopes=SCOPES)
    return gspread.authorize(credentials)


def _ensure_sheet_headers(worksheet: gspread.Worksheet) -> None:
    """シートにヘッダー行がなければ追加する。"""
    existing = worksheet.row_values(1)
    if not existing:
        worksheet.append_row(RAW_SHEET_HEADERS, value_input_option="RAW")
        logger.info("ヘッダー行を追加しました: %s", worksheet.title)


def append_records(records: list[UsageRecord]) -> int:
    """UsageRecord のリストを対応する raw_* シートへ追記する。

    Returns:
        追記した行数
    """
    if not records:
        logger.warning("追記するレコードがありません")
        return 0

    if not GOOGLE_SHEETS_SPREADSHEET_ID:
        raise ValueError("GOOGLE_SHEETS_SPREADSHEET_ID が設定されていません")

    client = _get_client()
    spreadsheet = client.open_by_key(GOOGLE_SHEETS_SPREADSHEET_ID)

    # サービスごとにグループ化
    grouped: dict[str, list[UsageRecord]] = {}
    for record in records:
        grouped.setdefault(record.service_name, []).append(record)

    total_appended = 0

    for service_name, service_records in grouped.items():
        sheet_name = SHEET_NAME_MAP.get(service_name, f"raw_{service_name}")
        logger.info("シート '%s' へ %d 件追記開始", sheet_name, len(service_records))

        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            logger.info("シート '%s' が見つかりません。新規作成します。", sheet_name)
            worksheet = spreadsheet.add_worksheet(
                title=sheet_name, rows=1000, cols=len(RAW_SHEET_HEADERS)
            )

        _ensure_sheet_headers(worksheet)

        # バッチ追記
        rows = [r.to_row() for r in service_records]
        worksheet.append_rows(rows, value_input_option="RAW")
        total_appended += len(rows)
        logger.info("シート '%s' へ %d 件追記完了", sheet_name, len(rows))

    return total_appended


def append_from_json(filepath: str | Path) -> int:
    """JSON 中間ファイルからレコードを読み込み、Sheets へ追記する。"""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"中間ファイルが見つかりません: {path}")

    records = load_records_from_json(path)
    logger.info("JSON ファイルから %d 件のレコードを読み込みました: %s", len(records), path)
    return append_records(records)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python -m src.sheets.append_to_sheets <jsonファイルパス>")
        sys.exit(1)

    json_path = sys.argv[1]
    try:
        count = append_from_json(json_path)
        print(f"{count} 件を Google Sheets へ追記しました")
    except Exception:
        logger.exception("Sheets 追記でエラーが発生しました")
        sys.exit(1)
