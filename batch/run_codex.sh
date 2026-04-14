#!/bin/bash
# ============================================
# Codex 利用状況取得バッチ
# ============================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === Codex 取得バッチ開始 ==="

if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

python -m src.main --targets codex "$@"
EXIT_CODE=$?

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === Codex 取得バッチ終了 (exit: $EXIT_CODE) ==="
exit $EXIT_CODE
