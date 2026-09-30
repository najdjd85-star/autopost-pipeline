"""
이미 발행된 글들의 이미지(alt=원래 프롬프트, src=이미지 URL)를 읽어서
이미지 캐시(data/image_cache/{site}.json)를 채워 넣는 일회성 스크립트.

언제 쓰나: image_hybrid_engine의 캐싱 로직이 배포되기 전에 만들어진 이미지들도
캐시 재사용 대상에 포함시키고 싶을 때. 정상 파이프라인(process_image_slots)을
거치지 않고 만들어진 이미지(예: 일괄 재생성 스크립트로 만든 이미지)는 캐시에
자동으로 안 들어가므로, 이 스크립트로 사후에 채워 넣는다.

사용법:
    venv/bin/python scripts/seed_image_cache.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wp_client import WordPressClient
from utils.http import safe_get
from image_hybrid_engine import add_to_image_cache, _cache_path

_IMG_SRC_ALT = re.compile(r'<img[^>]*src="([^"]+)"[^>]*alt="([^"]*)"')
_IMG_ALT_SRC = re.compile(r'<img[^>]*alt="([^"]*)"[^>]*src="([^"]+)"')


def main() -> None:
    for site in ["A", "B", "C"]:
        wp = WordPressClient(site)
        if not wp.is_configured:
            print(f"Site {site}: 워드프레스 미설정 - 건너뜁니다.")
            continue

        if _cache_path(site).exists():
            _cache_path(site).unlink()

        all_posts = []
        page = 1
        while True:
            resp = safe_get(
                wp._api_url("wp/v2/posts"),
                headers=wp._auth_header(),
                params={"per_page": 100, "page": page, "status": "publish", "context": "edit"},
                timeout=20,
            )
            if resp is None or resp.status_code != 200:
                break
            data = resp.json()
            if not data:
                break
            all_posts.extend(data)
            if len(data) < 100:
                break
            page += 1

        count = 0
        for p in all_posts:
            content = p["content"]["raw"]
            pairs = _IMG_SRC_ALT.findall(content)
            if not pairs:
                pairs = [(src, alt) for alt, src in _IMG_ALT_SRC.findall(content)]
            for src, alt in pairs:
                if "gemini_" in src and alt:
                    add_to_image_cache(site, alt, src)
                    count += 1

        print(f"Site {site}: {count}개 캐시 항목 생성")


if __name__ == "__main__":
    main()
