"""
이메일 수집 API & 주간 AI 뉴스레터 자동 작성/발송 모듈.

- SQLite(subscribers.db)로 구독자 관리.
- Flask API(포트 5000) `/api/subscribe` 엔드포인트: 등록 즉시 Resend로
  '2026 가이드북 PDF 링크' 웰컴 메일 발송.
- build_and_send_weekly_newsletter(): 최근 7일간 발행 글을 바탕으로 Claude가
  주간 브리핑 HTML을 작성해 구독자 전원에게 Resend로 일괄 발송.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, jsonify, request
from flask_cors import CORS

from config import DATA_DIR, settings
from generator import CLAUDE_MODEL, GeneratorNotConfiguredError, _get_client
from utils.logger import get_logger
from wp_client import WordPressClient

logger = get_logger(__name__)

DB_PATH = DATA_DIR / "subscribers.db"
GUIDEBOOK_PDF_URL = "https://your-domain.com/downloads/2026-guidebook.pdf"


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------
def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                site TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def add_subscriber(email: str, site: str = "") -> bool:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return False

    init_db()
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO subscribers (email, site, created_at) VALUES (?, ?, ?)",
                (email, site, datetime.utcnow().isoformat()),
            )
            conn.commit()
        return True
    except sqlite3.Error as exc:
        logger.warning("구독자 저장 실패: %s", exc)
        return False


def list_subscribers() -> List[str]:
    init_db()
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            cursor = conn.execute("SELECT email FROM subscribers")
            return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as exc:
        logger.warning("구독자 목록 조회 실패: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Resend 이메일 발송
# ---------------------------------------------------------------------------
def send_welcome_email(email: str) -> bool:
    if not settings.resend_api_key:
        logger.info("RESEND_API_KEY 미설정 - 웰컴 메일 발송을 건너뜁니다 (구독은 저장됨).")
        return False

    try:
        import resend

        resend.api_key = settings.resend_api_key
        resend.Emails.send(
            {
                "from": settings.sender_email,
                "to": [email],
                "subject": "🎁 가입 완료! 2026 가이드북을 확인하세요",
                "html": f"""
                <div style="font-family:sans-serif;max-width:520px;margin:0 auto;">
                  <h2>구독해주셔서 감사합니다!</h2>
                  <p>아래 버튼을 눌러 2026 가이드북 PDF를 받아보세요.</p>
                  <a href="{GUIDEBOOK_PDF_URL}"
                     style="display:inline-block;padding:14px 28px;background:#4f7cff;
                     color:#fff;border-radius:8px;text-decoration:none;font-weight:700;">
                     📄 2026 가이드북 다운로드</a>
                </div>
                """,
            }
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("웰컴 메일 발송 실패: %s", exc)
        return False


def send_newsletter_to_all(html: str) -> Dict[str, Any]:
    subscribers = list_subscribers()
    if not subscribers:
        return {"status": "skipped", "reason": "no_subscribers"}

    if not settings.resend_api_key:
        logger.info("RESEND_API_KEY 미설정 - 뉴스레터 발송을 건너뜁니다.")
        return {"status": "skipped", "reason": "not_configured"}

    sent, failed = 0, 0
    try:
        import resend

        resend.api_key = settings.resend_api_key
        for email in subscribers:
            try:
                resend.Emails.send(
                    {
                        "from": settings.sender_email,
                        "to": [email],
                        "subject": "📬 이번 주 놓치면 안 되는 정보 정리",
                        "html": html,
                    }
                )
                sent += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("뉴스레터 발송 실패 (%s): %s", email, exc)
                failed += 1
        return {"status": "ok", "sent": sent, "failed": failed, "total": len(subscribers)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("뉴스레터 일괄 발송 중 오류: %s", exc)
        return {"status": "error", "reason": str(exc)}


# ---------------------------------------------------------------------------
# 주간 뉴스레터 콘텐츠 생성
# ---------------------------------------------------------------------------
def build_weekly_newsletter_html(days: int = 7) -> str:
    all_posts: List[Dict[str, Any]] = []
    for site_key in ("A", "B", "C"):
        wp = WordPressClient(site_key)
        posts = wp.get_recent_posts(days=days)
        all_posts.extend(posts)

    if not all_posts:
        logger.info("최근 %d일간 발행된 글이 없어 기본 뉴스레터 템플릿을 사용합니다.", days)
        titles_block = "이번 주는 새로운 업데이트가 없었습니다."
    else:
        titles_block = "\n".join(
            f"- {p.get('title', {}).get('rendered', '') if isinstance(p.get('title'), dict) else p.get('title', '')}"
            for p in all_posts[:15]
        )

    client = _get_client()
    if client is None:
        logger.info("ANTHROPIC_API_KEY 미설정 - 기본 템플릿으로 뉴스레터를 생성합니다.")
        return _fallback_newsletter_html(titles_block)

    try:
        prompt = f"""아래는 이번 주 발행된 글 제목 목록입니다:
{titles_block}

이 목록을 바탕으로 구독자에게 보낼 주간 브리핑 이메일 HTML을 작성하세요.
친근한 어투로 핵심 소식 3~5개를 요약하고, 각 항목에 궁금증을 유발하는 한줄 후킹 문구를 붙이세요.
인라인 CSS만 사용하고, 완성된 HTML 문자열만 출력하세요 (설명 없이)."""
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            logger.info(
                "Claude 뉴스레터 생성 호출 완료 - 입력 %s 토큰 / 출력 %s 토큰",
                usage.input_tokens,
                usage.output_tokens,
            )
        html = "".join(block.text for block in response.content if hasattr(block, "text"))
        return html.strip() or _fallback_newsletter_html(titles_block)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Claude 뉴스레터 생성 실패, 기본 템플릿 사용: %s", exc)
        return _fallback_newsletter_html(titles_block)


def _fallback_newsletter_html(titles_block: str) -> str:
    template_path = Path(__file__).resolve().parent / "templates" / "newsletter_email.html"
    if template_path.exists():
        return template_path.read_text(encoding="utf-8").replace("{{TITLES_BLOCK}}", titles_block)
    return f"<div><h2>이번 주 소식</h2><pre>{titles_block}</pre></div>"


def build_and_send_weekly_newsletter() -> Dict[str, Any]:
    html = build_weekly_newsletter_html()
    return send_newsletter_to_all(html)


# ---------------------------------------------------------------------------
# Flask API
# ---------------------------------------------------------------------------
def create_flask_app() -> Flask:
    """`.run()`을 호출하지 않는 순수 Flask 앱 팩토리 - main.py가 스레드에서 구동한다."""
    app = Flask(__name__)
    CORS(app)
    init_db()

    @app.route("/api/subscribe", methods=["POST"])
    def subscribe():  # noqa: ANN202
        payload = request.get_json(silent=True) or {}
        email = payload.get("email", "")
        site = payload.get("site", "")

        if not email or "@" not in email:
            return jsonify({"ok": False, "error": "유효한 이메일이 아닙니다."}), 400

        saved = add_subscriber(email, site)
        if not saved:
            return jsonify({"ok": False, "error": "이미 등록되었거나 저장에 실패했습니다."}), 400

        send_welcome_email(email)
        return jsonify({"ok": True, "message": "구독이 완료되었습니다. 메일함을 확인해주세요."})

    @app.route("/api/health", methods=["GET"])
    def health():  # noqa: ANN202
        return jsonify({"ok": True, "service": "newsletter_system"})

    return app


def run_flask_server(host: str = "0.0.0.0", port: int = 5000) -> None:
    app = create_flask_app()
    # use_reloader=False 필수: 리로더가 프로세스를 재실행하면 main.py가 띄운
    # 스케줄러/텔레그램봇 스레드가 중복 생성된다.
    app.run(host=host, port=port, debug=False, use_reloader=False)
