"""
텔레그램 승인 카드의 버튼(🌐/✏️/✅/❌) 콜백이 실제로 프로세스 경계를 넘어
정상 수신되는지 확인하는 1회성 테스트 하네스. Claude(generator.py)는
호출하지 않는다.

⚠️ 안전 설계: 이 스크립트는 telegram_bot.handle_callback(실제 발행 로직이
연결된 프로덕션 핸들러)을 절대 사용하지 않는다. 대신 이 스크립트만의 안전한
콜백 핸들러를 등록해서, 어떤 버튼을 눌러도 "수신 확인" 메시지만 남기고
끝난다 - 워드프레스 발행도, 소셜 배포도, 실제로 아무것도 실행하지 않는다.
(과거 버전은 실제 handle_callback을 재사용해서 워드프레스 자격증명이 설정된
뒤에는 "✅ 승인"을 누르면 실제로 사이트에 테스트 글이 발행되는 사고가 있었다.
이 스크립트는 그 문제를 근본적으로 차단하도록 다시 작성되었다.)

사용법:
    venv\\Scripts\\python.exe scripts\\test_approval_flow.py

주의: 텔레그램은 봇 토큰 하나당 동시에 1개의 getUpdates 폴링만 허용한다.
이 스크립트를 실행하기 전에 main.py daemon(또는 GUI의 데몬)이 켜져 있다면
반드시 먼저 꺼야 한다.
"""
from __future__ import annotations

import asyncio
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import telegram_bot  # noqa: E402
from config import settings  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger("test_approval_flow")

DUMMY_DRAFT = {
    "title": "[테스트] 버튼 클릭 흐름 확인용 샘플 (실제 발행 안 됨)",
    "fact_summary": "이 카드는 실제 콘텐츠가 아니며, 승인/반려 버튼의 콜백 수신 여부만 확인하기 위한 테스트입니다.",
    "longtail_keywords": ["테스트1", "테스트2"],
    "shorts_script": "이것은 버튼 동작 테스트를 위한 짧은 샘플 나레이션입니다.",
}

MAX_WAIT_SECONDS = 180
_RESULT: dict = {"action": None, "approval_id": None}


async def _safe_test_callback(update, context) -> None:  # noqa: ANN001
    """어떤 버튼을 눌러도 실제 발행/배포를 절대 실행하지 않는 테스트 전용 핸들러."""
    query = update.callback_query
    await query.answer()

    action, _, approval_id = query.data.partition(":")
    pending = telegram_bot._load_pending(approval_id)  # noqa: SLF001

    if pending is None:
        await query.edit_message_text(
            "⚠️ [테스트] 대기열에서 찾을 수 없습니다 (approval_id 불일치 또는 이미 처리됨)."
        )
        _RESULT["action"] = "not_found"
        _RESULT["approval_id"] = approval_id
        return

    await query.edit_message_text(
        f"✅ [테스트] 버튼 클릭 수신 확인 (action={action}).\n"
        f"실제 워드프레스 발행이나 소셜 배포는 전혀 실행되지 않았습니다."
    )
    telegram_bot._delete_pending(approval_id)  # noqa: SLF001
    _RESULT["action"] = action
    _RESULT["approval_id"] = approval_id


def main() -> int:
    if not (settings.telegram_bot_token and settings.telegram_admin_chat_id):
        print("[오류] 텔레그램 미설정 - 테스트를 진행할 수 없습니다.")
        return 1

    from telegram.ext import Application, CallbackQueryHandler

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.add_handler(CallbackQueryHandler(_safe_test_callback))

    import threading

    def _run() -> None:
        telegram_bot._LOOP = asyncio.new_event_loop()  # noqa: SLF001
        asyncio.set_event_loop(telegram_bot._LOOP)  # noqa: SLF001
        application.run_polling(stop_signals=None, close_loop=False)

    thread = threading.Thread(target=_run, name="test-telegram-bot", daemon=True)
    thread.start()
    time.sleep(2)  # 폴링이 준비될 시간을 잠깐 준다.

    approval_id = uuid.uuid4().hex[:10]
    draft = dict(DUMMY_DRAFT)
    draft["_approval_id"] = approval_id

    text, keyboard = telegram_bot.format_approval_card("A", draft)
    telegram_bot._save_pending(  # noqa: SLF001
        approval_id, {"site": "A", "draft": draft, "post_id": None}
    )

    async def _send() -> None:
        import telegram

        bot = telegram.Bot(token=settings.telegram_bot_token)
        await bot.send_message(
            chat_id=settings.telegram_admin_chat_id,
            text=text + "\n\n🧪 [안전 테스트 카드] 어떤 버튼을 눌러도 실제 발행은 되지 않습니다.",
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    asyncio.run(_send())
    print(f"[안내] 안전 테스트 카드 발송 완료 (approval_id={approval_id}).")
    print(f"[안내] 텔레그램에서 아무 버튼이나 눌러주세요. 최대 {MAX_WAIT_SECONDS}초 동안 기다립니다...")

    waited = 0
    while _RESULT["action"] is None and waited < MAX_WAIT_SECONDS:
        time.sleep(2)
        waited += 2

    if _RESULT["action"] is not None:
        print(f"[결과] ✅ 콜백 수신 확인됨: action={_RESULT['action']}")
        print("       (워드프레스/소셜 미디어는 전혀 건드리지 않았습니다)")
    else:
        print(f"[결과] {MAX_WAIT_SECONDS}초 동안 버튼 클릭이 없어 테스트를 종료합니다.")

    try:
        asyncio.run_coroutine_threadsafe(application.stop(), telegram_bot._LOOP)  # noqa: SLF001
        time.sleep(1)
    except Exception:  # noqa: BLE001
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
