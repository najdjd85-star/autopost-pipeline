"""상위 노출 글 구조 벤치마킹.

네이버 블로그 검색 상위 글의 "구조"(분량, 소제목, 이미지/표 수, 도입부 방식)를 코드로 측정하고,
싼 모델(Haiku) 한 번으로 공통 구성/독자 질문/빈틈을 요약해 generator 프롬프트에 넣을 브리프로 만든다.

문장은 베끼지 않는다. 브리프에는 소제목 흐름과 다룬 주제만 담고, 프롬프트에도 재창작을 명시한다.
키워드+날짜별로 결과를 캐시하고(같은 키워드를 하루에 여러 번 분석하지 않음), 실패하면 빈 문자열을 돌려
기존 동작으로 되돌아간다. 모든 LLM 호출은 llm_usage.call_message의 예산/호출 수 가드를 거친다.
"""
from __future__ import annotations

import json
import os
import re
import statistics
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from competitor_analyzer import search_naver_blogs
from config import OUTPUT_DIR, settings
from llm_usage import LLMGuardError, call_message
from utils.http import safe_get
from utils.logger import get_logger

logger = get_logger(__name__)

BENCHMARK_MODEL = os.environ.get("BENCHMARK_MODEL", "claude-haiku-5-5")
CACHE_PATH = OUTPUT_DIR / "benchmark_cache.json"
CACHE_KEEP_DAYS = 3
TOP_N = 5
FETCH_GAP_SECONDS = 0.7
MAX_HEADING_CHARS = 80
MAX_HEADINGS_PER_POST = 12
_NAVER_BLOG_RE = re.compile(r"https?://(?:m\.)?blog\.naver\.com/([^/?#]+)/(\d+)")

BENCHMARK_TOOL = {
    "name": "submit_benchmark",
    "description": "상위 노출 글들의 구성 분석 결과를 제출한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "common_sections": {
                "type": "array",
                "items": {"type": "string"},
                "description": "상위 글들이 공통으로 다루는 소제목/주제(순서대로, 최대 7개)",
            },
            "reader_questions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "검색자가 실제로 궁금해하는 질문(최대 6개)",
            },
            "hook_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "도입부/제목에서 쓰는 유형(예: 결론 먼저, 탈락 사유 제시). 문장을 옮기지 말고 유형만(최대 3개)",
            },
            "format_elements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "독자가 반기는 구성요소(표, 번호 목록, 체크리스트, FAQ 등)와 쓰이는 위치(최대 5개)",
            },
            "gaps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "상위 글이 다루지 않았거나 얕게 다룬 각도. 우리 글이 차별화할 지점(최대 4개)",
            },
        },
        "required": ["common_sections", "reader_questions", "hook_patterns", "format_elements", "gaps"],
    },
}

SYSTEM_PROMPT = (
    "당신은 한국어 검색 콘텐츠의 편집 분석가입니다. 주어진 상위 노출 블로그 글들의 구조 자료(소제목 목록과 수치)를 "
    "읽고, 새 글을 쓸 작가가 참고할 구성 분석만 submit_benchmark 도구로 제출하세요. "
    "원문의 문장이나 고유한 표현을 옮기지 말고, 주제와 구성 유형만 요약합니다. "
    "각 항목은 한 줄(60자 이내)로 쓰세요."
)


# ---------------------------------------------------------------------------
# 수집/측정 (LLM 없음)
# ---------------------------------------------------------------------------
def fetch_structure(url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """네이버 블로그 글 하나의 구조를 측정한다. 네이버 블로그가 아니거나 실패하면 None."""
    match = _NAVER_BLOG_RE.match(url or "")
    if not match:
        return None
    post_url = f"https://blog.naver.com/PostView.naver?blogId={match.group(1)}&logNo={match.group(2)}"
    resp = safe_get(post_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    if resp is None or resp.status_code != 200:
        return None
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        main = soup.select_one("div.se-main-container") or soup.select_one("#postViewArea")
        if main is None:
            return None
        text = main.get_text(" ", strip=True)
        headings: List[str] = []
        for el in main.select("div.se-component.se-sectionTitle, div.se-component.se-quotation"):
            heading = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
            if 2 <= len(heading) <= MAX_HEADING_CHARS and heading not in headings:
                headings.append(heading)
        return {
            "chars": len(text),
            "images": len(main.select("img")),
            "tables": len(main.select("table")),
            "headings": headings[:MAX_HEADINGS_PER_POST],
        }
    except Exception as exc:  # noqa: BLE001 - 벤치마킹 실패가 글 생성을 막으면 안 된다
        logger.info("블로그 구조 측정 실패(%s): %s", url, exc)
        return None


def collect_structures(keyword: str, top_n: int = TOP_N) -> List[Dict[str, Any]]:
    results = search_naver_blogs(keyword, display=top_n)
    posts: List[Dict[str, Any]] = []
    for item in results:
        structure = fetch_structure(item.get("url", ""))
        if structure:
            structure["title"] = item.get("title", "")
            posts.append(structure)
        time.sleep(FETCH_GAP_SECONDS)
    return posts


def _stats_line(posts: List[Dict[str, Any]]) -> str:
    def median(key: str) -> int:
        return int(statistics.median(p[key] for p in posts))

    return (
        f"분량 중앙값 {median('chars'):,}자(범위 {min(p['chars'] for p in posts):,}~{max(p['chars'] for p in posts):,}), "
        f"이미지 중앙값 {median('images')}개, 표 있는 글 {sum(1 for p in posts if p['tables'])}/{len(posts)}편, "
        f"소제목 중앙값 {median_len(posts)}개"
    )


def median_len(posts: List[Dict[str, Any]]) -> int:
    return int(statistics.median(len(p["headings"]) for p in posts))


def _outline_text(posts: List[Dict[str, Any]]) -> str:
    blocks = []
    for i, post in enumerate(posts, 1):
        lines = "\n".join(f"   - {h}" for h in post["headings"]) or "   (소제목 없음)"
        blocks.append(f"{i}. 제목: {post['title']}\n   분량 {post['chars']:,}자, 이미지 {post['images']}개, 표 {post['tables']}개\n{lines}")
    return "\n".join(blocks)


# ---------------------------------------------------------------------------
# 요약(Haiku 1회) + 캐시
# ---------------------------------------------------------------------------
def _load_cache() -> Dict[str, Any]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(cache: Dict[str, Any]) -> None:
    today = datetime.now(timezone.utc).date()
    fresh = {}
    for key, entry in cache.items():
        try:
            age = (today - datetime.fromisoformat(entry["date"]).date()).days
        except (KeyError, ValueError):
            continue
        if age <= CACHE_KEEP_DAYS:
            fresh[key] = entry
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(fresh, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _analyze(client: Any, keyword: str, posts: List[Dict[str, Any]], site: Optional[str]) -> Optional[Dict[str, Any]]:
    user_prompt = (
        f"[검색 키워드] {keyword}\n\n[상위 노출 글 {len(posts)}편의 구조]\n{_outline_text(posts)}\n\n"
        "위 구조를 바탕으로 submit_benchmark 도구를 호출하세요."
    )
    response = call_message(
        client,
        purpose="benchmark",
        site=site,
        model=BENCHMARK_MODEL,
        max_tokens=1200,
        system=SYSTEM_PROMPT,
        tools=[BENCHMARK_TOOL],
        tool_choice={"type": "tool", "name": BENCHMARK_TOOL["name"]},
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": user_prompt}],
    )
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == BENCHMARK_TOOL["name"]:
            return dict(block.input)
    return None


def _format_brief(stats: str, analysis: Dict[str, Any]) -> str:
    def bullets(key: str) -> str:
        return "\n".join(f"  - {str(v)[:90]}" for v in analysis.get(key, [])[:7])

    return (
        "[상위 노출 글 벤치마크 - 구성과 주제만 참고하고 문장·표현은 절대 따라 쓰지 말 것. 100% 새로 작성]\n"
        f"- 측정: {stats}\n"
        f"- 상위 글이 공통으로 다루는 흐름:\n{bullets('common_sections')}\n"
        f"- 검색자가 궁금해하는 질문(소제목/FAQ에 반영):\n{bullets('reader_questions')}\n"
        f"- 도입·제목 유형:\n{bullets('hook_patterns')}\n"
        f"- 반기는 구성요소:\n{bullets('format_elements')}\n"
        f"- 상위 글이 놓친 각도(우리 글의 차별점으로 삼을 것):\n{bullets('gaps')}\n"
        "- 위 공통 흐름을 모두 베끼지 말고, 독자 질문은 빠짐없이 답하되 놓친 각도를 최소 1개 깊게 다룰 것.\n"
    )


def build_benchmark_brief(keyword: str, site: Optional[str] = None, client: Any = None) -> str:
    """generator 프롬프트에 넣을 벤치마크 브리프를 돌려준다. 어떤 실패든 빈 문자열(기존 동작)."""
    if not keyword:
        return ""
    cache_key = f"{keyword}"
    today = datetime.now(timezone.utc).date().isoformat()
    cache = _load_cache()
    entry = cache.get(cache_key)
    if entry and entry.get("date") == today and entry.get("brief"):
        return entry["brief"]

    try:
        posts = collect_structures(keyword)
        if len(posts) < 2:
            logger.info("벤치마크: 구조를 측정한 상위 글이 %s편뿐이라 건너뜁니다.", len(posts))
            return ""
        if client is None:
            if not settings.anthropic_api_key:
                return ""
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=1)
        analysis = _analyze(client, keyword, posts, site)
        if not analysis:
            return ""
        brief = _format_brief(_stats_line(posts), analysis)
    except LLMGuardError as exc:
        logger.warning("벤치마크 생략(LLM 가드): %s", exc)
        return ""
    except Exception as exc:  # noqa: BLE001 - 선택 기능, 실패해도 기존 방식으로 진행
        logger.warning("벤치마크 분석 실패, 기존 방식으로 진행: %s", exc)
        return ""

    cache[cache_key] = {"date": today, "brief": brief}
    _save_cache(cache)
    return brief
