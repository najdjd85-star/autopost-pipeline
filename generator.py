"""
Claude API 콘텐츠 생성 엔진 - 심리 저격 & 반응형 비주얼 UI 강제.

trend_scraper -> keyword_expander -> competitor_analyzer 순으로 수집한 데이터를
프롬프트에 주입하고, Claude의 tool use(구조화된 도구 호출) 기능으로 콘텐츠를
받는다. html_content에는 인라인 CSS/JS 때문에 큰따옴표가 매우 많이 등장하는데,
모델이 "JSON 문자열로 직접 이스케이프해서 출력"하도록 시키면 긴 응답일수록
이스케이프를 빠뜨려 파싱이 깨지기 쉽다. tool use는 Anthropic API가 값 자체를
구조화해서 돌려주므로(문자열 escape를 모델이 직접 신경쓸 필요가 없음) 이 문제를
근본적으로 없애준다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from competitor_analyzer import get_top_blog_references
from config import settings
from constants import (
    AFFILIATE_SLOT_BOT,
    AFFILIATE_SLOT_MID,
    AFFILIATE_SLOT_TOP,
    CLAUDE_MODEL,
    IMAGE_SLOT_1,
    IMAGE_SLOT_2,
    REQUIRED_GENERATOR_KEYS,
    SITE_LABELS,
    SITE_OFFICIAL_URLS,
)
from keyword_expander import expand_to_longtail
from trend_scraper import fetch_today_hot_topics
from utils.logger import get_logger
from video_trend_analyzer import format_trend_briefing, get_trending_videos

logger = get_logger(__name__)

MODEL = CLAUDE_MODEL
TOOL_NAME = "submit_blog_content"

# Anthropic tool use 스키마 - REQUIRED_GENERATOR_KEYS와 반드시 일치해야 한다.
CONTENT_TOOL = {
    "name": TOOL_NAME,
    "description": (
        "작성이 완료된 블로그 포스트와 소셜/영상용 부가 콘텐츠를 구조화된 형태로 제출합니다."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "SEO 및 클릭률을 고려한 제목"},
            "fact_summary": {"type": "string", "description": "핵심 팩트 요약 (2~3문장)"},
            "html_content": {
                "type": "string",
                "description": "시스템 프롬프트의 모든 규칙(심리 작성 규칙 + 필수 UI 컴포넌트 + 슬롯 플레이스홀더)을 만족하는 완성된 HTML 문자열",
            },
            "image_prompts": {
                "type": "object",
                "description": "이미지 슬롯별 영문 검색/생성 프롬프트",
                "properties": {
                    "slot_1": {"type": "string"},
                    "slot_2": {"type": "string"},
                },
                "required": ["slot_1", "slot_2"],
            },
            "shorts_script": {
                "type": "string",
                "description": (
                    "30초 세로 쇼츠 나레이션 대본. 실제로 성우가 그대로 읽고 화면 자막으로도 "
                    "그대로 노출되는 순수 발화 텍스트만 작성한다. '(0-3초)', '(장면1)', "
                    "'나레이터:' 같은 시간 지시문/연출 메모/화자 표시는 절대 포함하지 않는다."
                ),
            },
            "longform_chapters": {
                "type": "array",
                "description": "5~7분 롱폼 영상용 챕터 목록",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "script": {
                            "type": "string",
                            "description": (
                                "해당 챕터 나레이션. 시간 지시문/연출 메모 없이 순수 발화 텍스트만."
                            ),
                        },
                        "stock_query_en": {"type": "string"},
                    },
                    "required": ["title", "script", "stock_query_en"],
                },
            },
            "threads_post": {"type": "string", "description": "스레드 본문 요약 (500자 이내)"},
            "threads_comment": {
                "type": "string",
                "description": "스레드 첫 댓글. 블로그 링크 자리에 {POST_URL} 플레이스홀더 사용",
            },
            "ig_caption": {"type": "string", "description": "인스타그램 릴스 캡션 (해시태그 포함)"},
            "pinterest_desc": {"type": "string", "description": "핀터레스트 설명 (SEO 키워드 포함)"},
        },
        "required": list(REQUIRED_GENERATOR_KEYS),
    },
}


class GeneratorNotConfiguredError(RuntimeError):
    """ANTHROPIC_API_KEY가 설정되지 않아 콘텐츠 생성을 수행할 수 없을 때 발생."""


class GeneratorResponseError(RuntimeError):
    """Claude 응답이 요구하는 JSON 스키마를 만족하지 못할 때 발생."""


def _get_client():
    """anthropic.Anthropic 클라이언트를 반환한다. 키가 없으면 None."""
    if not settings.anthropic_api_key:
        return None
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def build_system_prompt(site: str) -> str:
    site_label = SITE_LABELS.get(site, site)
    official_url = SITE_OFFICIAL_URLS.get(site, "")
    return f"""당신은 대한민국 최상위 1% 바이럴 블로그 카피라이터이자 UI/UX 퍼블리셔입니다.
지금부터 "{site_label}" 주제로 워드프레스에 바로 게시할 완성된 HTML 콘텐츠를 작성합니다.

[절대 규칙 1 - 심리 작성 규칙]
1. 도입부(intro): 지루한 공고문 말투를 절대 금지합니다. "매년 수십만 명이 이 조건 하나 때문에
   탈락합니다" 같은 상실 공포(FOMO)와 신청자 탈락 원인으로 글을 시작하세요.
2. 소제목(h2/h3): 실제 네이버 지식인에 올라올 법한 구어체 의문문 형태로 호기심을 유발하세요.
   예) "저도 이거 받을 수 있나요?", "이미 신청했는데 왜 탈락했을까요?"
3. 페르소나 사례: 조건이 비슷하지만 결과가 상반된 가상 인물 2명(예: "김OO씨(합격)" vs "이OO씨(불합격)")의
   판정 비교를 본문 중간에 박스 형태로 삽입하세요.
4. 상식 깨기(Myth Buster): 대중이 흔히 오해하는 사실 1가지를 제시하고 바로 팩트로 정정하는
   단락을 반드시 넣으세요.

[절대 규칙 2 - 반응형 비주얼 UI 컴포넌트 (인라인 CSS로 직접 작성, 외부 CSS 파일 참조 금지)]
html_content 안에 아래 컴포넌트를 전부 포함해야 합니다:
1. 3분할 키 메트릭스 카드: 상단에 지원금액/대상/기간(또는 사이트 주제에 맞는 3개 핵심 지표)을
   flexbox 또는 grid로 3등분한 카드 UI.
2. 3단계 타임라인 프로세스 바: 신청 절차를 3단계로 시각화한 가로 타임라인.
3. `<details>` 기반 아코디언 FAQ: 질문 2개 이상, `<summary>`와 본문으로 구성.
4. `<div class="benefit-calc">` 모의 판별/계산기 위젯: 순수 Vanilla JavaScript(<script> 태그, 외부
   라이브러리 금지)로 입력값에 따라 결과를 즉시 보여주는 위젯. 반드시 동작 가능한 JS 로직 포함.
5. 그라데이션 배경의 공식 신청 바로가기 CTA 버튼 (linear-gradient 인라인 스타일).
   href는 반드시 "{official_url}" 을 그대로 사용하세요 (실제 존재하는 공식 사이트 주소입니다).
   "#"이나 다른 임의의 주소를 절대 사용하지 마세요 - 클릭했을 때 아무 데도 안 가는
   가짜 버튼이 되어서는 안 됩니다.
6. 아래 플레이스홀더를 본문 흐름에 맞는 위치에 정확히 그대로(문자 변경 없이) 삽입:
   - "{IMAGE_SLOT_1}" : 도입부 직후
   - "{IMAGE_SLOT_2}" : 본문 중반(페르소나 사례 근처)
   - "{AFFILIATE_SLOT_TOP}" : 메트릭스 카드 직후
   - "{AFFILIATE_SLOT_MID}" : 계산기 위젯 직후
   - "{AFFILIATE_SLOT_BOT}" : 글 최하단

[절대 규칙 3 - 레퍼런스 처리 원칙]
아래 사용자 메시지에 상위 노출 경쟁 블로그의 제목/핵심 텍스트가 주어집니다.
그 안의 "사실 정보(수치, 조건, 절차 등)"는 빠짐없이 흡수하되, 문장 표현·문단 구성·소제목
전부를 100% 새롭게 재창작해야 합니다. 문장을 그대로 베끼거나 표현만 살짝 바꾸는 것은 금지입니다.

[출력 형식]
설명이나 마크다운 없이, 반드시 제공된 도구(submit_blog_content)를 한 번 호출해서 모든 필드를
채워 제출하세요. html_content는 완성된 HTML을 그대로(이스케이프 걱정 없이 자연스럽게 줄바꿈과
큰따옴표를 포함해서) 작성하면 됩니다.
"""


def build_user_prompt(
    site: str,
    keyword: str,
    longtail: List[str],
    references: List[Dict[str, str]],
    trend_briefing: str,
    video_trend_briefing: str = "",
) -> str:
    if references:
        ref_lines = []
        for i, ref in enumerate(references, 1):
            ref_lines.append(
                f"{i}. 제목: {ref.get('title','')}\n   핵심내용: {ref.get('excerpt','')[:500]}"
            )
        ref_block = "\n".join(ref_lines)
    else:
        ref_block = "(상위 노출 블로그 레퍼런스를 가져오지 못했습니다 - 아래 트렌드 데이터만으로 작성하세요.)"

    return f"""[오늘의 트렌드 브리핑]
{trend_briefing}

[메인 키워드] {keyword}
[확장된 롱테일 키워드 후보] {', '.join(longtail)}

[상위 1~3위 블로그 레퍼런스 - 팩트만 흡수, 문체는 100% 재창작]
{ref_block}

[최근 3개월 조회수 상위 관련 유튜브 영상 - shorts_script/longform_chapters 작성 시
제목·후킹 패턴만 참고하고 내용/문장은 절대 베끼지 말 것. 100% 새로운 대본으로 작성]
{video_trend_briefing or "(참고 데이터 없음 - 일반적인 후킹 원칙으로 작성하세요.)"}

위 정보를 바탕으로 시스템 프롬프트의 모든 규칙을 만족하는 콘텐츠를 submit_blog_content 도구로 제출하세요."""


def _validate(data: Dict[str, Any]) -> Dict[str, Any]:
    missing = [k for k in REQUIRED_GENERATOR_KEYS if k not in data]
    if missing:
        raise GeneratorResponseError(f"필수 키 누락: {missing}")
    return data


def _call_claude(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    """Claude를 tool use 모드로 호출해 구조화된 콘텐츠 dict를 받는다.

    tool_choice로 submit_blog_content 호출을 강제하므로, 응답의 tool_use 블록
    input이 곧 우리가 원하는 dict다 - 텍스트를 직접 JSON으로 파싱할 필요가 없어
    html_content 안의 따옴표/줄바꿈 이스케이프 문제가 원천적으로 발생하지 않는다.
    """
    client = _get_client()
    if client is None:
        raise GeneratorNotConfiguredError(
            "ANTHROPIC_API_KEY가 설정되지 않았습니다. .env에 키를 추가하세요."
        )

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=system_prompt,
        tools=[CONTENT_TOOL],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[{"role": "user", "content": user_prompt}],
    )

    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "Claude 호출 완료 - 입력 %s 토큰 / 출력 %s 토큰 (model=%s)",
            usage.input_tokens,
            usage.output_tokens,
            MODEL,
        )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == TOOL_NAME:
            return dict(block.input)

    raise GeneratorResponseError("Claude 응답에 submit_blog_content 도구 호출이 없습니다.")


def generate_post(site: str, base_keyword: Optional[str] = None) -> Dict[str, Any]:
    """사이트별 콘텐츠를 생성한다.

    site: "A"/"B"/"C" (또는 "site_a" 등)
    base_keyword: 생략 시 오늘의 핫토픽에서 자동 선정.

    ANTHROPIC_API_KEY가 없으면 GeneratorNotConfiguredError를 던진다 - 호출부
    (main.py/telegram_bot.py)에서만 잡아 로그/알림 후 안전하게 종료해야 한다.
    """
    site = site.upper().replace("SITE_", "")

    hot = fetch_today_hot_topics(site)
    keyword = base_keyword or (hot["keywords"][0] if hot["keywords"] else SITE_LABELS.get(site, site))

    longtail = expand_to_longtail(keyword)
    references = get_top_blog_references(longtail[0] if longtail else keyword)

    try:
        video_trends = get_trending_videos(keyword)
        video_trend_briefing = format_trend_briefing(video_trends)
    except Exception as exc:  # noqa: BLE001 - 선택 기능, 실패해도 계속 진행
        logger.info("유튜브 트렌드 조회 실패, 참고 없이 진행: %s", exc)
        video_trend_briefing = ""

    system_prompt = build_system_prompt(site)
    user_prompt = build_user_prompt(
        site, keyword, longtail, references, hot["briefing_text"], video_trend_briefing
    )

    try:
        data = _validate(_call_claude(system_prompt, user_prompt))
    except GeneratorResponseError as exc:
        logger.warning("1차 응답 검증 실패(%s) - 1회 재시도합니다.", exc)
        retry_prompt = (
            user_prompt
            + "\n\n[중요] 방금 응답에 필수 필드가 빠졌습니다. submit_blog_content 도구를"
            " 다시 호출하되, 모든 필드를 빠짐없이 채워주세요."
        )
        data = _validate(_call_claude(system_prompt, retry_prompt))

    data["site"] = site
    data["keyword"] = keyword
    data["longtail_keywords"] = longtail
    return data
