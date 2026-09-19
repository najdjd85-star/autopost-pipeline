"""
통합 스케줄러 & CLI 엔트리포인트.

CLI:
    python main.py run-now [site_a|site_b|site_c|all]
    python main.py preview [site_a|site_b|site_c]   # 어디에도 등록/발행하지 않고 로컬 미리보기만 생성
    python main.py refresh-check
    python main.py send-newsletter
    python main.py daemon          # 스케줄러+텔레그램봇+Flask 구독서버 상시 구동

스케줄:
    매일 07:00        -> 사이트별 콘텐츠 생성 + 텔레그램 승인 요청 파이프라인
    매주 월요일 08:00  -> 주간 뉴스레터 발송
    매주 일요일 23:00  -> 서치콘솔 순위 방어 점검
    30분마다          -> 자동발행 점검 (AUTO_PUBLISH_TIMEOUT_HOURS 초과 대기건 자동 발행)

영상(쇼츠/롱폼) 렌더링은 지원하지 않는다 - 워드프레스 발행 + 색인핑/스레드/
핀터레스트 배포만 수행한다(유튜브/인스타그램 릴스는 영상이 필요해 제외).
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import webbrowser
from datetime import datetime
from typing import Any, Dict, List

import schedule

import telegram_bot
from config import OUTPUT_DIR, settings, validate_config
from constants import SITE_BADGES, SITE_CLI_ALIASES, SITE_KEYS
from content_updater import run_rank_check
from generator import GeneratorNotConfiguredError, generate_post
from image_hybrid_engine import process_image_slots
from newsletter_system import build_and_send_weekly_newsletter, run_flask_server
from smart_affiliate_matcher import inject_affiliate_slots
from utils.logger import get_logger
from utils.telegram_notify import send_message_sync
from wp_client import WordPressClient

logger = get_logger(__name__)


def _resolve_sites(site_arg: str) -> List[str]:
    site_arg = site_arg.lower()
    if site_arg == "all":
        return list(SITE_KEYS)
    if site_arg in SITE_CLI_ALIASES:
        return [SITE_CLI_ALIASES[site_arg]]
    if site_arg.upper() in SITE_KEYS:
        return [site_arg.upper()]
    raise ValueError(f"알 수 없는 site 인자: {site_arg!r} (site_a/site_b/site_c/all 중 하나)")


def _run_site_pipeline(site: str) -> None:
    logger.info("[Site %s] 콘텐츠 생성 파이프라인 시작", site)
    try:
        draft = generate_post(site)
    except GeneratorNotConfiguredError as exc:
        logger.warning("[Site %s] 콘텐츠 생성 불가: %s", site, exc)
        send_message_sync(f"⚠️ [Site {site}] ANTHROPIC_API_KEY 미설정으로 콘텐츠 생성을 건너뜁니다.")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("[Site %s] 콘텐츠 생성 중 예기치 못한 오류: %s", site, exc)
        send_message_sync(f"❌ [Site {site}] 콘텐츠 생성 중 오류: {exc}")
        return

    logger.info("[Site %s] 콘텐츠 생성 완료: %s", site, draft.get("title"))

    approval_id = telegram_bot.send_approval_request_sync(site, draft)
    if approval_id is None:
        logger.warning("[Site %s] 텔레그램 승인 요청을 보내지 못했습니다 (설정을 확인하세요).", site)
    else:
        logger.info(
            "[Site %s] 텔레그램 승인 요청 발송 완료 (approval_id=%s). 승인 버튼 클릭은 "
            "데몬(daemon)이 폴링 중이어야 처리됩니다.",
            site,
            approval_id,
        )


def cmd_run_now(site_arg: str) -> None:
    for site in _resolve_sites(site_arg):
        _run_site_pipeline(site)


def _build_preview_document(site: str, draft: Dict[str, Any], rendered_html: str) -> str:
    """워드프레스/SNS 어디에도 발행하지 않는 순수 로컬 미리보기 HTML 문서를 만든다."""
    badge = SITE_BADGES.get(site, site)

    def esc(text: str) -> str:
        return (text or "").replace("<", "&lt;").replace(">", "&gt;")

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>[미리보기] {esc(draft.get('title',''))}</title>
<style>
  body{{font-family:'Malgun Gothic',sans-serif;max-width:820px;margin:0 auto;padding:24px;
       background:#f4f6fb;color:#1b2036;}}
  .banner{{background:#fff3cd;border:1px solid #ffe08a;color:#7a5b00;padding:12px 16px;
       border-radius:8px;margin-bottom:20px;font-size:14px;line-height:1.6;}}
  .post{{background:#fff;border-radius:12px;padding:28px;box-shadow:0 1px 3px rgba(0,0,0,.08);}}
  .badge{{display:inline-block;background:#24406b;color:#fff;font-size:12px;font-weight:700;
       padding:4px 10px;border-radius:999px;margin-bottom:10px;}}
  details{{margin-top:22px;background:#fff;border-radius:12px;padding:16px 20px;
       box-shadow:0 1px 3px rgba(0,0,0,.08);}}
  summary{{font-weight:700;cursor:pointer;}}
  .field{{margin:14px 0;}}
  .field b{{display:block;color:#555;font-size:12px;margin-bottom:4px;}}
  .field div, .field ul{{background:#f7f8fc;border-radius:8px;padding:10px 12px;font-size:14px;
       white-space:pre-wrap;}}
</style></head>
<body>
  <div class="banner">⚠️ 이 페이지는 로컬 미리보기입니다. 워드프레스·스레드·핀터레스트
  어디에도 등록/발행되지 않았습니다. 실제로 발행하려면 GUI/텔레그램에서 승인 절차를 거쳐야 합니다.</div>
  <div class="post">
    <span class="badge">{badge}</span>
    {rendered_html}
  </div>
  <details>
    <summary>다른 채널용 콘텐츠 (스레드 / 핀터레스트)</summary>
    <div class="field"><b>스레드 본문 (threads_post)</b><div>{esc(draft.get('threads_post',''))}</div></div>
    <div class="field"><b>스레드 첫 댓글 (threads_comment)</b><div>{esc(draft.get('threads_comment',''))}</div></div>
    <div class="field"><b>핀터레스트 설명 (pinterest_desc)</b><div>{esc(draft.get('pinterest_desc',''))}</div></div>
  </details>
</body></html>"""


def _preview_site(site: str) -> None:
    """콘텐츠를 생성하되 워드프레스/SNS 어디에도 등록하지 않고 로컬 파일로만 저장한다."""
    logger.info("[Site %s] 미리보기 전용 콘텐츠 생성 시작 (발행하지 않음)", site)
    try:
        draft = generate_post(site)
    except GeneratorNotConfiguredError as exc:
        logger.warning("[Site %s] 미리보기 생성 불가: %s", site, exc)
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("[Site %s] 미리보기 생성 중 예기치 못한 오류: %s", site, exc)
        return

    # 이미지/제휴 슬롯도 실제 로직 그대로 처리한다 - 단, WordPressClient는
    # 미디어 업로드에만 쓰이고 create_draft_post/publish_post는 절대 호출하지
    # 않으므로 워드프레스에는 아무것도 등록되지 않는다.
    wp = WordPressClient(site)
    html = draft.get("html_content", "")
    html = process_image_slots(html, draft.get("image_prompts", {}), wp, post_id=0)
    html = inject_affiliate_slots(html, post_id=0, site=site, keyword=draft.get("keyword", ""))

    preview_dir = OUTPUT_DIR / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = preview_dir / f"{site}_{ts}.json"
    html_path = preview_dir / f"{site}_{ts}.html"

    json_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_build_preview_document(site, draft, html), encoding="utf-8")

    logger.info("[Site %s] 미리보기 저장 완료 (미발행): %s", site, html_path)
    try:
        webbrowser.open(html_path.as_uri())
    except Exception as exc:  # noqa: BLE001
        logger.info("브라우저 자동 열기 실패 - 파일을 직접 열어주세요: %s (%s)", html_path, exc)


def cmd_preview(site_arg: str) -> None:
    for site in _resolve_sites(site_arg):
        _preview_site(site)


def cmd_test_approval(site_arg: str) -> None:
    """Claude를 호출하지 않고, 더미 내용으로 텔레그램 승인 카드+쇼츠 영상만 테스트 발송한다."""
    for site in _resolve_sites(site_arg):
        ok = telegram_bot.send_test_approval_card(site)
        if ok:
            logger.info("[Site %s] 테스트 승인 카드 발송 완료 - 텔레그램을 확인하세요.", site)
        else:
            logger.warning("[Site %s] 테스트 승인 카드 발송 실패 (TELEGRAM_BOT_TOKEN/ADMIN_CHAT_ID 확인).", site)


def cmd_publish(approval_id: str) -> None:
    """실제 발행(WP + 나머지 채널 배포). 승인/자동발행 시 자동으로 호출된다."""
    telegram_bot.run_publish_stage_sync(approval_id)


def cmd_refresh_check() -> None:
    for site in SITE_KEYS:
        try:
            run_rank_check(site)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Site %s] 순위 방어 점검 중 오류: %s", site, exc)


def cmd_send_newsletter() -> None:
    result = build_and_send_weekly_newsletter()
    logger.info("뉴스레터 발송 결과: %s", result)


def daily_pipeline_job() -> None:
    logger.info("=== 일일 포스팅 파이프라인 시작 (스케줄) ===")
    cmd_run_now("all")


def weekly_newsletter_job() -> None:
    logger.info("=== 주간 뉴스레터 발송 시작 (스케줄) ===")
    cmd_send_newsletter()


def sunday_rankcheck_job() -> None:
    logger.info("=== 일요일 순위 방어 점검 시작 (스케줄) ===")
    cmd_refresh_check()


def auto_publish_check_job() -> None:
    telegram_bot.check_expired_approvals_and_auto_publish_sync()


def _register_schedule_jobs() -> None:
    schedule.every().day.at(settings.schedule_time).do(daily_pipeline_job)
    schedule.every(30).minutes.do(auto_publish_check_job)

    # NEWSLETTER_SCHEDULE_TIME 예: "Monday 08:00"
    try:
        day_str, time_str = settings.newsletter_schedule_time.split(" ", 1)
        getattr(schedule.every(), day_str.lower()).at(time_str).do(weekly_newsletter_job)
    except (ValueError, AttributeError):
        logger.warning(
            "NEWSLETTER_SCHEDULE_TIME(%s) 형식이 올바르지 않아 기본값(월 08:00)을 사용합니다.",
            settings.newsletter_schedule_time,
        )
        schedule.every().monday.at("08:00").do(weekly_newsletter_job)

    schedule.every().sunday.at("23:00").do(sunday_rankcheck_job)


def start_scheduler_loop() -> None:
    _register_schedule_jobs()
    logger.info(
        "스케줄러 시작 - 매일 %s 포스팅 / %s 뉴스레터 / 매주 일요일 23:00 순위점검 / "
        "30분마다 자동발행 점검(%s시간 초과 대기건)",
        settings.schedule_time,
        settings.newsletter_schedule_time,
        settings.auto_publish_timeout_hours,
    )
    while True:
        schedule.run_pending()
        time.sleep(30)


def cmd_daemon() -> None:
    threading.Thread(target=run_flask_server, name="flask-subscribe", daemon=True).start()
    logger.info("Flask 구독 서버 스레드 시작 (포트 5000)")

    bot_thread = telegram_bot.start_bot_in_thread()
    if bot_thread is None:
        logger.warning("텔레그램 봇이 시작되지 않았습니다 (토큰 미설정). 승인 알림 없이 계속 진행합니다.")

    try:
        start_scheduler_loop()
    except KeyboardInterrupt:
        logger.info("종료 신호 수신 - 데몬을 종료합니다.")
        telegram_bot.stop_bot()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="3사이트 통합 패시브 미디어 파이프라인 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_now = subparsers.add_parser("run-now", help="즉시 콘텐츠 생성 파이프라인 실행")
    run_now.add_argument("site", choices=["site_a", "site_b", "site_c", "all"])

    preview = subparsers.add_parser(
        "preview", help="어디에도 등록/발행하지 않고 로컬 미리보기 파일만 생성"
    )
    preview.add_argument("site", choices=["site_a", "site_b", "site_c", "all"])

    test_approval = subparsers.add_parser(
        "test-approval", help="Claude 호출 없이 더미 내용으로 텔레그램 승인 카드만 테스트 발송"
    )
    test_approval.add_argument("site", choices=["site_a", "site_b", "site_c", "all"])

    subparsers.add_parser("refresh-check", help="서치콘솔 순위 방어 점검 즉시 실행")
    subparsers.add_parser("send-newsletter", help="주간 뉴스레터 즉시 발송")
    subparsers.add_parser("daemon", help="스케줄러+텔레그램봇+구독서버 상시 구동")

    # telegram_bot.py가 승인 콜백/자동발행 시점에 별도 프로세스로 띄울 때
    # 내부적으로 사용하는 커맨드다 - 직접 실행할 일은 거의 없다.
    publish = subparsers.add_parser(
        "publish", help="[내부용] 워드프레스 발행 + 나머지 채널(색인핑/스레드/핀터레스트) 배포"
    )
    publish.add_argument("approval_id")

    return parser


def main() -> None:
    report = validate_config()
    if report["missing_required"]:
        logger.warning(
            "필수 설정이 누락되었습니다: %s (콘텐츠 생성 등 관련 기능은 호출 시 실패합니다)",
            report["missing_required"],
        )

    parser = build_arg_parser()
    args = parser.parse_args()

    if args.command == "run-now":
        cmd_run_now(args.site)
    elif args.command == "preview":
        cmd_preview(args.site)
    elif args.command == "test-approval":
        cmd_test_approval(args.site)
    elif args.command == "refresh-check":
        cmd_refresh_check()
    elif args.command == "send-newsletter":
        cmd_send_newsletter()
    elif args.command == "daemon":
        cmd_daemon()
    elif args.command == "publish":
        cmd_publish(args.approval_id)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
