"""이미 발행한 글 정리(1회성, 여러 번 돌려도 같은 결과).

- 작성 과정의 말(페르소나·상식 깨기·레퍼런스)과 출처 없는 일반화 문장을 뺀다(content_guard.clean_html).
- 정부지원금(A)·세금(C) 글에서 주제와 상관없는 쿠팡 상품 카드를 뺀다.
- 글 끝에 같은 사이트의 '함께 보면 좋은 글' 3개를 붙인다(없을 때만).

실행: venv/Scripts/python.exe scripts/clean_posts.py          (바꿀 내용만 보여 줌)
      venv/Scripts/python.exe scripts/clean_posts.py --apply  [--relink: 관련 글 블록 다시 만들기]  (원문을 data/output/clean_backup_<사이트>.json에 저장한 뒤 반영)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import content_guard  # noqa: E402
from config import OUTPUT_DIR  # noqa: E402
from utils.http import safe_get  # noqa: E402
from wp_client import WordPressClient  # noqa: E402


def all_posts(wp: WordPressClient) -> list:
    out, page = [], 1
    while True:
        resp = safe_get(wp._api_url("wp/v2/posts"), headers=wp._auth_header(),
                        params={"per_page": 100, "page": page, "context": "edit", "status": "publish,future"}, timeout=40)
        if resp is None or resp.status_code != 200 or not resp.json():
            break
        out += resp.json()
        page += 1
    return out


def main(apply: bool, relink: bool = False) -> None:
    for site in ("A", "B", "C"):
        wp = WordPressClient(site)
        posts = all_posts(wp)
        backup = OUTPUT_DIR / f"clean_backup_{site}.json"
        if apply and not backup.exists():
            backup.write_text(json.dumps({p["id"]: p["content"]["raw"] for p in posts}, ensure_ascii=False), encoding="utf-8")
        stats = {"글": len(posts), "바뀜": 0, "작성용 말": 0, "뺀 문장": 0, "상품 카드": 0, "관련 글": 0}
        for p in posts:
            raw = p["content"]["raw"]
            title = p["title"]["raw"]
            new, rep = content_guard.clean_html(raw, title)
            stats["작성용 말"] += bool(rep["leaks"])
            stats["뺀 문장"] += len(rep["claims"])
            for s in rep["claims"][:2]:
                print(f"  [{site} {p['id']}] 뺌: {s[:120]}")
            if site in ("A", "C"):
                new, n = content_guard.strip_affiliate_cards(new)
                stats["상품 카드"] += n
            if relink:  # 제목이 바뀐 글이 있을 때: 붙여 둔 관련 글 블록을 새로 만든다
                new = re.sub(r'<div class="related-posts".*?</ul></div>\n?', "", new, flags=re.S)
            if "related-posts" not in new:
                items = content_guard.related_posts(posts_view(posts), title, title, exclude_link=p["link"])
                block = content_guard.related_block(items)
                at = new.find('<div class="source-footer"')
                new = new[:at] + block + "\n" + new[at:] if at > 0 else new + "\n" + block
                stats["관련 글"] += 1
            if new != raw:
                stats["바뀜"] += 1
                if apply:
                    ok = wp.update_post(p["id"], content=new)
                    if not ok:
                        print(f"  [{site} {p['id']}] 반영 실패")
        print(site, stats)


def posts_view(posts: list) -> list:
    return [{"title": {"rendered": p["title"]["raw"]}, "link": p["link"]} for p in posts if p.get("status") == "publish"]


if __name__ == "__main__":
    main("--apply" in sys.argv, "--relink" in sys.argv)
