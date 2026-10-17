"""기준 연도 자동 갱신 - 해가 바뀌면(또는 12/20부터) 서버가 스스로 새 연도 기준을 조사해 팩트 시트를 갱신한다.

사람이 묻지 않아도 돌아가도록 만들었지만, 틀린 숫자가 글에 나가는 것이 가장 큰 위험이라 안전장치를 겹쳐 둔다.
1. 조사는 정부 공식 사이트(go.kr / or.kr 계열)만 검색하도록 도메인을 제한한다(블로그끼리 숫자가 엇갈리던 문제 방지).
2. 코드로 검증을 통과한 것만 반영한다: 구조 유지, 새 연도 표기, 바뀐 수치마다 공식 출처 URL, 수치 변화폭 상식 범위.
3. 새 연도 값을 못 찾으면(아직 미발표) 반영하지 않는다 - 이때 fact_sheets.get_fact_sheet가 "N년 기준, 올해와 다를 수 있음"
   주의문을 자동으로 붙여, 글이 옛 수치를 올해 기준인 것처럼 단정하지 않는다.
4. 반영/실패/미발표를 텔레그램으로 요약해 알리고, 모든 변경은 data/output/fact_overrides.json에만 쓴다(원본 코드는 그대로).

비용: 시트당 약 $0.1~0.2(웹 검색 포함), 하루 최대 5개·일일 비용 소프트 한도 $0.8. 44개를 한 번 갱신하는 데 약 $5~8.
기준 중위소득은 따로 조사해 data/output/standards.json에 저장한다(허브 판정 규칙이 읽는다).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from config import OUTPUT_DIR, settings
from constants import CLAUDE_MODEL
from fact_sheets import _FACT_SHEETS, base_sheet_text, iter_sheets, load_overrides, sheet_key, year_of
from llm_usage import LLMGuardError, call_message, today_totals
from utils.logger import get_logger

logger = get_logger(__name__)

KST = timezone(timedelta(hours=9))
OVERRIDE_PATH = OUTPUT_DIR / "fact_overrides.json"
STATE_PATH = OUTPUT_DIR / "standards_state.json"
STANDARDS_PATH = OUTPUT_DIR / "standards.json"

MAX_SHEETS_PER_RUN = 5
DAILY_SOFT_CAP_USD = 0.8
MAX_SEARCHES = 6

OFFICIAL_HOSTS = [
    "mohw.go.kr", "bokjiro.go.kr", "korea.kr", "nts.go.kr", "hometax.go.kr", "moel.go.kr", "work24.go.kr", "hrd.go.kr",
    "nps.or.kr", "nhis.or.kr", "moe.go.kr", "molit.go.kr", "myhome.go.kr", "mogef.go.kr", "moef.go.kr", "gov.kr",
    "kosaf.go.kr", "law.go.kr", "kcomwel.or.kr", "fss.or.kr", "kftc.or.kr", "kepco.co.kr", "energyvoucher.or.kr",
]
_OFFICIAL_SUFFIXES = tuple("." + h for h in OFFICIAL_HOSTS) + tuple(OFFICIAL_HOSTS)
# 허브에서 쓰는 순서대로 먼저 갱신한다
PRIORITY = [
    "근로장려금", "기초연금", "청년월세", "부모급여", "아동수당", "생계급여", "주거급여", "의료급여", "교육급여", "에너지바우처",
    "한부모", "국민취업지원제도", "국민내일배움카드", "임신·출산", "월세 세액공제", "자녀 세액공제", "연금저축", "ISA", "중소기업 취업청년",
]

WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": MAX_SEARCHES,
    "allowed_domains": OFFICIAL_HOSTS,
}

SYSTEM_PROMPT = (
    "당신은 한국 복지·세금 제도의 연도별 기준을 확인하는 사실 점검 담당입니다. 주어진 '사실 메모'를 새 연도 기준으로 "
    "갱신하되, 정부 공식 사이트(검색 도구가 이미 공식 도메인만 허용함)에서 확인된 내용만 반영합니다. 추측·계산으로 지어낸 "
    "수치는 절대 넣지 않습니다. 확인하지 못한 것은 바꾸지 말고 '확인 불가'로 보고하세요. 최종 응답은 JSON 객체 하나뿐이며 "
    "다른 글을 붙이지 않습니다."
)


def _now() -> datetime:
    return datetime.now(KST)


def target_year(now: Optional[datetime] = None) -> int:
    now = now or _now()
    return now.year + 1 if now.month == 12 else now.year


def in_window(now: Optional[datetime] = None) -> bool:
    """12/20 ~ 3/31 은 매일, 그 밖에는 월요일에만(미발표로 남은 시트의 재시도) 점검한다."""
    now = now or _now()
    return (now.month == 12 and now.day >= 20) or now.month in (1, 2, 3) or now.weekday() == 0


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(path, data) -> None:
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.warning("기준 갱신 파일 저장 실패: %s", exc)


def _notify(text: str) -> None:
    try:
        from utils.telegram_notify import send_message_sync

        send_message_sync(text)
    except Exception as exc:  # noqa: BLE001
        logger.info("기준 갱신 알림 전송 실패(무시): %s", exc)


# ---------------------------------------------------------------------------
# 검증
# ---------------------------------------------------------------------------
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _first_number(text: str) -> Optional[float]:
    match = _NUM_RE.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _is_official(url: str) -> bool:
    host = (urlparse(url or "").hostname or "").lower()
    return bool(host) and any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS)


def validate_update(old_text: str, result: Dict[str, Any], year: int) -> Optional[str]:
    """통과하면 None, 아니면 거절 사유(문자열)."""
    status = result.get("status")
    if status != "updated":
        return f"status={status}"
    new_text = result.get("text") or ""
    if not isinstance(new_text, str) or not new_text.strip():
        return "본문 없음"
    if year_of(new_text) != year:
        return f"새 본문의 기준 연도가 {year}년이 아님"
    if not new_text.lstrip().startswith("[검증된 사실 메모"):
        return "머리말 형식이 깨짐"
    if "[금지]" not in new_text:
        return "[금지] 절이 사라짐"
    ratio = len(new_text) / max(1, len(old_text))
    if not 0.6 <= ratio <= 1.6:
        return f"본문 길이 변화가 큼({ratio:.2f}배)"
    changes = result.get("changes") or []
    if not isinstance(changes, list):
        return "changes 형식 오류"
    if not changes and new_text.strip() != old_text.strip() and _numbers_differ(old_text, new_text):
        return "수치가 바뀌었는데 changes가 없음"
    for ch in changes:
        if not isinstance(ch, dict):
            return "changes 항목 형식 오류"
        if not _is_official(str(ch.get("source", ""))):
            return f"공식 출처가 없는 변경: {str(ch.get('fact', ''))[:30]}"
        old_n, new_n = _first_number(str(ch.get("old", ""))), _first_number(str(ch.get("new", "")))
        if old_n and new_n and not 0.4 <= new_n / old_n <= 2.5:
            return f"수치 변화폭이 비정상: {ch.get('old')} -> {ch.get('new')}"
    return None


def _numbers_differ(a: str, b: str) -> bool:
    strip = lambda t: re.sub(r"\d{4}년 기준", "", t)  # noqa: E731
    return sorted(_NUM_RE.findall(strip(a))) != sorted(_NUM_RE.findall(strip(b)))


# ---------------------------------------------------------------------------
# 조사 호출
# ---------------------------------------------------------------------------
def _client():
    if not settings.anthropic_api_key:
        return None
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=1)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except ValueError:
        return None


def _ask(client: Any, user_prompt: str) -> Optional[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = [{"role": "user", "content": user_prompt}]
    response = None
    for _ in range(4):  # 서버 도구(웹 검색)가 한 턴을 일시중지(pause_turn)하면 이어서 진행한다
        response = call_message(
            client,
            purpose="policy_update",
            model=CLAUDE_MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            tools=[WEB_SEARCH_TOOL],
            thinking={"type": "disabled"},
            messages=messages,
        )
        if getattr(response, "stop_reason", None) != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": response.content}]
    if response is None:
        return None
    text = "".join(getattr(b, "text", "") for b in response.content if getattr(b, "type", None) == "text")
    return _extract_json(text)


def research_sheet(client: Any, key: str, old_text: str, year: int) -> Optional[Dict[str, Any]]:
    prompt = f"""[갱신 대상] {key}
[목표 기준 연도] {year}년

아래 '현재 사실 메모'는 {year_of(old_text)}년 기준입니다. {year}년 기준으로 바뀐 내용이 있는지 공식 사이트에서 찾아, 메모를 갱신하세요.

규칙:
- 메모의 각 사실(금액·비율·소득/재산 기준·한도·신청 시기·대상)을 {year}년 기준으로 확인합니다. 공식 자료에서 확인된 값만 반영합니다.
- 확인했더니 그대로인 항목은 원문 그대로 둡니다. 바뀐 항목만 고칩니다.
- {year}년 값이 아직 발표되지 않았거나 공식 사이트에서 확인되지 않으면 그 항목은 바꾸지 말고 unresolved에 적습니다. 그런 항목이 메모의 핵심 수치라면 전체를 갱신하지 말고 status를 "not_available"로 하세요.
- 새 본문의 첫 줄 형식, "[금지]" 절, 항목 구조는 그대로 유지합니다. 머리말의 연도만 {year}년으로 바꿉니다. 원문에 없던 새 수치를 임의로 추가하지 마세요(공식 자료에서 확인한 것만 추가 가능).
- 개정이 '확정'이 아니라 '개정안/논의 중'이면 반영하지 말고 unresolved에 적습니다.

반드시 아래 JSON 하나만 출력하세요:
{{"status": "updated" | "not_available" | "unchanged",
  "text": "갱신된 사실 메모 전문(updated일 때만)",
  "changes": [{{"fact": "무엇이", "old": "예전 값", "new": "새 값", "source": "공식 출처 URL"}}],
  "unresolved": ["확인하지 못한 항목"]}}

[현재 사실 메모]
{old_text}
"""
    return _ask(client, prompt)


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
def _due_sheets(year: int, state: Dict[str, Any], today: str) -> List[tuple]:
    due = []
    for key, tokens, text in iter_sheets():
        sy = year_of(text)
        if not sy or sy >= year:
            continue
        info = state.get(key, {})
        if info.get("last_try") == today:
            continue
        due.append((key, tokens, text))

    def rank(item):
        name = item[0]
        return next((i for i, p in enumerate(PRIORITY) if p in name or name in p), len(PRIORITY))

    return sorted(due, key=rank)


def run_update(now: Optional[datetime] = None, force: bool = False, only: Optional[str] = None, dry: bool = False) -> Dict[str, Any]:
    now = now or _now()
    year = target_year(now)
    today = now.date().isoformat()
    state = _load(STATE_PATH, {})
    due = _due_sheets(year, state, today)
    if only:
        due = [d for d in due if only in d[0]] or [(k, t, x) for k, t, x in iter_sheets() if only in k]
    result = {"year": year, "due": len(due), "updated": [], "not_available": [], "failed": [], "skipped_budget": False}
    if not due:
        return result
    if not force and not in_window(now):
        return result
    client = None if dry else _client()
    if not dry and client is None:
        logger.warning("ANTHROPIC_API_KEY가 없어 기준 갱신을 건너뜁니다.")
        return result

    overrides = load_overrides()
    for key, tokens, text in due[:MAX_SHEETS_PER_RUN]:
        if not dry and today_totals()["cost"] >= DAILY_SOFT_CAP_USD:
            result["skipped_budget"] = True
            break
        info = state.setdefault(key, {})
        info["last_try"] = today
        info["tries"] = int(info.get("tries", 0)) + 1
        if dry:
            result["not_available"].append(key)
            continue
        try:
            data = research_sheet(client, key, text, year)
        except LLMGuardError as exc:
            logger.warning("기준 갱신 중단(LLM 가드): %s", exc)
            result["skipped_budget"] = True
            break
        except Exception as exc:  # noqa: BLE001 - 한 시트 실패가 나머지를 막지 않게
            logger.warning("기준 갱신 조사 실패(%s): %s", key, exc)
            info["last_status"] = f"error: {str(exc)[:80]}"
            result["failed"].append(key)
            continue
        if not data:
            info["last_status"] = "응답 파싱 실패"
            result["failed"].append(key)
            continue
        if data.get("status") in ("not_available", "unchanged"):
            info["last_status"] = data.get("status")
            result["not_available"].append(key)
            continue
        reason = validate_update(text, data, year)
        if reason:
            info["last_status"] = f"검증 거절: {reason}"
            result["failed"].append(f"{key}({reason})")
            logger.warning("기준 갱신 검증 거절(%s): %s", key, reason)
            continue
        overrides[key] = {
            "year": year,
            "text": data["text"],
            "changes": data.get("changes", []),
            "unresolved": data.get("unresolved", []),
            "updated_at": now.isoformat(timespec="seconds"),
        }
        _save(OVERRIDE_PATH, overrides)
        info["last_status"] = "updated"
        result["updated"].append(key)
        if any(p in key or key in p for p in PRIORITY):  # 허브 제도는 새 수치로 글을 한 번 다시 쓴다
            from topic_planner import add_refresh

            add_refresh(key)
        lines = "\n".join(
            f"· {str(c.get('fact', ''))[:40]}: {str(c.get('old', ''))[:20]} → {str(c.get('new', ''))[:20]}"
            for c in (data.get("changes") or [])[:6]
        )
        _notify(f"✅ <b>[기준 자동 갱신]</b> {key} → {year}년 기준\n{lines or '(수치 변경 없음, 연도만 갱신)'}")
    _save(STATE_PATH, state)

    remaining = len([1 for _, _, x in iter_sheets() if (year_of(x) or year) < year])
    if result["updated"] or result["failed"] or result["not_available"]:
        _notify(
            f"🗂 <b>[기준 갱신 요약] {year}년</b>\n갱신 {len(result['updated'])} / 미발표·변경없음 {len(result['not_available'])} / "
            f"검증 거절·실패 {len(result['failed'])} / 남은 시트 {remaining}개\n"
            + ("거절·실패: " + ", ".join(result["failed"][:6]) + "\n" if result["failed"] else "")
            + "갱신되지 않은 시트는 글에서 수치를 단정하지 않도록 자동으로 '옛 기준' 주의문이 붙습니다."
        )
    return result


# ---------------------------------------------------------------------------
# 기준 중위소득(허브 판정 규칙이 쓰는 표)
# ---------------------------------------------------------------------------
def validate_median(current: Dict[str, Any], new: Dict[str, Any]) -> Optional[str]:
    try:
        vals = [int(new["median"][str(i)]) for i in range(1, 7)]
    except (KeyError, TypeError, ValueError):
        return "가구원 1~6인 값이 모두 필요함"
    if any(b <= a for a, b in zip(vals, vals[1:])):
        return "가구원 수가 늘수록 커져야 함"
    if not 1_500_000 < vals[0] < 5_000_000:
        return "1인 가구 값이 비정상"
    ratio4 = vals[3] / vals[0]
    if not 2.3 <= ratio4 <= 2.8:
        return f"4인/1인 비율({ratio4:.2f})이 비정상"
    if current.get("median"):
        prev = int(current["median"]["1"])
        if not 1.0 <= vals[0] / prev <= 1.15:
            return f"전년 대비 인상률이 비정상({vals[0] / prev:.3f}배)"
    if not _is_official(str(new.get("source", ""))):
        return "공식 출처 없음"
    return None


def update_median(now: Optional[datetime] = None, dry: bool = False) -> Optional[Dict[str, Any]]:
    now = now or _now()
    year = target_year(now)
    current = _load(STANDARDS_PATH, {"year": 2026, "median": {"1": 2564238, "2": 4199292, "3": 5359036, "4": 6494738, "5": 7556719, "6": 8555952}})
    if current.get("year", 0) >= year or dry:
        return None
    client = _client()
    if client is None:
        return None
    prompt = (
        f"{year}년 기준 중위소득(보건복지부 고시)의 가구원수별 월 금액(원)을 공식 사이트에서 찾아 JSON 하나로만 답하세요.\n"
        '{"status": "updated" | "not_available", "year": ' + str(year) + ', "median": {"1": 정수, "2": 정수, "3": 정수, "4": 정수, "5": 정수, "6": 정수}, "source": "공식 출처 URL"}\n'
        f"{year}년 값이 아직 확정·발표되지 않았다면 status를 not_available로 하고 추측하지 마세요."
    )
    try:
        data = _ask(client, prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("중위소득 조사 실패: %s", exc)
        return None
    if not data or data.get("status") != "updated":
        return None
    reason = validate_median(current, data)
    if reason:
        logger.warning("중위소득 검증 거절: %s", reason)
        _notify(f"⚠️ 기준 중위소득 자동 갱신 검증 거절: {reason}")
        return None
    out = {"year": year, "median": {k: int(v) for k, v in data["median"].items()}, "source": data["source"], "updated_at": now.isoformat(timespec="seconds")}
    _save(STANDARDS_PATH, out)
    _notify(f"✅ <b>[기준 중위소득 자동 갱신]</b> {year}년: 1인 {out['median']['1']:,}원 / 4인 {out['median']['4']:,}원")
    return out


def run_daily() -> None:
    """데몬이 하루 한 번 부른다(토큰은 갱신할 시트가 있을 때만 쓴다)."""
    try:
        if in_window():
            update_median()
        run_update()
    except Exception as exc:  # noqa: BLE001
        logger.warning("기준 자동 갱신 중 오류(무시): %s", exc)
