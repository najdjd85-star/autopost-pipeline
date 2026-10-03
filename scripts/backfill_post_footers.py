"""이미 발행된 글에 (1) 계산기 면책 문구 (2) 공식 출처 + 정보 기준일 박스를 소급 추가한다 (멱등).

정보 기준일은 각 글의 게시일이다. 공정위/제휴 고지 문단이 있으면 그 바로 앞에 출처 박스를 넣는다.

실행: venv/bin/python scripts/backfill_post_footers.py [--dry-run]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smart_affiliate_matcher import add_calculator_disclaimer, build_source_footer
from utils.http import safe_get, safe_post
from utils.logger import get_logger
from wp_client import WordPressClient

logger = get_logger(__name__)

_DISCLOSURE_MARKER = '<p style="font-size:12px;color:#888;margin:24px 0 0;'


def _fetch_all_posts(wp: WordPressClient) -> list:
    posts, page = [], 1
    while True:
        resp = safe_get(
            wp._api_url("wp/v2/posts"),
            headers=wp._auth_header(),
            params={
                "per_page": 50,
                "page": page,
                "status": "publish",
                "context": "edit",
                "_fields": "id,date,title,content",
            },
            timeout=30,
        )
        if resp is None or resp.status_code != 200:
            break
        batch = resp.json()
        posts.extend(batch)
        if len(batch) < 50:
            break
        page += 1
    return posts


def _with_footer(raw: str, site: str, post_date: str) -> str:
    if "source-footer" in raw:
        return raw
    footer = build_source_footer(site, post_date)
    idx = raw.rfind(_DISCLOSURE_MARKER)
    if idx == -1:
        return raw + "\n" + footer
    return raw[:idx] + footer + "\n" + raw[idx:]


def backfill(site: str, dry_run: bool) -> None:
    wp = WordPressClient(site)
    if not wp.is_configured:
        return
    changed = unchanged = failed = 0
    for post in _fetch_all_posts(wp):
        raw = post.get("content", {}).get("raw", "")
        info_date = post["date"][:10].replace("-", ".")
        new = _with_footer(add_calculator_disclaimer(raw), site, info_date)
        if new == raw:
            unchanged += 1
            continue
        if dry_run:
            changed += 1
            continue
        resp = safe_post(
            wp._api_url(f"wp/v2/posts/{post['id']}"),
            headers={**wp._auth_header(), "Content-Type": "application/json"},
            data=json.dumps({"content": new}),
            timeout=30,
        )
        if resp is not None and resp.status_code in (200, 201):
            changed += 1
        else:
            failed += 1
            logger.warning("[Site %s] #%s 갱신 실패", site, post["id"])
    logger.info("[Site %s] 갱신 %s / 변경없음 %s / 실패 %s (dry_run=%s)", site, changed, unchanged, failed, dry_run)


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    for key in ("A", "B", "C"):
        backfill(key, dry)
