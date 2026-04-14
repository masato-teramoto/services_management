"""ロギングモジュール

ファイル出力とコンソール出力の両方を行うロガーを提供する。
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

from src.common.config import LOG_DIR, LOG_LEVEL


def get_logger(name: str) -> logging.Logger:
    """名前付きロガーを生成して返す。

    - コンソール (stdout) とログファイルの両方に出力
    - ログファイルは日付ごとに分割
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # コンソール出力
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ファイル出力
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"{datetime.now():%Y-%m-%d}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
