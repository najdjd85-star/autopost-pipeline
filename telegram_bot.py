"""
원클릭 승인 텔레그램 봇 및 통합 배포 체인 트리거.

python-telegram-bot v20+(asyncio 기반)를 전용 스레드에서 실행하여,
main.py의 동기(schedule) 루프/Flask 스레드와 충돌 없이 공존한다.

메시지 포맷: [Site 뱃지] + 제목 + 요약 카드
인라인 버튼: [🌐 웹 미리보기] [✏️ WP 수정] [✅ 일괄 발행 승인] [❌ 반려]
승인 클릭 시: WP 공개 -> 색인 핑 -> 스레드 -> 핀터레스트 순차 배포.

영상(쇼츠/롱폼) 제작은 지원하지 않는다 - 렌더링 서버의 메모리/CPU 부담이 커서
제외했다(자세한 경위는 프로젝트 메모리 참고). 이 때문에 영상이 필요한
유튜브/인스타그램 릴스 배포도 함께 제외된다.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from config import BASE_DIR, OUTPUT_DIR, settings
from constants import SITE_BADGES
from image_hybrid_engine import process_image_slots
from smart_affiliate_matcher import inject_affiliate_slots
from social_distributor import build_card_news_thumbnail, distribute_all
from utils.logger import get_logger
from wp_client import WordPressClient

logger = get_logger(__name__)

# 승인 대기 중인 초안들을 담는 인메모리 캐시 (같은 프로세스 안에서는 이걸 우선 사용).
# {approval_id: {"site": str, "draft": dict, "post_id": int|None}}
PENDING: Dict[str, Dict[str, Any]] = {}

# `python main.py run-now`(CLI 한 번 실행)와 `daemon`(상시 폴링)은 서로 다른
# 프로세스인 경우가 흔하다 - CLI가 만든 승인 요청을 daemon 프로세스의
# handle_callback이 찾을 수 있어야 하므로, 인메모리 PENDING만으로는 부족하고
# 디스크에도 반드시 저장해야 한다 (프로세스 경계를 넘는 유일한 방법).
_PENDING_DIR = OUTPUT_DIR / "pending_approvals"


def _pending_file(approval_id: str) -> Path:
    return _PENDING_DIR / f"{approval_id}.json"


def _save_pending(approval_id: str, data: Dict[str, Any]) -> None:
    PENDING[approval_id] = data
    try:
        _PENDING_DIR.mkdir(parents=True, exist_ok=True)
        _pending_file(approval_id).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("승인 요청(%s) 디스크 저장 실패: %s", approval_id, exc)


def _load_pending(approval_id: str) -> Optional[Dict[str, Any]]:
    if approval_id in PENDING:
        return PENDING[approval_id]
    path = _pending_file(approval_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        PENDING[approval_id] = data
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("승인 요청(%s) 디스크 로드 실패: %s", approval_id, exc)
        return None


def _delete_pending(approval_id: str) -> None:
    PENDING.pop(approval_id, None)
    try:
        _pending_file(approval_id).unlink(missing_ok=True)
    except OSError:
        pass


def _spawn_stage(command: str, approval_id: str) -> None:
    """다음 단계(CLI 서브커맨드)를 완전히 별도 OS 프로세스로 띄우고 기다리지 않는다.

    콘텐츠 생성/영상 렌더링/멀티채널 배포를 전부 한 프로세스 안에서 순차로
    처리하면(특히 메모리가 작은 서버에서) 메모리가 계속 누적되다 OOM으로
    죽는 문제가 있어, 단계마다 새 프로세스로 분리해 매 단계 시작 시 항상
    깨끗한 메모리 상태에서 시작하게 한다. `start_new_session=True`로 완전히
    분리해 부모(텔레그램 봇 폴링 프로세스나 로그인 세션)가 끝나도 살아남는다.
    """
    log_dir = OUTPUT_DIR / approval_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{command}.log"
    try:
        with open(log_path, "a", encoding="utf-8") as log_file:
            subprocess.Popen(
                [sys.executable, str(BASE_DIR / "main.py"), command, approval_id],
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                cwd=str(BASE_DIR),
            )
    except OSError as exc:
        logger.warning("다음 단계(%s) 프로세스 실행 실패(%s): %s", command, approval_id, exc)


_LOOP: Optional[asyncio.AbstractEventLoop] = None
_BOT_THREAD: Optional[threading.Thread] = None
_APPLICATION: Any = None

# python-telegram-bot의 기본 타임아웃(수 초)은 영상 업로드에는 너무 짧아
# "Timed out" 오류가 나기 쉽다 - send_video 호출마다 넉넉한 값으로 덮어쓴다.
VIDEO_UPLOAD_TIMEOUTS = {
    "read_timeout": 120,
    "write_timeout": 120,
    "connect_timeout": 30,
    "pool_timeout": 30,
}


def _is_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_admin_chat_id)


def format_approval_card(site: str, draft: Dict[str, Any]) -> Tuple[str, Any]:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    badge = SITE_BADGES.get(site, site)
    title = draft.get("title", "(제목 없음)")
    summary = draft.get("fact_summary", "")

    timeout_h = settings.auto_publish_timeout_hours
    text = (
        f"{badge}\n"
        f"<b>{title}</b>\n\n"
        f"{summary}\n\n"
        f"롱테일 키워드: {', '.join(draft.get('longtail_keywords', [])[:5])}\n\n"
        f"⏰ {timeout_h:g}시간 동안 응답이 없으면 자동으로 발행됩니다."
    )

    approval_id = draft.get("_approval_id", "")
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🌐 웹 미리보기", callback_data=f"preview:{approval_id}"),
                InlineKeyboardButton("✏️ WP 수정", callback_data=f"edit:{approval_id}"),
            ],
            [
                InlineKeyboardButton("✅ 일괄 발행 승인", callback_data=f"approve:{approval_id}"),
                InlineKeyboardButton("❌ 반려", callback_data=f"reject:{approval_id}"),
            ],
        ]
    )
    return text, keyboard


async def _send_test_approval_async(site: str) -> None:
    """generate_post()(Claude 호출) 없이, 더미 내용으로 실제 승인 카드+쇼츠 영상을 보낸다.

    _APPLICATION(데몬의 polling Application)에 의존하지 않고 자체적으로
    telegram.Bot을 만들어 보내므로, 데몬이 켜져 있지 않아도 카드는 도착한다.
    단, ✅ 버튼을 눌렀을 때의 콜백 처리는 데몬(polling)이 켜져 있어야 동작한다.
    """
    import telegram

    dummy_draft: Dict[str, Any] = {
        "title": "[테스트] 이 카드는 실제 콘텐츠가 아닙니다",
        "fact_summary": "텔레그램 승인 카드의 형식과 버튼이 정상적으로 도착하는지 확인하기 위한 샘플입니다.",
        "longtail_keywords": ["테스트 키워드1", "테스트 키워드2", "테스트 키워드3"],
        "shorts_script": "이것은 텔레그램 승인 카드 테스트를 위한 짧은 샘플 나레이션입니다. 실제 콘텐츠가 아닙니다.",
        "_approval_id": "test",
    }

    text, keyboard = format_approval_card(site, dummy_draft)
    text += (
        "\n\n⚠️ 이건 테스트 카드입니다 (Claude를 호출하지 않아 토큰이 소모되지 않았습니다). "
        "실제 콘텐츠가 없으므로 승인을 눌러도 발행되지 않고, 데몬이 꺼져 있으면 버튼 자체가 반응하지 않습니다."
    )

    bot = telegram.Bot(token=settings.telegram_bot_token)
    await bot.send_message(
        chat_id=settings.telegram_admin_chat_id, text=text, parse_mode="HTML", reply_markup=keyboard
    )


def send_test_approval_card(site: str) -> bool:
    """CLI/GUI에서 호출하는 동기 래퍼. Claude를 호출하지 않는다."""
    if not _is_configured():
        logger.warning("TELEGRAM_BOT_TOKEN/ADMIN_CHAT_ID 미설정 - 테스트 카드를 보낼 수 없습니다.")
        return False
    try:
        asyncio.run(_send_test_approval_async(site))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("테스트 승인 카드 발송 실패: %s", exc)
        return False


async def send_approval_request(site: str, draft: Dict[str, Any]) -> Optional[str]:
    """초안을 승인 대기열에 등록하고 텔레그램으로 승인 요청 카드(텍스트만)를 보낸다.

    _APPLICATION(데몬의 polling Application)에 의존하지 않고 자체 telegram.Bot으로
    보낸다 - `run-now`가 daemon과 별도 프로세스로 실행되는 경우가 흔하기 때문에,
    "봇이 지금 이 프로세스에서 폴링 중이어야만 카드를 보낼 수 있다"는 제약을
    없애야 한다. 대기열은 디스크에도 저장되므로, 실제 버튼 콜백은 나중에
    daemon 프로세스가 폴링 중일 때 처리되면 된다.
    """
    if not _is_configured():
        logger.warning("텔레그램 봇 미설정 - 승인 요청을 보낼 수 없습니다.")
        return None

    import telegram

    approval_id = uuid.uuid4().hex[:10]
    draft["_approval_id"] = approval_id

    text, keyboard = format_approval_card(site, draft)

    try:
        _save_pending(
            approval_id,
            {
                "site": site,
                "draft": draft,
                "post_id": None,
                "post_url": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        bot = telegram.Bot(token=settings.telegram_bot_token)
        await bot.send_message(
            chat_id=settings.telegram_admin_chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return approval_id
    except Exception as exc:  # noqa: BLE001
        logger.warning("승인 요청 발송 실패: %s", exc)
        return None


def send_approval_request_sync(site: str, draft: Dict[str, Any]) -> Optional[str]:
    """동기 컨텍스트(main.py의 schedule 루프 등)에서 바로 호출하는 래퍼.

    send_approval_request가 더 이상 데몬의 공유 이벤트 루프(_LOOP)를 필요로
    하지 않으므로, submit_coroutine 없이 자체 이벤트 루프로 바로 실행하면 된다
    (daemon의 봇 폴링 루프는 별도 스레드에서 돌기 때문에 충돌하지 않는다).
    """
    try:
        return asyncio.run(send_approval_request(site, draft))
    except Exception as exc:  # noqa: BLE001
        logger.warning("승인 요청 발송 실패(sync): %s", exc)
        return None


# 실제 발행은 승인/자동발행 시점에 완전히 별도의 OS 프로세스로 실행한다
# (_spawn_stage) - 텔레그램 콜백 핸들러(또는 30분 자동발행 점검 루프)를 WP
# API 호출/이미지 처리/배포 네트워크 요청으로 블로킹하지 않기 위해서다.
# 영상 렌더링을 뺀 뒤로는 무거운 단계가 없어져 굳이 여러 단계로 나눌 필요가
# 없으므로, WP 발행부터 나머지 채널 배포까지 한 단계(_publish_stage)로 처리한다.


async def _publish_stage(approval_id: str) -> None:
    """워드프레스 발행 + 썸네일 생성 + 나머지 채널(색인핑/스레드/핀터레스트) 배포."""
    import telegram

    pending = _load_pending(approval_id)
    if pending is None:
        logger.warning("승인 대기(%s)를 찾을 수 없어 발행을 중단합니다.", approval_id)
        return

    site = pending["site"]
    draft = pending["draft"]
    bot = telegram.Bot(token=settings.telegram_bot_token)

    wp = WordPressClient(site)
    html = draft.get("html_content", "")
    draft_post = wp.create_draft_post(draft.get("title", ""), html)
    if draft_post is None:
        await bot.send_message(
            chat_id=settings.telegram_admin_chat_id,
            text="❌ 워드프레스 초안 생성 실패로 발행이 중단되었습니다.",
        )
        _delete_pending(approval_id)
        return

    post_id = draft_post.get("id", 0)
    html = process_image_slots(html, draft.get("image_prompts", {}), wp, post_id)
    html = inject_affiliate_slots(html, post_id, site, draft.get("keyword", ""))

    published = wp.update_post(post_id, content=html, status="publish")
    if published is None:
        await bot.send_message(
            chat_id=settings.telegram_admin_chat_id,
            text="❌ 워드프레스 발행 실패로 중단되었습니다.",
        )
        _delete_pending(approval_id)
        return

    post_url = published.get("link", "")
    pending["post_id"] = post_id
    pending["post_url"] = post_url
    _save_pending(approval_id, pending)

    workdir = OUTPUT_DIR / f"post_{post_id}"
    workdir.mkdir(parents=True, exist_ok=True)
    thumbnail_path = build_card_news_thumbnail(
        draft.get("title", ""), draft.get("fact_summary", ""), workdir / "thumbnail.png"
    )

    distribution = distribute_all(
        site=site,
        post_url=post_url,
        thumbnail_path=thumbnail_path,
        captions={
            "title": draft.get("title", ""),
            "fact_summary": draft.get("fact_summary", ""),
            "threads_post": draft.get("threads_post", ""),
            "threads_comment": draft.get("threads_comment", ""),
            "pinterest_desc": draft.get("pinterest_desc", ""),
        },
        post_id=post_id,
    )
    results = {"wordpress": {"status": "ok", "post_id": post_id, "url": post_url}, **distribution}

    await bot.send_message(
        chat_id=settings.telegram_admin_chat_id, text=_format_result_report(site, results)
    )
    _delete_pending(approval_id)


def run_publish_stage_sync(approval_id: str) -> None:
    try:
        asyncio.run(_publish_stage(approval_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("발행 실패(%s): %s", approval_id, exc)
        try:
            import telegram

            async def _notify_failure() -> None:
                bot = telegram.Bot(token=settings.telegram_bot_token)
                await bot.send_message(
                    chat_id=settings.telegram_admin_chat_id,
                    text=f"❌ 발행/배포 단계에서 오류가 발생했습니다: {exc}",
                )

            asyncio.run(_notify_failure())
        except Exception:  # noqa: BLE001
            pass
        _delete_pending(approval_id)


def _format_result_report(site: str, results: Dict[str, Any]) -> str:
    badge = SITE_BADGES.get(site, site)
    lines = [f"{badge} 발행 결과 보고"]
    for channel, result in results.items():
        status = result.get("status", "unknown") if isinstance(result, dict) else str(result)
        icon = {"ok": "✅", "skipped": "⏭️", "error": "❌"}.get(status, "❔")
        lines.append(f"{icon} {channel}: {status}")

    if results.get("youtube_comment", {}).get("status") == "ok":
        video_id = results.get("youtube", {}).get("video_id", "")
        lines.append(
            "\n📌 유튜브 댓글에 링크를 자동으로 남겼습니다. YouTube API는 댓글 고정을 "
            "지원하지 않아 이 부분만 직접 눌러주세요.\n"
            f"https://youtube.com/watch?v={video_id}"
        )
    return "\n".join(lines)


async def handle_callback(update, context) -> None:  # noqa: ANN001
    query = update.callback_query
    await query.answer()

    action, _, approval_id = query.data.partition(":")
    pending = _load_pending(approval_id)
    if pending is None:
        await query.edit_message_text("⚠️ 이미 처리되었거나 만료된 요청입니다.")
        return

    site = pending["site"]
    draft = pending["draft"]

    if action == "reject":
        await query.edit_message_text(f"❌ 반려되었습니다: {draft.get('title', '')}")
        _delete_pending(approval_id)
        return

    if action == "preview":
        await query.message.reply_text(
            f"🌐 미리보기는 워드프레스 초안 저장 후 대시보드에서 확인할 수 있습니다.\n"
            f"제목: {draft.get('title', '')}"
        )
        return

    if action == "edit":
        await query.message.reply_text(
            "✏️ 워드프레스 관리자 페이지에서 초안을 직접 수정한 뒤 다시 승인해주세요."
        )
        return

    if action == "approve":
        await query.edit_message_text(
            f"⏳ 발행을 시작합니다: {draft.get('title', '')}\n"
            "(WP 발행 -> 색인핑/스레드/핀터레스트 배포 순서로 진행합니다)"
        )
        _spawn_stage("publish", approval_id)


async def _auto_publish_expired(approval_id: str, pending: Dict[str, Any]) -> None:
    """AUTO_PUBLISH_TIMEOUT_HOURS 동안 응답이 없어 자동으로 발행한다 (approve 버튼과 동일한 파이프라인)."""
    import telegram

    draft = pending["draft"]
    bot = telegram.Bot(token=settings.telegram_bot_token)

    await bot.send_message(
        chat_id=settings.telegram_admin_chat_id,
        text=(
            f"⏰ {settings.auto_publish_timeout_hours:g}시간 동안 응답이 없어 "
            f"자동으로 발행합니다: {draft.get('title', '')}"
        ),
    )
    _spawn_stage("publish", approval_id)


async def check_expired_approvals_and_auto_publish() -> None:
    """대기 중인 승인 요청 중 제한 시간(AUTO_PUBLISH_TIMEOUT_HOURS)을 넘긴 건을 자동 발행한다.

    main.py의 schedule 루프가 주기적으로 호출한다. handle_callback의 버튼 처리와
    마찬가지로 daemon 프로세스가 폴링 중일 때만(=이 함수가 호출될 때만) 동작한다.
    """
    if not _is_configured() or not _PENDING_DIR.exists():
        return

    timeout = timedelta(hours=settings.auto_publish_timeout_hours)
    now = datetime.now(timezone.utc)

    for path in sorted(_PENDING_DIR.glob("*.json")):
        approval_id = path.stem
        pending = _load_pending(approval_id)
        if pending is None:
            continue

        if pending.get("post_id"):
            # 이미 워드프레스 발행 단계까지 끝난 건이다(자동발행이든 수동승인이든).
            # 이후 쇼츠/롱폼 단계가 오래 걸리거나(렌더링 실패 등) 완전히 멈춰서
            # 대기 기록이 삭제되지 않고 남아있더라도, 여기서 다시 워드프레스
            # 발행을 재실행하면 안 된다 - 그러면 같은 글이 30분마다 계속
            # 중복 발행된다(실제로 발생했던 사고: 렌더링이 안 끝나 대기 기록이
            # 안 지워지고, 그때마다 이 체크가 새 글을 계속 만들어 냄).
            continue

        created_at_raw = pending.get("created_at")
        if not created_at_raw:
            continue  # 이 필드 도입 이전에 저장된 예전 대기건은 자동발행 대상에서 제외

        try:
            created_at = datetime.fromisoformat(created_at_raw)
        except ValueError:
            continue

        if now - created_at >= timeout:
            logger.info(
                "승인 대기(%s)가 %s시간을 넘겨 자동 발행을 시작합니다.",
                approval_id,
                settings.auto_publish_timeout_hours,
            )
            await _auto_publish_expired(approval_id, pending)


def check_expired_approvals_and_auto_publish_sync() -> None:
    """동기 컨텍스트(main.py의 schedule 루프)에서 호출하는 래퍼."""
    if not _is_configured():
        return
    try:
        asyncio.run(check_expired_approvals_and_auto_publish())
    except Exception as exc:  # noqa: BLE001
        logger.warning("자동 발행 점검 실패: %s", exc)


def build_application():
    """텔레그램 Application을 생성한다. 토큰 미설정 시 None."""
    if not _is_configured():
        logger.warning("TELEGRAM_BOT_TOKEN/ADMIN_CHAT_ID 미설정 - 텔레그램 봇을 시작하지 않습니다.")
        return None

    from telegram.ext import Application, CallbackQueryHandler

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.add_handler(CallbackQueryHandler(handle_callback))
    return application


def _run_bot_loop() -> None:
    global _LOOP, _APPLICATION

    _LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(_LOOP)

    _APPLICATION = build_application()
    if _APPLICATION is None:
        return

    # stop_signals=None: 시그널 핸들러를 등록하지 않음 -> 메인 스레드가 아닌
    # 별도 스레드에서 안전하게 polling을 실행할 수 있게 함.
    _APPLICATION.run_polling(stop_signals=None, close_loop=False)


def start_bot_in_thread() -> Optional[threading.Thread]:
    """텔레그램 봇을 전용 스레드+이벤트 루프에서 시작한다. 미설정 시 None 반환."""
    global _BOT_THREAD

    if not _is_configured():
        logger.warning("텔레그램 미설정 - 봇 스레드를 시작하지 않습니다.")
        return None

    _BOT_THREAD = threading.Thread(target=_run_bot_loop, name="telegram-bot", daemon=True)
    _BOT_THREAD.start()
    return _BOT_THREAD


def submit_coroutine(coro):  # noqa: ANN001, ANN201
    """다른 스레드(예: schedule 루프)에서 봇의 이벤트 루프로 코루틴을 안전하게 제출한다."""
    if _LOOP is None:
        logger.warning("텔레그램 봇 이벤트 루프가 아직 시작되지 않았습니다.")
        return None
    return asyncio.run_coroutine_threadsafe(coro, _LOOP)


def stop_bot() -> None:
    global _APPLICATION
    if _APPLICATION is not None and _LOOP is not None:
        try:
            asyncio.run_coroutine_threadsafe(_APPLICATION.stop(), _LOOP)
        except Exception as exc:  # noqa: BLE001
            logger.warning("텔레그램 봇 종료 중 오류: %s", exc)
