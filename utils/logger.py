"""공용 로거. 콘솔 + 로테이팅 파일 핸들러를 idempotent하게 구성한다."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from config import LOG_DIR

_CONFIGURED = False


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    try:
        log_path = LOG_DIR / "pipeline.log"
        file_handler = RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        # 파일 시스템에 쓸 수 없는 환경(읽기 전용 등)이어도 콘솔 로깅은 계속 동작.
        root.warning("로그 파일 핸들러 구성 실패 - 콘솔 로그만 사용합니다.")

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure_root()
    return logging.getLogger(name)
