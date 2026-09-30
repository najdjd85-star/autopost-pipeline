"""
Gemini/Flux 생성 우선 + Pexels/Pollinations 폴백 하이브리드 이미지 엔진.

본문 중의 IMAGE_SLOT_1 플레이스홀더를 처리한다:
  1차: Google AI Studio(Gemini) 이미지 생성 API로 글 내용에 맞는 이미지를 직접 생성.
       (Pexels 스톡 검색은 "검색"이라 완전히 일치하는 사진이 없으면 엉뚱한 키워드만
       겹치는 사진을 억지로 반환하는 문제가 실측으로 있었음 - 생성 방식으로 바꿔서
       매번 프롬프트에 맞는 이미지를 새로 만들도록 한다.)
  2차: Gemini 크레딧 소진/호출 실패 시 fal.ai의 Flux(schnell) 모델로 생성.
  3차: 그마저 실패하면 Pexels API로 영문 키워드 기반 실사 스톡 이미지 검색.
  4차: 그마저도 실패하면 Pollinations.ai 무료 Flux 엔드포인트로 최종 폴백.
  업로드: 워드프레스 REST API(wp/v2/media)로 업로드 후 alt/caption 포함
          반응형 <figure> 블록으로 치환.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from config import DATA_DIR, settings
from constants import IMAGE_SLOT_1, POLLINATIONS_IMAGE_SIZE
from utils.http import safe_get, safe_post
from utils.logger import get_logger
from wp_client import WordPressClient

logger = get_logger(__name__)

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
POLLINATIONS_BASE_URL = "https://image.pollinations.ai/prompt"
GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
# fal.ai 동기(sync) 엔드포인트 - 큐/폴링 없이 한 번의 HTTP 요청으로 결과를 바로 받는다.
# schnell 모델은 fal의 Flux 라인업 중 가장 빠르고 저렴한 버전(품질도 블로그
# 삽입 이미지 용도로는 충분).
FAL_FLUX_URL = "https://fal.run/fal-ai/flux/schnell"

_SLOT_TOKEN_TO_KEY = {IMAGE_SLOT_1: "slot_1"}


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


def generate_google_ai_image(
    prompt_en: str, width: int = POLLINATIONS_IMAGE_SIZE[0], height: int = POLLINATIONS_IMAGE_SIZE[1]
) -> Optional[bytes]:
    """Google AI Studio(Gemini) 이미지 생성 API로 프롬프트에 맞는 이미지를 생성한다."""
    if not settings.google_ai_studio_api_key:
        logger.info("GOOGLE_AI_STUDIO_API_KEY 미설정 - Gemini 이미지 생성을 건너뜁니다.")
        return None

    aspect_ratio = "16:9" if width >= height else "9:16"
    payload = {
        "model": GEMINI_IMAGE_MODEL,
        "input": [{"type": "text", "text": prompt_en}],
        "response_format": {
            "type": "image",
            "mime_type": "image/jpeg",
            "aspect_ratio": aspect_ratio,
            # image_size를 안 주면 기본값 "1K"가 적용되는데, 실측 결과 16:9 등
            # 정사각형이 아닌 비율에서는 "1K"가 1024x1024 정사각형보다 총 픽셀
            # 수가 커져서 토큰(=비용)이 예상보다 4배 가까이 나오는 걸 확인했다
            # (하루 62장 생성에 약 28만 토큰, 장당 4500토큰 수준 - 정사각형 1K
            # 기준가 1120토큰의 4배). 블로그에 삽입되는 이미지는 반응형으로
            # 축소 표시되므로 화질 손해 없이 가장 작은 사이즈로 고정해 비용을
            # 최소화한다. API가 실제로 받는 최소 티어 값은 "512"다(문서의
            # "0.5K" 예시와 다름 - 실측으로 확인함, 잘못 보내면 400 에러로
            # 정확한 지원값 목록을 알려줌: 512/1K/2K/4K). 512 기준 실측
            # 747토큰≈$0.045/장으로, image_size 없이 16:9만 요청했을 때
            # (장당 4500토큰대)보다 약 6배 저렴하다.
            "image_size": "512",
        },
    }
    resp = safe_post(
        GEMINI_INTERACTIONS_URL,
        headers={
            "x-goog-api-key": settings.google_ai_studio_api_key,
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=30,
    )
    if resp is None or resp.status_code != 200:
        logger.warning(
            "Gemini 이미지 생성 실패: status=%s body=%s",
            getattr(resp, "status_code", "N/A"),
            getattr(resp, "text", "")[:300],
        )
        return None

    try:
        data = resp.json()
        # 응답은 {"steps": [{"type": "thought", ...}, {"type": "model_output",
        # "content": [{"type": "image", "mime_type": ..., "data": "<base64>"}]}]}
        # 형태다(실측으로 확인함 - 문서 예시의 interaction.outputImage 경로와 다름).
        for step in data.get("steps", []):
            if step.get("type") != "model_output":
                continue
            for block in step.get("content", []):
                if block.get("type") == "image" and block.get("data"):
                    return base64.b64decode(block["data"])
        logger.warning("Gemini 응답에 이미지 블록이 없습니다: %s", json.dumps(data)[:300])
        return None
    except (ValueError, KeyError) as exc:
        logger.warning("Gemini 이미지 응답 파싱 실패: %s", exc)
        return None


def generate_flux_image(
    prompt_en: str, width: int = POLLINATIONS_IMAGE_SIZE[0], height: int = POLLINATIONS_IMAGE_SIZE[1]
) -> Optional[bytes]:
    """fal.ai의 Flux(schnell) 모델로 이미지를 생성한다.

    Gemini(Google AI Studio) 크레딧이 소진되거나 호출이 실패했을 때의 2순위
    생성 경로다. fal의 동기(sync) 엔드포인트(fal.run)를 쓰므로 큐 등록 후
    상태를 폴링할 필요 없이 한 번의 요청으로 결과를 바로 받는다.
    """
    if not settings.fal_api_key:
        logger.info("FAL_API_KEY 미설정 - Flux 이미지 생성을 건너뜁니다.")
        return None

    payload = {
        "prompt": prompt_en,
        "image_size": {"width": width, "height": height},
        "num_images": 1,
    }
    resp = safe_post(
        FAL_FLUX_URL,
        headers={
            "Authorization": f"Key {settings.fal_api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=30,
    )
    if resp is None or resp.status_code != 200:
        logger.warning(
            "Flux 이미지 생성 실패: status=%s body=%s",
            getattr(resp, "status_code", "N/A"),
            getattr(resp, "text", "")[:300],
        )
        return None

    try:
        data = resp.json()
        images = data.get("images", [])
        if not images or not images[0].get("url"):
            logger.warning("Flux 응답에 이미지가 없습니다: %s", json.dumps(data)[:300])
            return None
        image_url = images[0]["url"]
    except (ValueError, KeyError) as exc:
        logger.warning("Flux 응답 파싱 실패: %s", exc)
        return None

    img_resp = safe_get(image_url, timeout=20)
    if img_resp is None or img_resp.status_code != 200:
        logger.warning("Flux 이미지 다운로드 실패: %s", image_url)
        return None
    return img_resp.content


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
    """이미지를 확보한다. (바이트, 소스라벨) 튜플을 반환. 전부 실패하면 (None, 'none').

    우선순위: Gemini(Google AI Studio) -> Flux(fal.ai) -> Pexels -> Pollinations.
    Gemini 생성을 최우선으로 시도한다 - 글 내용에 맞춰 매번 새로 그리므로
    Pexels 스톡 검색의 "검색어만 겹치는 엉뚱한 사진" 문제가 원천적으로 없다.
    Gemini 크레딧이 소진되거나(과금/쿼터 에러) 호출이 실패하면 Flux로 넘어가고,
    Flux마저 실패하면 예전 방식(Pexels -> Pollinations)으로 최종 폴백한다.
    별도의 "소진 감지" 로직은 없다 - Gemini 호출이 실패하면 이유를 가리지 않고
    바로 다음 순위로 넘어가므로, 크레딧이 떨어져 매 호출이 실패하기 시작하는
    순간부터 자연스럽게 Flux가 주력이 된다.
    """
    image_bytes = generate_google_ai_image(prompt_en)
    if image_bytes:
        return image_bytes, "google-ai-studio"

    image_bytes = generate_flux_image(prompt_en)
    if image_bytes:
        return image_bytes, "flux"

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


# ---------------------------------------------------------------------------
# 이미지 캐시 - 비슷한 맥락의 프롬프트면 새로 생성(=토큰 소모)하지 않고
# 예전에 만들어둔 이미지를 재사용한다. Gemini 생성이 Pexels/Pollinations보다
# 품질은 훨씬 좋지만 매번 새로 생성하면 콘텐츠 생성용 Claude 토큰과 별개로
# 비용이 계속 쌓이기 때문에(실측 문의로 확인) 추가한 절감 장치다.
# 사이트별로 캐시를 분리한다(사이트마다 이미지 톤/맥락이 다르므로).
# ---------------------------------------------------------------------------
IMAGE_CACHE_DIR = DATA_DIR / "image_cache"
IMAGE_CACHE_MAX_ENTRIES = 60
IMAGE_CACHE_SIMILARITY_THRESHOLD = 0.45

_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "with", "and", "or", "for",
    "style", "photo", "photos", "photograph", "realistic", "image", "one",
    "two", "three", "looking", "while",
}


def _cache_path(site: str) -> Path:
    return IMAGE_CACHE_DIR / f"{site}.json"


def _prompt_word_set(prompt_en: str) -> set:
    words = re.findall(r"[a-zA-Z]+", prompt_en.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _load_image_cache(site: str) -> List[Dict[str, str]]:
    path = _cache_path(site)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save_image_cache(site: str, entries: List[Dict[str, str]]) -> None:
    IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    trimmed = entries[-IMAGE_CACHE_MAX_ENTRIES:]
    try:
        _cache_path(site).write_text(
            json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("[Site %s] 이미지 캐시 저장 실패: %s", site, exc)


def find_cached_image(site: str, prompt_en: str) -> Optional[str]:
    """비슷한 맥락(단어 겹침 비율 기준)의 캐시된 이미지가 있으면 media_url을 반환한다."""
    target_words = _prompt_word_set(prompt_en)
    if not target_words:
        return None

    best_url: Optional[str] = None
    best_score = IMAGE_CACHE_SIMILARITY_THRESHOLD
    for entry in _load_image_cache(site):
        cached_words = _prompt_word_set(entry.get("prompt", ""))
        if not cached_words:
            continue
        overlap = len(target_words & cached_words) / len(target_words | cached_words)
        if overlap >= best_score:
            best_score = overlap
            best_url = entry.get("media_url")

    if best_url:
        logger.info(
            "[Site %s] 비슷한 맥락(유사도 %.2f)의 캐시 이미지 재사용 - 새로 생성하지 않음",
            site,
            best_score,
        )
    return best_url


def add_to_image_cache(site: str, prompt_en: str, media_url: str) -> None:
    entries = _load_image_cache(site)
    entries.append(
        {
            "prompt": prompt_en,
            "media_url": media_url,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _save_image_cache(site, entries)


def process_image_slots(
    html: str, image_prompts: Dict[str, str], wp: WordPressClient, post_id: int = 0
) -> str:
    """html_content 안의 IMAGE_SLOT_1을 실제 <figure> 블록으로 치환한다."""
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

        site_key = wp.site_key
        cached_url = find_cached_image(site_key, prompt_en)
        if cached_url:
            figure = build_figure_html(cached_url, alt=prompt_en, caption="출처: google-ai-studio")
            result = result.replace(token, figure)
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
            if source in ("google-ai-studio", "flux"):
                add_to_image_cache(site_key, prompt_en, media["source_url"])
        else:
            # 워드프레스 업로드 실패/미설정 시에도 이미지 자체는 확보했으므로 안내 문구만 대체.
            figure = _placeholder_figure(f"{prompt_key} (업로드 대기)")

        result = result.replace(token, figure)

    return result
