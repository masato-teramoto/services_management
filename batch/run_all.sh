#!/bin/bash
# ============================================
# 全サービス利用状況取得バッチ
# ============================================
# 使い方:
#   ./batch/run_all.sh           # 全サービス取得 + Sheets追記
#   ./batch/run_all.sh --skip-sheets  # Sheets追記をスキップ
# ============================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 全サービス取得バッチ開始 ==="

# Python 仮想環境があれば有効化
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# メインスクリプト実行
python -m src.main "$@"
EXIT_CODE=$?

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 全サービス取得バッチ終了 (exit: $EXIT_CODE) ==="
exit $EXIT_CODE
