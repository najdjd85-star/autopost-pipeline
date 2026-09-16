"""
구글 서치콘솔 기반 상위 글 순위 방어 갱신 모듈.

Search Console API로 최근 28일간 평균 순위 4~15위 사이 포스팅을 감지하고,
Claude로 최신 팩트/FAQ를 보강해 리라이팅한 뒤 텔레그램 승인을 요청한다.

순환 임포트 방지를 위해 무거운 telegram_bot.py(polling Application)를 임포트
하지 않고, 상태 없는 utils.telegram_notify만 사용한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from config import get_site, settings
from generator import CLAUDE_MODEL, GeneratorNotConfiguredError, _get_client
from utils.logger import get_logger
from utils.telegram_notify import send_message_sync
from wp_client import WordPressClient

# generator.py와 동일한 이유로, HTML을 텍스트로 받아 JSON 파싱하지 않고
# tool use로 구조화된 값을 직접 받는다 (따옴표/줄바꿈 이스케이프 문제 회피).
REWRITE_TOOL = {
    "name": "submit_rewrite",
    "description": "리라이팅된 HTML 본문과 변경 요약을 제출합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "updated_html": {"type": "string", "description": "최신화된 전체 HTML 본문"},
            "change_summary": {"type": "string", "description": "무엇을 왜 바꿨는지 2~3문장 요약"},
        },
        "required": ["updated_html", "change_summary"],
    },
}

logger = get_logger(__name__)


def fetch_search_console_rankings(site_url: str, days: int = 28) -> List[Dict[str, Any]]:
    """Search Console API에서 최근 N일 페이지별 평균 순위를 가져온다."""
    key_path = Path(settings.google_key_path)
    if not key_path.exists():
        logger.info("GOOGLE_KEY_PATH(%s) 없음 - 서치콘솔 조회를 건너뜁니다.", key_path)
        return []
    if not site_url:
        return []

    try:
        import datetime

        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            str(key_path), scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
        )
        service = build("searchconsole", "v1", credentials=creds)

        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days)

        response = (
            service.searchanalytics()
            .query(
                siteUrl=site_url,
                body={
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "dimensions": ["page"],
                    "rowLimit": 200,
                },
            )
            .execute()
        )
        rows = response.get("rows", [])
        return [
            {"page": row["keys"][0], "position": row.get("position", 0), "clicks": row.get("clicks", 0)}
            for row in rows
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("서치콘솔 순위 조회 실패: %s", exc)
        return []


def find_rank_defense_candidates(
    rows: List[Dict[str, Any]], low: int = 4, high: int = 15
) -> List[Dict[str, Any]]:
    """평균 순위가 low~high 사이인, 즉 '조금만 더 밀면 상위로 갈 수 있는' 후보를 찾는다."""
    return [row for row in rows if low <= row.get("position", 0) <= high]


def rewrite_post_for_rank_defense(site: str, post: Dict[str, Any], current_html: str) -> Dict[str, Any]:
    """Claude로 최신 팩트 업데이트 + FAQ 보강 리라이팅을 수행한다."""
    client = _get_client()
    if client is None:
        raise GeneratorNotConfiguredError("ANTHROPIC_API_KEY 미설정으로 순위 방어 리라이팅 불가")

    prompt = f"""아래는 현재 순위 방어가 필요한(평균 4~15위) 게시물의 기존 HTML 본문입니다.
페이지: {post.get('page')}
평균 순위: {post.get('position')}

[기존 본문]
{current_html[:6000]}

요청사항:
1. 최신 팩트/수치로 업데이트할 만한 부분을 찾아 갱신하세요 (추측하지 말고 표현을 최신화).
2. 기존 FAQ 아코디언에 실제 검색 사용자가 궁금해할 질문 1~2개를 추가로 보강하세요.
3. 전체 HTML 구조(슬롯 플레이스홀더 포함)는 최대한 유지하세요.

설명 없이 submit_rewrite 도구를 호출해서 결과를 제출하세요.
"""
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=6000,
        tools=[REWRITE_TOOL],
        tool_choice={"type": "tool", "name": "submit_rewrite"},
        messages=[{"role": "user", "content": prompt}],
    )
    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "Claude 리라이팅 호출 완료 - 입력 %s 토큰 / 출력 %s 토큰",
            usage.input_tokens,
            usage.output_tokens,
        )
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_rewrite":
            return dict(block.input)

    logger.warning("순위 방어 리라이팅 응답에 submit_rewrite 도구 호출이 없습니다.")
    return {"updated_html": current_html, "change_summary": "도구 호출 실패 - 변경 없음"}


def request_rank_defense_approval(site: str, post: Dict[str, Any], proposed_html: str) -> None:
    message = (
        f"📈 [순위 방어 후보] Site {site}\n"
        f"페이지: {post.get('page')}\n"
        f"현재 평균 순위: {post.get('position'):.1f}\n\n"
        f"리라이팅 초안이 준비되었습니다. 워드프레스에서 직접 검토 후 반영해주세요."
    )
    send_message_sync(message)


def run_rank_check(site: str) -> List[Dict[str, Any]]:
    """사이트 하나의 순위 방어 파이프라인 전체를 실행한다."""
    site = site.upper().replace("SITE_", "")
    site_cfg = get_site(site)
    wp = WordPressClient(site)

    rows = fetch_search_console_rankings(site_cfg.wp_url)
    candidates = find_rank_defense_candidates(rows)

    if not candidates:
        logger.info("[Site %s] 순위 방어 대상 없음 (평균 4~15위 게시물 없음)", site)
        return []

    processed = []
    for candidate in candidates:
        try:
            # 실제 운영에서는 candidate['page'] URL로 워드프레스 post_id를 역조회해야 하나,
            # 이 파이프라인 단계에서는 개념 검증용으로 현재 본문을 알 수 없는 경우 스킵 처리한다.
            current_html = candidate.get("current_html", "")
            if not current_html:
                logger.info("[Site %s] %s 본문 조회 불가 - 건너뜁니다.", site, candidate.get("page"))
                continue

            rewrite_result = rewrite_post_for_rank_defense(site, candidate, current_html)
            request_rank_defense_approval(site, candidate, rewrite_result.get("updated_html", ""))
            processed.append({**candidate, **rewrite_result})
        except GeneratorNotConfiguredError as exc:
            logger.warning("[Site %s] %s", site, exc)
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Site %s] 순위 방어 처리 중 오류: %s", site, exc)
            continue

    return processed
