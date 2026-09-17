"""
스톡 우선 검색 + AI 생성 자동 폴백 하이브리드 이미지 엔진.

본문 중의 IMAGE_SLOT_1/2 플레이스홀더를 처리한다:
  1차: Pexels API로 영문 키워드 기반 1080p 실사 스톡 이미지 검색.
  2차: 검색 실패/타임아웃 시 Pollinations.ai 무료 Flux 엔드포인트로 자동 우회하여
       실시간 AI 이미지 생성 (1200x675).
  업로드: 워드프레스 REST API(wp/v2/media)로 업로드 후 alt/caption 포함
          반응형 <figure> 블록으로 치환.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple
from urllib.parse import quote

from config import settings
from constants import IMAGE_SLOT_1, IMAGE_SLOT_2, POLLINATIONS_IMAGE_SIZE
from utils.http import safe_get
from utils.logger import get_logger
from wp_client import WordPressClient

logger = get_logger(__name__)

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
POLLINATIONS_BASE_URL = "https://image.pollinations.ai/prompt"

_SLOT_TOKEN_TO_KEY = {IMAGE_SLOT_1: "slot_1", IMAGE_SLOT_2: "slot_2"}


def search_pexels_photo(query_en: str) -> Optional[bytes]:
    """Pexels API로 1080p 실사 스톡 이미지를 검색해 원본 바이트를 반환한다."""
    if not settings.pexels_api_key:
        logger.info("PEXELS_API_KEY 미설정 - Pexels 검색을 건너뜁니다.")
        return None

    resp = safe_get(
        PEXELS_SEARCH_URL,
        headers={"Authorization": settings.pexels_api_key},
        params={"query": query_en, "per_page": 1, "orientation": "landscape", "size": "large"},
        timeout=10,
    )
    if resp is None or resp.status_code != 200:
        logger.info("Pexels 검색 실패/결과없음 - Pollinations로 폴백합니다.")
        return None

    try:
        photos = resp.json().get("photos", [])
        if not photos:
            return None
        image_url = photos[0]["src"].get("large2x") or photos[0]["src"].get("large")
        img_resp = safe_get(image_url, timeout=15)
        if img_resp is None or img_resp.status_code != 200:
            return None
        return img_resp.content
    except (ValueError, KeyError, IndexError) as exc:
        logger.warning("Pexels 응답 처리 실패: %s", exc)
        return None


def generate_pollinations_image(
    prompt_en: str, width: int = POLLINATIONS_IMAGE_SIZE[0], height: int = POLLINATIONS_IMAGE_SIZE[1]
) -> Optional[bytes]:
    """Pollinations.ai 무료 Flux 엔드포인트로 이미지를 실시간 생성한다 (API 키 불필요)."""
    try:
        url = f"{POLLINATIONS_BASE_URL}/{quote(prompt_en)}"
        resp = safe_get(
            url,
            params={"width": width, "height": height, "model": "flux", "nologo": "true"},
            timeout=25,
        )
        if resp is None or resp.status_code != 200:
            logger.warning("Pollinations.ai 이미지 생성 실패")
            return None
        return resp.content
    except Exception as exc:  # noqa: BLE001
        logger.warning("Pollinations.ai 호출 중 오류: %s", exc)
        return None


# Pexels는 실사 스톡 "사진"만 있는 라이브러리라, 인포그래픽/일러스트/아이콘
# 스타일을 요청하면 매칭되는 사진이 없어 엉뚱한(제목에 겹치는 영단어만 있는)
# 사진을 억지로 반환하는 것을 실측으로 확인함(예: "infographic style" 요청 시
# "FEED BACK" 글자가 적힌 무관한 사진이 나옴). 이런 스타일 키워드가 프롬프트에
# 있으면 아예 Pexels를 건너뛰고 바로 AI 생성(Pollinations)으로 간다.
_NON_PHOTO_STYLE_KEYWORDS = (
    "infographic", "illustration", "flat design", "icon", "diagram",
    "vector", "cartoon", "clipart", "clip art", "graphic design",
)


def _looks_like_non_photo_style(prompt_en: str) -> bool:
    lowered = prompt_en.lower()
    return any(kw in lowered for kw in _NON_PHOTO_STYLE_KEYWORDS)


def resolve_image_for_slot(prompt_en: str) -> Tuple[Optional[bytes], str]:
    """이미지를 확보한다. (바이트, 소스라벨) 튜플을 반환. 둘 다 실패하면 (None, 'none')."""
    if _looks_like_non_photo_style(prompt_en):
        image_bytes = generate_pollinations_image(prompt_en)
        if image_bytes:
            return image_bytes, "pollinations-ai"
        # AI 생성마저 실패하면 그때는 Pexels로라도 시도(완전히 이미지 없는 것보다 낫다).
        image_bytes = search_pexels_photo(prompt_en)
        if image_bytes:
            return image_bytes, "pexels"
        return None, "none"

    image_bytes = search_pexels_photo(prompt_en)
    if image_bytes:
        return image_bytes, "pexels"

    image_bytes = generate_pollinations_image(prompt_en)
    if image_bytes:
        return image_bytes, "pollinations-ai"

    return None, "none"


def build_figure_html(media_url: str, alt: str, caption: str) -> str:
    return f"""<figure style="margin:24px 0;text-align:center;">
  <img src="{media_url}" alt="{alt}" loading="lazy"
       style="width:100%;max-width:100%;height:auto;border-radius:12px;display:block;margin:0 auto;">
  <figcaption style="font-size:13px;color:#888;margin-top:8px;">{caption}</figcaption>
</figure>"""


def _placeholder_figure(alt: str) -> str:
    """이미지 확보에 완전히 실패했을 때 파이프라인을 막지 않기 위한 대체 블록."""
    return f"""<div style="margin:24px 0;padding:40px;text-align:center;background:#f2f2f2;
    border-radius:12px;color:#999;font-size:14px;">🖼️ 이미지 준비 중 ({alt})</div>"""


def process_image_slots(
    html: str, image_prompts: Dict[str, str], wp: WordPressClient, post_id: int = 0
) -> str:
    """html_content 안의 IMAGE_SLOT_1/2를 실제 <figure> 블록으로 치환한다."""
    if not html:
        return html

    result = html
    for token, prompt_key in _SLOT_TOKEN_TO_KEY.items():
        if token not in result:
            continue

        prompt_en = image_prompts.get(prompt_key, "") if image_prompts else ""
        if not prompt_en:
            result = result.replace(token, _placeholder_figure(prompt_key))
            continue

        image_bytes, source = resolve_image_for_slot(prompt_en)
        if image_bytes is None:
            result = result.replace(token, _placeholder_figure(prompt_key))
            continue

        filename = f"{prompt_key}_{post_id}.jpg"
        media = wp.upload_media(image_bytes, filename, "image/jpeg") if wp.is_configured else None

        if media and media.get("source_url"):
            figure = build_figure_html(
                media["source_url"], alt=prompt_en, caption=f"출처: {source}"
            )
        else:
            # 워드프레스 업로드 실패/미설정 시에도 이미지 자체는 확보했으므로 안내 문구만 대체.
            figure = _placeholder_figure(f"{prompt_key} (업로드 대기)")

        result = result.replace(token, figure)

    return result
