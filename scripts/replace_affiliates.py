"""기존 글의 옛 제휴 카드(쿠팡 API·링크프라이스·애드픽)를 모두 빼고, 새 쿠팡 파트너스 고정 링크 카드 1장으로 바꾼다.

제휴 명의 변경(2026-10)에 따른 일회성 작업이다. 고정 링크는 coupang_static.py.
- 기본은 드라이런(아무것도 고치지 않고 건수만 보고). 실제 반영은 --apply.
- 고치기 전 원문은 data/output/affiliate_backup_<사이트>.json에 저장한다(되돌리기용).
- 카드가 있던 글(또는 제휴 고지 문단이 있던 글)만 고친다. 카드 자리는 옛 카드가 있던 곳(여러 개면 첫 번째 자리)이다.

실행: venv/bin/python scripts/replace_affiliates.py [--apply] [--site A]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import OUTPUT_DIR
from constants import COUPANG_DISCLOSURE_TEXT, FTC_DISCLOSURE_TEXT
from smart_affiliate_matcher import build_affiliate_card
from utils.http import safe_get
from utils.logger import get_logger
from wp_client import WordPressClient

logger = get_logger(__name__)

CARD_START = re.compile(r'<div class="affiliate-card\b')
DIV_TAG = re.compile(r"<div\b|</div>")
DISCLOSURE_RE = re.compile(r'<p style="font-size:12px;color:#888;margin:24px 0 0;[^>]*>(.*?)</p>', re.DOTALL)
AFFILIATE_HOST_RE = re.compile(r'href="[^"]*(?:coupang|coupa\.ng|adpick|linkprice|lptag)[^"]*"', re.IGNORECASE)
NEW_LINK_RE = re.compile(r"link\.coupang\.com/a/iet")
LINK_BANK_TITLES = ("Coupang links data",)


def strip_cards(raw: str) -> Tuple[str, int, Optional[int]]:
    """affiliate-card div를 짝이 맞는 곳까지 통째로 지운다. (새 글, 지운 개수, 첫 카드 자리)를 돌려준다."""
    out, pos, removed, first = [], 0, 0, None
    while True:
        m = CARD_START.search(raw, pos)
        if not m:
            out.append(raw[pos:])
            break
        depth, end = 0, None
        for t in DIV_TAG.finditer(raw, m.start()):
            depth += 1 if t.group().startswith("<div") else -1
            if depth == 0:
                end = t.end()
                break
        if end is None:  # 짝이 안 맞으면 건드리지 않는다
            out.append(raw[pos:])
            break
        out.append(raw[pos:m.start()])
        if first is None:
            first = sum(len(x) for x in out)
        pos = end
        removed += 1
        while raw[pos:pos + 1] == "\n":  # 카드 뒤 빈 줄 정리
            pos += 1
    return "".join(out), removed, first


def disclosure_html() -> str:
    return (
        '<p style="font-size:12px;color:#888;margin:24px 0 0;line-height:1.6;">'
        f"{FTC_DISCLOSURE_TEXT}<br>{COUPANG_DISCLOSURE_TEXT}</p>"
    )


def transform(raw: str, title: str, site: str, post_id: int) -> Tuple[Optional[str], dict]:
    """새 원문과 보고용 정보를 돌려준다. 고칠 게 없으면 (None, 정보)."""
    info = {"cards": 0, "disclosure": 0}
    if NEW_LINK_RE.search(raw) and not CARD_START.search(raw):
        return None, info  # 이미 바꾼 글
    body, removed, first = strip_cards(raw)
    info["cards"] = removed

    def drop_disclosure(m: "re.Match[str]") -> str:
        text = m.group(1)
        if any(w in text for w in ("제휴", "쿠팡", "커미션", "링크프라이스")):
            info["disclosure"] += 1
            return ""
        return m.group(0)

    body = DISCLOSURE_RE.sub(drop_disclosure, body)
    if not removed and not info["disclosure"]:
        return None, info  # 제휴와 상관없는 글/페이지
    card = build_affiliate_card(site, "bot", post_id, title)
    if not card.strip():
        return None, info
    if first is not None and first <= len(body):
        body = body[:first] + card + "\n" + body[first:]
    elif '<div class="source-footer"' in body:
        i = body.index('<div class="source-footer"')
        body = body[:i] + card + "\n" + body[i:]
    else:
        body = body.rstrip() + "\n" + card
    body = body.rstrip() + "\n" + disclosure_html()
    info["leftover"] = AFFILIATE_HOST_RE.findall(re.sub(r"https://link\.coupang\.com/a/iet\w+", "", body))
    return body, info


def fetch_all(wp: WordPressClient) -> List[Tuple[str, dict]]:
    items: List[Tuple[str, dict]] = []
    for kind in ("posts", "pages"):
        page = 1
        while True:
            resp = safe_get(
                wp._api_url(f"wp/v2/{kind}"),
                headers=wp._auth_header(),
                params={"per_page": 50, "page": page, "status": "publish,draft,private,pending,future",
                        "context": "edit", "_fields": "id,status,title,content,link"},
                timeout=40,
            )
            if resp is None or resp.status_code != 200:
                break
            batch = resp.json()
            items += [(kind, p) for p in batch]
            if len(batch) < 50:
                break
            page += 1
    return items


def _push(wp: WordPressClient, kind: str, post_id: int, content: str) -> bool:
    import requests

    r = requests.post(
        wp._api_url(f"wp/v2/{kind}/{post_id}"),
        headers={**wp._auth_header(), "Content-Type": "application/json"},
        json={"content": content},
        timeout=60,
    )
    return r.status_code == 200


def run(site: str, apply: bool) -> dict:
    wp = WordPressClient(site)
    if not wp.is_configured:
        return {}
    items = fetch_all(wp)
    plan, skipped, left = [], 0, []
    for kind, p in items:
        title = (p.get("title") or {}).get("raw", "")
        if title in LINK_BANK_TITLES:
            continue
        raw = (p.get("content") or {}).get("raw", "")
        new, info = transform(raw, title, site, p["id"])
        if new is None:
            skipped += 1
            continue
        if info.get("leftover"):
            left.append((p["id"], info["leftover"][:2]))
        plan.append({"kind": kind, "id": p["id"], "title": title, "raw": raw, "new": new, "info": info})
        logger.info("[%s] %s %s: 카드 %s개·고지 %s곳 교체 - %s", site, kind, p["id"], info["cards"], info["disclosure"], title[:30])
    failed = 0
    if apply and plan:
        path = OUTPUT_DIR / f"affiliate_backup_{site}.json"  # 고치기 전에 원문부터 저장한다(되돌리기용)
        path.write_text(json.dumps([{k: v for k, v in e.items() if k not in ("new", "info")} for e in plan], ensure_ascii=False), encoding="utf-8")
        for e in plan:
            if not _push(wp, e["kind"], e["id"], e["new"]):
                failed += 1
                logger.warning("[%s] %s %s 반영 실패", site, e["kind"], e["id"])
    return {"items": len(items), "changed": len(plan), "skipped": skipped, "failed": failed, "leftover": left}


if __name__ == "__main__":
    do_apply = "--apply" in sys.argv
    only = sys.argv[sys.argv.index("--site") + 1] if "--site" in sys.argv else None
    for s in "ABC":
        if only and s != only:
            continue
        print(s, run(s, do_apply), "(반영함)" if do_apply else "(드라이런)")
