"""LLM 호출의 단일 관문: 비용 가드 + 호출별 사용량 로그 + 배치(50% 할인) + 폭주 방지.

모든 Claude 호출은 call_message()를 거친다. 호출 직전에 오늘 누적 사용량을 검사해서 일일 예산,
일일 호출 수, 사이트별 일일 생성 수 중 하나라도 넘으면 API를 부르지 않고 LLMGuardError를 던진다
(스케줄 중복 실행·재시도 루프·수집 데이터 폭주 같은 버그가 비용으로 번지는 것을 막는 안전장치).

사용량은 data/output/api_usage.jsonl에 한 줄 JSON으로 쌓이고, `python main.py usage`로 요약해 볼 수 있다.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config import OUTPUT_DIR, settings
from utils.logger import get_logger

logger = get_logger(__name__)

USAGE_LOG = OUTPUT_DIR / "api_usage.jsonl"

# USD / 1M tokens (표준 단가). 캐시 읽기 0.1배, 캐시 쓰기(5분) 1.25배, 배치 0.5배.
PRICES: Dict[str, tuple] = {
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
}
_UNKNOWN_MODEL_PRICE = (5.0, 25.0)  # 모르는 모델은 비싸게 잡아서 예산 가드가 더 일찍 걸리게 한다


class LLMGuardError(RuntimeError):
    """비용 가드(일일 예산/호출 수/생성 수/프롬프트 크기)에 걸려 API 호출을 하지 않았을 때."""


def estimate_cost(model: str, usage: Any, batch: bool = False) -> float:
    price_in, price_out = PRICES.get(model, _UNKNOWN_MODEL_PRICE)
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cost = (
        inp * price_in
        + out * price_out
        + cache_read * price_in * 0.1
        + cache_write * price_in * 1.25
    ) / 1_000_000
    return cost * (0.5 if batch else 1.0)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _read_records(date: Optional[str] = None, days: int = 1) -> List[Dict[str, Any]]:
    if not USAGE_LOG.exists():
        return []
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat()
    records: List[Dict[str, Any]] = []
    try:
        for line in USAGE_LOG.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            rec_date = rec.get("date", "")
            if (date and rec_date == date) or (not date and rec_date >= cutoff):
                records.append(rec)
    except OSError:
        return []
    return records


def _append(record: Dict[str, Any]) -> None:
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("사용량 로그 기록 실패(무시): %s", exc)


def record_usage(
    purpose: str,
    model: str,
    usage: Any,
    *,
    site: Optional[str] = None,
    batch: bool = False,
    stop_reason: Optional[str] = None,
    seconds: float = 0.0,
    request_id: str = "",
) -> float:
    cost = estimate_cost(model, usage, batch)
    _append(
        {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "date": _today(),
            "kind": "llm",
            "purpose": purpose,
            "site": site,
            "model": model,
            "batch": batch,
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            "cost_usd": round(cost, 5),
            "stop_reason": stop_reason,
            "seconds": round(seconds, 1),
            "request_id": request_id,
        }
    )
    logger.info(
        "[LLM] %s%s site=%s model=%s in=%s out=%s cost=$%.4f%s",
        purpose,
        " (batch)" if batch else "",
        site or "-",
        model,
        getattr(usage, "input_tokens", 0),
        getattr(usage, "output_tokens", 0),
        cost,
        f" stop={stop_reason}" if stop_reason and stop_reason != "end_turn" and stop_reason != "tool_use" else "",
    )
    return cost


def today_totals() -> Dict[str, Any]:
    records = [r for r in _read_records(_today()) if r.get("kind") == "llm"]
    return {
        "calls": len(records),
        "cost": sum(r.get("cost_usd", 0.0) for r in records),
        "records": records,
    }


def check_budget(purpose: str, site: Optional[str] = None) -> None:
    """오늘 누적이 한도를 넘었으면 LLMGuardError. 호출 직전에 항상 부른다."""
    totals = today_totals()
    if totals["cost"] >= settings.llm_daily_budget_usd:
        raise LLMGuardError(
            f"일일 LLM 예산 초과: 오늘 ${totals['cost']:.2f} / 한도 ${settings.llm_daily_budget_usd:.2f} "
            "(LLM_DAILY_BUDGET_USD로 조정). 호출을 중단합니다."
        )
    if totals["calls"] >= settings.llm_max_calls_per_day:
        raise LLMGuardError(
            f"일일 LLM 호출 수 초과: 오늘 {totals['calls']}회 / 한도 {settings.llm_max_calls_per_day}회 "
            "(LLM_MAX_CALLS_PER_DAY로 조정). 호출을 중단합니다."
        )
    if purpose == "generate" and site:
        generations = sum(
            1 for r in totals["records"] if r.get("purpose") == "generate" and r.get("site") == site
        )
        if generations >= settings.llm_max_generations_per_site_per_day:
            raise LLMGuardError(
                f"Site {site}의 오늘 글 생성 {generations}회 - 한도 {settings.llm_max_generations_per_site_per_day}회 "
                "초과(LLM_MAX_GENERATIONS_PER_SITE_PER_DAY로 조정). 중복 실행/루프를 의심하세요."
            )


def _prompt_chars(params: Dict[str, Any]) -> int:
    return sum(
        len(json.dumps(params.get(key, ""), ensure_ascii=False)) for key in ("system", "messages", "tools")
    )


def _run_batch(client: Any, params: Dict[str, Any], purpose: str) -> Optional[Any]:
    """요청 1건짜리 배치를 만들어 결과 Message를 돌려준다. 실패/시간초과면 None(호출부가 일반 호출로 폴백)."""
    custom_id = f"{purpose}-{uuid.uuid4().hex[:8]}"
    try:
        batch = client.messages.batches.create(requests=[{"custom_id": custom_id, "params": params}])
    except Exception as exc:  # noqa: BLE001
        logger.warning("[LLM] 배치 생성 실패 - 일반 호출로 폴백: %s", exc)
        return None

    deadline = time.time() + settings.llm_batch_timeout_seconds
    delay = 5.0
    ended = False
    while time.time() < deadline:
        try:
            batch = client.messages.batches.retrieve(batch.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LLM] 배치 상태 조회 실패(재시도): %s", exc)
        else:
            if batch.processing_status == "ended":
                ended = True
                break
        time.sleep(delay)
        delay = min(delay * 1.5, 30.0)

    if not ended:
        logger.warning("[LLM] 배치가 %ss 안에 안 끝나 취소하고 일반 호출로 폴백합니다.", settings.llm_batch_timeout_seconds)
        try:
            client.messages.batches.cancel(batch.id)
            for _ in range(18):  # 취소 직전에 이미 처리됐을 수 있어 결과를 최대 90초 더 확인
                time.sleep(5)
                batch = client.messages.batches.retrieve(batch.id)
                if batch.processing_status == "ended":
                    break
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LLM] 배치 취소 중 오류(무시): %s", exc)

    try:
        for result in client.messages.batches.results(batch.id):
            if result.custom_id == custom_id and result.result.type == "succeeded":
                return result.result.message
            if result.custom_id == custom_id:
                logger.warning("[LLM] 배치 결과 %s - 일반 호출로 폴백", result.result.type)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[LLM] 배치 결과 조회 실패 - 일반 호출로 폴백: %s", exc)
    return None


def call_message(
    client: Any,
    *,
    purpose: str,
    site: Optional[str] = None,
    use_batch: bool = False,
    **params: Any,
) -> Any:
    """가드 검사 -> (배치 시도 ->) 일반 호출 -> 사용량 기록. 반환값은 anthropic Message."""
    check_budget(purpose, site)

    size = _prompt_chars(params)
    if size > settings.llm_max_prompt_chars:
        raise LLMGuardError(
            f"프롬프트가 비정상적으로 큽니다({size:,}자 > {settings.llm_max_prompt_chars:,}자). "
            "수집 데이터 폭주를 의심해 호출을 중단합니다(LLM_MAX_PROMPT_CHARS로 조정)."
        )

    model = params.get("model", "")
    started = time.time()
    message = None
    batched = False
    if use_batch and settings.llm_use_batch:
        message = _run_batch(client, params, purpose)
        batched = message is not None
    if message is None:
        message = client.messages.create(**params)

    record_usage(
        purpose,
        model,
        getattr(message, "usage", None),
        site=site,
        batch=batched,
        stop_reason=getattr(message, "stop_reason", None),
        seconds=time.time() - started,
        request_id=getattr(message, "id", ""),
    )
    return message


# ---------------------------------------------------------------------------
# 이미지 생성 비용 가드 (Gemini/Flux 유료 생성만 횟수를 센다)
# ---------------------------------------------------------------------------
def image_generation_allowed() -> bool:
    count = sum(1 for r in _read_records(_today()) if r.get("kind") == "image")
    if count >= settings.image_max_per_day:
        logger.warning("[IMG] 일일 유료 이미지 생성 한도(%s) 도달 - 무료 폴백만 사용합니다.", settings.image_max_per_day)
        return False
    return True


def record_image(source: str, site: Optional[str] = None) -> None:
    _append(
        {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "date": _today(),
            "kind": "image",
            "source": source,
            "site": site,
        }
    )


# ---------------------------------------------------------------------------
# CLI 요약 (python main.py usage)
# ---------------------------------------------------------------------------
def format_summary(days: int = 7) -> str:
    records = _read_records(days=days)
    if not records:
        return "사용량 기록이 없습니다."
    by_day: Dict[str, Dict[str, float]] = {}
    by_purpose: Dict[str, Dict[str, float]] = {}
    for rec in records:
        day = by_day.setdefault(rec["date"], {"calls": 0, "cost": 0.0, "images": 0})
        if rec.get("kind") == "image":
            day["images"] += 1
            continue
        day["calls"] += 1
        day["cost"] += rec.get("cost_usd", 0.0)
        purpose = by_purpose.setdefault(rec.get("purpose", "?"), {"calls": 0, "cost": 0.0})
        purpose["calls"] += 1
        purpose["cost"] += rec.get("cost_usd", 0.0)
    lines = [f"최근 {days}일 LLM 사용량 (일일 한도 ${settings.llm_daily_budget_usd:.2f}, 호출 {settings.llm_max_calls_per_day}회)"]
    for day in sorted(by_day):
        d = by_day[day]
        lines.append(f"  {day}  호출 {int(d['calls'])}회  ${d['cost']:.3f}  이미지(유료) {int(d['images'])}장")
    lines.append("용도별:")
    for name, p in sorted(by_purpose.items(), key=lambda kv: -kv[1]["cost"]):
        lines.append(f"  {name:<18} {int(p['calls'])}회  ${p['cost']:.3f}")
    lines.append(f"합계 ${sum(d['cost'] for d in by_day.values()):.3f}")
    return "\n".join(lines)
