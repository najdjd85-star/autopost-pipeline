"""테마 기본 푸터(클릭해도 이동하지 않는 '#' 가짜 링크 Blog/Shop/Events 등)를 실제 페이지 링크와
고지 문구로 교체하고, 사이트 제목/설명을 도메인명 대신 사이트 이름으로 바꾼다 (멱등).

실행: venv/bin/python scripts/fix_footer_and_identity.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.http import safe_get, safe_post
from utils.logger import get_logger
from wp_client import WordPressClient

logger = get_logger(__name__)

IDENTITY = {
    "A": ("정부지원금 안내소", "공식 기준으로 정리하는 정부지원금 신청 조건과 탈락 사례"),
    "B": ("통신비 절약 안내소", "알뜰폰·요금제·렌탈 비용을 줄이는 방법 정리"),
    "C": ("세금·연금 안내소", "연말정산, 종합소득세, 해외주식 세금, 연금 제도 정리"),
}


def _page_link(wp: WordPressClient, slugs: list) -> str:
    for slug in slugs:
        resp = safe_get(
            wp._api_url("wp/v2/pages"),
            headers=wp._auth_header(),
            params={"slug": slug, "_fields": "link"},
            timeout=15,
        )
        if resp is not None and resp.status_code == 200 and resp.json():
            return resp.json()[0]["link"]
    return "/"


def footer_markup(wp: WordPressClient, tagline: str) -> str:
    about = _page_link(wp, [quote("소개").lower(), "소개"])
    contact = _page_link(wp, [quote("문의하기").lower(), "문의하기"])
    privacy = _page_link(wp, ["privacy-policy", "privacy-policy-2"])
    calc = _page_link(wp, ["calculators"])
    return f"""<!-- wp:group {{"style":{{"spacing":{{"padding":{{"top":"var:preset|spacing|60","bottom":"var:preset|spacing|50"}}}}}},"layout":{{"type":"constrained"}}}} -->
<div class="wp-block-group" style="padding-top:var(--wp--preset--spacing--60);padding-bottom:var(--wp--preset--spacing--50)"><!-- wp:site-title {{"level":2}} /-->

<!-- wp:paragraph -->
<p>{tagline}</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p><a href="{about}">소개</a> · <a href="{contact}">문의하기</a> · <a href="{privacy}">개인정보처리방침</a> · <a href="{calc}">계산기</a></p>
<!-- /wp:paragraph -->

<!-- wp:paragraph {{"fontSize":"small"}} -->
<p class="has-small-font-size">본 사이트의 정보는 일반적인 안내이며 개인별 자격·금액·세액을 보장하지 않습니다. 정확한 내용은 해당 공식 기관에서 확인하세요. 일부 글에는 제휴 링크가 포함되어 수수료가 발생할 수 있습니다. © Daily Fix Point</p>
<!-- /wp:paragraph --></div>
<!-- /wp:group -->"""


def run(site: str) -> None:
    wp = WordPressClient(site)
    title, tagline = IDENTITY[site]
    resp = safe_post(
        wp._api_url("wp/v2/template-parts/twentytwentyfive//footer"),
        headers={**wp._auth_header(), "Content-Type": "application/json"},
        data=json.dumps({"content": footer_markup(wp, tagline)}),
        timeout=30,
    )
    logger.info("[Site %s] 푸터 교체: %s", site, getattr(resp, "status_code", "N/A"))
    resp = safe_post(
        wp._api_url("wp/v2/settings"),
        headers={**wp._auth_header(), "Content-Type": "application/json"},
        data=json.dumps({"title": title, "description": tagline}),
        timeout=30,
    )
    logger.info("[Site %s] 사이트 제목/설명 변경: %s", site, getattr(resp, "status_code", "N/A"))


if __name__ == "__main__":
    for key in ("A", "B", "C"):
        run(key)
