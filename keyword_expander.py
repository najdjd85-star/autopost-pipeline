"""
'빈집털이' 롱테일 키워드 자동 발굴 모듈.

네이버 자동완성 API로 메인 키워드를 확장하고, 실패 시 고전환 접미사
휴리스틱으로 폴백한다 (항상 비어있지 않은 리스트를 반환).
"""
from __future__ import annotations

import json
from typing import List

from config import settings
from utils.http import safe_get
from utils.logger import get_logger

logger = get_logger(__name__)

NAVER_AUTOCOMPLETE_URL = "https://ac.search.naver.com/nx/ac"

# 고전환 롱테일 접미사 - 검색량은 적지만 실질 신청/구매 의도가 강한 '빈집' 키워드
LONGTAIL_SUFFIXES = ["탈락", "알바", "조건", "부모님집", "중복", "후기", "신청방법", "자격"]


def _naver_autocomplete(keyword: str, max_results: int) -> List[str]:
    if not keyword:
        return []
    resp = safe_get(
        NAVER_AUTOCOMPLETE_URL,
        params={"q": keyword, "con": 1, "frm": "nx", "ans": 2, "r_format": "json", "r_enc": "UTF-8"},
        timeout=6,
    )
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else json.loads(resp.text)
        groups = data.get("items", [])
        suggestions: List[str] = []
        for group in groups:
            for item in group:
                text = item[0] if isinstance(item, list) and item else None
                if text and text not in suggestions:
                    suggestions.append(text)
        return suggestions[:max_results]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        logger.info("네이버 자동완성 응답 파싱 실패 (비공식 API 특성상 정상적인 변동일 수 있음): %s", exc)
        return []


def _heuristic_longtail(keyword: str, max_results: int) -> List[str]:
    return [f"{keyword} {suffix}" for suffix in LONGTAIL_SUFFIXES][:max_results]


def expand_to_longtail(keyword: str, max_results: int = 10) -> List[str]:
    """메인 키워드를 고전환 롱테일 키워드로 확장한다. 항상 비어있지 않은 리스트 반환."""
    keyword = (keyword or "").strip()
    if not keyword:
        return []

    suggestions = _naver_autocomplete(keyword, max_results)
    heuristic = _heuristic_longtail(keyword, max_results)

    combined: List[str] = []
    for item in suggestions + heuristic:
        if item not in combined:
            combined.append(item)

    if not combined:
        # 이론상 heuristic이 항상 비어있지 않은 리스트를 만들어내므로 도달하지 않지만 방어적으로 처리.
        combined = [keyword]

    return combined[:max_results]
