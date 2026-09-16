"""
최근 N개월간 조회수가 높은 관련 유튜브 영상을 찾아, 쇼츠/롱폼 영상 대본을 쓸 때
"어떤 제목·후킹이 잘 먹히는지" 참고 자료로 활용하는 모듈.

competitor_analyzer.py(네이버 블로그 벤치마킹)와 동일한 원칙이다: 실제 대본이나
자막을 가져오는 게 아니라 제목/조회수/길이 같은 메타데이터만 참고하고,
generator.py가 그 패턴을 참고해 100% 새로운 대본을 쓰도록 유도한다
(저작권 문제 없음 - 남의 대본을 베끼지 않는다).

YOUTUBE_API_KEY(단순 API 키, 업로드용 OAuth와 별개)가 없으면 빈 결과를
반환하며, generator.py는 이 참고자료 없이도 정상적으로 진행한다.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
SHORTS_MAX_SECONDS = 90  # 이보다 짧으면 "쇼츠 참고", 길면 "롱폼 참고"로 분류


def _parse_iso8601_duration(duration: str) -> int:
    """"PT7M30S" 같은 ISO8601 duration 문자열을 초 단위 정수로 변환한다."""
    m = _DURATION_RE.match(duration or "")
    if not m:
        return 0
    hours, minutes, seconds = (int(g) if g else 0 for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


def _get_youtube_search_client():
    """검색 전용 유튜브 클라이언트 (단순 API 키 인증, OAuth 불필요)."""
    if not settings.youtube_api_key:
        return None
    try:
        from googleapiclient.discovery import build

        return build("youtube", "v3", developerKey=settings.youtube_api_key)
    except Exception as exc:  # noqa: BLE001
        logger.info("유튜브 검색 클라이언트 생성 실패: %s", exc)
        return None


def get_trending_videos(
    keyword: str, months: int = 3, max_results: int = 15
) -> Dict[str, List[Dict[str, Any]]]:
    """최근 months개월간 keyword 관련 조회수 상위 영상을 쇼츠/롱폼으로 나눠 반환한다.

    반환: {"shorts": [...], "longform": [...]} 각 항목은
    {title, channel, view_count, url, duration_seconds}.
    YOUTUBE_API_KEY 미설정 또는 조회 실패 시 빈 리스트만 담긴 dict를 반환한다
    (예외를 던지지 않음 - 선택 기능).
    """
    empty: Dict[str, List[Dict[str, Any]]] = {"shorts": [], "longform": []}
    client = _get_youtube_search_client()
    if client is None or not keyword:
        return empty

    published_after = (datetime.now(timezone.utc) - timedelta(days=months * 30)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    try:
        search_resp = (
            client.search()
            .list(
                q=keyword,
                part="id",
                type="video",
                order="viewCount",
                publishedAfter=published_after,
                regionCode="KR",
                relevanceLanguage="ko",
                maxResults=max_results,
            )
            .execute()
        )
        video_ids = [
            item["id"]["videoId"] for item in search_resp.get("items", []) if item.get("id", {}).get("videoId")
        ]
        if not video_ids:
            return empty

        videos_resp = (
            client.videos()
            .list(part="snippet,statistics,contentDetails", id=",".join(video_ids))
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("유튜브 트렌드 영상 조회 실패 (선택 기능이라 계속 진행): %s", exc)
        return empty

    shorts: List[Dict[str, Any]] = []
    longform: List[Dict[str, Any]] = []
    for item in videos_resp.get("items", []):
        duration_sec = _parse_iso8601_duration(item.get("contentDetails", {}).get("duration", ""))
        try:
            view_count = int(item.get("statistics", {}).get("viewCount", 0))
        except (TypeError, ValueError):
            view_count = 0
        entry = {
            "title": item.get("snippet", {}).get("title", ""),
            "channel": item.get("snippet", {}).get("channelTitle", ""),
            "view_count": view_count,
            "url": f"https://www.youtube.com/watch?v={item.get('id')}",
            "duration_seconds": duration_sec,
        }
        (shorts if duration_sec and duration_sec <= SHORTS_MAX_SECONDS else longform).append(entry)

    shorts.sort(key=lambda v: v["view_count"], reverse=True)
    longform.sort(key=lambda v: v["view_count"], reverse=True)
    return {"shorts": shorts[:5], "longform": longform[:5]}


def format_trend_briefing(trends: Dict[str, List[Dict[str, Any]]]) -> str:
    """generator.py 프롬프트에 그대로 넣을 수 있는 텍스트 브리핑을 만든다."""
    if not trends.get("shorts") and not trends.get("longform"):
        return "(최근 3개월 관련 유튜브 트렌드 데이터를 가져오지 못했습니다 - 참고 없이 작성하세요.)"

    lines: List[str] = []
    if trends.get("shorts"):
        lines.append("[최근 3개월 조회수 상위 관련 쇼츠/릴스 - 제목 패턴만 참고, 내용은 베끼지 말 것]")
        for v in trends["shorts"]:
            lines.append(f"- ({v['view_count']:,}회) {v['title']}")
    if trends.get("longform"):
        lines.append("[최근 3개월 조회수 상위 관련 롱폼 영상 - 제목/구성 패턴만 참고]")
        for v in trends["longform"]:
            lines.append(f"- ({v['view_count']:,}회) {v['title']}")
    return "\n".join(lines)
