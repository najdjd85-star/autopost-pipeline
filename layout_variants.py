"""글 구조(레이아웃) 변형 - 모든 글이 같은 컴포넌트 조합으로 나와 "템플릿 대량 생성"처럼 보이는
문제를 줄이기 위해, 글마다 서로 다른 구조를 골라 프롬프트에 주입한다.

최근에 쓴 구조는 사이트별 히스토리 파일(data/output/layout_history_{site}.json)에 기록해 두고,
최근 N개와 겹치지 않는 구조 중에서 무작위로 고른다.
"""
from __future__ import annotations

import json
import random
from typing import Any, Dict, List, Optional

from config import OUTPUT_DIR
from constants import (
    AFFILIATE_SLOT_BOT,
    AFFILIATE_SLOT_MID,
    AFFILIATE_SLOT_TOP,
    IMAGE_SLOT_1,
)
from utils.logger import get_logger

logger = get_logger(__name__)

_AVOID_RECENT = 4

_CALC_REQUIRED = (
    "계산기: 필수. [검증된 계산기]에 정확히 맞는 게 있으면 그 키와 CALCULATOR_SLOT을 쓰고, "
    "없으면 calculator_type='custom'으로 benefit-calc 위젯을 직접 작성."
)
_CALC_IF_VERIFIED = (
    "계산기: [검증된 계산기]에 정확히 맞는 게 있을 때만 calculator_type에 그 키를 넣고 "
    "CALCULATOR_SLOT을 삽입. 맞는 게 없으면 calculator_type='none'으로 하고 계산기를 넣지 마세요 "
    "(custom 위젯도 쓰지 말 것)."
)

VARIANTS: Dict[str, Dict[str, Any]] = {
    "qa": {
        "name": "지식인 Q&A형",
        "summary": "독자가 실제로 물어볼 질문을 소제목으로 순서대로 답해 가는 구조.",
        "components": [
            "도입부 FOMO 문단",
            "3분할 키 메트릭스 카드",
            "질문형 h2 소제목 5~6개(각 3~4문단)",
            "페르소나 사례 박스 3인(합격 1명, 불합격 2명)",
            "계산기",
            "FAQ 아코디언 4개 이상",
            "다음 단계 체크리스트",
        ],
        "skip": "가로 타임라인은 넣지 마세요.",
        "slots": {
            IMAGE_SLOT_1: "도입부 직후",
            AFFILIATE_SLOT_TOP: "메트릭스 카드 직후",
            AFFILIATE_SLOT_MID: "계산기 직후",
            AFFILIATE_SLOT_BOT: "글 최하단",
        },
        "calculator": _CALC_REQUIRED,
    },
    "case_story": {
        "name": "사례 스토리형",
        "summary": "가상 인물 3명의 상황→결과→원인→교훈을 이야기처럼 풀어가는 구조.",
        "components": [
            "한 인물의 짧은 에피소드로 시작하는 도입부(통계식 FOMO 문장으로 시작 금지)",
            "사례 h2 3개(각각 상황·결과·탈락/성공 원인·교훈을 3~4문단으로)",
            "3인 결과를 한눈에 비교하는 요약 표(table, 인라인 스타일)",
            "공통 교훈 박스",
            "FAQ 아코디언 3개",
            "다음 단계 체크리스트",
        ],
        "skip": "3분할 메트릭스 카드와 가로 타임라인은 넣지 마세요.",
        "slots": {
            IMAGE_SLOT_1: "도입 에피소드 직후",
            AFFILIATE_SLOT_TOP: "첫 번째 사례 섹션 직후",
            AFFILIATE_SLOT_MID: "요약 표 직후",
            AFFILIATE_SLOT_BOT: "글 최하단",
        },
        "calculator": _CALC_IF_VERIFIED + " 넣는다면 공통 교훈 박스 앞에 두세요.",
    },
    "step_guide": {
        "name": "단계별 가이드형",
        "summary": "준비물부터 신청 완료까지 순서대로 따라 하게 만드는 실전 가이드 구조.",
        "components": [
            "짧은 도입부(3~4문장)",
            "준비물 체크리스트(✅ 목록 박스)",
            "세로 번호 단계 5~7개(번호 원형 배지 + 설명 + 주의 박스)",
            "가로 타임라인(처리 기간/일정)",
            "흔한 실수 TOP5(번호 목록)",
            "FAQ 아코디언 3개",
        ],
        "skip": "페르소나 사례 박스와 3분할 메트릭스 카드는 넣지 마세요.",
        "slots": {
            IMAGE_SLOT_1: "도입부 직후",
            AFFILIATE_SLOT_TOP: "준비물 체크리스트 직후",
            AFFILIATE_SLOT_MID: "세로 단계 가이드 직후",
            AFFILIATE_SLOT_BOT: "글 최하단",
        },
        "calculator": _CALC_IF_VERIFIED + " 넣는다면 세로 단계 가이드 직후에 두세요.",
    },
    "compare_table": {
        "name": "비교표형",
        "summary": "선택지·조건을 표로 비교하고 대상별 추천을 제시하는 구조.",
        "components": [
            "도입부(어떤 선택이 헷갈리는지 짚기)",
            "핵심 비교 표(table, 최소 4행 3열, 인라인 스타일, 모바일에서 가로 스크롤 가능하게)",
            "표의 각 행을 풀어 설명하는 h2 섹션들",
            "'이런 분께 추천 / 이런 분께는 비추천' 2열 박스",
            "계산기",
            "FAQ 아코디언 4개",
            "다음 단계 체크리스트",
        ],
        "skip": "3분할 메트릭스 카드와 가로 타임라인은 넣지 마세요. 페르소나 사례는 1~2명으로 짧게.",
        "slots": {
            IMAGE_SLOT_1: "도입부 직후",
            AFFILIATE_SLOT_TOP: "비교 표 직후",
            AFFILIATE_SLOT_MID: "추천/비추천 박스 직후",
            AFFILIATE_SLOT_BOT: "글 최하단",
        },
        "calculator": _CALC_IF_VERIFIED + " 넣는다면 추천/비추천 박스 앞에 두세요.",
    },
    "myth_fact": {
        "name": "오해 vs 팩트형",
        "summary": "흔한 오해 5가지를 하나씩 뒤집으며 정확한 사실을 알려주는 구조.",
        "components": [
            "도입부(많이들 이렇게 알고 있다는 문제 제기)",
            "오해 vs 팩트 카드 5쌍(❌ 오해 / ⭕ 팩트 2열 카드)",
            "오해별 심층 h2 섹션(각 3문단 이상)",
            "한 줄 핵심 요약 박스",
            "짧은 사례 1개",
            "FAQ 아코디언 3개",
            "다음 단계 체크리스트",
        ],
        "skip": "3분할 메트릭스 카드와 가로 타임라인은 넣지 마세요. 페르소나 3인 박스 대신 짧은 사례 1개만.",
        "slots": {
            IMAGE_SLOT_1: "도입부 직후",
            AFFILIATE_SLOT_TOP: "오해 vs 팩트 카드 직후",
            AFFILIATE_SLOT_MID: "한 줄 핵심 요약 박스 직후",
            AFFILIATE_SLOT_BOT: "글 최하단",
        },
        "calculator": _CALC_IF_VERIFIED + " 넣는다면 한 줄 핵심 요약 박스 앞에 두세요.",
    },
    "brief_news": {
        "name": "핵심 브리핑형",
        "summary": "바뀐 점·일정을 먼저 요약하고 대상별로 정리하는 뉴스 브리핑 구조.",
        "components": [
            "상단 '3줄 핵심 요약' 박스",
            "3분할 키 메트릭스 카드",
            "일정/기한 가로 타임라인(3~5단계)",
            "'바뀐 점 / 유지되는 점' 2열 비교 박스",
            "대상별 Q&A h2 3개(예: 청년·직장인·부모님 가구 등 주제에 맞게)",
            "FAQ 아코디언 4개",
            "다음 단계 체크리스트",
        ],
        "skip": "페르소나 사례 박스는 넣지 마세요.",
        "slots": {
            IMAGE_SLOT_1: "3줄 요약 박스 직후",
            AFFILIATE_SLOT_TOP: "메트릭스 카드 직후",
            AFFILIATE_SLOT_MID: "바뀐 점/유지되는 점 박스 직후",
            AFFILIATE_SLOT_BOT: "글 최하단",
        },
        "calculator": _CALC_IF_VERIFIED + " 넣는다면 대상별 Q&A 앞에 두세요.",
    },
    "calc_first": {
        "name": "계산기 우선형",
        "summary": "계산기를 먼저 보여주고, 결과별 해석과 근거를 뒤에 붙이는 구조.",
        "components": [
            "2~3문장짜리 짧은 도입부",
            "계산기(도입부 바로 뒤)",
            "'결과가 이렇게 나왔다면' h2 3구간(충분/경계선/부족)별 해석",
            "계산 근거와 기준 설명 h2",
            "사례 박스 2인",
            "FAQ 아코디언 4개",
            "다음 단계 체크리스트",
        ],
        "skip": "3분할 메트릭스 카드와 가로 타임라인은 넣지 마세요.",
        "slots": {
            IMAGE_SLOT_1: "도입부 직후(계산기 앞)",
            AFFILIATE_SLOT_TOP: "'결과 해석' 섹션 직후",
            AFFILIATE_SLOT_MID: "사례 박스 직후",
            AFFILIATE_SLOT_BOT: "글 최하단",
        },
        "calculator": _CALC_REQUIRED + " 도입부 바로 뒤에 두세요.",
    },
}


def _history_path(site: str):
    return OUTPUT_DIR / f"layout_history_{site}.json"


def _load_history(site: str) -> List[str]:
    try:
        data = json.loads(_history_path(site).read_text(encoding="utf-8"))
        return [k for k in data if k in VARIANTS]
    except (OSError, ValueError):
        return []


def pick_variant(site: str, forced: Optional[str] = None) -> str:
    """최근 쓴 구조와 겹치지 않는 구조 키를 고른다."""
    if forced in VARIANTS:
        return forced
    recent = _load_history(site)[-_AVOID_RECENT:]
    candidates = [k for k in VARIANTS if k not in recent] or list(VARIANTS)
    return random.choice(candidates)


def record_variant(site: str, key: str) -> None:
    history = _load_history(site)
    history.append(key)
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        _history_path(site).write_text(json.dumps(history[-20:]), encoding="utf-8")
    except OSError as exc:
        logger.info("구조 히스토리 저장 실패(무시): %s", exc)


def format_variant_prompt(key: str) -> str:
    v = VARIANTS[key]
    components = "\n".join(f"  {i}. {c}" for i, c in enumerate(v["components"], 1))
    slots = "\n".join(f'  - "{token}": {where}' for token, where in v["slots"].items())
    return f"""[이번 글의 구조 - 반드시 이 구조로 쓰세요: {v['name']}]
{v['summary']}
다른 글과 겉모습이 똑같아 보이지 않도록, 아래 구성 순서를 지키세요.
- 필수 구성(순서대로):
{components}
- 제외: {v['skip']}
- 플레이스홀더 위치(문자 그대로 삽입):
{slots}
- {v['calculator']}
(구조 지시와 시스템 프롬프트의 컴포넌트 규칙이 다르면 이 구조 지시를 따르세요. 공통 규칙인
h2 인라인 스타일, 공식 CTA 버튼, 분량 3,000자 이상, 상식 깨기 단락 1개는 항상 유지합니다.)

"""
