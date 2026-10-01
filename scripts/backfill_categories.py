"""기존에 전부 Uncategorized로 쌓인 글들을 사이트별 실제 카테고리로 재분류하는 1회성 스크립트.

telegram_bot.py의 발행 코드가 wp.create_draft_post() 호출 시 category 인자를
넘기지 않아서 생긴 과거 버그의 소급 수정이다. 제목의 키워드로 분류하므로
완벽하지 않을 수 있지만, 전부 Uncategorized인 것보다는 훨씬 낫다.

실행: venv/bin/python scripts/backfill_categories.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from constants import SITE_CATEGORIES
from utils.logger import get_logger
from wp_client import WordPressClient

logger = get_logger(__name__)

# (제목에 포함되면 매칭, 우선순위 순) -> 카테고리명. 매칭되는 게 없으면 해당 사이트의
# SITE_CATEGORIES 첫 번째 항목(기본 카테고리)으로 분류한다.
_RULES = {
    "A": [
        (("주거", "전세", "월세", "자가"), "주거지원"),
        (("기초연금", "연금"), "연금"),
    ],
    "B": [
        (("렌탈", "정수기"), "렌탈"),
    ],
    "C": [
        (("종합소득세", "부가가치세"), "종합소득세"),
        (("국민연금",), "국민연금"),
    ],
}


def classify(site: str, title: str) -> str:
    for keywords, category in _RULES.get(site, []):
        if any(kw in title for kw in keywords):
            return category
    return SITE_CATEGORIES[site][0]


def backfill(site: str) -> None:
    wp = WordPressClient(site)
    if not wp.is_configured:
        logger.warning("[Site %s] 미설정 - 건너뜁니다.", site)
        return

    category_ids = {name: wp.get_or_create_category(name) for name in SITE_CATEGORIES[site]}
    logger.info("[Site %s] 카테고리 id: %s", site, category_ids)

    posts = []
    page = 1
    while True:
        from utils.http import safe_get

        resp = safe_get(
            wp._api_url("wp/v2/posts"),
            headers=wp._auth_header(),
            params={"per_page": 50, "page": page, "status": "publish,draft", "_fields": "id,title"},
            timeout=20,
        )
        if resp is None or resp.status_code != 200:
            break
        batch = resp.json()
        if not batch:
            break
        posts.extend(batch)
        if len(batch) < 50:
            break
        page += 1

    counts: dict = {}
    for post in posts:
        title = post.get("title", {}).get("rendered", "")
        category_name = classify(site, title)
        cat_id = category_ids.get(category_name)
        if not cat_id:
            continue
        result = wp.update_post(post["id"], categories=[cat_id])
        counts[category_name] = counts.get(category_name, 0) + 1
        status = "OK" if result else "FAIL"
        logger.info("[Site %s] #%s -> %s (%s) [%s]", site, post["id"], category_name, title[:30], status)

    logger.info("[Site %s] 분류 완료: %s", site, counts)


if __name__ == "__main__":
    for site_key in ("A", "B", "C"):
        backfill(site_key)
