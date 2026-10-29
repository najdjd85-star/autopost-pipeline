"""쿠팡 링크 은행: 한국 IP(데스크탑)에서 만든 상품 딥링크를 서버가 가져다 쓴다.

서버는 해외 IP라 쿠팡 Open API가 접속을 거절한다("Access denied" 웹페이지가 옴). 그래서
- 데스크탑이 하루 한 번 scripts/refresh_coupang_links.py로 상품 링크를 만들어
  gov 사이트의 비공개 워드프레스 페이지(slug=coupang-link-bank)에 JSON으로 저장하고,
- 서버는 쿠팡 API 호출이 실패했을 때 이 페이지에서 링크를 꺼내 쓴다(6시간 캐시).
7일이 지난 항목은 쓰지 않고 기존의 "쿠팡 홈" 고정 링크로 대체된다. 가격은 금방 바뀌므로 저장하지 않는다.
"""
from __future__ import annotations

import json
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from affiliate_topics import all_topic_queries, must_for, name_matches, queries_for
from config import OUTPUT_DIR
from utils.http import safe_get, safe_post
from utils.logger import get_logger
from wp_client import WordPressClient

logger = get_logger(__name__)

BANK_SITE = "A"
BANK_PAGE_SLUG = "coupang-link-bank"
BANK_MAX_AGE_DAYS = 7
CACHE_TTL_SECONDS = 6 * 3600
CACHE_PATH = OUTPUT_DIR / "coupang_bank_cache.json"
PROBE_PATH = OUTPUT_DIR / "coupang_probes.json"  # [데스크탑] 유효기간 측정용 표본 링크
CHECK_LOG = OUTPUT_DIR / "coupang_link_check.log"
PROBE_KEEP_DAYS = 14
API_CALL_GAP_SECONDS = 7.0  # 쿠팡 검색 API 호출 한도(분당 약 10회)를 넉넉히 지킨다

# 사이트별 상품 검색어. life(통신/렌탈)는 글 주제와 맞는 상품이 많고, gov/tax는 무난한 생활용품 위주.
QUERIES: Dict[str, List[str]] = {
    "A": ["문서 보관함", "서류 파일 정리", "가계부", "공학용 계산기"],
    "B": [
        "공기청정기", "안마의자", "정수기", "와이파이 공유기", "보조배터리",
        "무선 충전기", "스마트폰 거치대", "해외여행 멀티어댑터", "무선 이어폰", "휴대폰 케이스",
    ],
    "C": ["가계부", "문서 보관함", "공학용 계산기", "재테크 도서"],
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _find_page(wp: WordPressClient) -> Optional[Dict[str, Any]]:
    resp = safe_get(
        wp._api_url("wp/v2/pages"),
        headers=wp._auth_header(),
        params={"slug": BANK_PAGE_SLUG, "status": "private,publish,draft", "context": "edit"},
        timeout=20,
    )
    if resp is not None and resp.status_code == 200 and resp.json():
        return resp.json()[0]
    return None


def load_remote_bank() -> Optional[Dict[str, Any]]:
    """비공개 페이지에서 은행 JSON을 읽는다(인증 필요). 실패하면 None."""
    wp = WordPressClient(BANK_SITE)
    if not wp.is_configured:
        return None
    page = _find_page(wp)
    if not page:
        return None
    raw = page.get("content", {}).get("raw", "")
    try:
        return json.loads(raw)
    except ValueError:
        logger.warning("쿠팡 링크 은행 페이지 내용을 JSON으로 읽지 못했습니다.")
        return None


def publish_bank(bank: Dict[str, Any]) -> bool:
    wp = WordPressClient(BANK_SITE)
    if not wp.is_configured:
        return False
    page = _find_page(wp)
    url = wp._api_url(f"wp/v2/pages/{page['id']}") if page else wp._api_url("wp/v2/pages")
    resp = safe_post(
        url,
        headers={**wp._auth_header(), "Content-Type": "application/json"},
        data=json.dumps(
            {
                "title": "(내부용) 쿠팡 링크 은행",
                "slug": BANK_PAGE_SLUG,
                "status": "private",
                "content": json.dumps(bank, ensure_ascii=False),
            }
        ),
        timeout=30,
    )
    return resp is not None and resp.status_code in (200, 201)


def check_link(url: str) -> Dict[str, Any]:
    """딥링크가 아직 쿠팡 페이지로 리다이렉트되는지 본다(클릭이 아니라 응답 헤더만 확인)."""
    resp = safe_get(url, allow_redirects=False, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
    if resp is None:
        return {"ok": False, "detail": "no_response"}
    location = resp.headers.get("Location", "")
    ok = resp.status_code in (301, 302, 303, 307, 308) and "coupang.com" in location
    return {"ok": ok, "detail": f"{resp.status_code} -> {location[:70]}"}


def run_probes(today_items: Optional[List[Dict[str, Any]]] = None) -> int:
    """[데스크탑] today_items가 None이면 예전 표본 링크가 아직 열리는지 점검해 로그를 남기고 서버가 믿어도 되는
    최대 연령(일)을 돌려준다. 리스트를 주면 점검 없이 오늘 만든 링크 일부를 새 표본으로 등록만 한다."""
    try:
        probes = json.loads(PROBE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        probes = []

    max_age = BANK_MAX_AGE_DAYS
    kept: List[Dict[str, Any]] = []
    lines: List[str] = []
    for probe in probes:
        try:
            age_hours = (_now() - datetime.fromisoformat(probe["generated_at"])).total_seconds() / 3600
        except (KeyError, ValueError):
            continue
        if age_hours > PROBE_KEEP_DAYS * 24:
            continue
        if today_items is not None:
            kept.append(probe)
            continue
        result = check_link(probe["url"])
        lines.append(f"{_now().isoformat(timespec='seconds')} age={age_hours:.0f}h ok={result['ok']} {result['detail']}")
        if not result["ok"] and age_hours >= 6:
            max_age = min(max_age, max(1, int(age_hours // 24) - 1) if age_hours >= 24 else 1)
        kept.append(probe)

    # 오늘 만든 링크 중 2개를 새 표본으로 추가(이미 오늘 표본이 있으면 건너뜀)
    today = _now().date().isoformat()
    if today_items and not any(p.get("generated_at", "").startswith(today) for p in kept):
        for item in today_items[:2]:
            kept.append({"url": item["url"], "generated_at": item["generated_at"]})

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        PROBE_PATH.write_text(json.dumps(kept, ensure_ascii=False), encoding="utf-8")
        if lines:
            with CHECK_LOG.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
    except OSError:
        pass
    logger.info("쿠팡 링크 유효성 표본 %s개 점검, 서버 사용 한도 %s일", len(lines), max_age)
    return max_age


def refresh_bank() -> Dict[str, int]:
    """[데스크탑에서 실행] 모든 검색어의 상품 링크를 새로 만들어 업로드한다."""
    from constants import COUPANG_API_ENABLED

    if not COUPANG_API_ENABLED:  # 제휴 명의 변경: 새 계정 API 키가 나올 때까지 갱신하지 않는다(옛 계정 호출 방지)
        logger.info("쿠팡 API 사용 꺼짐(COUPANG_API_ENABLED=0): 링크 은행 갱신을 건너뜁니다.")
        return {"made": 0, "kept": 0, "failed": 0, "uploaded": 0, "skipped": 1}

    from smart_affiliate_matcher import (  # 순환 임포트 방지용 지연 임포트
        build_coupang_deeplink,
        coupang_blocked_minutes,
        coupang_calls_left,
    )

    all_queries = dict(QUERIES)
    all_queries["T"] = all_topic_queries()  # 글 주제별(독자가 살 만한) 상품 - affiliate_topics.py
    needed = sum(len(q) for q in all_queries.values())
    blocked = coupang_blocked_minutes()
    if blocked or coupang_calls_left() < needed:
        # 한도를 넘기면 쿠팡이 경고를 세고 3회 초과 시 파트너스 이용을 제한하므로, 모자라면 한 건도 보내지 않고 끝낸다.
        logger.warning(
            "쿠팡 호출 한도 보호: 이번 갱신에 %s회가 필요하지만 지금은 %s회만 보낼 수 있어 건너뜁니다(%s).",
            needed, coupang_calls_left(), f"차단 해제까지 약 {blocked}분" if blocked else "최근 1시간 호출 기록 때문",
        )
        return {"made": 0, "kept": 0, "failed": 0, "uploaded": 0, "skipped": 1}

    previous = load_remote_bank() or {}
    max_age_days = run_probes()  # 예전 표본 먼저 점검(오늘 표본은 아래에서 추가)
    bank: Dict[str, Any] = {
        "generated_at": _now().isoformat(timespec="seconds"),
        "max_age_days": max_age_days,
        "sites": {},
    }
    made = kept = failed = 0
    first_call = True

    for site, queries in all_queries.items():
        old_items = {i.get("query"): i for i in previous.get("sites", {}).get(site, [])}
        items: List[Dict[str, Any]] = []
        for query in queries:
            if coupang_blocked_minutes():  # 도중에 한도 초과 응답이 오면 즉시 멈추고 이전 항목을 유지
                if query in old_items and name_matches(old_items[query].get("name", ""), must_for(query)):
                    items.append(old_items[query])
                    kept += 1
                else:
                    failed += 1
                continue
            if not first_call:
                time.sleep(API_CALL_GAP_SECONDS)
            first_call = False
            product = build_coupang_deeplink(query, must=must_for(query))  # 주제 검색어는 상품 이름이 검색어와 맞는지 확인
            if product and product.get("url"):
                items.append(
                    {
                        "query": query,
                        "name": product.get("name", query),
                        "url": product["url"],
                        "image": product.get("image", ""),
                        "generated_at": _now().isoformat(timespec="seconds"),
                    }
                )
                made += 1
            elif query in old_items and name_matches(old_items[query].get("name", ""), must_for(query)):
                items.append(old_items[query])  # 이번에 실패하면 이전 항목을 유지(7일 한도 안에서만 쓰임) - 단, 상품이 검색어와 맞을 때만
                kept += 1
            else:
                failed += 1
        bank["sites"][site] = items

    if made == 0:
        logger.warning("쿠팡 API 호출이 전부 실패해 업로드하지 않습니다(이 PC도 막혔는지 확인하세요).")
        return {"made": made, "kept": kept, "failed": failed, "uploaded": 0}

    all_items = [i for items in bank["sites"].values() for i in items if i.get("generated_at", "").startswith(_now().date().isoformat())]
    run_probes(all_items)  # 오늘 만든 링크 중 일부를 내일부터 점검할 표본으로 등록
    uploaded = 1 if publish_bank(bank) else 0
    return {"made": made, "kept": kept, "failed": failed, "uploaded": uploaded}


# ---------------------------------------------------------------------------
# 서버 쪽: 은행에서 상품 꺼내기
# ---------------------------------------------------------------------------
def _load_bank_cached() -> Optional[Dict[str, Any]]:
    cached: Optional[Dict[str, Any]] = None
    try:
        cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cached = None

    if cached and time.time() - cached.get("fetched_at", 0) < CACHE_TTL_SECONDS:
        return cached.get("bank")

    bank = load_remote_bank()
    if bank is not None:
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_text(
                json.dumps({"fetched_at": time.time(), "bank": bank}, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass
        return bank
    return cached.get("bank") if cached else None  # 원격 조회가 실패하면 낡은 캐시라도 7일 한도 안에서 사용


def pick_product(site: str, keyword: str) -> Optional[Dict[str, str]]:
    """사이트 은행에서 키워드와 맞는 상품을 고른다. 맞는 게 없으면 그 사이트의 아무 상품, 없으면 None."""
    from constants import COUPANG_API_ENABLED

    if not COUPANG_API_ENABLED:  # 옛 계정으로 만든 링크가 은행에 남아 있어도 쓰지 않는다
        return None
    try:
        bank = _load_bank_cached()
    except Exception as exc:  # noqa: BLE001 - 은행 조회 실패가 글 발행을 막으면 안 된다
        logger.info("쿠팡 링크 은행 조회 실패(무시): %s", exc)
        return None
    if not bank:
        return None

    cutoff = _now() - timedelta(days=min(BANK_MAX_AGE_DAYS, int(bank.get("max_age_days", BANK_MAX_AGE_DAYS))))

    def _fresh(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for item in items:
            try:
                if datetime.fromisoformat(item["generated_at"]) >= cutoff and item.get("url"):
                    out.append(item)
            except (KeyError, ValueError):
                continue
        return out

    # 글 주제에 맞는 독자용 상품이 있으면 그것을 먼저 쓴다(예: 교육급여 글 -> 학부모용 책가방·학용품)
    topic_queries = set(queries_for(keyword))
    if topic_queries:
        topical = [i for i in _fresh(bank.get("sites", {}).get("T", [])) if i.get("query") in topic_queries]
        if topical:
            chosen = random.choice(topical)
            return {"name": chosen.get("name", ""), "url": chosen["url"], "image": chosen.get("image", ""), "price": ""}

    fresh = _fresh(bank.get("sites", {}).get(site, []))
    if not fresh:
        return None

    keyword_tokens = set((keyword or "").split())
    matched = [i for i in fresh if i["query"] in (keyword or "") or keyword_tokens & set(i["query"].split())]
    chosen = random.choice(matched or fresh)
    return {"name": chosen.get("name", ""), "url": chosen["url"], "image": chosen.get("image", ""), "price": ""}
