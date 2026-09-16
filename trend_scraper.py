"""
실시간 트렌드 및 공식 팩트 수집 모듈.

공공데이터포털(보조금24) API, 대한민국 정책브리핑 RSS, 구글 트렌드(한국) 일별
급상승 RSS를 수집해 오늘의 핫토픽 브리핑 텍스트를 만든다. 세 소스 중 일부가
실패해도 나머지로 계속 진행하며, 전부 실패하면 오프라인 스텁 브리핑을 반환한다
(절대 예외를 전파하지 않는다).
"""
from __future__ import annotations

from typing import Dict, List

import feedparser

from config import settings
from constants import SITE_KEYS, SITE_LABELS
from utils.http import safe_get
from utils.logger import get_logger

logger = get_logger(__name__)

POLICY_BRIEFING_RSS = "https://www.korea.kr/rss/policy.xml"
GOOGLE_TRENDS_DAILY_RSS_KR = "https://trends.google.com/trending/rss?geo=KR"
PUBLIC_DATA_SUBSIDY_API = (
    "https://api.odcloud.kr/api/gov24/v3/serviceList"  # 보조금24(정부24) 서비스 목록 API
)

# 사이트별 핵심 키워드 시드 (트렌드 소스가 전부 실패했을 때의 최소 폴백에도 사용)
SITE_SEED_KEYWORDS = {
    "A": ["정부지원금", "생계급여", "근로장려금"],
    "B": ["알뜰폰 요금제", "인터넷 결합할인", "정수기 렌탈"],
    "C": ["연말정산 환급", "종합소득세 환급", "국민연금 조기수령"],
}


def fetch_public_data_subsidies(limit: int = 20) -> List[Dict[str, str]]:
    """공공데이터포털 보조금24 API에서 지원사업 목록을 가져온다."""
    if not settings.public_data_api_key:
        logger.info("PUBLIC_DATA_API_KEY 미설정 - 공공데이터포털 조회를 건너뜁니다.")
        return []

    resp = safe_get(
        PUBLIC_DATA_SUBSIDY_API,
        params={
            "page": 1,
            "perPage": limit,
            "returnType": "JSON",
            "serviceKey": settings.public_data_api_key,
        },
        timeout=10,
    )
    if resp is None or resp.status_code != 200:
        logger.warning("공공데이터포털 응답 실패 - 건너뜁니다.")
        return []

    try:
        data = resp.json()
        items = data.get("data", [])
        return [
            {
                "title": item.get("servNm", ""),
                "summary": item.get("servDgst", ""),
                "url": item.get("servDtlLink", ""),
            }
            for item in items
        ]
    except (ValueError, AttributeError) as exc:
        logger.warning("공공데이터포털 응답 파싱 실패: %s", exc)
        return []


def fetch_policy_briefing_rss(limit: int = 20) -> List[Dict[str, str]]:
    """대한민국 정책브리핑 RSS 피드를 파싱한다."""
    try:
        feed = feedparser.parse(POLICY_BRIEFING_RSS)
        entries = feed.entries[:limit] if getattr(feed, "entries", None) else []
        return [
            {
                "title": e.get("title", ""),
                "summary": e.get("summary", ""),
                "url": e.get("link", ""),
            }
            for e in entries
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("정책브리핑 RSS 파싱 실패: %s", exc)
        return []


def fetch_google_trends_daily_kr(limit: int = 20) -> List[Dict[str, str]]:
    """구글 트렌드 한국 일별 급상승 검색어 RSS를 파싱한다."""
    try:
        feed = feedparser.parse(GOOGLE_TRENDS_DAILY_RSS_KR)
        entries = feed.entries[:limit] if getattr(feed, "entries", None) else []
        return [{"title": e.get("title", ""), "url": e.get("link", "")} for e in entries]
    except Exception as exc:  # noqa: BLE001
        logger.warning("구글 트렌드 RSS 파싱 실패: %s", exc)
        return []


def _filter_keywords_for_site(
    site: str, subsidies: List[Dict[str, str]], briefings: List[Dict[str, str]], trends: List[Dict[str, str]]
) -> List[str]:
    seeds = SITE_SEED_KEYWORDS.get(site, [])
    keywords: List[str] = list(seeds)

    combined_titles = (
        [s["title"] for s in subsidies]
        + [b["title"] for b in briefings]
        + [t["title"] for t in trends]
    )
    for title in combined_titles:
        if not title:
            continue
        for seed in seeds:
            # 시드 키워드의 핵심 토큰이 제목에 등장하면 관련 트렌드로 채택
            if any(tok in title for tok in seed.split()):
                keywords.append(title.strip())
                break

    # 중복 제거, 순서 유지
    seen = set()
    unique_keywords = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            unique_keywords.append(k)
    return unique_keywords[:15]


def fetch_today_hot_topics(site: str) -> Dict[str, object]:
    """오늘의 핫토픽 브리핑을 만든다. 항상 dict를 반환하며 예외를 던지지 않는다."""
    site = site.upper().replace("SITE_", "")
    if site not in SITE_KEYS:
        site = "A"

    subsidies = fetch_public_data_subsidies()
    briefings = fetch_policy_briefing_rss()
    trends = fetch_google_trends_daily_kr()

    keywords = _filter_keywords_for_site(site, subsidies, briefings, trends)

    if not keywords:
        logger.info("[Site %s] 모든 트렌드 소스 실패 - 오프라인 폴백 키워드 사용", site)
        keywords = SITE_SEED_KEYWORDS.get(site, ["정부지원금"])

    label = SITE_LABELS.get(site, site)
    briefing_lines = [f"[{label}] 오늘의 핫토픽 키워드: {', '.join(keywords[:8])}"]
    for b in briefings[:3]:
        if b.get("title"):
            briefing_lines.append(f"- 정책브리핑: {b['title']}")
    for s in subsidies[:3]:
        if s.get("title"):
            briefing_lines.append(f"- 지원사업: {s['title']}")

    return {
        "site": site,
        "keywords": keywords,
        "briefing_text": "\n".join(briefing_lines),
        "sources": {
            "subsidies": subsidies,
            "briefings": briefings,
            "trends": trends,
        },
    }
