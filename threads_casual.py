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
MAX_CHARS = 120
POOL_STYLE = "human-v2"  # 말투 규칙을 바꾸면 올려서 예전 말투로 쌓아 둔 글을 버린다
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

HUMAN_EXAMPLES = (
    "[말투 참고 - 이런 느낌으로, 내용은 베끼지 말 것]\n"
    "통신비 고지서 또 올랐네\n"
    "이 돈이면 치킨이 몇 마리냐 ㅋㅋ\n\n"
    "월급날인데 통장은 구경만 하고 지나감 ㅠㅠ\n\n"
    "연말정산 얘기가 벌써 나오네\n"
    "토해내는 쪽일지 받는 쪽일지부터 궁금함\n\n"
    "보일러 켜기 전에 한참 고민하는 계절...\n\n"
    "핸드폰 요금제 몇 년째 그대로인 사람 은근 많을걸\n"
    "나도 그랬음 ㅎㅎ"
)

SYSTEM_PROMPT = (
    "당신은 정부지원금·세금/연금·통신비 절약 주제의 스레드 계정을 운영하는 평범한 사람입니다. "
    "링크나 홍보 없이 올리는 짧은 혼잣말 글을 씁니다. AI가 쓴 글처럼 보이면 실패입니다. 반드시 지킬 것:\n"
    "1) 친구한테 카톡하듯 쓰는 반말 구어체입니다. 문장을 깔끔하게 끝맺지 말고, 말끝을 흐리거나(~네, ~더라, ~는데, ~ㅋㅋ, ~...) "
    "생각나는 대로 툭 던집니다. 어미는 글마다 다르게 쓰고 '~임', '~인 듯'을 반복하지 않습니다.\n"
    "2) 한 장면이나 한 가지 감정만 씁니다(고지서를 연 순간, 월급날 통장, 마트 계산대, 환절기 난방비 같은 것). "
    "정보를 정리해 주거나 교훈·결론·요약으로 끝내지 않습니다. 설명하려 들지 마세요.\n"
    "3) 'ㅋㅋ', 'ㅎㅎ', 'ㅠㅠ', '...' 같은 표현을 글의 절반쯤에만 자연스럽게 섞습니다(전부에 넣으면 부자연스럽습니다). "
    "마침표는 거의 찍지 않고 느낌표는 쓰지 않습니다. 이모지는 쓰지 않습니다.\n"
    "4) '~해보세요', '~하세요', '알아두면 좋은', '꿀팁', '필수', '놓치지 마', '총정리', '꼭 확인' 같은 안내문·광고 말투와 "
    "존댓말은 쓰지 않습니다.\n"
    "5) 기분·반응(어이없다, 막막하다, 귀찮다, 궁금하다)은 자연스럽게 써도 됩니다. 하지만 '신청해서 받았다', '얼마 절약했다' 같은 "
    "구체적인 결과 후기나 지어낸 사건, 금액·소득 기준·제도 조건·날짜 단정은 쓰지 않습니다(정보 계정이라 틀리면 안 됩니다).\n"
    "6) URL, 해시태그, 구매·가입·신청 유도, 광고 문구는 금지합니다. '공감', '공감하면', '~하신 분?', '좋아요/팔로우/댓글' 같은 "
    "반응 요구 문구도 쓰지 않습니다.\n"
    f"7) 첫 줄은 {FIRST_LINE_MAX}자 안의 짧은 한 줄로 스크롤을 멈추게 합니다. 전체는 최대 {MAX_LINES}줄·{MAX_CHARS}자이고, 한두 줄로 끝나는 글도 섞습니다.\n"
    "8) 읽는 사람 누구나 '아 맞다 그거' 싶은 일상 소재(월급날, 공과금·통신비 고지서, 환절기, 연말정산 시즌, 장 볼 때 물가)만 씁니다.\n"
    "9) 서로 겹치는 문장·표현은 쓰지 않고, 이미 쓴 글 목록과 비슷한 글은 피합니다. 열 개가 같은 틀(질문으로 끝나기 등)이 되지 않게 "
    "길이·어조·구조를 서로 다르게 합니다.\n\n"
    + HUMAN_EXAMPLES
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
    text = "\n".join(re.sub(r"(?<!\.)\.$", "", ln) for ln in lines)  # 줄 끝 마침표는 사람이 잘 안 찍는다
    if re.search(r"공감|스푼|하신\s*분|손\s*들어|좋아요|팔로우|댓글", text):  # 공감·반응을 요구하는 문구
        return None
    if re.search(r"습니다|니다[.!?\s]|세요|까요|나요|에요|예요|꿀팁|알아두|놓치지|총정리|꼭\s*확인|필수|해보자|해봐요", text):  # 존댓말·안내문·광고 말투
        return None
    if text.count("!") >= 2 or re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", text):  # 느낌표 남발·이모지
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
    if bank.get("style") != POOL_STYLE:
        bank["pool"] = []
        bank["style"] = POOL_STYLE
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
