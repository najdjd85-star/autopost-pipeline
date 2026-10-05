"""기존 글의 이미지 캡션에 노출된 내부 식별자("출처: google-ai-studio" 등)를 사람이 읽는 문구로 바꾼다 (멱등).

실행: venv/bin/python scripts/backfill_image_captions.py [--dry-run]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backfill_post_footers import _fetch_all_posts
from utils.http import safe_post
from utils.logger import get_logger
from wp_client import WordPressClient

logger = get_logger(__name__)

_PATTERN = re.compile(r"출처:\s*(google-ai-studio|flux|pollinations-ai|pexels)")


def _replace(match: "re.Match[str]") -> str:
    return "사진: Pexels" if match.group(1) == "pexels" else "AI 생성 이미지"


def run(site: str, dry_run: bool) -> None:
    wp = WordPressClient(site)
    changed = failed = 0
    for post in _fetch_all_posts(wp):
        raw = post.get("content", {}).get("raw", "")
        new = _PATTERN.sub(_replace, raw)
        if new == raw:
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
    logger.info("[Site %s] 캡션 갱신 %s / 실패 %s (dry_run=%s)", site, changed, failed, dry_run)


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    for key in ("A", "B", "C"):
        run(key, dry)
