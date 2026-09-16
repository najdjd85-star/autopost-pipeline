"""
상태 없는(stateless) 단발성 텔레그램 발송 유틸리티.

telegram_bot.py의 polling Application(장기 실행 이벤트 루프)과는 완전히
분리되어 있다 - 이 모듈은 호출할 때마다 자체 이벤트 루프를 만들고 닫으므로
어느 스레드에서 호출해도 안전하다. content_updater.py처럼 승인 알림만
보내면 되고 인라인 버튼 콜백을 처리할 필요가 없는 모듈은 무거운
telegram_bot.py 대신 이 모듈을 사용한다 (순환 임포트 방지 목적도 겸함).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)


def _is_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_admin_chat_id)


def send_message_sync(
    text: str, chat_id: Optional[str] = None, parse_mode: str = "HTML"
) -> bool:
    if not _is_configured() and not chat_id:
        logger.info("TELEGRAM_BOT_TOKEN/ADMIN_CHAT_ID 미설정 - 메시지 발송을 건너뜁니다: %.60s", text)
        return False
    target_chat_id = chat_id or settings.telegram_admin_chat_id

    try:
        import telegram  # python-telegram-bot

        async def _send() -> None:
            bot = telegram.Bot(token=settings.telegram_bot_token)
            await bot.send_message(chat_id=target_chat_id, text=text, parse_mode=parse_mode)

        asyncio.run(_send())
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("텔레그램 메시지 발송 실패: %s", exc)
        return False


def send_photo_sync(
    photo_path: Path, caption: str = "", chat_id: Optional[str] = None
) -> bool:
    if not _is_configured() and not chat_id:
        logger.info("TELEGRAM 미설정 - 사진 발송을 건너뜁니다.")
        return False
    target_chat_id = chat_id or settings.telegram_admin_chat_id

    photo_path = Path(photo_path)
    if not photo_path.exists():
        logger.warning("전송할 사진 파일이 존재하지 않습니다: %s", photo_path)
        return False

    try:
        import telegram

        async def _send() -> None:
            bot = telegram.Bot(token=settings.telegram_bot_token)
            with open(photo_path, "rb") as fh:
                await bot.send_photo(chat_id=target_chat_id, photo=fh, caption=caption)

        asyncio.run(_send())
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("텔레그램 사진 발송 실패: %s", exc)
        return False
