"""
위치별(top/mid/bot) 서브ID 추적 및 CPA/쿠팡 스마트 제휴 링크 주입 엔진.

generator.py가 만든 html_content 안의 AFFILIATE_SLOT_TOP/MID/BOT 플레이스홀더를
사이트별(A/B/C) 제휴 링크 카드로 치환한다. 쿠팡 파트너스 Open API 키가 설정된
경우 문맥 연관 상품 딥링크 카드를 추가로 렌더링한다.

이 모듈은 config/constants에만 의존하는 Layer 1 모듈이며, 다른 어떤
프로젝트 모듈도 임포트하지 않는다.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote, urlencode

from config import BASE_DIR, OUTPUT_DIR, get_site, settings
from affiliate_topics import must_for, queries_for
from coupang_link_bank import pick_product
from coupang_static import pick_static_product
from constants import (
    AFFILIATE_SLOT_BOT,
    AFFILIATE_SLOT_MID,
    CALCULATOR_DISCLAIMER_TEXT,
    AFFILIATE_SLOT_TOP,
    COUPANG_API_ENABLED,
    COUPANG_DISCLOSURE_TEXT,
    FTC_DISCLOSURE_TEXT,
    SITE_SOURCES,
)
from utils.http import safe_get
from utils.logger import get_logger

logger = get_logger(__name__)

REL_ATTR = "sponsored nofollow noopener noreferrer"

_SLOT_TOKEN_TO_NAME = {
    AFFILIATE_SLOT_TOP: "top",
    AFFILIATE_SLOT_MID: "mid",
    AFFILIATE_SLOT_BOT: "bot",
}

_SLOT_LABELS = {
    "top": "🔥 지금 바로 확인하기",
    "mid": "📊 내 조건으로 비교해보기",
    "bot": "✅ 놓치기 전에 신청하기",
}

COUPANG_DOMAIN = "https://api-gateway.coupang.com"

# 쿠팡은 시간당 호출 한도를 넘기면 경고를 세고, 3회 초과하면 파트너스 이용을 제한한다. 그래서 호출 기록을 파일에 남겨
# (프로세스를 다시 켜도 이어지게) 한 시간에 보낼 수 있는 횟수를 막고, 한도 초과 응답이 한 번이라도 오면 일정 시간 호출을 끊는다.
COUPANG_GUARD_PATH = OUTPUT_DIR / "coupang_api_guard.json"
COUPANG_MAX_CALLS_PER_HOUR = 50  # 링크 갱신 1회(약 46개 검색어)가 한 시간 안에 두 번 나가지 못하게 하는 상한
COUPANG_MAX_CALLS_PER_DAY = int(os.environ.get("COUPANG_MAX_CALLS_PER_DAY", "60"))  # 하루 1회 갱신(46회) + 여유. 하루에 여러 번 돌려도 총량이 넘지 않게
# 하루 상한의 '하루'는 24시간이 아니라 20시간이다: 매일 같은 시각(19시)에 도는 정기 갱신이 어제 호출(늦게 끝났거나 늦게 시작한 경우 포함) 때문에
# 건너뛰어지지 않게 한다. 같은 날 여러 번 돌리는 것만 막으면 된다.
COUPANG_DAY_WINDOW_SECONDS = 20 * 3600
COUPANG_COOLDOWN_SECONDS = 3 * 3600
_RATE_LIMIT_WORDS = ("초과", "제한", "too many", "rate limit")


def _guard_load() -> Dict[str, object]:
    try:
        data = json.loads(COUPANG_GUARD_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    now = time.time()
    calls = [t for t in data.get("calls", []) if isinstance(t, (int, float)) and now - t < COUPANG_DAY_WINDOW_SECONDS]  # 하루 상한까지 세려고 20시간치를 남긴다
    return {"calls": calls, "blocked_until": float(data.get("blocked_until", 0) or 0)}


def _guard_save(state: Dict[str, object]) -> None:
    try:
        COUPANG_GUARD_PATH.parent.mkdir(parents=True, exist_ok=True)
        COUPANG_GUARD_PATH.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


def coupang_calls_left() -> int:
    """지금 보낼 수 있는 쿠팡 API 호출 수. 한도 초과로 호출을 끊어 둔 동안에는 0."""
    state = _guard_load()
    if state["blocked_until"] > time.time():
        return 0
    now = time.time()
    last_hour = sum(1 for t in state["calls"] if now - t < 3600)
    return max(0, min(COUPANG_MAX_CALLS_PER_HOUR - last_hour, COUPANG_MAX_CALLS_PER_DAY - len(state["calls"])))


def coupang_blocked_minutes() -> int:
    """한도 초과 응답을 받아 호출을 끊어 둔 경우 남은 분. 아니면 0."""
    remaining = _guard_load()["blocked_until"] - time.time()
    return int(remaining // 60) + 1 if remaining > 0 else 0


def _guard_note_call() -> None:
    state = _guard_load()
    state["calls"].append(time.time())
    _guard_save(state)


def _guard_note_rate_limited() -> None:
    state = _guard_load()
    state["blocked_until"] = time.time() + COUPANG_COOLDOWN_SECONDS
    _guard_save(state)
    logger.warning("쿠팡 호출 한도 초과 응답을 받아 %s시간 동안 쿠팡 API 호출을 멈춥니다.", COUPANG_COOLDOWN_SECONDS // 3600)

def build_utm_link(base_url: str, slot: str, post_id: int) -> str:
    """제휴 링크에 위치별 서브ID 추적 파라미터를 결합한다."""
    if not base_url:
        return ""
    params = {
        "utm_source": "blog",
        "utm_medium": "affiliate",
        "utm_content": slot,
        "sub_id": f"post_{post_id}",
    }
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode(params)}"


def _pick_site_affiliate_url(site: str) -> Optional[str]:
    """사이트별 제휴 카테고리 중 하나를 대표 링크로 선택한다 (get_primary_affiliate_link 전용)."""
    return None  # 제휴 명의 변경: 쿠팡 고정 링크 외의 제휴 링크는 쓰지 않는다


# 제휴 링크 종류(키)별로 실제 무엇을 확인/신청하는지 명시한 CTA 문구.
# 예전에는 top/mid/bot 위치별로 문구만 다르고 실제 링크는 전부 사이트의
# 첫 번째 제휴 링크 하나로 고정되어 있어서(예: 3개 버튼이 전부 같은 곳으로
# 이동), 버튼 문구와 실제 도착지가 안 맞고 같은 링크가 반복되는 문제가
# 있었다 - 슬롯마다 사이트가 가진 제휴 링크를 돌아가며 배정하고, 그 링크의
# 실제 성격에 맞는 문구를 쓰도록 고쳤다.
_AFFILIATE_KEY_LABELS = {
    "loan": "💳 내 신용점수 무료로 확인하기",
    "welfare": "🔍 내 지원금 자격 미리 확인하기",
    "mvno": "📱 요금제 비교하고 갈아타기",
    "rental": "🔧 우리 동네 전문가 찾기",
    "internet": "📶 와이파이 공유기·인터넷 용품 특가 확인",
    "refund": "💸 숨은 환급액 조회하기",
    "pension": "👴 연금 혜택 확인하기",
}


def _pick_slot_affiliate(site: str, slot: str) -> Tuple[str, Optional[str], str]:
    """슬롯(top/mid/bot) 순서에 맞춰 사이트가 가진 제휴 링크를 하나씩 돌아가며
    배정한다. (제휴 키, URL, 버튼 라벨)을 반환하며, 설정된 제휴 링크가 하나도
    없으면 ("", None, 기본 라벨)을 반환한다."""
    return "", None, _SLOT_LABELS.get(slot, "지금 확인하기")  # 제휴 명의 변경: 사이트별 제휴 링크는 쓰지 않는다


def get_primary_affiliate_link(site: str, slot: str, post_id: int) -> Optional[str]:
    """블로그 본문 슬롯이 아닌 다른 채널(유튜브 설명란 등)에서도 쓸 수 있는,
    사이트 대표 제휴 링크 + 위치별 서브ID 추적 URL을 반환한다. 제휴 링크가
    설정되지 않은 사이트라면 None을 반환한다."""
    base_url = _pick_site_affiliate_url(site)
    if not base_url:
        return None
    return build_utm_link(base_url, slot, post_id)


def _coupang_hmac_signature(
    method: str, url_path: str, query: str, secret_key: str, access_key: str
) -> str:
    """쿠팡 파트너스 Open API HMAC 서명 생성 (CEA algorithm).

    공식 문서 기준 서명 메시지는 datetime + method + path + query 순서로
    전부 이어붙인 문자열이다 (query는 "?" 없이, GET 쿼리 파라미터 포함).
    query를 빼먹으면 서명이 틀어져 조용히 401로 실패한다.
    """
    datetime_gmt = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    message = datetime_gmt + method + url_path + query
    signature = hmac.new(
        secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"


def build_coupang_deeplink(keyword: str, must: Optional[list] = None) -> Optional[Dict[str, str]]:
    """쿠팡 파트너스 Open API로 키워드 연관 상품 딥링크를 생성한다.

    COUPANG_ACCESS_KEY/SECRET_KEY가 없으면 None을 반환한다 (선택 기능).
    must가 있으면 검색 결과 10개 중 상품 이름이 must 조건(affiliate_topics.name_matches)을 만족하는 첫 상품만 쓴다 -
    검색어와 무관한 상품이 첫 결과로 나오는 경우를 걸러낸다. 만족하는 상품이 없으면 None.
    """
    if not COUPANG_API_ENABLED or not settings.coupang_configured:
        return None
    if coupang_calls_left() <= 0:
        logger.info("쿠팡 API 호출 한도 보호로 '%s' 조회를 건너뜁니다.", keyword)
        return None
    _guard_note_call()

    url_path = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
    query = urlencode({"keyword": keyword, "limit": 10 if must else 1})
    full_path = f"{url_path}?{query}"

    try:
        auth_header = _coupang_hmac_signature(
            "GET", url_path, query, settings.coupang_secret_key, settings.coupang_access_key
        )
        resp = safe_get(
            f"{COUPANG_DOMAIN}{full_path}",
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            timeout=8,
        )
        if resp is None or resp.status_code != 200:
            status = getattr(resp, "status_code", "no_response")
            body = getattr(resp, "text", "")[:300] if resp is not None else ""
            logger.info("쿠팡 딥링크 조회 실패 (status=%s): %s", status, body)
            if status == 429 or any(word in body.lower() for word in _RATE_LIMIT_WORDS):
                _guard_note_rate_limited()
            return None
        data = resp.json()
        products = data.get("data", {}).get("productData", [])
        if not products:
            return None
        if must:
            from affiliate_topics import name_matches

            matching = [p for p in products if name_matches(p.get("productName", ""), must)]
            if not matching:
                logger.info("쿠팡 검색 '%s': 상품 이름이 검색어와 맞는 결과가 없어 건너뜁니다.", keyword)
                return None
            products = matching
        product = products[0]
        return {
            "name": product.get("productName", keyword),
            "url": product.get("productUrl", ""),
            "image": product.get("productImage", ""),
            "price": str(product.get("productPrice", "")),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("쿠팡 딥링크 생성 중 오류: %s", exc)
        return None


def _get_coupang_card_data(keyword: str, site: str) -> Optional[Dict[str, str]]:
    """카드에 넣을 쿠팡 상품을 고른다. 새 계정의 API 키가 나오기 전에는 고정 링크(coupang_static.py)만 쓴다.

    COUPANG_API_ENABLED=1이면 API → 링크 은행 순서로 먼저 시도하고, 실패하면 고정 링크로 대체한다.
    """
    if COUPANG_API_ENABLED:
        topic_queries = queries_for(keyword)
        coupang = None
        if topic_queries:
            for query in random.sample(topic_queries, k=len(topic_queries)):
                coupang = build_coupang_deeplink(query, must=must_for(query))
                if coupang and coupang.get("url"):
                    break
        elif keyword:
            coupang = build_coupang_deeplink(keyword)
        if coupang and coupang.get("url"):
            return coupang
        banked = pick_product(site, keyword)
        if banked:
            return banked
    return pick_static_product(keyword)


_BAG_ICON_SVG = (
    '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="#e5533d" '
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M6 8h12l-1 12H7L6 8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/></svg>'
)


def build_affiliate_card(site: str, slot: str, post_id: int, keyword: str = "") -> str:
    """단일 슬롯에 들어갈 제휴 카드 HTML을 생성한다 (고지 문구는 포함하지 않음 -
    글 전체에서 한 번만 보여주면 되므로 inject_affiliate_slots가 마지막에 한 번만 붙인다)."""
    _, base_url, label = _pick_slot_affiliate(site, slot)

    cards: List[str] = []

    if base_url:
        link = build_utm_link(base_url, slot, post_id)
        cards.append(
            f"""
<div class="affiliate-card affiliate-card-{slot}" style="margin:24px 0;padding:20px;
    border-radius:14px;background:linear-gradient(135deg,#eef4ff,#f7f9ff);
    border:1px solid #dbe6ff;text-align:center;">
  <a href="{link}" target="_blank" rel="{REL_ATTR}"
     style="display:inline-block;padding:14px 32px;border-radius:999px;
     background:linear-gradient(90deg,#4f7cff,#7b5cff);color:#fff;
     font-weight:700;font-size:16px;text-decoration:none;">{label}</a>
</div>
""".strip()
        )
    else:
        logger.debug("사이트 %s 슬롯 %s: 제휴 링크 미설정 - 카드 생략", site, slot)

    coupang = _get_coupang_card_data(keyword, site)
    if coupang and coupang.get("url"):
        cp_link = coupang["url"] if coupang.get("static") else build_utm_link(coupang["url"], f"{slot}_coupang", post_id)
        # 실시간 상품 이미지가 있으면 그대로 쓰고, 폴백(고정 링크)이라 이미지가
        # 없으면 빈 자리 대신 아이콘 배지를 넣어 카드가 허전해 보이지 않게 한다.
        if coupang.get("image"):
            image_html = (
                f"""<img src="{coupang['image']}" alt="{coupang.get('name','')}"
       style="width:80px;height:80px;object-fit:cover;border-radius:10px;flex-shrink:0;">"""
            )
        else:
            image_html = (
                f"""<div style="width:56px;height:56px;border-radius:12px;background:#fff0ed;
       display:flex;align-items:center;justify-content:center;flex-shrink:0;">{_BAG_ICON_SVG}</div>"""
            )
        desc_html = (
            f"""<div style="font-size:12px;color:#888;margin-top:2px;">{coupang['desc']}</div>"""
            if coupang.get("desc")
            else ""
        )
        price_html = (
            f"""<div style="font-size:13px;color:#e5533d;font-weight:700;margin-top:4px;">
      {coupang['price']}원</div>"""
            if coupang.get("price")
            else ""
        )
        cards.append(
            f"""
<div class="affiliate-card affiliate-card-coupang" style="margin:16px 0;padding:16px;
    border-radius:14px;background:#fff;border:1px solid #eee;display:flex;
    gap:14px;align-items:center;">
  {image_html}
  <div style="flex:1;text-align:left;">
    <div style="font-size:14px;font-weight:600;color:#222;">{coupang.get('name','')}</div>
    {desc_html}{price_html}
  </div>
  <a href="{cp_link}" target="_blank" rel="{REL_ATTR}"
     style="padding:10px 18px;border-radius:999px;background:#111;color:#fff;
     font-size:13px;font-weight:600;text-decoration:none;white-space:nowrap;">쿠팡에서 보기</a>
</div>
""".strip()
        )

    return "\n".join(cards)


def add_calculator_disclaimer(html: str) -> str:
    """benefit-calc 위젯 바로 아래에 면책 문구를 한 번만 넣는다 (계산기가 없으면 그대로)."""
    if not html or "benefit-calc" not in html or "calc-disclaimer" in html:
        return html

    disclaimer = (
        '<p class="calc-disclaimer" style="font-size:12px;color:#888;margin:8px 0 20px;'
        f'line-height:1.6;">{CALCULATOR_DISCLAIMER_TEXT}</p>\n'
    )
    script_end = html.find("</script>", html.find("benefit-calc"))
    if script_end != -1:
        insert_at = script_end + len("</script>")
        return html[:insert_at] + "\n" + disclaimer + html[insert_at:]
    if AFFILIATE_SLOT_MID in html:
        return html.replace(AFFILIATE_SLOT_MID, disclaimer + AFFILIATE_SLOT_MID, 1)
    return html


def build_source_footer(site: str, info_date: str) -> str:
    links = " · ".join(
        f'<a href="{url}" target="_blank" rel="noopener noreferrer">{name}</a>'
        for name, url in SITE_SOURCES.get(site, ())
    )
    return (
        '<div class="source-footer" style="margin:28px 0 8px;padding:16px 18px;border:1px solid #e5e7eb;'
        'border-radius:12px;background:#fafafa;font-size:13px;line-height:1.8;">'
        f"<strong>📚 참고 출처</strong> · 정보 기준일 {info_date}<br>{links}<br>"
        '<span style="color:#888;">제도와 수치는 바뀔 수 있으니 최신 내용은 위 공식 사이트에서 확인하세요.</span></div>'
    )


def add_source_footer(html: str, site: str, info_date: Optional[str] = None) -> str:
    """글 하단에 공식 출처 박스와 정보 기준일을 한 번만 넣는다 (info_date: YYYY.MM.DD, 기본은 오늘 KST)."""
    if not html or "source-footer" in html or site not in SITE_SOURCES:
        return html
    if info_date is None:
        info_date = datetime.now(timezone(timedelta(hours=9))).strftime("%Y.%m.%d")
    return html + "\n" + build_source_footer(site, info_date)


# 애드센스 심사 기간 동안은 글당 제휴 카드를 3개(top/mid/bot)가 아니라 1개로 제한한다.
# 광고 밀도가 낮아 보이도록 가장 덜 공격적인 위치(글 최하단)만 실제 카드로 채우고
# 나머지 슬롯은 빈 문자열로 치환한다. 승인 후 늘리려면 이 집합에 슬롯 이름을 추가하면 된다.
_ACTIVE_AFFILIATE_SLOTS = {"bot"}


def inject_affiliate_slots(html: str, post_id: int, site: str, keyword: str = "") -> str:
    """html_content 안의 AFFILIATE_SLOT_* 플레이스홀더를 실제 카드로 치환한다.

    슬롯이 top/mid/bot 여러 개라 카드마다 고지 문구를 넣으면 글 하나에 최대
    9번까지 같은 문구가 반복돼 스팸처럼 보인다 - 그래서 각 카드에는 고지
    문구를 넣지 않고, 실제로 제휴 카드가 하나라도 들어간 글이면 본문 맨
    끝에 딱 한 번만 모아서 붙인다.
    """
    if not html:
        return html

    result = add_source_footer(add_calculator_disclaimer(html), site)
    any_affiliate_content = False
    any_coupang_content = False
    for token, slot_name in _SLOT_TOKEN_TO_NAME.items():
        if token in result:
            if slot_name not in _ACTIVE_AFFILIATE_SLOTS:
                result = result.replace(token, "")
                continue
            card_html = build_affiliate_card(site, slot_name, post_id, keyword)
            result = result.replace(token, card_html)
            if card_html.strip():
                any_affiliate_content = True
            if "affiliate-card-coupang" in card_html:
                any_coupang_content = True

    if any_affiliate_content:
        disclosure_lines = [FTC_DISCLOSURE_TEXT]
        if any_coupang_content:
            disclosure_lines.append(COUPANG_DISCLOSURE_TEXT)
        result += (
            f'\n<p style="font-size:12px;color:#888;margin:24px 0 0;line-height:1.6;">'
            f"{'<br>'.join(disclosure_lines)}</p>"
        )
    return result
