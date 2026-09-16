"""
상위 노출 블로그 실시간 벤치마킹 모듈.

확장된 롱테일 키워드로 네이버 검색 API(blog)를 호출해 상위 1~3위 블로그의
제목과 본문 핵심 텍스트를 크롤링한다. 여기서 얻은 레퍼런스는 generator.py의
프롬프트에 주입되어, Claude가 "핵심 정보는 흡수하되 문체/구성은 100% 새롭게
재창작"하도록 유도하는 데 쓰인다.

2026년 네이버 검색 API는 기존 "네이버 개발자센터" 방식에서 "NAVER API HUB"
(NAVER Cloud Platform)로 이관되었다. 2026-07-31 이후 신규 발급 애플리케이션은
개발자센터 방식을 아예 선택할 수 없고 API HUB 자격증명만 사용 가능하며,
엔드포인트/인증 헤더 이름이 모두 변경되었다 (기존 X-Naver-Client-Id 방식은
2027-06-30까지 기존 사용자에 한해 한시적으로만 유지됨). 이 모듈은 API HUB
방식을 기준으로 구현되어 있다.

실패 시 빈 리스트를 반환하며, generator.py는 이를 "경쟁사 팩트 생략, 트렌드
데이터만으로 진행"으로 처리한다.
"""
from __future__ import annotations

import re
from typing import Dict, List

from bs4 import BeautifulSoup

from config import settings
from utils.http import safe_get
from utils.logger import get_logger

logger = get_logger(__name__)

# NAVER API HUB (신규, 2026년 이관) - NAVER Cloud Platform 콘솔에서 발급.
NAVER_BLOG_SEARCH_API = "https://naverapihub.apigw.ntruss.com/search/v1/blog"


def _strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def search_naver_blogs(longtail_keyword: str, display: int = 5) -> List[Dict[str, str]]:
    """네이버 검색 API(NAVER API HUB, blog)로 롱테일 키워드 검색 결과를 가져온다."""
    if not (settings.naver_client_id and settings.naver_client_secret):
        logger.info("NAVER_CLIENT_ID/SECRET 미설정 - 블로그 검색을 건너뜁니다.")
        return []

    resp = safe_get(
        NAVER_BLOG_SEARCH_API,
        headers={
            # NAVER API HUB 인증 헤더 (구 X-Naver-Client-Id/Secret에서 이름이 변경됨).
            "X-NCP-APIGW-API-KEY-ID": settings.naver_client_id,
            "X-NCP-APIGW-API-KEY": settings.naver_client_secret,
        },
        params={"query": longtail_keyword, "display": display, "sort": "sim"},
        timeout=8,
    )
    if resp is None or resp.status_code != 200:
        status = getattr(resp, "status_code", "no_response")
        body = getattr(resp, "text", "")[:200] if resp is not None else ""
        logger.warning("네이버 블로그 검색 API 응답 실패 (status=%s): %s", status, body)
        return []

    try:
        items = resp.json().get("items", [])
        return [
            {
                "title": _strip_html_tags(item.get("title", "")),
                "url": item.get("link", ""),
                "description": _strip_html_tags(item.get("description", "")),
            }
            for item in items
        ]
    except ValueError as exc:
        logger.warning("네이버 블로그 검색 응답 파싱 실패: %s", exc)
        return []


def scrape_blog_post(url: str, timeout: int = 8) -> Dict[str, str]:
    """블로그 게시물 본문 핵심 텍스트를 크롤링한다. 실패 시 빈 dict 반환."""
    if not url:
        return {}

    resp = safe_get(url, timeout=timeout)
    if resp is None or resp.status_code != 200:
        return {}

    try:
        soup = BeautifulSoup(resp.text, "html.parser")

        # 네이버 블로그는 본문이 iframe(mainFrame) 안에 있는 경우가 많아 실패할 수 있음 -
        # 이 경우 검색 API의 description(요약)만으로도 충분히 레퍼런스 역할을 하므로 정상 동작.
        title_tag = soup.find(["h1", "h2", "title"])
        title = title_tag.get_text(strip=True) if title_tag else ""

        paragraphs = soup.find_all(["p", "div"], limit=50)
        body_text = " ".join(p.get_text(" ", strip=True) for p in paragraphs)
        body_text = re.sub(r"\s+", " ", body_text)[:1500]

        return {"title": title, "body_text": body_text}
    except Exception as exc:  # noqa: BLE001
        logger.info("블로그 본문 크롤링 실패 (%s): %s", url, exc)
        return {}


def get_top_blog_references(keyword: str, top_n: int = 3) -> List[Dict[str, str]]:
    """상위 top_n개 블로그의 제목+핵심 텍스트 레퍼런스를 반환한다. 실패 시 빈 리스트."""
    search_results = search_naver_blogs(keyword, display=max(top_n, 5))
    if not search_results:
        return []

    references: List[Dict[str, str]] = []
    for item in search_results[:top_n]:
        scraped = scrape_blog_post(item["url"])
        excerpt = scraped.get("body_text") or item.get("description", "")
        references.append(
            {
                "title": scraped.get("title") or item.get("title", ""),
                "url": item.get("url", ""),
                "excerpt": excerpt,
            }
        )
    return references
