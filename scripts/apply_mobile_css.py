"""세 WordPress 사이트의 전역 스타일(사용자 CSS)에 모바일 최적화 CSS를 넣는다 (멱등, 기존 사용자 CSS는 보존).

실행: venv/bin/python scripts/apply_mobile_css.py [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from mobile_css import CSS_MARKER, MOBILE_CSS
from utils.http import safe_get
from utils.logger import get_logger
from wp_client import WordPressClient

logger = get_logger(__name__)


def _global_styles_url(wp: WordPressClient) -> str:
    resp = safe_get(wp._api_url("wp/v2/themes"), headers=wp._auth_header(), params={"status": "active"}, timeout=20)
    links = resp.json()[0]["_links"]
    return next(v[0]["href"] for k, v in links.items() if "global-styles" in k)


def apply(site: str, dry: bool = False) -> bool:
    wp = WordPressClient(site)
    if not wp.is_configured:
        logger.warning("[Site %s] WordPress 설정이 없어 건너뜁니다.", site)
        return False
    url = _global_styles_url(wp)
    current = safe_get(url, headers=wp._auth_header(), params={"context": "edit"}, timeout=20).json()
    styles = dict(current.get("styles") or {})
    css = styles.get("css") or ""
    if CSS_MARKER in css:  # 예전 버전이 있으면 그 부분만 교체한다
        css = css[: css.index(CSS_MARKER)].rstrip()
    styles["css"] = (css + "\n" if css else "") + MOBILE_CSS
    if dry:
        logger.info("[Site %s] (dry) %s 에 CSS %s자 적용 예정", site, url, len(styles["css"]))
        return True
    resp = requests.post(
        url,
        headers={**wp._auth_header(), "Content-Type": "application/json"},
        json={"styles": styles},
        timeout=30,
    )
    ok = resp.status_code == 200 and CSS_MARKER in ((resp.json().get("styles") or {}).get("css") or "")
    logger.info("[Site %s] 모바일 CSS 적용 %s (HTTP %s)", site, "성공" if ok else "실패", resp.status_code)
    return ok


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    results = {s: apply(s, dry) for s in "ABC"}
    print(results)
    sys.exit(0 if all(results.values()) else 1)
