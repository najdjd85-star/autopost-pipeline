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

import html
import re
from typing import Any, Dict, List, Optional

from calculator_library import CALCULATOR_CHOICES
from competitor_analyzer import get_top_blog_references
from fact_sheets import get_fact_sheet
from layout_variants import VARIANTS, format_variant_prompt, pick_variant, record_variant
from situational_personas import format_persona_prompt, pick_persona, record_persona
from config import settings
from constants import (
    AFFILIATE_SLOT_BOT,
    AFFILIATE_SLOT_MID,
    AFFILIATE_SLOT_TOP,
    CALCULATOR_SLOT,
    CLAUDE_MODEL,
    IMAGE_SLOT_1,
    REQUIRED_GENERATOR_KEYS,
    SITE_CATEGORIES,
    SITE_LABELS,
    SITE_OFFICIAL_URLS,
)
from keyword_expander import expand_to_longtail
from trend_scraper import fetch_today_hot_topics
from utils.logger import get_logger
from video_trend_analyzer import format_trend_briefing, get_trending_videos
from wp_client import WordPressClient

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
            "title": {
                "type": "string",
                "description": (
                    "SEO 및 클릭률을 고려한 제목. 아래 [절대 규칙 1의 6번 - 제목 구조 다양화] "
                    "규칙을 반드시 따를 것 - 매번 같은 문장 틀(예: '~~, 매년 수십만 명이 이 조건 "
                    "하나로 OO합니다')을 재사용하지 말고, 그때그때 다른 구조를 골라 쓴다."
                ),
            },
            "category": {
                "type": "string",
                "description": "이 글의 워드프레스 카테고리. 아래 [사용 가능한 카테고리] 목록 중 글 주제에 가장 맞는 것 하나를 글자 그대로 선택할 것.",
            },
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
                },
                "required": ["slot_1"],
            },
            "calculator_type": {
                "type": "string",
                "description": (
                    "아래 [검증된 계산기] 목록 중 글 주제에 정확히 맞는 키 하나. 구조 지시상 계산기를 "
                    "빼거나 맞는 게 없으면 'none', 필수인데 맞는 게 없으면 'custom'."
                ),
            },
            "slug": {
                "type": "string",
                "description": (
                    "글 주소(URL)용 영문 슬러그. 소문자 영문/숫자와 하이픈만, 3~5단어, 60자 이내. "
                    "예: 'part-time-income-support-check'. 한글 금지."
                ),
            },
            "threads_post": {
                "type": "string",
                "description": (
                    "스레드 본문 요약 (500자 이내). 존댓말 금지. 톤은 '조사해보고 알게 된 팩트를 "
                    "혼잣말하듯 친구에게 공유'하는 느낌(~더라, ~였음, ~인 듯, ~임). 훈계·명령형, "
                    "'너네' 같은 호칭, 과격한 말투는 금지(돈·복지 정보라 신뢰가 중요함). "
                    "'내가 직접 겪어봤는데' 같은 지어낸 경험담도 금지하고 '찾아보니까' 식의 "
                    "조사형 표현만 쓴다. 구체적인 숫자나 조건을 최소 1개 넣는다. 끝에서 두 번째 "
                    "줄에는 독자가 댓글로 자기 상황을 남기고 싶어지는 짧은 질문을 넣는다"
                    "(예: '너는 어떤 경우인지 궁금함'). 스레드 본문 자체에는 링크를 넣지 않으므로"
                    "(링크는 별도 첫 댓글에만 들어감), 맨 마지막 문장은 댓글을 확인하도록 유도하는 "
                    "문장으로 마무리한다. 예: '자세한 내용/링크는 댓글에 남겨둠', '나머지는 댓글에 있음'."
                ),
            },
            "threads_comment": {
                "type": "string",
                "description": (
                    "스레드 첫 댓글. threads_post와 동일하게 반말체 유지. '이거 안 보면 진짜 "
                    "손해다' 식으로 안 보면 손해 본다는 느낌을 강하게 주는 클릭 유도 문장으로 "
                    "시작하고, 그 다음 블로그 링크 자리에 {POST_URL} 플레이스홀더를 그대로 넣어 "
                    "마무리한다. 예: '이거 모르고 넘어가면 진짜 손해임, 자세한 내용 여기서 "
                    "확인해 {POST_URL}'"
                ),
            },
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
    categories = SITE_CATEGORIES.get(site, ())
    category_list = ", ".join(f'"{c}"' for c in categories)
    calculator_choices = "\n".join(f"   - {k}: {d}" for k, d in CALCULATOR_CHOICES.items())
    return f"""당신은 대한민국 최상위 1% 바이럴 블로그 카피라이터이자 UI/UX 퍼블리셔입니다.
지금부터 "{site_label}" 주제로 워드프레스에 바로 게시할 완성된 HTML 콘텐츠를 작성합니다.

[사용 가능한 카테고리] {category_list}
category 필드에는 위 목록 중 오늘 글의 주제와 가장 가까운 것 하나를 띄어쓰기/글자 하나까지
정확히 그대로 입력하세요. 목록에 없는 이름을 새로 만들어내지 마세요.

[절대 규칙 1 - 심리 작성 규칙]
1. 도입부(intro, 본문 첫 문단): 지루한 공고문 말투를 절대 금지합니다. "매년 수십만 명이 이
   조건 하나 때문에 탈락합니다" 같은 상실 공포(FOMO)와 신청자 탈락 원인으로 글을 시작하세요.
   단, 이건 본문 첫 문단 예시일 뿐 title에 그대로 쓰라는 뜻이 아닙니다(아래 6번 참고).
2. 소제목(h2/h3): 실제 네이버 지식인에 올라올 법한 구어체 의문문 형태로 호기심을 유발하세요.
   예) "저도 이거 받을 수 있나요?", "이미 신청했는데 왜 탈락했을까요?"
3. 페르소나 사례: [이번 글의 구조]가 요구할 때, 조건이 비슷하지만 결과가 상반된 가상 인물(예:
   "김OO씨(합격)" vs "이OO씨(불합격)")의 판정 비교를 박스나 섹션으로 넣으세요. 인원수와 형식은
   구조 지시를 따릅니다.
4. 상식 깨기(Myth Buster): 대중이 흔히 오해하는 사실 1가지를 제시하고 바로 팩트로 정정하는
   단락을 반드시 넣으세요.
5. 분량과 깊이: 짧고 얕은 글은 절대 안 됩니다. html_content의 실제 텍스트 분량이 최소
   공백 포함 3,000자 이상이 되도록, 아래 내용을 전부 구체적으로 풀어서 쓰세요.
   - 각 소제목(h2) 밑에는 최소 3~4문단 분량의 설명을 넣으세요 (한두 문장으로 끝내지 마세요).
   - 조건/기준을 나열할 때는 각 항목마다 "왜 이 기준이 있는지, 실제로 어떤 case에서
     문제가 되는지" 구체적 사례나 숫자를 곁들여 설명하세요.
   - 페르소나 사례·FAQ·체크리스트의 개수와 형식은 [이번 글의 구조] 지시를 따르되, FAQ 답변은
     2~3문장 이상으로 충분히 설명하세요.
   - 구조 지시에 체크리스트가 있으면 "다음 단계로 무엇을 확인해야 하는지"를 정리하세요.
   - 정확성: 지원금액·소득 기준·세율·기한 같은 수치는 확실히 아는 공식 수치만 쓰세요. 확실하지
     않으면 구체 숫자를 지어내지 말고 "정확한 기준은 공식 사이트에서 확인" 식으로 안내하세요.
     레퍼런스 블로그의 수치가 서로 다르면 단정하지 마세요.
6. 제목(title) 구조 다양화: title은 본문 도입부와 다른 문장 구조를 써야 합니다.
   "~~, 매년 수십만 명이 이 조건 하나로 OO합니다/탈락합니다" 같은 특정 문장 틀을
   매번 반복하지 마세요 - 실제로 이 틀만 계속 우려먹어서 제목만 보면 다 똑같아
   보인다는 지적을 받았습니다. 아래 서로 다른 제목 구조 중에서 오늘 주제에 가장
   잘 맞는 것을 골라 쓰되, [중요 - 최근 발행한 글 제목 목록]에 나온 구조와도
   겹치지 않게 하세요:
   - 질문형: "OO, 저만 안 되는 걸까요?"
   - 직접화법형: "저는 분명 OO인데 왜 탈락했을까요"
   - 숫자/TOP형: "OO 탈락 이유 TOP3, 이것만 알아도 다릅니다"
   - 경고/시점형: "OO 신청 전에 이것부터 확인하세요"
   - 비교형: "OO 자가 vs 전세, 조건이 이렇게 다릅니다"
   - 후기/발견형: "OO 후기 뒤지다 알게 된 사실"
   - 총정리/나열형: "OO 조건 5가지, 하나라도 놓치면 탈락"
   - 반전형: "다들 OO라고 아는데, 사실은 아닙니다"

[절대 규칙 2 - 반응형 비주얼 UI 컴포넌트 (인라인 CSS로 직접 작성, 외부 CSS 파일 참조 금지)]
아래는 컴포넌트 작성 규격입니다. 어떤 컴포넌트를 쓸지, 어떤 순서로 쓸지는 사용자 메시지의
[이번 글의 구조]가 정하며(매 글 다른 구조), 0·5·6번은 모든 글에 공통입니다.
0. 모든 `<h2>` 소제목은 일반 본문과 확실히 구분되도록 인라인 스타일을 넣으세요
   (예: 좌측 컬러 border-left 4px + 배경색 옅게 + padding, 또는 이모지 prefix + 밑줄 accent).
   본문 대비 시각적으로 눈에 띄어야 하며, 글 안의 모든 h2에 동일한 스타일을 일관되게
   적용하세요 (일부만 꾸미고 나머지는 기본 글씨로 두지 마세요).
1. 3분할 키 메트릭스 카드: 상단에 지원금액/대상/기간(또는 사이트 주제에 맞는 3개 핵심 지표)을
   flexbox 또는 grid로 3등분한 카드 UI.
2. 3단계 타임라인 프로세스 바: 신청 절차를 3단계로 시각화한 가로 타임라인.
3. `<details>` 기반 아코디언 FAQ: 질문 4개 이상, `<summary>`와 본문(2~3문장 이상)으로 구성.
4. 계산기: 아래 [검증된 계산기] 중 오늘 글 주제에 정확히 맞는 것이 있으면 calculator_type에 그
   키를 넣고, 본문에는 위젯 코드를 직접 쓰지 말고 "{CALCULATOR_SLOT}" 자리표시자만 넣으세요
   (공식 수치가 검증된 계산기가 코드로 자동 삽입됩니다). [이번 글의 구조]가 계산기를 넣지
   말라고 하거나 맞는 검증 계산기가 없으면 calculator_type을 "none"으로 하세요. 구조가 계산기를
   필수로 요구하는데 맞는 게 없을 때만 calculator_type을 "custom"으로 하고 `<div class="benefit-calc">` 모의 판별/계산기 위젯을 직접 작성하세요
   (순수 Vanilla JavaScript, 외부 라이브러리 금지, 반드시 동작하는 JS). custom 위젯에는 정확히
   아는 공식 수치만 쓰고, 기준값이 불확실하면 "자격 있음/없음" 판정 대신 입력값의 단순 계산이나
   체크리스트로 만드세요 (틀린 기준으로 신청을 권하면 안 됩니다).
   [검증된 계산기]
{calculator_choices}
5. 그라데이션 배경의 공식 신청 바로가기 CTA 버튼 (linear-gradient 인라인 스타일).
   href는 반드시 "{official_url}" 을 그대로 사용하세요 (실제 존재하는 공식 사이트 주소입니다).
   "#"이나 다른 임의의 주소를 절대 사용하지 마세요 - 클릭했을 때 아무 데도 안 가는
   가짜 버튼이 되어서는 안 됩니다.
6. 아래 플레이스홀더를 정확히 그대로(문자 변경 없이) 삽입하되, 위치는 [이번 글의 구조]가
   지정한 대로 따르세요:
   - "{IMAGE_SLOT_1}"
   - "{AFFILIATE_SLOT_TOP}"
   - "{CALCULATOR_SLOT}" : 4번에서 검증된 계산기를 고른 경우에만
   - "{AFFILIATE_SLOT_MID}"
   - "{AFFILIATE_SLOT_BOT}"

[절대 규칙 3 - 레퍼런스 처리 원칙]
아래 사용자 메시지에 상위 노출 경쟁 블로그의 제목/핵심 텍스트가 주어집니다.
그 안의 "사실 정보(수치, 조건, 절차 등)"는 빠짐없이 흡수하되, 문장 표현·문단 구성·소제목
전부를 100% 새롭게 재창작해야 합니다. 문장을 그대로 베끼거나 표현만 살짝 바꾸는 것은 금지입니다.

[출력 형식]
설명이나 마크다운 없이, 반드시 제공된 도구(submit_blog_content)를 한 번 호출해서 모든 필드를
채워 제출하세요. html_content는 완성된 HTML을 그대로(이스케이프 걱정 없이 자연스럽게 줄바꿈과
큰따옴표를 포함해서) 작성하면 됩니다.
"""


def _fetch_recent_titles(site: str, days: int = 30) -> List[str]:
    """최근 발행 글 제목 목록 (키워드 중복 회피 + Claude에게 반복 금지 지시용)."""
    try:
        wp = WordPressClient(site)
        posts = wp.get_recent_posts(days=days, per_page=30)
        return [
            html.unescape(p.get("title", {}).get("rendered", ""))
            for p in posts
            if p.get("title")
        ]
    except Exception as exc:  # noqa: BLE001 - 실패해도 생성 자체는 막지 않는다
        logger.info("[Site %s] 최근 글 제목 조회 실패, 중복 회피 없이 진행: %s", site, exc)
        return []


def _pick_fresh_keyword(keywords: List[str], recent_titles: List[str]) -> str:
    """최근 제목에 이미 등장한 키워드는 건너뛰고, 아직 안 쓴 키워드를 고른다.

    site별 SITE_SEED_KEYWORDS가 매번 keywords[0]에 고정으로 오기 때문에, 이 함수가
    없으면 매일 똑같은 메인 키워드로 글을 써서(예: 매번 "연말정산 환급") 제목/구성이
    거의 똑같은 글이 계속 쌓이는 문제가 실제로 있었다.
    """
    for kw in keywords:
        if not any(kw in title for title in recent_titles):
            return kw
    return keywords[0] if keywords else ""


def build_user_prompt(
    site: str,
    keyword: str,
    longtail: List[str],
    references: List[Dict[str, str]],
    trend_briefing: str,
    video_trend_briefing: str = "",
    recent_titles: Optional[List[str]] = None,
    layout_block: str = "",
    persona_block: str = "",
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

    if recent_titles:
        recent_block = "\n".join(f"- {t}" for t in recent_titles[:15])
        dedup_section = f"""[중요 - 최근 발행한 글 제목 목록 (절대 반복 금지)]
아래는 이 사이트에 최근 발행된 글 제목들입니다. 오늘 쓸 글은 이 글들과
제목·소제목 구성·페르소나 이름(김OO씨/이OO씨 등)·구체적 사례·전개 순서가
겹치면 안 됩니다. 같은 메인 키워드를 다루더라도 완전히 다른 세부 각도
(예: 다른 대상층, 다른 탈락/성공 사유, 다른 조건, 다른 최신 이슈)로
새롭게 써야 합니다.

특히 title의 "문장 구조"도 아래 목록과 겹치면 안 됩니다. 아래 목록을 훑어보고
이미 많이 쓰인 문장 틀(예: "~~, 매년 수십만 명이 이 조건 하나로 OO합니다" 류가
반복되고 있다면)은 이번에는 피하고, 시스템 프롬프트의 [절대 규칙 1의 6번]에 있는
다른 제목 구조를 사용하세요.
{recent_block}

"""
    else:
        dedup_section = ""

    fact_sheet = get_fact_sheet(keyword)
    if fact_sheet:
        dedup_section += fact_sheet + "\n"
    dedup_section += layout_block
    dedup_section += persona_block

    return f"""{dedup_section}[오늘의 트렌드 브리핑]
{trend_briefing}

[메인 키워드] {keyword}
[확장된 롱테일 키워드 후보] {', '.join(longtail)}

[상위 1~3위 블로그 레퍼런스 - 팩트만 흡수, 문체는 100% 재창작]
{ref_block}

[최근 3개월 조회수 상위 관련 유튜브 영상 - title/html_content 작성 시
제목·후킹 패턴만 참고하고 내용/문장은 절대 베끼지 말 것. 100% 새로운 글로 작성]
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


def generate_post(
    site: str,
    base_keyword: Optional[str] = None,
    layout: Optional[str] = None,
    persona: Optional[str] = None,
) -> Dict[str, Any]:
    """사이트별 콘텐츠를 생성한다.

    site: "A"/"B"/"C" (또는 "site_a" 등)
    base_keyword: 생략 시 오늘의 핫토픽에서 자동 선정.

    ANTHROPIC_API_KEY가 없으면 GeneratorNotConfiguredError를 던진다 - 호출부
    (main.py/telegram_bot.py)에서만 잡아 로그/알림 후 안전하게 종료해야 한다.
    """
    site = site.upper().replace("SITE_", "")

    hot = fetch_today_hot_topics(site)
    recent_titles = _fetch_recent_titles(site)
    keyword = base_keyword or (
        _pick_fresh_keyword(hot["keywords"], recent_titles)
        if hot["keywords"]
        else SITE_LABELS.get(site, site)
    )

    longtail = expand_to_longtail(keyword)
    references = get_top_blog_references(longtail[0] if longtail else keyword)

    try:
        video_trends = get_trending_videos(keyword)
        video_trend_briefing = format_trend_briefing(video_trends)
    except Exception as exc:  # noqa: BLE001 - 선택 기능, 실패해도 계속 진행
        logger.info("유튜브 트렌드 조회 실패, 참고 없이 진행: %s", exc)
        video_trend_briefing = ""

    variant = pick_variant(site, layout)
    logger.info("[Site %s] 이번 글 구조: %s (%s)", site, variant, VARIANTS[variant]["name"])
    target_persona = pick_persona(site, persona)
    if target_persona:
        logger.info("[Site %s] 이번 글 타깃 상황: %s", site, target_persona)

    system_prompt = build_system_prompt(site)
    user_prompt = build_user_prompt(
        site,
        keyword,
        longtail,
        references,
        hot["briefing_text"],
        video_trend_briefing,
        recent_titles,
        format_variant_prompt(variant),
        format_persona_prompt(target_persona),
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

    valid_categories = SITE_CATEGORIES.get(site, ())
    if valid_categories and data.get("category") not in valid_categories:
        logger.warning(
            "[Site %s] Claude가 목록에 없는 카테고리(%s)를 반환해 기본값으로 대체합니다.",
            site,
            data.get("category"),
        )
        data["category"] = valid_categories[0]

    if data.get("calculator_type") not in CALCULATOR_CHOICES and data.get("calculator_type") != "none":
        data["calculator_type"] = "custom"
    data["layout_variant"] = variant
    record_variant(site, variant)
    if target_persona:
        data["target_persona"] = target_persona
        record_persona(site, target_persona)

    slug = str(data.get("slug", "")).strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+){1,6}", slug) or len(slug) > 60:
        data.pop("slug", None)
    else:
        data["slug"] = slug

    data["site"] = site
    data["keyword"] = keyword
    data["longtail_keywords"] = longtail
    return data
