"""
소셜 4종(Pinterest/Instagram/Threads/YouTube) 동시 배포 및 색인 핑 모듈.

각 publish_*/ping_* 함수는 실패해도 예외를 던지지 않고 표준화된
{"status": "ok"|"skipped"|"error", ...} dict를 반환한다 - 하나의 죽은 토큰이
나머지 채널 배포를 막지 않도록 하기 위함이다.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image, ImageDraw, ImageFont

from config import settings
from constants import FTC_DISCLOSURE_TEXT, THUMBNAIL_SIZE
from smart_affiliate_matcher import get_primary_affiliate_link
from utils.http import safe_get, safe_post
from utils.logger import get_logger

logger = get_logger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"
# 2026년 기준 "Instagram API with Instagram Login"(페이스북 페이지 연결 불필요) 전용 호스트.
# 이 방식으로 발급된 IGAA... 토큰은 graph.facebook.com이 아니라 이 호스트에서만 동작한다.
INSTAGRAM_API_BASE = "https://graph.instagram.com/v25.0"
THREADS_API_BASE = "https://graph.threads.net/v1.0"
PINTEREST_API_BASE = "https://api.pinterest.com/v5"
GOOGLE_INDEXING_API = "https://indexing.googleapis.com/v3/urlNotifications:publish"
NAVER_PING_URL = "https://searchadvisor.naver.com/indexnow"
# youtube.upload는 영상 업로드만 가능하고 댓글 작성 권한이 없다. force-ssl은 영상
# 업로드까지 포함하는 상위 스코프라 이걸로 통일하면 댓글 자동 작성도 같은 토큰으로
# 가능해진다. 단, 이미 youtube.upload만으로 발급된 기존 토큰은 이 상위 권한이
# 없으므로 scripts/generate_youtube_token.py로 재동의(재발급)를 받아야 한다.
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]


# ---------------------------------------------------------------------------
# 카드뉴스 썸네일
# ---------------------------------------------------------------------------
def build_card_news_thumbnail(title: str, summary: str, output_path: Path) -> Path:
    """Pillow로 1000x1500 다크 테마 카드뉴스 썸네일을 생성한다."""
    width, height = THUMBNAIL_SIZE
    img = Image.new("RGB", (width, height), color=(18, 20, 28))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("malgun.ttf", 64)
        body_font = ImageFont.truetype("malgun.ttf", 34)
    except OSError:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    # 상단 그라데이션 느낌의 액센트 바
    draw.rectangle([(0, 0), (width, 24)], fill=(79, 124, 255))

    margin = 70
    draw.text((margin, 220), _wrap_text(title, 14), font=title_font, fill=(255, 255, 255))
    draw.text((margin, 620), _wrap_text(summary, 22), font=body_font, fill=(200, 205, 220))

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def _wrap_text(text: str, max_chars: int) -> str:
    words = (text or "").split()
    lines, current = [], ""
    for w in words:
        if len(current) + len(w) + 1 > max_chars:
            lines.append(current)
            current = w
        else:
            current = f"{current} {w}".strip()
    if current:
        lines.append(current)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pinterest
# ---------------------------------------------------------------------------
def publish_pinterest_pin(
    image_path: Path, title: str, description: str, link: str
) -> Dict[str, Any]:
    if not (settings.pinterest_access_token and settings.pinterest_board_id):
        logger.info("Pinterest 토큰/보드 미설정 - 핀 등록을 건너뜁니다.")
        return {"status": "skipped", "reason": "not_configured"}

    try:
        import base64

        image_path = Path(image_path)
        if not image_path.exists():
            return {"status": "error", "reason": "image_not_found"}

        image_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        payload = {
            "board_id": settings.pinterest_board_id,
            "title": title[:100],
            "description": description[:500],
            "link": link,
            "media_source": {
                "source_type": "image_base64",
                "content_type": "image/png",
                "data": image_b64,
            },
        }
        resp = safe_post(
            f"{PINTEREST_API_BASE}/pins",
            headers={
                "Authorization": f"Bearer {settings.pinterest_access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload),
            timeout=30,
        )
        if resp is None or resp.status_code not in (200, 201):
            return {"status": "error", "reason": f"http_{getattr(resp, 'status_code', 'none')}"}
        return {"status": "ok", "response": resp.json()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Pinterest 핀 등록 실패: %s", exc)
        return {"status": "error", "reason": str(exc)}


# ---------------------------------------------------------------------------
# Instagram Reels (Meta Graph API)
# ---------------------------------------------------------------------------
def publish_instagram_reel(
    video_url: str, caption: str, max_wait_seconds: int = 120
) -> Dict[str, Any]:
    """Instagram API(Instagram Login 방식, graph.instagram.com)로 릴스를 업로드한다.

    video_url은 공개적으로 접근 가능한 URL이어야 한다 (API 제약).
    공식 플로우: 1) 컨테이너 생성(media_type=REELS) 2) status_code가 FINISHED가
    될 때까지 폴링 3) media_publish. 2단계를 건너뛰고 바로 발행하면 인스타그램이
    아직 영상 처리 중이라 실패하는 경우가 많다.
    """
    if not (settings.ig_access_token and settings.ig_user_id):
        logger.info("IG 토큰/유저ID 미설정 - 릴스 업로드를 건너뜁니다.")
        return {"status": "skipped", "reason": "not_configured"}

    try:
        create_resp = safe_post(
            f"{INSTAGRAM_API_BASE}/{settings.ig_user_id}/media",
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "access_token": settings.ig_access_token,
            },
            timeout=30,
        )
        if create_resp is None or create_resp.status_code != 200:
            status = getattr(create_resp, "status_code", "no_response")
            body = getattr(create_resp, "text", "")[:300] if create_resp is not None else ""
            logger.warning("인스타그램 릴스 컨테이너 생성 실패 (status=%s): %s", status, body)
            return {"status": "error", "reason": "media_create_failed"}
        container_id = create_resp.json().get("id")

        # 컨테이너가 FINISHED 상태가 될 때까지 폴링 (영상 처리 시간 필요).
        waited = 0
        poll_interval = 5
        while waited < max_wait_seconds:
            status_resp = safe_get(
                f"{INSTAGRAM_API_BASE}/{container_id}",
                params={"fields": "status_code", "access_token": settings.ig_access_token},
                timeout=15,
            )
            status_code = (
                status_resp.json().get("status_code") if status_resp is not None and status_resp.status_code == 200 else None
            )
            if status_code == "FINISHED":
                break
            if status_code in ("ERROR", "EXPIRED"):
                logger.warning("인스타그램 릴스 컨테이너 처리 실패: status_code=%s", status_code)
                return {"status": "error", "reason": f"container_{status_code.lower()}"}
            time.sleep(poll_interval)
            waited += poll_interval
        else:
            logger.warning("인스타그램 릴스 컨테이너 처리 시간 초과 (%s초)", max_wait_seconds)
            return {"status": "error", "reason": "container_timeout"}

        publish_resp = safe_post(
            f"{INSTAGRAM_API_BASE}/{settings.ig_user_id}/media_publish",
            data={"creation_id": container_id, "access_token": settings.ig_access_token},
            timeout=30,
        )
        if publish_resp is None or publish_resp.status_code != 200:
            status = getattr(publish_resp, "status_code", "no_response")
            body = getattr(publish_resp, "text", "")[:300] if publish_resp is not None else ""
            logger.warning("인스타그램 릴스 발행 실패 (status=%s): %s", status, body)
            return {"status": "error", "reason": "publish_failed"}
        return {"status": "ok", "response": publish_resp.json()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("인스타그램 릴스 업로드 실패: %s", exc)
        return {"status": "error", "reason": str(exc)}


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------
def _wait_for_threads_container_ready(
    creation_id: str, access_token: str, max_attempts: int = 6, delay_seconds: float = 3.0
) -> bool:
    """threads_publish 호출 전에 컨테이너 처리가 끝났는지 확인한다.

    생성(POST /threads) 직후 바로 발행(POST /threads_publish)을 호출하면 아직
    미디어 컨테이너 처리가 안 끝나서 "미디어를 찾을 수 없음"(subcode 4279009)
    오류가 나는 걸 실측으로 확인했다 - 특히 답글(reply_to_id 지정)에서 잘
    발생한다. Meta 공식 가이드대로 status가 FINISHED가 될 때까지 짧게 폴링한다.
    """
    for _ in range(max_attempts):
        status_resp = safe_get(
            f"{THREADS_API_BASE}/{creation_id}",
            params={"fields": "status,error_message", "access_token": access_token},
            timeout=15,
        )
        if status_resp is not None and status_resp.status_code == 200:
            status = status_resp.json().get("status")
            if status == "FINISHED":
                return True
            if status == "ERROR":
                return False
        time.sleep(delay_seconds)
    return False


def publish_threads_post(text: str) -> Dict[str, Any]:
    if not settings.threads_access_token:
        logger.info("THREADS_ACCESS_TOKEN 미설정 - 스레드 게시를 건너뜁니다.")
        return {"status": "skipped", "reason": "not_configured"}

    try:
        # Threads는 인스타그램과 연동되어 있어도 별도의 자체 유저ID 체계를 쓴다
        # (IG_USER_ID를 넣으면 "does not exist" 에러가 난다 - 실측으로 확인함).
        # "me"는 액세스 토큰 소유자 본인을 가리키는 그래프 API 예약어라 항상 정확하다.
        user_id = "me"
        create_resp = safe_post(
            f"{THREADS_API_BASE}/{user_id}/threads",
            data={
                "media_type": "TEXT",
                "text": text,
                "access_token": settings.threads_access_token,
            },
            timeout=20,
        )
        if create_resp is None or create_resp.status_code != 200:
            logger.warning(
                "스레드 게시 생성 실패: status=%s body=%s",
                getattr(create_resp, "status_code", "N/A"),
                getattr(create_resp, "text", ""),
            )
            return {"status": "error", "reason": "create_failed"}
        creation_id = create_resp.json().get("id")

        _wait_for_threads_container_ready(creation_id, settings.threads_access_token)

        publish_resp = safe_post(
            f"{THREADS_API_BASE}/{user_id}/threads_publish",
            data={"creation_id": creation_id, "access_token": settings.threads_access_token},
            timeout=20,
        )
        if publish_resp is None or publish_resp.status_code != 200:
            logger.warning(
                "스레드 게시 발행 실패: status=%s body=%s",
                getattr(publish_resp, "status_code", "N/A"),
                getattr(publish_resp, "text", ""),
            )
            return {"status": "error", "reason": "publish_failed"}

        result = publish_resp.json()
        return {"status": "ok", "post_id": result.get("id"), "response": result}
    except Exception as exc:  # noqa: BLE001
        logger.warning("스레드 게시 실패: %s", exc)
        return {"status": "error", "reason": str(exc)}


def add_threads_first_comment(post_id: str, comment_text: str) -> Dict[str, Any]:
    if not (settings.threads_access_token and post_id):
        return {"status": "skipped", "reason": "not_configured_or_no_post_id"}

    try:
        # publish_threads_post와 동일하게 생성(threads) -> 발행(threads_publish)
        # 2단계가 반드시 필요하다. 이전 코드는 생성만 하고 발행을 안 해서,
        # 댓글이 실제로는 미발행 상태로 남아 "아직 답글이 없습니다"가 되는
        # 버그가 있었다(실측으로 확인함 - 본문은 정상 게시되는데 첫 댓글만 안 달림).
        create_resp = safe_post(
            f"{THREADS_API_BASE}/me/threads",
            data={
                "media_type": "TEXT",
                "text": comment_text,
                "reply_to_id": post_id,
                "access_token": settings.threads_access_token,
            },
            timeout=20,
        )
        if create_resp is None or create_resp.status_code != 200:
            logger.warning(
                "스레드 첫 댓글 생성 실패: status=%s body=%s",
                getattr(create_resp, "status_code", "N/A"),
                getattr(create_resp, "text", ""),
            )
            return {"status": "error", "reason": "comment_create_failed"}
        creation_id = create_resp.json().get("id")

        _wait_for_threads_container_ready(creation_id, settings.threads_access_token)

        publish_resp = safe_post(
            f"{THREADS_API_BASE}/me/threads_publish",
            data={"creation_id": creation_id, "access_token": settings.threads_access_token},
            timeout=20,
        )
        if publish_resp is None or publish_resp.status_code != 200:
            logger.warning(
                "스레드 첫 댓글 발행 실패: status=%s body=%s",
                getattr(publish_resp, "status_code", "N/A"),
                getattr(publish_resp, "text", ""),
            )
            return {"status": "error", "reason": "comment_publish_failed"}

        return {"status": "ok", "response": publish_resp.json()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("스레드 첫 댓글 등록 실패: %s", exc)
        return {"status": "error", "reason": str(exc)}


# ---------------------------------------------------------------------------
# YouTube (google-api-python-client) - OAuth 사용자 인증 필요 (서비스 계정 불가)
# ---------------------------------------------------------------------------
def publish_youtube_longform(video_path: Path, title: str, description: str) -> Dict[str, Any]:
    """YouTube Data API v3로 롱폼 영상을 업로드한다.

    주의: YouTube 업로드는 서비스 계정만으로는 개인 채널에 대한 권한이 없다.
    YOUTUBE_CLIENT_SECRETS_PATH(OAuth 클라이언트) + 최초 1회 브라우저 동의 절차로
    생성된 YOUTUBE_TOKEN_PATH가 필요하다. 두 파일이 없으면 스킵한다.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        return {"status": "skipped", "reason": "video_not_found"}

    secrets_path = Path(settings.youtube_client_secrets_path)
    token_path = Path(settings.youtube_token_path)
    if not secrets_path.exists() or not token_path.exists():
        logger.info(
            "YouTube OAuth 설정 미완료(%s / %s) - 업로드를 건너뜁니다. "
            "최초 1회 OAuth 동의 절차가 별도로 필요합니다.",
            secrets_path,
            token_path,
        )
        return {"status": "skipped", "reason": "oauth_not_configured"}

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_SCOPES)
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {"title": title[:100], "description": description[:5000], "categoryId": "25"},
            "status": {"privacyStatus": "public"},
        }
        media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = request.execute()
        return {"status": "ok", "video_id": response.get("id")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("YouTube 업로드 실패: %s", exc)
        return {"status": "error", "reason": str(exc)}


def add_youtube_comment(video_id: str, comment_text: str) -> Dict[str, Any]:
    """업로드된 영상에 최상위 댓글을 자동으로 작성한다(URL 등 안내용).

    주의: YouTube Data API는 댓글을 "고정"하는 기능 자체를 제공하지 않는다
    (채널 소유자가 유튜브 스튜디오에서 직접 눌러야 함). 이 함수는 댓글 작성까지만
    자동화하고, 고정은 distribute_all()에서 텔레그램으로 리마인드한다.
    """
    if not video_id:
        return {"status": "skipped", "reason": "no_video_id"}

    secrets_path = Path(settings.youtube_client_secrets_path)
    token_path = Path(settings.youtube_token_path)
    if not secrets_path.exists() or not token_path.exists():
        return {"status": "skipped", "reason": "oauth_not_configured"}

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_SCOPES)
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {"snippet": {"textOriginal": comment_text}},
            }
        }
        response = youtube.commentThreads().insert(part="snippet", body=body).execute()
        return {"status": "ok", "comment_id": response.get("id")}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "YouTube 댓글 작성 실패(%s): %s - 기존 토큰이 youtube.upload 스코프로만 "
            "발급되어 있으면 scripts/generate_youtube_token.py로 재동의가 필요합니다.",
            video_id,
            exc,
        )
        return {"status": "error", "reason": str(exc)}


# ---------------------------------------------------------------------------
# 색인 핑
# ---------------------------------------------------------------------------
def ping_google_indexing(url: str) -> bool:
    if not Path(settings.google_key_path).exists():
        logger.info("GOOGLE_KEY_PATH(서비스계정) 파일 없음 - 구글 색인 핑을 건너뜁니다.")
        return False

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            settings.google_key_path,
            scopes=["https://www.googleapis.com/auth/indexing"],
        )
        service = build("indexing", "v3", credentials=creds)
        service.urlNotifications().publish(
            body={"url": url, "type": "URL_UPDATED"}
        ).execute()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("구글 색인 핑 실패: %s", exc)
        return False


def ping_naver(url: str) -> bool:
    """네이버 서치어드바이저 IndexNow 핑."""
    resp = safe_get(NAVER_PING_URL, params={"url": url}, timeout=10)
    ok = resp is not None and resp.status_code in (200, 202)
    if not ok:
        logger.info("네이버 색인 핑 실패/미지원 - 계속 진행합니다.")
    return ok


def _build_youtube_description(site: str, post_id: int, post_url: str, fact_summary: str) -> str:
    """유튜브 설명란에 넣을 텍스트를 만든다.

    유튜브 쇼핑의 "영상 위 상품 카드" 기능은 채널 자격(YPP)과 스토어 연결이
    필요해 API로 자동화할 수 없지만, 설명란에 제휴 링크를 넣는 것은 자격 조건
    없이 지금 바로 가능하다 - 그래서 이 함수가 그 최소한의 대안을 제공한다.
    """
    lines = [fact_summary, "", f"📖 원문 보러가기: {post_url}"]

    affiliate_link = get_primary_affiliate_link(site, "youtube", post_id)
    if affiliate_link:
        lines += ["", f"🔗 바로가기: {affiliate_link}", FTC_DISCLOSURE_TEXT]

    return "\n".join(line for line in lines if line is not None)


# ---------------------------------------------------------------------------
# 통합 배포
# ---------------------------------------------------------------------------
def distribute_all(
    site: str,
    post_url: str,
    thumbnail_path: Optional[Path] = None,
    video_paths: Optional[Dict[str, Path]] = None,
    captions: Optional[Dict[str, str]] = None,
    post_id: int = 0,
) -> Dict[str, Any]:
    """5개 채널에 순차 배포하고 채널별 결과를 집계한다. 하나의 실패가 전체를 막지 않는다."""
    video_paths = video_paths or {}
    captions = captions or {}
    results: Dict[str, Any] = {}

    results["google_index"] = {"status": "ok" if ping_google_indexing(post_url) else "error"}
    results["naver_index"] = {"status": "ok" if ping_naver(post_url) else "error"}

    threads_result = publish_threads_post(captions.get("threads_post", ""))
    results["threads"] = threads_result
    if threads_result.get("status") == "ok" and captions.get("threads_comment"):
        comment_text = captions["threads_comment"].replace("{POST_URL}", post_url)
        results["threads_comment"] = add_threads_first_comment(
            threads_result.get("post_id", ""), comment_text
        )

    shorts_path = video_paths.get("shorts")
    if shorts_path:
        # IG Reels는 공개 URL이 필요 - 워드프레스 등에 업로드된 URL을 전달하는 것을 전제로 함.
        results["instagram"] = publish_instagram_reel(
            str(video_paths.get("shorts_public_url", "")), captions.get("ig_caption", "")
        )
    else:
        results["instagram"] = {"status": "skipped", "reason": "no_video"}

    if thumbnail_path:
        results["pinterest"] = publish_pinterest_pin(
            thumbnail_path,
            captions.get("title", ""),
            captions.get("pinterest_desc", ""),
            post_url,
        )
    else:
        results["pinterest"] = {"status": "skipped", "reason": "no_thumbnail"}

    longform_path = video_paths.get("longform")
    if longform_path:
        description = _build_youtube_description(
            site, post_id, post_url, captions.get("fact_summary", "")
        )
        youtube_result = publish_youtube_longform(
            longform_path, captions.get("title", ""), description
        )
        results["youtube"] = youtube_result

        video_id = youtube_result.get("video_id")
        if youtube_result.get("status") == "ok" and video_id:
            comment_text = f"📖 자세한 내용/신청 방법 원문: {post_url}"
            results["youtube_comment"] = add_youtube_comment(video_id, comment_text)
            # 댓글 고정 리마인드는 여기서 텔레그램으로 직접 보내지 않는다 - 이 함수의
            # 유일한 실제 호출측(telegram_bot._publish_longform_stage)은 항상 이미
            # 실행 중인 asyncio 이벤트 루프 안에서 돌기 때문에, 여기서 동기 래퍼
            # send_message_sync()의 asyncio.run()을 부르면 "cannot be called from a
            # running event loop"로 매번 조용히 실패한다. 대신 결과 dict에만 담아
            # 반환하고, telegram_bot._format_result_report()가 이미 await로 보내는
            # 발행 결과 보고 메시지에 리마인드를 포함시킨다.
    else:
        results["youtube"] = {"status": "skipped", "reason": "no_video"}

    return results
