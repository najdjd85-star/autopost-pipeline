"""상황별(연령·직업·가구형태) 롱테일 타깃팅.

지자체별 세부 기준(예: "인천 미추홀구 청년월세지원")은 지역마다 실제 조건이 달라
파이프라인에 그 데이터가 없는 한 지어내게 될 위험이 커서 쓰지 않는다. 대신 전국
공통 제도 안에서 "어떤 상황의 사람이 보는 글인가"만 바꿔서 롱테일을 만든다 -
"40대 직장인 주택담보대출 거치기간 연장 조건"처럼 지역 없이도 구체성을 낼 수 있다.

layout_variants.py와 같은 패턴으로, 사이트별 최근 사용 이력을 피해 돌아가며 고른다.
"""
from __future__ import annotations

import json
import random
from typing import List, Optional

from config import OUTPUT_DIR
from constants import SITE_A, SITE_B, SITE_C
from utils.logger import get_logger

logger = get_logger(__name__)

_AVOID_RECENT = 5

SITE_PERSONAS = {
    SITE_A: (
        "사회초년생(첫 취업, 소득 신고 이력 짧음)",
        "프리랜서·N잡러(소득이 들쭉날쭉함)",
        "맞벌이 부부(가구소득 합산이 쟁점)",
        "1인가구 청년",
        "부모님과 함께 사는 미혼 자녀(세대분리 쟁점)",
        "신혼부부(혼인신고 전후)",
        "다자녀 가구",
        "비정규직·계약직 근로자",
        "자영업자·소상공인",
        "최근 실직·퇴사한 구직자",
    ),
    SITE_B: (
        "자취 시작한 사회초년생",
        "부모님 명의 회선을 쓰다 독립하는 자녀",
        "가족 여러 명이 회선을 합치려는 가구",
        "노년층 보호자가 대신 가입해주는 경우",
        "자주 해외로 출장·여행 가는 직장인",
        "재택근무라 인터넷 의존도가 높은 프리랜서",
        "자취 자취 자취생 계약 만료로 이사하는 세입자",
        "1인가구 고정비를 줄이려는 사람",
    ),
    SITE_C: (
        "프리랜서·3.3% 원천징수 근로자",
        "맞벌이 부부(공제 배분이 쟁점)",
        "투잡·N잡러",
        "사회초년생(첫 연말정산)",
        "은퇴를 앞둔 50대",
        "해외주식 투자자",
        "개인사업자·간이과세자",
        "무주택 1인가구 세입자",
        "자녀에게 자산을 물려주려는 부모 세대",
    ),
}

_PERSONA_PROMPT_TEMPLATE = """[이번 글의 타깃 상황 - 제목과 사례 설정에 반영]
오늘 글은 특히 "{persona}"인 독자가 자신의 이야기라고 느끼도록 제목·도입부·사례를
구성하세요. 단, 이는 글의 관점일 뿐입니다:
- 제도 자체의 전국 공통 기준(금액/소득/세율/기한)만 다루고, 이 상황에만 해당하는
  별도 지자체 기준이나 특례가 있다고 지어내지 마세요.
- 페르소나 사례 인물(합격/불합격 비교 등)의 이름과 구체 설정은 이 상황에 맞게
  자연스럽게 바꾸되, 수치는 시스템 프롬프트의 정확성 규칙을 그대로 따르세요.
- [중요 - 최근 발행한 글 제목 목록]과 타깃이 겹치더라도, 접근 각도(이번엔 이 상황
  특유의 고민 지점)를 다르게 하면 됩니다.

"""


def _history_path(site: str):
    return OUTPUT_DIR / f"persona_history_{site}.json"


def _load_history(site: str) -> List[str]:
    try:
        data = json.loads(_history_path(site).read_text(encoding="utf-8"))
        return [p for p in data if p in SITE_PERSONAS.get(site, ())]
    except (OSError, ValueError):
        return []


def pick_persona(site: str, forced: Optional[str] = None) -> str:
    choices = SITE_PERSONAS.get(site, ())
    if not choices:
        return ""
    if forced in choices:
        return forced
    recent = _load_history(site)[-_AVOID_RECENT:]
    candidates = [p for p in choices if p not in recent] or list(choices)
    return random.choice(candidates)


def record_persona(site: str, persona: str) -> None:
    if not persona:
        return
    history = _load_history(site)
    history.append(persona)
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        _history_path(site).write_text(json.dumps(history[-20:], ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.info("페르소나 히스토리 저장 실패(무시): %s", exc)


def format_persona_prompt(persona: str) -> str:
    if not persona:
        return ""
    return _PERSONA_PROMPT_TEMPLATE.format(persona=persona)
