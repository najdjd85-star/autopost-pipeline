"""모든 글/페이지 맨 위(헤더)와 맨 아래(푸터)에 눈에 띄는 '메인으로' 버튼을 넣는다 (멱등).

계산기를 쓰거나 글을 읽고 나면 허브 메인으로 돌아갈 길이 햄버거 메뉴 안에만 있어서, 연세 드신 분들이 찾기 어렵다는
지적에 따라 메뉴를 열지 않아도 보이는 큰 버튼(집 아이콘 + 글자)을 헤더에 달고, 푸터에도 큰 버튼을 단다.

실행: venv/bin/python scripts/add_home_button.py   (푸터에는 넣지 않는다 - 본문 아래 버튼과 중복)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.http import safe_get, safe_post
from utils.logger import get_logger
from wp_client import WordPressClient

logger = get_logger(__name__)

HUB_URL = "https://dailyfixpoint.com"
HOUSE = (
    '<svg width="{s}" height="{s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 11l9-8 9 8"/>'
    '<path d="M5 10v10h5v-6h4v6h5V10"/></svg>'
)

HEADER_BUTTON = (
    '<!-- wp:html -->\n'
    f'<a class="dfp-home" href="{HUB_URL}" aria-label="데일리픽스 메인 화면으로 가기" '
    'style="display:inline-flex;align-items:center;gap:6px;min-height:44px;padding:0 14px;border-radius:999px;'
    'background:#185fa5;color:#fff;font-size:15px;font-weight:600;text-decoration:none;white-space:nowrap">'
    + HOUSE.format(s=20)
    + "메인</a>\n<!-- /wp:html -->\n"
)

# (더 이상 푸터에 넣지 않는다: 본문 아래 버튼과 중복되어 제거함. 원복용 참고로만 남김)
FOOTER_BUTTON = (
    '<!-- wp:html -->\n'
    '<div style="margin:0 0 20px">'
    f'<a class="dfp-home-foot" href="{HUB_URL}" aria-label="데일리픽스 메인 화면으로 돌아가기" '
    'style="display:flex;align-items:center;justify-content:center;gap:10px;min-height:56px;padding:0 20px;'
    'border-radius:14px;background:#185fa5;color:#fff;font-size:18px;font-weight:600;text-decoration:none">'
    + HOUSE.format(s=24)
    + "메인 화면으로 돌아가기</a></div>\n<!-- /wp:html -->\n\n"
)


def add_header_button(site: str) -> None:
    wp = WordPressClient(site)
    url = wp._api_url("wp/v2/template-parts/twentytwentyfive//header")
    resp = safe_get(url, headers=wp._auth_header(), params={"context": "edit"}, timeout=20)
    content = resp.json()["content"]["raw"]
    if "dfp-home" in content:
        logger.info("[Site %s] 헤더에 이미 메인 버튼이 있습니다.", site)
        return
    marker = "<!-- wp:navigation"
    if content.count(marker) != 1:
        logger.warning("[Site %s] 헤더 구조가 예상과 달라 건드리지 않습니다.", site)
        return
    new_content = content.replace(marker, HEADER_BUTTON + "\t\t\t" + marker)
    res = safe_post(
        url,
        headers={**wp._auth_header(), "Content-Type": "application/json"},
        data=json.dumps({"content": new_content}),
        timeout=30,
    )
    logger.info("[Site %s] 헤더 메인 버튼 추가: %s", site, getattr(res, "status_code", "N/A"))


BODY_BUTTON = (
    '<!-- wp:group {"layout":{"type":"constrained"},"style":{"spacing":{"margin":{"top":"var:preset|spacing|50"}}}} -->\n'
    '<div class="wp-block-group" style="margin-top:var(--wp--preset--spacing--50)"><!-- wp:html -->\n'
    f'<a class="dfp-home-body" href="{HUB_URL}" aria-label="데일리픽스 메인 화면으로 돌아가기" '
    'style="display:flex;align-items:center;justify-content:center;gap:10px;min-height:56px;padding:0 20px;'
    'border-radius:14px;background:#185fa5;color:#fff;font-size:18px;font-weight:600;text-decoration:none">'
    + HOUSE.format(s=24)
    + "메인 화면으로 돌아가기</a>\n<!-- /wp:html --></div>\n<!-- /wp:group -->\n"
)
CONTENT_MARKER = '<!-- wp:post-content {"align":"full","layout":{"type":"constrained"}} /-->'


def add_body_button(site: str) -> None:
    """글(single)과 페이지(page) 템플릿의 본문 바로 아래에 큰 '메인으로' 버튼을 넣는다."""
    wp = WordPressClient(site)
    for slug in ("single", "page"):
        url = wp._api_url(f"wp/v2/templates/twentytwentyfive//{slug}")
        resp = safe_get(url, headers=wp._auth_header(), params={"context": "edit"}, timeout=20)
        content = resp.json()["content"]["raw"]
        if "dfp-home-body" in content:
            logger.info("[Site %s] %s 템플릿에 이미 본문 버튼이 있습니다.", site, slug)
            continue
        if content.count(CONTENT_MARKER) != 1:
            logger.warning("[Site %s] %s 템플릿 구조가 예상과 달라 건드리지 않습니다.", site, slug)
            continue
        res = safe_post(
            url,
            headers={**wp._auth_header(), "Content-Type": "application/json"},
            data=json.dumps({"content": content.replace(CONTENT_MARKER, CONTENT_MARKER + "\n" + BODY_BUTTON)}),
            timeout=30,
        )
        logger.info("[Site %s] %s 템플릿 본문 버튼 추가: %s", site, slug, getattr(res, "status_code", "N/A"))


if __name__ == "__main__":
    for key in ("A", "B", "C"):
        add_header_button(key)
        add_body_button(key)
