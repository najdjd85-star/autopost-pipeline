"""스레드 일상 글 - 링크만 올리는 계정으로 보이지 않게 가끔 섞는 짧은 글.

링크 없는 가벼운 글(계절 환기, 질문, 한 줄 팁, 퀴즈)을 Haiku로 한 번에 여러 개 만들어 은행에 쌓아 두고,
하루 1건 이하·며칠에 한 번 빠지는 식으로 무작위 시각에 올린다(예약/시간대/차단기는 threads_guard가 맡는다).

정보·금융 계정이라 신뢰가 중요하고 Meta 정책상 가짜 경험담은 위험하다. 그래서 프롬프트로 다음을 강제한다:
- "내가 해봤다/겪었다" 같은 지어낸 개인 경험 금지, 구체 수치·금액·제도 내용 단정 금지, 링크/홍보/구매 유도 금지.
- 계절·시기 관찰, 가벼운 질문, 일반적인 상식 팁, 퀴즈처럼 거짓이 될 수 없는 내용만.
코드에서도 URL/해시태그 남발/지나치게 긴 글은 걸러낸다. 생성 비용은 은행 채울 때 1회(약 $0.003, Haiku).
"""
from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config import OUTPUT_DIR, settings
from llm_usage import LLMGuardError, call_message
from utils.logger import get_logger

logger = get_logger(__name__)

BANK_PATH = OUTPUT_DIR / "threads_casual_bank.json"
MODEL = os.environ.get("THREADS_CASUAL_MODEL", "claude-haiku-5-5")
REFILL_BELOW = 3
BATCH_SIZE = 10
HISTORY_KEEP = 60
SKIP_CHANCE = 0.25  # 일정하게 올리면 오히려 봇처럼 보여서 가끔 건너뛴다
MIN_HOURS_BETWEEN = 20
MAX_CHARS = 140
FIRST_LINE_MAX = 32  # 첫 줄은 짧고 세게
MAX_LINES = 4
KST = timezone(timedelta(hours=9))

TOOL = {
    "name": "submit_casual_posts",
    "description": "스레드에 올릴 가벼운 일상 글 목록을 제출한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "posts": {
                "type": "array",
                "items": {"type": "string"},
                "description": f"일상 글 {BATCH_SIZE}개. 각각 첫 줄이 짧고 임팩트 있는 글(첫 줄 {FIRST_LINE_MAX}자 이내, 전체 최대 {MAX_LINES}줄·{MAX_CHARS}자).",
            }
        },
        "required": ["posts"],
    },
}

SYSTEM_PROMPT = (
    "당신은 정부지원금·세금/연금·통신비 절약 정보를 다루는 스레드 계정의 에디터입니다. "
    "링크나 홍보 없이 올리는 가벼운 일상 글을 씁니다. 반드시 지킬 것:\n"
    "1) 말투는 반말체 독백(~더라, ~임, ~인 듯, ~할 때 됐음)이고 존댓말·훈계·명령형은 쓰지 않습니다.\n"
    "2) '내가 해봤는데', '어제 겪었는데' 같은 지어낸 개인 경험·후기는 금지합니다. 계절·시기 관찰, 가벼운 질문, "
    "누구나 아는 일반 상식 팁, 퀴즈처럼 사실과 어긋날 수 없는 내용만 씁니다.\n"
    "3) 구체적인 금액·소득 기준·제도 조건·날짜를 단정하지 마세요(틀릴 수 있음). 제도 이름은 언급해도 되지만 내용은 일반론으로.\n"
    "4) URL, 해시태그 3개 이상, 이모지 남발, 구매·가입·신청 유도, 광고 문구는 금지합니다.\n"
    "5) 형식은 계절 환기, 가벼운 질문, 한 줄 생각, 미니 팁을 섞습니다.\n"
    "6) 서로 겹치는 문장·표현을 쓰지 말고, 이미 쓴 글 목록과 비슷한 글은 피합니다.\n"
    f"7) 첫 줄이 승부입니다: 첫 줄은 {FIRST_LINE_MAX}자 안의 짧고 임팩트 있는 한 줄로, 스크롤을 멈추게 할 만큼 '나도 그런데' 싶은 상황이나 의외의 관점을 던집니다. 그 뒤에 이어지는 말은 1~2줄만 짧게 덧붙입니다(전체 최대 {MAX_LINES}줄, {MAX_CHARS}자).\n"
    "8) 읽는 사람 누구나 '맞아 그렇지' 하고 고개를 끄덕일 일상 소재만 씁니다(월급날 통장, 공과금·통신비 고지서, 환절기, "
    "연말정산 시즌, 장 볼 때 물가 같은 것). 특정 상황에 사는 사람만 공감하는 얘기는 피합니다.\n"
    "9) '공감 한 스푼', '공감하면', '~하신 분?', '좋아요/팔로우/댓글 달아줘' 같은 공감·반응을 요구하는 문구와 "
    "공감이라는 단어 자체를 쓰지 않습니다. 담담하게 툭 던지는 말투로 씁니다."
)


def _season_hint(now: datetime) -> str:
    month = now.astimezone(KST).month
    hints = {
        (12, 1, 2): "겨울(난방비, 연말정산 준비, 연초)",
        (3, 4, 5): "봄(새 학기, 이사철, 종합소득세 신고 시즌)",
        (6, 7, 8): "여름(장마, 전기요금, 휴가철 로밍)",
        (9, 10, 11): "가을(환절기, 연말정산 준비 시작, 연금·난방비 걱정 시작)",
    }
    for months, text in hints.items():
        if month in months:
            return f"{month}월, {text}"
    return f"{month}월"


def _load_bank() -> Dict[str, Any]:
    try:
        bank = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        bank = {}
    bank.setdefault("pool", [])
    bank.setdefault("used", [])
    return bank


def _save_bank(bank: Dict[str, Any]) -> None:
    bank["used"] = bank["used"][-HISTORY_KEEP:]
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        BANK_PATH.write_text(json.dumps(bank, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.info("일상 글 은행 저장 실패(무시): %s", exc)


def clean_post(text: str) -> Optional[str]:
    """프롬프트를 어긴 글을 코드에서 한 번 더 거른다. 통과하면 정리된 글, 아니면 None."""
    text = (text or "").strip()
    if not text or len(text) > MAX_CHARS:
        return None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines or len(lines) > MAX_LINES or len(lines[0]) > FIRST_LINE_MAX:  # 첫 줄은 짧고 세게
        return None
    text = "\n".join(lines)
    if re.search(r"공감|스푼|하신\s*분|손\s*들어|좋아요|팔로우|댓글", text):  # 공감·반응을 요구하는 문구
        return None
    if re.search(r"https?://|www\.|\.com|\.kr", text, re.IGNORECASE):
        return None
    if len(re.findall(r"#\w+", text)) >= 3:
        return None
    if re.search(r"(내가|제가|나는)\s*(직접\s*)?(해봤|써봤|겪었|신청해봤|가입해봤)|어제\s*겪|며칠 전에 직접", text):
        return None  # 지어낸 개인 경험담
    if re.search(r"(신청|가입|구매|클릭|링크).{0,6}(하세요|하라|해라|해봐)", text):
        return None
    return text


def generate_bank(client: Any, now: Optional[datetime] = None, used: Optional[List[str]] = None) -> List[str]:
    """Haiku 한 번으로 일상 글 BATCH_SIZE개를 만들어 걸러서 돌려준다(예산/호출 수 가드 적용)."""
    now = now or datetime.now(timezone.utc)
    recent = "\n".join(f"- {t[:60]}" for t in (used or [])[-15:]) or "(없음)"
    response = call_message(
        client,
        purpose="threads_casual",
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": TOOL["name"]},
        thinking={"type": "disabled"},
        messages=[
            {
                "role": "user",
                "content": f"[지금 시기] {_season_hint(now)}\n[최근에 쓴 글 - 비슷한 건 피하기]\n{recent}\n\n"
                f"위 규칙에 맞는 일상 글 {BATCH_SIZE}개를 submit_casual_posts 도구로 제출하세요.",
            }
        ],
    )
    posts: List[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == TOOL["name"]:
            for raw in block.input.get("posts", []):
                cleaned = clean_post(str(raw))
                if cleaned and cleaned not in posts:
                    posts.append(cleaned)
    return posts


def _get_client() -> Any:
    if not settings.anthropic_api_key:
        return None
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=1)


def maybe_schedule_casual(now: Optional[datetime] = None, generate=None) -> Dict[str, Any]:
    """데몬이 주기적으로 부른다. 조건이 맞으면 일상 글 한 건을 예약한다.

    - 이미 예약된 일상 글이 있거나 마지막 게시가 20시간 이내면 건너뜀, 25% 확률로 그날은 건너뜀(불규칙하게).
    - 은행이 비어 가면 Haiku로 채움(예산 가드가 막으면 조용히 건너뜀).
    """
    import threads_guard as guard

    if os.environ.get("THREADS_CASUAL_ENABLED", "1") == "0":
        return {"status": "disabled"}
    now = now or datetime.now(timezone.utc)
    if guard.paused_until(now) or guard.casual_queued():
        return {"status": "skip", "reason": "paused_or_queued"}
    last = guard.last_casual_posted()
    if last and now - last < timedelta(hours=MIN_HOURS_BETWEEN):
        return {"status": "skip", "reason": "recent"}
    if random.random() < SKIP_CHANCE:
        return {"status": "skip", "reason": "random_skip"}

    bank = _load_bank()
    bank["pool"] = [p for p in bank["pool"] if clean_post(p)]  # 예전 말투(긴 글·공감 문구)로 쌓아 둔 글은 버린다
    if len(bank["pool"]) < REFILL_BELOW:
        try:
            make = generate or (lambda: generate_bank(_get_client(), now, bank["used"]))
            fresh = [p for p in make() if p not in bank["used"] and p not in bank["pool"]]
            bank["pool"].extend(fresh)
            logger.info("[Threads] 일상 글 은행 보충: +%s개", len(fresh))
        except LLMGuardError as exc:
            logger.warning("일상 글 생성 생략(LLM 가드): %s", exc)
        except Exception as exc:  # noqa: BLE001 - 선택 기능
            logger.warning("일상 글 생성 실패(무시): %s", exc)
    if not bank["pool"]:
        _save_bank(bank)
        return {"status": "skip", "reason": "empty_bank"}

    text = bank["pool"].pop(random.randrange(len(bank["pool"])))
    bank["used"].append(text)
    _save_bank(bank)
    return guard.enqueue_casual(text, now)
