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
import random
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote, urlencode

from config import BASE_DIR, get_site, settings
from constants import (
    AFFILIATE_SLOT_BOT,
    AFFILIATE_SLOT_MID,
    AFFILIATE_SLOT_TOP,
    COUPANG_FALLBACK_LINKS,
    FTC_DISCLOSURE_TEXT,
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

ADPICK_API_URL = "https://adpick.co.kr/apis/offers.php"
# 애드픽 문서상 "최대 1분에 1회 이하로 호출"해야 하고 별도 캐시가 필수라서,
# 여유 있게 1시간 캐시한다 (글 하나 발행할 때마다 실시간 호출하지 않음).
ADPICK_CACHE_PATH = BASE_DIR / "data" / "cache" / "adpick_offers.json"
ADPICK_CACHE_TTL_SECONDS = 3600


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
    """사이트별 제휴 카테고리 중 하나를 대표 링크로 선택한다."""
    site_cfg = get_site(site)
    for value in site_cfg.affiliates.values():
        if value:
            return value
    return None


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


def build_coupang_deeplink(keyword: str) -> Optional[Dict[str, str]]:
    """쿠팡 파트너스 Open API로 키워드 연관 상품 딥링크를 생성한다.

    COUPANG_ACCESS_KEY/SECRET_KEY가 없으면 None을 반환한다 (선택 기능).
    """
    if not settings.coupang_configured:
        return None

    url_path = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
    query = urlencode({"keyword": keyword, "limit": 1})
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
            return None
        data = resp.json()
        products = data.get("data", {}).get("productData", [])
        if not products:
            return None
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


def _load_adpick_cache() -> Optional[List[dict]]:
    if not ADPICK_CACHE_PATH.exists():
        return None
    try:
        data = json.loads(ADPICK_CACHE_PATH.read_text(encoding="utf-8"))
        if time.time() - data.get("fetched_at", 0) > ADPICK_CACHE_TTL_SECONDS:
            return None
        return data.get("offers") or None
    except (OSError, ValueError):
        return None


def _save_adpick_cache(offers: List[dict]) -> None:
    try:
        ADPICK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        ADPICK_CACHE_PATH.write_text(
            json.dumps({"fetched_at": time.time(), "offers": offers}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("애드픽 캠페인 캐시 저장 실패: %s", exc)


def _fetch_adpick_offers() -> List[dict]:
    """애드픽 캠페인 리스트를 가져온다. 1시간 이내 캐시가 있으면 그걸 그대로 쓴다
    (API 정책상 1분에 1회 이하로만 호출해야 함)."""
    cached = _load_adpick_cache()
    if cached is not None:
        return cached

    if not settings.adpick_affid:
        return []

    resp = safe_get(
        ADPICK_API_URL,
        params={"affid": settings.adpick_affid, "category": "4", "order": "rand"},
        timeout=8,
    )
    if resp is None or resp.status_code != 200:
        return []
    try:
        offers = resp.json()
    except ValueError:
        return []
    if not isinstance(offers, list):
        return []

    _save_adpick_cache(offers)
    return offers


# "생활" 카테고리로 필터링해도 데이팅/채팅 앱이 섞여 나오는 것을 실측으로 확인함 -
# 정부지원금/세금환급처럼 진지한 콘텐츠 옆에 뜨면 사이트 신뢰도를 해치므로
# 제목에 이런 키워드가 있는 캠페인은 후보에서 아예 제외한다.
_ADPICK_BLOCKLIST_KEYWORDS = (
    "채팅", "소개팅", "데이트", "매칭", "친구", "만남", "미팅", "썸", "이성",
)


def build_adpick_offer() -> Optional[Dict[str, str]]:
    """애드픽 캠페인 리스트 API에서 광고 하나를 골라 카드 데이터로 반환한다.

    앱 설치/가입형 광고 위주라 대출/세금환급 같은 콘텐츠와 결이 완전히 맞진
    않지만, 쿠팡처럼 보너스 카드로 추가 수익 채널을 하나 더 확보하는 용도다.
    AFFID 미설정이거나 API 실패 시, 또는 적절한 캠페인이 하나도 없으면
    None을 반환한다(선택 기능).
    """
    if not settings.adpick_affid:
        return None
    try:
        offers = _fetch_adpick_offers()
        safe_offers = [
            o for o in offers
            if not any(kw in o.get("apAppTitle", "") for kw in _ADPICK_BLOCKLIST_KEYWORDS)
        ]
        if not safe_offers:
            return None
        offer = random.choice(safe_offers)
        images = offer.get("apImages") or {}
        return {
            "name": offer.get("apAppTitle", "추천 앱"),
            "url": offer.get("apTrackingLink", ""),
            "image": images.get("icon114") or images.get("icon", ""),
            "desc": offer.get("apAppPromoText") or offer.get("apHeadline", ""),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("애드픽 캠페인 조회 실패: %s", exc)
        return None


def _get_coupang_card_data(keyword: str, site: str) -> Optional[Dict[str, str]]:
    """쿠팡 API로 상품 딥링크를 먼저 시도하고, 실패하면(예: 서버가 해외 IP라
    쿠팡이 차단하는 경우) 사이트별 고정 딥링크로 대체한다.

    고정 링크는 실시간 상품명/이미지/가격 정보가 없으므로 name/image/price를
    비워 반환한다 - 카드 렌더링 쪽에서 이 경우 이미지/가격 줄을 생략한다.
    """
    coupang = build_coupang_deeplink(keyword) if keyword else None
    if coupang and coupang.get("url"):
        return coupang

    fallback_url = COUPANG_FALLBACK_LINKS.get(site)
    if fallback_url:
        return {"name": "지금 쿠팡 인기 상품 확인하기", "url": fallback_url, "image": "", "price": ""}
    return None


def _disclosure_html() -> str:
    return (
        f'<p style="font-size:12px;color:#888;margin:6px 0 0;line-height:1.5;">'
        f"{FTC_DISCLOSURE_TEXT}</p>"
    )


def build_affiliate_card(site: str, slot: str, post_id: int, keyword: str = "") -> str:
    """단일 슬롯에 들어갈 완성된 제휴 카드 HTML을 생성한다."""
    base_url = _pick_site_affiliate_url(site)
    label = _SLOT_LABELS.get(slot, "지금 확인하기")

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
  {_disclosure_html()}
</div>
""".strip()
        )
    else:
        logger.info("사이트 %s 슬롯 %s: 제휴 링크 미설정 - 카드 생략", site, slot)

    coupang = _get_coupang_card_data(keyword, site)
    if coupang and coupang.get("url"):
        cp_link = build_utm_link(coupang["url"], f"{slot}_coupang", post_id)
        image_html = (
            f"""<img src="{coupang['image']}" alt="{coupang.get('name','')}"
       style="width:80px;height:80px;object-fit:cover;border-radius:10px;flex-shrink:0;">"""
            if coupang.get("image")
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
    {price_html}
  </div>
  <a href="{cp_link}" target="_blank" rel="{REL_ATTR}"
     style="padding:10px 18px;border-radius:999px;background:#111;color:#fff;
     font-size:13px;font-weight:600;text-decoration:none;white-space:nowrap;">바로가기</a>
</div>
<p style="font-size:11px;color:#999;">이 포스팅은 쿠팡 파트너스 활동의 일환으로,
이에 따른 일정액의 수수료를 제공받습니다.</p>
""".strip()
        )

    adpick = build_adpick_offer()
    if adpick and adpick.get("url"):
        ap_link = build_utm_link(adpick["url"], f"{slot}_adpick", post_id)
        ap_image_html = (
            f"""<img src="{adpick['image']}" alt="{adpick.get('name','')}"
       style="width:56px;height:56px;object-fit:cover;border-radius:10px;flex-shrink:0;">"""
            if adpick.get("image")
            else ""
        )
        cards.append(
            f"""
<div class="affiliate-card affiliate-card-adpick" style="margin:16px 0;padding:14px 16px;
    border-radius:14px;background:#fafafa;border:1px solid #eee;display:flex;
    gap:12px;align-items:center;">
  {ap_image_html}
  <div style="flex:1;text-align:left;">
    <div style="font-size:13px;font-weight:600;color:#222;">{adpick.get('name','')}</div>
    <div style="font-size:12px;color:#888;margin-top:2px;">{adpick.get('desc','')}</div>
  </div>
  <a href="{ap_link}" target="_blank" rel="{REL_ATTR}"
     style="padding:8px 16px;border-radius:999px;background:#333;color:#fff;
     font-size:12px;font-weight:600;text-decoration:none;white-space:nowrap;">확인하기</a>
</div>
""".strip()
        )

    return "\n".join(cards)


def inject_affiliate_slots(html: str, post_id: int, site: str, keyword: str = "") -> str:
    """html_content 안의 AFFILIATE_SLOT_* 플레이스홀더를 실제 카드로 치환한다."""
    if not html:
        return html

    result = html
    for token, slot_name in _SLOT_TOKEN_TO_NAME.items():
        if token in result:
            card_html = build_affiliate_card(site, slot_name, post_id, keyword)
            result = result.replace(token, card_html)
    return result
