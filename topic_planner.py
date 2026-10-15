"""주제 다양화 플래너 - 키워드 쉬어가기, 글 유형 로테이션, 제목 각도 상한, 뉴스 연동.

글이 단조로워 보이던 원인을 코드로 막는다.
1. 같은 핵심 키워드/계열(예: 해외주식 양도세·배당세·손익통산)이 연달아 나오지 않게 한다.
   - 키워드마다 "마지막으로 쓴 지 얼마나 됐는지"를 (선정 히스토리 + 최근 발행 제목)에서 계산해 가장 오래된 것부터 고른다.
   - 최근 선정한 키워드와 같은 계열은 잠시 제외한다.
2. 글 유형(개편 해설/일정 캘린더/계산 사례집/선택 가이드/용어 정리/체크리스트/문제 해결/뉴스 풀이)을 돌려 쓴다.
   기존 "탈락·오해" 각도는 문제 해결 유형 하나로 줄어든다.
3. 최근 제목에 부정 어휘(탈락/오해/손해...)가 몰려 있으면 이번 제목에서 금지한다.
4. 이번 주 정책 뉴스가 사이트 키워드와 맞으면 뉴스 풀이 유형으로 쓴다.
5. 검증된 팩트 시트가 없는 확장 키워드는 수치를 지어내지 않도록 주의 문구를 붙인다.

토큰을 쓰지 않는다(전부 로컬 계산). 히스토리는 data/output/topic_history_{site}.json.
"""
from __future__ import annotations

import json
import random
from typing import Any, Dict, List, Optional

from config import OUTPUT_DIR
from fact_sheets import get_fact_sheet
from utils.logger import get_logger

logger = get_logger(__name__)

_AVOID_RECENT_TYPES = 3
_AVOID_RECENT_FAMILIES = 3
_PICK_FROM_OLDEST = 4
_HISTORY_KEEP = 30
_NEGATIVE_WINDOW = 10
_NEGATIVE_LIMIT = 4

# 같은 계열로 묶을 첫 단어 (표기가 달라도 같은 주제 덩어리)
_FAMILY_ALIASES = {
    "미국주식": "해외주식",
    "국내시장": "해외주식",
    "연말정산": "연말정산",
    "종합소득세": "소득세",
    "프리랜서": "소득세",
    "연금저축": "연금계좌",
    "IRP": "연금계좌",
    "퇴직연금": "연금계좌",
    "퇴직금": "연금계좌",
    "기초연금": "연금",
    "국민연금": "국민연금",
    "알뜰폰": "알뜰폰",
    "인터넷": "인터넷",
    "정수기": "렌탈",
    "공기청정기": "렌탈",
    "안마의자": "렌탈",
    "비데": "렌탈",
    "휴대폰": "휴대폰",
    "자급제폰": "휴대폰",
    "중고폰": "휴대폰",
    "청년월세": "청년",
    "청년도약계좌": "청년",
    "청년지원금": "청년",
    "청년내일저축계좌": "청년",
    "청년": "청년",
    "근로장려금": "장려금",
    "자녀장려금": "장려금",
    "부모급여": "육아",
    "아동수당": "육아",
    "첫만남이용권": "육아",
    "산후조리비": "육아",
    "다자녀": "육아",
}

NEGATIVE_WORDS = (
    "탈락", "오해", "날렸", "날릴", "날리", "손해", "놓친", "놓치", "폭탄", "추징", "거절", "실화", "사실은 아닙니다",
    "몰라서", "배신", "함정",
)

# 글 유형: angle(다룰 각도), title(제목 톤), layouts(어울리는 구조 키), intro(도입 방식)
CONTENT_TYPES: Dict[str, Dict[str, Any]] = {
    "policy_update": {
        "name": "개편·변경 해설",
        "angle": "올해 무엇이 바뀌었고(기준·금액·일정), 누가 영향을 받는지 해설한다. 바뀌기 전과 후를 대비하고, 해당·비해당 대상을 갈라 준다.",
        "title": "'2026년 달라진 점', '무엇이 바뀌었나' 같은 정보형 제목. 부정 어휘 금지.",
        "intro": "도입부는 '바뀐 점 한 줄 요약'으로 시작(통계 겁주기 문장 금지).",
        "layouts": ["brief_news", "compare_table", "myth_fact"],
    },
    "calendar": {
        "name": "마감일·일정 캘린더",
        "angle": "언제까지 무엇을 해야 하는지를 시간순(월별·단계별)으로 정리한다. 놓치기 쉬운 기한과 준비 시작 시점을 알려 준다.",
        "title": "'언제까지', '일정 총정리', '월별로 정리' 같은 일정형 제목. 부정 어휘 금지.",
        "intro": "도입부는 '지금 시점에서 가장 가까운 기한'으로 시작.",
        "layouts": ["step_guide", "brief_news"],
    },
    "case_calc": {
        "name": "계산 사례집",
        "angle": "구체적인 숫자 사례 3개를 직접 계산해 보여준다(가상 인물, 입력값→계산 과정→결과). 숫자는 확인된 기준 안에서만 쓴다.",
        "title": "'직접 계산해보면', '이 조건이면 얼마' 같은 숫자형 제목. 부정 어휘 금지.",
        "intro": "도입부는 첫 사례의 입력값과 결과를 먼저 보여주며 시작.",
        "layouts": ["calc_first", "case_story"],
    },
    "choose": {
        "name": "선택 가이드(A vs B)",
        "angle": "헷갈리는 두 가지 이상의 선택지를 같은 기준으로 비교하고, 상황별 추천을 제시한다.",
        "title": "'A vs B', '어느 쪽이 유리할까' 같은 비교형 제목. 부정 어휘 금지.",
        "intro": "도입부는 '무엇이 헷갈리는지'를 짚으며 시작.",
        "layouts": ["compare_table", "qa"],
    },
    "glossary": {
        "name": "용어·개념 정리",
        "angle": "이 주제를 이해할 때 자주 막히는 용어와 개념을 쉬운 말로 풀고 예시로 설명한다. 용어는 반드시 이 글의 주제에서 실제로 쓰이는 것만 고른다(다른 분야의 용어를 끌어오지 않는다).",
        "title": "'한 번에 이해하기', '쉽게 풀어보면' 같은 설명형 제목. 부정 어휘 금지.",
        "intro": "도입부는 가장 헷갈리는 용어 하나를 쉬운 비유로 풀며 시작.",
        "layouts": ["qa", "myth_fact"],
    },
    "checklist": {
        "name": "체크리스트·서류 모음",
        "angle": "신청 전에 확인할 항목과 준비 서류를 빠짐없이 정리한다. 항목마다 어디서 확인/발급하는지 알려 준다.",
        "title": "'체크리스트', '준비물 한눈에' 같은 실용형 제목. 부정 어휘 금지.",
        "intro": "도입부는 짧게, 바로 체크리스트로 들어갈 수 있게 시작.",
        "layouts": ["step_guide", "qa"],
    },
    "problem_solve": {
        "name": "탈락·거절 원인 해결",
        "angle": "많은 사람이 탈락·거절되는 구체적 원인과 해결 방법을 사례로 보여 준다.",
        "title": "",  # 기존 시스템 프롬프트의 제목 규칙을 그대로 따른다.
        "intro": "",
        "layouts": ["qa", "case_story", "myth_fact", "step_guide"],
    },
    "news_hook": {
        "name": "이번 주 소식 풀이",
        "angle": "아래 [이번 주 실제 뉴스]를 계기로, 독자에게 어떤 의미인지 풀이한다. 뉴스에 없는 수치는 지어내지 않는다.",
        "title": "'이번 주', '발표', '시행' 같은 소식형 제목. 부정 어휘 금지.",
        "intro": "도입부는 뉴스의 핵심 한 줄로 시작.",
        "layouts": ["brief_news", "qa"],
    },
}

_UNVERIFIED_CAUTION = (
    "[주의 - 검증된 팩트 시트가 없는 주제]\n"
    "이 주제는 검증된 수치 자료가 없습니다. 금액·소득 기준·기한·요율 같은 구체 수치는 위 상위 글 레퍼런스에서 "
    "여러 곳이 일치하는 경우에만 쓰고, 확신이 없으면 숫자를 쓰지 말고 '공식 공고/약관에서 확인'으로 안내하세요. "
    "특정 상품명·요금제 가격을 지어내지 마세요.\n\n"
)


def _history_path(site: str):
    return OUTPUT_DIR / f"topic_history_{site}.json"


def _load_history(site: str) -> Dict[str, List[str]]:
    try:
        data = json.loads(_history_path(site).read_text(encoding="utf-8"))
        return {"keywords": list(data.get("keywords", [])), "types": list(data.get("types", []))}
    except (OSError, ValueError, AttributeError):
        return {"keywords": [], "types": []}


def record_pick(site: str, keyword: str, content_type: str) -> None:
    history = _load_history(site)
    history["keywords"].append(keyword)
    history["types"].append(content_type)
    history = {k: v[-_HISTORY_KEEP:] for k, v in history.items()}
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        _history_path(site).write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.info("주제 히스토리 저장 실패(무시): %s", exc)


def family_of(keyword: str) -> str:
    first = (keyword or "").split()[0] if (keyword or "").split() else ""
    return _FAMILY_ALIASES.get(first, first)


def _tokens(keyword: str) -> List[str]:
    return [t for t in (keyword or "").split() if len(t) >= 2]


def _title_distance(seed: str, titles: List[str]) -> Optional[int]:
    """최근 제목(최신순)에서 이 키워드가 마지막으로 나온 위치(0=가장 최근). 없으면 None.

    제목은 키워드를 그대로 쓰지 않고 바꿔 쓰는 경우가 많아(예: '인터넷 이사 이전설치' -> '인터넷 이전설치'),
    토큰이 하나만 빠져도 같은 키워드로 본다.
    """
    tokens = _tokens(seed)
    if not tokens:
        return None
    need = len(tokens) if len(tokens) == 1 else len(tokens) - 1
    for index, title in enumerate(titles):
        if sum(1 for t in tokens if t in title) >= need:
            return index
    return None


def _recency(seed: str, history_keywords: List[str], titles: List[str]) -> int:
    """클수록 오래전에 썼다는 뜻(안 쓴 키워드는 매우 큼). 히스토리와 제목 중 더 최근 기록을 쓴다."""
    distances: List[int] = []
    for offset, kw in enumerate(reversed(history_keywords)):
        if kw == seed:
            distances.append(offset)
            break
    title_distance = _title_distance(seed, titles)
    if title_distance is not None:
        distances.append(title_distance)
    return min(distances) if distances else 10_000


def pick_keyword(site: str, seeds: List[str], recent_titles: List[str]) -> str:
    """가장 오래 안 쓴 키워드를 고른다(최근 계열 제외, 오래된 상위 몇 개 중 무작위)."""
    if not seeds:
        return ""
    history = _load_history(site)
    recent_families = {family_of(k) for k in history["keywords"][-_AVOID_RECENT_FAMILIES:]}
    for title in recent_titles[:_AVOID_RECENT_FAMILIES]:
        for seed in seeds:
            if _title_distance(seed, [title]) == 0:
                recent_families.add(family_of(seed))

    scored = [(seed, _recency(seed, history["keywords"], recent_titles)) for seed in seeds]
    eligible = [item for item in scored if family_of(item[0]) not in recent_families] or scored
    eligible.sort(key=lambda item: -item[1])
    return random.choice([seed for seed, _ in eligible[:_PICK_FROM_OLDEST]])


def pick_content_type(site: str, news_available: bool) -> str:
    history = _load_history(site)
    recent = history["types"][-_AVOID_RECENT_TYPES:]
    pool = [t for t in CONTENT_TYPES if t != "news_hook" or news_available]
    candidates = [t for t in pool if t not in recent]
    if news_available and "news_hook" in candidates:
        return "news_hook"  # 이번 주 소식은 시의성이 있어서 쓸 수 있을 때 우선
    if candidates:
        return random.choice(candidates)
    return random.choice(pool)


def negative_title_count(titles: List[str]) -> int:
    return sum(1 for t in titles[:_NEGATIVE_WINDOW] if any(w in t for w in NEGATIVE_WORDS))


def find_news_for_site(seeds: List[str], briefings: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """사이트 키워드와 맞는 정책 뉴스 한 건과 그 키워드를 찾는다."""
    for item in briefings or []:
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        for seed in seeds:
            tokens = _tokens(seed)
            if tokens and any(t in text for t in tokens if len(t) >= 3):
                return {"keyword": seed, "title": item.get("title", ""), "summary": item.get("summary", ""), "url": item.get("url", "")}
    return None


def _strip(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def plan_topic(
    site: str,
    seeds: List[str],
    briefings: List[Dict[str, str]],
    recent_titles: List[str],
    forced_keyword: Optional[str] = None,
    unverified_seeds: Optional[set] = None,
) -> Dict[str, Any]:
    """오늘 글의 키워드·유형·프롬프트 블록·어울리는 구조 목록을 정한다."""
    history = _load_history(site)
    news = None if forced_keyword else find_news_for_site(seeds, briefings)
    if news:
        families = {family_of(k) for k in history["keywords"][-_AVOID_RECENT_FAMILIES:]}
        if family_of(news["keyword"]) in families or _title_distance(news["keyword"], recent_titles[:_AVOID_RECENT_FAMILIES]) == 0:
            news = None

    content_type = pick_content_type(site, news_available=news is not None)
    if content_type != "news_hook":
        news = None
    keyword = forced_keyword or (news["keyword"] if news else pick_keyword(site, seeds, recent_titles))

    spec = CONTENT_TYPES[content_type]
    block = ""
    if content_type != "problem_solve":
        block += (
            f"[이번 글의 유형 - {spec['name']}]\n"
            f"- 다룰 각도: {spec['angle']}\n"
            f"- 제목 톤: {spec['title']}\n"
        )
        if spec["intro"]:
            block += f"- 도입: {spec['intro']}\n"
        block += (
            "(유형 지시는 '무엇을 어떤 각도로 다룰지', 구조 지시는 '컴포넌트를 어떤 순서로 배치할지'입니다. 둘이 충돌하면 "
            "구조 지시의 컴포넌트 규칙을 따르되 각도와 제목 톤은 유형 지시를 따르세요. 시스템 프롬프트의 FOMO·탈락 겁주기 "
            "도입 규칙은 이번 글에서는 적용하지 않습니다.)\n\n"
        )
    elif negative_title_count(recent_titles) >= _NEGATIVE_LIMIT:
        block += (
            "[제목 톤 제한]\n"
            f"최근 제목 {_NEGATIVE_WINDOW}개 중 {negative_title_count(recent_titles)}개가 탈락·오해·손해 같은 부정 어휘를 썼습니다. "
            "이번 제목에는 그런 어휘를 쓰지 말고, 정보형·숫자형·질문형으로 쓰세요.\n\n"
        )

    if content_type == "news_hook" and news:
        block += (
            "[이번 주 실제 뉴스]\n"
            f"- 제목: {_strip(news['title'])[:150]}\n- 요약: {_strip(news['summary'])[:400]}\n"
            "뉴스에 적힌 사실만 쓰고, 적혀 있지 않은 금액·일정·대상은 지어내지 마세요.\n\n"
        )

    if unverified_seeds and keyword in unverified_seeds and not get_fact_sheet(keyword):
        block += _UNVERIFIED_CAUTION

    return {
        "keyword": keyword,
        "content_type": content_type,
        "block": block,
        "layouts": spec["layouts"],
    }
